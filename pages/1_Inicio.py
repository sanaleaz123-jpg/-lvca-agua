"""
pages/1_Inicio.py
Dashboard principal — Panel de control LVCA AUTODEMA.

Secciones:
    1. Tarjetas KPI: muestras, parámetros, excedencias, puntos monitoreados
    2. Tabla de excedencias activas (últimos 30 días)
    3. Gráficos Plotly: excedencias por parámetro y por punto
    4. Mapa Folium: 12 puntos de muestreo coloreados por estado ECA

Acceso mínimo: visitante (todos los roles).
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import (
    COLORS,
    aplicar_estilos,
    page_header,
    section_header,
    stat_counters,
    top_nav,
)
from services.cache import cached
from services.resultado_service import get_metricas_dashboard, get_puntos_con_estado

# Centro del mapa: Arequipa / cuenca Chili-Quilca
MAPA_CENTRO = [-15.75, -71.53]
MAPA_ZOOM   = 8

COLORES_PUNTO = {
    "excedencia": "red",
    "cumple":     "green",
    "sin_datos":  "gray",
}

ICONOS_PUNTO = {
    "excedencia": "exclamation-sign",
    "cumple":     "ok-sign",
    "sin_datos":  "minus-sign",
}


# ─────────────────────────────────────────────────────────────────────────────
# Sección hero — Franja de contadores institucionales (estilo Observatorio ANA)
# ─────────────────────────────────────────────────────────────────────────────

from pathlib import Path


def _contar_cuencas() -> int:
    """N° de cuencas con cartografía disponible (archivos GeoJSON)."""
    try:
        carpeta = Path(__file__).resolve().parents[1] / "static" / "geojson" / "cuencas"
        return len(list(carpeta.glob("*.geojson")))
    except Exception:
        return 0


def _render_hero_contadores(
    metricas: dict, puntos: list[dict], n_cuencas: int | None = None
) -> None:
    """
    Banda de estadísticas tipo Observatorio del Agua (ANA): cifras grandes de
    la vigilancia de calidad del agua, alimentadas con datos reales.
    """
    total_puntos = len(puntos)
    con_dato = [p for p in puntos if p.get("estado") in ("cumple", "excedencia")]
    cumplen  = [p for p in con_dato if p.get("estado") == "cumple"]
    pct_cumpl = round(len(cumplen) / len(con_dato) * 100) if con_dato else 0
    cuencas_val = n_cuencas if n_cuencas is not None else _contar_cuencas()

    items = [
        {"valor": f"{metricas['muestras_mes']:,}".replace(",", " "),
         "label": "Muestras (30 días)", "icon": "science"},
        {"valor": f"{metricas['parametros_mes']:,}".replace(",", " "),
         "label": "Parámetros analizados", "icon": "analytics"},
        {"valor": total_puntos,
         "label": "Puntos de monitoreo", "icon": "place"},
        {"valor": cuencas_val,
         "label": "Cuencas vigiladas", "icon": "water_drop"},
        {"valor": pct_cumpl, "suffix": "%",
         "label": "Cumplimiento ECA", "icon": "verified"},
    ]
    stat_counters(items, titulo="Observatorio de Calidad del Agua")


# ─────────────────────────────────────────────────────────────────────────────
# Sección 0 — Grilla de módulo-cards estilo SSDH-ANA
# ─────────────────────────────────────────────────────────────────────────────

def _render_module_grid() -> None:
    """
    Grilla 3×2 de navegación a los módulos principales (estilo SSDH-ANA).
    Cada card es un st.page_link con emoji icon, envuelto en un container
    con key para scopear el CSS sin afectar page_links de otras partes
    (ej. top_nav).
    """
    st.markdown(
        """
        <style>
        /* Card layout: ícono arriba en círculo pastel + label abajo. */
        .st-key-lvca_module_grid [data-testid="stPageLink"] a {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 16px !important;
            padding: 30px 18px 26px 18px !important;
            background: #ffffff !important;
            border: 1px solid #eef2f6 !important;
            border-radius: var(--lvca-radius-md, 12px) !important;
            text-align: center !important;
            min-height: 158px !important;
            box-shadow: var(--lvca-shadow-xs, 0 1px 2px rgba(15,23,42,0.05)) !important;
            transition: transform 0.18s cubic-bezier(0.4,0,0.2,1),
                        box-shadow 0.18s cubic-bezier(0.4,0,0.2,1),
                        border-color 0.18s cubic-bezier(0.4,0,0.2,1) !important;
            color: #1a1a1a !important;
            font-weight: 600 !important;
            font-size: 0.92rem !important;
            line-height: 1.3 !important;
            white-space: normal !important;
        }
        .st-key-lvca_module_grid [data-testid="stPageLink"] a:hover {
            transform: translateY(-1px) !important;
            box-shadow: var(--lvca-shadow-sm, 0 1px 3px rgba(15,23,42,0.06)) !important;
            border-color: #0D47A1 !important;
            color: #0D47A1 !important;
        }
        /* Primer span dentro del <a> = contenedor del icono (emoji). */
        .st-key-lvca_module_grid [data-testid="stPageLink"] a > span:first-child {
            width: 56px !important;
            height: 56px !important;
            background: rgba(13,71,161,0.08) !important;
            border-radius: 50% !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            font-size: 28px !important;
            line-height: 1 !important;
            flex-shrink: 0 !important;
            transition: background 0.15s ease !important;
        }
        .st-key-lvca_module_grid [data-testid="stPageLink"] a:hover > span:first-child {
            background: rgba(13,71,161,0.14) !important;
        }
        /* Evitar que el label se trunque con "..." en cards estrechas. */
        .st-key-lvca_module_grid [data-testid="stPageLink"] a p,
        .st-key-lvca_module_grid [data-testid="stPageLink"] a div,
        .st-key-lvca_module_grid [data-testid="stPageLink"] a > span:not(:first-child) {
            overflow: visible !important;
            text-overflow: clip !important;
            white-space: normal !important;
            line-height: 1.3 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container(key="lvca_module_grid"):
        r1 = st.columns(3, gap="medium")
        with r1[0]:
            st.page_link("pages/7_Geoportal.py",
                         label="Geoportal",
                         icon=":material/map:",
                         use_container_width=True)
        with r1[1]:
            st.page_link("pages/2_Campanas.py",
                         label="Campañas de Monitoreo",
                         icon=":material/event:",
                         use_container_width=True)
        with r1[2]:
            st.page_link("pages/3_Muestras_Campo.py",
                         label="Muestras de Campo",
                         icon=":material/science:",
                         use_container_width=True)

        r2 = st.columns(3, gap="medium")
        with r2[0]:
            st.page_link("pages/4_Resultados_Lab.py",
                         label="Resultados de Laboratorio",
                         icon=":material/biotech:",
                         use_container_width=True)
        with r2[1]:
            st.page_link("pages/8_Informes.py",
                         label="Informes",
                         icon=":material/description:",
                         use_container_width=True)
        with r2[2]:
            st.page_link("pages/10_Base_Datos.py",
                         label="Base de Datos",
                         icon=":material/database:",
                         use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sección 1 — Tarjetas KPI
# ─────────────────────────────────────────────────────────────────────────────

def _render_kpi_card_material(valor, label: str, color: str, icon: str) -> str:
    """
    KPI card estilo SSDH-ANA con Material icon (en vez de SVG custom del
    icon() registry). Mismo patrón visual que los KPI del Geoportal v2:
    borde inferior coloreado + ícono circular pastel + valor grande dark.
    """
    h = color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    halo = f"rgba({r},{g},{b},0.12)"
    return f"""
    <div class="lvca-kpi-lite" style="--kpi-accent:{color}; --kpi-accent-bg:{halo};">
        <div class="lvca-kpi-lite-head" style="justify-content:space-between;">
            <div class="lvca-kpi-lite-label" style="flex:1;">{label}</div>
            <div class="lvca-kpi-lite-icon">
                <span class="material-symbols-rounded">{icon}</span>
            </div>
        </div>
        <div class="lvca-kpi-lite-value">{valor}</div>
    </div>"""


def _render_kpis(metricas: dict) -> None:
    cards = [
        {"valor": metricas["muestras_mes"],
         "label": "Muestras (30 d)",
         "color": COLORS["secondary"], "icon": "science"},
        {"valor": metricas["parametros_mes"],
         "label": "Parámetros analizados",
         "color": "#00796B", "icon": "analytics"},
        {"valor": metricas["excedencias_activas"],
         "label": "Excedencias activas",
         "color": COLORS["eca_excede"], "icon": "warning"},
        {"valor": metricas["puntos_monitoreados"],
         "label": "Puntos monitoreados",
         "color": "#1565C0", "icon": "place"},
    ]
    cols = st.columns(4, gap="medium")
    for col, card in zip(cols, cards):
        with col:
            st.markdown(_render_kpi_card_material(**card), unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sección 2 — Tabla de excedencias
# ─────────────────────────────────────────────────────────────────────────────

def _format_excedencia_pct(e: dict) -> str:
    """Signo + porcentaje de excedencia respecto al límite ECA."""
    if e.get("lim_max") and e["lim_max"] > 0:
        return f"+{((e['valor'] / e['lim_max'] - 1) * 100):.1f}%"
    if e.get("lim_min") and e["lim_min"] > 0:
        return "−{:.1f}%".format((1 - e["valor"] / e["lim_min"]) * 100)
    return "—"


def _render_excedencia_card(e: dict) -> str:
    """Card individual para una excedencia, estilo SSDH-ANA."""
    pct = _format_excedencia_pct(e)
    valor = f"{e['valor']:.4g}" if isinstance(e.get("valor"), (int, float)) else str(e.get("valor", ""))
    limite = f"{e['lim_max']:.4g}" if e.get("lim_max") else (
        f"≥ {e['lim_min']:.4g}" if e.get("lim_min") else "—"
    )
    unidad = e.get("unidad", "") or ""
    return f"""
    <div style="background:#ffffff; border:1px solid #e8eaed;
         border-left:3px solid #C62828; border-radius:8px;
         padding:12px 16px; margin-bottom:10px;
         display:grid; grid-template-columns:52px 1fr auto;
         gap:14px; align-items:center;
         box-shadow:0 1px 2px rgba(15,23,42,0.04);">
        <div style="width:52px; height:52px; border-radius:50%;
             background:rgba(198,40,40,0.1);
             display:inline-flex; align-items:center; justify-content:center;">
            <span class="material-symbols-rounded"
                style="font-size:26px; color:#C62828; line-height:1;">warning</span>
        </div>
        <div style="min-width:0;">
            <div style="font-size:0.92rem; font-weight:600; color:#1a1a1a;
                 line-height:1.3; overflow:hidden; text-overflow:ellipsis;
                 white-space:nowrap;">{e.get('punto_nombre', '—')}</div>
            <div style="font-size:0.8rem; color:#475569; margin-top:3px;
                 line-height:1.4;">
                <b>{e.get('parametro_nombre', '—')}</b> =
                <b style="color:#C62828;">{valor}</b> {unidad}
                <span style="color:#94a3b8;">· ECA {e.get('eca_codigo', '—')}
                (máx {limite})</span>
            </div>
            <div style="font-size:0.72rem; color:#94a3b8; margin-top:4px;">
                {e.get('fecha', '—')}
            </div>
        </div>
        <div style="font-size:0.95rem; font-weight:700; color:#C62828;
             white-space:nowrap; letter-spacing:-0.01em;">{pct}</div>
    </div>"""


def _render_tabla_excedencias(excedencias: list[dict]) -> None:
    from components.ui_styles import inline_note
    section_header("Excedencias activas (últimos 30 días)", "alert")

    if not excedencias:
        inline_note(
            "Sin excedencias ECA en los últimos 30 días — todos los puntos cumplen.",
            tipo="success",
        )
        return

    total = len(excedencias)
    inline_note(
        f"<b>{total} resultado(s)</b> superan los ECA "
        f"D.S. N° 004-2017-MINAM en los últimos 30 días.",
        tipo="warn",
    )

    # Render primeras 15 como cards; el resto queda accesible desde Base de Datos.
    max_visibles = 15
    visibles = excedencias[:max_visibles]
    cards_html = "".join(_render_excedencia_card(e) for e in visibles)
    st.markdown(cards_html, unsafe_allow_html=True)

    if total > max_visibles:
        st.caption(
            f"Mostrando las primeras {max_visibles} de {total}. "
            "Ver todas en **Base de Datos**."
        )

    enav1, enav2, _sp = st.columns([1.3, 1.3, 3.4])
    with enav1:
        st.page_link("pages/10_Base_Datos.py",
                     label="Ver en Base de Datos",
                     icon=":material/database:")
    with enav2:
        st.page_link("pages/7_Geoportal.py",
                     label="Ver en Geoportal",
                     icon=":material/map:")


# ─────────────────────────────────────────────────────────────────────────────
# Sección 3 — Gráficos de excedencias
# ─────────────────────────────────────────────────────────────────────────────

def _render_grafico_excedencias(excedencias: list[dict]) -> None:
    section_header("Parámetros con más excedencias ECA", "chart")

    if not excedencias:
        st.info("No hay datos para graficar.")
        return

    conteo = Counter(e["parametro_nombre"] for e in excedencias)
    df_chart = (
        pd.DataFrame(conteo.items(), columns=["Parámetro", "Excedencias"])
        .sort_values("Excedencias", ascending=True)
        .tail(15)
    )

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df_chart["Excedencias"],
        y=df_chart["Parámetro"],
        orientation="h",
        marker=dict(
            color=df_chart["Excedencias"],
            colorscale=[[0, "#e8870e"], [0.5, "#c56d00"], [1, "#c62828"]],
        ),
        text=df_chart["Excedencias"],
        textposition="outside",
        textfont=dict(size=12, color="#333"),
        hovertemplate="<b>%{y}</b><br>Excedencias: %{x}<extra></extra>",
    ))

    fig.update_layout(
        showlegend=False,
        yaxis_title=None,
        xaxis_title="Cantidad de excedencias",
        height=max(350, len(df_chart) * 32 + 100),
        margin=dict(l=0, r=40, t=10, b=30),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#f0f0f0", showgrid=True),
        yaxis=dict(showgrid=False),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_excedencias_por_punto(excedencias: list[dict]) -> None:
    """Gráfico de barras horizontal: puntos con más excedencias."""
    section_header("Puntos con más excedencias", "chart")

    if not excedencias:
        st.info("No hay datos.")
        return

    conteo = Counter(e["punto_nombre"] for e in excedencias)
    df_chart = (
        pd.DataFrame(conteo.items(), columns=["Punto", "Excedencias"])
        .sort_values("Excedencias", ascending=True)
    )

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df_chart["Excedencias"],
        y=df_chart["Punto"],
        orientation="h",
        marker=dict(
            color=df_chart["Excedencias"],
            colorscale=[
                [0, COLORS["eca_cumple"]],
                [0.5, COLORS["eca_alerta"]],
                [1, COLORS["eca_excede"]],
            ],
        ),
        text=df_chart["Excedencias"],
        textposition="outside",
        textfont=dict(size=12, color="#333"),
        hovertemplate="<b>%{y}</b><br>Excedencias: %{x}<extra></extra>",
    ))

    fig.update_layout(
        showlegend=False,
        yaxis_title=None,
        xaxis_title="Cantidad de excedencias",
        height=max(300, len(df_chart) * 35 + 80),
        margin=dict(l=0, r=40, t=10, b=30),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#f0f0f0", showgrid=True),
        yaxis=dict(showgrid=False),
    )

    st.plotly_chart(fig, use_container_width=True)


