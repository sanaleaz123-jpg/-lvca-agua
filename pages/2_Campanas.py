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
from components.nav_context import consumir_contexto
from components.ui_styles import (
    CAMPANA_ESTADO_COLORS,
    aplicar_estilos,
    page_header,
    section_header,
    style_eca_dataframe,
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
    peek_siguiente_codigo,
    restaurar_campana,
    set_parametros_lab_campana,
)
from services.etiquetas_service import (
    MODO_COLUMNA,
    MODO_SUPERFICIAL,
    PROFUNDIDADES_COLUMNA,
    TIPOS_COLUMNA,
    generar_etiquetas_campana,
    get_ensayos_disponibles,
)
from services.cadena_custodia_service import (
    get_matriz_ensayos,
    guardar_matriz_ensayos,
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


def _normalizar_cuenca(valor: str | None) -> str:
    """Normaliza el nombre de cuenca (colapsa espacios alrededor de guiones)."""
    if not valor:
        return "Sin cuenca"
    # "Quilca - Chili - Vitor" → "Quilca-Chili-Vitor"
    return " ".join(valor.replace(" - ", "-").split())


def _preparar_duplicado(camp: dict, puntos: list[dict], campana_id: str) -> None:
    """
    Construye un borrador en session_state con los datos de una campaña existente
    para pre-llenar el formulario "Nueva campaña". No copia código ni fechas.
    """
    sel_lab = get_parametros_lab_campana(campana_id)
    resp_actual = camp.get("responsable_campo") or ""
    resp_validos = [
        r.strip() for r in resp_actual.split(",")
        if r.strip() in _RESPONSABLES_CAMPO
    ]
    st.session_state["duplicar_camp"] = {
        "origen_codigo":         camp["codigo"],
        "origen_nombre":         camp.get("nombre") or "",
        "frecuencia":            (camp.get("frecuencia") or "mensual").lower(),
        "responsable_campo":     resp_validos,
        "observaciones":         camp.get("observaciones") or "",
        "puntos_ids":            [p["id"] for p in puntos],
        "parametros_lab":        sel_lab.get("parametros_lab") or [],
        "parametros_lab_extra":  sel_lab.get("parametros_lab_extra") or [],
    }


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


_ESTADO_LABEL_LIMPIO: dict[str, str] = {
    "planificada":    "Planificada",
    "en_campo":       "En campo",
    "en_laboratorio": "En laboratorio",
    "completada":     "Completada",
    "anulada":        "Anulada",
    "archivada":      "Archivada",
}

# Etiqueta mostrada → par {bg, fg} para tintar la celda Estado de la tabla,
# derivado del mapa centralizado CAMPANA_ESTADO_COLORS (paleta de pills). Así
# la celda combina con el pill del panel de detalle y con toda la plataforma.
_ESTADO_CELDA_COLORS: dict[str, dict[str, str]] = {
    label: CAMPANA_ESTADO_COLORS[key]
    for key, label in _ESTADO_LABEL_LIMPIO.items()
    if key in CAMPANA_ESTADO_COLORS
}


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Listado y detalle
# ─────────────────────────────────────────────────────────────────────────────

def _render_listado() -> None:
    # ── Filtros ──────────────────────────────────────────────────────────────
    section_header("Filtros", "filter")
    fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 1.5])

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

    with fc4:
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        incluir_archivadas = st.toggle(
            "Incluir archivadas",
            value=False,
            key="filtro_incluir_archivadas",
            help="Si está activo, las campañas archivadas también aparecerán en la tabla.",
        )

    # ── Consulta ─────────────────────────────────────────────────────────────
    campanas = get_campanas(
        filtro_estado=filtro_estado,
        fecha_desde=str(fecha_desde) if fecha_desde else None,
        fecha_hasta=str(fecha_hasta) if fecha_hasta else None,
        incluir_archivadas=incluir_archivadas,
    )

    if not campanas:
        st.info("No se encontraron campañas con los filtros seleccionados.")
        return

    # ── Tabla resumen (clickable) ────────────────────────────────────────────
    st.markdown(f"#### {len(campanas)} campaña(s) encontrada(s)")
    st.caption("Haz clic en una fila para ver el detalle de la campaña.")

    df = pd.DataFrame(campanas)
    df["estado_label"] = df["estado"].map(_ESTADO_LABEL_LIMPIO).fillna(df["estado"])

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

    styled = style_eca_dataframe(
        df_view, state_col="Estado", state_colors=_ESTADO_CELDA_COLORS
    )

    event = st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="tabla_campanas",
    )

    # ── Detalle de la campaña seleccionada ───────────────────────────────────
    sel_rows = getattr(event, "selection", {}).get("rows") if hasattr(event, "selection") else event.get("selection", {}).get("rows", [])
    if sel_rows:
        campana_id = campanas[sel_rows[0]]["id"]
        # La selección manual reemplaza cualquier detalle abierto por contexto
        st.session_state.pop("campanas_ctx_detalle", None)
    else:
        # Si otra página navegó aquí con campana_id, abrir su detalle directo
        campana_id = st.session_state.get("campanas_ctx_detalle")
        if not campana_id:
            st.info("Selecciona una campaña en la tabla para ver su detalle.")
            return

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

    if _estado == "anulada":
        st.error(
            ":material/cancel: **Campaña anulada.** Ya no participa del flujo de monitoreo. "
            "Sus datos se preservan para auditoría pero no se actualizarán."
        )
    elif _estado == "archivada":
        st.info(
            ":material/archive: **Campaña archivada.** Sus datos se preservan pero queda "
            "oculta del listado por defecto. Puedes restaurarla desde el panel inferior."
        )
    else:
        _idx_actual = _ciclo.index(_estado) if _estado in _ciclo else 0
        _timeline(
            [{"label": lbl, "sub": ""} for lbl in _labels_ciclo],
            current=_idx_actual,
        )

    rc1, rc2 = st.columns(2)
    rc1.markdown(f"**Responsable campo:** {camp.get('responsable_campo') or '—'}")
    rc2.markdown(f"**Responsable lab:** {camp.get('responsable_laboratorio') or '—'}")

    if camp.get("observaciones"):
        st.caption(f"Observaciones: {camp['observaciones']}")

    # ── Transición de estado y acciones ──────────────────────────────────────
    estado_actual = camp["estado"]

    bc1, bc2, bc3 = st.columns([3, 2, 2])

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
        if st.button(
            "Duplicar como nueva",
            key="btn_duplicar",
            icon=":material/content_copy:",
            help="Crea una nueva campaña pre-llenada con los datos de esta (puntos, parámetros, responsables).",
        ):
            _preparar_duplicado(camp, puntos, campana_id)
            toast(
                f"Borrador listo desde {camp['codigo']}. Ve a la pestaña «Nueva campaña».",
                tipo="info",
            )
            st.rerun()

    with bc3:
        if estado_actual not in ("completada", "anulada"):
            if st.button("Anular campaña", key="btn_anular", icon=":material/cancel:"):
                try:
                    actualizar_estado(campana_id, "anulada")
                    st.warning("Campaña anulada.")
                    st.rerun()
                except TransicionInvalidaError as exc:
                    st.error(str(exc))

    # ── Edición de campaña (admin) ───────────────────────────────────────────
    with st.expander(
        "Editar datos de la campaña",
        expanded=False,
        icon=":material/edit:",
    ):
        _render_editar_campana(campana_id, camp)

    # ── Puntos incluidos ─────────────────────────────────────────────────────
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

    # ── Etiquetas de frascos ────────────────────────────────────────────────
    with st.expander(
        "Generar etiquetas de frascos",
        expanded=False,
        icon=":material/label:",
    ):
        _render_etiquetas_frascos(campana_id, puntos)

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
            )
        with ec2:
            fecha_f = st.date_input(
                "Fecha fin",
                value=date.fromisoformat(camp["fecha_fin"][:10]) if camp.get("fecha_fin") else date.today(),
            )

        ec3, ec4 = st.columns(2)
        with ec3:
            freq_actual = (camp.get("frecuencia") or "mensual").lower()
            freq_idx = FRECUENCIAS.index(freq_actual) if freq_actual in FRECUENCIAS else 0
            frecuencia = st.selectbox(
                "Frecuencia",
                [f.capitalize() for f in FRECUENCIAS],
                index=freq_idx,
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
            )

        st.caption(
            f":material/science: **Responsable de laboratorio:** {_RESPONSABLE_LAB} "
            f"_(fijo para todas las campañas)_"
        )
        resp_lab_sel = _RESPONSABLE_LAB

        observaciones = st.text_area(
            "Observaciones",
            value=camp.get("observaciones") or "",
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
            if not set_parametros_lab_campana(
                campana_id,
                params_lab_sel,
                params_lab_extra,
                usuario_id=sesion.uid if sesion else None,
            ):
                st.warning(
                    "Los cambios de la campaña se guardaron, pero no se pudieron "
                    "registrar los parámetros de laboratorio. Reintenta esa parte.",
                    icon=":material/warning:",
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


_PROF_LABELS = {"S": "Superficie", "M": "Medio", "F": "Fondo"}

# Etiquetas cortas para las columnas de la matriz de ensayos (encabezados
# compactos). Cualquier ensayo no listado usa su nombre completo.
_ENSAYO_ABREV = {
    "Hierro y manganeso disuelto": "Fe/Mn",
    "Fitoplancton":                "Fitopl.",
    "Clorofila A":                 "Clorof. A",
    "Color":                       "Color",
    "Fisicoquímicos y nutrientes": "FQ + Nutr.",
    "DBO5":                        "DBO5",
    "Microcistina - LR":           "Microc. LR",
    "Zooplancton":                 "Zoopl.",
    "Perifiton":                   "Perif.",
    "DQO":                         "DQO",
    "Dureza":                      "Dureza",
}

# Profundidades donde un ensayo viene MARCADO por defecto. Los ensayos no
# listados se marcan en todas. Clave de profundidad: "S"/"M"/"F"
# (agua superficial cuenta como "S").
_DEFAULT_PROF_ENSAYO: dict[str, set[str]] = {
    "Microcistina - LR": {"S"},        # solo superficie
    "Fitoplancton":      {"S", "M"},   # superficie y medio
    "Clorofila A":       {"S", "M"},   # superficie y medio
    "DQO":               set(),        # desmarcado por defecto (se elige a voluntad)
}


def _marcado_default(ensayo: str, prof: str | None) -> bool:
    """¿El `ensayo` viene marcado por defecto en la profundidad `prof`?"""
    permitidas = _DEFAULT_PROF_ENSAYO.get(ensayo)
    if permitidas is None:
        return True
    return (prof or "S") in permitidas


def _matriz_ensayos_default(
    puntos: list[dict],
    tipo_muestreo: str,
    ensayos: list[str],
    seleccion_previa: dict[tuple, set] | None = None,
) -> tuple[pd.DataFrame, list[tuple]]:
    """
    Construye el DataFrame inicial de la matriz punto × ensayo y la metadata
    de filas (alineada por posición). Si hay `seleccion_previa` guardada para
    una fila (clave (punto_id, prof)), se usa esa; si no, se marca por defecto
    según la profundidad (ver `_DEFAULT_PROF_ENSAYO`).

    El perfil por columna (S/M/F) solo aplica a cuerpos lénticos
    (embalse/laguna, ver TIPOS_COLUMNA):
      • Superficial → una fila por punto (PROF. "Superficie").
      • Columna     → embalse/laguna: 3 filas (S/M/F); el resto: 1 fila
                      "Superficie".

    Devuelve (df, meta) donde meta[i] = (punto_id, prof|None) para la fila i.
    `prof=None` → agua superficial.
    """
    filas: list[dict] = []
    meta:  list[tuple] = []
    previa = seleccion_previa or {}

    def _fila(etiqueta: str, pid: str, prof: str | None, prof_label: str) -> dict:
        fila = {"Punto": etiqueta, "Prof.": prof_label}
        guardada = previa.get((pid, prof))
        for e in ensayos:
            if guardada is not None:
                fila[e] = e in guardada
            else:
                fila[e] = _marcado_default(e, prof)
        return fila

    for pt in puntos:
        etiqueta = f"{pt.get('codigo','')} — {pt.get('nombre','')}"
        pid = pt["id"]
        es_lentic = (pt.get("tipo") or "").lower() in TIPOS_COLUMNA

        if tipo_muestreo == MODO_COLUMNA and es_lentic:
            for prof in PROFUNDIDADES_COLUMNA:
                filas.append(_fila(etiqueta, pid, prof, _PROF_LABELS[prof]))
                meta.append((pid, prof))
        else:
            # Agua superficial (modo superficial, o punto no léntico en columna).
            filas.append(_fila(etiqueta, pid, None, _PROF_LABELS["S"]))
            meta.append((pid, None))

    return pd.DataFrame(filas), meta


def _matriz_set_columnas(
    base_key: str, widget_key: str, columnas: list[str], valor: bool
) -> None:
    """
    Callback de los botones "marcar/desmarcar": fija `valor` en las `columnas`
    indicadas del DataFrame base de la matriz y resetea el estado del editor
    (para que el nuevo base se muestre sin que las ediciones previas lo pisen).
    Corre como on_click, antes de instanciar el data_editor en el rerun.
    """
    df = st.session_state.get(base_key)
    if df is None:
        return
    df = df.copy()
    # Incorporar primero las ediciones manuales pendientes del editor, para no
    # perderlas al resetear el widget.
    estado = st.session_state.get(widget_key) or {}
    for ridx, cambios in (estado.get("edited_rows") or {}).items():
        for col, val in (cambios or {}).items():
            if col in df.columns:
                df.at[int(ridx), col] = val
    # Aplicar el cambio masivo (marca/desmarca columnas completas).
    for c in columnas:
        if c in df.columns:
            df[c] = valor
    st.session_state[base_key] = df
    st.session_state.pop(widget_key, None)


def _render_etiquetas_frascos(campana_id: str, puntos: list[dict]) -> None:
    """
    Generador del .docx con etiquetas pre-rellenas para los frascos de campo.
    Cada hoja contiene las etiquetas en una grilla 2×N (izquierda/derecha).

    El analista elige por punto —y por profundidad en modo columna— qué ensayos
    lleva cada estación, mediante una matriz de casillas (punto × ensayo).
    """
    if not puntos:
        st.caption("Vincula al menos un punto de muestreo para generar etiquetas.")
        return

    # El muestreo por columna (S/M/F) solo aplica a embalses/lagunas. Si la
    # campaña no tiene ninguno, solo se ofrece muestreo superficial.
    hay_lentic = any(
        (pt.get("tipo") or "").lower() in TIPOS_COLUMNA for pt in puntos
    )

    if hay_lentic:
        tipo_label = st.radio(
            "Tipo de muestreo en esta campaña",
            options=["Superficial", "Columna de agua"],
            horizontal=True,
            key=f"etiq_tipo_{campana_id}",
            help="Superficial: PROF=0.3 m, 1 hoja por punto. "
                 "Columna: en embalses/lagunas, 1 hoja por profundidad (S/M/F); "
                 "los demás puntos siempre van solo en superficie.",
        )
        tipo_muestreo = (
            MODO_SUPERFICIAL if tipo_label == "Superficial" else MODO_COLUMNA
        )
    else:
        tipo_muestreo = MODO_SUPERFICIAL
        st.caption(
            ":material/water_drop: Solo muestreo superficial "
            "(la campaña no tiene embalses ni lagunas)."
        )

    ensayos_disp = get_ensayos_disponibles()
    st.caption(
        ":material/info: Marca qué ensayos lleva cada punto y profundidad. "
        "Esta selección también define qué se marca en la **cadena de custodia**. "
        "Cada fila con al menos 1 ensayo genera una hoja (máx. 12 etiquetas)."
    )

    # Selección guardada previamente (compartida con la cadena de custodia).
    matriz_previa = get_matriz_ensayos(campana_id)
    prev_lookup: dict[tuple, set] = {}
    if matriz_previa:
        for fila in matriz_previa:
            prev_lookup[(fila.get("punto_id"), fila.get("prof"))] = set(
                fila.get("ensayos") or []
            )

    # DataFrame base ESTABLE: se construye una sola vez por (campaña, modo,
    # puntos, ensayos) y se cachea. Pasar siempre el MISMO objeto + un `key`
    # por modo evita el "rebote" de st.data_editor (que revivía casillas al
    # reconstruir el DataFrame en cada interacción). Las ediciones las gestiona
    # el propio widget vía su `key`; aquí no se reasigna el DataFrame cacheado.
    base_key   = f"etiq_matriz_df_{campana_id}_{tipo_muestreo}"
    meta_key   = base_key + "_meta"
    firma_key  = base_key + "_firma"
    widget_key = f"etiq_matriz_w_{campana_id}_{tipo_muestreo}"
    firma = tuple(p["id"] for p in puntos) + tuple(ensayos_disp)
    if st.session_state.get(firma_key) != firma:
        df0, meta0 = _matriz_ensayos_default(
            puntos, tipo_muestreo, ensayos_disp, seleccion_previa=prev_lookup
        )
        st.session_state[base_key] = df0
        st.session_state[meta_key] = meta0
        st.session_state[firma_key] = firma
    meta = st.session_state[meta_key]

    # ── Acciones rápidas: marcar/desmarcar toda la matriz o una columna ──────
    a1, a2, a3, a4, a5 = st.columns([1.1, 1.1, 1.8, 1, 1])
    a1.button(
        "Marcar todo", key=f"etiq_all_on_{campana_id}", use_container_width=True,
        icon=":material/select_check_box:",
        on_click=_matriz_set_columnas, args=(base_key, widget_key, ensayos_disp, True),
    )
    a2.button(
        "Desmarcar todo", key=f"etiq_all_off_{campana_id}", use_container_width=True,
        icon=":material/check_box_outline_blank:",
        on_click=_matriz_set_columnas, args=(base_key, widget_key, ensayos_disp, False),
    )
    ens_sel = a3.selectbox(
        "Columna (ensayo)", ensayos_disp, key=f"etiq_colsel_{campana_id}",
        label_visibility="collapsed",
    )
    a4.button(
        "Marcar col.", key=f"etiq_col_on_{campana_id}", use_container_width=True,
        on_click=_matriz_set_columnas, args=(base_key, widget_key, [ens_sel], True),
    )
    a5.button(
        "Desmarcar col.", key=f"etiq_col_off_{campana_id}", use_container_width=True,
        on_click=_matriz_set_columnas, args=(base_key, widget_key, [ens_sel], False),
    )

    col_cfg: dict = {
        "Punto": st.column_config.TextColumn("Punto", disabled=True, width="medium"),
        "Prof.": st.column_config.TextColumn("Prof.", disabled=True, width="small"),
    }
    for e in ensayos_disp:
        col_cfg[e] = st.column_config.CheckboxColumn(_ENSAYO_ABREV.get(e, e), help=e)

    edited = st.data_editor(
        st.session_state[base_key],
        column_config=col_cfg,
        hide_index=True,
        num_rows="fixed",
        use_container_width=True,
        key=widget_key,
    )

    # Filas completas de la matriz (incluye renglones sin marcar, para
    # persistir el estado exacto y que la cadena sepa qué NO se hace).
    filas_todas: list[dict] = []
    for i, (pid, prof) in enumerate(meta):
        marcados = [e for e in ensayos_disp if bool(edited.iloc[i][e])]
        filas_todas.append({"punto_id": pid, "prof": prof, "ensayos": marcados})

    # Solo los renglones con al menos 1 ensayo generan hoja.
    filas_seleccion = [f for f in filas_todas if f["ensayos"]]

    sesion = st.session_state.get("sesion")
    uid = sesion.uid if sesion else None

    sel_resp = st.multiselect(
        "Muestreado por",
        options=_RESPONSABLES_CAMPO,
        default=_RESPONSABLES_CAMPO[:2],
        key=f"etiq_resp_{campana_id}",
        max_selections=_MAX_RESP_CAMPO,
        help="Aparecerán en el campo «MUESTREADO POR» de cada etiqueta.",
    )

    n_hojas = len(filas_seleccion)
    n_etiq  = sum(len(f["ensayos"]) for f in filas_seleccion)

    if st.button(
        "Guardar selección para la cadena",
        key=f"btn_save_matriz_{campana_id}",
        icon=":material/save:",
        help="Guarda esta matriz en la campaña; la cadena de custodia marcará "
             "los parámetros según lo elegido aquí.",
    ):
        if guardar_matriz_ensayos(campana_id, filas_todas, usuario_id=uid):
            st.success("Selección guardada. La cadena de custodia la usará.")
        else:
            st.warning(
                "No se pudo guardar (¿migración 006 pendiente?). Las etiquetas "
                "igual se generan, pero la cadena no reflejará esta selección."
            )

    col_a, col_b = st.columns([1, 2])
    with col_a:
        if n_hojas == 0:
            st.button(
                "Generar etiquetas",
                key=f"btn_gen_etiq_{campana_id}",
                disabled=True,
                icon=":material/label:",
            )
            st.caption("Marca al menos un ensayo en algún punto.")
        else:
            try:
                with st.spinner("Generando documento..."):
                    # Auto-guardar la selección para mantener la cadena en sync.
                    guardar_matriz_ensayos(campana_id, filas_todas, usuario_id=uid)
                    docx_bytes = generar_etiquetas_campana(
                        campana_id=campana_id,
                        responsables=sel_resp,
                        filas_seleccion=filas_seleccion,
                    )
                st.download_button(
                    label="Descargar etiquetas (Word)",
                    data=docx_bytes,
                    file_name=f"etiquetas_{campana_id[:8]}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    key=f"btn_dl_etiq_{campana_id}",
                    icon=":material/label:",
                )
            except Exception as exc:
                st.error(f"No se pudo generar el documento: {exc}")
    with col_b:
        st.caption(
            f":material/description: **{n_hojas} hoja(s) · {n_etiq} etiqueta(s)** en total."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Formulario nueva campaña
# ─────────────────────────────────────────────────────────────────────────────

def _render_formulario_nueva() -> None:
    section_header("Nueva campaña de monitoreo", "plus")
    proximo_codigo = peek_siguiente_codigo()
    st.caption(
        f":material/badge: **Próximo código:** `{proximo_codigo}` _(se asigna al crear la campaña)._"
    )

    # Cargar puntos disponibles para el multiselect
    puntos = get_todos_los_puntos()
    opciones_puntos = {
        f"{p['codigo']} — {p['nombre']} ({p.get('tipo','')})": p["id"]
        for p in puntos
    }

    # ── Borrador desde "Duplicar campaña" ────────────────────────────────────
    borrador = st.session_state.get("duplicar_camp")
    borrador_codigo = (borrador or {}).get("origen_codigo")
    borrador_aplicado = st.session_state.get("duplicar_camp_aplicado")

    # Si entra un borrador nuevo, limpiar widget-state previo para que los
    # defaults del duplicado se apliquen (Streamlit ignora `default=` cuando
    # ya existe un valor en session_state).
    if borrador and borrador_codigo != borrador_aplicado:
        keys_a_limpiar = [
            "new_nombre", "new_frecuencia", "new_resp_campo",
            "new_puntos_sel", "new_obs", "new_plab_extras",
        ]
        for p in get_parametros_lab_cadena():
            keys_a_limpiar.append(f"new_plab_{p['clave']}")
        for k in keys_a_limpiar:
            st.session_state.pop(k, None)
        st.session_state["duplicar_camp_aplicado"] = borrador_codigo

    if borrador:
        bn1, bn2 = st.columns([4, 1])
        with bn1:
            st.info(
                f":material/content_copy: **Duplicando desde {borrador['origen_codigo']}** — "
                f"{borrador['origen_nombre']}. Ajusta nombre y fechas; el resto ya está pre-llenado."
            )
        with bn2:
            if st.button(
                "Descartar borrador",
                key="btn_descartar_dup",
                icon=":material/close:",
            ):
                st.session_state.pop("duplicar_camp", None)
                st.session_state.pop("duplicar_camp_aplicado", None)
                # Limpiar widgets pre-llenados
                for k in [
                    "new_nombre", "new_frecuencia", "new_resp_campo",
                    "new_puntos_sel", "new_obs", "new_plab_extras",
                ]:
                    st.session_state.pop(k, None)
                for p in get_parametros_lab_cadena():
                    st.session_state.pop(f"new_plab_{p['clave']}", None)
                st.rerun()

    # Defaults derivados del borrador (o defaults base)
    def_nombre   = f"{borrador['origen_nombre']} (copia)" if borrador else ""
    def_freq_idx = (
        FRECUENCIAS.index(borrador["frecuencia"])
        if borrador and borrador["frecuencia"] in FRECUENCIAS
        else 0
    )
    def_puntos_labels: list[str]
    if borrador:
        ids_borrador = set(borrador["puntos_ids"])
        def_puntos_labels = [
            label for label, pid in opciones_puntos.items() if pid in ids_borrador
        ]
    else:
        def_puntos_labels = list(opciones_puntos.keys())  # todos por defecto

    def_obs = borrador["observaciones"] if borrador else ""
    def_lab_sel = borrador["parametros_lab"] if borrador else None
    def_lab_extra = borrador["parametros_lab_extra"] if borrador else None
    def_resp_campo = borrador["responsable_campo"] if borrador else []

    # ── Atajos de selección de puntos por cuenca (fuera del form) ────────────
    cuencas_disponibles = sorted({_normalizar_cuenca(p.get("cuenca")) for p in puntos})
    labels_por_cuenca: dict[str, list[str]] = {c: [] for c in cuencas_disponibles}
    for p in puntos:
        cuenca = _normalizar_cuenca(p.get("cuenca"))
        label = f"{p['codigo']} — {p['nombre']} ({p.get('tipo', '')})"
        labels_por_cuenca[cuenca].append(label)

    with st.container(border=True):
        st.caption(
            ":material/place: **Atajo:** selección rápida de puntos por cuenca "
            "(luego puedes ajustar uno por uno en el formulario)."
        )
        n_cols = 2 + len(cuencas_disponibles)
        cols_atajo = st.columns(n_cols)

        if cols_atajo[0].button(
            f"Todos ({len(opciones_puntos)})",
            key="btn_pts_todos",
            icon=":material/select_all:",
            use_container_width=True,
        ):
            st.session_state["new_puntos_sel"] = list(opciones_puntos.keys())
            st.rerun()
        if cols_atajo[1].button(
            "Limpiar",
            key="btn_pts_clear",
            icon=":material/clear_all:",
            use_container_width=True,
        ):
            st.session_state["new_puntos_sel"] = []
            st.rerun()
        for i, cuenca in enumerate(cuencas_disponibles):
            if cols_atajo[i + 2].button(
                f"Solo {cuenca} ({len(labels_por_cuenca[cuenca])})",
                key=f"btn_pts_cuenca_{i}",
                icon=":material/water:",
                use_container_width=True,
            ):
                st.session_state["new_puntos_sel"] = list(labels_por_cuenca[cuenca])
                st.rerun()

    with st.form("form_nueva_campana", clear_on_submit=False):
        nombre = st.text_input(
            "Nombre de la campaña *",
            value=def_nombre,
            placeholder="Monitoreo mensual marzo 2025 — Cuenca Chili",
            key="new_nombre",
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
                index=def_freq_idx,
                key="new_frecuencia",
            )
        with fc4:
            responsable_campo_sel = st.multiselect(
                f"Responsable de campo (máx. {_MAX_RESP_CAMPO})",
                _opciones_responsables_campo(),
                default=def_resp_campo,
                max_selections=_MAX_RESP_CAMPO,
                key="new_resp_campo",
            )

        st.caption(
            f":material/science: **Responsable de laboratorio:** {_RESPONSABLE_LAB} "
            f"_(fijo para todas las campañas)_"
        )
        responsable_lab_sel = _RESPONSABLE_LAB

        n_pts_sel = len(st.session_state.get("new_puntos_sel", def_puntos_labels))
        puntos_sel = st.multiselect(
            f"Puntos de muestreo incluidos * ({n_pts_sel} de {len(opciones_puntos)})",
            list(opciones_puntos.keys()),
            default=def_puntos_labels,
            key="new_puntos_sel",
        )

        section_header("Parámetros de laboratorio a analizar", "beaker")
        params_lab_sel, params_lab_extra = _render_seleccion_parametros_lab(
            key_prefix="new",
            seleccionados_default=def_lab_sel,
            extras_default=def_lab_extra,
        )

        observaciones = st.text_area(
            "Observaciones",
            value=def_obs,
            placeholder="Notas sobre la campaña...",
            key="new_obs",
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
                if not set_parametros_lab_campana(
                    creada["id"],
                    params_lab_sel,
                    params_lab_extra,
                    usuario_id=usuario_id,
                ):
                    st.warning(
                        "La campaña se creó, pero no se pudieron registrar los "
                        "parámetros de laboratorio. Edítala para reintentar esa parte.",
                        icon=":material/warning:",
                    )
                success_check_overlay(
                    f"Campaña {creada['codigo']} creada"
                )
                st.success(
                    f"Campaña **{creada['codigo']}** creada con "
                    f"{len(puntos_ids)} punto(s) de muestreo y "
                    f"{len(params_lab_sel) + len(params_lab_extra)} parámetro(s) de laboratorio."
                )
                # Limpiar borrador de duplicado si lo había
                st.session_state.pop("duplicar_camp", None)
                st.session_state.pop("duplicar_camp_aplicado", None)
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

    # Contexto de navegación: otra página pidió abrir una campaña concreta
    ctx = consumir_contexto("campanas")
    if ctx.get("campana_id"):
        st.session_state["campanas_ctx_detalle"] = ctx["campana_id"]

    tab_lista, tab_nueva = st.tabs([
        ":material/list: Listado de campañas",
        ":material/add: Nueva campaña",
    ])

    with tab_lista:
        _render_listado()

    with tab_nueva:
        _render_formulario_nueva()


main()
