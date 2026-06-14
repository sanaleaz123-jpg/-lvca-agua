"""
services/etiquetas_service.py
Genera un archivo Word con etiquetas de frascos de muestreo para una campaña.

Parte de la plantilla `ETIQUETAS_EnBlanco_10puntos.docx` (5 ensayos
predefinidos con su preservante correspondiente) y produce un .docx con
una hoja por cada combinación (punto, profundidad), distribuyendo las N
etiquetas de ensayo en una grilla de 2 columnas (3 izquierda + 2 derecha
para 5 ensayos) que reutiliza la outer table 3×3 de la plantilla.

Modos de muestreo:
    "superficial" → 1 hoja por punto, profundidad fija "0.3 m",
                    código = código del punto.
    "columna"     → 1 hoja por cada profundidad seleccionada (S/M/F)
                    de cada punto. Profundidad en blanco; código del
                    punto con sufijo "(S)", "(M)" o "(F)".

Funciones públicas:
    get_ensayos_disponibles()      → lista de los 5 ensayos de la plantilla
    generar_etiquetas_campana(...) → bytes del .docx generado
"""

from __future__ import annotations

import os
from copy import deepcopy
from datetime import datetime, date
from io import BytesIO

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from database.client import get_db


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

# 5 ensayos fijos de la plantilla, con el preservante asociado (no editable —
# coinciden con las cajas pre-impresas en `ETIQUETAS_EnBlanco_10puntos.docx`).
ENSAYOS_PLANTILLA: list[dict] = [
    {"nombre": "Hierro y manganeso disuelto", "preservante": "HNO3"},
    {"nombre": "Fitoplancton",                "preservante": "LUGOL"},
    {"nombre": "Clorofila A",                 "preservante": "S/P"},
    {"nombre": "Color",                       "preservante": "S/P"},
    {"nombre": "Fisicoquímicos y nutrientes", "preservante": "S/P"},
]

# Modos válidos de muestreo (parámetro `tipo_muestreo`).
MODO_SUPERFICIAL = "superficial"
MODO_COLUMNA     = "columna"

# Orden canónico de profundidades para muestreo en columna.
PROFUNDIDADES_COLUMNA = ["S", "M", "F"]

# Mapeo tipo de punto → código de matriz (mismo criterio que
# cadena_custodia_service.py para mantener consistencia con la cadena oficial).
_TIPO_A_MATRIZ: dict[str, str] = {
    "laguna":    "ADL",
    "rio":       "ADR",
    "canal":     "ADR",
    "manantial": "AMA",
    "embalse":   "ADL",
    "pozo":      "ASUB",
}

# Texto pre-impreso de "MUESTREADO POR" en la plantilla — a reemplazar.
_MUESTREADO_POR_DEFAULT = "A. Llacho, A. Vilcapaza"

# Posiciones (fila, col) dentro de la outer table 3×3 donde se ubican las
# etiquetas (col 1 es separadora). Orden de lectura: izquierda→derecha,
# arriba→abajo. Hay 6 posiciones disponibles; usamos hasta 5.
_POSICIONES_ETIQUETAS = [(0, 0), (0, 2), (1, 0), (1, 2), (2, 0), (2, 2)]

# Ruta a la plantilla (raíz del proyecto LVCA).
_TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "ETIQUETAS_EnBlanco_10puntos.docx"
)


# ─────────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────────

def get_ensayos_disponibles() -> list[str]:
    """Nombres de los 5 ensayos disponibles en la plantilla, en orden."""
    return [e["nombre"] for e in ENSAYOS_PLANTILLA]


