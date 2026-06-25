"""
database/seeds/seed_taxonomia_fitoplancton.py
Carga inicial de la tabla ``taxonomia_fitoplancton`` (migración 023).

Vuelca las ~70 especies de la constante histórica
``services.fitoplancton_service.TAXONOMIA_FITOPLANCTON`` (que aporta filo +
unidad + células/unidad + biovolumen) y les añade la jerarquía
Clase / Orden / Familia desde un mapa curado alineado con AlgaeBase.

Si hay conexión a internet, intenta CONFIRMAR/COMPLETAR cada género contra GBIF
(backbone que incluye AlgaeBase) y guarda la ``gbif_key`` para trazabilidad. El
mapa curado tiene prioridad sobre GBIF para Clase/Orden/Familia (es revisión
manual); GBIF sólo rellena lo que falte y aporta la clave.

UPSERT idempotente por 'especie'.

Ejecutar:
    cd lvca_agua && python -m database.seeds.seed_taxonomia_fitoplancton
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds._utils import upsert_batch, imprimir_resumen
from services.fitoplancton_service import TAXONOMIA_FITOPLANCTON


# ─────────────────────────────────────────────────────────────────────────────
# Jerarquía curada por GÉNERO (clase, orden, familia) — alineada con AlgaeBase.
# Las entradas "ND"/sin género quedan sólo con su filo (division).
# ─────────────────────────────────────────────────────────────────────────────
JERARQUIA_GENERO: dict[str, tuple[str | None, str | None, str | None]] = {
    # ── Cyanobacteria (clase Cyanophyceae) ──────────────────────────────────
    "Dolichospermum": ("Cyanophyceae", "Nostocales", "Aphanizomenonaceae"),
    "Nodularia":      ("Cyanophyceae", "Nostocales", "Nostocaceae"),
    "Nostoc":         ("Cyanophyceae", "Nostocales", "Nostocaceae"),
    "Oscillatoria":   ("Cyanophyceae", "Oscillatoriales", "Oscillatoriaceae"),
    "Phormidium":     ("Cyanophyceae", "Oscillatoriales", "Oscillatoriaceae"),
    "Pseudanabaena":  ("Cyanophyceae", "Synechococcales", "Pseudanabaenaceae"),
    "Chroococcus":    ("Cyanophyceae", "Chroococcales", "Chroococcaceae"),
    "Lyngbya":        ("Cyanophyceae", "Oscillatoriales", "Oscillatoriaceae"),
    "Spirulina":      ("Cyanophyceae", "Spirulinales", "Spirulinaceae"),
    # ── Bacillariophyta (diatomeas) ─────────────────────────────────────────
    "Aulacoseira":    ("Coscinodiscophyceae", "Aulacoseirales", "Aulacoseiraceae"),
    "Achnanthidium":  ("Bacillariophyceae", "Cocconeidales", "Achnanthidiaceae"),
    "Amphora":        ("Bacillariophyceae", "Thalassiophysales", "Catenulaceae"),
    "Asterionella":   ("Fragilariophyceae", "Fragilariales", "Fragilariaceae"),
    "Coconeis":       ("Bacillariophyceae", "Cocconeidales", "Cocconeidaceae"),
    "Cocconeis":      ("Bacillariophyceae", "Cocconeidales", "Cocconeidaceae"),
    "Cymbella":       ("Bacillariophyceae", "Cymbellales", "Cymbellaceae"),
    "Cymatopleura":   ("Bacillariophyceae", "Surirellales", "Surirellaceae"),
    "Diploneis":      ("Bacillariophyceae", "Naviculales", "Diploneidaceae"),
    "Diatoma":        ("Fragilariophyceae", "Fragilariales", "Tabellariaceae"),
    "Encyonema":      ("Bacillariophyceae", "Cymbellales", "Cymbellaceae"),
    "Caloneis":       ("Bacillariophyceae", "Naviculales", "Naviculaceae"),
    "Epithemia":      ("Bacillariophyceae", "Rhopalodiales", "Rhopalodiaceae"),
    "Eunotia":        ("Bacillariophyceae", "Eunotiales", "Eunotiaceae"),
    "Fragilaria":     ("Fragilariophyceae", "Fragilariales", "Fragilariaceae"),
    "Frustulia":      ("Bacillariophyceae", "Naviculales", "Amphipleuraceae"),
    "Gomphonema":     ("Bacillariophyceae", "Cymbellales", "Gomphonemataceae"),
    "Hannaea":        ("Fragilariophyceae", "Fragilariales", "Fragilariaceae"),
    "Hantzchia":      ("Bacillariophyceae", "Bacillariales", "Bacillariaceae"),
    "Hantzschia":     ("Bacillariophyceae", "Bacillariales", "Bacillariaceae"),
    "Ceratoneis":     ("Fragilariophyceae", "Fragilariales", "Fragilariaceae"),
    "Navicula":       ("Bacillariophyceae", "Naviculales", "Naviculaceae"),
    "Neidium":        ("Bacillariophyceae", "Naviculales", "Neidiaceae"),
    "Nitzschia":      ("Bacillariophyceae", "Bacillariales", "Bacillariaceae"),
    "Pinnularia":     ("Bacillariophyceae", "Naviculales", "Pinnulariaceae"),
    "Rhoincosphenia": ("Bacillariophyceae", "Cymbellales", "Gomphonemataceae"),
    "Rhoicosphenia":  ("Bacillariophyceae", "Cymbellales", "Gomphonemataceae"),
    "Rhopalodia":     ("Bacillariophyceae", "Rhopalodiales", "Rhopalodiaceae"),
    "Sellaphora":     ("Bacillariophyceae", "Naviculales", "Sellaphoraceae"),
    "Melosira":       ("Coscinodiscophyceae", "Melosirales", "Melosiraceae"),
    "Surirella":      ("Bacillariophyceae", "Surirellales", "Surirellaceae"),
    "Staurosirella":  ("Fragilariophyceae", "Fragilariales", "Staurosiraceae"),
    "Synedra":        ("Fragilariophyceae", "Fragilariales", "Fragilariaceae"),
    "Ulnaria":        ("Fragilariophyceae", "Fragilariales", "Ulnariaceae"),
    "Tryblionella":   ("Bacillariophyceae", "Bacillariales", "Bacillariaceae"),
    # ── Chlorophyta ─────────────────────────────────────────────────────────
    "Acutodesmus":    ("Chlorophyceae", "Sphaeropleales", "Scenedesmaceae"),
    "Ankistrodesmus": ("Chlorophyceae", "Sphaeropleales", "Selenastraceae"),
    "Botryococcus":   ("Trebouxiophyceae", None, "Botryococcaceae"),
    "Crucigenia":     ("Chlorophyceae", "Sphaeropleales", "Scenedesmaceae"),
    "Chlamydomonas":  ("Chlorophyceae", "Chlamydomonadales", "Chlamydomonadaceae"),
    "Desmodesmus":    ("Chlorophyceae", "Sphaeropleales", "Scenedesmaceae"),
    "Dictyosphaerium":("Trebouxiophyceae", "Chlorellales", "Chlorellaceae"),
    "Elakatothrix":   ("Trebouxiophyceae", None, "Koliellaceae"),
    "Eudorina":       ("Chlorophyceae", "Chlamydomonadales", "Volvocaceae"),
    "Lagerheimia":    ("Trebouxiophyceae", "Chlorellales", "Oocystaceae"),
    "Microspora":     ("Chlorophyceae", "Sphaeropleales", "Microsporaceae"),
    "Monoraphidium":  ("Chlorophyceae", "Sphaeropleales", "Selenastraceae"),
    "Nephrocytium":   ("Trebouxiophyceae", "Chlorellales", "Oocystaceae"),
    "Oedogonium":     ("Chlorophyceae", "Oedogoniales", "Oedogoniaceae"),
    "Oocystis":       ("Trebouxiophyceae", "Chlorellales", "Oocystaceae"),
    "Pandorina":      ("Chlorophyceae", "Chlamydomonadales", "Volvocaceae"),
    "Pediastrum":     ("Chlorophyceae", "Sphaeropleales", "Hydrodictyaceae"),
    "Scenedesmus":    ("Chlorophyceae", "Sphaeropleales", "Scenedesmaceae"),
    "Schroederia":    ("Chlorophyceae", "Sphaeropleales", "Schroederiaceae"),
    "Sphaerocystis":  ("Chlorophyceae", "Chlamydomonadales", None),
    "Stigeoclonium":  ("Chlorophyceae", "Chaetophorales", "Chaetophoraceae"),
    "Ulothrix":       ("Ulvophyceae", "Ulotrichales", "Ulotrichaceae"),
    # ── Ochrophyta ──────────────────────────────────────────────────────────
    "Dinobryon":      ("Chrysophyceae", "Chromulinales", "Dinobryaceae"),
    "Mallomonas":     ("Synurophyceae", "Synurales", "Mallomonadaceae"),
    # ── Charophyta ──────────────────────────────────────────────────────────
    "Closterium":     ("Zygnematophyceae", "Desmidiales", "Closteriaceae"),
    "Cosmarium":      ("Zygnematophyceae", "Desmidiales", "Desmidiaceae"),
    "Gonatozygon":    ("Zygnematophyceae", "Desmidiales", "Gonatozygaceae"),
    "Mougeotia":      ("Zygnematophyceae", "Zygnematales", "Zygnemataceae"),
    "Spirogyra":      ("Zygnematophyceae", "Zygnematales", "Zygnemataceae"),
    "Staurastrum":    ("Zygnematophyceae", "Desmidiales", "Desmidiaceae"),
    "Staurodesmus":   ("Zygnematophyceae", "Desmidiales", "Desmidiaceae"),
    "Zygnema":        ("Zygnematophyceae", "Zygnematales", "Zygnemataceae"),
    # ── Euglenophyta (clase Euglenophyceae) ─────────────────────────────────
    "Euglena":        ("Euglenophyceae", "Euglenales", "Euglenaceae"),
    "Lepocinclis":    ("Euglenophyceae", "Euglenales", "Phacaceae"),
    "Phacus":         ("Euglenophyceae", "Euglenales", "Phacaceae"),
    "Trachelomonas":  ("Euglenophyceae", "Euglenales", "Euglenaceae"),
    # ── Dinophyta ───────────────────────────────────────────────────────────
    "Peridinium":     ("Dinophyceae", "Peridiniales", "Peridiniaceae"),
    # ── Cryptophyta ─────────────────────────────────────────────────────────
    "Cryptomonas":    ("Cryptophyceae", "Cryptomonadales", "Cryptomonadaceae"),
}

# Entradas especiales que NO son género (familia/clase/ND): jerarquía parcial.
JERARQUIA_ESPECIAL: dict[str, tuple[str | None, str | None, str | None]] = {
    "Pseudanabaeenaceae ND": ("Cyanophyceae", "Synechococcales", "Pseudanabaenaceae"),
    "Cianobacteria ND":      ("Cyanophyceae", None, None),
    "Bacillariophyta sp":    (None, None, None),
    "Euglenophyta sp.":      ("Euglenophyceae", None, None),
    "Orden Chlorellaceae":   ("Trebouxiophyceae", "Chlorellales", "Chlorellaceae"),
}


def _genero(nombre: str) -> str:
    return (nombre or "").strip().split()[0] if nombre.strip() else ""


def _jerarquia(nombre: str) -> tuple[str | None, str | None, str | None]:
    if nombre in JERARQUIA_ESPECIAL:
        return JERARQUIA_ESPECIAL[nombre]
    return JERARQUIA_GENERO.get(_genero(nombre), (None, None, None))


def run(verificar_gbif: bool = True) -> None:
    db = get_admin_client()

    # Importar la verificación sólo si se pide (requiere red).
    verificar = None
    if verificar_gbif:
        try:
            from services.taxonomia_fitoplancton_service import _verificar_gbif as verificar
        except Exception:
            verificar = None

    filas: list[dict] = []
    for filo, especies in TAXONOMIA_FITOPLANCTON.items():
        for orden_visual, esp in enumerate(especies):
            nombre = esp["nombre"]
            clase, orden, familia = _jerarquia(nombre)
            gbif_key = None
            fuente = "seed"

            # Confirmar/completar contra GBIF (no pisa el mapa curado).
            if verificar:
                gb = None
                try:
                    gb = verificar(_genero(nombre))
                except Exception:
                    gb = None
                if gb:
                    gbif_key = gb.get("gbif_key")
                    clase = clase or gb.get("clase")
                    orden = orden or gb.get("orden")
                    familia = familia or gb.get("familia")
                    fuente = "seed+gbif"

            filas.append({
                "division":            filo,
                "clase":               clase,
                "orden":               orden,
                "familia":             familia,
                "especie":             nombre,
                "unidad":              esp.get("unidad", "celula"),
                "celulas_por_unidad":  int(esp.get("celulas_por_unidad", 1)),
                "volumen_celula_um3":  float(esp.get("volumen_celula_um3", 0)),
                "gbif_key":            gbif_key,
                "fuente_verificacion": fuente,
                "orden_visual":        orden_visual,
                "activo":              True,
            })

    ok, errores = upsert_batch(db, "taxonomia_fitoplancton", filas, "especie")
    imprimir_resumen("SEED: taxonomia_fitoplancton", len(filas), ok, errores)


if __name__ == "__main__":
    # Por defecto intenta verificar contra GBIF; usa --offline para saltarlo.
    run(verificar_gbif="--offline" not in sys.argv)
