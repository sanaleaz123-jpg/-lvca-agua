"""
components/ui_styles.py
Sistema de estilos globales para la plataforma LVCA.

Provee CSS unificado, helpers de tarjetas KPI, encabezados de página
y componentes visuales reutilizables.
"""

from __future__ import annotations

import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Paleta de colores
# ─────────────────────────────────────────────────────────────────────────────

COLORS = {
    "primary":    "#0e6ba8",
    "primary_light": "#e8f4fd",
    "secondary":  "#0a9396",
    "accent":     "#ee9b00",
    "success":    "#2d6a4f",
    "danger":     "#e63946",
    "warning":    "#f4a261",
    "info":       "#457b9d",
    "text":       "#1d3557",
    "text_light": "#6c757d",
    "bg_card":    "#ffffff",
    "bg_subtle":  "#f8f9fa",
    "border":     "#e0e4e8",
}


# ─────────────────────────────────────────────────────────────────────────────
# CSS Global
# ─────────────────────────────────────────────────────────────────────────────

_GLOBAL_CSS = """
<style>
/* ── Tipografía general ─────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0e1f3d 0%, #132d5e 100%);
}
[data-testid="stSidebar"] * {
    color: #e0e8f0 !important;
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
    color: #e0e8f0 !important;
    transition: all 0.2s ease;
}
[data-testid="stSidebar"] button:hover {
    background: rgba(255,255,255,0.18) !important;
    border-color: rgba(255,255,255,0.3) !important;
}
/* Sidebar links */
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
    border-radius: 8px !important;
    padding: 6px 12px !important;
    margin: 2px 0 !important;
    transition: all 0.2s ease;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
    background: rgba(255,255,255,0.1) !important;
}

/* ── Ocultar nav nativa ────────────────────────────────────────────────── */
[data-testid='stSidebarNav'] {
    display: none;
}

/* ── Métricas st.metric más limpias ────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}
[data-testid="stMetric"] label {
    color: #6c757d !important;
    font-size: 0.8rem !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-weight: 600 !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    color: #1d3557 !important;
}

/* ── Tabs más elegantes ─────────────────────────────────────────────────── */
[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.88rem;
    padding: 10px 20px;
    border-radius: 8px 8px 0 0;
}

/* ── DataFrames ────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e0e4e8;
}

/* ── Botones primarios ─────────────────────────────────────────────────── */
.stButton > button[kind="primary"] {
    border-radius: 8px;
    font-weight: 600;
    letter-spacing: 0.3px;
    transition: all 0.2s ease;
}

/* ── Formularios ───────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    border: 1px solid #e0e4e8 !important;
    border-radius: 12px !important;
    padding: 20px !important;
    background: #fafbfc !important;
}

/* ── Expanders ─────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #e0e4e8;
    border-radius: 10px;
    overflow: hidden;
}

/* ── Dividers más sutiles ──────────────────────────────────────────────── */
hr {
    border-color: #e8ecf0 !important;
    margin: 1rem 0 !important;
}

/* ── Page link cards ───────────────────────────────────────────────────── */
.lvca-card {
    background: #ffffff;
    border: 1px solid #e0e4e8;
    border-radius: 12px;
    padding: 24px 20px;
    text-align: center;
    transition: all 0.2s ease;
    height: 100%;
}
.lvca-card:hover {
    border-color: #0e6ba8;
    box-shadow: 0 4px 16px rgba(14,107,168,0.1);
    transform: translateY(-2px);
}
.lvca-card-icon {
    font-size: 2rem;
    margin-bottom: 8px;
}
.lvca-card-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1d3557;
    margin-bottom: 6px;
}
.lvca-card-desc {
    font-size: 0.82rem;
    color: #6c757d;
    line-height: 1.4;
}

/* ── Header de página ─────────────────────────────────────────────────── */
.lvca-page-header {
    padding: 8px 0 16px 0;
    margin-bottom: 8px;
}
.lvca-page-header h1 {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #1d3557 !important;
    margin-bottom: 2px !important;
}
.lvca-page-header p {
    color: #6c757d;
    font-size: 0.85rem;
    margin: 0;
}

/* ── Badge de rol mejorado ─────────────────────────────────────────────── */
.lvca-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}
.lvca-badge-admin { background: #d4edda; color: #1a472a; }
.lvca-badge-visual { background: #cce5ff; color: #0c3547; }
.lvca-badge-visit { background: #fff3cd; color: #4a3300; }

/* ── Sección info box ──────────────────────────────────────────────────── */
.lvca-info-box {
    background: linear-gradient(135deg, #e8f4fd 0%, #f0f8ff 100%);
    border-left: 4px solid #0e6ba8;
    border-radius: 0 10px 10px 0;
    padding: 14px 18px;
    margin: 8px 0;
    font-size: 0.9rem;
    color: #1d3557;
}

/* ── Scroll suave ─────────────────────────────────────────────────────── */
html { scroll-behavior: smooth; }
</style>
"""


def aplicar_estilos() -> None:
    """Inyecta el CSS global. Llamar al inicio de cada página."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de componentes
# ─────────────────────────────────────────────────────────────────────────────

def page_header(titulo: str, subtitulo: str = "") -> None:
    """Encabezado de página estilizado."""
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
    """Caja informativa con borde azul lateral."""
    st.markdown(
        f'<div class="lvca-info-box">{texto}</div>',
        unsafe_allow_html=True,
    )


def section_header(titulo: str, icono: str = "") -> None:
    """Sub-encabezado de sección."""
    prefix = f"{icono} " if icono else ""
    st.markdown(
        f"<h3 style='color:#1d3557; font-size:1.15rem; font-weight:600; "
        f"margin-top:1.2rem; margin-bottom:0.5rem;'>{prefix}{titulo}</h3>",
        unsafe_allow_html=True,
    )
