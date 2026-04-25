"""
services/fitoplancton_service.py
Análisis cuantitativo de fitoplancton por el método Sedgewick-Rafter.

Capa de negocio pura (cálculo) + capa de persistencia (lectura/escritura del
JSONB en muestras.datos_fitoplancton). La UI no calcula nada — sólo invoca
``calcular_densidad_sedgewick_rafter`` y luego ``guardar_analisis_fitoplancton``.

Funciones públicas:
    calcular_densidad_sedgewick_rafter(...)  → cálculo puro (cel/mL, cel/L)
    guardar_analisis_fitoplancton(...)       → upsert del JSONB en muestras
    get_analisis_fitoplancton(muestra_id)    → lectura del JSONB

Taxonomía (constante): TAXONOMIA_FITOPLANCTON = {filo: [especies, ...]}
    Fuente: lista de identificación habitual del laboratorio para Sedgewick-Rafter.
    No se persiste en BD — el método define la taxonomía, no el ECA.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from database.client import get_admin_client


# ─────────────────────────────────────────────────────────────────────────────
# Taxonomía (constante de método — no migrar a BD)
# ─────────────────────────────────────────────────────────────────────────────

TAXONOMIA_FITOPLANCTON: dict[str, list[str]] = {
    "Cyanobacteria": [
        "Oscillatoria sp.", "Anabaena sp.", "Chroococcus sp.", "Merismopedia sp.",
        "Microcystis sp.", "Nostoc sp.", "Phormidium sp.", "Pseudanabaena sp.",
        "Spirulina sp.", "Synechococcus sp.",
    ],
    "Bacillariophyta": [
        "Achnanthes sp.", "Amphora sp.", "Asterionella sp.", "Cocconeis sp.",
        "Cyclotella sp.", "Cymbella sp.", "Diatoma sp.", "Encyonema sp.",
        "Epithemia sp.", "Fragilaria sp.", "Gomphonema sp.", "Melosira sp.",
        "Navicula sp.", "Nitzschia sp.", "Pinnularia sp.", "Rhoicosphenia sp.",
        "Rhopalodia sp.", "Surirella sp.", "Synedra sp.", "Tabellaria sp.",
        "Ulnaria sp.",
    ],
    "Charophyta": [
        "Closterium sp.", "Cosmarium sp.", "Staurastrum sp.",
    ],
    "Chlorophyta": [
        "Ankistrodesmus sp.", "Botryococcus sp.", "Chlamydomonas sp.",
        "Chlorella sp.", "Coelastrum sp.", "Crucigenia sp.", "Dictyosphaerium sp.",
        "Eudorina sp.", "Monoraphidium sp.", "Oocystis sp.", "Pandorina sp.",
        "Pediastrum sp.", "Scenedesmus sp.", "Selenastrum sp.", "Sphaerocystis sp.",
        "Stigeoclonium sp.", "Tetraedron sp.", "Tetraspora sp.", "Ulothrix sp.",
        "Volvox sp.",
    ],
    "Dinophyta": [
        "Ceratium sp.", "Peridinium sp.",
    ],
    "Euglenozoa": [
        "Euglena sp.", "Phacus sp.", "Trachelomonas sp.",
    ],
}

# Iconos Material por filo (para la UI — no afectan la lógica).
ICONOS_FILO: dict[str, str] = {
    "Cyanobacteria":   "bubble_chart",
    "Bacillariophyta": "grain",
    "Charophyta":      "spa",
    "Chlorophyta":     "eco",
    "Dinophyta":       "scatter_plot",
    "Euglenozoa":      "blur_on",
}


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo (función pura — sin Streamlit, sin BD)
# Fuente: APHA Standard Methods for the Examination of Water and Wastewater,
# método Sedgewick-Rafter para enumeración de fitoplancton.
# ─────────────────────────────────────────────────────────────────────────────

# Profundidad de la cámara Sedgewick-Rafter (D). Constante por diseño de fábrica.
PROFUNDIDAD_CAMARA_MM: float = 1.0


def calcular_densidad_sedgewick_rafter(
    conteos_brutos:     dict[str, int],
    vol_muestra_ml:     float,
    vol_concentrado_ml: float,
    area_campo_mm2:     float,
    num_campos:         int,
    profundidad_mm:     float = PROFUNDIDAD_CAMARA_MM,
) -> dict[str, dict[str, float | int]]:
    """
    Densidad de fitoplancton (cel/mL, cel/L) por el método Sedgewick-Rafter.

    Fórmula APHA Standard Methods:

                     C × 1000      Vc
        cel/mL  =  ───────────  ×  ──
                    A × D × F      Vs

        cel/L   =  cel/mL × 1000

    Variables:
        C    conteo bruto de la especie (células)            → conteos_brutos[especie]
        1000 volumen total de la cámara S-R en mm³ (= 1 mL)  → constante
        A    área del campo del microscopio (mm²)            → area_campo_mm2
        D    profundidad de la cámara (mm), siempre 1        → profundidad_mm
        F    número de campos leídos                         → num_campos
        Vc   volumen al que se concentró la muestra (mL)     → vol_concentrado_ml
        Vs   volumen original de muestra (mL)                → vol_muestra_ml

    Convenciones de uso:
        - Si se leyó toda la cámara: A=1000, F=1.
        - Si la muestra se leyó directa (sin concentrar): Vc = Vs.

    Retorna:
        {especie: {"conteo_bruto": int, "cel_ml": float, "cel_l": float}}
        Sólo se incluyen especies con conteo > 0.

    Lanza:
        ValueError si Vs, A, F o D son cero (división por cero).
    """
    if (
        vol_muestra_ml == 0
        or area_campo_mm2 == 0
        or num_campos == 0
        or profundidad_mm == 0
    ):
        raise ValueError(
            "El volumen de muestra (Vs), el área del campo (A), el número de "
            "campos (F) y la profundidad de la cámara (D) no pueden ser cero."
        )

    resultados: dict[str, dict[str, float | int]] = {}
    for especie, conteo in conteos_brutos.items():
        if conteo > 0:
            cel_ml = (
                (conteo * 1000.0)
                / (area_campo_mm2 * profundidad_mm * num_campos)
                * (vol_concentrado_ml / vol_muestra_ml)
            )
            cel_l = cel_ml * 1000.0
            resultados[especie] = {
                "conteo_bruto": int(conteo),
                "cel_ml": round(cel_ml, 4),
                "cel_l": round(cel_l, 4),
            }
    return resultados


def calcular_y_agrupar_por_filo(
    conteos_por_filo:   dict[str, dict[str, int]],
    vol_muestra_ml:     float,
    vol_concentrado_ml: float,
    area_campo_mm2:     float,
    num_campos:         int,
) -> dict[str, dict[str, dict[str, float | int]]]:
    """
    Wrapper que conserva la agrupación por filo en el resultado.

    Entrada:
        {"Cyanobacteria": {"Oscillatoria sp.": 5, ...}, "Bacillariophyta": {...}, ...}

    Retorna:
        {"Cyanobacteria": {"Oscillatoria sp.": {conteo_bruto, cel_ml, cel_l}, ...}, ...}
        Sólo se incluyen filos que tengan al menos una especie con conteo > 0.
    """
    salida: dict[str, dict[str, dict[str, float | int]]] = {}
    for filo, especies in conteos_por_filo.items():
        densidades = calcular_densidad_sedgewick_rafter(
            conteos_brutos=especies,
            vol_muestra_ml=vol_muestra_ml,
            vol_concentrado_ml=vol_concentrado_ml,
            area_campo_mm2=area_campo_mm2,
            num_campos=num_campos,
        )
        if densidades:
            salida[filo] = densidades
    return salida


# ─────────────────────────────────────────────────────────────────────────────
# Alerta OMS para cianobacterias — Tabla por células/mL
#
# Fuente:  WHO (1999) — "Toxic Cyanobacteria in Water: A guide to their public
#          health consequences, monitoring and management" (Chorus & Bartram,
#          1ra edición). Drinking-water Alert Levels Framework, capítulo 6.
#
# Nota:    La 2da edición de la guía OMS (Chorus & Welker, 2021) introduce una
#          tabla complementaria expresada en biovolumen (mm³/L) — vigilancia
#          >10 colonias·mL⁻¹ o >50 filamentos·mL⁻¹ / Alerta 1 ≥0,3 mm³·L⁻¹ /
#          Alerta 2 ≥4,0 mm³·L⁻¹. Esa tabla NO se aplica aquí porque requiere
#          el biovolumen específico por especie (volumen celular promedio),
#          dato no recolectado en este formulario. La tabla por células/mL de
#          1999 sigue siendo citada en la edición 2021 para escenarios de
#          agua potable.
# ─────────────────────────────────────────────────────────────────────────────

OMS_FUENTE: str = "OMS 1999 — Tabla por cél/mL (agua potable, Drinking-water Alert Levels Framework)"

CYANOBACTERIA_FILO: str = "Cyanobacteria"

# Niveles ordenados de mayor a menor severidad — la evaluación recorre la lista
# y devuelve el primero que cumpla el umbral mínimo.
NIVELES_OMS_CIANOBACTERIAS: list[dict] = [
    {
        "nivel":             "alerta_2",
        "label":             "Alerta 2",
        "umbral_min_cel_ml": 100_000.0,
        "umbral_max_cel_ml": None,
        "color_bg":          "#f8d7da",
        "color_fg":          "#721c24",
        "color_borde":       "#dc3545",
        "icono":             "dangerous",
        "descripcion": (
            "Floración de cianobacterias establecida en el cuerpo de agua "
            "con elevado riesgo de toxicidad."
        ),
    },
    {
        "nivel":             "alerta_1",
        "label":             "Alerta 1",
        "umbral_min_cel_ml": 2_000.0,
        "umbral_max_cel_ml": 100_000.0,
        "color_bg":          "#fff3cd",
        "color_fg":          "#856404",
        "color_borde":       "#ffc107",
        "icono":             "warning",
        "descripcion": (
            "Concentraciones que traen riesgos asociados a cianotoxinas. "
            "Comunicar a las autoridades pertinentes para evaluar manejo "
            "operacional o tratamiento de agua."
        ),
    },
    {
        "nivel":             "vigilancia_inicial",
        "label":             "Vigilancia inicial",
        "umbral_min_cel_ml": 200.0,
        "umbral_max_cel_ml": 2_000.0,
        "color_bg":          "#d4edda",
        "color_fg":          "#155724",
        "color_borde":       "#28a745",
        "icono":             "monitoring",
        "descripcion": (
            "Posible etapa inicial del desarrollo de una floración: "
            "cianobacterias detectadas en muestras de agua cruda no concentrada."
        ),
    },
]


def evaluar_alerta_oms_cianobacterias(total_cel_ml: float) -> Optional[dict]:
    """
    Aplica los umbrales OMS por densidad celular al total de cianobacterias.

    Parámetros:
        total_cel_ml: suma de cel/mL de todas las especies del filo Cyanobacteria.

    Retorna:
        dict con {nivel, label, color_bg, color_fg, color_borde, icono,
                  descripcion, umbral_min_cel_ml, umbral_max_cel_ml}
        o None si total_cel_ml < 200 (sin alerta).
    """
    if total_cel_ml is None or total_cel_ml < 200.0:
        return None
    for nivel in NIVELES_OMS_CIANOBACTERIAS:
        if total_cel_ml >= nivel["umbral_min_cel_ml"]:
            return nivel
    return None


def total_cel_ml_filo(
    resultados_por_filo: dict[str, dict[str, dict[str, float | int]]],
    filo: str,
) -> float:
    """Suma cel/mL de todas las especies de un filo en el resultado del cálculo."""
    especies = resultados_por_filo.get(filo) or {}
    return float(sum(float(v.get("cel_ml", 0.0) or 0.0) for v in especies.values()))


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia (Supabase — JSONB en muestras.datos_fitoplancton)
# ─────────────────────────────────────────────────────────────────────────────

def guardar_analisis_fitoplancton(
    muestra_id:         str,
    vol_muestra_ml:     float,
    vol_concentrado_ml: float,
    area_campo_mm2:     float,
    num_campos:         int,
    resultados_por_filo: dict[str, dict[str, dict[str, float | int]]],
    analista_id:        Optional[str] = None,
) -> None:
    """
    Persiste el análisis de fitoplancton como un único documento JSONB en
    muestras.datos_fitoplancton.

    No usa la tabla resultados_laboratorio porque (a) no es un parámetro
    del DS 004-2017-MINAM y (b) un análisis Sedgewick-Rafter es un documento
    único por muestra que agrupa metadatos + 59 especies.
    """
    documento = {
        "metadatos": {
            "vol_muestra_ml":     vol_muestra_ml,
            "vol_concentrado_ml": vol_concentrado_ml,
            "area_campo_mm2":     area_campo_mm2,
            "num_campos":         num_campos,
            "fecha_analisis":     datetime.utcnow().date().isoformat(),
            "analista_id":        analista_id,
        },
        "resultados": resultados_por_filo,
    }
    db = get_admin_client()
    db.table("muestras").update({"datos_fitoplancton": documento}).eq("id", muestra_id).execute()


def get_analisis_fitoplancton(muestra_id: str) -> Optional[dict]:
    """
    Lee el JSONB datos_fitoplancton de la muestra. Retorna None si no hay
    análisis cargado o si la columna aún no existe (pre-migración 015).
    """
    db = get_admin_client()
    try:
        res = (
            db.table("muestras")
            .select("datos_fitoplancton")
            .eq("id", muestra_id)
            .single()
            .execute()
        )
        return (res.data or {}).get("datos_fitoplancton")
    except Exception:
        return None


def borrar_analisis_fitoplancton(muestra_id: str) -> None:
    """Limpia el análisis de fitoplancton de la muestra (set NULL)."""
    db = get_admin_client()
    db.table("muestras").update({"datos_fitoplancton": None}).eq("id", muestra_id).execute()
