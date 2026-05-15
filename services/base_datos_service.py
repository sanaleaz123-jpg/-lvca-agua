"""
services/base_datos_service.py
Lógica de negocio para la Base de Datos consolidada de resultados.

Funciones públicas:
    get_datos_consolidados(...)  → tabla pivotada: filas=muestras, cols=parámetros
    get_limites_eca_todos()      → {(eca_id, parametro_codigo): {min, max}}
    actualizar_resultado(...)    → editar un valor individual
    crear_resultado(...)         → insertar un valor nuevo
"""

from __future__ import annotations

from typing import Optional

from database.client import get_admin_client
from services.audit_service import registrar_cambio
from services.cache import cached
from services.parametro_registry import (
    get_columnas_parametros,
    get_codigos_parametros,
)


# Accesores dinámicos — se leen desde la BD (cacheados).
# Los módulos que importen COLUMNAS_PARAMETROS/CODIGOS_PARAMETROS
# obtienen funciones que siempre reflejan el estado actual de la BD.
COLUMNAS_PARAMETROS = get_columnas_parametros
CODIGOS_PARAMETROS = get_codigos_parametros


def get_datos_consolidados(
    campana_id: Optional[str] = None,
    punto_id: Optional[str] = None,
    fecha_inicio: Optional[str] = None,
    fecha_fin: Optional[str] = None,
    punto_ids=None,
) -> list[dict]:
    """
    Retorna una lista de dicts donde cada fila es una muestra
    con columnas pivotadas por parámetro + info de la muestra.

    Columnas fijas: muestra_id, codigo_muestra, punto_codigo, punto_nombre,
                    cuenca, tipo, eca_id, eca_codigo, fecha, hora, profundidad,
                    campana_id, campana_codigo, campana_nombre
    Columnas dinámicas: una por cada parámetro en COLUMNAS_PARAMETROS
                        con el valor numérico (o None)
    Columna extra: _resultado_ids → dict {param_codigo: resultado_id}

    Parámetros:
        punto_id:  filtra por un único punto_muestreo_id (legacy).
        punto_ids: filtra por varios punto_muestreo_id (tuple, hashable para cache).
                   Útil cuando un mismo "lugar de muestreo" agrupa varios puntos.
    """
    db = get_admin_client()

    # 1. Muestras con punto y ECA (campañas se cargan aparte, ver paso 1b).
    # Intentar incluir codigo_laboratorio (requiere migración 004)
    select_campos = (
        "id, codigo, fecha_muestreo, hora_recoleccion, "
        "campana_id, punto_muestreo_id, clima, nivel_agua, temperatura_transporte, "
        "puntos_muestreo(codigo, nombre, cuenca, tipo, eca_id, "
        "ecas(id, codigo, nombre))"
    )
    # Campos de profundidad (migración 005)
    _depth_extra = ""
    try:
        db.table("muestras").select("profundidad_tipo").limit(1).execute()
        _depth_extra = ", modo_muestreo, profundidad_tipo, profundidad_valor"
    except Exception:
        pass
    try:
        q_muestras = (
            db.table("muestras")
            .select(
                "id, codigo, codigo_laboratorio, fecha_muestreo, hora_recoleccion, "
                "campana_id, punto_muestreo_id, clima, nivel_agua, temperatura_transporte, "
                "puntos_muestreo(codigo, nombre, cuenca, tipo, eca_id, "
                "ecas(id, codigo, nombre))" + _depth_extra
            )
            .order("codigo", desc=False)
            .limit(5000)
        )
        # Test if the query works
        if campana_id:
            q_muestras = q_muestras.eq("campana_id", campana_id)
        if punto_id:
            q_muestras = q_muestras.eq("punto_muestreo_id", punto_id)
        if punto_ids:
            q_muestras = q_muestras.in_("punto_muestreo_id", list(punto_ids))
        if fecha_inicio:
            q_muestras = q_muestras.gte("fecha_muestreo", fecha_inicio)
        if fecha_fin:
            q_muestras = q_muestras.lte("fecha_muestreo", fecha_fin)
        muestras = q_muestras.execute().data or []
    except Exception:
        # Fallback without codigo_laboratorio
        q_muestras = (
            db.table("muestras")
            .select(select_campos)
            .order("codigo", desc=False)
            .limit(5000)
        )
        if campana_id:
            q_muestras = q_muestras.eq("campana_id", campana_id)
        if punto_id:
            q_muestras = q_muestras.eq("punto_muestreo_id", punto_id)
        if punto_ids:
            q_muestras = q_muestras.in_("punto_muestreo_id", list(punto_ids))
        if fecha_inicio:
            q_muestras = q_muestras.gte("fecha_muestreo", fecha_inicio)
        if fecha_fin:
            q_muestras = q_muestras.lte("fecha_muestreo", fecha_fin)
        muestras = q_muestras.execute().data or []

    # 1b. Cargar campañas referenciadas (query separado: evita problemas de
    # auto-detección de FK con embeds anidados en Supabase).
    camp_ids = list({m["campana_id"] for m in muestras if m.get("campana_id")})
    camp_info: dict[str, dict] = {}
    if camp_ids:
        try:
            r_camps = (
                db.table("campanas")
                .select("id, codigo, nombre, fecha_inicio")
                .in_("id", camp_ids)
                .execute()
            )
            camp_info = {c["id"]: c for c in (r_camps.data or [])}
        except Exception:
            camp_info = {}

    if not muestras:
        return []

    muestra_ids = [m["id"] for m in muestras]

    # 2. Resultados con parámetro
    r_res = (
        db.table("resultados_laboratorio")
        .select(
            "id, muestra_id, parametro_id, valor_numerico, "
            "parametros(codigo, nombre)"
        )
        .in_("muestra_id", muestra_ids)
        .execute()
    )
    resultados = r_res.data or []

    # Indexar resultados: {muestra_id: {param_codigo: {valor, resultado_id}}}
    res_index: dict[str, dict[str, dict]] = {}
    for r in resultados:
        mid = r["muestra_id"]
        param = r.get("parametros") or {}
        pcod = param.get("codigo", "")
        if not pcod:
            continue
        res_index.setdefault(mid, {})[pcod] = {
            "valor": r.get("valor_numerico"),
            "resultado_id": r["id"],
            "parametro_id": r["parametro_id"],
        }

    # 3. Construir filas pivotadas (columnas dinámicas desde BD)
    columnas = get_columnas_parametros()

    filas = []
    for m in muestras:
        punto = m.get("puntos_muestreo") or {}
        eca = punto.get("ecas") or {}
        camp = camp_info.get(m.get("campana_id") or "") or {}

        # Sufijo de profundidad para muestras de columna
        prof_tipo = m.get("profundidad_tipo")
        prof_suf_map = {"S": " (S)", "M": " (M)", "F": " (F)"}
        prof_suf = prof_suf_map.get(prof_tipo, "")

        fila = {
            "muestra_id": m["id"],
            "codigo_muestra": m.get("codigo", "") + prof_suf,
            "codigo_laboratorio": m.get("codigo_laboratorio", ""),
            "punto_codigo": punto.get("codigo", ""),
            "punto_nombre": punto.get("nombre", ""),
            "cuenca": punto.get("cuenca", ""),
            "tipo": punto.get("tipo", ""),
            "eca_id": punto.get("eca_id"),
            "eca_codigo": eca.get("codigo", ""),
            "fecha": str(m.get("fecha_muestreo") or "")[:10],
            "hora": m.get("hora_recoleccion", "") or "",
            "clima": m.get("clima", ""),
            "nivel_agua": m.get("nivel_agua", ""),
            "temperatura_transporte": m.get("temperatura_transporte"),
            "profundidad": m.get("profundidad_valor"),
            "campana_id": m.get("campana_id"),
            "campana_codigo": camp.get("codigo", ""),
            "campana_nombre": camp.get("nombre", ""),
            "campana_fecha_inicio": str(camp.get("fecha_inicio") or "")[:10],
            "_resultado_ids": {},
        }

        resultados_muestra = res_index.get(m["id"], {})
        for pcod, _ in columnas:
            info = resultados_muestra.get(pcod)
            if info:
                fila[pcod] = info["valor"]
                fila["_resultado_ids"][pcod] = {
                    "resultado_id": info["resultado_id"],
                    "parametro_id": info["parametro_id"],
                }
            else:
                fila[pcod] = None

        filas.append(fila)

    return filas


