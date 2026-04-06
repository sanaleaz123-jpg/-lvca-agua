"""
app.py
Punto de entrada de la aplicación Streamlit LVCA – AUTODEMA.

Responsabilidades:
  - Mostrar la pantalla de login si no hay sesión activa.
  - Almacenar la sesión en st.session_state["sesion"].
  - Redirigir al dashboard apropiado según el rol del usuario.
  - Exponer el menú de navegación lateral con las páginas permitidas por rol.

Ejecución:
    streamlit run app.py
"""

import streamlit as st

from config.settings import APP_NOMBRE, APP_ENTIDAD, APP_VERSION
from services.auth_service import login, logout, AuthError, SesionUsuario

# ─── configuración global de la app ──────────────────────────────────────────
st.set_page_config(
    page_title=APP_NOMBRE,
    page_icon="💧",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "About": f"**{APP_NOMBRE}**\n{APP_ENTIDAD}\nv{APP_VERSION}",
        "Report a bug": None,
        "Get help": None,
    },
)

# ─── definición de páginas por rol ───────────────────────────────────────────
# Cada entrada: (label, ruta_streamlit, rol_minimo)
PAGINAS = [
    ("🏠 Inicio",               "pages/1_Inicio.py",            "visitante"),
    ("📅 Campañas",             "pages/2_Campanas.py",           "administrador"),
    ("🧪 Muestras de campo",    "pages/3_Muestras_Campo.py",     "administrador"),
    ("🔬 Resultados de lab",    "pages/4_Resultados_Lab.py",     "visualizador"),
    ("📋 Parámetros / ECAs",    "pages/5_Parametros.py",         "administrador"),
    ("📍 Puntos de muestreo",   "pages/6_Puntos_Muestreo.py",   "administrador"),
    ("🗺️  Geoportal",            "pages/7_Geoportal.py",          "visitante"),
    ("📄 Informes",             "pages/8_Informes.py",           "visualizador"),
    ("⚙️  Administración",       "pages/9_Administracion.py",    "administrador"),
]

_ROL_NIVEL = {"administrador": 3, "visualizador": 2, "visitante": 1}


# ─── helpers de sesión ────────────────────────────────────────────────────────

def _sesion_activa() -> SesionUsuario | None:
    return st.session_state.get("sesion")


def _iniciar_sesion(sesion: SesionUsuario) -> None:
    st.session_state["sesion"] = sesion


def _cerrar_sesion() -> None:
    sesion = _sesion_activa()
    if sesion:
        logout(sesion)
    for key in list(st.session_state.keys()):
        del st.session_state[key]


# ─── pantalla de login ────────────────────────────────────────────────────────

