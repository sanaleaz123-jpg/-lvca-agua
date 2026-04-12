"""
pages/4_Resultados_Lab.py
Ingreso de resultados de laboratorio con semáforo ECA en tiempo real.

Flujo:
    1. Seleccionar campaña → punto de muestreo → muestra
    2. Editar parámetros (valor, observaciones) con inputs individuales
    3. Semáforo automático en tiempo real: 🟢 cumple / 🔴 excede
       Parámetros sin ECA o sin valor no muestran indicador.
    4. Guardar → upsert en resultados_laboratorio

Acceso mínimo: visualizador
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

from components.auth_guard import require_rol
from services.resultado_service import (
    get_campanas,
    get_puntos_de_campana,
    get_muestras,
    get_datos_muestra,
    guardar_resultados_lote,
    eliminar_resultados_muestra,
    _get_usuario_interno_id,
)

# ─── Constantes de visualización ─────────────────────────────────────────────

CATEGORIAS_ORDEN = ["Campo", "Fisicoquimico", "Hidrobiologico"]

_BG_VERDE = "#d4edda"
_BG_ROJO = "#f8d7da"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _semaforo_eca(valor, lim_min, lim_max) -> tuple[str, str]:
    """
    Retorna (emoji, color_fondo) para el valor y límites ECA dados.
    Cadenas vacías cuando no hay indicador que mostrar.
    """
    if valor is None or (lim_max is None and lim_min is None):
        return "", ""
    excede = (
        (lim_max is not None and valor > lim_max)
        or (lim_min is not None and valor < lim_min)
    )
    if excede:
        return "🔴", _BG_ROJO
    return "🟢", _BG_VERDE


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
            "categoria":      (p.get("categorias_parametro") or {}).get("nombre", "Sin categoría"),
            "valor_numerico": resultado.get("valor_numerico"),
            "unidad":         (p.get("unidades_medida") or {}).get("simbolo", ""),
            "lim_max":        limite.get("valor_maximo"),
            "lim_min":        limite.get("valor_minimo"),
            "observaciones":  resultado.get("observaciones") or "",
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
) -> dict[str, dict]:
    """
    Renderiza inputs individuales por parámetro con semáforo ECA en tiempo real.
    Retorna {parametro_id: {valor, observaciones}}.
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
    cs[2].caption(f"🔴 Exceden: **{n_exc}**")

    # Encabezado
    hcols = st.columns([3, 2, 0.7, 1, 0.6, 0.5])
    hcols[0].markdown("**Parámetro**")
    hcols[1].markdown("**Valor medido**")
    hcols[2].markdown("**Unidad**")
    hcols[3].markdown("**Lím. ECA**")
    hcols[4].markdown("**ECA**")
    hcols[5].markdown("")

    valores: dict[str, dict] = {}

    for fila in filas_cat:
        pid = fila["parametro_id"]
        lim_max = fila["lim_max"]
        lim_min = fila["lim_min"]
        existing_val = fila["valor_numerico"]

        cols = st.columns([3, 2, 0.7, 1, 0.6, 0.5])

        # Nombre del parámetro
        cols[0].markdown(f"**{fila['parametro']}**")

        # Input de valor (value=None muestra campo vacío)
        val = cols[1].number_input(
            fila["parametro"],
            value=existing_val,
            format="%.4g",
            label_visibility="collapsed",
            key=f"lab_v_{key_prefix}_{pid}",
        )

        # Unidad
        cols[2].caption(fila["unidad"])

        # Límite ECA
        if lim_max is not None and lim_min is not None:
            cols[3].caption(f"{lim_min} – {lim_max}")
        elif lim_max is not None:
            cols[3].caption(f"≤ {lim_max}")
        elif lim_min is not None:
            cols[3].caption(f"≥ {lim_min}")
        else:
            cols[3].caption("—")

        # Semáforo ECA en tiempo real (desde el valor actual del widget)
        emoji, bg = _semaforo_eca(val, lim_min, lim_max)
        if emoji:
            cols[4].markdown(
                f'<div style="background:{bg};padding:2px 8px;border-radius:4px;'
                f'text-align:center;font-size:1.1em">{emoji}</div>',
                unsafe_allow_html=True,
            )

        # Badge de guardado (✅ para parámetros ya persistidos en BD)
        if pid in saved_params:
            cols[5].markdown(
                '<div style="text-align:center" title="Guardado">✅</div>',
                unsafe_allow_html=True,
            )

        valores[pid] = {"valor": val, "observaciones": ""}

    # Observaciones en sección colapsable
    with st.expander("📝 Observaciones", expanded=False):
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

    st.title("Resultados de Laboratorio")
    st.caption("Ingreso y validación con semáforo ECA  ·  D.S. N° 004-2017-MINAM")

    # ── Selección en cascada ─────────────────────────────────────────────────
    with st.expander("📋 Seleccionar muestra", expanded=True):
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
    m3.metric("🔴 Exceden ECA", exceden_db)
    m4.metric("🟢 Cumplen ECA", cumplen_db)

    if exceden_db > 0:
        st.error(
            f"⚠️ **{exceden_db} parámetro(s) exceden el límite ECA** "
            f"({eca.get('codigo','')}) para este punto de muestreo."
        )

    st.divider()

    # ── Leyenda del semáforo ──────────────────────────────────────────────────
    with st.expander("Leyenda del semáforo ECA"):
        lc1, lc2, lc3 = st.columns(3)
        lc1.markdown("🟢 **Cumple** — valor dentro del límite ECA")
        lc2.markdown("🔴 **Excede** — valor supera el límite ECA")
        lc3.markdown("Sin indicador — parámetro sin ECA asignado o sin valor")

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
            cat_vals = _render_categoria(cats[cat], key_prefix, saved_params)
            all_valores.update(cat_vals)

    # ── Botón de guardado ─────────────────────────────────────────────────────
    st.divider()
    col_btn, col_space = st.columns([2, 5])
    with col_btn:
        guardar = st.button(
            "💾 Guardar resultados",
            type="primary",
            use_container_width=True,
        )

    if guardar:
        cambios = []
        for pid, data in all_valores.items():
            valor = data.get("valor")
            obs = data.get("observaciones", "")
            if valor is None and not obs:
                continue
            cambios.append({
                "parametro_id":   pid,
                "valor_numerico": float(valor) if valor is not None else None,
                "valor_texto":    None,
                "observaciones":  obs or None,
            })

        if not cambios:
            st.warning("No hay valores para guardar. Ingresa al menos un resultado.")
        else:
            analista_id = _get_usuario_interno_id(sesion.uid)
            with st.spinner(f"Guardando {len(cambios)} resultado(s)..."):
                ok, errores = guardar_resultados_lote(
                    muestra_id=muestra_id,
                    filas=cambios,
                    analista_id=analista_id,
                )

            if errores:
                st.error(f"Se guardaron {ok}/{len(cambios)} resultados. Errores:")
                for e in errores:
                    st.caption(f"• {e}")
            else:
                # Marcar parámetros como guardados (persiste hasta navegar fuera)
                st.session_state[saved_key] = {c["parametro_id"] for c in cambios}
                st.session_state[msg_key] = (
                    f"✅ {ok} resultado(s) guardado(s) correctamente."
                )
                # Invalidar caché para carga fresca en el siguiente render
                get_datos_muestra.clear()
                st.rerun()

    # ── Eliminar todos los resultados de esta muestra ────────────────────────
    sesion_rol = sesion.rol if sesion else "visitante"
    if sesion_rol == "administrador" and con_valor > 0:
        with st.expander("🗑️ Eliminar todos los resultados de esta muestra", expanded=False):
            st.warning(
                f"Se eliminarán **{con_valor} resultado(s)** de laboratorio para esta muestra. "
                "Esta acción no se puede deshacer."
            )
            if st.button("Eliminar todos los resultados", key="btn_eliminar_resultados", type="primary"):
                try:
                    n = eliminar_resultados_muestra(muestra_id)
                    st.session_state.pop(saved_key, None)
                    st.session_state.pop(msg_key, None)
                    get_datos_muestra.clear()
                    st.success(f"{n} resultado(s) eliminado(s).")
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
            f"🔴 Detalle de excedencias ({len(excedencias_rt)} parámetros)",
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
