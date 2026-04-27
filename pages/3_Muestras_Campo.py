"""
pages/3_Muestras_Campo.py
Registro de muestras de campo, mediciones in situ y cadena de custodia.

Tabs:
    1. Registro — formulario de nueva muestra
    2. In situ  — mediciones de campo con semáforo ECA
    3. Custodia — recepción en lab y transiciones de estado
    4. Listado  — tabla general con filtros
    5. Cadena   — generación de cadena de custodia AUTODEMA (Excel/PDF)

Acceso mínimo: administrador.
"""

from __future__ import annotations

from datetime import date, time

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import (
    aplicar_estilos,
    inline_note,
    page_header,
    section_header,
    success_check_overlay,
    top_nav,
)
# Nota: get_admin_client ya no se importa directamente — todas las queries van
# vía services/muestra_service (get_campana_detalle reemplazó al helper local
# que saltaba el patrón de services).
from services.muestra_service import (
    ESTADOS_MUESTRA,
    ESTADOS_FRASCO,
    ETIQUETA_ESTADO_MUESTRA,
    ETIQUETA_TIPO,
    OPCIONES_CLIMA,
    PROFUNDIDAD_LABELS,
    PROFUNDIDAD_SUFIJOS,
    TIPOS_MUESTRA,
    TRANSICIONES_MUESTRA,
    TransicionMuestraError,
    actualizar_estado_muestra,
    actualizar_muestra,
    crear_muestra,
    eliminar_muestra,
    get_campana_detalle,
    get_limites_insitu,
    get_mediciones_insitu,
    get_muestras_por_campana,
    get_muestra_por_campana_punto,
    get_puntos_de_campana_activa,
    get_usuarios_campo,
    recibir_en_laboratorio,
    registrar_insitu,
)
from services.parametro_registry import (
    get_parametros_insitu,
    get_parametros_lab_cadena,
)
from services.resultado_service import get_campanas, _get_usuario_interno_id
from services.campana_service import get_parametros_lab_campana
from services.cadena_custodia_service import (
    EQUIPOS_DEFAULT,
    config_para_campana,
    generar_excel_cadena,
    generar_pdf_cadena,
    get_equipos_registrados,
    guardar_config_persistida,
    registrar_equipo,
)
from services.storage_service import (
    delete_foto_campo,
    get_fotos_campo,
    upload_foto_campo,
)
from services.ficha_campo_service import generar_docx_fichas


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de presentación
# ─────────────────────────────────────────────────────────────────────────────

def _semaforo_insitu(valor, lim_min, lim_max) -> str:
    """
    Estado ECA del valor in situ como icono Material Symbols renderizado
    con un span colored. Se usa dentro de st.markdown(unsafe_allow_html=True)
    o en st.markdown directo (Streamlit interpreta los iconos en HTML inline).
    """
    if valor is None:
        return (
            '<span class="material-symbols-rounded" style="color:#9ca3af;">'
            "remove</span>"
        )
    if lim_max is None and lim_min is None:
        return (
            '<span class="material-symbols-rounded" style="color:#9ca3af;">'
            "horizontal_rule</span>"
        )
    excede = (
        (lim_max is not None and valor > lim_max)
        or (lim_min is not None and valor < lim_min)
    )
    if excede:
        return (
            '<span class="material-symbols-rounded" style="color:#dc2626;">'
            "error</span>"
        )
    return (
        '<span class="material-symbols-rounded" style="color:#16a34a;">'
        "check_circle</span>"
    )


def _muestras_por_campana_cached(campana_id: str, *, force: bool = False) -> list[dict]:
    """
    Cache de muestras por campaña a nivel sesión, válido por todo el ciclo de
    render. Antes get_muestras_por_campana se llamaba 5-6 veces por cada
    interacción (tabs múltiples). Ahora una sola query por (run, campana_id).

    Invalidar manualmente con `force=True` o `_invalidar_muestras_cache(id)`
    tras crear/editar/eliminar muestras.
    """
    cache: dict[str, list[dict]] = st.session_state.setdefault("_muestras_cache", {})
    if force or campana_id not in cache:
        cache[campana_id] = get_muestras_por_campana(campana_id)
    return cache[campana_id]


def _invalidar_muestras_cache(campana_id: str | None = None) -> None:
    """Invalida el cache. Si no se pasa campana_id, limpia todo el cache."""
    cache = st.session_state.get("_muestras_cache", {})
    if campana_id is None:
        cache.clear()
    else:
        cache.pop(campana_id, None)


_ESTADOS_ACTIVOS = ("planificada", "en_campo", "en_laboratorio")


def _global_campaign_selector() -> str | None:
    """
    Selector único de campaña que se renderiza UNA sola vez arriba de los
    tabs y persiste en `session_state["muestras_campana_id"]`. Todos los
    tabs leen esa misma campaña.

    Por defecto solo muestra campañas activas (planificada / en_campo /
    en_laboratorio). Hay un toggle para incluir las completadas/archivadas/
    anuladas (útil para consultar datos históricos en Listado o regenerar
    documentos).

    Cada tab valida internamente si el estado de la campaña es compatible
    con su acción (ej. Registro requiere en_campo) y muestra una nota si
    no lo es. Así el usuario nunca pierde el contexto al cambiar de tab.
    """
    todas = get_campanas()
    if not todas:
        st.warning("No hay campañas registradas todavía.")
        st.info(
            "Crea una campaña en la página **Campañas** y márcala como "
            "**'en_campo'** para empezar a registrar muestras."
        )
        return None

    incluir_cerradas = st.toggle(
        "Incluir campañas completadas / archivadas / anuladas",
        value=False,
        key="muestras_incluir_cerradas",
        help="Activa para consultar datos o regenerar documentos de campañas históricas.",
    )
    if incluir_cerradas:
        candidatas = todas
    else:
        candidatas = [c for c in todas if c.get("estado") in _ESTADOS_ACTIVOS]

    if not candidatas:
        agrupadas: dict[str, list[str]] = {}
        for c in todas:
            agrupadas.setdefault(c.get("estado", "desconocido"), []).append(c["codigo"])
        st.warning("No hay campañas activas (planificada / en_campo / en_laboratorio).")
        with st.expander("Ver campañas existentes", expanded=True):
            for est, codigos in agrupadas.items():
                st.markdown(
                    f"- **{est}** ({len(codigos)}): {', '.join(codigos[:5])}"
                    + (f" (+{len(codigos) - 5})" if len(codigos) > 5 else "")
                )
            st.info("Activa el toggle de arriba para verlas, o crea una nueva en **Campañas**.")
        return None

    opciones = {
        f"{c['codigo']} — {c['nombre']} ({c.get('estado', '')})": c["id"]
        for c in candidatas
    }
    label_sel = st.selectbox(
        "Campaña activa",
        list(opciones.keys()),
        key="muestras_global_camp",
    )
    return opciones[label_sel]


def _bloquear_si_estado_incorrecto(
    campana_id: str,
    estados_validos: tuple[str, ...],
    accion: str,
) -> bool:
    """
    Devuelve True si la campaña está en un estado válido para la acción del
    tab actual. Si no, muestra una nota explicativa con el estado actual y
    el o los estados requeridos, y devuelve False (el caller hace `return`).
    """
    info = _get_campana_info(campana_id)
    estado = info.get("estado", "")
    if estado in estados_validos:
        return True

    estados_str = " o ".join(f"<b>{e}</b>" for e in estados_validos)
    inline_note(
        f"Esta campaña está en estado <b>{estado}</b>. "
        f"Para {accion} la campaña debe estar en {estados_str}. "
        "Cambia el estado en la página <b>Campañas</b>.",
        tipo="warning",
    )
    return False


def _generate_download_widget(
    *,
    label_btn: str,
    label_dl: str,
    generate_fn,
    campana_id: str,
    state_key: str,
    file_name: str,
    mime: str,
    btn_kwargs: dict | None = None,
    extra_args: tuple = (),
) -> None:
    """
    Patrón reutilizable: botón "Generar X" + (cuando hay output cacheado para
    esta campaña) botón "Descargar X". El cache vive en session_state[state_key]
    junto con session_state[f"{state_key}_campana_id"] para evitar mostrar
    descargas correspondientes a otra campaña.

    generate_fn debe aceptar (campana_id, *extra_args) y retornar bytes.
    """
    btn_kwargs = btn_kwargs or {"use_container_width": True}
    cid_key = f"{state_key}_campana_id"

    if st.button(label_btn, key=f"btn_{state_key}", **btn_kwargs):
        with st.spinner(f"{label_btn}..."):
            try:
                output = generate_fn(campana_id, *extra_args)
                st.session_state[state_key] = output
                st.session_state[cid_key] = campana_id
            except Exception as exc:
                st.error(f"Error en '{label_btn}': {exc}")

    if (
        st.session_state.get(state_key)
        and st.session_state.get(cid_key) == campana_id
    ):
        st.download_button(
            label=label_dl,
            data=st.session_state[state_key],
            file_name=file_name,
            mime=mime,
            use_container_width=True,
            key=f"dl_{state_key}",
        )


