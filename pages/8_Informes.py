"""
pages/8_Informes.py
Generación de informes y exportación de datos.

Secciones:
    Tab 1 — Informe por campaña: excedencias, Reportes de Ensayo
            (Parámetros Fisicoquímicos / Fitoplancton / Microcistina) y envío por correo
    Tab 2 — Informe por punto: historial temporal, descarga Excel

Acceso mínimo: visualizador.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.nav_context import consumir_contexto, preseleccionar
from components.ui_styles import (
    ECA_CHIP_STYLES,
    aplicar_estilos,
    chip_eca_html,
    page_header,
    section_header,
    top_nav,
)
from services.informe_service import (
    get_resumen_campana,
    get_resumen_punto,
    generar_excel_punto,
    construir_resumen_correo,
)
from services.reporte_hidrobiologico_service import tiene_analisis_hidrobiologico
from services.reporte_fitoplancton_service import (
    generar_docx_fitoplancton_campana,
    especie_dominante_campana,
    DEFAULTS as FITO_DEFAULTS,
)
from services.microcistina_service import tiene_resultados_microcistina
from services.reporte_microcistina_service import (
    generar_docx_microcistina_campana,
    DEFAULTS as MC_DEFAULTS,
)
from services.pdf_service import docx_a_pdf
from services.resultado_service import get_campanas, _get_usuario_interno_id
from services.punto_service import get_puntos
from services.contactos_service import get_contactos, crear_contacto, correo_valido
from services.email_service import (
    smtp_configurado,
    enviar_correo,
    enviar_correo_prueba,
    registrar_envio,
    get_envios,
)


# Paleta de veredictos — fuente única en components.ui_styles, compartida
# con 4_Resultados_Lab.py. Se mantiene el alias local porque varios puntos
# del módulo consultan labels vía _CHIP_ESTADOS.get(...).
_CHIP_ESTADOS: dict[str, dict] = ECA_CHIP_STYLES


def _chip_estado_html(estado: str, motivo: str = "") -> str:
    return chip_eca_html(estado, motivo=motivo)


# ─────────────────────────────────────────────────────────────────────────────
# Centro de informes — generación cacheada + tarjetas + envío por correo
# ─────────────────────────────────────────────────────────────────────────────

# Los Reportes de Ensayo (.docx) se convierten a PDF antes de descargar/enviar,
# por lo que el MIME que ve el usuario es siempre PDF (ver docx_a_pdf).
_MIME_PDF = "application/pdf"


# Generación cacheada (evita re-generar en cada interacción de la página).
# Se limpia con el botón "Actualizar". Los .docx se cachean por overrides.
@st.cache_data(ttl=600, show_spinner=False)
def _gen_fisicoquimico(cid: str) -> bytes:
    # TODO: Informe de Parámetros Fisicoquímicos — pendiente de la plantilla.
    # Cuando se defina el modelo, implementarlo en
    # services/reporte_fisicoquimico_service.py, llamarlo aquí (ver _gen_fito /
    # _gen_micro como referencia) y poner "disp": True en _catalogo_reportes.
    raise NotImplementedError(
        "El informe de Parámetros Fisicoquímicos está en preparación."
    )


@st.cache_data(ttl=600, show_spinner=False)
def _gen_fito(cid: str, ov_items: tuple) -> bytes:
    # Se genera el .docx oficial y se convierte a PDF (formato idéntico).
    return docx_a_pdf(generar_docx_fitoplancton_campana(cid, dict(ov_items)))


@st.cache_data(ttl=600, show_spinner=False)
def _gen_micro(cid: str, ov_items: tuple) -> bytes:
    # Se rellena la plantilla oficial (.docx) y se convierte a PDF.
    return docx_a_pdf(generar_docx_microcistina_campana(cid, dict(ov_items)))


@st.cache_data(ttl=600, show_spinner=False)
def _especie_dominante(cid: str):
    """Especie dominante de fitoplancton (cacheada) para el resumen del correo."""
    try:
        return especie_dominante_campana(cid)
    except Exception:
        return None


def _limpiar_cache_generacion() -> None:
    for fn in (_gen_fisicoquimico, _gen_fito, _gen_micro):
        try:
            fn.clear()
        except Exception:
            pass


def _render_opciones_encabezado(campana, hay_hidrobio, hay_micro):
    """Expander colapsado con los campos editables del encabezado de los
    Reportes de Ensayo. Devuelve (overrides_fito, overrides_micro)."""
    ov_fito: dict = {}
    ov_micro: dict = {}
    if not (hay_hidrobio or hay_micro):
        return ov_fito, ov_micro

    with st.expander("Personalizar encabezado de los Reportes de Ensayo", icon=":material/tune:"):
        st.caption(
            "Opcional. Si lo dejas vacío se usan los valores por defecto y los "
            "datos de la campaña. Aplica a los Reportes de Ensayo (.docx)."
        )
        if hay_hidrobio:
            st.markdown("**Fitoplancton**")
            a, b = st.columns(2)
            ov_fito = {
                "solicitado_por": a.text_input("Solicitado por", value=FITO_DEFAULTS["solicitado_por"], key="fito_ov_sol"),
                "proyecto": a.text_input("Proyecto", value=campana.get("nombre", "") or FITO_DEFAULTS["proyecto"], key="fito_ov_proy"),
                "procedencia": a.text_input("Procedencia", value="", placeholder="(se deriva de los puntos)", key="fito_ov_proc"),
                "muestreado_por": b.text_input("Muestreado por", value=FITO_DEFAULTS["muestreado_por"], key="fito_ov_mues"),
                "condicion": b.text_input("Condición de conservación", value=FITO_DEFAULTS["condicion"], key="fito_ov_cond"),
            }
            fr = b.date_input("Fecha de emisión", value=None, format="DD/MM/YYYY", key="fito_ov_femis")
            ov_fito["fecha_emision"] = fr.isoformat() if fr else None
            ov_fito = {k: v for k, v in ov_fito.items() if v}
        if hay_micro:
            if hay_hidrobio:
                st.divider()
            st.markdown("**Microcistina (ELISA)**")
            a, b = st.columns(2)
            ov_micro = {
                "solicitado_por": a.text_input("Solicitado por", value=MC_DEFAULTS["solicitado_por"], key="mc_ov_sol"),
                "proyecto": a.text_input("Proyecto", value=campana.get("nombre", ""), key="mc_ov_proy"),
                "procedencia": a.text_input("Procedencia", value="", placeholder="(se deriva de los puntos)", key="mc_ov_proc"),
                "tipo_muestra": b.text_input("Tipo de muestra", value=MC_DEFAULTS["tipo_muestra"], key="mc_ov_tipo"),
                "muestreado_por": b.text_input("Muestreado por", value=MC_DEFAULTS["muestreado_por"], key="mc_ov_mues"),
            }
            ov_micro = {k: v for k, v in ov_micro.items() if v}
    return ov_fito, ov_micro


def _catalogo_reportes(campana, campana_id, hay_hidrobio, hay_micro, ov_fito, ov_micro):
    """Lista de reportes con disponibilidad y generador (cacheado)."""
    cod = campana["codigo"]
    fito_items = tuple(sorted(ov_fito.items()))
    micro_items = tuple(sorted(ov_micro.items()))
    return [
        {"key": "fisicoquimico", "titulo": "Parámetros Fisicoquímicos",
         "icono": ":material/water_drop:", "disp": False,
         "motivo": "En preparación — se habilitará al definir la plantilla del informe.",
         "file": f"Reporte_Fisicoquimico_{cod}.pdf", "mime": _MIME_PDF,
         "gen": lambda: _gen_fisicoquimico(campana_id)},
        {"key": "fito", "titulo": "Fitoplancton", "icono": ":material/biotech:", "disp": hay_hidrobio,
         "motivo": "Carga un análisis en Resultados → Hidrobiológico",
         "file": f"Reporte_Fitoplancton_{cod}.pdf", "mime": _MIME_PDF,
         "gen": lambda: _gen_fito(campana_id, fito_items)},
        {"key": "micro", "titulo": "Microcistina", "icono": ":material/science:", "disp": hay_micro,
         "motivo": "Calcula una corrida ELISA en Microcistina (ELISA)",
         "file": f"Reporte_Microcistina_{cod}.pdf", "mime": _MIME_PDF,
         "gen": lambda: _gen_micro(campana_id, micro_items)},
    ]


def _render_tarjetas_informes(reportes) -> None:
    """Fila de tarjetas, una por tipo de informe, con estado y descarga."""
    cols = st.columns(len(reportes))
    for col, r in zip(cols, reportes):
        with col:
            with st.container(border=True):
                st.markdown(f"##### {r['icono']} {r['titulo']}")
                if r["disp"]:
                    st.caption(":material/check_circle: Disponible")
                    try:
                        data = r["gen"]()
                        st.download_button(
                            "Descargar", data=data, file_name=r["file"], mime=r["mime"],
                            use_container_width=True, icon=":material/download:",
                            key=f"dl_{r['key']}",
                        )
                    except Exception as exc:
                        st.error(f"Error: {exc}")
                else:
                    st.caption(":material/block: No disponible")
                    st.caption(r["motivo"])


def _render_envio_correo(campana, campana_id, reportes, resumen) -> None:
    """Panel de envío de informes por correo (libreta + adjuntos + mensaje)."""
    section_header("Enviar informes por correo", "upload")

    disponibles = [r for r in reportes if r["disp"]]
    if not smtp_configurado():
        st.warning(
            "El servidor de correo aún no está configurado. Define `SMTP_HOST`, "
            "`SMTP_PORT`, `SMTP_USER` y `SMTP_PASSWORD` (y `SMTP_TLS`/`SMTP_SSL`) "
            "en el archivo `.env` o en los *secrets* de Streamlit para habilitar "
            "el envío.",
            icon=":material/mark_email_unread:",
        )

    # Libreta de contactos.
    contactos = get_contactos()
    labels = {f"{c['nombre']} — {c['correo']}"
              + (f" ({c['entidad']})" if c.get("entidad") else ""): c["correo"]
              for c in contactos}

    # Dos columnas: destinatarios/adjuntos a la izquierda, mensaje a la derecha.
    col_dest, col_msg = st.columns(2, gap="large")

    with col_dest:
        sel = st.multiselect(
            "Destinatarios (libreta de contactos)",
            options=list(labels.keys()),
            key=f"mail_sel_{campana_id}",
            placeholder="Elige uno o más contactos guardados",
        )
        otros = st.text_input(
            "Otros correos (separados por coma)",
            key=f"mail_otros_{campana_id}",
            placeholder="ej. persona@dominio.com, otra@dominio.com",
        )

        # Alta rápida de contacto a la libreta.
        with st.expander("Agregar contacto a la libreta", icon=":material/person_add:"):
            with st.form(f"form_nuevo_contacto_{campana_id}", clear_on_submit=True):
                c_nom = st.text_input("Nombre")
                n2, n3 = st.columns(2)
                c_cor = n2.text_input("Correo")
                c_ent = n3.text_input("Entidad", placeholder="(opcional)")
                if st.form_submit_button("Guardar contacto", icon=":material/save:"):
                    try:
                        crear_contacto(c_nom, c_cor, c_ent)
                        st.success(f"Contacto «{c_nom}» agregado.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc), icon=":material/error:")

        # Adjuntos disponibles (casillas).
        st.markdown("**Adjuntar:**")
        seleccion_adj = {}
        for r in disponibles:
            seleccion_adj[r["key"]] = st.checkbox(
                f"{r['icono']} {r['titulo']}", value=True,
                key=f"adj_{r['key']}_{campana_id}",
            )

    with col_msg:
        # Asunto y cuerpo (automáticos y editables).
        asunto_def = f"Informe LVCA — {campana['codigo']} ({campana.get('nombre', '')})"
        resumen_txt = construir_resumen_correo(resumen, _especie_dominante(campana_id))
        cuerpo_def = (
            "Estimados,\n\n"
            f"Adjuntamos los informes correspondientes a la campaña "
            f"{campana['codigo']} — {campana.get('nombre', '')}.\n\n"
            f"{resumen_txt}\n\n"
            "Saludos cordiales,\n"
            "Laboratorio de Vigilancia de Calidad del Agua (LVCA) — AUTODEMA"
        )
        asunto = st.text_input("Asunto", value=asunto_def, key=f"mail_asunto_{campana_id}")
        cuerpo = st.text_area("Mensaje", value=cuerpo_def, height=140, key=f"mail_cuerpo_{campana_id}")

        b1, b2 = st.columns([2, 1])
        enviar = b1.button(
            "Enviar informes", type="primary", use_container_width=True,
            icon=":material/send:", key=f"btn_enviar_{campana_id}",
            disabled=not smtp_configurado(),
        )
        with b2:
            with st.popover("Correo de prueba", use_container_width=True, disabled=not smtp_configurado()):
                dest_prueba = st.text_input("Enviar prueba a", key=f"mail_prueba_{campana_id}")
                if st.button("Enviar prueba", key=f"btn_prueba_{campana_id}"):
                    try:
                        enviar_correo_prueba(dest_prueba)
                        st.success("Correo de prueba enviado.")
                    except Exception as exc:
                        st.error(str(exc), icon=":material/error:")

    if enviar:
        destinatarios = [labels[s] for s in sel]
        destinatarios += [e.strip() for e in (otros or "").replace(";", ",").split(",") if e.strip()]
        # Validación y deduplicado.
        invalidos = [d for d in destinatarios if not correo_valido(d)]
        destinatarios = list(dict.fromkeys(d for d in destinatarios if correo_valido(d)))
        if invalidos:
            st.error(f"Correos inválidos: {', '.join(invalidos)}", icon=":material/error:")
        elif not destinatarios:
            st.error("Elige al menos un destinatario.", icon=":material/error:")
        else:
            adjuntos = []
            nombres_adj = []
            try:
                for r in disponibles:
                    if seleccion_adj.get(r["key"]):
                        adjuntos.append((r["file"], r["gen"](), r["mime"]))
                        nombres_adj.append(r["file"])
            except Exception as exc:
                st.error(f"Error preparando adjuntos: {exc}", icon=":material/error:")
                adjuntos = None
            if adjuntos is not None:
                if not adjuntos:
                    st.error("Selecciona al menos un documento para adjuntar.", icon=":material/error:")
                else:
                    sesion = st.session_state.get("sesion")
                    enviado_por = _get_usuario_interno_id(sesion.uid) if sesion else None
                    try:
                        with st.spinner("Enviando correo…"):
                            enviar_correo(destinatarios, asunto, cuerpo, adjuntos)
                        registrar_envio(campana_id, destinatarios, asunto, nombres_adj,
                                        enviado_por, estado="enviado")
                        st.success(
                            f"Informes enviados a {len(destinatarios)} destinatario(s): "
                            f"{', '.join(destinatarios)}.",
                            icon=":material/mark_email_read:",
                        )
                    except Exception as exc:
                        registrar_envio(campana_id, destinatarios, asunto, nombres_adj,
                                        enviado_por, estado="error", error=str(exc))
                        st.error(f"No se pudo enviar: {exc}", icon=":material/error:")

    # Historial de envíos.
    envios = get_envios(campana_id, limite=5)
    if envios:
        with st.expander(f"Últimos envíos ({len(envios)})", icon=":material/history:"):
            for e in envios:
                cuando = str(e.get("enviado_at", ""))[:16].replace("T", " ")
                estado = e.get("estado", "")
                icono = ":material/check_circle:" if estado == "enviado" else ":material/warning:"
                st.caption(f"{icono} {cuando} → {e.get('destinatarios', '')} · "
                           f"{e.get('adjuntos', '') or 'sin adjuntos'}")


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
    # Contexto de navegación: otra página pidió el informe de una campaña
    preseleccionar("inf_campana", opciones, consumir_contexto("informes").get("campana_id"))
    col_sel, col_refresh = st.columns([4, 1])
    with col_sel:
        sel = st.selectbox("Seleccionar campaña", list(opciones.keys()), key="inf_campana")
        campana_id = opciones[sel]
    with col_refresh:
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        refresh = st.button(
            "Actualizar", key="btn_refresh_informe",
            icon=":material/refresh:", use_container_width=True,
        )

    # Auto-cargar el informe si cambió la campaña o se presiona Actualizar
    cached_id = st.session_state.get("informe_campana_id")
    cached = st.session_state.get("informe_campana")
    if refresh or cached is None or cached_id != campana_id:
        if refresh:
            _limpiar_cache_generacion()
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

    # ── Tabla de excedencias (solo si existen) ───────────────────────────
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
    # ── Centro de informes (descargas) ────────────────────────────────────
    section_header("Informes de la campaña", "file")
    st.caption(
        "Descarga cada informe con un clic o envíalos por correo. Personaliza el "
        "encabezado de los Reportes de Ensayo en *opciones* si lo necesitas."
    )

    hay_hidrobio = tiene_analisis_hidrobiologico(campana_id)
    hay_micro = tiene_resultados_microcistina(campana_id)

    ov_fito, ov_micro = _render_opciones_encabezado(campana, hay_hidrobio, hay_micro)
    reportes = _catalogo_reportes(
        campana, campana_id, hay_hidrobio, hay_micro, ov_fito, ov_micro,
    )
    _render_tarjetas_informes(reportes)

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

    st.divider()
    _render_envio_correo(campana, campana_id, reportes, resumen)


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
