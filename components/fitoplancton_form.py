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
    ABREV_UNIDAD,
    CYANOBACTERIA_FILO,
    ICONOS_FILO,
    OMS_FUENTE,
    OMS_FUENTE_2021,
    TAXONOMIA_FITOPLANCTON,
    borrar_analisis_fitoplancton,
    calcular_y_agrupar_por_filo,
    evaluar_alerta_oms_2021,
    evaluar_alerta_oms_cianobacterias,
    evaluar_alerta_oms_clorofila,
    get_analisis_fitoplancton,
    get_clorofila_de_muestra,
    get_historico_cianobacterias_por_muestra,
    guardar_analisis_fitoplancton,
    total_biovolumen_filo,
    total_cel_ml_filo,
    total_unidades_ml_filo,
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


def _render_banner_nivel(
    titulo:        str,
    subtitulo:     str,
    nivel:         dict | None,
    metricas_html: str,
    fuente:        str,
) -> None:
    """
    Renderiza un banner OMS individual (1999 o 2021). Si nivel es None usa
    estilo neutral (gris) indicando que no hay alerta.
    """
    bg = nivel["color_bg"] if nivel else "#e2e3e5"
    fg = nivel["color_fg"] if nivel else "#383d41"
    borde = nivel["color_borde"] if nivel else "#6c757d"
    icono = nivel["icono"] if nivel else "check_circle"
    label = nivel["label"] if nivel else "Sin alerta"
    descripcion = nivel.get("descripcion", "") if nivel else (
        "Densidad/biomasa por debajo del umbral de vigilancia inicial."
    )
    criterio = nivel.get("criterio", "") if nivel else ""

    st.markdown(
        f"""
        <div style="
            background:{bg};color:{fg};
            border-left:6px solid {borde};
            padding:12px 16px;border-radius:6px;
            margin:8px 0;font-size:0.92em;line-height:1.45;height:100%;
        ">
            <div style="font-weight:700;font-size:1em;margin-bottom:2px">
                <span class="material-symbols-rounded" style="vertical-align:-5px;font-size:1.2em">{icono}</span>
                {titulo} — {label}
            </div>
            <div style="opacity:0.75;font-size:0.82em;margin-bottom:6px">{subtitulo}</div>
            <div style="opacity:0.92;margin-bottom:6px">{metricas_html}</div>
            {f'<div style="opacity:0.85;font-size:0.85em;margin-bottom:4px"><b>Criterio:</b> {criterio}</div>' if criterio else ''}
            <div style="opacity:0.82;font-size:0.85em;margin-bottom:4px">{descripcion}</div>
            <div style="opacity:0.65;font-size:0.78em;margin-top:6px">{fuente}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_alertas_oms_dual(resultados: dict, muestra_id: str) -> None:
    """
    Banner doble: OMS 1999 (cél/mL) y OMS 2021 (biovolumen mm³/L) lado a
    lado, sin combinar. Cruza con clorofila-a P124 cuando esté disponible.
    """
    total_cel = total_cel_ml_filo(resultados, CYANOBACTERIA_FILO)
    biovol = total_biovolumen_filo(resultados, CYANOBACTERIA_FILO)
    col_ml = total_unidades_ml_filo(resultados, CYANOBACTERIA_FILO, "colonia")
    fil_ml = total_unidades_ml_filo(resultados, CYANOBACTERIA_FILO, "filamento")

    n1999 = evaluar_alerta_oms_cianobacterias(total_cel)
    n2021 = evaluar_alerta_oms_2021(biovol, col_ml, fil_ml)

    # Métricas por banner.
    metr_1999 = (
        f"<b>Cianobacterias:</b> {total_cel:,.0f} cél/mL (equivalente)"
    )
    metr_2021 = (
        f"<b>Biovolumen:</b> {biovol:.4f} mm³/L &nbsp;·&nbsp; "
        f"{col_ml:,.1f} col/mL · {fil_ml:,.1f} fil/mL"
    )

    cols_oms = st.columns(2)
    with cols_oms[0]:
        _render_banner_nivel(
            titulo="OMS 1999",
            subtitulo="Por densidad celular (agua potable)",
            nivel=n1999,
            metricas_html=metr_1999,
            fuente=OMS_FUENTE,
        )
    with cols_oms[1]:
        _render_banner_nivel(
            titulo="OMS 2021",
            subtitulo="Por biovolumen (agua recreativa)",
            nivel=n2021,
            metricas_html=metr_2021,
            fuente=OMS_FUENTE_2021,
        )

    # Cruce con clorofila-a (informativo, debajo de los banners).
    clorofila = get_clorofila_de_muestra(muestra_id)
    if clorofila is not None:
        nivel_clf = evaluar_alerta_oms_clorofila(clorofila["valor"])
        clf_label = nivel_clf["label"] if nivel_clf else "sin alerta"
        st.caption(
            f":material/science: Corroboración con clorofila-a (P124): "
            f"{clorofila['valor']:.2f} {clorofila['unidad']} "
            f"→ {clf_label} (umbrales OMS 1999: ≥1 / ≥10 / ≥50 µg/L)."
        )
    else:
        st.caption(
            ":material/info: Clorofila-a (P124) no registrada — sin "
            "corroboración independiente disponible para esta muestra."
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
        for esp in especies:
            nombre = esp["nombre"]
            valor = (guardadas.get(nombre) or {}).get("conteo_bruto", 0)
            st.session_state.setdefault(_key(muestra_id, filo, nombre), int(valor or 0))


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
        # Banner OMS dual (1999 + 2021) sobre el análisis ya guardado.
        resultados_guardados = (doc_existente.get("resultados") or {})
        if CYANOBACTERIA_FILO in resultados_guardados:
            total_cyano_prev = total_cel_ml_filo(resultados_guardados, CYANOBACTERIA_FILO)
            biovol_prev = total_biovolumen_filo(resultados_guardados, CYANOBACTERIA_FILO)
            if total_cyano_prev > 0 or biovol_prev > 0:
                _render_alertas_oms_dual(resultados_guardados, muestra_id)

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
            unidades_distintas = sorted({e["unidad"] for e in especies})
            st.caption(
                f"{len(especies)} especies — registra 0 si no hay hallazgos. "
                f"Unidades de conteo en este filo: "
                f"{', '.join(ABREV_UNIDAD[u] for u in unidades_distintas)}."
            )

            conteos_filo: dict[str, int] = {}
            cols = st.columns(3)
            for i, esp in enumerate(especies):
                nombre = esp["nombre"]
                abrev = ABREV_UNIDAD.get(esp["unidad"], esp["unidad"])
                with cols[i % 3]:
                    valor = st.number_input(
                        f"{nombre} ({abrev})",
                        min_value=0,
                        step=1,
                        key=_key(muestra_id, filo, nombre),
                        help=(
                            f"Unidad de conteo: {esp['unidad']}. "
                            f"Aprox. {esp['celulas_por_unidad']} célula(s) por unidad. "
                            f"Volumen celular referencial: {esp['volumen_celula_um3']:g} µm³."
                        ),
                    )
                    conteos_filo[nombre] = int(valor or 0)
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

        # Tabla plana de resultados con todas las métricas: unidad/mL, cel/mL
        # equivalente y biovolumen. La unidad se etiqueta por especie.
        filas: list[dict] = []
        total_unidades_ml = 0.0
        total_cel_ml_eq = 0.0
        total_biovol_mm3l = 0.0
        for filo, especies in resultados.items():
            for nombre_esp, val in especies.items():
                unidad = val.get("unidad", "celula")
                abrev = ABREV_UNIDAD.get(unidad, unidad)
                filas.append({
                    "Filo": filo,
                    "Especie": nombre_esp,
                    "Unidad": abrev,
                    "Conteo bruto": val["conteo_bruto"],
                    f"{abrev}/mL": val["unidad_ml"],
                    "cél/mL (equiv.)": val.get("cel_ml_equiv", val["unidad_ml"]),
                    "Biovol (mm³/L)": val.get("biovolumen_mm3_l", 0.0),
                })
                total_unidades_ml += float(val["unidad_ml"])
                total_cel_ml_eq += float(val.get("cel_ml_equiv", val["unidad_ml"]))
                total_biovol_mm3l += float(val.get("biovolumen_mm3_l", 0.0))

        df = pd.DataFrame(filas)

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Especies registradas", len(df))
        m2.metric("Total unidades/mL", f"{total_unidades_ml:,.2f}")
        m3.metric("Total cél/mL (equiv.)", f"{total_cel_ml_eq:,.2f}")
        m4.metric("Biovolumen (mm³/L)", f"{total_biovol_mm3l:,.4f}")

        # Alertas OMS para cianobacterias (sobre el cálculo recién realizado).
        # Se muestran ambas tablas (1999 y 2021) por separado, sin combinar.
        if CYANOBACTERIA_FILO in resultados:
            _render_alertas_oms_dual(resultados, muestra_id)

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