def _fila_muestra(m: dict, campos: tuple[str, ...] = ()) -> dict:
    """
    Construye un dict de fila para una muestra, incluyendo solo los campos
    pedidos. Antes esta lógica vivía duplicada en los tabs Recepción y
    Listado con divergencias sutiles (uno mostraba Técnico, otro Hora, etc.).

    Campos disponibles:
        codigo, punto, fecha, hora, tipo, estado, tecnico, profundidad
    """
    pt = m.get("puntos_muestreo") or {}
    tec = m.get("tecnico") or {}
    prof_tipo = m.get("profundidad_tipo")
    prof_suf = (
        f" {PROFUNDIDAD_SUFIJOS[prof_tipo]}"
        if prof_tipo in PROFUNDIDAD_SUFIJOS else ""
    )

    out: dict = {}
    if "codigo" in campos:
        out["Código"] = f"{m['codigo']}{prof_suf}"
    if "punto" in campos:
        out["Punto"] = f"{pt.get('codigo','')} — {pt.get('nombre','')}"
    if "fecha" in campos:
        out["Fecha"] = str(m.get("fecha_muestreo", ""))[:10]
    if "hora" in campos:
        out["Hora"] = m.get("hora_recoleccion", "—")
    if "tipo" in campos:
        out["Tipo"] = ETIQUETA_TIPO.get(m.get("tipo_muestra", ""), "")
    if "estado" in campos:
        out["Estado"] = ETIQUETA_ESTADO_MUESTRA.get(
            m.get("estado", ""), m.get("estado", ""),
        )
    if "tecnico" in campos:
        out["Técnico"] = (
            f"{tec.get('nombre','')} {tec.get('apellido','')}".strip() or "—"
        )
    if "profundidad" in campos:
        modo = m.get("modo_muestreo", "superficial") or "superficial"
        if modo == "columna" and prof_tipo:
            prof_val = m.get("profundidad_valor", "")
            out["Profundidad"] = (
                f"{PROFUNDIDAD_LABELS.get(prof_tipo, prof_tipo)} ({prof_val} m)"
                if prof_val else PROFUNDIDAD_LABELS.get(prof_tipo, "")
            )
        else:
            out["Profundidad"] = "Superficial"
    return out


def _widget_nuevo_equipo(key_prefix: str) -> None:
    """
    Expander reutilizable para registrar un nuevo equipo de medición.
    Antes este bloque vivía duplicado en el tab In-situ (~768) y en el tab
    Documento CC (~1599) palabra por palabra.
    """
    with st.expander("Registrar nuevo equipo", expanded=False):
        ne1, ne2 = st.columns(2)
        with ne1:
            cod = st.text_input(
                "Código del equipo",
                key=f"{key_prefix}_eq_cod",
                placeholder="Ej. EQ-001",
            )
        with ne2:
            nom = st.text_input(
                "Nombre del equipo",
                key=f"{key_prefix}_eq_nom",
                placeholder="Ej. Multiparámetro Hanna HI98194",
            )
        if st.button("Agregar equipo", key=f"{key_prefix}_eq_btn"):
            if cod.strip() and nom.strip():
                registrar_equipo(cod.strip(), nom.strip())
                success_check_overlay(f"Equipo '{nom.strip()}' registrado")
                st.rerun()
            else:
                st.error("Completa código y nombre del equipo.")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Registro de nueva muestra
# ─────────────────────────────────────────────────────────────────────────────

# _get_campana_info movido a muestra_service.get_campana_detalle.
# Wrapper local mantenido para no tocar callers existentes.
def _get_campana_info(campana_id: str) -> dict:
    return get_campana_detalle(campana_id)


def _abreviar_nombre(nombre_completo: str) -> str:
    """
    Abrevia un nombre completo: iniciales de nombres, apellidos completos.
    'Adrian Llacho' → 'A. Llacho'
    'Jean Pierre Madariaga' → 'J. Madariaga'
    'Alfonso Torres E.' → 'A. Torres E.'
    """
    if not nombre_completo:
        return ""
    partes = nombre_completo.strip().split()
    if len(partes) <= 1:
        return nombre_completo
    # Última parte (o últimas si termina en inicial como "E.") son apellidos
    # Heurística: si es >=3 partes, primer(os) son nombre(s), último(s) apellido(s)
    # Para simplificar: primer token = nombre → inicial, resto = apellidos
    inicial = partes[0][0] + "."
    apellidos = " ".join(partes[1:])
    return f"{inicial} {apellidos}"


