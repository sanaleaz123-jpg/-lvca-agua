"""
services/microcistina_import.py
Lectura del libro Excel "SOLVER MICROCISTINAS SAES" para importar una corrida
ELISA a la plataforma.

Por defecto TOMA LOS VALORES QUE YA CALCULÓ EL SOLVER del Excel (curva 4PL,
control y concentraciones por muestra) — no recalcula. Si el libro no trae los
valores calculados (curva vacía), cae a recalcular con el motor propio
(services/elisa_microcistina.py) y lo avisa.

Celdas (hoja "MCT SAES"):
    - Estándares OD: E11:J12 (cols 5..10 = Std0..Std5; filas 11/12 = réplicas).
    - Curva 4PL: A=E35, B=E36, C=E37, D=E38; R²=G35; SSE=G32.
    - Control: OD en D43/D44; concentración por pozo en G43/G44; promedio H44;
      %CV en F44.
    - Muestras: pares desde la fila 45 (paso 2). C=label, D=OD; en la 2.ª fila
      del par: F=%CV, I=concentración (mg/L).

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
    cv_pct: float
    conc_ugL: Optional[float]        # µg/L (con factor) — None si fuera de rango
    en_rango: bool
    motivo: str = ""


@dataclass
class CorridaImportada:
    curva: CurvaParams
    control: ResultadoMuestra
    control_conc_1: Optional[float]
    control_conc_2: Optional[float]
    muestras: list[MuestraImportada]
    std_od: list[tuple[float, float]] = field(default_factory=list)
    control_od: tuple[float, float] = (0.0, 0.0)
    kit_lote: Optional[str] = None
    orden: Optional[int] = None
    factor: float = FACTOR_DILUCION_DEFAULT
    recalculado: bool = False
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
    recalcular: bool = False,
) -> CorridaImportada:
    """
    Lee el libro del Solver. Por defecto usa los valores ya calculados por el
    Excel; con ``recalcular=True`` recalcula desde las OD con el motor propio.
    ``origen`` puede ser bytes, BytesIO o ruta.
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

    # ── Estándares OD (E11:J12) — siempre se leen (para guardar/recalcular)
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

    # ── Curva 4PL: del Excel (E35:E38, G35, G32) o recalculada
    A = _num(ws, 35, 5); B = _num(ws, 36, 5)
    C = _num(ws, 37, 5); D = _num(ws, 38, 5)
    r2 = _num(ws, 35, 7); sse = _num(ws, 32, 7)
    if recalcular or None in (A, B, C, D):
        if not recalcular:
            avisos.append("El Excel no traía la curva calculada; se recalculó con el motor propio.")
        curva = fit_4pl(list(STD_CONC_UGL), [(a + b) / 2 for a, b in std_od])
        recalculado = True
    else:
        curva = CurvaParams(A=A, B=B, C=C, D=D, r2=r2 or 0.0, sse=sse or 0.0)
        recalculado = False
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

    # ── Control: OD en D43/D44; conc por pozo G43/G44; prom H44; %CV F44
    ctrl_od1 = _num(ws, 43, 4)
    ctrl_od2 = _num(ws, 44, 4)
    if ctrl_od1 is None or ctrl_od2 is None:
        raise ValueError("Faltan las absorbancias del control (D43/D44).")
    if recalculado:
        control = procesar_control(ctrl_od1, ctrl_od2, curva)
        from services.elisa_microcistina import concentracion_ugL
        control_conc_1 = concentracion_ugL(ctrl_od1, curva)
        control_conc_2 = concentracion_ugL(ctrl_od2, curva)
    else:
        control_conc_1 = _num(ws, 43, 7)   # G43 (µg/L)
        control_conc_2 = _num(ws, 44, 7)   # G44 (µg/L)
        prom = _num(ws, 44, 8)             # H44 (µg/L)
        cv = _num(ws, 44, 6)               # F44 (%CV)
        control = ResultadoMuestra(
            od_1=ctrl_od1, od_2=ctrl_od2, cv_pct=cv or 0.0,
            conc_ugL=prom, en_rango=prom is not None,
        )

    # ── Muestras: pares desde la fila 45 (paso 2)
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
        if recalculado:
            res = procesar_muestra(od1, od2, curva, factor=factor)
            cv_pct, conc_ugL, en_rango, motivo = (
                res.cv_pct, res.conc_ugL, res.en_rango, res.motivo
            )
        else:
            cv_pct = _num(ws, r + 1, 6) or 0.0        # F
            conc_mgL = _num(ws, r + 1, 9)             # I (mg/L)
            conc_ugL = conc_mgL * 1000.0 if conc_mgL is not None else None
            en_rango = conc_ugL is not None
            motivo = "" if en_rango else "Fuera del rango de la curva en el Excel."
        muestras.append(MuestraImportada(
            label=str(label).strip(),
            od_1=od1, od_2=od2, cv_pct=cv_pct,
            conc_ugL=conc_ugL, en_rango=en_rango, motivo=motivo,
        ))
        r += 2

    return CorridaImportada(
        curva=curva,
        control=control,
        control_conc_1=control_conc_1,
        control_conc_2=control_conc_2,
        muestras=muestras,
        std_od=std_od,
        control_od=(ctrl_od1, ctrl_od2),
        kit_lote=kit_lote,
        orden=orden,
        factor=factor,
        recalculado=recalculado,
        avisos=avisos,
    )
