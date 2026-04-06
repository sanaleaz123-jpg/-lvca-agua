"""
pages/3_Muestras_Campo.py
Registro de muestras de campo, mediciones in situ,
cadena de custodia, generación de etiquetas QR y cadena de custodia oficial.

Tabs:
    1. Registro — formulario de nueva muestra + descarga QR
    2. In situ  — mediciones de campo con semáforo ECA
    3. Custodia — recepción en lab y transiciones de estado
    4. Listado  — tabla general con filtros y descarga QR
    5. Cadena   — generación de cadena de custodia AUTODEMA (Excel/PDF)

Acceso mínimo: administrador.
"""

from __future__ import annotations

from datetime import date, time

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from database.client import get_admin_client
from services.muestra_service import (
    ESTADOS_MUESTRA,
    ESTADOS_FRASCO,
    ETIQUETA_ESTADO_MUESTRA,
    ETIQUETA_TIPO,
    OPCIONES_CLIMA,
    TIPOS_MUESTRA,
    TRANSICIONES_MUESTRA,
    TransicionMuestraError,
    actualizar_estado_muestra,
    actualizar_muestra,
    crear_muestra,
    eliminar_muestra,
    generar_qr_pdf,
    get_campanas_en_campo,
    get_limites_insitu,
    get_mediciones_insitu,
    get_muestras_por_campana,
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
from services.cadena_custodia_service import (
    EQUIPOS_DEFAULT,
    config_default,
    generar_excel_cadena,
    generar_pdf_cadena,
    get_equipos_registrados,
    registrar_equipo,
)
from services.storage_service import (
    upload_foto_campo,
    get_fotos_campo,
    delete_foto_campo,
)
from services.ficha_campo_service import generar_docx_fichas


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de presentación
# ─────────────────────────────────────────────────────────────────────────────

def _semaforo_insitu(valor, lim_min, lim_max) -> str:
    if valor is None:
        return "⬜"
    if lim_max is None and lim_min is None:
        return "⚪"
    excede = (
        (lim_max is not None and valor > lim_max)
        or (lim_min is not None and valor < lim_min)
    )
    return "🔴" if excede else "🟢"


def _selector_campana_campo(key_prefix: str) -> str | None:
    """Selector de campaña en estado 'en_campo'. Retorna campana_id o None."""
    campanas = get_campanas_en_campo()
    if not campanas:
        st.warning("No hay campañas en estado 'en_campo'. Cambia el estado de una campaña primero.")
        return None
    opciones = {f"{c['codigo']} — {c['nombre']}": c["id"] for c in campanas}
    label = st.selectbox("Campaña activa", list(opciones.keys()), key=f"{key_prefix}_camp")
    return opciones[label]


def _selector_campana_todas(key_prefix: str) -> str | None:
    """Selector de cualquier campaña. Retorna campana_id o None."""
    campanas = get_campanas()
    if not campanas:
        st.warning("No hay campañas registradas.")
        return None
    opciones = {
        f"{c['codigo']} — {c['nombre']} ({c.get('estado', '')})": c["id"]
        for c in campanas
    }
    label = st.selectbox("Campaña", list(opciones.keys()), key=f"{key_prefix}_camp")
    return opciones[label]


# ─────────────────────────────────────────────────────────────────────────────
# Tab 1 — Registro de nueva muestra
# ─────────────────────────────────────────────────────────────────────────────

def _get_campana_info(campana_id: str) -> dict:
    """Obtiene info de la campaña (fecha_inicio, fecha_fin, responsable_campo, etc.)."""
    db = get_admin_client()
    res = (
        db.table("campanas")
        .select("id, codigo, nombre, fecha_inicio, fecha_fin, responsable_campo")
        .eq("id", campana_id)
        .single()
        .execute()
    )
    return res.data or {}


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


def _render_registro() -> None:
    st.markdown("#### Nueva muestra de campo")
    st.caption("Código generado automáticamente: LVCA-YYYY-NNN")

    campana_id = _selector_campana_campo("reg")
    if not campana_id:
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

    usuarios = get_usuarios_campo()
    opciones_puntos = {
        f"{p['codigo']} — {p['nombre']}": p["id"] for p in puntos
    }
    opciones_tecnicos = {
        f"{u['apellido']}, {u['nombre']} ({u.get('institucion','')})": u["id"]
        for u in usuarios
    }

    with st.form("form_nueva_muestra", clear_on_submit=True):
        # ── Ubicación y tipo ─────────────────────────────────────────────
        c1, c2 = st.columns(2)
        with c1:
            punto_label = st.selectbox("Punto de muestreo *", list(opciones_puntos.keys()))
        with c2:
            tipo = st.selectbox(
                "Tipo de muestra",
                TIPOS_MUESTRA,
                format_func=lambda t: ETIQUETA_TIPO.get(t, t),
            )

        # ── Fecha, hora y técnico ────────────────────────────────────────
        c3, c4, c5 = st.columns(3)
        with c3:
            fecha_val = date.today()
            if camp_fecha_ini and camp_fecha_fin:
                fecha_val = max(camp_fecha_ini, min(date.today(), camp_fecha_fin))
            fecha = st.date_input(
                "Fecha de recolección *",
                value=fecha_val,
                min_value=camp_fecha_ini or date(2020, 1, 1),
                max_value=camp_fecha_fin or date(2099, 12, 31),
            )
        with c4:
            hora = st.time_input("Hora de recolección", value=time(9, 0))
        with c5:
            if opciones_tecnicos:
                tecnico_label = st.selectbox(
                    "Técnico de campo",
                    list(opciones_tecnicos.keys()),
                )
            else:
                tecnico_label = None
                st.info("Sin técnicos registrados.")

        # ── Condiciones de campo ─────────────────────────────────────────
        st.markdown("**Condiciones de campo**")
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            clima = st.selectbox("Clima", [""] + OPCIONES_CLIMA)
        with cc2:
            caudal = st.text_input("Caudal estimado", placeholder="Ej: 2.5 m3/s")
        with cc3:
            nivel = st.text_input("Nivel del embalse", placeholder="Ej: normal / alto / bajo")

        # ── Transporte ───────────────────────────────────────────────────
        temp_transporte = st.number_input(
            "Temperatura de transporte (°C)",
            min_value=-10.0,
            max_value=50.0,
            value=4.0,
            step=0.5,
        )

        observaciones = st.text_area(
            "Observaciones de campo",
            placeholder="Notas sobre condiciones, accesibilidad, olores, color del agua...",
        )

        # ── Fotos de campo ───────────────────────────────────────────────
        st.markdown("**Fotos de campo** (máx. 5, JPG o PNG)")
        fotos_subidas = st.file_uploader(
            "Seleccionar fotos",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="reg_fotos_upload",
        )

        submitted = st.form_submit_button(
            "Registrar muestra",
            type="primary",
            use_container_width=True,
        )

    if submitted:
        # Validar fotos
        if fotos_subidas and len(fotos_subidas) > 5:
            st.error("Máximo 5 fotos por muestra.")
            return

        # Advertencias de condiciones vacías (no bloquean)
        if not clima:
            st.warning("El campo 'Clima' está vacío. Se recomienda completarlo.")
        if not nivel.strip():
            st.warning("El campo 'Nivel del embalse' está vacío. Se recomienda completarlo.")

        punto_id = opciones_puntos[punto_label]
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
        }

        with st.spinner("Registrando muestra..."):
            try:
                creada = crear_muestra(datos)
            except Exception as exc:
                st.error(f"Error al crear la muestra: {exc}")
                return

        st.success(f"Muestra **{creada['codigo']}** registrada exitosamente.")

        # ── Subir fotos asociadas ────────────────────────────────────────
        if fotos_subidas:
            for archivo in fotos_subidas:
                try:
                    upload_foto_campo(
                        creada["id"],
                        archivo.getvalue(),
                        archivo.name,
                        archivo.type,
                    )
                except Exception as exc:
                    st.warning(f"Error subiendo {archivo.name}: {exc}")
            st.info(f"{len(fotos_subidas)} foto(s) subida(s).")

        # ── Generar y ofrecer descarga del QR ────────────────────────────
        try:
            pdf_bytes = generar_qr_pdf(creada["id"])
            st.download_button(
                label=f"📥 Descargar etiqueta QR — {creada['codigo']}",
                data=pdf_bytes,
                file_name=f"etiqueta_{creada['codigo']}.pdf",
                mime="application/pdf",
            )
        except ImportError:
            st.warning(
                "Instala qrcode y reportlab para generar etiquetas:\n\n"
                "`pip install qrcode[pil] reportlab`"
            )
        except Exception as exc:
            st.warning(f"No se pudo generar la etiqueta QR: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Tab 2 — Mediciones in situ
# ─────────────────────────────────────────────────────────────────────────────

def _render_insitu() -> None:
    st.markdown("#### Parámetros medidos en campo")

    # Selector de campaña — incluye TODAS las campañas con muestras, no solo 'en_campo'
    # Esto permite registrar mediciones in situ en cualquier campaña activa
    campanas_campo = get_campanas_en_campo()
    # También incluir campañas en_laboratorio (ya tienen muestras que pueden necesitar insitu)
    todas = get_campanas()
    # Combinar: primero en_campo, luego en_laboratorio (sin duplicados)
    ids_campo = {c["id"] for c in campanas_campo}
    campanas_insitu = list(campanas_campo)
    for c in todas:
        if c["id"] not in ids_campo and c.get("estado") in ("en_laboratorio", "en_campo"):
            campanas_insitu.append(c)

    if not campanas_insitu:
        st.warning("No hay campañas activas. Crea o activa una campaña primero.")
        return

    opciones_camp = {
        f"{c['codigo']} — {c['nombre']}": c["id"]
        for c in campanas_insitu
    }
    label_camp = st.selectbox("Campaña activa", list(opciones_camp.keys()), key="insitu_camp")
    campana_id = opciones_camp[label_camp]

    # Seleccionar muestra
    muestras = get_muestras_por_campana(campana_id)
    if not muestras:
        st.info("No hay muestras registradas en esta campaña.")
        return

    opciones_m = {
        f"{m['codigo']} — {(m.get('puntos_muestreo') or {}).get('nombre', '')} "
        f"[{ETIQUETA_ESTADO_MUESTRA.get(m.get('estado',''), m.get('estado',''))}]": m["id"]
        for m in muestras
    }
    label_m = st.selectbox("Muestra", list(opciones_m.keys()), key="insitu_muestra")
    muestra_id = opciones_m[label_m]

    # Información del punto y campaña para contexto
    muestra_sel = next((m for m in muestras if m["id"] == muestra_id), {})
    punto_info = muestra_sel.get("puntos_muestreo") or {}

    # Cargar datos existentes y límites ECA
    existentes = get_mediciones_insitu(muestra_id)
    limites = get_limites_insitu(muestra_id)

    # ── Equipos de medición (dropdown compartido con cadena) ─────────────
    st.markdown("**Equipos de medición**")

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
    with st.expander("Registrar nuevo equipo", expanded=False):
        ne1, ne2 = st.columns(2)
        with ne1:
            nuevo_eq_codigo = st.text_input("Código del equipo", key=f"nuevo_eq_cod_{muestra_id[:8]}")
        with ne2:
            nuevo_eq_nombre = st.text_input("Nombre del equipo", key=f"nuevo_eq_nom_{muestra_id[:8]}")
        if st.button("Agregar equipo", key=f"btn_nuevo_eq_{muestra_id[:8]}"):
            if nuevo_eq_codigo.strip() and nuevo_eq_nombre.strip():
                registrar_equipo(nuevo_eq_codigo.strip(), nuevo_eq_nombre.strip())
                st.success(f"Equipo '{nuevo_eq_nombre.strip()}' registrado.")
                st.rerun()
            else:
                st.error("Completa código y nombre del equipo.")

    # Extraer nombre del equipo para guardar
    equipo_nombre = ", ".join(equipos_sel) if equipos_sel else ""
    n_serie = ""
    if equipos_sel:
        # Extraer código del primer equipo seleccionado como referencia
        n_serie = equipos_sel[0].split(" — ")[0] if " — " in equipos_sel[0] else ""

    st.divider()

    # Tabla de parámetros con semáforo — KEYS scoped por muestra_id
    cols_header = st.columns([2, 2, 1, 1, 1])
    cols_header[0].markdown("**Parámetro**")
    cols_header[1].markdown("**Valor**")
    cols_header[2].markdown("**Unidad**")
    cols_header[3].markdown("**Lím. ECA**")
    cols_header[4].markdown("**Estado**")

    valores: dict[str, float | None] = {}
    # Use muestra_id prefix in keys to prevent stale values across campaigns/muestras
    key_prefix = muestra_id[:8]

    for p in get_parametros_insitu():
        clave = p["clave"]
        existente = existentes.get(clave, {})
        lim = limites.get(clave, {})
        lim_max = lim.get("valor_maximo")
        lim_min = lim.get("valor_minimo")

        cols = st.columns([2, 2, 1, 1, 1])
        cols[0].markdown(f"**{p['nombre']}**")

        val = cols[1].number_input(
            p["nombre"],
            value=existente.get("valor"),
            format="%.4g",
            label_visibility="collapsed",
            key=f"insitu_{key_prefix}_{clave}",
        )
        valores[clave] = val if val != 0.0 or existente.get("valor") == 0.0 else None
        if val == 0.0 and existente.get("valor") is None:
            valores[clave] = None

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
        cols[4].markdown(f"### {sem}")

    st.divider()

    if st.button("💾 Guardar mediciones in situ", type="primary", key="btn_insitu"):
        mediciones = [
            {
                "parametro": p["clave"],
                "valor":     valores[p["clave"]],
                "unidad":    p["unidad"],
            }
            for p in get_parametros_insitu()
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
                st.success(f"{ok} medición(es) guardada(s) correctamente.")
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 3 — Cadena de custodia
# ─────────────────────────────────────────────────────────────────────────────

def _render_custodia() -> None:
    st.markdown("#### Cadena de custodia")

    campana_id = _selector_campana_todas("custodia")
    if not campana_id:
        return

    muestras = get_muestras_por_campana(campana_id)
    if not muestras:
        st.info("No hay muestras en esta campaña.")
        return

    # ── Tabla resumen de estados ─────────────────────────────────────────
    filas = []
    for m in muestras:
        pt = m.get("puntos_muestreo") or {}
        tec = m.get("tecnico") or {}
        filas.append({
            "Código":  m["codigo"],
            "Punto":   f"{pt.get('codigo','')} — {pt.get('nombre','')}",
            "Fecha":   str(m.get("fecha_muestreo", ""))[:10],
            "Tipo":    ETIQUETA_TIPO.get(m.get("tipo_muestra", ""), ""),
            "Estado":  ETIQUETA_ESTADO_MUESTRA.get(m.get("estado", ""), m.get("estado", "")),
            "Técnico": f"{tec.get('nombre','')} {tec.get('apellido','')}".strip() or "—",
        })

    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    st.divider()

    # ── Selector de muestra para acciones ────────────────────────────────
    opciones_m = {
        f"{m['codigo']} — [{ETIQUETA_ESTADO_MUESTRA.get(m.get('estado',''), '')}]": m
        for m in muestras
    }
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
            st.markdown("**Recepción en laboratorio**")

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
            try:
                recibir_en_laboratorio(
                    muestra["id"],
                    receptor_id or "",
                    estado_frasco,
                    obs_recepcion,
                )
                st.success("Muestra recibida en laboratorio.")
                st.rerun()
            except TransicionMuestraError as exc:
                st.error(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tab 4 — Listado general
# ─────────────────────────────────────────────────────────────────────────────

def _render_listado() -> None:
    st.markdown("#### Listado de muestras")

    campana_id = _selector_campana_todas("listado")
    if not campana_id:
        return

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

    filas = []
    for m in muestras:
        pt = m.get("puntos_muestreo") or {}
        filas.append({
            "Código":   m["codigo"],
            "Punto":    f"{pt.get('codigo','')} — {pt.get('nombre','')}",
            "Fecha":    str(m.get("fecha_muestreo", ""))[:10],
            "Hora":     m.get("hora_recoleccion", "—"),
            "Tipo":     ETIQUETA_TIPO.get(m.get("tipo_muestra", ""), ""),
            "Estado":   ETIQUETA_ESTADO_MUESTRA.get(m.get("estado", ""), m.get("estado", "")),
            "Clima":    m.get("clima") or "—",
        })

    st.dataframe(pd.DataFrame(filas), use_container_width=True, hide_index=True)

    # ── Descarga de QR para cualquier muestra ────────────────────────────
    st.divider()
    opciones_qr = {
        f"{m['codigo']}": m["id"] for m in muestras
    }
    sel_qr = st.selectbox("Generar etiqueta QR para", list(opciones_qr.keys()), key="list_qr")
    muestra_id_qr = opciones_qr[sel_qr]

    if st.button("📥 Generar etiqueta QR", key="btn_qr_listado"):
        try:
            pdf_bytes = generar_qr_pdf(muestra_id_qr)
            st.download_button(
                label=f"Descargar etiqueta — {sel_qr}",
                data=pdf_bytes,
                file_name=f"etiqueta_{sel_qr}.pdf",
                mime="application/pdf",
                key="dl_qr_listado",
            )
        except ImportError:
            st.warning("Instala qrcode y reportlab: `pip install qrcode[pil] reportlab`")
        except Exception as exc:
            st.error(f"Error al generar QR: {exc}")

    # ── Editar / Eliminar muestra ──────────────────────────────────────────
    st.divider()
    opciones_edit = {f"{m['codigo']}": m for m in muestras}
    sel_edit = st.selectbox("Administrar muestra", list(opciones_edit.keys()), key="list_edit_muestra")
    muestra_sel = opciones_edit[sel_edit]

    with st.expander("✏️ Editar muestra", expanded=False):
        with st.form("form_editar_muestra", clear_on_submit=False):
            em1, em2 = st.columns(2)
            with em1:
                edit_tipo = st.selectbox(
                    "Tipo de muestra",
                    TIPOS_MUESTRA,
                    index=TIPOS_MUESTRA.index(muestra_sel.get("tipo_muestra", "simple"))
                    if muestra_sel.get("tipo_muestra") in TIPOS_MUESTRA else 0,
                    format_func=lambda t: ETIQUETA_TIPO.get(t, t),
                    key="edit_m_tipo",
                )
            with em2:
                edit_clima = st.selectbox(
                    "Clima",
                    [""] + OPCIONES_CLIMA,
                    index=(OPCIONES_CLIMA.index(muestra_sel["clima"]) + 1)
                    if muestra_sel.get("clima") in OPCIONES_CLIMA else 0,
                    key="edit_m_clima",
                )

            edit_obs = st.text_area(
                "Observaciones de campo",
                value=muestra_sel.get("observaciones_campo") or "",
                key="edit_m_obs",
            )

            edit_submitted = st.form_submit_button("Guardar cambios", type="primary")

        if edit_submitted:
            try:
                actualizar_muestra(muestra_sel["id"], {
                    "tipo_muestra":       edit_tipo,
                    "clima":              edit_clima or None,
                    "observaciones_campo": edit_obs.strip() or None,
                })
                st.success("Muestra actualizada.")
                st.rerun()
            except Exception as exc:
                st.error(f"Error: {exc}")

    if muestra_sel.get("estado") == "recolectada":
        with st.expander("🗑️ Eliminar muestra", expanded=False):
            st.warning("Solo se pueden eliminar muestras en estado 'recolectada' y sin resultados de laboratorio.")
            if st.button("Eliminar muestra permanentemente", key="btn_eliminar_muestra", type="primary"):
                try:
                    eliminar_muestra(muestra_sel["id"])
                    st.success("Muestra eliminada.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Tab 5 — Cadena de custodia oficial (Excel/PDF)
# ─────────────────────────────────────────────────────────────────────────────

_RECEPTORES_CADENA = ["Alfonso Torres E.", "Jean Pierre Madariaga"]
_SUPERVISOR_CADENA = "Ing. Ana Lucía Paz Alcázar"


def _render_cadena_custodia() -> None:
    st.markdown("#### Cadena de Custodia — Formato AUTODEMA")
    st.caption("Formato oficial CC-MON-01 del Laboratorio de Vigilancia y Calidad de Agua")

    campana_id = _selector_campana_todas("cadena")
    if not campana_id:
        return

    # Obtener info de la campaña para auto-poblar campos
    camp_info = _get_campana_info(campana_id)
    resp_campo = camp_info.get("responsable_campo") or ""
    # Abreviar cada responsable de campo
    muestreadores = [_abreviar_nombre(n.strip()) for n in resp_campo.split(",") if n.strip()]
    muestreador_auto = ", ".join(muestreadores)

    # Auto-copiar clima y nivel desde muestras de la campaña
    muestras_camp = get_muestras_por_campana(campana_id)
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
        cfg = config_default()

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
            cfg["nombre_muestreador"] = st.text_input(
                "Nombre muestreador",
                value=muestreador_auto,
                key="cc_muestreador",
            )
        with nc2:
            receptor_idx = 0
            cfg["nombre_receptor"] = st.selectbox(
                "Nombre receptor",
                _RECEPTORES_CADENA,
                index=receptor_idx,
                key="cc_receptor",
            )
        with nc3:
            st.markdown(f"**Supervisor/Jefe:** {_SUPERVISOR_CADENA}")
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

    # ── Preservación ─────────────────────────────────────────────────────
    with st.expander("Preservación", expanded=False):
        pc1, pc2, pc3, pc4, pc5, pc6 = st.columns(6)
        pres = cfg["preservacion"]
        with pc1:
            pres["HNO3"] = st.checkbox("HNO3", value=True, key="cc_hno3")
        with pc2:
            pres["H2SO4"] = st.checkbox("H2SO4", value=True, key="cc_h2so4")
        with pc3:
            pres["HCl"] = st.checkbox("HCl", value=False, key="cc_hcl")
        with pc4:
            pres["Lugol"] = st.checkbox("Lugol", value=True, key="cc_lugol")
        with pc5:
            pres["Formol"] = st.checkbox("Formol", value=False, key="cc_formol")
        with pc6:
            pres["S/P"] = st.checkbox("Sin preservación", value=True, key="cc_sp")
        # Eliminar NaOH si existía
        pres.pop("NaOH", None)

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

    # ── Parámetros de laboratorio ─────────────────────────────────────────
    with st.expander("Parámetros de laboratorio", expanded=False):
        st.caption("Parámetros fijos (marcados por defecto):")

        # Checkboxes para los 15 parámetros fijos
        params_seleccionados = []
        cols_per_row = 5
        param_list = list(get_parametros_lab_cadena())
        for i in range(0, len(param_list), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, col in enumerate(cols):
                idx = i + j
                if idx < len(param_list):
                    p = param_list[idx]
                    if col.checkbox(p["nombre"], value=True, key=f"cc_plab_{p['clave']}"):
                        params_seleccionados.append(p["clave"])

        cfg["parametros_lab"] = params_seleccionados

        # Parámetros extra
        st.markdown("**Parámetros adicionales** (separados por coma)")
        extras_text = st.text_input(
            "Parámetros extra",
            placeholder="Ej: Cianuro, DBO5, Coliformes totales",
            key="cc_params_extra",
            label_visibility="collapsed",
        )
        if extras_text.strip():
            cfg["parametros_lab_extra"] = [
                e.strip() for e in extras_text.split(",") if e.strip()
            ]

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

        # Registrar nuevo equipo inline
        with st.expander("Registrar nuevo equipo", expanded=False):
            ea1, ea2 = st.columns(2)
            with ea1:
                cod_extra = st.text_input("Código", key="cc_eq_cod_extra", placeholder="Código")
            with ea2:
                nom_extra = st.text_input("Nombre", key="cc_eq_nom_extra", placeholder="Nombre del equipo")
            if st.button("Agregar equipo", key="btn_cc_nuevo_eq"):
                if cod_extra.strip() and nom_extra.strip():
                    registrar_equipo(cod_extra.strip(), nom_extra.strip())
                    st.success(f"Equipo '{nom_extra.strip()}' registrado.")
                    st.rerun()
                else:
                    st.error("Completa código y nombre del equipo.")

        cfg["equipos"] = equipos if equipos else EQUIPOS_DEFAULT

    # ── Botones de descarga ──────────────────────────────────────────────
    st.divider()
    st.markdown("#### Descargar cadena de custodia")

    dc1, dc2 = st.columns(2)

    with dc1:
        if st.button("Generar Excel", key="btn_cc_excel", type="primary", use_container_width=True):
            with st.spinner("Generando Excel..."):
                try:
                    excel_bytes = generar_excel_cadena(campana_id, cfg)
                    st.session_state["cc_excel"] = excel_bytes
                    st.session_state["cc_campana_id"] = campana_id
                except Exception as exc:
                    st.error(f"Error generando Excel: {exc}")

        if st.session_state.get("cc_excel") and st.session_state.get("cc_campana_id") == campana_id:
            st.download_button(
                label="Descargar Excel",
                data=st.session_state["cc_excel"],
                file_name=f"cadena_custodia_{cfg['codigo_documento']}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="dl_cc_excel",
            )

    with dc2:
        if st.button("Generar PDF", key="btn_cc_pdf", use_container_width=True):
            with st.spinner("Generando PDF..."):
                try:
                    pdf_bytes = generar_pdf_cadena(campana_id, cfg)
                    st.session_state["cc_pdf"] = pdf_bytes
                    st.session_state["cc_pdf_campana_id"] = campana_id
                except Exception as exc:
                    st.error(f"Error generando PDF: {exc}")

        if st.session_state.get("cc_pdf") and st.session_state.get("cc_pdf_campana_id") == campana_id:
            st.download_button(
                label="Descargar PDF",
                data=st.session_state["cc_pdf"],
                file_name=f"cadena_custodia_{cfg['codigo_documento']}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="dl_cc_pdf",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Tab 6 — Fotos de campo
# ─────────────────────────────────────────────────────────────────────────────

def _render_fotos_campo() -> None:
    st.markdown("#### Fotos de campo")
    st.caption("Sube fotos desde archivo o toma fotos con la cámara del celular")

    campana_id = _selector_campana_todas("fotos")
    if not campana_id:
        return

    muestras = get_muestras_por_campana(campana_id)
    if not muestras:
        st.info("No hay muestras en esta campaña.")
        return

    opciones_m = {
        f"{m['codigo']} — {(m.get('puntos_muestreo') or {}).get('nombre', '')}": m["id"]
        for m in muestras
    }
    label_m = st.selectbox("Muestra", list(opciones_m.keys()), key="fotos_muestra")
    muestra_id = opciones_m[label_m]

    st.divider()

    # ── Subir fotos ─────────────────────────────────────────────────────
    col_upload, col_camera = st.columns(2)

    with col_upload:
        st.markdown("**Subir desde archivo**")
        archivos = st.file_uploader(
            "Seleccionar fotos",
            type=["jpg", "jpeg", "png"],
            accept_multiple_files=True,
            key="fotos_upload",
        )
        if archivos:
            if st.button(f"Subir {len(archivos)} foto(s)", key="btn_subir_fotos", type="primary"):
                for archivo in archivos:
                    try:
                        upload_foto_campo(
                            muestra_id,
                            archivo.getvalue(),
                            archivo.name,
                            archivo.type,
                        )
                    except Exception as exc:
                        st.error(f"Error subiendo {archivo.name}: {exc}")
                st.success(f"{len(archivos)} foto(s) subida(s).")
                st.rerun()

    with col_camera:
        st.markdown("**Tomar foto con cámara**")
        foto_cam = st.camera_input("Capturar foto", key="foto_camera")
        if foto_cam:
            if st.button("Guardar foto capturada", key="btn_guardar_cam"):
                try:
                    upload_foto_campo(
                        muestra_id,
                        foto_cam.getvalue(),
                        "captura_camara.jpg",
                        "image/jpeg",
                    )
                    st.success("Foto guardada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")

    # ── Galería de fotos existentes ─────────────────────────────────────
    st.divider()
    st.markdown("**Fotos guardadas**")
    fotos = get_fotos_campo(muestra_id)

    if not fotos:
        st.info("No hay fotos para esta muestra.")
    else:
        cols = st.columns(3)
        for i, foto in enumerate(fotos):
            with cols[i % 3]:
                st.image(foto["url"], caption=foto["name"], use_container_width=True)
                if st.button("Eliminar", key=f"del_foto_{i}"):
                    delete_foto_campo(muestra_id, foto["name"])
                    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Tab 7 — Ficha de campo (generación DOCX/PDF)
# ─────────────────────────────────────────────────────────────────────────────

def _render_ficha_campo() -> None:
    st.markdown("#### Fichas de Identificación del Punto de Monitoreo")
    st.caption("Genera todas las fichas de una campaña en un solo documento Word")

    campana_id = _selector_campana_todas("ficha")
    if not campana_id:
        return

    muestras = get_muestras_por_campana(campana_id)
    if not muestras:
        st.info("No hay muestras en esta campaña.")
        return

    # Resumen de puntos
    puntos_nombres = [
        (m.get("puntos_muestreo") or {}).get("nombre", m.get("codigo", ""))
        for m in muestras
    ]
    st.info(f"Se generarán **{len(muestras)}** fichas: {', '.join(puntos_nombres)}")

    st.divider()

    if st.button(
        f"Generar {len(muestras)} fichas DOCX",
        key="btn_fichas_docx",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner(f"Generando {len(muestras)} fichas..."):
            try:
                docx_bytes = generar_docx_fichas(campana_id)
                st.session_state["fichas_docx"] = docx_bytes
                st.session_state["fichas_campana_id"] = campana_id
            except Exception as exc:
                st.error(f"Error generando fichas: {exc}")

    if (
        st.session_state.get("fichas_docx")
        and st.session_state.get("fichas_campana_id") == campana_id
    ):
        campana_info = next(
            (m.get("campanas") or {} for m in muestras if m.get("campanas")), {}
        )
        campana_codigo = campana_info.get("codigo", "campana")
        st.download_button(
            label="Descargar fichas DOCX",
            data=st.session_state["fichas_docx"],
            file_name=f"fichas_campo_{campana_codigo}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
            key="dl_fichas_docx",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("administrador")
def main() -> None:
    st.title("Muestras de Campo")
    st.caption("Registro, mediciones in situ, cadena de custodia y etiquetas QR")

    tab_reg, tab_insitu, tab_custodia, tab_lista, tab_cadena, tab_fotos, tab_ficha = st.tabs([
        "Registro",
        "In situ",
        "Custodia",
        "Listado",
        "Cadena de Custodia",
        "Fotos de Campo",
        "Ficha de Campo",
    ])

    with tab_reg:
        _render_registro()

    with tab_insitu:
        _render_insitu()

    with tab_custodia:
        _render_custodia()

    with tab_lista:
        _render_listado()

    with tab_cadena:
        _render_cadena_custodia()

    with tab_fotos:
        _render_fotos_campo()

    with tab_ficha:
        _render_ficha_campo()


main()
