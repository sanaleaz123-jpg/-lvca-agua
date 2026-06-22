"""
services/microcistina_service.py
Persistencia y orquestación del ensayo ELISA de Microcistina LR (P091).

Une el motor de cálculo puro (services/elisa_microcistina.py) con la base de
datos: guarda la corrida (curva 4PL + control de calidad) por campaña y vuelca
el resultado de cada muestra en ``resultados_laboratorio`` (concentración en
µg/L, OD por duplicado, %CV y cualificador).

Funciones públicas:
    get_param_microcistina()                 → fila del parámetro P091 (id, lmd, lcm, unidad)
    get_muestras_microcistina(campana_id)    → muestras de la campaña + OD ya guardadas
    get_corrida(campana_id)                  → corrida ELISA guardada (o None)
    calcular_corrida(...)                     → cálculo en memoria (preview, sin guardar)
    guardar_corrida(...)                      → calcula y persiste corrida + resultados
    tiene_resultados_microcistina(campana_id) → bool (gate del reporte)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.client import get_db
from services.cache import cached
from services.elisa_microcistina import (
    STD_CONC_UGL,
    FACTOR_DILUCION_DEFAULT,
    CurvaParams,
    ResultadoMuestra,
    fit_4pl,
    procesar_muestra,
    procesar_control,
)

CODIGO_MICROCISTINA = "P091"


def _invalidar_cache() -> None:
    try:
        from services.cache import invalidate_operational
        invalidate_operational()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Parámetro y muestras
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=600, grupo="referencia")
def get_param_microcistina() -> Optional[dict]:
    """Fila del parámetro P091: id, nombre, lmd, lcm, símbolo de unidad."""
    db = get_db()
    try:
        res = (
            db.table("parametros")
            .select("id, codigo, nombre, lmd, lcm, unidades_medida(simbolo)")
            .eq("codigo", CODIGO_MICROCISTINA)
            .single()
            .execute()
        )
    except Exception:
        return None
    return res.data or None


@cached(ttl=120)
def get_muestras_microcistina(campana_id: str) -> list[dict]:
    """
    Muestras de la campaña (una por punto/nivel) con su punto y, si existe, la
    lectura ELISA ya guardada. Ordenadas por código de punto.

    Cada elemento:
        {id, codigo, fecha_muestreo, hora_recoleccion,
         punto: {id, codigo, nombre},
         od_1, od_2, valor_numerico, cv_pct, cualificador}
    """
    db = get_db()
    param = get_param_microcistina()
    param_id = (param or {}).get("id")

    m_res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, hora_recoleccion, punto_muestreo_id, "
            "puntos_muestreo(id, codigo, nombre, descripcion, utm_este, utm_norte)"
        )
        .eq("campana_id", campana_id)
        .order("fecha_muestreo")
        .execute()
    )
    muestras = m_res.data or []
    muestra_ids = [m["id"] for m in muestras]

    # Resultados P091 ya guardados (od, valor, cv, cualificador)
    por_muestra: dict[str, dict] = {}
    if muestra_ids and param_id:
        try:
            r_res = (
                db.table("resultados_laboratorio")
                .select("muestra_id, valor_numerico, cualificador, od_1, od_2, cv_pct, validado")
                .in_("muestra_id", muestra_ids)
                .eq("parametro_id", param_id)
                .execute()
            )
            por_muestra = {r["muestra_id"]: r for r in (r_res.data or [])}
        except Exception:
            por_muestra = {}

    salida = []
    for m in muestras:
        prev = por_muestra.get(m["id"], {})
        salida.append({
            "id": m["id"],
            "codigo": m.get("codigo"),
            "fecha_muestreo": m.get("fecha_muestreo"),
            "hora_recoleccion": m.get("hora_recoleccion"),
            "punto": m.get("puntos_muestreo") or {},
            "od_1": prev.get("od_1"),
            "od_2": prev.get("od_2"),
            "valor_numerico": prev.get("valor_numerico"),
            "cv_pct": prev.get("cv_pct"),
            "cualificador": prev.get("cualificador"),
            "validado": prev.get("validado", False),
        })
    salida.sort(key=lambda x: (x["punto"].get("codigo") or "", x.get("codigo") or ""))
    return salida


@cached(ttl=120)
def get_corrida(campana_id: str) -> Optional[dict]:
    """Corrida ELISA guardada para la campaña (o None)."""
    db = get_db()
    try:
        res = (
            db.table("elisa_microcistina_corridas")
            .select("*")
            .eq("campana_id", campana_id)
            .limit(1)
            .execute()
        )
    except Exception:
        return None
    data = res.data or []
    return data[0] if data else None


def tiene_resultados_microcistina(campana_id: str) -> bool:
    """True si la campaña tiene una corrida ELISA con curva ajustada."""
    corrida = get_corrida(campana_id)
    return bool(corrida and corrida.get("param_a") is not None)


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo (en memoria) de una corrida completa
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CorridaCalculada:
    curva: CurvaParams
    control: ResultadoMuestra
    # muestra_id → ResultadoMuestra
    resultados: dict[str, ResultadoMuestra]


def calcular_corrida(
    std_od: list[tuple[float, float]],
    control_od: tuple[float, float],
    muestras_od: dict[str, tuple[float, float]],
    factor: float = FACTOR_DILUCION_DEFAULT,
) -> CorridaCalculada:
    """
    Ajusta la curva 4PL y procesa control y muestras SIN tocar la BD.
    Útil para previsualizar en la UI antes de guardar.

    ``std_od`` son las 6 parejas (od1, od2) en orden Std0..Std5.
    ``muestras_od`` mapea muestra_id → (od1, od2).
    """
    if len(std_od) != len(STD_CONC_UGL):
        raise ValueError(
            f"Se requieren {len(STD_CONC_UGL)} estándares (Std0..Std5); "
            f"se recibieron {len(std_od)}."
        )
    od_prom = [(a + b) / 2.0 for a, b in std_od]
    curva = fit_4pl(list(STD_CONC_UGL), od_prom)

    control = procesar_control(control_od[0], control_od[1], curva)

    resultados: dict[str, ResultadoMuestra] = {}
    for mid, (o1, o2) in muestras_od.items():
        resultados[mid] = procesar_muestra(o1, o2, curva, factor=factor)

    return CorridaCalculada(curva=curva, control=control, resultados=resultados)


# ─────────────────────────────────────────────────────────────────────────────
# Guardado: corrida + resultados de laboratorio
# ─────────────────────────────────────────────────────────────────────────────

def guardar_corrida(
    campana_id: str,
    *,
    fecha_ensayo: Optional[str],
    kit_lote: Optional[str],
    factor: float,
    std_od: list[tuple[float, float]],
    control_od: tuple[float, float],
    muestras_od: dict[str, tuple[float, float]],
    qcs_nominal: float = 0.750,
    qcs_tolerancia: float = 0.185,
    cv_max: float = 15.0,
    observaciones: Optional[str] = None,
    analista_id: Optional[str] = None,
) -> CorridaCalculada:
    """
    Calcula la corrida (curva + control + muestras) y la persiste:
        - upsert en elisa_microcistina_corridas (una por campaña)
        - upsert de P091 en resultados_laboratorio por cada muestra con OD

    El valor_numerico se guarda en µg/L (unidad del parámetro). El cualificador
    se marca '<LCM' cuando la concentración cae por debajo del límite de
    cuantificación del método.
    """
    db = get_db()
    param = get_param_microcistina()
    if not param:
        raise ValueError("No se encontró el parámetro Microcistina LR (P091) en la BD.")
    param_id = param["id"]
    lcm = param.get("lcm")  # µg/L

    calc = calcular_corrida(std_od, control_od, muestras_od, factor=factor)
    curva = calc.curva
    control = calc.control

    # Código de reporte correlativo: se genera una sola vez por campaña y se
    # conserva en descargas posteriores.
    existente = get_corrida(campana_id) or {}
    codigo_reporte = existente.get("codigo_reporte") or _generar_codigo_reporte(db, fecha_ensayo)

    # 1. Upsert de la corrida
    corrida_row = {
        "campana_id": campana_id,
        "codigo_reporte": codigo_reporte,
        "fecha_ensayo": fecha_ensayo,
        "kit_lote": kit_lote,
        "factor_dilucion": factor,
        "std_od": [[a, b] for a, b in std_od],
        "param_a": curva.A,
        "param_b": curva.B,
        "param_c": curva.C,
        "param_d": curva.D,
        "r2": curva.r2,
        "sse": curva.sse,
        "control_od_1": control_od[0],
        "control_od_2": control_od[1],
        "control_conc_1": _conc_replica(control_od[0], curva),
        "control_conc_2": _conc_replica(control_od[1], curva),
        "control_conc_prom": control.conc_ugL,
        "control_cv": control.cv_pct,
        "qcs_nominal": qcs_nominal,
        "qcs_tolerancia": qcs_tolerancia,
        "cv_max": cv_max,
        "observaciones": observaciones,
        "updated_at": datetime.utcnow().isoformat(),
    }
    db.table("elisa_microcistina_corridas").upsert(
        corrida_row, on_conflict="campana_id"
    ).execute()

    # 2. Upsert de resultados por muestra (respeta validados existentes)
    fecha = fecha_ensayo or datetime.utcnow().date().isoformat()
    validados = _ids_validados(db, list(muestras_od.keys()), param_id)

    for mid, res in calc.resultados.items():
        if mid in validados:
            continue  # no sobreescribir resultados ya validados
        cualificador = None
        observ = res.motivo or None
        if res.conc_ugL is not None and lcm is not None and res.conc_ugL < float(lcm):
            cualificador = "<LCM"
        fila = {
            "muestra_id": mid,
            "parametro_id": param_id,
            "valor_numerico": res.conc_ugL,
            "od_1": res.od_1,
            "od_2": res.od_2,
            "cv_pct": res.cv_pct,
            "cualificador": cualificador,
            "observaciones": observ,
            "analista_id": analista_id,
            "fecha_analisis": fecha,
        }
        db.table("resultados_laboratorio").upsert(
            fila, on_conflict="muestra_id,parametro_id"
        ).execute()

    _invalidar_cache()
    return calc


def _generar_codigo_reporte(db, fecha_ensayo: Optional[str]) -> str:
    """
    Correlativo 'LVCA - NNN-MC-AAAA'. Usa la función SQL siguiente_codigo()
    (secuencia atómica por prefijo/año). Si falla, cae a un conteo de corridas.
    """
    anio = datetime.utcnow().year
    if fecha_ensayo:
        try:
            anio = int(str(fecha_ensayo)[:4])
        except (ValueError, TypeError):
            pass
    n = None
    try:
        rpc = db.rpc("siguiente_codigo", {
            "p_tabla": "reporte_mc", "p_prefijo": "MC", "p_anio": anio,
        }).execute()
        n = rpc.data
        if isinstance(n, list):
            n = n[0] if n else None
    except Exception:
        n = None
    if n is None:
        try:
            res = (
                db.table("elisa_microcistina_corridas")
                .select("id", count="exact")
                .execute()
            )
            n = (getattr(res, "count", 0) or 0) + 1
        except Exception:
            n = 1
    return f"LVCA - {int(n):03d}-MC-{anio}"


def _conc_replica(od: float, curva: CurvaParams) -> Optional[float]:
    from services.elisa_microcistina import concentracion_ugL
    return concentracion_ugL(od, curva)


def _ids_validados(db, muestra_ids: list[str], param_id: str) -> set[str]:
    if not muestra_ids:
        return set()
    try:
        res = (
            db.table("resultados_laboratorio")
            .select("muestra_id, validado")
            .in_("muestra_id", muestra_ids)
            .eq("parametro_id", param_id)
            .eq("validado", True)
            .execute()
        )
        return {r["muestra_id"] for r in (res.data or [])}
    except Exception:
        return set()
