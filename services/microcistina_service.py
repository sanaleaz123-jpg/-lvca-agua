"""
services/microcistina_service.py
Persistencia y orquestación del ensayo ELISA de Microcistina LR (P091).

Modelo: una CORRIDA es una placa ELISA (kit usado una sola vez) que puede
abarcar muestras de VARIAS campañas. Cada resultado de muestra
(``resultados_laboratorio``) queda vinculado a su corrida vía ``corrida_id``;
de ahí el reporte por campaña obtiene la curva y el control de calidad.

Funciones públicas:
    get_param_microcistina()                  → fila del parámetro P091
    get_muestras_microcistina(campana_id)     → muestras de la campaña + OD guardadas
    get_muestras_para_asignar()               → muestras de todas las campañas (mapeo import)
    get_corrida(campana_id)                    → placa ELISA ligada a la campaña (o None)
    tiene_resultados_microcistina(campana_id)  → bool (gate del reporte)
    estado_registro_microcistina(muestra_ids)  → {muestra_id: 'registrado'|'validado'}
    listar_corridas()                          → historial de placas + estadísticas
    get_muestras_de_corrida(corrida_id)        → muestras/resultados de una placa
    calcular_corrida(...)                       → cálculo en memoria (preview)
    guardar_corrida(campana_id, ...)           → guarda placa de una campaña (ingreso manual)
    guardar_corrida_importada(imp, asignaciones, ...) → guarda placa importada de Excel
    get_codigo_reporte(campana_id, ...)        → correlativo de reporte por campaña
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.client import get_db
from services.cache import cached
from services.elisa_microcistina import (
    STD_CONC_UGL,
    FACTOR_DILUCION_DEFAULT,
    CurvaParams,
    ResultadoMuestra,
    concentracion_ugL,
    fit_4pl,
    procesar_muestra,
    procesar_control,
)

CODIGO_MICROCISTINA = "P091"
CLAVE_MICROCISTINA = "p091"  # clave en la selección de parámetros de la campaña


def _invalidar_cache() -> None:
    try:
        from services.cache import invalidate_operational
        invalidate_operational()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Parámetro y muestras
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=600, grupo="referencia")
def get_param_microcistina() -> Optional[dict]:
    """Fila del parámetro P091: id, nombre, lmd, lcm, símbolo de unidad."""
    db = get_db()
    try:
        res = (
            db.table("parametros")
            .select("id, codigo, nombre, lmd, lcm, unidades_medida(simbolo)")
            .eq("codigo", CODIGO_MICROCISTINA)
            .single()
            .execute()
        )
    except Exception:
        return None
    return res.data or None


@cached(ttl=120)
def get_muestras_microcistina(campana_id: str) -> list[dict]:
    """
    Muestras de la campaña (una por punto/nivel) con su punto y, si existe, la
    lectura ELISA ya guardada (od_1/od_2, valor, %CV, cualificador).
    """
    db = get_db()
    param = get_param_microcistina()
    param_id = (param or {}).get("id")

    m_res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, hora_recoleccion, punto_muestreo_id, "
            "puntos_muestreo(id, codigo, nombre, descripcion, utm_este, utm_norte)"
        )
        .eq("campana_id", campana_id)
        .order("fecha_muestreo")
        .execute()
    )
    muestras = m_res.data or []
    muestra_ids = [m["id"] for m in muestras]

    por_muestra: dict[str, dict] = {}
    if muestra_ids and param_id:
        try:
            r_res = (
                db.table("resultados_laboratorio")
                .select("muestra_id, valor_numerico, cualificador, od_1, od_2, cv_pct, validado")
                .in_("muestra_id", muestra_ids)
                .eq("parametro_id", param_id)
                .execute()
            )
            por_muestra = {r["muestra_id"]: r for r in (r_res.data or [])}
        except Exception:
            por_muestra = {}

    salida = []
    for m in muestras:
        prev = por_muestra.get(m["id"], {})
        salida.append({
            "id": m["id"],
            "codigo": m.get("codigo"),
            "fecha_muestreo": m.get("fecha_muestreo"),
            "hora_recoleccion": m.get("hora_recoleccion"),
            "punto": m.get("puntos_muestreo") or {},
            "od_1": prev.get("od_1"),
            "od_2": prev.get("od_2"),
            "valor_numerico": prev.get("valor_numerico"),
            "cv_pct": prev.get("cv_pct"),
            "cualificador": prev.get("cualificador"),
            "validado": prev.get("validado", False),
        })
    salida.sort(key=lambda x: (x["punto"].get("codigo") or "", x.get("codigo") or ""))
    return salida


@cached(ttl=120)
def get_muestras_para_asignar() -> list[dict]:
    """
    Todas las muestras (de cualquier campaña) para el mapeo al importar una
    placa que abarca varias campañas. Cada elemento: {id, label}.
    """
    db = get_db()
    res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, "
            "campanas(codigo, nombre), puntos_muestreo(codigo, nombre)"
        )
        .order("fecha_muestreo", desc=True)
        .execute()
    )
    out = []
    for m in (res.data or []):
        camp = m.get("campanas") or {}
        p = m.get("puntos_muestreo") or {}
        fecha = (m.get("fecha_muestreo") or "")[:10]
        label = (
            f"{camp.get('codigo', '?')} · {p.get('codigo', '?')} · "
            f"{m.get('codigo', '')} ({fecha})"
        )
        out.append({"id": m["id"], "label": label})
    return out


_PROF_NOMBRES = {"S": "Superficie", "M": "Medio", "F": "Fondo"}


@cached(ttl=120)
def get_muestras_agrupadas_por_campana() -> dict:
    """
    Muestras de todas las campañas agrupadas para el mapeo en cascada del import.

    Devuelve: {campana_id: {"label": "<cod> — <nombre>",
                            "muestras": [{"id", "label": "<punto> — <nivel> (<fecha>)"}]}}
    Ordenado por campaña (fecha desc) y por código de punto.
    """
    db = get_db()
    res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, profundidad_tipo, campana_id, "
            "campanas(codigo, nombre, fecha_inicio), puntos_muestreo(codigo, nombre)"
        )
        .order("fecha_muestreo", desc=True)
        .execute()
    )
    grupos: dict = {}
    for m in (res.data or []):
        cid = m.get("campana_id")
        if not cid:
            continue
        camp = m.get("campanas") or {}
        p = m.get("puntos_muestreo") or {}
        if cid not in grupos:
            grupos[cid] = {
                "label": f"{camp.get('codigo', '?')} — {camp.get('nombre', '')}",
                "_orden": camp.get("fecha_inicio") or "",
                "muestras": [],
            }
        prof = m.get("profundidad_tipo")
        nivel = f" — {_PROF_NOMBRES.get(prof, prof)}" if prof else ""
        fecha = (m.get("fecha_muestreo") or "")[:10]
        etq = f"{p.get('codigo', '?')}{nivel} ({fecha})"
        grupos[cid]["muestras"].append({"id": m["id"], "label": etq})
    # Solo campañas que eligieron analizar microcistina (P091). La selección de
    # parámetros de laboratorio se hace en "Campañas"; una selección vacía
    # significa "todos los parámetros" (incluye microcistina).
    try:
        from services.campana_service import get_parametros_lab_campana
        filtrados: dict = {}
        for cid, info in grupos.items():
            sel = get_parametros_lab_campana(cid) or {}
            claves = sel.get("parametros_lab") or []
            if (not claves) or (CLAVE_MICROCISTINA in claves):
                filtrados[cid] = info
        grupos = filtrados
    except Exception:
        # Si no se puede determinar la selección, no filtrar (mejor mostrar todo).
        pass

    for info in grupos.values():
        info["muestras"].sort(key=lambda x: x["label"])
    # Reordenar campañas por fecha de inicio desc
    return dict(sorted(grupos.items(), key=lambda kv: kv[1]["_orden"], reverse=True))


@cached(ttl=120)
def get_corrida(campana_id: str) -> Optional[dict]:
    """Placa ELISA ligada a la campaña (vía resultados.corrida_id), o None."""
    db = get_db()
    param = get_param_microcistina()
    param_id = (param or {}).get("id")
    if not param_id:
        return None

    m_res = db.table("muestras").select("id").eq("campana_id", campana_id).execute()
    mids = [m["id"] for m in (m_res.data or [])]
    if not mids:
        return None

    try:
        rr = (
            db.table("resultados_laboratorio")
            .select("corrida_id")
            .in_("muestra_id", mids)
            .eq("parametro_id", param_id)
            .not_.is_("corrida_id", "null")
            .limit(1)
            .execute()
        )
    except Exception:
        return None
    rows = rr.data or []
    if not rows:
        return None
    corrida_id = rows[0]["corrida_id"]

    try:
        cr = (
            db.table("elisa_microcistina_corridas")
            .select("*").eq("id", corrida_id).limit(1).execute()
        )
    except Exception:
        return None
    data = cr.data or []
    return data[0] if data else None


def tiene_resultados_microcistina(campana_id: str) -> bool:
    """True si la campaña tiene una placa ELISA con curva ajustada."""
    corrida = get_corrida(campana_id)
    return bool(corrida and corrida.get("param_a") is not None)


def estado_registro_microcistina(muestra_ids: list[str]) -> dict[str, str]:
    """
    Para cada muestra_id dado, indica si YA tiene resultado de microcistina en la
    BD: ``"validado"`` (firmado) o ``"registrado"`` (guardado sin validar). Las
    muestras sin resultado simplemente no aparecen en el dict.

    Consulta fresca (sin caché) para reflejar el estado justo después de
    registrar. Úsalo para marcar con un check las muestras ya registradas en el
    panel ELISA.
    """
    ids = [m for m in (muestra_ids or []) if m]
    if not ids:
        return {}
    param_id = (get_param_microcistina() or {}).get("id")
    if not param_id:
        return {}
    db = get_db()
    try:
        res = (
            db.table("resultados_laboratorio")
            .select("muestra_id, validado")
            .in_("muestra_id", ids)
            .eq("parametro_id", param_id)
            .execute()
        )
    except Exception:
        return {}
    estado: dict[str, str] = {}
    for r in (res.data or []):
        mid = r.get("muestra_id")
        if mid:
            estado[mid] = "validado" if r.get("validado") else "registrado"
    return estado


# ─────────────────────────────────────────────────────────────────────────────
# Historial de corridas (placas) — listado, detalle y estadísticas para comparar
# ─────────────────────────────────────────────────────────────────────────────

def _f(x) -> Optional[float]:
    """float() tolerante: None/'' → None, valores no numéricos → None."""
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _corrida_es_valida(c: dict) -> bool:
    """
    ¿La corrida cumple los criterios CRÍTICos de aceptación? R² ≥ 0.98, control
    dentro de nominal ± tolerancia y %CV del control ≤ cv_max. Espejo de los
    criterios críticos del panel de validez (components/microcistina_form).
    """
    r2 = _f(c.get("r2"))
    ctrl = _f(c.get("control_conc_prom"))
    cv = _f(c.get("control_cv"))
    nom = _f(c.get("qcs_nominal")) or 0.750
    tol = _f(c.get("qcs_tolerancia")) or 0.185
    cvmax = _f(c.get("cv_max")) or 15.0
    if r2 is None or ctrl is None or cv is None:
        return False
    if r2 < 0.98:
        return False
    if not (nom - tol <= ctrl <= nom + tol):
        return False
    return cv <= cvmax


@cached(ttl=120)
def listar_corridas() -> list[dict]:
    """
    Lista TODAS las corridas ELISA (placas) con estadísticas agregadas, para el
    historial y la comparación. Cada dict tiene los campos persistidos de la
    corrida (curva, control, criterios QCS, lote, fecha, std_od…) más:
      - n_muestras : nº de muestras con resultado de microcistina en la corrida
      - n_validadas: nº de esas muestras ya validadas (firmadas)
      - campanas   : etiquetas de campaña que toca la placa (código, orden alfa)
      - es_valida  : bool (curva + control cumplen criterios de aceptación)
    Ordenada por fecha_ensayo desc, luego created_at desc.
    """
    db = get_db()
    try:
        corridas = (
            db.table("elisa_microcistina_corridas").select("*").execute().data
        ) or []
    except Exception:
        return []
    if not corridas:
        return []

    param_id = (get_param_microcistina() or {}).get("id")
    res_por_corrida: dict[str, list] = {}
    muestra_ids: set[str] = set()
    if param_id:
        try:
            rr = (
                db.table("resultados_laboratorio")
                .select("corrida_id, muestra_id, validado")
                .eq("parametro_id", param_id)
                .not_.is_("corrida_id", "null")
                .execute()
            )
            for r in (rr.data or []):
                cid = r.get("corrida_id")
                if cid:
                    res_por_corrida.setdefault(cid, []).append(r)
                    if r.get("muestra_id"):
                        muestra_ids.add(r["muestra_id"])
        except Exception:
            pass

    # muestra_id → etiqueta de campaña (código)
    camp_por_muestra: dict[str, str] = {}
    if muestra_ids:
        try:
            mr = (
                db.table("muestras")
                .select("id, campanas(codigo, nombre)")
                .in_("id", list(muestra_ids))
                .execute()
            )
            for m in (mr.data or []):
                camp = m.get("campanas") or {}
                camp_por_muestra[m["id"]] = camp.get("codigo") or camp.get("nombre") or "—"
        except Exception:
            pass

    salida: list[dict] = []
    for c in corridas:
        rows = res_por_corrida.get(c["id"], [])
        mids = {r["muestra_id"] for r in rows if r.get("muestra_id")}
        val = {r["muestra_id"] for r in rows if r.get("validado") and r.get("muestra_id")}
        camps = sorted({camp_por_muestra.get(mid, "—") for mid in mids})
        c = dict(c)
        c["n_muestras"] = len(mids)
        c["n_validadas"] = len(val)
        c["campanas"] = camps
        c["es_valida"] = _corrida_es_valida(c)
        salida.append(c)

    salida.sort(
        key=lambda x: (x.get("fecha_ensayo") or "", x.get("created_at") or ""),
        reverse=True,
    )
    return salida


@cached(ttl=120)
def get_muestras_de_corrida(corrida_id: str) -> list[dict]:
    """
    Muestras/resultados de UNA corrida (para el detalle del historial). Devuelve
    una fila por muestra con: campaña, punto, valor (µg/L), OD réplicas, %CV,
    cualificador y si está validada. Ordenada por campaña y punto.
    """
    if not corrida_id:
        return []
    param_id = (get_param_microcistina() or {}).get("id")
    if not param_id:
        return []
    db = get_db()
    try:
        rr = (
            db.table("resultados_laboratorio")
            .select(
                "muestra_id, valor_numerico, od_1, od_2, cv_pct, cualificador, "
                "validado, muestras(codigo, fecha_muestreo, profundidad_tipo, "
                "campanas(codigo, nombre), puntos_muestreo(codigo, nombre))"
            )
            .eq("parametro_id", param_id)
            .eq("corrida_id", corrida_id)
            .execute()
        )
    except Exception:
        return []
    out: list[dict] = []
    for r in (rr.data or []):
        m = r.get("muestras") or {}
        camp = m.get("campanas") or {}
        p = m.get("puntos_muestreo") or {}
        prof = m.get("profundidad_tipo")
        nivel = f" · {_PROF_NOMBRES.get(prof, prof)}" if prof else ""
        out.append({
            "muestra_id": r.get("muestra_id"),
            "campana": camp.get("codigo") or camp.get("nombre") or "—",
            "punto": p.get("codigo") or "—",
            "muestra": f"{p.get('codigo', '?')}{nivel}",
            "fecha": (m.get("fecha_muestreo") or "")[:10],
            "valor_ugL": _f(r.get("valor_numerico")),
            "od_1": _f(r.get("od_1")),
            "od_2": _f(r.get("od_2")),
            "cv_pct": _f(r.get("cv_pct")),
            "cualificador": r.get("cualificador"),
            "validado": bool(r.get("validado")),
        })
    out.sort(key=lambda x: (x["campana"], x["muestra"]))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo en memoria (preview)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CorridaCalculada:
    curva: CurvaParams
    control: ResultadoMuestra
    resultados: dict[str, ResultadoMuestra]   # muestra_id → resultado


def calcular_corrida(
    std_od: list[tuple[float, float]],
    control_od: tuple[float, float],
    muestras_od: dict[str, tuple[float, float]],
    factor: float = FACTOR_DILUCION_DEFAULT,
) -> CorridaCalculada:
    """Ajusta la curva 4PL y procesa control y muestras SIN tocar la BD."""
    if len(std_od) != len(STD_CONC_UGL):
        raise ValueError(
            f"Se requieren {len(STD_CONC_UGL)} estándares; se recibieron {len(std_od)}."
        )
    od_prom = [(a + b) / 2.0 for a, b in std_od]
    curva = fit_4pl(list(STD_CONC_UGL), od_prom)
    control = procesar_control(control_od[0], control_od[1], curva)
    resultados = {
        mid: procesar_muestra(o1, o2, curva, factor=factor)
        for mid, (o1, o2) in muestras_od.items()
    }
    return CorridaCalculada(curva=curva, control=control, resultados=resultados)


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia de la corrida (placa)
# ─────────────────────────────────────────────────────────────────────────────

def _corrida_row(
    *, curva: CurvaParams, control: ResultadoMuestra, control_od: tuple[float, float],
    std_od: list[tuple[float, float]], factor: float, kit_lote: Optional[str],
    fecha_ensayo: Optional[str], qcs_nominal: float, qcs_tolerancia: float,
    cv_max: float, observaciones: Optional[str], campana_id: Optional[str] = None,
) -> dict:
    return {
        "campana_id": campana_id,
        "fecha_ensayo": fecha_ensayo,
        "kit_lote": kit_lote,
        "factor_dilucion": factor,
        "std_od": [[a, b] for a, b in std_od],
        "param_a": curva.A, "param_b": curva.B, "param_c": curva.C, "param_d": curva.D,
        "r2": curva.r2, "sse": curva.sse,
        "control_od_1": control_od[0], "control_od_2": control_od[1],
        "control_conc_1": concentracion_ugL(control_od[0], curva),
        "control_conc_2": concentracion_ugL(control_od[1], curva),
        "control_conc_prom": control.conc_ugL,
        "control_cv": control.cv_pct,
        "qcs_nominal": qcs_nominal, "qcs_tolerancia": qcs_tolerancia, "cv_max": cv_max,
        "observaciones": observaciones,
        "updated_at": datetime.utcnow().isoformat(),
    }


def _persistir_corrida(db, row: dict, corrida_id: Optional[str]) -> Optional[str]:
    """Inserta o actualiza la corrida; devuelve su id (None si el insert no lo devuelve)."""
    if corrida_id:
        db.table("elisa_microcistina_corridas").update(row).eq("id", corrida_id).execute()
        return corrida_id
    ins = db.table("elisa_microcistina_corridas").insert(row).execute()
    data = ins.data or []
    return data[0]["id"] if data else None


def _upsert_resultado(db, *, muestra_id, param_id, corrida_id, res: ResultadoMuestra,
                      lcm, fecha, analista_id) -> None:
    cualificador = None
    observ = res.motivo or None
    if res.conc_ugL is not None and lcm is not None and res.conc_ugL < float(lcm):
        cualificador = "<LCM"
    fila = {
        "muestra_id": muestra_id,
        "parametro_id": param_id,
        "corrida_id": corrida_id,
        "valor_numerico": res.conc_ugL,
        "od_1": res.od_1, "od_2": res.od_2, "cv_pct": res.cv_pct,
        "cualificador": cualificador,
        "observaciones": observ,
        "analista_id": analista_id,
        "fecha_analisis": fecha,
    }
    db.table("resultados_laboratorio").upsert(
        fila, on_conflict="muestra_id,parametro_id"
    ).execute()


def guardar_corrida(
    campana_id: str, *, fecha_ensayo: Optional[str], kit_lote: Optional[str],
    factor: float, std_od: list[tuple[float, float]],
    control_od: tuple[float, float], muestras_od: dict[str, tuple[float, float]],
    qcs_nominal: float = 0.750, qcs_tolerancia: float = 0.185, cv_max: float = 15.0,
    observaciones: Optional[str] = None, analista_id: Optional[str] = None,
) -> CorridaCalculada:
    """
    Ingreso manual: guarda la placa de UNA campaña (todas sus muestras en la
    misma placa) y vuelca los resultados. Si la campaña ya tiene placa, la
    actualiza; si no, crea una.
    """
    db = get_db()
    param = get_param_microcistina()
    if not param:
        raise ValueError("No se encontró el parámetro Microcistina LR (P091) en la BD.")
    param_id = param["id"]
    lcm = param.get("lcm")

    calc = calcular_corrida(std_od, control_od, muestras_od, factor=factor)

    existente = get_corrida(campana_id) or {}
    row = _corrida_row(
        curva=calc.curva, control=calc.control, control_od=control_od, std_od=std_od,
        factor=factor, kit_lote=kit_lote, fecha_ensayo=fecha_ensayo,
        qcs_nominal=qcs_nominal, qcs_tolerancia=qcs_tolerancia, cv_max=cv_max,
        observaciones=observaciones, campana_id=campana_id,
    )
    corrida_id = _persistir_corrida(db, row, existente.get("id"))
    if not corrida_id:
        raise RuntimeError(
            "No se pudo guardar la corrida (la base de datos no devolvió su id). "
            "No se registraron resultados para evitar datos huérfanos."
        )

    fecha = fecha_ensayo or datetime.utcnow().date().isoformat()
    validados = _ids_validados(db, list(muestras_od.keys()), param_id)
    for mid, res in calc.resultados.items():
        if mid in validados:
            continue
        _upsert_resultado(db, muestra_id=mid, param_id=param_id, corrida_id=corrida_id,
                          res=res, lcm=lcm, fecha=fecha, analista_id=analista_id)

    _invalidar_cache()
    return calc


def guardar_corrida_importada(
    imp, asignaciones: dict[int, str], *,
    fecha_ensayo: Optional[str] = None, qcs_nominal: float = 0.750,
    qcs_tolerancia: float = 0.185, cv_max: float = 15.0,
    observaciones: Optional[str] = None, analista_id: Optional[str] = None,
) -> str:
    """
    Guarda una placa importada de Excel (services/microcistina_import). Crea una
    corrida nueva (sin campana_id, abarca varias campañas) y vuelca cada muestra
    asignada. ``asignaciones`` mapea índice de muestra importada → muestra_id.

    Devuelve el id de la corrida creada.
    """
    db = get_db()
    param = get_param_microcistina()
    if not param:
        raise ValueError("No se encontró el parámetro Microcistina LR (P091) en la BD.")
    param_id = param["id"]
    lcm = param.get("lcm")

    row = _corrida_row(
        curva=imp.curva, control=imp.control, control_od=imp.control_od,
        std_od=imp.std_od, factor=imp.factor, kit_lote=imp.kit_lote,
        fecha_ensayo=fecha_ensayo, qcs_nominal=qcs_nominal,
        qcs_tolerancia=qcs_tolerancia, cv_max=cv_max, observaciones=observaciones,
        campana_id=None,
    )
    # Usar las concentraciones del control tal como las calculó el Excel.
    if imp.control_conc_1 is not None:
        row["control_conc_1"] = imp.control_conc_1
    if imp.control_conc_2 is not None:
        row["control_conc_2"] = imp.control_conc_2
    corrida_id = _persistir_corrida(db, row, None)
    if not corrida_id:
        raise RuntimeError(
            "No se pudo crear la corrida (la base de datos no devolvió su id). "
            "No se registraron resultados para evitar datos huérfanos."
        )

    fecha = fecha_ensayo or datetime.utcnow().date().isoformat()
    muestra_ids = [mid for mid in asignaciones.values() if mid]
    validados = _ids_validados(db, muestra_ids, param_id)

    for idx, muestra_id in asignaciones.items():
        if not muestra_id or muestra_id in validados:
            continue
        if idx < 0 or idx >= len(imp.muestras):
            continue
        m = imp.muestras[idx]
        res = ResultadoMuestra(
            od_1=m.od_1, od_2=m.od_2, cv_pct=m.cv_pct,
            conc_ugL=m.conc_ugL, en_rango=m.en_rango, motivo=m.motivo,
        )
        _upsert_resultado(db, muestra_id=muestra_id, param_id=param_id,
                          corrida_id=corrida_id, res=res, lcm=lcm,
                          fecha=fecha, analista_id=analista_id)

    _invalidar_cache()
    return corrida_id


# ─────────────────────────────────────────────────────────────────────────────
# Código de reporte por campaña
# ─────────────────────────────────────────────────────────────────────────────

def get_codigo_reporte(
    campana_id: str, fecha_emision: Optional[str] = None, crear: bool = True
) -> Optional[str]:
    """
    Correlativo 'LVCA - NNN-MC-AAAA' por campaña. Lo lee de microcistina_reportes;
    si no existe y ``crear`` es True, lo genera y guarda.
    """
    db = get_db()
    try:
        r = (
            db.table("microcistina_reportes").select("*")
            .eq("campana_id", campana_id).limit(1).execute()
        )
        rows = r.data or []
    except Exception:
        rows = []
    if rows and rows[0].get("codigo_reporte"):
        return rows[0]["codigo_reporte"]
    if not crear:
        return None
    codigo = _generar_codigo_reporte(db, fecha_emision)
    try:
        db.table("microcistina_reportes").upsert(
            {"campana_id": campana_id, "codigo_reporte": codigo,
             "fecha_emision": fecha_emision},
            on_conflict="campana_id",
        ).execute()
    except Exception:
        pass
    return codigo


def _generar_codigo_reporte(db, fecha_emision: Optional[str]) -> str:
    """Correlativo vía función SQL siguiente_codigo(); cae a conteo si falla."""
    anio = datetime.utcnow().year
    if fecha_emision:
        try:
            anio = int(str(fecha_emision)[:4])
        except (ValueError, TypeError):
            pass
    n = None
    try:
        rpc = db.rpc("siguiente_codigo", {
            "p_tabla": "reporte_mc", "p_prefijo": "MC", "p_anio": anio,
        }).execute()
        n = rpc.data
        if isinstance(n, list):
            n = n[0] if n else None
    except Exception:
        n = None
    if n is None:
        try:
            res = db.table("microcistina_reportes").select("campana_id", count="exact").execute()
            n = (getattr(res, "count", 0) or 0) + 1
        except Exception:
            n = 1
    return f"LVCA - {int(n):03d}-MC-{anio}"


def _ids_validados(db, muestra_ids: list[str], param_id: str) -> set[str]:
    if not muestra_ids:
        return set()
    try:
        res = (
            db.table("resultados_laboratorio")
            .select("muestra_id, validado")
            .in_("muestra_id", muestra_ids)
            .eq("parametro_id", param_id)
            .eq("validado", True)
            .execute()
        )
        return {r["muestra_id"] for r in (res.data or [])}
    except Exception:
        return set()
