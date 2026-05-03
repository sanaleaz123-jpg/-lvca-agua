"""
services/mapa_service.py
Lógica de negocio para el geoportal interactivo.

Funciones públicas:
    get_puntos_geoportal(...)      → puntos con estado ECA y detalle de excedencias
    get_historial_punto(...)       → serie temporal de un parámetro en un punto
    get_limite_eca_parametro(...)   → límites ECA para la línea del gráfico
    get_ultimos_resultados_punto(...)→ últimos N resultados de un punto
    get_parametros_selector()      → lista de parámetros para el filtro
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from database.client import get_admin_client
from services.cache import cached
from services.punto_service import completar_latlon_desde_utm


# ─────────────────────────────────────────────────────────────────────────────
# Puntos con estado y excedencias (núcleo del geoportal)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_puntos_geoportal(
    fecha_inicio: str,
    fecha_fin:    str,
    campana_id:   Optional[str] = None,
) -> list[dict]:
    """
    Retorna todos los puntos activos con coordenadas, estado de excedencia
    y detalle de cada parámetro que excede el ECA.

    Cada punto incluye:
        id, codigo, nombre, latitud, longitud, altitud_msnm,
        tipo, cuenca, sistema_hidrico,
        eca  → {codigo, nombre}
        estado → 'excedencia' | 'cumple' | 'sin_datos'
        n_excedencias → int
        excedencias → [{parametro, codigo, valor, lim_max, lim_min, unidad, fecha}]
        ultima_fecha → str ISO date del resultado más reciente
    """
    db = get_admin_client()

    # 1. Todos los puntos activos con ECA
    pts = (
        db.table("puntos_muestreo")
        .select(
            "id, codigo, nombre, latitud, longitud, altitud_msnm, "
            "utm_este, utm_norte, utm_zona, "
            "tipo, cuenca, sistema_hidrico, eca_id, "
            "ecas(codigo, nombre)"
        )
        .eq("activo", True)
        .order("codigo")
        .execute()
    )
    puntos = pts.data or []

    # Completar lat/lon desde UTM para puntos que solo tienen coordenadas UTM
    for _p in puntos:
        completar_latlon_desde_utm(_p)

    # Filtrar puntos por campaña si se indicó
    if campana_id:
        cp_res = (
            db.table("campana_puntos")
            .select("punto_muestreo_id")
            .eq("campana_id", campana_id)
            .execute()
        )
        puntos_campana = {r["punto_muestreo_id"] for r in (cp_res.data or [])}
        puntos = [p for p in puntos if p["id"] in puntos_campana]

    # 2. Resultados en el rango de fechas
    query = (
        db.table("resultados_laboratorio")
        .select(
            "id, valor_numerico, fecha_analisis, "
            "parametros(id, codigo, nombre, unidades_medida(simbolo)), "
            "muestras(punto_muestreo_id, campana_id)"
        )
        .gte("fecha_analisis", fecha_inicio[:10])
        .lte("fecha_analisis", fecha_fin[:10])
        .not_.is_("valor_numerico", "null")
    )
    resultados = query.execute().data or []

    # Filtrar por campaña si se indicó
    if campana_id:
        resultados = [
            r for r in resultados
            if (r.get("muestras") or {}).get("campana_id") == campana_id
        ]

    # 3. Agrupar resultados por punto
    resultados_por_punto: dict[str, list] = {}
    for r in resultados:
        pid = (r.get("muestras") or {}).get("punto_muestreo_id")
        if pid:
            resultados_por_punto.setdefault(pid, []).append(r)

    # 4. Cargar límites ECA
    eca_ids = {p.get("eca_id") for p in puntos if p.get("eca_id")}
    param_ids = set()
    for r in resultados:
        pid = (r.get("parametros") or {}).get("id")
        if pid:
            param_ids.add(pid)

    limites: dict[tuple, dict] = {}
    if eca_ids and param_ids:
        lim_res = (
            db.table("eca_valores")
            .select("eca_id, parametro_id, valor_minimo, valor_maximo")
            .in_("eca_id", list(eca_ids))
            .in_("parametro_id", list(param_ids))
            .execute()
        )
        limites = {
            (l["eca_id"], l["parametro_id"]): l
            for l in (lim_res.data or [])
        }

    # 5. Calcular estado y excedencias por punto (contra su ECA específico)
    # Cada punto tiene su propio ECA según D.S. 004-2017-MINAM:
    #   4E1 (lagunas/embalses), 4E2 (ríos), 1A2 (consumo humano), 3D1 (riego)
    for p in puntos:
        p_res = resultados_por_punto.get(p["id"], [])
        eca_id = p.get("eca_id")
        p["excedencias"] = []
        p["ultima_fecha"] = None
        parametros_evaluados = set()

        for r in p_res:
            fecha = (r.get("fecha_analisis") or "")[:10]
            if not p["ultima_fecha"] or fecha > p["ultima_fecha"]:
                p["ultima_fecha"] = fecha

            prm = r.get("parametros") or {}
            param_id = prm.get("id")
            lim = limites.get((eca_id, param_id))
            if not lim:
                continue

            parametros_evaluados.add(param_id)
            valor = r["valor_numerico"]
            excede = (
                (lim.get("valor_maximo") is not None and valor > lim["valor_maximo"])
                or
                (lim.get("valor_minimo") is not None and valor < lim["valor_minimo"])
            )
            if excede:
                p["excedencias"].append({
                    "parametro":  prm.get("nombre", ""),
                    "codigo":     prm.get("codigo", ""),
                    "valor":      valor,
                    "lim_max":    lim.get("valor_maximo"),
                    "lim_min":    lim.get("valor_minimo"),
                    "unidad":     (prm.get("unidades_medida") or {}).get("simbolo", ""),
                    "fecha":      fecha,
                })

        n_evaluados = len(parametros_evaluados)
        n_exc = len(p["excedencias"])
        p["n_parametros_evaluados"] = n_evaluados
        p["n_excedencias"] = n_exc
        # Índice de cumplimiento: 1.0 = 100% cumple su ECA, 0.0 = nada cumple
        p["indice_cumplimiento"] = (
            round((n_evaluados - n_exc) / n_evaluados, 3)
            if n_evaluados > 0 else None
        )

        if p["excedencias"]:
            p["estado"] = "excedencia"
        elif p_res:
            p["estado"] = "cumple"
        else:
            p["estado"] = "sin_datos"

    # 6. Nivel de agua desde muestras (último valor disponible por punto)
    punto_ids = [p["id"] for p in puntos]
    if punto_ids:
        m_nivel_q = (
            db.table("muestras")
            .select("punto_muestreo_id, nivel_agua, fecha_muestreo")
            .in_("punto_muestreo_id", punto_ids)
            .not_.is_("nivel_agua", "null")
            .order("fecha_muestreo", desc=True)
        )
        if campana_id:
            m_nivel_q = m_nivel_q.eq("campana_id", campana_id)
        m_nivel = m_nivel_q.execute().data or []
        nivel_por_punto: dict[str, str] = {}
        for mn in m_nivel:
            pid = mn["punto_muestreo_id"]
            if pid not in nivel_por_punto:
                nivel_por_punto[pid] = mn["nivel_agua"]
        for p in puntos:
            p["nivel_agua"] = nivel_por_punto.get(p["id"])

    return puntos


# ─────────────────────────────────────────────────────────────────────────────
# Historial temporal de un parámetro en un punto (gráfico de tendencia)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=180)
def get_historial_punto(
    punto_id:     str,
    parametro_id: str,
    limite:       int = 50,
) -> list[dict]:
    """
    Serie temporal de un parámetro en un punto.

    Retorna lista de {fecha, fecha_muestreo, fecha_analisis, valor,
    muestra_codigo} ordenados por fecha de muestreo asc.

    `fecha` queda como alias de `fecha_muestreo` (la fecha en que el técnico
    de campo tomó la muestra) por ser la semánticamente correcta para gráficos
    de tendencia. `fecha_analisis` se conserva por si alguna pantalla la
    necesita explícitamente.
    """
    db = get_admin_client()

    # Muestras de este punto
    m_res = (
        db.table("muestras")
        .select("id")
        .eq("punto_muestreo_id", punto_id)
        .execute()
    )
    muestra_ids = [m["id"] for m in (m_res.data or [])]

    if not muestra_ids:
        return []

    # Resultados del parámetro para esas muestras
    r_res = (
        db.table("resultados_laboratorio")
        .select(
            "valor_numerico, fecha_analisis, "
            "muestras(codigo, fecha_muestreo)"
        )
        .eq("parametro_id", parametro_id)
        .in_("muestra_id", muestra_ids)
        .not_.is_("valor_numerico", "null")
        .order("fecha_analisis")
        .limit(limite)
        .execute()
    )

    items: list[dict] = []
    for r in (r_res.data or []):
        m = r.get("muestras") or {}
        fecha_muestreo = (m.get("fecha_muestreo") or "")[:10]
        fecha_analisis = (r.get("fecha_analisis") or "")[:10]
        items.append({
            "fecha":           fecha_muestreo or fecha_analisis,
            "fecha_muestreo":  fecha_muestreo,
            "fecha_analisis":  fecha_analisis,
            "valor":           r["valor_numerico"],
            "muestra_codigo":  m.get("codigo", ""),
        })

    # Orden cronológico por fecha de muestreo (fallback fecha_analisis)
    items.sort(key=lambda x: x["fecha"] or "")
    return items


@cached(ttl=600)
def get_limite_eca_parametro(
    punto_id:     str,
    parametro_id: str,
) -> dict:
    """
    Retorna los límites ECA de un parámetro para el punto indicado.
    {valor_minimo: float|None, valor_maximo: float|None, eca_codigo: str}
    """
    db = get_admin_client()

    pt = (
        db.table("puntos_muestreo")
        .select("eca_id, ecas(codigo)")
        .eq("id", punto_id)
        .single()
        .execute()
    )
    eca_id = pt.data.get("eca_id")
    eca_codigo = (pt.data.get("ecas") or {}).get("codigo", "")

    if not eca_id:
        return {"valor_minimo": None, "valor_maximo": None, "eca_codigo": ""}

    lim = (
        db.table("eca_valores")
        .select("valor_minimo, valor_maximo")
        .eq("eca_id", eca_id)
        .eq("parametro_id", parametro_id)
        .limit(1)
        .execute()
    )

    data = (lim.data[0] if lim.data else {})
    return {
        "valor_minimo": data.get("valor_minimo"),
        "valor_maximo": data.get("valor_maximo"),
        "eca_codigo":   eca_codigo,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Últimos resultados de un punto (tabla de detalle)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=180)
def get_ultimos_resultados_punto(
    punto_id: str,
    limite:   int = 10,
) -> list[dict]:
    """
    Últimos N resultados de un punto con nombre del parámetro y unidad.
    Ordenados por fecha descendente.
    """
    db = get_admin_client()

    m_res = (
        db.table("muestras")
        .select("id")
        .eq("punto_muestreo_id", punto_id)
        .execute()
    )
    muestra_ids = [m["id"] for m in (m_res.data or [])]

    if not muestra_ids:
        return []

    r_res = (
        db.table("resultados_laboratorio")
        .select(
            "valor_numerico, fecha_analisis, "
            "parametros(codigo, nombre, unidades_medida(simbolo)), "
            "muestras(codigo)"
        )
        .in_("muestra_id", muestra_ids)
        .not_.is_("valor_numerico", "null")
        .order("fecha_analisis", desc=True)
        .limit(limite)
        .execute()
    )

    return [
        {
            "fecha":      (r.get("fecha_analisis") or "")[:10],
            "muestra":    (r.get("muestras") or {}).get("codigo", ""),
            "parametro":  (r.get("parametros") or {}).get("nombre", ""),
            "codigo":     (r.get("parametros") or {}).get("codigo", ""),
            "valor":      r["valor_numerico"],
            "unidad":     ((r.get("parametros") or {}).get("unidades_medida") or {}).get("simbolo", ""),
        }
        for r in (r_res.data or [])
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Selector de parámetros (para el filtro del geoportal)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=600)
def get_parametros_selector() -> list[dict]:
    """Todos los parámetros activos con código, nombre, categoría y unidad."""
    db = get_admin_client()
    res = (
        db.table("parametros")
        .select("id, codigo, nombre, categorias_parametro(nombre), unidades_medida(simbolo)")
        .eq("activo", True)
        .order("codigo")
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────────────────────────────────────
# Tabla comparativa ECA: todos los parámetros de un punto vs límites
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_comparativa_eca_punto(
    punto_id: str,
    fecha_inicio: str,
    fecha_fin: str,
) -> list[dict]:
    """
    Retorna todos los parámetros con su último valor medido y los límites ECA
    correspondientes al punto, para una tabla comparativa completa.

    Cada dict: {parametro, codigo, categoria, valor, unidad, fecha,
                lim_min, lim_max, estado: 'excede'|'cumple'|'sin_dato'}
    """
    db = get_admin_client()

    # ECA del punto
    pt = (
        db.table("puntos_muestreo")
        .select("eca_id, ecas(codigo, nombre)")
        .eq("id", punto_id)
        .single()
        .execute()
    )
    eca_id = pt.data.get("eca_id")
    eca_info = pt.data.get("ecas") or {}

    # Muestras de este punto
    m_res = (
        db.table("muestras")
        .select("id")
        .eq("punto_muestreo_id", punto_id)
        .execute()
    )
    muestra_ids = [m["id"] for m in (m_res.data or [])]

    # Todos los parámetros activos
    params = (
        db.table("parametros")
        .select("id, codigo, nombre, categorias_parametro(nombre), unidades_medida(simbolo)")
        .eq("activo", True)
        .order("codigo")
        .execute()
    ).data or []

    # Límites ECA para este punto
    limites: dict[str, dict] = {}
    if eca_id:
        lim_res = (
            db.table("eca_valores")
            .select("parametro_id, valor_minimo, valor_maximo")
            .eq("eca_id", eca_id)
            .execute()
        )
        limites = {l["parametro_id"]: l for l in (lim_res.data or [])}

    # Últimos resultados por parámetro
    ultimos: dict[str, dict] = {}
    if muestra_ids:
        r_res = (
            db.table("resultados_laboratorio")
            .select("valor_numerico, fecha_analisis, parametro_id")
            .in_("muestra_id", muestra_ids)
            .gte("fecha_analisis", fecha_inicio[:10])
            .lte("fecha_analisis", fecha_fin[:10])
            .not_.is_("valor_numerico", "null")
            .order("fecha_analisis", desc=True)
            .execute()
        )
        for r in (r_res.data or []):
            pid = r["parametro_id"]
            if pid not in ultimos:
                ultimos[pid] = r

    # Construir tabla comparativa
    tabla = []
    for p in params:
        pid = p["id"]
        lim = limites.get(pid, {})
        ult = ultimos.get(pid)
        valor = ult["valor_numerico"] if ult else None
        fecha = (ult.get("fecha_analisis") or "")[:10] if ult else None

        lim_min = lim.get("valor_minimo")
        lim_max = lim.get("valor_maximo")

        # Estado
        tiene_eca = lim_min is not None or lim_max is not None
        if valor is None:
            estado = "sin_dato"
        elif not tiene_eca:
            estado = "sin_eca"
        elif (lim_max is not None and valor > lim_max) or (lim_min is not None and valor < lim_min):
            estado = "excede"
        else:
            estado = "cumple"

        tabla.append({
            "parametro":  p.get("nombre", ""),
            "codigo":     p.get("codigo", ""),
            "categoria":  (p.get("categorias_parametro") or {}).get("nombre", ""),
            "valor":      valor,
            "unidad":     (p.get("unidades_medida") or {}).get("simbolo", ""),
            "fecha":      fecha,
            "lim_min":    lim_min,
            "lim_max":    lim_max,
            "estado":     estado,
            "tiene_eca":  tiene_eca,
            "eca_codigo": eca_info.get("codigo", ""),
        })

    return tabla


# ─────────────────────────────────────────────────────────────────────────────
# Datos mensuales de un parámetro en todos los puntos (gráfico de barras)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=180)
def get_ultimo_valor_parametro_por_punto(
    parametro_id: str,
    fecha_inicio: str,
    fecha_fin: str,
    campana_id: Optional[str] = None,
) -> dict[str, dict]:
    """
    Para UN parámetro y un rango de fechas, devuelve el último valor por punto.
    Reemplaza el patrón N+1 de llamar get_comparativa_eca_punto N veces.

    Retorna: { punto_muestreo_id: {valor, fecha, lim_max, lim_min, estado} }
    """
    db = get_admin_client()

    query = (
        db.table("resultados_laboratorio")
        .select(
            "valor_numerico, fecha_analisis, "
            "muestras(punto_muestreo_id, campana_id, fecha_muestreo, "
            "  puntos_muestreo(eca_id))"
        )
        .eq("parametro_id", parametro_id)
        .gte("fecha_analisis", fecha_inicio[:10])
        .lte("fecha_analisis", fecha_fin[:10])
        .not_.is_("valor_numerico", "null")
        .order("fecha_analisis", desc=True)
    )
    rows = query.execute().data or []

    if campana_id:
        rows = [
            r for r in rows
            if (r.get("muestras") or {}).get("campana_id") == campana_id
        ]

    # Deduplicar por punto, quedándonos con el más reciente.
    # `fecha` retorna fecha_muestreo (cuando el campo tomó la muestra) si
    # está disponible — semánticamente correcta para charts comparativos —
    # con fallback a fecha_analisis para muestras heredadas.
    por_punto: dict[str, dict] = {}
    eca_ids: set[str] = set()
    for r in rows:
        m = r.get("muestras") or {}
        pid = m.get("punto_muestreo_id")
        if not pid or pid in por_punto:
            continue
        eca_id = (m.get("puntos_muestreo") or {}).get("eca_id")
        f_muestreo = (m.get("fecha_muestreo") or "")[:10]
        f_analisis = (r.get("fecha_analisis") or "")[:10]
        por_punto[pid] = {
            "valor":           r["valor_numerico"],
            "fecha":           f_muestreo or f_analisis,
            "fecha_muestreo":  f_muestreo,
            "fecha_analisis":  f_analisis,
            "eca_id":          eca_id,
        }
        if eca_id:
            eca_ids.add(eca_id)

    # Cargar límites ECA para todos los ECAs encontrados (1 query)
    limites: dict[str, dict] = {}
    if eca_ids:
        lim_res = (
            db.table("eca_valores")
            .select("eca_id, valor_minimo, valor_maximo")
            .in_("eca_id", list(eca_ids))
            .eq("parametro_id", parametro_id)
            .execute()
        )
        limites = {l["eca_id"]: l for l in (lim_res.data or [])}

    # Anotar cada punto con sus límites y estado
    for pid, info in por_punto.items():
        lim = limites.get(info.get("eca_id") or "")
        info["lim_max"] = (lim or {}).get("valor_maximo")
        info["lim_min"] = (lim or {}).get("valor_minimo")
        v = info["valor"]
        excede = (
            (info["lim_max"] is not None and v > info["lim_max"])
            or
            (info["lim_min"] is not None and v < info["lim_min"])
        )
        info["estado"] = "excede" if excede else "cumple" if lim else "sin_eca"

    return por_punto


@cached(ttl=300)
def get_datos_mensuales_parametro(
    parametro_id: str,
    anio: int,
    punto_id: str | None = None,
) -> list[dict]:
    """
    Retorna valores mensuales de un parámetro durante un año.

    Si se pasa punto_id, filtra solo a las muestras de ese punto.
    Si es None, devuelve todos los puntos activos.

    Cada dict: {punto_codigo, punto_nombre, mes (1-12), valor, fecha}
    """
    db = get_admin_client()

    fecha_inicio = f"{anio}-01-01"
    fecha_fin = f"{anio}-12-31"

    # Si filtramos por punto, primero obtenemos los muestra_ids de ese punto
    muestra_ids: list[str] | None = None
    if punto_id:
        m_res = (
            db.table("muestras")
            .select("id")
            .eq("punto_muestreo_id", punto_id)
            .gte("fecha_muestreo", fecha_inicio)
            .lte("fecha_muestreo", fecha_fin)
            .execute()
        )
        muestra_ids = [m["id"] for m in (m_res.data or [])]
        if not muestra_ids:
            return []

    query = (
        db.table("resultados_laboratorio")
        .select(
            "valor_numerico, fecha_analisis, "
            "muestras(punto_muestreo_id, puntos_muestreo(codigo, nombre))"
        )
        .eq("parametro_id", parametro_id)
        .gte("fecha_analisis", fecha_inicio)
        .lte("fecha_analisis", fecha_fin)
        .not_.is_("valor_numerico", "null")
        .order("fecha_analisis")
    )
    if muestra_ids is not None:
        query = query.in_("muestra_id", muestra_ids)
    r_res = query.execute()

    datos = []
    for r in (r_res.data or []):
        muestra = r.get("muestras") or {}
        punto = muestra.get("puntos_muestreo") or {}
        fecha = (r.get("fecha_analisis") or "")[:10]
        if not fecha or not punto.get("codigo"):
            continue
        mes = int(fecha[5:7])
        datos.append({
            "punto_codigo": punto.get("codigo", ""),
            "punto_nombre": punto.get("nombre", ""),
            "mes": mes,
            "valor": r["valor_numerico"],
            "fecha": fecha,
        })

    return datos
