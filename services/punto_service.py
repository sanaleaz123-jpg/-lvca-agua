"""
services/punto_service.py
Lógica de negocio para gestión de puntos de muestreo.

Funciones públicas:
    get_puntos(filtro_cuenca, filtro_tipo, busqueda)  → lista filtrada
    get_punto(punto_id)                               → detalle con ECA
    crear_punto(datos)                                → insert
    actualizar_punto(punto_id, datos)                 → update
    toggle_punto(punto_id, activo)                    → activar/desactivar
    get_cuencas()                                     → valores únicos
    get_tipos()                                       → valores únicos
"""

from __future__ import annotations

from typing import Optional

from database.client import get_admin_client
from services.audit_service import registrar_cambio, registrar_cambios_multiples
from services.cache import cached


# Tipos válidos de punto
TIPOS_PUNTO = ["rio", "laguna", "canal", "manantial", "pozo", "embalse", "bocatoma", "desarenador", "otro"]


def _invalidar_cache() -> None:
    """Limpia el caché de puntos y del geoportal tras cualquier modificación."""
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Listado
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_puntos(
    filtro_cuenca: Optional[str] = None,
    filtro_tipo: Optional[str] = None,
    busqueda: Optional[str] = None,
    solo_activos: bool = False,
) -> list[dict]:
    """Retorna puntos de muestreo con ECA asociado."""
    db = get_admin_client()
    query = (
        db.table("puntos_muestreo")
        .select(
            "id, codigo, nombre, descripcion, tipo, cuenca, sistema_hidrico, lugar_muestreo, "
            "utm_este, utm_norte, utm_zona, latitud, longitud, altitud_msnm, "
            "entidad_responsable, activo, eca_id, "
            "departamento, provincia, distrito, accesibilidad, representatividad, finalidad, "
            "ecas(id, codigo, nombre)"
        )
        .order("codigo")
    )

    if solo_activos:
        query = query.eq("activo", True)
    if filtro_cuenca:
        query = query.eq("cuenca", filtro_cuenca)
    if filtro_tipo:
        query = query.eq("tipo", filtro_tipo)

    data = query.execute().data or []

    if busqueda:
        term = busqueda.lower()
        data = [
            p for p in data
            if term in (p.get("codigo") or "").lower()
            or term in (p.get("nombre") or "").lower()
            or term in (p.get("descripcion") or "").lower()
        ]

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Detalle
# ─────────────────────────────────────────────────────────────────────────────

def get_punto(punto_id: str) -> dict | None:
    """Detalle de un punto con ECA."""
    db = get_admin_client()
    res = (
        db.table("puntos_muestreo")
        .select(
            "id, codigo, nombre, descripcion, tipo, cuenca, sistema_hidrico, lugar_muestreo, "
            "utm_este, utm_norte, utm_zona, latitud, longitud, altitud_msnm, "
            "entidad_responsable, activo, eca_id, "
            "departamento, provincia, distrito, accesibilidad, representatividad, finalidad, "
            "ecas(id, codigo, nombre)"
        )
        .eq("id", punto_id)
        .maybe_single()
        .execute()
    )
    return res.data


# ─────────────────────────────────────────────────────────────────────────────
# Creación y edición
# ─────────────────────────────────────────────────────────────────────────────

def crear_punto(datos: dict) -> dict:
    """Inserta un nuevo punto de muestreo."""
    db = get_admin_client()
    fila = _build_fila(datos)
    res = db.table("puntos_muestreo").insert(fila).execute()
    creado = res.data[0]
    registrar_cambio(
        tabla="puntos_muestreo",
        registro_id=creado["id"],
        accion="crear",
        valor_nuevo=f"{datos.get('codigo', '')} — {datos.get('nombre', '')}",
    )
    _invalidar_cache()
    return creado


