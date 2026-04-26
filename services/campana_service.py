"""
services/campana_service.py
Lógica de negocio para gestión de campañas de monitoreo.

Funciones públicas:
    get_campanas(filtro_estado, fecha_desde, fecha_hasta)
    crear_campana(datos)           → genera código automático CAMP-YYYY-NNN
    actualizar_estado(id, estado)  → transición validada del estado
    get_detalle_campana(id)        → puntos, muestras, % avance de análisis
    get_todos_los_puntos()         → para el multiselect del formulario
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

from database.client import get_admin_client
from services.audit_service import registrar_cambio


def _invalidar_cache() -> None:
    """Limpia cachés tras modificar campañas."""
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

ESTADOS = [
    "planificada",
    "en_campo",
    "en_laboratorio",
    "completada",
    "anulada",
    "archivada",
]

TRANSICIONES_VALIDAS: dict[str, str] = {
    "planificada":      "en_campo",
    "en_campo":         "en_laboratorio",
    "en_laboratorio":   "completada",
}

ETIQUETA_ESTADO: dict[str, str] = {
    "planificada":      "📋 Planificada",
    "en_campo":         "🏕️ En campo",
    "en_laboratorio":   "🔬 En laboratorio",
    "completada":       "✅ Completada",
    "anulada":          "❌ Anulada",
    "archivada":        "📦 Archivada",
}

FRECUENCIAS = [
    "mensual",
    "bimestral",
    "trimestral",
    "semestral",
    "anual",
    "extraordinaria",
]


# ─────────────────────────────────────────────────────────────────────────────
# Listado
# ─────────────────────────────────────────────────────────────────────────────

def get_campanas(
    filtro_estado: Optional[str] = None,
    fecha_desde:   Optional[str] = None,
    fecha_hasta:   Optional[str] = None,
    incluir_archivadas: bool = False,
) -> list[dict]:
    """
    Retorna campañas con filtros opcionales.
    filtro_estado: uno de ESTADOS o None para todos.
    fecha_desde/hasta: ISO date strings (YYYY-MM-DD).
    incluir_archivadas: por defecto False — campañas archivadas quedan ocultas
                       hasta que se pidan explícitamente.
    """
    db = get_admin_client()
    query = (
        db.table("campanas")
        .select(
            "id, codigo, nombre, fecha_inicio, fecha_fin, estado, "
            "frecuencia, responsable_campo, responsable_laboratorio, observaciones"
        )
        .order("fecha_inicio", desc=True)
    )

    if filtro_estado and filtro_estado in ESTADOS:
        query = query.eq("estado", filtro_estado)
    elif not incluir_archivadas:
        query = query.neq("estado", "archivada")
    if fecha_desde:
        query = query.gte("fecha_inicio", fecha_desde)
    if fecha_hasta:
        query = query.lte("fecha_inicio", fecha_hasta)

    return query.execute().data or []


# ─────────────────────────────────────────────────────────────────────────────
# Creación
# ─────────────────────────────────────────────────────────────────────────────

def get_todos_los_puntos() -> list[dict]:
    """Puntos activos para el multiselect del formulario de nueva campaña."""
    db = get_admin_client()
    res = (
        db.table("puntos_muestreo")
        .select("id, codigo, nombre, tipo, cuenca")
        .eq("activo", True)
        .order("codigo")
        .execute()
    )
    return res.data or []


def crear_campana(datos: dict, usuario_id: Optional[str] = None) -> dict:
    """
    Inserta una campaña nueva con código autogenerado y la vincula
    a los puntos de muestreo seleccionados.

    datos esperados:
        nombre, fecha_inicio (str ISO), fecha_fin (str ISO),
        frecuencia, responsable_campo, responsable_laboratorio,
        observaciones, puntos_ids (list[str])

    Retorna el dict de la campaña creada.
    """
    db = get_admin_client()
    codigo = _generar_codigo(db)

    campana = {
        "codigo":                    codigo,
        "nombre":                    datos["nombre"],
        "fecha_inicio":              datos["fecha_inicio"],
        "fecha_fin":                 datos["fecha_fin"],
        "frecuencia":                datos.get("frecuencia", "mensual"),
        "estado":                    "planificada",
        "responsable_campo":         datos.get("responsable_campo") or None,
        "responsable_laboratorio":   datos.get("responsable_laboratorio") or None,
        "observaciones":             datos.get("observaciones") or None,
    }

    res = db.table("campanas").insert(campana).execute()
    campana_creada = res.data[0]

    # Vincular puntos de muestreo
    puntos_ids = datos.get("puntos_ids", [])
    if puntos_ids:
        links = [
            {"campana_id": campana_creada["id"], "punto_muestreo_id": pid}
            for pid in puntos_ids
        ]
        db.table("campana_puntos").insert(links).execute()

    registrar_cambio(
        tabla="campanas",
        registro_id=campana_creada["id"],
        accion="crear",
        valor_nuevo=f"{codigo} — {datos['nombre']} ({len(puntos_ids)} pto)",
        usuario_id=usuario_id,
    )
    _invalidar_cache()
    return campana_creada


# ─────────────────────────────────────────────────────────────────────────────
# Cambio de estado
# ─────────────────────────────────────────────────────────────────────────────

class TransicionInvalidaError(Exception):
    """El cambio de estado solicitado no es válido."""


def actualizar_estado(campana_id: str, nuevo_estado: str, usuario_id: Optional[str] = None) -> None:
    """
    Actualiza el estado de una campaña con validación de transición.

    Transiciones permitidas (lineales):
        planificada → en_campo → en_laboratorio → completada

    Desde cualquier estado (excepto completada) se puede ir a 'anulada'.
    """
    db = get_admin_client()

    # Obtener estado actual
    res = (
        db.table("campanas")
        .select("estado")
        .eq("id", campana_id)
        .single()
        .execute()
    )
    estado_actual = res.data["estado"]

    # Validar transición
    if nuevo_estado == "anulada":
        if estado_actual == "completada":
            raise TransicionInvalidaError(
                "No se puede anular una campaña ya completada."
            )
    elif TRANSICIONES_VALIDAS.get(estado_actual) != nuevo_estado:
        raise TransicionInvalidaError(
            f"No se puede pasar de '{estado_actual}' a '{nuevo_estado}'. "
            f"La siguiente etapa válida es: "
            f"'{TRANSICIONES_VALIDAS.get(estado_actual, '(ninguna)')}'."
        )

    db.table("campanas").update(
        {"estado": nuevo_estado}
    ).eq("id", campana_id).execute()
    registrar_cambio(
        tabla="campanas",
        registro_id=campana_id,
        accion="cambio_estado",
        campo="estado",
        valor_anterior=estado_actual,
        valor_nuevo=nuevo_estado,
        usuario_id=usuario_id,
    )
    _invalidar_cache()


# ─────────────────────────────────────────────────────────────────────────────
# Detalle de campaña
# ─────────────────────────────────────────────────────────────────────────────

def get_detalle_campana(campana_id: str) -> dict:
    """
    Retorna toda la información de una campaña para la vista de detalle:
        campana  → datos de la campaña
        puntos   → puntos vinculados
        muestras → muestras con conteo de resultados y % de avance
        avance   → resumen global de progreso
    """
    db = get_admin_client()

    # 1. Campaña
    campana = (
        db.table("campanas")
        .select("*")
        .eq("id", campana_id)
        .single()
        .execute()
        .data
    )

    # 2. Puntos vinculados (tabla campana_puntos)
    pts_res = (
        db.table("campana_puntos")
        .select("puntos_muestreo(id, codigo, nombre, tipo, cuenca)")
        .eq("campana_id", campana_id)
        .execute()
    )
    puntos = [
        r["puntos_muestreo"]
        for r in (pts_res.data or [])
        if r.get("puntos_muestreo")
    ]
    puntos.sort(key=lambda x: x.get("codigo", ""))

    # 3. Muestras de esta campaña
    m_res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, estado, punto_muestreo_id, "
            "puntos_muestreo(codigo, nombre)"
        )
        .eq("campana_id", campana_id)
        .order("fecha_muestreo")
        .execute()
    )
    muestras = m_res.data or []

    # 4. Conteo de resultados por muestra (una sola query)
    muestra_ids = [m["id"] for m in muestras]
    resultados_por_muestra: dict[str, int] = {}

    if muestra_ids:
        r_res = (
            db.table("resultados_laboratorio")
            .select("muestra_id")
            .in_("muestra_id", muestra_ids)
            .execute()
        )
        resultados_por_muestra = dict(
            Counter(r["muestra_id"] for r in (r_res.data or []))
        )

    # 5. Total de parámetros activos (para calcular %)
    total_params = (
        db.table("parametros")
        .select("id", count="exact")
        .eq("activo", True)
        .execute()
        .count or 0
    )

    # 6. Enriquecer cada muestra con avance
    for m in muestras:
        n_res = resultados_por_muestra.get(m["id"], 0)
        m["n_resultados"]     = n_res
        m["total_parametros"] = total_params
        m["avance_pct"]       = round(n_res / total_params * 100, 1) if total_params else 0.0

    # 7. Resumen global
    total_esperado   = len(muestras) * total_params
    total_registrado = sum(resultados_por_muestra.values())

    avance = {
        "total_muestras":              len(muestras),
        "muestras_con_resultados":     sum(1 for c in resultados_por_muestra.values() if c > 0),
        "total_resultados_esperados":  total_esperado,
        "total_resultados_registrados": total_registrado,
        "porcentaje": round(total_registrado / total_esperado * 100, 1) if total_esperado else 0.0,
    }

    return {
        "campana":  campana,
        "puntos":   puntos,
        "muestras": muestras,
        "avance":   avance,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def actualizar_campana(campana_id: str, datos: dict) -> dict:
    """
    Actualiza campos editables de una campaña existente.

    datos puede incluir:
        nombre, fecha_inicio, fecha_fin, frecuencia,
        responsable_campo, responsable_laboratorio, observaciones
    """
    db = get_admin_client()
    campos = {}
    for key in (
        "nombre", "fecha_inicio", "fecha_fin", "frecuencia",
        "responsable_campo", "responsable_laboratorio", "observaciones",
    ):
        if key in datos:
            val = datos[key]
            campos[key] = val.strip() if isinstance(val, str) and val else val or None

    if not campos:
        raise ValueError("No se proporcionaron campos para actualizar.")

    res = (
        db.table("campanas")
        .update(campos)
        .eq("id", campana_id)
        .execute()
    )
    _invalidar_cache()
    return res.data[0] if res.data else {}


def actualizar_puntos_campana(campana_id: str, puntos_ids: list[str]) -> None:
    """
    Reemplaza los puntos vinculados a una campaña.
    Elimina los existentes y crea los nuevos vínculos.
    """
    db = get_admin_client()
    # Eliminar vínculos actuales
    db.table("campana_puntos").delete().eq("campana_id", campana_id).execute()
    # Crear nuevos
    if puntos_ids:
        links = [
            {"campana_id": campana_id, "punto_muestreo_id": pid}
            for pid in puntos_ids
        ]
        db.table("campana_puntos").insert(links).execute()
    _invalidar_cache()


# ─────────────────────────────────────────────────────────────────────────────
# Parámetros de laboratorio por campaña
# Se persisten en cadena_custodia_config (ya existente) para que la Cadena de
# Custodia y la Ficha de Campo consuman la misma fuente de verdad: lo decidido
# al planificar la campaña.
# ─────────────────────────────────────────────────────────────────────────────

def get_parametros_lab_campana(campana_id: str) -> dict:
    """
    Retorna los parámetros de laboratorio seleccionados para la campaña:
        {"parametros_lab": [claves...], "parametros_lab_extra": [nombres...]}

    Si la campaña no tiene selección guardada, retorna dict con listas vacías
    (el consumidor debe interpretar eso como "todos seleccionados por defecto").
    """
    try:
        db = get_admin_client()
        res = (
            db.table("cadena_custodia_config")
            .select("config")
            .eq("campana_id", campana_id)
            .maybe_single()
            .execute()
        )
        cfg = (res.data or {}).get("config") if res else None
        if cfg:
            return {
                "parametros_lab":       cfg.get("parametros_lab", []) or [],
                "parametros_lab_extra": cfg.get("parametros_lab_extra", []) or [],
            }
    except Exception:
        pass
    return {"parametros_lab": [], "parametros_lab_extra": []}


def set_parametros_lab_campana(
    campana_id: str,
    parametros_lab: list[str],
    parametros_lab_extra: list[str] | None = None,
    usuario_id: Optional[str] = None,
) -> bool:
    """
    Persiste la selección de parámetros de laboratorio para una campaña.
    Actualiza la fila existente en cadena_custodia_config o la crea.

    parametros_lab: lista de claves (lowercase codigo, ej. ["p019","p025"]).
    parametros_lab_extra: lista de nombres libres.
    """
    try:
        db = get_admin_client()
        # Leer config actual para mezclar con el resto de campos
        existente = (
            db.table("cadena_custodia_config")
            .select("config")
            .eq("campana_id", campana_id)
            .maybe_single()
            .execute()
        )
        cfg = (existente.data or {}).get("config") if existente else None
        if not cfg:
            # Base mínima — la CC la completa al generar el documento
            cfg = {}
        cfg["parametros_lab"] = list(parametros_lab or [])
        cfg["parametros_lab_extra"] = list(parametros_lab_extra or [])

        payload = {
            "campana_id":      campana_id,
            "config":          cfg,
            "actualizado_por": usuario_id,
            "updated_at":      datetime.utcnow().isoformat(),
        }
        db.table("cadena_custodia_config").upsert(
            payload, on_conflict="campana_id"
        ).execute()
        return True
    except Exception:
        return False


def archivar_campana(campana_id: str, motivo: str = "", usuario_id: Optional[str] = None) -> None:
    """
    Soft-delete: marca la campaña como 'archivada' sin borrar datos.

    La campaña queda oculta en listados regulares pero todos sus datos
    (muestras, resultados, mediciones, audit) se preservan íntegros.
    Recuperable con restaurar_campana().
    """
    db = get_admin_client()
    payload: dict = {
        "estado": "archivada",
        "archivada_at": datetime.utcnow().isoformat(),
    }
    if usuario_id:
        payload["archivada_por"] = usuario_id
    if motivo:
        payload["motivo_archivado"] = motivo

    try:
        db.table("campanas").update(payload).eq("id", campana_id).execute()
    except Exception:
        # Fallback pre-migración 006: solo cambiar estado
        db.table("campanas").update({"estado": "archivada"}).eq("id", campana_id).execute()
    registrar_cambio(
        tabla="campanas",
        registro_id=campana_id,
        accion="archivar",
        valor_nuevo=motivo or "(sin motivo)",
        usuario_id=usuario_id,
    )
    _invalidar_cache()


def restaurar_campana(campana_id: str, nuevo_estado: str = "completada", usuario_id: Optional[str] = None) -> None:
    """Saca una campaña del archivo y la devuelve a un estado operativo."""
    if nuevo_estado == "archivada":
        raise ValueError("Para restaurar elige un estado distinto a 'archivada'.")
    db = get_admin_client()
    payload = {
        "estado": nuevo_estado,
        "archivada_at": None,
        "archivada_por": None,
        "motivo_archivado": None,
    }
    try:
        db.table("campanas").update(payload).eq("id", campana_id).execute()
    except Exception:
        db.table("campanas").update({"estado": nuevo_estado}).eq("id", campana_id).execute()
    registrar_cambio(
        tabla="campanas",
        registro_id=campana_id,
        accion="restaurar",
        valor_nuevo=nuevo_estado,
        usuario_id=usuario_id,
    )
    _invalidar_cache()


def eliminar_campana(campana_id: str, forzar: bool = False, usuario_id: Optional[str] = None) -> dict:
    """
    BORRADO FÍSICO de una campaña y sus registros relacionados.

    ⚠️  DESTRUCTIVO. En operación normal usa archivar_campana() (soft-delete).
        Esta función queda solo para limpieza administrativa de campañas
        de prueba o errores groseros antes de que se generen datos reales.

    Si forzar=False: solo permite planificada/anulada sin muestras.
    Si forzar=True:  elimina en cascada (resultados → mediciones → muestras → puntos → campaña).

    Retorna dict con conteo de registros eliminados.
    """
    db = get_admin_client()

    # Obtener estado
    res = (
        db.table("campanas")
        .select("estado")
        .eq("id", campana_id)
        .single()
        .execute()
    )
    estado = res.data["estado"]

    # Obtener muestras de esta campaña
    m_res = (
        db.table("muestras")
        .select("id")
        .eq("campana_id", campana_id)
        .execute()
    )
    muestra_ids = [m["id"] for m in (m_res.data or [])]
    n_muestras = len(muestra_ids)

    if not forzar:
        if estado not in ("planificada", "anulada"):
            raise ValueError(
                f"Solo se pueden eliminar campañas planificadas o anuladas. "
                f"Estado actual: '{estado}'. Usa eliminación forzada."
            )
        if n_muestras > 0:
            raise ValueError(
                f"La campaña tiene {n_muestras} muestra(s). Usa eliminación forzada."
            )

    # Eliminar en cascada
    n_resultados = 0
    n_mediciones = 0

    if muestra_ids:
        # 1. Eliminar resultados de laboratorio de todas las muestras
        r_count = (
            db.table("resultados_laboratorio")
            .select("id", count="exact")
            .in_("muestra_id", muestra_ids)
            .execute()
        )
        n_resultados = r_count.count or 0
        if n_resultados > 0:
            db.table("resultados_laboratorio").delete().in_("muestra_id", muestra_ids).execute()

        # 2. Eliminar mediciones in situ
        mi_count = (
            db.table("mediciones_insitu")
            .select("id", count="exact")
            .in_("muestra_id", muestra_ids)
            .execute()
        )
        n_mediciones = mi_count.count or 0
        if n_mediciones > 0:
            db.table("mediciones_insitu").delete().in_("muestra_id", muestra_ids).execute()

        # 3. Eliminar muestras
        db.table("muestras").delete().eq("campana_id", campana_id).execute()

    # 4. Eliminar vínculos con puntos
    db.table("campana_puntos").delete().eq("campana_id", campana_id).execute()

    # 5. Eliminar campaña
    db.table("campanas").delete().eq("id", campana_id).execute()

    registrar_cambio(
        tabla="campanas",
        registro_id=campana_id,
        accion="eliminar",
        valor_anterior=f"{n_muestras} muestras, {n_resultados} resultados, {n_mediciones} mediciones",
        usuario_id=usuario_id,
    )
    _invalidar_cache()

    return {
        "muestras": n_muestras,
        "resultados": n_resultados,
        "mediciones": n_mediciones,
    }


def peek_siguiente_codigo() -> str:
    """
    Vista previa del próximo código sin reservarlo (no atómico, solo informativo).
    Útil para mostrar "se creará como CAMP-YYYY-NNN" antes de enviar el form.
    """
    year = datetime.utcnow().year
    prefijo = f"CAMP-{year}-"
    try:
        db = get_admin_client()
        res = (
            db.table("campanas")
            .select("codigo")
            .like("codigo", f"{prefijo}%")
            .execute()
        )
        max_seq = 0
        for row in (res.data or []):
            try:
                seq = int(row["codigo"].replace(prefijo, ""))
                max_seq = max(max_seq, seq)
            except (ValueError, KeyError):
                pass
        return f"{prefijo}{max_seq + 1:03d}"
    except Exception:
        return f"{prefijo}???"


def _generar_codigo(db) -> str:
    """
    Genera el siguiente código secuencial: CAMP-YYYY-NNN.
    Usa la función PostgreSQL siguiente_codigo() (atómica, sin race conditions).
    Cae a SELECT MAX+1 solo si la migración 006 no se ha aplicado.
    """
    year = datetime.utcnow().year
    prefijo = f"CAMP-{year}-"

    try:
        res = db.rpc("siguiente_codigo", {
            "p_tabla": "campanas",
            "p_prefijo": "CAMP",
            "p_anio": year,
        }).execute()
        seq = int(res.data)
        return f"{prefijo}{seq:03d}"
    except Exception:
        # Fallback pre-migración 006 (sujeto a race condition)
        res = (
            db.table("campanas")
            .select("codigo")
            .like("codigo", f"{prefijo}%")
            .execute()
        )
        max_seq = 0
        for row in (res.data or []):
            try:
                seq = int(row["codigo"].replace(prefijo, ""))
                max_seq = max(max_seq, seq)
            except (ValueError, KeyError):
                pass
        return f"{prefijo}{max_seq + 1:03d}"
