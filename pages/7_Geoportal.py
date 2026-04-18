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
from components.ui_styles import aplicar_estilos, page_header
from services.mapa_service import (
    get_comparativa_eca_punto,
    get_datos_mensuales_parametro,
    get_historial_punto,
    get_limite_eca_parametro,
    get_parametros_selector,
    get_puntos_geoportal,
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

def _render_kpi_card(valor, label: str, color: str, icono: str) -> str:
    """Genera HTML para una tarjeta KPI — estilo limpio con acento de color."""
    return f"""
    <div style="background:#ffffff; border-radius:10px; padding:16px 20px;
         text-align:center; border:1px solid #e2e8f0;
         box-shadow:0 1px 3px rgba(0,0,0,0.04); transition: all 0.15s ease;">
        <div style="font-size:1.4rem; margin-bottom:4px;">{icono}</div>
        <div style="font-size:2rem; font-weight:800; line-height:1.1; color:{color};">{valor}</div>
        <div style="font-size:0.72rem; color:#64748b; margin-top:4px; text-transform:uppercase;
             letter-spacing:0.5px; font-weight:600;">{label}</div>
    </div>"""


def _render_dashboard(puntos: list[dict]) -> None:
    """Metricas globales estilo ANA + torta + alertas."""
    n_total = len(puntos)
    n_exc = sum(1 for p in puntos if p["estado"] == "excedencia")
    n_ok = sum(1 for p in puntos if p["estado"] == "cumple")
    n_sin = sum(1 for p in puntos if p["estado"] == "sin_datos")

    indices = [p["indice_cumplimiento"] for p in puntos if p.get("indice_cumplimiento") is not None]
    ic_general = round(sum(indices) / len(indices) * 100, 1) if indices else 0

    # ── KPIs estilo ANA con colores fuertes ──────────────────────────────
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(_render_kpi_card(n_total, "Puntos Monitoreados", "#1b6b35", "📍"), unsafe_allow_html=True)
    with k2:
        st.markdown(_render_kpi_card(n_ok, "Cumplen ECA", "#2e7d32", "✅"), unsafe_allow_html=True)
    with k3:
        st.markdown(_render_kpi_card(n_exc, "Con Excedencias", "#c62828", "⚠️"), unsafe_allow_html=True)
    with k4:
        st.markdown(_render_kpi_card(n_sin, "Sin Datos", "#616161", "—"), unsafe_allow_html=True)
    with k5:
        color_ic = "#2e7d32" if ic_general >= 80 else "#e8870e" if ic_general >= 50 else "#c62828"
        st.markdown(_render_kpi_card(f"{ic_general}%", "Cumplimiento ECA", color_ic, "📊"), unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # ── Barra de cumplimiento + torta ────────────────────────────────────
    col_barra, col_torta = st.columns([3, 2])

    with col_barra:
        color_barra = "#2e7d32" if ic_general >= 80 else "#e8870e" if ic_general >= 50 else "#c62828"
        st.markdown(
            f"""<div style="background:#ffffff; border-radius:10px; padding:16px 20px;
                 border:1px solid #e2e8f0; margin-top:4px;">
            <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:6px;">
                <span style="font-weight:600; color:#1e293b;">Indice de Cumplimiento General ECA</span>
                <span style="color:{color_barra}; font-weight:bold; font-size:1.1rem;">{ic_general}%</span>
            </div>
            <div style="background:#f1f5f9; border-radius:8px; height:24px; overflow:hidden;">
                <div style="background:linear-gradient(90deg, {color_barra}, {color_barra}dd);
                     width:{ic_general}%; height:100%; border-radius:8px;
                     transition: width 0.5s;"></div>
            </div>
            <div style="font-size:11px; color:#64748b; margin-top:6px;">
                D.S. N° 004-2017-MINAM — Estandares Nacionales de Calidad Ambiental para Agua
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
            with st.expander(f"⚠️ {len(criticos)} punto(s) con excedencia", expanded=False):
                for p in criticos[:5]:
                    exc_list = p.get("excedencias", [])
                    params_exc = ", ".join(
                        f"{e['parametro']}" for e in exc_list[:4]
                    )
                    if len(exc_list) > 4:
                        params_exc += f" (+{len(exc_list)-4})"
                    st.markdown(
                        f"""<div style="display:flex; align-items:center; padding:6px 10px; margin:2px 0;
                            background:#fef5f5; border-left:3px solid #c62828; border-radius:4px; font-size:12px;">
                            <div style="flex:1;">
                                <b>{p['codigo']}</b> — {p['nombre']}
                                <span style="color:#888; margin-left:6px; font-size:11px;">{params_exc}</span>
                            </div>
                            <span style="color:#c62828; font-weight:bold; font-size:11px;">{len(exc_list)}</span>
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
    )

    # Tile layers
    folium.TileLayer("OpenStreetMap", name="Calles").add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satélite",
    ).add_to(m)
    folium.TileLayer(
        tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attr="OpenTopoMap", name="Topográfico",
    ).add_to(m)

    MiniMap(toggle_display=True, position="bottomright", zoom_level_offset=-5).add_to(m)

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

    # FIX 1: HeatMap BEFORE markers so markers render on top
    if mostrar_heatmap and heat_data:
        fg_heat = folium.FeatureGroup(name="Mapa de calor ECA", show=True)
        HeatMap(
            heat_data,
            min_opacity=0.3,
            max_zoom=13,
            radius=30,
            blur=20,
            gradient={
                "0.0": "#2e7d32",
                "0.3": "#0a9396",
                "0.5": "#e8870e",
                "0.7": "#c56d00",
                "1.0": "#c62828",
            },
        ).add_to(fg_heat)
        fg_heat.add_to(m)

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
    ic = punto.get("indice_cumplimiento")
    if ic is None:
        st.info("Sin datos para evaluar cumplimiento.")
        return

    pct = round(ic * 100, 1)
    n_eval = punto.get("n_parametros_evaluados", 0)
    n_exc = punto.get("n_excedencias", 0)

    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=pct,
        number={"suffix": "%", "font": {"size": 36}},
        delta={"reference": 100, "suffix": "%", "decreasing": {"color": "#c62828"}},
        title={"text": f"Cumplimiento ECA<br><span style='font-size:12px; color:#666;'>{n_eval-n_exc}/{n_eval} parámetros OK</span>"},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": "#1b6b35"},
            "steps": [
                {"range": [0, 50], "color": "#fce4e4"},
                {"range": [50, 80], "color": "#fef3e2"},
                {"range": [80, 100], "color": "#e8f5e9"},
            ],
            "threshold": {
                "line": {"color": "#c62828", "width": 3},
                "thickness": 0.8,
                "value": 100,
            },
        },
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=10))
    st.plotly_chart(fig, use_container_width=True)


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

