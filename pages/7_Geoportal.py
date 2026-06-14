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
from components.nav_context import consumir_contexto, ir_a
from components.ui_styles import (
    COLORS,
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
    get_limites_eca_parametro_todos,
    get_parametros_selector,
    get_puntos_geoportal,
    get_ultimo_valor_parametro_por_punto,
    get_ultimos_resultados_punto,
)
from services.resultado_service import get_campanas, get_puntos_de_campana
from services.fitoplancton_service import (
    get_alertas_oms_por_punto,
    get_phyllum_dominante_punto,
)


# ─────────────────────────────────────────────────────────────────────────────
# Paleta de zonas ECA por categoría (Modo Campaña — chart comparativo)
# ─────────────────────────────────────────────────────────────────────────────
# Coincide con la referencia visual del usuario: cada zona es el rectángulo
# (lim_min → lim_max) dibujado detrás del valor del punto, coloreado según
# la categoría ECA de ESE punto. Solo 4 categorías + fallback "sin_eca".
ECA_CATEGORIA_COLORES: dict[str, dict[str, str]] = {
    "1 A2": {"fill": "#A7F3D0", "stroke": "#10B981"},   # verde menta
    "3 D1": {"fill": "#FED7AA", "stroke": "#EA580C"},   # naranja claro
    "4 E1": {"fill": "#E9D5FF", "stroke": "#7C3AED"},   # lavanda
    "4 E2": {"fill": "#BAE6FD", "stroke": "#0284C7"},   # celeste
}
ECA_FALLBACK = {"fill": "#E5E7EB", "stroke": "#94A3B8"}


def _color_zona_eca(eca_codigo: str) -> dict[str, str]:
    """Devuelve el dict {fill, stroke} para una categoría ECA. Match flexible."""
    if not eca_codigo:
        return ECA_FALLBACK
    cod = eca_codigo.strip().upper().replace("  ", " ")
    for clave, paleta in ECA_CATEGORIA_COLORES.items():
        if clave.upper() == cod:
            return paleta
    return ECA_FALLBACK


# ─────────────────────────────────────────────────────────────────────────────
# Paleta de phyllums fitoplancton — coloreo del dot/marker en charts
# hidrobiológicos. La búsqueda es por substring case-insensitive en el
# nombre/código del parámetro.
# ─────────────────────────────────────────────────────────────────────────────
PHYLLUM_COLORES: list[tuple[str, str]] = [
    # (substring a buscar, color hex)
    ("cianobacter", "#0D9488"),   # verde-azul (teal)
    ("cyano",       "#0D9488"),
    ("bacillario",  "#92400E"),   # marrón
    ("diatomea",    "#92400E"),
    ("clorof",      "#16A34A"),   # verde
    ("chlorophy",   "#16A34A"),
    ("ochrop",      "#EAB308"),   # amarillo
    ("ocrof",       "#EAB308"),
    ("cryptof",     "#06B6D4"),   # celeste (cyan)
    ("cryptoph",    "#06B6D4"),
    ("euglen",      "#EC4899"),   # rosa
    ("dinofla",     "#7C3AED"),   # morado
    ("rhodophy",    "#DC2626"),   # rojo (algas rojas)
    ("rodof",       "#DC2626"),
]
PHYLLUM_DEFAULT_COLOR = "#64748B"  # slate gris fallback


def _color_phyllum(parametro: dict) -> str:
    """Color del dot/línea para un parámetro hidrobiológico según phyllum."""
    busca = (
        f"{parametro.get('nombre','') or ''} "
        f"{parametro.get('codigo','') or ''}"
    ).lower()
    for clave, color in PHYLLUM_COLORES:
        if clave in busca:
            return color
    return PHYLLUM_DEFAULT_COLOR


def _display_nombre_parametro(parametro: dict) -> str:
    """Nombre user-friendly del parámetro. Normaliza Cyanobacteria/Cyanophyta
    → 'Cianobacteria' a nivel de plataforma para consistencia visual."""
    nombre = parametro.get("nombre") or ""
    nl = nombre.lower()
    if "cyano" in nl or "cianobacter" in nl:
        return "Cianobacteria"
    return nombre


def _es_cianobacteria(parametro: dict) -> bool:
    """True si el parámetro corresponde a cianobacterias (por nombre o código)."""
    busca = (
        f"{parametro.get('nombre','') or ''} "
        f"{parametro.get('codigo','') or ''}"
    ).lower()
    return ("cyano" in busca) or ("cianobacter" in busca)


def _es_hidrobiologico(parametro: dict) -> bool:
    """True si el parámetro está en la categoría Hidrobiológico."""
    return _clasificar_cat(parametro) == "Hidrobiologico"


def _oms_bandas_cianobacteria(parametro: dict) -> list[dict]:
    """
    Devuelve las bandas horizontales OMS para cianobacterias según la unidad
    del parámetro:
        - cel/mL → OMS 1999, Drinking-water Alert Levels Framework
        - mm³/L  → OMS 2021, biovolumen para agua recreativa

    Cada banda: {lo, hi, color, label}. `hi` puede ser None (banda superior).
    Los colores siguen las filas de la tabla oficial OMS:
        verde menta = vigilancia / nivel inicial
        amarillo    = alerta 1
        rojo        = alerta 2
    """
    unidad = ((parametro.get("unidades_medida") or {}).get("simbolo") or "").lower()
    if any(t in unidad for t in ("cel/ml", "cel.ml", "cel·ml", "cel ml")):
        return [
            {"lo": 200,    "hi": 2000,   "color": "#A7F3D0",
             "stroke": "#10B981", "label": "Vigilancia (>200 cél/mL)"},
            {"lo": 2000,   "hi": 100000, "color": "#FDE68A",
             "stroke": "#F59E0B", "label": "Alerta 1 (≥2000 cél/mL)"},
            {"lo": 100000, "hi": None,   "color": "#FECACA",
             "stroke": "#EF4444", "label": "Alerta 2 (>100 000 cél/mL)"},
        ]
    if "mm" in unidad and ("3" in unidad or "³" in unidad):
        return [
            {"lo": 0,    "hi": 0.3,  "color": "#A7F3D0",
             "stroke": "#10B981", "label": "Vigilancia (<0.3 mm³/L)"},
            {"lo": 0.3,  "hi": 4.0,  "color": "#FDE68A",
             "stroke": "#F59E0B", "label": "Alerta 1 (0.3-4.0 mm³/L)"},
            {"lo": 4.0,  "hi": None, "color": "#FECACA",
             "stroke": "#EF4444", "label": "Alerta 2 (≥4.0 mm³/L)"},
        ]
    return []


def _format_valor(v) -> str:
    """Formatea un número sin notación científica.

    Reglas:
        |v| ≥ 10 000 → entero con separador de miles ("100,000")
        |v| ≥ 100   → 1 decimal ("1,060.5", trailing zeros stripped)
        |v| ≥ 1     → 3 cifras significativas ("7.44")
        |v| < 1     → 4 decimales ("0.0123")
    """
    if v is None:
        return "—"
    av = abs(v)
    if av >= 10000:
        return f"{v:,.0f}"
    if av >= 100:
        s = f"{v:,.1f}"
        return s.rstrip("0").rstrip(".") if "." in s else s
    if av >= 1:
        return f"{v:.3g}"
    return f"{v:.4f}".rstrip("0").rstrip(".")


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
# Análisis Avanzado — gráfico compacto del panel derecho (Fase B)
# ─────────────────────────────────────────────────────────────────────────────


def _buscar_parametro_por_nombre(parametros: list[dict], aguja: str) -> dict | None:
    """Devuelve el primer parámetro cuyo nombre contiene `aguja` (insensible a tildes/case)."""
    aguja_l = aguja.lower()
    for p in parametros:
        if aguja_l in (p.get("nombre") or "").lower():
            return p
    return None


