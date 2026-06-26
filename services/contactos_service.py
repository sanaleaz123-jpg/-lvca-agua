"""
services/contactos_service.py
Libreta de contactos (destinatarios) para el envío de informes por correo.

Tabla: contactos_informes (migración 025).

Funciones públicas:
    get_contactos(incluir_inactivos=False) -> list[dict]   (cacheado)
    crear_contacto(nombre, correo, entidad) -> dict
    desactivar_contacto(contacto_id) -> None
    correo_valido(correo) -> bool
"""

from __future__ import annotations

import re
from typing import Optional

from database.client import get_db
from services.cache import cached, invalidate_all

_TABLA = "contactos_informes"
_RE_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def correo_valido(correo: str) -> bool:
    return bool(_RE_CORREO.match((correo or "").strip()))


@cached(ttl=300, grupo="referencia")
def get_contactos(incluir_inactivos: bool = False) -> list[dict]:
    """Lista la libreta de contactos ordenada por entidad y nombre."""
    try:
        db = get_db()
        q = db.table(_TABLA).select("*")
        if not incluir_inactivos:
            q = q.eq("activo", True)
        res = q.order("entidad").order("nombre").execute()
        return res.data or []
    except Exception:
        # Tabla aún no creada (migración 025 pendiente) — sin libreta.
        return []


def crear_contacto(nombre: str, correo: str, entidad: Optional[str] = None) -> dict:
    """Alta de un contacto. Lanza ValueError si el correo es inválido o repetido."""
    nombre = (nombre or "").strip()
    correo = (correo or "").strip().lower()
    if not nombre:
        raise ValueError("El nombre del contacto es obligatorio.")
    if not correo_valido(correo):
        raise ValueError(f"Correo inválido: «{correo}».")

    db = get_db()
    existe = db.table(_TABLA).select("id").eq("correo", correo).limit(1).execute()
    if existe.data:
        raise ValueError(f"El correo «{correo}» ya está en la libreta.")

    res = db.table(_TABLA).insert({
        "nombre": nombre, "correo": correo,
        "entidad": (entidad or "").strip() or None, "activo": True,
    }).execute()
    invalidate_all()
    return (res.data or [{}])[0]


def desactivar_contacto(contacto_id: str) -> None:
    """Baja lógica de un contacto."""
    db = get_db()
    db.table(_TABLA).update({"activo": False}).eq("id", contacto_id).execute()
    invalidate_all()
