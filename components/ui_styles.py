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
    "primary":       "#0D47A1",
    "primary_dark":  "#0A3D7A",
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
    # Semáforo ECA unificado — espejo Python de las variables CSS
    # --lvca-acento-* (:root). Usar SIEMPRE estas claves en gráficos
    # Plotly/Folium y HTML inyectado, nunca hex literales.
    "eca_cumple":    "#10B981",
    "eca_alerta":    "#F59E0B",
    "eca_excede":    "#EF4444",
    "eca_sin_dato":  "#94A3B8",
}


# Estados de campaña → par {bg, fg} (espejo de las clases .lvca-pill-* del CSS).
# Fuente única para que la celda "Estado" de la tabla de campañas combine con
# el pill del panel de detalle y con el resto de la plataforma — reemplaza los
# colores Bootstrap sueltos que vivían en pages/2_Campanas.py.
CAMPANA_ESTADO_COLORS: dict[str, dict[str, str]] = {
    "planificada":    {"bg": "#f1f5f9", "fg": "#475569"},
    "en_campo":       {"bg": "#e0f2fe", "fg": "#0369a1"},
    "en_laboratorio": {"bg": "#fff4e0", "fg": "#a85d00"},
    "completada":     {"bg": "#dcfce7", "fg": "#166534"},
    "anulada":        {"bg": "#fce4e4", "fg": "#a31f1f"},
    "archivada":      {"bg": "#f8fafc", "fg": "#64748b"},
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


@st.cache_data(show_spinner=False)
def logo_data_uri(path: str, max_width: int = 160) -> str:
    """
    Lee un PNG del disco, lo redimensiona a `max_width` (preservando aspecto)
    y lo devuelve como data:URI base64. Cacheado para ejecutarse una sola vez.

    Reutilizable en el top-nav, login y footer sin volver a leer disco. Si el
    archivo no existe o PIL no está disponible, devuelve "" (el caller decide
    el fallback).
    """
    import base64
    import io
    from pathlib import Path as _Path

    try:
        from PIL import Image
    except Exception:
        return ""

    p = _Path(path)
    if not p.exists():
        return ""
    try:
        with Image.open(p) as img:
            img = img.convert("RGBA")
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


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
    --lvca-brand-azul-darker: #0A3D7A;   /* hover/active del primario (espejo COLORS["primary_dark"]) */
    --lvca-brand-azul-mid:    #1565C0;   /* foco WCAG + chip de marca — un solo azul de foco */
    --lvca-brand-azul-light:  #2563EB;
    --lvca-acento-verde:      #10B981;
    --lvca-acento-verde-dark: #047857;
    --lvca-acento-amarillo:   #F59E0B;
    --lvca-acento-amarillo-dark: #B45309;
    --lvca-acento-rojo:       #EF4444;
    --lvca-acento-rojo-dark:  #B91C1C;
    --lvca-acento-teal:       #0a9396;
    --lvca-nav-bg:            #0C3568;   /* fondo de la barra de navegación superior */
    --lvca-bg-app:            #F1F5F9;
    --lvca-bg-card:           #FFFFFF;
    --lvca-surface-alt:       #F8FAFC;   /* superficie alterna (headers de tabla, separadores) */
    --lvca-border:            #E2E8F0;
    --lvca-border-soft:       #F1F5F9;
    --lvca-text:              #0F172A;
    --lvca-text-muted:        #64748B;
    --lvca-text-faint:        #94A3B8;

    /* Escala tipográfica única — fuente de verdad de los tamaños.
       Reconcilia los h1 que competían (global 1.5rem, banner 2rem/800,
       page-header legacy 1.55rem) en una jerarquía coherente. */
    --lvca-fs-display: 2.125rem;   /* título de página (banner) — presencia institucional */
    --lvca-fs-h1:      1.5rem;
    --lvca-fs-h2:      1.25rem;
    --lvca-fs-h3:      1.0625rem;
    --lvca-fs-body:    0.875rem;
    --lvca-fs-cap:     0.75rem;     /* overline / caption */

    /* Ritmo de espaciado base 4px — paddings/márgenes consistentes. */
    --lvca-space-1: 4px;
    --lvca-space-2: 8px;
    --lvca-space-3: 12px;
    --lvca-space-4: 16px;
    --lvca-space-5: 24px;
    --lvca-space-6: 32px;
    --lvca-space-7: 48px;

    /* Tokens de forma, profundidad y movimiento.
       Escalera de elevación afinada: sombras estratificadas, blur algo mayor
       y alpha menor para un acabado premium más suave. */
    --lvca-radius-sm:   8px;
    --lvca-radius-md:   12px;
    --lvca-radius-lg:   16px;
    --lvca-shadow-xs:   0 1px 2px rgba(15,23,42,0.04), 0 1px 1px rgba(15,23,42,0.03);
    --lvca-shadow-sm:   0 1px 3px rgba(15,23,42,0.05), 0 1px 2px rgba(15,23,42,0.03);
    --lvca-shadow-md:   0 4px 12px rgba(15,23,42,0.06), 0 2px 4px rgba(15,23,42,0.03);
    --lvca-shadow-lg:   0 12px 32px rgba(15,23,42,0.10), 0 4px 8px rgba(15,23,42,0.04);
    --lvca-ease:        cubic-bezier(0.4, 0, 0.2, 1);
    --lvca-t:           0.18s;
    --lvca-focus-ring:  0 0 0 3px rgba(13,71,161,0.15);
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
h1 { font-weight: 700 !important; font-size: var(--lvca-fs-h1) !important; letter-spacing: -0.02em; }
h2 { font-weight: 600 !important; font-size: var(--lvca-fs-h2) !important; }
h3 { font-weight: 600 !important; font-size: var(--lvca-fs-h3) !important; }
h4 { font-weight: 600 !important; font-size: 0.95rem !important; }
small, .small, .stCaption, [data-testid="stCaption"] {
    font-size: 0.78rem !important;
    color: #94a3b8 !important;
}

/* ── Fondo de aplicación gris (estilo enterprise dashboard) ──────────────
   El contenido vive en tarjetas blancas que resaltan sobre este fondo.
   Refuerza el theme de config.toml por si el despliegue lo ignora. */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background: linear-gradient(180deg, #F7F9FC 0%, #E9EEF5 100%) !important;
    background-attachment: fixed !important;
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
    color: #0D47A1 !important;
    padding-left: 16px !important;
}

/* ── Métricas — tarjeta con profundidad sutil y lift en hover ──────────── */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #eef2f6;
    border-radius: var(--lvca-radius-lg);
    padding: 11px 16px;
    box-shadow: var(--lvca-shadow-sm);
    transition: all var(--lvca-t) var(--lvca-ease);
}
[data-testid="stMetric"]:hover {
    border-color: #e2e8f0;
    box-shadow: var(--lvca-shadow-md);
    transform: translateY(-2px);
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
    font-weight: 700 !important;
    color: #0f172a !important;
    letter-spacing: -0.02em;
    font-variant-numeric: tabular-nums;
}
[data-testid="stMetric"] [data-testid="stMetricDelta"] {
    font-size: 0.78rem !important;
}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] button[data-baseweb="tab"] {
    font-weight: 500;
    font-size: 0.88rem;
    padding: 8px 18px;
    border-radius: 8px 8px 0 0;
    transition: all 0.15s ease;
}
[data-testid="stTabs"] button[data-baseweb="tab"]:hover {
    background: #f8fafc;
}

/* ── DataFrames — sin líneas verticales, header limpio ─────────────────── */
[data-testid="stDataFrame"] {
    border-radius: var(--lvca-radius-md);
    overflow: hidden;
    border: 1px solid #eef2f6;
    box-shadow: var(--lvca-shadow-xs);
}
[data-testid="stDataFrame"] [role="columnheader"] {
    background: #f8fafc !important;
    border-bottom: 1px solid #e2e8f0 !important;
    border-right: none !important;
    color: #475569 !important;
    font-weight: 600 !important;
    font-size: 0.74rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}
[data-testid="stDataFrame"] [role="gridcell"] {
    border-right: none !important;
    border-bottom: 1px solid #f8fafc !important;
    font-size: 0.86rem !important;
    font-variant-numeric: tabular-nums;
}
[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {
    background: #f1f5f9 !important;
}

/* Gráficos Plotly como tarjeta blanca — sobre el fondo gris quedan
   integrados al sistema de cards sin tocar cada figura. */
[data-testid="stPlotlyChart"] {
    background: #ffffff;
    border: 1px solid #eef2f6;
    border-radius: var(--lvca-radius-md);
    box-shadow: var(--lvca-shadow-xs);
    padding: 5px 8px;
}

/* st.table también — tarjeta blanca */
[data-testid="stTable"] {
    background: #ffffff;
    border: 1px solid #eef2f6 !important;
    border-radius: var(--lvca-radius-md);
    box-shadow: var(--lvca-shadow-xs);
    overflow: hidden;
}
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
    padding: 0.4rem 0.9rem !important;
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
    outline: none;
    box-shadow: var(--lvca-focus-ring) !important;
}

/* Botones secundarios — superficie blanca para resaltar sobre fondo gris */
.stButton > button[kind="secondary"],
button[kind="secondary"] {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    color: #334155 !important;
}
.stButton > button[kind="secondary"]:hover,
button[kind="secondary"]:hover {
    border-color: #cbd5e1 !important;
    background: #ffffff !important;
}

/* Botones primarios — azul institucional sólido (minimalista, sin gradiente) */
.stButton > button[kind="primary"],
button[kind="primary"] {
    background: linear-gradient(180deg, #1357b3 0%, var(--lvca-brand-azul-dark) 100%) !important;
    border-color: var(--lvca-brand-azul-dark) !important;
    color: white !important;
    box-shadow: 0 2px 6px rgba(13, 71, 161, 0.22) !important;
}
.stButton > button[kind="primary"]:hover,
button[kind="primary"]:hover {
    background: linear-gradient(180deg, var(--lvca-brand-azul-dark) 0%, var(--lvca-brand-azul-darker) 100%) !important;
    border-color: var(--lvca-brand-azul-darker) !important;
    box-shadow: 0 5px 14px rgba(13, 71, 161, 0.30) !important;
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
    box-shadow: 0 0 0 3px rgba(13, 71, 161, 0.12);
}

/* ── Formularios — tarjeta con profundidad mínima ──────────────────────── */
[data-testid="stForm"] {
    border: 1px solid #eef2f6 !important;
    border-radius: var(--lvca-radius-md) !important;
    padding: 12px 14px !important;
    background: #ffffff !important;
    box-shadow: var(--lvca-shadow-xs);
}

/* Inputs estándar — fondo blanco limpio, focus en verde institucional */
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea,
[data-baseweb="select"] > div {
    background: #ffffff !important;
    border-color: #e2e8f0 !important;
    border-radius: var(--lvca-radius-sm) !important;
    transition: all 0.15s ease;
}
[data-baseweb="input"] input {
    padding-top: 0.4rem !important;
    padding-bottom: 0.4rem !important;
}
[data-baseweb="input"] input:focus,
[data-baseweb="textarea"] textarea:focus {
    background: #ffffff !important;
    border-color: var(--lvca-brand-azul-dark) !important;
    box-shadow: var(--lvca-focus-ring) !important;
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
    border-bottom: 2px solid var(--lvca-brand-azul-dark) !important;
    box-shadow: none !important;
}
.lvca-form-minimal label {
    color: #64748b !important;
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 500 !important;
}

/* ── Expanders — tarjeta blanca ────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: #ffffff;
    border: 1px solid #eef2f6;
    border-radius: var(--lvca-radius-md);
    box-shadow: var(--lvca-shadow-xs);
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stExpander"]:hover {
    border-color: #e2e8f0;
    box-shadow: var(--lvca-shadow-sm);
}
[data-testid="stExpander"] details,
[data-testid="stExpander"] summary {
    background: transparent !important;
}

/* ── Dividers — visibles sobre el fondo gris de la app ─────────────────── */
hr {
    border-color: #dbe3ec !important;
    margin: 0.5rem 0 !important;
    opacity: 0.9;
}

/* ── Espaciado entre bloques principales ───────────────────────────────── */
.block-container {
    padding-top: 2.5rem !important;
    padding-bottom: 3rem !important;
}
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"],
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
    gap: 0.35rem;
}

/* Colapsar los contenedores que SOLO inyectan CSS/fuentes invisibles
   (los st.markdown de <style>/<link> de aplicar_estilos, top_nav y footer).
   Cada uno dejaba un stElementContainer de altura 0 que IGUAL consumía el
   gap del stack vertical → ~80px de hueco fantasma sobre el banner de CADA
   página. El <style>/<link> sigue aplicando aunque su contenedor esté
   display:none (las reglas CSS no dependen de que su <style> sea visible).

   IMPORTANTE: el :not(:has(...)) excluye los markdown que mezclan <style>
   con contenido VISIBLE en el mismo st.markdown (p. ej. la tabla HTML de
   Base de Datos = <style> + <div><table>). Solo se colapsan los contenedores
   cuyo markdown es exclusivamente <style>/<link>, nunca los que tienen tabla
   u otro elemento visible. */
[data-testid="stElementContainer"]:has(> .stMarkdown > [data-testid="stMarkdownContainer"] > style):not(:has(> .stMarkdown > [data-testid="stMarkdownContainer"] > :not(style):not(link))),
[data-testid="stElementContainer"]:has(> .stMarkdown > [data-testid="stMarkdownContainer"] > link):not(:has(> .stMarkdown > [data-testid="stMarkdownContainer"] > :not(style):not(link))) {
    display: none !important;
}

/* ── Compactación de widgets de formulario ───────────────────────────────
   Pega el label a su control y reduce el aire por campo. Es el mayor
   ahorro de scroll en páginas con muchos campos (Puntos, Resultados,
   Muestras). Solo espaciado; no toca el alto del control ni su lógica. */
[data-testid="stWidgetLabel"] {
    margin-bottom: 1px !important;
}
[data-testid="stWidgetLabel"] p {
    line-height: 1.2 !important;
}
/* Dentro de formularios, gap mínimo entre campos. */
[data-testid="stForm"] [data-testid="stVerticalBlock"] {
    gap: 0.25rem !important;
}
/* Caption / texto de ayuda más pegado. */
[data-testid="stCaptionContainer"] {
    margin-top: 0 !important;
    margin-bottom: 2px !important;
}
/* Expander: cabecera y contenido con menos relleno vertical. */
[data-testid="stExpander"] summary {
    padding-top: 0.45rem !important;
    padding-bottom: 0.45rem !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
    padding-top: 0.25rem !important;
}

