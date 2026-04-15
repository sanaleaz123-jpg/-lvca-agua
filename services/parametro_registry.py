"""
services/parametro_registry.py
Registro centralizado de parámetros leído dinámicamente desde la base de datos.

Todas las páginas y servicios que necesiten la lista de parámetros deben
usar este módulo en lugar de listas hardcodeadas.  Cuando se añade, edita
o desactiva un parámetro desde la página de Parámetros, basta con llamar
a ``invalidar_cache_parametros()`` para que el cambio se propague a:

    - Base de Datos consolidada
    - Cadena de custodia
    - Fichas de campo / Muestras in situ
    - Informes
    - Geoportal

Funciones públicas:
    get_parametros_activos()       → todos los parámetros activos desde la BD
    get_columnas_parametros()      → [(codigo, label), ...] para tablas pivotadas
    get_codigos_parametros()       → [codigo, ...]
    get_cat_params()               → {"Campo (In situ)": ["P001",...], ...}
    get_parametros_insitu()        → parámetros de campo con clave y unidad
    get_campo_a_parametro_map()    → {"ph": "P001", ...}
    get_insitu_a_cadena_map()      → {"ph": "ph", "oxigeno_disuelto": "od", ...}
    get_parametros_lab_cadena()    → parámetros de laboratorio para cadena de custodia
    get_parametros_campo_cadena()  → parámetros de campo para cadena de custodia
    invalidar_cache_parametros()   → limpiar caché tras CRUD de parámetros
"""

from __future__ import annotations

import json
from pathlib import Path

from database.client import get_admin_client
from services.cache import cached

# ─────────────────────────────────────────────────────────────────────────────
# Preservante / Tipo de frasco — configuración por parámetro
# ─────────────────────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "parametros_config.json"

PRESERVANTES_OPCIONES = ["HCl", "Formol", "Ninguno"]

TIPOS_FRASCO_OPCIONES = [
    "Vidrio ámbar 500 ml",
    "Polipropileno 500 ml",
    "Polipropileno 250 ml",
    "Polipropileno 120 ml",
    "Polipropileno 1000 ml",
    "Polipropileno ámbar 120 ml",
]