def _render_donut_estado(puntos: list[dict]) -> None:
    """Donut chart con distribución de estados de los puntos."""
    estados = Counter(p.get("estado", "sin_datos") for p in puntos)
    etiquetas = {
        "excedencia": "Excedencia",
        "cumple": "Cumple ECA",
        "sin_datos": "Sin datos",
    }
    labels = [etiquetas.get(k, k) for k in estados.keys()]
    values = list(estados.values())
    colors = [{
        "excedencia": COLORS["eca_excede"],
        "cumple":     COLORS["eca_cumple"],
        "sin_datos":  COLORS["eca_sin_dato"],
    }.get(k, "#999") for k in estados.keys()]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.55,
        marker=dict(colors=colors),
        textinfo="label+value",
        textfont=dict(size=13),
        hovertemplate="<b>%{label}</b><br>%{value} punto(s)<br>%{percent}<extra></extra>",
    )])

    fig.update_layout(
        title=dict(text="<b>Estado ECA de puntos</b>", font_size=14),
        height=320,
        margin=dict(l=10, r=10, t=50, b=10),
        showlegend=False,
        annotations=[dict(
            text=f"<b>{len(puntos)}</b><br>puntos",
            x=0.5, y=0.5,
            font_size=16,
            showarrow=False,
        )],
    )

    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sección 4 — Mapa Folium de puntos de muestreo
