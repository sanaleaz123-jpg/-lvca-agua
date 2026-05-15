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
from components.ui_styles import aplicar_estilos, page_header, top_nav
from services.resultado_service import get_campanas
from services.punto_service import get_puntos


def _es_admin() -> bool:
    """Verifica si el usuario actual tiene rol de administrador."""
    sesion = st.session_state.get("sesion")
    if not sesion:
        return False
    return getattr(sesion, "rol", None) == "administrador"


# Decimales por categoría para mostrar en la tabla (no persiste en BD).
_FORMATO_POR_CATEGORIA = {
    "Parámetros de Campo": "%.2f",
    "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)": "%.3f",
    "Parámetros Hidrobiológicos": "%.1f",
}
_FORMATO_FALLBACK = "%.4g"


def _formato_por_codigo(cat_params: dict) -> dict:
    """Mapa {codigo: format_string} según la categoría del parámetro."""
    mapa: dict[str, str] = {}
    for cat_nombre, codigos in cat_params.items():
        fmt = _FORMATO_POR_CATEGORIA.get(cat_nombre, _FORMATO_FALLBACK)
        for cod in codigos:
            mapa[cod] = fmt
    return mapa


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


# Estilos CSS para la tabla HTML con separadores amarillos por campaña.
_BD_TABLE_CSS = """
<style>
  .bd-table-wrap {
    overflow-x: auto;
    max-height: 720px;
    border: 1px solid #dee2e6;
    border-radius: 6px;
    margin-bottom: 0.75rem;
  }
  table.bd-table {
    border-collapse: collapse;
    font-size: 12px;
    width: max-content;
    min-width: 100%;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  table.bd-table thead th {
    position: sticky;
    top: 0;
    background: #f1f3f5;
    color: #212529;
    font-weight: 600;
    padding: 6px 10px;
    border: 1px solid #dee2e6;
    text-align: center;
    white-space: nowrap;
    z-index: 2;
  }
  table.bd-table tbody td {
    padding: 4px 10px;
    border: 1px solid #e9ecef;
    background: #ffffff;
    white-space: nowrap;
    text-align: right;
  }
  table.bd-table tbody td.text { text-align: left; }
  table.bd-table tbody tr:hover td { background: #f8f9fa; }
  table.bd-table td.exceed {
    background: #ffe0e0 !important;
    color: #dc3545;
    font-weight: 700;
  }
  table.bd-table tr.bd-sep td {
    background: #FFEB3B !important;
    color: #212529;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 6px 10px;
    border-top: 2px solid #f1c40f;
    border-bottom: 1px solid #e0c200;
    text-align: left;
  }
</style>
"""


def _fmt_valor(val, fmt: str) -> str:
    """Formatea un valor numérico usando un format string estilo %.2f."""
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    try:
        return fmt % float(val)
    except (TypeError, ValueError):
        return str(val)


_MES_ES = {
    1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO", 6: "JUNIO",
    7: "JULIO", 8: "AGOSTO", 9: "SETIEMBRE", 10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE",
}


def _etiqueta_campana(d: dict) -> str:
    """Etiqueta amarilla del separador: MES YYYY · CODIGO — nombre."""
    fecha = d.get("campana_fecha_inicio") or d.get("fecha") or ""
    mes_txt = ""
    if fecha and len(fecha) >= 7:
        try:
            anio, mes = int(fecha[:4]), int(fecha[5:7])
            mes_txt = f"{_MES_ES.get(mes, '')} {anio}"
        except ValueError:
            mes_txt = ""
    cod = d.get("campana_codigo") or ""
    nom = d.get("campana_nombre") or ""
    partes = [p for p in (mes_txt, cod, nom) if p]
    return "  ·  ".join(partes) if partes else "Sin campaña"