def _leer_config() -> dict:
    """Lee el JSON de configuración de preservante/tipo_frasco."""
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _guardar_config(data: dict) -> None:
    """Guarda el JSON de configuración."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(data, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )


def get_param_config(codigo: str) -> dict:
    """Retorna {preservante, tipo_frasco} para un código de parámetro."""
    cfg = _leer_config()
    return cfg.get(codigo, {"preservante": "Ninguno", "tipo_frasco": ""})


def set_param_config(codigo: str, preservante: str, tipo_frasco: str) -> None:
    """Guarda la config de preservante/tipo_frasco para un parámetro."""
    cfg = _leer_config()
    cfg[codigo] = {"preservante": preservante, "tipo_frasco": tipo_frasco}
    _guardar_config(cfg)


def get_all_param_configs() -> dict[str, dict]:
    """Retorna toda la configuración: {codigo: {preservante, tipo_frasco}}."""
    return _leer_config()


# ─────────────────────────────────────────────────────────────────────────────
# Clasificación de categorías
# ─────────────────────────────────────────────────────────────────────────────

_CAT_ORDER = {"Campo": 0, "Fisicoquimico": 1, "Hidrobiologico": 2}

_CAT_DISPLAY = {
    "Campo": "Parámetros de Campo",
    "Fisicoquimico": "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)",
    "Hidrobiologico": "Parámetros Hidrobiológicos",
}

_CAT_DISPLAY_INV = {v: k for k, v in _CAT_DISPLAY.items()}

# Normalización: nombre de categoría en BD → nombre interno corto
_CAT_NORMALIZE: dict[str, str] = {
    # Nombres nuevos (actuales en BD)
    "Parámetros de Campo": "Campo",
    "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)": "Fisicoquimico",
    "Parámetros Hidrobiológicos": "Hidrobiologico",
    # Nombres legacy (por si quedan en caché o datos viejos)
    "Campo": "Campo",
    "Fisicoquimico": "Fisicoquimico",
    "Hidrobiologico": "Hidrobiologico",
    "Metales": "Fisicoquimico",
}

_CATEGORIAS_EXCLUIDAS = {"Plaguicidas", "Microbiologico"}

# Códigos que siempre son "Campo" independientemente de su categoría en BD
_CODIGOS_CAMPO = {"P001", "P002", "P003", "P004", "P006", "P008", "P009"}


# ─────────────────────────────────────────────────────────────────────────────
# Mapeos fijos ligados al esquema de mediciones_insitu
# (la tabla mediciones_insitu usa claves texto como "ph", "temperatura", etc.)
# ─────────────────────────────────────────────────────────────────────────────

_CLAVE_INSITU_A_CODIGO = {
    "ph":               "P001",
    "temperatura":      "P002",
    "conductividad":    "P003",
    "oxigeno_disuelto": "P004",
    "turbidez":         "P006",
    "tds":              "P009",
    "salinidad":        "P008",
}

_CODIGO_A_CLAVE_INSITU = {v: k for k, v in _CLAVE_INSITU_A_CODIGO.items()}

_INSITU_A_CADENA = {
    "ph": "ph",
    "temperatura": "temperatura",
    "turbidez": "turbidez",
    "conductividad": "conductividad",
    "oxigeno_disuelto": "od",
    "salinidad": "salinidad",
    "tds": "tds",
}


# ─────────────────────────────────────────────────────────────────────────────
# Consulta base (cacheada)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_parametros_activos() -> list[dict]:
    """
    Todos los parámetros activos con categoría y unidad, ordenados por código.
    """
    db = get_admin_client()
    res = (
        db.table("parametros")
        .select(
            "id, codigo, nombre, activo, "
            "categorias_parametro(id, nombre), "
            "unidades_medida(id, simbolo, nombre)"
        )
        .eq("activo", True)
        .order("codigo")
        .execute()
    )
    return res.data or []


# Parámetros reclasificados por decisión funcional
_RECLASIFICAR_A_FISICOQUIMICO = {"P124"}  # Clorofila A → Fisicoquímico


def clasificar_categoria(param: dict) -> str:
    """Determina la categoría normalizada de un parámetro."""
    cat_raw = (param.get("categorias_parametro") or {}).get("nombre", "")
    codigo = param.get("codigo", "")
    if codigo in _CODIGOS_CAMPO:
        return "Campo"
    if codigo in _RECLASIFICAR_A_FISICOQUIMICO:
        return "Fisicoquimico"
    return _CAT_NORMALIZE.get(cat_raw, cat_raw)


# ─────────────────────────────────────────────────────────────────────────────
# Funciones públicas — reemplazan constantes hardcodeadas
# ─────────────────────────────────────────────────────────────────────────────

def get_columnas_parametros() -> list[tuple[str, str]]:
    """
    Reemplazo dinámico de ``COLUMNAS_PARAMETROS``.
    Retorna ``[(codigo, label), ...]`` ordenados por categoría → código.
    """
    params = get_parametros_activos()
    items: list[tuple[str, str, int]] = []

    for p in params:
        cat = clasificar_categoria(p)
        if cat in _CATEGORIAS_EXCLUIDAS:
            continue
        codigo = p.get("codigo", "")
        nombre = p.get("nombre", "")
        unidad = (p.get("unidades_medida") or {}).get("simbolo", "")
        label = f"{nombre} ({unidad})" if unidad else nombre
        order = _CAT_ORDER.get(cat, 99)
        items.append((codigo, label, order))

    items.sort(key=lambda x: (x[2], x[0]))
    return [(cod, lbl) for cod, lbl, _ in items]


def get_codigos_parametros() -> list[str]:
    """Reemplazo dinámico de ``CODIGOS_PARAMETROS``."""
    return [cod for cod, _ in get_columnas_parametros()]


def get_cat_params() -> dict[str, list[str]]:
    """
    Reemplazo dinámico de ``cat_params``.
    Retorna ``{"Campo (In situ)": ["P001",...], "Fisicoquímico": [...], ...}``
    """
    params = get_parametros_activos()
    cats: dict[str, list[str]] = {}

    for p in params:
        cat = clasificar_categoria(p)
        if cat in _CATEGORIAS_EXCLUIDAS:
            continue
        display = _CAT_DISPLAY.get(cat, cat)
        cats.setdefault(display, []).append(p.get("codigo", ""))

    # Orden consistente: Campo → Fisicoquímico → Hidrobiológico → otros
    ordered: dict[str, list[str]] = {}
    for int_name in ["Campo", "Fisicoquimico", "Hidrobiologico"]:
        display_name = _CAT_DISPLAY.get(int_name, int_name)
        if display_name in cats:
            ordered[display_name] = sorted(cats[display_name])
    for k, v in cats.items():
        if k not in ordered:
            ordered[k] = sorted(v)

    return ordered


def get_parametros_insitu() -> list[dict]:
    """
    Reemplazo dinámico de ``PARAMETROS_INSITU``.
    Retorna parámetros de campo con clave, nombre, unidad y código.
    """
    params = get_parametros_activos()
    result = []
    for p in params:
        codigo = p.get("codigo", "")
        clave = _CODIGO_A_CLAVE_INSITU.get(codigo)
        if not clave:
            continue
        unidad = (p.get("unidades_medida") or {}).get("simbolo", "")
        result.append({
            "clave": clave,
            "nombre": p.get("nombre", ""),
            "unidad": unidad,
            "codigo": codigo,
        })

    # Orden fijo según la convención de medición
    clave_order = list(_CLAVE_INSITU_A_CODIGO.keys())
    result.sort(key=lambda x: clave_order.index(x["clave"]) if x["clave"] in clave_order else 99)
    return result


def get_campo_a_parametro_map() -> dict[str, str]:
    """Reemplazo dinámico de ``_CAMPO_A_PARAMETRO``. Retorna ``{clave: codigo}``."""
    return dict(_CLAVE_INSITU_A_CODIGO)


def get_insitu_a_cadena_map() -> dict[str, str]:
    """Reemplazo de ``_INSITU_MAP``. Retorna ``{clave_insitu: clave_cadena}``."""
    return dict(_INSITU_A_CADENA)


def get_parametros_lab_cadena() -> list[dict]:
    """
    Reemplazo dinámico de ``PARAMETROS_LAB_DEFAULT``.
    Retorna parámetros de laboratorio (no campo) para la cadena de custodia.
    """
    params = get_parametros_activos()
    result = []
    for p in params:
        cat = clasificar_categoria(p)
        if cat in _CATEGORIAS_EXCLUIDAS or cat == "Campo":
            continue
        codigo = p.get("codigo", "")
        result.append({
            "clave": codigo.lower(),
            "nombre": p.get("nombre", ""),
            "codigo": codigo,
        })
    return result


def get_parametros_campo_cadena() -> list[dict]:
    """
    Reemplazo dinámico de ``PARAMETROS_CAMPO``.
    Retorna parámetros de campo para la cadena de custodia.
    """
    insitu = get_parametros_insitu()
    result = []
    for p in insitu:
        clave_cadena = _INSITU_A_CADENA.get(p["clave"], p["clave"])
        unidad = p.get("unidad", "")
        nombre = p.get("nombre", "")
        label = f"{nombre} ({unidad})" if unidad else nombre
        result.append({
            "clave": clave_cadena,
            "nombre": label,
            "codigo": p.get("codigo", ""),
        })
    return result


def invalidar_cache_parametros() -> None:
    """Limpia todos los cachés relacionados con parámetros."""
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass
