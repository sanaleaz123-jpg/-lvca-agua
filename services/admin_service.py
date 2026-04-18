"""
services/admin_service.py
Lógica de negocio para administración del sistema.

Funciones públicas:
    get_usuarios()                              → lista de usuarios con perfil
    get_usuario(usuario_id)                     → detalle
    actualizar_rol(usuario_id, nuevo_rol)       → cambiar rol
    toggle_usuario(usuario_id, activo)          → activar/desactivar
    crear_usuario(email, password, datos)       → crear en Auth + perfil
    get_estadisticas_sistema()                  → métricas generales
    get_actividad_reciente(dias)                → últimas muestras y resultados
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from database.client import get_admin_client
from services.auth_service import Rol


ROLES: list[Rol] = ["administrador", "analista_lab", "tecnico_campo", "visualizador", "visitante"]


# ─────────────────────────────────────────────────────────────────────────────
# Gestión de usuarios
# ─────────────────────────────────────────────────────────────────────────────

def get_usuarios() -> list[dict]:
    """Lista todos los usuarios registrados en la tabla 'usuarios' con email de Auth."""
    db = get_admin_client()
    res = (
        db.table("usuarios")
        .select("id, auth_id, nombre, apellido, rol, institucion, activo, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    usuarios = res.data or []

    # Obtener emails desde Supabase Auth
    try:
        auth_users = db.auth.admin.list_users()
        email_map = {str(u.id): u.email for u in auth_users}
    except Exception:
        email_map = {}

    for u in usuarios:
        u["email"] = email_map.get(u.get("auth_id", ""), "—")

    return usuarios


def get_usuario(usuario_id: str) -> dict | None:
    """Detalle de un usuario con email de Auth."""
    db = get_admin_client()
    res = (
        db.table("usuarios")
        .select("id, auth_id, nombre, apellido, rol, institucion, activo, created_at")
        .eq("id", usuario_id)
        .maybe_single()
        .execute()
    )
    if not res.data:
        return None

    usuario = res.data
    # Obtener email desde Auth
    try:
        auth_user = db.auth.admin.get_user_by_id(usuario["auth_id"])
        usuario["email"] = auth_user.user.email
    except Exception:
        usuario["email"] = "—"

    return usuario


def actualizar_usuario(usuario_id: str, datos: dict) -> dict:
    """Actualiza nombre, apellido, institución de un usuario."""
    db = get_admin_client()
    campos = {}
    for key in ("nombre", "apellido", "institucion"):
        if key in datos:
            campos[key] = datos[key].strip() if datos[key] else None
    res = (
        db.table("usuarios")
        .update(campos)
        .eq("id", usuario_id)
        .execute()
    )
    return res.data[0] if res.data else {}


def actualizar_rol(usuario_id: str, nuevo_rol: Rol) -> None:
    """Cambia el rol de un usuario."""
    if nuevo_rol not in ROLES:
        raise ValueError(f"Rol inválido: {nuevo_rol}")
    db = get_admin_client()
    db.table("usuarios").update({"rol": nuevo_rol}).eq("id", usuario_id).execute()


def toggle_usuario(usuario_id: str, activo: bool) -> None:
    """Activa o desactiva un usuario."""
    db = get_admin_client()
    db.table("usuarios").update({"activo": activo}).eq("id", usuario_id).execute()


def eliminar_usuario(usuario_id: str) -> None:
    """
    Elimina un usuario de la tabla 'usuarios' y de Supabase Auth.
    Solo si el usuario no tiene muestras ni resultados asociados.
    """
    db = get_admin_client()

    # Obtener auth_id
    usuario = (
        db.table("usuarios")
        .select("auth_id")
        .eq("id", usuario_id)
        .maybe_single()
        .execute()
    )
    if not usuario.data:
        raise ValueError("Usuario no encontrado.")

    auth_id = usuario.data["auth_id"]

    # Verificar muestras como técnico
    m_count = (
        db.table("muestras")
        .select("id", count="exact")
        .eq("tecnico_campo_id", usuario_id)
        .execute()
    )
    if (m_count.count or 0) > 0:
        raise ValueError(
            f"No se puede eliminar: el usuario es técnico en {m_count.count} muestra(s)."
        )

    # Eliminar perfil de la tabla usuarios
    db.table("usuarios").delete().eq("id", usuario_id).execute()

    # Eliminar de Supabase Auth
    try:
        db.auth.admin.delete_user(auth_id)
    except Exception:
        pass  # Si falla Auth, el perfil ya fue eliminado


def resetear_password(usuario_id: str, nueva_password: str) -> None:
    """Resetea la contraseña de un usuario vía Supabase Auth Admin API."""
    if len(nueva_password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")

    db = get_admin_client()

    # Obtener auth_id
    usuario = (
        db.table("usuarios")
        .select("auth_id")
        .eq("id", usuario_id)
        .maybe_single()
        .execute()
    )
    if not usuario.data:
        raise ValueError("Usuario no encontrado.")

    db.auth.admin.update_user_by_id(
        usuario.data["auth_id"],
        {"password": nueva_password},
    )


def crear_usuario(
    email: str,
    password: str,
    nombre: str,
    apellido: str,
    rol: Rol = "visitante",
    institucion: str = "",
) -> dict:
    """
    Crea un usuario en Supabase Auth y registra su perfil en la tabla 'usuarios'.
    """
    db = get_admin_client()

    # Crear en Supabase Auth (admin API)
    auth_resp = db.auth.admin.create_user({
        "email": email.strip().lower(),
        "password": password,
        "email_confirm": True,
    })

    uid = auth_resp.user.id

    # Crear perfil en la tabla usuarios
    perfil = {
        "auth_id":      uid,
        "nombre":       nombre.strip(),
        "apellido":     apellido.strip(),
        "rol":          rol,
        "institucion":  institucion.strip() or None,
        "activo":       True,
    }
    res = db.table("usuarios").insert(perfil).execute()
    resultado = res.data[0] if res.data else perfil
    resultado["email"] = email.strip().lower()
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# Estadísticas del sistema
# ─────────────────────────────────────────────────────────────────────────────

def get_estadisticas_sistema() -> dict:
    """Métricas generales del sistema."""
    db = get_admin_client()

    usuarios = db.table("usuarios").select("id", count="exact").execute()
    campanas = db.table("campanas").select("id", count="exact").execute()
    muestras = db.table("muestras").select("id", count="exact").execute()
    resultados = db.table("resultados_laboratorio").select("id", count="exact").execute()
    parametros = db.table("parametros").select("id", count="exact").eq("activo", True).execute()
    puntos = db.table("puntos_muestreo").select("id", count="exact").eq("activo", True).execute()

    return {
        "usuarios":   usuarios.count or 0,
        "campanas":   campanas.count or 0,
        "muestras":   muestras.count or 0,
        "resultados": resultados.count or 0,
        "parametros": parametros.count or 0,
        "puntos":     puntos.count or 0,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Actividad reciente
# ─────────────────────────────────────────────────────────────────────────────

def get_actividad_reciente(dias: int = 7) -> dict:
    """
    Actividad reciente del sistema:
        ultimas_muestras, ultimos_resultados, campanas_activas
    """
    db = get_admin_client()
    fecha_corte = (datetime.utcnow() - timedelta(days=dias)).date().isoformat()

    # Últimas muestras
    m_res = (
        db.table("muestras")
        .select(
            "codigo, fecha_muestreo, estado, "
            "puntos_muestreo(codigo, nombre), "
            "campanas(codigo)"
        )
        .gte("fecha_muestreo", fecha_corte)
        .order("fecha_muestreo", desc=True)
        .limit(20)
        .execute()
    )

    # Campañas activas (no completadas ni anuladas)
    c_res = (
        db.table("campanas")
        .select("codigo, nombre, estado, fecha_inicio, fecha_fin")
        .in_("estado", ["planificada", "en_campo", "en_laboratorio"])
        .order("fecha_inicio", desc=True)
        .execute()
    )

    return {
        "ultimas_muestras":   m_res.data or [],
        "campanas_activas":   c_res.data or [],
    }
