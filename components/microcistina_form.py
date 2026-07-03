"""
components/microcistina_form.py
Panel del ensayo ELISA de Microcistina LR (kit SAES/ABRAXIS, EPA 546), montado
en *Resultados de Laboratorio*.

Flujo único: se sube la placa de absorbancias (Excel del lector) o el libro del
Solver; la plataforma ajusta la curva 4PL, calcula el control y las
concentraciones de las muestras cargadas (hasta 41), muestra la curva de
calibración y el mapa de la placa, y el analista asigna cada muestra a su
campaña/estación y registra. No siempre se cargan todos los pocillos: la
cantidad de muestras se detecta y es ajustable. Una placa puede abarcar varias
campañas. No hay ingreso manual de absorbancias.

Función pública:
    render_panel_microcistina(analista_id)
"""

from __future__ import annotations

import hashlib
from typing import Optional

import pandas as pd
import streamlit as st

from components.ui_styles import COLORS, chip_eca_html, icon
from services.elisa_microcistina import STD_CONC_UGL
from services.microcistina_import import (
    mapa_placa,
    parse_excel_solver,
    parse_grid_text,
    parse_placa_cruda,
    parse_placa_excel,
)
from services.microcistina_service import (
    estado_registro_microcistina,
    get_muestras_agrupadas_por_campana,
    get_param_microcistina,
    guardar_corrida_importada,
)
from services.resultado_service import validar_resultados


def render_panel_microcistina(
    campana_id: Optional[str] = None,
    analista_id: Optional[str] = None,
) -> None:
    """Panel ELISA de microcistina: importar placa → curva + cálculo → asignar."""
    st.caption(
        "Sube la placa de absorbancias del lector (o el Excel del Solver). La "
        "plataforma ajusta la curva 4PL, calcula el control y las concentraciones, "
        "y tú asignas cada muestra a su campaña/estación. Una placa puede abarcar "
        "varias campañas."
    )
    _render_leyenda()
    _render_import(analista_id)


def _render_leyenda() -> None:
    """Leyenda de las siglas usadas en el ensayo."""
    with st.expander("¿Qué significan las siglas?", icon=":material/help:"):
        st.markdown(
            "- **OD**: densidad óptica (absorbancia a 450 nm). *A mayor OD, menor microcistina* (relación inversa).\n"
            "- **ST0–ST5**: estándares de calibración (0, 0.05, 0.15, 0.4, 1.5 y 5.0 µg/L).\n"
            "- **Control / QCS**: Estándar de Control de Calidad (valor esperado 0.75 ± 0.185 µg/L).\n"
            "- **LRB**: blanco de reactivo de laboratorio (*Laboratory Reagent Blank*).\n"
            "- **%CV**: coeficiente de variación de los duplicados (criterio: muestras < 15 %, estándares < 10 %).\n"
            "- **L.D.M.**: Límite de Detección del Método = 0.000016 mg/L (0.016 µg/L).\n"
            "- **L.C.M.**: Límite de Cuantificación del Método = 0.00005 mg/L (0.05 µg/L). "
            "Valores por debajo se reportan como *< 0.00005 mg/L*.\n"
            "- **Curva 4PL**: ajuste logístico de 4 parámetros — **A** (Amax), **B** (pendiente), "
            "**C** (IC50), **D** (mínimo); **R²** = bondad de ajuste.\n"
            "- **B/B0 %**: señal de cada estándar respecto al estándar 0 (Amax).\n"
            "- **ECA**: Estándar de Calidad Ambiental (D.S. 004-2017-MINAM). Microcistina Cat. A2 = 1 µg/L "
            "(igual que el límite de la OMS).\n"
            "- **Unidades**: 1 mg/L = 1000 µg/L (ppb)."
        )