def _render_registro(campana_id: str) -> None:
    section_header("Registro de muestra de campo", "edit")
    st.caption("Si el punto ya tiene una muestra en la campaña, se cargan los datos para editar.")

    if not _bloquear_si_estado_incorrecto(
        campana_id, ("en_campo",), "registrar muestras"
    ):
        return

    # Obtener info de la campaña para restringir fechas
    camp_info = _get_campana_info(campana_id)
    camp_fecha_ini = None
    camp_fecha_fin = None
    if camp_info.get("fecha_inicio"):
        try:
            camp_fecha_ini = date.fromisoformat(str(camp_info["fecha_inicio"])[:10])
        except (ValueError, TypeError):
            pass
    if camp_info.get("fecha_fin"):
        try:
            camp_fecha_fin = date.fromisoformat(str(camp_info["fecha_fin"])[:10])
        except (ValueError, TypeError):
            pass

    puntos = get_puntos_de_campana_activa(campana_id)
    if not puntos:
        st.info("Esta campaña no tiene puntos de muestreo vinculados.")
        return

    # Filtrar técnicos a los responsables de campo definidos en la campaña.
    # Si la campaña no tiene responsables definidos (campo vacío) o ninguno
    # de los nombres declarados coincide con un usuario registrado, caemos al
    # listado completo para no bloquear el registro.
    usuarios = get_usuarios_campo()
    resp_campo_str = camp_info.get("responsable_campo") or ""
    resp_campo_set = {
        n.strip() for n in resp_campo_str.split(",") if n.strip()
    }
    if resp_campo_set:
        usuarios_filtrados = [
            u for u in usuarios
            if f"{u.get('nombre','')} {u.get('apellido','')}".strip() in resp_campo_set
        ]
        if usuarios_filtrados:
            usuarios = usuarios_filtrados
        else:
            inline_note(
                "Los responsables de campo declarados en la campaña no coinciden con "
                "ningún usuario del sistema — se muestra el listado completo. "
                "Verifica los nombres en la página <b>Campañas</b>.",
                tipo="warning",
            )

    opciones_puntos = {
        f"{p['codigo']} — {p['nombre']}": p["id"] for p in puntos
    }
    opciones_tecnicos = {
        f"{u['apellido']}, {u['nombre']} ({u.get('institucion','')})": u["id"]
        for u in usuarios
    }

    # ── Seleccionar punto (fuera del form para detectar muestra existente) ──
    punto_label = st.selectbox("Punto de muestreo *", list(opciones_puntos.keys()), key="reg_punto")
    punto_id = opciones_puntos[punto_label]

    # ── Detectar si ya existe una muestra para este punto en la campaña ──
    existente = get_muestra_por_campana_punto(campana_id, punto_id)
    es_edicion = existente is not None

    if es_edicion:
        modo_exist = existente.get("modo_muestreo", "superficial") or "superficial"
        if modo_exist == "columna" and existente.get("_grupo_muestras"):
            grupo = existente["_grupo_muestras"]
            codigos_prof = ", ".join(
                f"{grupo[t]['codigo']} {PROFUNDIDAD_SUFIJOS[t]}"
                for t in ("S", "M", "F") if t in grupo
            )
            st.info(f"Muestras existentes (columna): **{codigos_prof}** — Editando datos.")
        else:
            st.info(f"Muestra existente: **{existente['codigo']}** — Editando datos.")
        # Preparar valores por defecto desde la muestra existente
        def_tipo = existente.get("tipo_muestra", "simple")
        try:
            def_fecha = date.fromisoformat(str(existente.get("fecha_muestreo", ""))[:10])
        except (ValueError, TypeError):
            def_fecha = date.today()
        try:
            h_parts = (existente.get("hora_recoleccion") or "09:00").split(":")
            def_hora = time(int(h_parts[0]), int(h_parts[1]))
        except (ValueError, IndexError):
            def_hora = time(9, 0)
        def_clima = existente.get("clima") or ""
        def_caudal = existente.get("caudal_estimado") or ""
        def_nivel = existente.get("nivel_agua") or ""
        def_temp = existente.get("temperatura_transporte")
        if def_temp is None:
            def_temp = 4.0
        else:
            def_temp = float(def_temp)
        def_obs = existente.get("observaciones_campo") or ""
        def_tecnico_id = existente.get("tecnico_campo_id")
        def_modo = modo_exist
        def_prof_total = existente.get("profundidad_total")
        def_prof_secchi = existente.get("profundidad_secchi")
        # Profundidades individuales
        def_profundidades = {}
        if existente.get("_grupo_muestras"):
            for tp, info in existente["_grupo_muestras"].items():
                def_profundidades[tp] = info.get("valor")
        elif existente.get("profundidad_valor") is not None:
            tp = existente.get("profundidad_tipo", "S")
            def_profundidades[tp] = existente["profundidad_valor"]
    else:
        def_tipo = "simple"
        def_fecha = date.today()
        if camp_fecha_ini and camp_fecha_fin:
            def_fecha = max(camp_fecha_ini, min(date.today(), camp_fecha_fin))
        def_hora = time(9, 0)
        def_clima = ""
        def_caudal = ""
        def_nivel = ""
        def_temp = 4.0
        def_obs = ""
        def_tecnico_id = None
        def_modo = "superficial"
        def_prof_total = None
        def_prof_secchi = None
        def_profundidades = {}

    # Índice del tipo de muestra
    tipo_idx = TIPOS_MUESTRA.index(def_tipo) if def_tipo in TIPOS_MUESTRA else 0

    # Índice del clima
    lista_clima = [""] + OPCIONES_CLIMA
    clima_idx = lista_clima.index(def_clima) if def_clima in lista_clima else 0

    # Índice del técnico
    tecnico_idx = 0
    if def_tecnico_id and opciones_tecnicos:
        for i, (_, tid) in enumerate(opciones_tecnicos.items()):
            if tid == def_tecnico_id:
                tecnico_idx = i
                break

    # ── Modo de muestreo (FUERA del form para que sea dinámico) ────────
    modos_muestreo = ["superficial", "columna"]
    modo_idx = modos_muestreo.index(def_modo) if def_modo in modos_muestreo else 0

    section_header("Modo de muestreo", "droplet")
    modo_muestreo = st.radio(
        "Tipo de muestreo",
        modos_muestreo,
        index=modo_idx,
        format_func=lambda m: "Superficial" if m == "superficial" else "Columna de agua (Superficie / Medio / Fondo)",
        horizontal=True,
        key="reg_modo_muestreo",
    )

    # ── Fotos ya guardadas del punto (FUERA del form para permitir eliminar) ─
    if es_edicion:
        muestra_id_existente = existente["id"]
        fotos_guardadas = get_fotos_campo(muestra_id_existente)
        if fotos_guardadas:
            section_header(
                f"Fotos guardadas de este punto ({len(fotos_guardadas)})",
                "image",
            )
            st.caption(
                "Fotos ya registradas para esta muestra. Usa el botón para "
                "eliminar una foto específica."
            )
            cols_gal = st.columns(min(len(fotos_guardadas), 5))
            for idx, foto in enumerate(fotos_guardadas):
                with cols_gal[idx % len(cols_gal)]:
                    st.image(foto["url"], use_container_width=True)
                    if st.button(
                        "Eliminar",
                        key=f"del_foto__{muestra_id_existente}__{foto['name']}",
                        use_container_width=True,
                    ):
                        delete_foto_campo(muestra_id_existente, foto["name"])
                        st.rerun()

    with st.form("form_muestra", clear_on_submit=False):
        # ── Tipo ─────────────────────────────────────────────────────────
        tipo = st.selectbox(
            "Tipo de muestra",
            TIPOS_MUESTRA,
            index=tipo_idx,
            format_func=lambda t: ETIQUETA_TIPO.get(t, t),
        )

        # ── Fecha, hora y técnico ────────────────────────────────────────
        c3, c4, c5 = st.columns(3)
        with c3:
            fecha = st.date_input(
                "Fecha de recolección *",
                value=def_fecha,
                min_value=camp_fecha_ini or date(2020, 1, 1),
                max_value=camp_fecha_fin or date(2099, 12, 31),
            )
        with c4:
            hora = st.time_input("Hora de recolección", value=def_hora)
        with c5:
            if opciones_tecnicos:
                tecnico_label = st.selectbox(
                    "Técnico de campo",
                    list(opciones_tecnicos.keys()),
                    index=tecnico_idx,
                )
            else:
                tecnico_label = None
                st.info("Sin técnicos registrados.")

        # ── Campos de profundidad ───────────────────────────────────────
        prof_total_val = None
        prof_secchi_val = None
        prof_s_val = None
        prof_m_val = None
        prof_f_val = None

        if modo_muestreo == "superficial":
            # Solo 1 campo de profundidad para superficial
            prof_s_val = st.number_input(
                "Profundidad de muestreo (m)",
                min_value=0.0, max_value=50.0, step=0.1,
                value=float(def_profundidades.get("S", 0.3)),
                key="reg_prof_sup",
            )
        else:
            # Columna de agua: ecosonda, Secchi y 3 profundidades
            section_header("Profundidades", "waves")
            st.caption("Ingrese las profundidades en metros para cada nivel de muestreo.")
            pt1, pt2 = st.columns(2)
            with pt1:
                prof_total_val = st.number_input(
                    "Profundidad total (ecosonda) (m)",
                    min_value=0.0, max_value=500.0, step=0.1,
                    value=float(def_prof_total) if def_prof_total else 0.0,
                    key="reg_prof_total",
                )
            with pt2:
                prof_secchi_val = st.number_input(
                    "Profundidad Secchi (disco) (m)",
                    min_value=0.0, max_value=100.0, step=0.1,
                    value=float(def_prof_secchi) if def_prof_secchi else 0.0,
                    key="reg_prof_secchi",
                )
            ps1, ps2, ps3 = st.columns(3)
            with ps1:
                prof_s_val = st.number_input(
                    "Prof. Superficie (m)",
                    min_value=0.0, max_value=500.0, step=0.1,
                    value=float(def_profundidades.get("S", 0.3)),
                    key="reg_prof_s",
                )
            with ps2:
                prof_m_val = st.number_input(
                    "Prof. Medio (m)",
                    min_value=0.0, max_value=500.0, step=0.1,
                    value=float(def_profundidades.get("M", 0.0)),
                    key="reg_prof_m",
                )
            with ps3:
                prof_f_val = st.number_input(
                    "Prof. Fondo (m)",
                    min_value=0.0, max_value=500.0, step=0.1,
                    value=float(def_profundidades.get("F", 0.0)),
                    key="reg_prof_f",
                )

        # ── Transporte ───────────────────────────────────────────────────
        temp_transporte = st.number_input(
            "Temperatura de transporte (°C)",
            min_value=-10.0,
            max_value=50.0,
            value=def_temp,
            step=0.5,
        )

        # ── Observaciones (incluye clima, descarga, nivel) ──────────────
        section_header("Observaciones de campo", "file")
        oc1, oc2, oc3 = st.columns(3)
        with oc1:
            clima = st.selectbox("Clima", lista_clima, index=clima_idx)
        with oc2:
            caudal = st.text_input("Descarga", value=def_caudal, placeholder="Ej: 2.5 m3/s")
        with oc3:
            nivel = st.text_input("Nivel del embalse", value=def_nivel, placeholder="Ej: normal / alto / bajo")

        observaciones = st.text_area(
            "Observaciones adicionales",
            value=def_obs,
            placeholder="Notas sobre condiciones, accesibilidad, olores, color del agua...",
        )

        # ── Fotos de campo ───────────────────────────────────────────────
        if es_edicion:
            section_header("Agregar más fotos (opcional, máx. 5)", "eye")
            st.caption(
                "Selecciona fotos adicionales para sumarlas a las ya "
                "guardadas. Se subirán al presionar **Actualizar muestra**."
            )
        else:
            section_header("Fotos iniciales (opcional, máx. 5)", "eye")
            st.caption(
                "Sube hasta 5 fotos al registrar la muestra. La primera se "
                "usa en la Ficha de Campo."
            )
        fotos_subidas = st.file_uploader(
            "Seleccionar fotos JPG/PNG",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key=f"reg_fotos_upload__{campana_id}__{punto_id}",
        )
        # Feedback inmediato del conteo de fotos para evitar errores tardíos
        if fotos_subidas:
            n_f = len(fotos_subidas)
            if n_f > 5:
                st.error(f"Has seleccionado {n_f} fotos. Máximo permitido: 5. "
                         "Quita las extra antes de continuar.")
            else:
                st.caption(f"{n_f} foto(s) seleccionada(s).")

        btn_label = "Actualizar muestra" if es_edicion else "Registrar muestra"
        if modo_muestreo == "columna" and not es_edicion:
            btn_label = "Registrar 3 muestras (S/M/F)"
        submitted = st.form_submit_button(
            btn_label,
            type="primary",
            use_container_width=True,
        )

    if submitted:
        # Validar fotos (segunda barrera por si subió 6+ y aún así presionó)
        if fotos_subidas and len(fotos_subidas) > 5:
            st.error("Máximo 5 fotos por muestra. Quita las extra y reintenta.")
            return

        # Validar profundidades si columna — mensaje específico apuntando al campo
        if modo_muestreo == "columna":
            faltantes = []
            if not prof_total_val or prof_total_val <= 0:
                faltantes.append("**Profundidad total** (ecosonda)")
            if not prof_f_val or prof_f_val <= 0:
                faltantes.append("**Profundidad de fondo**")
            if faltantes:
                st.error(
                    "Para muestreo de columna debes ingresar: "
                    + " y ".join(faltantes)
                    + ". Tus otros datos NO se han perdido — corrige y vuelve a presionar."
                )
                return

        tecnico_id = opciones_tecnicos[tecnico_label] if tecnico_label else None

        datos = {
            "campana_id":              campana_id,
            "punto_muestreo_id":       punto_id,
            "tipo_muestra":            tipo,
            "fecha_muestreo":          str(fecha),
            "hora_recoleccion":        hora.strftime("%H:%M"),
            "tecnico_campo_id":        tecnico_id,
            "clima":                   clima or None,
            "caudal_estimado":         caudal.strip() or None,
            "nivel_agua":              nivel.strip() or None,
            "temperatura_transporte":  temp_transporte,
            "observaciones_campo":     observaciones.strip() or None,
            "modo_muestreo":           modo_muestreo,
        }

        # Campos de profundidad
        if modo_muestreo == "columna":
            datos["profundidad_total"] = prof_total_val if prof_total_val else None
            datos["profundidad_secchi"] = prof_secchi_val if prof_secchi_val else None
            datos["profundidades"] = {
                "S": prof_s_val,
                "M": prof_m_val,
                "F": prof_f_val,
            }
        else:
            # Superficial: guardar profundidad de muestreo
            datos["profundidad_valor"] = prof_s_val if prof_s_val else 0.3

        if es_edicion:
            # ── Actualizar muestra existente ─────────────────────────────
            with st.spinner("Actualizando muestra..."):
                try:
                    actualizar_muestra(existente["id"], datos)
                    # Si es columna, actualizar las 3 muestras del grupo
                    if modo_muestreo == "columna" and existente.get("_grupo_muestras"):
                        for tp, info in existente["_grupo_muestras"].items():
                            actualizar_muestra(info["id"], {
                                **datos,
                                "profundidad_valor": datos.get("profundidades", {}).get(tp),
                            })
                    _invalidar_muestras_cache(campana_id)
                except Exception as exc:
                    st.error(f"Error al actualizar: {exc}")
                    return
            success_check_overlay(f"Muestra {existente['codigo']} actualizada")
            st.success(f"Muestra **{existente['codigo']}** actualizada correctamente.")
            muestra_id_fotos = existente["id"]
        else:
            # ── Crear nueva muestra ──────────────────────────────────────
            with st.spinner("Registrando muestra..."):
                try:
                    creada = crear_muestra(datos)
                    _invalidar_muestras_cache(campana_id)
                except Exception as exc:
                    st.error(f"Error al crear la muestra: {exc}")
                    return
            if modo_muestreo == "columna":
                success_check_overlay(f"3 muestras registradas — {creada['codigo']}")
                st.success(f"3 muestras de columna registradas. Primera: **{creada['codigo']}**")
            else:
                success_check_overlay(f"Muestra {creada['codigo']} registrada")
                st.success(f"Muestra **{creada['codigo']}** registrada exitosamente.")
            muestra_id_fotos = creada["id"]

        # ── Subir fotos asociadas ────────────────────────────────────────
        if fotos_subidas:
            for archivo in fotos_subidas:
                try:
                    upload_foto_campo(
                        muestra_id_fotos,
                        archivo.getvalue(),
                        archivo.name,
                        archivo.type,
                    )
                except Exception as exc:
                    st.warning(f"Error subiendo {archivo.name}: {exc}")
            st.info(f"{len(fotos_subidas)} foto(s) subida(s).")

        # Puente al tab "In situ" — evita que el técnico tenga que cambiar
        # de tab y re-seleccionar la misma campaña/punto manualmente.
        if not es_edicion:
            st.divider()
            cta_a, cta_b = st.columns(2)
            with cta_a:
                if st.button(
                    "Registrar mediciones in-situ ahora",
                    key=f"btn_goto_insitu_{muestra_id_fotos}",
                    type="primary",
                    icon=":material/arrow_forward:",
                    use_container_width=True,
                ):
                    # La campaña ya es global — solo pre-seleccionamos la
                    # muestra en el tab in-situ.
                    st.session_state["insitu_prefill_muestra_id"] = muestra_id_fotos
                    st.rerun()
            with cta_b:
                if st.button(
                    "Registrar otra muestra",
                    key=f"btn_otra_muestra_{muestra_id_fotos}",
                    icon=":material/add:",
                    use_container_width=True,
                ):
                    st.rerun()
        else:
            # Refrescar para mostrar datos actualizados (modo edición)
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Mediciones in situ
# ─────────────────────────────────────────────────────────────────────────────

