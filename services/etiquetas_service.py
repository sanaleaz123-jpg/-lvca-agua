"""
services/etiquetas_service.py
Genera un archivo Word con etiquetas de frascos de muestreo para una campaña.

Parte de la plantilla `ETIQUETAS_EnBlanco_10puntos.docx` (5 ensayos
predefinidos con su preservante correspondiente) y produce un .docx con
1 punto por hoja: hasta 5 etiquetas apiladas en la columna izquierda,
una por cada ensayo seleccionado, con los datos del punto pre-rellenos.

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
from docx.oxml.ns import qn

from database.client import get_admin_client


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
    campana_id:           str,
    ensayos_seleccionados: list[str],
    responsables:         list[str],
) -> bytes:
    """
    Genera el .docx con etiquetas para todos los puntos de la campaña.

    Args:
        campana_id: UUID de la campaña.
        ensayos_seleccionados: nombres de ensayos a incluir (subset de
            `ENSAYOS_PLANTILLA`).
        responsables: nombres de los responsables de campo. Se concatenan
            con coma para el campo "MUESTREADO POR".

    Returns:
        Bytes del archivo .docx listo para descarga.

    Raises:
        FileNotFoundError: si la plantilla no existe.
        ValueError: si la campaña no tiene puntos o no hay ensayos.
    """
    if not ensayos_seleccionados:
        raise ValueError("Debes seleccionar al menos un ensayo.")
    if not os.path.exists(_TEMPLATE_PATH):
        raise FileNotFoundError(
            f"Plantilla de etiquetas no encontrada: {_TEMPLATE_PATH}"
        )

    campana, puntos = _cargar_datos(campana_id)
    if not puntos:
        raise ValueError("La campaña no tiene puntos de muestreo vinculados.")

    fecha_str   = _formatear_fecha_mes_anio(campana.get("fecha_inicio"))
    prof_str    = "0.3 m" if (campana.get("frecuencia") or "").lower() == "mensual" else ""
    resp_str    = ", ".join(r.strip() for r in responsables if r and r.strip()) or _MUESTREADO_POR_DEFAULT

    # Mantener orden de la plantilla (no el orden de selección del usuario).
    ensayos_filtrados = [e for e in ENSAYOS_PLANTILLA if e["nombre"] in ensayos_seleccionados]

    doc = Document(_TEMPLATE_PATH)
    etiqueta_templates = _extraer_etiqueta_templates(doc)
    _limpiar_body(doc)

    body = doc.element.body
    sectPr = body.find(qn("w:sectPr"))

    for i, pt in enumerate(puntos):
        estacion = pt.get("nombre", "") or ""
        codigo   = pt.get("codigo", "") or ""
        matriz   = _TIPO_A_MATRIZ.get((pt.get("tipo") or "").lower(), "AN")

        valores = {
            "ESTACION":        estacion,
            "CODIGO":          codigo,
            "FECHA":           fecha_str,
            "HORA":            "",
            "MATRIZ":          matriz,
            "PROF":            prof_str,
            "MUESTREADO_POR":  resp_str,
        }

        if i > 0:
            # Salto de página entre puntos.
            page_break = _crear_parrafo_salto_pagina()
            if sectPr is not None:
                sectPr.addprevious(page_break)
            else:
                body.append(page_break)

        for ensayo in ensayos_filtrados:
            tbl_template = etiqueta_templates.get(ensayo["nombre"])
            if tbl_template is None:
                continue
            etiqueta = deepcopy(tbl_template)
            _rellenar_etiqueta(etiqueta, valores)

            if sectPr is not None:
                sectPr.addprevious(etiqueta)
            else:
                body.append(etiqueta)

            # Pequeño párrafo separador para evitar tablas adyacentes
            # (Word renderiza tablas pegadas si no hay <w:p> entre ellas).
            sep = _crear_parrafo_separador()
            if sectPr is not None:
                sectPr.addprevious(sep)
            else:
                body.append(sep)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ─────────────────────────────────────────────────────────────────────────────

def _cargar_datos(campana_id: str) -> tuple[dict, list[dict]]:
    """Trae la campaña y sus puntos ordenados por código."""
    db = get_admin_client()

    camp = (
        db.table("campanas")
        .select("codigo, nombre, fecha_inicio, frecuencia")
        .eq("id", campana_id)
        .single()
        .execute()
        .data
        or {}
    )

    pts_res = (
        db.table("campana_puntos")
        .select("puntos_muestreo(codigo, nombre, tipo)")
        .eq("campana_id", campana_id)
        .execute()
    )
    puntos = [r["puntos_muestreo"] for r in (pts_res.data or []) if r.get("puntos_muestreo")]
    puntos = sorted(puntos, key=lambda p: p.get("codigo") or "")
    return camp, puntos


def _formatear_fecha_mes_anio(fecha_iso: str | None) -> str:
    """
    Devuelve "___/MM/AAAA" para que el día se llene a mano en campo.
    Si la fecha no es interpretable, retorna cadena vacía.
    """
    if not fecha_iso:
        return ""
    try:
        if isinstance(fecha_iso, (datetime, date)):
            f = fecha_iso
        else:
            f = datetime.fromisoformat(str(fecha_iso)[:10])
        return f"___/{f.month:02d}/{f.year}"
    except (ValueError, TypeError):
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Manipulación de la plantilla
# ─────────────────────────────────────────────────────────────────────────────

def _extraer_etiqueta_templates(doc) -> dict[str, object]:
    """
    Recorre las tablas externas de la plantilla y captura UNA etiqueta
    (elemento <w:tbl> outer del recuadro) por cada uno de los 5 ensayos.
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