def _pantalla_login() -> None:
    # Centrar el formulario
    col_izq, col_centro, col_der = st.columns([1, 1.6, 1])

    with col_centro:
        st.markdown("<br><br>", unsafe_allow_html=True)

        # Logo / cabecera
        st.markdown(
            f"""
            <div style="text-align:center; margin-bottom:1.5rem;">
                <h1 style="font-size:2.2rem; margin-bottom:0;">💧 LVCA</h1>
                <p style="color:#555; margin:0;">Laboratorio de Calidad de Agua</p>
                <p style="color:#888; font-size:.85rem;">{APP_ENTIDAD}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("form_login", clear_on_submit=False):
            st.markdown("### Iniciar sesión")
            email    = st.text_input("Correo electrónico", placeholder="usuario@autodema.gob.pe")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Ingresar", type="primary", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Completa todos los campos.")
            else:
                with st.spinner("Verificando credenciales..."):
                    try:
                        sesion = login(email, password)
                        _iniciar_sesion(sesion)
                        st.rerun()
                    except AuthError as exc:
                        st.error(str(exc))

        st.markdown(
            f"<p style='text-align:center;color:#aaa;font-size:.75rem;"
            f"margin-top:2rem;'>v{APP_VERSION}</p>",
            unsafe_allow_html=True,
        )


# ─── barra lateral con navegación ─────────────────────────────────────────────

def _sidebar(sesion: SesionUsuario) -> None:
    # Ocultar la navegación nativa de Streamlit (basada en nombres de archivo)
    st.markdown(
        "<style>[data-testid='stSidebarNav']{display:none}</style>",
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.markdown(f"## 💧 LVCA")
        st.caption(APP_ENTIDAD)
        st.divider()

        # Info del usuario
        st.markdown(f"**{sesion.nombre_completo}**")
        _badge_rol(sesion.rol)
        if sesion.institucion:
            st.caption(sesion.institucion)
        st.divider()

        # Navegación filtrada por rol
        st.markdown("**Navegación**")
        nivel_usuario = _ROL_NIVEL.get(sesion.rol, 1)

        for label, ruta, rol_minimo in PAGINAS:
            if nivel_usuario >= _ROL_NIVEL.get(rol_minimo, 1):
                st.page_link(ruta, label=label)

        st.divider()

        # Botón de cerrar sesión
        if st.button("🚪 Cerrar sesión", use_container_width=True):
            _cerrar_sesion()
            st.rerun()

        st.caption(f"v{APP_VERSION}")


def _badge_rol(rol: str) -> None:
    colores = {
        "administrador": ("#1a472a", "#d4edda"),
        "visualizador":  ("#0c3547", "#cce5ff"),
        "visitante":     ("#4a3300", "#fff3cd"),
    }
    bg, fg_bg = colores.get(rol, ("#333", "#eee"))
    st.markdown(
        f'<span style="background:{fg_bg};color:{bg};padding:2px 8px;'
        f'border-radius:4px;font-size:.75rem;font-weight:600;">'
        f'{rol.capitalize()}</span>',
        unsafe_allow_html=True,
    )


# ─── dashboard de bienvenida ──────────────────────────────────────────────────

def _dashboard(sesion: SesionUsuario) -> None:
    _sidebar(sesion)

    st.title(f"Bienvenido, {sesion.nombre} 👋")
    st.caption(f"Rol: {sesion.rol.capitalize()} · {sesion.email}")
    st.divider()

    # Tarjetas de acceso rápido según rol
    nivel = _ROL_NIVEL.get(sesion.rol, 1)

    if nivel >= 2:  # visualizador o superior
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.markdown("#### 📅 Campañas")
            st.write("Gestiona las campañas de monitoreo activas.")
            st.page_link("pages/2_Campanas.py", label="Ir a campañas →")

        with col2:
            st.markdown("#### 🧪 Muestras")
            st.write("Registra muestras de campo y cadena de custodia.")
            st.page_link("pages/3_Muestras_Campo.py", label="Nueva muestra →")

        with col3:
            st.markdown("#### 🔬 Resultados")
            st.write("Ingresa resultados y revisa alertas ECA.")
            st.page_link("pages/4_Resultados_Lab.py", label="Ver resultados →")

        with col4:
            st.markdown("#### 🗺️ Geoportal")
            st.write("Mapa interactivo de puntos de muestreo.")
            st.page_link("pages/7_Geoportal.py", label="Abrir mapa →")

    else:  # visitante
        st.info(
            "Tienes acceso de **visitante**. Puedes consultar el geoportal "
            "y el mapa de puntos de muestreo."
        )
        st.page_link("pages/7_Geoportal.py", label="🗺️ Ver Geoportal")

    if nivel >= 3:  # administrador
        st.divider()
        st.markdown("#### Accesos de administración")
        c1, c2 = st.columns(2)
        with c1:
            st.page_link("pages/5_Parametros.py",     label="📋 Parámetros / ECAs")
            st.page_link("pages/6_Puntos_Muestreo.py", label="📍 Puntos de muestreo")
        with c2:
            st.page_link("pages/8_Informes.py",       label="📄 Generar informes")
            st.page_link("pages/9_Administracion.py", label="⚙️ Administración")


# ─── punto de entrada ─────────────────────────────────────────────────────────

def main() -> None:
    sesion = _sesion_activa()

    if sesion is None:
        # Ocultar sidebar en la pantalla de login
        st.markdown(
            "<style>[data-testid='stSidebar']{display:none}</style>",
            unsafe_allow_html=True,
        )
        _pantalla_login()
    else:
        _dashboard(sesion)


if __name__ == "__main__":
    main()
