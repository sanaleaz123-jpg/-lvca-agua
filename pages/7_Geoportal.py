"""
pages/7_Geoportal.py
Geoportal interactivo de monitoreo de calidad de agua — Cuenca Chili-Quilca.

Secciones:
    1. Dashboard resumen: métricas, gráfico de torta, panel de alertas
    2. Mapa Folium optimizado: CircleMarkers térmicos + HeatMap + polígonos
    3. Panel de detalle: gauge, tendencia, comparativa ECA, barras

Acceso mínimo: visitante (público).
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import aplicar_estilos, page_header, top_nav
from services.mapa_service import (
    get_comparativa_eca_punto,
    get_datos_mensuales_parametro,
    get_historial_punto,
    get_limite_eca_parametro,
    get_parametros_selector,
    get_puntos_geoportal,
    get_ultimo_valor_parametro_por_punto,
    get_ultimos_resultados_punto,
)
from services.resultado_service import get_campanas


# ─── Constantes ──────────────────────────────────────────────────────────────

MAPA_CENTRO = [-15.75, -71.53]
MAPA_ZOOM = 8

COLORES = {
    "excedencia": "#c62828",
    "cumple":     "#2e7d32",
    "sin_datos":  "#9e9e9e",
}

MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

# Categorías internas → display para tabs
_CAT_NORMALIZE: dict[str, str] = {
    "Parámetros de Campo": "Campo",
    "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)": "Fisicoquimico",
    "Parámetros Hidrobiológicos": "Hidrobiologico",
    "Campo": "Campo",
    "Fisicoquimico": "Fisicoquimico",
    "Hidrobiologico": "Hidrobiologico",
    "Metales": "Fisicoquimico",
}

_CODIGOS_CAMPO = {"P001", "P002", "P003", "P004", "P006", "P008", "P009"}


# ─── Helpers de color ────────────────────────────────────────────────────────

def _color_termico(p: dict) -> str:
    """Color hex según índice de cumplimiento ECA del punto."""
    ic = p.get("indice_cumplimiento")
    if ic is None:
        return "#808080"
    if ic == 1.0:
        return "#2e7d32"
    t = 1.0 - ic
    if t <= 0.5:
        r = int(40 + t * 2 * 200)
        g = int(167 - t * 2 * 40)
        b = int(69 - t * 2 * 60)
    else:
        r = int(220 + (t - 0.5) * 2 * 20)
        g = int(127 - (t - 0.5) * 2 * 110)
        b = int(9)
    return f"#{min(r,255):02x}{max(g,0):02x}{max(b,0):02x}"


def _color_estado(estado: str) -> str:
    return COLORES.get(estado, "#808080")


def _clasificar_cat(param: dict) -> str:
    """Clasifica un parámetro en categoría interna."""
    codigo = (param.get("codigo") or "").upper()
    if codigo in _CODIGOS_CAMPO:
        return "Campo"
    cat_raw = (param.get("categorias_parametro") or {}).get("nombre", "")
    return _CAT_NORMALIZE.get(cat_raw, cat_raw)


# ─────────────────────────────────────────────────────────────────────────────
# 1. DASHBOARD RESUMEN
# ─────────────────────────────────────────────────────────────────────────────

def _render_kpi_card(valor, label: str, color: str, icono_name: str) -> str:
    """
    Tarjeta KPI estilo SNIRH/ANA (POC rediseño 2026-04-21):
    - Borde izquierdo 4px del color identitario (en vez de franja superior).
    - Ícono SVG en círculo (border-radius 50%) sobre halo suave del color,
      anclado arriba a la derecha.
    - Card más compacta (min-height 92px vs 130px antes), border-radius 6px
      para look más institucional, sombra un poco más presente.
    - Label uppercase pequeño, valor prominente en peso 700.
    """
    from components.ui_styles import icon as _icon

    # rgba con alpha 0.12 para fondo de halo (más compatible que hex 8 dígitos)
    def _hex_to_rgba(h: str, alpha: float) -> str:
        h = h.lstrip("#")
        if len(h) != 6:
            return f"rgba(148,163,184,{alpha})"
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    halo_bg = _hex_to_rgba(color, 0.12)
    icono_svg = _icon(icono_name, size=18, color=color)

    return f"""
    <div style="background:#ffffff; border-radius:6px;
         padding:14px 16px;
         border:1px solid #f1f5f9;
         border-left:4px solid {color};
         box-shadow:0 2px 6px rgba(15,23,42,0.06);
         transition: transform 0.15s ease, box-shadow 0.15s ease;
         min-height:92px; display:flex; flex-direction:column;
         position:relative;">
        <div style="position:absolute; top:12px; right:12px;
             width:36px; height:36px; border-radius:50%;
             background:{halo_bg};
             display:inline-flex; align-items:center; justify-content:center;">
            {icono_svg}
        </div>
        <div style="font-size:0.62rem; color:#64748b;
             text-transform:uppercase; letter-spacing:0.05em;
             font-weight:600; margin-bottom:8px;
             padding-right:48px;">{label}</div>
        <div style="font-size:1.7rem; font-weight:700;
             line-height:1; color:{color}; letter-spacing:-0.02em;">
             {valor}
        </div>
    </div>"""


def _render_dashboard(puntos: list[dict]) -> None:
    """Metricas globales estilo ANA + torta + alertas."""
    n_total = len(puntos)
    n_exc = sum(1 for p in puntos if p["estado"] == "excedencia")
    n_ok = sum(1 for p in puntos if p["estado"] == "cumple")
    n_sin = sum(1 for p in puntos if p["estado"] == "sin_datos")

    indices = [p["indice_cumplimiento"] for p in puntos if p.get("indice_cumplimiento") is not None]
    ic_general = round(sum(indices) / len(indices) * 100, 1) if indices else 0

    # ── KPIs estilo SSDH/ANA: cada métrica con su color identitario,
    #     franja inferior y halo sutil en el ícono ─────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(_render_kpi_card(n_total, "Puntos monitoreados", "#0a9396", "map_pin"), unsafe_allow_html=True)
    with k2:
        st.markdown(_render_kpi_card(n_ok, "Cumplen ECA", "#1b6b35", "check"), unsafe_allow_html=True)
    with k3:
        st.markdown(_render_kpi_card(n_exc, "Con excedencias", "#c62828", "alert"), unsafe_allow_html=True)
    with k4:
        st.markdown(_render_kpi_card(n_sin, "Sin datos", "#94a3b8", "info"), unsafe_allow_html=True)
    with k5:
        color_ic = "#1b6b35" if ic_general >= 80 else "#e8870e" if ic_general >= 50 else "#c62828"
        st.markdown(_render_kpi_card(f"{ic_general}%", "Cumplimiento ECA", color_ic, "shield"), unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ── Barra de cumplimiento + torta ────────────────────────────────────
    col_barra, col_torta = st.columns([3, 2])

    with col_barra:
        color_barra = "#1b6b35" if ic_general >= 80 else "#e8870e" if ic_general >= 50 else "#c62828"
        st.markdown(
            f"""<div style="background:#ffffff; border-radius:12px; padding:18px 22px;
                 border:1px solid #f1f5f9; margin-top:4px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                <span style="font-size:0.7rem; color:#94a3b8; text-transform:uppercase;
                     letter-spacing:0.05em; font-weight:600;">Índice de cumplimiento general ECA</span>
                <span style="color:{color_barra}; font-weight:600; font-size:1.05rem; letter-spacing:-0.01em;">{ic_general}%</span>
            </div>
            <div style="background:#f1f5f9; border-radius:6px; height:8px; overflow:hidden;">
                <div style="background:{color_barra}; width:{ic_general}%; height:100%;
                     border-radius:6px; transition: width 0.5s;"></div>
            </div>
            <div style="font-size:0.72rem; color:#94a3b8; margin-top:10px;">
                D.S. N° 004-2017-MINAM
            </div>
            </div>""",
            unsafe_allow_html=True,
        )

        # Panel de alertas compacto
        criticos = sorted(
            [p for p in puntos if p["estado"] == "excedencia"],
            key=lambda x: x.get("n_excedencias", 0),
            reverse=True,
        )
        if criticos:
            from components.ui_styles import icon as _icon
            label_exp = f"{len(criticos)} punto(s) con excedencia"
            with st.expander(label_exp, expanded=False):
                for p in criticos[:5]:
                    exc_list = p.get("excedencias", [])
                    params_exc = ", ".join(
                        f"{e['parametro']}" for e in exc_list[:4]
                    )
                    if len(exc_list) > 4:
                        params_exc += f" (+{len(exc_list)-4})"
                    st.markdown(
                        f"""<div style="display:flex; align-items:center; padding:10px 14px; margin:4px 0;
                            background:#fef5f5; border-left:3px solid #c62828; border-radius:8px; font-size:0.82rem;">
                            <div style="flex:1;">
                                <b style="color:#0f172a;">{p['codigo']}</b>
                                <span style="color:#475569;"> — {p['nombre']}</span>
                                <span style="color:#94a3b8; margin-left:8px; font-size:0.76rem;">{params_exc}</span>
                            </div>
                            <span style="color:#c62828; font-weight:600; font-size:0.78rem;">{len(exc_list)}</span>
                        </div>""",
                        unsafe_allow_html=True,
                    )

    with col_torta:
        fig_torta = go.Figure(go.Pie(
            labels=["Cumple ECA", "Excedencia", "Sin datos"],
            values=[n_ok, n_exc, n_sin],
            marker_colors=["#2e7d32", "#c62828", "#9e9e9e"],
            hole=0.55,
            textinfo="value+percent",
            textfont_size=12,
            hovertemplate="%{label}: %{value} puntos (%{percent})<extra></extra>",
        ))
        fig_torta.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            height=220,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5, font_size=11),
            annotations=[dict(
                text=f"<b>{n_total}</b><br>puntos",
                x=0.5, y=0.5, font_size=14, showarrow=False,
            )],
        )
        st.plotly_chart(fig_torta, use_container_width=True, key="torta_general")


# ─────────────────────────────────────────────────────────────────────────────
# 2. MAPA OPTIMIZADO (Fix 1: z-index — markers always above heatmap)
# ─────────────────────────────────────────────────────────────────────────────

def _cargar_geojson_puntos() -> dict[str, dict]:
    """Carga los archivos GeoJSON de siluetas de cuerpos de agua (represas)."""
    import json
    from pathlib import Path

    geojson_dir = Path(__file__).parent.parent / "static" / "geojson"
    siluetas = {}
    if not geojson_dir.exists():
        return siluetas
    for f in geojson_dir.glob("*.geojson"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            codigo = data.get("properties", {}).get("punto", "")
            if codigo:
                siluetas[codigo] = data
        except Exception:
            pass
    return siluetas


def _cargar_geojson_cuencas() -> list[dict]:
    """
    Carga los polígonos de cuencas desde `static/geojson/cuencas/*.geojson`.
    Estilo SSDH/ANA: outline verde brillante sobre satélite para anclar
    visualmente al territorio.
    """
    import json
    from pathlib import Path

    cuencas_dir = Path(__file__).parent.parent / "static" / "geojson" / "cuencas"
    cuencas = []
    if not cuencas_dir.exists():
        return cuencas
    for f in cuencas_dir.glob("*.geojson"):
        try:
            with open(f, encoding="utf-8") as fh:
                cuencas.append({
                    "data": json.load(fh),
                    "nombre": f.stem.replace("_", " "),
                })
        except Exception:
            pass
    return cuencas


def _popup_html(p: dict) -> str:
    """Popup compacto para el marcador (Fix 2: campos corregidos)."""
    eca = p.get("ecas") or {}
    exc = p.get("excedencias", [])
    ic = p.get("indice_cumplimiento")
    n_eval = p.get("n_parametros_evaluados", 0)
    n_exc = p.get("n_excedencias", 0)
    color = _color_termico(p)

    pct_txt = f"{int(ic*100)}% ({n_eval-n_exc}/{n_eval})" if ic is not None else "Sin datos"

    # UTM coordinates (Zona 19S)
    utm_e = p.get("utm_este")
    utm_n = p.get("utm_norte")
    utm_txt = f"{utm_e:.0f} E / {utm_n:.0f} N" if utm_e and utm_n else "—"

    # Nivel del embalse
    nivel = p.get("nivel_agua")
    nivel_txt = f"{nivel}" if nivel else "—"

    html = (
        f"<div style='min-width:280px; font-family:sans-serif; font-size:12px;'>"
        f"<div style='background:{color}; height:4px; border-radius:4px 4px 0 0; margin:-1px -1px 6px -1px;'></div>"
        f"<b style='font-size:14px;'>{p['codigo']}</b>"
        f"<span style='color:#666; margin-left:6px;'>{p['nombre']}</span>"
        f"<table style='font-size:11px; color:#555; margin:4px 0;'>"
        f"<tr><td><b>Cuenca:</b></td><td>{p.get('cuenca','—')}</td></tr>"
        f"<tr><td><b>Sistema Hídrico:</b></td><td>{p.get('sistema_hidrico','—')}</td></tr>"
        f"<tr><td><b>Tipo:</b></td><td>{(p.get('tipo') or '—').capitalize()}</td></tr>"
        f"<tr><td><b>ECA:</b></td><td>{eca.get('codigo','—')}</td></tr>"
        f"<tr><td><b>UTM (19S):</b></td><td>{utm_txt}</td></tr>"
        f"<tr><td><b>Nivel embalse:</b></td><td>{nivel_txt}</td></tr>"
        f"<tr><td><b>Cumple:</b></td><td>{pct_txt}</td></tr>"
        f"</table>"
    )

    # ALL exceedances — no truncation, show parameter name + unit
    if exc:
        html += f"<hr style='margin:4px 0; border-color:#eee;'><span style='color:#dc3545; font-weight:bold;'>{len(exc)} excedencia(s):</span><br>"
        for e in exc:
            lim = e.get("lim_max")
            param_name = e.get("parametro", e.get("codigo", ""))
            unidad = e.get("unidad", "")
            lim_txt = f"{lim} {unidad}" if lim else "—"
            html += (
                f"<span style='font-size:11px;'>{param_name}: "
                f"<b style='color:red;'>{e['valor']}</b> / {lim_txt}</span><br>"
            )

    html += "</div>"
    return html


def _construir_mapa(puntos: list[dict], solo_excedencias: bool, mostrar_heatmap: bool):
    """Mapa Folium: HeatMap added FIRST (below), markers added LAST (above)."""
    import folium
    from folium.plugins import HeatMap, MiniMap

    m = folium.Map(
        location=MAPA_CENTRO,
        zoom_start=MAPA_ZOOM,
        tiles=None,
        prefer_canvas=True,
        max_zoom=22,         # permite hacer zoom muy cerca
        min_zoom=5,
    )

    # Tile layers — max_native_zoom evita que Leaflet quede en blanco al
    # pedir tiles más allá de lo que el proveedor sirve. max_zoom mantiene
    # el control de zoom disponible (sobreescala el último tile válido).
    folium.TileLayer(
        "OpenStreetMap",
        name="Calles",
        max_native_zoom=19, max_zoom=22,
    ).add_to(m)
    # Esri World Imagery: cobertura limitada en zonas altiplánicas remotas.
    # En la cuenca Chili-Quilca (Aguada Blanca, Pampa de Arrieros, etc.) no
    # hay imagen satelital de alta resolución más allá de zoom 17. Limitamos
    # max_native_zoom y max_zoom para que Leaflet repita el último tile válido
    # en lugar de pedir tiles inexistentes (que vienen como "Map data not yet
    # available").
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satélite",
        max_native_zoom=17, max_zoom=19,
    ).add_to(m)
    # Capa Topográfico removida — el satélite + calles cubren los casos de uso
    # y reduce la carga visual del control de capas.

    MiniMap(toggle_display=True, position="bottomright", zoom_level_offset=-5).add_to(m)

    # ── Polígonos de cuencas hidrográficas (estilo SSDH/ANA) ─────────────
    # Outline verde brillante, sin relleno, para anclar visualmente al
    # territorio sin tapar los detalles del mapa base.
    cuencas = _cargar_geojson_cuencas()
    if cuencas:
        fg_cuencas = folium.FeatureGroup(name="Cuencas hidrográficas", show=True)
        for cu in cuencas:
            folium.GeoJson(
                cu["data"],
                style_function=lambda feature: {
                    "color": "#22c55e",      # verde brillante (SSDH)
                    "weight": 2.2,
                    "fillColor": "#22c55e",
                    "fillOpacity": 0.04,      # apenas perceptible — solo enmarca
                    "dashArray": "0",
                },
                highlight_function=lambda feature: {
                    "color": "#15803d",
                    "weight": 3,
                    "fillOpacity": 0.10,
                },
                tooltip=f"Cuenca: {cu['nombre']}",
            ).add_to(fg_cuencas)
        fg_cuencas.add_to(m)

    # Polígonos de represas/lagunas
    siluetas = _cargar_geojson_puntos()
    fg_poligonos = folium.FeatureGroup(name="Represas/Lagunas", show=True)

    # Datos para HeatMap
    heat_data = []

    pts_filtrados = []
    for p in puntos:
        lat = p.get("latitud")
        lon = p.get("longitud")
        if lat is None or lon is None:
            continue
        estado = p.get("estado", "sin_datos")
        if solo_excedencias and estado != "excedencia":
            continue
        pts_filtrados.append(p)

        # Polígono GeoJSON si existe (represas)
        color_hex = _color_termico(p)
        geojson_data = siluetas.get(p["codigo"])
        if geojson_data:
            folium.GeoJson(
                geojson_data,
                style_function=lambda feature, c=color_hex: {
                    "fillColor": c,
                    "color": "#333",
                    "weight": 2,
                    "fillOpacity": 0.5,
                },
                highlight_function=lambda feature, c=color_hex: {
                    "fillColor": c,
                    "color": "#000",
                    "weight": 3,
                    "fillOpacity": 0.7,
                },
                tooltip=f"{p['codigo']} — {p['nombre']}",
                popup=folium.Popup(_popup_html(p), max_width=340, lazy=True),
            ).add_to(fg_poligonos)

        # HeatMap data
        ic = p.get("indice_cumplimiento")
        if ic is not None:
            weight = 1.0 - ic
            if weight > 0:
                heat_data.append([lat, lon, weight])

    fg_poligonos.add_to(m)

    # HeatMap antes que los marcadores para que los marcadores queden encima.
    # max_zoom controla hasta qué zoom el plugin re-genera la grilla; lo
    # subimos para que el calor siga visible al hacer zoom in. radius/blur
    # más conservadores para que se vea legible en cualquier zoom.
    if mostrar_heatmap and heat_data:
        fg_heat = folium.FeatureGroup(name="Mapa de calor ECA", show=True)
        HeatMap(
            heat_data,
            min_opacity=0.35,
            max_zoom=18,
            radius=22,
            blur=16,
            gradient={
                "0.0": "#2e7d32",
                "0.3": "#0a9396",
                "0.5": "#e8870e",
                "0.7": "#c56d00",
                "1.0": "#c62828",
            },
        ).add_to(fg_heat)
        fg_heat.add_to(m)

        # CRÍTICO: el canvas del heatmap intercepta el cursor y bloquea los
        # clicks a los marcadores debajo. Lo dejamos puramente visual con
        # pointer-events: none. Solo afecta al canvas del plugin (clase
        # 'leaflet-heatmap-layer'), no al canvas de los CircleMarker que
        # vive en otro pane (.leaflet-marker-pane / overlayPane SVG).
        m.get_root().html.add_child(folium.Element(
            '<style>'
            'canvas.leaflet-heatmap-layer{pointer-events:none !important;}'
            '</style>'
        ))

    # Capa de marcadores — added LAST so they are on top of heatmap
    fg_puntos = folium.FeatureGroup(name="Puntos de monitoreo", show=True)
    for p in pts_filtrados:
        lat = p["latitud"]
        lon = p["longitud"]
        color_hex = _color_termico(p)
        estado = p.get("estado", "sin_datos")
        popup_html = _popup_html(p)
        n_eval = p.get("n_parametros_evaluados", 0)
        radius = max(6, min(14, 6 + n_eval * 0.5))

        folium.CircleMarker(
            location=[lat, lon],
            radius=radius,
            color="#333",
            weight=1.5,
            fill=True,
            fill_color=color_hex,
            fill_opacity=0.85,
            tooltip=f"{p['codigo']} — {p['nombre']} ({estado.replace('_',' ')})",
            popup=folium.Popup(popup_html, max_width=340, lazy=True),
        ).add_to(fg_puntos)

    fg_puntos.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Leyenda
    leyenda_html = """
    <div style="position:fixed; bottom:30px; left:30px; z-index:1000;
         background:white; padding:10px 14px; border-radius:8px;
         border:1px solid #ccc; font-size:11px; line-height:1.7;
         box-shadow:0 2px 8px rgba(0,0,0,0.15); min-width:180px;">
      <b style="font-size:12px;">Estado ECA</b><br>
      <span style="font-size:9px; color:#666;">D.S. N° 004-2017-MINAM</span>
      <div style="margin:6px 0;">
        <span style="color:#2e7d32; font-size:14px;">&#9679;</span> Cumple ECA<br>
        <span style="color:#0a9396; font-size:14px;">&#9679;</span> Excedencia leve<br>
        <span style="color:#e8870e; font-size:14px;">&#9679;</span> Excedencia media<br>
        <span style="color:#c62828; font-size:14px;">&#9679;</span> Excedencia alta<br>
        <span style="color:#9e9e9e; font-size:14px;">&#9679;</span> Sin datos
      </div>
      <div style="font-size:9px; color:#999; border-top:1px solid #eee; padding-top:3px;">
        Radio = N° parámetros evaluados
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda_html))

    return m