/* ── Cards — borde casi invisible, sin sombra base ──────────────────── */
.lvca-card {
    background: #ffffff;
    border: 1px solid #f1f5f9;
    border-radius: var(--lvca-radius-md);
    padding: 13px 18px;
    text-align: center;
    transition: all var(--lvca-t) var(--lvca-ease);
    height: 100%;
    box-shadow: var(--lvca-shadow-xs);
}
.lvca-card:hover {
    border-color: #e2e8f0;
    box-shadow: var(--lvca-shadow-sm);
    transform: translateY(-2px);
}
.lvca-card-icon {
    margin-bottom: 10px;
    color: var(--lvca-brand-azul-dark);
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

/* ── Primitiva de tarjeta unificada — generada por card() en ui_styles ──
   Superficie blanca tokenizada con barra de acento opcional. Reemplaza el
   HTML de tarjeta escrito a mano (excedencias, tareas, informes, tiles). */
.lvca-card-surface {
    transition: box-shadow var(--lvca-t) var(--lvca-ease),
                transform var(--lvca-t) var(--lvca-ease),
                border-color var(--lvca-t) var(--lvca-ease);
}
.lvca-card-surface--hover:hover {
    box-shadow: var(--lvca-shadow-sm);
    transform: translateY(-2px);
    border-color: var(--lvca-border) !important;
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
    gap: 11px;
    color: #0f172a;
    font-size: 1.05rem;
    font-weight: 700;
    margin: 0.9rem 0 0.4rem 0;
    padding-bottom: 6px;
    border-bottom: 1px solid var(--lvca-border);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
/* Ícono de sección dentro de un chip teal suave — acento de marca moderno. */
.lvca-section-header svg {
    color: var(--lvca-acento-teal);
    background: rgba(10, 147, 150, 0.10);
    border-radius: 8px;
    padding: 6px;
    width: 18px; height: 18px;
    box-sizing: content-box;
    flex-shrink: 0;
}

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
    background: #ffffff;
    border: 1px solid #eef2f6;
    border-left: 3px solid #0D47A1;
    border-radius: 0 8px 8px 0;
    padding: 8px 14px;
    margin: 5px 0;
    font-size: 0.88rem;
    color: #334155;
    box-shadow: var(--lvca-shadow-xs);
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
    font-size: 0.7rem;
    font-weight: 500;
    padding: 5px 16px;
    z-index: 100;
    letter-spacing: 0.02em;
    border-top: 1px solid rgba(255,255,255,0.12);
}
.lvca-footer .lvca-footer-sep {
    margin: 0 8px;
    opacity: 0.55;
}
.lvca-footer .lvca-footer-strong { font-weight: 700; }
.lvca-footer .lvca-footer-link {
    color: #ffffff; text-decoration: underline;
    text-underline-offset: 2px; opacity: 0.9;
}
.lvca-footer .lvca-footer-link:hover { opacity: 1; }
/* Padding-bottom en el main container para que el contenido no se
   oculte detrás del footer fijo. Se duplica sobre .block-container
   como fallback por si cambia el data-testid en versiones futuras. */
[data-testid="stMainBlockContainer"],
.block-container {
    padding-bottom: 36px !important;
}

/* ── Filter bar estilo SSDH: blanco con sombra sutil ──────────────────── */
.lvca-filter-bar {
    background: #ffffff;
    border: 1px solid #eef0f2;
    border-radius: 10px;
    padding: 8px 16px;
    margin-bottom: 8px;
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
    border-bottom: 1px solid #dbe3ec;
    margin-bottom: 10px;
}
[data-testid="stTabs"] button[data-baseweb="tab"] {
    padding: 8px 18px !important;
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
    color: #0D47A1 !important;
    background: rgba(13, 71, 161, 0.05) !important;
}
[data-testid="stTabs"] button[data-baseweb="tab"][aria-selected="true"] {
    color: #0D47A1 !important;
    font-weight: 600 !important;
    border-bottom-color: transparent !important;
    border-image: linear-gradient(90deg, #0D47A1, #0a9396) 1 !important;
    border-bottom: 2.5px solid !important;
    background: rgba(13, 71, 161, 0.06) !important;
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
    border-left: 4px solid #0D47A1;
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
    padding: 14px 20px;
    margin: 6px 0;
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
    background: #0D47A1; color: white; border-color: #0D47A1;
}
.lvca-timeline-step.active .lvca-timeline-circle {
    background: #fff4e0; color: #a85d00; border-color: #e8870e;
    box-shadow: 0 0 0 4px rgba(232, 135, 14, 0.15);
}
.lvca-timeline-line {
    position: absolute; top: 17px; left: 0; right: 0; height: 2px;
    background: linear-gradient(to right,
        #0D47A1 var(--progress, 0%),
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
    margin: 4px 0;
    border-radius: 8px;
    background: #ffffff;
    border: 1px solid #eef2f6;
    border-left: 3px solid #0a9396;
    font-size: 0.85rem;
    color: #1e293b;
}
.lvca-inline-note.warn   { border-left-color: #e8870e; background:#fffaf0; }
.lvca-inline-note.danger { border-left-color: #c62828; background:#fef5f5; }
.lvca-inline-note.success{ border-left-color: #2e7d32; background:#f0faf2; }
.lvca-inline-note .lvca-inline-icon { flex: 0 0 auto; margin-top: 1px; opacity: 0.85; }

/* ── KPI cards "bold" (refinadas) ───────────────────────────────────────
   Tarjeta BLANCA con el número como protagonista en el color semántico,
   acento vertical izquierdo, ícono en chip tintado y bullets/foot/sparkline
   de soporte. Coherentes con las KPI lite de Inicio. El color de cada
   variante se inyecta vía las custom props --kpi-c (color) y --kpi-bg
   (tinte del chip). Pensadas para el geoportal y dashboards ejecutivos. */
.lvca-kpi-bold {
    background: #ffffff;
    border: 1px solid #eef2f6;
    border-radius: var(--lvca-radius-lg);
    padding: 14px 16px 13px 20px;
    min-height: 120px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    box-shadow: var(--lvca-shadow-xs);
    transition: transform 0.18s cubic-bezier(0.4,0,0.2,1),
                box-shadow 0.18s cubic-bezier(0.4,0,0.2,1);
    position: relative;
    overflow: hidden;
    color: var(--lvca-text);
}
.lvca-kpi-bold::after {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 5px;
    background: var(--kpi-c, var(--lvca-brand-azul-dark));
}
.lvca-kpi-bold:hover {
    transform: translateY(-2px);
    box-shadow: var(--lvca-shadow-sm);
}
.lvca-kpi-bold .lvca-kpi-head {
    display: flex; align-items: center;
    justify-content: space-between; gap: 10px;
}
.lvca-kpi-bold .lvca-kpi-title {
    font-size: 0.74rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--lvca-text-muted);
    line-height: 1.3;
    flex: 1;
}
.lvca-kpi-bold .lvca-kpi-icon {
    width: 40px; height: 40px;
    border-radius: 999px;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    background: var(--kpi-bg, #e8f0fb);
    color: var(--kpi-c, var(--lvca-brand-azul-dark));
}
.lvca-kpi-bold .lvca-kpi-icon .material-symbols-rounded {
    font-size: 22px; line-height: 1;
}
.lvca-kpi-bold .lvca-kpi-value {
    font-size: 2.8rem;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.035em;
    margin: 10px 0 4px 0;
    font-variant-numeric: tabular-nums;
    color: var(--kpi-c, var(--lvca-brand-azul-dark));
}
.lvca-kpi-bold .lvca-kpi-bullets {
    list-style: none;
    padding: 0; margin: 8px 0 0 0;
    font-size: 0.78rem;
    line-height: 1.6;
    font-weight: 500;
    color: var(--lvca-text-muted);
}
.lvca-kpi-bold .lvca-kpi-bullets li::before {
    content: "•";
    margin-right: 6px;
    color: var(--kpi-c, var(--lvca-brand-azul-dark));
    font-weight: 700;
}
.lvca-kpi-bold .lvca-kpi-foot {
    font-size: 0.72rem;
    color: var(--lvca-text-faint);
    margin-top: 8px;
    font-weight: 500;
}

/* Variantes por color semántico — definen el color del número/acento/chip */
.lvca-kpi-bold.azul     { --kpi-c: var(--lvca-brand-azul-dark);    --kpi-bg: #e8f0fb; }
.lvca-kpi-bold.amarillo { --kpi-c: var(--lvca-acento-amarillo-dark); --kpi-bg: #fef3c7; }
.lvca-kpi-bold.rojo     { --kpi-c: var(--lvca-acento-rojo-dark);    --kpi-bg: #fee2e2; }
.lvca-kpi-bold.verde    { --kpi-c: var(--lvca-acento-verde-dark);   --kpi-bg: #dcfce7; }
.lvca-kpi-bold.gris     { --kpi-c: #64748b;                         --kpi-bg: #f1f5f9; }

/* Sparkline contenedor — trazo en el color semántico (se fija en el caller) */
.lvca-kpi-bold .lvca-kpi-spark {
    margin-top: 10px;
    height: 32px;
    width: 100%;
    opacity: 0.95;
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
    box-shadow: var(--lvca-shadow-xs);
    padding: 0;
    overflow: hidden;
}
.lvca-panel-punto .lvca-panel-head {
    padding: 14px 16px 12px 16px;
    border-bottom: 1px solid var(--lvca-border-soft);
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px;
    background: #F8FAFC;
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

/* ── Geoportal: tarjeta "Phyllum dominante" ─────────────────────────────
   Coherente con .lvca-panel-punto (mismo radius/sombra). El color del filo
   entra como custom property --lvca-phy-color (dinámico por phyllum). */
.lvca-panel-phyllum {
    background: #ffffff;
    border: 1px solid var(--lvca-border-soft);
    border-left: 4px solid var(--lvca-phy-color, var(--lvca-text-faint));
    border-radius: 12px;
    box-shadow: 0 4px 14px rgba(15,23,42,0.05),
                0 1px 3px rgba(15,23,42,0.03);
    padding: 10px 14px;
    margin-top: 10px;
    font-size: 0.78rem;
}
.lvca-panel-phyllum .lbl {
    color: var(--lvca-text-faint);
    font-size: 0.66rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-weight: 600;
}
.lvca-panel-phyllum .row {
    display: flex; align-items: center; justify-content: space-between;
    gap: 10px; margin-top: 4px;
}
.lvca-panel-phyllum .dot {
    display: inline-block; width: 10px; height: 10px; border-radius: 50%;
    margin-right: 6px; vertical-align: -1px;
    background: var(--lvca-phy-color, var(--lvca-text-faint));
}
.lvca-panel-phyllum b { color: var(--lvca-text); }
.lvca-panel-phyllum .cel { font-size: 0.72rem; color: var(--lvca-text-muted); }
.lvca-panel-phyllum .meta {
    color: var(--lvca-text-faint); font-size: 0.66rem; margin-top: 3px;
}

/* ── Geoportal: hint "Selecciona un parámetro…" (estado vacío) ──────────── */
.lvca-geo-empty-hint {
    background: var(--lvca-surface-alt, #F8FAFC);
    border: 1px dashed var(--lvca-border, #CBD5E1);
    border-radius: 10px;
    padding: 24px 18px;
    margin-top: 8px;
    text-align: center;
    color: var(--lvca-text-muted);
    font-size: 0.86rem;
}
.lvca-geo-empty-hint .material-symbols-rounded {
    font-size: 24px; color: var(--lvca-text-faint);
    vertical-align: middle; margin-right: 6px;
}

/* ── Geoportal: placeholder "— sin parámetros" del selector de categoría ── */
.lvca-geo-sel-empty {
    font-size: 0.78rem; color: var(--lvca-text-faint);
}
.lvca-geo-sel-empty .titulo {
    font-size: 0.84rem; color: var(--lvca-text-muted);
    font-weight: 500; margin-bottom: 4px;
}
.lvca-geo-sel-empty .cuerpo { padding: 7px 0; }

/* ── Geoportal: encabezado de grupo de los 3 selectores de parámetro ───── */
.lvca-geo-sel-header {
    display: flex; align-items: center; gap: 6px;
    font-size: 0.72rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.04em; color: var(--lvca-text-faint);
    margin: 2px 0 4px 0;
}
.lvca-geo-sel-header svg { flex-shrink: 0; }

/* ── Geoportal: vista integrada (KPIs compactas + sidebar) ──────────────
   Movido desde el st.markdown inline de pages/7_Geoportal.py para no
   reinyectar ~60 líneas de CSS en cada rerun completo. Selectores
   namespaced: no afectan otras páginas. */
/* Padding superior compacto para maximizar espacio vertical.
   Doble :has para ganar a la regla genérica del top-nav (108px), que de otro
   modo deja un hueco en blanco entre la barra azul y las tarjetas. */
[data-testid="stMainBlockContainer"]:has(.lvca-geo-vista-integrada),
[data-testid="stMainBlockContainer"]:has(.lvca-geo-vista-integrada):has(.st-key-lvca_top_nav) {
    padding-top: 84px !important;
    padding-bottom: 10px !important;
}
/* El div .lvca-geo-vista-integrada es solo un ancla de CSS: su contenedor se
   saca del flujo (display:none) para que NO deje hueco vertical sobre las
   tarjetas. El elemento sigue en el DOM, así que :has(...) del padding y los
   selectores de ancla siguen funcionando. */
[data-testid="stElementContainer"]:has(.lvca-geo-vista-integrada) {
    display: none !important;
}
/* KPI cards más compactas */
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold,
.lvca-geo-kpis .lvca-kpi-bold {
    min-height: 124px !important;
    padding: 14px 16px 13px 20px !important;
    border-radius: 12px !important;
}
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-value,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-value {
    font-size: 2.35rem !important;
    margin: 6px 0 4px 0 !important;
}
/* Bullets en una sola línea con ellipsis: evita el amontonamiento cuando
   el bullet es "CÓDIGO — Nombre largo". El texto completo queda en title. */
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-bullets li,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-bullets li {
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    max-width: 100%;
}
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-title,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-title {
    font-size: 0.7rem !important;
}
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-icon,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-icon {
    width: 34px !important; height: 34px !important;
    border-radius: 999px !important;
}
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-icon .material-symbols-rounded,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-icon .material-symbols-rounded {
    font-size: 20px !important;
}
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-bullets,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-bullets {
    font-size: 0.72rem !important;
    line-height: 1.55 !important;
    margin: 3px 0 0 0 !important;
}
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-foot,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-foot {
    font-size: 0.62rem !important;
    margin-top: 2px !important;
}
.lvca-geo-vista-integrada ~ div .lvca-kpi-bold .lvca-kpi-spark,
.lvca-geo-kpis .lvca-kpi-bold .lvca-kpi-spark {
    margin-top: 4px !important; height: 22px !important;
}
/* Sidebar derecha del geoportal — gaps mínimos */
.lvca-geo-sidebar [data-testid="stVerticalBlock"] {
    gap: 0.5rem !important;
}
.lvca-geo-sidebar [data-testid="stRadio"] {
    margin-bottom: -8px;
}
.lvca-geo-sidebar .stRadio > div {
    flex-direction: row !important;
    gap: 10px !important;
}

/* ── Banner de página (page_header + login) ─────────────────────────────
   Minimalista refinado: encabezado claro sobre tarjeta blanca, título en
   tinta oscura y filete inferior fino azul→teal que une las dos identidades
   cromáticas sin recurrir a un bloque de color saturado. */
.lvca-banner {
    position: relative;
    overflow: hidden;
    background:
        radial-gradient(130% 150% at 100% 0%, rgba(10,147,150,0.07) 0%, rgba(10,147,150,0) 46%),
        linear-gradient(135deg, #ffffff 0%, #f3f8fd 100%);
    color: var(--lvca-text);
    padding: 12px 32px 12px 36px;
    border: 1px solid var(--lvca-border-soft);
    border-radius: var(--lvca-radius-lg);
    box-shadow: var(--lvca-shadow-sm);
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 20px;
    flex-wrap: wrap;
}
/* Barra de acento vertical azul→teal con leve resplandor: presencia
   institucional marcada sin recurrir a un bloque de color saturado. */
.lvca-banner::after {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 6px;
    background: linear-gradient(180deg, var(--lvca-brand-azul-dark), var(--lvca-acento-teal));
    box-shadow: 0 0 18px rgba(13,71,161,0.28);
}
.lvca-banner .lvca-banner-body { flex: 1; min-width: 260px; position: relative; }
.lvca-banner h1 {
    margin: 0;
    font-size: var(--lvca-fs-display) !important;
    font-weight: 700 !important;
    color: var(--lvca-text) !important;
    letter-spacing: -0.025em;
    line-height: 1.15;
}
.lvca-banner .lvca-banner-sub {
    margin: 4px 0 0 0;
    font-size: 0.9rem;
    color: var(--lvca-text-muted);
    font-weight: 500;
}
.lvca-banner .lvca-banner-ambito {
    display: flex; align-items: center; gap: 8px;
    background: #eef4fb;
    border: 1px solid #dbe7f5;
    padding: 6px 14px;
    border-radius: 999px;
    font-size: 0.8rem;
    color: var(--lvca-brand-azul-dark);
    font-weight: 600;
    white-space: nowrap;
    position: relative;
}

/* ── KPI "lite": tarjeta blanca con acento semántico ────────────────────
   Ícono circular pastel + valor grande + borde inferior 3px de color.
   Variantes: azul / verde / amarillo / rojo / gris. */
.lvca-kpi-lite {
    background: #ffffff;
    border: 1px solid #eef2f6;
    border-radius: var(--lvca-radius-lg);
    padding: 12px 16px 11px 20px;
    box-shadow: var(--lvca-shadow-xs);
    transition: all var(--lvca-t) var(--lvca-ease);
    position: relative;
    overflow: hidden;
    height: 100%;
}
/* Acento vertical izquierdo: color semántico protagonista en el borde. */
.lvca-kpi-lite::after {
    content: "";
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 5px;
    background: var(--kpi-accent, var(--lvca-brand-azul));
}
.lvca-kpi-lite:hover {
    box-shadow: var(--lvca-shadow-sm);
    transform: translateY(-2px);
}
.lvca-kpi-lite .lvca-kpi-lite-head {
    display: flex; align-items: center; gap: 10px;
}
.lvca-kpi-lite .lvca-kpi-lite-icon {
    width: 40px; height: 40px;
    border-radius: 999px;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    background: var(--kpi-accent-bg, #e0f2fe);
    color: var(--kpi-accent, var(--lvca-brand-azul));
}
.lvca-kpi-lite .lvca-kpi-lite-icon .material-symbols-rounded { font-size: 22px; }
.lvca-kpi-lite .lvca-kpi-lite-label {
    font-size: 0.74rem;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    line-height: 1.3;
}
.lvca-kpi-lite .lvca-kpi-lite-value {
    font-size: 2.8rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.035em;
    margin-top: 8px;
    line-height: 1;
    font-variant-numeric: tabular-nums;
}
.lvca-kpi-lite .lvca-kpi-lite-foot {
    font-size: 0.76rem;
    color: #64748b;
    margin-top: 8px;
}
.lvca-kpi-lite.verde    { --kpi-accent: var(--lvca-acento-verde);    --kpi-accent-bg: #dcfce7; }
.lvca-kpi-lite.amarillo { --kpi-accent: var(--lvca-acento-amarillo); --kpi-accent-bg: #fef3c7; }
.lvca-kpi-lite.rojo     { --kpi-accent: var(--lvca-acento-rojo);     --kpi-accent-bg: #fee2e2; }
.lvca-kpi-lite.gris     { --kpi-accent: #94a3b8;                     --kpi-accent-bg: #f1f5f9; }
.lvca-kpi-lite.azul     { --kpi-accent: var(--lvca-brand-azul-light); --kpi-accent-bg: #e0f2fe; }
.lvca-kpi-lite.teal     { --kpi-accent: var(--lvca-acento-teal);     --kpi-accent-bg: #d4f1f2; }

/* ── Scrollbar custom (WebKit) — detalle de pulido en tablas largas ───── */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 999px;
    border: 2px solid transparent;
    background-clip: content-box;
}
::-webkit-scrollbar-thumb:hover { background-color: #94a3b8; }

/* ── Accesibilidad: respetar preferencia de movimiento reducido ───────── */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }
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
    <span class="lvca-footer-strong">Laboratorio de Vigilancia y Calidad del Agua (LVCA)</span>
    <span class="lvca-footer-sep">&middot;</span>
    Proyecto Especial Majes-Siguas &mdash; AUTODEMA
    <span class="lvca-footer-sep">&middot;</span>
    <span class="material-symbols-rounded"
        style="font-size:13px; vertical-align:-2px; margin-right:2px;">location_on</span>
    Arequipa, Perú
    <span class="lvca-footer-sep">&middot;</span>
    D.S. N° 004-2017-MINAM
    <span class="lvca-footer-sep">&middot;</span>
    <a href="https://www.gob.pe" target="_blank" rel="noopener" class="lvca-footer-link">gob.pe</a>
    <span class="lvca-footer-sep">&middot;</span>
    v1.0.0
</div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Responsividad + accesibilidad — bloque independiente para no tocar el
# _GLOBAL_CSS. Se inyecta después del global, así sus reglas (media queries
# y :focus-visible) ganan en orden de cascada cuando empatan en especificidad.
# ─────────────────────────────────────────────────────────────────────────────

_RESPONSIVE_A11Y_CSS = """<style>
/* ── Accesibilidad: foco visible para navegación por teclado (WCAG 2.4.7) ── */
a:focus-visible,
button:focus-visible,
[role="button"]:focus-visible,
.stButton > button:focus-visible,
[data-testid="stPageLink"] a:focus-visible,
[data-baseweb="input"] input:focus-visible,
[data-baseweb="select"]:focus-within,
textarea:focus-visible,
[data-baseweb="tab"]:focus-visible {
    outline: 2px solid var(--lvca-brand-azul-mid) !important;
    outline-offset: 2px !important;
    border-radius: 6px;
}
/* Sobre el nav azul oscuro, un anillo claro (teal) tiene mejor contraste. */
.st-key-lvca_top_nav [data-testid="stPageLink"] a:focus-visible {
    outline: 2px solid #5eead4 !important;
}
/* Contraste AA: subir levemente textos tenues sobre el nav oscuro. */
.lvca-brand-sub { color: rgba(255,255,255,0.80) !important; }
.lvca-user-rol  { color: rgba(255,255,255,0.72) !important; }

/* ── Respiración entre secciones ─────────────────────────────────────────── */
.lvca-section-header { margin-top: 0.9rem !important; }

/* ── Responsividad: tablet ───────────────────────────────────────────────── */
@media (max-width: 820px) {
    /* El subtítulo de marca ocupa demasiado: se oculta y deja sitio a los logos. */
    .lvca-brand-sub { display: none !important; }
    .lvca-brand-chip img { height: 22px; }
    /* Links de nav más compactos y con espacio para envolver. */
    .st-key-lvca_top_nav [data-testid="stPageLink"] a {
        padding: 6px 9px !important;
        font-size: 0.78rem !important;
    }
    /* El nav fijo crece al envolver los links → más colchón para el contenido. */
    [data-testid="stMainBlockContainer"]:has(.st-key-lvca_top_nav) {
        padding-top: 134px !important;
    }
    /* Banner de página más compacto. */
    .lvca-banner { padding: 16px 18px !important; }
    .lvca-banner h1 { font-size: 1.15rem !important; }
}

/* ── Responsividad: móvil ────────────────────────────────────────────────── */
@media (max-width: 560px) {
    /* Contadores del hero a ancho completo, uno por fila. */
    .lvca-stat { flex-basis: 100% !important; border-right: none !important; }
    .lvca-stat-num { font-size: 1.7rem; }
    .lvca-footer { font-size: 0.62rem; padding: 5px 10px; }
    [data-testid="stMainBlockContainer"]:has(.st-key-lvca_top_nav) {
        padding-top: 152px !important;
    }
}

/* Respeta a quienes prefieren menos movimiento. */
@media (prefers-reduced-motion: reduce) {
    * { animation-duration: 0.001ms !important; transition-duration: 0.001ms !important; }
}
</style>"""


# ─────────────────────────────────────────────────────────────────────────────
# Tema Plotly unificado ("lvca") + primitiva de tarjeta
# ─────────────────────────────────────────────────────────────────────────────

# Secuencia de colores de marca para series categóricas en gráficos.
LVCA_COLORWAY: list[str] = [
    COLORS["primary"],     # azul institucional
    COLORS["secondary"],   # teal
    COLORS["accent"],      # naranja
    COLORS["eca_cumple"],  # verde
    COLORS["eca_alerta"],  # ámbar
    COLORS["eca_excede"],  # rojo
    "#1565C0",             # azul medio
    "#7C3AED",             # violeta (categoría extra)
]

_PLOTLY_TEMPLATE_REGISTRADO = False


def register_plotly_template() -> None:
    """
    Registra (una sola vez) el template Plotly 'lvca' y lo fija como default.

    Look LVCA: fuente Inter, papel transparente (la figura vive dentro de la
    card blanca de [data-testid="stPlotlyChart"]), área de plot blanca, grilla
    gris-borde suave, ticks gris medio, colorway de marca y hover oscuro.

    Idempotente — bandera de módulo para no re-registrar en cada rerun. Falla
    silenciosa si Plotly no está disponible. Llamado desde aplicar_estilos().
    """
    global _PLOTLY_TEMPLATE_REGISTRADO
    if _PLOTLY_TEMPLATE_REGISTRADO:
        return
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except Exception:
        return

    _eje = dict(
        showgrid=True,
        gridcolor="#eef2f6",
        gridwidth=1,
        zeroline=False,
        linecolor="#e2e8f0",
        tickfont=dict(color="#64748b", size=12),
        title=dict(font=dict(color="#475569", size=12)),
    )
    pio.templates["lvca"] = go.layout.Template(
        layout=dict(
            font=dict(
                family="Inter, -apple-system, 'Segoe UI', Roboto, sans-serif",
                color="#1e293b", size=13,
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#ffffff",
            colorway=LVCA_COLORWAY,
            xaxis=_eje,
            yaxis=_eje,
            margin=dict(l=48, r=20, t=40, b=40),
            hoverlabel=dict(
                bgcolor="#0f172a",
                bordercolor="#0f172a",
                font=dict(family="Inter, sans-serif", color="#ffffff", size=12),
            ),
            legend=dict(font=dict(color="#475569", size=12), bgcolor="rgba(0,0,0,0)"),
            title=dict(font=dict(color="#0f172a", size=15)),
        )
    )
    pio.templates.default = "lvca"
    _PLOTLY_TEMPLATE_REGISTRADO = True


def eca_colorscale() -> list[list]:
    """Escala continua del semáforo ECA (verde→ámbar→rojo) para
    marker.colorscale de barras/heatmaps. Deriva de COLORS, sin hex literales."""
    return [
        [0.0, COLORS["eca_cumple"]],
        [0.5, COLORS["eca_alerta"]],
        [1.0, COLORS["eca_excede"]],
    ]


def apply_plotly_layout(
    fig,
    *,
    height: int | None = None,
    legend: bool = False,
    x_title: str | None = None,
    y_title: str | None = None,
    **layout,
):
    """
    Aplica el look LVCA a una figura Plotly existente y la devuelve.

    Usa el template 'lvca' (lo registra si hace falta), papel transparente (la
    card blanca de Streamlit ya da el fondo) y opcionalmente altura, leyenda y
    títulos de eje. Reemplaza los fig.update_layout(...) ad-hoc de las páginas.
    Cualquier kwarg extra de layout se reenvía a fig.update_layout().
    """
    register_plotly_template()
    base: dict = {"template": "lvca", "paper_bgcolor": "rgba(0,0,0,0)"}
    if height is not None:
        base["height"] = height
    base["showlegend"] = bool(legend)
    if x_title is not None:
        base["xaxis_title"] = x_title
    if y_title is not None:
        base["yaxis_title"] = y_title
    base.update(layout)
    try:
        fig.update_layout(**base)
    except Exception:
        pass
    return fig


def card(
    body_html: str,
    *,
    accent: str | None = None,
    padding: str | None = None,
    radius: str = "md",
    hover: bool = True,
    extra_class: str = "",
) -> str:
    """
    Devuelve el HTML de una tarjeta-superficie blanca tokenizada, con barra de
    acento izquierda opcional. Primitiva única que reemplaza el HTML de tarjeta
    escrito a mano (excedencias, tareas, informes, tiles de módulo).

    accent : clave de COLORS (p. ej. "eca_excede", "primary", "secondary") o un
             hex/var() literal; None → sin barra de acento.
    radius : "sm" | "md" | "lg" → --lvca-radius-*.
    padding: override CSS del padding; por defecto var(--lvca-space-5).
    hover  : activa el lift sutil en hover.

    Uso: st.markdown(card("<b>Hola</b>", accent="eca_excede"), unsafe_allow_html=True)
    """
    radius_map = {
        "sm": "var(--lvca-radius-sm)",
        "md": "var(--lvca-radius-md)",
        "lg": "var(--lvca-radius-lg)",
    }
    radius_var = radius_map.get(radius, radius)
    pad = padding or "var(--lvca-space-5)"
    styles = [
        "position:relative",
        "overflow:hidden",
        "background:var(--lvca-bg-card)",
        "border:1px solid var(--lvca-border-soft)",
        f"border-radius:{radius_var}",
        "box-shadow:var(--lvca-shadow-sm)",
        f"padding:{pad}",
    ]
    accent_html = ""
    if accent:
        color = COLORS.get(accent, accent)
        styles.append(f"padding-left:calc({pad} + 6px)")
        accent_html = (
            f'<span style="position:absolute; left:0; top:0; bottom:0; width:4px; '
            f'background:{color};"></span>'
        )
    hover_cls = " lvca-card-surface--hover" if hover else ""
    cls = f"lvca-card-surface{hover_cls}" + (f" {extra_class}" if extra_class else "")
    return (
        f'<div class="{cls}" style="{"; ".join(styles)};">'
        f'{accent_html}{body_html}</div>'
    )


def style_eca_dataframe(
    df,
    *,
    state_col: str | None = None,
    state_colors: dict | None = None,
    numeric_format: dict | None = None,
):
    """
    Aplica el look de plataforma a un DataFrame y devuelve un pandas Styler.
    Centraliza el coloreado de tablas para reemplazar los df.style.map() ad-hoc.

    state_col / state_colors: pinta la columna `state_col` como celda tintada
        estilo pill, usando state_colors = {valor_mostrado: {"bg", "fg"}}
        (consistente con los .lvca-pill-* y CAMPANA_ESTADO_COLORS).
    numeric_format: dict {columna: fmt} → Styler.format para dígitos alineados.

    Pensado para st.dataframe (preserva selección/orden, a diferencia de
    renderizar HTML). Si se necesita un pill real, usar estado_pill() en HTML.
    """
    styler = df.style
    if state_col and state_colors:
        def _estilo_estado(val):
            par = state_colors.get(val)
            if not par:
                return ""
            return (
                f"background-color:{par['bg']}; color:{par['fg']}; "
                f"text-align:center; font-weight:600; border-radius:4px;"
            )
        styler = styler.map(_estilo_estado, subset=[state_col])
    if numeric_format:
        styler = styler.format(numeric_format)
    return styler


def aplicar_estilos() -> None:
    """
    Inyecta el CSS global y la fuente Inter. Llamar al inicio de cada página.

    Usa el patrón canónico de Streamlit: dos llamadas separadas a
    st.markdown(unsafe_allow_html=True) — una para el <link> de Google Fonts
    y otra para el bloque <style>. Esto evita que el parser de markdown se
    confunda con múltiples elementos top-level mezclados.

    Además inyecta el footer institucional (position:fixed) que se muestra
    en todas las páginas. Como `position:fixed` saca el elemento del flow,
    el orden de inyección no importa. Registra también el template Plotly
    'lvca' para que cualquier gráfico posterior herede el look de marca.
    """
    register_plotly_template()
    st.markdown(_FONT_LINK, unsafe_allow_html=True)
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)
    st.markdown(_RESPONSIVE_A11Y_CSS, unsafe_allow_html=True)
    st.markdown(_FOOTER_HTML, unsafe_allow_html=True)


def page_header(titulo: str, subtitulo: str = "", ambito: str = "") -> None:
    """
    Encabezado de página — banner minimalista refinado (.lvca-banner).

    - Tarjeta blanca con título en tinta oscura a tamaño display
      (--lvca-fs-display) y filete vertical de acento azul→teal a la
      izquierda; sin bloque de color saturado de fondo.
    - Subtítulo opcional en gris tenue debajo del título.
    - Ámbito opcional: píldora a la derecha, equivalente al "UH 132" del
      SSDH. Solo lo usa el Geoportal por ahora; el resto de páginas lo
      dejan vacío.

    Compatibilidad: la firma vieja `page_header(titulo, subtitulo)` sigue
    funcionando — las 9 páginas que lo usan así quedan con el nuevo banner
    sin cambios adicionales.
    """
    ambito_html = (
        f'<div class="lvca-banner-ambito">'
        f'<span class="material-symbols-rounded" '
        f'style="font-size:18px; line-height:1;">map</span> {ambito}'
        f'</div>'
        if ambito else ""
    )
    sub_html = (
        f'<p class="lvca-banner-sub">{subtitulo}</p>'
        if subtitulo else ""
    )
    st.markdown(
        f"""
        <div class="lvca-banner">
            <div class="lvca-banner-body">
                <h1>{titulo}</h1>
                {sub_html}
            </div>
            {ambito_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Franja de contadores institucionales (estilo Observatorio del Agua — ANA)
# ─────────────────────────────────────────────────────────────────────────────

def stat_counters(items: list[dict], titulo: str = "") -> None:
    """
    Franja de estadísticas tipo "Observatorio del Agua" del SNIRH/ANA: una banda
    azul institucional con números grandes + label + ícono. Pensada para la
    landing, encima del grid de módulos.

    Cada item es un dict:
        {"valor": "1 234" | int, "label": "Muestras", "icon": "science",
         "suffix": "%" (opcional)}

    `icon` es el nombre de un Material Symbol (mismo set que el resto de la app).
    El CSS es autocontenido (inline) para no depender del orden de inyección.
    """
    if not items:
        return

    titulo_html = (
        f'<div class="lvca-stats-title">{titulo}</div>' if titulo else ""
    )

    cards = []
    for it in items:
        valor = it.get("valor", "—")
        suffix = it.get("suffix", "")
        icono = it.get("icon", "water_drop")
        label = it.get("label", "")
        cards.append(
            f'<div class="lvca-stat">'
            f'<span class="lvca-stat-ico material-symbols-rounded">{icono}</span>'
            f'<div class="lvca-stat-num">{valor}'
            f'<span class="lvca-stat-suffix">{suffix}</span></div>'
            f'<div class="lvca-stat-lbl">{label}</div>'
            f'</div>'
        )

    st.markdown(
        """
        <style>
        .lvca-stats-band {
            background: #0D47A1;
            border-radius: var(--lvca-radius-lg, 16px);
            padding: 10px 22px;
            margin: 4px 0 8px 0;
            box-shadow: var(--lvca-shadow-xs, 0 1px 2px rgba(15,23,42,0.05));
            position: relative;
            overflow: hidden;
        }
        .lvca-stats-title {
            color: rgba(255,255,255,0.78);
            font-size: 0.72rem; font-weight: 700;
            letter-spacing: 0.10em; text-transform: uppercase;
            margin-bottom: 10px;
        }
        .lvca-stats-row {
            display: flex; flex-wrap: wrap; gap: 8px;
            position: relative; z-index: 1;
        }
        .lvca-stat {
            flex: 1 1 140px; min-width: 130px;
            display: flex; flex-direction: column; align-items: center;
            text-align: center; padding: 6px 10px;
            border-right: 1px solid rgba(255,255,255,0.12);
            opacity: 0;
            animation: lvca-stat-in 0.55s cubic-bezier(0.22,1,0.36,1) forwards;
        }
        .lvca-stat:last-child { border-right: none; }
        /* Entrada escalonada (fade + slide-up) al cargar — efecto Observatorio.
           No es un count-up JS (Streamlit no ejecuta <script> inyectado), pero
           da sensación de dashboard "vivo" de forma fiable en todo navegador. */
        @keyframes lvca-stat-in {
            from { opacity: 0; transform: translateY(10px); }
            to   { opacity: 1; transform: translateY(0); }
        }
        .lvca-stat:nth-child(1) { animation-delay: 0.05s; }
        .lvca-stat:nth-child(2) { animation-delay: 0.13s; }
        .lvca-stat:nth-child(3) { animation-delay: 0.21s; }
        .lvca-stat:nth-child(4) { animation-delay: 0.29s; }
        .lvca-stat:nth-child(5) { animation-delay: 0.37s; }
        .lvca-stat:nth-child(6) { animation-delay: 0.45s; }
        .lvca-stat-num { transition: transform 0.2s var(--lvca-ease, ease); }
        .lvca-stat:hover .lvca-stat-num { transform: scale(1.06); }
        @media (prefers-reduced-motion: reduce) {
            .lvca-stat { animation: none; opacity: 1; }
        }
        .lvca-stat-ico {
            font-size: 28px !important; line-height: 1;
            color: #7FD4FF; margin-bottom: 10px;
        }
        .lvca-stat-num {
            color: #ffffff; font-weight: 800;
            font-size: 2.5rem; line-height: 1.02;
            letter-spacing: -0.03em;
            font-variant-numeric: tabular-nums;
        }
        .lvca-stat-suffix {
            font-size: 1.1rem; font-weight: 700;
            color: rgba(255,255,255,0.80); margin-left: 2px;
        }
        .lvca-stat-lbl {
            color: rgba(255,255,255,0.78);
            font-size: 0.74rem; font-weight: 500;
            margin-top: 6px; line-height: 1.25;
        }
        @media (max-width: 640px) {
            .lvca-stat { border-right: none; flex-basis: 45%; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="lvca-stats-band">{titulo_html}'
        f'<div class="lvca-stats-row">{"".join(cards)}</div></div>',
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
    background: linear-gradient(180deg, #0F3F78 0%, var(--lvca-nav-bg) 100%) !important;
    border-bottom: 2px solid rgba(45, 212, 191, 0.38);
    padding: 10px 1.5rem 6px 1.5rem;
    box-shadow: 0 2px 12px rgba(8, 42, 87, 0.28),
                inset 0 1px 0 rgba(255,255,255,0.08);
}

/* Ocultar el stHeader de Streamlit (la delgada barra nativa arriba)
   para que no choque con el top-nav fijo. */
[data-testid="stHeader"] {
    display: none !important;
}

/* Empujar el contenido de la página para que no quede oculto bajo el
   top-nav fijo. La altura depende del tamaño del label de usuario +
   altura de los page_links. 94px es un buffer ajustado (el nav mide ~83px);
   si el top-nav quedara más compacto/alto, ajustar aquí. */
[data-testid="stMainBlockContainer"]:has(.st-key-lvca_top_nav) {
    padding-top: 86px !important;
}
/* Línea 1: marca + usuario */
.lvca-brand {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 4px;
}
.lvca-brand-logo {
    width: 28px; height: 28px;
    border-radius: 8px;
    background: var(--lvca-brand-azul-mid);
    color: #ffffff;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}
.lvca-brand-logo .material-symbols-rounded { font-size: 18px; line-height: 1; }
/* Chip blanco que sostiene los logos institucionales reales, visible sobre
   el azul oscuro del nav independientemente de los colores del logo. */
.lvca-brand-chip {
    display: inline-flex; align-items: center; gap: 10px;
    background: #ffffff;
    border-radius: 10px;
    padding: 5px 10px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.22);
    flex-shrink: 0;
}
.lvca-brand-chip img {
    height: 26px; width: auto; display: block;
}
.lvca-brand-chip .lvca-brand-sep {
    width: 1px; height: 22px; background: #e2e8f0; flex-shrink: 0;
}
.lvca-brand-name {
    font-weight: 700; color: #ffffff; font-size: 1.15rem;
    letter-spacing: -0.015em;
}
.lvca-brand-sub {
    font-size: 0.76rem; color: rgba(255,255,255,0.65);
}
.lvca-user-block {
    display: flex; align-items: center; justify-content: flex-end;
    gap: 8px; font-size: 0.76rem; line-height: 1.3;
}
.lvca-user-text { text-align: right; }
.lvca-user-name { font-weight: 600; color: #ffffff; display: block; }
.lvca-user-rol  { color: rgba(255,255,255,0.55); text-transform: uppercase;
                  letter-spacing: 0.04em; font-size: 0.66rem; }
.lvca-user-avatar {
    width: 30px; height: 30px;
    border-radius: 999px;
    background: rgba(255,255,255,0.15);
    border: 1px solid rgba(255,255,255,0.25);
    color: #ffffff;
    font-weight: 700; font-size: 0.72rem;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    letter-spacing: 0.02em;
}

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
    color: rgba(255,255,255,0.80) !important;
    border-radius: 8px !important;
    border: 1px solid transparent !important;
    background: transparent !important;
    transition: all 0.15s ease !important;
    white-space: nowrap;
}
.st-key-lvca_top_nav [data-testid="stPageLink"] a p,
.st-key-lvca_top_nav [data-testid="stPageLink"] a span,
.st-key-lvca_top_nav [data-testid="stPageLink"] a div {
    color: inherit !important;
}
.st-key-lvca_top_nav [data-testid="stPageLink"] a:hover {
    background: rgba(255,255,255,0.10) !important;
    color: #ffffff !important;
}
/* Página activa: Streamlit marca el link actual con aria-current="page".
   Si la versión instalada no lo emite, la regla simplemente no aplica. */
.st-key-lvca_top_nav [data-testid="stPageLink"] a[aria-current="page"] {
    background: rgba(255,255,255,0.22) !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    box-shadow: inset 0 -3px 0 #2dd4bf;
}
.st-key-lvca_top_nav [data-testid="stPageLink"] a[aria-current="page"] p {
    font-weight: 700 !important;
}
/* Ícono de la página activa en teal de acento para reforzar el "estás aquí". */
.st-key-lvca_top_nav [data-testid="stPageLink"] a[aria-current="page"] .material-symbols-rounded {
    color: #5eead4 !important;
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
            lvca_uri = logo_data_uri("imagenes/logo_lvca.png", max_width=160)
            autodema_uri = logo_data_uri("imagenes/autodema_logo.png", max_width=160)
            if lvca_uri or autodema_uri:
                imgs = []
                if lvca_uri:
                    imgs.append(f'<img src="{lvca_uri}" alt="LVCA">')
                if lvca_uri and autodema_uri:
                    imgs.append('<span class="lvca-brand-sep"></span>')
                if autodema_uri:
                    imgs.append(f'<img src="{autodema_uri}" alt="AUTODEMA">')
                marca = f'<span class="lvca-brand-chip">{"".join(imgs)}</span>'
            else:
                marca = (
                    '<span class="lvca-brand-logo">'
                    '<span class="material-symbols-rounded">water_drop</span>'
                    '</span>'
                    '<span class="lvca-brand-name">LVCA</span>'
                )
            st.markdown(
                '<div class="lvca-brand">'
                f'{marca}'
                '<span class="lvca-brand-sub">Plataforma de Vigilancia y Calidad del Agua · AUTODEMA</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        with head_r:
            rol_label = sesion.rol.replace("_", " ").capitalize()
            iniciales = "".join(
                p[0] for p in (sesion.nombre_completo or "").split()[:2]
            ).upper() or "U"
            st.markdown(
                f'<div class="lvca-user-block">'
                f'<span class="lvca-user-text">'
                f'<span class="lvca-user-name">{sesion.nombre_completo}</span>'
                f'<span class="lvca-user-rol">{rol_label}</span>'
                f'</span>'
                f'<span class="lvca-user-avatar">{iniciales}</span>'
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
        items = "".join(f'<li title="{b}">{b}</li>' for b in bullets)
        bullets_html = f'<ul class="lvca-kpi-bullets">{items}</ul>'

    foot_html = (
        f'<div class="lvca-kpi-foot">{foot}</div>' if foot else ""
    )

    spark_html = ""
    if sparkline:
        # Tarjeta blanca: el trazo del sparkline va en el color semántico
        # de la variante, con un relleno tenue del mismo tono.
        _spark = {
            "azul":     ("#0D47A1", "rgba(13,71,161,0.10)"),
            "verde":    ("#047857", "rgba(4,120,87,0.10)"),
            "rojo":     ("#B91C1C", "rgba(185,28,28,0.10)"),
            "amarillo": ("#B45309", "rgba(180,83,9,0.10)"),
            "gris":     ("#64748b", "rgba(100,116,139,0.10)"),
        }.get(color, ("#0D47A1", "rgba(13,71,161,0.10)"))
        spark_svg = sparkline_svg(sparkline, stroke=_spark[0], fill=_spark[1])
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

# Chip de veredicto ECA (motor de cumplimiento, 5 estados) — fuente única
# compartida por 4_Resultados_Lab y 8_Informes. Las claves coinciden con los
# valores string de services.cumplimiento_service.EstadoECA (no se importa
# aquí para no acoplar components → services).
ECA_CHIP_STYLES: dict[str, dict] = {
    "cumple":                {"bg": "#dcfce7", "fg": "#166534", "label": "Cumple"},
    "excede":                {"bg": "#fee2e2", "fg": "#b91c1c", "label": "Excede"},
    "excede_excepcion_art6": {"bg": "#fef3c7", "fg": "#b45309", "label": "Art. 6"},
    "no_verificable":        {"bg": "#f1f5f9", "fg": "#475569", "label": "No verif."},
    "no_aplica":             {"bg": "#ede9fe", "fg": "#6d28d9", "label": "No aplica"},
}


def chip_eca_html(estado: str, motivo: str = "", label: str | None = None) -> str:
    """
    HTML de un chip pill compacto del veredicto ECA. El motivo se expone
    vía title= (tooltip nativo). `label` permite sobreescribir el texto
    (ej. "Excede +320%"); si se omite usa el label del estado.
    """
    info = ECA_CHIP_STYLES.get(estado)
    if info is None:
        return estado or ""
    motivo = (motivo or "").replace('"', "'")
    texto = label if label is not None else info["label"]
    return (
        f'<span title="{motivo}" style="display:inline-block;'
        f'background:{info["bg"]};color:{info["fg"]};'
        f'padding:2px 10px;border-radius:999px;text-align:center;'
        f'font-size:0.75rem;font-weight:600;white-space:nowrap;'
        f'line-height:1.5;">{texto}</span>'
    )


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
