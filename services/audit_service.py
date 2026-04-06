"""
services/audit_service.py
Servicio de auditoría para registrar cambios en parámetros y puntos de muestreo.

Intenta escribir en la tabla `audit_log` de Supabase. Si la tabla no existe
(migración 004 pendiente), almacena los registros en un archivo JSON local.

Funciones públicas:
    registrar_cambio(tabla, registro_id, accion, ...)
    get_historial(tabla, registro_id)  → lista de cambios
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from database.client import get_admin_client

_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "audit_log.json"
_DB_AVAILABLE: bool | None = None  # cache tras primer intento


def _check_db() -> bool:
    """Verifica si la tabla audit_log existe en la BD."""
    global _DB_AVAILABLE
    if _DB_AVAILABLE is not None:
        return _DB_AVAILABLE
    try:
        db = get_admin_client()
        db.table("audit_log").select("id").limit(1).execute()
        _DB_AVAILABLE = True
    except Exception:
        _DB_AVAILABLE = False
    return _DB_AVAILABLE


def _write_local(entry: dict) -> None:
    """Escribe en el archivo JSON local como fallback."""
    entries = []
    if _LOG_PATH.exists():
        try:
            entries = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            entries = []
    entries.append(entry)
    # Mantener últimos 5000 registros
    if len(entries) > 5000:
        entries = entries[-5000:]
    _LOG_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")


def registrar_cambio(
    tabla: str,
    registro_id: str,
    accion: str,
    campo: Optional[str] = None,
    valor_anterior: Optional[str] = None,
    valor_nuevo: Optional[str] = None,
    usuario_id: Optional[str] = None,
) -> None:
    """
    Registra un cambio en el audit log.

    Args:
        tabla: nombre de la tabla ('parametros', 'puntos_muestreo')
        registro_id: UUID del registro afectado
        accion: 'crear', 'editar', 'eliminar', 'desactivar', 'activar'
        campo: campo modificado (None para crear/eliminar)
        valor_anterior: valor previo como string
        valor_nuevo: valor nuevo como string
        usuario_id: identificador del usuario
    """
    entry = {
        "tabla": tabla,
        "registro_id": str(registro_id),
        "accion": accion,
        "campo": campo,
        "valor_anterior": valor_anterior,
        "valor_nuevo": valor_nuevo,
        "usuario_id": usuario_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    if _check_db():
        try:
            db = get_admin_client()
            db.table("audit_log").insert(entry).execute()
            return
        except Exception:
            pass

    # Fallback: local JSON
    _write_local(entry)


def registrar_cambios_multiples(
    tabla: str,
    registro_id: str,
    accion: str,
    cambios: dict[str, tuple[str | None, str | None]],
    usuario_id: Optional[str] = None,
) -> None:
    """
    Registra múltiples cambios de campo en una sola operación.

    cambios: {campo: (valor_anterior, valor_nuevo)}
    Solo registra los campos que efectivamente cambiaron.
    """
    for campo, (ant, nuevo) in cambios.items():
        if str(ant) != str(nuevo):
            registrar_cambio(
                tabla=tabla,
                registro_id=registro_id,
                accion=accion,
                campo=campo,
                valor_anterior=str(ant) if ant is not None else None,
                valor_nuevo=str(nuevo) if nuevo is not None else None,
                usuario_id=usuario_id,
            )


def get_historial(
    tabla: str,
    registro_id: Optional[str] = None,
    limite: int = 50,
) -> list[dict]:
    """
    Retorna el historial de cambios para una tabla y/o registro.
    Ordenados por fecha descendente.
    """
    if _check_db():
        try:
            db = get_admin_client()
            q = (
                db.table("audit_log")
                .select("*")
                .eq("tabla", tabla)
                .order("created_at", desc=True)
                .limit(limite)
            )
            if registro_id:
                q = q.eq("registro_id", registro_id)
            return q.execute().data or []
        except Exception:
            pass

    # Fallback: local JSON
    if not _LOG_PATH.exists():
        return []
    try:
        entries = json.loads(_LOG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception):
        return []

    filtered = [
        e for e in entries
        if e.get("tabla") == tabla
        and (registro_id is None or e.get("registro_id") == registro_id)
    ]
    filtered.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return filtered[:limite]