@cached(ttl=600)
def get_limites_eca_todos() -> dict[tuple[str, str], dict]:
    """
    Retorna un dict {(eca_id, parametro_codigo): {valor_minimo, valor_maximo}}
    para todos los ECAs y parámetros activos.
    """
    db = get_admin_client()

    # Parámetros con código
    params = (
        db.table("parametros")
        .select("id, codigo")
        .eq("activo", True)
        .execute()
    ).data or []
    param_id_to_code = {p["id"]: p["codigo"] for p in params}

    # Límites ECA
    limites_raw = (
        db.table("eca_valores")
        .select("eca_id, parametro_id, valor_minimo, valor_maximo")
        .execute()
    ).data or []

    limites = {}
    for lim in limites_raw:
        pcod = param_id_to_code.get(lim["parametro_id"])
        if pcod:
            limites[(lim["eca_id"], pcod)] = {
                "valor_minimo": lim.get("valor_minimo"),
                "valor_maximo": lim.get("valor_maximo"),
            }

    return limites


def actualizar_resultado(resultado_id: str, valor: float | None) -> None:
    """Actualiza el valor numérico de un resultado existente. Registra el cambio."""
    db = get_admin_client()

    # Leer valor anterior para auditoría
    anterior = (
        db.table("resultados_laboratorio")
        .select("valor_numerico, parametro_id, parametros(codigo)")
        .eq("id", resultado_id)
        .single()
        .execute()
    ).data or {}
    val_ant = anterior.get("valor_numerico")
    param_cod = (anterior.get("parametros") or {}).get("codigo", "")

    db.table("resultados_laboratorio").update(
        {"valor_numerico": valor}
    ).eq("id", resultado_id).execute()

    # Registrar cambio si el valor es diferente
    if str(val_ant) != str(valor):
        registrar_cambio(
            tabla="resultados_laboratorio",
            registro_id=resultado_id,
            accion="editar",
            campo=f"valor_numerico ({param_cod})",
            valor_anterior=str(val_ant) if val_ant is not None else None,
            valor_nuevo=str(valor) if valor is not None else None,
        )

    _invalidar_cache()


def crear_resultado(muestra_id: str, parametro_id: str, valor: float) -> dict:
    """Crea un nuevo resultado de laboratorio."""
    db = get_admin_client()
    res = db.table("resultados_laboratorio").insert({
        "muestra_id": muestra_id,
        "parametro_id": parametro_id,
        "valor_numerico": valor,
    }).execute()
    _invalidar_cache()
    return res.data[0]


def get_parametros_map() -> dict[str, str]:
    """Retorna {codigo: parametro_id} para crear nuevos resultados."""
    db = get_admin_client()
    params = (
        db.table("parametros")
        .select("id, codigo")
        .eq("activo", True)
        .execute()
    ).data or []
    return {p["codigo"]: p["id"] for p in params}


def _invalidar_cache() -> None:
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass
