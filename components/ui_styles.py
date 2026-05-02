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
    # Dominio LVCA
    "microscope":   '<path d="M6 18h8"/><path d="M3 22h18"/><path d="M14 22a7 7 0 1 0 0-14h-1"/><path d="M9 14h2"/><path d="M9 12a2 2 0 0 1-2-2V6h6v4a2 2 0 0 1-2 2"/><path d="M12 6V3a1 1 0 0 0-1-1H9a1 1 0 0 0-1 1v3"/>',
    "test_tube":    '<path d="M14.5 2v17.5c0 1.4-1.1 2.5-2.5 2.5h0c-1.4 0-2.5-1.1-2.5-2.5V2"/><path d="M8.5 2h7"/><path d="M14.5 16h-5"/>',
    "thermometer":  '<path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/>',
    "waves":        '<path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/><path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1"/>',
    "bug":          '<path d="M8 2l1.88 1.88"/><path d="M14.12 3.88L16 2"/><path d="M9 7.13v-1a3.003 3.003 0 1 1 6 0v1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6"/><path d="M12 20v-9"/><path d="M6.53 9C4.6 8.8 3 7.1 3 5"/><path d="M6 13H2"/><path d="M3 21c0-2.1 1.7-3.8 3.8-4"/><path d="M20.97 5c0 2.1-1.6 3.8-3.5 4"/><path d="M22 13h-4"/><path d="M17.2 17c2.1.2 3.8 1.9 3.8 4"/>',
    "database":     '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    "map":          '<polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>',
    "tube_lab":     '<path d="M9 3h6v8.5a3.5 3.5 0 0 1-7 0V3z" transform="translate(-1 0)"/><path d="M16 3h6v8.5a3.5 3.5 0 0 1-7 0V3z" transform="translate(-2 0)"/>',
    "ban":          '<circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/>',
    "circle":       '<circle cx="12" cy="12" r="10"/>',
    "circle_dot":   '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3" fill="currentColor"/>',
    "clock":        '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    "arrow_right":  '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
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
    # Material Symbols Rounded — para íconos en HTML <span class="material-symbols-rounded">.
    # Streamlit la carga automáticamente solo si hay st.page_link(icon=":material/..."),
    # así que la forzamos aquí para que funcione también en login y cualquier HTML
    # inyectado antes de que se rendericen los page_links.
    '<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0" rel="stylesheet">'
)

