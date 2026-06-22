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
from components.nav_context import consumir_contexto, ir_a, preseleccionar, rol_alcanza
from components.ui_styles import (
    ECA_CHIP_STYLES,
    aplicar_estilos,
    chip_eca_html,
    page_header,
    success_check_overlay,
    toast,
    top_nav,
)
from services.parametro_registry import clasificar_categoria
from services.resultado_service import (
    get_campanas,
    get_puntos_de_campana,
    get_muestras,
    get_grupo_columna,
    get_datos_muestra,
    guardar_resultados_lote,
    eliminar_resultados_muestra,
    _get_usuario_interno_id,
    evaluar_resultado_ctx,
)
from services.cumplimiento_service import EstadoECA
from services.fitoplancton_service import (
    NIVELES_OMS_CIANOBACTERIAS,
    NIVELES_OMS_2021_CIANOBACTERIAS,
    evaluar_alerta_oms_cianobacterias,
)
from components.fitoplancton_form import render_subseccion_fitoplancton

# Códigos de los parámetros agregados de fitoplancton — se renderizan con
# semáforo OMS en lugar del veredicto ECA estándar (no hay ECA en la norma).
COD_CYANO_CEL_ML:    str = "FITO_CYANOBACTERIA_CEL"
COD_CYANO_BIOVOLUMEN: str = "FITO_CYANOBACTERIA_BIOVOL"

# ─── Constantes de visualización ─────────────────────────────────────────────

CATEGORIAS_ORDEN = ["Campo", "Fisicoquimico", "Hidrobiologico"]

# Niveles de columna de agua (muestreo en profundidad)
_PROF_NOMBRES = {"S": "Superficie", "M": "Medio", "F": "Fondo"}
_ORDEN_PROF = {"S": 0, "M": 1, "F": 2}

_BG_VERDE = ECA_CHIP_STYLES["cumple"]["bg"]
_BG_ROJO = ECA_CHIP_STYLES["excede"]["bg"]


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


def _chip_veredicto_eca(veredicto) -> str:
    """
    Retorna HTML de un chip compacto con el estado del veredicto ECA. El motivo
    se expone via title= (tooltip nativo del navegador). La paleta vive en
    components.ui_styles.ECA_CHIP_STYLES (compartida con 8_Informes).
    """
    if veredicto is None:
        return ""
    est = ECA_CHIP_STYLES.get(veredicto.estado)
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

    return chip_eca_html(veredicto.estado, motivo=veredicto.motivo or "", label=label)


def _chip_oms_cianobacterias_cel(valor: float | None) -> str:
    """
    Chip para el parámetro Cianobacteria (cel/mL) con la paleta OMS 1999.
    Niveles: vigilancia inicial >=200, alerta 1 >=2 000, alerta 2 >=100 000.
    """
    if valor is None:
        return (
            '<div title="Sin valor cargado" '
            'style="background:#f1f3f5;color:#6c757d;padding:2px 8px;'
            'border-radius:10px;text-align:center;font-size:0.82em;'
            'font-weight:500;white-space:nowrap">Sin valor</div>'
        )
    nivel = evaluar_alerta_oms_cianobacterias(float(valor))
    if nivel is None:
        bg, fg, label, motivo = (
            "#d4edda", "#155724", "Sin alerta",
            "OMS 1999: < 200 cél/mL, sin nivel de alerta.",
        )
    else:
        bg = nivel["color_bg"]
        fg = nivel["color_fg"]
        label = nivel["label"]
        motivo = f"OMS 1999 — {nivel['descripcion']}".replace('"', "'")
    return (
        f'<div title="{motivo}" style="background:{bg};color:{fg};'
        f'padding:2px 8px;border-radius:10px;text-align:center;font-size:0.82em;'
        f'font-weight:500;white-space:nowrap">{label}</div>'
    )


