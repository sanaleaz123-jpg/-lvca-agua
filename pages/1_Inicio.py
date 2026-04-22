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
from components.ui_styles import aplicar_estilos, page_header, section_header, top_nav
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
            gap: 14px !important;
            padding: 26px 16px 22px 16px !important;
            background: #ffffff !important;
            border: 1px solid #e8eaed !important;
            border-radius: 10px !important;
            text-align: center !important;
            min-height: 150px !important;
            box-shadow: 0 1px 2px rgba(15,23,42,0.04) !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease,
                        border-color 0.15s ease !important;
            color: #1a1a1a !important;
            font-weight: 600 !important;
            font-size: 0.92rem !important;
            line-height: 1.3 !important;
            white-space: normal !important;
        }
        .st-key-lvca_module_grid [data-testid="stPageLink"] a:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 4px 16px rgba(21,101,192,0.15) !important;
            border-color: #1565C0 !important;
            color: #1565C0 !important;
        }
        /* Primer span dentro del <a> = contenedor del icono (emoji). */
        .st-key-lvca_module_grid [data-testid="stPageLink"] a > span:first-child {
            width: 56px !important;
            height: 56px !important;
            background: rgba(21,101,192,0.08) !important;
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
            background: rgba(21,101,192,0.15) !important;
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
                 background:{halo};
                 display:inline-flex; align-items:center;
                 justify-content:center; flex-shrink:0;">
                <span class="material-symbols-rounded"
                    style="font-size:22px; color:{color}; line-height:1;">{icon}</span>
            </div>
        </div>
        <div style="font-size:1.9rem; font-weight:400;
             color:#1a1a1a; line-height:1; letter-spacing:-0.02em;">{valor}</div>
    </div>"""


def _render_kpis(metricas: dict) -> None:
    cards = [
        {"valor": metricas["muestras_mes"],
         "label": "Muestras (30 d)",
         "color": "#0A9396", "icon": "science"},
        {"valor": metricas["parametros_mes"],
         "label": "Parámetros analizados",
         "color": "#00796B", "icon": "analytics"},
        {"valor": metricas["excedencias_activas"],
         "label": "Excedencias activas",
         "color": "#C62828", "icon": "warning"},
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
    st.subheader("Excedencias activas (últimos 30 días)")

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


# ─────────────────────────────────────────────────────────────────────────────
# Sección 3 — Gráficos de excedencias
# ─────────────────────────────────────────────────────────────────────────────

def _render_grafico_excedencias(excedencias: list[dict]) -> None:
    st.subheader("Parámetros con más excedencias ECA")

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
    st.subheader("Puntos con más excedencias")

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
            colorscale=[[0, "#0a9396"], [0.5, "#1b6b35"], [1, "#c62828"]],
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
    colors = [{"excedencia": "#c62828", "cumple": "#2e7d32", "sin_datos": "#9e9e9e"}.get(k, "#999") for k in estados.keys()]

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
    st.subheader("Mapa de puntos de muestreo")

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
    leyenda = """
    <div style="position:fixed; bottom:24px; left:24px; z-index:1000;
         background:#ffffff; padding:12px 16px; border-radius:8px;
         font-size:12px; line-height:1.55; min-width:160px;
         box-shadow: 0 4px 16px rgba(15,23,42,0.14),
                     0 1px 3px rgba(15,23,42,0.08);
         font-family:sans-serif;">
      <div style="font-weight:700; color:#1a1a1a; font-size:13px;
           letter-spacing:-0.01em; margin-bottom:6px;">Estado ECA</div>
      <div style="color:#475569;">
        <span style="color:#c62828; font-size:14px;">&#9679;</span> Excedencia activa<br>
        <span style="color:#2e7d32; font-size:14px;">&#9679;</span> Cumple ECA<br>
        <span style="color:#9e9e9e; font-size:14px;">&#9679;</span> Sin datos recientes
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

        barra_color = {"excedencia": "#dc3545", "cumple": "#28a745", "sin_datos": "#6c757d"}.get(estado, "#6c757d")

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

    # ── 0. Acceso a módulos (grilla SSDH-ANA) ───────────────────────────────
    _render_module_grid()
    st.divider()

    # ── Cargar datos ─────────────────────────────────────────────────────────
    with st.spinner("Cargando métricas..."):
        try:
            metricas = get_metricas_dashboard(dias=30)
            puntos   = get_puntos_con_estado(dias=30)
        except Exception as exc:
            st.error(f"Error al cargar datos del dashboard: {exc}")
            st.stop()

    excedencias = metricas["excedencias_lista"]

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


def _render_tareas_pendientes() -> None:
    """
    Lista de tareas operacionales que el usuario debería atender ahora,
    en lugar de los genéricos botones de 'Acceso rápido'. Cada item lleva
    a la página exacta donde se resuelve.
    """
    from database.client import get_admin_client
    from components.ui_styles import section_header, icon, COLORS
    db = get_admin_client()

    section_header("Tareas pendientes", "list")

    items: list[dict] = []

    # 1. Campañas en curso (en_campo o en_laboratorio)
    try:
        camp_curso = (
            db.table("campanas")
            .select("codigo, nombre, estado")
            .in_("estado", ["en_campo", "en_laboratorio"])
            .order("fecha_inicio", desc=True)
            .limit(50)
            .execute()
            .data or []
        )
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
    except Exception:
        pass

    # 2. Muestras analizadas/recibidas sin resultados completos
    try:
        muestras_lab = (
            db.table("muestras")
            .select("id, codigo, estado")
            .in_("estado", ["en_laboratorio", "analizada"])
            .limit(200)
            .execute()
            .data or []
        )
        if muestras_lab:
            items.append({
                "icon": "beaker",
                "color": COLORS["secondary"],
                "title": f"{len(muestras_lab)} muestra(s) en laboratorio",
                "detail": "Muestras recibidas o en análisis pendientes de cierre.",
                "page": "pages/4_Resultados_Lab.py",
                "cta": "Cargar resultados",
            })
    except Exception:
        pass

    # 3. Resultados sin validar (si la migración 006 está aplicada)
    try:
        sin_validar = (
            db.table("resultados_laboratorio")
            .select("id", count="exact")
            .eq("validado", False)
            .not_.is_("valor_numerico", "null")
            .limit(1)
            .execute()
        )
        n_sin_val = sin_validar.count or 0
        if n_sin_val > 0:
            items.append({
                "icon": "shield",
                "color": COLORS["warning"],
                "title": f"{n_sin_val} resultado(s) sin validar",
                "detail": "Resultados ingresados pero no firmados por supervisor.",
                "page": "pages/4_Resultados_Lab.py",
                "cta": "Validar resultados",
            })
    except Exception:
        pass

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