def _render_insitu(campana_id: str) -> None:
    section_header("Parámetros medidos en campo", "thermometer")

    # Las mediciones in-situ pueden registrarse en cualquier momento mientras
    # la campaña esté en campo o ya recibida en lab.
    if not _bloquear_si_estado_incorrecto(
        campana_id,
        ("en_campo", "en_laboratorio"),
        "registrar mediciones in situ",
    ):
        return

    # Si el usuario llegó aquí desde "Registrar mediciones in-situ ahora →"
    # del tab Registro, pre-seleccionamos la muestra recién creada
    muestra_prefill = st.session_state.pop("insitu_prefill_muestra_id", None)

    muestras = _muestras_por_campana_cached(campana_id)
    if not muestras:
        st.info("No hay muestras registradas en esta campaña.")
        return

    # Agrupar muestras por punto para detectar columna (3 muestras = columna)
    muestras_por_punto: dict[str, list[dict]] = {}
    for m in muestras:
        pt = m.get("puntos_muestreo") or {}
        pt_id = pt.get("id", "")
        muestras_por_punto.setdefault(pt_id, []).append(m)

    # Construir opciones: seleccionar por punto
    opciones_punto_insitu: dict[str, str] = {}
    for pt_id, ms in muestras_por_punto.items():
        pt = (ms[0].get("puntos_muestreo") or {})
        pt_name = pt.get("nombre", "")
        pt_code = pt.get("codigo", "")
        n_muestras = len(ms)
        codigos = ", ".join(m["codigo"] for m in ms)
        if n_muestras >= 3:
            label = f"{pt_code} — {pt_name} ({n_muestras} muestras: {codigos})"
        else:
            label = f"{ms[0]['codigo']} — {pt_name}"
        opciones_punto_insitu[label] = pt_id

    # Si veníamos del flujo "Registrar mediciones in-situ ahora", pre-seleccionar
    # el punto cuya muestra acaba de crearse (solo en el primer render tras el puente)
    if muestra_prefill and "insitu_punto" not in st.session_state:
        for _label, _pid in opciones_punto_insitu.items():
            if any(m["id"] == muestra_prefill for m in muestras_por_punto[_pid]):
                st.session_state["insitu_punto"] = _label
                break

    label_punto = st.selectbox("Punto de muestreo", list(opciones_punto_insitu.keys()), key="insitu_punto")
    punto_id_sel = opciones_punto_insitu[label_punto]
    muestras_punto = muestras_por_punto[punto_id_sel]

    # Modo columna: la fuente de verdad es el campo modo_muestreo de la BD
    # (o el grupo_profundidad si la migración 005 no se aplicó).
    # Antes se usaba `len(muestras_punto) >= 3` como heurística — fallaba si
    # el técnico solo había cargado 2 profundidades parcialmente.
    es_columna = any(
        m.get("modo_muestreo") == "columna" or m.get("grupo_profundidad")
        for m in muestras_punto
    )

    # Muestra principal (primera del grupo)
    muestra_sel = muestras_punto[0]
    muestra_id = muestra_sel["id"]
    punto_info = muestra_sel.get("puntos_muestreo") or {}

    if es_columna:
        # Ordenar por profundidad_tipo si existe, sino por código
        def _sort_prof(m):
            tp = m.get("profundidad_tipo", "")
            return {"S": 0, "M": 1, "F": 2}.get(tp, 9)
        muestras_punto.sort(key=_sort_prof)
        # Mostrar info
        prof_total = muestras_punto[0].get("profundidad_total", "—")
        prof_secchi = muestras_punto[0].get("profundidad_secchi", "—")
        st.info(
            f"Muestreo en columna de agua — "
            f"Prof. total: {prof_total} m | Secchi: {prof_secchi} m | "
            f"{len(muestras_punto)} muestras"
        )

    # Cargar datos existentes y límites ECA (de la muestra principal)
    existentes = get_mediciones_insitu(muestra_id)
    limites = get_limites_insitu(muestra_id)

    # ── Equipos de medición (dropdown compartido con cadena) ─────────────
    section_header("Equipos de medición", "microscope")

    equipos_disponibles = get_equipos_registrados()
    opciones_eq = [f"{e['codigo']} — {e['nombre']}" for e in equipos_disponibles]

    # Precargar equipos previamente usados en esta muestra
    equipos_previos = []
    if existentes:
        primer_med = next(iter(existentes.values()), {})
        eq_prev = primer_med.get("equipo", "")
        if eq_prev:
            equipos_previos = [o for o in opciones_eq if eq_prev in o]

    # Selección de equipos (máx 4)
    equipos_sel = st.multiselect(
        "Seleccionar equipos utilizados (máx. 4)",
        opciones_eq,
        default=equipos_previos,
        max_selections=4,
        key=f"insitu_equipos_{muestra_id[:8]}",
    )

    # Opción para registrar un nuevo equipo
    _widget_nuevo_equipo(f"insitu_{muestra_id[:8]}")

    # Extraer nombre del equipo para guardar
    equipo_nombre = ", ".join(equipos_sel) if equipos_sel else ""
    n_serie = ""
    if equipos_sel:
        n_serie = equipos_sel[0].split(" — ")[0] if " — " in equipos_sel[0] else ""

    st.divider()

    # ── Determinar muestras a llenar in situ ────────────────────────────
    # Si es columna (3+ muestras del mismo punto), tabla unificada. Si no, single.
    if es_columna and len(muestras_punto) >= 3:
        _render_insitu_columna(muestras_punto, limites, equipo_nombre, n_serie)
    else:
        _render_insitu_single(muestra_id, existentes, limites, equipo_nombre, n_serie)


