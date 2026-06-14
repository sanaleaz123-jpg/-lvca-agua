"""
services/logging_config.py
Configuración central de logging para la plataforma LVCA.

Antes, los errores se tragaban con `except Exception: pass` y no quedaba
ningún rastro, lo que hacía imposible diagnosticar fallos en producción
(Streamlit Cloud). Este módulo expone un logger único que escribe a stderr
(capturado por los logs de Streamlit Cloud) con nivel según el entorno.

Uso:
    from services.logging_config import get_logger
    logger = get_logger(__name__)

    logger.info("Operación completada")
    try:
        ...
    except Exception:
        logger.exception("Falló X")   # incluye el traceback completo
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def _configurar() -> None:
    """Configura el logger raíz 'lvca' una sola vez por proceso."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    try:
        from config.settings import IS_DEV
        nivel = logging.DEBUG if IS_DEV else logging.INFO
    except Exception:
        nivel = logging.INFO

    root = logging.getLogger("lvca")
    root.setLevel(nivel)
    # Evita handlers duplicados si el módulo se reimporta (reruns de Streamlit).
    if not root.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.addHandler(handler)
    # No propagar al root global para no duplicar con loggers de terceros.
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Devuelve un logger bajo el namespace 'lvca.<modulo>'.

    `name` suele ser `__name__`; se usa solo el último segmento como sufijo
    para mantener nombres cortos y legibles en los logs.
    """
    _configurar()
    sufijo = name.split(".")[-1]
    return logging.getLogger(f"lvca.{sufijo}")