def _chip_oms_cianobacterias_biovol(valor: float | None) -> str:
    """
    Chip para Cianobacteria (biovolumen mm³/L) con la paleta OMS 2021.
    Umbrales: alerta 2 >=4,0; alerta 1 >=0,3; sin alerta otherwise (la fila
    Vigilancia inicial por col/mL o fil/mL no se evalúa aquí porque esos
    sub-conteos no se persisten en resultados_laboratorio — sólo viven en
    el JSONB del análisis Sedgewick-Rafter, donde sí se muestra el banner
    completo OMS 2021).
    """
    if valor is None:
        return (
            '<div title="Sin valor cargado" '
            'style="background:#f1f3f5;color:#6c757d;padding:2px 8px;'
            'border-radius:10px;text-align:center;font-size:0.82em;'
            'font-weight:500;white-space:nowrap">Sin valor</div>'
        )
    v = float(valor)
    if v >= 4.0:
        nivel = NIVELES_OMS_2021_CIANOBACTERIAS[0]
    elif v >= 0.3:
        nivel = NIVELES_OMS_2021_CIANOBACTERIAS[1]
    else:
        bg, fg, label, motivo = (
            "#d4edda", "#155724", "Sin alerta",
            "OMS 2021: biovolumen < 0,3 mm³/L, sin nivel de alerta por biomasa.",
        )
        return (
            f'<div title="{motivo}" style="background:{bg};color:{fg};'
            f'padding:2px 8px;border-radius:10px;text-align:center;font-size:0.82em;'
            f'font-weight:500;white-space:nowrap">{label}</div>'
        )
    bg = nivel["color_bg"]
    fg = nivel["color_fg"]
    label = nivel["label"]
    motivo = f"OMS 2021 — {nivel['descripcion']} ({nivel['criterio']})".replace('"', "'")
    return (
        f'<div title="{motivo}" style="background:{bg};color:{fg};'
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

    # Contexto de navegación: otra página pidió abrir campaña/punto/muestra
    ctx = consumir_contexto("resultados")

    # ── Campaña
    opciones_c = {f"{c['nombre']} ({c.get('estado','')})": c["id"] for c in campanas}
    preseleccionar("sel_campana", opciones_c, ctx.get("campana_id"))
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
    preseleccionar("sel_punto", opciones_p, ctx.get("punto_id"))
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

    # Agrupar muestras de columna de agua (S/M/F) en una sola opción; el valor
    # apunta al nivel Superficie (representante) y el cuerpo expande el grupo.
    grupos_col: dict[str, list[dict]] = {}
    individuales: list[dict] = []
    for m in muestras:
        g = m.get("grupo_profundidad")
        if g and m.get("modo_muestreo") == "columna":
            grupos_col.setdefault(g, []).append(m)
        else:
            individuales.append(m)

    opciones_m: dict[str, str] = {}
    for g, ms in grupos_col.items():
        ms.sort(key=lambda x: _ORDEN_PROF.get(x.get("profundidad_tipo"), 9))
        niveles = " / ".join(_PROF_NOMBRES.get(x.get("profundidad_tipo"), "?") for x in ms)
        codigos = ", ".join(x["codigo"] for x in ms)
        fecha = (ms[0].get("fecha_muestreo") or "")[:10]
        etq = f"Columna {niveles} — {codigos} ({fecha})"
        opciones_m[etq] = ms[0]["id"]
    for m in individuales:
        etq = f"{m['codigo']} – {m.get('fecha_muestreo','')[:10]} [{m.get('estado','')}]"
        opciones_m[etq] = m["id"]
    preseleccionar("sel_muestra", opciones_m, ctx.get("muestra_id"))
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

        # Veredicto en cels[5]:
        #   - Cianobacteria (cel/mL)        → OMS 1999
        #   - Cianobacteria (biovolumen)    → OMS 2021
        #   - Resto                         → motor ECA estándar (5 estados)
        codigo = fila.get("codigo")
        if codigo == COD_CYANO_CEL_ML:
            cols[5].markdown(
                _chip_oms_cianobacterias_cel(val), unsafe_allow_html=True,
            )
        elif codigo == COD_CYANO_BIOVOLUMEN:
            cols[5].markdown(
                _chip_oms_cianobacterias_biovol(val), unsafe_allow_html=True,
            )
        elif datos is not None:
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

    # ── Atajos del flujo con la selección actual ─────────────────────────────
    # Campañas y Muestras exigen rol administrador: solo se ofrecen a quien
    # puede entrar (rol_alcanza evita aterrizar en "Acceso denegado").
    if campana_id:
        _admin = rol_alcanza("administrador")
        nav1, nav2, nav3, nav4, _sp = st.columns([1.2, 1.2, 1.2, 1.2, 1.6])
        with nav1:
            if _admin and st.button("Campaña", key="res_nav_campana",
                                    icon=":material/event:", use_container_width=True):
                ir_a("campanas", campana_id=campana_id)
        with nav2:
            if _admin and st.button("Muestras", key="res_nav_muestras",
                                    icon=":material/edit_note:", use_container_width=True):
                ir_a("muestras", campana_id=campana_id)
        with nav3:
            if st.button("Base de Datos", key="res_nav_bd",
                         icon=":material/database:", use_container_width=True):
                ir_a("base_datos", campana_id=campana_id, punto_id=punto_id)
        with nav4:
            if st.button("Informe", key="res_nav_informe",
                         icon=":material/description:", use_container_width=True):
                ir_a("informes", campana_id=campana_id)

    if not muestra_id:
        st.stop()

    # El cuerpo de captura corre como fragment: cada input/checkbox del panel
    # re-renderiza SOLO esta zona — los selectores, la navegación y el resto
    # de la página no se vuelven a ejecutar (Streamlit ≥1.37).
    _cuerpo_muestra(muestra_id)


@st.fragment
def _cuerpo_muestra(muestra_id: str) -> None:
    """
    Enrutador del panel de captura. Si la muestra pertenece a un muestreo en
    columna de agua (2+ niveles S/M/F), renderiza la tabla unificada por nivel;
    en caso contrario, el panel simple de una muestra. Aislado en un fragment
    para que los reruns de sus widgets no recarguen la página.
    """
    grupo = get_grupo_columna(muestra_id)
    if len(grupo) >= 2:
        _render_columna(grupo)
    else:
        _render_single_body(muestra_id)


def _render_single_body(muestra_id: str) -> None:
    """
    Panel de captura de una muestra (barra informativa, métricas, tabs por
    categoría, guardado, validación, carga masiva y excedencias). Los guardados
    llaman st.rerun() (scope app por defecto) para refrescar también selectores
    y métricas externas.
    """
    sesion = st.session_state.get("sesion")
    if not sesion:
        st.error("Sesión expirada. Inicia sesión nuevamente.")
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

    # Forzar la presencia del tab Hidrobiologico aunque no haya parámetros hidro
    # en la muestra, para que la subsección Fitoplancton (Sedgewick-Rafter) esté
    # siempre accesible.
    cats.setdefault("Hidrobiologico", [])

    cats_ordenadas = [c for c in CATEGORIAS_ORDEN if c in cats]
    cats_ordenadas += [c for c in cats if c not in CATEGORIAS_ORDEN]

    tabs = st.tabs([f"{cat} ({len(cats[cat])})" for cat in cats_ordenadas])

    analista_id_actual = _get_usuario_interno_id(sesion.uid)

    all_valores: dict[str, dict] = {}
    for tab_widget, cat in zip(tabs, cats_ordenadas):
        with tab_widget:
            if cat == "Hidrobiologico":
                # Sub-tabs: parámetros estándar + Fitoplancton (Sedgewick-Rafter)
                sub_param, sub_fito = st.tabs([
                    f":material/science: Parámetros ({len(cats[cat])})",
                    ":material/biotech: Fitoplancton (Sedgewick-Rafter)",
                ])
                with sub_param:
                    if cats[cat]:
                        cat_vals = _render_categoria(
                            cats[cat], key_prefix, saved_params, datos=datos
                        )
                        all_valores.update(cat_vals)
                    else:
                        st.caption(
                            "Sin parámetros hidrobiológicos del DS 004-2017-MINAM "
                            "en esta muestra."
                        )
                with sub_fito:
                    render_subseccion_fitoplancton(muestra_id, analista_id_actual)
            else:
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


# ─────────────────────────────────────────────────────────────────────────────
# Columna de agua — tabla unificada por nivel (S / M / F)
# ─────────────────────────────────────────────────────────────────────────────

def _render_columna(grupo: list[dict]) -> None:
    """
    Vista para un muestreo en columna de agua. Por defecto muestra la tabla
    unificada con una columna de valor por nivel (Superficie / Medio / Fondo);
    el usuario puede cambiar a un nivel concreto para la gestión avanzada
    (cualificadores, observaciones, validación, carga masiva, fitoplancton,
    eliminar) reutilizando el panel simple de esa muestra.
    """
    labels = ["Vista unificada (todos los niveles)"]
    nivel_por_label: dict[str, str] = {}
    for m in grupo:
        tp = m.get("profundidad_tipo")
        lbl = f"{_PROF_NOMBRES.get(tp, tp or '?')} — {m['codigo']}"
        labels.append(lbl)
        nivel_por_label[lbl] = m["id"]

    sel = st.radio(
        "Modo de ingreso",
        labels,
        horizontal=True,
        key=f"res_col_modo_{grupo[0]['id'][:8]}",
        help=(
            "Vista unificada: ingresa los valores de todos los niveles lado a "
            "lado. Selecciona un nivel para gestión avanzada (cualificadores, "
            "observaciones, validación, carga masiva, fitoplancton, eliminar)."
        ),
    )
    if sel == labels[0]:
        _render_ingreso_columna(grupo)
    else:
        _render_single_body(nivel_por_label[sel])


def _render_ingreso_columna(grupo: list[dict]) -> None:
    """Tabla unificada de ingreso con una columna de valor por nivel."""
    sesion = st.session_state.get("sesion")
    if not sesion:
        st.error("Sesión expirada. Inicia sesión nuevamente.")
        st.stop()

    # ── Cargar datos de cada nivel ───────────────────────────────────────────
    with st.spinner("Cargando parámetros y resultados de los niveles..."):
        niveles: list[dict] = []
        for m in grupo:
            try:
                d = get_datos_muestra(m["id"])
            except Exception as exc:
                st.error(f"Error al cargar el nivel {m.get('codigo')}: {exc}")
                st.stop()
            filas = _preparar_filas(d)
            niveles.append({
                "meta":      m,
                "datos":     d,
                "filas":     filas,
                "filas_idx": {f["parametro_id"]: f for f in filas},
            })

    primera = niveles[0]
    muestra0 = primera["datos"]["muestra"]
    punto = muestra0.get("puntos_muestreo") or {}
    eca = punto.get("ecas") or {}

    # ── Barra informativa ────────────────────────────────────────────────────
    codigos = ", ".join(n["meta"]["codigo"] for n in niveles)
    col_a, col_b, col_c = st.columns(3)
    col_a.info(f"**Columna:** {len(niveles)} niveles — {codigos}")
    col_b.info(f"**Punto:** {punto.get('codigo','—')} — {punto.get('nombre','—')}")
    col_c.info(
        f"**ECA:** {eca.get('codigo','Sin ECA')} — {eca.get('nombre','')}"
        if eca.get("codigo") else "**ECA:** No asignado"
    )

    # ── Métricas agregadas ───────────────────────────────────────────────────
    total = len(primera["filas"])
    con_valor = sum(
        1 for n in niveles for f in n["filas"] if f["valor_numerico"] is not None
    )
    exceden = sum(
        1 for n in niveles for f in n["filas"]
        if f["valor_numerico"] is not None and (
            (f["lim_max"] is not None and f["valor_numerico"] > f["lim_max"])
            or (f["lim_min"] is not None and f["valor_numerico"] < f["lim_min"])
        )
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Parámetros × niveles", f"{total} × {len(niveles)}")
    m2.metric("Valores ingresados", con_valor)
    m3.metric("Exceden ECA", exceden)

    # Mensajes persistentes de guardado por nivel
    for n in niveles:
        mk = f"lab_msg_{n['meta']['id']}"
        if mk in st.session_state:
            st.success(st.session_state[mk])
            del st.session_state[mk]

    st.divider()
    st.caption(
        "Edita los valores de cada nivel. Los cualificadores y observaciones se "
        "gestionan por nivel desde el selector superior."
    )
    st.subheader("Ingreso de resultados por nivel de profundidad")

    # ── Tabs por categoría ───────────────────────────────────────────────────
    cats0: dict[str, list[dict]] = defaultdict(list)
    for f in primera["filas"]:
        cats0[f["categoria"]].append(f)
    cats0.setdefault("Hidrobiologico", [])
    cats_ord = [c for c in CATEGORIAS_ORDEN if c in cats0]
    cats_ord += [c for c in cats0 if c not in CATEGORIAS_ORDEN]
    tabs = st.tabs([f"{c} ({len(cats0[c])})" for c in cats_ord])

    analista_actual = _get_usuario_interno_id(sesion.uid)
    # valores_por_nivel[j] = {pid: {valor}}  (alineado con niveles[j])
    valores_por_nivel: list[dict[str, dict]] = [{} for _ in niveles]

    for tab_widget, cat in zip(tabs, cats_ord):
        with tab_widget:
            if cat == "Hidrobiologico":
                sub_param, sub_fito = st.tabs([
                    f":material/science: Parámetros ({len(cats0[cat])})",
                    ":material/biotech: Fitoplancton (Sedgewick-Rafter)",
                ])
                with sub_param:
                    if cats0[cat]:
                        _render_categoria_columna(cats0[cat], niveles, valores_por_nivel)
                    else:
                        st.caption(
                            "Sin parámetros hidrobiológicos del DS 004-2017-MINAM "
                            "en esta muestra."
                        )
                with sub_fito:
                    fito_tabs = st.tabs([
                        _PROF_NOMBRES.get(n["meta"].get("profundidad_tipo"), "?")
                        for n in niveles
                    ])
                    for ft, n in zip(fito_tabs, niveles):
                        with ft:
                            render_subseccion_fitoplancton(n["meta"]["id"], analista_actual)
            else:
                if cats0[cat]:
                    _render_categoria_columna(cats0[cat], niveles, valores_por_nivel)

    # ── Guardar todos los niveles ────────────────────────────────────────────
    st.divider()
    col_btn, _sp = st.columns([2, 5])
    with col_btn:
        guardar = st.button(
            f"Guardar resultados ({len(niveles)} niveles)",
            icon=":material/save:", type="primary", use_container_width=True,
            key="btn_guardar_columna",
        )

    if guardar:
        analista_id = _get_usuario_interno_id(sesion.uid)
        total_ok, total_err, total_bloq = 0, [], 0
        guardados_por_nivel: dict[str, set] = {}
        for j, n in enumerate(niveles):
            cambios = []
            for pid, data in valores_por_nivel[j].items():
                valor = data.get("valor")
                # Preservar cualificador/observaciones existentes del nivel
                fila = n["filas_idx"].get(pid, {})
                cualif = fila.get("cualificador")
                obs = fila.get("observaciones") or ""
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
                continue
            ok, errs, blocs = guardar_resultados_lote(
                muestra_id=n["meta"]["id"], filas=cambios, analista_id=analista_id,
            )
            total_ok += ok
            total_err.extend(errs)
            total_bloq += len(blocs)
            guardados_por_nivel[n["meta"]["id"]] = {c["parametro_id"] for c in cambios}

        if total_bloq:
            st.warning(
                f"{total_bloq} resultado(s) están validados y no se sobreescribieron.",
                icon=":material/lock:",
            )
        if total_err:
            st.error(f"Se guardaron {total_ok} resultado(s). Errores:")
            for e in total_err:
                st.caption(f"• {e}")
        elif total_ok > 0:
            for mid, pids in guardados_por_nivel.items():
                st.session_state[f"lab_guardado_{mid}"] = pids
            success_check_overlay(
                f"{total_ok} resultado(s) guardado(s) en {len(guardados_por_nivel)} nivel(es)"
            )
            get_datos_muestra.clear()
            st.rerun()
        else:
            st.warning("No hay valores para guardar. Ingresa al menos un resultado.")


def _render_categoria_columna(
    filas_cat: list[dict],
    niveles: list[dict],
    valores_por_nivel: list[dict[str, dict]],
) -> None:
    """
    Renderiza una categoría con una columna de valor por nivel (S/M/F) y el
    veredicto ECA por nivel. Acumula los valores ingresados en
    `valores_por_nivel` (alineado con `niveles`).
    """
    n_niv = len(niveles)
    col_widths = [2.4] + [1.6] * n_niv + [0.7, 1.0]

    # Encabezado
    hcols = st.columns(col_widths)
    hcols[0].markdown("**Parámetro**")
    for j, n in enumerate(niveles):
        tp = n["meta"].get("profundidad_tipo")
        pv = n["meta"].get("profundidad_valor")
        lbl = _PROF_NOMBRES.get(tp, tp or "?")
        hcols[1 + j].markdown(f"**{lbl}**" + (f" ({pv} m)" if pv else ""))
    hcols[1 + n_niv].markdown("**Unidad**")
    hcols[2 + n_niv].markdown("**Lím. ECA**")

    for fila in filas_cat:
        pid = fila["parametro_id"]
        lim_max = fila["lim_max"]
        lim_min = fila["lim_min"]
        codigo = fila.get("codigo")

        cols = st.columns(col_widths)
        cols[0].markdown(f"**{fila['parametro']}**")

        for j, n in enumerate(niveles):
            f_niv = n["filas_idx"].get(pid, {})
            existing_val = f_niv.get("valor_numerico")
            is_validado = bool(f_niv.get("validado"))
            cualif_n = f_niv.get("cualificador") or None
            _ev = float(existing_val) if existing_val is not None else None
            val = cols[1 + j].number_input(
                f"{fila['parametro']} ({n['meta']['codigo']})",
                value=_ev, step=0.01, format="%.4g",
                label_visibility="collapsed", disabled=is_validado,
                key=f"lab_col_v_{n['meta']['id'][:8]}_{pid}",
            )
            # Veredicto por nivel (NH3 usa el pH/T in situ propio del nivel)
            if codigo == COD_CYANO_CEL_ML:
                cols[1 + j].markdown(
                    _chip_oms_cianobacterias_cel(val), unsafe_allow_html=True,
                )
            elif codigo == COD_CYANO_BIOVOLUMEN:
                cols[1 + j].markdown(
                    _chip_oms_cianobacterias_biovol(val), unsafe_allow_html=True,
                )
            else:
                ver = evaluar_resultado_ctx(
                    n["datos"], pid, valor_lab=val, cualificador=cualif_n,
                )
                chip = _chip_veredicto_eca(ver)
                if chip:
                    cols[1 + j].markdown(chip, unsafe_allow_html=True)

            valores_por_nivel[j][pid] = {"valor": val}

        cols[1 + n_niv].caption(fila["unidad"])
        if lim_max is not None and lim_min is not None:
            cols[2 + n_niv].caption(f"{lim_min} – {lim_max}")
        elif lim_max is not None:
            cols[2 + n_niv].caption(f"≤ {lim_max}")
        elif lim_min is not None:
            cols[2 + n_niv].caption(f"≥ {lim_min}")
        else:
            cols[2 + n_niv].caption("—")


main()