def _render_insitu_single(
    muestra_id: str,
    existentes: dict,
    limites: dict,
    equipo_nombre: str,
    n_serie: str,
    key_suffix: str = "",
) -> None:
    """Renderiza el formulario in situ para una sola muestra."""
    n_guardados = len(existentes)
    if n_guardados > 0:
        st.caption(f"*{n_guardados} parámetro(s) guardado(s)*")
    else:
        st.caption("*Sin datos guardados*")

    cols_header = st.columns([2, 2, 1, 1, 1])
    cols_header[0].markdown("**Parámetro**")
    cols_header[1].markdown("**Valor**")
    cols_header[2].markdown("**Unidad**")
    cols_header[3].markdown("**Lím. ECA**")
    cols_header[4].markdown("**Estado**")

    valores: dict[str, float | None] = {}
    key_prefix = f"{muestra_id[:8]}{key_suffix}"

    # Cargar parámetros una sola vez por render (antes se llamaba 2 veces)
    _parametros_insitu = get_parametros_insitu()

    for p in _parametros_insitu:
        clave = p["clave"]
        existente = existentes.get(clave, {})
        lim = limites.get(clave, {})
        lim_max = lim.get("valor_maximo")
        lim_min = lim.get("valor_minimo")

        cols = st.columns([2, 2, 1, 1, 1])
        cols[0].markdown(f"**{p['nombre']}**")

        # Castear todo a float para evitar StreamlitMixedNumericTypesError
        # (los rangos vienen de NUMERIC en BD y pueden interpretarse como int)
        _val_in   = existente.get("valor")
        _val_in   = float(_val_in)   if _val_in   is not None else None
        _min_in   = p.get("valor_minimo")
        _min_in   = float(_min_in)   if _min_in   is not None else None
        _max_in   = p.get("valor_maximo")
        _max_in   = float(_max_in)   if _max_in   is not None else None
        val = cols[1].number_input(
            p["nombre"],
            value=_val_in,
            min_value=_min_in,
            max_value=_max_in,
            step=0.01,
            format="%.4g",
            label_visibility="collapsed",
            placeholder="No medido",
            key=f"insitu_{key_prefix}_{clave}",
        )
        valores[clave] = val

        cols[2].caption(p["unidad"])

        if lim_max is not None and lim_min is not None:
            cols[3].caption(f"{lim_min} – {lim_max}")
        elif lim_max is not None:
            cols[3].caption(f"≤ {lim_max}")
        elif lim_min is not None:
            cols[3].caption(f"≥ {lim_min}")
        else:
            cols[3].caption("—")

        sem = _semaforo_insitu(valores[clave], lim_min, lim_max)
        cols[4].markdown(
            f'<div style="font-size:1.6em; line-height:1;">{sem}</div>',
            unsafe_allow_html=True,
        )

    st.divider()

    if st.button("Guardar mediciones in situ", type="primary", icon=":material/save:", key=f"btn_insitu{key_suffix}"):
        mediciones = [
            {
                "parametro": p["clave"],
                "valor":     valores[p["clave"]],
                "unidad":    p["unidad"],
            }
            for p in _parametros_insitu
            if valores.get(p["clave"]) is not None
        ]

        if not mediciones:
            st.warning("Ingresa al menos un valor.")
        else:
            ok, errores = registrar_insitu(muestra_id, mediciones, equipo_nombre, n_serie)
            if errores:
                st.error(f"Guardados {ok}/{len(mediciones)}. Errores:")
                for e in errores:
                    st.caption(f"• {e}")
            else:
                success_check_overlay(f"{ok} medición(es) guardadas")
                st.rerun()


def _render_insitu_columna(
    muestras_prof: list[dict],
    limites: dict,
    equipo_nombre: str,
    n_serie: str,
) -> None:
    """Tabla unificada con columnas de valor por profundidad (S/M/F)."""
    # Limitar a 3 muestras (S/M/F)
    muestras_prof = muestras_prof[:3]
    # Asignar tipo S/M/F si no viene de la BD
    fallback_tipos = ["S", "M", "F"]
    # Cargar existentes para cada profundidad
    datos_por_prof: list[tuple[dict, dict, str]] = []  # (muestra, existentes, tipo)
    for i, m in enumerate(muestras_prof):
        tp = m.get("profundidad_tipo") or (fallback_tipos[i] if i < 3 else "?")
        mid = m["id"]
        existentes_m = get_mediciones_insitu(mid)
        datos_por_prof.append((m, existentes_m, tp))

    # Construir headers con profundidad en metros + indicador guardado
    col_headers = ["**Parámetro**"]
    guardado_labels = [""]
    for m, existentes_m, tp in datos_por_prof:
        prof_val = m.get("profundidad_valor", "")
        label = PROFUNDIDAD_LABELS.get(tp, tp)
        if prof_val:
            col_headers.append(f"**{label} ({prof_val} m)**")
        else:
            col_headers.append(f"**{label}**")
        # Check si tiene datos guardados
        n_guardados = len(existentes_m)
        if n_guardados > 0:
            guardado_labels.append(f"*{n_guardados} param. guardados*")
        else:
            guardado_labels.append("*Sin datos*")
    col_headers += ["**Unidad**", "**Lím. ECA**"]
    guardado_labels += ["", ""]

    n_prof = len(datos_por_prof)
    col_widths = [2] + [2] * n_prof + [1, 1]
    header_cols = st.columns(col_widths)
    for i, h in enumerate(col_headers):
        header_cols[i].markdown(h)
    # Fila de estado guardado
    status_cols = st.columns(col_widths)
    for i, gl in enumerate(guardado_labels):
        if gl:
            status_cols[i].caption(gl)

    # Almacenar valores por profundidad
    valores_por_prof: list[dict[str, float | None]] = [{} for _ in range(n_prof)]

    # Una sola query por render (antes se llamaba 2 veces)
    _parametros_insitu_col = get_parametros_insitu()

    for p in _parametros_insitu_col:
        clave = p["clave"]
        lim = limites.get(clave, {})
        lim_max = lim.get("valor_maximo")
        lim_min = lim.get("valor_minimo")

        cols = st.columns(col_widths)
        cols[0].markdown(f"**{p['nombre']}**")

        # Un input por profundidad — todos los argumentos numéricos en float
        # para evitar StreamlitMixedNumericTypesError
        _min_p = p.get("valor_minimo")
        _min_p = float(_min_p) if _min_p is not None else None
        _max_p = p.get("valor_maximo")
        _max_p = float(_max_p) if _max_p is not None else None
        for j, (m, existentes_m, tp) in enumerate(datos_por_prof):
            existente = existentes_m.get(clave, {})
            _val_e = existente.get("valor")
            _val_e = float(_val_e) if _val_e is not None else None
            val = cols[1 + j].number_input(
                f"{p['nombre']} ({tp})",
                value=_val_e,
                min_value=_min_p,
                max_value=_max_p,
                step=0.01,
                format="%.4g",
                label_visibility="collapsed",
                placeholder="—",
                key=f"insitu_{m['id'][:8]}_{tp}_{clave}",
            )
            valores_por_prof[j][clave] = val

        # Unidad
        cols[1 + n_prof].caption(p["unidad"])

        # Límite ECA
        if lim_max is not None and lim_min is not None:
            cols[2 + n_prof].caption(f"{lim_min} – {lim_max}")
        elif lim_max is not None:
            cols[2 + n_prof].caption(f"≤ {lim_max}")
        elif lim_min is not None:
            cols[2 + n_prof].caption(f"≥ {lim_min}")
        else:
            cols[2 + n_prof].caption("—")

    st.divider()

    if st.button("Guardar mediciones in situ (3 profundidades)", type="primary", icon=":material/save:", key="btn_insitu_col"):
        total_ok = 0
        total_err: list[str] = []
        for j, (m, _, tp) in enumerate(datos_por_prof):
            mediciones = [
                {
                    "parametro": p["clave"],
                    "valor":     valores_por_prof[j][p["clave"]],
                    "unidad":    p["unidad"],
                }
                for p in _parametros_insitu_col
                if valores_por_prof[j].get(p["clave"]) is not None
            ]
            if mediciones:
                ok, errores = registrar_insitu(m["id"], mediciones, equipo_nombre, n_serie)
                total_ok += ok
                total_err.extend(errores)

        if total_err:
            st.error(f"Guardados {total_ok} valores. Errores:")
            for e in total_err:
                st.caption(f"• {e}")
        elif total_ok > 0:
            success_check_overlay(f"{total_ok} medición(es) guardadas en {n_prof} profundidades")
            st.rerun()
        else:
            st.warning("Ingresa al menos un valor.")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Cadena de custodia
