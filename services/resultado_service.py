"""
services/resultado_service.py
Lógica de negocio para resultados de laboratorio y alertas ECA.

Funciones públicas:
    get_datos_muestra(muestra_id)          → todo lo necesario para la pantalla
    get_resultados_por_muestra(muestra_id) → resultados existentes con semáforo ECA
    guardar_resultado(...)                 → upsert individual
    guardar_resultados_lote(...)           → upsert de múltiples filas
    get_excedencias_activas(dias)          → para el dashboard de alertas
    get_campanas()                         → lista de campañas activas/cerradas
    get_puntos_de_campana(campana_id)      → puntos con muestras en la campaña
    get_muestras(campana_id, punto_id)     → muestras filtradas
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from database.client import get_db
from services.cache import cached
from services.audit_service import registrar_cambio
from services.logging_config import get_logger

logger = get_logger(__name__)


def _invalidar_cache() -> None:
    """Limpia cachés tras modificar resultados."""
    try:
        from services.cache import invalidate_operational
        invalidate_operational()
    except Exception:
        logger.warning("No se pudo invalidar el caché tras modificar un resultado "
                       "(posibles datos obsoletos hasta el próximo TTL).", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ResultadoItem:
    """Un parámetro con su valor medido y su estado ECA."""
    parametro_id: str
    codigo: str
    nombre: str
    categoria: str
    unidad: str
    valor_numerico: Optional[float]
    valor_texto: Optional[str]
    lim_min: Optional[float]
    lim_max: Optional[float]
    observaciones: str = ""
    resultado_id: Optional[str] = None

    @property
    def estado_eca(self) -> str:
        """'cumple' | 'excede' | 'sin_limite' | 'sin_dato'"""
        if self.valor_numerico is None and not self.valor_texto:
            return "sin_dato"
        if self.lim_max is None and self.lim_min is None:
            return "sin_limite"
        if self.valor_numerico is not None:
            if self.lim_max is not None and self.valor_numerico > self.lim_max:
                return "excede"
            if self.lim_min is not None and self.valor_numerico < self.lim_min:
                return "excede"
        return "cumple"

    @property
    def semaforo(self) -> str:
        return {
            "cumple":     "🟢",
            "excede":     "🔴",
            "sin_limite": "⚪",
            "sin_dato":   "⬜",
        }[self.estado_eca]


# ─────────────────────────────────────────────────────────────────────────────
# Selectores (cascada campaña → punto → muestra)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_campanas() -> list[dict]:
    """Campañas ordenadas por fecha descendente."""
    db = get_db()
    res = (
        db.table("campanas")
        .select("id, codigo, nombre, fecha_inicio, fecha_fin, estado")
        .order("fecha_inicio", desc=True)
        .execute()
    )
    return res.data or []


@cached(ttl=300)
def get_puntos_de_campana(campana_id: str) -> list[dict]:
    """
    Retorna los puntos de muestreo que tienen al menos una muestra
    en la campaña indicada.
    """
    db = get_db()
    res = (
        db.table("muestras")
        .select("punto_muestreo_id, puntos_muestreo(id, codigo, nombre)")
        .eq("campana_id", campana_id)
        .execute()
    )
    vistos: set[str] = set()
    puntos: list[dict] = []
    for fila in (res.data or []):
        p = fila.get("puntos_muestreo") or {}
        pid = p.get("id")
        if pid and pid not in vistos:
            vistos.add(pid)
            puntos.append(p)
    return sorted(puntos, key=lambda x: x.get("codigo", ""))


@cached(ttl=120)
def get_muestras(campana_id: str, punto_id: str) -> list[dict]:
    """Muestras de una campaña y punto concretos.

    Incluye los campos de columna de agua (modo_muestreo, profundidad_tipo,
    grupo_profundidad, profundidad_valor) para que la página de resultados pueda
    agrupar los niveles S/M/F de un mismo muestreo en una tabla unificada.
    """
    db = get_db()
    try:
        res = (
            db.table("muestras")
            .select(
                "id, codigo, fecha_muestreo, estado, "
                "modo_muestreo, profundidad_tipo, grupo_profundidad, profundidad_valor"
            )
            .eq("campana_id", campana_id)
            .eq("punto_muestreo_id", punto_id)
            .order("fecha_muestreo", desc=True)
            .execute()
        )
    except Exception:
        # Fallback pre-migración 005 (sin columnas de profundidad)
        res = (
            db.table("muestras")
            .select("id, codigo, fecha_muestreo, estado")
            .eq("campana_id", campana_id)
            .eq("punto_muestreo_id", punto_id)
            .order("fecha_muestreo", desc=True)
            .execute()
        )
    return res.data or []


# Orden canónico de niveles de columna de agua
_ORDEN_PROF = {"S": 0, "M": 1, "F": 2}


@cached(ttl=120)
def get_grupo_columna(muestra_id: str) -> list[dict]:
    """
    Si la muestra pertenece a un muestreo en columna de agua, retorna TODAS las
    muestras del grupo (S/M/F) ordenadas Superficie → Medio → Fondo. Si no es
    columna (o la migración 005 no está aplicada), retorna lista vacía.

    Cada elemento: {id, codigo, profundidad_tipo, profundidad_valor}.
    """
    db = get_db()
    try:
        row = (
            db.table("muestras")
            .select("grupo_profundidad, modo_muestreo")
            .eq("id", muestra_id)
            .limit(1)
            .execute()
        )
    except Exception:
        return []
    data = (row.data or [{}])[0]
    grupo = data.get("grupo_profundidad")
    if not grupo or data.get("modo_muestreo") != "columna":
        return []
    res = (
        db.table("muestras")
        .select("id, codigo, profundidad_tipo, profundidad_valor")
        .eq("grupo_profundidad", grupo)
        .execute()
    )
    muestras = res.data or []
    muestras.sort(key=lambda m: _ORDEN_PROF.get(m.get("profundidad_tipo"), 9))
    return muestras


# ─────────────────────────────────────────────────────────────────────────────
# Carga del bloque de datos para la pantalla de resultados
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=120)
def get_datos_muestra(muestra_id: str) -> dict:
    """
    Devuelve un dict con todo lo necesario para renderizar la página:
        muestra       → info de la muestra + punto + ECA + mediciones in situ
        parametros    → lista completa de parámetros activos con metadata ECA
        limites       → {parametro_id: {valor_min, valor_max, expresado_como, forma_analitica}}
        resultados    → {parametro_id: {id, valor_numerico, valor_texto, observaciones, ...}}
        mediciones    → {parametro_text: valor}  (pH, T, etc. in situ)
        excepciones   → {parametro_id: True}  (Art. 6 vigentes para el punto)
    """
    db = get_db()

    # 1. Muestra → punto (con flag Art. 7) → ECA
    m = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, estado, campana_id, "
            "puntos_muestreo(id, codigo, nombre, eca_id, dentro_zona_mezcla, "
            "  ecas(id, codigo, nombre))"
        )
        .eq("id", muestra_id)
        .single()
        .execute()
    )
    muestra = m.data
    punto = muestra.get("puntos_muestreo") or {}
    eca_info = punto.get("ecas") or {}
    eca_id = punto.get("eca_id")
    eca_codigo = eca_info.get("codigo")
    punto_id = punto.get("id")

    # 2. Límites ECA para este punto (con metadata de migraciones 010 y 012)
    limites: dict[str, dict] = {}
    if eca_id:
        try:
            lim_res = (
                db.table("eca_valores")
                .select(
                    "parametro_id, valor_minimo, valor_maximo, "
                    "expresado_como, forma_analitica"
                )
                .eq("eca_id", eca_id)
                .execute()
            )
        except Exception:
            # Fallback pre-migración 010/012
            lim_res = (
                db.table("eca_valores")
                .select("parametro_id, valor_minimo, valor_maximo")
                .eq("eca_id", eca_id)
                .execute()
            )
        limites = {r["parametro_id"]: r for r in (lim_res.data or [])}

    # 3. Todos los parámetros activos con unidad, categoría y metadata ECA
    #    Excluir categorías que no se usan (Plaguicidas, Microbiologico)
    try:
        par_res = (
            db.table("parametros")
            .select(
                "id, codigo, nombre, "
                "es_eca, observacion_tecnica, forma_analitica, lmd, lcm, "
                "unidades_medida(simbolo), "
                "categorias_parametro(nombre)"
            )
            .eq("activo", True)
            .order("codigo")
            .execute()
        )
    except Exception:
        # Fallback pre-migraciones 006/010/012
        par_res = (
            db.table("parametros")
            .select(
                "id, codigo, nombre, "
                "unidades_medida(simbolo), "
                "categorias_parametro(nombre)"
            )
            .eq("activo", True)
            .order("codigo")
            .execute()
        )
    from services.parametro_registry import clasificar_categoria
    _CATEGORIAS_EXCLUIDAS = {"Plaguicidas", "Microbiologico"}
    par_data = []
    for p in (par_res.data or []):
        cat_nombre = clasificar_categoria(p)
        if cat_nombre in _CATEGORIAS_EXCLUIDAS:
            continue
        if p.get("categorias_parametro"):
            p["categorias_parametro"] = {"nombre": cat_nombre}
        par_data.append(p)

    # 4. Resultados ya guardados para esta muestra
    try:
        res_res = (
            db.table("resultados_laboratorio")
            .select("id, parametro_id, valor_numerico, valor_texto, observaciones, "
                    "cualificador, validado, validado_at")
            .eq("muestra_id", muestra_id)
            .execute()
        )
    except Exception:
        # Fallback pre-migración 006
        res_res = (
            db.table("resultados_laboratorio")
            .select("id, parametro_id, valor_numerico, valor_texto, observaciones")
            .eq("muestra_id", muestra_id)
            .execute()
        )
    resultados = {r["parametro_id"]: r for r in (res_res.data or [])}

    # 5. Mediciones in situ (pH, T, etc.) — necesarias para NH3 Cat 4
    mediciones: dict[str, float] = {}
    try:
        ins_res = (
            db.table("mediciones_insitu")
            .select("parametro, valor")
            .eq("muestra_id", muestra_id)
            .execute()
        )
        for r in (ins_res.data or []):
            key = (r.get("parametro") or "").lower().strip()
            if r.get("valor") is not None:
                mediciones[key] = float(r["valor"])
    except Exception:
        pass  # tabla existe desde v1, pero defensivo

    # 6. Excepciones Art. 6 vigentes para este punto
    excepciones: dict[str, bool] = {}
    if punto_id:
        try:
            exc_res = (
                db.table("excepciones_art6")
                .select("parametro_id, fecha_vencimiento")
                .eq("punto_muestreo_id", punto_id)
                .eq("vigente", True)
                .execute()
            )
            from datetime import date as _date
            hoy = _date.today().isoformat()
            for r in (exc_res.data or []):
                venc = r.get("fecha_vencimiento")
                if venc is None or venc >= hoy:
                    excepciones[r["parametro_id"]] = True
        except Exception:
            pass  # migración 013 aún no aplicada en entornos antiguos

    return {
        "muestra":     muestra,
        "eca_id":      eca_id,
        "eca_codigo":  eca_codigo,
        "punto_id":    punto_id,
        "dentro_zona_mezcla": bool(punto.get("dentro_zona_mezcla")),
        "limites":     limites,
        "parametros":  par_data,
        "resultados":  resultados,
        "mediciones":  mediciones,
        "excepciones": excepciones,
    }


# ─────────────────────────────────────────────────────────────────────────────
# API pública: consulta de resultados con semáforo
# ─────────────────────────────────────────────────────────────────────────────

def get_resultados_por_muestra(muestra_id: str) -> list[ResultadoItem]:
    """
    Retorna la lista completa de parámetros con sus valores y estado ECA.
    Parámetros sin valor tienen estado 'sin_dato'.
    """
    datos = get_datos_muestra(muestra_id)
    items: list[ResultadoItem] = []

    for p in datos["parametros"]:
        pid = p["id"]
        resultado = datos["resultados"].get(pid, {})
        limite = datos["limites"].get(pid, {})
        items.append(ResultadoItem(
            parametro_id   = pid,
            codigo         = p["codigo"],
            nombre         = p["nombre"],
            categoria      = (p.get("categorias_parametro") or {}).get("nombre", ""),
            unidad         = (p.get("unidades_medida") or {}).get("simbolo", ""),
            valor_numerico = resultado.get("valor_numerico"),
            valor_texto    = resultado.get("valor_texto"),
            lim_min        = limite.get("valor_minimo"),
            lim_max        = limite.get("valor_maximo"),
            observaciones  = resultado.get("observaciones") or "",
            resultado_id   = resultado.get("id"),
        ))
    return items


# ─────────────────────────────────────────────────────────────────────────────
# API pública: guardado
# ─────────────────────────────────────────────────────────────────────────────

def guardar_resultado(
    muestra_id:     str,
    parametro_id:   str,
    valor_numerico: Optional[float],
    valor_texto:    Optional[str],
    observaciones:  str,
    analista_id:    Optional[str] = None,
) -> None:
    """
    Upsert idempotente de un resultado individual.
    Conflict key: (muestra_id, parametro_id).
    """
    db = get_db()
    fila = {
        "muestra_id":     muestra_id,
        "parametro_id":   parametro_id,
        "valor_numerico": valor_numerico,
        "valor_texto":    valor_texto,
        "observaciones":  observaciones or None,
        "analista_id":    analista_id,
        "fecha_analisis": datetime.utcnow().date().isoformat(),
    }
    db.table("resultados_laboratorio").upsert(
        fila, on_conflict="muestra_id,parametro_id"
    ).execute()
    _invalidar_cache()


def guardar_resultados_lote(
    muestra_id:  str,
    filas:       list[dict],   # [{parametro_id, valor_numerico, valor_texto, observaciones, cualificador}]
    analista_id: Optional[str] = None,
) -> tuple[int, list[str], list[str]]:
    """
    Guarda múltiples resultados en lotes de 50.

    Resultados ya marcados como validado=true NO se sobreescriben — quedan
    bloqueados hasta que un administrador los desvalide explícitamente.

    Retorna (ok_count, lista_de_errores, lista_de_bloqueados).
    """
    db = get_db()
    hoy = datetime.utcnow().date().isoformat()
    ok = 0
    errores: list[str] = []
    bloqueados: list[str] = []
    LOTE = 50

    # Identificar parámetros con resultado validado (no se pueden sobreescribir)
    param_ids = [f["parametro_id"] for f in filas]
    if param_ids:
        try:
            res_val = (
                db.table("resultados_laboratorio")
                .select("parametro_id, validado")
                .eq("muestra_id", muestra_id)
                .in_("parametro_id", param_ids)
                .eq("validado", True)
                .execute()
            )
            ids_validados = {r["parametro_id"] for r in (res_val.data or [])}
        except Exception:
            # Pre-migración 006: no existe columna validado
            ids_validados = set()
    else:
        ids_validados = set()

    payload = []
    for f in filas:
        if f["parametro_id"] in ids_validados:
            bloqueados.append(f["parametro_id"])
            continue
        row = {
            "muestra_id":     muestra_id,
            "parametro_id":   f["parametro_id"],
            "valor_numerico": f.get("valor_numerico"),
            "valor_texto":    f.get("valor_texto"),
            "observaciones":  f.get("observaciones") or None,
            "analista_id":    analista_id,
            "fecha_analisis": hoy,
        }
        if f.get("cualificador"):
            row["cualificador"] = f["cualificador"]
        payload.append(row)

    for i in range(0, len(payload), LOTE):
        lote = payload[i : i + LOTE]
        try:
            db.table("resultados_laboratorio").upsert(
                lote, on_conflict="muestra_id,parametro_id"
            ).execute()
            ok += len(lote)
        except Exception:
            # Reintenta sin cualificador (pre-migración 006)
            for fila in lote:
                fila_compat = {k: v for k, v in fila.items() if k != "cualificador"}
                try:
                    db.table("resultados_laboratorio").upsert(
                        fila_compat, on_conflict="muestra_id,parametro_id"
                    ).execute()
                    ok += 1
                except Exception as exc:
                    errores.append(f"{fila['parametro_id']}: {exc}")
    _invalidar_cache()
    return ok, errores, bloqueados


def validar_resultados(
    muestra_id: str,
    parametro_ids: list[str],
    validador_id: Optional[str] = None,
) -> int:
    """
    Marca resultados como validados (firmados por supervisor).
    Una vez validados quedan bloqueados contra ediciones por upsert.
    Retorna el número de resultados validados.
    """
    db = get_db()
    payload = {
        "validado":     True,
        "validado_por": validador_id,
        "validado_at":  datetime.utcnow().isoformat(),
    }
    res = (
        db.table("resultados_laboratorio")
        .update(payload)
        .eq("muestra_id", muestra_id)
        .in_("parametro_id", parametro_ids)
        .execute()
    )
    n = len(res.data or [])
    if n > 0:
        registrar_cambio(
            tabla="resultados_laboratorio",
            registro_id=muestra_id,
            accion="validar",
            valor_nuevo=f"{n} resultado(s) validado(s)",
            usuario_id=validador_id,
        )
    _invalidar_cache()
    return n


def desvalidar_resultados(
    muestra_id: str,
    parametro_ids: list[str],
    usuario_id: Optional[str] = None,
) -> int:
    """
    Quita la marca de validado para permitir corregir un resultado.
    Solo administradores deben llamar a esta función (la UI debe enforzarlo).
    """
    db = get_db()
    payload = {
        "validado":     False,
        "validado_por": None,
        "validado_at":  None,
    }
    res = (
        db.table("resultados_laboratorio")
        .update(payload)
        .eq("muestra_id", muestra_id)
        .in_("parametro_id", parametro_ids)
        .execute()
    )
    n = len(res.data or [])
    if n > 0:
        registrar_cambio(
            tabla="resultados_laboratorio",
            registro_id=muestra_id,
            accion="desvalidar",
            valor_nuevo=f"{n} resultado(s) desvalidado(s)",
            usuario_id=usuario_id,
        )
    _invalidar_cache()
    return n


# ─────────────────────────────────────────────────────────────────────────────
# API pública: eliminación de resultados
# ─────────────────────────────────────────────────────────────────────────────

def eliminar_resultado(resultado_id: str) -> None:
    """Elimina un resultado individual de laboratorio por su ID."""
    db = get_db()
    db.table("resultados_laboratorio").delete().eq("id", resultado_id).execute()
    _invalidar_cache()


def eliminar_resultados_muestra(muestra_id: str, usuario_id: Optional[str] = None) -> int:
    """
    Elimina todos los resultados de laboratorio de una muestra.
    Retorna la cantidad eliminada.
    """
    db = get_db()
    res = (
        db.table("resultados_laboratorio")
        .select("id", count="exact")
        .eq("muestra_id", muestra_id)
        .execute()
    )
    count = res.count or 0
    if count > 0:
        db.table("resultados_laboratorio").delete().eq("muestra_id", muestra_id).execute()
        registrar_cambio(
            tabla="resultados_laboratorio",
            registro_id=muestra_id,
            accion="eliminar",
            valor_anterior=f"{count} resultado(s)",
            usuario_id=usuario_id,
        )
        _invalidar_cache()
    return count


# ─────────────────────────────────────────────────────────────────────────────
# API pública: excedencias activas (para el dashboard)
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_excedencias_activas(dias: int = 30) -> list[dict]:
    """
    Retorna resultados recientes que superan el límite ECA del punto de muestreo.

    Cada elemento del resultado:
        fecha, muestra_codigo, punto_nombre, eca_codigo,
        parametro_codigo, parametro_nombre, valor, lim_max, lim_min, unidad
    """
    db = get_db()
    fecha_corte = (datetime.utcnow() - timedelta(days=dias)).isoformat()

    # 1. Resultados recientes con valor numérico y cadena de joins
    res = (
        db.table("resultados_laboratorio")
        .select(
            "id, valor_numerico, fecha_analisis, "
            "parametros(id, codigo, nombre, unidades_medida(simbolo)), "
            "muestras(id, codigo, campana_id, "
            "  puntos_muestreo(id, nombre, eca_id, ecas(codigo)))"
        )
        .gte("fecha_analisis", fecha_corte[:10])
        .not_.is_("valor_numerico", "null")
        .limit(2000)
        .execute()
    )
    resultados = res.data or []

    if not resultados:
        return []

    # 2. Recolectar eca_ids y parametro_ids únicos
    eca_ids: set[str] = set()
    param_ids: set[str] = set()
    for r in resultados:
        m = r.get("muestras") or {}
        p = m.get("puntos_muestreo") or {}
        if p.get("eca_id"):
            eca_ids.add(p["eca_id"])
        prm = r.get("parametros") or {}
        if prm.get("id"):
            param_ids.add(prm["id"])

    if not eca_ids:
        return []

    # 3. Límites para esos ECAs y parámetros
    lim_res = (
        db.table("eca_valores")
        .select("eca_id, parametro_id, valor_minimo, valor_maximo")
        .in_("eca_id", list(eca_ids))
        .in_("parametro_id", list(param_ids))
        .execute()
    )
    limites: dict[tuple, dict] = {
        (l["eca_id"], l["parametro_id"]): l
        for l in (lim_res.data or [])
    }

    # 4. Filtrar excedencias
    excedencias: list[dict] = []
    for r in resultados:
        m = r.get("muestras") or {}
        pt = m.get("puntos_muestreo") or {}
        prm = r.get("parametros") or {}
        eca_id = pt.get("eca_id")
        param_id = prm.get("id")
        lim = limites.get((eca_id, param_id))
        if not lim:
            continue

        valor = r["valor_numerico"]
        excede = (
            (lim.get("valor_maximo") is not None and valor > lim["valor_maximo"])
            or
            (lim.get("valor_minimo") is not None and valor < lim["valor_minimo"])
        )
        if excede:
            excedencias.append({
                "fecha":             r.get("fecha_analisis", "")[:10],
                "muestra_codigo":    m.get("codigo", ""),
                "punto_id":          pt.get("id", ""),
                "punto_nombre":      pt.get("nombre", ""),
                "eca_codigo":        (pt.get("ecas") or {}).get("codigo", ""),
                "parametro_codigo":  prm.get("codigo", ""),
                "parametro_nombre":  prm.get("nombre", ""),
                "valor":             valor,
                "lim_max":           lim.get("valor_maximo"),
                "lim_min":           lim.get("valor_minimo"),
                "unidad":            (prm.get("unidades_medida") or {}).get("simbolo", ""),
            })

    return sorted(excedencias, key=lambda x: x["fecha"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# API pública: métricas y datos para el dashboard
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_metricas_dashboard(dias: int = 30, cuenca: str | None = None) -> dict:
    """
    Métricas de resumen para las tarjetas del dashboard.

    `cuenca` (opcional): si se indica, todas las métricas se acotan a los
    puntos de esa cuenca (vista "por cuenca", estilo Visor por Cuencas del
    ANA). Si es None, el comportamiento es global e idéntico al original.

    Retorna:
        muestras_mes       → int  (muestras tomadas en el periodo)
        parametros_mes     → int  (resultados individuales registrados)
        excedencias_activas→ int  (resultados que superan ECA)
        puntos_monitoreados→ int  (puntos distintos con muestras)
    """
    db = get_db()
    fecha_corte = (datetime.utcnow() - timedelta(days=dias)).date().isoformat()

    # IDs de los puntos de la cuenca seleccionada (None = sin filtro de cuenca).
    # Se compara por forma canónica para tolerar variantes de grafía en BD.
    punto_ids: list[str] | None = None
    if cuenca:
        from services.punto_service import normalizar_cuenca
        objetivo = normalizar_cuenca(cuenca)
        pr = (
            db.table("puntos_muestreo")
            .select("id, cuenca")
            .execute()
        )
        punto_ids = [
            r["id"] for r in (pr.data or [])
            if normalizar_cuenca(r.get("cuenca")) == objetivo
        ]
        if not punto_ids:
            # Cuenca sin puntos → métricas en cero, sin más consultas.
            return {
                "muestras_mes": 0, "parametros_mes": 0,
                "excedencias_activas": 0, "puntos_monitoreados": 0,
                "excedencias_lista": [],
            }

    # Muestras del periodo
    m_q = (
        db.table("muestras")
        .select("id", count="exact")
        .gte("fecha_muestreo", fecha_corte)
    )
    if punto_ids is not None:
        m_q = m_q.in_("punto_muestreo_id", punto_ids)
    muestras_mes = m_q.execute().count or 0

    # Resultados individuales del periodo
    if punto_ids is None:
        parametros_mes = (
            db.table("resultados_laboratorio")
            .select("id", count="exact")
            .gte("fecha_analisis", fecha_corte)
            .execute()
            .count or 0
        )
    else:
        # Acotar resultados a las muestras de la cuenca.
        mids = [
            r["id"] for r in (
                db.table("muestras")
                .select("id")
                .in_("punto_muestreo_id", punto_ids)
                .execute()
                .data or []
            )
        ]
        if mids:
            parametros_mes = (
                db.table("resultados_laboratorio")
                .select("id", count="exact")
                .gte("fecha_analisis", fecha_corte)
                .in_("muestra_id", mids)
                .execute()
                .count or 0
            )
        else:
            parametros_mes = 0

    # Puntos distintos con muestras en el periodo
    pm_q = (
        db.table("muestras")
        .select("punto_muestreo_id")
        .gte("fecha_muestreo", fecha_corte)
    )
    if punto_ids is not None:
        pm_q = pm_q.in_("punto_muestreo_id", punto_ids)
    puntos_ids = {r["punto_muestreo_id"] for r in (pm_q.execute().data or [])}
    puntos_monitoreados = len(puntos_ids)

    # Excedencias (reutiliza la función existente; se filtran por punto_id)
    excedencias = get_excedencias_activas(dias)
    if punto_ids is not None:
        _ids = set(punto_ids)
        excedencias = [e for e in excedencias if e.get("punto_id") in _ids]

    return {
        "muestras_mes":        muestras_mes,
        "parametros_mes":      parametros_mes,
        "excedencias_activas": len(excedencias),
        "puntos_monitoreados": puntos_monitoreados,
        "excedencias_lista":   excedencias,
    }


@cached(ttl=300)
def get_puntos_con_estado(dias: int = 30) -> list[dict]:
    """
    Retorna los 12 puntos de muestreo con lat/lon y estado de excedencia.

    Cada punto incluye:
        id, codigo, nombre, latitud, longitud, altitud_msnm, tipo,
        estado → 'excedencia' | 'cumple' | 'sin_datos'
        n_excedencias → int
    """
    db = get_db()

    # Todos los puntos activos con coordenadas
    pts = (
        db.table("puntos_muestreo")
        .select("id, codigo, nombre, latitud, longitud, altitud_msnm, tipo, cuenca")
        .eq("activo", True)
        .order("codigo")
        .execute()
    )
    puntos = pts.data or []

    # Unificar la grafía de cuenca a la forma canónica (BD con variantes).
    from services.punto_service import normalizar_cuenca
    for _p in puntos:
        if _p.get("cuenca"):
            _p["cuenca"] = normalizar_cuenca(_p["cuenca"])

    # Puntos que tienen excedencias activas (por ID, no por nombre)
    excedencias = get_excedencias_activas(dias)
    puntos_con_exc: dict[str, int] = {}
    for e in excedencias:
        pid = e.get("punto_id", "")
        if pid:
            puntos_con_exc[pid] = puntos_con_exc.get(pid, 0) + 1

    # Puntos que tienen muestras recientes (sin excedencia = cumple)
    fecha_corte = (datetime.utcnow() - timedelta(days=dias)).date().isoformat()
    m_res = (
        db.table("muestras")
        .select("punto_muestreo_id")
        .gte("fecha_muestreo", fecha_corte)
        .execute()
    )
    puntos_con_datos = {r["punto_muestreo_id"] for r in (m_res.data or [])}

    # Asignar estado a cada punto
    for p in puntos:
        n_exc = puntos_con_exc.get(p["id"], 0)
        if n_exc > 0:
            p["estado"] = "excedencia"
            p["n_excedencias"] = n_exc
        elif p["id"] in puntos_con_datos:
            p["estado"] = "cumple"
            p["n_excedencias"] = 0
        else:
            p["estado"] = "sin_datos"
            p["n_excedencias"] = 0

    return puntos


# ─────────────────────────────────────────────────────────────────────────────
# Helper interno
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=600, grupo="referencia")
def _get_usuario_interno_id(auth_id: str) -> Optional[str]:
    """Resuelve el UUID interno de 'usuarios' a partir del auth_id de Supabase.

    Cacheado (grupo referencia): el mapeo auth_id→UUID interno es estable durante
    la sesión, así no se pega a Supabase en cada rerun del fragment de captura
    (cada tecleo). Se invalida solo con cambios de datos de referencia.
    """
    try:
        res = (
            get_db()
            .table("usuarios")
            .select("id")
            .eq("auth_id", auth_id)
            .maybe_single()
            .execute()
        )
        return res.data["id"] if res.data else None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Evaluación ECA por resultado — pega el motor con los datos cargados en
# get_datos_muestra(). Devuelve un VeredictoECA listo para renderizar en la UI.
# ─────────────────────────────────────────────────────────────────────────────

def _buscar_medicion_insitu(mediciones: dict[str, float], *claves) -> Optional[float]:
    """
    Retorna el primer valor de mediciones cuyo nombre coincide (case-insensitive)
    con alguna de las claves provistas. Tolera variantes ('pH', 'ph', 'temperatura',
    'temperatura del agua', 'temp', etc.).
    """
    if not mediciones:
        return None
    for clave in claves:
        c = clave.lower().strip()
        if c in mediciones:
            return mediciones[c]
        for k, v in mediciones.items():
            if k.startswith(c) or c in k:
                return v
    return None


def evaluar_resultado_ctx(datos: dict, parametro_id: str,
                          valor_lab: Optional[float] = None,
                          cualificador: Optional[str] = None):
    """
    Construye el ContextoEvaluacion con los datos de get_datos_muestra() y ejecuta
    el motor de cumplimiento. Permite pasar valor_lab/cualificador en memoria
    (sin leer de BD) para refrescar el veredicto en tiempo real mientras el
    usuario edita un input en la página.

    Retorna el VeredictoECA (ver services/cumplimiento_service.py).
    """
    from services.cumplimiento_service import evaluar, ContextoEvaluacion

    param = next(
        (p for p in datos.get("parametros", []) if p.get("id") == parametro_id),
        None,
    )
    if not param:
        return None

    limite = datos.get("limites", {}).get(parametro_id, {}) or {}
    resultado = datos.get("resultados", {}).get(parametro_id, {}) or {}
    mediciones = datos.get("mediciones", {}) or {}
    excepciones = datos.get("excepciones", {}) or {}

    # Valor y cualificador: privilegiar lo que venga del input en vivo,
    # si no hay, caer a lo guardado.
    v = valor_lab if valor_lab is not None else resultado.get("valor_numerico")
    q = cualificador if cualificador is not None else resultado.get("cualificador")

    unidad = (param.get("unidades_medida") or {}).get("simbolo", "")

    muestra = datos.get("muestra") or {}
    ctx = ContextoEvaluacion(
        valor_lab=v,
        cualificador=q,
        parametro_codigo=param.get("codigo", ""),
        parametro_nombre=param.get("nombre", ""),
        parametro_es_eca=bool(param.get("es_eca", True)),
        parametro_unidad_simbolo=unidad,
        parametro_lmd=param.get("lmd"),
        parametro_lcm=param.get("lcm"),
        parametro_forma_analitica=param.get("forma_analitica") or "no_aplica",
        eca_codigo=datos.get("eca_codigo"),
        eca_valor_minimo=limite.get("valor_minimo"),
        eca_valor_maximo=limite.get("valor_maximo"),
        eca_expresado_como=limite.get("expresado_como"),
        eca_forma_analitica=limite.get("forma_analitica") or "no_aplica",
        ph=_buscar_medicion_insitu(mediciones, "ph"),
        temperatura_celsius=_buscar_medicion_insitu(
            mediciones, "temperatura", "temp", "temperatura_agua", "temperatura del agua"
        ),
        # Contexto temporal/espacial — requerido para evaluación Δ3 de Temperatura
        fecha_muestreo=muestra.get("fecha_muestreo"),
        punto_id=datos.get("punto_id"),
        dentro_zona_mezcla=bool(datos.get("dentro_zona_mezcla")),
        tiene_excepcion_art6=bool(excepciones.get(parametro_id)),
    )
    return evaluar(ctx)