def _render_barras_tendencia_anual(punto: dict, parametros: list[dict]) -> None:
    """
    Gráfico de barras anual del panel derecho — se actualiza cada vez que
    cambia el punto seleccionado. Cada barra es el promedio anual del
    parámetro (Turbidez por defecto, fallback pH → primer disponible).

    Coloreo semántico por barra:
        - Verde (#10B981)  si el promedio cumple el ECA aplicable
        - Rojo  (#EF4444)  si excede el límite máximo del ECA
        - Ámbar (#F59E0B)  si está por debajo del mínimo del ECA

    Líneas horizontales de referencia: ECA máx (rojo dashed), ECA mín
    (verde dashed). Sin queries nuevas — usa get_historial_punto +
    get_limite_eca_parametro (ambas cacheadas).
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

    if df.empty:
        st.caption(f"_Sin datos suficientes de **{param['nombre']}**._")
        return

    df_agg = (
        df.groupby("anio", as_index=False)
        .agg(promedio=("valor", "mean"), n=("valor", "count"))
        .sort_values("anio")
    )

    lim = get_limite_eca_parametro(punto["id"], param["id"])
    lim_max = lim.get("valor_maximo")
    lim_min = lim.get("valor_minimo")
    eca_cod = lim.get("eca_codigo", "")

    colores = []
    for v in df_agg["promedio"]:
        if lim_max is not None and v > lim_max:
            colores.append(COLORS["eca_excede"])    # excede ECA máx
        elif lim_min is not None and v < lim_min:
            colores.append(COLORS["eca_alerta"])    # debajo ECA mín
        else:
            colores.append(COLORS["eca_cumple"])    # cumple

    unidad = (param.get("unidades_medida") or {}).get("simbolo", "")
    y_label = f"{param['nombre']} ({unidad})" if unidad else param["nombre"]

    fig = go.Figure(go.Bar(
        x=df_agg["anio"].astype(str),
        y=df_agg["promedio"],
        marker_color=colores,
        marker_line_color="#0F172A",
        marker_line_width=0.6,
        text=[f"{v:.3g}" for v in df_agg["promedio"]],
        textposition="outside",
        textfont=dict(size=10, color="#1e293b"),
        customdata=df_agg["n"],
        hovertemplate=(
            f"<b>%{{x}}</b><br>"
            f"{param['nombre']}: %{{y:.4g}}<br>"
            f"N° mediciones: %{{customdata}}"
            f"<extra></extra>"
        ),
        width=0.55,
    ))

    if lim_max is not None:
        fig.add_hline(
            y=lim_max, line_dash="dash", line_color=COLORS["eca_excede"],
            line_width=1.6, opacity=0.85,
            annotation_text=f"Máx ECA: {lim_max}",
            annotation_position="top right",
            annotation_font_size=9, annotation_font_color=COLORS["eca_excede"],
        )
    if lim_min is not None:
        fig.add_hline(
            y=lim_min, line_dash="dash", line_color=COLORS["eca_cumple"],
            line_width=1.6, opacity=0.85,
            annotation_text=f"Mín ECA: {lim_min}",
            annotation_position="bottom right",
            annotation_font_size=9, annotation_font_color=COLORS["eca_cumple"],
        )

    fig.update_layout(
        height=240,
        margin=dict(l=40, r=10, t=20, b=30),
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
        bargap=0.30,
    )

    st.markdown(
        f'<div style="font-size:0.78rem; color:#64748b; margin:4px 0 0 0;">'
        f'Promedio anual de <b>{param["nombre"]}</b> en {punto["codigo"]} '
        f'<span style="color:#94a3b8;">vs ECA {eca_cod}</span></div>',
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        fig, use_container_width=True,
        config={"displayModeBar": False},
        key=f"barras_anual_{punto['id']}_{param['id']}",
    )

    # Mini-leyenda inline (3 chips)
    st.markdown(
        '<div style="display:flex; gap:14px; font-size:0.7rem; '
        'color:#64748b; margin:2px 0 4px 0; flex-wrap:wrap;">'
        '<span><span style="display:inline-block; width:10px; height:10px; '
        'background:#10B981; border-radius:2px; margin-right:4px; vertical-align:-1px;"></span>Cumple ECA</span>'
        '<span><span style="display:inline-block; width:10px; height:10px; '
        'background:#F59E0B; border-radius:2px; margin-right:4px; vertical-align:-1px;"></span>Bajo ECA mín</span>'
        '<span><span style="display:inline-block; width:10px; height:10px; '
        'background:#EF4444; border-radius:2px; margin-right:4px; vertical-align:-1px;"></span>No cumple ECA</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Modo Campaña — gráfico comparativo (dots + zonas ECA por punto)
# ─────────────────────────────────────────────────────────────────────────────


def _render_grafico_campana_comparativo(
    campana: dict,
    parametro: dict,
    puntos: list[dict],
    fi_buscar: str | None = None,
    ff_buscar: str | None = None,
) -> None:
    """
    Chart comparativo del Modo Campaña. Casos:

    1. Físico-químico/Campo con ECA → para cada punto se dibuja la zona
       (rectángulo) entre lim_min y lim_max del ECA aplicable. Dot rojo si
       excede, azul si cumple, gris si sin ECA. Anotaciones de límites.

    2. Cianobacteria → bandas horizontales globales OMS (1999 cel/mL o
       2021 mm³/L). NO zonas por punto. Dot color verde-azul.

    3. Otros hidrobiológicos (no cianobacteria) → sin zonas, sin líneas.
       Dot color del phyllum (marrón Bacillariophyta, verde Clorofitas,
       amarillo Ochrophyta, celeste Cryptofitas, etc).

    4. Temperatura → sin ECA (DS define un Δ, no valor absoluto). Dots
       grises con caption explicativo.
    """
    if not puntos:
        st.info("La campaña seleccionada no tiene puntos asociados.")
        return

    fi = fi_buscar or (campana.get("fecha_inicio") or "")[:10]
    ff = ff_buscar or (campana.get("fecha_fin") or "")[:10]
    if not fi or not ff:
        st.warning("La campaña no tiene fechas de inicio/fin definidas.")
        return

    ultimos = get_ultimo_valor_parametro_por_punto(
        parametro["id"], fi, ff, campana_id=campana.get("id"),
    )

    # ── Detección de tipo de parámetro
    es_temp = _es_temperatura(parametro)
    es_hb   = _es_hidrobiologico(parametro)
    es_cyano = _es_cianobacteria(parametro)
    bandas_oms = _oms_bandas_cianobacteria(parametro) if es_cyano else []

    # En hidrobiológicos (excepto cianobacteria) NO hay ECA. En cianobacteria
    # tampoco hay ECA por punto — usamos OMS global. En Temperatura tampoco.
    aplicar_eca_por_punto = not (es_hb or es_temp)

    # Límites del parámetro para todos los puntos en una sola pasada
    # (antes: 2 queries por punto dentro del loop).
    limites_todos = get_limites_eca_parametro_todos(parametro["id"]) if aplicar_eca_por_punto else {}

    items: list[dict] = []
    for p in puntos:
        info = ultimos.get(p["id"]) or {}
        lim = limites_todos.get(p["id"], {}) if aplicar_eca_por_punto else {}
        eca_cod = (
            ((p.get("ecas") or {}).get("codigo") or lim.get("eca_codigo", ""))
            if aplicar_eca_por_punto else ""
        )
        items.append({
            "codigo":   p.get("codigo", ""),
            "nombre":   p.get("nombre", ""),
            "valor":    info.get("valor"),
            "fecha":    info.get("fecha"),
            "lim_min":  lim.get("valor_minimo") if aplicar_eca_por_punto else None,
            "lim_max":  lim.get("valor_maximo") if aplicar_eca_por_punto else None,
            "eca_cod":  (eca_cod or "").strip() if aplicar_eca_por_punto else "",
        })

    # Calcular extremos del eje Y. Y MIN = 0 SIEMPRE (no hay valores
    # negativos en parámetros LVCA — fix solicitado por el usuario).
    todos_lim_max = [i["lim_max"] for i in items if i["lim_max"] is not None]
    todos_lim_min = [i["lim_min"] for i in items if i["lim_min"] is not None]
    todos_valores = [i["valor"]   for i in items if i["valor"]   is not None]

    universo = todos_lim_max + todos_lim_min + todos_valores
    # Si es cianobacteria, considerar también los thresholds OMS para el rango
    if bandas_oms:
        for b in bandas_oms:
            if b["lo"] is not None:
                universo.append(b["lo"])
            if b["hi"] is not None:
                universo.append(b["hi"])

    if not universo:
        st.info(
            f"Sin datos ni límites para **{_display_nombre_parametro(parametro)}** "
            f"en los puntos de **{campana['codigo']}**."
        )
        return

    y_max_data = max(universo)
    pad_top = y_max_data * 0.18 if y_max_data > 0 else 1.0
    y_lo = 0.0
    y_hi = y_max_data + pad_top

    fig = go.Figure()
    shapes = []
    annotations = []

    # ── Caso A: Cianobacteria → bandas horizontales globales OMS
    if bandas_oms:
        for b in bandas_oms:
            b_hi = b["hi"] if b["hi"] is not None else y_hi
            shapes.append(dict(
                type="rect",
                xref="paper", yref="y",
                x0=0, x1=1,
                y0=b["lo"], y1=b_hi,
                fillcolor=b["color"], opacity=0.55,
                line=dict(width=0),
                layer="below",
            ))
            # Línea horizontal en el TOP de cada banda (excepto la superior)
            if b["hi"] is not None:
                shapes.append(dict(
                    type="line",
                    xref="paper", yref="y",
                    x0=0, x1=1,
                    y0=b_hi, y1=b_hi,
                    line=dict(color=b["stroke"], width=1.4, dash="dash"),
                    layer="below",
                ))
            # Anotación a la derecha del chart
            y_pos = (b["lo"] + b_hi) / 2 if b["hi"] is not None else (b["lo"] + b["lo"] * 0.2 + 1)
            annotations.append(dict(
                x=1.0, y=y_pos,
                xref="paper", yref="y",
                text=f"<b>{b['label']}</b>",
                showarrow=False,
                xanchor="right",
                font=dict(size=9, color=b["stroke"]),
            ))

    # ── Caso B: Físico-químico/Campo con ECA → zonas por punto
    elif aplicar_eca_por_punto:
        for idx, it in enumerate(items):
            tiene_lim = (it["lim_min"] is not None) or (it["lim_max"] is not None)
            if tiene_lim:
                col = _color_zona_eca(it["eca_cod"])
                z_lo = it["lim_min"] if it["lim_min"] is not None else y_lo
                z_hi = it["lim_max"] if it["lim_max"] is not None else y_hi

                shapes.append(dict(
                    type="rect",
                    xref="x", yref="y",
                    x0=idx - 0.40, x1=idx + 0.40,
                    y0=z_lo, y1=z_hi,
                    fillcolor=col["fill"], opacity=0.30,
                    line=dict(color=col["stroke"], width=1),
                    layer="below",
                ))
                # Anotaciones ancladas al borde IZQUIERDO del rectángulo y
                # DENTRO de él — antes iban centradas encima/debajo del
                # límite y se solapaban con el valor del punto (que va
                # centrado sobre el dot).
                if it["lim_max"] is not None:
                    annotations.append(dict(
                        x=idx - 0.38, y=it["lim_max"],
                        xref="x", yref="y",
                        text=f"{it['eca_cod'] or '—'} = {_format_valor(it['lim_max'])}",
                        showarrow=False,
                        xanchor="left", yanchor="top",
                        yshift=-2,
                        font=dict(size=8.5, color=col["stroke"]),
                    ))
                if it["lim_min"] is not None:
                    annotations.append(dict(
                        x=idx - 0.38, y=it["lim_min"],
                        xref="x", yref="y",
                        text=f"{it['eca_cod'] or '—'} = {_format_valor(it['lim_min'])}",
                        showarrow=False,
                        xanchor="left", yanchor="bottom",
                        yshift=2,
                        font=dict(size=8.5, color=col["stroke"]),
                    ))

    # ── Color del dot
    color_phyllum_unico = _color_phyllum(parametro) if (es_hb or es_cyano) else None

    def _color_dot(it: dict) -> str:
        if it["valor"] is None:
            return "#94A3B8"
        # Hidrobiológicos (incluyendo cyano) → color del phyllum, fijo
        if color_phyllum_unico is not None:
            return color_phyllum_unico
        # Físico-químicos: rojo no cumple / azul cumple / gris sin ECA
        if it["lim_min"] is None and it["lim_max"] is None:
            return "#94A3B8"
        if (it["lim_max"] is not None and it["valor"] > it["lim_max"]) or \
           (it["lim_min"] is not None and it["valor"] < it["lim_min"]):
            return "#EF4444"
        return "#2563EB"

    # ── Trace dots
    x_vals = [it["codigo"] for it in items]
    y_vals = [it["valor"] for it in items]
    text_vals = [_format_valor(it["valor"]) if it["valor"] is not None else "—" for it in items]
    text_vals_b = [f"<b>{t}</b>" for t in text_vals]
    colores_dot = [_color_dot(it) for it in items]

    unidad = (parametro.get("unidades_medida") or {}).get("simbolo", "")
    nombre_dis = _display_nombre_parametro(parametro)

    hover_lines = []
    for it in items:
        if it["valor"] is None:
            hover_lines.append(
                f"<b>{it['codigo']}</b> — {it['nombre']}<br>"
                f"Sin medición de {nombre_dis} en esta campaña.<br>"
                + (f"ECA: {it['eca_cod'] or 'sin categoría'}" if aplicar_eca_por_punto else "")
            )
        else:
            base = (
                f"<b>{it['codigo']}</b> — {it['nombre']}<br>"
                f"Valor: {_format_valor(it['valor'])} {unidad}"
            )
            if aplicar_eca_por_punto:
                eca_txt = (
                    f"<br>ECA: {it['eca_cod'] or 'sin categoría'}"
                    + (
                        f" (mín {_format_valor(it['lim_min'])} / máx {_format_valor(it['lim_max'])})"
                        if (it["lim_min"] is not None and it["lim_max"] is not None) else
                        f" (máx {_format_valor(it['lim_max'])})" if it["lim_max"] is not None else
                        f" (mín {_format_valor(it['lim_min'])})" if it["lim_min"] is not None else ""
                    )
                )
                base += eca_txt
            elif bandas_oms:
                base += "<br>Estándar: OMS (cianobacterias)"
            elif es_hb:
                base += "<br>Hidrobiológico — sin ECA aplicable"
            base += f"<br>Fecha de muestreo: {it['fecha'] or '—'}"
            hover_lines.append(base)

    fig.add_trace(go.Scatter(
        x=x_vals,
        y=[v if v is not None else None for v in y_vals],
        mode="markers+text",
        marker=dict(
            size=12, color=colores_dot,
            line=dict(color="#0F172A", width=1.2),
        ),
        text=text_vals_b,
        textposition="top center",
        textfont=dict(size=10, color="#1E293B"),
        hovertext=hover_lines,
        hovertemplate="%{hovertext}<extra></extra>",
        showlegend=False,
    ))

    y_label = f"{nombre_dis} ({unidad})" if unidad else nombre_dis

    fig.update_layout(
        title=dict(
            text=f"<b>{nombre_dis}</b>" + (f" ({unidad})" if unidad else ""),
            x=0.5, xanchor="center",
            font=dict(size=14, color="#0F172A"),
        ),
        height=340,
        margin=dict(l=50, r=140 if bandas_oms else 20, t=50, b=80),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="rgba(0,0,0,0)",
        shapes=shapes,
        annotations=annotations,
        xaxis=dict(
            tickangle=-45,
            tickfont=dict(size=10, color="#1E293B"),
            showgrid=False,
            zeroline=False,
        ),
        yaxis=dict(
            title=dict(text=y_label, font=dict(size=10, color="#64748b")),
            range=[y_lo, y_hi],
            rangemode="tozero",
            gridcolor="#F1F5F9",
            zeroline=True, zerolinecolor="#E2E8F0",
            tickfont=dict(size=10, color="#64748b"),
            exponentformat="none",
            separatethousands=True,
        ),
        showlegend=False,
    )

    st.plotly_chart(
        fig, use_container_width=True,
        config={"displayModeBar": False},
        key=f"chart_camp_{campana['id']}_{parametro['id']}",
    )

    # Leyenda contextual según el caso del chart
    leyenda_html = (
        '<div style="border-top:1px solid #f1f5f9; padding-top:8px; margin-top:4px;">'
        '<div style="font-size:0.72rem; color:#94a3b8; '
        'text-transform:uppercase; letter-spacing:0.05em; '
        'font-weight:600; margin-bottom:4px;">Cómo leer el gráfico</div>'
    )

    if bandas_oms:
        # Cianobacteria — leyenda OMS
        chips_oms = "".join(
            f'<span style="display:inline-flex; align-items:center; gap:5px; '
            f'font-size:0.72rem; color:#475569;">'
            f'<span style="display:inline-block; width:14px; height:10px; '
            f'background:{b["color"]}; opacity:0.65; '
            f'border:1px solid {b["stroke"]}; border-radius:3px;"></span>'
            f'{b["label"]}</span>'
            for b in bandas_oms
        )
        unidad = ((parametro.get("unidades_medida") or {}).get("simbolo") or "").lower()
        fuente = (
            "OMS 1999 (Drinking-water Alert Levels Framework)"
            if "cel" in unidad else
            "OMS 2021 (biovolumen — agua recreativa)"
        )
        leyenda_html += (
            f'<div style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:4px;">'
            '<span style="display:inline-flex; align-items:center; gap:5px; '
            'font-size:0.72rem; color:#475569;">'
            f'<span style="display:inline-block; width:11px; height:11px; '
            f'background:{_color_phyllum(parametro)}; border-radius:50%; '
            'border:1px solid #0F172A;"></span>'
            'Cianobacteria</span>'
            f'{chips_oms}'
            '</div>'
            f'<div style="font-size:0.68rem; color:#94a3b8;">'
            f'Bandas globales según {fuente}'
            '</div>'
        )
    elif es_hb:
        # Hidrobiológico no cianobacteria — sin estándar
        leyenda_html += (
            '<div style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:4px;">'
            '<span style="display:inline-flex; align-items:center; gap:5px; '
            'font-size:0.72rem; color:#475569;">'
            f'<span style="display:inline-block; width:11px; height:11px; '
            f'background:{_color_phyllum(parametro)}; border-radius:50%; '
            'border:1px solid #0F172A;"></span>'
            f'{_display_nombre_parametro(parametro)}</span>'
            '</div>'
            '<div style="font-size:0.68rem; color:#94a3b8;">'
            'Parámetro hidrobiológico — sin ECA aplicable en el D.S. N° 004-2017-MINAM'
            '</div>'
        )
    elif es_temp:
        leyenda_html += (
            '<div style="font-size:0.72rem; color:#475569;">'
            '<b>Temperatura:</b> el ECA se evalúa como Δ sobre el natural, '
            'no como valor absoluto. Dots informativos sin coloreo de cumplimiento.'
            '</div>'
        )
    else:
        # Físico-químico/Campo con ECA — leyenda completa
        cats_presentes = {it["eca_cod"] for it in items if it["eca_cod"]}
        chips_cats = []
        for cat, paleta in ECA_CATEGORIA_COLORES.items():
            if cat in cats_presentes:
                chips_cats.append(
                    f'<span style="display:inline-flex; align-items:center; gap:5px; '
                    f'font-size:0.72rem; color:#475569;">'
                    f'<span style="display:inline-block; width:14px; height:10px; '
                    f'background:{paleta["fill"]}; opacity:0.6; '
                    f'border:1px solid {paleta["stroke"]}; '
                    f'border-radius:3px;"></span>'
                    f'<b>{cat}</b></span>'
                )
        leyenda_html += (
            '<div style="display:flex; flex-wrap:wrap; gap:14px; margin-bottom:6px;">'
            '<span style="display:inline-flex; align-items:center; gap:5px; '
            'font-size:0.72rem; color:#475569;">'
            '<span style="display:inline-block; width:11px; height:11px; '
            'background:#2563EB; border-radius:50%; border:1px solid #0F172A;"></span>'
            'Cumple ECA</span>'
            '<span style="display:inline-flex; align-items:center; gap:5px; '
            'font-size:0.72rem; color:#475569;">'
            '<span style="display:inline-block; width:11px; height:11px; '
            'background:#EF4444; border-radius:50%; border:1px solid #0F172A;"></span>'
            'No cumple ECA</span>'
            '<span style="display:inline-flex; align-items:center; gap:5px; '
            'font-size:0.72rem; color:#475569;">'
            '<span style="display:inline-block; width:11px; height:11px; '
            'background:#94A3B8; border-radius:50%; border:1px solid #0F172A;"></span>'
            'Sin ECA / sin medición</span>'
            '</div>'
        )
        if chips_cats:
            leyenda_html += (
                '<div style="font-size:0.7rem; color:#94a3b8; margin-bottom:3px;">'
                'Zonas coloreadas = rango ECA según categoría aplicable a cada punto'
                '</div>'
                '<div style="display:flex; flex-wrap:wrap; gap:14px;">'
                + "".join(chips_cats) +
                '</div>'
            )

    leyenda_html += "</div>"
    st.markdown(leyenda_html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Modo Punto — barras mensuales con TODAS las mediciones individuales
# ─────────────────────────────────────────────────────────────────────────────


def _es_temperatura(parametro: dict) -> bool:
    """True si el parámetro es Temperatura — el ECA del DS-004-2017 es un Δ
    sobre el natural, no un valor absoluto. Visualizamos sin coloreo ECA
    para no confundir al usuario."""
    nombre = (parametro.get("nombre") or "").lower()
    codigo = (parametro.get("codigo") or "").upper()
    return ("temperatura" in nombre) or codigo == "P008"


def _render_linea_estacionalidad(
    punto: dict,
    parametro: dict,
    anio: int,
) -> None:
    """
    Estacionalidad estilo R-Studio (línea + markers). Casos:

    - Físico-químico/Campo con ECA → línea verde + markers coloreados
      (rojo no cumple / azul cumple / gris sin ECA), con líneas ECA
      máx (rojo) y mín (verde) como referencia. Sombreado: rojo arriba
      del máx, rojo bajo el mín, verde claro entre ambos (cumplimiento).
    - Cianobacteria → bandas horizontales globales OMS (cel/mL o mm³/L).
      Línea y markers en color phyllum (verde-azul).
    - Otros hidrobiológicos → línea + markers en color del phyllum, sin
      líneas ECA ni sombreado.
    - Temperatura → markers grises, sin líneas ECA (el DS define un Δ).
    """
    historial = get_historial_punto(punto["id"], parametro["id"], limite=400)
    nombre_dis = _display_nombre_parametro(parametro)
    if not historial:
        st.info(f"Sin mediciones de **{nombre_dis}** en {punto['codigo']} / {anio}.")
        return

    df = pd.DataFrame(historial)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df.dropna(subset=["fecha", "valor"])
    df = df[df["fecha"].dt.year == int(anio)]
    if df.empty:
        st.info(f"Sin mediciones de **{nombre_dis}** en {punto['codigo']} / {anio}.")
        return

    df = df.sort_values("fecha").reset_index(drop=True)

    es_temp = _es_temperatura(parametro)
    es_hb = _es_hidrobiologico(parametro)
    es_cyano = _es_cianobacteria(parametro)
    bandas_oms = _oms_bandas_cianobacteria(parametro) if es_cyano else []

    # En hidrobiológicos no aplica ECA (sólo OMS para cianobacteria).
    # Temperatura tampoco.
    aplicar_eca = not (es_hb or es_temp)
    lim = get_limite_eca_parametro(punto["id"], parametro["id"]) if aplicar_eca else {}
    lim_max = lim.get("valor_maximo") if aplicar_eca else None
    lim_min = lim.get("valor_minimo") if aplicar_eca else None
    eca_cod = lim.get("eca_codigo", "") if aplicar_eca else ""
    tiene_eca = (lim_max is not None) or (lim_min is not None)

    # Rango Y — siempre desde 0
    valores = df["valor"].tolist()
    universo = list(valores)
    if lim_max is not None: universo.append(lim_max)
    if lim_min is not None: universo.append(lim_min)
    if bandas_oms:
        for b in bandas_oms:
            if b["lo"] is not None: universo.append(b["lo"])
            if b["hi"] is not None: universo.append(b["hi"])
    y_max_data = max(universo) if universo else 1.0
    y_lo = 0.0
    y_hi = y_max_data * 1.18 if y_max_data > 0 else 1.0

    # Color del marker
    color_phyllum_unico = _color_phyllum(parametro) if (es_hb or es_cyano) else None

    colores_marker: list[str] = []
    for v in df["valor"]:
        if color_phyllum_unico is not None:
            colores_marker.append(color_phyllum_unico)
        elif not tiene_eca:
            colores_marker.append(COLORS["eca_sin_dato"])
        elif (lim_max is not None and v > lim_max) or (lim_min is not None and v < lim_min):
            colores_marker.append(COLORS["eca_excede"])
        else:
            colores_marker.append("#2563EB")

    unidad = (parametro.get("unidades_medida") or {}).get("simbolo", "")
    y_label = f"{nombre_dis} ({unidad})" if unidad else nombre_dis
    color_linea = (
        color_phyllum_unico
        if color_phyllum_unico is not None
        else (COLORS["eca_cumple"] if tiene_eca else COLORS["eca_sin_dato"])
    )

    fig = go.Figure()

    # ── Sombreado de fondo según el caso
    shapes = []
    annotations = []

    if bandas_oms:
        for b in bandas_oms:
            b_hi = b["hi"] if b["hi"] is not None else y_hi
            shapes.append(dict(
                type="rect",
                xref="paper", yref="y",
                x0=0, x1=1,
                y0=b["lo"], y1=b_hi,
                fillcolor=b["color"], opacity=0.45,
                line=dict(width=0),
                layer="below",
            ))
            if b["hi"] is not None:
                shapes.append(dict(
                    type="line",
                    xref="paper", yref="y",
                    x0=0, x1=1,
                    y0=b_hi, y1=b_hi,
                    line=dict(color=b["stroke"], width=1.4, dash="dash"),
                    layer="below",
                ))
                annotations.append(dict(
                    x=1.0, y=b_hi,
                    xref="paper", yref="y",
                    text=f"{b['label']}",
                    showarrow=False,
                    xanchor="right",
                    font=dict(size=8.5, color=b["stroke"]),
                    yshift=8,
                ))
    elif tiene_eca:
        # Sombreado ECA: rojo arriba de máx, rojo bajo mín, verde claro entre
        if lim_max is not None:
            shapes.append(dict(
                type="rect",
                xref="paper", yref="y",
                x0=0, x1=1,
                y0=lim_max, y1=y_hi,
                fillcolor="#FECACA", opacity=0.40,
                line=dict(width=0),
                layer="below",
            ))
        if lim_min is not None:
            shapes.append(dict(
                type="rect",
                xref="paper", yref="y",
                x0=0, x1=1,
                y0=y_lo, y1=lim_min,
                fillcolor="#FECACA", opacity=0.40,
                line=dict(width=0),
                layer="below",
            ))
        # Banda de cumplimiento (verde claro)
        if lim_max is not None and lim_min is not None:
            shapes.append(dict(
                type="rect",
                xref="paper", yref="y",
                x0=0, x1=1,
                y0=lim_min, y1=lim_max,
                fillcolor="#A7F3D0", opacity=0.25,
                line=dict(width=0),
                layer="below",
            ))
        elif lim_max is not None:
            shapes.append(dict(
                type="rect",
                xref="paper", yref="y",
                x0=0, x1=1,
                y0=y_lo, y1=lim_max,
                fillcolor="#A7F3D0", opacity=0.20,
                line=dict(width=0),
                layer="below",
            ))
        elif lim_min is not None:
            shapes.append(dict(
                type="rect",
                xref="paper", yref="y",
                x0=0, x1=1,
                y0=lim_min, y1=y_hi,
                fillcolor="#A7F3D0", opacity=0.20,
                line=dict(width=0),
                layer="below",
            ))

    # Línea + markers principales
    fig.add_trace(go.Scatter(
        x=df["fecha"], y=df["valor"],
        mode="lines+markers",
        line=dict(color=color_linea, width=2.2, shape="linear"),
        marker=dict(
            size=9, color=colores_marker,
            line=dict(color="#0F172A", width=1.2),
            symbol="circle",
        ),
        text=[_format_valor(v) for v in df["valor"]],
        customdata=df[["fecha"]].astype(str).values,
        hovertemplate=(
            f"<b>%{{customdata[0]}}</b><br>"
            f"{nombre_dis}: <b>%{{text}}</b>"
            + (f" {unidad}" if unidad else "")
            + "<extra></extra>"
        ),
        showlegend=False,
    ))

    # Líneas ECA solo en físico-químico/campo con ECA
    if lim_max is not None:
        fig.add_hline(
            y=lim_max, line_dash="dash", line_color=COLORS["eca_excede"],
            line_width=1.6, opacity=0.95,
            annotation_text=f"Máx ECA: {_format_valor(lim_max)}",
            annotation_position="top right",
            annotation_font_size=9, annotation_font_color=COLORS["eca_excede"],
        )
    if lim_min is not None:
        fig.add_hline(
            y=lim_min, line_dash="dash", line_color=COLORS["eca_cumple"],
            line_width=1.6, opacity=0.95,
            annotation_text=f"Mín ECA: {_format_valor(lim_min)}",
            annotation_position="bottom right",
            annotation_font_size=9, annotation_font_color=COLORS["eca_cumple"],
        )

    titulo = (
        f"<b>{nombre_dis}</b>"
        + (f" ({unidad})" if unidad else "")
        + f"  ·  {punto['codigo']} ({anio})"
        + (f"  ·  ECA {eca_cod}" if (eca_cod and aplicar_eca) else "")
    )

    fig.update_layout(
        title=dict(
            text=titulo,
            x=0.02, xanchor="left",
            font=dict(size=12, color="#0F172A"),
        ),
        height=300,
        margin=dict(l=40, r=120 if bandas_oms else 30, t=40, b=40),
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="rgba(0,0,0,0)",
        shapes=shapes,
        annotations=annotations,
        xaxis=dict(
            range=[f"{anio}-01-01", f"{anio}-12-31"],
            tickformat="%b",
            dtick="M1",
            tickfont=dict(size=10, color="#64748b"),
            showgrid=True,
            gridcolor="#F1F5F9",
        ),
        yaxis=dict(
            title=dict(text=y_label, font=dict(size=10, color="#64748b")),
            range=[y_lo, y_hi],
            rangemode="tozero",
            gridcolor="#F1F5F9",
            zeroline=True, zerolinecolor="#E2E8F0",
            tickfont=dict(size=10, color="#64748b"),
            exponentformat="none",
            separatethousands=True,
        ),
        showlegend=False,
        hovermode="closest",
    )

    st.plotly_chart(
        fig, use_container_width=True,
        config={"displayModeBar": False},
        key=f"linea_estac_{punto['id']}_{parametro['id']}_{anio}",
    )

    # Leyenda contextual
    if bandas_oms:
        chips_oms = "".join(
            f'<span style="display:inline-flex; align-items:center; gap:5px;">'
            f'<span style="display:inline-block; width:14px; height:10px; '
            f'background:{b["color"]}; opacity:0.65; '
            f'border:1px solid {b["stroke"]}; border-radius:3px;"></span>'
            f'{b["label"]}</span>'
            for b in bandas_oms
        )
        st.markdown(
            '<div style="display:flex; gap:14px; font-size:0.7rem; '
            'color:#475569; flex-wrap:wrap; border-top:1px solid #f1f5f9; '
            f'padding-top:6px;">{chips_oms}</div>',
            unsafe_allow_html=True,
        )
    elif es_hb:
        st.markdown(
            f'<div style="font-size:0.7rem; color:#64748b; line-height:1.5; '
            f'border-top:1px solid #f1f5f9; padding-top:6px;">'
            f'<b>{nombre_dis}</b> — sin ECA aplicable en el '
            f'D.S. N° 004-2017-MINAM. Línea y markers en color del phyllum.'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif es_temp:
        st.markdown(
            '<div style="font-size:0.72rem; color:#64748b; line-height:1.5; '
            'border-top:1px solid #f1f5f9; padding-top:6px;">'
            '<b>Temperatura</b> — el ECA se evalúa como Δ sobre el natural, '
            'no como valor absoluto.'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="display:flex; gap:14px; font-size:0.7rem; '
            'color:#475569; margin:2px 0 4px 0; flex-wrap:wrap; '
            'border-top:1px solid #f1f5f9; padding-top:6px;">'
            '<span style="display:inline-flex; align-items:center; gap:5px;">'
            '<span style="display:inline-block; width:11px; height:11px; '
            'background:#2563EB; border-radius:50%; border:1px solid #0F172A;"></span>'
            'Cumple ECA</span>'
            '<span style="display:inline-flex; align-items:center; gap:5px;">'
            '<span style="display:inline-block; width:11px; height:11px; '
            'background:#EF4444; border-radius:50%; border:1px solid #0F172A;"></span>'
            'No cumple ECA</span>'
            '<span style="display:inline-flex; align-items:center; gap:5px;">'
            '<span style="display:inline-block; width:14px; height:10px; '
            'background:#FECACA; opacity:0.6; border:1px solid #EF4444; '
            'border-radius:2px;"></span>Zona no cumple</span>'
            '<span style="display:inline-flex; align-items:center; gap:5px;">'
            '<span style="display:inline-block; width:14px; height:10px; '
            'background:#A7F3D0; opacity:0.5; border:1px solid #10B981; '
            'border-radius:2px;"></span>Zona cumple</span>'
            '</div>',
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Modo Punto — Estado ECA compacto (tabla)
# ─────────────────────────────────────────────────────────────────────────────


def _render_estado_eca_compacto(punto: dict, fecha_inicio: str, fecha_fin: str) -> None:
    """Tabla compacta de comparativa ECA por parámetro para un punto."""
    datos = get_comparativa_eca_punto(punto["id"], fecha_inicio, fecha_fin)
    if not datos:
        st.info("Sin datos para este punto en el periodo seleccionado.")
        return
    _render_comparativa_eca_filtered(datos, cat="punto_sidebar")


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

    # Panel de alertas críticas eliminado — los puntos con excedencias ya
    # aparecen como bullets en la KPI roja "Con excedencias activas".


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


def _construir_mapa(
    puntos: list[dict],
    solo_excedencias: bool,
    centro: list[float] | None = None,
    zoom: int | None = None,
    punto_sel_id: str | None = None,
):
    """
    Mapa Folium con cuencas, red hídrica, puntos y alertas OMS de
    cianobacterias. El HeatMap se eliminó porque duplicaba la información
    cromática de los marcadores (mismo IC, dos canales visuales).

    centro/zoom permiten enfocar el mapa (ej. al punto seleccionado en
    Modo Punto). punto_sel_id dibuja un anillo de selección sobre ese punto.
    """
    import folium
    from folium.plugins import MiniMap, Fullscreen, MeasureControl

    m = folium.Map(
        location=centro or MAPA_CENTRO,
        zoom_start=zoom or MAPA_ZOOM,
        tiles=None,
        prefer_canvas=True,
        max_zoom=22,         # permite hacer zoom muy cerca
        min_zoom=5,
    )

    # Tile layers — max_native_zoom evita que Leaflet quede en blanco al
    # pedir tiles más allá de lo que el proveedor sirve. max_zoom mantiene
    # el control de zoom disponible (sobreescala el último tile válido).
    #
    # El primer TileLayer añadido es el basemap activo por defecto. Usamos un
    # mapa claro (CartoDB Positron) para el look limpio de geoportal: deja
    # respirar a las capas (cuencas, ríos, puntos) sin la saturación del
    # satélite, que queda como opción.
    folium.TileLayer(
        "CartoDB positron",
        name="Mapa claro",
        max_native_zoom=20, max_zoom=22,
    ).add_to(m)
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

    # Plugins de navegación/medición — útiles para técnicos de campo.
    Fullscreen(
        position="topleft",
        title="Pantalla completa",
        title_cancel="Salir de pantalla completa",
    ).add_to(m)
    MeasureControl(
        position="topleft",
        primary_length_unit="kilometers",
        secondary_length_unit="meters",
        primary_area_unit="hectares",
        active_color="#1565C0",
        completed_color="#0D47A1",
    ).add_to(m)

    # ── Estilizado de los controles Leaflet para integrarlos con la app ──────
    # El control de capas, el zoom, fullscreen y la regla usan por defecto el
    # look genérico de Leaflet. Lo reemplazamos por el lenguaje visual del
    # portal: tarjetas redondeadas, sombra suave, fuente Inter y azules de
    # marca. Se inyecta en el <head> del mapa, así aplica sin importar el
    # orden de creación de los controles.
    _MAP_CONTROLS_CSS = """
    <style>
    .leaflet-container { font-family: 'Inter','Segoe UI',sans-serif; }
    /* Panel de capas */
    .leaflet-control-layers {
        border: 1px solid #e2e8f0 !important;
        border-radius: 12px !important;
        box-shadow: 0 8px 24px rgba(15,23,42,0.10), 0 2px 6px rgba(15,23,42,0.06) !important;
        overflow: hidden;
        background: #ffffff !important;
    }
    .leaflet-control-layers-toggle {
        border-radius: 12px !important;
        width: 38px !important; height: 38px !important;
        background-size: 20px 20px !important;
    }
    .leaflet-control-layers-expanded {
        padding: 12px 14px 12px 12px !important;
        min-width: 188px;
        color: #334155;
        font-size: 12.5px;
    }
    /* Título "Capas" del panel expandido */
    .leaflet-control-layers-expanded::before {
        content: "Capas";
        display: block;
        font-weight: 700;
        font-size: 13px;
        color: #0f172a;
        letter-spacing: -0.01em;
        margin: 0 0 8px 0;
        padding-bottom: 6px;
        border-bottom: 1px solid #f1f5f9;
    }
    .leaflet-control-layers label {
        display: flex; align-items: center; gap: 8px;
        margin: 2px 0; font-weight: 500; cursor: pointer;
        line-height: 1.5;
    }
    .leaflet-control-layers label span { display: inline-flex; align-items: center; gap: 8px; }
    .leaflet-control-layers-selector { accent-color: #0D47A1; width: 15px; height: 15px; }
    .leaflet-control-layers-separator {
        border-top: 1px solid #e2e8f0 !important; margin: 8px 0 !important;
    }
    /* Botones de barra: zoom, fullscreen, regla */
    .leaflet-bar {
        border: none !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 12px rgba(15,23,42,0.10) !important;
        overflow: hidden;
    }
    .leaflet-bar a, .leaflet-bar a:hover {
        width: 32px !important; height: 32px !important;
        line-height: 32px !important;
        color: #0D47A1 !important;
        border-bottom: 1px solid #eef2f6 !important;
    }
    .leaflet-bar a:hover { background: #f1f5f9 !important; }
    .leaflet-bar a.leaflet-disabled { color: #cbd5e1 !important; }
    /* Atribución más sutil */
    .leaflet-control-attribution {
        background: rgba(255,255,255,0.78) !important;
        border-radius: 6px 0 0 0 !important;
        font-size: 10px !important; color: #94a3b8 !important;
    }
    </style>
    """
    m.get_root().header.add_child(folium.Element(_MAP_CONTROLS_CSS))

    # ── Polígonos de cuencas hidrográficas (estilo SSDH/ANA) ─────────────
    # Outline de color por cuenca para distinguirlas a simple vista. Se usan
    # tonos de agua (azul institucional + teal) en vez de verde/rojo para no
    # competir con el semáforo ECA de los puntos (verde=cumple, rojo=excede).
    #   Quilca-Vítor-Chili → azul institucional   · Colca-Camaná → teal
    cuencas = _cargar_geojson_cuencas()

    def _color_cuenca(nombre: str) -> tuple[str, str]:
        """Devuelve (color_base, color_hover) según la cuenca."""
        n = nombre.lower()
        if "quilca" in n or "vitor" in n or "chili" in n:
            return ("#0D47A1", "#0A3D7A")    # azul institucional
        if "colca" in n or "caman" in n:
            return ("#0a9396", "#07686a")    # teal / teal oscuro
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
        """
        version: '1999' (cél/mL, anillo sólido) o '2021' (biovolumen, anillo
        punteado). Capa visible POR DEFECTO (`show=True`) — feedback usuario.
        Popup conciso: solo nivel + valor relevante + fecha. La info detallada
        se ve en la sidebar (Modo Punto).
        """
        clave = f"oms_{version}"
        label = (
            f"{titulo} ({n_puntos_cyano})"
            if n_puntos_cyano else f"{titulo} (sin análisis)"
        )
        fg = folium.FeatureGroup(name=label, show=True)
        for p in pts_filtrados:
            alerta = alertas_cyano.get(p["id"])
            if not alerta:
                continue
            nivel_info = alerta.get(clave) or {}
            if version == "1999":
                valor_str = f"{alerta.get('total_cyano_cel_ml', 0):,.0f} cél/mL"
            else:
                valor_str = f"{alerta.get('biovolumen_mm3_l', 0):,.4f} mm³/L"
            tooltip = (
                f"{p['codigo']} · OMS {version} · "
                f"{nivel_info.get('label','—')} · {valor_str}"
            )
            popup_html = (
                f'<div style="font-family:sans-serif; min-width:170px;">'
                f'<div style="font-weight:700; color:#0F172A; '
                f'font-size:12px;">{p["codigo"]}</div>'
                f'<div style="background:{nivel_info.get("color_bg","#e2e3e5")}; '
                f'border-left:4px solid {nivel_info.get("color_borde","#6c757d")}; '
                f'padding:5px 8px; border-radius:4px; font-size:11.5px; '
                f'margin-top:4px;">'
                f'<b>OMS {version}: {nivel_info.get("label","—")}</b><br>'
                f'<span style="color:#475569;">{valor_str}</span><br>'
                f'<span style="color:#94A3B8; font-size:10.5px;">'
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
                popup=folium.Popup(popup_html, max_width=240),
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

    # Anillo de selección sobre el punto activo en Modo Punto — referencia
    # visual de cuál punto está cargado en el panel lateral.
    if punto_sel_id:
        for p in pts_filtrados:
            if p.get("id") == punto_sel_id:
                folium.CircleMarker(
                    location=[p["latitud"], p["longitud"]],
                    radius=26,
                    color="#0D47A1",
                    weight=3,
                    fill=False,
                    dash_array="6,4",
                    tooltip=f"Punto seleccionado: {p['codigo']}",
                ).add_to(m)
                break

    # Lector de coordenadas UTM WGS84 zona 19S bajo el cursor — los técnicos
    # de campo trabajan con UTM, no con lat/lon. Conversión Transverse
    # Mercator estándar en JS (meridiano central zona 19 = -69°).
    utm_js = f"""
    (function() {{
        var map = {m.get_name()};
        var ctl = L.control({{position: 'bottomright'}});
        ctl.onAdd = function() {{
            var div = L.DomUtil.create('div');
            div.id = 'lvca-utm';
            div.style.cssText = 'background:rgba(255,255,255,0.92);' +
                'padding:3px 10px;border-radius:6px;' +
                'font:11px/1.5 monospace;color:#334155;' +
                'box-shadow:0 1px 4px rgba(0,0,0,0.18);';
            div.innerHTML = 'UTM 19S &nbsp;—&nbsp; mueve el cursor';
            return div;
        }};
        ctl.addTo(map);
        function deg2utm19s(lat, lon) {{
            var a = 6378137.0, f = 1/298.257223563, k0 = 0.9996;
            var e2 = f*(2-f), ep2 = e2/(1-e2);
            var latr = lat*Math.PI/180;
            var A = Math.cos(latr)*((lon+69)*Math.PI/180);
            var sl = Math.sin(latr), cl = Math.cos(latr), tl = Math.tan(latr);
            var N = a/Math.sqrt(1-e2*sl*sl), T = tl*tl, C = ep2*cl*cl;
            var e4 = e2*e2, e6 = e4*e2;
            var M = a*((1-e2/4-3*e4/64-5*e6/256)*latr
                  -(3*e2/8+3*e4/32+45*e6/1024)*Math.sin(2*latr)
                  +(15*e4/256+45*e6/1024)*Math.sin(4*latr)
                  -(35*e6/3072)*Math.sin(6*latr));
            var E = k0*N*(A+(1-T+C)*Math.pow(A,3)/6
                  +(5-18*T+T*T+72*C-58*ep2)*Math.pow(A,5)/120)+500000;
            var Nn = k0*(M+N*tl*(A*A/2+(5-T+9*C+4*C*C)*Math.pow(A,4)/24
                   +(61-58*T+T*T+600*C-330*ep2)*Math.pow(A,6)/720))+10000000;
            return [E, Nn];
        }}
        map.on('mousemove', function(e) {{
            var u = deg2utm19s(e.latlng.lat, e.latlng.lng);
            var el = document.getElementById('lvca-utm');
            if (el) {{
                el.innerHTML = 'UTM 19S &nbsp; E ' + u[0].toFixed(0) +
                               ' &nbsp; N ' + u[1].toFixed(0);
            }}
        }});
    }})();
    """
    m.get_root().script.add_child(folium.Element(utm_js))

    # Panel de capas siempre visible (estilo Visor Geohidro del ANA): el
    # usuario ve y togglea las capas sin tener que abrir el control.
    folium.LayerControl(collapsed=False).add_to(m)

    # Leyenda estilo mockup "Integrated Eco-Aura" — esquina inferior derecha,
    # con tres ítems (Cumple / Excedencia Leve / Excedencia Alta) usando
    # íconos vectoriales (círculo verde, triángulo amarillo, círculo rojo).
    # Se mantienen "media" y "sin datos" como filas extra colapsables —
    # son útiles para el técnico AUTODEMA pero no aparecen en el mockup
    # por ser un dashboard ejecutivo.
    leyenda_html = """
    <div id="lvca-legend" style="position:absolute; bottom:18px; left:18px;
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
               letter-spacing:-0.01em;">Leyenda</div>
          <div style="font-size:10px; color:#94a3b8; margin-top:1px;">
            Monitoreo de calidad del agua
          </div>
        </div>
        <span id="lvca-legend-caret" style="color:#94a3b8;
             font-size:10px; margin-left:12px;">&#9662;</span>
      </div>
      <div id="lvca-legend-body" style="margin-top:8px; color:#334155;
           display:block;">
        <div style="font-weight:700; color:#0F172A; font-size:12px;
             letter-spacing:-0.01em; margin-bottom:4px;">Estado ECA
          <span style="font-weight:500; color:#94a3b8; font-size:10px;">
            · D.S. 004-2017-MINAM</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px; padding:3px 0;">
          <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
            <circle cx="12" cy="12" r="9" fill="#10B981" stroke="#047857" stroke-width="1"/>
          </svg>
          <span style="font-weight:500;">Cumple ECA</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px; padding:3px 0;">
          <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
            <circle cx="12" cy="12" r="9" fill="#F59E0B" stroke="#B45309" stroke-width="1"/>
          </svg>
          <span style="font-weight:500;">Excede ECA · leve</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px; padding:3px 0;">
          <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
            <circle cx="12" cy="12" r="9" fill="#EF4444" stroke="#B91C1C" stroke-width="1"/>
          </svg>
          <span style="font-weight:500;">Excede ECA · severo</span>
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
          Color continuo (verde→ámbar→rojo) según índice de cumplimiento.<br>
          Radio = N° parámetros evaluados
        </div>
        <div style="border-top:1px solid #f1f5f9; padding-top:8px; margin-top:8px;">
          <div style="font-weight:700; color:#0F172A; font-size:12px;
               letter-spacing:-0.01em; margin-bottom:4px;">Alerta OMS</div>
          <div style="display:flex; align-items:center; gap:10px; padding:2px 0;">
            <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
              <circle cx="12" cy="12" r="9" fill="none" stroke="#475569" stroke-width="2.5"/>
            </svg>
            <span style="font-weight:500;">OMS 1999
              <span style="color:#94a3b8; font-size:10.5px;">(cél/mL)</span>
            </span>
          </div>
          <div style="display:flex; align-items:center; gap:10px; padding:2px 0;">
            <svg width="14" height="14" viewBox="0 0 24 24" style="flex-shrink:0;">
              <circle cx="12" cy="12" r="9" fill="none" stroke="#475569"
                   stroke-width="2.5" stroke-dasharray="3,2"/>
            </svg>
            <span style="font-weight:500;">OMS 2021
              <span style="color:#94a3b8; font-size:10.5px;">(biovolumen)</span>
            </span>
          </div>
          <div style="font-size:10px; color:#94a3b8; margin-top:4px;">
            Color del anillo = nivel (verde/amarillo/rojo)
          </div>
        </div>
        <div style="border-top:1px solid #f1f5f9; padding-top:8px; margin-top:8px;">
          <div style="font-weight:700; color:#0F172A; font-size:12px;
               letter-spacing:-0.01em; margin-bottom:4px;">Capas base</div>
          <div style="display:flex; align-items:center; gap:10px; padding:2px 0;">
            <svg width="16" height="10" viewBox="0 0 16 10" style="flex-shrink:0;">
              <rect x="1" y="1" width="14" height="8" rx="1" fill="rgba(13,71,161,0.06)"
                    stroke="#0D47A1" stroke-width="1.6"/>
            </svg>
            <span style="font-weight:500;">Cuenca Quilca-Vítor-Chili</span>
          </div>
          <div style="display:flex; align-items:center; gap:10px; padding:2px 0;">
            <svg width="16" height="10" viewBox="0 0 16 10" style="flex-shrink:0;">
              <rect x="1" y="1" width="14" height="8" rx="1" fill="rgba(10,147,150,0.06)"
                    stroke="#0a9396" stroke-width="1.6"/>
            </svg>
            <span style="font-weight:500;">Cuenca Colca-Camaná</span>
          </div>
          <div style="display:flex; align-items:center; gap:10px; padding:2px 0;">
            <svg width="16" height="10" viewBox="0 0 16 10" style="flex-shrink:0;">
              <line x1="1" y1="5" x2="15" y2="5" stroke="#1d4ed8" stroke-width="2.5"/>
            </svg>
            <span style="font-weight:500;">Ríos</span>
          </div>
          <div style="display:flex; align-items:center; gap:10px; padding:2px 0;">
            <svg width="16" height="10" viewBox="0 0 16 10" style="flex-shrink:0;">
              <line x1="1" y1="5" x2="15" y2="5" stroke="#60a5fa" stroke-width="1.6"
                    stroke-dasharray="3,3"/>
            </svg>
            <span style="font-weight:500;">Quebradas</span>
          </div>
        </div>
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda_html))

    return m


# ─────────────────────────────────────────────────────────────────────────────
# Exportación de puntos (GeoJSON / KML) — para QGIS, ArcGIS y Google Earth
# ─────────────────────────────────────────────────────────────────────────────

def _export_geojson_puntos(puntos: list[dict]) -> str:
    """FeatureCollection con los puntos visibles y su estado ECA."""
    import json
    feats = []
    for p in puntos:
        if p.get("latitud") is None or p.get("longitud") is None:
            continue
        feats.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [p["longitud"], p["latitud"]],
            },
            "properties": {
                "codigo":               p.get("codigo"),
                "nombre":               p.get("nombre"),
                "estado":               p.get("estado"),
                "cuenca":               p.get("cuenca"),
                "eca":                  (p.get("ecas") or {}).get("codigo"),
                "indice_cumplimiento":  p.get("indice_cumplimiento"),
                "parametros_evaluados": p.get("n_parametros_evaluados"),
                "excedencias":          p.get("n_excedencias"),
            },
        })
    return json.dumps(
        {"type": "FeatureCollection", "features": feats},
        ensure_ascii=False, indent=2,
    )


