"""
components/ui_styles.py
Sistema de estilos globales para la plataforma LVCA.

Paleta institucional:
    - Verde AUTODEMA/PEIMS: sidebar, headers, elementos principales
    - Naranja/ambar LVCA: acentos, highlights, botones primarios
    - Teal/turquesa LVCA: elementos secundarios, info, links
"""

from __future__ import annotations

import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Paleta de colores institucional
# ─────────────────────────────────────────────────────────────────────────────

COLORS = {
    # Verde AUTODEMA/PEIMS
    "primary":       "#1b6b35",
    "primary_dark":  "#0d3f1e",
    "primary_light": "#e8f5e9",
    # Naranja/ambar LVCA
    "accent":        "#e8870e",
    "accent_light":  "#fef3e2",
    "accent_dark":   "#c56d00",
    # Teal LVCA
    "secondary":     "#0a9396",
    "secondary_light": "#e0f7f7",
    # Semaforo
    "success":       "#2e7d32",
    "danger":        "#c62828",
    "warning":       "#ef8c00",
    # Neutros
    "text":          "#1a2e1a",
    "text_light":    "#5f7161",
    "bg_card":       "#ffffff",
    "bg_subtle":     "#f5f7f5",
    "border":        "#d5ddd5",
}


# ─────────────────────────────────────────────────────────────────────────────
# CSS Global
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_CSS = """
<style>
/* ── Sidebar — verde AUTODEMA oscuro ───────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d3f1e 0%, #145228 50%, #1b6b35 100%);
}
[data-testid="stSidebar"] * {
    color: #d4e8d4 !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {
    color: #ffffff !important;
    font-weight: 700;
}
[data-testid="stSidebar"] .stDivider {
    border-color: rgba(255,255,255,0.12) !important;
}
[data-testid="stSidebar"] button {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    color: #d4e8d4 !important;
    transition: all 0.2s ease;
}
[data-testid="stSidebar"] button:hover {
    background: rgba(232,135,14,0.2) !important;
    border-color: rgba(232,135,14,0.4) !important;
}
/* Sidebar links */
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
    border-radius: 8px !important;
    padding: 6px 12px !important;
    margin: 2px 0 !important;
    transition: all 0.2s ease;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
    background: rgba(232,135,14,0.15) !important;
}

/* ── Ocultar nav nativa ────────────────────────────────────────────────── */
[data-testid='stSidebarNav'] {
    display: none;
}

/* ── Metricas st.metric ────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #d5ddd5;
    border-left: 4px solid #1b6b35;
    border-radius: 10px;
    padding: 16px 20px;
    box-shadow: 0 1px 4px rgba(27,107,53,0.06);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 14px rgba(27,107,53,0.12);
}
[data-testid="stMetric"] label {
    color: #5f7161 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600 !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    color: #1a2e1a !important;
}

/* ── Tabs ───────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.88rem;
    padding: 10px 20px;
    border-radius: 8px 8px 0 0;
}
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    border-bottom-color: #e8870e !important;
}

/* ── DataFrames ────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #d5ddd5;
}

/* ── Botones primarios — naranja LVCA ──────────────────────────────────── */
.stButton > button[kind="primary"],
button[kind="primary"] {
    background-color: #e8870e !important;
    border-color: #e8870e !important;
    border-radius: 8px;
    font-weight: 600;
    letter-spacing: 0.3px;
    transition: all 0.2s ease;
}
.stButton > button[kind="primary"]:hover,
button[kind="primary"]:hover {
    background-color: #c56d00 !important;
    border-color: #c56d00 !important;
}

/* ── Formularios ───────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    border: 1px solid #d5ddd5 !important;
    border-radius: 12px !important;
    padding: 20px !important;
    background: #fafcfa !important;
}

/* ── Expanders ─────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #d5ddd5;
    border-radius: 10px;
    overflow: hidden;
}

/* ── Dividers ──────────────────────────────────────────────────────────── */
hr {
    border-color: #dde5dd !important;
    margin: 1rem 0 !important;
}

/* ── Cards de acceso rapido ────────────────────────────────────────────── */
.lvca-card {
    background: #ffffff;
    border: 1px solid #d5ddd5;
    border-top: 3px solid #1b6b35;
    border-radius: 10px;
    padding: 24px 20px;
    text-align: center;
    transition: all 0.2s ease;
    height: 100%;
}
.lvca-card:hover {
    border-top-color: #e8870e;
    box-shadow: 0 4px 16px rgba(27,107,53,0.1);
    transform: translateY(-2px);
}
.lvca-card-icon {
    font-size: 2.2rem;
    margin-bottom: 10px;
}
.lvca-card-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1a2e1a;
    margin-bottom: 6px;
}
.lvca-card-desc {
    font-size: 0.82rem;
    color: #5f7161;
    line-height: 1.4;
}

/* ── Header de pagina ──────────────────────────────────────────────────── */
.lvca-page-header {
    padding: 4px 0 12px 0;
    margin-bottom: 4px;
    border-bottom: 2px solid #e8870e;
}
.lvca-page-header h1 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #1b6b35 !important;
    margin-bottom: 2px !important;
}
.lvca-page-header p {
    color: #5f7161;
    font-size: 0.85rem;
    margin: 0;
}

/* ── Badge de rol ──────────────────────────────────────────────────────── */
.lvca-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}
.lvca-badge-admin { background: rgba(232,135,14,0.2); color: #c56d00; }
.lvca-badge-visual { background: rgba(10,147,150,0.15); color: #0a9396; }
.lvca-badge-visit { background: rgba(255,255,255,0.15); color: #d4e8d4; }

/* ── Info box — teal LVCA ──────────────────────────────────────────────── */
.lvca-info-box {
    background: linear-gradient(135deg, #e0f7f7 0%, #f0faf5 100%);
    border-left: 4px solid #0a9396;
    border-radius: 0 10px 10px 0;
    padding: 14px 18px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #1a2e1a;
}

/* ── Alertas / success ─────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px;
}

/* ── Scroll suave ──────────────────────────────────────────────────────── */
html { scroll-behavior: smooth; }
</style>
"""


def aplicar_estilos() -> None:
    """Inyecta el CSS global. Llamar al inicio de cada pagina."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de componentes
# ─────────────────────────────────────────────────────────────────────────────

def page_header(titulo: str, subtitulo: str = "") -> None:
    """Encabezado de pagina estilizado."""
    sub_html = f"<p>{subtitulo}</p>" if subtitulo else ""
    st.markdown(
        f'<div class="lvca-page-header">'
        f'<h1>{titulo}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def badge_rol(rol: str) -> None:
    """Badge de rol con estilo pill."""
    cls_map = {
        "administrador": "lvca-badge-admin",
        "visualizador": "lvca-badge-visual",
        "visitante": "lvca-badge-visit",
    }
    cls = cls_map.get(rol, "lvca-badge-visit")
    st.markdown(
        f'<span class="lvca-badge {cls}">{rol.capitalize()}</span>',
        unsafe_allow_html=True,
    )


def info_box(texto: str) -> None:
    """Caja informativa con borde teal lateral."""
    st.markdown(
        f'<div class="lvca-info-box">{texto}</div>',
        unsafe_allow_html=True,
    )


def section_header(titulo: str, icono: str = "") -> None:
    """Sub-encabezado de seccion."""
    prefix = f"{icono} " if icono else ""
    st.markdown(
        f"<h3 style='color:#1b6b35; font-size:1.15rem; font-weight:600; "
        f"margin-top:1.2rem; margin-bottom:0.5rem;'>{prefix}{titulo}</h3>",
        unsafe_allow_html=True,
    )