def actualizar_punto(punto_id: str, datos: dict) -> dict:
    """Actualiza un punto existente."""
    db = get_admin_client()

    # Leer valores anteriores para auditoría
    anterior = (
        db.table("puntos_muestreo")
        .select("nombre, descripcion, tipo, cuenca, sistema_hidrico, lugar_muestreo, "
                "utm_este, utm_norte, utm_zona, latitud, longitud, altitud_msnm, "
                "departamento, provincia, distrito, accesibilidad, representatividad, "
                "finalidad, eca_id, entidad_responsable")
        .eq("id", punto_id)
        .single()
        .execute()
    ).data or {}

    campos = _build_fila(datos)
    campos.pop("codigo", None)
    res = (
        db.table("puntos_muestreo")
        .update(campos)
        .eq("id", punto_id)
        .execute()
    )

    # Registrar cambios en audit log
    cambios = {
        k: (anterior.get(k), v)
        for k, v in campos.items()
        if str(anterior.get(k)) != str(v)
    }
    if cambios:
        registrar_cambios_multiples(
            tabla="puntos_muestreo",
            registro_id=punto_id,
            accion="editar",
            cambios=cambios,
        )

    _invalidar_cache()
    return res.data[0]


def toggle_punto(punto_id: str, activo: bool) -> None:
    """Activa o desactiva un punto."""
    db = get_admin_client()
    db.table("puntos_muestreo").update({"activo": activo}).eq("id", punto_id).execute()
    registrar_cambio(
        tabla="puntos_muestreo",
        registro_id=punto_id,
        accion="activar" if activo else "desactivar",
        campo="activo",
        valor_anterior=str(not activo),
        valor_nuevo=str(activo),
    )
    _invalidar_cache()


def eliminar_punto(punto_id: str) -> None:
    """
    Elimina un punto de muestreo de forma permanente.
    Solo se permite si no tiene muestras asociadas.
    """
    db = get_admin_client()

    # Leer datos para auditoría
    punto_data = (
        db.table("puntos_muestreo")
        .select("codigo, nombre")
        .eq("id", punto_id)
        .maybe_single()
        .execute()
    ).data or {}
    punto_desc = f"{punto_data.get('codigo', '')} — {punto_data.get('nombre', '')}"

    # Verificar muestras asociadas
    m_count = (
        db.table("muestras")
        .select("id", count="exact")
        .eq("punto_muestreo_id", punto_id)
        .execute()
    )
    if (m_count.count or 0) > 0:
        raise ValueError(
            f"No se puede eliminar: el punto tiene {m_count.count} muestra(s) asociadas."
        )

    # Eliminar vínculos con campañas
    db.table("campana_puntos").delete().eq("punto_muestreo_id", punto_id).execute()
    # Eliminar punto
    db.table("puntos_muestreo").delete().eq("id", punto_id).execute()
    registrar_cambio(
        tabla="puntos_muestreo",
        registro_id=punto_id,
        accion="eliminar",
        valor_anterior=punto_desc,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers para selectores
# ─────────────────────────────────────────────────────────────────────────────

def get_cuencas() -> list[str]:
    """Valores únicos de cuenca existentes en la tabla."""
    db = get_admin_client()
    res = (
        db.table("puntos_muestreo")
        .select("cuenca")
        .execute()
    )
    return sorted({r["cuenca"] for r in (res.data or []) if r.get("cuenca")})


def get_tipos() -> list[str]:
    """Valores únicos de tipo existentes en la tabla."""
    db = get_admin_client()
    res = (
        db.table("puntos_muestreo")
        .select("tipo")
        .execute()
    )
    return sorted({r["tipo"] for r in (res.data or []) if r.get("tipo")})


# ─────────────────────────────────────────────────────────────────────────────
# Internos
# ─────────────────────────────────────────────────────────────────────────────

def _build_fila(datos: dict) -> dict:
    """Construye el dict de columnas a partir de los datos del formulario."""
    fila: dict = {}
    campos_texto = (
        "codigo", "nombre", "descripcion", "tipo", "cuenca", "sistema_hidrico", "lugar_muestreo",
        "utm_zona", "entidad_responsable",
        "departamento", "provincia", "distrito",
        "accesibilidad", "representatividad", "finalidad",
        "sistema_hidrico", "lugar_muestreo",
    )
    for c in campos_texto:
        if c in datos:
            fila[c] = datos[c].strip() if datos[c] else None

    campos_num = ("utm_este", "utm_norte", "latitud", "longitud", "altitud_msnm")
    for c in campos_num:
        if c in datos:
            fila[c] = datos[c] if datos[c] is not None else None

    if "eca_id" in datos:
        fila["eca_id"] = datos["eca_id"] or None

    if "activo" in datos:
        fila["activo"] = datos["activo"]

    return fila
