"""
pages/5_Parametros.py
Gestión de parámetros de calidad de agua y valores ECA.

Secciones:
    Tab 1 — Listado: filtro por categoría, búsqueda, tabla con detalle expandible
    Tab 2 — Nuevo parámetro: formulario de alta (incluye preservante y tipo de frasco)
    Tab 3 — Valores ECA: edición de límites por norma

Acceso mínimo: administrador.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import aplicar_estilos, page_header
from services.parametro_service import (
    get_parametros,
    get_parametro,
    crear_parametro,
    actualizar_parametro,
    toggle_parametro,
    eliminar_parametro,
    get_categorias,
    get_unidades,
    crear_unidad,
    get_ecas,
    get_valores_eca,
    guardar_valor_eca,
    eliminar_valor_eca,
)
from services.parametro_registry import (
    PRESERVANTES_OPCIONES,
    TIPOS_FRASCO_OPCIONES,
    get_param_config,
    set_param_config,
    invalidar_cache_parametros,
)

# ─── Orden fijo de categorías ────────────────────────────────────────────────
_CATEGORIAS_ORDEN = [
    "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)",
    "Parámetros Hidrobiológicos",
    "Parámetros de Campo",
]


# ─────────────────────────────────────────────────────────────────────────────
# Helper: selector de unidad con fallback de texto libre
# ─────────────────────────────────────────────────────────────────────────────

def _selector_unidad(
    unidades: list[dict],
    default_simbolo: str = "",
    key_suffix: str = "",
) -> str | None:
    """
    Dropdown de unidades existentes + opción "Otra (escribir)" que muestra
    un text_input para crear una unidad nueva.  Retorna el unidad_id.
    """
    uni_opciones = {f"{u['simbolo']} — {u['nombre']}": u["id"] for u in unidades}
    labels = list(uni_opciones.keys()) + ["— Otra (escribir) —"]

    # Detectar índice del valor actual
    idx = 0
    for i, label in enumerate(labels[:-1]):
        if label.startswith(default_simbolo + " "):
            idx = i
            break

    sel = st.selectbox(
        "Unidad *",
        labels,
        index=idx,
        key=f"sel_uni_{key_suffix}",
    )

    if sel == "— Otra (escribir) —":
        c1, c2 = st.columns(2)
        with c1:
            nuevo_sim = st.text_input(
                "Símbolo de la nueva unidad",
                key=f"nueva_uni_sim_{key_suffix}",
                placeholder="ej: mg/L",
            )
        with c2:
            nuevo_nom = st.text_input(
                "Nombre completo",
                key=f"nueva_uni_nom_{key_suffix}",
                placeholder="ej: Miligramos por litro",
            )
        if nuevo_sim.strip() and nuevo_nom.strip():
            # Verificar si ya existe
            for u in unidades:
                if u["simbolo"].lower() == nuevo_sim.strip().lower():
                    return u["id"]
            # Crear nueva unidad
            try:
                nueva = crear_unidad(nuevo_sim.strip(), nuevo_nom.strip())
                st.caption(f"Nueva unidad registrada: **{nueva['simbolo']}**")
                return nueva["id"]
            except Exception as exc:
                st.error(f"Error al crear unidad: {exc}")
                return None
        else:
            st.caption("Completa símbolo y nombre para crear la nueva unidad.")
            return None

    return uni_opciones[sel]


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Listado de parámetros
# ─────────────────────────────────────────────────────────────────────────────

def _render_listado() -> None:
    st.markdown("#### Filtros")
    fc1, fc2, fc3 = st.columns(3)

    categorias = get_categorias()
    # Filtrar a las 3 categorías válidas y ordenar
    categorias = [c for c in categorias if c["nombre"] in _CATEGORIAS_ORDEN]
    categorias.sort(key=lambda c: _CATEGORIAS_ORDEN.index(c["nombre"]))
    opciones_cat = {"Todas": None}
    opciones_cat.update({c["nombre"]: c["id"] for c in categorias})

    with fc1:
        sel_cat = st.selectbox(
            "Categoría", list(opciones_cat.keys()), key="filtro_cat_param"
        )
        filtro_cat = opciones_cat[sel_cat]

    with fc2:
        busqueda = st.text_input(
            "Buscar (código o nombre)", key="busqueda_param"
        )

    with fc3:
        solo_activos = st.checkbox("Solo activos", value=True, key="solo_activos_param")

    # ── Consulta ────────────────────────────────────────────────────────────
    parametros = get_parametros(
        filtro_categoria=filtro_cat,
        busqueda=busqueda.strip() or None,
        solo_activos=solo_activos,
    )

    if not parametros:
        st.info("No se encontraron parámetros con los filtros seleccionados.")
        return

    # ── Tabla resumen ───────────────────────────────────────────────────────
    st.markdown(f"#### {len(parametros)} parámetro(s)")

    filas = []
    for p in parametros:
        cat = (p.get("categorias_parametro") or {}).get("nombre", "—")
        uni = (p.get("unidades_medida") or {}).get("simbolo", "—")
        cfg = get_param_config(p.get("codigo", ""))
        filas.append({
            "Código":       p["codigo"],
            "Nombre":       p["nombre"],
            "Categoría":    cat,
            "Unidad":       uni,
            "Preservante":  cfg.get("preservante", "—"),
            "Tipo frasco":  cfg.get("tipo_frasco", "—") or "—",
            "Método":       p.get("metodo_analitico") or "—",
            "Activo":       "Sí" if p.get("activo") else "No",
        })

    st.dataframe(
        pd.DataFrame(filas),
        use_container_width=True,
        hide_index=True,
    )

    # ── Selector de detalle / edición ────────────────────────────────────────
    st.divider()
    opciones_detalle = {
        f"{p['codigo']} — {p['nombre']}": p["id"]
        for p in parametros
    }
    sel_detalle = st.selectbox(
        "Editar parámetro",
        list(opciones_detalle.keys()),
        key="sel_detalle_param",
    )
    parametro_id = opciones_detalle[sel_detalle]
    _render_editar(parametro_id)


def _render_editar(parametro_id: str) -> None:
    """Formulario de edición de un parámetro existente."""
    param = get_parametro(parametro_id)
    if not param:
        st.error("Parámetro no encontrado.")
        return

    codigo = param.get("codigo", "")
    categorias = get_categorias()
    categorias = [c for c in categorias if c["nombre"] in _CATEGORIAS_ORDEN]
    categorias.sort(key=lambda c: _CATEGORIAS_ORDEN.index(c["nombre"]))
    unidades = get_unidades()

    cat_opciones = {c["nombre"]: c["id"] for c in categorias}
    cat_nombres = list(cat_opciones.keys())
    cat_actual = (param.get("categorias_parametro") or {}).get("nombre", "")
    cat_idx = cat_nombres.index(cat_actual) if cat_actual in cat_nombres else 0

    uni_actual = (param.get("unidades_medida") or {}).get("simbolo", "")

    # Configuración preservante/tipo_frasco
    cfg = get_param_config(codigo)

    with st.form("form_editar_param", clear_on_submit=False):
        st.markdown(f"##### Editando: {param['codigo']}")

        nombre = st.text_input("Nombre *", value=param.get("nombre", ""))
        descripcion = st.text_input(
            "Nombre corto / descripción",
            value=param.get("descripcion") or "",
        )

        ec1, ec2 = st.columns(2)
        with ec1:
            sel_cat_edit = st.selectbox("Categoría", cat_nombres, index=cat_idx)
        with ec2:
            # Unidad dentro del form (sin free-text por limitaciones del form)
            uni_opciones = {f"{u['simbolo']} — {u['nombre']}": u["id"] for u in unidades}
            uni_labels = list(uni_opciones.keys())
            uni_idx = 0
            for i, label in enumerate(uni_labels):
                if label.startswith(uni_actual + " "):
                    uni_idx = i
                    break
            sel_uni_edit = st.selectbox("Unidad", uni_labels, index=uni_idx)

        metodo = st.text_input(
            "Método analítico",
            value=param.get("metodo_analitico") or "",
        )

        # Preservante y tipo de frasco
        pc1, pc2 = st.columns(2)
        with pc1:
            pres_opciones = list(PRESERVANTES_OPCIONES)
            pres_actual = cfg.get("preservante", "Ninguno")
            if pres_actual not in pres_opciones:
                pres_opciones.append(pres_actual)
            pres_idx = pres_opciones.index(pres_actual) if pres_actual in pres_opciones else 0
            sel_preservante = st.selectbox("Preservante", pres_opciones, index=pres_idx)
        with pc2:
            frasco_opciones = list(TIPOS_FRASCO_OPCIONES)
            frasco_actual = cfg.get("tipo_frasco", "")
            if frasco_actual and frasco_actual not in frasco_opciones:
                frasco_opciones.append(frasco_actual)
            frasco_idx = frasco_opciones.index(frasco_actual) if frasco_actual in frasco_opciones else 0
            sel_frasco = st.selectbox("Tipo de frasco", frasco_opciones, index=frasco_idx)

        submitted = st.form_submit_button("Guardar cambios", type="primary")

    # ── Botón activar/desactivar (fuera del form) ─────────────────────────
    bc1, bc2 = st.columns(2)
    with bc1:
        if param.get("activo"):
            if st.button("Desactivar parámetro", key="btn_desactivar_param"):
                toggle_parametro(parametro_id, False)
                st.warning("Parámetro desactivado.")
                st.rerun()
        else:
            if st.button("Activar parámetro", key="btn_activar_param", type="primary"):
                toggle_parametro(parametro_id, True)
                st.success("Parámetro activado.")
                st.rerun()

    # ── Eliminar parámetro ───────────────────────────────────────────────
    with bc2:
        with st.expander("🗑️ Eliminar parámetro", expanded=False):
            st.warning(
                "Si el parámetro tiene resultados de laboratorio vinculados, "
                "se marcará como inactivo en lugar de eliminarse."
            )
            if st.button("Eliminar parámetro", key="btn_eliminar_param", type="primary"):
                try:
                    resultado = eliminar_parametro(parametro_id)
                    if resultado == "desactivado":
                        st.warning(
                            "El parámetro tiene resultados vinculados. "
                            "Se marcó como **inactivo** (no eliminado)."
                        )
                    else:
                        st.success("Parámetro eliminado permanentemente.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if submitted:
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
            return

        datos = {
            "nombre":           nombre.strip(),
            "descripcion":      descripcion.strip(),
            "categoria_id":     cat_opciones[sel_cat_edit],
            "unidad_id":        uni_opciones[sel_uni_edit],
            "metodo_analitico": metodo.strip(),
        }
        try:
            actualizar_parametro(parametro_id, datos)
            set_param_config(codigo, sel_preservante, sel_frasco)
            st.success("Parámetro actualizado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"Error al actualizar: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Nuevo parámetro
# ─────────────────────────────────────────────────────────────────────────────

def _render_nuevo() -> None:
    st.markdown("#### Nuevo parámetro de calidad de agua")

    categorias = get_categorias()
    categorias = [c for c in categorias if c["nombre"] in _CATEGORIAS_ORDEN]
    categorias.sort(key=lambda c: _CATEGORIAS_ORDEN.index(c["nombre"]))
    unidades = get_unidades()

    cat_opciones = {c["nombre"]: c["id"] for c in categorias}

    # ── Campos fuera del form (para el selector de unidad con free-text) ──
    st.markdown("##### Datos básicos")

    nc1, nc2 = st.columns(2)
    with nc1:
        codigo = st.text_input(
            "Código *", placeholder="P155",
            help="Código único del parámetro (ej: P155)",
            key="nuevo_param_codigo",
        )
    with nc2:
        nombre = st.text_input(
            "Nombre *", placeholder="Nombre completo del parámetro",
            key="nuevo_param_nombre",
        )

    descripcion = st.text_input(
        "Nombre corto / descripción",
        placeholder="Abreviatura o nombre corto",
        key="nuevo_param_desc",
    )

    nc3, nc4 = st.columns(2)
    with nc3:
        sel_cat = st.selectbox(
            "Categoría *",
            list(cat_opciones.keys()),
            key="nuevo_param_cat",
        )
    with nc4:
        unidad_id = _selector_unidad(unidades, key_suffix="nuevo")

    metodo = st.text_input(
        "Método analítico",
        placeholder="Ej: SM 4500-H+ B electrométrico",
        key="nuevo_param_metodo",
    )

    # ── Preservante y tipo de frasco ─────────────────────────────────────
    st.markdown("##### Preservación y envase")
    pc1, pc2 = st.columns(2)
    with pc1:
        sel_preservante = st.selectbox(
            "Preservante",
            PRESERVANTES_OPCIONES,
            index=2,  # "Ninguno" por defecto
            key="nuevo_param_preservante",
        )
    with pc2:
        sel_frasco = st.selectbox(
            "Tipo de frasco",
            TIPOS_FRASCO_OPCIONES,
            key="nuevo_param_frasco",
        )

    st.divider()
    submitted = st.button(
        "Crear parámetro", type="primary", use_container_width=True,
        key="btn_crear_param",
    )

    if submitted:
        errores = []
        if not codigo.strip():
            errores.append("El código es obligatorio.")
        if not nombre.strip():
            errores.append("El nombre es obligatorio.")
        if not unidad_id:
            errores.append("Selecciona o crea una unidad de medida.")
        if errores:
            for e in errores:
                st.error(e)
            return

        datos = {
            "codigo":           codigo.strip().upper(),
            "nombre":           nombre.strip(),
            "descripcion":      descripcion.strip() or None,
            "categoria_id":     cat_opciones[sel_cat],
            "unidad_id":        unidad_id,
            "metodo_analitico": metodo.strip() or None,
        }
        try:
            creado = crear_parametro(datos)
            # Guardar config de preservante/tipo_frasco
            set_param_config(
                creado["codigo"],
                sel_preservante,
                sel_frasco,
            )
            st.success(f"Parámetro **{creado['codigo']}** creado exitosamente.")
            st.balloons()
        except Exception as exc:
            st.error(f"Error al crear el parámetro: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Valores ECA
# ─────────────────────────────────────────────────────────────────────────────

def _render_valores_eca() -> None:
    st.markdown("#### Límites ECA por parámetro")
    st.caption("D.S. N° 004-2017-MINAM — Estándares de Calidad Ambiental para Agua")

    ecas = get_ecas()
    if not ecas:
        st.warning("No hay ECAs registrados.")
        return

    eca_opciones = {f"{e['codigo']} — {e['nombre']}": e["id"] for e in ecas}
    sel_eca = st.selectbox(
        "Seleccionar ECA",
        list(eca_opciones.keys()),
        key="sel_eca_valores",
    )
    eca_id = eca_opciones[sel_eca]

    eca_sel = next((e for e in ecas if e["id"] == eca_id), {})
    if eca_sel.get("descripcion"):
        st.caption(eca_sel["descripcion"])

    # ── Tabla de valores existentes ───────────────────────────────────────────
    valores = get_valores_eca(eca_id)

    if valores:
        st.markdown(f"**{len(valores)}** parámetro(s) con límite definido")

        filas_eca = []
        for v in valores:
            filas_eca.append({
                "Parámetro":  v["parametro_nombre"],
                "Unidad":     v["unidad"],
                "Lím. mín.":  v["valor_minimo"] if v["valor_minimo"] is not None else "—",
                "Lím. máx.":  v["valor_maximo"] if v["valor_maximo"] is not None else "—",
            })

        st.dataframe(
            pd.DataFrame(filas_eca),
            use_container_width=True,
            hide_index=True,
        )

        # ── Editar/eliminar un valor existente ────────────────────────────────
        st.divider()
        st.markdown("##### Editar valor existente")

        val_opciones = {
            f"{v['parametro_codigo']} — {v['parametro_nombre']}": v
            for v in valores
        }
        sel_val = st.selectbox(
            "Seleccionar parámetro",
            list(val_opciones.keys()),
            key="sel_val_editar",
        )
        val_sel = val_opciones[sel_val]

        with st.form("form_editar_eca_val", clear_on_submit=False):
            ve1, ve2 = st.columns(2)
            with ve1:
                nuevo_min = st.number_input(
                    "Valor mínimo",
                    value=val_sel["valor_minimo"] if val_sel["valor_minimo"] is not None else 0.0,
                    format="%.6f",
                    key="edit_eca_min",
                    help="Dejar en 0 si no aplica límite mínimo",
                )
            with ve2:
                nuevo_max = st.number_input(
                    "Valor máximo",
                    value=val_sel["valor_maximo"] if val_sel["valor_maximo"] is not None else 0.0,
                    format="%.6f",
                    key="edit_eca_max",
                    help="Dejar en 0 si no aplica límite máximo",
                )

            ec1, ec2 = st.columns(2)
            with ec1:
                btn_guardar = st.form_submit_button("Guardar cambios", type="primary")
            with ec2:
                btn_eliminar = st.form_submit_button("Eliminar límite")

        if btn_guardar:
            guardar_valor_eca(
                eca_id,
                val_sel["parametro_id"],
                nuevo_min if nuevo_min != 0 else None,
                nuevo_max if nuevo_max != 0 else None,
            )
            st.success("Valor ECA actualizado.")
            st.rerun()

        if btn_eliminar:
            eliminar_valor_eca(val_sel["id"])
            st.warning("Límite eliminado.")
            st.rerun()

    else:
        st.info("Este ECA aún no tiene valores límite definidos.")

    # ── Agregar nuevo valor ──────────────────────────────────────────────────
    st.divider()
    st.markdown("##### Agregar nuevo límite")

    from services.parametro_service import get_parametros as _get_params
    all_params = _get_params(solo_activos=True)

    ids_con_valor = {v["parametro_id"] for v in valores}
    params_sin_valor = [p for p in all_params if p["id"] not in ids_con_valor]

    if not params_sin_valor:
        st.caption("Todos los parámetros activos ya tienen límite en este ECA.")
        return

    param_opciones = {
        f"{p['codigo']} — {p['nombre']}": p["id"]
        for p in params_sin_valor
    }

    with st.form("form_nuevo_eca_val", clear_on_submit=True):
        sel_param = st.selectbox(
            "Parámetro",
            list(param_opciones.keys()),
            key="sel_param_nuevo_eca",
        )

        vn1, vn2 = st.columns(2)
        with vn1:
            val_min = st.number_input(
                "Valor mínimo", value=0.0, format="%.6f", key="nuevo_eca_min",
                help="Dejar en 0 si no aplica",
            )
        with vn2:
            val_max = st.number_input(
                "Valor máximo", value=0.0, format="%.6f", key="nuevo_eca_max",
                help="Dejar en 0 si no aplica",
            )

        submitted = st.form_submit_button(
            "Agregar límite", type="primary", use_container_width=True,
        )

    if submitted:
        if val_min == 0 and val_max == 0:
            st.error("Debes definir al menos un valor (mínimo o máximo).")
            return

        guardar_valor_eca(
            eca_id,
            param_opciones[sel_param],
            val_min if val_min != 0 else None,
            val_max if val_max != 0 else None,
        )
        st.success("Nuevo límite ECA agregado.")
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("administrador")
def main() -> None:
    aplicar_estilos()
    page_header("Parametros y ECAs", "Gestion de parametros de calidad de agua y estandares ambientales")

    tab_lista, tab_nuevo, tab_eca = st.tabs([
        "Listado de parámetros",
        "Nuevo parámetro",
        "Valores ECA",
    ])

    with tab_lista:
        _render_listado()

    with tab_nuevo:
        _render_nuevo()

    with tab_eca:
        _render_valores_eca()


main()