# ─────────────────────────────────────────────────────────────────────────────

def _render_custodia(campana_id: str) -> None:
    section_header("Recepción en laboratorio", "archive")
    st.caption(
        "Avanza el estado de cada muestra individual: registra recepción "
        "en lab, cambia a 'analizada', etc. Para generar el documento oficial "
        "PDF/Excel ve al tab **Documento CC**."
    )

    muestras = _muestras_por_campana_cached(campana_id)
    if not muestras:
        st.info("No hay muestras en esta campaña.")
        return

    # ── Tabla resumen de estados ─────────────────────────────────────────
    filas = [
        _fila_muestra(
            m,
            campos=("codigo", "punto", "fecha", "hora", "tipo", "estado", "tecnico"),
        )
        for m in muestras
    ]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    st.divider()

    # ── Selector de muestra para acciones ────────────────────────────────
    opciones_m = {}
    for m in muestras:
        prof_tipo = m.get("profundidad_tipo")
        prof_suf = f" {PROFUNDIDAD_SUFIJOS[prof_tipo]}" if prof_tipo in PROFUNDIDAD_SUFIJOS else ""
        label = f"{m['codigo']}{prof_suf} — [{ETIQUETA_ESTADO_MUESTRA.get(m.get('estado',''), '')}]"
        opciones_m[label] = m
    label_sel = st.selectbox(
        "Seleccionar muestra para acción",
        list(opciones_m.keys()),
        key="custodia_muestra",
    )
    muestra = opciones_m[label_sel]
    estado_actual = muestra.get("estado", "")

    col_a, col_b = st.columns(2)

    # ── Avanzar estado (excepto en_transporte → en_laboratorio que usa recepción) ──
    with col_a:
        siguiente = TRANSICIONES_MUESTRA.get(estado_actual)
        if siguiente and siguiente != "en_laboratorio":
            etiq = ETIQUETA_ESTADO_MUESTRA.get(siguiente, siguiente)
            if st.button(f"Avanzar a → {etiq}", key="btn_avanzar_muestra", type="primary"):
                try:
                    actualizar_estado_muestra(muestra["id"], siguiente)
                    st.success(f"Estado actualizado a {etiq}.")
                    st.rerun()
                except TransicionMuestraError as exc:
                    st.error(str(exc))
        elif estado_actual == "analizada":
            st.success("Muestra ya analizada.")

    # ── Recepción en laboratorio (transporte → laboratorio) ──────────────
    with col_b:
        if estado_actual == "en_transporte":
            section_header("Recepción en laboratorio", "archive")

    if estado_actual == "en_transporte":
        with st.form("form_recepcion", clear_on_submit=False):
            sesion = st.session_state.get("sesion")
            st.markdown(f"Receptor: **{sesion.nombre_completo if sesion else '—'}**")

            estado_frasco = st.selectbox(
                "Estado del frasco",
                ESTADOS_FRASCO,
                format_func=lambda e: e.replace("_", " ").capitalize(),
            )
            obs_recepcion = st.text_input(
                "Observaciones de recepción",
                placeholder="Temperatura de llegada, integridad del sello...",
            )

            btn_recibir = st.form_submit_button("Registrar recepción", type="primary")

        if btn_recibir:
            receptor_id = _get_usuario_interno_id(sesion.uid) if sesion else None
            if not receptor_id:
                st.error(
                    "Tu usuario no tiene un perfil interno asociado. "
                    "Contacta al administrador para que te dé de alta en la tabla `usuarios` "
                    "antes de recibir muestras (la cadena de custodia exige identificar al receptor)."
                )
            else:
                try:
                    recibir_en_laboratorio(
                        muestra["id"],
                        receptor_id,
                        estado_frasco,
                        obs_recepcion,
                    )
                    success_check_overlay("Muestra recibida en laboratorio")
                    # Marcar para mostrar el banner de "ir al documento CC"
                    st.session_state["_recepcion_recien_hecha"] = campana_id
                    st.rerun()
                except TransicionMuestraError as exc:
                    st.error(str(exc))
                except ValueError as exc:
                    st.error(str(exc))

    # ── Puente al Documento CC ───────────────────────────────────────────
    # Cuento muestras listas para cadena (estado >= en_laboratorio)
    n_listas = sum(
        1 for m in muestras
        if m.get("estado") in ("en_laboratorio", "analizada")
    )
    if n_listas > 0:
        st.divider()
        col_resumen, col_cta = st.columns([3, 2])
        with col_resumen:
            inline_note(
                f"<b>{n_listas} muestra(s)</b> ya están en laboratorio o analizadas — "
                "puedes generar el documento de cadena de custodia oficial.",
                tipo="info",
            )
        with col_cta:
            if st.button(
                "Generar Documento CC para esta campaña",
                key="btn_goto_cadena_cc",
                type="primary",
                icon=":material/description:",
                use_container_width=True,
            ):
                # La campaña ya es global — solo señalizamos el "salto" para
                # mostrar el banner contextual en el tab Documento CC.
                st.session_state["_jump_to_cadena"] = True
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 4 — Listado general
# ─────────────────────────────────────────────────────────────────────────────