_GLOBAL_CSS = """<style>
/* ── Variables CSS centralizadas (paleta "Integrated Eco-Aura") ──────────
   Fuente única de verdad de los colores de marca + acentos semánticos
   ECA. Cualquier color usado en HTML inyectado debe referenciar estas
   variables vía `var(--lvca-...)` en lugar de hex literales. */
:root {
    --lvca-brand-azul:        #1E6091;
    --lvca-brand-azul-dark:   #0D47A1;
    --lvca-brand-azul-light:  #2563EB;
    --lvca-acento-verde:      #10B981;
    --lvca-acento-verde-dark: #047857;
    --lvca-acento-amarillo:   #F59E0B;
    --lvca-acento-amarillo-dark: #B45309;
    --lvca-acento-rojo:       #EF4444;
    --lvca-acento-rojo-dark:  #B91C1C;
    --lvca-acento-teal:       #0a9396;
    --lvca-bg-app:            #F8FAFC;
    --lvca-bg-card:           #FFFFFF;
    --lvca-border:            #E2E8F0;
    --lvca-border-soft:       #F1F5F9;
    --lvca-text:              #0F172A;
    --lvca-text-muted:        #64748B;
    --lvca-text-faint:        #94A3B8;
}

/* Tipografía global Inter — densidad ajustada para minimalismo */
html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif !important;
    font-feature-settings: 'cv11', 'ss01';
    font-size: 14px;
}
p, li, span, label {
    line-height: 1.55;
}
h1, h2, h3, h4, h5, h6 {
    font-family: 'Inter', sans-serif !important;
    letter-spacing: -0.015em;
    color: #0f172a;
}
h1 { font-weight: 600 !important; font-size: 1.6rem !important; }
h2 { font-weight: 600 !important; font-size: 1.3rem !important; }
h3 { font-weight: 600 !important; font-size: 1.1rem !important; }
h4 { font-weight: 500 !important; font-size: 0.98rem !important; }
small, .small, .stCaption, [data-testid="stCaption"] {
    font-size: 0.78rem !important;
    color: #94a3b8 !important;
}

/* ── Ocultar nav nativa de Streamlit ───────────────────────────────────── */
[data-testid='stSidebarNav'] { display: none; }

/* ── Sidebar global OFF: la navegación se sirve vía top_nav() ──────────── */
[data-testid="stSidebar"],
[data-testid="collapsedControl"] {
    display: none !important;
}
[data-testid="stMain"] { margin-left: 0 !important; }

/* ── Sidebar limpio (separación por espacio, no por línea fuerte) ──────── */
[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid #f1f5f9;
}
[data-testid="stSidebar"] * { color: #334155 !important; font-size: 13px; }
[data-testid="stSidebar"] .stDivider { border-color: #f1f5f9 !important; }
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

/* ── Métricas — minimalismo equilibrado: borde casi invisible, sin sombra ── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #f1f5f9;
    border-radius: 10px;
    padding: 18px 22px;
    box-shadow: none;
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
[data-testid="stMetric"]:hover {
    border-color: #e2e8f0;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
[data-testid="stMetric"] label {
    color: #94a3b8 !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.85rem !important;
    font-weight: 600 !important;
    color: #0f172a !important;
    letter-spacing: -0.02em;
}
[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-size: 0.78rem !important;
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

/* ── DataFrames — sin líneas verticales, header limpio ─────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #f1f5f9;
}
[data-testid="stDataFrame"] [role="columnheader"] {
    background: #ffffff !important;
    border-bottom: 1px solid #e2e8f0 !important;
    border-right: none !important;
    color: #64748b !important;
    font-weight: 600 !important;
    font-size: 0.74rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stDataFrame"] [role="gridcell"] {
    border-right: none !important;
    border-bottom: 1px solid #f8fafc !important;
    font-size: 0.86rem !important;
}
[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {
    background: #fafbfc !important;
}

/* st.table también */
[data-testid="stTable"] table {
    border-collapse: collapse;
    border: none !important;
}
[data-testid="stTable"] th {
    background: transparent !important;
    border: none !important;
    border-bottom: 1px solid #e2e8f0 !important;
    color: #64748b !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 0.74rem !important;
    padding: 10px 14px !important;
}
[data-testid="stTable"] td {
    border: none !important;
    border-bottom: 1px solid #f8fafc !important;
    padding: 10px 14px !important;
    font-size: 0.86rem !important;
}

/* ── Botones — minimalista con animación sutil ─────────────────────────── */
.stButton > button,
button[kind="primary"],
button[kind="secondary"] {
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.86rem !important;
    font-family: 'Inter', sans-serif !important;
    letter-spacing: 0.005em;
    padding: 0.5rem 1rem !important;
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: none;
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

/* ── Formularios — borde más sutil, sin sombra ─────────────────────────── */
[data-testid="stForm"] {
    border: 1px solid #f1f5f9 !important;
    border-radius: 12px !important;
    padding: 24px !important;
    background: #ffffff !important;
    box-shadow: none;
}

/* Inputs estándar — más livianos, focus en verde institucional */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="select"] > div {
    background: #fafbfc !important;
    border-color: #e2e8f0 !important;
    border-radius: 8px !important;
    transition: all 0.15s ease;
}
[data-baseweb="input"] input:focus,
[data-baseweb="textarea"] textarea:focus {
    background: #ffffff !important;
    border-color: #1b6b35 !important;
    box-shadow: 0 0 0 3px rgba(27, 107, 53, 0.10) !important;
}

/* Variante minimalista para formularios largos: solo borde inferior */
.lvca-form-minimal [data-baseweb="input"] input,
.lvca-form-minimal [data-baseweb="textarea"] textarea {
    background: transparent !important;
    border-radius: 0 !important;
    border-top: none !important;
    border-left: none !important;
    border-right: none !important;
    border-bottom: 1px solid #d1d5db !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
}
.lvca-form-minimal [data-baseweb="input"] input:focus,
.lvca-form-minimal [data-baseweb="textarea"] textarea:focus {
    border-bottom: 2px solid #1b6b35 !important;
    box-shadow: none !important;
}
.lvca-form-minimal label {
    color: #64748b !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 500 !important;
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

/* ── Dividers — más aireados y casi invisibles ─────────────────────────── */
hr {
    border-color: #f1f5f9 !important;
    margin: 1.5rem 0 !important;
    opacity: 0.7;
}

/* ── Espaciado entre bloques principales ───────────────────────────────── */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 3rem !important;
}
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
    gap: 0.5rem;
}

/* ── Cards — borde casi invisible, sin sombra base ──────────────────── */
.lvca-card {
    background: #ffffff;
    border: 1px solid #f1f5f9;
    border-radius: 12px;
    padding: 24px 22px;
    text-align: center;
    transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
    height: 100%;
    box-shadow: none;
}
.lvca-card:hover {
    border-color: #e2e8f0;
    box-shadow: 0 2px 8px rgba(15,23,42,0.04);
    transform: translateY(-1px);
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

/* ── Encabezados de página y sección — más aireados ───────────────────── */
.lvca-page-header {
    padding: 4px 0 18px 0;
    margin-bottom: 8px;
}
.lvca-page-header h1 {
    font-size: 1.55rem !important;
    font-weight: 600 !important;
    color: #0f172a !important;
    margin-bottom: 4px !important;
    letter-spacing: -0.02em;
}
.lvca-page-header p {
    color: #94a3b8;
    font-size: 0.82rem;
    margin: 0;
}
.lvca-section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    color: #1e293b;
    font-size: 0.92rem;
    font-weight: 500;
    margin: 1.6rem 0 0.6rem 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #f1f5f9;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
.lvca-section-header svg { color: #94a3b8; }

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

/* ── Material Symbols Rounded: clase base por si Streamlit no la define
      todavía cuando el HTML se renderiza (ej. en el login). ──────────── */
.material-symbols-rounded {
    font-family: 'Material Symbols Rounded', sans-serif !important;
    font-weight: normal;
    font-style: normal;
    line-height: 1;
    letter-spacing: normal;
    text-transform: none;
    display: inline-block;
    white-space: nowrap;
    word-wrap: normal;
    direction: ltr;
    font-feature-settings: 'liga';
    -webkit-font-feature-settings: 'liga';
    -webkit-font-smoothing: antialiased;
}

/* ── Footer institucional (position:fixed abajo) ──────────────────────── */
.lvca-footer {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #0D47A1;
    color: #ffffff;
    text-align: center;
    font-size: 0.72rem;
    font-weight: 500;
    padding: 7px 16px 6px 16px;
    z-index: 100;
    letter-spacing: 0.02em;
    box-shadow: 0 -2px 8px rgba(13, 71, 161, 0.15);
}
.lvca-footer .lvca-footer-sep {
    margin: 0 8px;
    opacity: 0.55;
}
/* Padding-bottom en el main container para que el contenido no se
   oculte detrás del footer fijo. */
[data-testid="stMainBlockContainer"] {
    padding-bottom: 48px !important;
}

/* ── Filter bar estilo SSDH: blanco con sombra sutil ──────────────────── */
.lvca-filter-bar {
    background: #ffffff;
    border: 1px solid #eef0f2;
    border-radius: 10px;
    padding: 16px 22px;
    margin-bottom: 18px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.lvca-filter-bar label {
    color: #475569 !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ── Tabs SSDH: padding grande, underline azul al activar, fondo tintado
      en hover. Aplica a todas las st.tabs de la plataforma. ──────────── */
[data-testid="stTabs"] {
    border-bottom: 1px solid #eef0f2;
    margin-bottom: 14px;
}
[data-testid="stTabs"] button[data-baseweb="tab"] {
    padding: 12px 20px !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    color: #64748b !important;
    border-radius: 0 !important;
    margin-right: 2px !important;
    background: transparent !important;
    border-bottom: 3px solid transparent !important;
    transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease !important;
}
[data-testid="stTabs"] button[data-baseweb="tab"]:hover {
    color: #1565C0 !important;
    background: rgba(21, 101, 192, 0.04) !important;
}
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    color: #1565C0 !important;
    font-weight: 600 !important;
    border-bottom-color: #1565C0 !important;
    background: rgba(21, 101, 192, 0.06) !important;
}
/* El highlight nativo de Streamlit (la barrita inferior) lo ocultamos:
   nosotros estamos usando border-bottom del propio botón para el underline. */
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    display: none !important;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    border-bottom: none !important;
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
    animation:
        lvcaFadeIn    0.18s cubic-bezier(0.4, 0, 0.2, 1),
        lvcaOverlayOut 0.3s ease 1.5s forwards;
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
@keyframes lvcaOverlayOut {
    to { opacity: 0; visibility: hidden; pointer-events: none; }
}

/* ── Toast (esquina superior derecha) ──────────────────────────────────── */
.lvca-toast-wrap {
    position: fixed;
    top: 24px;
    right: 24px;
    z-index: 9998;
    animation:
        lvcaToastIn  0.25s cubic-bezier(0.4, 0, 0.2, 1),
        lvcaToastOut 0.3s ease 2.7s forwards;
}
.lvca-toast {
    background: white;
    border-radius: 12px;
    padding: 14px 18px;
    box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12);
    border-left: 4px solid #1b6b35;
    display: flex;
    align-items: flex-start;
    gap: 12px;
    min-width: 280px;
    max-width: 420px;
}
.lvca-toast .lvca-toast-icon {
    flex: 0 0 auto;
    width: 32px;
    height: 32px;
    border-radius: 999px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #e8f5e9;
    color: #2e7d32;
}
.lvca-toast.lvca-toast-info    { border-left-color: #0a9396; }
.lvca-toast.lvca-toast-info  .lvca-toast-icon { background: #e0f7f7; color: #0a9396; }
.lvca-toast.lvca-toast-warn    { border-left-color: #e8870e; }
.lvca-toast.lvca-toast-warn  .lvca-toast-icon { background: #fff4e0; color: #e8870e; }
.lvca-toast.lvca-toast-danger  { border-left-color: #c62828; }
.lvca-toast.lvca-toast-danger .lvca-toast-icon { background: #fce4e4; color: #c62828; }
.lvca-toast .lvca-toast-body { flex: 1; min-width: 0; }
.lvca-toast .lvca-toast-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: #1e293b;
    line-height: 1.3;
}
.lvca-toast .lvca-toast-sub {
    font-size: 0.78rem;
    color: #64748b;
    margin-top: 2px;
}
@keyframes lvcaToastIn {
    from { transform: translateX(120%); opacity: 0; }
    to   { transform: translateX(0);    opacity: 1; }
}
@keyframes lvcaToastOut {
    to { opacity: 0; transform: translateX(40%); visibility: hidden; pointer-events: none; }
}

/* ── Estado pill (compacto, con icono y dot de color) ──────────────────── */
.lvca-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    border: 1px solid transparent;
    line-height: 1;
}
.lvca-pill .lvca-pill-dot {
    width: 7px; height: 7px; border-radius: 999px;
    background: currentColor;
    display: inline-block;
}
.lvca-pill svg { width: 14px; height: 14px; }
.lvca-pill-planificada  { background:#f1f5f9; color:#475569; border-color:#e2e8f0; }
.lvca-pill-en_campo     { background:#e0f2fe; color:#0369a1; border-color:#bae6fd; }
.lvca-pill-en_lab       { background:#fff4e0; color:#a85d00; border-color:#fed7aa; }
.lvca-pill-validada     { background:#dcfce7; color:#166534; border-color:#bbf7d0; }
.lvca-pill-completada   { background:#dcfce7; color:#166534; border-color:#bbf7d0; }
.lvca-pill-anulada      { background:#fce4e4; color:#a31f1f; border-color:#fecaca; }
.lvca-pill-archivada    { background:#f8fafc; color:#64748b; border-color:#e2e8f0; }
.lvca-pill-excede       { background:#fce4e4; color:#a31f1f; border-color:#fecaca; }
.lvca-pill-cumple       { background:#dcfce7; color:#166534; border-color:#bbf7d0; }
.lvca-pill-sin_dato     { background:#f8fafc; color:#94a3b8; border-color:#e2e8f0; }

/* ── Estado card (descriptiva — para docs y estados extendidos) ────────── */
.lvca-estado-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-top: 3px solid #94a3b8;
    border-radius: 10px;
    padding: 14px 16px;
    height: 100%;
    transition: all 0.15s ease;
}
.lvca-estado-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.lvca-estado-card-icon {
    width: 36px; height: 36px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    background: #f8fafc; color: #64748b;
    margin-bottom: 10px;
}
.lvca-estado-card-title {
    font-size: 0.95rem; font-weight: 700; color: #1e293b;
    margin-bottom: 6px;
}
.lvca-estado-card-desc {
    font-size: 0.8rem; color: #475569; line-height: 1.45;
    margin-bottom: 12px;
}
.lvca-estado-card-foot {
    border-top: 1px dashed #e2e8f0;
    padding-top: 8px;
    font-size: 0.65rem; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 0.5px;
    display: flex; justify-content: space-between; align-items: center;
}
.lvca-card-planificada { border-top-color: #64748b; }
.lvca-card-planificada .lvca-estado-card-icon { background:#f1f5f9; color:#475569; }
.lvca-card-en_campo    { border-top-color: #0369a1; }
.lvca-card-en_campo    .lvca-estado-card-icon { background:#e0f2fe; color:#0369a1; }
.lvca-card-en_lab      { border-top-color: #a85d00; }
.lvca-card-en_lab      .lvca-estado-card-icon { background:#fff4e0; color:#a85d00; }
.lvca-card-validada    { border-top-color: #166534; }
.lvca-card-validada    .lvca-estado-card-icon { background:#dcfce7; color:#166534; }
.lvca-card-anulada     { border-top-color: #a31f1f; }
.lvca-card-anulada     .lvca-estado-card-icon { background:#fce4e4; color:#a31f1f; }

/* ── Timeline (ciclo de vida) ──────────────────────────────────────────── */
.lvca-timeline {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 18px 24px;
    margin: 8px 0;
}
.lvca-timeline-row {
    display: flex; align-items: center; justify-content: space-between;
    position: relative;
}
.lvca-timeline-step {
    display: flex; flex-direction: column; align-items: center;
    flex: 1; position: relative; z-index: 1;
    text-align: center;
}
.lvca-timeline-circle {
    width: 36px; height: 36px; border-radius: 999px;
    background: #f1f5f9; color: #94a3b8;
    border: 2px solid #e2e8f0;
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.85rem;
}
.lvca-timeline-step.done .lvca-timeline-circle {
    background: #1b6b35; color: white; border-color: #1b6b35;
}
.lvca-timeline-step.active .lvca-timeline-circle {
    background: #fff4e0; color: #a85d00; border-color: #e8870e;
    box-shadow: 0 0 0 4px rgba(232, 135, 14, 0.15);
}
.lvca-timeline-line {
    position: absolute; top: 17px; left: 0; right: 0; height: 2px;
    background: linear-gradient(to right,
        #1b6b35 var(--progress, 0%),
        #e2e8f0 var(--progress, 0%));
    z-index: 0;
}
.lvca-timeline-label {
    margin-top: 8px; font-size: 0.85rem; font-weight: 600; color: #1e293b;
}
.lvca-timeline-step.pending .lvca-timeline-label { color: #94a3b8; }
.lvca-timeline-sub {
    font-size: 0.7rem; color: #64748b; margin-top: 2px;
}

/* ── Inline note (con barra de color izquierda, sin fondo) ────────────── */
.lvca-inline-note {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 10px 14px;
    margin: 6px 0;
    border-radius: 8px;
    background: #f8fafc;
    border-left: 3px solid #0a9396;
    font-size: 0.85rem;
    color: #1e293b;
}
.lvca-inline-note.warn   { border-left-color: #e8870e; background:#fffaf0; }
.lvca-inline-note.danger { border-left-color: #c62828; background:#fef5f5; }
.lvca-inline-note.success{ border-left-color: #2e7d32; background:#f0faf2; }
.lvca-inline-note .lvca-inline-icon { flex: 0 0 auto; margin-top: 1px; opacity: 0.85; }

/* ── KPI cards "bold" (estilo mockup Integrated Eco-Aura) ────────────────
   Tarjetas con fondo sólido en color semántico, valor grande contrastado,
   ícono Material Symbol esquina superior derecha y bullet-list opcional
   debajo. Pensadas para el geoportal y dashboards de resumen ejecutivo. */
.lvca-kpi-bold {
    border-radius: 14px;
    padding: 18px 20px 16px 20px;
    min-height: 140px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: 0 4px 14px rgba(15,23,42,0.06),
                0 1px 3px rgba(15,23,42,0.04);
    transition: transform 0.18s cubic-bezier(0.4,0,0.2,1),
                box-shadow 0.18s cubic-bezier(0.4,0,0.2,1);
    position: relative;
    overflow: hidden;
}
.lvca-kpi-bold:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 22px rgba(15,23,42,0.10),
                0 2px 6px rgba(15,23,42,0.06);
}
.lvca-kpi-bold .lvca-kpi-head {
    display: flex; align-items: flex-start;
    justify-content: space-between; gap: 10px;
}
.lvca-kpi-bold .lvca-kpi-title {
    font-size: 0.92rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    line-height: 1.25;
    flex: 1;
}
.lvca-kpi-bold .lvca-kpi-icon {
    width: 38px; height: 38px;
    border-radius: 10px;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    background: rgba(255,255,255,0.18);
}
.lvca-kpi-bold .lvca-kpi-icon .material-symbols-rounded {
    font-size: 24px; line-height: 1;
}
.lvca-kpi-bold .lvca-kpi-value {
    font-size: 2.6rem;
    font-weight: 700;
    line-height: 1;
    letter-spacing: -0.03em;
    margin: 6px 0 4px 0;
    font-variant-numeric: tabular-nums;
}
.lvca-kpi-bold .lvca-kpi-bullets {
    list-style: none;
    padding: 0; margin: 6px 0 0 0;
    font-size: 0.78rem;
    line-height: 1.6;
    font-weight: 500;
}
.lvca-kpi-bold .lvca-kpi-bullets li::before {
    content: "• ";
    margin-right: 4px;
    opacity: 0.9;
}
.lvca-kpi-bold .lvca-kpi-foot {
    font-size: 0.7rem;
    opacity: 0.85;
    margin-top: 6px;
    font-weight: 500;
}

/* Variantes por color semántico */
.lvca-kpi-bold.azul {
    background: linear-gradient(135deg, var(--lvca-brand-azul) 0%, var(--lvca-brand-azul-dark) 100%);
    color: #ffffff;
}
.lvca-kpi-bold.amarillo {
    background: linear-gradient(135deg, var(--lvca-acento-amarillo) 0%, var(--lvca-acento-amarillo-dark) 100%);
    color: #1a1a1a;
}
.lvca-kpi-bold.rojo {
    background: linear-gradient(135deg, var(--lvca-acento-rojo) 0%, var(--lvca-acento-rojo-dark) 100%);
    color: #ffffff;
}
.lvca-kpi-bold.verde {
    background: linear-gradient(135deg, var(--lvca-acento-verde) 0%, var(--lvca-acento-verde-dark) 100%);
    color: #ffffff;
}
.lvca-kpi-bold.gris {
    background: linear-gradient(135deg, #94a3b8 0%, #64748b 100%);
    color: #ffffff;
}

/* Sparkline contenedor — SVG pintado en blanco semitransparente */
.lvca-kpi-bold .lvca-kpi-spark {
    margin-top: 8px;
    height: 32px;
    width: 100%;
    opacity: 0.85;
}
.lvca-kpi-bold .lvca-kpi-spark svg {
    width: 100%; height: 100%;
    display: block;
}

/* ── Toast flotante de éxito (top-right, auto-fade) ────────────────────── */
.lvca-toast-success {
    position: fixed;
    top: 78px;
    right: 22px;
    z-index: 1500;
    background: #ECFDF5;
    border: 1px solid #A7F3D0;
    border-left: 4px solid var(--lvca-acento-verde);
    border-radius: 10px;
    padding: 12px 16px 12px 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    color: #065F46;
    font-size: 0.84rem;
    font-weight: 500;
    box-shadow: 0 8px 24px rgba(16,185,129,0.18),
                0 2px 6px rgba(15,23,42,0.06);
    max-width: 340px;
    animation: lvcaToastIn 0.32s cubic-bezier(0.4,0,0.2,1),
               lvcaToastOut 0.4s cubic-bezier(0.4,0,0.2,1) 4.6s forwards;
}
.lvca-toast-success .material-symbols-rounded {
    font-size: 22px;
    color: var(--lvca-acento-verde);
    background: #ffffff;
    border-radius: 50%;
    padding: 2px;
    flex-shrink: 0;
}
@keyframes lvcaToastIn {
    from { opacity: 0; transform: translateY(-8px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes lvcaToastOut {
    to { opacity: 0; transform: translateY(-8px); pointer-events: none; }
}

/* ── Panel del punto integrado (estilo "ficha embebida") ────────────────
   Tarjeta blanca con bordes redondeados que se siente parte del mismo
   contenedor que el mapa: misma sombra, mismo radius, mismo borde. */
.lvca-panel-punto {
    background: #ffffff;
    border-radius: 12px;
    border: 1px solid var(--lvca-border-soft);
    box-shadow: 0 4px 14px rgba(15,23,42,0.05),
                0 1px 3px rgba(15,23,42,0.03);
    padding: 0;
    overflow: hidden;
}
.lvca-panel-punto .lvca-panel-head {
    padding: 14px 16px 12px 16px;
    border-bottom: 1px solid var(--lvca-border-soft);
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px;
    background: linear-gradient(180deg, #F8FAFC 0%, #FFFFFF 100%);
}
.lvca-panel-punto .lvca-panel-head .lvca-panel-codigo {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--lvca-text);
    letter-spacing: -0.01em;
}
.lvca-panel-punto .lvca-panel-head .lvca-panel-nombre {
    font-size: 0.78rem;
    color: var(--lvca-text-muted);
    margin-top: 2px;
    line-height: 1.3;
}
.lvca-panel-punto .lvca-panel-body {
    padding: 12px 16px 14px 16px;
}
.lvca-panel-punto .lvca-panel-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px 16px;
    font-size: 0.74rem;
    line-height: 1.45;
}
.lvca-panel-punto .lvca-panel-grid .lbl {
    color: var(--lvca-text-faint);
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
}
.lvca-panel-punto .lvca-panel-grid .val {
    color: var(--lvca-text);
    font-weight: 600;
    font-size: 0.82rem;
}
.lvca-panel-punto .lvca-panel-utm {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px dashed var(--lvca-border-soft);
    font-size: 0.74rem;
    color: var(--lvca-text-muted);
}
.lvca-panel-punto .lvca-panel-utm .val {
    color: var(--lvca-text);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
}

html { scroll-behavior: smooth; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

_FOOTER_HTML = """
<div class="lvca-footer">
    <span class="material-symbols-rounded"
        style="font-size:14px; vertical-align:-2px; margin-right:4px;">water_drop</span>
    PEIMS / LVCA &middot; AUTODEMA
    <span class="lvca-footer-sep">&middot;</span>
    D.S. N° 004-2017-MINAM
    <span class="lvca-footer-sep">&middot;</span>
    v1.0.0