def _export_kml_puntos(puntos: list[dict]) -> str:
    """KML con placemarks coloreados por estado (Google Earth)."""
    from xml.sax.saxutils import escape

    # KML usa color aabbggrr (alpha, blue, green, red)
    def _kml_color(hex_rgb: str) -> str:
        h = hex_rgb.lstrip("#")
        return f"ff{h[4:6]}{h[2:4]}{h[0:2]}".lower()

    placemarks = []
    for p in puntos:
        if p.get("latitud") is None or p.get("longitud") is None:
            continue
        color = _kml_color(_color_termico(p))
        ic = p.get("indice_cumplimiento")
        ic_str = f"{ic*100:.1f}%" if ic is not None else "sin datos"
        desc = (
            f"Estado: {p.get('estado', '—')}\n"
            f"Cumplimiento ECA: {ic_str}\n"
            f"Parámetros evaluados: {p.get('n_parametros_evaluados', 0)}\n"
            f"Excedencias: {p.get('n_excedencias', 0)}\n"
            f"Cuenca: {p.get('cuenca', '—')}"
        )
        placemarks.append(
            f"<Placemark>"
            f"<name>{escape(str(p.get('codigo', '')))}</name>"
            f"<description>{escape(desc)}</description>"
            f"<Style><IconStyle><color>{color}</color>"
            f"<Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon>"
            f"</IconStyle></Style>"
            f"<Point><coordinates>{p['longitud']},{p['latitud']},0</coordinates></Point>"
            f"</Placemark>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        "<name>Puntos de monitoreo LVCA</name>"
        + "".join(placemarks) +
        "</Document></kml>"
    )


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
    colores = [
        COLORS["eca_excede"] if r["estado"] == "excede" else COLORS["eca_cumple"]
        for _, r in df.iterrows()
    ]

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

    color_barra = COLORS["primary"]
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
    st.download_button(
        ":material/download: CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"ultimos_resultados_{punto.get('codigo', 'punto')}.csv",
        mime="text/csv",
        key=f"dl_ultimos_res_{cat}",
    )


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("visitante")
def main() -> None:
    aplicar_estilos()
    top_nav()

    # El CSS de la vista integrada (KPIs compactas + sidebar) vive ahora en
    # _GLOBAL_CSS (components/ui_styles.py) para no reinyectarse en cada rerun.
    # Los marker-divs .lvca-geo-vista-integrada / .lvca-geo-kpis / .lvca-geo-sidebar
    # se siguen emitiendo en runtime y son las anclas de esos selectores.

    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.error("Instala: `pip install folium streamlit-folium`")
        st.stop()

    # Marker para que el CSS de KPIs apunte solo a esta página
    st.markdown('<div class="lvca-geo-vista-integrada"></div>', unsafe_allow_html=True)

    # Estado por defecto del modo (Campaña / Punto)
    st.session_state.setdefault("geo_modo", "campana")

    # Rango de fechas defaults (180 días) — el filtro de fechas del mapa
    # se eliminó por feedback del usuario: la búsqueda de "Modo Campaña"
    # ya tiene su propio rango ampliado y el chart de "Modo Punto" tiene
    # selector de año independiente, así que un filtro global no aporta.
    fecha_inicio = date.today() - timedelta(days=180)
    fecha_fin    = date.today()

    with st.spinner("Cargando datos..."):
        try:
            puntos = get_puntos_geoportal(str(fecha_inicio), str(fecha_fin), None)
        except Exception as exc:
            st.error(f"Error al cargar puntos: {exc}")
            st.stop()

    puntos_con_coords = [p for p in puntos if p.get("latitud") and p.get("longitud")]
    if not puntos_con_coords:
        st.warning("No hay puntos con coordenadas disponibles.")
        st.stop()

    opciones_punto = {f"{p['codigo']} — {p['nombre']}": p for p in puntos_con_coords}
    parametros = get_parametros_selector()
    campanas = get_campanas()

    # Contexto de navegación: otra página pidió enfocar un punto concreto.
    # Se aplica antes de crear el radio "geo_modo" y el selectbox "geo_punto".
    ctx_punto_id = consumir_contexto("geoportal").get("punto_id")
    if ctx_punto_id:
        for _lbl, _p in opciones_punto.items():
            if _p.get("id") == ctx_punto_id:
                st.session_state["geo_punto"] = _lbl
                st.session_state["geo_modo"] = "punto"
                break

    # ── 1. Dashboard global (4 KPIs full width — compactas) ─────────────
    st.markdown('<div class="lvca-geo-kpis">', unsafe_allow_html=True)
    _render_dashboard(puntos_con_coords)
    st.markdown('</div>', unsafe_allow_html=True)
    success_toast(
        "Datos de monitoreo actualizados exitosamente.",
        key="geoportal_load",
    )

    # ── 2. Mapa (7/12) + Sidebar derecha (5/12) ─────────────────────────
    # Ambas columnas corren como fragments: tocar los filtros del mapa NO
    # re-renderiza la sidebar (gráficos Plotly), y tocar parámetro/año/tabs
    # de la sidebar NO reconstruye el mapa Folium. Solo cambiar de punto o
    # de modo escala a rerun completo (el mapa debe recentrarse).
    col_mapa, col_side = st.columns([7, 5], gap="medium")

    with col_mapa:
        _fragmento_mapa(puntos_con_coords, opciones_punto)

    with col_side:
        _fragmento_sidebar(
            opciones_punto, parametros, campanas,
            str(fecha_inicio), str(fecha_fin),
        )


