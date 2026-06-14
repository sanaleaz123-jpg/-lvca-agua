"""
services/cache.py
Decorador de caché compatible con Streamlit y con entornos sin Streamlit.

Uso:
    from services.cache import cached

    @cached(ttl=300)                      # dato operacional (por defecto)
    def mi_funcion_costosa(arg1, arg2):
        ...

    @cached(ttl=600, grupo="referencia")  # dato de referencia (cambia rara vez)
    def get_limites_eca():
        ...

Invalidación selectiva (ver más abajo):
    from services.cache import invalidate_operational, invalidate_all

    invalidate_operational()  # tras crear/editar muestras, resultados, campañas
    invalidate_all()          # tras editar parámetros, ECAs, puntos (referencia)
"""

from __future__ import annotations

import functools
import time
from typing import Any, Callable

_USE_ST_CACHE = False
_st_cache_data: Any = None

try:
    from streamlit import cache_data
    _USE_ST_CACHE = True
    _st_cache_data = cache_data
except ImportError:
    pass


# Registro de funciones cacheadas por grupo, para invalidación selectiva.
# Cada valor es la lista de funciones cacheadas (todas exponen .clear()).
_REGISTRY: dict[str, list[Any]] = {}


def _registrar(grupo: str, fn: Any) -> None:
    _REGISTRY.setdefault(grupo, []).append(fn)


def cached(
    ttl: int = 300,
    show_spinner: bool = False,
    grupo: str = "operacional",
) -> Callable:
    """
    Decorador de caché.
    - En Streamlit: usa @st.cache_data con TTL
    - Fuera de Streamlit: caché simple en memoria con TTL

    `grupo` habilita la invalidación selectiva:
      - "operacional" (por defecto): datos que cambian con el trabajo diario
        (campañas, muestras, resultados, dashboard, geoportal). Se limpian en
        cada escritura operacional.
      - "referencia": datos que casi nunca cambian (parámetros, ECAs, catálogo
        de puntos, cuencas, tipos). NO se limpian al registrar/editar muestras o
        resultados; solo cuando se editan en sus propias pantallas de admin.
    """
    def decorator(func: Callable) -> Callable:
        if _USE_ST_CACHE:
            wrapped = _st_cache_data(ttl=ttl, show_spinner=show_spinner)(func)
            _registrar(grupo, wrapped)
            return wrapped

        # Fallback: caché simple con TTL
        _cache: dict[str, tuple[float, Any]] = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key = str(args) + str(sorted(kwargs.items()))
            now = time.time()
            if key in _cache:
                ts, val = _cache[key]
                if now - ts < ttl:
                    return val
            result = func(*args, **kwargs)
            _cache[key] = (now, result)
            return result

        wrapper.clear = _cache.clear  # type: ignore[attr-defined]
        _registrar(grupo, wrapper)
        return wrapper

    return decorator


def invalidate(*grupos: str) -> None:
    """Limpia el caché de los grupos indicados (p. ej. invalidate("operacional"))."""
    for grupo in grupos:
        for fn in _REGISTRY.get(grupo, []):
            try:
                fn.clear()
            except Exception:
                pass


def invalidate_operational() -> None:
    """
    Invalida solo los datos operacionales (campañas, muestras, resultados,
    dashboard, geoportal). Los datos de referencia (parámetros, ECAs, catálogo
    de puntos) se conservan: no cambian al registrar/editar muestras o resultados.
    Usar tras una mutación de datos operacionales.
    """
    invalidate("operacional")


def invalidate_all() -> None:
    """
    Invalida TODO el caché (operacional + referencia). Usar tras mutaciones de
    datos de referencia (alta/edición de parámetros, ECAs, puntos), que pueden
    repercutir también en vistas operacionales.
    """
    if _USE_ST_CACHE:
        try:
            _st_cache_data.clear()
        except Exception:
            pass
    else:
        for fns in _REGISTRY.values():
            for fn in fns:
                try:
                    fn.clear()
                except Exception:
                    pass
