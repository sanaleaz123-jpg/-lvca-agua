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

import re
from typing import Optional

from database.client import get_admin_client
from services.audit_service import registrar_cambio, registrar_cambios_multiples
from services.cache import cached


# Tipos válidos de punto
TIPOS_PUNTO = ["rio", "laguna", "canal", "manantial", "pozo", "embalse", "bocatoma", "desarenador", "otro"]

# Cuencas canónicas — únicas oficialmente válidas en la plataforma.
# Cualquier otra grafía (con/sin espacios, con/sin tildes) se normaliza
# a una de estas en lectura y escritura para evitar duplicados visuales.
CUENCAS_CANONICAS: list[str] = [
    "Quilca-Chili-Vitor",
    "Colca-Camaná",
]


def _slug_cuenca(raw: str) -> str:
    """Clave de comparación: minúsculas, sin tildes, sin espacios ni guiones."""
    if not raw:
        return ""
    s = raw.strip().lower()
    repl = (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n"))
    for a, b in repl:
        s = s.replace(a, b)
    for ch in (" ", "-", "_", ".", "/"):
        s = s.replace(ch, "")
    return s


_CUENCA_SLUG_MAP = {_slug_cuenca(c): c for c in CUENCAS_CANONICAS}


def normalizar_cuenca(raw: str | None) -> str | None:
    """
    Devuelve la grafía canónica de una cuenca si coincide con alguna conocida
    (ignorando mayúsculas, espacios, guiones y tildes). Si no coincide,
    retorna el valor con strip(); permite registrar cuencas nuevas sin perder
    el texto que ingresó el usuario.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    return _CUENCA_SLUG_MAP.get(_slug_cuenca(s), s)


def _coords_invalidas(v) -> bool:
    """True si el valor de lat/lon debe considerarse vacío (None o ~0)."""
    if v is None:
        return True
    try:
        return abs(float(v)) < 1e-8
    except (TypeError, ValueError):
        return True


def completar_latlon_desde_utm(punto: dict) -> dict:
    """
    Si el punto tiene UTM pero no lat/lon (o están en 0), calcula lat/lon
    desde UTM y los rellena en el dict. Mutación in-place + retorna el dict.
    No persiste en BD: los mapas reciben coordenadas válidas aunque la fila
    de la BD aún tenga lat/lon = 0.
    """
    if not punto:
        return punto
    if punto.get("utm_este") and punto.get("utm_norte"):
        if _coords_invalidas(punto.get("latitud")) or _coords_invalidas(punto.get("longitud")):
            lat, lon = utm_a_latlon(
                punto.get("utm_este"),
                punto.get("utm_norte"),
                punto.get("utm_zona") or "19S",
            )
            if lat is not None and lon is not None:
                punto["latitud"] = lat
                punto["longitud"] = lon
    return punto


def utm_a_latlon(
    utm_este: float | None,
    utm_norte: float | None,
    utm_zona: str | None = "19S",
) -> tuple[float | None, float | None]:
    """
    Convierte coordenadas UTM (WGS84) a (latitud, longitud) decimales.
    Convención usada en LVCA: la zona se nota como '18S', '19S', '19N', etc.
    'S' = hemisferio sur (Perú); por defecto se asume sur.
    Retorna (None, None) si la conversión no es posible.
    """
    if utm_este in (None, 0) or utm_norte in (None, 0):
        return None, None
    try:
        from pyproj import Transformer
        zona_str = (utm_zona or "19S").strip().upper()
        m = re.match(r"(\d+)\s*([A-Z]?)", zona_str)
        if not m:
            return None, None
        zone_num = int(m.group(1))
        letra = m.group(2) or "S"
        # En el uso peruano "S" = Sur (hemisferio sur). Solo "N" explícito = norte.
        es_sur = letra != "N"
        epsg = (32700 if es_sur else 32600) + zone_num
        tr = Transformer.from_crs(epsg, 4326, always_xy=True)
        lon, lat = tr.transform(float(utm_este), float(utm_norte))
        return float(lat), float(lon)
    except Exception:
        return None, None


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
            "dentro_zona_mezcla, zona_mezcla_observacion, "   # migración 013
            "ecas(id, codigo, nombre)"
        )
        .order("codigo")
    )

    if solo_activos:
        query = query.eq("activo", True)
    if filtro_tipo:
        query = query.eq("tipo", filtro_tipo)

    data = query.execute().data or []

    # Normalizar cuenca antes de filtrar para que las grafías mixtas en BD
    # (p.ej. "Quilca - Chili - Vitor" vs "Quilca-Chili-Vitor") agrupen igual.
    for p in data:
        if p.get("cuenca"):
            p["cuenca"] = normalizar_cuenca(p["cuenca"])

    if filtro_cuenca:
        cuenca_norm = normalizar_cuenca(filtro_cuenca)
        data = [p for p in data if p.get("cuenca") == cuenca_norm]

    if busqueda:
        term = busqueda.lower()
        data = [
            p for p in data
            if term in (p.get("codigo") or "").lower()
            or term in (p.get("nombre") or "").lower()
            or term in (p.get("descripcion") or "").lower()
        ]

    for p in data:
        completar_latlon_desde_utm(p)

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
            "dentro_zona_mezcla, zona_mezcla_observacion, "   # migración 013
            "ecas(id, codigo, nombre)"
        )
        .eq("id", punto_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        return None
    if res.data.get("cuenca"):
        res.data["cuenca"] = normalizar_cuenca(res.data["cuenca"])
    return completar_latlon_desde_utm(res.data)


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
        .select("codigo, nombre, descripcion, tipo, cuenca, sistema_hidrico, lugar_muestreo, "
                "utm_este, utm_norte, utm_zona, latitud, longitud, altitud_msnm, "
                "departamento, provincia, distrito, accesibilidad, representatividad, "
                "finalidad, eca_id, entidad_responsable")
        .eq("id", punto_id)
        .single()
        .execute()
    ).data or {}

    campos = _build_fila(datos)

    # Si se intenta cambiar el código, verificar que no esté en uso por otro punto
    nuevo_cod = campos.get("codigo")
    if nuevo_cod and nuevo_cod != anterior.get("codigo"):
        dup = (
            db.table("puntos_muestreo")
            .select("id")
            .eq("codigo", nuevo_cod)
            .neq("id", punto_id)
            .limit(1)
            .execute()
        ).data or []
        if dup:
            raise ValueError(f"Ya existe otro punto con código '{nuevo_cod}'.")

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
    """
    Cuencas únicas para selectores. Combina las canónicas con las existentes
    en BD (normalizadas), ordenadas: primero las canónicas en orden fijo,
    luego cualquier cuenca custom adicional.
    """
    db = get_admin_client()
    res = (
        db.table("puntos_muestreo")
        .select("cuenca")
        .execute()
    )
    en_bd = {
        normalizar_cuenca(r["cuenca"])
        for r in (res.data or [])
        if r.get("cuenca")
    }
    en_bd.discard(None)
    extras = sorted(en_bd - set(CUENCAS_CANONICAS))
    return list(CUENCAS_CANONICAS) + extras


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

    # Cuenca: aplicar normalización canónica si coincide con una conocida
    if fila.get("cuenca"):
        fila["cuenca"] = normalizar_cuenca(fila["cuenca"])

    campos_num = ("utm_este", "utm_norte", "latitud", "longitud", "altitud_msnm")
    for c in campos_num:
        if c in datos:
            fila[c] = datos[c] if datos[c] is not None else None

    # Auto-conversión UTM → WGS84 cuando se entregan UTM y no lat/lon.
    # Permite que los mapas (Geoportal, mapa de puntos) muestren puntos
    # ingresados solo con coordenadas UTM.
    if fila.get("utm_este") and fila.get("utm_norte"):
        if not fila.get("latitud") or not fila.get("longitud"):
            zona = fila.get("utm_zona") or datos.get("utm_zona") or "19S"
            lat, lon = utm_a_latlon(fila["utm_este"], fila["utm_norte"], zona)
            if lat is not None and lon is not None:
                fila["latitud"] = lat
                fila["longitud"] = lon

    if "eca_id" in datos:
        fila["eca_id"] = datos["eca_id"] or None

    if "activo" in datos:
        fila["activo"] = datos["activo"]

    # Art. 7 — zona de mezcla (migración 013)
    if "dentro_zona_mezcla" in datos:
        fila["dentro_zona_mezcla"] = bool(datos["dentro_zona_mezcla"])
    if "zona_mezcla_observacion" in datos:
        v = datos["zona_mezcla_observacion"]
        fila["zona_mezcla_observacion"] = (v.strip() if isinstance(v, str) and v.strip() else None)

    return fila