# ─────────────────────────────────────────────────────────────────────────────
# 3. GAUGE DE CUMPLIMIENTO POR PUNTO
# ─────────────────────────────────────────────────────────────────────────────

def _render_gauge(punto: dict) -> None:
    """Indicador de cumplimiento ECA — bullet limpio, sin delta engañoso."""
    ic = punto.get("indice_cumplimiento")
    if ic is None:
        st.info("Sin datos suficientes para evaluar el cumplimiento ECA.")
        return

    pct = round(ic * 100, 1)
    n_eval = punto.get("n_parametros_evaluados", 0)
    n_exc = punto.get("n_excedencias", 0)
    n_ok = max(n_eval - n_exc, 0)

    color_principal = "#2e7d32" if pct >= 80 else "#e8870e" if pct >= 50 else "#c62828"
    color_fondo = "#e8f5e9" if pct >= 80 else "#fef3e2" if pct >= 50 else "#fce4e4"

    # Bullet horizontal: más compacto y legible que el gauge circular
    fig = go.Figure(go.Indicator(
        mode="number+gauge",
        value=pct,
        number={"suffix": "%", "font": {"size": 30, "color": color_principal}},
        gauge={
            "shape": "bullet",
            "axis": {"range": [0, 100], "tickwidth": 1, "ticksuffix": "%"},
            "bar": {"color": color_principal, "thickness": 0.65},
            "bgcolor": color_fondo,
            "borderwidth": 0,
            "steps": [
                {"range": [0, 50],  "color": "#fde8e8"},
                {"range": [50, 80], "color": "#fff4e0"},
                {"range": [80, 100], "color": "#e8f5e9"},
            ],
            "threshold": {
                "line": {"color": "#1e293b", "width": 3},
                "thickness": 0.85,
                "value": 80,
            },
        },
        domain={"x": [0.18, 1], "y": [0.15, 0.85]},
        title={"text": "<b>Cumplimiento ECA</b>",
               "font": {"size": 13, "color": "#1e293b"}},
    ))
    fig.update_layout(
        height=130,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Detalle bajo el bullet
    sub_a, sub_b, sub_c = st.columns(3)
    sub_a.metric("Parámetros evaluados", n_eval)
    sub_b.metric("Cumplen ECA", n_ok, delta=None)
    sub_c.metric("Excedencias", n_exc, delta=None,
                 delta_color="inverse")


# ─────────────────────────────────────────────────────────────────────────────
# 4. GRÁFICO DE TENDENCIA TEMPORAL (Fix 4: bar chart + subtitle)
# ─────────────────────────────────────────────────────────────────────────────

def _render_tendencia(punto: dict, parametro: dict, campana_label: str, cat: str = "") -> None:
    historial = get_historial_punto(punto["id"], parametro["id"])
    if not historial:
        st.info(f"Sin datos de **{parametro['nombre']}** para este punto.")
        return

    df = pd.DataFrame(historial)
    df["fecha"] = pd.to_datetime(df["fecha"])

    lim = get_limite_eca_parametro(punto["id"], parametro["id"])
    lim_max = lim.get("valor_maximo")
    lim_min = lim.get("valor_minimo")
    eca_cod = lim.get("eca_codigo", "")

    colores = []
    for v in df["valor"]:
        excede = (lim_max is not None and v > lim_max) or (lim_min is not None and v < lim_min)
        colores.append("#dc3545" if excede else "#28a745")

    unidad = (parametro.get("unidades_medida") or {}).get("simbolo", "")
    y_label = f"{parametro['nombre']} ({unidad})" if unidad else parametro["nombre"]

    fig = go.Figure()

    # Zonas ECA sombreadas
    if lim_max is not None and lim_min is not None:
        fig.add_hrect(y0=lim_min, y1=lim_max, fillcolor="rgba(40,167,69,0.08)", line_width=0,
                      annotation_text=f"Rango ECA {eca_cod}", annotation_position="top right",
                      annotation_font_color="green", annotation_font_size=10)
    elif lim_max is not None:
        y_top = max(df["valor"].max(), lim_max) * 1.3
        fig.add_hrect(y0=lim_max, y1=y_top, fillcolor="rgba(220,53,69,0.07)", line_width=0)
        y_bot = min(df["valor"].min(), 0) * 0.9 if df["valor"].min() < 0 else 0
        fig.add_hrect(y0=y_bot, y1=lim_max, fillcolor="rgba(40,167,69,0.05)", line_width=0)
    elif lim_min is not None:
        y_bot = min(df["valor"].min(), lim_min) * 0.7
        fig.add_hrect(y0=y_bot, y1=lim_min, fillcolor="rgba(220,53,69,0.07)", line_width=0)

    # Fix 4: vertical bar chart instead of scatter/point
    fig.add_trace(go.Bar(
        x=df["fecha"], y=df["valor"],
        name=parametro["nombre"],
        marker_color=colores,
        text=[f"{v:.4g}" for v in df["valor"]],
        textposition="outside",
        textfont_size=9,
        hovertemplate=f"<b>%{{x|%d/%m/%Y}}</b><br>{parametro['nombre']}: %{{y:.4g}}<extra></extra>",
    ))

    if lim_max is not None:
        fig.add_hline(y=lim_max, line_dash="dash", line_color="red", line_width=2,
                      annotation_text=f"Máx ECA: {lim_max}", annotation_position="top left",
                      annotation_font_color="red", annotation_font_size=11)
    if lim_min is not None:
        fig.add_hline(y=lim_min, line_dash="dash", line_color="orange", line_width=2,
                      annotation_text=f"Mín ECA: {lim_min}", annotation_position="bottom left",
                      annotation_font_color="orange", annotation_font_size=11)

    subtitle = f"{punto['codigo']} — {punto['nombre']} · ECA: {eca_cod}"
    if campana_label and campana_label != "Todas":
        subtitle += f" · Campaña: {campana_label}"

    fig.update_layout(
        title=dict(
            text=f"<b>{parametro['codigo']} — {parametro['nombre']}</b><br>"
                 f"<span style='font-size:12px; color:#666;'>{subtitle}</span>",
            font_size=15,
        ),
        xaxis_title="Fecha", yaxis_title=y_label,
        height=400, margin=dict(l=20, r=20, t=80, b=40),
        hovermode="x unified", plot_bgcolor="white",
        xaxis=dict(gridcolor="#f0f0f0", showgrid=True),
        yaxis=dict(gridcolor="#f0f0f0", showgrid=True, zeroline=True, zerolinecolor="#ddd"),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"tend_{cat}")


# ─────────────────────────────────────────────────────────────────────────────
# 5. TABLA COMPARATIVA ECA POR PARÁMETRO (reemplaza radar)
# ─────────────────────────────────────────────────────────────────────────────

# _render_tabla_eca_parametros() se eliminó — su función la cumple ahora
# _render_comparativa_eca_filtered() en el tab "Estado ECA".


# Nota: la antigua _render_comparativa_eca() se eliminó. La versión activa es
# _render_comparativa_eca_filtered() — más abajo, llamada desde tab_eca.


# ─────────────────────────────────────────────────────────────────────────────
# 7. BARRAS COMPARATIVAS: un parámetro en TODOS los puntos
# ─────────────────────────────────────────────────────────────────────────────

def _render_barras_comparativa_puntos(
    puntos: list[dict], parametro: dict,
    fecha_inicio: str, fecha_fin: str,
    campana_label: str,
    cat: str = "",
) -> None:
    """
    Compara un parámetro entre todos los puntos en barras horizontales.

    Una sola query agrupada (get_ultimo_valor_parametro_por_punto) reemplaza
    el patrón anterior N+1 (get_comparativa_eca_punto por cada punto).
    """
    ultimos = get_ultimo_valor_parametro_por_punto(
        parametro["id"], fecha_inicio, fecha_fin,
    )
    db_data = []
    for p in puntos:
        info = ultimos.get(p["id"])
        if not info or info.get("valor") is None:
            continue
        db_data.append({
            "punto":  p.get("codigo", ""),
            "nombre": p.get("nombre", ""),
            "valor":  info["valor"],
            "lim_max": info.get("lim_max"),
            "lim_min": info.get("lim_min"),
            "estado": info.get("estado"),
        })

    if not db_data:
        st.info(
            f"Sin datos recientes de {parametro['nombre']} en los puntos monitoreados."
        )
        return

    df = pd.DataFrame(db_data).sort_values("valor", ascending=True)
    colores = ["#c62828" if r["estado"] == "excede" else "#1b6b35" for _, r in df.iterrows()]

    unidad = (parametro.get("unidades_medida") or {}).get("simbolo", "")
    x_label = f"{parametro['nombre']} ({unidad})" if unidad else parametro["nombre"]

    scope = "Último valor por punto"
    if campana_label and campana_label != "Todas":
        scope += f" · Campaña: {campana_label}"

    fig = go.Figure(go.Bar(
        y=df["punto"], x=df["valor"],
        orientation="h",
        marker_color=colores,
        text=[f"{v:.3g}" for v in df["valor"]],
        textposition="outside", textfont_size=10,
        customdata=df[["nombre"]].values,
        hovertemplate="<b>%{y}</b> — %{customdata[0]}<br>Valor: %{x:.4g}<extra></extra>",
    ))

    lim_max = db_data[0].get("lim_max")
    lim_min = db_data[0].get("lim_min")
    if lim_max is not None:
        fig.add_vline(
            x=lim_max, line_dash="dash", line_color="#c62828", line_width=2,
            annotation_text=f"ECA máx: {lim_max}",
            annotation_position="top right", annotation_font_color="#c62828",
        )
    if lim_min is not None:
        fig.add_vline(
            x=lim_min, line_dash="dash", line_color="#e8870e", line_width=2,
            annotation_text=f"ECA mín: {lim_min}",
            annotation_position="bottom right", annotation_font_color="#e8870e",
        )

    fig.update_layout(
        title=dict(
            text=f"<b>{parametro['nombre']}</b><br>"
                 f"<span style='font-size:12px; color:#64748b;'>{scope}</span>",
            x=0.02, xanchor="left",
        ),
        xaxis_title=x_label,
        height=max(280, len(df) * 32 + 100),
        margin=dict(l=80, r=40, t=70, b=40),
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#f1f5f9", autorange="reversed"),
        xaxis=dict(gridcolor="#f1f5f9", zerolinecolor="#e2e8f0"),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"barras_comp_{cat}")


# ─────────────────────────────────────────────────────────────────────────────
# 8. BARRAS MENSUALES
# ─────────────────────────────────────────────────────────────────────────────

def _render_barras_mensuales(
    punto: dict, parametro: dict, anio: int,
    limite_eca: dict | None = None,
    campana_label: str = "",
    cat: str = "",
) -> None:
    """
    Comportamiento mensual del parámetro EN EL PUNTO seleccionado.
    Antes mostraba todos los puntos a la vez — ahora se ciñe al punto activo
    para que coincida con el subtítulo y sea interpretable.
    """
    datos = get_datos_mensuales_parametro(parametro["id"], anio, punto_id=punto["id"])
    if not datos:
        st.info(f"Sin datos de {parametro['nombre']} para {anio} en este punto.")
        return

    df = pd.DataFrame(datos)
    # Promedio por mes (puede haber múltiples campañas en un mismo mes)
    df_agg = df.groupby("mes", as_index=False)["valor"].mean()
    valores_por_mes = {int(r["mes"]): r["valor"] for _, r in df_agg.iterrows()}
    valores = [valores_por_mes.get(m) for m in range(1, 13)]

    color_barra = "#1b6b35"
    fig = go.Figure(go.Bar(
        x=MESES, y=valores,
        marker_color=color_barra,
        text=[f"{v:.3g}" if v is not None else "" for v in valores],
        textposition="outside", textfont_size=10,
        hovertemplate="<b>%{x}</b><br>Valor: %{y:.4g}<extra></extra>",
    ))

    if limite_eca:
        lim_max = limite_eca.get("valor_maximo")
        lim_min = limite_eca.get("valor_minimo")
        if lim_max is not None:
            fig.add_hline(y=lim_max, line_dash="dash", line_color="#c62828", line_width=2,
                          annotation_text=f"ECA máx: {lim_max}", annotation_position="top right",
                          annotation_font_color="#c62828")
        if lim_min is not None:
            fig.add_hline(y=lim_min, line_dash="dash", line_color="#e8870e", line_width=2,
                          annotation_text=f"ECA mín: {lim_min}", annotation_position="bottom right",
                          annotation_font_color="#e8870e")

    unidad = (parametro.get("unidades_medida") or {}).get("simbolo", "")
    y_label = f"{parametro['nombre']} ({unidad})" if unidad else parametro["nombre"]

    subtitle = f"{punto['codigo']} — {punto['nombre']}"
    if campana_label and campana_label != "Todas":
        subtitle += f" · Campaña: {campana_label}"

    fig.update_layout(
        title=dict(
            text=f"<b>{parametro.get('nombre', '')} — Promedio mensual {anio}</b><br>"
                 f"<span style='font-size:12px; color:#64748b;'>{subtitle}</span>",
            x=0.02, xanchor="left",
        ),
        xaxis_title="", yaxis_title=y_label,
        height=380, margin=dict(b=40, t=70, l=60, r=30),
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#f1f5f9", zerolinecolor="#e2e8f0"),
        xaxis=dict(showgrid=False),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, key=f"barras_mens_{cat}")


# ─────────────────────────────────────────────────────────────────────────────
# 9. ÚLTIMOS RESULTADOS
# ─────────────────────────────────────────────────────────────────────────────

def _render_ultimos_resultados(punto: dict, cat: str = "") -> None:
    resultados = get_ultimos_resultados_punto(punto["id"], limite=15)
    if not resultados:
        st.info("Sin resultados recientes para este punto.")
        return

    df = pd.DataFrame(resultados)
    df = df.drop(columns=["codigo"], errors="ignore")
    df.columns = ["Fecha", "Muestra", "Parámetro", "Valor", "Unidad"]
    st.dataframe(df, use_container_width=True, hide_index=True,
                 column_config={"Valor": st.column_config.NumberColumn(format="%.4g")},
                 key=f"ultimos_res_{cat}")


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("visitante")
def main() -> None:
    aplicar_estilos()
    top_nav()
    page_header("Geoportal", "Monitoreo de Calidad de Agua — Sistemas Chili Regulado y Colca Regulado · AUTODEMA")

    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.error("Instala: `pip install folium streamlit-folium`")
        st.stop()

    # ── Barra de filtros (en el área principal, no en sidebar) ──────────
    from components.ui_styles import filter_bar_open, filter_bar_close
    filter_bar_open()
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 2, 2])
    with fc1:
        fecha_inicio = st.date_input(
            "Desde", value=date.today() - timedelta(days=90), key="geo_desde",
        )
    with fc2:
        fecha_fin = st.date_input(
            "Hasta", value=date.today(), key="geo_hasta",
        )
    with fc3:
        campanas = get_campanas()
        opciones_camp = {"Todas": None}
        opciones_camp.update({f"{c['codigo']} — {c['nombre']}": c["id"] for c in campanas})
        sel_camp = st.selectbox("Campaña", list(opciones_camp.keys()), key="geo_camp")
        campana_id = opciones_camp[sel_camp]
    with fc4:
        opt_c1, opt_c2 = st.columns(2)
        with opt_c1:
            solo_exc = st.checkbox("Solo excedencias", key="geo_solo_exc")
        with opt_c2:
            mostrar_heatmap = st.checkbox("Mapa de calor", value=True, key="geo_heatmap")
    filter_bar_close()

    # ── Cargar datos ────────────────────────────────────────────────────
    with st.spinner("Cargando datos..."):
        try:
            puntos = get_puntos_geoportal(str(fecha_inicio), str(fecha_fin), campana_id)
        except Exception as exc:
            st.error(f"Error al cargar puntos: {exc}")
            st.stop()

    puntos_con_coords = [p for p in puntos if p.get("latitud") and p.get("longitud")]

    if not puntos_con_coords:
        st.warning("No hay puntos con coordenadas disponibles para la campaña seleccionada.")
        st.stop()

    # ── Selectores de punto y parámetro (también en el main area, arriba
    #     del panel de análisis para que estén siempre visibles) ──────────
    opciones_punto = {f"{p['codigo']} — {p['nombre']}": p for p in puntos_con_coords}
    parametros = get_parametros_selector()
    opciones_param = {f"{pr['codigo']} — {pr['nombre']}": pr for pr in parametros}
    # Se renderizan más abajo junto al panel de detalle para mantener el flujo:
    # Dashboard → Mapa → (aquí) Selectores + Detalle + Análisis

    # ── 1. Dashboard resumen ────────────────────────────────────────────
    _render_dashboard(puntos_con_coords)

    st.divider()

    # ── 2. Mapa ─────────────────────────────────────────────────────────
    mapa = _construir_mapa(puntos_con_coords, solo_exc, mostrar_heatmap)
    map_data = st_folium(mapa, use_container_width=True, height=520, returned_objects=["last_object_clicked"])
    st.caption(
        "Para zoom muy cerrado se recomienda la capa **Calles** — el satélite "
        "Esri no tiene imágenes de alta resolución en zonas altiplánicas "
        "remotas de la cuenca alta del Chili."
    )

    # Click en el mapa → actualizar la selección persistente del selectbox
    if map_data and map_data.get("last_object_clicked"):
        clicked = map_data["last_object_clicked"]
        clat, clon = clicked.get("lat"), clicked.get("lng")
        if clat and clon:
            min_dist = float("inf")
            closest_label = None
            for label, p in opciones_punto.items():
                dist = (p["latitud"] - clat) ** 2 + (p["longitud"] - clon) ** 2
                if dist < min_dist:
                    min_dist = dist
                    closest_label = label
            current = st.session_state.get("geo_punto")
            if closest_label and min_dist < 0.01 and closest_label != current:
                st.session_state["geo_punto"] = closest_label
                st.rerun()

    # ── 3. Selectores de punto y parámetro ──────────────────────────────
    st.divider()
    sel_c1, sel_c2 = st.columns(2)
    with sel_c1:
        sel_punto_label = st.selectbox(
            "Punto de muestreo a analizar",
            list(opciones_punto.keys()),
            key="geo_punto",
            help="Click en el mapa también cambia esta selección.",
        )
    with sel_c2:
        sel_param_label = st.selectbox(
            "Parámetro a graficar",
            list(opciones_param.keys()),
            key="geo_param",
        )
    punto_sel = opciones_punto[sel_punto_label]
    param_sel = opciones_param[sel_param_label]

    # ── 4. Detalle del punto seleccionado ───────────────────────────────
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    eca_info = punto_sel.get("ecas") or {}
    exc_punto = punto_sel.get("excedencias", [])
    n_exc_punto = len(exc_punto)
    estado_punto = punto_sel.get("estado", "sin_datos")
    color_estado = {"excedencia": "#c62828", "cumple": "#2e7d32", "sin_datos": "#9e9e9e"}.get(estado_punto, "#9e9e9e")
    # Mapeo al dominio "resultado" del nuevo sistema de pills
    from components.ui_styles import estado_pill as _pill
    _pill_key = {"excedencia": "excede", "cumple": "cumple", "sin_datos": "sin_dato"}.get(estado_punto, "sin_dato")
    estado_html = _pill(_pill_key, dominio="resultado")

    # Header del punto con estilo
    st.markdown(
        f"""<div style="background:white; border:1px solid #e2e8f0; border-left:5px solid {color_estado};
             border-radius:10px; padding:16px 20px; margin-bottom:12px;">
            <div style="display:flex; align-items:center; justify-content:space-between;">
                <div>
                    <span style="font-size:1.2rem; font-weight:700; color:#1e293b;">
                        {punto_sel['codigo']} — {punto_sel['nombre']}
                    </span>
                    <span style="margin-left:12px;">{estado_html}</span>
                </div>
                <div style="text-align:right; font-size:0.8rem; color:#64748b;">
                    {(punto_sel.get('tipo') or '—').capitalize()} &middot;
                    {punto_sel.get('cuenca', '—')} &middot;
                    {punto_sel.get('altitud_msnm', '—')} msnm
                </div>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Tres tarjetas de contexto — minimalistas (sin fondos saturados)
    i1, i2, i3 = st.columns(3)
    _ctx_card = lambda label, valor, color: (
        f'<div style="background:#ffffff; border:1px solid #f1f5f9; border-radius:10px; '
        f'padding:14px 18px; text-align:left;">'
        f'<div style="font-size:0.7rem; color:#94a3b8; text-transform:uppercase; '
        f'letter-spacing:0.05em; font-weight:600;">{label}</div>'
        f'<div style="font-weight:600; color:{color}; margin-top:6px; font-size:0.95rem;">{valor}</div>'
        f'</div>'
    )
    i1.markdown(_ctx_card("Sistema hídrico", punto_sel.get('sistema_hidrico', '—'), '#0f172a'), unsafe_allow_html=True)
    i2.markdown(_ctx_card("ECA aplicable",   eca_info.get('codigo', '—'),               '#0f172a'), unsafe_allow_html=True)
    i3.markdown(_ctx_card("Último dato",     punto_sel.get('ultima_fecha', '—'),        '#0f172a'), unsafe_allow_html=True)

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Cumplimiento ECA: bullet horizontal a ancho completo
    _render_gauge(punto_sel)

    # Excedencias activas (compactado)
    if exc_punto:
        with st.expander(f"⚠️ {n_exc_punto} excedencia(s) activa(s) en este punto", expanded=True):
            df_exc = pd.DataFrame(exc_punto)
            df_exc["pct_exceso"] = df_exc.apply(
                lambda r: round((r["valor"] / r["lim_max"] - 1) * 100, 1)
                          if r.get("lim_max") and r["lim_max"] > 0 else None,
                axis=1,
            )
            df_show = df_exc[["fecha", "parametro", "valor", "lim_max", "unidad", "pct_exceso"]].rename(columns={
                "fecha": "Fecha", "parametro": "Parámetro", "valor": "Valor",
                "lim_max": "Límite", "unidad": "Unidad", "pct_exceso": "% Exceso",
            })
            st.dataframe(
                df_show, use_container_width=True, hide_index=True,
                column_config={
                    "% Exceso": st.column_config.NumberColumn(format="%.1f%%"),
                    "Valor":    st.column_config.NumberColumn(format="%.4g"),
                    "Límite":   st.column_config.NumberColumn(format="%.4g"),
                },
            )

    # ── Fix 6: Tabs de categoría de parámetros ─────────────────────────
    tab_campo, tab_fq, tab_hidro = st.tabs([
        "Parámetros de Campo",
        "Parámetros Fisicoquímicos",
        "Parámetros Hidrobiológicos",
    ])

    with tab_campo:
        _render_categoria_tabs(punto_sel, param_sel, "Campo",
                               puntos_con_coords, str(fecha_inicio), str(fecha_fin), sel_camp)

    with tab_fq:
        _render_categoria_tabs(punto_sel, param_sel, "Fisicoquimico",
                               puntos_con_coords, str(fecha_inicio), str(fecha_fin), sel_camp)

    with tab_hidro:
        st.info("Módulo en desarrollo")


def _render_categoria_tabs(
    punto_sel: dict, param_sel: dict, categoria: str,
    puntos_con_coords: list[dict],
    fecha_inicio: str, fecha_fin: str,
    campana_label: str,
) -> None:
    """
    Pestañas analíticas para una categoría — reorganizadas para evitar duplicación:
        1. Tendencia        : evolución temporal del parámetro seleccionado
        2. Comparar puntos  : un parámetro entre todos los puntos
        3. Estacionalidad   : comportamiento mensual del parámetro
        4. Estado ECA       : tabla resumen + últimos resultados (consolidados)
    """
    # Validación: si el parámetro elegido no pertenece a esta categoría, avisamos
    cat_param = _clasificar_cat(param_sel)
    if cat_param != categoria:
        st.warning(
            f"El parámetro **{param_sel.get('nombre', '')}** está en categoría "
            f"**{cat_param}**, no en **{categoria}**. "
            "Los gráficos siguen disponibles, pero el filtro por pestaña no aplica."
        )

    tab_tend, tab_comp_puntos, tab_barras, tab_eca = st.tabs([
        "📈 Tendencia",
        "📊 Comparar puntos",
        "🗓️ Estacionalidad",
        "🛡️ Estado ECA y últimos resultados",
    ])

    with tab_tend:
        # Chart a ancho completo — la tabla redundante se eliminó
        _render_tendencia(punto_sel, param_sel, campana_label, cat=categoria)

    with tab_comp_puntos:
        st.markdown(f"**{param_sel['nombre']} — comparación entre puntos**")
        st.caption(
            "Cada barra es el último valor disponible del parámetro en el periodo seleccionado."
        )
        _render_barras_comparativa_puntos(
            puntos_con_coords, param_sel, fecha_inicio, fecha_fin, campana_label, cat=categoria,
        )

    with tab_barras:
        fecha_fin_dt = date.fromisoformat(fecha_fin)
        anio_sel = st.selectbox(
            "Año a visualizar",
            list(range(fecha_fin_dt.year, fecha_fin_dt.year - 5, -1)),
            key=f"geo_anio_{categoria}",
        )
        limite_eca = get_limite_eca_parametro(punto_sel["id"], param_sel["id"])
        _render_barras_mensuales(punto_sel, param_sel, anio_sel, limite_eca, campana_label, cat=categoria)

    with tab_eca:
        eca_info = punto_sel.get("ecas") or {}
        st.markdown(
            f"**Comparativa vs ECA** · {eca_info.get('codigo', '')} — {eca_info.get('nombre', '')}"
        )
        datos = get_comparativa_eca_punto(punto_sel["id"], fecha_inicio, fecha_fin)
        datos_cat = [d for d in datos if _clasificar_cat_comparativa(d) == categoria]
        if datos_cat:
            _render_comparativa_eca_filtered(datos_cat, cat=categoria)
        else:
            st.info("Sin datos para esta categoría en el periodo seleccionado.")

        st.divider()
        st.markdown("**Últimos 15 resultados (todas las categorías)**")
        _render_ultimos_resultados(punto_sel, cat=categoria)


def _clasificar_cat_comparativa(d: dict) -> str:
    """Classify a comparativa row into category."""
    codigo = (d.get("codigo") or "").upper()
    if codigo in _CODIGOS_CAMPO:
        return "Campo"
    cat_raw = d.get("categoria", "")
    return _CAT_NORMALIZE.get(cat_raw, "Fisicoquimico")


def _render_comparativa_eca_filtered(datos_f: list[dict], cat: str = "") -> None:
    """Render comparativa ECA table for a filtered set of parameters."""
    datos_with_data = [d for d in datos_f if d["valor"] is not None or d["lim_max"] is not None or d["lim_min"] is not None]
    if not datos_with_data:
        st.info("No hay parámetros con datos o límites ECA definidos.")
        return

    df = pd.DataFrame(datos_with_data)

    def _map_estado(row):
        if row.get("estado") == "excede":
            return "EXCEDE"
        elif row.get("estado") == "sin_eca":
            return "SIN ECA"
        elif row.get("estado") == "cumple":
            return "Cumple"
        return "—"

    df["Estado"] = df.apply(_map_estado, axis=1)

    df_show = df[["parametro", "valor", "unidad", "lim_min", "lim_max", "Estado", "fecha"]].copy()
    df_show.columns = ["Parámetro", "Valor", "Unidad", "Lím. Mín", "Lím. Máx", "Estado", "Fecha"]

    def _color_estado_cell(val):
        if val == "EXCEDE":
            return "background-color:#ffe0e0; color:#dc3545; font-weight:bold;"
        elif val == "Cumple":
            return "background-color:#e0ffe0; color:#28a745; font-weight:bold;"
        elif val == "SIN ECA":
            return "color:#888;"
        return ""

    n_exc = sum(1 for d in datos_with_data if d["estado"] == "excede")
    n_ok = sum(1 for d in datos_with_data if d["estado"] == "cumple")
    n_sin = sum(1 for d in datos_with_data if d["estado"] == "sin_dato")

    c1, c2, c3 = st.columns(3)
    c1.metric("Exceden ECA", n_exc)
    c2.metric("Cumplen ECA", n_ok)
    c3.metric("Sin dato", n_sin)

    st.dataframe(
        df_show.style.map(_color_estado_cell, subset=["Estado"]),
        use_container_width=True, hide_index=True,
        height=min(400, 35 * len(df_show) + 38),
        key=f"comp_eca_filtered_{cat}",
    )


main()