def _render_tabla_eca_parametros(punto: dict, fecha_inicio: str, fecha_fin: str, cat: str = "") -> None:
    """Tabla de % del límite ECA por parámetro — reemplaza el radar."""
    datos = get_comparativa_eca_punto(punto["id"], fecha_inicio, fecha_fin)
    validos = [d for d in datos if d["valor"] is not None and d.get("tiene_eca")]
    if not validos:
        return

    # Build table data
    rows = []
    for d in validos:
        lim_max = d.get("lim_max")
        lim_min = d.get("lim_min")
        if lim_max and lim_max > 0:
            pct = round(d["valor"] / lim_max * 100, 1)
        elif lim_min and lim_min > 0:
            pct = round(lim_min / d["valor"] * 100, 1) if d["valor"] > 0 else 0
        else:
            continue
        rows.append({
            "Parámetro": d["parametro"],
            "Valor": d["valor"],
            "Unidad": d["unidad"],
            "Límite ECA": lim_max if lim_max else lim_min,
            "% del límite": pct,
            "Estado": "EXCEDE" if d["estado"] == "excede" else "Cumple",
        })

    if not rows:
        return

    st.markdown("**% del límite ECA por parámetro**")
    df = pd.DataFrame(rows)

    def _style_estado(val):
        if val == "EXCEDE":
            return "background-color:#ffe0e0; color:#dc3545; font-weight:bold;"
        elif val == "Cumple":
            return "background-color:#e0ffe0; color:#28a745;"
        return ""

    def _style_pct(val):
        try:
            v = float(val)
            if v > 100:
                return "color:#dc3545; font-weight:bold;"
        except (ValueError, TypeError):
            pass
        return ""

    st.dataframe(
        df.style.map(_style_estado, subset=["Estado"]).map(_style_pct, subset=["% del límite"]),
        use_container_width=True, hide_index=True,
        height=min(400, 35 * len(df) + 38),
        key=f"tabla_eca_params_{cat}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. COMPARATIVA ECA (tabla) — Fix 5: cumple, SIN ECA, no código column
# ─────────────────────────────────────────────────────────────────────────────

def _render_comparativa_eca(punto: dict, fecha_inicio: str, fecha_fin: str) -> None:
    datos = get_comparativa_eca_punto(punto["id"], fecha_inicio, fecha_fin)
    if not datos:
        st.info("Sin datos para comparativa ECA.")
        return

    datos_f = [d for d in datos if d["valor"] is not None or d["lim_max"] is not None or d["lim_min"] is not None]
    if not datos_f:
        st.info("No hay parámetros con datos o límites ECA definidos.")
        return

    df = pd.DataFrame(datos_f)

    # Fix 5: "cumple" instead of "OK", "SIN ECA" for parameters without ECA
    def _map_estado(row):
        if row.get("estado") == "excede":
            return "EXCEDE"
        elif row.get("estado") == "sin_eca":
            return "SIN ECA"
        elif row.get("estado") == "cumple":
            return "Cumple"
        return "—"

    df["Estado"] = df.apply(_map_estado, axis=1)

    # Fix 5: remove "código" column
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

    n_exc = sum(1 for d in datos_f if d["estado"] == "excede")
    n_ok = sum(1 for d in datos_f if d["estado"] == "cumple")
    n_sin = sum(1 for d in datos_f if d["estado"] == "sin_dato")

    c1, c2, c3 = st.columns(3)
    c1.metric("Exceden ECA", n_exc)
    c2.metric("Cumplen ECA", n_ok)
    c3.metric("Sin dato", n_sin)

    st.dataframe(
        df_show.style.map(_color_estado_cell, subset=["Estado"]),
        use_container_width=True, hide_index=True,
        height=min(400, 35 * len(df_show) + 38),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 7. BARRAS COMPARATIVAS: un parámetro en TODOS los puntos
# ─────────────────────────────────────────────────────────────────────────────

def _render_barras_comparativa_puntos(
    puntos: list[dict], parametro: dict,
    fecha_inicio: str, fecha_fin: str,
    campana_label: str,
    cat: str = "",
) -> None:
    """Gráfico de barras horizontal: compara un parámetro entre todos los puntos."""
    db_data = []
    for p in puntos:
        datos = get_comparativa_eca_punto(p["id"], fecha_inicio, fecha_fin)
        for d in datos:
            if d["codigo"] == parametro["codigo"] and d["valor"] is not None:
                db_data.append({
                    "punto": p["codigo"],
                    "nombre": p["nombre"],
                    "valor": d["valor"],
                    "lim_max": d["lim_max"],
                    "estado": d["estado"],
                })
                break

    if not db_data:
        st.info(f"Sin datos de {parametro['nombre']} en los puntos monitoreados.")
        return

    df = pd.DataFrame(db_data).sort_values("valor", ascending=True)
    colores = ["#dc3545" if r["estado"] == "excede" else "#1a73e8" for _, r in df.iterrows()]

    unidad = (parametro.get("unidades_medida") or {}).get("simbolo", "")
    x_label = f"{parametro['nombre']} ({unidad})" if unidad else parametro["nombre"]

    # Title with scope
    scope = "por punto de monitoreo"
    if campana_label and campana_label != "Todas":
        scope += f" · Campaña: {campana_label}"

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df["punto"], x=df["valor"],
        orientation="h",
        marker_color=colores,
        text=[f"{v:.3g}" for v in df["valor"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Valor: %{x:.4g}<extra></extra>",
    ))

    lim_max = db_data[0].get("lim_max")
    if lim_max is not None:
        fig.add_vline(x=lim_max, line_dash="dash", line_color="red", line_width=2,
                      annotation_text=f"ECA máx: {lim_max}", annotation_position="top right",
                      annotation_font_color="red")

    fig.update_layout(
        title=f"<b>Comparación de {parametro['nombre']}</b><br>"
              f"<span style='font-size:12px; color:#666;'>{scope}</span>",
        xaxis_title=x_label,
        height=max(300, len(df) * 30 + 100),
        margin=dict(l=100, r=60, t=70, b=40),
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#f5f5f5"),
        xaxis=dict(gridcolor="#f0f0f0"),
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
    datos = get_datos_mensuales_parametro(parametro["id"], anio)
    if not datos:
        st.info(f"Sin datos de {parametro['nombre']} para {anio}.")
        return

    df = pd.DataFrame(datos)
    df_agg = df.groupby(["punto_codigo", "punto_nombre", "mes"], as_index=False)["valor"].mean()
    fig = go.Figure()

    puntos_u = df_agg[["punto_codigo", "punto_nombre"]].drop_duplicates().sort_values("punto_codigo")
    for _, row in puntos_u.iterrows():
        df_p = df_agg[df_agg["punto_codigo"] == row["punto_codigo"]]
        meses_vals = {r["mes"]: r["valor"] for _, r in df_p.iterrows()}
        valores = [meses_vals.get(m, None) for m in range(1, 13)]
        fig.add_trace(go.Bar(
            name=f"{row['punto_codigo']}", x=MESES, y=valores,
            text=[f"{v:.2g}" if v is not None else "" for v in valores],
            textposition="outside", textfont_size=9,
        ))

    if limite_eca:
        lim_max = limite_eca.get("valor_maximo")
        lim_min = limite_eca.get("valor_minimo")
        if lim_max is not None:
            fig.add_hline(y=lim_max, line_dash="dash", line_color="red", line_width=2,
                          annotation_text=f"ECA máx: {lim_max}", annotation_position="top right", annotation_font_color="red")
        if lim_min is not None:
            fig.add_hline(y=lim_min, line_dash="dash", line_color="orange", line_width=2,
                          annotation_text=f"ECA mín: {lim_min}", annotation_position="bottom right", annotation_font_color="orange")

    unidad = (parametro.get("unidades_medida") or {}).get("simbolo", "")
    y_label = f"{parametro['nombre']} ({unidad})" if unidad else parametro["nombre"]

    subtitle = f"{punto['codigo']} — {punto['nombre']}"
    if campana_label and campana_label != "Todas":
        subtitle += f" · Campaña: {campana_label}"

    fig.update_layout(
        title=f"<b>{parametro.get('nombre', '')} — Comportamiento mensual {anio}</b><br>"
              f"<span style='font-size:12px; color:#666;'>{subtitle}</span>",
        xaxis_title="Mes", yaxis_title=y_label,
        barmode="group", height=450, margin=dict(b=100, t=80),
        legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5, font_size=10),
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
    page_header("Geoportal", "Monitoreo de Calidad de Agua — Cuenca Chili-Quilca")

    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.error("Instala: `pip install folium streamlit-folium`")
        st.stop()

    # ── Sidebar: filtros ────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("Filtros")

        fecha_inicio = st.date_input("Desde", value=date.today() - timedelta(days=90), key="geo_desde")
        fecha_fin = st.date_input("Hasta", value=date.today(), key="geo_hasta")

        campanas = get_campanas()
        opciones_camp = {"Todas": None}
        opciones_camp.update({f"{c['codigo']} — {c['nombre']}": c["id"] for c in campanas})
        sel_camp = st.selectbox("Campaña", list(opciones_camp.keys()), key="geo_camp")
        campana_id = opciones_camp[sel_camp]

        st.divider()
        solo_exc = st.checkbox("Solo excedencias", key="geo_solo_exc")
        mostrar_heatmap = st.checkbox("Mapa de calor", value=True, key="geo_heatmap")

        st.divider()
        st.subheader("Detalle de punto")

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

    # ── Selector de punto y parámetro (sidebar) ─────────────────────────
    with st.sidebar:
        # Fix 3: only show points that are in the campaign
        opciones_punto = {f"{p['codigo']} — {p['nombre']}": p for p in puntos_con_coords}
        sel_punto_label = st.selectbox("Punto de muestreo", list(opciones_punto.keys()), key="geo_punto")
        punto_sel = opciones_punto[sel_punto_label]

        # Fix 6: parameter selector with category tabs logic
        parametros = get_parametros_selector()
        opciones_param = {f"{pr['codigo']} — {pr['nombre']}": pr for pr in parametros}
        sel_param_label = st.selectbox("Parámetro", list(opciones_param.keys()), key="geo_param")
        param_sel = opciones_param[sel_param_label]

    # ── 1. Dashboard resumen ────────────────────────────────────────────
    _render_dashboard(puntos_con_coords)

    st.divider()

    # ── 2. Mapa ─────────────────────────────────────────────────────────
    mapa = _construir_mapa(puntos_con_coords, solo_exc, mostrar_heatmap)
    map_data = st_folium(mapa, use_container_width=True, height=520, returned_objects=["last_object_clicked"])

    # Si el usuario hace click en el mapa, seleccionar ese punto
    if map_data and map_data.get("last_object_clicked"):
        clicked = map_data["last_object_clicked"]
        clat, clon = clicked.get("lat"), clicked.get("lng")
        if clat and clon:
            min_dist = float("inf")
            for label, p in opciones_punto.items():
                dist = (p["latitud"] - clat)**2 + (p["longitud"] - clon)**2
                if dist < min_dist:
                    min_dist = dist
                    closest_label = label
            if min_dist < 0.01:
                punto_sel = opciones_punto[closest_label]

    # ── 3. Detalle del punto seleccionado ───────────────────────────────
    st.divider()
    eca_info = punto_sel.get("ecas") or {}
    exc_punto = punto_sel.get("excedencias", [])
    n_exc_punto = len(exc_punto)
    estado_punto = punto_sel.get("estado", "sin_datos")
    color_estado = {"excedencia": "#c62828", "cumple": "#2e7d32", "sin_datos": "#9e9e9e"}.get(estado_punto, "#9e9e9e")
    estado_label = {"excedencia": "EXCEDENCIA", "cumple": "CUMPLE ECA", "sin_datos": "SIN DATOS"}.get(estado_punto, "—")

    # Header del punto con estilo
    st.markdown(
        f"""<div style="background:white; border:1px solid #e2e8f0; border-left:5px solid {color_estado};
             border-radius:10px; padding:16px 20px; margin-bottom:12px;">
            <div style="display:flex; align-items:center; justify-content:space-between;">
                <div>
                    <span style="font-size:1.2rem; font-weight:700; color:#1e293b;">
                        {punto_sel['codigo']} — {punto_sel['nombre']}
                    </span>
                    <span style="background:{color_estado}; color:white; padding:3px 10px; border-radius:20px;
                         font-size:0.7rem; font-weight:600; margin-left:12px; letter-spacing:0.5px;">
                        {estado_label}
                    </span>
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

    col_info, col_gauge = st.columns([3, 2])

    with col_info:
        # Info cards en grid
        i1, i2, i3 = st.columns(3)
        i1.markdown(
            f"""<div style="background:#e8f5e9; border-radius:8px; padding:10px 14px; text-align:center;">
            <div style="font-size:0.7rem; color:#64748b; text-transform:uppercase;">Sistema Hidrico</div>
            <div style="font-weight:700; color:#1b6b35;">{punto_sel.get('sistema_hidrico', '—')}</div>
            </div>""", unsafe_allow_html=True)
        i2.markdown(
            f"""<div style="background:#e0f7f7; border-radius:8px; padding:10px 14px; text-align:center;">
            <div style="font-size:0.7rem; color:#64748b; text-transform:uppercase;">ECA Aplicable</div>
            <div style="font-weight:700; color:#0a9396;">{eca_info.get('codigo', '—')}</div>
            </div>""", unsafe_allow_html=True)
        i3.markdown(
            f"""<div style="background:#fef3e2; border-radius:8px; padding:10px 14px; text-align:center;">
            <div style="font-size:0.7rem; color:#64748b; text-transform:uppercase;">Ultimo Dato</div>
            <div style="font-weight:700; color:#c56d00;">{punto_sel.get('ultima_fecha', '—')}</div>
            </div>""", unsafe_allow_html=True)

        # Excedencias activas
        if exc_punto:
            st.markdown(f"**{n_exc_punto} excedencia(s) activa(s)**")
            df_exc = pd.DataFrame(exc_punto)
            df_exc["pct_exceso"] = df_exc.apply(
                lambda r: round((r["valor"] / r["lim_max"] - 1) * 100, 1) if r.get("lim_max") and r["lim_max"] > 0 else None,
                axis=1,
            )
            df_show = df_exc[["fecha", "parametro", "valor", "lim_max", "unidad", "pct_exceso"]].rename(columns={
                "fecha": "Fecha", "parametro": "Parametro", "valor": "Valor",
                "lim_max": "Limite", "unidad": "Unidad", "pct_exceso": "% Exceso",
            })
            st.dataframe(df_show, use_container_width=True, hide_index=True,
                         column_config={"% Exceso": st.column_config.NumberColumn(format="%.1f%%")})

    with col_gauge:
        _render_gauge(punto_sel)

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
    """Render analysis tabs for a given parameter category."""
    tab_tend, tab_comp_puntos, tab_barras, tab_eca, tab_result = st.tabs([
        "Tendencia temporal",
        "Comparar puntos",
        "Comportamiento mensual",
        "Comparativa ECA",
        "Últimos resultados",
    ])

    with tab_tend:
        col_chart, col_tabla = st.columns([3, 2])
        with col_chart:
            _render_tendencia(punto_sel, param_sel, campana_label, cat=categoria)
        with col_tabla:
            _render_tabla_eca_parametros(punto_sel, fecha_inicio, fecha_fin, cat=categoria)

    with tab_comp_puntos:
        st.markdown(f"**Comparación de {param_sel['nombre']} entre todos los puntos**")
        _render_barras_comparativa_puntos(puntos_con_coords, param_sel, fecha_inicio, fecha_fin, campana_label, cat=categoria)

    with tab_barras:
        fecha_fin_dt = date.fromisoformat(fecha_fin)
        anio_sel = st.selectbox(
            "Año", list(range(fecha_fin_dt.year, fecha_fin_dt.year - 5, -1)),
            key=f"geo_anio_{categoria}",
        )
        limite_eca = get_limite_eca_parametro(punto_sel["id"], param_sel["id"])
        _render_barras_mensuales(punto_sel, param_sel, anio_sel, limite_eca, campana_label, cat=categoria)

    with tab_eca:
        eca_info = punto_sel.get("ecas") or {}
        st.markdown(f"**Comparativa vs ECA** · {eca_info.get('codigo', '')} — {eca_info.get('nombre', '')}")

        # Filter comparativa data by category
        datos = get_comparativa_eca_punto(punto_sel["id"], fecha_inicio, fecha_fin)
        datos_cat = [d for d in datos if _clasificar_cat_comparativa(d) == categoria]
        if datos_cat:
            _render_comparativa_eca_filtered(datos_cat, cat=categoria)
        else:
            st.info("Sin datos para esta categoría.")

    with tab_result:
        st.markdown("**Últimos 15 resultados**")
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
