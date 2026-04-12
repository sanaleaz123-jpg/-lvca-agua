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
# Sección 1 — Tarjetas KPI
# ─────────────────────────────────────────────────────────────────────────────

def _render_kpis(metricas: dict) -> None:
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Muestras (30 d)",        metricas["muestras_mes"])
    k2.metric("Parámetros analizados",  metricas["parametros_mes"])
    k3.metric("Excedencias activas",    metricas["excedencias_activas"])
    k4.metric("Puntos monitoreados",    metricas["puntos_monitoreados"])


# ─────────────────────────────────────────────────────────────────────────────
# Sección 2 — Tabla de excedencias
# ─────────────────────────────────────────────────────────────────────────────

def _render_tabla_excedencias(excedencias: list[dict]) -> None:
    st.subheader("Excedencias activas (últimos 30 días)")

    if not excedencias:
        st.success("Sin excedencias ECA en los últimos 30 días.")
        return

    df = pd.DataFrame(excedencias)

    # Calcular % de excedencia
    df["excedencia_pct"] = df.apply(
        lambda r: f"+{((r['valor'] / r['lim_max'] - 1) * 100):.1f}%"
        if r.get("lim_max") and r["lim_max"] > 0
        else ("−{:.1f}%".format((1 - r["valor"] / r["lim_min"]) * 100)
              if r.get("lim_min") and r["lim_min"] > 0 else "—"),
        axis=1,
    )

    df_vista = df[[
        "fecha", "punto_nombre", "eca_codigo",
        "parametro_nombre", "valor", "lim_max", "unidad", "excedencia_pct",
    ]].copy()
    df_vista.columns = [
        "Fecha", "Punto", "ECA",
        "Parámetro", "Valor", "Límite", "Unidad", "Excedencia",
    ]

    st.dataframe(
        df_vista,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Valor":  st.column_config.NumberColumn(format="%.4g"),
            "Límite": st.column_config.NumberColumn(format="%.4g"),
        },
    )
    st.caption(f"{len(excedencias)} resultado(s) que superan los ECA D.S. N° 004-2017-MINAM.")


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
            colorscale=[[0, "#ffc107"], [0.5, "#fd7e14"], [1, "#dc3545"]],
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
            colorscale=[[0, "#17a2b8"], [0.5, "#6f42c1"], [1, "#dc3545"]],
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
    colors = [{"excedencia": "#dc3545", "cumple": "#28a745", "sin_datos": "#6c757d"}.get(k, "#999") for k in estados.keys()]

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

    # Leyenda
    leyenda = """
    <div style="position:fixed; bottom:30px; left:30px; z-index:1000;
         background:white; padding:10px 14px; border-radius:6px;
         border:1px solid #ccc; font-size:13px; line-height:1.6;
         box-shadow: 0 2px 6px rgba(0,0,0,0.15);">
      <b>Estado ECA</b><br>
      <span style="color:red;">&#9679;</span> Excedencia activa<br>
      <span style="color:green;">&#9679;</span> Cumple ECA<br>
      <span style="color:gray;">&#9679;</span> Sin datos recientes
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

    st.title("Panel de Control LVCA")
    st.caption(
        f"AUTODEMA — Cuenca Chili-Quilca  ·  "
        f"Sesión: **{sesion.nombre_completo}** · Rol: `{sesion.rol}`"
    )

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

    # ── Acceso rápido (cards) ────────────────────────────────────────────────
    st.divider()
    st.subheader("Acceso rápido")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        if st.button("Campañas", use_container_width=True):
            st.switch_page("pages/2_Campanas.py")
    with c2:
        if st.button("Resultados Lab", use_container_width=True):
            st.switch_page("pages/4_Resultados_Lab.py")
    with c3:
        if st.button("Informes", use_container_width=True):
            st.switch_page("pages/8_Informes.py")
    with c4:
        if st.button("Geoportal", use_container_width=True):
            st.switch_page("pages/7_Geoportal.py")


main()
