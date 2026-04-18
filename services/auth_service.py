"""
services/auth_service.py
Lógica de autenticación y autorización sobre Supabase Auth.

Flujo:
  1. login(email, password)  →  llama a Supabase Auth sign_in_with_password
  2. Recupera el perfil del usuario desde la tabla 'usuarios' (auth_id = uid)
  3. Devuelve un dict con toda la info de sesión (sin exponer tokens al caller)

El módulo NO conoce Streamlit: solo trabaja con datos puros.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from gotrue.errors import AuthApiError

from database.client import get_client

Rol = Literal["administrador", "analista_lab", "tecnico_campo", "visualizador", "visitante"]

# Jerarquía operacional:
#   administrador  : control total (configura sistema, gestiona usuarios, valida)
#   analista_lab   : ingresa y valida resultados de laboratorio
#   tecnico_campo  : registra muestras y mediciones in-situ
#   visualizador   : solo lectura del sistema
#   visitante      : acceso público (geoportal, dashboards)
ROL_JERARQUIA: dict[Rol, int] = {
    "administrador": 5,
    "analista_lab":  4,
    "tecnico_campo": 3,
    "visualizador":  2,
    "visitante":     1,
}

# Etiquetas para la UI
ROL_LABELS: dict[Rol, str] = {
    "administrador": "Administrador",
    "analista_lab":  "Analista de laboratorio",
    "tecnico_campo": "Técnico de campo",
    "visualizador":  "Visualizador",
    "visitante":     "Visitante",
}


@dataclass
class SesionUsuario:
    """Información de la sesión activa. Se almacena en st.session_state."""
    uid: str            # UUID de Supabase Auth
    email: str
    nombre: str
    apellido: str
    rol: Rol
    institucion: str
    access_token: str   # JWT de Supabase
    refresh_token: str

    @property
    def nombre_completo(self) -> str:
        return f"{self.nombre} {self.apellido}"

    def tiene_rol(self, rol_minimo: Rol) -> bool:
        """True si el usuario tiene al menos el rol indicado."""
        return ROL_JERARQUIA.get(self.rol, 0) >= ROL_JERARQUIA.get(rol_minimo, 0)

    def es_admin(self) -> bool:
        return self.rol == "administrador"


class AuthError(Exception):
    """Error de autenticación con mensaje amigable para mostrar en UI."""


def login(email: str, password: str) -> SesionUsuario:
    """
    Autentica al usuario y devuelve su sesión.

    Raises:
        AuthError: si las credenciales son incorrectas o el usuario está inactivo.
    """
    db = get_client()

    # 1. Autenticar con Supabase Auth
    try:
        resp = db.auth.sign_in_with_password(
            {"email": email.strip().lower(), "password": password}
        )
    except AuthApiError as exc:
        _traducir_error(exc)   # siempre lanza AuthError

    if resp.user is None:
        raise AuthError("No se pudo obtener la sesión. Intenta de nuevo.")

    uid = resp.user.id

    # 2. Leer perfil desde la tabla 'usuarios'
    perfil = _obtener_perfil(db, uid)

    # 3. Verificar que la cuenta esté activa
    if not perfil.get("activo", True):
        db.auth.sign_out()
        raise AuthError("Tu cuenta está desactivada. Contacta al administrador.")

    return SesionUsuario(
        uid=uid,
        email=resp.user.email,
        nombre=perfil.get("nombre", ""),
        apellido=perfil.get("apellido", ""),
        rol=perfil.get("rol", "visitante"),
        institucion=perfil.get("institucion", ""),
        access_token=resp.session.access_token,
        refresh_token=resp.session.refresh_token,
    )


def logout(sesion: SesionUsuario | None = None) -> None:
    """Cierra la sesión en Supabase Auth."""
    try:
        get_client().auth.sign_out()
    except Exception:
        pass  # aunque falle en el servidor, la sesión local se borra en app.py


def cambiar_password(sesion: SesionUsuario, nueva_password: str) -> None:
    """Actualiza la contraseña del usuario autenticado."""
    if len(nueva_password) < 8:
        raise AuthError("La contraseña debe tener al menos 8 caracteres.")
    db = get_client()
    try:
        db.auth.update_user({"password": nueva_password})
    except AuthApiError as exc:
        _traducir_error(exc)


def obtener_perfil_por_uid(uid: str) -> dict:
    """Recupera el perfil desde la tabla 'usuarios' dado un auth_id."""
    return _obtener_perfil(get_client(), uid)


# ─── helpers privados ────────────────────────────────────────────────────────

def _obtener_perfil(db, uid: str) -> dict:
    """
    Busca el perfil en la tabla 'usuarios'.
    Si no existe (usuario creado en Auth pero sin perfil), devuelve defaults.
    """
    res = (
        db.table("usuarios")
        .select("nombre, apellido, rol, institucion, activo")
        .eq("auth_id", uid)
        .maybe_single()
        .execute()
    )
    if res.data is None:
        # Perfil no creado aún → rol mínimo por seguridad
        return {"nombre": "", "apellido": "", "rol": "visitante",
                "institucion": "", "activo": True}
    return res.data


def _traducir_error(exc: AuthApiError) -> None:
    """Convierte errores de Supabase Auth a mensajes en español y lanza AuthError."""
    msg = str(exc).lower()
    if "invalid login credentials" in msg or "invalid_credentials" in msg:
        raise AuthError("Correo o contraseña incorrectos.")
    if "email not confirmed" in msg:
        raise AuthError("Debes confirmar tu correo electrónico antes de ingresar.")
    if "too many requests" in msg:
        raise AuthError("Demasiados intentos fallidos. Espera unos minutos.")
    if "user not found" in msg:
        raise AuthError("No existe una cuenta con ese correo.")
    raise AuthError(f"Error de autenticación: {exc}")
