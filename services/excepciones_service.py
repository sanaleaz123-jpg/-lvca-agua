"""
services/excepciones_service.py
Consulta de flags Art. 7 (zona de mezcla) y excepciones Art. 6 (naturales).

Se usa desde cumplimiento_service.py para enriquecer el ContextoEvaluacion
antes de emitir veredicto. El servicio es CRUD simple — la lógica de qué
hacer con los flags vive en el motor de cumplimiento.
"""

from __future__ import annotations

from typing import Optional
from datetime import date

from database.client import get_admin_client
from services.cache import cached


# ─────────────────────────────────────────────────────────────────────────────
# Art. 7 — zona de mezcla
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def punto_dentro_zona_mezcla(punto_id: str) -> bool:
    """Retorna True si el punto está marcado como dentro de zona de mezcla."""
    if not punto_id:
        return False
    db = get_admin_client()
    res = (
        db.table("puntos_muestreo")
        .select("dentro_zona_mezcla")
        .eq("id", punto_id)
        .maybe_single()
        .execute()
    )
    data = (res.data if res else None) or {}
    return bool(data.get("dentro_zona_mezcla"))


# ─────────────────────────────────────────────────────────────────────────────
# Art. 6 — excepciones por condiciones naturales
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def tiene_excepcion_art6(punto_id: str, parametro_id: str) -> bool:
    """
    Retorna True si existe una excepción Art. 6 vigente para (punto, parámetro).
    Una excepción está vigente si:
      - vigente = TRUE
      - fecha_vencimiento es NULL o >= hoy
    """
    if not punto_id or not parametro_id:
        return False
    db = get_admin_client()
    res = (
        db.table("excepciones_art6")
        .select("id, fecha_vencimiento")
        .eq("punto_muestreo_id", punto_id)
        .eq("parametro_id", parametro_id)
        .eq("vigente", True)
        .execute()
    )
    hoy = date.today().isoformat()
    for r in (res.data or []):
        vence = r.get("fecha_vencimiento")
        if vence is None or vence >= hoy:
            return True
    return False


def listar_excepciones_art6(punto_id: Optional[str] = None) -> list[dict]:
    """
    Lista excepciones Art. 6. Filtra por punto si se provee.
    Retorna filas con datos del punto y parámetro ya resueltos.
    """
    db = get_admin_client()
    query = (
        db.table("excepciones_art6")
        .select(
            "id, punto_muestreo_id, parametro_id, vigente, "
            "rj_ana_sustento, fecha_aprobacion, fecha_vencimiento, "
            "causa_natural, descripcion, created_at, "
            "puntos_muestreo(codigo, nombre), "
            "parametros(codigo, nombre)"
        )
        .order("created_at", desc=True)
    )
    if punto_id:
        query = query.eq("punto_muestreo_id", punto_id)
    res = query.execute()
    return res.data or []


def registrar_excepcion_art6(
    *,
    punto_id: str,
    parametro_id: str,
    rj_ana_sustento: str,
    fecha_aprobacion: str,
    causa_natural: str,
    descripcion: str = "",
    fecha_vencimiento: Optional[str] = None,
    registrado_por: Optional[str] = None,
) -> dict:
    """Crea o actualiza una excepción Art. 6 (UPSERT por punto+parámetro)."""
    db = get_admin_client()
    fila = {
        "punto_muestreo_id": punto_id,
        "parametro_id":      parametro_id,
        "vigente":           True,
        "rj_ana_sustento":   rj_ana_sustento,
        "fecha_aprobacion":  fecha_aprobacion,
        "fecha_vencimiento": fecha_vencimiento,
        "causa_natural":     causa_natural,
        "descripcion":       descripcion,
        "registrado_por":    registrado_por,
    }
    res = (
        db.table("excepciones_art6")
        .upsert(fila, on_conflict="punto_muestreo_id,parametro_id")
        .execute()
    )
    # Invalidar caché de getters rápidos
    tiene_excepcion_art6.clear()
    return res.data[0] if res.data else fila


def revocar_excepcion_art6(punto_id: str, parametro_id: str) -> None:
    """Marca la excepción como no vigente (soft-delete)."""
    db = get_admin_client()
    db.table("excepciones_art6").update({"vigente": False}).eq(
        "punto_muestreo_id", punto_id
    ).eq("parametro_id", parametro_id).execute()
    tiene_excepcion_art6.clear()
