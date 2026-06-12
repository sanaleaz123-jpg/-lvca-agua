"""
components/nav_context.py
Sistema central de navegación entre páginas con contexto por ID.

Antes cada página inventaba su propia clave de session_state para
pre-seleccionar algo en otra página (reg_camp, sel_campana, inf_campana...),
escribiendo el *label* exacto del selectbox destino. Eso es frágil: si el
formato del label cambia, el enlace se rompe en silencio (pasó con
Campañas → Muestras de Campo).

Este módulo estandariza el patrón con IDs, no labels:

    # Página origen
    from components.nav_context import ir_a
    ir_a("resultados", campana_id=camp["id"])

    # Página destino (al inicio de main, antes de crear widgets)
    from components.nav_context import consumir_contexto
    ctx = consumir_contexto("resultados")
    ...
    # al construir el selectbox {label: id}:
    preseleccionar("sel_campana", opciones_c, ctx.get("campana_id"))

El contexto viaja en session_state["_nav_ctx"], etiquetado con la página
destino, y se consume (pop) una sola vez: los reruns posteriores no lo
re-aplican, así el usuario puede cambiar el selector libremente.

Claves de contexto convencionales:
    campana_id, punto_id, muestra_id, parametro_id, parametro_codigo
"""

from __future__ import annotations

from typing import Any

import streamlit as st

_CTX_KEY = "_nav_ctx"

# Alias corto → ruta de página. Único lugar donde se mapean rutas.
PAGINAS: dict[str, str] = {
    "inicio":     "pages/1_Inicio.py",
    "campanas":   "pages/2_Campanas.py",
    "muestras":   "pages/3_Muestras_Campo.py",
    "resultados": "pages/4_Resultados_Lab.py",
    "parametros": "pages/5_Parametros.py",
    "puntos":     "pages/6_Puntos_Muestreo.py",
    "geoportal":  "pages/7_Geoportal.py",
    "informes":   "pages/8_Informes.py",
    "admin":      "pages/9_Administracion.py",
    "base_datos": "pages/10_Base_Datos.py",
}


def _ruta(pagina: str) -> str:
    """Acepta alias ('resultados') o ruta directa ('pages/4_Resultados_Lab.py')."""
    return PAGINAS.get(pagina, pagina)


def ir_a(pagina: str, **contexto: Any) -> None:
    """
    Navega a otra página dejando contexto identificado por IDs.

        ir_a("resultados", campana_id=camp["id"], punto_id=punto["id"])
    """
    destino = _ruta(pagina)
    if contexto:
        st.session_state[_CTX_KEY] = {"_destino": destino, **contexto}
    else:
        st.session_state.pop(_CTX_KEY, None)
    st.switch_page(destino)


# Claves de contexto aceptadas también como query params de la URL
# (deep links compartibles: .../Resultados_Lab?campana_id=...&muestra_id=...)
_QP_CLAVES = ("campana_id", "punto_id", "muestra_id", "parametro_id")


def consumir_contexto(pagina: str) -> dict:
    """
    Devuelve y elimina el contexto si fue dejado para esta página.
    Si no hay contexto de sesión, intenta leerlo de los query params de la
    URL (deep link compartido) — también one-shot: se consumen al aplicarse,
    así el usuario puede cambiar los selectores libremente después.
    Llamar al inicio de main(), ANTES de instanciar los widgets afectados.
    """
    ctx = st.session_state.get(_CTX_KEY)
    if isinstance(ctx, dict) and ctx.get("_destino") == _ruta(pagina):
        st.session_state.pop(_CTX_KEY, None)
        ctx = dict(ctx)
        ctx.pop("_destino", None)
        return ctx

    # Fallback: deep link por URL
    try:
        qp = {k: st.query_params[k] for k in _QP_CLAVES if k in st.query_params}
        for k in qp:
            del st.query_params[k]
        return qp
    except Exception:
        return {}


def rol_alcanza(rol_minimo: str) -> bool:
    """
    True si la sesión activa alcanza el rol indicado. Útil para mostrar
    atajos de navegación solo a quien puede entrar a la página destino
    (evita aterrizar en 'Acceso denegado').
    """
    sesion = st.session_state.get("sesion")
    try:
        return bool(sesion and sesion.tiene_rol(rol_minimo))
    except Exception:
        return False


def preseleccionar(widget_key: str, opciones: dict, valor_id: Any) -> bool:
    """
    Dado un dict de selectbox {label: id} y un id objetivo, fija en
    session_state[widget_key] el label correspondiente para que el
    selectbox nazca pre-seleccionado. Retorna True si hubo match.

    Debe ejecutarse ANTES de crear el widget con esa key.
    """
    if valor_id is None:
        return False
    for label, _id in opciones.items():
        if _id == valor_id:
            st.session_state[widget_key] = label
            return True
    return False