</div>
"""


def aplicar_estilos() -> None:
    """
    Inyecta el CSS global y la fuente Inter. Llamar al inicio de cada página.

    Usa el patrón canónico de Streamlit: dos llamadas separadas a
    st.markdown(unsafe_allow_html=True) — una para el <link> de Google Fonts
    y otra para el bloque <style>. Esto evita que el parser de markdown se
    confunda con múltiples elementos top-level mezclados.

    Además inyecta el footer institucional (position:fixed) que se muestra
    en todas las páginas. Como `position:fixed` saca el elemento del flow,
    el orden de inyección no importa.
    """
    st.markdown(_FONT_LINK, unsafe_allow_html=True)
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown(_FOOTER_HTML, unsafe_allow_html=True)


def page_header(titulo: str, subtitulo: str = "", ambito: str = "") -> None:
    """
    Encabezado de página — banner estilo SSDH-ANA.

    - Gradiente azul institucional (#0D47A1 → #1565C0).
    - Título en blanco, subtítulo en blanco semitransparente.
    - Ámbito opcional: píldora a la derecha, equivalente al "UH 132" del
      SSDH. Solo lo usa el Geoportal por ahora; el resto de páginas lo
      dejan vacío.

    Compatibilidad: la firma vieja `page_header(titulo, subtitulo)` sigue
    funcionando — las 9 páginas que lo usan así quedan con el nuevo banner
    sin cambios adicionales.
    """
    ambito_html = (
        f'<div style="display:flex; align-items:center; gap:8px; '
        f'background:rgba(255,255,255,0.12); padding:6px 14px; '
        f'border-radius:20px; font-size:0.8rem; color:#ffffff; '
        f'font-weight:500; white-space:nowrap;">'
        f'<span class="material-symbols-rounded" '
        f'style="font-size:18px; line-height:1;">map</span> {ambito}'
        f'</div>'
        if ambito else ""
    )
    sub_html = (
        f'<p style="margin:4px 0 0 0; font-size:0.82rem; '
        f'color:rgba(255,255,255,0.82); font-weight:400;">{subtitulo}</p>'
        if subtitulo else ""
    )
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0D47A1 0%,#1565C0 100%);
             color:white; padding:18px 26px; border-radius:10px;
             box-shadow:0 4px 12px rgba(13,71,161,0.25);
             margin-bottom:18px;
             display:flex; align-items:center; justify-content:space-between;
             gap:20px; flex-wrap:wrap;">
            <div style="flex:1; min-width:260px;">
                <h1 style="margin:0; font-size:1.5rem; font-weight:700;
                     color:#ffffff; letter-spacing:-0.02em; line-height:1.2;">{titulo}</h1>
                {sub_html}
            </div>
            {ambito_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Top navigation horizontal (estilo SSDH/ANA)
# ─────────────────────────────────────────────────────────────────────────────

# CSS específico de top-nav (se inyecta solo cuando se llama a top_nav()).
#
# Uso `position: fixed` (no sticky) porque sticky es frágil en Streamlit:
# depende de que ningún ancestro tenga overflow:hidden/auto, pero forzar
# overflow:visible en los contenedores de scroll de Streamlit (stMain /
# stAppViewContainer) deshabilita el scroll de la página.
#
# Fixed no depende de ancestros: siempre queda pegado al viewport.
# Contrapartida: hay que añadir padding-top al contenido para que no
# quede oculto debajo, y ocultar stHeader (la barra casi-invisible de
# Streamlit) para que no se solape.
_TOP_NAV_CSS = """<style>
.st-key-lvca_top_nav {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 999 !important;
    background: #ffffff !important;
    border-bottom: 1px solid #e2e8f0;
    padding: 10px 1.5rem 6px 1.5rem;
    box-shadow: 0 1px 3px rgba(15,23,42,0.04);
}

/* Ocultar el stHeader de Streamlit (la delgada barra nativa arriba)
   para que no choque con el top-nav fijo. */
[data-testid="stHeader"] {
    display: none !important;
}

/* Empujar el contenido de la página para que no quede oculto bajo el
   top-nav fijo. La altura depende del tamaño del label de usuario +
   altura de los page_links. 108px es un buffer seguro; si el top-nav
   quedara más compacto/alto, ajustar aquí. */
[data-testid="stMainBlockContainer"]:has(.st-key-lvca_top_nav) {
    padding-top: 108px !important;
}
/* Línea 1: marca + usuario */
.lvca-brand {
    display: flex; align-items: baseline; gap: 12px;
    margin-bottom: 4px;
}
.lvca-brand-name {
    font-weight: 700; color: #1b6b35; font-size: 1.15rem;
    letter-spacing: -0.015em;
}
.lvca-brand-sub {
    font-size: 0.76rem; color: #64748b;
}
.lvca-user-block {
    text-align: right; font-size: 0.76rem; line-height: 1.3;
}
.lvca-user-name { font-weight: 600; color: #1e293b; display: block; }
.lvca-user-rol  { color: #94a3b8; text-transform: uppercase;
                  letter-spacing: 0.04em; font-size: 0.66rem; }

/* Page links dentro del top-nav: se ven como pills horizontales */
.st-key-lvca_top_nav [data-testid="stPageLink"] {
    margin: 0 !important;
}
.st-key-lvca_top_nav [data-testid="stPageLink"] a {
    display: flex !important;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px 12px !important;
    margin: 0 !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    color: #475569 !important;
    border-radius: 8px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    transition: all 0.15s ease !important;
    white-space: nowrap;
}
.st-key-lvca_top_nav [data-testid="stPageLink"] a:hover {
    background: #f1f5f9 !important;
    color: #1b6b35 !important;
}
/* Material Symbols en los links del top-nav: tamaño y color coherentes
   con el tamaño del label (16px, color heredado). */
.st-key-lvca_top_nav [data-testid="stPageLink"] a .material-symbols-rounded,
.st-key-lvca_top_nav [data-testid="stPageLink"] a span[class*="material"] {
    font-size: 18px !important;
    line-height: 1 !important;
}
/* El contenido del link no se trunca: label completo siempre visible */
.st-key-lvca_top_nav [data-testid="stPageLink"] a > div,
.st-key-lvca_top_nav [data-testid="stPageLink"] a p,
.st-key-lvca_top_nav [data-testid="stPageLink"] a span {
    overflow: visible !important;
    text-overflow: clip !important;
    white-space: nowrap !important;
    max-width: none !important;
}
/* Columnas del horizontal-block: ancho auto según contenido, no equi-repartido */
.st-key-lvca_top_nav [data-testid="stHorizontalBlock"] {
    flex-wrap: wrap !important;
    gap: 2px !important;
    align-items: center;
}
</style>"""

# Mapeo página → ícono Material Symbols (usados por st.page_link nativo)
_TOP_NAV_ICONS: dict[str, str] = {
    "pages/1_Inicio.py":          ":material/home:",
    "pages/2_Campanas.py":        ":material/event:",
    "pages/3_Muestras_Campo.py":  ":material/science:",
    "pages/4_Resultados_Lab.py":  ":material/biotech:",
    "pages/10_Base_Datos.py":     ":material/database:",
    "pages/8_Informes.py":        ":material/description:",
    "pages/7_Geoportal.py":       ":material/map:",
    "pages/5_Parametros.py":      ":material/list_alt:",
    "pages/6_Puntos_Muestreo.py": ":material/place:",
    "pages/9_Administracion.py":  ":material/settings:",
}

# Labels cortos específicos del top-nav (los labels largos de _PAGINAS_NAV
# se truncan visualmente cuando hay muchas páginas).
_TOP_NAV_LABELS: dict[str, str] = {
    "pages/1_Inicio.py":          "Inicio",
    "pages/2_Campanas.py":        "Campañas",
    "pages/3_Muestras_Campo.py":  "Muestras",
    "pages/4_Resultados_Lab.py":  "Resultados",
    "pages/10_Base_Datos.py":     "Base de Datos",
    "pages/8_Informes.py":        "Informes",
    "pages/7_Geoportal.py":       "Geoportal",
    "pages/5_Parametros.py":      "Parámetros",
    "pages/6_Puntos_Muestreo.py": "Puntos",
    "pages/9_Administracion.py":  "Admin",
}


def top_nav() -> None:
    """
    Barra de navegación horizontal arriba de la página (estilo SSDH/ANA).
    Reemplaza al sidebar — lo oculta vía CSS dentro del wrapper.

    Llamar inmediatamente después de aplicar_estilos() y antes de cualquier
    otro contenido. Solo renderiza si hay sesión activa.
    """
    sesion = st.session_state.get("sesion")
    if not sesion:
        return

    # Importar dinámicamente para evitar circular import
    from components.auth_guard import _PAGINAS_NAV
    from services.auth_service import ROL_JERARQUIA

    nivel_user = ROL_JERARQUIA.get(sesion.rol, 0)
    permitidas = [
        (label, ruta, rol)
        for label, ruta, rol, _seccion in _PAGINAS_NAV
        if nivel_user >= ROL_JERARQUIA.get(rol, 0)
    ]
    if not permitidas:
        return

    # CSS solo cuando se usa
    st.markdown(_TOP_NAV_CSS, unsafe_allow_html=True)

    # st.container(key=...) genera una clase `.st-key-lvca_top_nav` sobre un
    # wrapper real del DOM — necesario para que `position: sticky` funcione
    # (un <div> insertado por markdown no envuelve los siblings posteriores).
    with st.container(key="lvca_top_nav"):
        # Línea 1: marca + usuario
        head_l, head_r = st.columns([4, 1])
        with head_l:
            st.markdown(
                '<div class="lvca-brand">'
                '<span class="lvca-brand-name">LVCA</span>'
                '<span class="lvca-brand-sub">Plataforma de Vigilancia y Calidad del Agua · AUTODEMA</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        with head_r:
            rol_label = sesion.rol.replace("_", " ").capitalize()
            st.markdown(
                f'<div class="lvca-user-block">'
                f'<span class="lvca-user-name">{sesion.nombre_completo}</span>'
                f'<span class="lvca-user-rol">{rol_label}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Línea 2: links de navegación horizontales.
        # Pesos proporcionales a la longitud del label corto, para que los
        # largos tengan más espacio y los cortos no desperdicien ancho.
        labels_short = [
            _TOP_NAV_LABELS.get(ruta, label) for label, ruta, _rol in permitidas
        ]
        weights = [max(3, len(lbl) + 2) for lbl in labels_short]
        nav_cols = st.columns(weights, gap="small")
        for col, (_, ruta, _rol), lbl in zip(nav_cols, permitidas, labels_short):
            with col:
                st.page_link(ruta, label=lbl, icon=_TOP_NAV_ICONS.get(ruta))


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


def sparkline_svg(
    values,
    width=180,
    height=32,
    stroke="#ffffff",
    fill="rgba(255,255,255,0.20)",
    stroke_width=1.8,
):
    """
    Genera un SVG inline de sparkline (línea + área) a partir de una lista
    de valores. Pensado para usar dentro de las tarjetas KPI bold.

    No depende de matplotlib — el path lo construimos a mano para evitar
    overhead. Si la lista está vacía, devuelve un SVG vacío del mismo tamaño.
    """
    if not values:
        return f'<svg viewBox="0 0 {width} {height}"></svg>'

    if len(values) == 1:
        values = [values[0], values[0]]

    vmin = min(values)
    vmax = max(values)
    rng = vmax - vmin if vmax != vmin else 1.0

    pad_y = 3
    h_eff = height - 2 * pad_y
    n = len(values)
    step = width / (n - 1)

    points = []
    for i, v in enumerate(values):
        x = i * step
        y = pad_y + (h_eff - (v - vmin) / rng * h_eff)
        points.append((x, y))

    line_path = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in points)
    area_path = (
        line_path
        + f" L {points[-1][0]:.2f},{height} L {points[0][0]:.2f},{height} Z"
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<path d="{area_path}" fill="{fill}" stroke="none"/>'
        f'<path d="{line_path}" fill="none" stroke="{stroke}" '
        f'stroke-width="{stroke_width}" stroke-linecap="round" '
        f'stroke-linejoin="round"/>'
        f'</svg>'
    )


def kpi_bold_card(
    valor,
    label,
    color="azul",
    icon_material="insights",
    bullets=None,
    foot="",
    sparkline=None,
):
    """
    HTML de una tarjeta KPI estilo "Integrated Eco-Aura" (mockup LVCA).

    Args:
        valor:          número grande mostrado (15, 10, 3...).
        label:          título superior izquierdo ("Total Muestras (30 d)").
        color:          variante semántica — "azul", "amarillo", "rojo",
                        "verde" o "gris".
        icon_material:  nombre del ícono Material Symbols Rounded
                        (sin prefijo `:material/`).
        bullets:        lista corta de strings que se renderizan como
                        viñetas debajo del valor (• pH, • Turbidez...).
        foot:           texto pequeño debajo de bullets (legend / hint).
        sparkline:      lista de floats para mini-gráfico (solo se ve bien
                        en variante "azul" — el blanco contrasta).

    Devuelve un string HTML para insertar con `st.markdown(unsafe_allow_html=True)`.
    """
    bullets_html = ""
    if bullets:
        items = "".join(f"<li>{b}</li>" for b in bullets)
        bullets_html = f'<ul class="lvca-kpi-bullets">{items}</ul>'

    foot_html = (
        f'<div class="lvca-kpi-foot">{foot}</div>' if foot else ""
    )

    spark_html = ""
    if sparkline:
        # En variante "amarillo" usamos un trazo oscuro para contraste.
        if color == "amarillo":
            spark_svg = sparkline_svg(
                sparkline, stroke="#1a1a1a",
                fill="rgba(0,0,0,0.10)",
            )
        else:
            spark_svg = sparkline_svg(sparkline)
        spark_html = f'<div class="lvca-kpi-spark">{spark_svg}</div>'

    return (
        f'<div class="lvca-kpi-bold {color}">'
        f'  <div class="lvca-kpi-head">'
        f'    <div class="lvca-kpi-title">{label}</div>'
        f'    <div class="lvca-kpi-icon">'
        f'      <span class="material-symbols-rounded">{icon_material}</span>'
        f'    </div>'
        f'  </div>'
        f'  <div>'
        f'    <div class="lvca-kpi-value">{valor}</div>'
        f'    {bullets_html}'
        f'    {foot_html}'
        f'    {spark_html}'
        f'  </div>'
        f'</div>'
    )


def success_toast(mensaje, key=None):
    """
    Toast verde flotante arriba-derecha — se desvanece a ~5 s vía CSS.

    Si `key` se provee, solo se muestra una vez por sesión: la segunda
    llamada con la misma key no rendea nada. Útil para "Datos actualizados
    exitosamente" al primer load del geoportal sin spamear en cada rerun.
    """
    if key:
        flag = f"_lvca_toast_{key}"
        if st.session_state.get(flag):
            return
        st.session_state[flag] = True

    st.markdown(
        f'<div class="lvca-toast-success">'
        f'<span class="material-symbols-rounded">check_circle</span>'
        f'<span>{mensaje}</span>'
        f'</div>',
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


def minimal_form_open() -> None:
    """
    Wrapper para formularios largos con inputs underline-style.
    Solo borde inferior en inputs, fondo transparente, focus en verde.
    Usar antes de st.form() y cerrar después con minimal_form_close().
    """
    st.markdown('<div class="lvca-form-minimal">', unsafe_allow_html=True)


def minimal_form_close() -> None:
    st.markdown('</div>', unsafe_allow_html=True)


def success_check_overlay(mensaje: str = "Guardado correctamente") -> None:
    """
    Renderiza un overlay con check verde animado en el centro de la pantalla.
    Llamar inmediatamente después de un guardado exitoso.
    El overlay se desvanece a ~1.8s via animación CSS (keyframe lvcaOverlayOut).
    """
    # Nota: scripts dentro de st.markdown(unsafe_allow_html=True) NO se ejecutan
    # (los navegadores no corren <script> insertado por innerHTML). Por eso el
    # ciclo de vida del overlay está 100% en CSS.
    overlay_html = f"""
    <div class="lvca-success-overlay">
        <div class="lvca-success-card">
            <svg class="lvca-check-svg" viewBox="0 0 56 56">
                <circle cx="28" cy="28" r="26"/>
                <path d="M16 28 l9 9 l16 -18"/>
            </svg>
            <div class="lvca-success-msg">{mensaje}</div>
        </div>
    </div>
    """
    st.markdown(overlay_html, unsafe_allow_html=True)


def toast(
    mensaje: str,
    tipo: str = "success",
    sub: str | None = None,
    icono: str | None = None,
) -> None:
    """
    Notificación flotante con ícono prominente (esquina superior derecha, ~3s).

    tipo: "success" | "info" | "warn" | "danger"
    sub:  línea secundaria opcional (caption pequeño debajo del título)
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
        "danger":  "trash",
    }
    cls = cls_map.get(tipo, "")
    icon_name = icono or icon_map.get(tipo, "info")
    icon_svg = icon(icon_name, size=18, color="currentColor")
    sub_html = f'<div class="lvca-toast-sub">{sub}</div>' if sub else ''
    toast_html = f"""
    <div class="lvca-toast-wrap">
        <div class="lvca-toast {cls}">
            <div class="lvca-toast-icon">{icon_svg}</div>
            <div class="lvca-toast-body">
                <div class="lvca-toast-title">{mensaje}</div>
                {sub_html}
            </div>
        </div>
    </div>
    """
    st.markdown(toast_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Pills de estado (compactos, con ícono — para tablas y listados)
# ─────────────────────────────────────────────────────────────────────────────

# Mapeo estado → (clase CSS, ícono Lucide, label legible)
_ESTADO_CAMPANA = {
    "planificada":      ("planificada", "calendar",   "Planificada"),
    "en_campo":         ("en_campo",    "map_pin",    "En campo"),
    "en_laboratorio":   ("en_lab",      "test_tube",  "En laboratorio"),
    "validada":         ("validada",    "shield",     "Validada"),
    "completada":       ("completada",  "check",      "Completada"),
    "anulada":          ("anulada",     "ban",        "Anulada"),
    "archivada":        ("archivada",   "archive",    "Archivada"),
}
_ESTADO_RESULTADO = {
    "excede":   ("excede",   None, "Excede"),
    "cumple":   ("cumple",   None, "Cumple"),
    "sin_dato": ("sin_dato", None, "Sin dato"),
    "sin_eca":  ("sin_dato", None, "Sin ECA"),
}


def estado_pill(estado: str, dominio: str = "campana", extra: str = "") -> str:
    """
    Devuelve el HTML de un pill compacto con ícono y color por estado.

    dominio: "campana" (estados de campaña) o "resultado" (cumple/excede).
    extra: texto adicional al final del label, ej. " +320%" para excedencias.
    """
    mapping = _ESTADO_CAMPANA if dominio == "campana" else _ESTADO_RESULTADO
    cls, icono_name, label = mapping.get(estado, ("planificada", "info", estado.capitalize()))
    icon_html = icon(icono_name, size=14) if icono_name else '<span class="lvca-pill-dot"></span>'
    return (
        f'<span class="lvca-pill lvca-pill-{cls}">'
        f'{icon_html}<span>{label}{extra}</span>'
        f'</span>'
    )


def excede_pill(pct_exceso: float | None = None) -> str:
    """Pill 'Excede +X%' / 'Cumple' para tablas de resultados ECA."""
    if pct_exceso is None:
        return estado_pill("cumple", dominio="resultado")
    return estado_pill("excede", dominio="resultado", extra=f"  +{pct_exceso:.0f}%")


def estado_card(
    estado: str,
    descripcion: str,
    foot_label: str = "",
    foot_meta: str = "",
) -> str:
    """
    Tarjeta descriptiva del estado (para docs / paneles informativos).

    estado: clave del estado (ver _ESTADO_CAMPANA).
    descripcion: 1-2 líneas explicativas de qué significa el estado.
    foot_label: texto del pie (ej. "ESPERANDO INICIO").
    foot_meta:  metadato del pie (ej. "#5A6B5..."), normalmente código corto.
    """
    cls, icono_name, label = _ESTADO_CAMPANA.get(estado, ("planificada", "info", estado.capitalize()))
    return (
        f'<div class="lvca-estado-card lvca-card-{cls}">'
        f'<div class="lvca-estado-card-icon">{icon(icono_name, size=20)}</div>'
        f'<div class="lvca-estado-card-title">{label}</div>'
        f'<div class="lvca-estado-card-desc">{descripcion}</div>'
        f'<div class="lvca-estado-card-foot">'
        f'<span>{foot_label}</span><span>{foot_meta}</span>'
        f'</div>'
        f'</div>'
    )


def timeline(steps: list[dict], current: int = 0) -> None:
    """
    Renderiza un timeline horizontal de pasos para el ciclo de vida.

    steps: lista de {"label": str, "sub": str (opcional)}.
    current: índice del paso activo (los anteriores quedan como completados).
    """
    n = len(steps)
    progress = round(100 * current / max(n - 1, 1)) if n > 1 else 0
    html_steps = []
    for i, step in enumerate(steps):
        if i < current:
            cls = "done"
            inner = icon("check", size=18, color="#ffffff")
        elif i == current:
            cls = "active"
            inner = str(i + 1)
        else:
            cls = "pending"
            inner = str(i + 1)
        sub = step.get("sub", "")
        html_steps.append(
            f'<div class="lvca-timeline-step {cls}">'
            f'<div class="lvca-timeline-circle">{inner}</div>'
            f'<div class="lvca-timeline-label">{step["label"]}</div>'
            f'<div class="lvca-timeline-sub">{sub}</div>'
            f'</div>'
        )
    html = (
        f'<div class="lvca-timeline">'
        f'<div class="lvca-timeline-row">'
        f'<div class="lvca-timeline-line" style="--progress:{progress}%;"></div>'
        f'{"".join(html_steps)}'
        f'</div></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def inline_note(texto: str, tipo: str = "info", icono: str | None = None) -> None:
    """
    Nota inline con barra lateral de color (sin halo de fondo).
    tipo: "info" | "warn" | "danger" | "success".
    """
    icon_map = {"info": "info", "warn": "alert", "danger": "alert", "success": "check"}
    color_map = {
        "info": COLORS["secondary"], "warn": COLORS["warning"],
        "danger": COLORS["danger"],  "success": COLORS["success"],
    }
    cls = "" if tipo == "info" else tipo
    icon_name = icono or icon_map.get(tipo, "info")
    icon_svg = icon(icon_name, size=16, color=color_map.get(tipo, COLORS["secondary"]))
    st.markdown(
        f'<div class="lvca-inline-note {cls}">'
        f'<span class="lvca-inline-icon">{icon_svg}</span>'
        f'<span>{texto}</span></div>',
        unsafe_allow_html=True,
    )
