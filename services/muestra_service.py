"""
services/muestra_service.py
Lógica de negocio para registro de muestras de campo,
mediciones in situ, cadena de custodia y generación de etiquetas QR.

Funciones públicas:
    crear_muestra(datos)                   → código LVCA-YYYY-NNN
    registrar_insitu(muestra_id, mediciones)
    get_mediciones_insitu(muestra_id)
    get_limites_insitu(muestra_id)         → límites ECA para parámetros in situ
    recibir_en_laboratorio(muestra_id, ...) → custodia
    actualizar_estado_muestra(id, estado)
    generar_qr_pdf(muestra_id)             → bytes PDF descargable
    get_muestras_por_campana(campana_id, ...)
    get_usuarios_campo()
    get_campanas_en_campo()
    get_puntos_de_campana_activa(campana_id)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from io import BytesIO
from typing import Optional

from database.client import get_admin_client
from services.parametro_registry import (
    get_parametros_insitu,
    get_campo_a_parametro_map,
)

# Etiquetas de profundidad
PROFUNDIDAD_LABELS = {"S": "Superficie", "M": "Medio", "F": "Fondo"}
PROFUNDIDAD_SUFIJOS = {"S": "(S)", "M": "(M)", "F": "(F)"}


def _invalidar_cache() -> None:
    """Limpia cachés tras modificar muestras/mediciones."""
    try:
        import streamlit as st
        st.cache_data.clear()
    except Exception:
        pass

# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

TIPOS_MUESTRA = [
    "simple",
    "compuesta",
    "duplicada",
    "blanco_campo",
    "blanco_viaje",
]

ETIQUETA_TIPO: dict[str, str] = {
    "simple":       "Simple",
    "compuesta":    "Compuesta",
    "duplicada":    "Duplicada (QA/QC)",
    "blanco_campo": "Blanco de campo",
    "blanco_viaje": "Blanco de viaje",
}

ESTADOS_MUESTRA = [
    "recolectada",
    "en_transporte",
    "en_laboratorio",
    "analizada",
]

TRANSICIONES_MUESTRA: dict[str, str] = {
    "recolectada":      "en_transporte",
    "en_transporte":    "en_laboratorio",
    "en_laboratorio":   "analizada",
}

ETIQUETA_ESTADO_MUESTRA: dict[str, str] = {
    "recolectada":      "🟡 Recolectada",
    "en_transporte":    "🚗 En transporte",
    "en_laboratorio":   "🔬 En laboratorio",
    "analizada":        "✅ Analizada",
}

ESTADOS_FRASCO = [
    "integro",
    "fisura_leve",
    "tapa_floja",
    "derrame_parcial",
    "roto",
]

OPCIONES_CLIMA = [
    "Despejado",
    "Parcialmente nublado",
    "Nublado",
    "Lluvia leve",
    "Lluvia moderada",
    "Lluvia intensa",
]

# Parámetros medidos en campo (in situ) — dinámico desde BD
# Se mantiene el nombre ``PARAMETROS_INSITU`` como función para retrocompatibilidad
PARAMETROS_INSITU = get_parametros_insitu


# ─────────────────────────────────────────────────────────────────────────────
# Selectores
# ─────────────────────────────────────────────────────────────────────────────

def get_campanas_en_campo() -> list[dict]:
    """Campañas con estado 'en_campo' (aptas para registrar muestras)."""
    db = get_admin_client()
    res = (
        db.table("campanas")
        .select("id, codigo, nombre, fecha_inicio, fecha_fin")
        .eq("estado", "en_campo")
        .order("fecha_inicio", desc=True)
        .execute()
    )
    return res.data or []


def get_puntos_de_campana_activa(campana_id: str) -> list[dict]:
    """Puntos vinculados a la campaña (desde campana_puntos)."""
    db = get_admin_client()
    res = (
        db.table("campana_puntos")
        .select("puntos_muestreo(id, codigo, nombre, tipo, cuenca, eca_id)")
        .eq("campana_id", campana_id)
        .execute()
    )
    puntos = [
        r["puntos_muestreo"]
        for r in (res.data or [])
        if r.get("puntos_muestreo")
    ]
    return sorted(puntos, key=lambda x: x.get("codigo", ""))


def get_usuarios_campo() -> list[dict]:
    """Usuarios activos con rol visualizador o superior (técnicos de campo)."""
    db = get_admin_client()
    res = (
        db.table("usuarios")
        .select("id, nombre, apellido, rol, institucion")
        .eq("activo", True)
        .in_("rol", ["administrador", "visualizador"])
        .order("apellido")
        .execute()
    )
    return res.data or []


# ─────────────────────────────────────────────────────────────────────────────
# Creación de muestra
# ─────────────────────────────────────────────────────────────────────────────

def crear_muestra(datos: dict) -> dict:
    """
    Inserta una nueva muestra con código autogenerado LVCA-YYYY-NNN.

    datos esperados:
        campana_id, punto_muestreo_id, tipo_muestra,
        fecha_muestreo (str ISO), hora_recoleccion (str HH:MM),
        tecnico_campo_id, clima, caudal_estimado, nivel_agua,
        preservante, temperatura_transporte, observaciones_campo,
        modo_muestreo ('superficial' | 'columna'),
        profundidad_total, profundidad_secchi,
        profundidades: {S: valor_m, M: valor_m, F: valor_m}  (solo columna)

    Retorna el dict de la muestra creada (primera si columna).
    """
    modo = datos.get("modo_muestreo", "superficial")

    if modo == "columna":
        return _crear_muestras_columna(datos)

    return _crear_muestra_simple(datos)


def _crear_muestra_simple(datos: dict) -> dict:
    """Crea una sola muestra (superficial o normal)."""
    db = get_admin_client()
    codigo = _generar_codigo_muestra(db)

    fila = _build_fila(datos, codigo)
    fila["modo_muestreo"] = datos.get("modo_muestreo", "superficial")

    return _insert_muestra(db, fila)


def _crear_muestras_columna(datos: dict) -> dict:
    """Crea 3 muestras vinculadas (S, M, F) para muestreo en columna de agua."""
    db = get_admin_client()
    grupo_id = str(uuid.uuid4())
    profundidades = datos.get("profundidades", {})

    primera = None
    for tipo_prof in ("S", "M", "F"):
        codigo = _generar_codigo_muestra(db)
        fila = _build_fila(datos, codigo)
        fila["modo_muestreo"] = "columna"
        fila["profundidad_tipo"] = tipo_prof
        fila["profundidad_valor"] = profundidades.get(tipo_prof)
        fila["grupo_profundidad"] = grupo_id
        fila["profundidad_total"] = datos.get("profundidad_total")
        fila["profundidad_secchi"] = datos.get("profundidad_secchi")

        created = _insert_muestra(db, fila)
        if primera is None:
            primera = created

    _invalidar_cache()
    return primera


def _build_fila(datos: dict, codigo: str) -> dict:
    """Construye el dict base para insertar una muestra."""
    fila = {
        "codigo":                  codigo,
        "campana_id":              datos["campana_id"],
        "punto_muestreo_id":       datos["punto_muestreo_id"],
        "tipo_muestra":            datos.get("tipo_muestra", "simple"),
        "fecha_muestreo":          datos["fecha_muestreo"],
        "hora_recoleccion":        datos.get("hora_recoleccion"),
        "tecnico_campo_id":        datos.get("tecnico_campo_id"),
        "clima":                   datos.get("clima"),
        "caudal_estimado":         datos.get("caudal_estimado"),
        "nivel_agua":              datos.get("nivel_agua"),
        "preservante":             datos.get("preservante"),
        "temperatura_transporte":  datos.get("temperatura_transporte"),
        "observaciones_campo":     datos.get("observaciones_campo") or None,
        "estado":                  "recolectada",
    }
    cod_lab = datos.get("codigo_laboratorio")
    if cod_lab and isinstance(cod_lab, str) and cod_lab.strip():
        fila["codigo_laboratorio"] = cod_lab.strip()
    return fila


def _insert_muestra(db, fila: dict) -> dict:
    """Inserta una muestra, con fallback si columnas nuevas no existen."""
    # Campos que requieren migraciones (pueden no existir)
    campos_opcionales = [
        "codigo_laboratorio", "modo_muestreo", "profundidad_tipo",
        "profundidad_valor", "grupo_profundidad",
        "profundidad_total", "profundidad_secchi",
    ]
    try:
        res = db.table("muestras").insert(fila).execute()
        _invalidar_cache()
        return res.data[0]
    except Exception:
        # Quitar campos opcionales que pueden no existir
        for campo in campos_opcionales:
            fila.pop(campo, None)

    res = db.table("muestras").insert(fila).execute()
    _invalidar_cache()
    return res.data[0]


# ─────────────────────────────────────────────────────────────────────────────
# Mediciones in situ
# ─────────────────────────────────────────────────────────────────────────────

# Mapeo: clave de campo → código de parámetro en tabla `parametros`
# Ahora se lee del registro centralizado
_CAMPO_A_PARAMETRO = get_campo_a_parametro_map()


def registrar_insitu(
    muestra_id: str,
    mediciones: list[dict],
    equipo: str = "",
    numero_serie: str = "",
) -> tuple[int, list[str]]:
    """
    Guarda mediciones in situ (pH, T, CE, OD, turbidez, TDS, salinidad).

    mediciones: [{parametro, valor, unidad}]  (parametro = clave como 'ph')
    UPSERT por (muestra_id, parametro).

    Además crea/actualiza registros en resultados_laboratorio para que
    los parámetros de campo también se evalúen contra el ECA del punto.

    Retorna (ok_count, errores).
    """
    db = get_admin_client()
    ok = 0
    errores: list[str] = []

    # Obtener fecha de la muestra para resultados_laboratorio
    muestra = (
        db.table("muestras")
        .select("fecha_muestreo")
        .eq("id", muestra_id)
        .single()
        .execute()
    ).data
    fecha_muestra = (muestra or {}).get("fecha_muestreo")

    # Cargar IDs de parámetros para el mapeo campo → resultados_laboratorio
    codigos_campo = list(_CAMPO_A_PARAMETRO.values())
    params_db = (
        db.table("parametros")
        .select("id, codigo")
        .in_("codigo", codigos_campo)
        .execute()
    ).data or []
    param_id_por_codigo = {p["codigo"]: p["id"] for p in params_db}

    for m in mediciones:
        if m.get("valor") is None:
            continue
        fila = {
            "muestra_id":   muestra_id,
            "parametro":    m["parametro"],
            "valor":        m["valor"],
            "unidad":       m.get("unidad", ""),
            "equipo":       equipo or None,
            "numero_serie": numero_serie or None,
        }
        try:
            db.table("mediciones_insitu").upsert(
                fila, on_conflict="muestra_id,parametro"
            ).execute()
            ok += 1

            # También guardar en resultados_laboratorio para evaluar vs ECA
            codigo_param = _CAMPO_A_PARAMETRO.get(m["parametro"])
            param_id = param_id_por_codigo.get(codigo_param) if codigo_param else None
            if param_id and fecha_muestra:
                existente = (
                    db.table("resultados_laboratorio")
                    .select("id")
                    .eq("muestra_id", muestra_id)
                    .eq("parametro_id", param_id)
                    .execute()
                )
                rows = existente.data or []
                if rows:
                    db.table("resultados_laboratorio").update({
                        "valor_numerico": m["valor"],
                        "fecha_analisis": fecha_muestra,
                    }).eq("id", rows[0]["id"]).execute()
                else:
                    db.table("resultados_laboratorio").insert({
                        "muestra_id":     muestra_id,
                        "parametro_id":   param_id,
                        "valor_numerico": m["valor"],
                        "fecha_analisis": fecha_muestra,
                    }).execute()

        except Exception as exc:
            errores.append(f"{m['parametro']}: {exc}")

    _invalidar_cache()
    return ok, errores


def get_mediciones_insitu(muestra_id: str) -> dict[str, dict]:
    """
    Retorna mediciones in situ existentes.
    Formato: {clave_parametro: {valor, unidad, equipo, numero_serie}}
    """
    db = get_admin_client()
    res = (
        db.table("mediciones_insitu")
        .select("parametro, valor, unidad, equipo, numero_serie")
        .eq("muestra_id", muestra_id)
        .execute()
    )
    return {r["parametro"]: r for r in (res.data or [])}


def get_limites_insitu(muestra_id: str) -> dict[str, dict]:
    """
    Retorna los límites ECA aplicables a los parámetros in situ,
    basándose en el ECA asignado al punto de muestreo de la muestra.

    Formato: {nombre_parametro_normalizado: {valor_minimo, valor_maximo}}

    La búsqueda compara los nombres de los parámetros ECA contra
    los nombres definidos en PARAMETROS_INSITU.
    """
    db = get_admin_client()

    # Muestra → punto → eca_id
    m = (
        db.table("muestras")
        .select("puntos_muestreo(eca_id)")
        .eq("id", muestra_id)
        .single()
        .execute()
    )
    eca_id = (m.data.get("puntos_muestreo") or {}).get("eca_id")
    if not eca_id:
        return {}

    # Límites ECA con nombre del parámetro
    res = (
        db.table("eca_valores")
        .select("valor_minimo, valor_maximo, parametros(nombre)")
        .eq("eca_id", eca_id)
        .execute()
    )

    # Nombres de referencia de parámetros in situ (lowercase para matching)
    nombres_insitu = {p["nombre"].lower(): p["clave"] for p in get_parametros_insitu()}

    limites: dict[str, dict] = {}
    for r in (res.data or []):
        nombre_db = ((r.get("parametros") or {}).get("nombre") or "").lower()
        # Buscar coincidencia parcial
        for nombre_ref, clave in nombres_insitu.items():
            if nombre_ref in nombre_db or nombre_db in nombre_ref:
                limites[clave] = {
                    "valor_minimo": r.get("valor_minimo"),
                    "valor_maximo": r.get("valor_maximo"),
                }
                break

    return limites


# ─────────────────────────────────────────────────────────────────────────────
# Cadena de custodia
# ─────────────────────────────────────────────────────────────────────────────

class TransicionMuestraError(Exception):
    """Transición de estado inválida para la muestra."""


def actualizar_estado_muestra(muestra_id: str, nuevo_estado: str) -> None:
    """
    Transición simple de estado.
    recolectada → en_transporte → en_laboratorio → analizada
    """
    db = get_admin_client()

    res = (
        db.table("muestras")
        .select("estado")
        .eq("id", muestra_id)
        .single()
        .execute()
    )
    actual = res.data["estado"]

    if TRANSICIONES_MUESTRA.get(actual) != nuevo_estado:
        raise TransicionMuestraError(
            f"No se puede pasar de '{actual}' a '{nuevo_estado}'. "
            f"Siguiente estado válido: '{TRANSICIONES_MUESTRA.get(actual, '(ninguno)')}'."
        )

    db.table("muestras").update(
        {"estado": nuevo_estado}
    ).eq("id", muestra_id).execute()
    _invalidar_cache()


def recibir_en_laboratorio(
    muestra_id:     str,
    receptor_id:    str,
    estado_frasco:  str,
    observaciones:  str = "",
) -> None:
    """
    Registra la recepción de una muestra en el laboratorio.
    Cambia el estado a 'en_laboratorio' y guarda datos de custodia.
    """
    db = get_admin_client()

    # Verificar que esté en estado 'en_transporte'
    res = (
        db.table("muestras")
        .select("estado")
        .eq("id", muestra_id)
        .single()
        .execute()
    )
    if res.data["estado"] != "en_transporte":
        raise TransicionMuestraError(
            f"La muestra debe estar 'en_transporte' para ser recibida. "
            f"Estado actual: '{res.data['estado']}'."
        )

    db.table("muestras").update({
        "estado":                   "en_laboratorio",
        "receptor_lab_id":          receptor_id,
        "fecha_recepcion_lab":      datetime.utcnow().isoformat(),
        "estado_frasco_recepcion":  estado_frasco,
        "observaciones_recepcion":  observaciones or None,
    }).eq("id", muestra_id).execute()


# ─────────────────────────────────────────────────────────────────────────────
# Listado de muestras
# ─────────────────────────────────────────────────────────────────────────────

def get_muestras_por_campana(
    campana_id:    str,
    filtro_estado: Optional[str] = None,
    filtro_punto:  Optional[str] = None,
) -> list[dict]:
    """Muestras de una campaña con filtros opcionales."""
    db = get_admin_client()
    _select_base = (
        "id, codigo, tipo_muestra, fecha_muestreo, hora_recoleccion, "
        "estado, clima, nivel_agua, temperatura_transporte, "
        "preservante, observaciones_campo, "
        "puntos_muestreo(id, codigo, nombre), "
        "tecnico:usuarios!tecnico_campo_id(nombre, apellido)"
    )
    _select_con_lab = (
        "id, codigo, codigo_laboratorio, tipo_muestra, fecha_muestreo, hora_recoleccion, "
        "estado, clima, nivel_agua, temperatura_transporte, "
        "preservante, observaciones_campo, "
        "puntos_muestreo(id, codigo, nombre), "
        "tecnico:usuarios!tecnico_campo_id(nombre, apellido)"
    )
    _depth_fields = (
        ", modo_muestreo, profundidad_tipo, profundidad_valor, "
        "grupo_profundidad, profundidad_total, profundidad_secchi"
    )

    # Detectar si codigo_laboratorio existe (test con query separada)
    try:
        db.table("muestras").select("codigo_laboratorio").limit(1).execute()
        select_fields = _select_con_lab
    except Exception:
        select_fields = _select_base

    # Intentar agregar campos de profundidad
    try:
        db.table("muestras").select("modo_muestreo").limit(1).execute()
        select_fields += _depth_fields
    except Exception:
        pass

    query = (
        db.table("muestras")
        .select(select_fields)
        .eq("campana_id", campana_id)
        .order("fecha_muestreo", desc=True)
    )

    if filtro_estado and filtro_estado in ESTADOS_MUESTRA:
        query = query.eq("estado", filtro_estado)
    if filtro_punto:
        query = query.eq("punto_muestreo_id", filtro_punto)

    return query.execute().data or []


def get_muestra_por_campana_punto(campana_id: str, punto_id: str) -> dict | None:
    """Retorna la muestra más reciente de un punto en una campaña, o None.
    Para muestras de columna, retorna la primera (S) del grupo."""
    db = get_admin_client()
    _select = (
        "id, codigo, tipo_muestra, fecha_muestreo, hora_recoleccion, "
        "estado, clima, caudal_estimado, nivel_agua, preservante, "
        "temperatura_transporte, observaciones_campo, "
        "tecnico_campo_id, punto_muestreo_id"
    )
    # Intentar con campos de profundidad
    try:
        res = (
            db.table("muestras")
            .select(
                _select + ", modo_muestreo, profundidad_tipo, profundidad_valor, "
                "grupo_profundidad, profundidad_total, profundidad_secchi"
            )
            .eq("campana_id", campana_id)
            .eq("punto_muestreo_id", punto_id)
            .order("fecha_muestreo", desc=True)
            .execute()
        )
        datos = res.data or []
    except Exception:
        res = (
            db.table("muestras")
            .select(_select)
            .eq("campana_id", campana_id)
            .eq("punto_muestreo_id", punto_id)
            .order("fecha_muestreo", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    if not datos:
        return None

    # Si la primera muestra es de columna, retornar con las 3 profundidades
    primera = datos[0]
    grupo = primera.get("grupo_profundidad")
    if grupo and primera.get("modo_muestreo") == "columna":
        # Agrupar las 3 muestras del mismo grupo
        grupo_muestras = [d for d in datos if d.get("grupo_profundidad") == grupo]
        profundidades = {}
        for gm in grupo_muestras:
            tp = gm.get("profundidad_tipo")
            if tp:
                profundidades[tp] = {
                    "id": gm["id"],
                    "codigo": gm["codigo"],
                    "valor": gm.get("profundidad_valor"),
                }
        primera["_grupo_muestras"] = profundidades
    return primera


def get_muestras_grupo(grupo_profundidad: str) -> list[dict]:
    """Retorna las muestras de un grupo de profundidad (S, M, F)."""
    db = get_admin_client()
    res = (
        db.table("muestras")
        .select("id, codigo, profundidad_tipo, profundidad_valor")
        .eq("grupo_profundidad", grupo_profundidad)
        .order("profundidad_tipo")
        .execute()
    )
    return res.data or []


def get_muestra_detalle(muestra_id: str) -> dict:
    """Detalle completo de una muestra individual."""
    db = get_admin_client()
    res = (
        db.table("muestras")
        .select(
            "*, "
            "puntos_muestreo(codigo, nombre, eca_id, ecas(codigo, nombre)), "
            "tecnico:usuarios!tecnico_campo_id(nombre, apellido), "
            "receptor:usuarios!receptor_lab_id(nombre, apellido), "
            "campanas(codigo, nombre)"
        )
        .eq("id", muestra_id)
        .single()
        .execute()
    )
    return res.data


# ─────────────────────────────────────────────────────────────────────────────
# Generación de etiqueta QR (PDF 5cm × 3cm)
# ─────────────────────────────────────────────────────────────────────────────

def generar_qr_pdf(muestra_id: str) -> bytes:
    """
    Genera un PDF de 5cm × 3cm con código QR y datos de la muestra.
    El QR codifica: código, punto, fecha, campaña.

    Requiere: pip install qrcode[pil] reportlab

    Retorna bytes del PDF (listo para st.download_button).
    """
    import qrcode
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    db = get_admin_client()
    muestra = (
        db.table("muestras")
        .select(
            "codigo, fecha_muestreo, tipo_muestra, "
            "puntos_muestreo(codigo, nombre), "
            "campanas(codigo)"
        )
        .eq("id", muestra_id)
        .single()
        .execute()
        .data
    )

    punto   = muestra.get("puntos_muestreo") or {}
    campana = muestra.get("campanas") or {}

    # ── Datos del QR ─────────────────────────────────────────────────────────
    qr_payload = json.dumps({
        "codigo":  muestra["codigo"],
        "punto":   punto.get("codigo", ""),
        "fecha":   str(muestra.get("fecha_muestreo", ""))[:10],
        "campana": campana.get("codigo", ""),
        "tipo":    muestra.get("tipo_muestra", ""),
    }, ensure_ascii=True)

    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(qr_payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")

    qr_buffer = BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    # ── PDF label 5cm × 3cm ──────────────────────────────────────────────────
    ancho  = 50 * mm
    alto   = 30 * mm

    pdf_buffer = BytesIO()
    c = rl_canvas.Canvas(pdf_buffer, pagesize=(ancho, alto))

    # Borde
    c.setStrokeColorRGB(0.7, 0.7, 0.7)
    c.setLineWidth(0.3)
    c.rect(0.5 * mm, 0.5 * mm, ancho - 1 * mm, alto - 1 * mm)

    # QR (lado izquierdo)
    qr_size = 20 * mm
    c.drawImage(
        ImageReader(qr_buffer),
        2 * mm, 5 * mm,
        qr_size, qr_size,
    )

    # Texto (lado derecho)
    tx = 24 * mm

    c.setFont("Helvetica-Bold", 5)
    c.drawString(tx, alto - 5 * mm, "AUTODEMA - LVCA")

    c.setFont("Helvetica-Bold", 8)
    c.drawString(tx, alto - 10 * mm, muestra["codigo"])

    c.setFont("Helvetica", 5)
    c.drawString(tx, alto - 14 * mm, f"Punto: {punto.get('codigo', '—')}")

    nombre_corto = (punto.get("nombre") or "")[:22]
    c.drawString(tx, alto - 17.5 * mm, nombre_corto)

    fecha_str = str(muestra.get("fecha_muestreo", ""))[:10]
    c.drawString(tx, alto - 21 * mm, f"Fecha: {fecha_str}")

    tipo_label = ETIQUETA_TIPO.get(muestra.get("tipo_muestra", ""), "")
    c.setFont("Helvetica-Oblique", 4.5)
    c.drawString(tx, alto - 24.5 * mm, tipo_label)

    c.save()
    return pdf_buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def actualizar_muestra(muestra_id: str, datos: dict) -> dict:
    """
    Actualiza campos editables de una muestra existente.

    datos puede incluir:
        tipo_muestra, fecha_muestreo, hora_recoleccion, tecnico_campo_id,
        clima, caudal_estimado, nivel_agua, preservante,
        temperatura_transporte, observaciones_campo, codigo_laboratorio
    """
    db = get_admin_client()
    campos = {}
    campos_texto = (
        "tipo_muestra", "fecha_muestreo", "hora_recoleccion",
        "clima", "preservante", "observaciones_campo", "codigo_laboratorio",
    )
    for key in campos_texto:
        if key in datos:
            val = datos[key]
            campos[key] = val.strip() if isinstance(val, str) and val else val or None

    campos_ref = ("tecnico_campo_id", "punto_muestreo_id")
    for key in campos_ref:
        if key in datos:
            campos[key] = datos[key] or None

    campos_num = (
        "caudal_estimado", "nivel_agua", "temperatura_transporte",
        "profundidad_valor", "profundidad_total", "profundidad_secchi",
    )
    for key in campos_num:
        if key in datos:
            campos[key] = datos[key] if datos[key] is not None else None

    if not campos:
        raise ValueError("No se proporcionaron campos para actualizar.")

    res = (
        db.table("muestras")
        .update(campos)
        .eq("id", muestra_id)
        .execute()
    )
    return res.data[0] if res.data else {}


def eliminar_muestra(muestra_id: str) -> None:
    """
    Elimina una muestra y sus registros relacionados.
    Solo se permite eliminar muestras en estado 'recolectada'.
    """
    db = get_admin_client()

    # Verificar estado
    res = (
        db.table("muestras")
        .select("estado")
        .eq("id", muestra_id)
        .single()
        .execute()
    )
    estado = res.data["estado"]
    if estado != "recolectada":
        raise ValueError(
            f"Solo se pueden eliminar muestras en estado 'recolectada'. "
            f"Estado actual: '{estado}'."
        )

    # Verificar que no tenga resultados de laboratorio
    r_count = (
        db.table("resultados_laboratorio")
        .select("id", count="exact")
        .eq("muestra_id", muestra_id)
        .execute()
    )
    if (r_count.count or 0) > 0:
        raise ValueError(
            f"No se puede eliminar: la muestra tiene {r_count.count} resultado(s) de laboratorio."
        )

    # Eliminar mediciones in situ
    db.table("mediciones_insitu").delete().eq("muestra_id", muestra_id).execute()
    # Eliminar muestra
    db.table("muestras").delete().eq("id", muestra_id).execute()


def _generar_codigo_muestra(db) -> str:
    """
    Genera código secuencial: LVCA-YYYY-NNN.
    Ejemplo: LVCA-2025-001, LVCA-2025-002, ...
    """
    year = datetime.utcnow().year
    prefijo = f"LVCA-{year}-"

    res = (
        db.table("muestras")
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
