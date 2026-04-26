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
    get_parametros_lab_campana,
    get_todos_los_puntos,
    restaurar_campana,
    set_parametros_lab_campana,
)
from services.parametro_registry import get_parametros_lab_cadena


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


def _render_seleccion_parametros_lab(
    key_prefix: str,
    seleccionados_default: list[str] | None = None,
    extras_default: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Bloque reutilizable: selección de parámetros de laboratorio que serán
    analizados en la campaña. Decide los parámetros que aparecerán marcados
    con "X" en la Ficha de Campo y en el Documento de Cadena de Custodia.

    seleccionados_default: lista de claves (lowercase codigo) pre-marcadas.
        Si es None, se marcan todas.
    extras_default: nombres libres a mostrar como extras.

    Retorna (claves_seleccionadas, extras).
    """
    param_list = list(get_parametros_lab_cadena())
    if seleccionados_default is None:
        preseleccion: set[str] = {p["clave"] for p in param_list}
    else:
        preseleccion = set(seleccionados_default)

    st.caption(
        "Marca qué parámetros de laboratorio se analizarán en esta campaña. "
        "Estos se mostrarán con «X» en la Ficha de Campo y en la Cadena de "
        "Custodia."
    )

    seleccionados: list[str] = []
    cols_per_row = 5
    for i in range(0, len(param_list), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(param_list):
                continue
            p = param_list[idx]
            marcado = col.checkbox(
                p["nombre"],
                value=p["clave"] in preseleccion,
                key=f"{key_prefix}_plab_{p['clave']}",
            )
            if marcado:
                seleccionados.append(p["clave"])

    extras_str = ", ".join(extras_default or [])
    extras_text = st.text_input(
        "Parámetros adicionales (separados por coma)",
        value=extras_str,
        placeholder="Ej: Cianuro, DBO5, Coliformes totales",
        key=f"{key_prefix}_plab_extras",
    )
    extras = [e.strip() for e in extras_text.split(",") if e.strip()]
    return seleccionados, extras


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

    # ── Tabla resumen (clickable) ────────────────────────────────────────────
    st.markdown(f"#### {len(campanas)} campaña(s) encontrada(s)")
    st.caption("Haz clic en una fila para ver el detalle de la campaña.")

    df = pd.DataFrame(campanas)
    df["estado_label"] = df["estado"].apply(_badge_estado)

    df_view = df[[
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
    })

    event = st.dataframe(
        df_view,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tabla_campanas",
    )

    # ── Detalle de la campaña seleccionada ───────────────────────────────────
    sel_rows = getattr(event, "selection", {}).get("rows") if hasattr(event, "selection") else event.get("selection", {}).get("rows", [])
    if not sel_rows:
        st.info("Selecciona una campaña en la tabla para ver su detalle.")
        return

    campana_id = campanas[sel_rows[0]]["id"]
    st.divider()
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
    with st.expander(
        "Editar datos de la campaña",
        expanded=False,
        icon=":material/edit:",
    ):
        _render_editar_campana(campana_id, camp)

    # ── Puntos incluidos ─────────────────────────────────────────────────────
    st.divider()
    with st.expander(
        f"Puntos de muestreo incluidos ({len(puntos)})",
        expanded=True,
        icon=":material/place:",
    ):
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
        f"Muestras y avance de análisis ({avance['porcentaje']:.1f}%)",
        expanded=True,
        icon=":material/science:",
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

    # ── Archivar / restaurar (soft-delete, recomendado) ──────────────────────
    st.divider()
    sesion = st.session_state.get("sesion")
    usuario_id = sesion.uid if sesion else None
    es_archivada = camp["estado"] == "archivada"

    with st.expander(
        "Archivar campaña" if not es_archivada else "Restaurar campaña archivada",
        expanded=False,
        icon=":material/archive:",
    ):
        st.caption(
            "Archivar oculta la campaña de los listados sin borrar datos. "
            "Recomendado para campañas finalizadas que ya no se consultan."
        )
        if not es_archivada:
            motivo = st.text_input(
                "Motivo (opcional)",
                placeholder="Ej. Campaña cerrada, datos consolidados en informe anual",
                key=f"motivo_archivado_{campana_id}",
            )
            if st.button(
                "Archivar campaña",
                key=f"btn_archivar_{campana_id}",
                type="primary",
                icon=":material/archive:",
            ):
                try:
                    archivar_campana(campana_id, motivo=motivo, usuario_id=usuario_id)
                    toast(f"Campaña {camp['codigo']} archivada", tipo="info")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error al archivar: {exc}")
        else:
            st.info(f"Esta campaña está archivada. Restáurala para volver a operar sobre ella.")
            if st.button(
                "Restaurar campaña",
                key=f"btn_restaurar_{campana_id}",
                icon=":material/restore_from_trash:",
            ):
                try:
                    restaurar_campana(campana_id)
                    toast(f"Campaña {camp['codigo']} restaurada", tipo="success")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error al restaurar: {exc}")

    # ── Eliminar permanentemente (irreversible) ──────────────────────────────
    with st.expander(
        "Eliminar permanentemente",
        expanded=False,
        icon=":material/warning:",
    ):
        st.error(
            "**ATENCIÓN:** El borrado físico destruye datos para siempre. "
            "Para campañas con datos válidos usa **Archivar** en su lugar."
        )
        st.warning(
            f"Se eliminará **{camp['codigo']}** y **todos** sus datos asociados "
            f"(muestras, resultados, mediciones in situ). Esta acción es irreversible."
        )
        confirmar = st.text_input(
            f"Escribe el código **{camp['codigo']}** para confirmar:",
            key="confirmar_eliminar_camp",
        )
        if st.button(
            "Eliminar permanentemente",
            key="btn_eliminar_camp",
            type="primary",
            icon=":material/delete_forever:",
        ):
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
    # Cargar la selección actual de parámetros de lab (fuera del form para
    # que el widget de checkboxes pueda renderizarse consistentemente).
    sel_actual = get_parametros_lab_campana(campana_id)
    claves_actuales = sel_actual["parametros_lab"] or None  # None = todos
    extras_actuales = sel_actual["parametros_lab_extra"]

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

        st.caption(
            f":material/science: **Responsable de laboratorio:** {_RESPONSABLE_LAB} "
            f"_(fijo para todas las campañas)_"
        )
        resp_lab_sel = _RESPONSABLE_LAB

        observaciones = st.text_area(
            "Observaciones",
            value=camp.get("observaciones") or "",
            key="edit_obs",
        )

        section_header("Parámetros de laboratorio a analizar", "beaker")
        params_lab_sel, params_lab_extra = _render_seleccion_parametros_lab(
            key_prefix=f"edit_{campana_id}",
            seleccionados_default=claves_actuales,
            extras_default=extras_actuales,
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
            sesion = st.session_state.get("sesion")
            set_parametros_lab_campana(
                campana_id,
                params_lab_sel,
                params_lab_extra,
                usuario_id=sesion.uid if sesion else None,
            )
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

    with st.form("form_nueva_campana", clear_on_submit=False):
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

        st.caption(
            f":material/science: **Responsable de laboratorio:** {_RESPONSABLE_LAB} "
            f"_(fijo para todas las campañas)_"
        )
        responsable_lab_sel = _RESPONSABLE_LAB

        puntos_sel = st.multiselect(
            "Puntos de muestreo incluidos *",
            list(opciones_puntos.keys()),
            default=list(opciones_puntos.keys()),  # todos por defecto
        )

        section_header("Parámetros de laboratorio a analizar", "beaker")
        params_lab_sel, params_lab_extra = _render_seleccion_parametros_lab(
            key_prefix="new",
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
                set_parametros_lab_campana(
                    creada["id"],
                    params_lab_sel,
                    params_lab_extra,
                    usuario_id=usuario_id,
                )
                success_check_overlay(
                    f"Campaña {creada['codigo']} creada"
                )
                st.success(
                    f"Campaña **{creada['codigo']}** creada con "
                    f"{len(puntos_ids)} punto(s) de muestreo y "
                    f"{len(params_lab_sel) + len(params_lab_extra)} parámetro(s) de laboratorio."
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

    tab_lista, tab_nueva = st.tabs([
        ":material/list: Listado de campañas",
        ":material/add: Nueva campaña",
    ])

    with tab_lista:
        _render_listado()

    with tab_nueva:
        _render_formulario_nueva()


main()