def _render_listado(campana_id: str) -> None:
    section_header("Listado de muestras", "list")

    # Filtros
    fc1, fc2 = st.columns(2)
    with fc1:
        opciones_estado = ["Todos"] + [
            ETIQUETA_ESTADO_MUESTRA.get(e, e) for e in ESTADOS_MUESTRA
        ]
        sel_estado = st.selectbox("Filtrar por estado", opciones_estado, key="list_estado")
        filtro_estado = None
        for e in ESTADOS_MUESTRA:
            if ETIQUETA_ESTADO_MUESTRA.get(e, e) == sel_estado:
                filtro_estado = e
                break

    with fc2:
        puntos = get_puntos_de_campana_activa(campana_id)
        opciones_punto = {"Todos": None}
        opciones_punto.update({
            f"{p['codigo']} — {p['nombre']}": p["id"] for p in puntos
        })
        sel_punto = st.selectbox("Filtrar por punto", list(opciones_punto.keys()), key="list_punto")
        filtro_punto = opciones_punto[sel_punto]

    muestras = get_muestras_por_campana(campana_id, filtro_estado, filtro_punto)

    if not muestras:
        st.info("No hay muestras con los filtros seleccionados.")
        return

    st.markdown(f"**{len(muestras)} muestra(s)**")

    filas = [
        _fila_muestra(
            m,
            campos=("codigo", "punto", "profundidad", "fecha", "hora", "tipo", "estado"),
        )
        for m in muestras
    ]
    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    # ── Editar / Eliminar muestra ──────────────────────────────────────────
    st.divider()
    opciones_edit = {f"{m['codigo']}": m for m in muestras}
    sel_edit = st.selectbox("Administrar muestra", list(opciones_edit.keys()), key="list_edit_muestra")
    muestra_sel = opciones_edit[sel_edit]

    # Antes había aquí un form parcial que solo dejaba editar 3 campos
    # (tipo, clima, obs). Eso confundía al usuario que asumía que el resto
    # no era editable. Ahora un único botón remite al tab Registro, que
    # detecta la muestra existente y precarga TODOS los campos.
    inline_note(
        "Para editar esta muestra (fecha, hora, técnico, profundidades, etc.) "
        "ve al tab <b>Registro</b> — selecciona la misma campaña y punto y "
        "se cargarán todos los datos para corrección.",
        tipo="info",
    )

    if muestra_sel.get("estado") == "recolectada":
        with st.expander("Eliminar muestra", expanded=False, icon=":material/delete:"):
            st.warning("Solo se pueden eliminar muestras en estado 'recolectada' y sin resultados de laboratorio.")
            if st.button("Eliminar muestra permanentemente", key="btn_eliminar_muestra", type="primary"):
                try:
                    eliminar_muestra(muestra_sel["id"])
                    _invalidar_muestras_cache(campana_id)
                    st.success("Muestra eliminada.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tab 5 — Cadena de custodia oficial (Excel/PDF)
# ─────────────────────────────────────────────────────────────────────────────

# Lista fija de receptores autorizados para la cadena de custodia (solo estos
# dos nombres pueden firmar como receptor en el laboratorio).
_RECEPTORES_CADENA = ["Alfonso Torres", "Jean Pierre Llerena"]

# Supervisor/Jefe único para toda la plataforma.
_SUPERVISOR_CADENA = "Ing. Ana Lucía Paz Alcázar"


def _render_cadena_custodia(campana_id: str) -> None:
    section_header("Documento de Cadena de Custodia — Formato AUTODEMA", "clipboard")
    st.caption(
        "Genera el documento oficial CC-MON-01 (Excel y PDF) a partir de las "
        "muestras recibidas en laboratorio. Para cambiar el estado de una "
        "muestra usa el tab **Recepción en Lab**."
    )

    # Si el usuario llegó desde el botón "Generar Documento CC" del tab
    # Recepción, mostrar acuse contextual
    if st.session_state.pop("_jump_to_cadena", False):
        inline_note(
            "Llegaste desde el tab Recepción en Lab. La campaña ya está "
            "pre-seleccionada — completa los datos y genera el documento.",
            tipo="success",
        )

    # Obtener info de la campaña para auto-poblar campos
    camp_info = _get_campana_info(campana_id)
    resp_campo = camp_info.get("responsable_campo") or ""
    # Abreviar cada responsable de campo
    muestreadores = [_abreviar_nombre(n.strip()) for n in resp_campo.split(",") if n.strip()]
    muestreador_auto = ", ".join(muestreadores)

    # Auto-copiar clima y nivel desde muestras de la campaña
    muestras_camp = _muestras_por_campana_cached(campana_id)
    obs_auto_parts = []
    temp_transporte_vals = []
    for m in muestras_camp:
        if m.get("clima"):
            obs_auto_parts.append(f"Clima: {m['clima']}")
        if m.get("nivel_agua"):
            obs_auto_parts.append(f"Nivel embalse: {m['nivel_agua']}")
        if m.get("temperatura_transporte") is not None:
            temp_transporte_vals.append(m["temperatura_transporte"])
        break  # Tomar del primer registro como referencia
    obs_auto = "; ".join(dict.fromkeys(obs_auto_parts))  # dedup
    temp_transporte_auto = temp_transporte_vals[0] if temp_transporte_vals else None

    # ── Configuración del documento ──────────────────────────────────────
    with st.expander("Configuración del documento", expanded=False):
        # Cargar config persistida si existe (sino, default)
        cfg = config_para_campana(campana_id)

        # Campaña (read-only, reemplaza "Lugar de monitoreo")
        campana_label = f"{camp_info.get('nombre', '')} [{camp_info.get('codigo', '')}]"
        st.markdown(f"**Campaña:** {campana_label}")

        dc1, dc2, dc3 = st.columns(3)
        with dc1:
            cfg["codigo_documento"] = st.text_input(
                "Código documento", value="CC-MON-01", key="cc_codigo_doc",
            )
        with dc2:
            cfg["revision"] = st.text_input(
                "Revisión", value="03", key="cc_revision",
            )
        with dc3:
            cfg["urgencia"] = st.selectbox(
                "Urgencia", ["Regular", "Alta"], key="cc_urgencia",
            )

        cfg["muestreo_por"] = st.radio(
            "Muestreo realizado por",
            ["laboratorio", "otro"],
            format_func=lambda x: "Personal de laboratorio" if x == "laboratorio" else "Otro",
            horizontal=True,
            key="cc_muestreo_por",
        )

        nc1, nc2, nc3 = st.columns(3)
        with nc1:
            # Muestreador: se toma automáticamente de los responsables de campo
            # definidos al crear la campaña. No es editable aquí — si hay que
            # cambiarlo, hacerlo en la página Campañas.
            st.text_input(
                "Nombre muestreador",
                value=muestreador_auto,
                disabled=True,
                key="cc_muestreador_display",
                help="Se toma de los responsables de campo definidos en la campaña.",
            )
            cfg["nombre_muestreador"] = muestreador_auto
        with nc2:
            cfg["nombre_receptor"] = st.selectbox(
                "Nombre receptor",
                _RECEPTORES_CADENA,
                index=0,
                key="cc_receptor",
            )
        with nc3:
            st.text_input(
                "Supervisor/Jefe",
                value=_SUPERVISOR_CADENA,
                disabled=True,
                key="cc_supervisor_display",
                help="Supervisor fijo para toda la plataforma.",
            )
            cfg["nombre_supervisor"] = _SUPERVISOR_CADENA

        # Fecha y hora de recepción
        fr1, fr2 = st.columns(2)
        with fr1:
            fecha_recepcion = st.date_input(
                "Fecha de recepción", value=date.today(), key="cc_fecha_recep",
            )
        with fr2:
            hora_recepcion = st.time_input(
                "Hora de recepción", value=time(12, 0), key="cc_hora_recep",
            )

        # Sobrescribir el lugar con la campaña y agregar auto-obs
        cfg["campana_label"] = campana_label
        cfg["observaciones_generales"] = st.text_input(
            "Observaciones generales",
            value=obs_auto,
            key="cc_obs_generales",
        )
        if temp_transporte_auto is not None:
            cfg["temperatura_transporte"] = temp_transporte_auto

    # Preservación: cada parámetro trae su propio preservante desde la
    # configuración del módulo Parámetros. El documento lo resuelve
    # automáticamente al generarse, por eso dejamos todos los preservantes
    # disponibles (el servicio decide qué marcar según los params activos).
    cfg["preservacion"] = {
        "HNO3":   True, "H2SO4": True, "HCl":    True,
        "Lugol":  True, "Formol": True, "S/P":   True,
    }

    # ── Condiciones de la muestra ─────────────────────────────────────────
    with st.expander("Condiciones de la muestra", expanded=False):
        cc1, cc2, cc3 = st.columns(3)
        cond = cfg["condiciones"]
        with cc1:
            cond["refrigerado"] = st.checkbox("Refrigerado", value=True, key="cc_refrig")
            cond["congelado"] = st.checkbox("Congelado", value=False, key="cc_cong")
        with cc2:
            cond["icepack"] = st.checkbox("Icepack", value=True, key="cc_ice")
            cond["caja_conservadora"] = st.checkbox("Caja conservadora", value=False, key="cc_caja")
        with cc3:
            cond["temp_ambiente"] = st.checkbox("Temperatura ambiente", value=False, key="cc_temp")
            cond["hielo_potable"] = st.checkbox("Hielo calidad potable", value=False, key="cc_hielo")

    # ── Parámetros de laboratorio (definidos en la Campaña) ──────────────
    # La selección de parámetros la decide el usuario al crear/editar la
    # campaña. Aquí solo se muestra un resumen de lo que saldrá marcado en
    # el documento — no se permite editarlo en esta pantalla.
    sel_camp = get_parametros_lab_campana(campana_id)
    claves_camp = sel_camp["parametros_lab"]
    extras_camp = sel_camp["parametros_lab_extra"]
    if claves_camp:
        cfg["parametros_lab"] = claves_camp
    # Si la campaña no tiene selección explícita, se marcan todos por defecto
    # (comportamiento de config_default).
    cfg["parametros_lab_extra"] = extras_camp or []

    with st.expander("Parámetros de laboratorio (definidos en la campaña)", expanded=False):
        param_list = list(get_parametros_lab_cadena())
        seleccion_set = set(
            claves_camp if claves_camp else [p["clave"] for p in param_list]
        )
        marcados = [p["nombre"] for p in param_list if p["clave"] in seleccion_set]
        st.caption(
            f"{len(marcados)} de {len(param_list)} parámetros marcados "
            f"+ {len(extras_camp)} adicional(es). "
            f"Para modificar, abre la página **Campañas** y edita esta campaña."
        )
        if marcados:
            st.markdown("**Marcados:** " + ", ".join(marcados))
        no_marcados = [p["nombre"] for p in param_list if p["clave"] not in seleccion_set]
        if no_marcados:
            st.caption("No marcados: " + ", ".join(no_marcados))
        if extras_camp:
            st.markdown("**Adicionales:** " + ", ".join(extras_camp))

    # ── Equipos (compartido con In situ) ─────────────────────────────────
    with st.expander("Equipos utilizados", expanded=False):
        equipos_disp = get_equipos_registrados()
        opciones_eq_cc = [f"{e['codigo']} — {e['nombre']}" for e in equipos_disp]

        # Preseleccionar los equipos por defecto
        defaults_cc = [
            o for o in opciones_eq_cc
            for ed in EQUIPOS_DEFAULT
            if ed["codigo"] in o
        ]

        equipos_sel_cc = st.multiselect(
            "Seleccionar equipos (máx. 4)",
            opciones_eq_cc,
            default=defaults_cc,
            max_selections=4,
            key="cc_equipos_sel",
        )

        # Convertir selección a formato esperado por cfg
        equipos = []
        for sel in equipos_sel_cc:
            parts = sel.split(" — ", 1)
            equipos.append({
                "codigo": parts[0].strip() if len(parts) > 0 else "",
                "nombre": parts[1].strip() if len(parts) > 1 else sel,
            })

        # Registrar nuevo equipo inline (usa helper compartido)
        _widget_nuevo_equipo("cc")

        cfg["equipos"] = equipos if equipos else EQUIPOS_DEFAULT

    # ── Botones de descarga ──────────────────────────────────────────────
    st.divider()
    section_header("Descargar cadena de custodia", "download")

    # Persistir configuración para reutilizar en próximas generaciones
    sesion = st.session_state.get("sesion")
    col_save, _ = st.columns([1, 3])
    with col_save:
        if st.button("Guardar configuración para esta campaña",
                     key="btn_cc_save_cfg", icon=":material/save:", use_container_width=True):
            uid = sesion.uid if sesion else None
            if guardar_config_persistida(campana_id, cfg, usuario_id=uid):
                success_check_overlay("Configuración guardada")
                st.caption("Se cargará automáticamente la próxima vez.")
            else:
                st.warning(
                    "No se pudo guardar (¿migración 006 aplicada?). "
                    "La configuración seguirá funcionando solo en esta sesión."
                )

    dc1, dc2 = st.columns(2)

    with dc1:
        _generate_download_widget(
            label_btn="Generar Excel",
            label_dl="Descargar Excel",
            generate_fn=lambda cid, c=cfg: generar_excel_cadena(cid, c),
            campana_id=campana_id,
            state_key="cc_excel",
            file_name=f"cadena_custodia_{cfg['codigo_documento']}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            btn_kwargs={"type": "primary", "use_container_width": True},
        )

    with dc2:
        _generate_download_widget(
            label_btn="Generar PDF",
            label_dl="Descargar PDF",
            generate_fn=lambda cid, c=cfg: generar_pdf_cadena(cid, c),
            campana_id=campana_id,
            state_key="cc_pdf",
            file_name=f"cadena_custodia_{cfg['codigo_documento']}.pdf",
            mime="application/pdf",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tab — Ficha de campo (generación DOCX/PDF)
# ─────────────────────────────────────────────────────────────────────────────

def _render_ficha_campo(campana_id: str) -> None:
    section_header("Fichas de Identificación del Punto de Monitoreo", "file")
    st.caption("Genera todas las fichas de una campaña en un solo documento Word")

    muestras = _muestras_por_campana_cached(campana_id)
    if not muestras:
        st.info("No hay muestras en esta campaña.")
        return

    # Resumen de puntos (deduplicar — 1 ficha por punto, no por muestra)
    puntos_vistos: set[str] = set()
    puntos_info: list[str] = []
    for m in muestras:
        pt = m.get("puntos_muestreo") or {}
        pt_id = pt.get("id", m.get("codigo", ""))
        if pt_id not in puntos_vistos:
            puntos_vistos.add(pt_id)
            pt_nombre = pt.get("nombre", m.get("codigo", ""))
            pt_codigo = pt.get("codigo", "")
            puntos_info.append(f"{pt_nombre} ({pt_codigo})" if pt_codigo else pt_nombre)
    st.info(f"Se generarán **{len(puntos_info)}** fichas: {', '.join(puntos_info)}")

    # ── Parámetros definidos en la campaña ───────────────────────────────
    # Los parámetros que aparecerán marcados en la ficha se deciden al crear
    # o editar la campaña (página Campañas). Aquí solo se muestra el resumen.
    sel_camp_ficha = get_parametros_lab_campana(campana_id)
    claves_ficha = sel_camp_ficha["parametros_lab"]
    param_list_ficha = list(get_parametros_lab_cadena())
    if claves_ficha:
        # Convertir claves (lowercase) → códigos (P###) que espera el servicio
        codigos_por_clave = {p["clave"]: p["codigo"] for p in param_list_ficha}
        params_ficha_lab = [codigos_por_clave[c] for c in claves_ficha if c in codigos_por_clave]
    else:
        # Sin selección explícita = todos
        params_ficha_lab = [p["codigo"] for p in param_list_ficha]

    with st.expander("Parámetros de laboratorio (definidos en la campaña)", expanded=False):
        nombres_marcados = [
            p["nombre"] for p in param_list_ficha
            if p["codigo"] in set(params_ficha_lab)
        ]
        st.caption(
            f"{len(nombres_marcados)} de {len(param_list_ficha)} parámetros "
            f"aparecerán marcados en la ficha. Para modificar, abre la página "
            f"**Campañas** y edita esta campaña."
        )
        if nombres_marcados:
            st.markdown("**Marcados:** " + ", ".join(nombres_marcados))

    st.divider()

    # Determinar código de campaña (para nombre del archivo) ahora — el helper
    # lo usa al construir el nombre del download_button.
    campana_info = next(
        (m.get("campanas") or {} for m in muestras if m.get("campanas")), {}
    )
    campana_codigo = campana_info.get("codigo", "campana")

    _generate_download_widget(
        label_btn=f"Generar {len(muestras)} fichas DOCX",
        label_dl="Descargar fichas DOCX",
        generate_fn=lambda cid, p=params_ficha_lab: generar_docx_fichas(
            cid, params_seleccionados=p,
        ),
        campana_id=campana_id,
        state_key="fichas_docx",
        file_name=f"fichas_campo_{campana_codigo}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        btn_kwargs={"type": "primary", "use_container_width": True},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("administrador")
def main() -> None:
    aplicar_estilos()
    top_nav()
    # El cache de muestras vive solo dentro de un mismo render — al inicio
    # se limpia para que cualquier rerun (después de crear/editar/eliminar)
    # vea datos frescos. Dentro del render los 5 tabs comparten la query.
    st.session_state.pop("_muestras_cache", None)
    page_header("Muestras de Campo", "Registro, mediciones in situ y cadena de custodia")

    # Selector único de campaña — todos los tabs operan sobre esta misma
    # campaña. Cada tab valida internamente si su acción es compatible con
    # el estado actual.
    campana_id = _global_campaign_selector()
    if not campana_id:
        return

    # Orden lógico del flujo operativo:
    #   campo (Registro → In situ)
    #   transición a lab (Recepción en Lab)
    #   reportes (Documento CC, Ficha, Listado)
    tab_reg, tab_insitu, tab_custodia, tab_cadena, tab_ficha, tab_lista = st.tabs([
        "Registro",
        "In situ",
        "Recepción en Lab",
        "Documento CC",
        "Ficha de Campo",
        "Listado",
    ])

    with tab_reg:
        _render_registro(campana_id)

    with tab_insitu:
        _render_insitu(campana_id)

    with tab_custodia:
        _render_custodia(campana_id)

    with tab_lista:
        _render_listado(campana_id)

    with tab_cadena:
        _render_cadena_custodia(campana_id)

    with tab_ficha:
        _render_ficha_campo(campana_id)


main()
