"""
pages/6_Puntos_Muestreo.py
Gestión de puntos de muestreo del programa de monitoreo.

Secciones:
    Tab 1 — Listado: filtro por cuenca/tipo, búsqueda, tabla y detalle
    Tab 2 — Nuevo punto: formulario de alta con coordenadas UTM/WGS84
    Tab 3 — Mapa de puntos: vista rápida con Folium

Acceso mínimo: administrador.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import aplicar_estilos, page_header, section_header, top_nav
from services.punto_service import (
    get_puntos,
    get_punto,
    crear_punto,
    actualizar_punto,
    toggle_punto,
    eliminar_punto,
    get_cuencas,
    get_tipos,
    TIPOS_PUNTO,
)
from services.parametro_service import get_ecas
from services.storage_service import upload_croquis, get_croquis_url


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Listado de puntos
# ─────────────────────────────────────────────────────────────────────────────

def _render_listado() -> None:
    section_header("Filtros", "filter")
    fc1, fc2, fc3, fc4 = st.columns(4)

    cuencas = get_cuencas()
    tipos = get_tipos()

    with fc1:
        opciones_cuenca = ["Todas"] + cuencas
        sel_cuenca = st.selectbox("Cuenca", opciones_cuenca, key="filtro_cuenca_pt")
        filtro_cuenca = sel_cuenca if sel_cuenca != "Todas" else None

    with fc2:
        opciones_tipo = ["Todos"] + tipos
        sel_tipo = st.selectbox("Tipo", opciones_tipo, key="filtro_tipo_pt")
        filtro_tipo = sel_tipo if sel_tipo != "Todos" else None

    with fc3:
        busqueda = st.text_input("Buscar", key="busqueda_pt")

    with fc4:
        solo_activos = st.checkbox("Solo activos", value=True, key="solo_activos_pt")

    # ── Consulta ─────────────────────────────────────────────────────────────
    puntos = get_puntos(
        filtro_cuenca=filtro_cuenca,
        filtro_tipo=filtro_tipo,
        busqueda=busqueda.strip() or None,
        solo_activos=solo_activos,
    )

    if not puntos:
        st.info("No se encontraron puntos con los filtros seleccionados.")
        return

    # ── Tabla resumen ────────────────────────────────────────────────────────
    st.markdown(f"#### {len(puntos)} punto(s) de muestreo")

    filas = []
    for p in puntos:
        eca = (p.get("ecas") or {}).get("codigo", "—")
        filas.append({
            "Código":    p["codigo"],
            "Nombre":    p["nombre"],
            "Tipo":      (p.get("tipo") or "—").capitalize(),
            "Cuenca":    p.get("cuenca") or "—",
            "Sistema Hídrico": p.get("sistema_hidrico") or p.get("subcuenca") or "—",
            "Altitud":   f"{p['altitud_msnm']:.0f} msnm" if p.get("altitud_msnm") else "—",
            "ECA":       eca,
            "Activo":    "Si" if p.get("activo") else "No",
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
        for p in puntos
    }
    sel_detalle = st.selectbox(
        "Editar punto",
        list(opciones_detalle.keys()),
        key="sel_detalle_pt",
    )
    punto_id = opciones_detalle[sel_detalle]
    _render_editar(punto_id)


def _render_editar(punto_id: str) -> None:
    """Formulario de edición de un punto existente."""
    punto = get_punto(punto_id)
    if not punto:
        st.error("Punto no encontrado.")
        return

    # Prefijo único por punto para evitar valores fantasma al cambiar de punto
    kp = punto_id[:8]

    ecas = get_ecas()
    eca_opciones = {"Sin ECA asignado": None}
    eca_opciones.update({f"{e['codigo']} — {e['nombre']}": e["id"] for e in ecas})
    eca_labels = list(eca_opciones.keys())
    eca_actual = (punto.get("ecas") or {}).get("codigo", "")
    eca_idx = 0
    for i, label in enumerate(eca_labels):
        if label.startswith(eca_actual + " "):
            eca_idx = i
            break

    tipo_idx = TIPOS_PUNTO.index(punto["tipo"]) if punto.get("tipo") in TIPOS_PUNTO else 0

    with st.form(f"form_editar_pt_{kp}", clear_on_submit=False):
        st.markdown(f"##### Editando: {punto['codigo']}")

        nombre = st.text_input("Nombre *", value=punto.get("nombre", ""), key=f"edit_nom_{kp}")
        descripcion = st.text_area(
            "Descripción",
            value=punto.get("descripcion") or "",
            height=100,
            key=f"edit_desc_{kp}",
        )

        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            tipo = st.selectbox(
                "Tipo",
                [t.capitalize() for t in TIPOS_PUNTO],
                index=tipo_idx,
                key=f"edit_tipo_{kp}",
            )
        with ec2:
            cuenca = st.text_input("Cuenca", value=punto.get("cuenca") or "", key=f"edit_cuenca_{kp}")
        with ec3:
            sistema_hidrico = st.text_input("Sistema Hídrico", value=punto.get("sistema_hidrico") or punto.get("subcuenca") or "", key=f"edit_sh_{kp}")

        section_header("Coordenadas", "map_pin")
        co1, co2, co3 = st.columns(3)
        with co1:
            utm_este = st.number_input(
                "UTM Este", value=punto.get("utm_este") or 0.0,
                format="%.1f", key=f"edit_utm_e_{kp}",
            )
        with co2:
            utm_norte = st.number_input(
                "UTM Norte", value=punto.get("utm_norte") or 0.0,
                format="%.1f", key=f"edit_utm_n_{kp}",
            )
        with co3:
            altitud = st.number_input(
                "Altitud (msnm)", value=punto.get("altitud_msnm") or 0.0,
                format="%.1f", key=f"edit_alt_{kp}",
            )

        co4, co5 = st.columns(2)
        with co4:
            latitud = st.number_input(
                "Latitud (WGS84)", value=punto.get("latitud") or 0.0,
                format="%.8f", key=f"edit_lat_{kp}",
            )
        with co5:
            longitud = st.number_input(
                "Longitud (WGS84)", value=punto.get("longitud") or 0.0,
                format="%.8f", key=f"edit_lon_{kp}",
            )

        sel_eca = st.selectbox("ECA asignado", eca_labels, index=eca_idx, key=f"edit_eca_{kp}")
        entidad = st.text_input(
            "Entidad responsable",
            value=punto.get("entidad_responsable") or "",
            key=f"edit_ent_{kp}",
        )

        section_header("Datos para ficha de campo", "file")
        ub1, ub2, ub3 = st.columns(3)
        with ub1:
            departamento = st.text_input(
                "Departamento", value=punto.get("departamento") or "AREQUIPA",
                key=f"edit_dpto_{kp}",
            )
        with ub2:
            provincia = st.text_input(
                "Provincia", value=punto.get("provincia") or "",
                key=f"edit_prov_{kp}",
            )
        with ub3:
            distrito = st.text_input(
                "Distrito", value=punto.get("distrito") or "",
                key=f"edit_dist_{kp}",
            )

        accesibilidad = st.text_area(
            "Accesibilidad",
            value=punto.get("accesibilidad") or "",
            height=80, key=f"edit_acces_{kp}",
            placeholder="Ej: A 15 km del desvío de la carretera Arequipa-Chivay...",
        )
        representatividad = st.text_area(
            "Representatividad",
            value=punto.get("representatividad") or "",
            height=80, key=f"edit_repre_{kp}",
            placeholder="Ej: Caracteriza la calidad del agua embalsada en...",
        )
        finalidad = st.text_area(
            "Finalidad",
            value=punto.get("finalidad") or "",
            height=80, key=f"edit_final_{kp}",
            placeholder="Ej: Monitoreo de vigilancia de calidad de agua.",
        )

        submitted = st.form_submit_button("Guardar cambios", type="primary")

    # ── Botón activar/desactivar ──────────────────────────────────────────
    bc1, bc2 = st.columns(2)
    with bc1:
        if punto.get("activo"):
            if st.button("Desactivar punto", key=f"btn_desact_{kp}"):
                toggle_punto(punto_id, False)
                st.warning("Punto desactivado.")
                st.rerun()
        else:
            if st.button("Activar punto", key=f"btn_act_{kp}", type="primary"):
                toggle_punto(punto_id, True)
                st.success("Punto activado.")
                st.rerun()

    # ── Eliminar punto ─────────────────────────────────────────────────────
    with bc2:
        if not punto.get("activo"):
            with st.expander("🗑️ Eliminar punto", expanded=False):
                st.warning("Solo se pueden eliminar puntos sin muestras asociadas.")
                if st.button("Eliminar permanentemente", key=f"btn_elim_{kp}", type="primary"):
                    try:
                        eliminar_punto(punto_id)
                        st.success("Punto eliminado.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

    if submitted:
        if not nombre.strip():
            st.error("El nombre es obligatorio.")
            return

        datos = {
            "nombre":               nombre.strip(),
            "descripcion":          descripcion.strip(),
            "tipo":                 tipo.lower(),
            "cuenca":               cuenca.strip(),
            "sistema_hidrico":      sistema_hidrico.strip() or None,
            "utm_este":             utm_este if utm_este != 0 else None,
            "utm_norte":            utm_norte if utm_norte != 0 else None,
            "utm_zona":             "19S",
            "latitud":              latitud if latitud != 0 else None,
            "longitud":             longitud if longitud != 0 else None,
            "altitud_msnm":         altitud if altitud != 0 else None,
            "eca_id":               eca_opciones[sel_eca],
            "entidad_responsable":  entidad.strip(),
            "departamento":         departamento.strip() or None,
            "provincia":            provincia.strip() or None,
            "distrito":             distrito.strip() or None,
            "accesibilidad":        accesibilidad.strip() or None,
            "representatividad":    representatividad.strip() or None,
            "finalidad":            finalidad.strip() or None,
        }
        try:
            actualizar_punto(punto_id, datos)
            st.success("Punto actualizado correctamente.")
            st.rerun()
        except Exception as exc:
            st.error(f"Error al actualizar: {exc}")

    # ── Croquis del punto ──────────────────────────────────────────────
    st.divider()
    section_header("Croquis del punto de monitoreo", "map")
    croquis_url = get_croquis_url(punto_id)
    if croquis_url:
        st.image(croquis_url, caption="Croquis actual", width=400)

    croquis_file = st.file_uploader(
        "Subir imagen de croquis",
        type=["jpg", "jpeg", "png"],
        key=f"croquis_{punto_id}",
    )
    if croquis_file:
        if st.button("Guardar croquis", key=f"btn_croquis_{punto_id}"):
            try:
                url = upload_croquis(punto_id, croquis_file.getvalue(), croquis_file.type)
                st.success("Croquis guardado correctamente.")
                st.rerun()
            except Exception as exc:
                st.error(f"Error al subir croquis: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Nuevo punto
# ─────────────────────────────────────────────────────────────────────────────

def _render_nuevo() -> None:
    # Mostrar mensaje de creación exitosa (persiste tras rerun)
    msg_key = "punto_creado_msg"
    if msg_key in st.session_state:
        st.success(st.session_state.pop(msg_key))

    section_header("Nuevo punto de muestreo", "plus")

    ecas = get_ecas()
    eca_opciones = {"Sin ECA asignado": None}
    eca_opciones.update({f"{e['codigo']} — {e['nombre']}": e["id"] for e in ecas})

    with st.form("form_nuevo_pt", clear_on_submit=True):
        nc1, nc2 = st.columns(2)
        with nc1:
            codigo = st.text_input(
                "Código *", placeholder="PM-13",
                help="Código único del punto (ej: PM-13)",
            )
        with nc2:
            nombre = st.text_input(
                "Nombre *", placeholder="Nombre descriptivo del punto",
            )

        descripcion = st.text_area(
            "Descripción",
            placeholder="Descripción de la ubicación y contexto del punto...",
            height=100,
        )

        nc3, nc4, nc5 = st.columns(3)
        with nc3:
            tipo = st.selectbox(
                "Tipo *",
                [t.capitalize() for t in TIPOS_PUNTO],
            )
        with nc4:
            cuenca = st.text_input("Cuenca *", placeholder="Chili")
        with nc5:
            n_sistema_hidrico = st.text_input("Sistema Hídrico", placeholder="Chili Regulado")

        section_header("Coordenadas", "map_pin")
        co1, co2, co3 = st.columns(3)
        with co1:
            utm_este = st.number_input("UTM Este", value=0.0, format="%.1f")
        with co2:
            utm_norte = st.number_input("UTM Norte", value=0.0, format="%.1f")
        with co3:
            altitud = st.number_input("Altitud (msnm)", value=0.0, format="%.1f")

        co4, co5 = st.columns(2)
        with co4:
            latitud = st.number_input("Latitud (WGS84)", value=0.0, format="%.8f")
        with co5:
            longitud = st.number_input("Longitud (WGS84)", value=0.0, format="%.8f")

        sel_eca = st.selectbox("ECA asignado", list(eca_opciones.keys()))
        entidad = st.text_input(
            "Entidad responsable",
            placeholder="AUTODEMA",
        )

        section_header("Datos para ficha de campo", "file")
        nu1, nu2, nu3 = st.columns(3)
        with nu1:
            n_departamento = st.text_input("Departamento", value="AREQUIPA", key="new_dpto")
        with nu2:
            n_provincia = st.text_input("Provincia", placeholder="CAYLLOMA", key="new_prov")
        with nu3:
            n_distrito = st.text_input("Distrito", placeholder="CALLALLI", key="new_dist")

        n_accesibilidad = st.text_area(
            "Accesibilidad",
            height=80, key="new_acces",
            placeholder="Ej: A 15 km del desvío de la carretera Arequipa-Chivay...",
        )
        n_representatividad = st.text_area(
            "Representatividad",
            height=80, key="new_repre",
            placeholder="Ej: Caracteriza la calidad del agua embalsada en...",
        )
        n_finalidad = st.text_area(
            "Finalidad",
            height=80, key="new_finalidad",
            placeholder="Ej: Monitoreo de vigilancia de calidad de agua.",
        )

        submitted = st.form_submit_button(
            "Crear punto", type="primary", use_container_width=True,
        )

    if submitted:
        errores = []
        if not codigo.strip():
            errores.append("El código es obligatorio.")
        if not nombre.strip():
            errores.append("El nombre es obligatorio.")
        if not cuenca.strip():
            errores.append("La cuenca es obligatoria.")
        if errores:
            for e in errores:
                st.error(e)
            return

        datos = {
            "codigo":               codigo.strip().upper(),
            "nombre":               nombre.strip(),
            "descripcion":          descripcion.strip() or None,
            "tipo":                 tipo.lower(),
            "cuenca":               cuenca.strip(),
            "sistema_hidrico":      n_sistema_hidrico.strip() or None,
            "utm_este":             utm_este if utm_este != 0 else None,
            "utm_norte":            utm_norte if utm_norte != 0 else None,
            "utm_zona":             "19S",
            "latitud":              latitud if latitud != 0 else None,
            "longitud":             longitud if longitud != 0 else None,
            "altitud_msnm":         altitud if altitud != 0 else None,
            "eca_id":               eca_opciones[sel_eca],
            "entidad_responsable":  entidad.strip() or None,
            "departamento":         n_departamento.strip() or None,
            "provincia":            n_provincia.strip() or None,
            "distrito":             n_distrito.strip() or None,
            "accesibilidad":        n_accesibilidad.strip() or None,
            "representatividad":    n_representatividad.strip() or None,
            "finalidad":            n_finalidad.strip() or None,
            "activo":               True,
        }
        try:
            creado = crear_punto(datos)
            st.session_state["punto_creado_msg"] = (
                f"Punto **{creado['codigo']}** creado exitosamente."
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Error al crear el punto: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Mapa de puntos
# ─────────────────────────────────────────────────────────────────────────────

def _render_mapa() -> None:
    section_header("Ubicación de puntos de muestreo", "map_pin")

    puntos = get_puntos(solo_activos=True)
    puntos_con_coords = [
        p for p in puntos
        if p.get("latitud") and p.get("longitud")
    ]

    if not puntos_con_coords:
        st.info("No hay puntos con coordenadas definidas.")
        return

    try:
        import folium
        from streamlit_folium import st_folium
    except ImportError:
        st.warning("Instala folium y streamlit-folium para ver el mapa.")
        return

    # Centrar en el promedio de coordenadas
    lat_center = sum(p["latitud"] for p in puntos_con_coords) / len(puntos_con_coords)
    lon_center = sum(p["longitud"] for p in puntos_con_coords) / len(puntos_con_coords)

    m = folium.Map(location=[lat_center, lon_center], zoom_start=9)

    colores_tipo = {
        "laguna":    "blue",
        "rio":       "green",
        "canal":     "orange",
        "manantial": "purple",
        "embalse":   "darkblue",
        "pozo":      "cadetblue",
    }

    for p in puntos_con_coords:
        color = colores_tipo.get(p.get("tipo", ""), "gray")
        eca_cod = (p.get("ecas") or {}).get("codigo", "Sin ECA")
        popup_html = (
            f"<b>{p['codigo']}</b><br>"
            f"{p['nombre']}<br>"
            f"Tipo: {(p.get('tipo') or '—').capitalize()}<br>"
            f"Cuenca: {p.get('cuenca', '—')}<br>"
            f"Altitud: {p.get('altitud_msnm', '—')} msnm<br>"
            f"ECA: {eca_cod}"
        )
        folium.Marker(
            location=[p["latitud"], p["longitud"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{p['codigo']} — {p['nombre']}",
            icon=folium.Icon(color=color, icon="tint", prefix="fa"),
        ).add_to(m)

    st_folium(m, use_container_width=True, height=500)

    # Leyenda
    st.caption(
        "Colores: "
        "Azul = Laguna/Embalse | "
        "Verde = Río | "
        "Naranja = Canal | "
        "Morado = Manantial"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("administrador")
def main() -> None:
    aplicar_estilos()
    top_nav()
    page_header(
        "Puntos de Muestreo",
        "Gestión de puntos de monitoreo",
        ambito="Cuenca Chili-Quilca",
    )

    tab_lista, tab_nuevo, tab_mapa = st.tabs([
        "Listado de puntos",
        "Nuevo punto",
        "Mapa",
    ])

    with tab_lista:
        _render_listado()

    with tab_nuevo:
        _render_nuevo()

    with tab_mapa:
        _render_mapa()


main()
