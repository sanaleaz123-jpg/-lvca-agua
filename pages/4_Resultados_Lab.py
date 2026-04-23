"""
pages/4_Resultados_Lab.py
Ingreso de resultados de laboratorio con semáforo ECA en tiempo real.

Flujo:
    1. Seleccionar campaña → punto de muestreo → muestra
    2. Editar parámetros (valor, observaciones) con inputs individuales
    3. Veredicto ECA en tiempo real con 5 estados: cumple, excede, excede_art6,
       no_verificable, no_aplica (motor services/cumplimiento_service.py).
    4. Guardar → upsert en resultados_laboratorio

Acceso mínimo: visualizador
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from components.ui_styles import aplicar_estilos, page_header, success_check_overlay, toast, top_nav
from services.parametro_registry import clasificar_categoria
from services.resultado_service import (
    get_campanas,
    get_puntos_de_campana,
    get_muestras,
    get_datos_muestra,
    guardar_resultados_lote,
    eliminar_resultados_muestra,
    _get_usuario_interno_id,
    evaluar_resultado_ctx,
)
from services.cumplimiento_service import EstadoECA

# ─── Constantes de visualización ─────────────────────────────────────────────

CATEGORIAS_ORDEN = ["Campo", "Fisicoquimico", "Hidrobiologico"]

_BG_VERDE = "#d4edda"
_BG_ROJO = "#f8d7da"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _semaforo_eca(valor, lim_min, lim_max) -> tuple[str, str]:
    """
    (legacy) Compara valor vs rango ECA fijo. Ahora se usa el motor de
    cumplimiento (_chip_veredicto_eca). Se conserva por si otros módulos la llaman.
    """
    if valor is None or (lim_max is None and lim_min is None):
        return "", ""
    excede = (
        (lim_max is not None and valor > lim_max)
        or (lim_min is not None and valor < lim_min)
    )
    if excede:
        return "excede", _BG_ROJO
    return "cumple", _BG_VERDE


# Chip de veredicto con 5 estados (motor de cumplimiento).
# Paleta alineada con SSDH/ANA: verde cumple, rojo excede, amarillo excepción,
# gris no verificable, lila no aplica.
_CHIP_ESTADOS: dict[str, dict] = {
    EstadoECA.CUMPLE:                {"bg": "#d4edda", "fg": "#155724", "label": "Cumple"},
    EstadoECA.EXCEDE:                {"bg": "#f8d7da", "fg": "#721c24", "label": "Excede"},
    EstadoECA.EXCEDE_EXCEPCION_ART6: {"bg": "#fff3cd", "fg": "#856404", "label": "Art. 6"},
    EstadoECA.NO_VERIFICABLE:        {"bg": "#e2e3e5", "fg": "#383d41", "label": "No verif."},
    EstadoECA.NO_APLICA:             {"bg": "#ede7f6", "fg": "#4527a0", "label": "No aplica"},
}


def _chip_veredicto_eca(veredicto) -> str:
    """
    Retorna HTML de un chip compacto con el estado del veredicto ECA. El motivo
    se expone via title= (tooltip nativo del navegador).
    """
    if veredicto is None:
        return ""
    est = _CHIP_ESTADOS.get(veredicto.estado)
    if est is None:
        return ""

    # Añadir % excedido cuando aplica (excede / excede_art6)
    label = est["label"]
    if veredicto.estado in (EstadoECA.EXCEDE, EstadoECA.EXCEDE_EXCEPCION_ART6) \
            and veredicto.valor_comparado is not None \
            and veredicto.eca_valor_maximo is not None \
            and veredicto.eca_valor_maximo > 0 \
            and veredicto.valor_comparado > veredicto.eca_valor_maximo:
        pct = (veredicto.valor_comparado / veredicto.eca_valor_maximo - 1) * 100
        label = f"{label} +{pct:.0f}%"

    motivo = (veredicto.motivo or "").replace('"', "'")
    return (
        f'<div title="{motivo}" style="background:{est["bg"]};color:{est["fg"]};'
        f'padding:2px 8px;border-radius:10px;text-align:center;font-size:0.82em;'
        f'font-weight:500;white-space:nowrap">{label}</div>'
    )


def _preparar_filas(datos: dict) -> list[dict]:
    """Convierte datos de get_datos_muestra en filas planas para renderizar."""
    filas = []
    for p in datos["parametros"]:
        pid = p["id"]
        resultado = datos["resultados"].get(pid, {})
        limite = datos["limites"].get(pid, {})
        filas.append({
            "parametro_id":   pid,
            "resultado_id":   resultado.get("id"),
            "codigo":         p["codigo"],
            "parametro":      p["nombre"],
            "categoria":      clasificar_categoria(p),
            "valor_numerico": resultado.get("valor_numerico"),
            "unidad":         (p.get("unidades_medida") or {}).get("simbolo", ""),
            "lim_max":        limite.get("valor_maximo"),
            "lim_min":        limite.get("valor_minimo"),
            "observaciones":  resultado.get("observaciones") or "",
            "cualificador":   resultado.get("cualificador"),
            "validado":       bool(resultado.get("validado")),
        })
    return filas


# ─────────────────────────────────────────────────────────────────────────────
# Selectores en cascada
# ─────────────────────────────────────────────────────────────────────────────

def _panel_seleccion() -> tuple[str | None, str | None, str | None]:
    """
    Renderiza los tres selectores (campaña, punto, muestra).
    Retorna (campana_id, punto_id, muestra_id). Cualquiera puede ser None.
    """
    campanas = get_campanas()
    if not campanas:
        st.warning("No hay campañas registradas. Crea al menos una campaña primero.")
        return None, None, None

    # ── Campaña
    opciones_c = {f"{c['nombre']} ({c.get('estado','')})": c["id"] for c in campanas}
    etiqueta_c = st.selectbox(
        "Campaña de monitoreo",
        list(opciones_c.keys()),
        key="sel_campana",
    )
    campana_id = opciones_c[etiqueta_c]

    # ── Punto de muestreo (filtrado por campaña)
    puntos = get_puntos_de_campana(campana_id)
    if not puntos:
        st.info("Esta campaña no tiene muestras registradas.")
        return campana_id, None, None

    opciones_p = {f"{p['codigo']} – {p['nombre']}": p["id"] for p in puntos}
    etiqueta_p = st.selectbox(
        "Punto de muestreo",
        list(opciones_p.keys()),
        key="sel_punto",
    )
    punto_id = opciones_p[etiqueta_p]

    # ── Muestra (filtrada por campaña + punto)
    muestras = get_muestras(campana_id, punto_id)
    if not muestras:
        st.info("No hay muestras para este punto en la campaña seleccionada.")
        return campana_id, punto_id, None

    opciones_m = {
        f"{m['codigo']} – {m.get('fecha_muestreo','')[:10]} [{m.get('estado','')}]": m["id"]
        for m in muestras
    }
    etiqueta_m = st.selectbox(
        "Muestra",
        list(opciones_m.keys()),
        key="sel_muestra",
    )
    muestra_id = opciones_m[etiqueta_m]

    return campana_id, punto_id, muestra_id


# ─────────────────────────────────────────────────────────────────────────────
# Renderizado por categoría con inputs individuales y semáforo en tiempo real
# ─────────────────────────────────────────────────────────────────────────────

def _render_categoria(
    filas_cat: list[dict],
    key_prefix: str,
    saved_params: set[str],
    datos: dict | None = None,
) -> dict[str, dict]:
    """
    Renderiza inputs individuales por parámetro con veredicto ECA en tiempo real.
    Si `datos` (dict completo de get_datos_muestra) se pasa, usa el motor de
    cumplimiento para evaluar con 5 estados (cumple, excede, excede_art6,
    no_verificable, no_aplica) aplicando conversión de especies, matricial NH3,
    cualificadores, forma analítica, zona mezcla y excepciones Art. 6.
    Si `datos=None`, hace fallback a la comparación simple lim_min/lim_max.

    Retorna {parametro_id: {valor, observaciones, cualificador}}.
    """
    con_datos = sum(1 for f in filas_cat if f["valor_numerico"] is not None)
    cs = st.columns(3)
    cs[0].caption(f"Parámetros: **{len(filas_cat)}**")
    cs[1].caption(f"Con valor: **{con_datos}**")
    n_exc = sum(
        1 for f in filas_cat
        if f["valor_numerico"] is not None
        and (f["lim_max"] is not None or f["lim_min"] is not None)
        and (
            (f["lim_max"] is not None and f["valor_numerico"] > f["lim_max"])
            or (f["lim_min"] is not None and f["valor_numerico"] < f["lim_min"])
        )
    )
    cs[2].markdown(
        f'<span style="font-size:0.85em">:material/warning: Exceden estimados: '
        f'<b>{n_exc}</b></span>',
        unsafe_allow_html=True,
    )

    # Encabezado
    hcols = st.columns([3, 1.6, 1.1, 0.7, 1, 0.6, 0.5])
    hcols[0].markdown("**Parámetro**")
    hcols[1].markdown("**Valor**")
    hcols[2].markdown("**Cualif.**")
    hcols[3].markdown("**Unidad**")
    hcols[4].markdown("**Lím. ECA**")
    hcols[5].markdown("**ECA**")
    hcols[6].markdown("")

    _CUALIFS = ["", "<LMD", "<LCM", ">LCM", "Ausencia", "Presencia", "ND", "Trazas"]

    valores: dict[str, dict] = {}

    for fila in filas_cat:
        pid = fila["parametro_id"]
        lim_max = fila["lim_max"]
        lim_min = fila["lim_min"]
        existing_val = fila["valor_numerico"]
        is_validado = fila.get("validado", False)
        cualif_actual = fila.get("cualificador") or ""

        cols = st.columns([3, 1.6, 1.1, 0.7, 1, 0.6, 0.5])

        # Nombre del parámetro (con candado si está validado)
        nombre = fila["parametro"]
        if is_validado:
            cols[0].markdown(
                f":material/lock: **{nombre}**",
                help="Resultado validado — bloqueado",
            )
        else:
            cols[0].markdown(f"**{nombre}**")

        # Input de valor (deshabilitado si validado).
        # Castear a float para evitar StreamlitMixedNumericTypesError.
        _ev = float(existing_val) if existing_val is not None else None
        val = cols[1].number_input(
            fila["parametro"],
            value=_ev,
            step=0.01,
            format="%.4g",
            label_visibility="collapsed",
            disabled=is_validado,
            key=f"lab_v_{key_prefix}_{pid}",
        )

        # Cualificador
        cualif_idx = _CUALIFS.index(cualif_actual) if cualif_actual in _CUALIFS else 0
        cualif = cols[2].selectbox(
            "Cualif",
            _CUALIFS,
            index=cualif_idx,
            label_visibility="collapsed",
            disabled=is_validado,
            key=f"lab_q_{key_prefix}_{pid}",
        )

        # Unidad
        cols[3].caption(fila["unidad"])

        # Límite ECA
        if lim_max is not None and lim_min is not None:
            cols[4].caption(f"{lim_min} – {lim_max}")
        elif lim_max is not None:
            cols[4].caption(f"≤ {lim_max}")
        elif lim_min is not None:
            cols[4].caption(f"≥ {lim_min}")
        else:
            cols[4].caption("—")

        # Veredicto ECA via motor de cumplimiento (5 estados). Fallback al pill
        # antiguo si no hay contexto completo (ej. página embebida sin datos).
        if datos is not None:
            ver = evaluar_resultado_ctx(datos, pid, valor_lab=val, cualificador=(cualif or None))
            cols[5].markdown(_chip_veredicto_eca(ver), unsafe_allow_html=True)
        else:
            from components.ui_styles import excede_pill as _ex_pill
            if val is not None and (lim_max is not None or lim_min is not None):
                pct = None
                if lim_max is not None and val > lim_max and lim_max > 0:
                    pct = (val / lim_max - 1) * 100
                elif lim_min is not None and val < lim_min and lim_min > 0:
                    pct = (1 - val / lim_min) * 100
                cols[5].markdown(_ex_pill(pct), unsafe_allow_html=True)

        # Badge de estado: validado tiene prioridad sobre guardado
        if is_validado:
            cols[6].markdown(":material/verified_user:", help="Validado")
        elif pid in saved_params:
            cols[6].markdown(":material/check_circle:", help="Guardado")

        valores[pid] = {"valor": val, "observaciones": "", "cualificador": cualif or None}

    # Observaciones en sección colapsable
    with st.expander("Observaciones", icon=":material/edit_note:", expanded=False):
        for fila in filas_cat:
            pid = fila["parametro_id"]
            existing_obs = fila.get("observaciones", "") or ""
            obs = st.text_input(
                fila["parametro"],
                value=existing_obs,
                key=f"lab_obs_{key_prefix}_{pid}",
            )
            if pid in valores:
                valores[pid]["observaciones"] = obs.strip() if obs else ""

    return valores


# ─────────────────────────────────────────────────────────────────────────────
# Página principal
# ─────────────────────────────────────────────────────────────────────────────

@require_rol("visualizador")
def main() -> None:
    sesion = st.session_state.get("sesion")
    if not sesion:
        st.error("Sesión expirada. Inicia sesión nuevamente.")
        st.stop()

    aplicar_estilos()
    top_nav()
    page_header("Resultados de Laboratorio", "Ingreso y validación con semáforo ECA &middot; D.S. N° 004-2017-MINAM")

    # ── Selección en cascada ─────────────────────────────────────────────────
    with st.expander("Seleccionar muestra", icon=":material/list:", expanded=True):
        campana_id, punto_id, muestra_id = _panel_seleccion()

    if not muestra_id:
        st.stop()

    # ── Cargar datos ─────────────────────────────────────────────────────────
    with st.spinner("Cargando parámetros y resultados..."):
        try:
            datos = get_datos_muestra(muestra_id)
        except Exception as exc:
            st.error(f"Error al cargar la muestra: {exc}")
            st.stop()

    muestra = datos["muestra"]
    punto = muestra.get("puntos_muestreo") or {}
    eca = punto.get("ecas") or {}

    # ── Barra informativa ────────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns(3)
    col_a.info(f"**Muestra:** {muestra.get('codigo','—')}")
    col_b.info(f"**Punto:** {punto.get('codigo','—')} — {punto.get('nombre','—')}")
    col_c.info(
        f"**ECA:** {eca.get('codigo','Sin ECA')} — {eca.get('nombre','')}"
        if eca.get("codigo") else "**ECA:** No asignado"
    )

    # ── Preparar datos ───────────────────────────────────────────────────────
    filas = _preparar_filas(datos)
    key_prefix = muestra_id[:8]

    # Estado de guardado persistente (session_state)
    saved_key = f"lab_guardado_{muestra_id}"
    msg_key = f"lab_msg_{muestra_id}"

    # Parámetros con resultado guardado: resultado_id existente + recién guardados
    saved_params: set[str] = set()
    for f in filas:
        if f["resultado_id"]:
            saved_params.add(f["parametro_id"])
    saved_params |= st.session_state.get(saved_key, set())

    # Mostrar mensaje persistente de guardado exitoso
    if msg_key in st.session_state:
        st.success(st.session_state[msg_key])

    # ── Métricas de resumen (basadas en datos guardados en BD) ───────────────
    total = len(filas)
    con_valor = sum(1 for f in filas if f["valor_numerico"] is not None)
    exceden_db = sum(
        1 for f in filas
        if f["valor_numerico"] is not None and (
            (f["lim_max"] is not None and f["valor_numerico"] > f["lim_max"])
            or (f["lim_min"] is not None and f["valor_numerico"] < f["lim_min"])
        )
    )
    cumplen_db = sum(
        1 for f in filas
        if f["valor_numerico"] is not None
        and (f["lim_max"] is not None or f["lim_min"] is not None)
        and not (
            (f["lim_max"] is not None and f["valor_numerico"] > f["lim_max"])
            or (f["lim_min"] is not None and f["valor_numerico"] < f["lim_min"])
        )
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total parámetros", total)
    m2.metric("Con valor", con_valor)
    m3.metric("Exceden ECA", exceden_db)
    m4.metric("Cumplen ECA", cumplen_db)

    if exceden_db > 0:
        st.error(
            f"**{exceden_db} parámetro(s) exceden el límite ECA** "
            f"({eca.get('codigo','')}) para este punto de muestreo.",
            icon=":material/warning:",
        )

    st.divider()

    # ── Leyenda de estados ECA (motor de cumplimiento) ────────────────────────
    with st.expander("Leyenda de estados ECA", icon=":material/help:"):
        lc1, lc2, lc3 = st.columns(3)
        lc1.markdown(
            "**Cumple** — valor dentro del rango ECA aplicable, convertido a la "
            "especie oficial del DS cuando corresponde."
        )
        lc1.markdown(
            "**Excede** — valor supera el umbral. Se indica el % de excedencia."
        )
        lc2.markdown(
            "**Art. 6** — excede, pero hay excepción aprobada por ANA "
            "(condición natural no antrópica)."
        )
        lc2.markdown(
            "**No verif.** — no se puede emitir juicio: LC>ECA, falta pH/T para "
            "NH₃ Cat 4, zona de mezcla, o discrepancia total/disuelta."
        )
        lc3.markdown(
            "**No aplica** — parámetro sin ECA en el DS 004-2017-MINAM para la "
            "categoría del punto (ej. fosfatos, o P-total en Cat 3)."
        )

    # ── Ingreso por categoría (tabs) ─────────────────────────────────────────
    st.subheader("Ingreso de resultados por categoría")

    cats: dict[str, list[dict]] = defaultdict(list)
    for f in filas:
        cats[f["categoria"]].append(f)

    cats_ordenadas = [c for c in CATEGORIAS_ORDEN if c in cats]
    cats_ordenadas += [c for c in cats if c not in CATEGORIAS_ORDEN]

    tabs = st.tabs([f"{cat} ({len(cats[cat])})" for cat in cats_ordenadas])

    all_valores: dict[str, dict] = {}
    for tab_widget, cat in zip(tabs, cats_ordenadas):
        with tab_widget:
            cat_vals = _render_categoria(cats[cat], key_prefix, saved_params, datos=datos)
            all_valores.update(cat_vals)

    # ── Botón de guardado ─────────────────────────────────────────────────────
    st.divider()
    col_btn, col_space = st.columns([2, 5])
    with col_btn:
        guardar = st.button(
            "Guardar resultados",
            icon=":material/save:",
            type="primary",
            use_container_width=True,
        )

    if guardar:
        cambios = []
        for pid, data in all_valores.items():
            valor = data.get("valor")
            obs = data.get("observaciones", "")
            cualif = data.get("cualificador")
            # Cualificadores cualitativos válidos sin valor numérico
            cualif_solo = cualif in ("Ausencia", "Presencia", "ND", "<LMD", "<LCM")
            if valor is None and not obs and not cualif_solo:
                continue
            cambios.append({
                "parametro_id":   pid,
                "valor_numerico": float(valor) if valor is not None else None,
                "valor_texto":    cualif if cualif in ("Ausencia", "Presencia") else None,
                "observaciones":  obs or None,
                "cualificador":   cualif,
            })

        if not cambios:
            st.warning("No hay valores para guardar. Ingresa al menos un resultado.")
        else:
            analista_id = _get_usuario_interno_id(sesion.uid)
            with st.spinner(f"Guardando {len(cambios)} resultado(s)..."):
                ok, errores, bloqueados = guardar_resultados_lote(
                    muestra_id=muestra_id,
                    filas=cambios,
                    analista_id=analista_id,
                )

            if bloqueados:
                st.warning(
                    f"{len(bloqueados)} resultado(s) están **validados** y no se sobreescribieron. "
                    "Un administrador debe desvalidarlos primero para poder editar.",
                    icon=":material/lock:",
                )
            if errores:
                st.error(f"Se guardaron {ok}/{len(cambios)} resultados. Errores:")
                for e in errores:
                    st.caption(f"• {e}")
            else:
                # Marcar parámetros como guardados (persiste hasta navegar fuera)
                st.session_state[saved_key] = {c["parametro_id"] for c in cambios}
                st.session_state[msg_key] = (
                    f"{ok} resultado(s) guardado(s) correctamente."
                )
                success_check_overlay(f"{ok} resultado(s) guardado(s)")
                # Invalidar caché para carga fresca en el siguiente render
                get_datos_muestra.clear()
                st.rerun()

    # ── Eliminar todos los resultados de esta muestra ────────────────────────
    sesion_rol = sesion.rol if sesion else "visitante"

    # ── Validación / desvalidación de resultados (solo administrador) ─────────
    if sesion_rol == "administrador":
        n_validados = sum(1 for f in filas if f.get("validado"))
        n_no_validados = sum(1 for f in filas if not f.get("validado") and f["valor_numerico"] is not None)
        with st.expander(
            f"Validar resultados ({n_validados} validados, {n_no_validados} pendientes)",
            icon=":material/verified_user:",
            expanded=False,
        ):
            st.caption(
                "Validar bloquea los resultados contra ediciones accidentales. "
                "Solo admins pueden desvalidar para corregir."
            )
            from services.resultado_service import validar_resultados, desvalidar_resultados
            col_v, col_d = st.columns(2)
            pendientes_ids = [f["parametro_id"] for f in filas
                              if not f.get("validado") and f["valor_numerico"] is not None]
            validados_ids = [f["parametro_id"] for f in filas if f.get("validado")]
            with col_v:
                if pendientes_ids and st.button(
                    f"Validar {len(pendientes_ids)} pendiente(s)",
                    key="btn_validar_todos", type="primary",
                ):
                    validador_id = _get_usuario_interno_id(sesion.uid)
                    n = validar_resultados(muestra_id, pendientes_ids, validador_id)
                    success_check_overlay(f"{n} resultado(s) validado(s)")
                    get_datos_muestra.clear()
                    st.rerun()
            with col_d:
                if validados_ids and st.button(
                    f"Desvalidar {len(validados_ids)} (permitir editar)",
                    key="btn_desvalidar_todos",
                ):
                    n = desvalidar_resultados(muestra_id, validados_ids)
                    toast(f"{n} resultado(s) desvalidado(s) — ahora son editables", tipo="warn")
                    get_datos_muestra.clear()
                    st.rerun()

    # ── Carga masiva desde Excel / CSV ────────────────────────────────────────
    with st.expander("Carga masiva desde Excel / CSV", icon=":material/upload_file:", expanded=False):
        st.caption(
            "Sube un archivo con dos columnas: **codigo** (P001, P019, ...) y **valor** "
            "(numérico, opcional). Una columna **cualificador** (opcional) acepta "
            "<LMD, <LCM, Ausencia, Presencia, ND, Trazas. "
            "Resultados validados quedarán bloqueados."
        )

        # Plantilla descargable
        codigos_existentes = sorted({f["codigo"] for f in filas})
        plantilla_csv = "codigo,valor,cualificador,observaciones\n" + "\n".join(
            f"{c},,," for c in codigos_existentes
        )
        st.download_button(
            "Descargar plantilla CSV",
            data=plantilla_csv.encode("utf-8"),
            file_name=f"plantilla_resultados_{muestra_id[:8]}.csv",
            mime="text/csv",
            key="dl_plantilla_csv",
        )

        archivo = st.file_uploader(
            "Archivo de carga (Excel o CSV)",
            type=["xlsx", "csv"],
            key=f"upload_lab_{muestra_id}",
        )
        if archivo is not None:
            try:
                import pandas as _pd
                if archivo.name.lower().endswith(".csv"):
                    df_carga = _pd.read_csv(archivo)
                else:
                    df_carga = _pd.read_excel(archivo)
                df_carga.columns = [str(c).strip().lower() for c in df_carga.columns]
                if "codigo" not in df_carga.columns:
                    st.error("El archivo debe tener una columna 'codigo'.")
                else:
                    cod_a_pid = {f["codigo"]: f["parametro_id"] for f in filas}
                    cargas: list[dict] = []
                    no_match: list[str] = []
                    for _, row in df_carga.iterrows():
                        cod = str(row.get("codigo", "")).strip().upper()
                        if not cod:
                            continue
                        pid = cod_a_pid.get(cod)
                        if not pid:
                            no_match.append(cod)
                            continue
                        valor = row.get("valor")
                        if _pd.isna(valor):
                            valor = None
                        else:
                            try:
                                valor = float(valor)
                            except (TypeError, ValueError):
                                valor = None
                        cualif = row.get("cualificador")
                        if _pd.isna(cualif) or not cualif:
                            cualif = None
                        else:
                            cualif = str(cualif).strip()
                        obs = row.get("observaciones")
                        if _pd.isna(obs) or not obs:
                            obs = None
                        else:
                            obs = str(obs).strip()
                        if valor is None and not cualif and not obs:
                            continue
                        cargas.append({
                            "parametro_id":   pid,
                            "valor_numerico": valor,
                            "valor_texto":    cualif if cualif in ("Ausencia", "Presencia") else None,
                            "cualificador":   cualif,
                            "observaciones":  obs,
                        })

                    st.info(f"Filas válidas detectadas: **{len(cargas)}**")
                    if no_match:
                        st.warning(
                            f"{len(no_match)} código(s) no coinciden con parámetros activos: "
                            f"{', '.join(no_match[:10])}"
                        )

                    if cargas and st.button(
                        f"Cargar {len(cargas)} resultado(s)",
                        key="btn_bulk_upload", type="primary",
                        icon=":material/upload:",
                    ):
                        analista_id = _get_usuario_interno_id(sesion.uid)
                        ok, errs, blocs = guardar_resultados_lote(
                            muestra_id=muestra_id,
                            filas=cargas,
                            analista_id=analista_id,
                        )
                        if blocs:
                            toast(f"{len(blocs)} validado(s) no sobreescritos", tipo="warn")
                        if errs:
                            st.error(f"Cargados {ok}/{len(cargas)}. Errores:")
                            for e in errs:
                                st.caption(f"• {e}")
                        else:
                            success_check_overlay(f"{ok} resultado(s) cargados")
                        get_datos_muestra.clear()
                        st.rerun()
            except Exception as exc:
                st.error(f"Error procesando el archivo: {exc}")

    if sesion_rol == "administrador" and con_valor > 0:
        with st.expander("Vaciar resultados de esta muestra", expanded=False):
            st.warning(
                f"Se eliminarán **{con_valor} resultado(s)** de laboratorio para esta muestra. "
                "Esta acción no se puede deshacer."
            )
            st.markdown('<div class="lvca-danger">', unsafe_allow_html=True)
            del_btn = st.button(
                "Eliminar todos los resultados",
                key="btn_eliminar_resultados", type="primary",
                icon=":material/delete:",
            )
            st.markdown('</div>', unsafe_allow_html=True)
            if del_btn:
                try:
                    n = eliminar_resultados_muestra(muestra_id)
                    st.session_state.pop(saved_key, None)
                    st.session_state.pop(msg_key, None)
                    get_datos_muestra.clear()
                    toast(f"{n} resultado(s) eliminado(s)", tipo="danger")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Error: {exc}")

    # ── Excedencias en detalle (tiempo real desde valores actuales) ───────────
    filas_by_pid = {f["parametro_id"]: f for f in filas}
    excedencias_rt = []
    for pid, data in all_valores.items():
        val = data.get("valor")
        if val is None:
            continue
        info = filas_by_pid.get(pid)
        if not info:
            continue
        lm = info["lim_max"]
        ln = info["lim_min"]
        if lm is None and ln is None:
            continue
        if (lm is not None and val > lm) or (ln is not None and val < ln):
            excedencias_rt.append({
                "Código":       info["codigo"],
                "Parámetro":    info["parametro"],
                "Valor medido": val,
                "Unidad":       info["unidad"],
                "Límite ECA":   lm,
            })

    if excedencias_rt:
        st.divider()
        with st.expander(
            f"Detalle de excedencias ({len(excedencias_rt)} parámetros)",
            icon=":material/error:",
            expanded=True,
        ):
            df_exc = pd.DataFrame(excedencias_rt)
            df_exc["Excedencia"] = df_exc.apply(
                lambda r: f"+{((r['Valor medido'] / r['Límite ECA'] - 1) * 100):.1f}%"
                if r["Límite ECA"] and r["Límite ECA"] > 0 else "—",
                axis=1,
            )
            st.dataframe(df_exc, use_container_width=True, hide_index=True)
            st.caption(
                "Notifica estas excedencias a los responsables vía el módulo de Notificaciones."
            )


main()
