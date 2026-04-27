"""
pages/7_Geoportal.py
Geoportal técnico de monitoreo de calidad de agua — cuencas
Quilca-Vítor-Chili y Colca-Camaná.

Layout:
    1. Filtros (fechas, campaña, solo excedencias)
    2. Dashboard global: 4 KPIs + barra cumplimiento + alertas críticas
    3. Mapa Folium + panel lateral del punto seleccionado (2 columnas)
       Click en marcador → actualiza el panel sin scroll
    4. Análisis del punto: filtro de categoría + selector de parámetro
       4 tabs: Tendencia, Comparar puntos, Estacionalidad, Estado ECA

Audiencia actual: técnicos AUTODEMA/ANA. La versión ciudadana se hará aparte.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import aplicar_estilos, page_header, section_header, top_nav
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
from services.fitoplancton_service import get_alertas_oms_por_punto


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

def _render_kpi_card(
    valor,
    label: str,
    color: str,
    icono_name: str,
    unidad: str = "",
) -> str:
    """
    Tarjeta KPI estilo SSDH-ANA (rediseño 2026-04-21 v2):
    - Borde INFERIOR 3px del color identitario (no lateral).
    - Título arriba-izquierda en case normal, peso 500 (no uppercase).
    - Ícono SVG en círculo pastel (halo del color) arriba-derecha, en el
      mismo row que el título vía flexbox.
    - Valor grande DEBAJO, en negro oscuro (#1a1a1a), peso regular 400
      (no coloreado, no bold) — es lo que da el aire institucional SSDH.
    - Unidad opcional en texto pequeño gris al lado del valor.
    """
    from components.ui_styles import icon as _icon

    # rgba con alpha para fondo de halo (más compatible que hex 8 dígitos)
    def _hex_to_rgba(h: str, alpha: float) -> str:
        h = h.lstrip("#")
        if len(h) != 6:
            return f"rgba(148,163,184,{alpha})"
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"

    halo_bg = _hex_to_rgba(color, 0.12)
    icono_svg = _icon(icono_name, size=22, color=color)

    unidad_html = (
        f'<span style="font-size:0.78rem; color:#6b7280; '
        f'font-weight:400; margin-left:4px;">{unidad}</span>'
        if unidad else ""
    )

    return f"""
    <div style="background:#ffffff; border-radius:8px;
         padding:14px 18px 12px 18px;
         border:1px solid #e8eaed;
         border-bottom:3px solid {color};
         box-shadow:0 1px 2px rgba(15,23,42,0.04);
         min-height:110px; display:flex; flex-direction:column;">
        <div style="display:flex; justify-content:space-between;
             align-items:flex-start; gap:10px; margin-bottom:14px;">
            <div style="font-size:0.88rem; color:#374151; font-weight:500;
                 letter-spacing:-0.01em; flex:1; line-height:1.3;">{label}</div>
            <div style="width:42px; height:42px; border-radius:50%;
                 background:{halo_bg};
                 display:inline-flex; align-items:center;
                 justify-content:center; flex-shrink:0;">
                {icono_svg}
            </div>
        </div>
        <div style="display:flex; align-items:baseline;">
            <span style="font-size:1.9rem; font-weight:400;
                 color:#1a1a1a; line-height:1; letter-spacing:-0.02em;">{valor}</span>{unidad_html}
        </div>
    </div>"""


def _render_dashboard(puntos: list[dict]) -> None:
    """
    Resumen ejecutivo: 4 KPIs + barra de cumplimiento + alertas críticas.
    La torta se eliminó (duplicaba la información de los KPIs 2-3-4).
    El KPI '% Cumplimiento ECA' se eliminó (duplicaba la barra inferior).
    """
    n_total = len(puntos)
    n_exc = sum(1 for p in puntos if p["estado"] == "excedencia")
    n_ok = sum(1 for p in puntos if p["estado"] == "cumple")
    n_sin = sum(1 for p in puntos if p["estado"] == "sin_datos")

    indices = [p["indice_cumplimiento"] for p in puntos if p.get("indice_cumplimiento") is not None]
    ic_general = round(sum(indices) / len(indices) * 100, 1) if indices else 0

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(_render_kpi_card(n_total, "Puntos monitoreados", "#0a9396", "map_pin"), unsafe_allow_html=True)
    with k2:
        st.markdown(_render_kpi_card(n_ok, "Cumplen ECA", "#1b6b35", "check"), unsafe_allow_html=True)
    with k3:
        st.markdown(_render_kpi_card(n_exc, "Con excedencias", "#c62828", "alert"), unsafe_allow_html=True)
    with k4:
        st.markdown(_render_kpi_card(n_sin, "Sin datos", "#94a3b8", "info"), unsafe_allow_html=True)

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # Barra de cumplimiento general — ancho completo
    color_barra = "#1b6b35" if ic_general >= 80 else "#e8870e" if ic_general >= 50 else "#c62828"
    st.markdown(
        f"""<div style="background:#ffffff; border-radius:12px; padding:18px 22px;
             border:1px solid #f1f5f9;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
            <span style="font-size:0.7rem; color:#94a3b8; text-transform:uppercase;
                 letter-spacing:0.05em; font-weight:600;">Índice de cumplimiento general ECA</span>
            <span style="color:{color_barra}; font-weight:600; font-size:1.25rem; letter-spacing:-0.01em;">{ic_general}%</span>
        </div>
        <div style="background:#f1f5f9; border-radius:6px; height:10px; overflow:hidden;">
            <div style="background:{color_barra}; width:{ic_general}%; height:100%;
                 border-radius:6px; transition: width 0.5s;"></div>
        </div>
        <div style="font-size:0.72rem; color:#94a3b8; margin-top:10px;">
            D.S. N° 004-2017-MINAM · promedio simple del índice por punto
        </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Panel de alertas críticas (global)
    criticos = sorted(
        [p for p in puntos if p["estado"] == "excedencia"],
        key=lambda x: x.get("n_excedencias", 0),
        reverse=True,
    )
    if criticos:
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        label_exp = f"{len(criticos)} punto(s) con excedencias activas"
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


# ─────────────────────────────────────────────────────────────────────────────
# 2. MAPA OPTIMIZADO (Fix 1: z-index — markers always above heatmap)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def _cargar_geojson_puntos() -> dict[str, dict]:
    """Carga las siluetas de cuerpos de agua (represas). Cacheado en disco."""
    import json
    from pathlib import Path

    geojson_dir = Path(__file__).parent.parent / "static" / "geojson"
    siluetas: dict[str, dict] = {}
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


@st.cache_data(show_spinner=False)
def _cargar_geojson_cuencas() -> list[dict]:
    """Polígonos de cuencas (`static/geojson/cuencas/*.geojson`). Cacheado."""
    import json
    from pathlib import Path

    cuencas_dir = Path(__file__).parent.parent / "static" / "geojson" / "cuencas"
    cuencas: list[dict] = []
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


@st.cache_data(show_spinner=False)
def _cargar_geojson_rios() -> list[dict]:
    """Red hídrica (`static/geojson/rios/*.geojson`). Cacheado."""
    import json
    from pathlib import Path

    rios_dir = Path(__file__).parent.parent / "static" / "geojson" / "rios"
    items: list[dict] = []
    if not rios_dir.exists():
        return items
    for f in rios_dir.glob("*.geojson"):
        try:
            with open(f, encoding="utf-8") as fh:
                items.append({
                    "data": json.load(fh),
                    "nombre": f.stem.replace("rios_", "").replace("_", " ").title(),
                })
        except Exception:
            pass
    return items


def _popup_html(p: dict) -> str:
    """
    Popup minimalista — solo identificación del punto + estado.
    El detalle completo (UTM, ECA, sistema hídrico, excedencias) vive ahora
    en el panel lateral del punto seleccionado, no en el popup.
    """
    eca = p.get("ecas") or {}
    ic = p.get("indice_cumplimiento")
    n_eval = p.get("n_parametros_evaluados", 0)
    n_exc = p.get("n_excedencias", 0)
    color = _color_termico(p)

    if ic is None:
        estado_txt = "Sin datos"
        sub_txt = ""
    else:
        estado_txt = f"{int(ic*100)}% cumple ECA"
        sub_txt = f"{n_eval - n_exc} de {n_eval} parámetros dentro de norma"

    return (
        f"<div style='min-width:220px; font-family:sans-serif;'>"
        f"<div style='background:{color}; height:4px; border-radius:4px 4px 0 0; "
        f"margin:-1px -1px 8px -1px;'></div>"
        f"<div style='font-weight:700; font-size:13px; color:#0f172a;'>{p['codigo']}</div>"
        f"<div style='color:#475569; font-size:12px; margin-bottom:8px;'>{p['nombre']}</div>"
        f"<div style='font-size:11px; color:#64748b;'>"
        f"{eca.get('codigo','—')} · {p.get('cuenca','—')}"
        f"</div>"
        f"<div style='margin-top:6px; font-size:12px; color:{color}; font-weight:600;'>{estado_txt}</div>"
        f"<div style='font-size:10px; color:#94a3b8;'>{sub_txt}</div>"
        f"<div style='font-size:10px; color:#94a3b8; margin-top:8px; "
        f"border-top:1px solid #f1f5f9; padding-top:6px;'>"
        f"Selecciona el punto en el panel lateral para el detalle completo."
        f"</div>"
        f"</div>"
    )


def _construir_mapa(puntos: list[dict], solo_excedencias: bool):
    """
    Mapa Folium con cuencas, red hídrica, puntos y alertas OMS de
    cianobacterias. Las capas se agrupan en el LayerControl en cuatro
    secciones: Mapa base, Territorio, Monitoreo y Cianobacterias (OMS).
    """
    import folium
    from folium.plugins import GroupedLayerControl, MiniMap

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
    tile_calles = folium.TileLayer(
        "OpenStreetMap",
        name="Calles",
        max_native_zoom=19, max_zoom=22,
    )
    tile_calles.add_to(m)
    # Esri World Imagery: cobertura limitada en zonas altiplánicas remotas.
    # En la cuenca Chili-Quilca (Aguada Blanca, Pampa de Arrieros, etc.) no
    # hay imagen satelital de alta resolución más allá de zoom 17. Limitamos
    # max_native_zoom y max_zoom para que Leaflet repita el último tile válido
    # en lugar de pedir tiles inexistentes (que vienen como "Map data not yet
    # available").
    tile_satelite = folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satélite",
        max_native_zoom=17, max_zoom=19,
    )
    tile_satelite.add_to(m)
    # Capa Topográfico removida — el satélite + calles cubren los casos de uso
    # y reduce la carga visual del control de capas.

    MiniMap(toggle_display=True, position="bottomright", zoom_level_offset=-5).add_to(m)

    # ── Polígonos de cuencas hidrográficas (estilo SSDH/ANA) ─────────────
    # Outline de color por cuenca para distinguirlas a simple vista:
    #   Quilca-Vítor-Chili → verde    · Colca-Camaná → rojo
    cuencas = _cargar_geojson_cuencas()

    def _color_cuenca(nombre: str) -> tuple[str, str]:
        """Devuelve (color_base, color_hover) según la cuenca."""
        n = nombre.lower()
        if "quilca" in n or "vitor" in n or "chili" in n:
            return ("#22c55e", "#15803d")    # verde / verde oscuro
        if "colca" in n or "caman" in n:
            return ("#dc2626", "#991b1b")    # rojo / rojo oscuro
        return ("#64748b", "#334155")         # gris fallback

    fg_cuencas: folium.FeatureGroup | None = None
    if cuencas:
        fg_cuencas = folium.FeatureGroup(name="Cuencas hidrográficas", show=True)
        for cu in cuencas:
            base, hover = _color_cuenca(cu["nombre"])
            folium.GeoJson(
                cu["data"],
                style_function=lambda feature, c=base: {
                    "color": c,
                    "weight": 2.5,
                    "fillColor": c,
                    "fillOpacity": 0.05,     # apenas perceptible — solo enmarca
                    "dashArray": "0",
                },
                highlight_function=lambda feature, c=hover: {
                    "color": c,
                    "weight": 3.5,
                    "fillOpacity": 0.12,
                },
                tooltip=f"Cuenca: {cu['nombre']}",
            ).add_to(fg_cuencas)
        fg_cuencas.add_to(m)

    # ── Red hídrica: ríos y quebradas ────────────────────────────────────
    # Estilo ANA: línea azul. Los ríos son más gruesos/opacos que las
    # quebradas para permitir una lectura jerárquica a cualquier zoom.
    rios_gj = _cargar_geojson_rios()
    fg_rios: folium.FeatureGroup | None = None
    fg_quebradas: folium.FeatureGroup | None = None
    if rios_gj:
        fg_rios = folium.FeatureGroup(name="Ríos", show=True)
        fg_quebradas = folium.FeatureGroup(name="Quebradas", show=False)

        def _style_rio(feature):
            return {
                "color": "#1d4ed8",      # azul río ANA
                "weight": 2.5,
                "opacity": 0.9,
            }

        def _style_quebrada(feature):
            return {
                "color": "#60a5fa",      # azul claro — quebrada secundaria
                "weight": 1.3,
                "opacity": 0.8,
                "dashArray": "3,3",
            }

        for capa in rios_gj:
            data = capa["data"]
            # Separamos ríos y quebradas en features independientes para
            # poder togglearlos por separado en el layer control.
            feats_rio = [
                f for f in data.get("features", [])
                if (f.get("properties", {}).get("TIPO_CA") or "").lower().startswith("r")
            ]
            feats_queb = [
                f for f in data.get("features", [])
                if (f.get("properties", {}).get("TIPO_CA") or "").lower().startswith("q")
            ]

            if feats_rio:
                folium.GeoJson(
                    {"type": "FeatureCollection", "features": feats_rio},
                    style_function=_style_rio,
                    tooltip=folium.GeoJsonTooltip(
                        fields=["NOMBRE_CA", "LONG_KM", "CATEGORIA"],
                        aliases=["Río:", "Longitud (km):", "Categoría ECA:"],
                        localize=True, sticky=False, labels=True,
                    ),
                ).add_to(fg_rios)

            if feats_queb:
                folium.GeoJson(
                    {"type": "FeatureCollection", "features": feats_queb},
                    style_function=_style_quebrada,
                    tooltip=folium.GeoJsonTooltip(
                        fields=["NOMBRE_CA", "LONG_KM", "CATEGORIA"],
                        aliases=["Quebrada:", "Longitud (km):", "Categoría ECA:"],
                        localize=True, sticky=False, labels=True,
                    ),
                ).add_to(fg_quebradas)

        fg_rios.add_to(m)
        fg_quebradas.add_to(m)

    # Polígonos de represas/lagunas — sin popup propio para no solapar con
    # el popup del marcador del punto (antes había dos popups encima de la
    # misma represa).
    siluetas = _cargar_geojson_puntos()
    fg_poligonos = folium.FeatureGroup(name="Represas/Lagunas", show=True)

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
            ).add_to(fg_poligonos)

    fg_poligonos.add_to(m)

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

    # ── Capas: Alerta OMS Cianobacterias (1999 y 2021 — ambas separadas) ──
    # Cada capa es un anillo coloreado encima del marcador ECA con el nivel
    # del último análisis fitoplancton. Las dos tablas se reportan sin
    # combinar: el usuario decide cuál mirar según el contexto (agua potable
    # vs agua recreativa).
    try:
        alertas_cyano = get_alertas_oms_por_punto()
        cyano_error = None
    except Exception as exc:
        alertas_cyano = {}
        cyano_error = str(exc)

    n_puntos_cyano = sum(1 for p in pts_filtrados if alertas_cyano.get(p["id"]))

    def _construir_fg_oms(version: str, titulo: str) -> folium.FeatureGroup:
        """version: '1999' o '2021'. Lee `oms_1999`/`oms_2021` del dict."""
        clave = f"oms_{version}"
        label = (
            f"{titulo} ({n_puntos_cyano})"
            if n_puntos_cyano else f"{titulo} (sin análisis)"
        )
        fg = folium.FeatureGroup(name=label, show=False)
        for p in pts_filtrados:
            alerta = alertas_cyano.get(p["id"])
            if not alerta:
                continue
            nivel_info = alerta.get(clave) or {}
            extra = (
                f"{alerta.get('total_cyano_cel_ml', 0):,.0f} cél/mL"
                if version == "1999"
                else f"{alerta.get('biovolumen_mm3_l', 0):.4f} mm³/L"
            )
            tooltip = (
                f"{p['codigo']} — {nivel_info.get('label','—')} "
                f"(OMS {version}) · {extra}"
            )
            popup_html = (
                f'<div style="font-family:sans-serif;min-width:220px">'
                f'<div style="font-weight:700;color:#1a1a1a">{p["codigo"]}</div>'
                f'<div style="color:#475569;font-size:12px;margin-bottom:6px">'
                f'{p["nombre"]}</div>'
                f'<div style="background:{nivel_info.get("color_bg","#e2e3e5")};'
                f'border-left:4px solid {nivel_info.get("color_borde","#6c757d")};'
                f'padding:6px 10px;border-radius:4px;font-size:12px">'
                f'<b>OMS {version} — {nivel_info.get("label","—")}</b><br>'
                f'cél/mL equiv: {alerta.get("total_cyano_cel_ml",0):,.0f}<br>'
                f'biovolumen: {alerta.get("biovolumen_mm3_l",0):.4f} mm³/L<br>'
                f'colonias/mL: {alerta.get("colonias_ml",0):,.1f} · '
                f'filamentos/mL: {alerta.get("filamentos_ml",0):,.1f}<br>'
                f'<span style="opacity:0.7">Último análisis: '
                f'{alerta.get("ultima_fecha","—")}</span>'
                f'</div></div>'
            )
            folium.CircleMarker(
                location=[p["latitud"], p["longitud"]],
                radius=18 if version == "1999" else 22,
                color=nivel_info.get("color_borde", "#6c757d"),
                weight=3,
                fill=False,
                dash_array=None if version == "1999" else "5,5",
                tooltip=tooltip,
                popup=folium.Popup(popup_html, max_width=340),
            ).add_to(fg)
        return fg

    fg_oms_1999 = _construir_fg_oms("1999", "Alerta OMS 1999 — cél/mL")
    fg_oms_2021 = _construir_fg_oms("2021", "Alerta OMS 2021 — biovolumen")
    fg_oms_1999.add_to(m)
    fg_oms_2021.add_to(m)

    # Guardamos meta en el mapa para mostrar caption en la página.
    m._cyano_meta = {  # type: ignore[attr-defined]
        "n_puntos_con_analisis": n_puntos_cyano,
        "error": cyano_error,
    }

    # Control de capas agrupado: secciones "Mapa base" (radio, exclusivo),
    # "Territorio" (cuencas + red hídrica + represas), "Monitoreo" (puntos)
    # y "Cianobacterias (OMS)". Antes era una lista plana de 8 capas sin
    # jerarquía. Colapsado por defecto para no tapar el mapa al cargar.
    grupos: dict[str, list] = {
        "Mapa base": [tile_calles, tile_satelite],
    }
    territorio: list = [fg for fg in (fg_cuencas, fg_rios, fg_quebradas) if fg is not None]
    territorio.append(fg_poligonos)
    if territorio:
        grupos["Territorio"] = territorio
    grupos["Monitoreo"] = [fg_puntos]
    grupos["Cianobacterias (OMS)"] = [fg_oms_1999, fg_oms_2021]

    GroupedLayerControl(
        groups=grupos,
        exclusive_groups=["Mapa base"],
        collapsed=True,
    ).add_to(m)

    # Leyenda compacta: solo la información que un técnico no puede inferir
    # del mapa. Se quitaron las secciones "Red hídrica" y "Cuencas" porque
    # el color de las líneas y los polígonos ya las identifica visualmente.
    # Se colapsa al click sobre el título para liberar la esquina del mapa.
    leyenda_html = """
    <div id="lvca-legend" style="position:fixed; bottom:18px; left:18px;
         z-index:1000; background:#ffffff; padding:10px 14px;
         border-radius:8px; font-size:11.5px; line-height:1.55;
         min-width:150px;
         box-shadow: 0 4px 16px rgba(15,23,42,0.14),
                     0 1px 3px rgba(15,23,42,0.08);
         font-family:sans-serif;">
      <div onclick="
        var b=document.getElementById('lvca-legend-body');
        var c=document.getElementById('lvca-legend-caret');
        if(b.style.display==='none'){b.style.display='block';c.innerHTML='&#9662;';}
        else{b.style.display='none';c.innerHTML='&#9656;';}
      " style="cursor:pointer; display:flex; align-items:center;
           justify-content:space-between; user-select:none;">
        <div>
          <div style="font-weight:700; color:#1a1a1a; font-size:12.5px;
               letter-spacing:-0.01em;">Estado ECA</div>
          <div style="font-size:10px; color:#94a3b8;">
            D.S. N° 004-2017-MINAM
          </div>
        </div>
        <span id="lvca-legend-caret" style="color:#94a3b8;
             font-size:10px; margin-left:10px;">&#9662;</span>
      </div>
      <div id="lvca-legend-body" style="margin-top:6px;">
        <div style="color:#475569;">
          <span style="color:#2e7d32; font-size:14px;">&#9679;</span> Cumple ECA<br>
          <span style="color:#0a9396; font-size:14px;">&#9679;</span> Excedencia leve<br>
          <span style="color:#e8870e; font-size:14px;">&#9679;</span> Excedencia media<br>
          <span style="color:#c62828; font-size:14px;">&#9679;</span> Excedencia alta<br>
          <span style="color:#9e9e9e; font-size:14px;">&#9679;</span> Sin datos
        </div>
        <div style="font-size:10px; color:#94a3b8; border-top:1px solid #f1f5f9;
             padding-top:5px; margin-top:6px;">
          Radio del marcador = N° parámetros evaluados
        </div>
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda_html))

    return m


# ─────────────────────────────────────────────────────────────────────────────
# 3. GAUGE DE CUMPLIMIENTO POR PUNTO
# ─────────────────────────────────────────────────────────────────────────────

def _render_gauge(punto: dict) -> None:
    """Indicador de cumplimiento ECA — bullet horizontal compacto."""
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

    # Título encima como markdown (antes el title interno del Indicator
    # quedaba cortado a la izquierda en columnas estrechas).
    st.markdown(
        '<div style="font-size:0.72rem; color:#94a3b8; '
        'text-transform:uppercase; letter-spacing:0.05em; '
        'font-weight:600; margin-top:8px;">Cumplimiento ECA</div>',
        unsafe_allow_html=True,
    )

    fig = go.Figure(go.Indicator(
        mode="number+gauge",
        value=pct,
        number={"suffix": "%", "font": {"size": 28, "color": color_principal}},
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
        domain={"x": [0, 1], "y": [0.15, 0.85]},
    ))
    fig.update_layout(
        height=95,
        margin=dict(l=10, r=10, t=10, b=5),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    sub_a, sub_b, sub_c = st.columns(3)
    sub_a.metric("Evaluados", n_eval)
    sub_b.metric("Cumplen", n_ok)
    sub_c.metric("Exceden", n_exc, delta_color="inverse")


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
            "fecha":  info.get("fecha", "—"),
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

    scope = "Último valor por punto en el periodo"
    if campana_label and campana_label != "Todas":
        scope += f" · Campaña: {campana_label}"

    # Anotamos la fecha del dato sobre la barra para que el técnico vea
    # de inmediato si está comparando mediciones de campañas distintas.
    text_labels = [f"{v:.3g}  ({f})" for v, f in zip(df["valor"], df["fecha"])]

    fig = go.Figure(go.Bar(
        y=df["punto"], x=df["valor"],
        orientation="h",
        marker_color=colores,
        text=text_labels,
        textposition="outside", textfont_size=10,
        customdata=df[["nombre", "fecha"]].values,
        hovertemplate=(
            "<b>%{y}</b> — %{customdata[0]}<br>"
            "Valor: %{x:.4g}<br>"
            "Fecha: %{customdata[1]}"
            "<extra></extra>"
        ),
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
    page_header(
        "Geoportal",
        "Vigilancia de Calidad del Agua · LVCA",
        ambito="Cuencas Quilca-Vítor-Chili y Colca-Camaná · AUTODEMA",
    )

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
        solo_exc = st.checkbox(
            "Solo puntos con excedencias",
            key="geo_solo_exc",
            help="Oculta del mapa los puntos que cumplen ECA o sin datos.",
        )
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

    opciones_punto = {f"{p['codigo']} — {p['nombre']}": p for p in puntos_con_coords}
    parametros = get_parametros_selector()

    # ── 1. Dashboard global ─────────────────────────────────────────────
    _render_dashboard(puntos_con_coords)

    st.divider()

    # ── 2. Mapa + panel lateral del punto seleccionado ──────────────────
    # Layout 2 columnas: mapa a la izquierda, ficha del punto a la derecha.
    # El click en el mapa actualiza el selectbox del panel sin scrollear.
    col_mapa, col_panel = st.columns([7, 5], gap="medium")

    with col_mapa:
        mapa = _construir_mapa(puntos_con_coords, solo_exc)
        map_data = st_folium(
            mapa, use_container_width=True, height=620,
            returned_objects=["last_object_clicked"],
        )
        st.caption(
            "Para zoom muy cerrado se recomienda la capa **Calles** — el satélite "
            "Esri no tiene imágenes de alta resolución en zonas altiplánicas "
            "remotas de la cuenca alta del Chili."
        )

        # Estado de la capa "Alerta OMS Cianobacterias" debajo del mapa.
        cyano_meta = getattr(mapa, "_cyano_meta", {}) or {}
        n_cyano = cyano_meta.get("n_puntos_con_analisis", 0)
        cyano_err = cyano_meta.get("error")
        if cyano_err:
            st.caption(
                f":material/warning: Capa Alerta OMS Cianobacterias: error al "
                f"consultar análisis fitoplancton ({cyano_err})."
            )
        elif n_cyano == 0:
            st.caption(
                ":material/info: Capas **Alerta OMS 1999** y **Alerta OMS 2021** "
                "disponibles en el control de capas pero vacías: ningún punto del "
                "filtro tiene análisis Sedgewick-Rafter cargado todavía."
            )
        else:
            st.caption(
                f":material/biotech: **{n_cyano}** punto(s) con análisis "
                "fitoplancton. Activa **OMS 1999** (anillo sólido, densidad celular) "
                "u **OMS 2021** (anillo punteado, biovolumen) en el control de capas."
            )

    # Click en el mapa → actualiza la selección persistente del selectbox
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

    # Panel lateral (col derecha) — ficha del punto
    with col_panel:
        sel_punto_label = st.selectbox(
            "Punto seleccionado",
            list(opciones_punto.keys()),
            key="geo_punto",
            help="Click en un marcador del mapa también cambia esta selección.",
        )
        punto_sel = opciones_punto[sel_punto_label]
        _render_panel_punto(punto_sel)

    st.divider()

    # ── 3. Análisis del punto (ancho completo) ──────────────────────────
    section_header(f"Análisis · {punto_sel['codigo']} — {punto_sel['nombre']}", "analytics")

    # Filtro de categoría sobre el selector de parámetro.
    # Sustituye los antiguos tabs de Campo / Fisicoquímico / Hidrobiológico.
    cat_c1, cat_c2 = st.columns([1, 3])
    with cat_c1:
        categoria_filtro = st.radio(
            "Categoría",
            ["Todas", "Campo", "Fisicoquimico", "Hidrobiologico"],
            horizontal=False,
            key="geo_cat_filtro",
            label_visibility="visible",
        )
    with cat_c2:
        if categoria_filtro == "Todas":
            params_filtrados = parametros
        else:
            params_filtrados = [pr for pr in parametros if _clasificar_cat(pr) == categoria_filtro]

        if not params_filtrados:
            st.warning(f"No hay parámetros en la categoría **{categoria_filtro}**.")
            st.stop()

        opciones_param_filt = {f"{pr['codigo']} — {pr['nombre']}": pr for pr in params_filtrados}
        sel_param_label = st.selectbox(
            "Parámetro a graficar",
            list(opciones_param_filt.keys()),
            key="geo_param",
        )
        param_sel = opciones_param_filt[sel_param_label]

    _render_analisis_punto(
        punto_sel, param_sel, puntos_con_coords,
        str(fecha_inicio), str(fecha_fin), sel_camp,
    )


def _render_panel_punto(punto_sel: dict) -> None:
    """
    Ficha del punto seleccionado para el panel lateral.
    Layout vertical (columna estrecha): header + estado, datos clave en
    lista, bullet ECA y excedencias activas.
    """
    eca_info = punto_sel.get("ecas") or {}
    exc_punto = punto_sel.get("excedencias", [])
    n_exc_punto = len(exc_punto)
    estado_punto = punto_sel.get("estado", "sin_datos")
    color_estado = {
        "excedencia": "#c62828", "cumple": "#2e7d32", "sin_datos": "#9e9e9e",
    }.get(estado_punto, "#9e9e9e")

    from components.ui_styles import estado_pill as _pill
    _pill_key = {
        "excedencia": "excede", "cumple": "cumple", "sin_datos": "sin_dato",
    }.get(estado_punto, "sin_dato")
    estado_html = _pill(_pill_key, dominio="resultado")

    # Header compacto: código + estado en una fila, datos clave en grid 2x3
    # con labels cortos. Antes ocupaba demasiada altura en el panel lateral.
    altitud = punto_sel.get('altitud_msnm', '—')
    altitud_txt = f"{altitud} msnm" if altitud not in (None, "—") else "—"

    utm_e = punto_sel.get("utm_este")
    utm_n = punto_sel.get("utm_norte")
    utm_txt = f"{utm_e:.0f} E · {utm_n:.0f} N" if utm_e and utm_n else "—"

    st.markdown(
        f"""<div style="background:white; border:1px solid #e2e8f0;
             border-left:4px solid {color_estado}; border-radius:10px;
             padding:12px 14px; margin-top:6px;">
            <div style="display:flex; align-items:center; justify-content:space-between;
                 gap:10px; margin-bottom:8px;">
                <div style="font-size:1rem; font-weight:700; color:#1e293b;
                     line-height:1.2; flex:1;">{punto_sel['codigo']}</div>
                <div>{estado_html}</div>
            </div>
            <div style="font-size:0.82rem; color:#475569; margin-bottom:10px;
                 line-height:1.3;">{punto_sel['nombre']}</div>
            <div style="display:grid; grid-template-columns:1fr 1fr;
                 gap:6px 14px; font-size:0.74rem; color:#64748b;
                 line-height:1.45;">
                <div><span style="color:#94a3b8;">Tipo</span><br>
                     <b style="color:#1e293b;">{(punto_sel.get('tipo') or '—').capitalize()}</b></div>
                <div><span style="color:#94a3b8;">ECA aplicable</span><br>
                     <b style="color:#1e293b;">{eca_info.get('codigo', '—')}</b></div>
                <div><span style="color:#94a3b8;">Cuenca</span><br>
                     <b style="color:#1e293b;">{punto_sel.get('cuenca', '—')}</b></div>
                <div><span style="color:#94a3b8;">Sistema hídrico</span><br>
                     <b style="color:#1e293b;">{punto_sel.get('sistema_hidrico', '—')}</b></div>
                <div><span style="color:#94a3b8;">Altitud</span><br>
                     <b style="color:#1e293b;">{altitud_txt}</b></div>
                <div><span style="color:#94a3b8;">Último dato</span><br>
                     <b style="color:#1e293b;">{punto_sel.get('ultima_fecha', '—')}</b></div>
            </div>
            <div style="border-top:1px solid #f1f5f9; padding-top:8px;
                 margin-top:10px; font-size:0.74rem; color:#64748b;">
                <span style="color:#94a3b8;">UTM (Zona 19S)</span><br>
                <b style="color:#1e293b; font-variant-numeric:tabular-nums;">{utm_txt}</b>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )

    _render_gauge(punto_sel)

    if exc_punto:
        label_exc = (
            f"{n_exc_punto} excedencia activa" if n_exc_punto == 1
            else f"{n_exc_punto} excedencias activas"
        )
        with st.expander(label_exc, expanded=True):
            df_exc = pd.DataFrame(exc_punto)
            df_exc["pct_exceso"] = df_exc.apply(
                lambda r: round((r["valor"] / r["lim_max"] - 1) * 100, 1)
                          if r.get("lim_max") and r["lim_max"] > 0 else None,
                axis=1,
            )
            df_show = df_exc[["parametro", "valor", "lim_max", "unidad", "pct_exceso"]].rename(columns={
                "parametro": "Parámetro", "valor": "Valor",
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


def _render_analisis_punto(
    punto_sel: dict, param_sel: dict,
    puntos_con_coords: list[dict],
    fecha_inicio: str, fecha_fin: str,
    campana_label: str,
) -> None:
    """
    Tabs analíticas del punto seleccionado — sin separación por categoría.
    La categoría se filtra arriba en el selector de parámetro.

    Se conservan las 4 vistas:
        1. Tendencia       — evolución temporal del parámetro
        2. Comparar puntos — el mismo parámetro entre todos los puntos
        3. Estacionalidad  — promedio mensual del parámetro en el punto
        4. Estado ECA      — tabla comparativa + últimos resultados
    """
    tab_tend, tab_comp, tab_seas, tab_eca = st.tabs([
        ":material/show_chart: Tendencia",
        ":material/bar_chart: Comparar puntos",
        ":material/calendar_month: Estacionalidad",
        ":material/shield: Estado ECA",
    ])

    with tab_tend:
        _render_tendencia(punto_sel, param_sel, campana_label, cat="all")

    with tab_comp:
        st.caption(
            "Cada barra es el **último valor disponible** del parámetro en cada "
            "punto dentro del rango de fechas. La fecha del dato se muestra en el hover."
        )
        _render_barras_comparativa_puntos(
            puntos_con_coords, param_sel, fecha_inicio, fecha_fin, campana_label, cat="all",
        )

    with tab_seas:
        fecha_fin_dt = date.fromisoformat(fecha_fin)
        anio_sel = st.selectbox(
            "Año a visualizar",
            list(range(fecha_fin_dt.year, fecha_fin_dt.year - 5, -1)),
            key="geo_anio_all",
        )
        limite_eca = get_limite_eca_parametro(punto_sel["id"], param_sel["id"])
        _render_barras_mensuales(punto_sel, param_sel, anio_sel, limite_eca, campana_label, cat="all")

    with tab_eca:
        eca_info = punto_sel.get("ecas") or {}
        st.markdown(
            f"**Comparativa vs ECA** · {eca_info.get('codigo', '')} — {eca_info.get('nombre', '')}"
        )
        datos = get_comparativa_eca_punto(punto_sel["id"], fecha_inicio, fecha_fin)
        if datos:
            _render_comparativa_eca_filtered(datos, cat="all")
        else:
            st.info("Sin datos para este punto en el periodo seleccionado.")

        st.divider()
        section_header("Últimos 15 resultados", "list")
        _render_ultimos_resultados(punto_sel, cat="all")


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