def generar_etiquetas_campana(
    campana_id:            str,
    ensayos_seleccionados: list[str],
    responsables:          list[str],
    tipo_muestreo:         str = MODO_SUPERFICIAL,
    profundidades_por_punto: dict[str, list[str]] | None = None,
) -> bytes:
    """
    Genera el .docx con etiquetas para todos los puntos de la campaña.

    Args:
        campana_id: UUID de la campaña.
        ensayos_seleccionados: nombres de ensayos a incluir (subset de
            `ENSAYOS_PLANTILLA`).
        responsables: nombres de los responsables de campo. Se concatenan
            con coma para el campo "MUESTREADO POR".
        tipo_muestreo: "superficial" (PROF=0.3 m, 1 hoja por punto)
            o "columna" (PROF en blanco, 1 hoja por cada profundidad
            seleccionada de cada punto, con sufijo (S)/(M)/(F) en CÓDIGO).
        profundidades_por_punto: requerido si tipo_muestreo == "columna".
            Diccionario {punto_id: ["S","M","F",...]} con las profundidades
            a generar para cada punto. Puntos no incluidos o con lista vacía
            son omitidos.

    Returns:
        Bytes del archivo .docx listo para descarga.

    Raises:
        FileNotFoundError: si la plantilla no existe.
        ValueError: si la campaña no tiene puntos, no hay ensayos, o el
            modo "columna" no produce ningún slot (ninguna profundidad
            seleccionada en ningún punto).
    """
    if not ensayos_seleccionados:
        raise ValueError("Debes seleccionar al menos un ensayo.")
    if tipo_muestreo not in (MODO_SUPERFICIAL, MODO_COLUMNA):
        raise ValueError(f"tipo_muestreo inválido: {tipo_muestreo!r}")
    if not os.path.exists(_TEMPLATE_PATH):
        raise FileNotFoundError(
            f"Plantilla de etiquetas no encontrada: {_TEMPLATE_PATH}"
        )

    campana, puntos = _cargar_datos(campana_id)
    if not puntos:
        raise ValueError("La campaña no tiene puntos de muestreo vinculados.")

    fecha_str = _formatear_fecha(
        campana.get("fecha_inicio"), campana.get("fecha_fin")
    )
    resp_str  = (
        ", ".join(r.strip() for r in responsables if r and r.strip())
        or _MUESTREADO_POR_DEFAULT
    )

    # Mantener orden de la plantilla (no el orden de selección del usuario).
    ensayos_filtrados = [
        e for e in ENSAYOS_PLANTILLA if e["nombre"] in ensayos_seleccionados
    ]

    slots = _construir_slots(puntos, tipo_muestreo, profundidades_por_punto or {})
    if not slots:
        raise ValueError(
            "No hay profundidades seleccionadas para ningún punto. "
            "Marca al menos una profundidad (S, M o F) en algún punto."
        )

    doc = Document(_TEMPLATE_PATH)
    etiqueta_templates = _extraer_etiqueta_templates(doc)
    outer_template     = _extraer_outer_template(doc)
    _limpiar_body(doc)

    body   = doc.element.body
    sectPr = body.find(qn("w:sectPr"))

    for i, slot in enumerate(slots):
        valores = {
            "ESTACION":       slot["estacion"],
            "CODIGO":         slot["codigo_etiqueta"],
            "FECHA":          fecha_str,
            "HORA":           "",
            "MATRIZ":         slot["matriz"],
            "PROF":           slot["prof_valor"],
            "MUESTREADO_POR": resp_str,
        }

        if i > 0:
            page_break = _crear_parrafo_salto_pagina()
            _anexar(body, sectPr, page_break)

        hoja = _construir_hoja(
            outer_template, etiqueta_templates, ensayos_filtrados, valores
        )
        _anexar(body, sectPr, hoja)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ─────────────────────────────────────────────────────────────────────────────

