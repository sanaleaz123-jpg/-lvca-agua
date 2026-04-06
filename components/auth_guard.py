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

# Mensajes por rol requerido
_MENSAJES: dict[Rol, str] = {
    "administrador": "Solo los **administradores** pueden acceder a esta sección.",
    "visualizador":  "Necesitas al menos el rol **Visualizador** para ver esta sección.",
    "visitante":     "Debes iniciar sesión para continuar.",
}

# Páginas con etiquetas corregidas (con ñ/tildes) para el sidebar
_PAGINAS_NAV = [
    ("🏠 Inicio",               "pages/1_Inicio.py",            "visitante"),
    ("📅 Campañas",             "pages/2_Campanas.py",           "administrador"),
    ("🧪 Muestras de campo",    "pages/3_Muestras_Campo.py",     "administrador"),
    ("🔬 Resultados de lab",    "pages/4_Resultados_Lab.py",     "visualizador"),
    ("📋 Parámetros / ECAs",    "pages/5_Parametros.py",         "administrador"),
    ("📍 Puntos de muestreo",   "pages/6_Puntos_Muestreo.py",   "administrador"),
    ("🗺️ Geoportal",            "pages/7_Geoportal.py",          "visitante"),
    ("📄 Informes",             "pages/8_Informes.py",           "visualizador"),
    ("⚙️ Administración",       "pages/9_Administracion.py",     "administrador"),
    ("📊 Base Datos",           "pages/10_Base_Datos.py",        "visualizador"),
]

_ROL_NIVEL = {"administrador": 3, "visualizador": 2, "visitante": 1}


def _render_sidebar() -> None:
    """Renderiza el sidebar con navegación personalizada (etiquetas con ñ/tildes)."""
    sesion = st.session_state.get("sesion")
    if not sesion:
        return

    # Ocultar la navegación nativa de Streamlit (basada en nombres de archivo)
    st.markdown(
        "<style>[data-testid='stSidebarNav']{display:none}</style>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown("## 💧 LVCA")
        st.caption("AUTODEMA")
        st.divider()

        st.markdown(f"**{sesion.nombre_completo}**")
        st.caption(f"Rol: {sesion.rol.capitalize()}")
        st.divider()

        nivel_usuario = _ROL_NIVEL.get(sesion.rol, 1)
        for label, ruta, rol_minimo in _PAGINAS_NAV:
            if nivel_usuario >= _ROL_NIVEL.get(rol_minimo, 1):
                st.page_link(ruta, label=label)

        st.divider()
        if st.button("🚪 Cerrar sesión", use_container_width=True, key="btn_logout_guard"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def verificar_sesion() -> bool:
    """True si hay una sesión activa en session_state."""
    return st.session_state.get("sesion") is not None


def verificar_acceso(rol_minimo: Rol = "visitante") -> None:
    """
    Verifica sesión y rol. Si no cumple, muestra mensaje y detiene la página
    con st.stop() para que el resto del código no se ejecute.
    Renderiza el sidebar con navegación corregida.
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

    _render_sidebar()


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
    st.warning("### Acceso restringido")
    st.info("Por favor, inicia sesión para continuar.")
    if st.button("Ir al inicio de sesión", type="primary"):
        st.switch_page("app.py")


def _pantalla_acceso_denegado(rol_requerido: Rol, rol_actual: Rol) -> None:
    st.error("### Acceso denegado")
    st.write(_MENSAJES.get(rol_requerido, "No tienes permisos para esta sección."))
    st.caption(f"Tu rol actual: **{rol_actual.capitalize()}**")
    if st.button("← Volver al inicio"):
        st.switch_page("app.py")
