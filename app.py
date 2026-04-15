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
from components.ui_styles import aplicar_estilos, badge_rol, page_header

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
# Cada entrada: (label, ruta_streamlit, rol_minimo, seccion)
PAGINAS = [
    ("Inicio",              "pages/1_Inicio.py",            "visitante",      "principal"),
    ("Campañas",            "pages/2_Campanas.py",           "administrador", "campo"),
    ("Muestras de campo",   "pages/3_Muestras_Campo.py",     "administrador", "campo"),
    ("Resultados de lab",   "pages/4_Resultados_Lab.py",     "visualizador",  "datos"),
    ("Base de Datos",       "pages/10_Base_Datos.py",        "visualizador",  "datos"),
    ("Informes",            "pages/8_Informes.py",           "visualizador",  "datos"),
    ("Geoportal",           "pages/7_Geoportal.py",          "visitante",     "visualizacion"),
    ("Parámetros / ECAs",   "pages/5_Parametros.py",         "administrador", "config"),
    ("Puntos de muestreo",  "pages/6_Puntos_Muestreo.py",   "administrador", "config"),
    ("Administración",      "pages/9_Administracion.py",     "administrador", "config"),
]

_SECCION_LABELS = {
    "principal":     "INICIO",
    "campo":         "TRABAJO DE CAMPO",
    "datos":         "DATOS Y REPORTES",
    "visualizacion": "VISUALIZACION",
    "config":        "CONFIGURACION",
}

_SECCION_ICONOS = {
    "principal":     "🏠",
    "campo":         "🧪",
    "datos":         "📊",
    "visualizacion": "🗺️",
    "config":        "⚙️",
}

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
    # Ocultar sidebar en login
    st.markdown(
        "<style>[data-testid='stSidebar']{display:none}</style>",
        unsafe_allow_html=True,
    )

    col_izq, col_centro, col_der = st.columns([1.2, 1.4, 1.2])

    with col_centro:
        st.markdown("<br>", unsafe_allow_html=True)

        # Logo / cabecera
        st.markdown(
            f"""
            <div style="text-align:center; margin-bottom:2rem;">
                <div style="display:inline-flex; align-items:center; justify-content:center;
                     width:70px; height:70px; border-radius:18px;
                     background:linear-gradient(135deg, #0e6ba8, #0a9396);
                     margin-bottom:12px; box-shadow:0 4px 16px rgba(14,107,168,0.25);">
                    <span style="font-size:2rem; filter:brightness(2);">💧</span>
                </div>
                <h1 style="font-size:2rem; margin:0; color:#1d3557; font-weight:700;">
                    LVCA
                </h1>
                <p style="color:#6c757d; margin:4px 0 0 0; font-size:0.9rem;">
                    Laboratorio de Calidad de Agua
                </p>
                <p style="color:#adb5bd; font-size:0.8rem; margin:2px 0 0 0;">
                    {APP_ENTIDAD}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("form_login", clear_on_submit=False):
            st.markdown(
                "<p style='font-weight:600; font-size:1.05rem; color:#1d3557; "
                "margin-bottom:4px;'>Iniciar sesion</p>",
                unsafe_allow_html=True,
            )
            email = st.text_input(
                "Correo electronico",
                placeholder="usuario@autodema.gob.pe",
                label_visibility="collapsed",
            )
            st.caption("Correo electronico")
            password = st.text_input(
                "Contrasena",
                type="password",
                label_visibility="collapsed",
            )
            st.caption("Contrasena")
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button(
                "Ingresar", type="primary", use_container_width=True,
            )

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
            f"<p style='text-align:center;color:#adb5bd;font-size:.72rem;"
            f"margin-top:2rem;'>v{APP_VERSION}</p>",
            unsafe_allow_html=True,
        )


# ─── barra lateral con navegación ─────────────────────────────────────────────

def _sidebar(sesion: SesionUsuario) -> None:
    aplicar_estilos()

    with st.sidebar:
        # Header
        st.markdown(
            """
            <div style="text-align:center; padding:8px 0 4px 0;">
                <span style="font-size:1.5rem;">💧</span>
                <span style="font-size:1.3rem; font-weight:700; color:#ffffff !important;
                      margin-left:4px; vertical-align:middle;">LVCA</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='text-align:center; font-size:0.72rem; color:#8ba4c4 !important; "
            f"margin:0; padding-bottom:8px;'>{APP_ENTIDAD}</p>",
            unsafe_allow_html=True,
        )
        st.divider()

        # Info del usuario
        st.markdown(
            f"<p style='font-weight:600; font-size:0.9rem; margin-bottom:2px; "
            f"color:#ffffff !important;'>{sesion.nombre_completo}</p>",
            unsafe_allow_html=True,
        )
        badge_rol(sesion.rol)
        if sesion.institucion:
            st.markdown(
                f"<p style='font-size:0.75rem; color:#8ba4c4 !important; margin-top:4px;'>"
                f"{sesion.institucion}</p>",
                unsafe_allow_html=True,
            )
        st.divider()

        # Navegación agrupada por sección
        nivel_usuario = _ROL_NIVEL.get(sesion.rol, 1)
        secciones_vistas: set[str] = set()

        for label, ruta, rol_minimo, seccion in PAGINAS:
            if nivel_usuario < _ROL_NIVEL.get(rol_minimo, 1):
                continue

            if seccion not in secciones_vistas:
                secciones_vistas.add(seccion)
                icono = _SECCION_ICONOS.get(seccion, "")
                sec_label = _SECCION_LABELS.get(seccion, "")
                st.markdown(
                    f"<p style='font-size:0.65rem; font-weight:700; color:#8ba4c4 !important; "
                    f"text-transform:uppercase; letter-spacing:1px; margin:12px 0 4px 4px; "
                    f"padding:0;'>{icono} {sec_label}</p>",
                    unsafe_allow_html=True,
                )

            st.page_link(ruta, label=label)

        st.divider()

        if st.button("Cerrar sesion", use_container_width=True, icon="🚪"):
            _cerrar_sesion()
            st.rerun()

        st.markdown(
            f"<p style='text-align:center; font-size:0.65rem; color:#5a7a9a !important; "
            f"margin-top:8px;'>v{APP_VERSION}</p>",
            unsafe_allow_html=True,
        )