def _cargar_datos(campana_id: str) -> tuple[dict, list[dict]]:
    """Trae la campaña y sus puntos ordenados por código."""
    db = get_db()

    camp = (
        db.table("campanas")
        .select("codigo, nombre, fecha_inicio, fecha_fin, frecuencia")
        .eq("id", campana_id)
        .single()
        .execute()
        .data
        or {}
    )

    pts_res = (
        db.table("campana_puntos")
        .select("puntos_muestreo(id, codigo, nombre, tipo)")
        .eq("campana_id", campana_id)
        .execute()
    )
    puntos = [
        r["puntos_muestreo"] for r in (pts_res.data or [])
        if r.get("puntos_muestreo")
    ]
    puntos = sorted(puntos, key=lambda p: p.get("codigo") or "")
    return camp, puntos


def _formatear_fecha(fecha_inicio, fecha_fin) -> str:
    """
    Devuelve la fecha a imprimir en la etiqueta según la duración:

      • Si la campaña dura un solo día (fecha_inicio == fecha_fin) →
        "DD/MM/AAAA" — la fecha está totalmente determinada.
      • Si dura varios días (o fecha_fin desconocida) →
        "___/MM/AAAA" — el día se llena a mano en campo.

    Devuelve cadena vacía si fecha_inicio no es interpretable.
    """
    f_ini = _to_date(fecha_inicio)
    if f_ini is None:
        return ""

    f_fin = _to_date(fecha_fin)
    if f_fin is not None and f_fin == f_ini:
        return f"{f_ini.day:02d}/{f_ini.month:02d}/{f_ini.year}"
    return f"___/{f_ini.month:02d}/{f_ini.year}"


