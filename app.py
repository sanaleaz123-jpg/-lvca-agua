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
        /* Botón primario "Ingresar" — selectores múltiples para ganar
           especificidad contra el tema default de Streamlit (verde).
           El form submit button usa kind="primaryFormSubmit" en ciertas
           versiones; añadimos fallback genérico. */
        .st-key-lvca_login_card button[kind="primary"],
        .st-key-lvca_login_card button[kind="primaryFormSubmit"],
        .st-key-lvca_login_card [data-testid="stFormSubmitButton"] button,
        .st-key-lvca_login_card .stFormSubmitButton button {
            background: linear-gradient(135deg,#0D47A1 0%,#1565C0 100%) !important;
            background-color: #0D47A1 !important;
            color: #ffffff !important;
            border: none !important;
            box-shadow: 0 2px 6px rgba(13,71,161,0.2) !important;
            font-weight: 600 !important;
            letter-spacing: 0.02em !important;
        }
        .st-key-lvca_login_card button[kind="primary"]:hover,
        .st-key-lvca_login_card button[kind="primaryFormSubmit"]:hover,
        .st-key-lvca_login_card [data-testid="stFormSubmitButton"] button:hover,
        .st-key-lvca_login_card .stFormSubmitButton button:hover {
            background: linear-gradient(135deg,#0D47A1 0%,#1976D2 100%) !important;
            box-shadow: 0 4px 12px rgba(13,71,161,0.3) !important;
            transform: translateY(-1px) !important;
        }
        /* Contenedores de logos: fondo blanco, sombra sutil, alto uniforme
           — para que el PNG con transparencia no muestre el checker pattern
           del tema oscuro / fondo gris. */
        .lvca-logo-frame {
            background: #ffffff;
            border: 1px solid #eef0f2;
            border-radius: 10px;
            padding: 14px 18px;
            height: 110px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 1px 3px rgba(15,23,42,0.04);
        }
        .lvca-logo-frame img {
            max-height: 82px;
            max-width: 100%;
            object-fit: contain;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns([1, 1.6, 1])
    with cols[1]:
        with st.container(key="lvca_login_card"):
            # Banner azul arriba del card (con gradiente SSDH).
            # El ícono water_drop usa Material Symbols Rounded (font cargado
            # desde aplicar_estilos() → _FONT_LINK).
            st.markdown(
                """
                <div style="background:linear-gradient(135deg,#0D47A1 0%,#1565C0 100%);
                     color:white; padding:28px 28px 22px 28px; text-align:center;">
                    <div style="display:flex; align-items:center; gap:14px;
                         justify-content:center; margin-bottom:6px;">
                        <span class="material-symbols-rounded"
                            style="font-size:36px; line-height:1; color:#ffffff;
                            font-variation-settings:'FILL' 1;">water_drop</span>
                        <h1 style="margin:0; font-size:1.35rem; font-weight:700;
                             color:#ffffff; letter-spacing:-0.02em; line-height:1.2;
                             text-align:left;">
                            Laboratorio de Vigilancia<br>
                            de Calidad de Agua
                        </h1>
                    </div>
                    <p style="margin:10px 0 0 0; font-size:0.82rem;
                         color:rgba(255,255,255,0.92); font-weight:600;
                         letter-spacing:0.1em; text-transform:uppercase;">
                        AUTODEMA
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Cuerpo del card — logos + form
            inner_cols = st.columns([1, 10, 1])
            with inner_cols[1]:
                st.markdown("<div style='height:22px;'></div>", unsafe_allow_html=True)

                # Logos en contenedores blancos uniformes para que el PNG
                # transparente del LVCA no muestre el checker pattern.
                import base64
                from pathlib import Path

                def _img_data_uri(path: str) -> str:
                    p = Path(path)
                    if not p.exists():
                        return ""
                    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                    return f"data:image/png;base64,{b64}"

                autodema_uri = _img_data_uri("imagenes/autodema_logo.png")
                lvca_uri = _img_data_uri("imagenes/logo_lvca.png")

                st.markdown(
                    f"""
                    <div style="display:grid; grid-template-columns:1fr 1fr;
                         gap:14px; margin-bottom:4px;">
                        <div class="lvca-logo-frame">
                            <img src="{autodema_uri}" alt="PEIMS-AUTODEMA"/>
                        </div>
                        <div class="lvca-logo-frame">
                            <img src="{lvca_uri}" alt="LVCA"/>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(
                    "<div style='text-align:center; color:#1565C0; font-size:0.88rem; "
                    "font-weight:600; margin:22px 0 8px 0; letter-spacing:-0.01em;'>"
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
