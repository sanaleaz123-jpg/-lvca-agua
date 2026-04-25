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
    "Miozoa": [
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
    "Miozoa":          "scatter_plot",
    "Euglenozoa":      "blur_on",
}


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo (función pura — sin Streamlit, sin BD)
# ─────────────────────────────────────────────────────────────────────────────

def calcular_densidad_sedgewick_rafter(
    conteos_brutos:     dict[str, int],
    vol_muestra_ml:     float,
    vol_concentrado_ml: float,
    area_campo_mm2:     float,
    num_campos:         int,
) -> dict[str, dict[str, float | int]]:
    """
    Calcula densidad de fitoplancton (cel/mL, cel/L) por el método Sedgewick-Rafter.

    Fórmula:
        factor_camara          = 1000 / (area_campo_mm2 · profundidad · num_campos)
        factor_concentracion   = vol_concentrado_ml / vol_muestra_ml
        cel/mL = conteo · factor_camara · factor_concentracion
        cel/L  = cel/mL · 1000

        La profundidad de la cámara S-R es constante: 1 mm.

    Parámetros:
        conteos_brutos:     {especie: conteo_entero}
        vol_muestra_ml:     volumen inicial de la muestra (mL)
        vol_concentrado_ml: volumen al que se redujo la muestra (mL)
        area_campo_mm2:     área del campo del microscopio (mm²); 1000 si toda la cámara
        num_campos:         cantidad de campos revisados; 1 si toda la cámara

    Retorna:
        {especie: {"conteo_bruto": int, "cel_ml": float, "cel_l": float}}
        Sólo se incluyen especies con conteo > 0.

    Lanza:
        ValueError si vol_muestra_ml, area_campo_mm2 o num_campos son cero.
    """
    if vol_muestra_ml == 0 or area_campo_mm2 == 0 or num_campos == 0:
        raise ValueError(
            "El volumen de muestra, el área del campo y el número de campos no pueden ser cero."
        )

    factor_camara = 1000.0 / (area_campo_mm2 * 1.0 * num_campos)
    factor_concentracion = vol_concentrado_ml / vol_muestra_ml

    resultados: dict[str, dict[str, float | int]] = {}
    for especie, conteo in conteos_brutos.items():
        if conteo > 0:
            cel_ml = (conteo * factor_camara) * factor_concentracion
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
