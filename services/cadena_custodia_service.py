"""
services/cadena_custodia_service.py
Generación de Cadena de Custodia en formato Excel y PDF.
Formato oficial AUTODEMA — CC-MON-01 Rev 03.

El Excel se genera a partir de la plantilla original (templates/cadena_template.xlsx)
preservando exactamente el formato, colores, fuentes, merges y estructura.

Funciones públicas:
    get_datos_cadena(campana_id)                 → datos para la cadena
    generar_excel_cadena(campana_id, config)      → bytes .xlsx
    generar_pdf_cadena(campana_id, config)        → bytes .pdf
"""

from __future__ import annotations

import os
from datetime import datetime
from io import BytesIO
from typing import Optional

from database.client import get_admin_client
from services.parametro_registry import (
    get_parametros_lab_cadena,
    get_parametros_campo_cadena,
    get_insitu_a_cadena_map,
)


# ─────────────────────────────────────────────────────────────────────────────
# Parámetros de laboratorio y campo — ahora dinámicos desde la BD
# Se mantienen los nombres para retrocompatibilidad con importaciones.
# ─────────────────────────────────────────────────────────────────────────────

def _get_parametros_lab_default() -> list[dict]:
    """Parámetros de laboratorio para la cadena, leídos de la BD."""
    return get_parametros_lab_cadena()

def _get_parametros_campo() -> list[dict]:
    """Parámetros de campo para la cadena, leídos de la BD."""
    return get_parametros_campo_cadena()

# Accesores globales para retrocompatibilidad de importación
PARAMETROS_LAB_DEFAULT = _get_parametros_lab_default
PARAMETROS_CAMPO = _get_parametros_campo

EQUIPOS_DEFAULT: list[dict] = [
    {"codigo": "21G102303/N",  "nombre": "Equipo multiparametro PRODSS YSI"},
    {"codigo": "9208180023",   "nombre": "Turbidimetro PALINTEST"},
]


def get_equipos_registrados() -> list[dict]:
    """
    Retorna la lista de equipos registrados en la tabla 'equipos_medicion'.
    Si la tabla no existe, retorna EQUIPOS_DEFAULT.
    """
    try:
        db = get_admin_client()
        res = (
            db.table("equipos_medicion")
            .select("id, codigo, nombre, activo")
            .eq("activo", True)
            .order("nombre")
            .execute()
        )
        equipos = res.data or []
        if equipos:
            return equipos
    except Exception:
        pass
    # Fallback a la lista por defecto
    return EQUIPOS_DEFAULT


def registrar_equipo(codigo: str, nombre: str) -> dict:
    """Registra un nuevo equipo de medición."""
    try:
        db = get_admin_client()
        res = db.table("equipos_medicion").insert({
            "codigo": codigo,
            "nombre": nombre,
            "activo": True,
        }).execute()
        return res.data[0]
    except Exception:
        # Si la tabla no existe, solo retornar el dict
        return {"codigo": codigo, "nombre": nombre}

# Mapeo de claves insitu a claves de la cadena — función para evaluación dinámica
def _get_insitu_map():
    return get_insitu_a_cadena_map()

# Mapeo dinámico: preservante → claves de parámetros lab que lo requieren.
# Se construye desde la configuración en data/parametros_config.json
# para que cualquier cambio en el módulo Parámetros se propague automáticamente.
def _get_preservante_claves() -> dict[str, set[str]]:
    """Construye {preservante: {codigo_lower, ...}} desde la config de parámetros."""
    from services.parametro_registry import get_all_param_configs
    mapping: dict[str, set[str]] = {}
    for codigo, cfg in get_all_param_configs().items():
        if not isinstance(cfg, dict):
            continue
        pres = cfg.get("preservante", "Ninguno")
        if pres and pres != "Ninguno":
            mapping.setdefault(pres, set()).add(codigo.lower())
    return mapping

# Fila en el template donde va cada preservante
_PRESERVANTE_ROW = {
    "HNO3": 4,
    "H2SO4": 5,
    "HCl": 6,
    "Lugol": 7,
    "S/P": 8,
    "Formol": 7,  # Comparte fila con Lugol (biológicos)
}

# Columna base de lab params en el template (15 columnas originales)
_COL_LAB_START = 26   # Z
_TEMPLATE_LAB_COUNT = 15
_TEMPLATE_FIELD_COUNT = 7

# Ruta de la plantilla
_TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "templates", "cadena_template.xlsx"
)


# ─────────────────────────────────────────────────────────────────────────────
# Obtener datos para la cadena
# ─────────────────────────────────────────────────────────────────────────────

