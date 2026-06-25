"""
services/taxonomia_fitoplancton_service.py
Catálogo de taxonomía de fitoplancton (tabla ``taxonomia_fitoplancton``),
gestionable desde pages/11_Catalogo_Fitoplancton.py.

Antes la taxonomía era una constante en código
(``services/fitoplancton_service.TAXONOMIA_FITOPLANCTON``). Ahora vive en BD con
la jerarquía completa División / Clase / Orden / Familia que el Reporte de Ensayo
de fitoplancton necesita.

Funciones públicas:
    get_taxonomia()                  → {division: [especie_dict, ...]} (cacheado)
    get_especies_planas(...)         → filas para la UI del catálogo
    verificar_clasificacion(nombre)  → consulta AlgaeBase (clave) o GBIF (libre)
    crear_especie(...)               → alta con jerarquía verificada
    actualizar_especie(...)          → edición
    desactivar_especie(id)           → baja lógica
    existe_especie(nombre)           → bool

Compatibilidad: ``get_taxonomia`` devuelve EXACTAMENTE el mismo shape que la
constante original (cada especie es un dict con
``nombre, unidad, celulas_por_unidad, volumen_celula_um3``) más los campos de
jerarquía ``clase, orden, familia``. Así los consumidores existentes
(fitoplancton_service, reporte_hidrobiologico_service, fitoplancton_form) siguen
funcionando sin cambios de contrato.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Optional

from database.client import get_db
from services.cache import cached, invalidate_all
from services.logging_config import get_logger

logger = get_logger(__name__)

# Orden canónico de los filos (para presentar el catálogo y el reporte siempre
# en el mismo orden, coincidiendo con el de la constante histórica).
ORDEN_FILOS: list[str] = [
    "Cyanobacteria",
    "Bacillariophyta",
    "Chlorophyta",
    "Ochrophyta",
    "Charophyta",
    "Euglenophyta",
    "Dinophyta",
    "Cryptophyta",
]

_TABLA = "taxonomia_fitoplancton"
_HTTP_TIMEOUT = 10  # s


# ─────────────────────────────────────────────────────────────────────────────
# Lectura (cacheada) — devuelve el shape compatible con la constante histórica
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=600, grupo="referencia")
def get_taxonomia() -> dict[str, list[dict]]:
    """
    Devuelve ``{division: [ {nombre, unidad, celulas_por_unidad,
    volumen_celula_um3, clase, orden, familia}, ... ]}`` leyendo de BD.

    Si la tabla no existe (migración 023 no aplicada) o está vacía, cae a la
    constante ``TAXONOMIA_FITOPLANCTON`` para no romper la app.
    """
    try:
        db = get_db()
        res = (
            db.table(_TABLA)
            .select(
                "division, clase, orden, familia, especie, unidad, "
                "celulas_por_unidad, volumen_celula_um3, orden_visual"
            )
            .eq("activo", True)
            .order("division")
            .order("orden_visual")
            .order("especie")
            .execute()
        )
        filas = res.data or []
    except Exception:
        filas = []

    if not filas:
        return _taxonomia_constante()

    agrupado: dict[str, list[dict]] = {}
    for f in filas:
        division = f.get("division") or "Sin clasificar"
        agrupado.setdefault(division, []).append({
            "nombre":             f.get("especie"),
            "unidad":             f.get("unidad") or "celula",
            "celulas_por_unidad": int(f.get("celulas_por_unidad") or 1),
            "volumen_celula_um3": float(f.get("volumen_celula_um3") or 0),
            "clase":              f.get("clase"),
            "orden":              f.get("orden"),
            "familia":            f.get("familia"),
        })

    # Reordenar por el orden canónico de filos; los filos extra van al final.
    ordenado: dict[str, list[dict]] = {}
    for filo in ORDEN_FILOS:
        if filo in agrupado:
            ordenado[filo] = agrupado.pop(filo)
    ordenado.update(agrupado)
    return ordenado


def _taxonomia_constante() -> dict[str, list[dict]]:
    """Fallback: copia de la constante histórica (sin jerarquía intermedia)."""
    from services.fitoplancton_service import TAXONOMIA_FITOPLANCTON
    salida: dict[str, list[dict]] = {}
    for filo, especies in TAXONOMIA_FITOPLANCTON.items():
        salida[filo] = [
            {**e, "clase": None, "orden": None, "familia": None}
            for e in especies
        ]
    return salida


def get_especies_planas(incluir_inactivas: bool = False) -> list[dict]:
    """Lista plana de filas del catálogo (para la pantalla de gestión)."""
    db = get_db()
    q = db.table(_TABLA).select("*")
    if not incluir_inactivas:
        q = q.eq("activo", True)
    res = q.order("division").order("orden_visual").order("especie").execute()
    return res.data or []


def existe_especie(nombre: str) -> bool:
    """True si ya hay una especie con ese nombre exacto."""
    db = get_db()
    res = (
        db.table(_TABLA).select("id").eq("especie", (nombre or "").strip())
        .limit(1).execute()
    )
    return bool(res.data)


# ─────────────────────────────────────────────────────────────────────────────
# Verificación taxonómica — AlgaeBase (con clave) o GBIF (respaldo libre)
# ─────────────────────────────────────────────────────────────────────────────

def _genero_de(nombre: str) -> str:
    """
    Extrae el género del nombre para la consulta. 'Navicula sp.' → 'Navicula'.
    Para nombres no resolubles (terminaciones ND / familia), devuelve "".
    """
    tok = (nombre or "").strip().split()
    if not tok:
        return ""
    primero = tok[0]
    # Entradas tipo "Pseudanabaeenaceae ND", "Cianobacteria ND", "Orden ..." no
    # son géneros; el caller las dejará sin jerarquía automática.
    if primero.lower() in ("orden", "clase", "familia", "division", "división"):
        return ""
    return primero


def _http_get_json(url: str, headers: Optional[dict] = None) -> Optional[dict]:
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Consulta taxonómica falló (%s): %s", url, exc)
        return None


def _verificar_gbif(genero: str) -> Optional[dict]:
    """
    Usa la GBIF Species Match API (libre, sin clave). AlgaeBase es una de las
    fuentes del backbone de GBIF, por lo que la jerarquía es consistente.
    """
    url = (
        "https://api.gbif.org/v1/species/match?strict=false&name="
        + urllib.parse.quote(genero)
    )
    data = _http_get_json(url)
    if not data or data.get("matchType") in (None, "NONE"):
        return None
    return {
        "clase":      data.get("class"),
        "orden":      data.get("order"),
        "familia":    data.get("family"),
        "division":   data.get("phylum"),
        "gbif_key":   data.get("usageKey"),
        "algaebase_id": None,
        "fuente":     "gbif",
        "match":      data.get("scientificName"),
        "confianza":  data.get("confidence"),
    }


def _verificar_algaebase(genero: str, api_key: str) -> Optional[dict]:
    """
    Consulta la API de AlgaeBase (https://api.algaebase.org). Requiere clave
    (cabecera ``abapikey``). Defensivo: ante cualquier forma inesperada de la
    respuesta, devuelve None para que el caller caiga a GBIF.
    """
    url = (
        "https://api.algaebase.org/v1.3/genus?genus="
        + urllib.parse.quote(genero)
    )
    data = _http_get_json(url, headers={"abapikey": api_key, "Accept": "application/json"})
    if not data:
        return None
    # La API devuelve un contenedor con "result"/"_embedded" según versión.
    item = None
    if isinstance(data, dict):
        res = data.get("result") or data.get("_embedded", {}).get("genus")
        if isinstance(res, list) and res:
            item = res[0]
        elif isinstance(res, dict):
            item = res
        else:
            item = data
    if not isinstance(item, dict):
        return None
    return {
        "clase":      item.get("dwc:class") or item.get("class"),
        "orden":      item.get("dwc:order") or item.get("order"),
        "familia":    item.get("dwc:family") or item.get("family"),
        "division":   item.get("dwc:phylum") or item.get("phylum"),
        "gbif_key":   None,
        "algaebase_id": str(item.get("dwc:scientificNameID") or item.get("id") or "") or None,
        "fuente":     "algaebase",
        "match":      item.get("dwc:scientificName") or item.get("genus") or genero,
        "confianza":  None,
    }


def verificar_clasificacion(nombre: str) -> Optional[dict]:
    """
    Verifica la clasificación de un taxón. Primero AlgaeBase (si hay clave en
    ``config.settings.ALGAEBASE_API_KEY``), luego GBIF como respaldo libre.

    Devuelve ``{clase, orden, familia, division, gbif_key, algaebase_id,
    fuente, match, confianza}`` o None si no se pudo resolver (p. ej. entradas
    "ND" sin género). El campo ``division`` es informativo: el filo lo decide el
    usuario en la pantalla (GBIF puede usar otro nombre de phylum p. ej.
    Euglenozoa en vez de Euglenophyta).
    """
    genero = _genero_de(nombre)
    if not genero:
        return None

    try:
        from config.settings import ALGAEBASE_API_KEY
    except Exception:
        ALGAEBASE_API_KEY = ""

    if ALGAEBASE_API_KEY:
        ab = _verificar_algaebase(genero, ALGAEBASE_API_KEY)
        if ab and (ab.get("familia") or ab.get("orden")):
            return ab
    return _verificar_gbif(genero)


# ─────────────────────────────────────────────────────────────────────────────
# Escritura (CRUD)
# ─────────────────────────────────────────────────────────────────────────────

def crear_especie(
    division: str,
    especie: str,
    *,
    clase: Optional[str] = None,
    orden: Optional[str] = None,
    familia: Optional[str] = None,
    unidad: str = "celula",
    celulas_por_unidad: int = 1,
    volumen_celula_um3: float = 0,
    gbif_key: Optional[int] = None,
    algaebase_id: Optional[str] = None,
    fuente_verificacion: Optional[str] = None,
) -> dict:
    """Alta de una especie en el catálogo. Lanza si el nombre ya existe."""
    especie = (especie or "").strip()
    if not especie:
        raise ValueError("El nombre de la especie es obligatorio.")
    if not division:
        raise ValueError("La división (filo) es obligatoria.")
    if existe_especie(especie):
        raise ValueError(f"La especie «{especie}» ya está en el catálogo.")

    fila = {
        "division":            division,
        "clase":               clase,
        "orden":               orden,
        "familia":             familia,
        "especie":             especie,
        "unidad":              unidad,
        "celulas_por_unidad":  int(celulas_por_unidad),
        "volumen_celula_um3":  float(volumen_celula_um3),
        "gbif_key":            gbif_key,
        "algaebase_id":        algaebase_id,
        "fuente_verificacion": fuente_verificacion,
        "activo":              True,
    }
    db = get_db()
    res = db.table(_TABLA).insert(fila).execute()
    invalidate_all()  # taxonomía es dato de referencia
    return (res.data or [{}])[0]


def actualizar_especie(especie_id: str, cambios: dict) -> None:
    """Actualiza campos de una especie por id."""
    if not cambios:
        return
    permitido = {
        "division", "clase", "orden", "familia", "especie", "unidad",
        "celulas_por_unidad", "volumen_celula_um3", "gbif_key",
        "algaebase_id", "fuente_verificacion", "orden_visual", "activo",
    }
    payload = {k: v for k, v in cambios.items() if k in permitido}
    if not payload:
        return
    db = get_db()
    db.table(_TABLA).update(payload).eq("id", especie_id).execute()
    invalidate_all()


def desactivar_especie(especie_id: str) -> None:
    """Baja lógica (no se borra para preservar análisis históricos)."""
    db = get_db()
    db.table(_TABLA).update({"activo": False}).eq("id", especie_id).execute()
    invalidate_all()
