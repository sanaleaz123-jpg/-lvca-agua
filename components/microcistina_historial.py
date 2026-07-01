"""
components/microcistina_historial.py
Historial y comparación de corridas (placas) del ensayo ELISA de Microcistina LR.

Cada corrida guardada (tabla elisa_microcistina_corridas) tiene su curva 4PL, el
control de calidad (QCS) y los criterios de aceptación. Este panel permite:
  - Lista: todas las corridas con sus estadísticas clave (R², control, %CV…).
  - Detalle: abrir una corrida y ver su curva, control y muestras.
  - Comparar curvas: superponer las curvas de calibración de 2+ corridas.
  - Tendencia de control (Levey-Jennings): control, R² y %CV a lo largo del tiempo.

Reutiliza los helpers de estilo/gráficos de components/ui_styles y los datos de
services/microcistina_service (listar_corridas / get_muestras_de_corrida).

Función pública:
    render_historial_microcistina()
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.nav_context import rol_alcanza
from components.ui_styles import (
    COLORS,
    LVCA_COLORWAY,
    apply_plotly_layout,
    icon,
    style_eca_dataframe,
)
from services.elisa_microcistina import STD_CONC_UGL
from services.microcistina_service import (
    eliminar_corrida,
    get_muestras_de_corrida,
    listar_corridas,
)

# Colores de estado de la corrida (espejo de los pills .lvca-pill-*).
_ESTADO_COLORS = {
    "Válida":  {"bg": "#dcfce7", "fg": "#166534"},
    "Revisar": {"bg": "#fce4e4", "fg": "#a31f1f"},
    "Validada":   {"bg": "#dcfce7", "fg": "#166534"},
    "Registrada": {"bg": "#e0f2fe", "fg": "#0369a1"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────────────────────────────────────────

def _num(x) -> Optional[float]:
    """float() tolerante: None/'' → None; no numérico → None."""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _fecha(iso: Optional[str]) -> str:
    """ISO (YYYY-MM-DD…) → DD/MM/YYYY; '—' si falta."""
    if not iso:
        return "—"
    s = str(iso)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return s


def _od_4pl(x: float, A: float, B: float, C: float, D: float) -> float:
    """OD esperada para una concentración según el modelo 4PL ajustado."""
    if x <= 0 or C == 0:
        return A
    try:
        return (A - D) / (1.0 + (x / C) ** B) + D
    except (ZeroDivisionError, ValueError, OverflowError):
        return A


def _params(c: dict):
    """(A, B, C, D, R²) de la corrida, o None si le falta algún parámetro."""
    A, B, C, D = (_num(c.get("param_a")), _num(c.get("param_b")),
                  _num(c.get("param_c")), _num(c.get("param_d")))
    if None in (A, B, C, D):
        return None
    return A, B, C, D, _num(c.get("r2"))


def _label_corrida(c: dict) -> str:
    """Etiqueta legible: fecha + lote + nº de muestras (identificación pedida)."""
    lote = c.get("kit_lote") or "s/lote"
    return f"{_fecha(c.get('fecha_ensayo'))} · lote {lote} · {c.get('n_muestras', 0)} muestra(s)"


def _label_corto(c: dict) -> str:
    """Etiqueta corta para leyendas de gráficos."""
    lote = (c.get("kit_lote") or "s/lote")
    return f"{_fecha(c.get('fecha_ensayo'))} · {lote}"


def _labels_unicos(corridas: list[dict]) -> dict[str, dict]:
    """Mapa etiqueta→corrida, garantizando etiquetas únicas para los selectores."""
    vistos: dict[str, int] = {}
    mapa: dict[str, dict] = {}
    for c in corridas:
        base = _label_corrida(c)
        if base in vistos:
            vistos[base] += 1
            lbl = f"{base} ({vistos[base]})"
        else:
            vistos[base] = 1
            lbl = base
        mapa[lbl] = c
    return mapa


def _badge_validez(ok: bool) -> str:
    """Pill inline 'Corrida válida' / 'Revisar' con iconografía de la plataforma."""
    if ok:
        return (
            "<span style='display:inline-flex;align-items:center;gap:5px;"
            "background:#dcfce7;color:#166534;padding:3px 10px;border-radius:999px;"
            "font-size:0.75rem;font-weight:600'>"
            + icon("check", size=14, color="#166534")
            + "Corrida válida</span>"
        )
    return (
        "<span style='display:inline-flex;align-items:center;gap:5px;"
        "background:#fce4e4;color:#a31f1f;padding:3px 10px;border-radius:999px;"
        "font-size:0.75rem;font-weight:600'>"
        + icon("alert", size=14, color="#a31f1f")
        + "Revisar</span>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Entrada pública
# ─────────────────────────────────────────────────────────────────────────────

def render_historial_microcistina(analista_id: Optional[str] = None) -> None:
    """Panel de historial y comparación de corridas ELISA (montado como sub-pestaña)."""
    corridas = listar_corridas()
    if not corridas:
        st.info(
            "Aún no hay corridas ELISA registradas. Registra una placa en la "
            "pestaña «Registrar» y aquí verás su historial y podrás comparar "
            "curvas y controles entre corridas."
        )
        return

    st.caption(
        f"{len(corridas)} corrida(s) registrada(s). Cada corrida es una placa ELISA "
        "con su curva de calibración 4PL y su control de calidad."
    )

    mapa = _labels_unicos(corridas)
    t_lista, t_det, t_comp, t_tend = st.tabs(
        ["Lista", "Detalle", "Comparar curvas", "Tendencia de control"]
    )
    with t_lista:
        _tab_lista(corridas)
    with t_det:
        _tab_detalle(mapa, analista_id)
    with t_comp:
        _tab_comparar(mapa)
    with t_tend:
        _tab_tendencia(corridas)


# ─────────────────────────────────────────────────────────────────────────────
# Pestaña: Lista
# ─────────────────────────────────────────────────────────────────────────────

def _tab_lista(corridas: list[dict]) -> None:
    n = len(corridas)
    validas = sum(1 for c in corridas if c.get("es_valida"))
    r2s = [v for v in (_num(c.get("r2")) for c in corridas) if v is not None]
    ctrls = [v for v in (_num(c.get("control_conc_prom")) for c in corridas) if v is not None]

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Corridas", n)
    k2.metric("Válidas", f"{validas}/{n}")
    k3.metric("R² promedio", f"{sum(r2s) / len(r2s):.4f}" if r2s else "—")
    k4.metric("Control prom.", f"{sum(ctrls) / len(ctrls):.3f} µg/L" if ctrls else "—")

    filas = []
    for c in corridas:
        filas.append({
            "Fecha": _fecha(c.get("fecha_ensayo")),
            "Lote": c.get("kit_lote") or "—",
            "Muestras": int(c.get("n_muestras", 0)),
            "Validadas": int(c.get("n_validadas", 0)),
            "Campañas": ", ".join(c.get("campanas") or []) or "—",
            "R²": _num(c.get("r2")),
            "Control µg/L": _num(c.get("control_conc_prom")),
            "%CV control": _num(c.get("control_cv")),
            "Factor": _num(c.get("factor_dilucion")),
            "Estado": "Válida" if c.get("es_valida") else "Revisar",
        })
    df = pd.DataFrame(filas)
    styler = style_eca_dataframe(df, state_col="Estado", state_colors=_ESTADO_COLORS)
    styler = styler.format(
        {"R²": "{:.4f}", "Control µg/L": "{:.3f}", "%CV control": "{:.2f}",
         "Factor": "{:.2f}"},
        na_rep="—",
    )
    st.dataframe(styler, hide_index=True, use_container_width=True)
    st.caption(
        "Estado «Válida» = R² ≥ 0.98, control dentro de nominal ± tolerancia y "
        "%CV del control ≤ máximo. Para el detalle de una corrida usa la pestaña "
        "«Detalle»."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pestaña: Detalle de una corrida
# ─────────────────────────────────────────────────────────────────────────────

def _tab_detalle(mapa: dict[str, dict], analista_id: Optional[str] = None) -> None:
    sel = st.selectbox("Elige una corrida", list(mapa.keys()), key="mc_hist_det_sel")
    c = mapa[sel]

    par = _params(c)
    m1, m2, m3, m4, m5 = st.columns(5)
    if par:
        A, B, C, D, r2 = par
        m1.metric("A (Amax)", f"{A:.4f}")
        m2.metric("B", f"{B:.4f}")
        m3.metric("C (IC50)", f"{C:.4f}")
        m4.metric("D", f"{D:.4f}")
        m5.metric("R²", f"{r2:.5f}" if r2 is not None else "—")
    else:
        st.warning("Esta corrida no tiene los parámetros de la curva guardados.")

    ctrl = _num(c.get("control_conc_prom"))
    cv = _num(c.get("control_cv"))
    nom = _num(c.get("qcs_nominal")) or 0.750
    tol = _num(c.get("qcs_tolerancia")) or 0.185
    cvmax = _num(c.get("cv_max")) or 15.0
    ctrl_txt = f"{ctrl:.3f}" if ctrl is not None else "—"
    cv_txt = f"{cv:.2f}%" if cv is not None else "—"
    st.markdown(
        f"**Control (QCS):** {ctrl_txt} µg/L · rango aceptable {nom - tol:.3f}–{nom + tol:.3f} "
        f"µg/L · %CV {cv_txt} (máx {cvmax:.0f}%) &nbsp; {_badge_validez(bool(c.get('es_valida')))}"
        f"<br><small>Lote {c.get('kit_lote') or '—'} · fecha {_fecha(c.get('fecha_ensayo'))} · "
        f"factor {(_num(c.get('factor_dilucion')) or 1.0):.2f} · "
        f"campañas: {', '.join(c.get('campanas') or []) or '—'}</small>",
        unsafe_allow_html=True,
    )

    if par:
        _plot_curva_detalle(c, par)

    st.markdown("##### Muestras de esta corrida")
    muestras = get_muestras_de_corrida(c["id"])
    n_val = sum(1 for m in muestras if m.get("validado"))
    if not muestras:
        st.caption("Esta corrida no tiene muestras asignadas.")
    else:
        filas = []
        for m in muestras:
            ug = m.get("valor_ugL")
            filas.append({
                "Campaña": m.get("campana") or "—",
                "Muestra": m.get("muestra") or "—",
                "Fecha": _fecha(m.get("fecha")),
                "Valor µg/L": ug,
                "Valor mg/L": (ug / 1000.0) if ug is not None else None,
                "OD 1": m.get("od_1"),
                "OD 2": m.get("od_2"),
                "%CV": m.get("cv_pct"),
                "Cualif.": m.get("cualificador") or "",
                "Estado": "Validada" if m.get("validado") else "Registrada",
            })
        dfm = pd.DataFrame(filas)
        stm = style_eca_dataframe(dfm, state_col="Estado", state_colors=_ESTADO_COLORS)
        stm = stm.format(
            {"Valor µg/L": "{:.4f}", "Valor mg/L": "{:.6f}", "OD 1": "{:g}",
             "OD 2": "{:g}", "%CV": "{:.1f}"},
            na_rep="—",
        )
        st.dataframe(stm, hide_index=True, use_container_width=True)

    _zona_eliminar(c, len(muestras), n_val, analista_id)


def _zona_eliminar(c: dict, n_muestras: int, n_val: int, analista_id: Optional[str]) -> None:
    """Zona de borrado de la corrida (solo analista_lab+, con confirmación)."""
    if not rol_alcanza("analista_lab"):
        return  # solo analista de laboratorio / administrador puede eliminar

    with st.expander("Eliminar esta corrida", icon=":material/delete:"):
        st.markdown(
            f"Se eliminarán **la corrida** (curva y control) y sus **{n_muestras} "
            "resultado(s)** de muestra. Las muestras quedarán como si no se hubieran "
            "analizado. **Esta acción no se puede deshacer.**"
        )
        if n_val:
            st.warning(
                f"Esta corrida tiene {n_val} resultado(s) validado(s) (firmados). "
                "Anula la validación de esas muestras antes de poder eliminarla."
            )
            return

        ok = st.checkbox(
            f"Confirmo que quiero eliminar esta corrida y sus {n_muestras} resultado(s).",
            key=f"mc_hist_del_chk_{c['id']}",
        )
        st.markdown('<div class="lvca-danger">', unsafe_allow_html=True)
        pulsado = st.button(
            "Eliminar corrida", type="primary", disabled=not ok,
            key=f"mc_hist_del_btn_{c['id']}",
        )
        st.markdown("</div>", unsafe_allow_html=True)
        if pulsado:
            try:
                res = eliminar_corrida(c["id"], usuario_id=analista_id)
                # Los selectores guardan la etiqueta de la corrida borrada; se
                # limpian para que no apunten a una opción inexistente tras el rerun.
                for k in ("mc_hist_det_sel", "mc_hist_cmp_sel"):
                    st.session_state.pop(k, None)
                st.success(
                    f"Corrida eliminada ({res['resultados_eliminados']} resultado(s) borrados)."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo eliminar: {exc}")


def _plot_curva_detalle(c: dict, par) -> None:
    A, B, C, D, _r2 = par
    xs = [i * 0.05 for i in range(0, 101)]
    fig = go.Figure()
    fig.add_scatter(x=xs, y=[_od_4pl(x, A, B, C, D) for x in xs],
                    mode="lines", name="Curva 4PL",
                    line=dict(color=COLORS["primary"]))
    std = c.get("std_od") or []
    try:
        ys = [(float(o[0]) + float(o[1])) / 2.0 for o in std]
        fig.add_scatter(x=list(STD_CONC_UGL)[:len(ys)], y=ys, mode="markers",
                        name="Estándares", marker=dict(size=9, color=COLORS["danger"]))
    except (TypeError, ValueError, IndexError):
        pass
    apply_plotly_layout(fig, height=300, legend=False,
                        x_title="Microcistina (µg/L)", y_title="OD (450 nm)",
                        margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Pestaña: Comparar curvas
# ─────────────────────────────────────────────────────────────────────────────

def _tab_comparar(mapa: dict[str, dict]) -> None:
    labels = list(mapa.keys())
    default = labels[:2]
    sel = st.multiselect(
        "Elige 2 o más corridas para superponer sus curvas de calibración",
        labels, default=default, key="mc_hist_cmp_sel",
    )
    if len(sel) < 2:
        st.info("Selecciona al menos 2 corridas.")
        return

    fig = go.Figure()
    xs = [i * 0.05 for i in range(0, 101)]
    filas = []
    for i, lbl in enumerate(sel):
        c = mapa[lbl]
        par = _params(c)
        color = LVCA_COLORWAY[i % len(LVCA_COLORWAY)]
        nombre = _label_corto(c)
        if par:
            A, B, C, D, r2 = par
            fig.add_scatter(x=xs, y=[_od_4pl(x, A, B, C, D) for x in xs],
                            mode="lines", name=nombre, line=dict(color=color))
            std = c.get("std_od") or []
            try:
                ys = [(float(o[0]) + float(o[1])) / 2.0 for o in std]
                fig.add_scatter(x=list(STD_CONC_UGL)[:len(ys)], y=ys, mode="markers",
                                name=nombre, marker=dict(size=7, color=color),
                                showlegend=False)
            except (TypeError, ValueError, IndexError):
                pass
        filas.append({
            "Corrida": nombre,
            "A": _num(c.get("param_a")),
            "B": _num(c.get("param_b")),
            "C (IC50)": _num(c.get("param_c")),
            "D": _num(c.get("param_d")),
            "R²": _num(c.get("r2")),
            "Control µg/L": _num(c.get("control_conc_prom")),
            "%CV control": _num(c.get("control_cv")),
            "Estado": "Válida" if c.get("es_valida") else "Revisar",
        })
    apply_plotly_layout(fig, height=420, legend=True,
                        x_title="Microcistina (µg/L)", y_title="OD (450 nm)")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### Parámetros comparados")
    df = pd.DataFrame(filas)
    styler = style_eca_dataframe(df, state_col="Estado", state_colors=_ESTADO_COLORS)
    styler = styler.format(
        {"A": "{:.4f}", "B": "{:.4f}", "C (IC50)": "{:.4f}", "D": "{:.4f}",
         "R²": "{:.5f}", "Control µg/L": "{:.3f}", "%CV control": "{:.2f}"},
        na_rep="—",
    )
    st.dataframe(styler, hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Pestaña: Tendencia de control (Levey-Jennings)
# ─────────────────────────────────────────────────────────────────────────────

def _mediana(vals: list[float], default: float) -> float:
    xs = sorted(v for v in vals if v is not None)
    if not xs:
        return default
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def _tab_tendencia(corridas: list[dict]) -> None:
    orden = sorted(
        corridas,
        key=lambda c: (c.get("fecha_ensayo") or c.get("created_at") or ""),
    )
    if len(orden) < 2:
        st.info("Se necesitan al menos 2 corridas para ver una tendencia.")
        return

    metrica = st.selectbox(
        "Métrica de control de calidad",
        ["Control (µg/L)", "R² de la curva", "%CV del control"],
        key="mc_hist_tend_metrica",
    )

    # Eje X: etiquetas únicas y ordenadas (nº + fecha) para no fusionar duplicados.
    x = [f"{i + 1}. {_fecha(c.get('fecha_ensayo'))}" for i, c in enumerate(orden)]
    hover = [f"Lote {c.get('kit_lote') or '—'}<br>{', '.join(c.get('campanas') or []) or '—'}"
             for c in orden]

    if metrica == "Control (µg/L)":
        y = [_num(c.get("control_conc_prom")) for c in orden]
        nom = _mediana([_num(c.get("qcs_nominal")) for c in orden], 0.750)
        tol = _mediana([_num(c.get("qcs_tolerancia")) for c in orden], 0.185)
        centro, low, high, y_title = nom, nom - tol, nom + tol, "Control (µg/L)"
    elif metrica == "R² de la curva":
        y = [_num(c.get("r2")) for c in orden]
        centro, low, high, y_title = None, 0.98, None, "R²"
    else:  # %CV del control
        y = [_num(c.get("control_cv")) for c in orden]
        cvmax = _mediana([_num(c.get("cv_max")) for c in orden], 15.0)
        centro, low, high, y_title = None, None, cvmax, "%CV del control"

    # Color de cada punto: rojo si queda fuera de la banda de aceptación.
    def _fuera(v):
        if v is None:
            return False
        if low is not None and v < low:
            return True
        if high is not None and v > high:
            return True
        return False

    colores = [COLORS["danger"] if _fuera(v) else COLORS["primary"] for v in y]

    fig = go.Figure()
    fig.add_scatter(
        x=x, y=y, mode="lines+markers", name=y_title,
        line=dict(color=COLORS["text_light"], width=1.5),
        marker=dict(size=9, color=colores),
        customdata=hover, hovertemplate="%{x}<br>%{y}<br>%{customdata}<extra></extra>",
    )
    if centro is not None:
        fig.add_hline(y=centro, line_dash="solid", line_color=COLORS["success"],
                      annotation_text="nominal", annotation_position="right")
    if low is not None:
        fig.add_hline(y=low, line_dash="dash", line_color=COLORS["danger"],
                      annotation_text="mín", annotation_position="right")
    if high is not None:
        fig.add_hline(y=high, line_dash="dash", line_color=COLORS["danger"],
                      annotation_text="máx", annotation_position="right")
    apply_plotly_layout(fig, height=380, legend=False, x_title="Corrida (orden cronológico)",
                        y_title=y_title)
    st.plotly_chart(fig, use_container_width=True)

    n_fuera = sum(1 for v in y if _fuera(v))
    if n_fuera:
        st.warning(
            f"{n_fuera} corrida(s) con {metrica.lower()} fuera del rango de aceptación "
            "(puntos en rojo). Revisar posible deriva del método o del kit."
        )
    else:
        st.caption(
            "Todas las corridas dentro del rango de aceptación. La línea verde es el "
            "valor nominal y las punteadas los límites — estilo carta de control "
            "(Levey-Jennings)."
        )
