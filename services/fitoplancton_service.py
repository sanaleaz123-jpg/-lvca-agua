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
from services.audit_service import registrar_cambio


# ─────────────────────────────────────────────────────────────────────────────
# Taxonomía (constante de método — no migrar a BD)
# ─────────────────────────────────────────────────────────────────────────────

# Cada especie es un dict con:
#   nombre              — nombre taxonómico (con sp.)
#   unidad              — natural unit de conteo: "celula" | "colonia" | "filamento"
#   celulas_por_unidad  — número promedio de células por unidad natural (1 si unicelular)
#   volumen_celula_um3  — biovolumen promedio de una célula individual (µm³)
#
# Fuentes consultadas:
#   - Olenina I. et al. 2006 — "Biovolumes and size-classes of phytoplankton in
#     the Baltic Sea". HELCOM Baltic Sea Environment Proceedings 106.
#   - Sun J. & Liu D. 2003 — "Geometric models for calculating cell biovolume
#     and surface area for phytoplankton". J Plankton Res 25:1331-1346.
#   - Hillebrand H. et al. 1999 — "Biovolume calculation for pelagic and
#     benthic microalgae". J Phycol 35:403-424.
#   - HELCOM PEG counting guidelines (2018 update).
#   - WHO 2021 Toxic Cyanobacteria in Water (2nd ed.) — definición de unidad
#     de conteo para cianobacterias.
#
# Los valores `celulas_por_unidad` y `volumen_celula_um3` son VALORES DE
# REFERENCIA basados en la literatura citada. Para alta precisión el
# laboratorio debe medir biovolumen específico de su muestra (ImageJ +
# fórmulas de Sun & Liu 2003). Estos defaults sirven para reportes de
# vigilancia rutinaria y para aplicar la Tabla OMS 2021 sin medición
# explícita.
TAXONOMIA_FITOPLANCTON: dict[str, list[dict]] = {
    "Cyanobacteria": [
        # Coloniales (mucilaginosas o cocoidales agrupadas)
        {"nombre": "Microcystis sp.",      "unidad": "colonia",   "celulas_por_unidad": 100, "volumen_celula_um3": 65},
        {"nombre": "Chroococcus sp.",      "unidad": "colonia",   "celulas_por_unidad": 4,   "volumen_celula_um3": 50},
        {"nombre": "Merismopedia sp.",     "unidad": "colonia",   "celulas_por_unidad": 32,  "volumen_celula_um3": 5},
        {"nombre": "Nostoc sp.",           "unidad": "colonia",   "celulas_por_unidad": 100, "volumen_celula_um3": 35},
        # Filamentosas (tricomas con o sin envoltura)
        {"nombre": "Anabaena sp.",         "unidad": "filamento", "celulas_por_unidad": 50,  "volumen_celula_um3": 30},
        {"nombre": "Oscillatoria sp.",     "unidad": "filamento", "celulas_por_unidad": 50,  "volumen_celula_um3": 200},
        {"nombre": "Phormidium sp.",       "unidad": "filamento", "celulas_por_unidad": 40,  "volumen_celula_um3": 35},
        {"nombre": "Pseudanabaena sp.",    "unidad": "filamento", "celulas_por_unidad": 30,  "volumen_celula_um3": 5},
        {"nombre": "Spirulina sp.",        "unidad": "filamento", "celulas_por_unidad": 10,  "volumen_celula_um3": 35},
        # Unicelulares (picocianobacterias)
        {"nombre": "Synechococcus sp.",    "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 5},
    ],
    # Bacillariophyta (diatomeas) — convención HELCOM PEG: cuenta cada célula
    # individual incluso en colonias/cadenas. Volumen por célula promedio.
    "Bacillariophyta": [
        {"nombre": "Achnanthes sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 200},
        {"nombre": "Amphora sp.",          "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 600},
        {"nombre": "Asterionella sp.",     "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 600},
        {"nombre": "Cocconeis sp.",        "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 250},
        {"nombre": "Cyclotella sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 500},
        {"nombre": "Cymbella sp.",         "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 1500},
        {"nombre": "Diatoma sp.",          "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 800},
        {"nombre": "Encyonema sp.",        "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 1200},
        {"nombre": "Epithemia sp.",        "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 2500},
        {"nombre": "Fragilaria sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 500},
        {"nombre": "Gomphonema sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 1000},
        {"nombre": "Melosira sp.",         "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 3500},
        {"nombre": "Navicula sp.",         "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 800},
        {"nombre": "Nitzschia sp.",        "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 600},
        {"nombre": "Pinnularia sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 5000},
        {"nombre": "Rhoicosphenia sp.",    "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 350},
        {"nombre": "Rhopalodia sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 2000},
        {"nombre": "Surirella sp.",        "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 5000},
        {"nombre": "Synedra sp.",          "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 1200},
        {"nombre": "Tabellaria sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 700},
        {"nombre": "Ulnaria sp.",          "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 1500},
    ],
    # Charophyta (desmidiaceas) — todas unicelulares.
    "Charophyta": [
        {"nombre": "Closterium sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 8000},
        {"nombre": "Cosmarium sp.",        "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 5000},
        {"nombre": "Staurastrum sp.",      "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 4000},
    ],
    # Chlorophyta — mezcla: unicelulares, cenobios coloniales y filamentos.
    "Chlorophyta": [
        # Unicelulares
        {"nombre": "Ankistrodesmus sp.",   "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 200},
        {"nombre": "Chlamydomonas sp.",    "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 250},
        {"nombre": "Chlorella sp.",        "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 30},
        {"nombre": "Monoraphidium sp.",    "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 100},
        {"nombre": "Oocystis sp.",         "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 200},
        {"nombre": "Selenastrum sp.",      "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 80},
        {"nombre": "Tetraedron sp.",       "unidad": "celula",    "celulas_por_unidad": 1,   "volumen_celula_um3": 700},
        # Cenobios coloniales (4-32 células fijas)
        {"nombre": "Botryococcus sp.",     "unidad": "colonia",   "celulas_por_unidad": 50,  "volumen_celula_um3": 250},
        {"nombre": "Coelastrum sp.",       "unidad": "colonia",   "celulas_por_unidad": 8,   "volumen_celula_um3": 200},
        {"nombre": "Crucigenia sp.",       "unidad": "colonia",   "celulas_por_unidad": 4,   "volumen_celula_um3": 80},
        {"nombre": "Dictyosphaerium sp.",  "unidad": "colonia",   "celulas_por_unidad": 8,   "volumen_celula_um3": 60},
        {"nombre": "Pediastrum sp.",       "unidad": "colonia",   "celulas_por_unidad": 16,  "volumen_celula_um3": 250},
        {"nombre": "Scenedesmus sp.",      "unidad": "colonia",   "celulas_por_unidad": 4,   "volumen_celula_um3": 80},
        {"nombre": "Sphaerocystis sp.",    "unidad": "colonia",   "celulas_por_unidad": 16,  "volumen_celula_um3": 250},
        {"nombre": "Tetraspora sp.",       "unidad": "colonia",   "celulas_por_unidad": 16,  "volumen_celula_um3": 100},
        # Volvocales (esféricas grandes con muchas células)
        {"nombre": "Eudorina sp.",         "unidad": "colonia",   "celulas_por_unidad": 32,  "volumen_celula_um3": 250},
        {"nombre": "Pandorina sp.",        "unidad": "colonia",   "celulas_por_unidad": 16,  "volumen_celula_um3": 250},
        {"nombre": "Volvox sp.",           "unidad": "colonia",   "celulas_por_unidad": 500, "volumen_celula_um3": 60},
        # Filamentosas
        {"nombre": "Stigeoclonium sp.",    "unidad": "filamento", "celulas_por_unidad": 30,  "volumen_celula_um3": 150},
        {"nombre": "Ulothrix sp.",         "unidad": "filamento", "celulas_por_unidad": 50,  "volumen_celula_um3": 250},
    ],
    # Dinophyta (dinoflagelados) — unicelulares grandes.
    "Dinophyta": [
        {"nombre": "Ceratium sp.",         "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 50000},
        {"nombre": "Peridinium sp.",       "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 12000},
    ],
    # Euglenozoa — unicelulares flagelados.
    "Euglenozoa": [
        {"nombre": "Euglena sp.",          "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 8000},
        {"nombre": "Phacus sp.",           "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 3500},
        {"nombre": "Trachelomonas sp.",    "unidad": "celula", "celulas_por_unidad": 1, "volumen_celula_um3": 2000},
    ],
}


# Etiquetas cortas para mostrar la unidad en UI sin ocupar mucho espacio.
ABREV_UNIDAD: dict[str, str] = {
    "celula":    "cél",
    "colonia":   "col",
    "filamento": "fil",
}


def get_especies_filo(filo: str) -> list[dict]:
    """Devuelve la lista de especies (dicts) de un filo, vacía si no existe."""
    return TAXONOMIA_FITOPLANCTON.get(filo, [])


def get_metadata_especie(filo: str, nombre_especie: str) -> dict | None:
    """Devuelve el dict completo {nombre, unidad, celulas_por_unidad, volumen_celula_um3} o None."""
    for esp in get_especies_filo(filo):
        if esp["nombre"] == nombre_especie:
            return esp
    return None

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

    # Restricción física: la concentración reduce el volumen, no lo aumenta.
    # Un Vc > Vs implicaría un dato mal capturado y daría densidades infladas.
    if vol_concentrado_ml > vol_muestra_ml:
        raise ValueError(
            f"El volumen concentrado (Vc={vol_concentrado_ml} mL) no puede "
            f"ser mayor al volumen original de muestra (Vs={vol_muestra_ml} mL). "
            "Si la muestra se leyó directa sin concentrar, usa Vc = Vs."
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
) -> dict[str, dict[str, dict[str, float | int | str]]]:
    """
    Calcula densidad y biovolumen por especie y agrupa por filo.

    Entrada:
        {"Cyanobacteria": {"Microcystis sp.": 5, ...}, ...}
        Los valores son CONTEOS de unidades naturales (no de células — la
        unidad depende de la especie según TAXONOMIA_FITOPLANCTON).

    Salida por especie:
        {
          "conteo_bruto":     int,    # unidades contadas
          "unidad":           str,    # "celula" | "colonia" | "filamento"
          "unidad_ml":        float,  # densidad en unidades/mL (Sedgewick-Rafter)
          "cel_ml_equiv":     float,  # equivalente en células/mL (× cels_por_unidad)
          "cel_l_equiv":      float,  # = cel_ml_equiv × 1000
          "biovolumen_mm3_l": float,  # biomasa estimada (mm³/L)
        }

    Sólo se incluyen filos con al menos una especie con conteo > 0.
    """
    salida: dict[str, dict[str, dict[str, float | int | str]]] = {}
    for filo, especies in conteos_por_filo.items():
        # Densidad bruta en unidades/mL (la fórmula APHA es ortogonal a la unidad).
        densidades = calcular_densidad_sedgewick_rafter(
            conteos_brutos=especies,
            vol_muestra_ml=vol_muestra_ml,
            vol_concentrado_ml=vol_concentrado_ml,
            area_campo_mm2=area_campo_mm2,
            num_campos=num_campos,
        )
        if not densidades:
            continue

        salida_filo: dict[str, dict[str, float | int | str]] = {}
        for nombre_especie, val in densidades.items():
            meta = get_metadata_especie(filo, nombre_especie)
            unidad = (meta or {}).get("unidad", "celula")
            cels_por_unidad = float((meta or {}).get("celulas_por_unidad", 1) or 1)
            vol_cel_um3 = float((meta or {}).get("volumen_celula_um3", 0) or 0)

            unidad_ml = float(val["cel_ml"])  # Sedgewick-Rafter da unidades/mL
            cel_ml_equiv = unidad_ml * cels_por_unidad
            cel_l_equiv = cel_ml_equiv * 1000.0
            # Biovolumen: cel/mL × µm³/cel × 1e-9 (µm³→mm³) × 1000 (mL→L) = ×1e-6
            biovolumen_mm3_l = cel_ml_equiv * vol_cel_um3 * 1e-6

            salida_filo[nombre_especie] = {
                "conteo_bruto":     int(val["conteo_bruto"]),
                "unidad":           unidad,
                "unidad_ml":        round(unidad_ml, 4),
                "cel_ml_equiv":     round(cel_ml_equiv, 4),
                "cel_l_equiv":      round(cel_l_equiv, 4),
                "biovolumen_mm3_l": round(biovolumen_mm3_l, 6),
                # Mantenemos cel_ml/cel_l por compatibilidad con datos legacy
                # del formato anterior: corresponden a unidad_ml/cel_l_unidad.
                "cel_ml":           round(unidad_ml, 4),
                "cel_l":            round(unidad_ml * 1000.0, 4),
            }
        salida[filo] = salida_filo
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
OMS_FUENTE_2021: str = "OMS 2021 — Tabla por biovolumen mm³/L (agua recreativa, Chorus & Welker 2da ed.)"

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


# ─────────────────────────────────────────────────────────────────────────────
# Alerta OMS 2021 — Tabla por biovolumen (mm³/L) + criterio de unidades
#
# Fuente: WHO (2021) — "Toxic Cyanobacteria in Water" 2nd ed. (Chorus & Welker).
#         Capítulo "Alert Levels Framework" — tabla por biovolumen para agua
#         recreativa.
#
# Criterios (literal):
#   Vigilancia inicial: >10 colonias·mL⁻¹  o  >50 filamentos·mL⁻¹
#   Alerta 1:           biovolumen ≥ 0,3 mm³·L⁻¹
#   Alerta 2:           biovolumen ≥ 4,0 mm³·L⁻¹
#
# Implementación:
#   - Si biovolumen >= 4.0  → Alerta 2
#   - Si biovolumen >= 0.3  → Alerta 1
#   - Si NO hay alerta por biovolumen pero sí por conteo de unidades
#     (col > 10 o fil > 50) → Vigilancia inicial
#   - En caso contrario → None (sin alerta)
# ─────────────────────────────────────────────────────────────────────────────

NIVELES_OMS_2021_CIANOBACTERIAS: list[dict] = [
    {
        "nivel":      "alerta_2",
        "label":      "Alerta 2",
        "criterio":   "biovolumen ≥ 4,0 mm³/L",
        "color_bg":   "#f8d7da",
        "color_fg":   "#721c24",
        "color_borde":"#dc3545",
        "icono":      "dangerous",
        "descripcion": (
            "Floración de cianobacterias establecida en el cuerpo de agua "
            "con elevado riesgo de toxicidad."
        ),
    },
    {
        "nivel":      "alerta_1",
        "label":      "Alerta 1",
        "criterio":   "biovolumen ≥ 0,3 mm³/L",
        "color_bg":   "#fff3cd",
        "color_fg":   "#856404",
        "color_borde":"#ffc107",
        "icono":      "warning",
        "descripcion": (
            "Concentraciones que traen riesgos asociados a cianotoxinas. "
            "Comunicar a las autoridades pertinentes para evaluar manejo "
            "operacional o tratamiento de agua."
        ),
    },
    {
        "nivel":      "vigilancia_inicial",
        "label":      "Vigilancia inicial",
        "criterio":   ">10 colonias/mL o >50 filamentos/mL",
        "color_bg":   "#d4edda",
        "color_fg":   "#155724",
        "color_borde":"#28a745",
        "icono":      "monitoring",
        "descripcion": (
            "Posible etapa inicial del desarrollo de una floración: "
            "cianobacterias presentes con biomasa aún baja."
        ),
    },
]


def evaluar_alerta_oms_2021(
    biovolumen_mm3_l:    float,
    colonias_por_ml:     float,
    filamentos_por_ml:   float,
) -> Optional[dict]:
    """
    Aplica los umbrales WHO 2021 para cianobacterias (Tabla por biovolumen
    + criterio de unidades para Vigilancia inicial).

    Retorna el dict del nivel disparado o None si no hay alerta.
    """
    if biovolumen_mm3_l >= 4.0:
        return NIVELES_OMS_2021_CIANOBACTERIAS[0]   # Alerta 2
    if biovolumen_mm3_l >= 0.3:
        return NIVELES_OMS_2021_CIANOBACTERIAS[1]   # Alerta 1
    if colonias_por_ml > 10 or filamentos_por_ml > 50:
        return NIVELES_OMS_2021_CIANOBACTERIAS[2]   # Vigilancia inicial
    return None


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
    resultados_por_filo: dict[str, dict[str, dict[str, float | int | str]]],
    filo: str,
) -> float:
    """
    Suma equivalente en CÉLULAS/mL de un filo (para aplicar OMS 1999).
    Lee `cel_ml_equiv` (presente desde el refactor C.1). Para datos legacy
    sin ese campo, cae al campo `cel_ml` antiguo (que asumía 1 unidad = 1 cel).
    """
    especies = resultados_por_filo.get(filo) or {}
    total = 0.0
    for v in especies.values():
        if "cel_ml_equiv" in v:
            total += float(v.get("cel_ml_equiv", 0.0) or 0.0)
        else:
            total += float(v.get("cel_ml", 0.0) or 0.0)  # legacy fallback
    return float(total)


def total_unidades_ml_filo(
    resultados_por_filo: dict[str, dict[str, dict[str, float | int | str]]],
    filo: str,
    unidad: str,
) -> float:
    """
    Suma de unidades/mL de un filo filtrando por tipo de unidad
    ("colonia" o "filamento"). Sirve para aplicar el criterio de
    Vigilancia OMS 2021 (>10 col/mL o >50 fil/mL).
    """
    especies = resultados_por_filo.get(filo) or {}
    total = 0.0
    for v in especies.values():
        if v.get("unidad") == unidad:
            total += float(v.get("unidad_ml", 0.0) or 0.0)
    return float(total)


def total_biovolumen_filo(
    resultados_por_filo: dict[str, dict[str, dict[str, float | int | str]]],
    filo: str,
) -> float:
    """Suma biovolumen mm³/L de todas las especies del filo (para OMS 2021)."""
    especies = resultados_por_filo.get(filo) or {}
    return float(sum(float(v.get("biovolumen_mm3_l", 0.0) or 0.0) for v in especies.values()))


# ─── Cruce con clorofila-a (parámetro P124) ──────────────────────────────────
# OMS 1999 ofrece umbrales paralelos en clorofila-a cuando hay dominancia de
# cianobacterias en el fitoplancton. Estos umbrales NO se aplican aisladamente
# (clorofila-a es un proxy de biomasa total, no específica de cianobacterias):
# se reportan junto al conteo celular para corroborar el nivel de alerta.

CLOROFILA_PARAM_CODIGO: str = "P124"

# Umbrales WHO 1999 para clorofila-a en presencia de dominancia cianobacteriana
# (µg/L). Fuente: Chorus & Bartram 1999, capítulo 6.
NIVELES_OMS_CLOROFILA_UG_L: list[dict] = [
    {"nivel": "alerta_2",           "label": "Alerta 2",           "umbral_min": 50.0},
    {"nivel": "alerta_1",           "label": "Alerta 1",           "umbral_min": 10.0},
    {"nivel": "vigilancia_inicial", "label": "Vigilancia inicial", "umbral_min": 1.0},
]


def evaluar_alerta_oms_clorofila(clorofila_ug_l: Optional[float]) -> Optional[dict]:
    """
    Aplica los umbrales OMS 1999 para clorofila-a (en presencia de dominancia
    cianobacteriana). Retorna None si el valor es nulo o < 1 µg/L.
    """
    if clorofila_ug_l is None or clorofila_ug_l < 1.0:
        return None
    for nivel in NIVELES_OMS_CLOROFILA_UG_L:
        if clorofila_ug_l >= nivel["umbral_min"]:
            return nivel
    return None


def get_clorofila_de_muestra(muestra_id: str) -> Optional[dict]:
    """
    Lee el resultado de Clorofila A (P124) para la muestra. Retorna
    {valor, unidad, fecha_analisis, validado} o None si no hay resultado.
    """
    db = get_admin_client()
    try:
        res = (
            db.table("resultados_laboratorio")
            .select(
                "valor_numerico, fecha_analisis, validado, "
                "parametros!inner(codigo, unidades_medida(simbolo))"
            )
            .eq("muestra_id", muestra_id)
            .eq("parametros.codigo", CLOROFILA_PARAM_CODIGO)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        fila = res.data[0]
        valor = fila.get("valor_numerico")
        if valor is None:
            return None
        unidad = (
            (fila.get("parametros") or {}).get("unidades_medida") or {}
        ).get("simbolo", "µg/L")
        return {
            "valor":          float(valor),
            "unidad":         unidad,
            "fecha_analisis": fila.get("fecha_analisis"),
            "validado":       bool(fila.get("validado") or False),
        }
    except Exception:
        return None


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

    # Detecta si es upsert sobre análisis previo (audit accion='actualizar')
    # o un primer guardado (audit accion='crear').
    accion = "crear"
    try:
        previo = (
            db.table("muestras")
            .select("datos_fitoplancton")
            .eq("id", muestra_id)
            .single()
            .execute()
        )
        if (previo.data or {}).get("datos_fitoplancton") is not None:
            accion = "actualizar"
    except Exception:
        pass

    db.table("muestras").update({"datos_fitoplancton": documento}).eq("id", muestra_id).execute()

    # Resumen del cambio para el audit log: total cianobacterias + nº especies.
    total_cyano = total_cel_ml_filo(resultados_por_filo, CYANOBACTERIA_FILO)
    n_especies = sum(len(esp) for esp in resultados_por_filo.values())
    resumen = (
        f"fitoplancton {accion}: {n_especies} especie(s) registrada(s); "
        f"cianobacterias = {total_cyano:.2f} cél/mL"
    )
    try:
        registrar_cambio(
            tabla="muestras",
            registro_id=muestra_id,
            accion=accion,
            campo="datos_fitoplancton",
            valor_nuevo=resumen,
            usuario_id=analista_id,
        )
    except Exception:
        # El audit no debe romper el guardado si falla.
        pass


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


def borrar_analisis_fitoplancton(
    muestra_id: str,
    usuario_id: Optional[str] = None,
) -> None:
    """Limpia el análisis de fitoplancton de la muestra (set NULL) y audita."""
    db = get_admin_client()
    db.table("muestras").update({"datos_fitoplancton": None}).eq("id", muestra_id).execute()
    try:
        registrar_cambio(
            tabla="muestras",
            registro_id=muestra_id,
            accion="eliminar",
            campo="datos_fitoplancton",
            valor_nuevo="análisis de fitoplancton eliminado",
            usuario_id=usuario_id,
        )
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Histórico por punto (serie temporal de cianobacterias)
# ─────────────────────────────────────────────────────────────────────────────

def get_historico_cianobacterias_por_punto(
    punto_muestreo_id: str,
    limite: int = 50,
) -> list[dict]:
    """
    Devuelve la serie histórica de densidad de cianobacterias para un punto,
    ordenada cronológicamente (más antigua → más reciente).

    Cada elemento incluye: muestra_id, codigo_muestra, fecha_muestreo,
    total_cyano_cel_ml, nivel_oms (label o None), color_bg.
    """
    db = get_admin_client()
    res = (
        db.table("muestras")
        .select("id, codigo, fecha_muestreo, datos_fitoplancton")
        .eq("punto_muestreo_id", punto_muestreo_id)
        .not_.is_("datos_fitoplancton", "null")
        .order("fecha_muestreo", desc=False)
        .limit(limite)
        .execute()
    )
    serie: list[dict] = []
    for fila in res.data or []:
        doc = fila.get("datos_fitoplancton") or {}
        resultados = doc.get("resultados") or {}
        total_cel = total_cel_ml_filo(resultados, CYANOBACTERIA_FILO)
        biovol = total_biovolumen_filo(resultados, CYANOBACTERIA_FILO)
        col_ml = total_unidades_ml_filo(resultados, CYANOBACTERIA_FILO, "colonia")
        fil_ml = total_unidades_ml_filo(resultados, CYANOBACTERIA_FILO, "filamento")
        n1999 = evaluar_alerta_oms_cianobacterias(total_cel)
        n2021 = evaluar_alerta_oms_2021(biovol, col_ml, fil_ml)
        serie.append({
            "muestra_id":          fila["id"],
            "codigo_muestra":      fila.get("codigo"),
            "fecha_muestreo":      fila.get("fecha_muestreo"),
            "total_cyano_cel_ml":  total_cel,
            "biovolumen_mm3_l":    biovol,
            "colonias_ml":         col_ml,
            "filamentos_ml":       fil_ml,
            "oms_1999_label":      (n1999["label"] if n1999 else "Sin alerta"),
            "oms_1999_codigo":     (n1999["nivel"] if n1999 else None),
            "oms_1999_color_borde":(n1999["color_borde"] if n1999 else "#6c757d"),
            "oms_2021_label":      (n2021["label"] if n2021 else "Sin alerta"),
            "oms_2021_codigo":     (n2021["nivel"] if n2021 else None),
            "oms_2021_color_borde":(n2021["color_borde"] if n2021 else "#6c757d"),
            # Aliases retro-compat para el componente histórico anterior:
            "nivel_oms":           (n1999["label"] if n1999 else "Sin alerta"),
            "color_borde":         (n1999["color_borde"] if n1999 else "#6c757d"),
        })
    return serie


def get_historico_cianobacterias_por_muestra(muestra_id: str) -> list[dict]:
    """
    Wrapper de conveniencia: dado un muestra_id, deduce el punto_muestreo_id
    y devuelve el histórico de cianobacterias en ese punto. La muestra actual
    se incluye en la serie si ya tiene datos guardados.
    """
    db = get_admin_client()
    try:
        res = (
            db.table("muestras")
            .select("punto_muestreo_id")
            .eq("id", muestra_id)
            .single()
            .execute()
        )
        pid = (res.data or {}).get("punto_muestreo_id")
    except Exception:
        return []
    if not pid:
        return []
    return get_historico_cianobacterias_por_punto(pid)


def get_alertas_oms_por_punto() -> dict[str, dict]:
    """
    Para uso del geoportal: devuelve {punto_muestreo_id: {ultima_fecha,
    total_cyano_cel_ml, nivel_oms, color_borde}} con el ÚLTIMO análisis
    por punto. Solo incluye puntos con al menos un análisis fitoplancton.
    """
    db = get_admin_client()
    res = (
        db.table("muestras")
        .select("punto_muestreo_id, fecha_muestreo, datos_fitoplancton")
        .not_.is_("datos_fitoplancton", "null")
        .order("fecha_muestreo", desc=True)
        .execute()
    )
    salida: dict[str, dict] = {}
    for fila in res.data or []:
        pid = fila.get("punto_muestreo_id")
        if not pid or pid in salida:  # solo el más reciente
            continue
        doc = fila.get("datos_fitoplancton") or {}
        resultados = doc.get("resultados") or {}
        total_cel = total_cel_ml_filo(resultados, CYANOBACTERIA_FILO)
        biovol = total_biovolumen_filo(resultados, CYANOBACTERIA_FILO)
        col_ml = total_unidades_ml_filo(resultados, CYANOBACTERIA_FILO, "colonia")
        fil_ml = total_unidades_ml_filo(resultados, CYANOBACTERIA_FILO, "filamento")
        n1999 = evaluar_alerta_oms_cianobacterias(total_cel)
        n2021 = evaluar_alerta_oms_2021(biovol, col_ml, fil_ml)

        def _empaquetar(nivel: dict | None) -> dict:
            if nivel is None:
                return {
                    "label":        "Sin alerta",
                    "codigo":       "sin_alerta",
                    "color_bg":     "#e2e3e5",
                    "color_borde":  "#6c757d",
                }
            return {
                "label":        nivel["label"],
                "codigo":       nivel["nivel"],
                "color_bg":     nivel["color_bg"],
                "color_borde":  nivel["color_borde"],
            }

        salida[pid] = {
            "ultima_fecha":       fila.get("fecha_muestreo"),
            "total_cyano_cel_ml": total_cel,
            "biovolumen_mm3_l":   biovol,
            "colonias_ml":        col_ml,
            "filamentos_ml":      fil_ml,
            "oms_1999":           _empaquetar(n1999),
            "oms_2021":           _empaquetar(n2021),
            # Aliases retro-compat:
            "nivel_oms":          (n1999["label"] if n1999 else "Sin alerta"),
            "nivel_codigo":       (n1999["nivel"] if n1999 else "sin_alerta"),
            "color_bg":           (n1999["color_bg"] if n1999 else "#e2e3e5"),
            "color_borde":        (n1999["color_borde"] if n1999 else "#6c757d"),
        }
    return salida
