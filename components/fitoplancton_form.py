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
    get_analisis_fitoplancton,
    guardar_analisis_fitoplancton,
    total_cel_ml_filo,
)


def _render_alerta_oms(total_cyano_cel_ml: float) -> None:
    """
    Banner OMS para cianobacterias según la Tabla por células/mL. Solo se
    muestra cuando total_cel_ml >= 200; bajo ese umbral no hay nivel definido.
    """
    nivel = evaluar_alerta_oms_cianobacterias(total_cyano_cel_ml)
    if nivel is None:
        st.caption(
            f":material/check_circle: Cianobacterias: "
            f"{total_cyano_cel_ml:,.0f} cél/mL — por debajo del umbral OMS 1999 "
            f"de vigilancia inicial (200 cél/mL)."
        )
        return

    rango = (
        f"≥ {nivel['umbral_min_cel_ml']:,.0f} cél/mL"
        if nivel["umbral_max_cel_ml"] is None
        else f"{nivel['umbral_min_cel_ml']:,.0f} – {nivel['umbral_max_cel_ml']:,.0f} cél/mL"
    )
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
            <div style="opacity:0.7;font-size:0.85em">
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
                _render_alerta_oms(total_cyano_prev)

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
                _render_alerta_oms(total_cyano)

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
            borrar_analisis_fitoplancton(muestra_id)
            # Limpiar la marca de carga para que se rehidrate vacío
            st.session_state.pop(f"fito_loaded_{muestra_id}", None)
            toast("Análisis de fitoplancton eliminado", tipo="warn")
            st.rerun()
        except Exception as exc:
            st.error(f"Error al eliminar: {exc}", icon=":material/error:")
