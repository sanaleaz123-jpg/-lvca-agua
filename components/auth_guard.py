"""
components/auth_guard.py
Decorador y función de guardia para controlar el acceso a páginas por rol.

Uso en cualquier página de /pages/:

    from components.auth_guard import require_rol

    @require_rol("visualizador")   # bloquea a visitantes
    def main():
        st.title("Resultados de laboratorio")
        ...

    main()

O sin decorador, para control manual:

    from components.auth_guard import verificar_acceso
    verificar_acceso("administrador")  # detiene la página si el rol no alcanza
"""

from __future__ import annotations

import functools
from typing import Callable

import streamlit as st

from services.auth_service import Rol, ROL_JERARQUIA
from components.ui_styles import aplicar_estilos

# Mensajes por rol requerido
_MENSAJES: dict[Rol, str] = {
    "administrador": "Solo los **administradores** pueden acceder a esta sección.",
    "analista_lab":  "Necesitas al menos el rol **Analista de laboratorio**.",
    "tecnico_campo": "Necesitas al menos el rol **Técnico de campo**.",
    "visualizador":  "Necesitas al menos el rol **Visualizador** para ver esta sección.",
    "visitante":     "Debes iniciar sesión para continuar.",
}

# Páginas agrupadas por sección
# (label, ruta, rol_minimo, seccion)
_PAGINAS_NAV = [
    ("Inicio",              "pages/1_Inicio.py",            "visitante",     "principal"),
    ("Campañas",            "pages/2_Campanas.py",          "tecnico_campo", "campo"),
    ("Muestras de campo",   "pages/3_Muestras_Campo.py",    "tecnico_campo", "campo"),
    ("Resultados de lab",   "pages/4_Resultados_Lab.py",    "analista_lab",  "datos"),
    ("Base de Datos",       "pages/10_Base_Datos.py",       "visualizador",  "datos"),
    ("Informes",            "pages/8_Informes.py",          "visualizador",  "datos"),
    ("Geoportal",           "pages/7_Geoportal.py",         "visitante",     "visualizacion"),
    ("Parámetros / ECAs",   "pages/5_Parametros.py",        "administrador", "config"),
    ("Puntos de muestreo",  "pages/6_Puntos_Muestreo.py",   "administrador", "config"),
    ("Administración",      "pages/9_Administracion.py",    "administrador", "config"),
]

def verificar_sesion() -> bool:
    """True si hay una sesión activa en session_state."""
    return st.session_state.get("sesion") is not None


def verificar_acceso(rol_minimo: Rol = "visitante") -> None:
    """
    Verifica sesión y rol. Si no cumple, muestra mensaje y detiene la página
    con st.stop() para que el resto del código no se ejecute.
    La navegación se sirve desde top_nav() dentro de cada página.
    """
    if not verificar_sesion():
        _pantalla_sin_sesion()
        st.stop()

    sesion = st.session_state["sesion"]
    nivel_usuario   = ROL_JERARQUIA.get(sesion.rol, 0)
    nivel_requerido = ROL_JERARQUIA.get(rol_minimo, 0)

    if nivel_usuario < nivel_requerido:
        _pantalla_acceso_denegado(rol_minimo, sesion.rol)
        st.stop()


def require_rol(rol_minimo: Rol = "visitante") -> Callable:
    """
    Decorador de función que aplica verificar_acceso() antes de ejecutar
    el cuerpo de la página.

        @require_rol("administrador")
        def main(): ...
    """
    def decorador(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            verificar_acceso(rol_minimo)
            return fn(*args, **kwargs)
        return wrapper
    return decorador


# ─── pantallas de bloqueo ─────────────────────────────────────────────────────

def _pantalla_sin_sesion() -> None:
    aplicar_estilos()
    st.warning("### Acceso restringido")
    st.info("Por favor, inicia sesión para continuar.")
    if st.button("Ir al inicio de sesión", type="primary"):
        st.switch_page("app.py")


def _pantalla_acceso_denegado(rol_requerido: Rol, rol_actual: Rol) -> None:
    aplicar_estilos()
    st.error("### Acceso denegado")
    st.write(_MENSAJES.get(rol_requerido, "No tienes permisos para esta sección."))
    st.caption(f"Tu rol actual: **{rol_actual.capitalize()}**")
    if st.button("← Volver al inicio"):
        st.switch_page("app.py")
