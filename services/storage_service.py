"""
services/storage_service.py
Gestión de archivos en Supabase Storage (croquis de puntos y fotos de campo).

Buckets requeridos en Supabase:
    - croquis        (público) — 1 imagen fija por punto de monitoreo
    - fotos-campo    (público) — múltiples fotos por muestra

Funciones públicas:
    upload_croquis(punto_id, file_bytes, content_type) → public_url
    get_croquis_url(punto_id) → str | None
    delete_croquis(punto_id) → None
    upload_foto_campo(muestra_id, file_bytes, filename, content_type) → public_url
    get_fotos_campo(muestra_id) → list[dict]
    delete_foto_campo(muestra_id, filename) → None
"""

from __future__ import annotations

import time
from io import BytesIO
from typing import Optional

from database.client import get_admin_client

BUCKET_CROQUIS = "croquis"
BUCKET_FOTOS = "fotos-campo"


_BUCKETS_VERIFIED: set[str] = set()


def _get_storage():
    return get_admin_client().storage


def _ensure_bucket(bucket: str, public: bool = True) -> None:
    """Crea el bucket si no existe (solo verifica una vez por sesión)."""
    if bucket in _BUCKETS_VERIFIED:
        return
    storage = _get_storage()
    try:
        storage.get_bucket(bucket)
    except Exception:
        try:
            storage.create_bucket(bucket, options={"public": public})
        except Exception:
            pass
    _BUCKETS_VERIFIED.add(bucket)


def _public_url(bucket: str, path: str) -> str:
    """Construye la URL pública de un archivo en storage."""
    res = _get_storage().from_(bucket).get_public_url(path)
    return res


# ─────────────────────────────────────────────────────────────────────────────
# Croquis (1 imagen fija por punto de monitoreo)
# ─────────────────────────────────────────────────────────────────────────────

def upload_croquis(punto_id: str, file_bytes: bytes, content_type: str = "image/jpeg") -> str:
    """Sube o reemplaza la imagen de croquis de un punto."""
    _ensure_bucket(BUCKET_CROQUIS)
    storage = _get_storage()
    # Determinar extensión correcta según content_type
    _ext_map = {
        "image/jpeg": ".jpg", "image/png": ".png",
        "image/gif": ".gif", "image/webp": ".webp",
    }
    ext = _ext_map.get(content_type, ".jpg")
    path = f"{punto_id}{ext}"
    # Intentar eliminar versiones anteriores (cualquier extensión)
    for old_ext in _ext_map.values():
        try:
            storage.from_(BUCKET_CROQUIS).remove([f"{punto_id}{old_ext}"])
        except Exception:
            pass
    storage.from_(BUCKET_CROQUIS).upload(
        path,
        file_bytes,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    return _public_url(BUCKET_CROQUIS, path)


def get_croquis_url(punto_id: str) -> Optional[str]:
    """Retorna la URL pública del croquis o None si no existe."""
    storage = _get_storage()
    try:
        files = storage.from_(BUCKET_CROQUIS).list(path="", options={"search": punto_id})
        for f in (files or []):
            name = f.get("name", "")
            if name.startswith(punto_id):
                return _public_url(BUCKET_CROQUIS, name)
    except Exception:
        pass
    return None


def delete_croquis(punto_id: str) -> None:
    """Elimina el croquis de un punto (cualquier extensión)."""
    storage = _get_storage()
    for ext in (".jpg", ".png", ".gif", ".webp"):
        try:
            storage.from_(BUCKET_CROQUIS).remove([f"{punto_id}{ext}"])
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Fotos de campo (múltiples por muestra)
# ─────────────────────────────────────────────────────────────────────────────

def upload_foto_campo(
    muestra_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str = "image/jpeg",
) -> str:
    """Sube una foto de campo asociada a una muestra."""
    _ensure_bucket(BUCKET_FOTOS)
    storage = _get_storage()
    ts = int(time.time() * 1000)
    # Limpiar nombre de archivo
    safe_name = filename.replace(" ", "_").replace("/", "_")
    path = f"{muestra_id}/{ts}_{safe_name}"
    storage.from_(BUCKET_FOTOS).upload(
        path,
        file_bytes,
        file_options={"content-type": content_type},
    )
    return _public_url(BUCKET_FOTOS, path)


def get_fotos_campo(muestra_id: str) -> list[dict]:
    """Lista las fotos de campo de una muestra."""
    storage = _get_storage()
    try:
        files = storage.from_(BUCKET_FOTOS).list(path=muestra_id)
        return [
            {
                "name": f["name"],
                "url": _public_url(BUCKET_FOTOS, f"{muestra_id}/{f['name']}"),
            }
            for f in (files or [])
            if f.get("name")
        ]
    except Exception:
        return []


def delete_foto_campo(muestra_id: str, filename: str) -> None:
    """Elimina una foto de campo específica."""
    try:
        _get_storage().from_(BUCKET_FOTOS).remove([f"{muestra_id}/{filename}"])
    except Exception:
        pass


def download_imagen(url: str) -> Optional[bytes]:
    """Descarga una imagen desde URL pública. Retorna bytes o None."""
    try:
        import httpx
        resp = httpx.get(url, timeout=15)
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None
