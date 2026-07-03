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

from typing import Optional

import pandas as pd
import streamlit as st

from components.ui_styles import COLORS, chip_eca_html, icon
from services.elisa_microcistina import STD_CONC_UGL
from services.microcistina_import import (
    CAPACIDAD_MUESTRAS,
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


def _render_placa_mapa(imp, n_activas: int) -> None:
    """Mapa 8×12 de la placa: cada pocillo con su rol y color por OD/conc.

    Reconstruye la distribución fija (ST0–ST5 y control en col 1-2; muestras
    S1..SN serpenteando) para ver de un vistazo cómo quedaron los pocillos y
    cuáles quedaron vacíos. El color codifica la OD o la concentración; los
    pocillos sobrantes (S(N+1)..) se muestran como vacíos.
    """
    try:
        import plotly.graph_objects as go
    except Exception:
        return

    ROWS = ["A", "B", "C", "D", "E", "F", "G", "H"]
    COLS = [str(i) for i in range(1, 13)]
    NROW, NCOL = 8, 12
    mapa = mapa_placa()

    z_od = [[None] * NCOL for _ in range(NROW)]
    z_conc = [[None] * NCOL for _ in range(NROW)]
    labels = [["—"] * NCOL for _ in range(NROW)]
    hover = [["Pocillo vacío"] * NCOL for _ in range(NROW)]

    def _poner(r, c1, c2, label, od1, od2, conc, cv):
        media = (od1 + od2) / 2.0
        conc_txt = f"{conc:.4g} µg/L" if conc is not None else "—"
        cv_txt = f"{cv:.1f}%" if cv is not None else "—"
        htxt = (f"<b>{label}</b><br>OD {od1:g} / {od2:g} (prom {media:.3f})"
                f"<br>%CV {cv_txt}<br>Conc {conc_txt}")
        for c in (c1, c2):
            z_od[r][c] = media
            z_conc[r][c] = conc if conc is not None else None
            labels[r][c] = label
            hover[r][c] = htxt

    # Estándares ST0..ST5
    for i, (r, c1, c2) in enumerate(mapa["std"]):
        if i < len(imp.std_od):
            o1, o2 = imp.std_od[i]
            _poner(r, c1, c2, f"ST{i}", o1, o2, STD_CONC_UGL[i], None)
    # Control (CT)
    cr, cc1, cc2 = mapa["control"]
    o1, o2 = imp.control_od
    _poner(cr, cc1, cc2, "CT", o1, o2, imp.control.conc_ugL, imp.control.cv_pct)
    # Muestras cargadas S1..SN (las sobrantes quedan vacías)
    for n in sorted(mapa["samples"].keys()):
        if n > n_activas or n > len(imp.muestras):
            continue
        r, c1, c2 = mapa["samples"][n]
        m = imp.muestras[n - 1]
        _poner(r, c1, c2, f"S{n}", m.od_1, m.od_2, m.conc_ugL, m.cv_pct)

    st.markdown("##### Distribución de la placa")
    color_por = st.radio(
        "Colorear por", ["OD", "Concentración (µg/L)"],
        horizontal=True, key="mc_placa_color", label_visibility="collapsed",
    )
    usar_conc = color_por.startswith("Conc")
    z = z_conc if usar_conc else z_od
    escala = "OrRd" if usar_conc else "YlGnBu"
    barra = "µg/L" if usar_conc else "OD"

    fig = go.Figure(go.Heatmap(
        z=z, x=COLS, y=ROWS,
        hovertext=hover, hovertemplate="%{hovertext}<extra></extra>",
        hoverongaps=False,
        colorscale=escala, colorbar=dict(title=barra, thickness=12),
        xgap=3, ygap=3,
    ))
    # Etiqueta de cada pocillo como anotación (así los vacíos también se rotulan).
    for r in range(NROW):
        for c in range(NCOL):
            vacio = labels[r][c] == "—"
            fig.add_annotation(
                x=COLS[c], y=ROWS[r], text=labels[r][c], showarrow=False,
                font=dict(size=10, color=(COLORS["text_muted"] if vacio else "#0f172a")),
            )
    fig.update_layout(
        height=360, margin=dict(l=10, r=10, t=10, b=10),
        xaxis=dict(side="top", title="Columna", fixedrange=True),
        yaxis=dict(autorange="reversed", title="Fila", fixedrange=True),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Col 1-2: estándares (ST0–ST5) y control (CT). Muestras S1..S"
        f"{n_activas} serpenteando de H→A por pares de columnas. "
        "Los pocillos «—» (sin color) quedaron vacíos."
    )


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
    nc1, nc2 = st.columns([1, 2.4])
    n_sel = int(nc1.number_input(
        "Nº de muestras en la placa", min_value=1, max_value=max(1, cap),
        value=int(n_det), step=1, key="mc_n_muestras",
    ))
    nc2.caption(
        f"Se detectaron **{n_det}** muestra(s) cargada(s)"
        + (f" · {cap - n_det} pocillo(s) vacío(s) al final." if cap - n_det else ".")
        + " Ajusta si es necesario; los pocillos sobrantes se ignoran."
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
