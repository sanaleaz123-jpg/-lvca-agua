"""
components/microcistina_form.py
Panel reutilizable del ensayo ELISA de Microcistina LR (kit SAES/ABRAXIS,
EPA 546). Se monta como subsección dentro de *Resultados de Laboratorio*.

El ensayo es a nivel de campaña (una placa cubre todas las muestras): el
analista ingresa las absorbancias (OD) por duplicado de los 6 estándares, el
control (QCS) y cada muestra; la plataforma ajusta la curva 4PL, calcula
concentraciones y %CV, guarda los resultados y habilita el Reporte de Ensayo.

Función pública:
    render_panel_microcistina(analista_id)
"""

from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from services.elisa_microcistina import STD_CONC_UGL, FACTOR_DILUCION_DEFAULT
from services.microcistina_service import (
    calcular_corrida,
    get_corrida,
    get_muestras_microcistina,
    get_param_microcistina,
    guardar_corrida,
)
from services.resultado_service import get_campanas, validar_resultados


def render_panel_microcistina(analista_id: Optional[str] = None) -> None:
    """Subsección de ingreso del ensayo ELISA de microcistina (por campaña)."""
    campanas = get_campanas()
    if not campanas:
        st.info("No hay campañas registradas.")
        return

    opciones = {f"{c['codigo']} — {c['nombre']}": c["id"] for c in campanas}
    sel = st.selectbox("Campaña", list(opciones.keys()), key="mc_campana")
    campana_id = opciones[sel]
    cid = campana_id[:8]  # sufijo de keys por campaña

    muestras = get_muestras_microcistina(campana_id)
    if not muestras:
        st.warning(
            "La campaña no tiene muestras registradas. Crea las muestras en "
            "*Muestras de campo* antes de cargar el ensayo."
        )
        return

    corrida = get_corrida(campana_id) or {}
    std_prev = corrida.get("std_od") or [[0.0, 0.0]] * len(STD_CONC_UGL)
    param = get_param_microcistina() or {}

    # ── Curva de calibración ─────────────────────────────────────────────
    st.markdown("##### Curva de calibración (estándares)")
    st.caption("Absorbancia (OD) por duplicado de cada estándar.")
    std_od: list[tuple[float, float]] = []
    for i, conc in enumerate(STD_CONC_UGL):
        c0, c1, c2 = st.columns([1.4, 1, 1])
        etiqueta = "Std 0 (Amax · 0 µg/L)" if i == 0 else f"Std {i} ({conc} µg/L)"
        c0.markdown(f"**{etiqueta}**")
        pv = std_prev[i] if i < len(std_prev) else [0.0, 0.0]
        o1 = c1.number_input("OD 1", key=f"std_{cid}_{i}_1", value=float(pv[0] or 0.0),
                             min_value=0.0, step=0.001, format="%.4f")
        o2 = c2.number_input("OD 2", key=f"std_{cid}_{i}_2", value=float(pv[1] or 0.0),
                             min_value=0.0, step=0.001, format="%.4f")
        std_od.append((o1, o2))

    # ── Control y metadatos ──────────────────────────────────────────────
    st.markdown("##### Control de calidad y metadatos")
    m1, m2, m3 = st.columns(3)
    with m1:
        ctrl_1 = st.number_input("Control OD 1", key=f"ctrl_{cid}_1",
                                 value=float(corrida.get("control_od_1") or 0.0),
                                 min_value=0.0, step=0.001, format="%.4f")
        ctrl_2 = st.number_input("Control OD 2", key=f"ctrl_{cid}_2",
                                 value=float(corrida.get("control_od_2") or 0.0),
                                 min_value=0.0, step=0.001, format="%.4f")
    with m2:
        kit_lote = st.text_input("Lote del kit", key=f"lote_{cid}",
                                 value=corrida.get("kit_lote") or "")
        factor = st.number_input(
            "Factor de dilución (muestras)", key=f"factor_{cid}",
            value=float(corrida.get("factor_dilucion") or FACTOR_DILUCION_DEFAULT),
            min_value=0.0, step=0.01, format="%.2f",
        )
        fecha_ensayo = st.date_input("Fecha de ensayo", key=f"fens_{cid}",
                                     value=None, format="DD/MM/YYYY")
    with m3:
        qcs_nominal = st.number_input("QCS nominal (µg/L)", key=f"qn_{cid}",
                                      value=float(corrida.get("qcs_nominal") or 0.750),
                                      min_value=0.0, step=0.001, format="%.3f")
        qcs_tol = st.number_input("Tolerancia ± (µg/L)", key=f"qt_{cid}",
                                  value=float(corrida.get("qcs_tolerancia") or 0.185),
                                  min_value=0.0, step=0.001, format="%.3f")
        cv_max = st.number_input("%CV máximo", key=f"cvm_{cid}",
                                 value=float(corrida.get("cv_max") or 15.0),
                                 min_value=0.0, step=1.0, format="%.0f")

    # ── Muestras ─────────────────────────────────────────────────────────
    st.markdown("##### Muestras")
    st.caption("Absorbancia (OD) por duplicado de cada muestra.")
    muestras_od: dict[str, tuple[float, float]] = {}
    for m in muestras:
        p = m.get("punto") or {}
        etiq = f"{p.get('codigo') or m.get('codigo') or m['id'][:8]}"
        c0, c1, c2 = st.columns([1.6, 1, 1])
        c0.markdown(f"**{etiq}**")
        o1 = c1.number_input("OD 1", key=f"m_{cid}_{m['id']}_1",
                             value=float(m.get("od_1") or 0.0),
                             min_value=0.0, step=0.001, format="%.4f")
        o2 = c2.number_input("OD 2", key=f"m_{cid}_{m['id']}_2",
                             value=float(m.get("od_2") or 0.0),
                             min_value=0.0, step=0.001, format="%.4f")
        if o1 > 0 and o2 > 0:
            muestras_od[m["id"]] = (o1, o2)

    # ── Vista previa del cálculo ─────────────────────────────────────────
    st.divider()
    st.markdown("##### Vista previa del cálculo")
    curva_lista = all(a > 0 and b > 0 for a, b in std_od)
    if not curva_lista:
        st.info("Ingresa las absorbancias de los 6 estándares (OD 1 y OD 2) para ajustar la curva.")
        return

    try:
        calc = calcular_corrida(std_od, (ctrl_1, ctrl_2), muestras_od, factor=factor)
    except Exception as exc:
        st.error(f"No se pudo ajustar la curva: {exc}")
        return

    cur = calc.curva
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("A (Amax)", f"{cur.A:.4f}")
    k2.metric("B (pend.)", f"{cur.B:.4f}")
    k3.metric("C (IC50)", f"{cur.C:.4f}")
    k4.metric("D (mín.)", f"{cur.D:.4f}")
    k5.metric("R²", f"{cur.r2:.5f}")
    if not cur.es_valida():
        st.warning(
            "La curva no cumple alguno de los criterios guía (A>0.7, D<0.15, R²≥0.98). "
            "Revisa las absorbancias de los estándares."
        )

    # Control
    if ctrl_1 > 0 and ctrl_2 > 0:
        ctrl = calc.control
        low, high = qcs_nominal - qcs_tol, qcs_nominal + qcs_tol
        conc_ok = (ctrl.conc_ugL is not None and low <= ctrl.conc_ugL <= high)
        cv_ok = ctrl.cv_pct <= cv_max
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Control (µg/L)", f"{ctrl.conc_ugL:.3f}" if ctrl.conc_ugL is not None else "—")
        cc2.metric("%CV control", f"{ctrl.cv_pct:.2f}%")
        cc3.metric("Rango aceptación", f"{low:.3f} – {high:.3f}")
        if conc_ok and cv_ok:
            st.success("Control dentro de criterios de aceptación.")
        else:
            st.warning("El control NO cumple los criterios de aceptación (concentración o %CV).")

    # Tabla de muestras
    lcm = param.get("lcm")
    filas = []
    for m in muestras:
        if m["id"] not in calc.resultados:
            continue
        p = m.get("punto") or {}
        r = calc.resultados[m["id"]]
        if r.conc_ugL is None:
            mgL = "Fuera de rango"
        elif lcm is not None and r.conc_ugL < float(lcm):
            mgL = f"< {float(lcm) / 1000:.5f}"
        else:
            mgL = f"{r.conc_ugL / 1000:.6f}"
        filas.append({
            "Punto": p.get("codigo") or m.get("codigo"),
            "OD 1": round(r.od_1, 4),
            "OD 2": round(r.od_2, 4),
            "%CV": round(r.cv_pct, 2),
            "Conc. (mg/L)": mgL,
            "Obs.": ("⚠ %CV > criterio" if r.cv_pct > cv_max else "")
                    + ((" " + r.motivo) if r.motivo else ""),
        })
    if filas:
        st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)
    else:
        st.info("Ingresa las absorbancias de al menos una muestra (OD 1 y OD 2 > 0).")

    # ── Guardar / Validar ────────────────────────────────────────────────
    st.divider()
    g1, g2 = st.columns(2)
    with g1:
        if st.button("Guardar corrida y resultados", type="primary",
                     use_container_width=True, icon=":material/save:",
                     key=f"mc_guardar_{cid}", disabled=not muestras_od):
            try:
                guardar_corrida(
                    campana_id,
                    fecha_ensayo=fecha_ensayo.isoformat() if fecha_ensayo else None,
                    kit_lote=kit_lote or None,
                    factor=factor,
                    std_od=std_od,
                    control_od=(ctrl_1, ctrl_2),
                    muestras_od=muestras_od,
                    qcs_nominal=qcs_nominal,
                    qcs_tolerancia=qcs_tol,
                    cv_max=cv_max,
                    analista_id=analista_id,
                )
                st.success(f"Guardado: {len(muestras_od)} muestra(s) y la curva de calibración.")
                st.rerun()
            except Exception as exc:
                st.error(f"Error al guardar: {exc}")

    with g2:
        if st.button("Validar resultados (firma)", use_container_width=True,
                     icon=":material/verified_user:", key=f"mc_validar_{cid}",
                     help="Marca los resultados como validados; fija la fecha de emisión del reporte."):
            param_id = param.get("id")
            if not param_id:
                st.error("No se encontró el parámetro Microcistina (P091).")
            else:
                n = 0
                for mid in muestras_od:
                    n += validar_resultados(mid, [param_id], validador_id=analista_id)
                st.success(f"{n} resultado(s) validado(s).")
                st.rerun()
