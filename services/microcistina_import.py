"""
services/microcistina_import.py
Lectura del libro Excel "SOLVER MICROCISTINAS SAES" para importar una corrida
ELISA a la plataforma.

La plataforma RECALCULA con su propio motor (services/elisa_microcistina.py) a
partir de las absorbancias (OD) que el Excel ya organizó en la hoja "MCT SAES",
y de paso cruza el resultado contra el valor que calculó el Solver del Excel
para avisar si hay discrepancias.

No se decodifica el "ORDEN" de la placa: se leen las OD ya de-referenciadas que
el Excel deja en celdas fijas (estándares en E11:J12; control y muestras en la
columna D desde la fila 43), por lo que el import es independiente del ORDEN.

Función pública:
    parse_excel_solver(origen) -> CorridaImportada
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional, Union

import openpyxl

from services.elisa_microcistina import (
    STD_CONC_UGL,
    FACTOR_DILUCION_DEFAULT,
    fit_4pl,
    procesar_muestra,
    procesar_control,
    CurvaParams,
    ResultadoMuestra,
)

HOJA = "MCT SAES"


@dataclass
class MuestraImportada:
    label: str                       # "Sample 1", etc. (etiqueta del Excel)
    od_1: float
    od_2: float
    cv_pct: float                    # recalculado
    conc_ugL: Optional[float]        # recalculado (µg/L, con factor)
    en_rango: bool
    motivo: str = ""
    conc_ugL_excel: Optional[float] = None   # lo que calculó el Solver (µg/L)
    discrepa: bool = False           # True si recalc vs Excel difieren > tol


@dataclass
class CorridaImportada:
    curva: CurvaParams
    control: ResultadoMuestra
    control_conc_excel: Optional[float]
    muestras: list[MuestraImportada]
    std_od: list[tuple[float, float]] = field(default_factory=list)
    control_od: tuple[float, float] = (0.0, 0.0)
    kit_lote: Optional[str] = None
    orden: Optional[int] = None
    factor: float = FACTOR_DILUCION_DEFAULT
    avisos: list[str] = field(default_factory=list)


def _num(ws, fila: int, col: int) -> Optional[float]:
    v = ws.cell(fila, col).value
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_excel_solver(
    origen: Union[bytes, BytesIO, str],
    factor: float = FACTOR_DILUCION_DEFAULT,
    tol_rel: float = 0.02,
) -> CorridaImportada:
    """
    Lee el libro del Solver y devuelve la corrida recalculada con el motor de la
    plataforma. ``origen`` puede ser bytes, un BytesIO o una ruta.

    Lanza ValueError si la hoja esperada no existe o faltan los estándares.
    """
    if isinstance(origen, bytes):
        origen = BytesIO(origen)
    wb = openpyxl.load_workbook(origen, data_only=True)
    if HOJA not in wb.sheetnames:
        raise ValueError(
            f"El archivo no parece ser el SOLVER de microcistina: falta la hoja '{HOJA}'."
        )
    ws = wb[HOJA]
    avisos: list[str] = []

    # ── Estándares: E11:J12 (cols 5..10 = Std0..Std5; filas 11 y 12 = réplicas)
    std_od: list[tuple[float, float]] = []
    for i in range(len(STD_CONC_UGL)):
        col = 5 + i
        a = _num(ws, 11, col)
        b = _num(ws, 12, col)
        if a is None or b is None:
            raise ValueError(
                f"Faltan absorbancias del estándar {i} (celdas "
                f"{openpyxl.utils.get_column_letter(col)}11/12)."
            )
        std_od.append((a, b))

    curva = fit_4pl(list(STD_CONC_UGL), [(a + b) / 2 for a, b in std_od])
    if not curva.es_valida():
        avisos.append(
            f"La curva no cumple los criterios guía (A={curva.A:.3f}, "
            f"D={curva.D:.3f}, R²={curva.r2:.4f})."
        )

    # ── Metadatos
    kit_lote = ws.cell(7, 10).value  # J7
    kit_lote = str(kit_lote).strip() if kit_lote not in (None, "") else None
    orden = _num(ws, 13, 19)  # S13
    orden = int(orden) if orden is not None else None

    # ── Control: filas 43/44, OD en columna D (4); conc Excel en I44 (col 9)
    ctrl_od1 = _num(ws, 43, 4)
    ctrl_od2 = _num(ws, 44, 4)
    if ctrl_od1 is None or ctrl_od2 is None:
        raise ValueError("Faltan las absorbancias del control (D43/D44).")
    control = procesar_control(ctrl_od1, ctrl_od2, curva)
    control_conc_excel = _num(ws, 44, 9)  # I44 (mg/L) → µg/L abajo
    if control_conc_excel is not None:
        control_conc_excel *= 1000.0  # mg/L → µg/L

    # ── Muestras: pares desde la fila 45, paso 2. C=label(3), D=OD(4),
    #    F=%CV(6), I=conc mg/L(9) — en la 2.ª fila del par.
    muestras: list[MuestraImportada] = []
    r = 45
    while r <= ws.max_row:
        label = ws.cell(r, 3).value
        od1 = _num(ws, r, 4)
        od2 = _num(ws, r + 1, 4)
        if (label is None or str(label).strip() == "") and od1 is None:
            break
        if od1 is None or od2 is None:
            r += 2
            continue
        res = procesar_muestra(od1, od2, curva, factor=factor)
        conc_excel = _num(ws, r + 1, 9)  # I (mg/L)
        conc_excel_ug = conc_excel * 1000.0 if conc_excel is not None else None
        discrepa = False
        if conc_excel_ug is not None and res.conc_ugL is not None:
            denom = max(abs(conc_excel_ug), 1e-9)
            discrepa = abs(res.conc_ugL - conc_excel_ug) / denom > tol_rel
        muestras.append(MuestraImportada(
            label=str(label).strip(),
            od_1=od1, od_2=od2,
            cv_pct=res.cv_pct,
            conc_ugL=res.conc_ugL,
            en_rango=res.en_rango,
            motivo=res.motivo,
            conc_ugL_excel=conc_excel_ug,
            discrepa=discrepa,
        ))
        r += 2

    n_disc = sum(1 for m in muestras if m.discrepa)
    if n_disc:
        avisos.append(
            f"{n_disc} muestra(s) difieren del valor del Excel en más del "
            f"{tol_rel*100:.0f}% (revisar)."
        )

    return CorridaImportada(
        curva=curva,
        control=control,
        control_conc_excel=control_conc_excel,
        muestras=muestras,
        std_od=std_od,
        control_od=(ctrl_od1, ctrl_od2),
        kit_lote=kit_lote,
        orden=orden,
        factor=factor,
        avisos=avisos,
    )
