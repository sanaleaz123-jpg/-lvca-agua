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

from components.ui_styles import aplicar_estilos
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
    """Pantalla de login estilo SSDH-ANA — card centrada con banner azul."""
    # Cargar estilos globales (inyecta CSS + footer institucional).
    aplicar_estilos()

    # CSS específico del login: fondo neutro + card centrada.
    st.markdown(
        """
        <style>
        [data-testid='stSidebar'],
        [data-testid='stSidebarNav'],
        [data-testid='collapsedControl'] { display: none !important; }
        [data-testid='stHeader'] { display: none !important; }
        [data-testid='stMain'] { margin-left: 0 !important; }
        [data-testid='stMainBlockContainer'] {
            padding-top: 32px !important;
            padding-bottom: 60px !important;
            background: #f8fafc;
            max-width: 100% !important;
        }
        /* El container con key="lvca_login_card" se convierte en card blanca
           con sombra y banner azul arriba. */
        .st-key-lvca_login_card {
            background: #ffffff !important;
            border-radius: 14px !important;
            box-shadow: 0 12px 32px rgba(13, 71, 161, 0.12),
                        0 4px 8px rgba(15, 23, 42, 0.04) !important;
            overflow: hidden !important;
            padding: 0 !important;
            border: 1px solid #eef0f2 !important;
        }
        /* Inputs del login con estilo más limpio. */
        .st-key-lvca_login_card [data-baseweb="input"] {
            border-radius: 8px !important;
        }
        .st-key-lvca_login_card [data-baseweb="input"]:focus-within {
            border-color: #1565C0 !important;
            box-shadow: 0 0 0 3px rgba(21,101,192,0.12) !important;
        }
        /* Labels de form */
        .st-key-lvca_login_card label p,
        .st-key-lvca_login_card label {
            color: #475569 !important;
            font-size: 0.8rem !important;
            font-weight: 500 !important;
        }
        /* Botón primario "Ingresar" */
        .st-key-lvca_login_card button[kind="primary"] {
            background: linear-gradient(135deg,#0D47A1 0%,#1565C0 100%) !important;
            border: none !important;
            box-shadow: 0 2px 6px rgba(13,71,161,0.2) !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em !important;
        }
        .st-key-lvca_login_card button[kind="primary"]:hover {
            box-shadow: 0 4px 12px rgba(13,71,161,0.3) !important;
            transform: translateY(-1px) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns([1, 1.6, 1])
    with cols[1]:
        with st.container(key="lvca_login_card"):
            # Banner azul arriba del card (con gradiente SSDH).
            st.markdown(
                """
                <div style="background:linear-gradient(135deg,#0D47A1 0%,#1565C0 100%);
                     color:white; padding:26px 30px 22px 30px; text-align:center;">
                    <div style="display:inline-flex; align-items:center; gap:10px;
                         justify-content:center; margin-bottom:8px;">
                        <span class="material-symbols-rounded"
                            style="font-size:30px; line-height:1; color:#ffffff;">water_drop</span>
                        <h1 style="margin:0; font-size:1.7rem; font-weight:700;
                             color:#ffffff; letter-spacing:-0.02em; line-height:1.1;">
                            Plataforma LVCA
                        </h1>
                    </div>
                    <p style="margin:0; font-size:0.82rem;
                         color:rgba(255,255,255,0.88); font-weight:400;">
                        Laboratorio de Vigilancia de la Calidad del Agua
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Cuerpo del card — logos + form
            inner_cols = st.columns([1, 10, 1])
            with inner_cols[1]:
                st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)

                logo_l, logo_r = st.columns([1, 1])
                with logo_l:
                    st.image("imagenes/autodema_logo.png", width=110)
                with logo_r:
                    st.image("imagenes/logo_lvca.png", width=110)

                st.markdown(
                    "<div style='text-align:center; color:#1565C0; font-size:0.85rem; "
                    "font-weight:600; margin:16px 0 8px 0; letter-spacing:-0.01em;'>"
                    "Iniciar sesión</div>",
                    unsafe_allow_html=True,
                )

                with st.form("form_login", clear_on_submit=False):
                    email = st.text_input(
                        "Correo electrónico",
                        placeholder="usuario@autodema.gob.pe",
                    )
                    password = st.text_input(
                        "Contraseña",
                        type="password",
                        placeholder="••••••••",
                    )
                    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                    submitted = st.form_submit_button(
                        "Ingresar",
                        type="primary",
                        use_container_width=True,
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

                # Pie del card
                st.markdown(
                    f"""<div style='text-align:center; color:#94a3b8;
                         font-size:0.72rem; margin-top:18px;
                         border-top:1px solid #f1f5f9; padding:12px 0 6px 0;'>
                        {APP_ENTIDAD} · v{APP_VERSION}
                    </div>""",
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
