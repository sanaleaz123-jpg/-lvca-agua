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
from components.ui_styles import aplicar_estilos, page_header, section_header
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
    from components.ui_styles import inline_note, excede_pill, estado_pill
    st.subheader("Excedencias activas (últimos 30 días)")

    if not excedencias:
        inline_note(
            "Sin excedencias ECA en los últimos 30 días — todos los puntos cumplen.",
            tipo="success",
        )
        return

    inline_note(
        f"<b>{len(excedencias)} resultado(s)</b> superan los ECA "
        f"D.S. N° 004-2017-MINAM en los últimos 30 días.",
        tipo="warn",
    )

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

    aplicar_estilos()
    page_header(
        "Panel de Control LVCA",
        f"AUTODEMA — Cuenca Chili-Quilca &middot; {sesion.nombre_completo}",
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
            st.markdown(
                f"""<div class="lvca-card" style="text-align:left;">
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:8px;">
                        <span style="color:{item['color']};">{icon(item['icon'], 22, item['color'])}</span>
                        <span style="font-weight:700; color:#1e293b; font-size:0.95rem;">
                            {item['title']}
                        </span>
                    </div>
                    <div style="font-size:0.82rem; color:#64748b; margin-bottom:14px; min-height:2.6em;">
                        {item['detail']}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.page_link(item["page"], label=f"→ {item['cta']}")


main()
