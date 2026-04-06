"""
services/cache.py
Decorador de caché compatible con Streamlit y con entornos sin Streamlit.

Uso:
    from services.cache import cached

    @cached(ttl=300)
    def mi_funcion_costosa(arg1, arg2):
        ...
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


def cached(ttl: int = 300, show_spinner: bool = False) -> Callable:
    """
    Decorador de caché.
    - En Streamlit: usa @st.cache_data con TTL
    - Fuera de Streamlit: caché simple en memoria con TTL
    """
    def decorator(func: Callable) -> Callable:
        if _USE_ST_CACHE:
            return _st_cache_data(ttl=ttl, show_spinner=show_spinner)(func)

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
        return wrapper

    return decorator