def _render_import(analista_id: Optional[str]) -> None:
    """Importa una corrida (placa OD o Excel del Solver) y la procesa."""
    modo = st.radio(
        "Origen de los datos",
        ["Placa de absorbancias (Excel)", "Excel del Solver"],
        horizontal=True, key="mc_modo_import",
    )
    imp = None
    if modo == "Excel del Solver":
        st.caption(
            "Sube el libro del Solver; la plataforma toma los valores ya "
            "calculados."
        )
        up = st.file_uploader("Archivo .xlsx del Solver", type=["xlsx"], key="mc_xlsx")
        if up:
            try:
                imp = parse_excel_solver(up.getvalue())
            except Exception as exc:
                st.error(f"No se pudo leer el archivo: {exc}")
    else:
        st.caption(
            "Sube el Excel con la placa de absorbancias (8 filas A–H × 12 "
            "columnas) tal como sale del lector. La plataforma ubica los "
            "estándares (ST0–ST5), el control y las muestras (hasta 41) con la "
            "distribución fija del laboratorio, detecta cuántas se cargaron y "
            "calcula todo (curva 4PL + concentraciones), igual que el Solver."
        )
        up = st.file_uploader("Excel de la placa (.xlsx)", type=["xlsx"],
                              key="mc_placa_xlsx")
        if up:
            try:
                imp = parse_placa_excel(up.getvalue())
            except Exception as exc:
                st.error(f"No se pudo leer la placa: {exc}")
        else:
            with st.expander("…o pegar la placa como texto"):
                st.caption(
                    "Pega solo las columnas que se corrieron (en pares de "
                    "réplicas): col 1-2 = estándares (ST0–ST5) + control + S1; "
                    "col 3-4, 5-6… = muestras. Lo que falte se toma como pocillos "
                    "vacíos. Mínimo: las 6 filas de estándares con sus 2 réplicas."
                )
                txt = st.text_area(
                    "Placa OD (8 filas A–H; 2 a 12 columnas)", height=200, key="mc_grid",
                    placeholder=("0.959 1.002 0.919 0.866\n"
                                 "0.861 0.806 0.85  0.92\n"
                                 "… hasta la fila H (aquí solo 4 columnas)"),
                )
                if txt.strip():
                    try:
                        imp = parse_placa_cruda(parse_grid_text(txt))
                    except Exception as exc:
                        st.error(f"No se pudo leer la placa: {exc}")
    if imp is None:
        return
    _render_resultado(imp, analista_id)


def _od_de_conc(conc: float, c) -> float:
    """OD esperada para una concentración según la curva 4PL ajustada."""
    if conc <= 0:
        return c.A
    return (c.A - c.D) / (1.0 + (conc / c.C) ** c.B) + c.D