# ─── dashboard de bienvenida ──────────────────────────────────────────────────

def _render_card(icono: str, titulo: str, desc: str, ruta: str, label_btn: str) -> None:
    """Tarjeta de acceso rápido."""
    st.markdown(
        f"""
        <div class="lvca-card">
            <div class="lvca-card-icon">{icono}</div>
            <div class="lvca-card-title">{titulo}</div>
            <div class="lvca-card-desc">{desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.page_link(ruta, label=label_btn, use_container_width=True)


def _dashboard(sesion: SesionUsuario) -> None:
    _sidebar(sesion)

    page_header(
        f"Bienvenido, {sesion.nombre}",
        f"{sesion.rol.capitalize()} &middot; {sesion.email}",
    )
    st.divider()

    nivel = _ROL_NIVEL.get(sesion.rol, 1)

    if nivel >= 2:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _render_card(
                "📅", "Campanas",
                "Gestiona las campanas de monitoreo activas.",
                "pages/2_Campanas.py", "Ir a campanas →",
            )
        with col2:
            _render_card(
                "🧪", "Muestras",
                "Registra muestras de campo y cadena de custodia.",
                "pages/3_Muestras_Campo.py", "Nueva muestra →",
            )
        with col3:
            _render_card(
                "🔬", "Resultados",
                "Ingresa resultados y revisa alertas ECA.",
                "pages/4_Resultados_Lab.py", "Ver resultados →",
            )
        with col4:
            _render_card(
                "🗺️", "Geoportal",
                "Mapa interactivo de puntos de muestreo.",
                "pages/7_Geoportal.py", "Abrir mapa →",
            )
    else:
        st.info(
            "Tienes acceso de **visitante**. Puedes consultar el geoportal "
            "y el mapa de puntos de muestreo."
        )
        st.page_link("pages/7_Geoportal.py", label="🗺️ Ver Geoportal")

    if nivel >= 3:
        st.divider()
        st.markdown(
            "<p style='font-size:0.75rem; font-weight:700; color:#6c757d; "
            "text-transform:uppercase; letter-spacing:1px; margin-bottom:8px;'>"
            "Accesos de administracion</p>",
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.page_link("pages/5_Parametros.py", label="📋 Parametros / ECAs",
                         use_container_width=True)
        with c2:
            st.page_link("pages/6_Puntos_Muestreo.py", label="📍 Puntos de muestreo",
                         use_container_width=True)
        with c3:
            st.page_link("pages/8_Informes.py", label="📄 Generar informes",
                         use_container_width=True)
        with c4:
            st.page_link("pages/9_Administracion.py", label="⚙️ Administracion",
                         use_container_width=True)


# ─── punto de entrada ─────────────────────────────────────────────────────

def main() -> None:
    sesion = _sesion_activa()

    if sesion is None:
        _pantalla_login()
    else:
        _dashboard(sesion)


if __name__ == "__main__":
    main()