def _render_tabla_por_campana(
    df: pd.DataFrame,
    datos: list[dict],
    columnas_visibles: list[tuple[str, str]],
    formato_codigo: dict,
    limites: dict,
) -> str:
    """
    Renderiza la base de datos como tabla HTML con separadores amarillos
    por campaña (estilo Excel: una fila completa amarilla con MES + código).

    El orden de las filas debe coincidir entre `df` y `datos`.
    """
    from html import escape

    columnas = list(df.columns)
    label_to_codigo = {label: cod for cod, label in columnas_visibles}
    text_cols = {"Fecha", "Hora", "Código Punto", "Punto", "Código Muestra",
                 "Código Lab.", "Cuenca", "Tipo", "ECA"}

    # Cabecera
    thead = "".join(f"<th>{escape(c)}</th>" for c in columnas)

    # Cuerpo: agrupar filas consecutivas que comparten campana_id.
    body_parts: list[str] = []
    ultimo_campana_key = object()
    n_cols = len(columnas)

    for idx, d in enumerate(datos):
        campana_key = d.get("campana_id") or d.get("campana_codigo") or "__sin__"
        if campana_key != ultimo_campana_key:
            label = escape(_etiqueta_campana(d))
            body_parts.append(
                f'<tr class="bd-sep"><td colspan="{n_cols}">{label}</td></tr>'
            )
            ultimo_campana_key = campana_key

        eca_id = d.get("eca_id")
        celdas: list[str] = []
        fila = df.iloc[idx]
        for col in columnas:
            raw = fila[col]
            cod = label_to_codigo.get(col)
            if cod is not None:
                fmt = formato_codigo.get(cod, _FORMATO_FALLBACK)
                txt = _fmt_valor(raw, fmt)
                exceed = (
                    raw is not None
                    and not (isinstance(raw, float) and pd.isna(raw))
                    and _excede_eca(raw, eca_id, cod, limites)
                )
                cls = " class=\"exceed\"" if exceed else ""
                celdas.append(f"<td{cls}>{escape(txt)}</td>")
            else:
                if raw is None or (isinstance(raw, float) and pd.isna(raw)):
                    txt = ""
                elif col == "Profundidad (m)":
                    try:
                        txt = f"{float(raw):.2f}"
                    except (TypeError, ValueError):
                        txt = str(raw)
                else:
                    txt = str(raw)
                cls = " class=\"text\"" if col in text_cols else ""
                celdas.append(f"<td{cls}>{escape(txt)}</td>")
        body_parts.append("<tr>" + "".join(celdas) + "</tr>")

    return (
        _BD_TABLE_CSS
        + '<div class="bd-table-wrap"><table class="bd-table">'
        + f"<thead><tr>{thead}</tr></thead>"
        + "<tbody>"
        + "".join(body_parts)
        + "</tbody></table></div>"
    )