def _to_date(valor):
    """Convierte un str ISO / date / datetime a date. None si no se puede."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return datetime.fromisoformat(str(valor)[:10]).date()
    except (ValueError, TypeError):
        return None


def _construir_slots(
    puntos:                  list[dict],
    tipo_muestreo:           str,
    profundidades_por_punto: dict[str, list[str]],
) -> list[dict]:
    """
    Expande los puntos en "slots" de generación. Cada slot = 1 hoja.

    Superficial → un slot por punto, código sin sufijo, PROF=0.3 m.
    Columna    → un slot por cada profundidad seleccionada de cada punto,
                 código con sufijo "(S)|(M)|(F)", PROF en blanco.
    """
    slots: list[dict] = []
    for pt in puntos:
        estacion = pt.get("nombre", "") or ""
        codigo   = pt.get("codigo", "") or ""
        matriz   = _TIPO_A_MATRIZ.get((pt.get("tipo") or "").lower(), "AN")

        if tipo_muestreo == MODO_SUPERFICIAL:
            slots.append({
                "estacion":         estacion,
                "codigo_etiqueta":  codigo,
                "matriz":           matriz,
                "prof_valor":       "0.3 m",
            })
        else:  # columna
            seleccionadas = profundidades_por_punto.get(pt.get("id"), [])
            for prof in PROFUNDIDADES_COLUMNA:
                if prof in seleccionadas:
                    slots.append({
                        "estacion":        estacion,
                        "codigo_etiqueta": f"{codigo} ({prof})",
                        "matriz":          matriz,
                        "prof_valor":      "",
                    })
    return slots


# ─────────────────────────────────────────────────────────────────────────────
# Manipulación de la plantilla
# ─────────────────────────────────────────────────────────────────────────────

def _extraer_etiqueta_templates(doc) -> dict[str, object]:
    """
    Captura UNA etiqueta (elemento <w:tbl> outer del recuadro) por cada uno
    de los 5 ensayos, recorriendo las tablas externas de la plantilla.
    Retorna {nombre_ensayo → elemento XML clonable}.
    """
    nombres_esperados = {e["nombre"] for e in ENSAYOS_PLANTILLA}
    capturados: dict[str, object] = {}

    for outer_table in doc.tables:
        for row in outer_table.rows:
            for cell in row.cells:
                if not cell.tables:
                    continue
                etiqueta_outer = cell.tables[0]   # 1x1 wrapper con borde
                text_completo = etiqueta_outer._element.xml
                for nombre in nombres_esperados:
                    if nombre in capturados:
                        continue
                    if nombre in text_completo:
                        capturados[nombre] = etiqueta_outer._element
                        break
        if len(capturados) >= len(nombres_esperados):
            break

    return capturados


def _extraer_outer_template(doc):
    """
    Devuelve la primera outer table 3×3 de la plantilla (estructura de hoja
    con 2 columnas de etiquetas + columna separadora central).
    """
    return doc.tables[0]._element


def _limpiar_body(doc) -> None:
    """Quita todas las tablas y párrafos del body, preservando <w:sectPr>."""
    body = doc.element.body
    sectPr = body.find(qn("w:sectPr"))
    for child in list(body):
        if child is sectPr:
            continue
        body.remove(child)


def _anexar(body, sectPr, elemento) -> None:
    """Inserta `elemento` antes de <w:sectPr> o al final si no existe."""
    if sectPr is not None:
        sectPr.addprevious(elemento)
    else:
        body.append(elemento)


def _crear_parrafo_salto_pagina():
    """Párrafo con page break para separar slots (hojas)."""
    p = OxmlElement("w:p")
    r = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    r.append(br)
    p.append(r)
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Construcción de la hoja
# ─────────────────────────────────────────────────────────────────────────────

def _construir_hoja(outer_template, etiqueta_templates, ensayos_a_incluir, valores):
    """
    Crea una outer table 3×3 (copia del template) y coloca las N etiquetas
    en las posiciones de lectura (izq→der, arriba→abajo). Las posiciones
    sobrantes quedan vacías.
    """
    hoja = deepcopy(outer_template)
    rows = hoja.findall(qn("w:tr"))

    for i, (ri, ci) in enumerate(_POSICIONES_ETIQUETAS):
        if ri >= len(rows):
            continue
        celdas_fila = rows[ri].findall(qn("w:tc"))
        if ci >= len(celdas_fila):
            continue
        celda = celdas_fila[ci]

        if i < len(ensayos_a_incluir):
            ensayo = ensayos_a_incluir[i]
            tbl_template = etiqueta_templates.get(ensayo["nombre"])
            if tbl_template is None:
                _vaciar_celda(celda)
                continue
            etiq = deepcopy(tbl_template)
            _rellenar_etiqueta(etiq, valores)
            _reemplazar_contenido_celda(celda, etiq)
        else:
            _vaciar_celda(celda)

    return hoja


def _reemplazar_contenido_celda(celda, etiqueta_tbl) -> None:
    """Quita tablas/párrafos de la celda (conserva <w:tcPr>) y mete la etiqueta."""
    tcPr = qn("w:tcPr")
    for child in list(celda):
        if child.tag != tcPr:
            celda.remove(child)
    celda.append(etiqueta_tbl)
    # Word requiere un párrafo después de una tabla anidada en celda.
    celda.append(OxmlElement("w:p"))


def _vaciar_celda(celda) -> None:
    """Deja la celda con solo <w:tcPr> + un párrafo vacío."""
    tcPr = qn("w:tcPr")
    for child in list(celda):
        if child.tag != tcPr:
            celda.remove(child)
    celda.append(OxmlElement("w:p"))


# ─────────────────────────────────────────────────────────────────────────────
# Llenado de campos dentro de una etiqueta
# ─────────────────────────────────────────────────────────────────────────────

def _rellenar_etiqueta(etiqueta_outer, valores: dict[str, str]) -> None:
    """
    Rellena los campos de una etiqueta clonada.

    Estructura real de la tabla de campos (8 filas × 4 columnas, anidada):
      Fila 0 → logo (gridSpan=4)
      Fila 1 → ESTACIÓN | : | (valor) | PRESERVANTE+opciones (vMerge)
      Fila 2 → CÓDIGO   | : | (valor) | (vMerge)
      Fila 3 → FECHA    | : | (tabla 1×4: FECHA-val | HORA | : | HORA-val)
      Fila 4 → MATRIZ   | : | (tabla 1×4: MATRIZ-val | PROF. | : | PROF-val)
      Fila 5 → ENSAYO   | : | (valor pre-impreso, NO tocar)
      Fila 6 → MUESTREADO POR: (gridSpan=4, solo etiqueta)
      Fila 7 → valor MUESTREADO POR (gridSpan=4)

    Campos esperados en `valores`:
        ESTACION, CODIGO, FECHA, HORA, MATRIZ, PROF, MUESTREADO_POR
    """
    content = _encontrar_tabla_campos(etiqueta_outer)
    if content is None:
        return

    rows = content.findall(qn("w:tr"))
    if len(rows) < 8:
        return

    _setear_paragrafo_de_celda(rows[1], col_idx=2, texto=valores.get("ESTACION", ""))
    _setear_paragrafo_de_celda(rows[2], col_idx=2, texto=valores.get("CODIGO", ""))
    _setear_par_anidado(
        rows[3], col_idx=2,
        izq=valores.get("FECHA", ""),
        der=valores.get("HORA", ""),
    )
    _setear_par_anidado(
        rows[4], col_idx=2,
        izq=valores.get("MATRIZ", ""),
        der=valores.get("PROF", ""),
    )
    # Fila 5 (ENSAYO): pre-impreso por etiqueta — no tocar.
    # Fila 6 (label MUESTREADO POR): no tocar.
    _setear_paragrafo_de_celda(rows[7], col_idx=0, texto=valores.get("MUESTREADO_POR", ""))


def _encontrar_tabla_campos(etiqueta_outer):
    """Devuelve el <w:tbl> de 8 filas con los campos (None si no existe)."""
    for tbl in etiqueta_outer.iter(qn("w:tbl")):
        if len(tbl.findall(qn("w:tr"))) == 8:
            return tbl
    return None


def _setear_paragrafo_de_celda(tr, col_idx: int, texto: str) -> None:
    """
    Pone `texto` en el primer <w:r>/<w:t> del primer <w:p> directo de la
    celda en la posición indicada. No toca tablas anidadas ni párrafos
    adicionales.
    """
    tcs = tr.findall(qn("w:tc"))
    if len(tcs) <= col_idx:
        return
    _set_paragrafo_directo(tcs[col_idx], texto)


def _setear_par_anidado(tr, col_idx: int, izq: str, der: str) -> None:
    """
    Para las filas FECHA y MATRIZ: la celda en `col_idx` contiene una
    tabla anidada 1×4 cuyas celdas son [valor_izq, label_der, ':', valor_der].
    Coloca `izq` en la celda 0 y `der` en la celda 3 (preserva labels).
    """
    tcs = tr.findall(qn("w:tc"))
    if len(tcs) <= col_idx:
        return
    contenedor = tcs[col_idx]
    tbl_anidada = contenedor.find(qn("w:tbl"))
    if tbl_anidada is None:
        return
    fila_anidada = tbl_anidada.find(qn("w:tr"))
    if fila_anidada is None:
        return
    sub_celdas = fila_anidada.findall(qn("w:tc"))
    if len(sub_celdas) >= 1:
        _set_paragrafo_directo(sub_celdas[0], izq)
    if len(sub_celdas) >= 4:
        _set_paragrafo_directo(sub_celdas[3], der)


def _set_paragrafo_directo(tc, texto: str) -> None:
    """
    Modifica el primer <w:p> directo del <w:tc> (ignora tablas anidadas).
    Pone `texto` en el primer <w:r>/<w:t>. Si no hay <w:t>, crea uno.
    """
    parrafos = [child for child in tc if child.tag == qn("w:p")]
    if not parrafos:
        return
    p = parrafos[0]
    ts = list(p.iter(qn("w:t")))
    if ts:
        ts[0].text = texto
        ts[0].set(qn("xml:space"), "preserve")
        for t in ts[1:]:
            t.text = ""
        return
    # Sin <w:t>: crear un run con texto.
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = texto
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    p.append(r)
