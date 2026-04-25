"""
components/fitoplancton_form.py
Subsección "Fitoplancton (Sedgewick-Rafter)" del tab Hidrobiológico
en pages/4_Resultados_Lab.py.

La UI sólo recolecta inputs e invoca el servicio puro
``calcular_densidad_sedgewick_rafter``. No hace cálculos ni queries directas.

Material Icons en todos los iconos (sin emojis — convención LVCA).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ui_styles import success_check_overlay, toast
from services.fitoplancton_service import (
    CYANOBACTERIA_FILO,
    ICONOS_FILO,
    OMS_FUENTE,
    TAXONOMIA_FITOPLANCTON,
    borrar_analisis_fitoplancton,
    calcular_y_agrupar_por_filo,
    evaluar_alerta_oms_cianobacterias,
    evaluar_alerta_oms_clorofila,
    get_analisis_fitoplancton,
    get_clorofila_de_muestra,
    get_historico_cianobacterias_por_muestra,
    guardar_analisis_fitoplancton,
    total_cel_ml_filo,
)


def _render_historico_cianobacterias(muestra_id: str) -> None:
    """
    Expander con la serie temporal de densidad de cianobacterias en el punto
    al que pertenece esta muestra. Una barra por análisis previo, coloreada
    según el nivel OMS 1999, con la fecha en el eje X.
    """
    serie = get_historico_cianobacterias_por_muestra(muestra_id)
    if not serie:
        return  # sin histórico que mostrar (primer análisis del punto)

    with st.expander(
        f"Histórico de cianobacterias en este punto ({len(serie)} análisis)",
        icon=":material/timeline:",
        expanded=False,
    ):
        df = pd.DataFrame([
            {
                "Fecha":         s["fecha_muestreo"],
                "Muestra":       s["codigo_muestra"],
                "cél/mL":        s["total_cyano_cel_ml"],
                "Nivel OMS":     s["nivel_oms"],
                "_color":        s["color_borde"],
            }
            for s in serie
        ])
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        df = df.sort_values("Fecha")

        # Gráfico de barras coloreadas por nivel.
        try:
            import altair as alt
            chart = (
                alt.Chart(df)
                .mark_bar(size=22)
                .encode(
                    x=alt.X("Fecha:T", title="Fecha de muestreo"),
                    y=alt.Y("cél/mL:Q", title="Cianobacterias (cél/mL)",
                            scale=alt.Scale(type="log", clamp=True)),
                    color=alt.Color(
                        "Nivel OMS:N",
                        scale=alt.Scale(
                            domain=["Alerta 2", "Alerta 1", "Vigilancia inicial", "Sin alerta"],
                            range=["#dc3545", "#ffc107", "#28a745", "#6c757d"],
                        ),
                        legend=alt.Legend(title="Nivel OMS 1999"),
                    ),
                    tooltip=["Fecha:T", "Muestra:N", "cél/mL:Q", "Nivel OMS:N"],
                )
                .properties(height=240)
            )
            st.altair_chart(chart, use_container_width=True)
        except Exception:
            # Fallback a tabla si Altair falla por cualquier razón.
            st.dataframe(df.drop(columns=["_color"]), use_container_width=True, hide_index=True)

        st.caption(
            "Eje Y en escala logarítmica para que niveles vigilancia inicial y "
            "alertas convivan en un mismo gráfico. Pasa el cursor sobre cada "
            "barra para ver código de muestra y valor exacto."
        )


def _coincide_alerta(nivel_cyano: dict | None, nivel_clf: dict | None) -> str:
    """
    Compara el nivel disparado por cianobacterias con el de clorofila-a.
    Retorna texto corto para mostrar al usuario:
      - "" si no hay clorofila para corroborar.
      - "coincide" si ambos disparan el mismo nivel.
      - "discrepancia: ..." si una dispara y la otra no, o difieren niveles.
    """
    if nivel_clf is None and nivel_cyano is None:
        return ""
    if nivel_clf is None:
        return "Sin clorofila-a registrada para corroborar."
    if nivel_cyano is None:
        return (
            f"Discrepancia: clorofila-a indica {nivel_clf['label']} pero "
            "el conteo celular está por debajo del umbral. Posible lisis "
            "celular o dominancia no cianobacteriana — revisar."
        )
    if nivel_clf["nivel"] == nivel_cyano["nivel"]:
        return f"Corroborado por clorofila-a ({nivel_clf['label']})."
    return (
        f"Discrepancia: conteo indica {nivel_cyano['label']}, "
        f"clorofila-a indica {nivel_clf['label']}."
    )


def _render_alerta_oms(total_cyano_cel_ml: float, muestra_id: str) -> None:
    """
    Banner OMS para cianobacterias (Tabla por cél/mL, WHO 1999) corroborado
    con clorofila-a (P124) cuando esté disponible en la misma muestra.
    """
    nivel = evaluar_alerta_oms_cianobacterias(total_cyano_cel_ml)
    clorofila = get_clorofila_de_muestra(muestra_id)
    nivel_clf = (
        evaluar_alerta_oms_clorofila(clorofila["valor"]) if clorofila else None
    )

    # Línea de clorofila-a (siempre que haya valor) para mostrar en cualquier rama.
    if clorofila is not None:
        clf_label = nivel_clf["label"] if nivel_clf else "sin alerta"
        clf_line = (
            f"<b>Clorofila-a:</b> {clorofila['valor']:.2f} {clorofila['unidad']} "
            f"&nbsp;·&nbsp; {clf_label} (umbrales OMS 1999: ≥1 / ≥10 / ≥50 µg/L)"
        )
    else:
        clf_line = (
            "<b>Clorofila-a:</b> no registrada para esta muestra "
            "(parámetro P124 sin resultado en laboratorio)."
        )

    if nivel is None:
        # Sin alerta por cianobacterias — pero si la clorofila dispara algo,
        # se muestra como discrepancia (banner amarillo informativo).
        if nivel_clf is not None:
            st.markdown(
                f"""
                <div style="background:#fff3cd;color:#856404;
                    border-left:6px solid #ffc107;padding:12px 16px;
                    border-radius:6px;margin:8px 0;font-size:0.92em;line-height:1.45">
                    <div style="font-weight:700;margin-bottom:4px">
                        <span class="material-symbols-rounded" style="vertical-align:-5px;font-size:1.3em">warning</span>
                        Discrepancia: clorofila-a {nivel_clf['label']} sin
                        cianobacterias detectadas
                    </div>
                    <div style="opacity:0.92;margin-bottom:6px">
                        Conteo celular: {total_cyano_cel_ml:,.0f} cél/mL — por
                        debajo del umbral OMS 1999 de vigilancia inicial.
                        Posible lisis celular previa, dominancia no
                        cianobacteriana, o resultado incongruente.
                    </div>
                    <div style="opacity:0.85;font-size:0.9em">{clf_line}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.caption(
                f":material/check_circle: Cianobacterias: "
                f"{total_cyano_cel_ml:,.0f} cél/mL — por debajo del umbral OMS "
                f"1999 de vigilancia inicial (200 cél/mL). {clf_line.replace('<b>','').replace('</b>','')}"
            )
        return

    rango = (
        f"≥ {nivel['umbral_min_cel_ml']:,.0f} cél/mL"
        if nivel["umbral_max_cel_ml"] is None
        else f"{nivel['umbral_min_cel_ml']:,.0f} – {nivel['umbral_max_cel_ml']:,.0f} cél/mL"
    )
    confirm = _coincide_alerta(nivel, nivel_clf)
    st.markdown(
        f"""
        <div style="
            background:{nivel['color_bg']};
            color:{nivel['color_fg']};
            border-left:6px solid {nivel['color_borde']};
            padding:12px 16px;
            border-radius:6px;
            margin:8px 0;
            font-size:0.92em;
            line-height:1.45;
        ">
            <div style="font-weight:700;font-size:1.05em;margin-bottom:4px">
                <span class="material-symbols-rounded" style="vertical-align:-5px;font-size:1.3em">
                    {nivel['icono']}
                </span>
                Cianobacterias — {nivel['label']} · {total_cyano_cel_ml:,.0f} cél/mL
            </div>
            <div style="opacity:0.92;margin-bottom:6px">
                <b>Umbral:</b> {rango} &nbsp;·&nbsp; {nivel['descripcion']}
            </div>
            <div style="opacity:0.85;font-size:0.9em;margin-bottom:4px">
                {clf_line}
            </div>
            <div style="opacity:0.85;font-size:0.85em;font-style:italic;margin-bottom:4px">
                {confirm}
            </div>
            <div style="opacity:0.65;font-size:0.8em">
                Fuente: {OMS_FUENTE}.
                La OMS 2021 (2da ed.) introduce una tabla complementaria por
                biovolumen (mm³/L) que requiere volumen celular específico — no
                aplicable con los datos del recuento Sedgewick-Rafter.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _key(muestra_id: str, filo: str, especie: str) -> str:
    """Key estable y única para los st.number_input de conteo."""
    safe_filo = filo.replace(" ", "_")
    safe_esp = especie.replace(" ", "_").replace(".", "")
    return f"fito_{muestra_id[:8]}_{safe_filo}_{safe_esp}"


def _meta_key(muestra_id: str, campo: str) -> str:
    return f"fito_meta_{muestra_id[:8]}_{campo}"


def _cargar_valores_iniciales(muestra_id: str, doc: dict | None) -> None:
    """
    Hidrata session_state con los valores ya guardados (si existen) la primera
    vez que se renderiza el formulario para esta muestra. Streamlit conserva
    las ediciones posteriores del usuario sin sobreescribirlas.
    """
    flag = f"fito_loaded_{muestra_id}"
    if st.session_state.get(flag):
        return
    st.session_state[flag] = True

    meta = (doc or {}).get("metadatos") or {}
    st.session_state.setdefault(_meta_key(muestra_id, "vol_muestra_ml"),
                                float(meta.get("vol_muestra_ml") or 0.0))
    st.session_state.setdefault(_meta_key(muestra_id, "vol_concentrado_ml"),
                                float(meta.get("vol_concentrado_ml") or 0.0))
    st.session_state.setdefault(_meta_key(muestra_id, "area_campo_mm2"),
                                float(meta.get("area_campo_mm2") or 1000.0))
    st.session_state.setdefault(_meta_key(muestra_id, "num_campos"),
                                int(meta.get("num_campos") or 1))

    resultados = (doc or {}).get("resultados") or {}
    for filo, especies in TAXONOMIA_FITOPLANCTON.items():
        guardadas = resultados.get(filo) or {}
        for especie in especies:
            valor = (guardadas.get(especie) or {}).get("conteo_bruto", 0)
            st.session_state.setdefault(_key(muestra_id, filo, especie), int(valor or 0))


# ─────────────────────────────────────────────────────────────────────────────
# Render principal
# ─────────────────────────────────────────────────────────────────────────────

def render_subseccion_fitoplancton(muestra_id: str, analista_id: str | None) -> None:
    """
    Renderiza la subsección Fitoplancton dentro del tab Hidrobiológico.

    Flujo:
      1. Formulario de metadatos (volúmenes, área, campos).
      2. Tabs por filo con conteo bruto por especie.
      3. Botón Calcular → invoca servicio puro y muestra densidades.
      4. Botón Guardar → persiste JSONB en muestras.datos_fitoplancton.
    """
    doc_existente = get_analisis_fitoplancton(muestra_id)
    _cargar_valores_iniciales(muestra_id, doc_existente)

    st.markdown(
        "**Fitoplancton — método Sedgewick-Rafter.** "
        "Ingresa metadatos del recuento y conteo bruto por especie. "
        "El sistema calcula densidad en cel/mL y cel/L."
    )

    if doc_existente:
        st.caption(
            f":material/check_circle: Análisis previo guardado el "
            f"{(doc_existente.get('metadatos') or {}).get('fecha_analisis', '—')}."
        )
        # Banner OMS sobre el análisis ya guardado (si tiene cianobacterias).
        resultados_guardados = (doc_existente.get("resultados") or {})
        if CYANOBACTERIA_FILO in resultados_guardados:
            total_cyano_prev = total_cel_ml_filo(resultados_guardados, CYANOBACTERIA_FILO)
            if total_cyano_prev > 0:
                _render_alerta_oms(total_cyano_prev, muestra_id)

    # Histórico del punto (independiente de tener análisis cargado en esta muestra).
    _render_historico_cianobacterias(muestra_id)

    # ── 1. Metadatos del recuento ────────────────────────────────────────────
    st.markdown("###### Metadatos del recuento")
    c1, c2, c3, c4 = st.columns(4)
    vol_muestra = c1.number_input(
        "Volumen muestra (mL)",
        min_value=0.0,
        step=1.0,
        format="%.2f",
        key=_meta_key(muestra_id, "vol_muestra_ml"),
        help="Volumen inicial de agua recolectada.",
    )
    vol_concentrado = c2.number_input(
        "Volumen concentrado (mL)",
        min_value=0.0,
        step=0.1,
        format="%.2f",
        key=_meta_key(muestra_id, "vol_concentrado_ml"),
        help="Volumen al que se redujo la muestra.",
    )
    area_campo = c3.number_input(
        "Área del campo (mm²)",
        min_value=0.0,
        step=10.0,
        format="%.2f",
        key=_meta_key(muestra_id, "area_campo_mm2"),
        help="Área de la cuadrícula. Usa 1000 si se leyó toda la cámara.",
    )
    num_campos = c4.number_input(
        "Número de campos leídos",
        min_value=0,
        step=1,
        key=_meta_key(muestra_id, "num_campos"),
        help="Cantidad de campos revisados. Usa 1 si se leyó toda la cámara.",
    )

    # Validación temprana Vc <= Vs (avisa antes de pulsar Calcular).
    if vol_concentrado > 0 and vol_muestra > 0 and vol_concentrado > vol_muestra:
        st.error(
            f"El volumen concentrado ({vol_concentrado:g} mL) no puede ser mayor "
            f"que el volumen original de muestra ({vol_muestra:g} mL). "
            "Si la muestra no se concentró, usa el mismo valor en ambos.",
            icon=":material/error:",
        )

    st.divider()

    # ── 2. Conteos por filo (tabs) ───────────────────────────────────────────
    st.markdown("###### Conteo bruto por filo")

    filos = list(TAXONOMIA_FITOPLANCTON.keys())
    tabs = st.tabs([f":material/{ICONOS_FILO.get(f,'biotech')}: {f}" for f in filos])

    conteos_por_filo: dict[str, dict[str, int]] = {}
    for tab_widget, filo in zip(tabs, filos):
        with tab_widget:
            especies = TAXONOMIA_FITOPLANCTON[filo]
            st.caption(f"{len(especies)} especies — registra 0 si no hay hallazgos.")

            conteos_filo: dict[str, int] = {}
            # 3 columnas para densidad de inputs sin scroll excesivo
            cols = st.columns(3)
            for i, especie in enumerate(especies):
                with cols[i % 3]:
                    valor = st.number_input(
                        especie,
                        min_value=0,
                        step=1,
                        key=_key(muestra_id, filo, especie),
                    )
                    conteos_filo[especie] = int(valor or 0)
            conteos_por_filo[filo] = conteos_filo

    st.divider()

    # ── 3. Cálculo + Guardado ────────────────────────────────────────────────
    bcols = st.columns([1.4, 1.4, 1.0, 2.2])
    calcular = bcols[0].button(
        "Calcular densidad",
        icon=":material/calculate:",
        use_container_width=True,
        key=f"fito_btn_calc_{muestra_id}",
    )
    guardar = bcols[1].button(
        "Guardar análisis",
        icon=":material/save:",
        type="primary",
        use_container_width=True,
        key=f"fito_btn_save_{muestra_id}",
    )
    limpiar = bcols[2].button(
        "Vaciar",
        icon=":material/delete:",
        use_container_width=True,
        key=f"fito_btn_clear_{muestra_id}",
        disabled=doc_existente is None,
        help="Elimina el análisis guardado para esta muestra.",
    )

    # ── Cálculo (vista previa, en memoria — no persiste) ─────────────────────
    if calcular or guardar:
        try:
            resultados = calcular_y_agrupar_por_filo(
                conteos_por_filo=conteos_por_filo,
                vol_muestra_ml=float(vol_muestra),
                vol_concentrado_ml=float(vol_concentrado),
                area_campo_mm2=float(area_campo),
                num_campos=int(num_campos),
            )
        except ValueError as exc:
            st.error(str(exc), icon=":material/error:")
            return

        if not resultados:
            st.warning(
                "No hay especies con conteo mayor a cero. Ingresa al menos un hallazgo.",
                icon=":material/info:",
            )
            return

        # Tabla plana de resultados (filo, especie, conteo, cel/mL, cel/L)
        filas: list[dict] = []
        total_cel_ml = 0.0
        for filo, especies in resultados.items():
            for especie, val in especies.items():
                filas.append({
                    "Filo": filo,
                    "Especie": especie,
                    "Conteo bruto": val["conteo_bruto"],
                    "cel/mL": val["cel_ml"],
                    "cel/L": val["cel_l"],
                })
                total_cel_ml += float(val["cel_ml"])

        df = pd.DataFrame(filas)

        m1, m2, m3 = st.columns(3)
        m1.metric("Especies registradas", len(df))
        m2.metric("Densidad total (cel/mL)", f"{total_cel_ml:,.2f}")
        m3.metric("Densidad total (cel/L)", f"{total_cel_ml * 1000:,.0f}")

        # Alerta OMS para cianobacterias (sobre el cálculo recién realizado).
        if CYANOBACTERIA_FILO in resultados:
            total_cyano = total_cel_ml_filo(resultados, CYANOBACTERIA_FILO)
            if total_cyano > 0:
                _render_alerta_oms(total_cyano, muestra_id)

        st.dataframe(df, use_container_width=True, hide_index=True)

        # ── Guardado en BD (sólo si pulsaron Guardar) ────────────────────────
        if guardar:
            try:
                guardar_analisis_fitoplancton(
                    muestra_id=muestra_id,
                    vol_muestra_ml=float(vol_muestra),
                    vol_concentrado_ml=float(vol_concentrado),
                    area_campo_mm2=float(area_campo),
                    num_campos=int(num_campos),
                    resultados_por_filo=resultados,
                    analista_id=analista_id,
                )
                success_check_overlay("Análisis de fitoplancton guardado")
                st.rerun()
            except Exception as exc:
                st.error(f"Error al guardar: {exc}", icon=":material/error:")

    # ── Limpieza ─────────────────────────────────────────────────────────────
    if limpiar:
        try:
            borrar_analisis_fitoplancton(muestra_id, usuario_id=analista_id)
            # Limpiar la marca de carga para que se rehidrate vacío
            st.session_state.pop(f"fito_loaded_{muestra_id}", None)
            toast("Análisis de fitoplancton eliminado", tipo="warn")
            st.rerun()
        except Exception as exc:
            st.error(f"Error al eliminar: {exc}", icon=":material/error:")
