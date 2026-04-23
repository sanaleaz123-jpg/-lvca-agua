"""
services/linea_base_service.py
Línea base de temperatura por punto y mes — evaluación del criterio Δ3
del DS 004-2017-MINAM.

El DS define el ECA de Temperatura en todas las categorías como "Δ 3 °C"
(variación máxima respecto al promedio mensual multianual del área, serie
1-5 años considerando estacionalidad). No es un valor absoluto: exige una
línea base histórica por punto y por mes.

Funciones públicas:
    obtener_linea_base(punto_id, mes)                      — una fila
    listar_linea_base(punto_id)                            — todas las del punto
    registrar_linea_base(...)                              — UPSERT
    eliminar_linea_base(punto_id, mes)                     — DELETE
    evaluar_delta_temperatura(punto_id, fecha, t_c)        — juicio Δ3

CRUD simple + un único cálculo. El motor de cumplimiento puede consumir
el resultado si lo necesita, o la UI llamarlo directamente.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from database.client import get_admin_client


UMBRAL_DELTA_C: float = 3.0  # regla fija del DS


# ─────────────────────────────────────────────────────────────────────────────
# Lecturas
# ─────────────────────────────────────────────────────────────────────────────

def obtener_linea_base(punto_id: str, mes: int) -> Optional[dict]:
    """Retorna la línea base para (punto, mes) o None si no existe."""
    if not punto_id or not (1 <= mes <= 12):
        return None
    db = get_admin_client()
    res = (
        db.table("linea_base_temperatura")
        .select(
            "id, mes, promedio_multianual_c, desviacion_std_c, "
            "n_anos, anio_inicio, anio_fin, observacion"
        )
        .eq("punto_muestreo_id", punto_id)
        .eq("mes", mes)
        .maybe_single()
        .execute()
    )
    return res.data if res else None


def listar_linea_base(punto_id: str) -> list[dict]:
    """Todas las líneas base del punto, ordenadas por mes."""
    db = get_admin_client()
    res = (
        db.table("linea_base_temperatura")
        .select(
            "id, mes, promedio_multianual_c, desviacion_std_c, "
            "n_anos, anio_inicio, anio_fin, observacion, created_at"
        )
        .eq("punto_muestreo_id", punto_id)
        .order("mes")
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────────────────────────────────────
# Escrituras
# ─────────────────────────────────────────────────────────────────────────────

def registrar_linea_base(
    *,
    punto_id: str,
    mes: int,
    promedio_multianual_c: float,
    n_anos: Optional[int] = None,
    desviacion_std_c: Optional[float] = None,
    anio_inicio: Optional[int] = None,
    anio_fin: Optional[int] = None,
    observacion: str = "",
    registrado_por: Optional[str] = None,
) -> dict:
    """UPSERT por (punto, mes)."""
    if not (1 <= mes <= 12):
        raise ValueError("mes debe estar entre 1 y 12")
    db = get_admin_client()
    fila = {
        "punto_muestreo_id":     punto_id,
        "mes":                   mes,
        "promedio_multianual_c": promedio_multianual_c,
        "desviacion_std_c":      desviacion_std_c,
        "n_anos":                n_anos,
        "anio_inicio":           anio_inicio,
        "anio_fin":              anio_fin,
        "observacion":           observacion,
        "registrado_por":        registrado_por,
    }
    res = (
        db.table("linea_base_temperatura")
        .upsert(fila, on_conflict="punto_muestreo_id,mes")
        .execute()
    )
    return res.data[0] if res.data else fila


def eliminar_linea_base(punto_id: str, mes: int) -> None:
    db = get_admin_client()
    db.table("linea_base_temperatura").delete().eq(
        "punto_muestreo_id", punto_id
    ).eq("mes", mes).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Evaluación Δ3
# ─────────────────────────────────────────────────────────────────────────────

def evaluar_delta_temperatura(
    *,
    punto_id: str,
    fecha_muestreo: date | str,
    temperatura_c: float,
) -> dict:
    """
    Evalúa si una medición de temperatura respeta el criterio Δ3 del DS.

    Retorna:
        {
            "puede_comparar":   bool,
            "motivo":           str,
            "temperatura_c":    float,
            "mes":              int,
            "linea_base":       dict | None,   # fila de linea_base_temperatura
            "delta_c":          float | None,  # t_medida - promedio_multianual
            "umbral_c":         float,         # 3.0 fijo
            "cumple":           bool | None,
        }
    """
    # Normalizar fecha
    if isinstance(fecha_muestreo, str):
        fecha_muestreo = datetime.fromisoformat(fecha_muestreo[:10]).date()
    mes = fecha_muestreo.month

    resultado: dict = {
        "puede_comparar": False,
        "motivo":          "",
        "temperatura_c":   temperatura_c,
        "mes":             mes,
        "linea_base":      None,
        "delta_c":         None,
        "umbral_c":        UMBRAL_DELTA_C,
        "cumple":          None,
    }

    lb = obtener_linea_base(punto_id, mes)
    if lb is None:
        resultado["motivo"] = (
            f"No existe línea base de temperatura para el mes {mes:02d} en este "
            "punto. El criterio Δ3 del DS 004-2017-MINAM exige una serie multianual "
            "(1-5 años) por mes calendario. Constituye no conformidad documental "
            "hasta que se registre la línea base."
        )
        return resultado

    resultado["linea_base"] = lb
    delta = float(temperatura_c) - float(lb["promedio_multianual_c"])
    resultado["delta_c"] = delta
    cumple = abs(delta) <= UMBRAL_DELTA_C
    resultado["cumple"] = cumple
    resultado["puede_comparar"] = True

    promedio = lb["promedio_multianual_c"]
    n = lb.get("n_anos") or "?"
    signo = "+" if delta >= 0 else ""
    resultado["motivo"] = (
        f"Δ = {signo}{delta:.2f} °C respecto al promedio multianual "
        f"({promedio} °C, serie de {n} años). "
        f"Umbral ±{UMBRAL_DELTA_C} °C → {'cumple' if cumple else 'excede'}."
    )
    return resultado
