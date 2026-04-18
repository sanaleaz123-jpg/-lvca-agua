"""
components/ui_styles.py
Sistema de estilos globales para la plataforma LVCA.

Estilo: dashboard profesional limpio — fondo blanco, sidebar claro,
colores institucionales solo en acentos puntuales.
"""

from __future__ import annotations

import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Paleta de colores
# ─────────────────────────────────────────────────────────────────────────────

COLORS = {
    "primary":       "#1b6b35",
    "accent":        "#e8870e",
    "secondary":     "#0a9396",
    "success":       "#2e7d32",
    "danger":        "#c62828",
    "text":          "#1e293b",
    "text_light":    "#64748b",
    "border":        "#e2e8f0",
}


_GLOBAL_CSS = """
<style>
/* ── Ocultar nav nativa ────────────────────────────────────────────────── */
[data-testid='stSidebarNav'] {
    display: none;
}

/* ── Sidebar limpio ────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stSidebar"] * {
    color: #334155 !important;
}
[data-testid="stSidebar"] .stDivider {
    border-color: #e2e8f0 !important;
}
[data-testid="stSidebar"] button {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    color: #334155 !important;
    border-radius: 8px !important;
    transition: all 0.15s ease;
}
[data-testid="stSidebar"] button:hover {
    background: #f1f5f9 !important;
    border-color: #cbd5e1 !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {
    border-radius: 8px !important;
    padding: 7px 12px !important;
    margin: 1px 0 !important;
    transition: all 0.15s ease;
    color: #475569 !important;
    font-weight: 500 !important;
}
[data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {
    background: #f1f5f9 !important;
    color: #1b6b35 !important;
}

/* ── Metricas ──────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
[data-testid="stMetric"] label {
    color: #64748b !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.7rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
}

/* ── Tabs ───────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-weight: 500;
    font-size: 0.88rem;
    padding: 10px 20px;
    border-radius: 8px 8px 0 0;
}

/* ── DataFrames ────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}

/* ── Botones primarios ─────────────────────────────────────────────────── */
.stButton > button[kind="primary"],
button[kind="primary"] {
    background-color: #1b6b35 !important;
    border-color: #1b6b35 !important;
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.15s ease;
}
.stButton > button[kind="primary"]:hover,
button[kind="primary"]:hover {
    background-color: #145228 !important;
    border-color: #145228 !important;
}

/* ── Formularios ───────────────────────────────────────────────────────── */
[data-testid="stForm"] {
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
    padding: 20px !important;
    background: #ffffff !important;
}

/* ── Expanders ─────────────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
}

/* ── Dividers ──────────────────────────────────────────────────────────── */
hr {
    border-color: #f1f5f9 !important;
    margin: 1rem 0 !important;
}

/* ── Cards ─────────────────────────────────────────────────────────────── */
.lvca-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 24px 20px;
    text-align: center;
    transition: all 0.15s ease;
    height: 100%;
}
.lvca-card:hover {
    border-color: #cbd5e1;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
}
.lvca-card-icon {
    font-size: 2rem;
    margin-bottom: 10px;
}
.lvca-card-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #1e293b;
    margin-bottom: 6px;
}
.lvca-card-desc {
    font-size: 0.82rem;
    color: #64748b;
    line-height: 1.4;
}

/* ── Header de pagina ──────────────────────────────────────────────────── */
.lvca-page-header {
    padding: 4px 0 14px 0;
    margin-bottom: 4px;
}
.lvca-page-header h1 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
    margin-bottom: 2px !important;
}
.lvca-page-header p {
    color: #64748b;
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
.lvca-badge-admin { background: #dcfce7; color: #166534; }
.lvca-badge-visual { background: #e0f2fe; color: #0369a1; }
.lvca-badge-visit { background: #f1f5f9; color: #475569; }

/* ── Info box ──────────────────────────────────────────────────────────── */
.lvca-info-box {
    background: #f8fafc;
    border-left: 3px solid #1b6b35;
    border-radius: 0 8px 8px 0;
    padding: 12px 16px;
    margin: 8px 0;
    font-size: 0.88rem;
    color: #334155;
}

/* ── Alertas ───────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {
    border-radius: 10px;
}

html { scroll-behavior: smooth; }
</style>
"""


def aplicar_estilos() -> None:
    """Inyecta el CSS global."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def page_header(titulo: str, subtitulo: str = "") -> None:
    """Encabezado de pagina."""
    sub_html = f"<p>{subtitulo}</p>" if subtitulo else ""
    st.markdown(
        f'<div class="lvca-page-header">'
        f'<h1>{titulo}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def badge_rol(rol: str) -> None:
    """Badge de rol."""
    cls_map = {
        "administrador": "lvca-badge-admin",
        "analista_lab":  "lvca-badge-admin",
        "tecnico_campo": "lvca-badge-visual",
        "visualizador":  "lvca-badge-visual",
        "visitante":     "lvca-badge-visit",
    }
    label_map = {
        "administrador": "Administrador",
        "analista_lab":  "Analista lab.",
        "tecnico_campo": "Técnico campo",
        "visualizador":  "Visualizador",
        "visitante":     "Visitante",
    }
    cls = cls_map.get(rol, "lvca-badge-visit")
    label = label_map.get(rol, rol.capitalize())
    st.markdown(
        f'<span class="lvca-badge {cls}">{label}</span>',
        unsafe_allow_html=True,
    )


def info_box(texto: str) -> None:
    """Caja informativa."""
    st.markdown(
        f'<div class="lvca-info-box">{texto}</div>',
        unsafe_allow_html=True,
    )


def section_header(titulo: str, icono: str = "") -> None:
    """Sub-encabezado de seccion."""
    prefix = f"{icono} " if icono else ""
    st.markdown(
        f"<h3 style='color:#1e293b; font-size:1.1rem; font-weight:600; "
        f"margin-top:1.2rem; margin-bottom:0.5rem;'>{prefix}{titulo}</h3>",
        unsafe_allow_html=True,
    )