def _firma_sync_mapa() -> tuple:
    """Estado de la sidebar del que depende el centrado del mapa."""
    return (
        st.session_state.get("geo_modo"),
        st.session_state.get("geo_punto"),
    )


@st.fragment
def _fragmento_mapa(puntos_con_coords: list[dict], opciones_punto: dict) -> None:
    """Columna izquierda: buscador + filtros del mapa + Folium + clicks."""
    from streamlit_folium import st_folium

    # ── Buscador de punto (zoom-to) — estilo Visor Geohidro del ANA ──────
    # Seleccionar un punto centra el mapa en él (Modo Punto) y sincroniza la
    # sidebar, igual que un click en el marcador.
    _PLACEHOLDER_BUSCAR = "🔍  Buscar punto de monitoreo…"
    labels_busqueda = list(opciones_punto.keys())
    sel_buscar = st.selectbox(
        "Buscar punto de monitoreo",
        [_PLACEHOLDER_BUSCAR] + labels_busqueda,
        key="geo_buscar",
        label_visibility="collapsed",
    )
    if (
        sel_buscar
        and sel_buscar != _PLACEHOLDER_BUSCAR
        and sel_buscar != st.session_state.get("geo_punto")
    ):
        st.session_state["geo_punto"] = sel_buscar
        st.session_state["geo_modo"] = "punto"
        st.session_state["_geo_sync_mapa"] = _firma_sync_mapa()
        st.rerun()  # scope app: sidebar y mapa se sincronizan

    # ── Filtros del mapa + exportación ───────────────────────────────
    fc1, fc2, fc3 = st.columns([2.4, 2.4, 1.4])
    with fc1:
        solo_exc = st.toggle(
            "Solo excedencias",
            key="geo_solo_exc",
            help="Muestra únicamente los puntos con excedencias ECA activas.",
        )
    with fc2:
        cuencas_disp = sorted({
            (p.get("cuenca") or "").strip()
            for p in puntos_con_coords
            if (p.get("cuenca") or "").strip()
        })
        cuenca_sel = st.selectbox(
            "Cuenca",
            ["Todas las cuencas"] + cuencas_disp,
            key="geo_filtro_cuenca",
            label_visibility="collapsed",
        )

    pts_mapa = puntos_con_coords
    if cuenca_sel and cuenca_sel != "Todas las cuencas":
        pts_mapa = [
            p for p in pts_mapa
            if (p.get("cuenca") or "").strip() == cuenca_sel
        ]

    with fc3:
        with st.popover(":material/download: Exportar", use_container_width=True):
            st.caption("Puntos visibles con su estado ECA")
            st.download_button(
                "GeoJSON (QGIS / ArcGIS)",
                data=_export_geojson_puntos(pts_mapa),
                file_name="puntos_lvca.geojson",
                mime="application/geo+json",
                key="dl_geojson_puntos",
                use_container_width=True,
            )
            st.download_button(
                "KML (Google Earth)",
                data=_export_kml_puntos(pts_mapa),
                file_name="puntos_lvca.kml",
                mime="application/vnd.google-earth.kml+xml",
                key="dl_kml_puntos",
                use_container_width=True,
            )

    # ── Enfoque del mapa: en Modo Punto, centrar en el punto activo ──
    centro = zoom_sel = punto_sel_id = None
    if st.session_state.get("geo_modo") == "punto":
        _lbl_sel = st.session_state.get("geo_punto")
        _p_sel = opciones_punto.get(_lbl_sel) if _lbl_sel else None
        if _p_sel:
            centro = [_p_sel["latitud"], _p_sel["longitud"]]
            zoom_sel = 13
            punto_sel_id = _p_sel.get("id")

    mapa = _construir_mapa(
        pts_mapa,
        solo_excedencias=solo_exc,
        centro=centro,
        zoom=zoom_sel,
        punto_sel_id=punto_sel_id,
    )
    map_data = st_folium(
        mapa, use_container_width=True, height=540,
        returned_objects=["last_object_clicked"],
    )
    n_visibles = sum(
        1 for p in pts_mapa
        if not solo_exc or p.get("estado") == "excedencia"
    )
    if n_visibles < len(puntos_con_coords):
        st.caption(
            f"Mostrando {n_visibles} de {len(puntos_con_coords)} puntos "
            f"(filtros activos)."
        )

    # Click en marcador → cambia automáticamente a Modo Punto + selecciona el punto.
    # IMPORTANTE: st_folium retorna `last_object_clicked` cacheado en cada rerun
    # (incluso cuando el rerun fue causado por OTRO widget como el selectbox de
    # campaña). Sin firma de click, cada cambio de campaña reactivaba el handler
    # y forzaba un salto a "Por punto" no deseado. Guardamos la firma del último
    # click procesado para que solo se dispare con clicks NUEVOS.
    if map_data and map_data.get("last_object_clicked"):
        clicked = map_data["last_object_clicked"]
        clat = clicked.get("lat")
        clon = clicked.get("lng")
        firma = (clat, clon)
        firma_anterior = st.session_state.get("geo_ultimo_click")
        if clat is not None and clon is not None and firma != firma_anterior:
            min_dist = float("inf")
            closest_label = None
            for label, p in opciones_punto.items():
                dist = (p["latitud"] - clat) ** 2 + (p["longitud"] - clon) ** 2
                if dist < min_dist:
                    min_dist = dist
                    closest_label = label
            if closest_label and min_dist < 0.01:
                st.session_state["geo_ultimo_click"] = firma
                st.session_state["geo_punto"] = closest_label
                st.session_state["geo_modo"] = "punto"
                # Registrar la firma para que la sidebar no re-escale el rerun
                st.session_state["_geo_sync_mapa"] = _firma_sync_mapa()
                st.rerun()  # scope app: sidebar y mapa se sincronizan


