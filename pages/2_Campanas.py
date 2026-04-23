"""
pages/2_Campanas.py
Gestión de campañas de monitoreo — CRUD completo.

Secciones:
    Tab 1 — Listado: filtro por estado/fecha, tabla, vista detalle expandible
    Tab 2 — Nueva campaña: formulario con código autogenerado

Acceso mínimo: administrador.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import (
    aplicar_estilos,
    page_header,
    section_header,
    success_check_overlay,
    toast,
    top_nav,
)
from services.campana_service import (
    ESTADOS,
    ETIQUETA_ESTADO,
    FRECUENCIAS,
    TRANSICIONES_VALIDAS,
    TransicionInvalidaError,
    actualizar_campana,
    actualizar_estado,
    actualizar_puntos_campana,
    archivar_campana,
    crear_campana,
    eliminar_campana,
    get_campanas,
    get_detalle_campana,
    get_todos_los_puntos,
    restaurar_campana,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constantes / helpers del módulo
# ─────────────────────────────────────────────────────────────────────────────

# Lista fija de responsables de campo autorizados (máx. 4 en simultáneo).
_RESPONSABLES_CAMPO = [
    "Victor Llacho",
    "Alfonso Torres",
    "Jean Pierre Llerena",
    "Alexis Vilcapaza",
]
# Responsable de laboratorio fijo — siempre será esta persona.
_RESPONSABLE_LAB = "Ing. Ana Lucía Paz Alcázar"
_MAX_RESP_CAMPO = 4


def _opciones_responsables_campo() -> list[str]:
    """Nombres elegibles como responsable de campo (lista fija)."""
    return list(_RESPONSABLES_CAMPO)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de presentación
# ─────────────────────────────────────────────────────────────────────────────

def _badge_estado(estado: str) -> str:
    """Retorna etiqueta con ícono para el estado."""
    return ETIQUETA_ESTADO.get(estado, estado)


def _color_estado(estado: str) -> str:
    return {
        "planificada":    "#6c757d",
        "en_campo":       "#0d6efd",
        "en_laboratorio": "#ffc107",
        "completada":     "#198754",
        "anulada":        "#dc3545",
    }.get(estado, "#6c757d")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Listado y detalle
# ─────────────────────────────────────────────────────────────────────────────

def _render_listado() -> None:
    # ── Filtros ──────────────────────────────────────────────────────────────
    section_header("Filtros", "filter")
    fc1, fc2, fc3 = st.columns(3)

    with fc1:
        opciones_estado = ["Todos"] + [_badge_estado(e) for e in ESTADOS]
        sel_estado_label = st.selectbox("Estado", opciones_estado, key="filtro_estado")
        # Resolución inversa: etiqueta → valor
        filtro_estado = None
        for e in ESTADOS:
            if _badge_estado(e) == sel_estado_label:
                filtro_estado = e
                break

    with fc2:
        fecha_desde = st.date_input(
            "Desde",
            value=date.today() - timedelta(days=365),
            key="filtro_desde",
        )

    with fc3:
        fecha_hasta = st.date_input(
            "Hasta",
            value=date.today() + timedelta(days=30),
            key="filtro_hasta",
        )

    # ── Consulta ─────────────────────────────────────────────────────────────
    campanas = get_campanas(
        filtro_estado=filtro_estado,
        fecha_desde=str(fecha_desde) if fecha_desde else None,
        fecha_hasta=str(fecha_hasta) if fecha_hasta else None,
    )

    if not campanas:
        st.info("No se encontraron campañas con los filtros seleccionados.")
        return

    # ── Tabla resumen ────────────────────────────────────────────────────────
    st.markdown(f"#### {len(campanas)} campaña(s) encontrada(s)")

    df = pd.DataFrame(campanas)
    df["estado_label"] = df["estado"].apply(_badge_estado)

    st.dataframe(
        df[[
            "codigo", "nombre", "fecha_inicio", "fecha_fin",
            "estado_label", "frecuencia", "responsable_campo",
        ]].rename(columns={
            "codigo":            "Código",
            "nombre":            "Nombre",
            "fecha_inicio":      "Inicio",
            "fecha_fin":         "Fin",
            "estado_label":      "Estado",
            "frecuencia":        "Frecuencia",
            "responsable_campo": "Resp. campo",
        }),
        use_container_width=True,
        hide_index=True,
    )

    # ── Archivar campaña (soft-delete, recomendado) ──────────────────────
    st.divider()
    with st.expander("📦 Archivar / restaurar campaña", expanded=False):
        st.caption(
            "Archivar oculta la campaña de los listados sin borrar datos. "
            "Recomendado para campañas finalizadas que ya no se consultan."
        )
        opciones_archivar = {
            f"{c['codigo']} — {c['nombre']} ({_badge_estado(c['estado'])})": c
            for c in campanas
        }
        sel_archivar = st.selectbox(
            "Seleccionar campaña",
            list(opciones_archivar.keys()),
            key="sel_archivar_camp",
        )
        camp_target = opciones_archivar[sel_archivar]
        motivo = st.text_input(
            "Motivo (opcional)",
            placeholder="Ej. Campaña cerrada, datos consolidados en informe anual",
            key="motivo_archivado_camp",
        )
        col_a, col_b = st.columns(2)
        sesion = st.session_state.get("sesion")
        usuario_id = sesion.uid if sesion else None
        with col_a:
            if camp_target["estado"] != "archivada":
                if st.button("Archivar", key="btn_archivar_camp", type="primary", icon=":material/archive:"):
                    try:
                        archivar_campana(camp_target["id"], motivo=motivo, usuario_id=usuario_id)
                        toast(f"Campaña {camp_target['codigo']} archivada", tipo="info")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error al archivar: {exc}")
            else:
                if st.button("Restaurar", key="btn_restaurar_camp", icon=":material/restore_from_trash:"):
                    try:
                        restaurar_campana(camp_target["id"])
                        toast(f"Campaña {camp_target['codigo']} restaurada", tipo="success")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error al restaurar: {exc}")

    # ── Eliminación PERMANENTE (solo casos extremos) ─────────────────────
    if sesion and getattr(sesion, "rol", "") == "administrador":
        with st.expander("⚠️ Eliminar permanentemente (irreversible)", expanded=False):
            st.error(
                "**ATENCIÓN:** El borrado físico destruye datos para siempre. "
                "Para campañas con datos válidos usa **Archivar** en su lugar."
            )
            opciones_eliminar = {
                f"{c['codigo']} — {c['nombre']} ({_badge_estado(c['estado'])})": c
                for c in campanas
            }
            sel_eliminar = st.selectbox(
                "Seleccionar campaña a eliminar permanentemente",
                list(opciones_eliminar.keys()),
                key="sel_eliminar_camp",
            )
            camp_eliminar = opciones_eliminar[sel_eliminar]
            st.warning(
                f"Se eliminará **{camp_eliminar['codigo']}** y **todos** sus datos: "
                f"muestras, resultados, mediciones."
            )
            confirmar_codigo = st.text_input(
                f"Escribe **{camp_eliminar['codigo']}** para confirmar:",
                key="confirmar_codigo_elim",
            )
            st.markdown('<div class="lvca-danger">', unsafe_allow_html=True)
            confirm_btn = st.button(
                "Eliminar permanentemente",
                key="btn_elim_camp_listado", type="primary",
                icon=":material/delete_forever:",
            )
            st.markdown('</div>', unsafe_allow_html=True)
            if confirm_btn:
                if confirmar_codigo.strip() != camp_eliminar["codigo"]:
                    st.error("El código no coincide.")
                else:
                    try:
                        info = eliminar_campana(camp_eliminar["id"], forzar=True)
                        toast(
                            f"Campaña eliminada — {info['muestras']} muestras, "
                            f"{info['resultados']} resultados",
                            tipo="danger",
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Error: {exc}")

    # ── Selector de detalle ──────────────────────────────────────────────────
    st.divider()
    opciones_detalle = {
        f"{c['codigo']} — {c['nombre']}": c["id"]
        for c in campanas
    }
    sel_detalle = st.selectbox(
        "Ver detalle de campaña",
        list(opciones_detalle.keys()),
        key="sel_detalle",
    )
    campana_id = opciones_detalle[sel_detalle]

    _render_detalle(campana_id)


def _render_detalle(campana_id: str) -> None:
    """Muestra el detalle completo de una campaña."""
    with st.spinner("Cargando detalle..."):
        try:
            detalle = get_detalle_campana(campana_id)
        except Exception as exc:
            st.error(f"Error al cargar detalle: {exc}")
            return

    camp   = detalle["campana"]
    puntos = detalle["puntos"]
    muestras = detalle["muestras"]
    avance = detalle["avance"]

    # ── Cabecera ─────────────────────────────────────────────────────────────
    from components.ui_styles import estado_pill, timeline as _timeline

    head_l, head_r = st.columns([4, 1])
    with head_l:
        st.markdown(f"### {camp['codigo']} — {camp['nombre']}")
    with head_r:
        st.markdown(estado_pill(camp["estado"]), unsafe_allow_html=True)

    hc2, hc3, hc4 = st.columns(3)
    hc2.metric("Frecuencia", (camp.get("frecuencia") or "—").capitalize())
    hc3.metric("Inicio",     str(camp.get("fecha_inicio", "—"))[:10])
    hc4.metric("Fin",        str(camp.get("fecha_fin", "—"))[:10])

    # Timeline visual del ciclo de vida de la campaña
    _ciclo = ["planificada", "en_campo", "en_laboratorio", "completada"]
    _labels_ciclo = ["Planificada", "En campo", "En laboratorio", "Completada"]
    _estado = camp["estado"]
    if _estado in _ciclo:
        _idx_actual = _ciclo.index(_estado)
    elif _estado == "anulada":
        _idx_actual = 0  # anulada se renderiza desde el inicio
    elif _estado == "archivada":
        _idx_actual = len(_ciclo) - 1
    else:
        _idx_actual = 0
    _timeline(
        [{"label": lbl, "sub": ""} for lbl in _labels_ciclo],
        current=_idx_actual,
    )

    rc1, rc2 = st.columns(2)
    rc1.markdown(f"**Responsable campo:** {camp.get('responsable_campo') or '—'}")
    rc2.markdown(f"**Responsable lab:** {camp.get('responsable_laboratorio') or '—'}")

    if camp.get("observaciones"):
        st.caption(f"Observaciones: {camp['observaciones']}")

    # ── Transición de estado ─────────────────────────────────────────────────
    estado_actual = camp["estado"]
    st.divider()

    bc1, bc2 = st.columns([3, 2])

    with bc1:
        siguiente = TRANSICIONES_VALIDAS.get(estado_actual)
        if siguiente:
            etiq = _badge_estado(siguiente)
            if st.button(
                f"Avanzar a → {etiq}",
                key="btn_avanzar",
                type="primary",
            ):
                try:
                    actualizar_estado(campana_id, siguiente)
                    st.success(f"Estado actualizado a {etiq}.")
                    st.rerun()
                except TransicionInvalidaError as exc:
                    st.error(str(exc))
        elif estado_actual == "completada":
            st.success("Esta campaña ya está completada.")
        elif estado_actual == "anulada":
            st.error("Esta campaña fue anulada.")

    with bc2:
        if estado_actual not in ("completada", "anulada"):
            if st.button("Anular campaña", key="btn_anular", icon=":material/cancel:"):
                try:
                    actualizar_estado(campana_id, "anulada")
                    st.warning("Campaña anulada.")
                    st.rerun()
                except TransicionInvalidaError as exc:
                    st.error(str(exc))

    # ── Edición de campaña (admin) ───────────────────────────────────────────
    st.divider()
    with st.expander("✏️ Editar datos de la campaña", expanded=False):
        _render_editar_campana(campana_id, camp)

    # ── Puntos incluidos ─────────────────────────────────────────────────────
    st.divider()
    with st.expander(f"📍 Puntos de muestreo incluidos ({len(puntos)})", expanded=True):
        if puntos:
            df_pts = pd.DataFrame(puntos)
            st.dataframe(
                df_pts[["codigo", "nombre", "tipo", "cuenca"]].rename(columns={
                    "codigo": "Código",
                    "nombre": "Nombre",
                    "tipo":   "Tipo",
                    "cuenca": "Cuenca",
                }),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("No hay puntos vinculados a esta campaña.")

        # Editar puntos vinculados
        _render_editar_puntos(campana_id, puntos)

    # ── Avance de análisis ───────────────────────────────────────────────────
    with st.expander(
        f"🧪 Muestras y avance de análisis ({avance['porcentaje']:.1f}%)",
        expanded=True,
    ):
        # Métricas globales
        ac1, ac2, ac3, ac4 = st.columns(4)
        ac1.metric("Muestras", avance["total_muestras"])
        ac2.metric("Con resultados", avance["muestras_con_resultados"])
        ac3.metric("Resultados",
                   f"{avance['total_resultados_registrados']}/{avance['total_resultados_esperados']}")
        ac4.metric("Avance", f"{avance['porcentaje']:.1f}%")

        # Barra de progreso
        st.progress(min(avance["porcentaje"] / 100.0, 1.0))

        # Tabla de muestras individuales
        if muestras:
            filas_m = []
            for m in muestras:
                pt = m.get("puntos_muestreo") or {}
                filas_m.append({
                    "Código":     m["codigo"],
                    "Punto":      f"{pt.get('codigo', '')} — {pt.get('nombre', '')}",
                    "Fecha":      str(m.get("fecha_muestreo", ""))[:10],
                    "Estado":     m.get("estado", ""),
                    "Resultados": f"{m['n_resultados']}/{m['total_parametros']}",
                    "Avance":     f"{m['avance_pct']:.1f}%",
                })
            st.dataframe(
                pd.DataFrame(filas_m),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.caption("Aún no hay muestras registradas en esta campaña.")

    # ── Eliminar campaña ──────────────────────────────────────────────────────
    st.divider()
    with st.expander("🗑️ Eliminar campaña", expanded=False):
        st.warning(
            f"Se eliminará **{camp['codigo']}** y **todos** sus datos asociados "
            f"(muestras, resultados, mediciones in situ). Esta acción es irreversible."
        )
        confirmar = st.text_input(
            f"Escribe el código **{camp['codigo']}** para confirmar:",
            key="confirmar_eliminar_camp",
        )
        if st.button("Eliminar campaña permanentemente", key="btn_eliminar_camp", type="primary"):
            if confirmar.strip() != camp["codigo"]:
                st.error("El código ingresado no coincide.")
            else:
                try:
                    info = eliminar_campana(campana_id, forzar=True)
                    st.success(
                        f"Campaña eliminada. "
                        f"{info['muestras']} muestra(s), "
                        f"{info['resultados']} resultado(s), "
                        f"{info['mediciones']} medición(es) eliminadas."
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Editar campaña y puntos
# ─────────────────────────────────────────────────────────────────────────────

def _render_editar_campana(campana_id: str, camp: dict) -> None:
    """Formulario inline para editar datos de la campaña."""
    with st.form("form_editar_campana", clear_on_submit=False):
        nombre = st.text_input("Nombre", value=camp.get("nombre") or "")

        ec1, ec2 = st.columns(2)
        with ec1:
            fecha_ini = st.date_input(
                "Fecha inicio",
                value=date.fromisoformat(camp["fecha_inicio"][:10]) if camp.get("fecha_inicio") else date.today(),
                key="edit_fecha_ini",
            )
        with ec2:
            fecha_f = st.date_input(
                "Fecha fin",
                value=date.fromisoformat(camp["fecha_fin"][:10]) if camp.get("fecha_fin") else date.today(),
                key="edit_fecha_fin",
            )

        ec3, ec4 = st.columns(2)
        with ec3:
            freq_actual = (camp.get("frecuencia") or "mensual").lower()
            freq_idx = FRECUENCIAS.index(freq_actual) if freq_actual in FRECUENCIAS else 0
            frecuencia = st.selectbox(
                "Frecuencia",
                [f.capitalize() for f in FRECUENCIAS],
                index=freq_idx,
                key="edit_frecuencia",
            )
        with ec4:
            # Parsear responsables actuales desde el texto almacenado
            opciones_resp = _opciones_responsables_campo()
            resp_actual = camp.get("responsable_campo") or ""
            default_resp = [
                r.strip() for r in resp_actual.split(",")
                if r.strip() in opciones_resp
            ]
            resp_campo_sel = st.multiselect(
                f"Responsable de campo (máx. {_MAX_RESP_CAMPO})",
                opciones_resp,
                default=default_resp,
                max_selections=_MAX_RESP_CAMPO,
                key="edit_resp_campo",
            )

        st.text_input(
            "Responsable de laboratorio",
            value=_RESPONSABLE_LAB,
            disabled=True,
            key="edit_resp_lab_display",
            help="Responsable de laboratorio fijo para todas las campañas.",
        )
        resp_lab_sel = _RESPONSABLE_LAB

        observaciones = st.text_area(
            "Observaciones",
            value=camp.get("observaciones") or "",
            key="edit_obs",
        )

        submitted = st.form_submit_button("Guardar cambios", type="primary")

    if submitted:
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
            return
        try:
            actualizar_campana(campana_id, {
                "nombre":                  nombre.strip(),
                "fecha_inicio":            str(fecha_ini),
                "fecha_fin":               str(fecha_f),
                "frecuencia":              frecuencia.lower(),
                "responsable_campo":       ", ".join(resp_campo_sel) if resp_campo_sel else None,
                "responsable_laboratorio": resp_lab_sel,
                "observaciones":           observaciones.strip() or None,
            })
            st.success("Campaña actualizada correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"Error al actualizar: {exc}")


def _render_editar_puntos(campana_id: str, puntos_actuales: list[dict]) -> None:
    """Permite agregar/quitar puntos de muestreo vinculados."""
    st.markdown("---")
    section_header("Modificar puntos vinculados", "edit")

    todos_los_puntos = get_todos_los_puntos()
    opciones = {
        f"{p['codigo']} — {p['nombre']} ({p.get('tipo', '')})": p["id"]
        for p in todos_los_puntos
    }
    ids_actuales = {p["id"] for p in puntos_actuales}
    labels_actuales = [
        label for label, pid in opciones.items() if pid in ids_actuales
    ]

    sel_puntos = st.multiselect(
        "Puntos de muestreo",
        list(opciones.keys()),
        default=labels_actuales,
        key="edit_puntos_campana",
    )

    if st.button("Actualizar puntos", key="btn_update_puntos"):
        nuevos_ids = [opciones[label] for label in sel_puntos]
        try:
            actualizar_puntos_campana(campana_id, nuevos_ids)
            st.success(f"Puntos actualizados ({len(nuevos_ids)} punto(s)).")
            st.rerun()
        except Exception as exc:
            st.error(f"Error: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Formulario nueva campaña
# ─────────────────────────────────────────────────────────────────────────────

def _render_formulario_nueva() -> None:
    section_header("Nueva campaña de monitoreo", "plus")
    st.caption("El código se generará automáticamente (CAMP-YYYY-NNN).")

    # Cargar puntos disponibles para el multiselect
    puntos = get_todos_los_puntos()
    opciones_puntos = {
        f"{p['codigo']} — {p['nombre']} ({p.get('tipo','')})": p["id"]
        for p in puntos
    }

    with st.form("form_nueva_campana", clear_on_submit=True):
        nombre = st.text_input(
            "Nombre de la campaña *",
            placeholder="Monitoreo mensual marzo 2025 — Cuenca Chili",
        )

        fc1, fc2 = st.columns(2)
        with fc1:
            fecha_inicio = st.date_input("Fecha inicio *", value=date.today())
        with fc2:
            fecha_fin = st.date_input(
                "Fecha fin *",
                value=date.today() + timedelta(days=15),
            )

        fc3, fc4 = st.columns(2)
        with fc3:
            frecuencia = st.selectbox(
                "Frecuencia",
                [f.capitalize() for f in FRECUENCIAS],
                index=0,
            )
        with fc4:
            responsable_campo_sel = st.multiselect(
                f"Responsable de campo (máx. {_MAX_RESP_CAMPO})",
                _opciones_responsables_campo(),
                max_selections=_MAX_RESP_CAMPO,
                key="new_resp_campo",
            )

        st.text_input(
            "Responsable de laboratorio",
            value=_RESPONSABLE_LAB,
            disabled=True,
            key="new_resp_lab_display",
            help="Responsable de laboratorio fijo para todas las campañas.",
        )
        responsable_lab_sel = _RESPONSABLE_LAB

        puntos_sel = st.multiselect(
            "Puntos de muestreo incluidos *",
            list(opciones_puntos.keys()),
            default=list(opciones_puntos.keys()),  # todos por defecto
        )

        observaciones = st.text_area(
            "Observaciones",
            placeholder="Notas sobre la campaña...",
        )

        submitted = st.form_submit_button(
            "Crear campaña",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        # Validaciones
        errores = []
        if not nombre.strip():
            errores.append("El nombre es obligatorio.")
        if fecha_fin < fecha_inicio:
            errores.append("La fecha fin no puede ser anterior a la fecha inicio.")
        if not puntos_sel:
            errores.append("Selecciona al menos un punto de muestreo.")

        if errores:
            for e in errores:
                st.error(e)
            return

        puntos_ids = [opciones_puntos[label] for label in puntos_sel]

        datos = {
            "nombre":                    nombre.strip(),
            "fecha_inicio":              str(fecha_inicio),
            "fecha_fin":                 str(fecha_fin),
            "frecuencia":                frecuencia.lower(),
            "responsable_campo":         ", ".join(responsable_campo_sel) if responsable_campo_sel else None,
            "responsable_laboratorio":   responsable_lab_sel,
            "observaciones":             observaciones.strip() or None,
            "puntos_ids":                puntos_ids,
        }

        sesion = st.session_state.get("sesion")
        usuario_id = sesion.uid if sesion else None
        with st.spinner("Creando campaña..."):
            try:
                creada = crear_campana(datos, usuario_id=usuario_id)
                success_check_overlay(
                    f"Campaña {creada['codigo']} creada"
                )
                st.success(
                    f"Campaña **{creada['codigo']}** creada con "
                    f"{len(puntos_ids)} punto(s) de muestreo."
                )
            except Exception as exc:
                st.error(f"Error al crear la campaña: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("administrador")
def main() -> None:
    aplicar_estilos()
    top_nav()
    page_header(
        "Campañas de Monitoreo",
        "Gestión del ciclo de vida de campañas · AUTODEMA",
        ambito="Cuenca Chili-Quilca",
    )

    tab_lista, tab_nueva = st.tabs(["📋 Listado de campañas", "➕ Nueva campaña"])

    with tab_lista:
        _render_listado()

    with tab_nueva:
        _render_formulario_nueva()


main()