def _limpiar_body(doc) -> None:
    """Quita todas las tablas y párrafos del body, preservando <w:sectPr>."""
    body = doc.element.body
    sectPr = body.find(qn("w:sectPr"))
    for child in list(body):
        if child is sectPr:
            continue
        body.remove(child)


def _crear_parrafo_salto_pagina():
    """Párrafo con page break para separar puntos."""
    from docx.oxml import OxmlElement
    p = OxmlElement("w:p")
    r = OxmlElement("w:r")
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    r.append(br)
    p.append(r)
    return p


def _crear_parrafo_separador():
    """Párrafo vacío con poca altura para separar dos etiquetas seguidas."""
    from docx.oxml import OxmlElement
    p = OxmlElement("w:p")
    pPr = OxmlElement("w:pPr")
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:before"), "0")
    spacing.set(qn("w:after"), "0")
    spacing.set(qn("w:line"), "60")
    spacing.set(qn("w:lineRule"), "exact")
    pPr.append(spacing)
    p.append(pPr)
    return p


def _rellenar_etiqueta(etiqueta_outer, valores: dict[str, str]) -> None:
    """
    Rellena los campos de una etiqueta clonada.

    La estructura real de la plantilla es:
        Tabla de campos (8 filas × 4 columnas, anidada dentro de la etiqueta):
          Fila 0 → logo (gridSpan=4)
          Fila 1 → ESTACIÓN | : | (valor) | PRESERVANTE+opciones (vMerge)
          Fila 2 → CÓDIGO   | : | (valor) | (vMerge continúa)
          Fila 3 → FECHA    | : | (tabla anidada 1×4: FECHA-val | HORA | : | HORA-val) | (vMerge)
          Fila 4 → MATRIZ   | : | (tabla anidada 1×4: MATRIZ-val | PROF. | : | PROF-val) | (vMerge)
          Fila 5 → ENSAYO   | : | (valor pre-impreso, NO tocar) | (vMerge)
          Fila 6 → MUESTREADO POR: (gridSpan=4, solo etiqueta)
          Fila 7 → valor pre-impreso de muestreado por (gridSpan=4)

    Campos esperados en `valores`:
        ESTACION, CODIGO, FECHA, HORA, MATRIZ, PROF, MUESTREADO_POR
    """
    content = _encontrar_tabla_campos(etiqueta_outer)
    if content is None:
        return

    rows = content.findall(qn("w:tr"))
    if len(rows) < 8:
        return

    # Fila 1: ESTACIÓN
    _setear_paragrafo_de_celda(rows[1], col_idx=2, texto=valores.get("ESTACION", ""))
    # Fila 2: CÓDIGO
    _setear_paragrafo_de_celda(rows[2], col_idx=2, texto=valores.get("CODIGO", ""))
    # Fila 3: FECHA + HORA (tabla anidada en celda 2, cells [0] y [3])
    _setear_par_anidado(
        rows[3], col_idx=2,
        izq=valores.get("FECHA", ""),
        der=valores.get("HORA", ""),
    )
    # Fila 4: MATRIZ + PROF.
    _setear_par_anidado(
        rows[4], col_idx=2,
        izq=valores.get("MATRIZ", ""),
        der=valores.get("PROF", ""),
    )
    # Fila 5 (ENSAYO): no tocar — viene pre-impreso por etiqueta.
    # Fila 6 (label MUESTREADO POR): no tocar.
    # Fila 7: valor MUESTREADO POR (gridSpan=4, single cell).
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
    # findall solo en hijos directos
    parrafos = [child for child in tc if child.tag == qn("w:p")]
    if not parrafos:
        return
    p = parrafos[0]
    # Encontrar primer <w:r>/<w:t>
    ts = list(p.iter(qn("w:t")))
    if ts:
        ts[0].text = texto
        ts[0].set(qn("xml:space"), "preserve")
        for t in ts[1:]:
            t.text = ""
        return
    # Si no hay <w:t>, agregar un run con formato por defecto.
    from docx.oxml import OxmlElement
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = texto
    t.set(qn("xml:space"), "preserve")
    r.append(t)
    p.append(r)
