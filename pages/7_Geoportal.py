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
from components.ui_styles import (
    aplicar_estilos,
    kpi_bold_card,
    page_header,
    section_header,
    success_toast,
    top_nav,
)
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
# Análisis Avanzado — gráficos compactos del panel derecho (Fase B)
# ─────────────────────────────────────────────────────────────────────────────

# Heurística de "indicadores clave" — coinciden por substring en el nombre
# (case-insensitive). Se usa el ORDEN para priorizar al elegir top N.
_INDICADORES_CLAVE = [
    "ph",
    "turbidez",
    "conductividad",
    "oxígeno",
    "dbo5",
    "fósforo",
    "nitratos",
    "coliformes",
]


def _buscar_parametro_por_nombre(parametros: list[dict], aguja: str) -> dict | None:
    """Devuelve el primer parámetro cuyo nombre contiene `aguja` (insensible a tildes/case)."""
    aguja_l = aguja.lower()
    for p in parametros:
        if aguja_l in (p.get("nombre") or "").lower():
            return p
    return None


def _seleccionar_indicadores_clave(parametros: list[dict], n: int = 4) -> list[dict]:
    """
    Para el heatmap del panel derecho — escoge hasta N parámetros que sean
    "indicadores típicos" de calidad de agua (ver _INDICADORES_CLAVE).
    Si no hay match para ninguno, retorna los primeros N de la lista.
    """
    elegidos: list[dict] = []
    vistos: set[str] = set()
    for nombre_pat in _INDICADORES_CLAVE:
        if len(elegidos) >= n:
            break
        p = _buscar_parametro_por_nombre(parametros, nombre_pat)
        if p and p["id"] not in vistos:
            elegidos.append(p)
            vistos.add(p["id"])
    if len(elegidos) < n:
        for p in parametros:
            if len(elegidos) >= n:
                break
            if p["id"] not in vistos:
                elegidos.append(p)
                vistos.add(p["id"])
    return elegidos


def _clasificar_eca(valor: float, lim_min, lim_max) -> int:
    """
    Devuelve un código entero de estado ECA para una celda:
        0 = sin datos
        1 = cumple
        2 = excedencia leve (≤ 30 % fuera de rango)
        3 = excedencia alta (> 30 % fuera de rango)
    """
    if valor is None:
        return 0
    if lim_max is not None and valor > lim_max:
        margen = (valor - lim_max) / lim_max if lim_max > 0 else 1.0
        return 3 if margen > 0.30 else 2
    if lim_min is not None and valor < lim_min:
        if lim_min > 0:
            margen = (lim_min - valor) / lim_min
            return 3 if margen > 0.30 else 2
        return 2
    return 1