@require_rol("visitante")
def main() -> None:
    aplicar_estilos()
    top_nav()
    page_header(
        "Base de Datos",
        "Consolidado de datos de campo, fisicoquímicos e hidrobiológicos por campaña",
    )

    es_admin = _es_admin()

    # ── Filtros (en main area, no sidebar) ──────────────────────────────
    from components.ui_styles import filter_bar_open, filter_bar_close
    filter_bar_open()

    fc1, fc2, fc3, fc4 = st.columns([1.4, 1.6, 1, 1])
    with fc1:
        campanas = get_campanas()
        opciones_camp = {"Todas las campañas": None}
        opciones_camp.update({
            f"{c['codigo']} — {c['nombre']}": c["id"] for c in campanas
        })
        sel_camp = st.selectbox("Campaña", list(opciones_camp.keys()), key="bd_camp")
        campana_id = opciones_camp[sel_camp]
    with fc2:
        # Filtro por nombre del lugar (represa / río / bocatoma).
        # Un mismo "lugar" puede tener varios puntos físicos: al seleccionarlo
        # se filtra por TODOS los punto_ids que comparten ese nombre.
        puntos = get_puntos(solo_activos=True)
        lugares: dict[str, list[str]] = {}
        for p in puntos:
            nombre = (p.get("nombre") or p.get("codigo") or "").strip()
            if not nombre:
                continue
            lugares.setdefault(nombre, []).append(p["id"])

        # Etiqueta con el tipo entre paréntesis cuando es único, para distinguir
        # "Río Sumbay" de "Represa Frayle" visualmente.
        tipos_por_nombre: dict[str, set[str]] = {}
        for p in puntos:
            nombre = (p.get("nombre") or p.get("codigo") or "").strip()
            if nombre:
                tipos_por_nombre.setdefault(nombre, set()).add((p.get("tipo") or "").strip())

        opciones_lugar: dict[str, tuple[str, ...] | None] = {"Todos los lugares": None}
        for nombre in sorted(lugares.keys()):
            tipos = {t for t in tipos_por_nombre.get(nombre, set()) if t}
            sufijo = f"  ·  {next(iter(tipos)).capitalize()}" if len(tipos) == 1 else ""
            opciones_lugar[f"{nombre}{sufijo}"] = tuple(lugares[nombre])

        sel_lugar = st.selectbox(
            "Lugar de muestreo",
            list(opciones_lugar.keys()),
            key="bd_lugar",
            help="Filtra por nombre del lugar (represa, río, bocatoma…). "
                 "Muestra todas las muestras de los puntos vinculados al lugar.",
        )
        punto_ids_filtro = opciones_lugar[sel_lugar]
    with fc3:
        _hoy = date.today()
        _default_desde = _hoy.replace(year=_hoy.year - 1)
        fecha_inicio = st.date_input("Desde", value=_default_desde, key="bd_desde")
    with fc4:
        fecha_fin = st.date_input("Hasta", value=_hoy, key="bd_hasta")

    # Segunda fila de opciones (categorías + flag de celdas vacías)
    fc5, fc6 = st.columns([3, 1])
    with fc5:
        _categorias_disponibles = list(get_cat_params().keys())
        categoria_filtro = st.multiselect(
            "Categorías a mostrar",
            _categorias_disponibles,
            default=_categorias_disponibles,
            key="bd_categorias",
        )
    with fc6:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        mostrar_vacios = st.checkbox("Mostrar celdas vacías", value=True, key="bd_vacios")
    filter_bar_close()

    # ── Cargar datos ────────────────────────────────────────────────────
    with st.spinner("Cargando base de datos..."):
        try:
            datos = get_datos_consolidados(
                campana_id=campana_id,
                punto_ids=punto_ids_filtro,
                fecha_inicio=str(fecha_inicio) if fecha_inicio else None,
                fecha_fin=str(fecha_fin) if fecha_fin else None,
            )
        except Exception as e:
            st.error(f"Error cargando datos consolidados: {type(e).__name__}: {e}")
            st.exception(e)
            st.stop()
        limites = get_limites_eca_todos()

    if not datos:
        st.info("No se encontraron resultados con los filtros seleccionados.")
        st.stop()

    # ── Filtrar columnas por categoría (dinámico desde BD) ──────────────
    cat_params = get_cat_params()
    COLUMNAS_PARAMETROS = get_columnas_parametros()
    formato_codigo = _formato_por_codigo(cat_params)

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
    # Orden cronológico ascendente para que los separadores amarillos por
    # campaña sigan el mismo orden del Excel (FEBRERO → MARZO → ABRIL …).
    datos = sorted(
        datos,
        key=lambda d: (
            d.get("campana_fecha_inicio") or d.get("fecha") or "",
            d.get("fecha") or "",
            d.get("punto_codigo") or "",
            d.get("codigo_muestra") or "",
        ),
    )

    df_rows = []
    for d in datos:
        row = {
            "Fecha": d["fecha"],
            "Hora": d.get("hora", ""),
            "Código Punto": d["punto_codigo"],
            "Punto": d["punto_nombre"],
            "Código Muestra": d.get("codigo_muestra", ""),
            "Código Lab.": d.get("codigo_laboratorio") or "",
            "Profundidad (m)": d.get("profundidad"),
            "Cuenca": d["cuenca"],
            "Tipo": (d["tipo"] or "").capitalize(),
            "ECA": d["eca_codigo"],
        }
        for cod, label in columnas_visibles:
            row[label] = d.get(cod)
        df_rows.append(row)

    # Ocultar columna "Código Lab." si ninguna muestra tiene valor asignado.
    # Reaparece automáticamente en cuanto se cargue un código en Recepción.
    if all(not r.get("Código Lab.") for r in df_rows):
        for r in df_rows:
            r.pop("Código Lab.", None)

    # Si ninguna muestra tiene profundidad registrada, también se oculta
    # para mantener la vista limpia en los puntos superficiales.
    if all(r.get("Profundidad (m)") in (None, "") for r in df_rows):
        for r in df_rows:
            r.pop("Profundidad (m)", None)

    df = pd.DataFrame(df_rows)

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

        html_table = _render_tabla_por_campana(
            df=df,
            datos=datos,
            columnas_visibles=columnas_visibles,
            formato_codigo=formato_codigo,
            limites=limites,
        )
        st.markdown(html_table, unsafe_allow_html=True)

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
                                format=formato_codigo.get(cod, _FORMATO_FALLBACK),
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
