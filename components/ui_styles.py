"""
components/ui_styles.py
Sistema de estilos globales para la plataforma LVCA.

Estilo: dashboard profesional limpio — fondo blanco, sidebar claro,
colores institucionales solo en acentos puntuales. Tipografía Inter.

API pública:
    aplicar_estilos()             — inyecta CSS + fonts (llamar al inicio de cada página)
    page_header(t, s)             — título de página
    section_header(t, icono)      — sub-encabezado consistente
    badge_rol(rol)
    info_box(texto)
    icon(name, size, color)       — SVG inline (Lucide-style)
    icon_label(name, label)       — ícono + texto, alineado
    success_check_overlay()       — overlay con check verde animado al guardar
    toast(mensaje, tipo)          — notificación flotante
"""

from __future__ import annotations

import streamlit as st


# ─────────────────────────────────────────────────────────────────────────────
# Paleta de colores (mantener sincronizada con .streamlit/config.toml)
# ─────────────────────────────────────────────────────────────────────────────

COLORS = {
    "primary":       "#1b6b35",
    "primary_dark":  "#145228",
    "accent":        "#e8870e",
    "secondary":     "#0a9396",
    "success":       "#2e7d32",
    "danger":        "#c62828",
    "danger_dark":   "#a31f1f",
    "warning":       "#e8870e",
    "text":          "#1e293b",
    "text_light":    "#64748b",
    "text_muted":    "#94a3b8",
    "border":        "#e2e8f0",
    "surface":       "#ffffff",
    "surface_alt":   "#f8fafc",
}


# ─────────────────────────────────────────────────────────────────────────────
# Iconografía SVG inline (estilo Lucide, stroke width 1.75)
# ─────────────────────────────────────────────────────────────────────────────

# Diccionario de paths SVG. Cada entrada es solo el contenido interno del <svg>.
# Tomados/inspirados en Lucide (https://lucide.dev) — MIT.
_ICON_PATHS: dict[str, str] = {
    "save":      '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    "trash":     '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
    "edit":      '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>',
    "plus":      '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "x":         '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
    "check":     '<polyline points="20 6 9 17 4 12"/>',
    "search":    '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    "filter":    '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "download":  '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
    "upload":    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
    "file":      '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
    "calendar":  '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
    "map_pin":   '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    "droplet":   '<path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/>',
    "beaker":    '<path d="M4.5 3h15"/><path d="M6 3v16a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V3"/><path d="M6 14h12"/>',
    "user":      '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
    "users":     '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "settings":  '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "logout":    '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>',
    "home":      '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
    "alert":     '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
    "info":      '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
    "chart":     '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
    "trend":     '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "shield":    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "lock":      '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
    "unlock":    '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>',
    "refresh":   '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    "archive":   '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>',
    "play":      '<polygon points="5 3 19 12 5 21 5 3"/>',
    "stop":      '<rect x="3" y="3" width="18" height="18"/>',
    "eye":       '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
    "list":      '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
    "grid":      '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>',
    "clipboard": '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>',
}


def icon(name: str, size: int = 16, color: str = "currentColor", stroke: float = 1.75) -> str:
    """Devuelve un SVG inline para usar en st.markdown(..., unsafe_allow_html=True)."""
    path = _ICON_PATHS.get(name, _ICON_PATHS["info"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke}" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="vertical-align:-3px; display:inline-block;">{path}</svg>'
    )


def icon_label(name: str, label: str, size: int = 16, color: str | None = None) -> str:
    """HTML con ícono + texto alineados horizontalmente."""
    color_attr = color or COLORS["text"]
    return (
        f'<span style="display:inline-flex; align-items:center; gap:6px; color:{color_attr};">'
        f'{icon(name, size, color_attr)}'
        f'<span>{label}</span>'
        f'</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# CSS global
# ─────────────────────────────────────────────────────────────────────────────

_FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
)