def _render_boxplot_anual(punto: dict, parametros: list[dict]) -> None:
    """
    Boxplot compacto de tendencia anual para el panel derecho.
    Usa Turbidez por defecto (mockup); fallback al primer parámetro
    disponible con datos. Sin queries nuevas — usa get_historial_punto
    que ya está cacheada (TTL 180s).
    """
    param = _buscar_parametro_por_nombre(parametros, "turbidez")
    if not param:
        param = _buscar_parametro_por_nombre(parametros, "ph") or (parametros[0] if parametros else None)
    if not param:
        st.caption("Sin parámetros disponibles para Análisis Avanzado.")
        return

    historial = get_historial_punto(punto["id"], param["id"], limite=200)
    if not historial:
        st.caption(
            f"_Sin datos históricos de **{param['nombre']}** en {punto['codigo']}._"
        )
        return

    df = pd.DataFrame(historial)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha", "valor"])
    df["anio"] = df["fecha"].dt.year

    if df.empty or df["anio"].nunique() < 1:
        st.caption(f"_Sin datos suficientes de **{param['nombre']}**._")
        return

    lim = get_limite_eca_parametro(punto["id"], param["id"])
    lim_max = lim.get("valor_maximo")
    lim_min = lim.get("valor_minimo")
    eca_cod = lim.get("eca_codigo", "")
    unidad = (param.get("unidades_medida") or {}).get("simbolo", "")
    y_label = f"{param['nombre']} ({unidad})" if unidad else param["nombre"]

    fig = go.Figure()
    anios_ordenados = sorted(df["anio"].unique())
    for anio in anios_ordenados:
        valores_a = df.loc[df["anio"] == anio, "valor"].tolist()
        fig.add_trace(go.Box(
            y=valores_a,
            x=[str(anio)] * len(valores_a),
            name=str(anio),
            marker_color="#1E6091",
            line_color="#0D47A1",
            fillcolor="rgba(30,96,145,0.30)",
            boxpoints="outliers",
            marker_size=4,
            showlegend=False,
            hovertemplate=(
                f"<b>{anio}</b><br>"
                "Mediana: %{median:.3g}<br>"
                "Q1-Q3: %{q1:.3g}–%{q3:.3g}<br>"
                "Min-Max: %{lowerfence:.3g}–%{upperfence:.3g}"
                "<extra></extra>"
            ),
        ))

    if lim_max is not None:
        fig.add_hline(
            y=lim_max, line_dash="solid", line_color="#EF4444",
            line_width=1.6, opacity=0.85,
            annotation_text=f"Máx ECA: {lim_max}",
            annotation_position="top right",
            annotation_font_size=9, annotation_font_color="#EF4444",
        )
    if lim_min is not None:
        fig.add_hline(
            y=lim_min, line_dash="solid", line_color="#10B981",
            line_width=1.6, opacity=0.85,
            annotation_text=f"Mín ECA: {lim_min}",
            annotation_position="bottom right",
            annotation_font_size=9, annotation_font_color="#10B981",
        )

    fig.update_layout(
        height=240,
        margin=dict(l=40, r=10, t=10, b=30),
        plot_bgcolor="#ffffff",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            title=dict(text="Año", font=dict(size=10, color="#64748b")),
            showgrid=False,
            tickfont=dict(size=10, color="#64748b"),
        ),
        yaxis=dict(
            title=dict(text=y_label, font=dict(size=10, color="#64748b")),
            gridcolor="#f1f5f9",
            zerolinecolor="#e2e8f0",
            tickfont=dict(size=10, color="#64748b"),
        ),
        showlegend=False,
    )

    st.markdown(
        f'<div style="font-size:0.78rem; color:#64748b; margin:4px 0 0 0;">'
        f'Tendencia <b>{param["nombre"]}</b> {punto["codigo"]} '
        f'<span style="color:#94a3b8;">vs ECA {eca_cod}</span></div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        fig, use_container_width=True,
        config={"displayModeBar": False},
        key=f"boxplot_anual_{punto['id']}_{param['id']}",
    )