@st.fragment
def _fragmento_sidebar(
    opciones_punto: dict,
    parametros: list[dict],
    campanas: list[dict],
    fecha_inicio: str,
    fecha_fin: str,
) -> None:
    """
    Columna derecha: modo Campaña/Punto + gráficos. Cambiar parámetro, año
    o tab re-renderiza solo esta columna. Cambiar de modo o de punto escala
    a rerun completo porque el mapa (fuera del fragment) debe recentrarse.
    """
    st.markdown('<div class="lvca-geo-sidebar">', unsafe_allow_html=True)

    # Toggle de modo (Campaña vs Punto)
    modo = st.radio(
        "Modo",
        options=["campana", "punto"],
        format_func=lambda v: ("Por campaña" if v == "campana" else "Por punto"),
        key="geo_modo",
        horizontal=True,
        label_visibility="collapsed",
    )

    if modo == "campana":
        _render_modo_campana(parametros, campanas)
    else:
        _render_modo_punto(
            opciones_punto, parametros,
            fecha_inicio, fecha_fin,
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # Sincronización con el mapa: si el modo o el punto cambiaron en este
    # rerun parcial, escalar a rerun completo para que el mapa se recentre.
    firma = _firma_sync_mapa()
    if st.session_state.get("_geo_sync_mapa") != firma:
        primera_vez = "_geo_sync_mapa" not in st.session_state
        st.session_state["_geo_sync_mapa"] = firma
        if not primera_vez:
            st.rerun()  # scope app


_TRES_CATS = ("campo", "fisicoquimico", "hidrobiologico")


def _on_change_param_cat(cat: str, key_prefix: str) -> None:
    """
    Callback exclusivo: cuando el usuario cambia el selectbox de UNA categoría,
    marca esa categoría como activa Y limpia las selecciones de las otras dos
    para que solo una a la vez esté "elegida".
    """
    st.session_state["geo_param_active_cat"] = cat
    for otra in _TRES_CATS:
        if otra != cat:
            otra_key = f"{key_prefix}_param_{otra}"
            if otra_key in st.session_state:
                st.session_state[otra_key] = None


def _render_3_selectores_parametro(
    parametros: list[dict],
    key_prefix: str,
) -> dict | None:
    """
    Renderiza 3 selectboxes side-by-side (Campo / Fisicoquímicos /
    Hidrobiológicos) con sus parámetros filtrados por categoría.

    Comportamiento exclusivo:
      - Inicio: los 3 selectores están en BLANCO (index=None, placeholder).
      - Al elegir uno → ese se vuelve "activo" y los otros 2 quedan en blanco.
      - Al elegir otro → ese se vuelve activo y el anterior queda en blanco.

    Returns:
        El parámetro seleccionado (dict) o None si ninguno está activo.
    """
    cats: dict[str, dict] = {
        "campo":          {"label": "Campo",           "params": []},
        "fisicoquimico":  {"label": "Fisicoquímicos",  "params": []},
        "hidrobiologico": {"label": "Hidrobiológicos", "params": []},
    }
    for p in parametros:
        c = _clasificar_cat(p)
        if c == "Campo":
            cats["campo"]["params"].append(p)
        elif c == "Fisicoquimico":
            cats["fisicoquimico"]["params"].append(p)
        elif c == "Hidrobiologico":
            cats["hidrobiologico"]["params"].append(p)

    for c in cats.values():
        c["opciones"] = {
            f"{p['codigo']} — {_display_nombre_parametro(p)}": p
            for p in c["params"]
        }

    st.markdown(
        '<div class="lvca-geo-sel-header">'
        '<span class="material-symbols-rounded" style="font-size:15px;">tune</span>'
        'Parámetro a visualizar'
        '</div>',
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.columns(3)
    cols = {"campo": c1, "fisicoquimico": c2, "hidrobiologico": c3}
    for cat_key, col in cols.items():
        with col:
            opc = cats[cat_key]["opciones"]
            label = cats[cat_key]["label"]
            if opc:
                st.selectbox(
                    label,
                    list(opc.keys()),
                    key=f"{key_prefix}_param_{cat_key}",
                    index=None,
                    placeholder="Seleccionar…",
                    on_change=_on_change_param_cat,
                    args=(cat_key, key_prefix),
                )
            else:
                st.markdown(
                    f'<div class="lvca-geo-sel-empty">'
                    f'<div class="titulo">{label}</div>'
                    f'<div class="cuerpo">— sin parámetros</div></div>',
                    unsafe_allow_html=True,
                )

    # Resolver parámetro activo: solo un selector debería tener valor distinto
    # de None gracias al callback exclusivo. Buscamos cuál tiene selección.
    active = st.session_state.get("geo_param_active_cat")
    if active and active in cats:
        sel_lbl = st.session_state.get(f"{key_prefix}_param_{active}")
        if sel_lbl:
            return cats[active]["opciones"].get(sel_lbl)

    # Si la categoría activa quedó sin selección (o no hay activa), revisar
    # si algún otro selector tiene valor — esto puede pasar al primer render
    # tras un cambio de modo Campaña↔Punto que comparte session_state.
    for cat_key in _TRES_CATS:
        sel_lbl = st.session_state.get(f"{key_prefix}_param_{cat_key}")
        if sel_lbl and cats[cat_key]["opciones"].get(sel_lbl):
            st.session_state["geo_param_active_cat"] = cat_key
            return cats[cat_key]["opciones"][sel_lbl]

    return None


def _render_modo_campana(parametros: list[dict], campanas: list[dict]) -> None:
    """Sidebar — Modo Campaña: selector de campaña + 3 selectores parámetro + chart."""
    if not campanas:
        st.info("No hay campañas registradas.")
        return

    opciones_camp = {f"{c['codigo']} — {c['nombre']}": c for c in campanas}
    sel_camp_lbl = st.selectbox(
        "Campaña",
        list(opciones_camp.keys()),
        key="geo_camp_chart",
    )

    parametro = _render_3_selectores_parametro(parametros, key_prefix="camp")
    if parametro is None:
        st.markdown(
            '<div class="lvca-geo-empty-hint">'
            '<span class="material-symbols-rounded">touch_app</span>'
            'Selecciona un parámetro de Campo, Fisicoquímicos o '
            'Hidrobiológicos para ver el gráfico.'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    campana = opciones_camp[sel_camp_lbl]

    fi = (campana.get("fecha_inicio") or "")[:10]
    ff = (campana.get("fecha_fin") or "")[:10]
    if not fi or not ff:
        st.warning("La campaña no tiene rango de fechas válido.")
        return

    # Ampliar el rango de búsqueda: las muestras de campo se toman dentro
    # de fecha_inicio/fecha_fin pero el laboratorio puede analizar varios
    # meses después. Si filtramos estricto al rango de la campaña, perdemos
    # los puntos cuyos análisis salieron tarde — bug reportado por el usuario.
    try:
        fi_d = date.fromisoformat(fi)
        ff_d = date.fromisoformat(ff)
        fi_buscar = (fi_d - timedelta(days=180)).isoformat()
        ff_buscar = (ff_d + timedelta(days=365)).isoformat()
    except ValueError:
        fi_buscar, ff_buscar = fi, ff

    # Sin intersección con get_puntos_de_campana — dejamos a campana_puntos
    # como única fuente de verdad de "puntos asignados". Los puntos sin
    # medición del parámetro se muestran con dot gris y "—".
    pts_camp = get_puntos_geoportal(fi_buscar, ff_buscar, campana["id"])
    if not pts_camp:
        st.info("La campaña no tiene puntos asignados.")
        return

    _render_grafico_campana_comparativo(campana, parametro, pts_camp, fi_buscar, ff_buscar)


def _render_modo_punto(
    opciones_punto: dict[str, dict],
    parametros: list[dict],
    fecha_inicio: str,
    fecha_fin: str,
) -> None:
    """Sidebar — Modo Punto: selector punto + 3 selectores parámetro + año + tabs."""
    pp_a, pp_b = st.columns([2, 1])
    with pp_a:
        sel_punto_lbl = st.selectbox(
            "Punto",
            list(opciones_punto.keys()),
            key="geo_punto",
            help="Sincronizado con el click en el marcador del mapa.",
        )
    with pp_b:
        anio_actual = date.today().year
        sel_anio = st.selectbox(
            "Año",
            list(range(anio_actual, anio_actual - 6, -1)),
            key="geo_punto_anio",
        )

    parametro = _render_3_selectores_parametro(parametros, key_prefix="punto")
    punto = opciones_punto[sel_punto_lbl]

    # Mini-tabs: Estacionalidad | Estado ECA | Ficha
    # Estacionalidad depende del parámetro elegido (placeholder si no hay).
    # Estado ECA y Ficha funcionan sin parámetro.
    tab_seas, tab_eca, tab_ficha = st.tabs([
        ":material/calendar_month: Estacionalidad",
        ":material/shield: Estado ECA",
        ":material/info: Ficha del punto",
    ])
    with tab_seas:
        if parametro is None:
            st.markdown(
                '<div class="lvca-geo-empty-hint">'
                '<span class="material-symbols-rounded">touch_app</span>'
                'Selecciona un parámetro de Campo, Fisicoquímicos o '
                'Hidrobiológicos para ver la estacionalidad.'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            _render_linea_estacionalidad(punto, parametro, sel_anio)
    with tab_eca:
        _render_estado_eca_compacto(punto, fecha_inicio, fecha_fin)
    with tab_ficha:
        _render_panel_punto(punto)

    # Atajos del flujo: el mismo punto en las demás secciones.
    # "Editar punto" solo se ofrece a quien puede entrar a esa página (admin).
    _sesion = st.session_state.get("sesion")
    _es_admin = bool(_sesion and _sesion.tiene_rol("administrador"))
    gnav1, gnav2 = st.columns(2)
    with gnav1:
        if st.button("Datos del punto", key="geo_nav_bd",
                     icon=":material/database:", use_container_width=True,
                     help="Abrir la Base de Datos filtrada por este lugar."):
            ir_a("base_datos", punto_id=punto.get("id"))
    with gnav2:
        if _es_admin and st.button(
                "Editar punto", key="geo_nav_punto",
                icon=":material/edit_location:", use_container_width=True,
                help="Abrir la ficha de gestión del punto."):
            ir_a("puntos", punto_id=punto.get("id"))


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

    # ── Ficha técnica descargable (PDF) — estilo fichas de estación del ANA.
    # Generación bajo demanda (solo al pulsar) para no construir el PDF en
    # cada rerun del panel.
    _pid = punto_sel.get("id")
    _ficha_key = f"_ficha_pdf_{_pid}"
    if st.button("Generar ficha técnica (PDF)", key=f"btn_ficha_{_pid}",
                 icon=":material/picture_as_pdf:", use_container_width=True):
        from services.informe_service import generar_pdf_punto
        with st.spinner("Generando ficha…"):
            try:
                st.session_state[_ficha_key] = generar_pdf_punto(_pid)
            except Exception as exc:
                st.session_state[_ficha_key] = None
                st.error(f"No se pudo generar la ficha: {exc}")
    if st.session_state.get(_ficha_key):
        st.download_button(
            "Descargar ficha PDF",
            data=st.session_state[_ficha_key],
            file_name=f"ficha_{punto_sel.get('codigo', 'punto')}.pdf",
            mime="application/pdf",
            key=f"dl_ficha_{_pid}",
            icon=":material/download:",
            use_container_width=True,
        )

    # ── Phyllum dominante (último análisis fitoplancton)
    try:
        phyllum_info = get_phyllum_dominante_punto(punto_sel["id"])
    except Exception:
        phyllum_info = None
    if phyllum_info:
        # Construimos un parametro "fake" para reusar _color_phyllum
        nombre_filo = phyllum_info["filo"]
        param_fake = {"nombre": nombre_filo, "codigo": nombre_filo}
        col_phy = _color_phyllum(param_fake)
        nombre_dis = _display_nombre_parametro(param_fake)
        cel_str = _format_valor(phyllum_info["cel_ml_equiv"])
        st.markdown(
            f'<div class="lvca-panel-phyllum" style="--lvca-phy-color:{col_phy};">'
            f'<div class="lbl">Phyllum dominante</div>'
            f'<div class="row">'
            f'<div><span class="dot"></span>'
            f'<b>{nombre_dis}</b>'
            f'<span class="cel" style="margin-left:8px;">'
            f'{phyllum_info["n_filos"]} filo(s) detectado(s)</span></div>'
            f'<div class="cel">{cel_str} cel/mL</div>'
            f'</div>'
            f'<div class="meta">'
            f'Muestra {phyllum_info["muestra_codigo"]} · {phyllum_info["fecha_muestreo"]}'
            f'</div></div>',
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
            st.download_button(
                ":material/download: CSV",
                data=df_show.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"excedencias_{punto_sel.get('codigo', 'punto')}.csv",
                mime="text/csv",
                key="dl_excedencias_punto",
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
    # utf-8-sig para que Excel abra tildes/ñ correctamente
    st.download_button(
        ":material/download: CSV",
        data=df_show.to_csv(index=False).encode("utf-8-sig"),
        file_name="comparativa_eca.csv",
        mime="text/csv",
        key=f"dl_comp_eca_{cat}",
    )


main()