# ─────────────────────────────────────────────────────────────────────────────

def _render_mapa(puntos: list[dict]) -> None:
    section_header("Mapa de puntos de muestreo", "map_pin")

    if not puntos:
        st.info("No hay puntos de muestreo registrados.")
        return

    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.warning(
            "Instala folium y streamlit-folium para ver el mapa:\n\n"
            "`pip install folium streamlit-folium`"
        )
        return

    m = folium.Map(
        location=MAPA_CENTRO,
        zoom_start=MAPA_ZOOM,
        tiles=None,
    )

    folium.TileLayer(tiles="OpenStreetMap", name="Calles").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satélite",
    ).add_to(m)

    # Leyenda estilo SSDH-ANA: sin borde, sombra más presente.
    leyenda = f"""
    <div style="position:fixed; bottom:24px; left:24px; z-index:1000;
         background:#ffffff; padding:12px 16px; border-radius:10px;
         font-size:12px; line-height:1.55; min-width:160px;
         box-shadow: 0 4px 16px rgba(15,23,42,0.14),
                     0 1px 3px rgba(15,23,42,0.08);
         font-family:sans-serif;">
      <div style="font-weight:700; color:#1a1a1a; font-size:13px;
           letter-spacing:-0.01em; margin-bottom:6px;">Estado ECA</div>
      <div style="color:#475569;">
        <span style="color:{COLORS['eca_excede']}; font-size:14px;">&#9679;</span> Excedencia activa<br>
        <span style="color:{COLORS['eca_cumple']}; font-size:14px;">&#9679;</span> Cumple ECA<br>
        <span style="color:{COLORS['eca_sin_dato']}; font-size:14px;">&#9679;</span> Sin datos recientes
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda))

    for p in puntos:
        lat = p.get("latitud")
        lon = p.get("longitud")
        if lat is None or lon is None:
            continue

        estado = p.get("estado", "sin_datos")
        color  = COLORES_PUNTO.get(estado, "gray")
        icono  = ICONOS_PUNTO.get(estado, "minus-sign")
        n_exc  = p.get("n_excedencias", 0)

        barra_color = {
            "excedencia": COLORS["eca_excede"],
            "cumple":     COLORS["eca_cumple"],
            "sin_datos":  COLORS["eca_sin_dato"],
        }.get(estado, COLORS["eca_sin_dato"])

        popup_html = (
            f"<div style='min-width:220px; font-family:sans-serif; font-size:13px;'>"
            f"<div style='background:{barra_color}; height:3px; border-radius:3px 3px 0 0; margin:-1px -1px 6px -1px;'></div>"
            f"<b>{p['codigo']}</b> — {p['nombre']}<br>"
            f"<span style='color:#666;'>Tipo: {(p.get('tipo') or '—').capitalize()} · "
            f"Cuenca: {p.get('cuenca', '—')}<br>"
            f"Altitud: {p.get('altitud_msnm', '—')} msnm</span><br>"
        )
        if estado == "excedencia":
            popup_html += f"<b style='color:red;'>{n_exc} excedencia(s)</b>"
        elif estado == "cumple":
            popup_html += "<b style='color:green;'>Cumple ECA</b>"
        else:
            popup_html += "<span style='color:gray;'>Sin datos recientes</span>"
        popup_html += "</div>"

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{p['codigo']} — {p['nombre']}",
            icon=folium.Icon(color=color, icon=icono, prefix="glyphicon"),
        ).add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    st_folium(m, use_container_width=True, height=520)


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("visitante")
def main() -> None:
    sesion = st.session_state.get("sesion")
    if not sesion:
        st.error("Sesión expirada. Inicia sesión nuevamente.")
        st.stop()

    aplicar_estilos()
    top_nav()
    page_header(
        "Panel de Control LVCA",
        f"AUTODEMA &middot; {sesion.nombre_completo}",
        ambito="Cuenca Chili-Quilca",
    )

    # ── Cargar puntos (siempre completos, para listar cuencas) ──────────────
    with st.spinner("Cargando métricas..."):
        try:
            puntos_all = get_puntos_con_estado(dias=30)
        except Exception as exc:
            st.error(f"Error al cargar datos del dashboard: {exc}")
            st.stop()

    # ── Selector de cuenca (vista "por cuenca", estilo Visor por Cuencas) ───
    cuencas_disp = sorted({
        (p.get("cuenca") or "").strip()
        for p in puntos_all if (p.get("cuenca") or "").strip()
    })
    fc_titulo, fc_sel = st.columns([3, 1.4])
    with fc_sel:
        sel_cuenca = st.selectbox(
            "Cuenca",
            ["Todas las cuencas"] + cuencas_disp,
            key="inicio_cuenca",
            label_visibility="collapsed",
        )
    cuenca_param = None if sel_cuenca == "Todas las cuencas" else sel_cuenca
    with fc_titulo:
        _ambito = sel_cuenca if cuenca_param else "Todas las cuencas"
        st.markdown(
            '<div style="display:flex; align-items:center; gap:8px; '
            'font-size:0.82rem; color:#64748b; font-weight:600; '
            'padding-top:6px;">'
            '<span class="material-symbols-rounded" '
            'style="font-size:18px; color:#0D47A1;">filter_alt</span>'
            f'Ámbito: <span style="color:#0D47A1;">{_ambito}</span></div>',
            unsafe_allow_html=True,
        )

    # ── Datos acotados a la cuenca seleccionada ─────────────────────────────
    with st.spinner("Cargando métricas..."):
        try:
            metricas = get_metricas_dashboard(dias=30, cuenca=cuenca_param)
        except Exception as exc:
            st.error(f"Error al cargar datos del dashboard: {exc}")
            st.stop()

    puntos = (
        puntos_all if cuenca_param is None
        else [p for p in puntos_all if (p.get("cuenca") or "").strip() == cuenca_param]
    )
    n_cuencas = 1 if cuenca_param else (len(cuencas_disp) or _contar_cuencas())
    excedencias = metricas["excedencias_lista"]

    # ── Hero: contadores institucionales (estilo Observatorio ANA) ──────────
    _render_hero_contadores(metricas, puntos, n_cuencas)

    # ── 0. Acceso a módulos (grilla SSDH-ANA) ───────────────────────────────
    _render_module_grid()
    st.divider()

    # ── 1. Tarjetas KPI ─────────────────────────────────────────────────────
    _render_kpis(metricas)
    st.divider()

    # ── 2. Excedencias: tabla ───────────────────────────────────────────────
    _render_tabla_excedencias(excedencias)
    st.divider()

    # ── 3. Gráficos de análisis ─────────────────────────────────────────────
    col_param, col_punto, col_donut = st.columns([2, 2, 1])

    with col_param:
        _render_grafico_excedencias(excedencias)

    with col_punto:
        _render_excedencias_por_punto(excedencias)

    with col_donut:
        _render_donut_estado(puntos)

    st.divider()

    # ── 4. Mapa de puntos ───────────────────────────────────────────────────
    _render_mapa(puntos)

    # ── Tareas pendientes accionables ───────────────────────────────────────
    st.divider()
    _render_tareas_pendientes()


@cached(ttl=120)
def _datos_tareas_pendientes() -> dict:
    """
    Consultas del bloque 'Tareas pendientes' agrupadas y cacheadas (TTL 2 min)
    para no golpear Supabase en cada rerun del dashboard. Está registrado en el
    grupo "operacional", así que cualquier mutación operacional (muestras,
    resultados, campañas) lo invalida y el bloque se refresca al instante.
    """
    from database.client import get_admin_client
    db = get_admin_client()
    datos: dict = {"camp_curso": [], "muestras_lab": [], "n_sin_validar": 0}

    try:
        datos["camp_curso"] = (
            db.table("campanas")
            .select("codigo, nombre, estado")
            .in_("estado", ["en_campo", "en_laboratorio"])
            .order("fecha_inicio", desc=True)
            .limit(50)
            .execute()
            .data or []
        )
    except Exception:
        pass

    try:
        datos["muestras_lab"] = (
            db.table("muestras")
            .select("id, codigo, estado")
            .in_("estado", ["en_laboratorio", "analizada"])
            .limit(200)
            .execute()
            .data or []
        )
    except Exception:
        pass

    try:
        sin_validar = (
            db.table("resultados_laboratorio")
            .select("id", count="exact")
            .eq("validado", False)
            .not_.is_("valor_numerico", "null")
            .limit(1)
            .execute()
        )
        datos["n_sin_validar"] = sin_validar.count or 0
    except Exception:
        pass

    return datos


def _render_tareas_pendientes() -> None:
    """
    Lista de tareas operacionales que el usuario debería atender ahora,
    en lugar de los genéricos botones de 'Acceso rápido'. Cada item lleva
    a la página exacta donde se resuelve.
    """
    from components.ui_styles import section_header, icon, COLORS

    section_header("Tareas pendientes", "list")

    datos = _datos_tareas_pendientes()
    items: list[dict] = []

    # 1. Campañas en curso (en_campo o en_laboratorio)
    camp_curso = datos["camp_curso"]
    if camp_curso:
        items.append({
            "icon": "play",
            "color": COLORS["primary"],
            "title": f"{len(camp_curso)} campaña(s) activa(s)",
            "detail": ", ".join(c["codigo"] for c in camp_curso[:3])
                      + (f" y {len(camp_curso)-3} más" if len(camp_curso) > 3 else ""),
            "page": "pages/2_Campanas.py",
            "cta": "Ver campañas",
        })

    # 2. Muestras analizadas/recibidas sin resultados completos
    muestras_lab = datos["muestras_lab"]
    if muestras_lab:
        items.append({
            "icon": "beaker",
            "color": COLORS["secondary"],
            "title": f"{len(muestras_lab)} muestra(s) en laboratorio",
            "detail": "Muestras recibidas o en análisis pendientes de cierre.",
            "page": "pages/4_Resultados_Lab.py",
            "cta": "Cargar resultados",
        })

    # 3. Resultados sin validar (si la migración 006 está aplicada)
    n_sin_val = datos["n_sin_validar"]
    if n_sin_val > 0:
        items.append({
            "icon": "shield",
            "color": COLORS["warning"],
            "title": f"{n_sin_val} resultado(s) sin validar",
            "detail": "Resultados ingresados pero no firmados por supervisor.",
            "page": "pages/4_Resultados_Lab.py",
            "cta": "Validar resultados",
        })

    if not items:
        st.info("No hay tareas pendientes — la operación está al día.")
        return

    cols = st.columns(min(3, len(items)))
    for i, item in enumerate(items):
        with cols[i % len(cols)]:
            # Card SSDH: ícono en círculo pastel a la izquierda, título +
            # detalle a la derecha, borde izquierdo del color de severidad.
            h = item["color"].lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            halo = f"rgba({r},{g},{b},0.12)"
            st.markdown(
                f"""<div style="background:#ffffff;
                     border:1px solid #e8eaed;
                     border-left:3px solid {item['color']};
                     border-radius:8px;
                     padding:14px 16px;
                     box-shadow:0 1px 2px rgba(15,23,42,0.04);
                     text-align:left;">
                    <div style="display:flex; align-items:flex-start;
                         gap:12px; margin-bottom:10px;">
                        <div style="width:38px; height:38px; border-radius:50%;
                             background:{halo}; flex-shrink:0;
                             display:inline-flex; align-items:center;
                             justify-content:center;">
                            <span style="color:{item['color']}; line-height:0;">
                                {icon(item['icon'], 20, item['color'])}
                            </span>
                        </div>
                        <div style="flex:1; min-width:0;">
                            <div style="font-weight:600; color:#1a1a1a;
                                 font-size:0.93rem; line-height:1.3;">
                                {item['title']}
                            </div>
                            <div style="font-size:0.78rem; color:#64748b;
                                 margin-top:4px; line-height:1.4;
                                 min-height:2.4em;">
                                {item['detail']}
                            </div>
                        </div>
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.page_link(item["page"], label=f"→ {item['cta']}")


main()