def _render_heatmap_eca_mensual(punto: dict, parametros: list[dict]) -> None:
    """
    Heatmap compacto: top 4 indicadores clave × últimos 24 meses, coloreado
    por estado ECA del valor mensual promedio. Usa get_historial_punto +
    get_limite_eca_parametro (ambas cacheadas).
    """
    indicadores = _seleccionar_indicadores_clave(parametros, n=4)
    if not indicadores:
        st.caption("Sin indicadores clave disponibles.")
        return

    fecha_fin_dt = date.today()
    n_meses = 18
    meses_x: list[str] = []
    meses_keys: list[tuple[int, int]] = []
    for offset in range(n_meses - 1, -1, -1):
        anio = fecha_fin_dt.year
        mes = fecha_fin_dt.month - offset
        while mes <= 0:
            mes += 12
            anio -= 1
        meses_x.append(f"{MESES[mes-1]}\n{anio}")
        meses_keys.append((anio, mes))

    z_matrix: list[list[int]] = []
    text_matrix: list[list[str]] = []
    y_labels: list[str] = []

    for param in indicadores:
        historial = get_historial_punto(punto["id"], param["id"], limite=200)
        lim = get_limite_eca_parametro(punto["id"], param["id"])
        lim_max = lim.get("valor_maximo")
        lim_min = lim.get("valor_minimo")

        promedios: dict[tuple[int, int], float] = {}
        if historial:
            df = pd.DataFrame(historial)
            df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
            df = df.dropna(subset=["fecha", "valor"])
            df["anio"] = df["fecha"].dt.year
            df["mes"] = df["fecha"].dt.month
            for (a, m), grp in df.groupby(["anio", "mes"]):
                promedios[(int(a), int(m))] = float(grp["valor"].mean())

        fila_z: list[int] = []
        fila_t: list[str] = []
        for key in meses_keys:
            valor = promedios.get(key)
            estado = _clasificar_eca(valor, lim_min, lim_max) if valor is not None else 0
            fila_z.append(estado)
            if valor is None:
                fila_t.append("Sin dato")
            else:
                etq = {1: "Cumple", 2: "Exc. leve", 3: "Exc. alta"}.get(estado, "Sin dato")
                fila_t.append(f"{valor:.3g} · {etq}")

        z_matrix.append(fila_z)
        text_matrix.append(fila_t)
        y_labels.append(param["nombre"])

    # Discrete colorscale: 0=sin dato, 1=cumple, 2=leve, 3=alta
    colorscale = [
        [0.00, "#e2e8f0"],     # 0
        [0.25, "#e2e8f0"],
        [0.26, "#10B981"],     # 1
        [0.50, "#10B981"],
        [0.51, "#F59E0B"],     # 2
        [0.75, "#F59E0B"],
        [0.76, "#EF4444"],     # 3
        [1.00, "#EF4444"],
    ]

    fig = go.Figure(go.Heatmap(
        z=z_matrix,
        x=meses_x,
        y=y_labels,
        text=text_matrix,
        hovertemplate="<b>%{y}</b> · %{x}<br>%{text}<extra></extra>",
        colorscale=colorscale,
        zmin=0, zmax=3,
        showscale=False,
        xgap=2, ygap=2,
    ))

    fig.update_layout(
        height=max(180, len(y_labels) * 38 + 70),
        margin=dict(l=10, r=10, t=10, b=40),
        plot_bgcolor="#ffffff",
        paper_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickfont=dict(size=8.5, color="#64748b"),
            tickangle=-45,
            showgrid=False,
        ),
        yaxis=dict(
            tickfont=dict(size=10, color="#1e293b"),
            showgrid=False,
            automargin=True,
        ),
    )
    st.plotly_chart(
        fig, use_container_width=True,
        config={"displayModeBar": False},
        key=f"heatmap_eca_{punto['id']}",
    )

    # Mini-leyenda inline para el heatmap
    st.markdown(
        '<div style="display:flex; gap:14px; font-size:0.7rem; '
        'color:#64748b; margin:2px 0 8px 0; flex-wrap:wrap;">'
        '<span><span style="display:inline-block; width:10px; height:10px; '
        'background:#10B981; border-radius:2px; margin-right:4px; vertical-align:-1px;"></span>Cumple</span>'
        '<span><span style="display:inline-block; width:10px; height:10px; '
        'background:#F59E0B; border-radius:2px; margin-right:4px; vertical-align:-1px;"></span>Exc. leve</span>'
        '<span><span style="display:inline-block; width:10px; height:10px; '
        'background:#EF4444; border-radius:2px; margin-right:4px; vertical-align:-1px;"></span>Exc. alta</span>'
        '<span><span style="display:inline-block; width:10px; height:10px; '
        'background:#e2e8f0; border-radius:2px; margin-right:4px; vertical-align:-1px;"></span>Sin dato</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. DASHBOARD RESUMEN
# ─────────────────────────────────────────────────────────────────────────────

def _build_sparkline_serie(puntos: list[dict]) -> list[float]:
    """
    Serie sintética para el sparkline del KPI azul "Puntos monitoreados".

    No agregamos queries nuevas (memoria: scope LVCA solo UI). Construimos
    una serie a partir de los índices de cumplimiento individuales de los
    puntos, ordenados de forma estable. Da una "tendencia" visual
    indicativa del estado del set sin pretender ser estadísticamente
    rigurosa — el técnico interpreta el dato real en los KPIs y la barra.
    """
    serie = [
        round((p.get("indice_cumplimiento") or 0) * 100, 1)
        for p in puntos
        if p.get("indice_cumplimiento") is not None
    ]
    if not serie:
        # Fallback: línea plana baja para no dejar el sparkline vacío.
        return [10, 10, 10, 10, 10]
    return serie[:18]


def _render_dashboard(puntos: list[dict]) -> None:
    """
    Resumen ejecutivo: 4 KPIs bold (paleta semántica) + barra de
    cumplimiento general + panel desplegable de alertas críticas.

    Estilo "Integrated Eco-Aura" — tarjetas con fondo sólido en color
    identitario, valor grande contrastado, sparkline en el azul, lista
    de bullets en amarillo y rojo. Funcionalmente equivalente al diseño
    anterior: mismas 4 métricas, mismas queries.
    """
    n_total = len(puntos)
    n_exc = sum(1 for p in puntos if p["estado"] == "excedencia")
    n_ok = sum(1 for p in puntos if p["estado"] == "cumple")
    n_sin = sum(1 for p in puntos if p["estado"] == "sin_datos")

    indices = [p["indice_cumplimiento"] for p in puntos if p.get("indice_cumplimiento") is not None]
    ic_general = round(sum(indices) / len(indices) * 100, 1) if indices else 0

    # Bullets para la tarjeta amarilla (cumplen): hasta 3 puntos con mejor IC.
    cumplen_top = sorted(
        [p for p in puntos if p["estado"] == "cumple"],
        key=lambda x: x.get("indice_cumplimiento", 0),
        reverse=True,
    )[:3]
    bullets_cumplen = [p["codigo"] for p in cumplen_top] if cumplen_top else None

    # Bullets para la tarjeta roja (excedencias): hasta 3 puntos con más excedencias.
    criticos = sorted(
        [p for p in puntos if p["estado"] == "excedencia"],
        key=lambda x: x.get("n_excedencias", 0),
        reverse=True,
    )
    bullets_exc = [
        f"{p['codigo']} — {p['nombre']}" for p in criticos[:3]
    ] if criticos else None

    serie_spark = _build_sparkline_serie(puntos)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            kpi_bold_card(
                valor=n_total,
                label="Puntos monitoreados",
                color="azul",
                icon_material="science",
                foot="Total en el periodo",
                sparkline=serie_spark,
            ),
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            kpi_bold_card(
                valor=n_ok,
                label="Cumplen ECA",
                color="verde",
                icon_material="check_circle",
                bullets=bullets_cumplen,
                foot="D.S. N° 004-2017-MINAM",
            ),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            kpi_bold_card(
                valor=n_exc,
                label="Con excedencias activas",
                color="rojo",
                icon_material="warning",
                bullets=bullets_exc,
                foot="(Click en marcador del mapa para ver detalle)",
            ),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            kpi_bold_card(
                valor=n_sin,
                label="Puntos sin datos",
                color="amarillo",
                icon_material="thermostat",
                foot="Pendientes de campaña en el periodo",
            ),
            unsafe_allow_html=True,
        )

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
    cianobacterias. El HeatMap se eliminó porque duplicaba la información
    cromática de los marcadores (mismo IC, dos canales visuales).
    """
    import folium
    from folium.plugins import MiniMap

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

    # Colapsado por defecto: el panel expandido tapaba una porción grande
    # del mapa. El usuario lo abre solo cuando necesita togglear capas.
    folium.LayerControl(collapsed=True).add_to(m)

    # Leyenda estilo mockup "Integrated Eco-Aura" — esquina inferior derecha,
    # con tres ítems (Cumple / Excedencia Leve / Excedencia Alta) usando
    # íconos vectoriales (círculo verde, triángulo amarillo, círculo rojo).
    # Se mantienen "media" y "sin datos" como filas extra colapsables —
    # son útiles para el técnico AUTODEMA pero no aparecen en el mockup
    # por ser un dashboard ejecutivo.
    leyenda_html = """
    <div id="lvca-legend" style="position:absolute; bottom:18px; right:18px;
         z-index:1000; background:#ffffff; padding:12px 16px;
         border-radius:12px; font-size:12px; line-height:1.6;
         min-width:170px;
         border:1px solid #e2e8f0;
         box-shadow: 0 8px 24px rgba(15,23,42,0.10),
                     0 2px 6px rgba(15,23,42,0.06);
         font-family:'Inter','Segoe UI',sans-serif;">
      <div onclick="
        var b=document.getElementById('lvca-legend-body');
        var c=document.getElementById('lvca-legend-caret');
        if(b.style.display==='none'){b.style.display='block';c.innerHTML='&#9662;';}
        else{b.style.display='none';c.innerHTML='&#9656;';}
      " style="cursor:pointer; display:flex; align-items:center;
           justify-content:space-between; user-select:none;
           padding-bottom:6px; border-bottom:1px solid #f1f5f9;">
        <div>
          <div style="font-weight:700; color:#0f172a; font-size:13px;
               letter-spacing:-0.01em;">Estado ECA</div>
          <div style="font-size:10px; color:#94a3b8; margin-top:1px;">
            D.S. N° 004-2017-MINAM
          </div>
        </div>
        <span id="lvca-legend-caret" style="color:#94a3b8;
             font-size:10px; margin-left:12px;">&#9662;</span>
      </div>
      <div id="lvca-legend-body" style="margin-top:8px; color:#334155;">
        <div style="display:flex; align-items:center; gap:10px; padding:3px 0;">
          <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
            <circle cx="12" cy="12" r="9" fill="#10B981" stroke="#047857" stroke-width="1"/>
          </svg>
          <span style="font-weight:500;">Cumple ECA</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px; padding:3px 0;">
          <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
            <polygon points="12,3 22,21 2,21" fill="#F59E0B" stroke="#B45309" stroke-width="1" stroke-linejoin="round"/>
          </svg>
          <span style="font-weight:500;">Excedencia Leve</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px; padding:3px 0;">
          <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
            <circle cx="12" cy="12" r="9" fill="#EF4444" stroke="#B91C1C" stroke-width="1"/>
            <circle cx="12" cy="12" r="3" fill="#ffffff"/>
          </svg>
          <span style="font-weight:500;">Excedencia Alta</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px; padding:3px 0;
             color:#64748b; font-size:11.5px;">
          <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
            <circle cx="12" cy="12" r="9" fill="#94a3b8" stroke="#64748b" stroke-width="1"/>
          </svg>
          <span>Sin datos</span>
        </div>
        <div style="font-size:10px; color:#94a3b8; border-top:1px solid #f1f5f9;
             padding-top:6px; margin-top:6px;">
          Radio = N° parámetros evaluados
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

    # Toast verde flotante: solo primera vez por sesión, no en cada rerun.
    success_toast(
        "Datos de monitoreo actualizados exitosamente.",
        key="geoportal_load",
    )

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

    # Panel lateral (col derecha) — ficha + Análisis Avanzado (boxplot + heatmap)
    with col_panel:
        sel_punto_label = st.selectbox(
            "Punto seleccionado",
            list(opciones_punto.keys()),
            key="geo_punto",
            help="Click en un marcador del mapa también cambia esta selección.",
        )
        punto_sel = opciones_punto[sel_punto_label]
        _render_panel_punto(punto_sel)

        # ── Análisis Avanzado de Calidad (mockup mockup "Integrated Eco-Aura")
        # Boxplot de Tendencia anual + Heatmap mensual ECA — ambos compactos
        # para caber en la columna estrecha. Contenido siempre visible (no
        # tabs) para que el técnico vea el patrón estacional y outliers de
        # un vistazo, sin clic adicional.
        st.markdown(
            '<div style="margin-top:14px; display:flex; align-items:center; '
            'gap:8px; padding:0 0 6px 0;">'
            '<span class="material-symbols-rounded" '
            'style="font-size:20px; color:#1E6091;">analytics</span>'
            '<span style="font-size:0.95rem; font-weight:700; color:#0F172A; '
            'letter-spacing:-0.01em;">Análisis Avanzado de Calidad</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        _render_boxplot_anual(punto_sel, parametros)

        st.markdown(
            '<div style="margin-top:10px; display:flex; align-items:center; '
            'gap:8px; padding:0 0 4px 0;">'
            '<span class="material-symbols-rounded" '
            'style="font-size:18px; color:#64748b;">grid_on</span>'
            '<span style="font-size:0.85rem; font-weight:600; color:#1e293b;">'
            'Monitoreo Temporal: Cumplimiento ECA por Parámetro</span>'
            '</div>',
            unsafe_allow_html=True,
        )
        _render_heatmap_eca_mensual(punto_sel, parametros)

        st.markdown(
            '<div style="font-size:0.7rem; color:#94a3b8; line-height:1.5; '
            'margin:4px 0 0 0;">'
            '<b>Guía de lectura:</b> el color de la celda indica el estado '
            'promedio del mes según el ECA aplicable.'
            '</div>',
            unsafe_allow_html=True,
        )

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
    Ficha del punto seleccionado — versión integrada (mockup
    "Integrated Eco-Aura"). Tarjeta blanca con bordes redondeados,
    misma sombra y radius que las KPI cards / mapa. Header con gradiente
    sutil + estado pill, body con grid 2×3 de datos clave y UTM al pie
    en ribbon punteado. Estilos en `.lvca-panel-punto` (ui_styles.py).
    """
    eca_info = punto_sel.get("ecas") or {}
    exc_punto = punto_sel.get("excedencias", [])
    n_exc_punto = len(exc_punto)
    estado_punto = punto_sel.get("estado", "sin_datos")

    from components.ui_styles import estado_pill as _pill
    _pill_key = {
        "excedencia": "excede", "cumple": "cumple", "sin_datos": "sin_dato",
    }.get(estado_punto, "sin_dato")
    estado_html = _pill(_pill_key, dominio="resultado")

    altitud = punto_sel.get("altitud_msnm", "—")
    altitud_txt = f"{altitud} msnm" if altitud not in (None, "—") else "—"

    utm_e = punto_sel.get("utm_este")
    utm_n = punto_sel.get("utm_norte")
    utm_txt = f"{utm_e:.0f} E · {utm_n:.0f} N" if utm_e and utm_n else "—"

    st.markdown(
        f"""<div class="lvca-panel-punto">
            <div class="lvca-panel-head">
                <div>
                    <div class="lvca-panel-codigo">{punto_sel['codigo']}</div>
                    <div class="lvca-panel-nombre">{punto_sel['nombre']}</div>
                </div>
                <div>{estado_html}</div>
            </div>
            <div class="lvca-panel-body">
                <div class="lvca-panel-grid">
                    <div>
                        <div class="lbl">Tipo</div>
                        <div class="val">{(punto_sel.get('tipo') or '—').capitalize()}</div>
                    </div>
                    <div>
                        <div class="lbl">ECA aplicable</div>
                        <div class="val">{eca_info.get('codigo', '—')}</div>
                    </div>
                    <div>
                        <div class="lbl">Cuenca</div>
                        <div class="val">{punto_sel.get('cuenca', '—')}</div>
                    </div>
                    <div>
                        <div class="lbl">Sistema hídrico</div>
                        <div class="val">{punto_sel.get('sistema_hidrico', '—')}</div>
                    </div>
                    <div>
                        <div class="lbl">Altitud</div>
                        <div class="val">{altitud_txt}</div>
                    </div>
                    <div>
                        <div class="lbl">Último dato</div>
                        <div class="val">{punto_sel.get('ultima_fecha', '—')}</div>
                    </div>
                </div>
                <div class="lvca-panel-utm">
                    <span style="color:var(--lvca-text-faint); font-size:0.66rem;
                         text-transform:uppercase; letter-spacing:0.04em;
                         font-weight:600;">UTM (Zona 19S)</span><br>
                    <span class="val">{utm_txt}</span>
                </div>
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
