"""
pages/10_Base_Datos.py
Base de Datos consolidada de resultados de monitoreo.

Tabla tipo hoja de cálculo con todos los resultados pivotados por parámetro.
- Filtros por campaña, punto, fecha
- Celdas coloreadas en rojo si el valor excede su ECA respectivo
- Edición directa para administradores
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from services.base_datos_service import (
    actualizar_resultado,
    crear_resultado,
    get_datos_consolidados,
    get_limites_eca_todos,
    get_parametros_map,
)
from services.parametro_registry import (
    get_columnas_parametros,
    get_codigos_parametros,
    get_cat_params,
)
from components.ui_styles import aplicar_estilos, page_header
from services.resultado_service import get_campanas
from services.punto_service import get_puntos


def _es_admin() -> bool:
    """Verifica si el usuario actual tiene rol de administrador."""
    sesion = st.session_state.get("sesion")
    if not sesion:
        return False
    return getattr(sesion, "rol", None) == "administrador"


def _excede_eca(valor, eca_id: str | None, param_codigo: str, limites: dict) -> bool:
    """Retorna True si el valor excede el ECA del punto."""
    if valor is None or eca_id is None:
        return False
    lim = limites.get((eca_id, param_codigo))
    if not lim:
        return False
    vmax = lim.get("valor_maximo")
    vmin = lim.get("valor_minimo")
    if vmax is not None and valor > vmax:
        return True
    if vmin is not None and valor < vmin:
        return True
    return False


def _colorear_celda(val, eca_id, param_codigo, limites):
    """Retorna estilo CSS si excede ECA."""
    if val is None or pd.isna(val):
        return ""
    try:
        v = float(val)
    except (ValueError, TypeError):
        return ""
    if _excede_eca(v, eca_id, param_codigo, limites):
        return "background-color: #ffe0e0; color: #dc3545; font-weight: bold;"
    return ""


@require_rol("visitante")
def main() -> None:
    aplicar_estilos()
    page_header(
        "Base de Datos",
        "Consolidado de datos de campo, fisicoquimicos e hidrobiologicos por campana",
    )

    es_admin = _es_admin()

    # ── Sidebar: filtros ────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("Filtros")

        # Campaña
        campanas = get_campanas()
        opciones_camp = {"Todas las campañas": None}
        opciones_camp.update({
            f"{c['codigo']} — {c['nombre']}": c["id"] for c in campanas
        })
        sel_camp = st.selectbox("Campaña", list(opciones_camp.keys()), key="bd_camp")
        campana_id = opciones_camp[sel_camp]

        # Punto
        puntos = get_puntos(solo_activos=True)
        opciones_punto = {"Todos los puntos": None}
        opciones_punto.update({
            f"{p['codigo']} — {p['nombre']}": p["id"] for p in puntos
        })
        sel_punto = st.selectbox("Punto de muestreo", list(opciones_punto.keys()), key="bd_punto")
        punto_id = opciones_punto[sel_punto]

        # Fechas — por defecto: ultimos 12 meses corridos
        st.markdown("**Rango de fechas**")
        _hoy = date.today()
        _default_desde = _hoy.replace(year=_hoy.year - 1)
        fecha_inicio = st.date_input("Desde", value=_default_desde, key="bd_desde")
        fecha_fin = st.date_input("Hasta", value=_hoy, key="bd_hasta")

        st.divider()

        # Opciones de vista
        st.subheader("Opciones")
        mostrar_vacios = st.checkbox("Mostrar celdas vacías", value=True, key="bd_vacios")
        _categorias_disponibles = list(get_cat_params().keys())
        categoria_filtro = st.multiselect(
            "Categorías",
            _categorias_disponibles,
            default=_categorias_disponibles,
            key="bd_categorias",
        )

    # ── Cargar datos ────────────────────────────────────────────────────
    with st.spinner("Cargando base de datos..."):
        datos = get_datos_consolidados(
            campana_id=campana_id,
            punto_id=punto_id,
            fecha_inicio=str(fecha_inicio) if fecha_inicio else None,
            fecha_fin=str(fecha_fin) if fecha_fin else None,
        )
        limites = get_limites_eca_todos()

    if not datos:
        st.info("No se encontraron resultados con los filtros seleccionados.")
        st.stop()

    # ── Filtrar columnas por categoría (dinámico desde BD) ──────────────
    cat_params = get_cat_params()
    COLUMNAS_PARAMETROS = get_columnas_parametros()

    codigos_visibles = []
    for cat in categoria_filtro:
        codigos_visibles.extend(cat_params.get(cat, []))

    columnas_visibles = [(cod, label) for cod, label in COLUMNAS_PARAMETROS if cod in codigos_visibles]

    # ── Métricas rápidas ────────────────────────────────────────────────
    n_muestras = len(datos)
    n_puntos = len({d["punto_codigo"] for d in datos})
    n_valores = sum(1 for d in datos for cod in codigos_visibles if d.get(cod) is not None)
    n_excedencias = sum(
        1 for d in datos
        for cod in codigos_visibles
        if d.get(cod) is not None and _excede_eca(d[cod], d.get("eca_id"), cod, limites)
    )

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Muestras", n_muestras)
    mc2.metric("Puntos", n_puntos)
    mc3.metric("Valores registrados", n_valores)
    mc4.metric("Excedencias ECA", n_excedencias,
               delta=f"-{round(n_excedencias/n_valores*100, 1)}%" if n_valores else "0%",
               delta_color="inverse")

    # ── Construir DataFrame para mostrar ────────────────────────────────
    cols_fijas = ["fecha", "punto_codigo", "punto_nombre", "cuenca", "tipo", "eca_codigo"]
    cols_param = [cod for cod, _ in columnas_visibles]

    df_rows = []
    for d in datos:
        row = {
            "Fecha": d["fecha"],
            "Hora": d.get("hora", ""),
            "Código Punto": d["punto_codigo"],
            "Punto": d["punto_nombre"],
            "Código Muestra": d.get("codigo_muestra", ""),
            "Código Lab.": d.get("codigo_laboratorio", ""),
            "Cuenca": d["cuenca"],
            "Tipo": (d["tipo"] or "").capitalize(),
            "ECA": d["eca_codigo"],
        }
        for cod, label in columnas_visibles:
            row[label] = d.get(cod)
        df_rows.append(row)

    df = pd.DataFrame(df_rows)

    # ── Estilizar: rojo si excede ECA ───────────────────────────────────
    def _aplicar_estilos(df_styler):
        """Aplica coloreado rojo a celdas que exceden ECA."""
        # Crear matriz de estilos
        estilos = pd.DataFrame("", index=df.index, columns=df.columns)

        for idx, d in enumerate(datos):
            eca_id = d.get("eca_id")
            for cod, label in columnas_visibles:
                val = d.get(cod)
                if val is not None and _excede_eca(val, eca_id, cod, limites):
                    estilos.at[idx, label] = "background-color: #ffe0e0; color: #dc3545; font-weight: bold;"

        return estilos

    # ── Tabs: Vista y Edición ───────────────────────────────────────────
    if es_admin:
        tab_vista, tab_edicion = st.tabs(["Vista consulta", "Edición de datos"])
    else:
        tab_vista = st.container()
        tab_edicion = None

    # ── Tab Vista ───────────────────────────────────────────────────────
    with tab_vista:
        st.markdown(f"**{n_muestras} registros** · {n_puntos} puntos · "
                    f"Las celdas en **rojo** exceden su ECA respectivo")

        # Configuración de columnas para st.dataframe
        col_config = {}
        for cod, label in columnas_visibles:
            col_config[label] = st.column_config.NumberColumn(
                label, format="%.4g", help=f"Parámetro {cod}"
            )

        styled = df.style.apply(_aplicar_estilos, axis=None)

        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            height=min(700, 35 * len(df) + 38),
        )

        # Botón de descarga
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Descargar CSV",
            csv,
            f"base_datos_lvca_{date.today()}.csv",
            "text/csv",
            key="bd_download",
        )

    # ── Tab Edición (solo admin) ────────────────────────────────────────
    if tab_edicion is not None:
        with tab_edicion:
            st.markdown("Selecciona una muestra para editar sus valores.")

            # Selector de muestra
            opciones_muestra = {
                f"{d['fecha']} · {d['punto_codigo']} — {d['punto_nombre']} ({d['codigo_muestra']})": i
                for i, d in enumerate(datos)
            }
            sel_muestra = st.selectbox("Muestra", list(opciones_muestra.keys()), key="bd_sel_muestra")
            idx_muestra = opciones_muestra[sel_muestra]
            muestra = datos[idx_muestra]

            st.markdown(f"**ECA aplicable:** {muestra['eca_codigo']}")

            # Formulario de edición
            with st.form("form_editar_resultados"):
                st.markdown("### Resultados por parámetro")

                # Dividir en columnas por categoría
                cambios = {}

                for cat_nombre, cat_codigos in cat_params.items():
                    if cat_nombre not in categoria_filtro:
                        continue

                    st.markdown(f"**{cat_nombre}**")
                    cols = st.columns(min(4, len(cat_codigos)))

                    params_cat = [(c, l) for c, l in columnas_visibles if c in cat_codigos]
                    for i, (cod, label) in enumerate(params_cat):
                        col = cols[i % len(cols)]
                        val_actual = muestra.get(cod)
                        excede = _excede_eca(val_actual, muestra.get("eca_id"), cod, limites)

                        # Mostrar límite ECA como ayuda
                        lim = limites.get((muestra.get("eca_id"), cod))
                        help_txt = ""
                        if lim:
                            parts = []
                            if lim.get("valor_minimo") is not None:
                                parts.append(f"mín: {lim['valor_minimo']}")
                            if lim.get("valor_maximo") is not None:
                                parts.append(f"máx: {lim['valor_maximo']}")
                            help_txt = f"ECA: {', '.join(parts)}"
                            if excede:
                                help_txt = "EXCEDE — " + help_txt

                        with col:
                            nuevo_val = st.number_input(
                                f"{'🔴 ' if excede else ''}{label}",
                                value=float(val_actual) if val_actual is not None else None,
                                format="%.4g",
                                help=help_txt or None,
                                key=f"edit_{cod}_{idx_muestra}",
                                step=None,
                            )

                            # Detectar cambio
                            if val_actual is not None and nuevo_val is not None:
                                if abs(nuevo_val - val_actual) > 1e-10:
                                    cambios[cod] = nuevo_val
                            elif val_actual is None and nuevo_val is not None:
                                cambios[cod] = nuevo_val

                submitted = st.form_submit_button("Guardar cambios", type="primary")

            if submitted and cambios:
                param_map = get_parametros_map()
                resultado_ids = muestra.get("_resultado_ids", {})
                n_ok = 0

                for cod, nuevo_val in cambios.items():
                    info = resultado_ids.get(cod)
                    try:
                        if info:
                            # Actualizar existente
                            actualizar_resultado(info["resultado_id"], nuevo_val)
                        else:
                            # Crear nuevo
                            pid = param_map.get(cod)
                            if pid:
                                crear_resultado(muestra["muestra_id"], pid, nuevo_val)
                        n_ok += 1
                    except Exception as e:
                        st.error(f"Error al guardar {cod}: {e}")

                if n_ok > 0:
                    st.success(f"Se guardaron {n_ok} cambio(s) correctamente.")
                    st.rerun()

            elif submitted and not cambios:
                st.info("No se detectaron cambios.")


main()
