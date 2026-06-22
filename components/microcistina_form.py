"""
components/microcistina_form.py
Panel del ensayo ELISA de Microcistina LR (kit SAES/ABRAXIS, EPA 546), montado
en *Resultados de Laboratorio*.

Flujo único: se sube la placa de absorbancias (Excel del lector) o el libro del
Solver; la plataforma ajusta la curva 4PL, calcula el control y las
concentraciones de las 41 muestras, muestra la curva de calibración, y el
analista asigna cada muestra a su campaña/estación y registra. Una placa puede
abarcar varias campañas. No hay ingreso manual de absorbancias.

Función pública:
    render_panel_microcistina(analista_id)
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from components.ui_styles import chip_eca_html
from services.elisa_microcistina import STD_CONC_UGL
from services.microcistina_import import (
    parse_excel_solver,
    parse_grid_text,
    parse_placa_cruda,
    parse_placa_excel,
)
from services.microcistina_service import (
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
    _render_import(analista_id)


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
            "estándares (ST0–ST5), el control y las 41 muestras con la "
            "distribución fija del laboratorio y calcula todo (curva 4PL + "
            "concentraciones), igual que el Solver del Excel."
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
                txt = st.text_area(
                    "Placa OD (8 filas × 12 columnas)", height=200, key="mc_grid",
                    placeholder=("A  0.959 1.002 0.919 0.866 ...\n"
                                 "B  0.861 0.806 0.85 0.92 ...\n... hasta la fila H"),
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


def _render_resultado(imp, analista_id: Optional[str]) -> None:
    """Resumen de la corrida + curva + mapeo de muestras + datos + registro."""
    c = imp.curva
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("A (Amax)", f"{c.A:.4f}")
    k2.metric("B", f"{c.B:.4f}")
    k3.metric("C (IC50)", f"{c.C:.4f}")
    k4.metric("D", f"{c.D:.4f}")
    k5.metric("R²", f"{c.r2:.5f}")
    ctrl_txt = f"{imp.control.conc_ugL:.3f} µg/L" if imp.control.conc_ugL is not None else "—"
    st.caption(
        f"Control: {ctrl_txt} (%CV {imp.control.cv_pct:.2f}) · ORDEN: "
        f"{imp.orden or '—'} · {len(imp.muestras)} muestra(s) en la placa."
    )
    for a in imp.avisos:
        st.warning(a)

    # Curva de calibración (se llena automáticamente con la placa subida).
    _render_curva(imp)

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
    h1, h2, h3 = st.columns([1.7, 1.3, 1.6])
    h1.caption("Muestra de la placa (valor final)")
    h2.caption("Campaña")
    h3.caption("Estación / muestra")

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
        c1, c2, c3 = st.columns([1.7, 1.3, 1.6])
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
