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
from components.ui_styles import aplicar_estilos, page_header
from services.informe_service import (
    get_resumen_campana,
    get_resumen_punto,
    generar_excel_campana,
    generar_excel_punto,
    generar_pdf_campana,
)
from services.resultado_service import get_campanas
from services.punto_service import get_puntos


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Informe por campaña
# ─────────────────────────────────────────────────────────────────────────────

def _render_informe_campana() -> None:
    st.markdown("#### Informe por campaña")

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

    # ── Métricas ─────────────────────────────────────────────────────────
    st.markdown(f"### {campana['codigo']} — {campana['nombre']}")

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Puntos", len(resumen["puntos"]))
    mc2.metric("Muestras", len(resumen["muestras"]))
    mc3.metric("Resultados", resumen["total_resultados"])
    mc4.metric("Excedencias", resumen["total_excedencias"])

    # ── Tabla de excedencias ─────────────────────────────────────────────
    if resumen["excedencias"]:
        st.markdown("#### Excedencias ECA detectadas")
        df_exc = pd.DataFrame(resumen["excedencias"])
        st.dataframe(
            df_exc[[
                "punto_codigo", "parametro_nombre", "valor",
                "lim_max", "lim_min", "unidad", "fecha_analisis",
            ]].rename(columns={
                "punto_codigo":     "Punto",
                "parametro_nombre": "Parámetro",
                "valor":            "Valor",
                "lim_max":          "Lím. máx.",
                "lim_min":          "Lím. mín.",
                "unidad":           "Unidad",
                "fecha_analisis":   "Fecha",
            }),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.success("No se detectaron excedencias ECA en esta campaña.")

    # ── Tabla de resultados completa ─────────────────────────────────────
    with st.expander(f"Ver todos los resultados ({resumen['total_resultados']})", expanded=False):
        if resumen["resultados"]:
            df_res = pd.DataFrame(resumen["resultados"])
            df_vista = df_res[[
                "muestra_codigo", "punto_codigo",
                "parametro_nombre", "valor", "unidad", "estado_eca",
            ]].rename(columns={
                "muestra_codigo":   "Muestra",
                "punto_codigo":     "Punto",
                "parametro_nombre": "Parámetro",
                "valor":            "Valor",
                "unidad":           "Unidad",
                "estado_eca":       "Estado ECA",
            })
            df_vista["Estado ECA"] = df_vista["Estado ECA"].map({
                "cumple": "Cumple", "excede": "EXCEDE",
                "sin_limite": "SIN ECA", "sin_dato": "Sin dato",
            }).fillna(df_vista["Estado ECA"])
            st.dataframe(
                df_vista,
                use_container_width=True,
                hide_index=True,
            )

    # ── Descargas ────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### Descargas")
    dc1, dc2 = st.columns(2)

    with dc1:
        try:
            excel_bytes = generar_excel_campana(campana_id)
            st.download_button(
                label="Descargar Excel",
                data=excel_bytes,
                file_name=f"informe_{campana['codigo']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Error generando Excel: {exc}")

    with dc2:
        try:
            pdf_bytes = generar_pdf_campana(campana_id)
            st.download_button(
                label="Descargar PDF",
                data=pdf_bytes,
                file_name=f"informe_{campana['codigo']}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Error generando PDF: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Informe por punto
# ─────────────────────────────────────────────────────────────────────────────

def _render_informe_punto() -> None:
    st.markdown("#### Informe por punto de muestreo")

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
    page_header("Informes", "Generacion de informes y exportacion de datos")

    tab_campana, tab_punto = st.tabs([
        "Informe por campaña",
        "Informe por punto",
    ])

    with tab_campana:
        _render_informe_campana()

    with tab_punto:
        _render_informe_punto()


main()