def get_datos_cadena(campana_id: str) -> dict:
    """
    Recopila todos los datos necesarios para generar la cadena de custodia:
        campana, muestras (con punto, coordenadas, mediciones insitu)
    """
    db = get_admin_client()

    # Campaña
    campana = (
        db.table("campanas")
        .select(
            "id, codigo, nombre, fecha_inicio, fecha_fin, estado, "
            "responsable_campo, responsable_laboratorio, observaciones"
        )
        .eq("id", campana_id)
        .single()
        .execute()
        .data
    )

    # Muestras con punto (coordenadas UTM, cuenca, etc.)
    m_res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, hora_recoleccion, tipo_muestra, "
            "estado, preservante, observaciones_campo, "
            "clima, nivel_agua, temperatura_transporte, "
            "puntos_muestreo(codigo, nombre, tipo, cuenca, sistema_hidrico, "
            "  utm_este, utm_norte, utm_zona, altitud_msnm, "
            "  latitud, longitud)"
        )
        .eq("campana_id", campana_id)
        .order("fecha_muestreo")
        .execute()
    )
    muestras = m_res.data or []

    # Mediciones in situ por muestra
    muestra_ids = [m["id"] for m in muestras]
    insitu_map: dict[str, dict] = {}

    if muestra_ids:
        i_res = (
            db.table("mediciones_insitu")
            .select("muestra_id, parametro, valor")
            .in_("muestra_id", muestra_ids)
            .execute()
        )
        insitu_key_map = _get_insitu_map()
        for r in (i_res.data or []):
            mid = r["muestra_id"]
            if mid not in insitu_map:
                insitu_map[mid] = {}
            clave_cadena = insitu_key_map.get(r["parametro"], r["parametro"])
            insitu_map[mid][clave_cadena] = r["valor"]

    # Enriquecer cada muestra con insitu
    for m in muestras:
        m["insitu"] = insitu_map.get(m["id"], {})

    # Lugar de monitoreo (del primer punto)
    lugar = ""
    cuenca = ""
    if muestras and muestras[0].get("puntos_muestreo"):
        pt0 = muestras[0]["puntos_muestreo"]
        lugar = pt0.get("nombre", "")
        cuenca = pt0.get("cuenca", "")

    return {
        "campana": campana,
        "muestras": muestras,
        "lugar": lugar,
        "cuenca": cuenca,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Configuración por defecto
# ─────────────────────────────────────────────────────────────────────────────

def config_default() -> dict:
    """Retorna la configuración por defecto de la cadena."""
    return {
        "codigo_documento": "CC-MON-01",
        "revision": "03",
        "area": "SUBGERENCIA DE OPERACIÓN Y MANTENIMIENTO - LABORATORIO DE VIGILANCIA DE CALIDAD DE AGUA",
        "direccion": "Urb. La Marina E-8 - Cayma - Arequipa",
        "telefono": "(054)254040",
        "institucion": "AUTORIDAD AUTONOMA DE MAJES",
        "urgencia": "Regular",
        "preservacion": {"HNO3": True, "H2SO4": True, "HCl": False, "Lugol": True, "Formol": False, "S/P": True},
        "condiciones": {"refrigerado": True, "icepack": True, "temp_ambiente": False,
                        "congelado": False, "caja_conservadora": False, "hielo_potable": False},
        "parametros_lab": [p["clave"] for p in _get_parametros_lab_default()],
        "parametros_lab_extra": [],
        "equipos": EQUIPOS_DEFAULT.copy(),
        "muestreo_por": "laboratorio",
        "nombre_muestreador": "",
        "nombre_receptor": "",
        "nombre_supervisor": "",
        "observaciones_generales": "",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helper: escritura segura en celdas (maneja MergedCells)
# ─────────────────────────────────────────────────────────────────────────────

def _safe_set(ws, row: int, col: int, value):
    """Escribe un valor en una celda; si es MergedCell, lo ignora."""
    try:
        ws.cell(row=row, column=col).value = value
    except (AttributeError, TypeError):
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Generación Excel — basada en plantilla original
# ─────────────────────────────────────────────────────────────────────────────

def generar_excel_cadena(campana_id: str, config: dict | None = None) -> bytes:
    """
    Genera el Excel de cadena de custodia a partir de la plantilla AUTODEMA.

    Carga templates/cadena_template.xlsx, actualiza campos dinámicos y datos
    de las muestras, y devuelve los bytes del .xlsx resultante.

    La plantilla tiene estructura fija: 15 columnas lab (Z–AN) y 7 campo
    (AO–AU).  Los nombres de los headers se sobreescriben dinámicamente
    con los parámetros activos de la BD.
    """
    from openpyxl import load_workbook

    cfg = config or config_default()
    datos = get_datos_cadena(campana_id)
    campana = datos["campana"]
    muestras = datos["muestras"]

    # Parámetros dinámicos — acotados a la capacidad del template
    all_lab = _get_parametros_lab_default()
    all_campo = _get_parametros_campo()
    lab_params = all_lab[:_TEMPLATE_LAB_COUNT]      # máx 15
    campo_params = all_campo[:_TEMPLATE_FIELD_COUNT]  # máx 7

    params_activos = set(
        cfg.get("parametros_lab", [p["clave"] for p in lab_params])
    )
    for extra in cfg.get("parametros_lab_extra", []):
        params_activos.add(extra.lower().replace(" ", "_"))

    # Posiciones fijas del template — NO se insertan columnas
    col_field_start = _COL_LAB_START + _TEMPLATE_LAB_COUNT   # 41 (AO)
    col_obs = col_field_start + _TEMPLATE_FIELD_COUNT          # 48 (AV)

    # ── Cargar plantilla ──────────────────────────────────────────────────
    wb = load_workbook(_TEMPLATE_PATH)
    ws = wb.active
    _set = lambda r, c, v: _safe_set(ws, r, c, v)

    # ── Sobreescribir headers de parámetros (fila 11) ────────────────────
    for i in range(_TEMPLATE_LAB_COUNT):
        if i < len(lab_params):
            _set(11, _COL_LAB_START + i, lab_params[i]["nombre"])
        else:
            _set(11, _COL_LAB_START + i, "")

    for i in range(_TEMPLATE_FIELD_COUNT):
        if i < len(campo_params):
            _set(11, col_field_start + i, campo_params[i]["nombre"])
        else:
            _set(11, col_field_start + i, "")

    # ══════════════════════════════════════════════════════════════════════
    # 1. ENCABEZADO (filas 2–12)
    # ══════════════════════════════════════════════════════════════════════

    # Revisión documento (AO4 = col 41, merge AO4:AW8 — posición fija)
    _set(4, 41,
         f"Revision documento:\n"
         f"Codigo: {cfg.get('codigo_documento', 'CC-MON-01')}\n"
         f"Revision : {cfg.get('revision', '03')}\n"
         f"Fecha: {datetime.utcnow().strftime('%d-%b-%Y')}")

    # Área / Sub-área (F4 = col 6, merge F4:W5)
    _set(4, 6, cfg.get("area", ""))

    # Dirección (F6 = col 6, merge F6:J7)
    _set(6, 6, cfg.get("direccion", "Urb. La Marina E-8 - Cayma - Arequipa"))

    # Teléfono (O6 = col 15, merge O6:Q7)
    _set(6, 15, cfg.get("telefono", "(054)254040"))

    # Urgencia (T6 = col 20, merge T6:W6 / T7:W7)
    urgencia = cfg.get("urgencia", "Regular")
    _set(6, 20, f"Regular ({'X' if urgencia == 'Regular' else '    '})")
    _set(7, 20, f"Alta ({'X' if urgencia == 'Alta' else '    '})")

    # Institución (F8 = col 6, merge F8:W9)
    _set(8, 6, cfg.get("institucion", "AUTORIDAD AUTONOMA DE MAJES"))

    # Campaña (antes "Lugar de monitoreo") (F10 = col 6, merge F10:W11)
    campana_label = cfg.get("campana_label") or datos.get("lugar", "")
    _set(10, 6, campana_label)

    # Nombre de cuenca (F12 = col 6, merge F12:W12)
    _set(12, 6, datos.get("cuenca", ""))

    # ══════════════════════════════════════════════════════════════════════
    # 2. MARCAS DE PRESERVANTES (filas 4–8, cols 26–40)
    # ══════════════════════════════════════════════════════════════════════

    # Limpiar marcas existentes en las 15 columnas lab
    for row in range(4, 9):
        for col in range(_COL_LAB_START, _COL_LAB_START + _TEMPLATE_LAB_COUNT):
            _set(row, col, None)

    # Colocar marcas según config — por clave de parámetro
    pres = cfg.get("preservacion", {})
    preservante_claves = _get_preservante_claves()
    for idx, p in enumerate(lab_params):
        clave = p.get("clave", "").lower()
        codigo = p.get("codigo", "").lower()
        if clave not in params_activos:
            continue
        preservante_asignado = "S/P"
        for pres_nombre, claves_set in preservante_claves.items():
            if clave in claves_set or codigo in claves_set:
                preservante_asignado = pres_nombre
                break
        if pres.get(preservante_asignado, True):
            row_pres = _PRESERVANTE_ROW.get(preservante_asignado)
            if row_pres:
                _set(row_pres, _COL_LAB_START + idx, "X")

    # ══════════════════════════════════════════════════════════════════════
    # 3. DATOS DE MUESTRAS (filas 15–36: 11 slots × 2 filas)
    # ══════════════════════════════════════════════════════════════════════

    for slot in range(11):
        r1 = 15 + slot * 2   # fila impar (E: / alt:)
        r2 = r1 + 1          # fila par   (N: / Z:)

        # ── Limpiar celdas del slot ───────────────────────────────────────
        for col in [2, 3, 6, 17, 18, 19, 24, 25, col_obs]:
            _set(r1, col, None)
        for col in [20, 21, 22, 23]:
            _set(r1, col, None)
            _set(r2, col, None)
        for col in range(_COL_LAB_START, _COL_LAB_START + _TEMPLATE_LAB_COUNT):
            _set(r1, col, None)
        for col in range(col_field_start, col_field_start + _TEMPLATE_FIELD_COUNT):
            _set(r1, col, None)

        # ── Si no hay muestra para este slot, saltar ─────────────────────
        if slot >= len(muestras):
            continue

        m = muestras[slot]
        pt = m.get("puntos_muestreo") or {}
        insitu = m.get("insitu", {})

        # N° (B = col 2, merge B:B r1:r2)
        _set(r1, 2, float(slot + 1))

        # Código de laboratorio (C = col 3, merge C:E r1:r2)
        _set(r1, 3, m.get("codigo", ""))

        # Punto de muestreo (F = col 6, merge F:P r1:r2)
        nombre_punto = pt.get("nombre", "")
        codigo_punto = pt.get("codigo", "")
        _set(r1, 6, f"{nombre_punto} /{codigo_punto}" if nombre_punto else "")

        # Fecha (Q = col 17, merge Q:Q r1:r2)
        fecha_raw = m.get("fecha_muestreo", "")
        try:
            fecha_dt = datetime.strptime(str(fecha_raw)[:10], "%Y-%m-%d")
            _set(r1, 17, fecha_dt)
        except (ValueError, TypeError):
            _set(r1, 17, str(fecha_raw)[:10] if fecha_raw else None)

        # Hora (R = col 18, merge R:R r1:r2)
        _set(r1, 18, m.get("hora_recoleccion", "") or "")

        # Tipo de muestra / Matriz (S = col 19, merge S:S r1:r2)
        tipo_mapa = {
            "laguna": "ADL", "rio": "ADR", "canal": "ADR",
            "manantial": "AMA", "embalse": "ADL", "pozo": "ASUB",
        }
        _set(r1, 19, tipo_mapa.get(pt.get("tipo", ""), "AN"))

        # Coordenadas UTM — NO merged entre r1/r2 (valores distintos)
        _set(r1, 20, "E:")
        _set(r1, 21, pt.get("utm_este"))
        _set(r1, 22, "alt: ")
        _set(r1, 23, pt.get("altitud_msnm"))

        _set(r2, 20, "N:")
        _set(r2, 21, pt.get("utm_norte"))
        _set(r2, 22, "Z: ")
        _set(r2, 23, pt.get("utm_zona", "19 L"))

        # N° de frascos (X=24, Y=25, cada uno merged r1:r2)
        has_fito = "p120" in params_activos
        has_micro = "p091" in params_activos
        _set(r1, 24, 1.0 if has_fito else 0)
        _set(r1, 25, 4.0 if has_micro else 3.0)

        # Parámetros de laboratorio — "x" en columnas activas (máx 15)
        for i, p in enumerate(lab_params):
            if p["clave"] in params_activos:
                _set(r1, _COL_LAB_START + i, "x")

        # Parámetros de campo — valores numéricos con coma decimal (máx 7)
        for i, p in enumerate(campo_params):
            val = insitu.get(p["clave"])
            if val is not None:
                _set(r1, col_field_start + i, str(val).replace(".", ","))

        # Observaciones (AV = col 48, posición fija del template)
        # Auto-incluir clima, nivel y temp. transporte junto a las observaciones
        obs_parts = []
        if m.get("clima"):
            obs_parts.append(f"Clima: {m['clima']}")
        if m.get("nivel_agua"):
            obs_parts.append(f"Nivel: {m['nivel_agua']}")
        if m.get("temperatura_transporte") is not None:
            obs_parts.append(f"T.transp: {m['temperatura_transporte']}°C")
        if m.get("observaciones_campo"):
            obs_parts.append(m["observaciones_campo"])
        obs = "; ".join(obs_parts)
        if obs:
            _set(r1, col_obs, obs)

    # ══════════════════════════════════════════════════════════════════════
    # 4. PIE DE PÁGINA (filas 38–65)
    # ══════════════════════════════════════════════════════════════════════

    # Muestreo realizado por
    muestreo = cfg.get("muestreo_por", "laboratorio")
    _set(39, 4, "(   X      )" if muestreo == "laboratorio" else "(         )")
    _set(39, 8, "(   X      )" if muestreo != "laboratorio" else "(         )")

    # Nombre del muestreador (B40, merge B40:D41)
    _set(40, 2, f"Nombre:  {cfg.get('nombre_muestreador', '')}")

    # Nombre receptor en sección muestreo (E40, merge E40:H41)
    _set(40, 5, f"Nombre: {cfg.get('nombre_receptor', '')}")

    # Fecha muestreo (B42, merge B42:D44)
    fecha_hoy = datetime.utcnow().strftime("%d/%m/%Y")
    _set(42, 2, f"Fecha: {fecha_hoy}")

    # Fecha recepción (E42, merge E42:H44)
    _set(42, 5, "Fecha:")

    # Firma muestreador (B45, merge B45:D48)
    _set(45, 2, "Firma:")

    # Firma receptor (E45, merge E45:H48)
    _set(45, 5, "Firma:")

    # Equipos (R40:V43 = código, W40:AC43 = nombre — equipo 1)
    # (R44:V47 = código, W44:AC47 = nombre — equipo 2)
    equipos = cfg.get("equipos", EQUIPOS_DEFAULT)
    if len(equipos) > 0:
        _set(40, 18, equipos[0].get("codigo", ""))
        _set(40, 23, equipos[0].get("nombre", ""))
    else:
        _set(40, 18, "")
        _set(40, 23, "")
    if len(equipos) > 1:
        _set(44, 18, equipos[1].get("codigo", ""))
        _set(44, 23, equipos[1].get("nombre", ""))
    else:
        _set(44, 18, "")
        _set(44, 23, "")

    # Coordinador / Supervisor (B49 es header fijo)
    _set(50, 2, f"Nombre: {cfg.get('nombre_supervisor', '')}")
    _set(52, 2, f"Fecha: {datetime.utcnow().strftime('%d/%m/%y')}")
    _set(54, 2, "Firma:")

    # Recepción de muestra — nombre y fecha (J51:N53, J54:N56)
    _set(51, 10, f"Nombre: {cfg.get('nombre_receptor', '')}")
    _set(54, 10, f"Fecha / Hora: {datetime.utcnow().strftime('%d/%m/%y - %H:%M')}")

    # Condiciones de la muestra (columna AW = 49, posición fija del template)
    cond = cfg.get("condiciones", {})
    _set(39, 49, f"({'X' if cond.get('temp_ambiente') else '   '})")
    _set(42, 49, f"({'x' if cond.get('refrigerado') else '    '})")
    _set(47, 49, f"({'x' if cond.get('congelado') else '    '})")
    _set(50, 49, f"({'x' if cond.get('caja_conservadora') else '    '})")
    _set(53, 49, f"({'x' if cond.get('icepack') else '    '})")
    _set(55, 49, f"({'x' if cond.get('hielo_potable') else '    '})")

    # Observaciones generales (B60, merge B60:AW65)
    _set(60, 2, cfg.get("observaciones_generales", ""))

    # ══════════════════════════════════════════════════════════════════════
    # 5. GUARDAR
    # ══════════════════════════════════════════════════════════════════════

    output = BytesIO()
    wb.save(output)
    return output.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Generación PDF
# ─────────────────────────────────────────────────────────────────────────────

def generar_pdf_cadena(campana_id: str, config: dict | None = None) -> bytes:
    """
    Genera el PDF de cadena de custodia formato AUTODEMA landscape A4.
    Usa canvas de reportlab para control total: texto rotado, colores,
    estructura fiel al template Excel original.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, black, white, Color

    cfg = config or config_default()
    datos = get_datos_cadena(campana_id)
    campana = datos["campana"]
    muestras = datos["muestras"]

    # Acotar parámetros a la misma estructura que el Excel (15 lab + 7 campo)
    all_lab = _get_parametros_lab_default()
    params_lab = list(all_lab[:_TEMPLATE_LAB_COUNT])
    for extra in cfg.get("parametros_lab_extra", []):
        params_lab.append({"clave": extra.lower().replace(" ", "_"), "nombre": extra})

    params_activos = set(
        cfg.get("parametros_lab", [p["clave"] for p in params_lab])
    )
    for extra in cfg.get("parametros_lab_extra", []):
        params_activos.add(extra.lower().replace(" ", "_"))

    output = BytesIO()
    W, H = landscape(A4)
    c = Canvas(output, pagesize=(W, H))

    # Colores del template AUTODEMA
    GREEN = HexColor("#A8D08D")
    LIGHT_GREEN = HexColor("#E2EFD9")
    GRAY_BG = HexColor("#F5F5F5")
    BORDER = HexColor("#808080")

    ML = 8 * mm   # margen izquierdo
    MR = 8 * mm   # margen derecho
    CW = W - ML - MR  # ancho útil

    # ── Helpers de dibujo ─────────────────────────────────────────────────

    def rect(x, y, w, h, fill=None):
        """Dibuja un rectángulo con borde y opcionalmente relleno."""
        if fill:
            c.setFillColor(fill)
            c.rect(x, y, w, h, fill=1, stroke=0)
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.4)
        c.rect(x, y, w, h, fill=0, stroke=1)

    def txt(x, y, text, font="Helvetica", size=6, color=black, align="l"):
        """Escribe texto. align: l=left, c=center, r=right."""
        c.setFont(font, size)
        c.setFillColor(color)
        if align == "c":
            c.drawCentredString(x, y, str(text))
        elif align == "r":
            c.drawRightString(x, y, str(text))
        else:
            c.drawString(x, y, str(text))

    def txt_rot(x, y, text, font="Helvetica-Bold", size=5.5):
        """Escribe texto rotado 90° (de abajo hacia arriba)."""
        c.saveState()
        c.translate(x, y)
        c.rotate(90)
        c.setFont(font, size)
        c.setFillColor(black)
        c.drawString(1.5, -1, str(text))
        c.restoreState()

    # ══════════════════════════════════════════════════════════════════════
    # 1. ENCABEZADO INSTITUCIONAL
    # ══════════════════════════════════════════════════════════════════════

    y = H - 8 * mm
    th = 13 * mm  # alto del título
    y -= th

    s1w = CW * 0.28
    s2w = CW * 0.28
    s3w = CW * 0.44

    # Bloque 1: Gobierno Regional
    rect(ML, y, s1w, th, white)
    txt(ML + s1w / 2, y + th / 2 + 2, "GOBIERNO REGIONAL", "Helvetica-Bold", 9, black, "c")
    txt(ML + s1w / 2, y + th / 2 - 8, "DE AREQUIPA", "Helvetica-Bold", 9, black, "c")

    # Bloque 2: Cadena de Custodia
    x2 = ML + s1w
    rect(x2, y, s2w, th, white)
    txt(x2 + s2w / 2, y + th / 2 - 2, "CADENA DE CUSTODIA", "Helvetica-Bold", 11, black, "c")

    # Bloque 3: AUTODEMA / LVCA
    x3 = x2 + s2w
    rect(x3, y, s3w, th, white)
    txt(x3 + s3w / 2, y + th / 2 + 2, "AUTORIDAD AUTONOMA DE MAJES", "Helvetica-Bold", 8, black, "c")
    txt(x3 + s3w / 2, y + th / 2 - 7,
        "LABORATORIO DE VIGILANCIA Y CALIDAD DE AGUA (LVCA)", "Helvetica", 6.5, black, "c")

    # ══════════════════════════════════════════════════════════════════════
    # 2. DATOS GENERALES + PRESERVACIÓN
    # ══════════════════════════════════════════════════════════════════════

    bh = 5 * mm  # alto de barra
    y -= bh

    # Barra "DATOS GENERALES"
    dg_w = CW * 0.52
    rect(ML, y, dg_w, bh, GREEN)
    txt(ML + 3, y + 1.5 * mm, "DATOS GENERALES DEL MONITOREO", "Helvetica-Bold", 7)

    # Barra "PRESERVACIÓN"
    pr_x = ML + dg_w
    pr_w = CW * 0.28
    rect(pr_x, y, pr_w, bh, GREEN)
    txt(pr_x + 3, y + 1.5 * mm, "PRESERVACIÓN", "Helvetica-Bold", 7)

    # Barra "PÁGINA"
    pg_x = pr_x + pr_w
    pg_w = CW * 0.20
    rect(pg_x, y, pg_w, bh, white)
    txt(pg_x + 3, y + 1.5 * mm, "PAGINA: 1 de 1", "Helvetica", 6)

    # ── Filas de datos del encabezado ─────────────────────────────────────
    rh = 4.5 * mm
    pres = cfg.get("preservacion", {})

    # Fila: Área + HNO3/H2SO4 + Código doc
    y -= rh
    rect(ML, y, dg_w, rh, white)
    txt(ML + 3, y + 1.2 * mm, f"ÁREA: {cfg.get('area', '')[:75]}", "Helvetica", 5.5)

    rect(pr_x, y, pr_w, rh, HexColor("#D5E8C0"))
    txt(pr_x + 3, y + 1.2 * mm,
        f"HNO3: {'X' if pres.get('HNO3') else '—'}     "
        f"H2SO4: {'X' if pres.get('H2SO4') else '—'}", "Helvetica", 5.5)

    rev_h = rh * 3
    rect(pg_x, y - rh * 2, pg_w, rev_h, white)
    txt(pg_x + 3, y + 1 * mm,
        f"Código: {cfg.get('codigo_documento', 'CC-MON-01')}  Rev: {cfg.get('revision', '03')}",
        "Helvetica", 5.5)
    txt(pg_x + 3, y + 1 * mm - rh, f"Fecha: {datetime.utcnow().strftime('%d-%b-%Y')}", "Helvetica", 5.5)

    # Fila: Dirección + HCl/Lugol/Formol
    y -= rh
    rect(ML, y, dg_w, rh, white)
    txt(ML + 3, y + 1.2 * mm,
        f"DIRECCIÓN: {cfg.get('direccion', '')}     TEL: {cfg.get('telefono', '')}",
        "Helvetica", 5.5)

    rect(pr_x, y, pr_w, rh, HexColor("#D5E8C0"))
    txt(pr_x + 3, y + 1.2 * mm,
        f"HCl: {'X' if pres.get('HCl') else '—'}     "
        f"Lugol: {'X' if pres.get('Lugol') else '—'}     "
        f"Formol: {'X' if pres.get('Formol') else '—'}     "
        f"S/P: {'X' if pres.get('S/P') else '—'}", "Helvetica", 5.5)

    # Fila: Institución + Urgencia
    y -= rh
    rect(ML, y, dg_w, rh, white)
    txt(ML + 3, y + 1.2 * mm,
        f"INSTITUCIÓN: {cfg.get('institucion', '')}     "
        f"URGENCIA: {cfg.get('urgencia', 'Regular')}", "Helvetica", 5.5)
    rect(pr_x, y, pr_w, rh, white)

    # Fila: Campaña + Cuenca
    campana_label = cfg.get("campana_label") or datos.get("lugar", "")
    y -= rh
    rect(ML, y, dg_w, rh, white)
    txt(ML + 3, y + 1.2 * mm,
        f"CAMPAÑA: {campana_label}     CUENCA: {datos.get('cuenca', '')}",
        "Helvetica-Bold", 5.5)
    rect(pr_x, y, pr_w + pg_w, rh, white)

    # ══════════════════════════════════════════════════════════════════════
    # 3. TABLA DE DATOS
    # ══════════════════════════════════════════════════════════════════════

    y -= 2 * mm

    # Definición de columnas (nombre, ancho) — misma estructura que Excel
    params_campo_pdf = list(_get_parametros_campo()[:_TEMPLATE_FIELD_COUNT])
    n_lab = len(params_lab)
    n_field = len(params_campo_pdf)

    fixed_cols = [
        ("N°", 4.5 * mm),
        ("Código Lab.", 18 * mm),
        ("Punto de Muestreo / Código", 40 * mm),
        ("Fecha", 14 * mm),
        ("Hora", 9 * mm),
        ("Matriz", 7 * mm),
        ("UTM Este", 14 * mm),
        ("UTM Norte", 14 * mm),
        ("Alt.", 9 * mm),
        ("Zona", 8 * mm),
        ("V", 4 * mm),
        ("P", 4 * mm),
    ]
    fixed_w = sum(w for _, w in fixed_cols)

    lab_col_w = 3.8 * mm
    field_col_w = 8.5 * mm
    lab_total = lab_col_w * n_lab
    field_total = field_col_w * n_field

    obs_w = CW - fixed_w - lab_total - field_total
    obs_w = max(obs_w, 15 * mm)

    # ── Fila de secciones ─────────────────────────────────────────────────
    sec_h = 5 * mm
    y -= sec_h
    x = ML

    rect(x, y, fixed_w, sec_h, GREEN)
    txt(x + fixed_w / 2, y + 1.5 * mm, "DATOS DE MUESTRA", "Helvetica-Bold", 6, black, "c")
    x += fixed_w

    rect(x, y, lab_total, sec_h, GREEN)
    txt(x + lab_total / 2, y + 1.5 * mm, "PARÁMETROS DE LABORATORIO", "Helvetica-Bold", 6, black, "c")
    x += lab_total

    rect(x, y, field_total, sec_h, LIGHT_GREEN)
    txt(x + field_total / 2, y + 1.5 * mm, "PARÁMETROS DE CAMPO", "Helvetica-Bold", 6, black, "c")
    x += field_total

    rect(x, y, obs_w, sec_h, GREEN)
    txt(x + obs_w / 2, y + 1.5 * mm, "OBS.", "Helvetica-Bold", 6, black, "c")

    # ── Fila de nombres de columna (rotados para params) ──────────────────
    hdr_h = 20 * mm
    y -= hdr_h
    x = ML

    # Columnas fijas — texto horizontal
    for name, w in fixed_cols:
        rect(x, y, w, hdr_h, GREEN)
        words = name.split()
        n_lines = len(words)
        for li, word in enumerate(words):
            ly = y + hdr_h / 2 + (n_lines / 2 - li - 0.5) * 6.5
            txt(x + w / 2, ly, word, "Helvetica-Bold", 5, black, "c")
        x += w

    # Params lab — texto rotado 90°, fondo blanco
    for p in params_lab:
        rect(x, y, lab_col_w, hdr_h, white)
        txt_rot(x + lab_col_w / 2 + 1.5, y + 1, p["nombre"])
        x += lab_col_w

    # Params campo — texto rotado 90°, fondo verde claro
    for p in params_campo_pdf:
        rect(x, y, field_col_w, hdr_h, LIGHT_GREEN)
        txt_rot(x + field_col_w / 2 + 1.5, y + 1, p["nombre"])
        x += field_col_w

    # Observaciones
    rect(x, y, obs_w, hdr_h, GREEN)
    txt(x + obs_w / 2, y + hdr_h / 2, "Observaciones", "Helvetica-Bold", 5, black, "c")

    # ── Filas de datos ────────────────────────────────────────────────────
    drh = 6 * mm  # alto de fila de datos

    for idx, m in enumerate(muestras):
        y -= drh
        if y < 45 * mm:
            break  # no hay espacio para más filas + pie

        pt = m.get("puntos_muestreo") or {}
        insitu = m.get("insitu", {})
        bg = white if idx % 2 == 0 else GRAY_BG

        tipo_mapa = {
            "laguna": "ADL", "rio": "ADR", "canal": "ADR",
            "manantial": "AMA", "embalse": "ADL", "pozo": "ASUB",
        }
        matriz = tipo_mapa.get(pt.get("tipo", ""), "AN")

        fecha_raw = m.get("fecha_muestreo", "")
        try:
            fecha_dt = datetime.strptime(str(fecha_raw)[:10], "%Y-%m-%d")
            fecha_str = fecha_dt.strftime("%d/%m/%y")
        except (ValueError, TypeError):
            fecha_str = str(fecha_raw)[:10]

        # Valores de las columnas fijas
        vals_fixed = [
            str(idx + 1),
            m.get("codigo", "") or "",
            f"{pt.get('nombre', '')[:28]} /{pt.get('codigo', '')}",
            fecha_str,
            (m.get("hora_recoleccion", "") or "")[:5],
            matriz,
            str(pt.get("utm_este", "") or ""),
            str(pt.get("utm_norte", "") or ""),
            str(pt.get("altitud_msnm", "") or ""),
            pt.get("utm_zona", "19L") or "",
            "1",
            str(int(4.0 if "p091" in params_activos else 3.0)),
        ]

        x = ML
        for ci, (_, w) in enumerate(fixed_cols):
            rect(x, y, w, drh, bg)
            val = vals_fixed[ci]
            al = "l" if ci == 2 else "c"
            tx = x + 1.5 if al == "l" else x + w / 2
            txt(tx, y + 1.8 * mm, val[:int(w / 2.8)] if len(val) > int(w / 2.8) else val,
                "Helvetica", 5, black, al)
            x += w

        # Params lab — "x"
        for p in params_lab:
            rect(x, y, lab_col_w, drh, bg)
            if p["clave"] in params_activos:
                txt(x + lab_col_w / 2, y + 1.8 * mm, "x", "Helvetica", 5, black, "c")
            x += lab_col_w

        # Params campo — valores
        for p in params_campo_pdf:
            rect(x, y, field_col_w, drh, bg)
            val = insitu.get(p["clave"])
            if val is not None:
                txt(x + field_col_w / 2, y + 1.8 * mm,
                    str(val).replace(".", ","), "Helvetica", 5, black, "c")
            x += field_col_w

        # Observaciones (auto-incluir clima, nivel, temp. transporte)
        obs_pdf_parts = []
        if m.get("clima"):
            obs_pdf_parts.append(f"Clima: {m['clima']}")
        if m.get("nivel_agua"):
            obs_pdf_parts.append(f"Nivel: {m['nivel_agua']}")
        if m.get("temperatura_transporte") is not None:
            obs_pdf_parts.append(f"T: {m['temperatura_transporte']}°C")
        if m.get("observaciones_campo"):
            obs_pdf_parts.append(m["observaciones_campo"])
        obs_text = "; ".join(obs_pdf_parts)[:40]
        rect(x, y, obs_w, drh, bg)
        txt(x + 1.5, y + 1.8 * mm, obs_text, "Helvetica", 4.5, black)

    # Filas vacías para completar mínimo visual
    remaining = max(0, 11 - len(muestras))
    for i in range(remaining):
        y -= drh
        if y < 45 * mm:
            break
        bg = white if (len(muestras) + i) % 2 == 0 else GRAY_BG
        x = ML
        for _, w in fixed_cols:
            rect(x, y, w, drh, bg)
            x += w
        for _ in params_lab:
            rect(x, y, lab_col_w, drh, bg)
            x += lab_col_w
        for _ in params_campo_pdf:
            rect(x, y, field_col_w, drh, bg)
            x += field_col_w
        rect(x, y, obs_w, drh, bg)

    # ══════════════════════════════════════════════════════════════════════
    # 4. PIE DE PÁGINA
    # ══════════════════════════════════════════════════════════════════════

    y -= 3 * mm
    pie_h = 6 * mm  # alto de fila de pie

    # Encabezados de sección
    sec_muestreo_w = CW * 0.30
    sec_recepcion_w = CW * 0.30
    sec_equipos_w = CW * 0.40

    y -= pie_h
    rect(ML, y, sec_muestreo_w, pie_h, GREEN)
    txt(ML + 3, y + 1.8 * mm, "MUESTREO REALIZADO POR:", "Helvetica-Bold", 6)

    rx = ML + sec_muestreo_w
    rect(rx, y, sec_recepcion_w, pie_h, GREEN)
    txt(rx + 3, y + 1.8 * mm, "RECEPCIÓN MUESTRA:", "Helvetica-Bold", 6)

    ex = rx + sec_recepcion_w
    rect(ex, y, sec_equipos_w, pie_h, GREEN)
    txt(ex + 3, y + 1.8 * mm, "DESCRIPCIÓN DE EQUIPOS UTILIZADOS:", "Helvetica-Bold", 6)

    # Detalle muestreo
    det_h = 5 * mm
    muestreo = cfg.get("muestreo_por", "laboratorio")

    y -= det_h
    rect(ML, y, sec_muestreo_w, det_h, white)
    txt(ML + 3, y + 1.5 * mm,
        f"Personal laboratorio: ({'X' if muestreo == 'laboratorio' else ' '})   "
        f"Otro: ({'X' if muestreo != 'laboratorio' else ' '})", "Helvetica", 5)

    rect(rx, y, sec_recepcion_w, det_h, white)
    txt(rx + 3, y + 1.5 * mm, f"Nombre: {cfg.get('nombre_receptor', '')}", "Helvetica", 5)

    equipos = cfg.get("equipos", EQUIPOS_DEFAULT)
    rect(ex, y, sec_equipos_w, det_h, white)
    if len(equipos) > 0:
        txt(ex + 3, y + 1.5 * mm,
            f"1. {equipos[0].get('codigo', '')} — {equipos[0].get('nombre', '')}", "Helvetica", 5)

    y -= det_h
    rect(ML, y, sec_muestreo_w, det_h, white)
    txt(ML + 3, y + 1.5 * mm, f"Nombre: {cfg.get('nombre_muestreador', '')}", "Helvetica", 5)

    rect(rx, y, sec_recepcion_w, det_h, white)
    txt(rx + 3, y + 1.5 * mm, "Fecha:", "Helvetica", 5)

    rect(ex, y, sec_equipos_w, det_h, white)
    if len(equipos) > 1:
        txt(ex + 3, y + 1.5 * mm,
            f"2. {equipos[1].get('codigo', '')} — {equipos[1].get('nombre', '')}", "Helvetica", 5)

    y -= det_h
    rect(ML, y, sec_muestreo_w, det_h, white)
    txt(ML + 3, y + 1.5 * mm, "Firma:", "Helvetica", 5)

    rect(rx, y, sec_recepcion_w, det_h, white)
    txt(rx + 3, y + 1.5 * mm, "Firma:", "Helvetica", 5)

    rect(ex, y, sec_equipos_w, det_h, white)

    # Supervisor
    y -= pie_h
    rect(ML, y, sec_muestreo_w, pie_h, GREEN)
    txt(ML + 3, y + 1.8 * mm,
        "COORDINADOR / SUPERVISOR:", "Helvetica-Bold", 6)

    rect(rx, y, sec_recepcion_w + sec_equipos_w, pie_h, white)
    txt(rx + 3, y + 1.8 * mm,
        f"Observaciones: {cfg.get('observaciones_generales', '')}", "Helvetica", 5)

    y -= det_h
    rect(ML, y, sec_muestreo_w, det_h, white)
    txt(ML + 3, y + 1.5 * mm, f"Nombre: {cfg.get('nombre_supervisor', '')}", "Helvetica", 5)

    rect(rx, y, sec_recepcion_w + sec_equipos_w, det_h, white)
    txt(rx + 3, y + 1.5 * mm,
        f"Generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC — LVCA / AUTODEMA",
        "Helvetica", 5, HexColor("#888888"))

    # ── Condiciones de la muestra ─────────────────────────────────────────
    y -= pie_h
    cond = cfg.get("condiciones", {})
    rect(ML, y, CW, pie_h, HexColor("#FFF9E6"))
    cond_items = [
        ("Refrigerado", cond.get("refrigerado")),
        ("Icepack", cond.get("icepack")),
        ("Temp. ambiente", cond.get("temp_ambiente")),
        ("Congelado", cond.get("congelado")),
        ("Caja conservadora", cond.get("caja_conservadora")),
        ("Hielo potable", cond.get("hielo_potable")),
    ]
    cond_str = "CONDICIONES DE LA MUESTRA:   " + "    ".join(
        f"{name}: ({'X' if val else ' '})" for name, val in cond_items
    )
    txt(ML + 3, y + 1.8 * mm, cond_str, "Helvetica-Bold", 5.5)

    # ══════════════════════════════════════════════════════════════════════
    c.save()
    return output.getvalue()