_GLOBAL_CSS = """<style>
/* Tipografía global Inter */
html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif !important;
    font-feature-settings: 'cv11', 'ss01';
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Inter', sans-serif !important;
    letter-spacing: -0.01em;
}

/* ── Ocultar nav nativa de Streamlit ───────────────────────────────────── */
[data-testid='stSidebarNav'] { display: none; }

/* ── Sidebar limpio ────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #e2e8f0;
}
[data-testid="stSidebar"] * { color: #334155 !important; }
[data-testid="stSidebar"] .stDivider { border-color: #e2e8f0 !important; }
[data-testid="stSidebar"] button {
    background: #f8fafc !important;
    border: 1px solid #e2e8f0 !important;
    color: #334155 !important;
    border-radius: 8px !important;
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
[data-testid="stSidebar"] button:hover {
    background: #f1f5f9 !important;
    border-color: #cbd5e1 !important;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0,0,0,0.04);
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
    padding-left: 16px !important;
}

/* ── Métricas ──────────────────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 20px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
[data-testid="stMetric"]:hover {
    border-color: #cbd5e1;
    box-shadow: 0 4px 10px rgba(0,0,0,0.04);
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

/* ── Tabs ──────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-weight: 500;
    font-size: 0.88rem;
    padding: 10px 20px;
    border-radius: 8px 8px 0 0;
    transition: all 0.15s ease;
}
[data-testid="stTabs"] button[data-baseweb="tab"]:hover {
    background: #f8fafc;
}

/* ── DataFrames ────────────────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}

/* ── Botones — animaciones suaves ──────────────────────────────────────── */
.stButton > button,
button[kind="primary"],
button[kind="secondary"] {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    letter-spacing: 0.01em;
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
.stButton > button:hover,
button[kind="primary"]:hover,
button[kind="secondary"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.08);
}
.stButton > button:active,
button[kind="primary"]:active,
button[kind="secondary"]:active {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    transition-duration: 0.05s !important;
}
.stButton > button:focus-visible,
button[kind="primary"]:focus-visible,
button[kind="secondary"]:focus-visible {
    outline: 2px solid #1b6b35;
    outline-offset: 2px;
}

/* Botones primarios — verde institucional */
.stButton > button[kind="primary"],
button[kind="primary"] {
    background-color: #1b6b35 !important;
    border-color: #1b6b35 !important;
    color: white !important;
}
.stButton > button[kind="primary"]:hover,
button[kind="primary"]:hover {
    background-color: #145228 !important;
    border-color: #145228 !important;
}

/* Clase auxiliar para botones destructivos: aplicar como wrapper o mediante
   contenedores con st.markdown('<div class="lvca-danger">…') antes del botón */
.lvca-danger .stButton > button,
.lvca-danger button[kind="primary"],
.lvca-danger button[kind="secondary"] {
    background-color: #c62828 !important;
    border-color: #c62828 !important;
    color: white !important;
}
.lvca-danger .stButton > button:hover,
.lvca-danger button[kind="primary"]:hover,
.lvca-danger button[kind="secondary"]:hover {
    background-color: #a31f1f !important;
    border-color: #a31f1f !important;
    box-shadow: 0 4px 12px rgba(198, 40, 40, 0.25);
}

/* Botón "ghost": sin fondo, solo borde sutil — para acciones terciarias */
.lvca-ghost .stButton > button {
    background: transparent !important;
    border: 1px solid #e2e8f0 !important;
    color: #475569 !important;
    font-weight: 500 !important;
    box-shadow: none !important;
}
.lvca-ghost .stButton > button:hover {
    background: #f8fafc !important;
    border-color: #cbd5e1 !important;
    color: #1e293b !important;
    transform: translateY(-1px);
}

/* ── Inputs y selectboxes — focus suave ────────────────────────────────── */
[data-baseweb="input"], [data-baseweb="select"] {
    transition: all 0.15s ease;
}
input:focus, textarea:focus, [data-baseweb="select"]:focus-within {
    box-shadow: 0 0 0 3px rgba(27, 107, 53, 0.12);
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
    transition: border-color 0.15s ease;
}
[data-testid="stExpander"]:hover {
    border-color: #cbd5e1;
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
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
    height: 100%;
}
.lvca-card:hover {
    border-color: #cbd5e1;
    box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    transform: translateY(-2px);
}
.lvca-card-icon {
    margin-bottom: 10px;
    color: #1b6b35;
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

/* ── Encabezados de página y sección ───────────────────────────────────── */
.lvca-page-header {
    padding: 4px 0 14px 0;
    margin-bottom: 4px;
}
.lvca-page-header h1 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
    margin-bottom: 2px !important;
    letter-spacing: -0.015em;
}
.lvca-page-header p {
    color: #64748b;
    font-size: 0.85rem;
    margin: 0;
}
.lvca-section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #1e293b;
    font-size: 1.05rem;
    font-weight: 600;
    margin: 1.4rem 0 0.6rem 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #f1f5f9;
}
.lvca-section-header svg { color: #64748b; }

/* ── Badges ────────────────────────────────────────────────────────────── */
.lvca-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}
.lvca-badge-admin  { background: #dcfce7; color: #166534; }
.lvca-badge-visual { background: #e0f2fe; color: #0369a1; }
.lvca-badge-visit  { background: #f1f5f9; color: #475569; }

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
    transition: all 0.15s ease;
}

/* ── Filter bar (barra de filtros en main area) ────────────────────────── */
.lvca-filter-bar {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 12px 18px;
    margin-bottom: 16px;
}

/* ── Toast / overlay para feedback de guardado ─────────────────────────── */
.lvca-success-overlay {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.18);
    z-index: 9999;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: lvcaFadeIn 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.lvca-success-card {
    background: white;
    border-radius: 18px;
    padding: 36px 44px;
    box-shadow: 0 24px 48px rgba(15, 23, 42, 0.18);
    text-align: center;
    animation: lvcaPopIn 0.28s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.lvca-success-card .lvca-check-svg {
    width: 64px;
    height: 64px;
    color: #2e7d32;
}
.lvca-success-card .lvca-check-svg circle {
    fill: none;
    stroke: #2e7d32;
    stroke-width: 2;
    stroke-dasharray: 166;
    stroke-dashoffset: 166;
    animation: lvcaCircle 0.5s cubic-bezier(0.65, 0, 0.45, 1) forwards;
}
.lvca-success-card .lvca-check-svg path {
    fill: none;
    stroke: #2e7d32;
    stroke-width: 3;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-dasharray: 36;
    stroke-dashoffset: 36;
    animation: lvcaCheck 0.32s 0.45s cubic-bezier(0.65, 0, 0.45, 1) forwards;
}
.lvca-success-msg {
    margin-top: 14px;
    font-size: 0.95rem;
    font-weight: 600;
    color: #1e293b;
}
@keyframes lvcaFadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes lvcaPopIn  { from { transform: scale(0.85); opacity: 0; }
                        to   { transform: scale(1);    opacity: 1; } }
@keyframes lvcaCircle { to { stroke-dashoffset: 0; } }
@keyframes lvcaCheck  { to { stroke-dashoffset: 0; } }

/* ── Toast (esquina superior derecha) ──────────────────────────────────── */
.lvca-toast-wrap {
    position: fixed;
    top: 24px;
    right: 24px;
    z-index: 9998;
    animation: lvcaToastIn 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.lvca-toast {
    background: white;
    border-radius: 10px;
    padding: 12px 16px;
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
    border-left: 4px solid #1b6b35;
    font-size: 0.88rem;
    font-weight: 500;
    color: #1e293b;
    min-width: 240px;
    max-width: 360px;
}
.lvca-toast.lvca-toast-info    { border-left-color: #0a9396; }
.lvca-toast.lvca-toast-warn    { border-left-color: #e8870e; }
.lvca-toast.lvca-toast-danger  { border-left-color: #c62828; }
@keyframes lvcaToastIn {
    from { transform: translateX(120%); opacity: 0; }
    to   { transform: translateX(0);    opacity: 1; }
}

html { scroll-behavior: smooth; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def aplicar_estilos() -> None:
    """
    Inyecta el CSS global y la fuente Inter. Llamar al inicio de cada página.

    Usa el patrón canónico de Streamlit: dos llamadas separadas a
    st.markdown(unsafe_allow_html=True) — una para el <link> de Google Fonts
    y otra para el bloque <style>. Esto evita que el parser de markdown se
    confunda con múltiples elementos top-level mezclados.
    """
    st.markdown(_FONT_LINK, unsafe_allow_html=True)
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def page_header(titulo: str, subtitulo: str = "") -> None:
    """Encabezado de página."""
    sub_html = f"<p>{subtitulo}</p>" if subtitulo else ""
    st.markdown(
        f'<div class="lvca-page-header">'
        f'<h1>{titulo}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def section_header(titulo: str, icono: str = "") -> None:
    """
    Sub-encabezado consistente de sección. Si `icono` es el nombre de un ícono
    SVG registrado, se renderiza como SVG; si no, se trata como emoji literal.
    """
    if icono and icono in _ICON_PATHS:
        prefix = icon(icono, size=18, color=COLORS["text_light"])
    elif icono:
        prefix = icono
    else:
        prefix = ""
    st.markdown(
        f'<div class="lvca-section-header">{prefix}<span>{titulo}</span></div>',
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
    """Caja informativa con barra lateral verde."""
    st.markdown(
        f'<div class="lvca-info-box">{texto}</div>',
        unsafe_allow_html=True,
    )


def filter_bar_open() -> None:
    """Inicio de barra de filtros (úsalo con st.columns dentro)."""
    st.markdown('<div class="lvca-filter-bar">', unsafe_allow_html=True)


def filter_bar_close() -> None:
    """Cierre de barra de filtros."""
    st.markdown('</div>', unsafe_allow_html=True)


def danger_button_wrapper_open() -> None:
    """Wrap el siguiente st.button para mostrarlo en rojo (destructivo)."""
    st.markdown('<div class="lvca-danger">', unsafe_allow_html=True)


def danger_button_wrapper_close() -> None:
    st.markdown('</div>', unsafe_allow_html=True)


def ghost_button_wrapper_open() -> None:
    """Botón ghost (sin fondo) para acciones terciarias."""
    st.markdown('<div class="lvca-ghost">', unsafe_allow_html=True)


def ghost_button_wrapper_close() -> None:
    st.markdown('</div>', unsafe_allow_html=True)


def success_check_overlay(mensaje: str = "Guardado correctamente") -> None:
    """
    Renderiza un overlay con check verde animado en el centro de la pantalla.
    Llamar inmediatamente después de un guardado exitoso, antes de st.rerun().
    El overlay se desvanece a los ~1.6s gracias a un setTimeout en JS.
    """
    overlay_html = f"""
    <div class="lvca-success-overlay" id="lvca-success-overlay">
        <div class="lvca-success-card">
            <svg class="lvca-check-svg" viewBox="0 0 56 56">
                <circle cx="28" cy="28" r="26"/>
                <path d="M16 28 l9 9 l16 -18"/>
            </svg>
            <div class="lvca-success-msg">{mensaje}</div>
        </div>
    </div>
    <script>
        setTimeout(function() {{
            var el = document.getElementById('lvca-success-overlay');
            if (el) el.style.transition = 'opacity 0.25s';
            if (el) el.style.opacity = '0';
            setTimeout(function() {{ if (el) el.remove(); }}, 280);
        }}, 1300);
    </script>
    """
    st.markdown(overlay_html, unsafe_allow_html=True)


def toast(mensaje: str, tipo: str = "success", icono: str | None = None) -> None:
    """
    Notificación flotante en esquina superior derecha (~3s).
    tipo: "success" | "info" | "warn" | "danger".
    """
    cls_map = {
        "success": "",
        "info":    "lvca-toast-info",
        "warn":    "lvca-toast-warn",
        "danger":  "lvca-toast-danger",
    }
    icon_map = {
        "success": "check",
        "info":    "info",
        "warn":    "alert",
        "danger":  "alert",
    }
    cls = cls_map.get(tipo, "")
    color_map = {
        "success": COLORS["primary"],
        "info":    COLORS["secondary"],
        "warn":    COLORS["warning"],
        "danger":  COLORS["danger"],
    }
    icon_name = icono or icon_map.get(tipo, "info")
    color = color_map.get(tipo, COLORS["primary"])
    icon_svg = icon(icon_name, size=18, color=color)
    toast_html = f"""
    <div class="lvca-toast-wrap" id="lvca-toast-wrap">
        <div class="lvca-toast {cls}">
            <span style="display:inline-flex; align-items:center; gap:10px;">
                {icon_svg}<span>{mensaje}</span>
            </span>
        </div>
    </div>
    <script>
        setTimeout(function() {{
            var el = document.getElementById('lvca-toast-wrap');
            if (el) el.style.transition = 'opacity 0.25s, transform 0.25s';
            if (el) {{ el.style.opacity = '0'; el.style.transform = 'translateX(40%)'; }}
            setTimeout(function() {{ if (el) el.remove(); }}, 280);
        }}, 2800);
    </script>
    """
    st.markdown(toast_html, unsafe_allow_html=True)
