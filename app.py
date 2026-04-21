"""
app.py
Punto de entrada de la aplicación Streamlit LVCA – AUTODEMA.

Responsabilidades:
  - Mostrar la pantalla de login si no hay sesión activa.
  - Almacenar la sesión en st.session_state["sesion"].
  - Una vez autenticado, redirigir a pages/1_Inicio.py (el panel real).

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
    initial_sidebar_state="collapsed",
    menu_items={
        "About": f"**{APP_NOMBRE}**\n{APP_ENTIDAD}\nv{APP_VERSION}",
        "Report a bug": None,
        "Get help": None,
    },
)

# Sidebar globalmente oculto — la navegación se sirve vía top_nav() en cada
# página. Inyectado lo más temprano posible para evitar flash del sidebar
# nativo de Streamlit antes de que el CSS de página cargue.
st.markdown(
    "<style>"
    "[data-testid='stSidebar'],"
    "[data-testid='stSidebarNav'],"
    "[data-testid='collapsedControl']"
    "{display:none !important}"
    "[data-testid='stMain']{margin-left:0 !important}"
    "</style>",
    unsafe_allow_html=True,
)


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

        # Logos institucionales
        logo_l, logo_r = st.columns([1, 1])
        with logo_l:
            st.image("imagenes/autodema_logo.png", width=120)
        with logo_r:
            st.image("imagenes/logo_lvca.png", width=120)

        # Texto cabecera
        st.markdown(
            f"""
            <div style="text-align:center; margin-bottom:1.5rem; margin-top:8px;">
                <h1 style="font-size:1.8rem; margin:0; color:#1b6b35; font-weight:700;">
                    Plataforma LVCA
                </h1>
                <p style="color:#64748b; margin:4px 0 0 0; font-size:0.85rem;">
                    Laboratorio de Vigilancia de la Calidad del Agua
                </p>
                <p style="color:#e8870e; font-size:0.8rem; font-weight:600; margin:4px 0 0 0;">
                    {APP_ENTIDAD}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("form_login", clear_on_submit=False):
            st.markdown(
                "<p style='font-weight:600; font-size:1.05rem; color:#1b6b35; "
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


# ─── punto de entrada ─────────────────────────────────────────────────────

def main() -> None:
    sesion = _sesion_activa()

    if sesion is None:
        _pantalla_login()
    else:
        # Sesión activa: redirigir al panel real (pages/1_Inicio.py).
        # El top_nav() de esa página sirve la navegación global.
        st.switch_page("pages/1_Inicio.py")


if __name__ == "__main__":
    main()