def _render_curva(imp) -> None:
    """Curva de calibración: tabla de estándares + parámetros + gráfico."""
    c = imp.curva
    if not imp.std_od:
        return
    od0 = ((imp.std_od[0][0] + imp.std_od[0][1]) / 2.0) or 1.0
    filas = []
    for i, (o1, o2) in enumerate(imp.std_od):
        conc = STD_CONC_UGL[i]
        mean = (o1 + o2) / 2.0
        cv = (abs(o1 - o2) / 1.4142135624 / mean * 100.0) if mean else 0.0
        filas.append({
            "Estándar": f"ST{i}", "µg/L": conc, "OD 1": o1, "OD 2": o2,
            "OD prom": round(mean, 4), "%CV": round(cv, 2),
            "B/B0 %": round(mean / od0 * 100.0, 1),
            "OD ajustada": round(_od_de_conc(conc, c), 4),
        })

    st.markdown("##### Curva de calibración")
    cc1, cc2 = st.columns([1.1, 1])
    with cc1:
        st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
        st.caption(
            f"4PL  Y = (A−D)/(1+(X/C)^B)+D · A={c.A:.4f}  B={c.B:.4f}  "
            f"C={c.C:.4f}  D={c.D:.4f} · R²={c.r2:.5f}"
        )
        if not c.es_valida():
            st.warning("La curva no cumple algún criterio guía (A>0.7, D<0.15, R²≥0.98).")
    with cc2:
        try:
            import plotly.graph_objects as go
            xs = [i * 0.05 for i in range(0, 101)]
            fig = go.Figure()
            fig.add_scatter(x=xs, y=[_od_de_conc(x, c) for x in xs],
                            mode="lines", name="Curva 4PL")
            fig.add_scatter(
                x=list(STD_CONC_UGL),
                y=[(o1 + o2) / 2 for o1, o2 in imp.std_od],
                mode="markers", name="Estándares",
                marker=dict(size=9, color="#c0392b"),
            )
            fig.update_layout(
                height=300, margin=dict(l=10, r=10, t=10, b=10), showlegend=False,
                xaxis_title="Microcistina (µg/L)", yaxis_title="OD (450 nm)",
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            pass


def _render_validez(imp) -> None:
    """Panel de control de calidad de la corrida con semáforo Cumple/Revisar."""
    c = imp.curva
    R2_MIN, A_MIN, D_MAX = 0.98, 0.7, 0.15
    QCS_NOM, QCS_TOL, CV_MUESTRA, CV_STD = 0.750, 0.185, 15.0, 10.0
    low, high = QCS_NOM - QCS_TOL, QCS_NOM + QCS_TOL
    ctrl = imp.control.conc_ugL

    std_cvs = [(abs(o1 - o2) / 1.4142135624 / ((o1 + o2) / 2) * 100.0)
               for o1, o2 in imp.std_od if (o1 + o2)]
    std_max = max(std_cvs) if std_cvs else 0.0
    altos = [m.label for m in imp.muestras if m.cv_pct > CV_MUESTRA]

    # (indicador, valor, ok, criterio, crítico)
    checks = [
        ("Ajuste de curva (R²)", f"{c.r2:.5f}", c.r2 >= R2_MIN, f"≥ {R2_MIN}", True),
        ("Señal máxima (A)", f"{c.A:.3f}", c.A > A_MIN, f"> {A_MIN}", False),
        ("Mínimo de curva (D)", f"{c.D:.3f}", c.D < D_MAX, f"< {D_MAX}", False),
        ("Control (µg/L)", f"{ctrl:.3f}" if ctrl is not None else "—",
         ctrl is not None and low <= ctrl <= high, f"{low:.3f}–{high:.3f}", True),
        ("%CV del control", f"{imp.control.cv_pct:.2f}%",
         imp.control.cv_pct <= CV_MUESTRA, f"≤ {CV_MUESTRA:.0f}%", True),
        ("%CV estándares (máx)", f"{std_max:.2f}%", std_max <= CV_STD, f"≤ {CV_STD:.0f}%", False),
        (f"Muestras con %CV > {CV_MUESTRA:.0f}%", str(len(altos)), len(altos) == 0, "0", False),
    ]

    st.markdown("##### Validez de la corrida")
    df = pd.DataFrame([{
        "Indicador": ind, "Valor": val, "Criterio": crit,
        "Estado": "✅ Cumple" if ok else "⚠ Revisar",
    } for ind, val, ok, crit, _ in checks])
    st.dataframe(df, hide_index=True, use_container_width=True)

    criticos_ok = all(ok for (_ind, _val, ok, _crit, crit_flag) in checks if crit_flag)
    advert = [ind for (ind, _v, ok, _c, _crit) in checks if not ok]
    if not criticos_ok:
        st.error("⚠ Revisar la corrida: no cumple un criterio crítico "
                 "(control fuera de rango, R² bajo o %CV del control alto).")
    elif advert:
        msg = "Corrida válida, con observaciones: " + "; ".join(advert) + "."
        if altos:
            msg += f" Muestras a reanalizar (%CV>{CV_MUESTRA:.0f}%): {', '.join(altos)}."
        st.warning(msg)
    else:
        st.success("✅ Corrida válida: cumple todos los criterios de control de calidad.")


# ── Mapa de la placa: paleta y helpers de color ──────────────────────────────
_OD_STOPS = ["#eff6ff", "#bae6fd", "#38bdf8", "#0284c7", "#075985"]   # frío (OD)
_CONC_STOPS = ["#fef9f5", "#fed7aa", "#fb923c", "#ea580c", "#b91c1c"]  # cálido (conc)
_CONC_OVER = "#7f1d1d"   # muestra sobre rango
_NEUTRAL = "#e9eef5"     # estándar en la vista de concentración

_PLACA_CSS = """
<style>
html,body{margin:0;background:transparent;}
.mc-wrap{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  padding:46px 6px 8px;box-sizing:border-box;color:#0f172a;}
.mc-plate{display:grid;grid-template-columns:24px repeat(12,minmax(0,1fr));
  gap:7px;max-width:760px;margin:0 auto;}
.mc-hd{font-size:11px;color:#94a3b8;text-align:center;align-self:center;font-weight:600;}
.mc-rl{font-size:11px;color:#94a3b8;font-weight:600;display:flex;align-items:center;justify-content:center;}
.mc-cell{position:relative;display:flex;align-items:center;justify-content:center;}
.mc-well{width:100%;max-width:40px;aspect-ratio:1;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:9.5px;font-weight:700;letter-spacing:.2px;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.35),0 1px 2px rgba(15,23,42,.14);
  animation:mcpop .5s cubic-bezier(.2,.7,.3,1.3) both;
  transition:transform .13s ease,box-shadow .13s ease;}
.mc-well:hover{transform:scale(1.18);box-shadow:0 6px 16px rgba(15,23,42,.28);z-index:6;}
.mc-empty{width:100%;max-width:40px;aspect-ratio:1;border-radius:50%;
  border:1.5px dashed #cbd5e1;background:#f8fafc;
  animation:mcpop .5s cubic-bezier(.2,.7,.3,1.3) both;}
@keyframes mcpop{0%{opacity:0;transform:scale(.2)}100%{opacity:1;transform:scale(1)}}
.mc-tip{position:absolute;bottom:120%;left:50%;transform:translateX(-50%) translateY(5px);
  background:#0f172a;color:#fff;padding:6px 9px;border-radius:7px;font-size:11px;
  line-height:1.4;white-space:nowrap;font-weight:500;opacity:0;pointer-events:none;
  transition:opacity .13s ease,transform .13s ease;z-index:30;box-shadow:0 8px 22px rgba(0,0,0,.28);}
.mc-tip:after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);
  border:5px solid transparent;border-top-color:#0f172a;}
.mc-cell:hover .mc-tip{opacity:1;transform:translateX(-50%) translateY(0);}
.mc-legend{display:flex;align-items:center;gap:8px;justify-content:center;flex-wrap:wrap;
  margin:22px auto 0;max-width:760px;font-size:11px;color:#475569;}
.mc-bar{width:150px;height:9px;border-radius:5px;box-shadow:inset 0 0 0 1px rgba(15,23,42,.08);}
.mc-lbl{font-variant-numeric:tabular-nums;}
.mc-sep{width:1px;height:16px;background:#e2e8f0;margin:0 4px;}
.mc-chip{display:inline-flex;align-items:center;gap:5px;}
.mc-chip i{width:12px;height:12px;border-radius:50%;display:inline-block;box-shadow:0 1px 2px rgba(15,23,42,.14);}
.mc-chip i.dash{background:#f8fafc;border:1.5px dashed #cbd5e1;box-shadow:none;}
</style>
"""


def _hex_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _grad(stops, t: float) -> str:
    """Color interpolado a lo largo de ``stops`` para t ∈ [0,1]."""
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    seg = t * (len(stops) - 1)
    i = min(int(seg), len(stops) - 2)
    f = seg - i
    a, b = _hex_rgb(stops[i]), _hex_rgb(stops[i + 1])
    return "#%02x%02x%02x" % tuple(round(a[k] + (b[k] - a[k]) * f) for k in range(3))


def _lum(hexcolor: str) -> float:
    r, g, b = _hex_rgb(hexcolor)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _placa_html(imp, n_activas: int, usar_conc: bool) -> str:
    """HTML de la placa 8×12 con pocillos circulares (sin el <style>).

    Función pura (sin Streamlit) para poder previsualizarla y testearla.
    Reconstruye la distribución fija (ST0–ST5 y control en col 1-2; muestras
    S1..SN serpenteando); los pocillos sobrantes se muestran vacíos.
    """
    mapa = mapa_placa()
    ROWS = "ABCDEFGH"
    wells: dict = {}     # (fila, col) -> datos del pocillo

    def _put(r, c1, c2, label, od1, od2, conc, cv, role, over=False):
        media = (od1 + od2) / 2.0
        for c in (c1, c2):
            wells[(r, c)] = dict(label=label, od=media, od1=od1, od2=od2,
                                 conc=conc, cv=cv, role=role, over=over)

    for i, (r, c1, c2) in enumerate(mapa["std"]):
        if i < len(imp.std_od):
            o1, o2 = imp.std_od[i]
            _put(r, c1, c2, f"ST{i}", o1, o2, STD_CONC_UGL[i], None, "std")
    cr, cc1, cc2 = mapa["control"]
    o1, o2 = imp.control_od
    _put(cr, cc1, cc2, "CT", o1, o2, imp.control.conc_ugL, imp.control.cv_pct, "control")
    for n in sorted(mapa["samples"].keys()):
        if n > n_activas or n > len(imp.muestras):
            continue
        r, c1, c2 = mapa["samples"][n]
        m = imp.muestras[n - 1]
        _put(r, c1, c2, f"S{n}", m.od_1, m.od_2, m.conc_ugL, m.cv_pct,
             "sample", over=(m.conc_ugL is None))

    # Escala activa (los estándares no entran en la de concentración).
    if usar_conc:
        vals = [w["conc"] for w in wells.values()
                if w["role"] in ("sample", "control") and w["conc"] is not None]
        vmin, vmax, stops = 0.0, (max(vals) if vals else 1.0), _CONC_STOPS
    else:
        vals = [w["od"] for w in wells.values()]
        vmin, vmax, stops = (min(vals), max(vals), _OD_STOPS) if vals else (0.0, 1.0, _OD_STOPS)

    def _fill(w) -> str:
        if usar_conc:
            if w["role"] == "std":
                return _NEUTRAL
            if w["over"]:
                return _CONC_OVER
            if w["conc"] is None:
                return _NEUTRAL
            t = (w["conc"] - vmin) / (vmax - vmin) if vmax > vmin else 0.5
            return _grad(stops, t)
        t = (w["od"] - vmin) / (vmax - vmin) if vmax > vmin else 0.5
        return _grad(stops, t)

    def _tip(w) -> str:
        od = f"{w['od1']:g}/{w['od2']:g}"
        if w["role"] == "std":
            return f"<b>{w['label']}</b> · estándar<br>{w['conc']:g} µg/L · OD {od}"
        if w["role"] == "control":
            cc = f"{w['conc']:.3f} µg/L" if w["conc"] is not None else "—"
            return f"<b>{w['label']}</b> · control<br>OD {od} · %CV {w['cv']:.1f}<br>{cc}"
        if w["over"]:
            return f"<b>{w['label']}</b><br>OD {od}<br>⚠ sobre rango (&gt;5 µg/L)"
        cc = f"{w['conc']:.4g} µg/L" if w["conc"] is not None else "—"
        return f"<b>{w['label']}</b><br>OD {od} · %CV {w['cv']:.1f}<br>{cc}"

    cells = ['<div class="mc-hd"></div>']
    cells += [f'<div class="mc-hd">{c}</div>' for c in range(1, 13)]
    for r in range(8):
        cells.append(f'<div class="mc-rl">{ROWS[r]}</div>')
        for c in range(12):
            delay = (r * 12 + c) * 0.010
            w = wells.get((r, c))
            if w is None:
                cells.append(
                    '<div class="mc-cell"><div class="mc-empty" '
                    f'style="animation-delay:{delay:.2f}s"></div></div>')
                continue
            fill = _fill(w)
            txt = "#ffffff" if _lum(fill) < 0.6 else "#0f172a"
            cells.append(
                '<div class="mc-cell">'
                f'<div class="mc-well" style="background:{fill};color:{txt};'
                f'animation-delay:{delay:.2f}s">{w["label"]}'
                f'<span class="mc-tip">{_tip(w)}</span></div></div>')
    plate = '<div class="mc-plate">' + "".join(cells) + "</div>"

    unidad = "µg/L" if usar_conc else "OD"
    # Los chips de "Estándar" (gris) y "Sobre rango" solo aplican en la vista de
    # concentración (en la de OD los estándares sí van coloreados en el gradiente).
    chips = ""
    if usar_conc:
        chips += '<span class="mc-chip"><i style="background:#e9eef5"></i>Estándar</span>'
        chips += '<span class="mc-chip"><i style="background:#7f1d1d"></i>Sobre rango</span>'
    chips += '<span class="mc-chip"><i class="dash"></i>Vacío</span>'
    legend = (
        '<div class="mc-legend">'
        f'<span class="mc-lbl">{vmin:.2f}</span>'
        f'<span class="mc-bar" style="background:linear-gradient(90deg,{", ".join(stops)})"></span>'
        f'<span class="mc-lbl">{vmax:.2f} {unidad}</span>'
        '<span class="mc-sep"></span>'
        f'{chips}'
        "</div>")

    return '<div class="mc-wrap">' + plate + legend + "</div>"


def _render_placa_mapa(imp, n_activas: int) -> None:
    """Mapa de la placa 8×12 con pocillos circulares: color por OD o
    concentración, animación de entrada escalonada y hover con detalle."""
    import streamlit.components.v1 as components

    st.markdown("##### Distribución de la placa")
    usar_conc = st.radio(
        "Colorear por", ["OD", "Concentración (µg/L)"],
        horizontal=True, key="mc_placa_color", label_visibility="collapsed",
    ).startswith("Conc")

    components.html(_PLACA_CSS + _placa_html(imp, n_activas, usar_conc),
                    height=500, scrolling=False)

    nota = (" En esta vista los estándares se muestran en gris (fuera de la escala "
            "de concentración)." if usar_conc else "")
    st.caption(
        "Placa 8×12. Col 1-2: estándares (ST0–ST5) y control (CT); muestras "
        f"S1..S{n_activas} serpenteando de H→A. Pasa el cursor por un pocillo para "
        "ver su detalle." + nota)


def _huella_placa(imp) -> str:
    """Huella estable de la placa (OD de estándares, control y muestras).

    Sirve para detectar cuándo se sube una placa DISTINTA entre reruns y así
    reiniciar el N autodetectado del widget (que de otro modo hereda el valor de
    la placa anterior, porque st.number_input persiste su 'key' e ignora 'value').
    """
    raw = repr((
        imp.std_od, imp.control_od,
        tuple((m.od_1, m.od_2) for m in imp.muestras),
        imp.n_muestras_detectadas,
    ))
    return hashlib.md5(raw.encode()).hexdigest()


def _render_resultado(imp, analista_id: Optional[str]) -> None:
    """Resumen de la corrida + curva + mapa de la placa + mapeo + registro."""
    c = imp.curva
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("A (Amax)", f"{c.A:.4f}")
    k2.metric("B", f"{c.B:.4f}")
    k3.metric("C (IC50)", f"{c.C:.4f}")
    k4.metric("D", f"{c.D:.4f}")
    k5.metric("R²", f"{c.r2:.5f}")

    # ── Nº de muestras cargadas (autodetectado, ajustable) ───────────────────
    # No siempre se cargan todos los pocillos: la placa se procesa completa y el
    # analista fija cuántas muestras se corrieron realmente. Las demás quedan
    # como pocillos vacíos al final del orden serpenteante y se ignoran.
    cap = len(imp.muestras)
    n_det = min(cap, imp.n_muestras_detectadas or cap)
    # El number_input persiste su valor por 'key' entre reruns e ignora 'value='
    # una vez creado. Para que cada placa NUEVA aplique SU propio N autodetectado
    # (y no herede el de la placa anterior), reiniciamos el estado del widget
    # cuando cambia la huella de la placa.
    fp = _huella_placa(imp)
    if st.session_state.get("mc_n_muestras_fp") != fp:
        st.session_state["mc_n_muestras_fp"] = fp
        st.session_state["mc_n_muestras"] = int(n_det)
    nc1, nc2 = st.columns([1, 2.4])
    n_sel = int(nc1.number_input(
        "Nº de muestras en la placa", min_value=1, max_value=max(1, cap),
        step=1, key="mc_n_muestras",
    ))
    nc2.caption(
        f"Se detectaron **{n_det}** muestra(s) cargada(s)"
        + (f" · {cap - n_det} pocillo(s) vacío(s) al final." if cap - n_det else ".")
        + " Ajústalo si es necesario. Si una muestra muy tóxica (OD≈0) quedó al "
        "final, súbelo a mano para no perderla."
    )
    # Recortar a las muestras realmente cargadas: validez, asignación y guardado
    # operan sobre este subconjunto.
    imp.muestras = imp.muestras[:n_sel]

    ctrl_txt = f"{imp.control.conc_ugL:.3f} µg/L" if imp.control.conc_ugL is not None else "—"
    st.caption(
        f"Control: {ctrl_txt} (%CV {imp.control.cv_pct:.2f}) · ORDEN: "
        f"{imp.orden or '—'} · {n_sel} muestra(s) cargada(s)."
    )
    for a in imp.avisos:
        st.warning(a)

    # Panel de validez de la corrida (control de calidad).
    _render_validez(imp)

    # Curva de calibración (se llena automáticamente con la placa subida).
    _render_curva(imp)

    # Mapa de la placa: distribución de los pocillos (estándares/control/muestras).
    _render_placa_mapa(imp, n_sel)

    # ── Mapeo de cada muestra de la placa a su campaña/estación ──────────────
    grupos = get_muestras_agrupadas_por_campana()
    camp_opts = {"— (elegir campaña)": None}
    for cid, info in grupos.items():
        camp_opts[info["label"]] = cid

    # Límites del método (se guardan en µg/L; para el informe se usan en mg/L).
    param = get_param_microcistina() or {}
    lcm = param.get("lcm")                       # µg/L
    lmd = param.get("lmd")                        # µg/L
    lcm_mg = (float(lcm) / 1000.0) if lcm is not None else None
    lmd_mg = (float(lmd) / 1000.0) if lmd is not None else None

    def _fmt_mg(x):
        return f"{x:.6f}".rstrip("0").rstrip(".") if x is not None else "—"

    st.markdown(f"##### Asignar las {len(imp.muestras)} muestras de la placa")
    if lcm_mg is not None:
        st.caption(
            f"Límites del método: L.D.M. = {_fmt_mg(lmd_mg)} mg/L · "
            f"L.C.M. = {_fmt_mg(lcm_mg)} mg/L. Valor final del informe: "
            f"resultados por debajo del L.C.M. se reportan como "
            f"**< {_fmt_mg(lcm_mg)} mg/L** (se muestra entre paréntesis el valor calculado)."
        )
    # Estado de registro (check por muestra): resuelve la asignación vigente de
    # cada fila desde session_state y consulta en la BD, en UNA sola llamada,
    # cuáles muestras ya tienen resultado de microcistina. Tras registrar (y el
    # rerun), la consulta ve los nuevos resultados y el check aparece solo.
    def _asignacion_vigente(i: int) -> Optional[str]:
        camp_label = st.session_state.get(f"mc_camp_{i}")
        cid_ = camp_opts.get(camp_label) if camp_label else None
        if not cid_ or cid_ not in grupos:
            return None
        mues_label = st.session_state.get(f"mc_mues_{i}")
        return {mm["label"]: mm["id"]
                for mm in grupos[cid_]["muestras"]}.get(mues_label)

    ids_vigentes = [_asignacion_vigente(i) for i in range(len(imp.muestras))]
    estado_reg = estado_registro_microcistina([m for m in ids_vigentes if m])
    n_reg = sum(1 for mid in ids_vigentes if estado_reg.get(mid))
    if n_reg:
        st.markdown(
            "<div style='display:flex;align-items:center;gap:6px;margin:2px 0 4px;"
            f"font-size:0.78rem;color:{COLORS['text_light']}'>"
            + icon("check", size=15, color=COLORS["success"])
            + f"<span>{n_reg} de {len(imp.muestras)} muestra(s) de la placa ya "
            "están registradas en la base de datos.</span></div>",
            unsafe_allow_html=True,
        )

    def _check_html(estado: Optional[str]) -> str:
        # Iconografía SVG (Lucide) de la plataforma, no emojis.
        if estado == "validado":
            return (
                "<div style='display:flex;align-items:center;justify-content:center;"
                "gap:4px' title='Registrada y validada (firmada)'>"
                + icon("check", size=18, color=COLORS["success"])
                + icon("lock", size=13, color=COLORS["text_light"])
                + "</div>"
            )
        if estado == "registrado":
            return (
                "<div style='display:flex;justify-content:center' "
                "title='Registrada'>"
                + icon("check", size=18, color=COLORS["success"])
                + "</div>"
            )
        return (
            f"<div style='text-align:center;color:{COLORS['text_muted']}' "
            "title='Sin registrar'>–</div>"
        )

    h1, h2, h3, h4 = st.columns([1.6, 1.25, 1.55, 0.5])
    h1.caption("Muestra de la placa (valor final)")
    h2.caption("Campaña")
    h3.caption("Estación / muestra")
    h4.caption("Registro")

    eca_ug = 1.0   # DS 004-2017 Cat A2 / OMS: Microcistina LR = 1 µg/L
    lcm_ug = float(lcm) if lcm is not None else None

    asignaciones: dict[int, str] = {}
    for idx, m in enumerate(imp.muestras):
        extra = ""
        if m.conc_ugL is None:
            # Muy concentrada (> estándar más alto, 5 µg/L) → excede el ECA.
            valor = "⚠ muy concentrada — diluir y reanalizar (> 0.005 mg/L)"
            valor_ug = "> 5 µg/L"
            chip = chip_eca_html("excede", motivo="Por encima del rango; supera el ECA (1 µg/L)")
        elif lcm_ug is not None and m.conc_ugL < lcm_ug:
            valor = f"< {lcm_mg:.5f} mg/L"
            valor_ug = f"< {lcm_ug:g} µg/L"
            extra = f" · calc {m.conc_ugL / 1000:.6f} mg/L"
            chip = chip_eca_html("cumple")
        else:
            ug = m.conc_ugL
            valor = f"{ug / 1000:.6f} mg/L"
            valor_ug = f"{ug:.4f}".rstrip("0").rstrip(".") + " µg/L"
            if ug > eca_ug:
                pct = (ug / eca_ug - 1.0) * 100.0
                chip = chip_eca_html("excede", label=f"Excede +{pct:.0f}%")
            else:
                chip = chip_eca_html("cumple")
        c1, c2, c3, c4 = st.columns([1.6, 1.25, 1.55, 0.5])
        c1.markdown(
            f"**{m.label}** — {valor} ({valor_ug})<br>"
            f"<small>OD {m.od_1:g}/{m.od_2:g} · %CV {m.cv_pct:.1f}{extra}</small><br>"
            f"<small>ECA A2 / OMS 1 µg/L:</small> {chip}",
            unsafe_allow_html=True,
        )
        camp_sel = c2.selectbox("Campaña", list(camp_opts.keys()),
                                key=f"mc_camp_{idx}", label_visibility="collapsed")
        cid = camp_opts[camp_sel]
        if cid:
            mopts = {"— (estación)": None}
            for mm in grupos[cid]["muestras"]:
                mopts[mm["label"]] = mm["id"]
            mues_sel = c3.selectbox("Estación", list(mopts.keys()),
                                    key=f"mc_mues_{idx}", label_visibility="collapsed")
            asignaciones[idx] = mopts[mues_sel]
        else:
            c3.selectbox("Estación", ["— (elige campaña primero)"],
                         key=f"mc_mues_{idx}", disabled=True, label_visibility="collapsed")
            asignaciones[idx] = None

        # Check de verificación: ✅ si la muestra asignada ya tiene resultado
        # de microcistina registrado (🔒 además si está validada/firmada).
        mid_asig = asignaciones[idx]
        c4.markdown(_check_html(estado_reg.get(mid_asig) if mid_asig else None),
                    unsafe_allow_html=True)

    elegidas = [v for v in asignaciones.values() if v]
    n_asig = len(elegidas)
    dup = n_asig != len(set(elegidas))
    if dup:
        st.error("Hay muestras de la placa asignadas a la misma muestra de la plataforma.")

    # ── Datos de la corrida y registro ───────────────────────────────────────
    st.divider()
    d1, d2 = st.columns(2)
    lote = d1.text_input("Lote del kit", value=imp.kit_lote or "", key="mc_lote")
    fecha_imp = d2.date_input("Fecha de ensayo", value=None,
                              key="mc_imp_fecha", format="DD/MM/YYYY")

    with st.expander("Opciones avanzadas (criterios del control QCS)"):
        a1, a2, a3 = st.columns(3)
        qcs_nominal = a1.number_input("QCS nominal (µg/L)", value=0.750,
                                      min_value=0.0, step=0.001, format="%.3f", key="mc_qcs_nom")
        qcs_tol = a2.number_input("Tolerancia ± (µg/L)", value=0.185,
                                  min_value=0.0, step=0.001, format="%.3f", key="mc_qcs_tol")
        cv_max = a3.number_input("%CV máximo", value=15.0,
                                 min_value=0.0, step=1.0, format="%.0f", key="mc_qcs_cv")

    validar = st.checkbox(
        "Validar (firmar) los resultados al registrar", value=False, key="mc_val_chk",
        help="Marca los resultados como validados y fija la fecha de emisión del reporte.",
    )

    if st.button(f"Registrar {n_asig} muestra(s)", type="primary",
                 key="mc_imp_reg", disabled=(n_asig == 0 or dup)):
        asign = {k: v for k, v in asignaciones.items() if v}
        try:
            imp.kit_lote = lote.strip() or imp.kit_lote
            guardar_corrida_importada(
                imp, asign,
                fecha_ensayo=fecha_imp.isoformat() if fecha_imp else None,
                qcs_nominal=qcs_nominal, qcs_tolerancia=qcs_tol, cv_max=cv_max,
                analista_id=analista_id,
            )
            if validar:
                pid = (get_param_microcistina() or {}).get("id")
                if pid:
                    for mid in asign.values():
                        validar_resultados(mid, [pid], validador_id=analista_id)
            st.success(
                f"Registradas {n_asig} muestra(s)"
                + (" y validadas." if validar else ".")
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Error al registrar: {exc}")
