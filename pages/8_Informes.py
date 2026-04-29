"""
pages/8_Informes.py
Generación de informes y exportación de datos.

Secciones:
    Tab 1 — Informe por campaña: resumen, excedencias, descarga PDF/Excel
    Tab 2 — Informe por punto: historial temporal, descarga Excel

Acceso mínimo: visualizador.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import aplicar_estilos, page_header, section_header, top_nav
from services.informe_service import (
    get_resumen_campana,
    get_resumen_punto,
    generar_excel_campana,
    generar_excel_punto,
    generar_pdf_campana,
)
from services.reporte_hidrobiologico_service import (
    generar_docx_hidrobiologico_campana,
    tiene_analisis_hidrobiologico,
)
from services.resultado_service import get_campanas
from services.punto_service import get_puntos
from services.cumplimiento_service import EstadoECA


# Paleta de veredictos — alineada con 4_Resultados_Lab.py
_CHIP_ESTADOS: dict[str, dict] = {
    EstadoECA.CUMPLE:                {"bg": "#d4edda", "fg": "#155724", "label": "Cumple"},
    EstadoECA.EXCEDE:                {"bg": "#f8d7da", "fg": "#721c24", "label": "Excede"},
    EstadoECA.EXCEDE_EXCEPCION_ART6: {"bg": "#fff3cd", "fg": "#856404", "label": "Art. 6"},
    EstadoECA.NO_VERIFICABLE:        {"bg": "#e2e3e5", "fg": "#383d41", "label": "No verif."},
    EstadoECA.NO_APLICA:             {"bg": "#ede7f6", "fg": "#4527a0", "label": "No aplica"},
}


def _chip_estado_html(estado: str, motivo: str = "") -> str:
    info = _CHIP_ESTADOS.get(estado)
    if info is None:
        return estado or ""
    motivo = (motivo or "").replace('"', "'")
    return (
        f'<span title="{motivo}" style="background:{info["bg"]};color:{info["fg"]};'
        f'padding:1px 8px;border-radius:10px;font-size:0.82em;font-weight:500;'
        f'white-space:nowrap">{info["label"]}</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Informe por campaña
# ─────────────────────────────────────────────────────────────────────────────

def _render_informe_campana() -> None:
    section_header("Informe por campaña", "file")

    campanas = get_campanas()
    if not campanas:
        st.info("No hay campañas registradas.")
        return

    opciones = {
        f"{c['codigo']} — {c['nombre']} ({c['estado']})": c["id"]
        for c in campanas
    }
    col_sel, col_refresh = st.columns([4, 1])
    with col_sel:
        sel = st.selectbox("Seleccionar campaña", list(opciones.keys()), key="inf_campana")
        campana_id = opciones[sel]
    with col_refresh:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        refresh = st.button(
            "Actualizar", key="btn_refresh_informe",
            icon=":material/refresh:", use_container_width=True,
        )

    # Auto-cargar el informe si cambió la campaña o se presiona Actualizar
    cached_id = st.session_state.get("informe_campana_id")
    cached = st.session_state.get("informe_campana")
    if refresh or cached is None or cached_id != campana_id:
        with st.spinner("Cargando informe..."):
            try:
                resumen = get_resumen_campana(campana_id)
                st.session_state["informe_campana"] = resumen
                st.session_state["informe_campana_id"] = campana_id
            except Exception as exc:
                st.error(f"Error al cargar informe: {exc}")
                return
    else:
        resumen = cached

    campana = resumen["campana"]

    # ── Métricas (5 estados del motor de cumplimiento) ───────────────────
    st.markdown(f"### {campana['codigo']} — {campana['nombre']}")

    por_estado = resumen.get("por_estado", {})
    n_cumple   = por_estado.get(EstadoECA.CUMPLE, 0)
    n_excede   = por_estado.get(EstadoECA.EXCEDE, 0)
    n_art6     = por_estado.get(EstadoECA.EXCEDE_EXCEPCION_ART6, 0)
    n_noverif  = por_estado.get(EstadoECA.NO_VERIFICABLE, 0)
    n_noaplica = por_estado.get(EstadoECA.NO_APLICA, 0)

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Puntos", len(resumen["puntos"]))
    mc2.metric("Muestras", len(resumen["muestras"]))
    mc3.metric("Resultados", resumen["total_resultados"])

    me1, me2, me3, me4, me5 = st.columns(5)
    me1.metric("Cumple",     n_cumple)
    me2.metric("Excede",     n_excede,
               delta=(f"-{n_excede}" if n_excede > 0 else None),
               delta_color="inverse")
    me3.metric("Art. 6",     n_art6)
    me4.metric("No verif.",  n_noverif)
    me5.metric("No aplica",  n_noaplica)

    # ── Tabla de excedencias ─────────────────────────────────────────────
    if resumen["excedencias"]:
        section_header("Excedencias ECA detectadas", "alert")
        exc_rows = []
        for e in resumen["excedencias"]:
            exc_rows.append({
                "Punto":      e.get("punto_codigo", ""),
                "Parámetro":  e.get("parametro_nombre", ""),
                "Valor":      e.get("valor_comparado") if e.get("valor_comparado") is not None else e.get("valor"),
                "Unidad":     e.get("unidad_comparada") or e.get("unidad"),
                "ECA máx":    e.get("eca_rango_max"),
                "Estado":     _CHIP_ESTADOS.get(e["estado_eca"], {}).get("label", e["estado_eca"]),
                "Motivo":     e.get("motivo", ""),
                "Fecha":      e.get("fecha_muestreo") or e.get("fecha_analisis"),
            })
        st.dataframe(
            pd.DataFrame(exc_rows),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Motivo": st.column_config.TextColumn("Motivo", width="large"),
            },
        )
    elif n_excede == 0 and n_art6 == 0:
        st.success(
            "No se detectaron excedencias ECA en esta campaña.",
            icon=":material/check_circle:",
        )

    # ── Leyenda de estados ECA ───────────────────────────────────────────
    with st.expander("Leyenda de estados ECA", icon=":material/help:"):
        lc1, lc2, lc3 = st.columns(3)
        lc1.markdown(
            "**Cumple** — dentro del rango ECA aplicable, con conversión a "
            "la especie oficial del DS cuando corresponde."
        )
        lc1.markdown(
            "**Excede** — supera el umbral ECA. Se evaluó con el motor de "
            "cumplimiento (forma analítica, especie, Δ3 temperatura, Tabla N°1 NH₃)."
        )
        lc2.markdown(
            "**Art. 6** — excede, pero el punto tiene excepción aprobada por "
            "ANA (condición natural no antrópica)."
        )
        lc2.markdown(
            "**No verif.** — no se puede emitir juicio: LC>ECA, falta pH/T "
            "para NH₃ Cat 4, zona de mezcla (Art. 7), falta línea base de "
            "temperatura, o discrepancia total/disuelta."
        )
        lc3.markdown(
            "**No aplica** — parámetro sin ECA en el DS 004-2017-MINAM para "
            "la categoría del punto (ej. Fosfatos, N amoniacal total en Cat 4, "
            "P total en Cat 3)."
        )

    # ── Tabla de resultados completa ─────────────────────────────────────
    with st.expander(
        f"Ver todos los resultados ({resumen['total_resultados']})",
        icon=":material/list:", expanded=False,
    ):
        if resumen["resultados"]:
            df_res = pd.DataFrame(resumen["resultados"])
            df_vista = df_res[[
                "muestra_codigo", "punto_codigo",
                "parametro_nombre", "valor", "unidad", "estado_eca", "motivo",
            ]].rename(columns={
                "muestra_codigo":   "Muestra",
                "punto_codigo":     "Punto",
                "parametro_nombre": "Parámetro",
                "valor":            "Valor",
                "unidad":           "Unidad",
                "estado_eca":       "Estado",
                "motivo":           "Motivo",
            })
            df_vista["Estado"] = df_vista["Estado"].map(
                lambda e: _CHIP_ESTADOS.get(e, {}).get("label", e)
            )
            st.dataframe(
                df_vista,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Motivo": st.column_config.TextColumn("Motivo", width="large"),
                },
            )

    # ── Descargas ────────────────────────────────────────────────────────
    st.divider()
    section_header("Descargas", "download")

    hay_hidrobio = tiene_analisis_hidrobiologico(campana_id)
    cols_descarga = st.columns(3 if hay_hidrobio else 2)

    with cols_descarga[0]:
        try:
            excel_bytes = generar_excel_campana(campana_id)
            st.download_button(
                label="Descargar Excel",
                data=excel_bytes,
                file_name=f"informe_{campana['codigo']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                icon=":material/table_view:",
            )
        except Exception as exc:
            st.error(f"Error generando Excel: {exc}")

    with cols_descarga[1]:
        try:
            pdf_bytes = generar_pdf_campana(campana_id)
            st.download_button(
                label="Descargar PDF",
                data=pdf_bytes,
                file_name=f"informe_{campana['codigo']}.pdf",
                mime="application/pdf",
                use_container_width=True,
                icon=":material/picture_as_pdf:",
            )
        except Exception as exc:
            st.error(f"Error generando PDF: {exc}")

    if hay_hidrobio:
        with cols_descarga[2]:
            try:
                docx_bytes = generar_docx_hidrobiologico_campana(campana_id)
                st.download_button(
                    label="Descargar datos hidrobiológicos",
                    data=docx_bytes,
                    file_name=f"hidrobiologia_{campana['codigo']}.docx",
                    mime=(
                        "application/vnd.openxmlformats-officedocument."
                        "wordprocessingml.document"
                    ),
                    use_container_width=True,
                    icon=":material/biotech:",
                    help=(
                        "Tabla de abundancia de fitoplancton por punto, "
                        "con conteos por especie y resumen TOTAL / N° Cel/mL / "
                        "N° Cel/L por phylum."
                    ),
                )
            except Exception as exc:
                st.error(f"Error generando reporte hidrobiológico: {exc}")
    else:
        st.caption(
            ":material/info: La descarga *Datos hidrobiológicos* se habilita "
            "cuando al menos una muestra de la campaña tenga el análisis de "
            "fitoplancton (Sedgewick-Rafter) cargado en *Resultados de "
            "laboratorio → Hidrobiológico*."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Informe por punto
# ─────────────────────────────────────────────────────────────────────────────

def _render_informe_punto() -> None:
    section_header("Informe por punto de muestreo", "map_pin")

    puntos = get_puntos(solo_activos=True)
    if not puntos:
        st.info("No hay puntos de muestreo registrados.")
        return

    opciones = {
        f"{p['codigo']} — {p['nombre']} ({p.get('cuenca', '')})": p["id"]
        for p in puntos
    }

    sel = st.selectbox("Seleccionar punto", list(opciones.keys()), key="inf_punto")
    punto_id = opciones[sel]

    pc1, pc2 = st.columns(2)
    with pc1:
        fecha_desde = st.date_input(
            "Desde",
            value=date.today() - timedelta(days=365),
            key="inf_pt_desde",
        )
    with pc2:
        fecha_hasta = st.date_input(
            "Hasta",
            value=date.today(),
            key="inf_pt_hasta",
        )

    refresh_punto = st.button(
        "Actualizar consulta", key="btn_gen_punto",
        icon=":material/refresh:",
    )

    cached_p_id = st.session_state.get("informe_punto_id")
    cached_p = st.session_state.get("informe_punto")
    cache_key = f"{punto_id}|{fecha_desde}|{fecha_hasta}"
    last_key = st.session_state.get("informe_punto_key")
    if refresh_punto or cached_p is None or last_key != cache_key:
        with st.spinner("Consultando datos..."):
            try:
                resumen = get_resumen_punto(
                    punto_id, str(fecha_desde), str(fecha_hasta),
                )
                st.session_state["informe_punto"] = resumen
                st.session_state["informe_punto_id"] = punto_id
                st.session_state["informe_punto_key"] = cache_key
            except Exception as exc:
                st.error(f"Error: {exc}")
                return
    else:
        resumen = cached_p

    punto = resumen["punto"]
    resultados = resumen["resultados"]

    st.markdown(f"### {punto['codigo']} — {punto['nombre']}")
    eca_info = (punto.get("ecas") or {}).get("nombre", "Sin ECA")
    st.caption(f"Tipo: {punto.get('tipo', '—')} | Cuenca: {punto.get('cuenca', '—')} | ECA: {eca_info}")

    if not resultados:
        st.info("No hay resultados en el rango de fechas seleccionado.")
        return

    st.metric("Total de resultados", len(resultados))

    # ── Gráfico de tendencia ─────────────────────────────────────────────
    df = pd.DataFrame(resultados)
    params_unicos = df["parametro"].unique().tolist()

    sel_param = st.selectbox(
        "Parámetro para gráfico",
        params_unicos,
        key="inf_pt_param_grafico",
    )

    df_param = df[df["parametro"] == sel_param].sort_values("fecha")
    if not df_param.empty:
        try:
            import plotly.express as px
            fig = px.line(
                df_param, x="fecha", y="valor",
                title=f"{sel_param} ({df_param.iloc[0]['unidad']})",
                markers=True,
            )
            fig.update_layout(xaxis_title="Fecha", yaxis_title="Valor", height=350)
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.line_chart(df_param.set_index("fecha")["valor"])

    # ── Tabla ────────────────────────────────────────────────────────────
    with st.expander(f"Ver todos los resultados ({len(resultados)})", expanded=False):
        st.dataframe(
            df[["fecha", "muestra", "parametro", "valor", "unidad"]].rename(columns={
                "fecha":     "Fecha",
                "muestra":   "Muestra",
                "parametro": "Parámetro",
                "valor":     "Valor",
                "unidad":    "Unidad",
            }),
            use_container_width=True,
            hide_index=True,
        )

    # ── Descarga Excel ───────────────────────────────────────────────────
    st.divider()
    try:
        excel_bytes = generar_excel_punto(punto_id, str(fecha_desde), str(fecha_hasta))
        st.download_button(
            label="Descargar Excel",
            data=excel_bytes,
            file_name=f"historial_{punto['codigo']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    except Exception as exc:
        st.error(f"Error generando Excel: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("visualizador")
def main() -> None:
    aplicar_estilos()
    top_nav()
    page_header("Informes", "Generación de informes y exportación de datos")

    tab_campana, tab_punto = st.tabs([
        "Informe por campaña",
        "Informe por punto",
    ])

    with tab_campana:
        _render_informe_campana()

    with tab_punto:
        _render_informe_punto()


main()
