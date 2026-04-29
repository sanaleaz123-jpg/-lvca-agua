"""
database/seeds/seed_parametros.py
Parámetros de campo, fisicoquímicos e hidrobiológicos — AUTODEMA Cuenca Chili.
UPSERT idempotente por 'codigo'. Requiere que seed_unidades.py se haya ejecutado primero.

Categorías:
    1 = Campo           (mediciones in situ)
    2 = Fisicoquimico   (laboratorio)
    3 = Hidrobiologico  (organismos acuáticos)

Ejecutar:
    cd lvca_agua && python -m database.seeds.seed_parametros
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds._utils import upsert_batch, imprimir_resumen

CATEGORIAS: list[dict] = [
    {"nombre": "Parámetros de Campo",
     "descripcion": "Mediciones in situ con equipos de campo"},
    {"nombre": "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)",
     "descripcion": "Parámetros físicos, químicos y metales analizados en laboratorio"},
    {"nombre": "Parámetros Hidrobiológicos",
     "descripcion": "Organismos acuáticos indicadores de calidad"},
]

_CAT_NOMBRE = {
    1: "Parámetros de Campo",
    2: "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)",
    3: "Parámetros Hidrobiológicos",
}

PARAMETROS: list[dict] = [

    # ════════════════════════════════════════════════════════
    # CATEGORÍA 1 — CAMPO (mediciones in situ)
    # ════════════════════════════════════════════════════════

    {"codigo": "P001", "nombre": "pH",
     "nombre_corto": "pH", "categoria_id": 1, "unidad_simbolo": "pH",
     "metodo_referencia": "SM 4500-H+ B electrométrico", "es_in_situ": True},

    {"codigo": "P002", "nombre": "Temperatura del agua",
     "nombre_corto": "Temp. agua", "categoria_id": 1, "unidad_simbolo": "°C",
     "metodo_referencia": "SM 2550 B", "es_in_situ": True,
     "observacion_tecnica": (
         "ECA = Δ3 °C (variación máxima ±3 °C respecto al promedio mensual multianual "
         "de la estación, serie 1-5 años). NO es un valor absoluto: requiere línea base "
         "histórica por estación para ser verificable — sin esa serie el parámetro "
         "constituye no conformidad documental del programa de monitoreo. "
         "Aplica a Cat 1-A2, 3-D1, 4-E1 y 4-E2."
     )},

    {"codigo": "P003", "nombre": "Conductividad/TDS/Salinidad",
     "nombre_corto": "C.E./TDS/Sal.", "categoria_id": 1, "unidad_simbolo": "uS/cm",
     "metodo_referencia": "SM 2510 B", "es_in_situ": True,
     "observacion_tecnica": (
         "Medición in situ a T de referencia 25 °C. ECA DS 004-2017-MINAM: "
         "Cat 1-A2 = 1 600 µS/cm; Cat 3-D1 = 2 500 µS/cm (indicador de salinidad, "
         "clasificación FAO: <700 sin restricción, 700-3000 restricción ligera-moderada); "
         "Cat 4-E1/E2 = 1 000 µS/cm. Lagunas y ríos altoandinos mineralizados pueden "
         "exceder sin causa antrópica — aplicable Art. 6 excepción por condiciones naturales."
     )},

    {"codigo": "P004", "nombre": "Oxígeno Disuelto",
     "nombre_corto": "OD", "categoria_id": 1, "unidad_simbolo": "mg O2/L",
     "metodo_referencia": "SM 4500-O G electrométrico", "es_in_situ": True,
     "observacion_tecnica": (
         "Valor ECA es MÍNIMO (≥), no promedio — aplica al valor más bajo registrado. "
         "Cat 1-A2 ≥ 5 mg/L; Cat 3-D1 ≥ 4 mg/L; Cat 4-E1/E2 ≥ 5 mg/L. "
         "En lagunas estratificadas (Cat 4-E1) se recomienda muestreo en columna de agua."
     )},

    {"codigo": "P006", "nombre": "Turbidez",
     "nombre_corto": "Turbidez", "categoria_id": 1, "unidad_simbolo": "NTU",
     "metodo_referencia": "SM 2130 B", "es_in_situ": True,
     "observacion_tecnica": (
         "NTU = UNT (Unidad Nefelométrica de Turbidez). Cat 1-A2 = 100 UNT. "
         "NO regulado en Cat 3 ni Cat 4 del DS (en Cat 4 se usan SST y Color verdadero)."
     )},

    # ════════════════════════════════════════════════════════
    # CATEGORÍA 2 — FISICOQUÍMICO (laboratorio)
    # ════════════════════════════════════════════════════════

    {"codigo": "P011", "nombre": "Color verdadero",
     "nombre_corto": "Color V.", "categoria_id": 2, "unidad_simbolo": "UCV",
     "metodo_referencia": "SM 2120 C espectrofotométrico con filtración previa 0,45 µm",
     "observacion_tecnica": (
         "CRÍTICO: requiere filtración simple previa (típicamente 0,45 µm) antes del "
         "análisis — Nota (b) del DS. Reportar color aparente (sin filtrar) NO cumple el ECA. "
         "Cat 1-A2 y Cat 3-D1 = 100 Pt/Co; Cat 4-E1/E2 = 20 Pt/Co (5× más restrictivo). "
         "Nota (a): aplica a aguas claras; en aguas con coloración natural (taninos, "
         "humedales) el criterio es 'sin cambio anormal' — documentar color de fondo."
     )},

    {"codigo": "P019", "nombre": "DBO5",
     "nombre_corto": "DBO5", "categoria_id": 2, "unidad_simbolo": "mg O2/L",
     "metodo_referencia": "SM 5210 B Winkler modificado",
     "requiere_preservacion": True, "tipo_preservacion": "Refrigeración 4°C", "tiempo_max_analisis_horas": 48,
     "observacion_tecnica": (
         "Demanda Bioquímica de Oxígeno a 5 días, 20 °C. "
         "Cat 1-A2 = 5 mg/L; Cat 3-D1 = 15 mg/L; Cat 4-E1 = 5 (lagunas, más exigente); "
         "Cat 4-E2 = 10 (ríos costa y sierra)."
     )},

    {"codigo": "P025", "nombre": "Dureza total",
     "nombre_corto": "Dureza", "categoria_id": 2, "unidad_simbolo": "mg CaCO3/L",
     "metodo_referencia": "SM 2340 C EDTA titulación"},

    {"codigo": "P028", "nombre": "Sólidos suspendidos totales SST",
     "nombre_corto": "SST", "categoria_id": 2, "unidad_simbolo": "mg/L",
     "metodo_referencia": "SM 2540 D gravimétrico filtro 0.45um",
     "requiere_preservacion": True, "tipo_preservacion": "Refrigeración 4°C", "tiempo_max_analisis_horas": 168,
     "observacion_tecnica": (
         "NO regulado en Cat 1-A2 (Cat 1 usa TDS gravimétrico = 1000 mg/L) ni en Cat 3-D1. "
         "Cat 4-E1 ≤ 25 mg/L (muy restrictivo para lagunas); Cat 4-E2-Costa y sierra ≤ 100; "
         "Cat 4-E2-Selva ≤ 400. NO confundir con TDS (sólidos disueltos totales)."
     )},

    {"codigo": "P031", "nombre": "Nitratos",
     "nombre_corto": "NO3-N", "categoria_id": 2, "unidad_simbolo": "mg N-NO3/L",
     "metodo_referencia": "SM 4500-NO3 B reducción cadmio",
     "requiere_preservacion": True, "tipo_preservacion": "H2SO4 pH<2 4°C", "tiempo_max_analisis_horas": 48,
     "observacion_tecnica": (
         "CRÍTICO — unidades distintas entre categorías. El DS expresa el ECA de nitratos como: "
         "(a) ion NO3- en Cat 1-A2 = 50 mg/L y Cat 4-E1/E2 = 13 mg/L; "
         "(b) suma NO3-N + NO2-N como N en Cat 3-D1 = 100 mg/L. "
         "Este parámetro está en unidad mg N-NO3/L — al comparar con Cat 1 o Cat 4 aplicar "
         "factor ×4,43 (resultado lab × 4,43 = mg NO3-/L). Ver services/conversion_especies.py. "
         "La especie oficial de cada ECA está en eca_valores.expresado_como."
     )},

    {"codigo": "P032", "nombre": "Nitritos",
     "nombre_corto": "NO2-N", "categoria_id": 2, "unidad_simbolo": "mg N-NO2/L",
     "metodo_referencia": "SM 4500-NO2 B colorimétrico", "tiempo_max_analisis_horas": 48,
     "observacion_tecnica": (
         "CRÍTICO — unidades distintas entre categorías. El DS expresa el ECA de nitritos como: "
         "(a) ion NO2- en Cat 1-A2 = 3 mg/L; "
         "(b) NO2-N como N en Cat 3-D1 = 10 mg/L; "
         "(c) no aplica en Cat 4. "
         "Este parámetro está en mg N-NO2/L — al comparar con Cat 1-A2 aplicar factor ×3,28 "
         "(resultado lab × 3,28 = mg NO2-/L). Cat 3-D1 no requiere conversión."
     )},

    # P033 — Nitrógeno amoniacal total (medido directamente por Nessler).
    # Aplica al ECA Cat 1 "Amoniaco-N" (regulado como N total, valor fijo 1,5 mg N/L).
    # NO aplica al ECA Cat 4 (que regula NH3 libre — ver P034 derivado).
    {"codigo": "P033", "nombre": "Nitrógeno amoniacal total (N-NH3)",
     "nombre_corto": "N-NH3 total", "categoria_id": 2, "unidad_simbolo": "mg N-NH4/L",
     "metodo_referencia": "SM 4500-NH3 B Nessler",
     "requiere_preservacion": True, "tipo_preservacion": "H2SO4 pH<2 4°C", "tiempo_max_analisis_horas": 28,
     "observacion_tecnica": (
         "Nitrógeno amoniacal TOTAL (NH3 libre + NH4+) expresado como N. "
         "Medido directamente por el método Nessler (SM 4500-NH3 B). "
         "Aplica al ECA Cat 1-A1/A2/A3 'Amoniaco-N' = 1,5 mg N/L — comparación directa "
         "(el lab reporta mg N-NH4/L y el ECA también es como N). "
         "NO aplica al ECA Cat 4, que regula NH3 libre (ver parámetro derivado P034 "
         "'Amoniaco libre NH3 no ionizado'). "
         "Antes llamado 'Amonio / Amoniaco' — renombrado en cambio #2 del plan para "
         "eliminar ambigüedad con P034."
     )},

    # P034 — Amoniaco libre (NH3 no ionizado). PARÁMETRO DERIVADO, no se mide en lab.
    # Se calcula a partir de P033 (N amoniacal total) + pH + T (mediciones in situ)
    # usando el equilibrio químico de la Tabla N°1 del DS (pKa ≈ 9,25 a 25 °C).
    # Aplica al ECA Cat 4-E1/E2 'Amoniaco Total NH3'.
    {"codigo": "P034", "nombre": "Amoniaco libre (NH3 no ionizado)",
     "nombre_corto": "NH3 libre", "categoria_id": 2, "unidad_simbolo": "mg NH3/L",
     "metodo_referencia": "Derivado de P033 + pH + T (Tabla N°1 DS 004-2017-MINAM)",
     "observacion_tecnica": (
         "Parámetro DERIVADO — no se mide directamente en laboratorio. Se calcula a partir "
         "de P033 'Nitrógeno amoniacal total' (medido por Nessler) y las mediciones de pH "
         "y T in situ, aplicando el equilibrio químico NH3/NH4+ (pKa ≈ 9,25 a 25 °C). "
         "Aplica al ECA Cat 4-E1/E2 'Amoniaco Total NH3' — valor ECA variable según Tabla N°1 "
         "del DS (p. ej. pH 8,0 y 15 °C → 0,715 mg NH3/L). "
         "Cálculo y comparación: pendiente de implementar (cambio #4 del plan, tabla matricial). "
         "Hasta entonces, los resultados de laboratorio P033 no deben compararse directamente "
         "contra el ECA Cat 4 (sobrestima incumplimiento)."
     )},

    {"codigo": "P036", "nombre": "Fósforo total",
     "nombre_corto": "P-Total", "categoria_id": 2, "unidad_simbolo": "mg P/L",
     "metodo_referencia": "SM 4500-P B E ácido ascórbico con digestión ácida",
     "requiere_preservacion": True, "tipo_preservacion": "H2SO4 pH<2 4°C", "tiempo_max_analisis_horas": 672,
     "observacion_tecnica": (
         "Incluye P orgánico + inorgánico, disuelto + particulado. Requiere digestión ácida "
         "previa al análisis colorimétrico — indispensable: sin digestión solo se mide "
         "ortofosfato soluble y no equivale a P total. "
         "ECA oficial DS 004-2017-MINAM: Cat 1-A2 = 0,15 mg P/L; Cat 4-E1 = 0,035 (muy estricto "
         "por vulnerabilidad a eutrofización en lagunas); Cat 4-E2 = 0,05. Cat 3-D1: NO regulado."
     )},

    {"codigo": "P038", "nombre": "Fosfatos",
     "nombre_corto": "Fosfatos", "categoria_id": 2, "unidad_simbolo": "mg/L",
     "metodo_referencia": "SM 4500-P B ácido ascórbico",
     "es_eca": False,
     "observacion_tecnica": (
         "NO es parámetro ECA. El DS 004-2017-MINAM NO establece valor ECA para fosfatos "
         "(PO4 3-, ortofosfatos, fósforo reactivo soluble SRP). Solo regula Fósforo Total "
         "(ver P036). Si el informe de ensayo reporta fosfatos sin Fósforo Total, NO cumple "
         "el marco normativo (Nota 5 del Excel oficial). "
         "Este parámetro se captura con fines de caracterización pero no se compara contra ECA."
     )},

    {"codigo": "P041", "nombre": "Sulfatos",
     "nombre_corto": "Sulfatos", "categoria_id": 2, "unidad_simbolo": "mg SO4/L",
     "metodo_referencia": "SM 4500-SO4 E gravimétrico",
     "observacion_tecnica": (
         "Cat 1-A2 = 500 mg/L; Cat 3-D1 = 1 000 mg/L (mismo valor riego restringido y no "
         "restringido); Cat 4 no regulado."
     )},

    {"codigo": "P042", "nombre": "Cloruros",
     "nombre_corto": "Cloruros", "categoria_id": 2, "unidad_simbolo": "mg/L",
     "metodo_referencia": "SM 4500-Cl B argentométrico Mohr",
     "observacion_tecnica": (
         "Cat 1-A2 = 250 mg/L; Cat 3-D1 = 500 mg/L (mismo valor riego restringido y no "
         "restringido); Cat 4 no regulado."
     )},

    {"codigo": "P074", "nombre": "Hierro disuelto",
     "nombre_corto": "Fe", "categoria_id": 2, "unidad_simbolo": "mg Fe/L",
     "metodo_referencia": "SM 3111 B llama AAS fenantrolina",
     "requiere_preservacion": True, "tipo_preservacion": "HNO3 pH<2 4°C", "tiempo_max_analisis_horas": 4320,
     "observacion_tecnica": (
         "ATENCIÓN: en el DS 004-2017-MINAM el ECA está expresado como Hierro TOTAL (no "
         "solo disuelto). Cat 1-A2 = 1 mg Fe/L; Cat 3-D1 = 5 mg/L; Cat 4 no regulado. "
         "El nombre actual del parámetro ('Hierro disuelto') puede generar confusión — "
         "revisar si el método realmente mide Fe total o solo la fracción disuelta."
     )},

    {"codigo": "P077", "nombre": "Manganeso disuelto",
     "nombre_corto": "Mn", "categoria_id": 2, "unidad_simbolo": "mg Mn/L",
     "metodo_referencia": "SM 3111 B llama AAS",
     "requiere_preservacion": True, "tipo_preservacion": "HNO3 pH<2 4°C", "tiempo_max_analisis_horas": 4320,
     "observacion_tecnica": (
         "ATENCIÓN: en el DS 004-2017-MINAM el ECA está expresado como Manganeso TOTAL. "
         "Cat 1-A2 = 0,4 mg Mn/L; Cat 3-D1 = 0,2 mg/L (más restrictivo que Cat 1 por "
         "fitotoxicidad en riego); Cat 4 no regulado. "
         "El nombre actual del parámetro ('Manganeso disuelto') puede generar confusión — "
         "revisar si el método mide Mn total o solo la fracción disuelta."
     )},

    {"codigo": "P091", "nombre": "Microcistina LR",
     "nombre_corto": "Microcistina", "categoria_id": 2, "unidad_simbolo": "ug/L",
     "metodo_referencia": "ELISA o HPLC-MS/MS",
     "requiere_preservacion": True, "tipo_preservacion": "Oscuridad -20°C", "tiempo_max_analisis_horas": 720,
     "observacion_tecnica": (
         "Solo regulado en Cat 1-A2 = 0,001 mg/L (equivalente a 1 µg/L). "
         "No regulado en Cat 3 ni Cat 4. Toxina de cianobacterias — aplicable sobre todo "
         "en embalses con floraciones (eutrofización)."
     )},

    # ════════════════════════════════════════════════════════
    # CATEGORÍA 3 — HIDROBIOLÓGICO
    # ════════════════════════════════════════════════════════

    {"codigo": "P120", "nombre": "Fitoplancton",
     "nombre_corto": "Fitoplancton", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Utermohl/Sedgewick-Rafter (sumatoria de todos los phyla)",
     "requiere_preservacion": True, "tipo_preservacion": "Lugol 1% 4°C", "tiempo_max_analisis_horas": 168,
     "es_eca": False,
     "observacion_tecnica": (
         "Total de fitoplancton (cel/mL): sumatoria automática de las densidades "
         "calculadas para todos los phyla. Se calcula al guardar el análisis "
         "Sedgewick-Rafter en Resultados de laboratorio → Hidrobiológico."
     )},

    # Phyla de fitoplancton — sumatoria automática de las especies del phylum
    # al guardar el análisis Sedgewick-Rafter. No tienen ECA (DS 004-2017-MINAM
    # no regula conteos por phylum). Códigos slug FITO_* → no se exponen al
    # usuario, son sólo identificadores internos para upsert idempotente.
    {"codigo": "FITO_CYANOBACTERIA_CEL", "nombre": "Cianobacteria",
     "nombre_corto": "Cianobacteria", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Cyanobacteria)",
     "es_eca": False,
     "observacion_tecnica": (
         "Sumatoria automática de las especies de Cyanobacteria del análisis "
         "Sedgewick-Rafter. Evaluación contra OMS 1999 (Drinking-water Alert "
         "Levels Framework): vigilancia inicial ≥200 cél/mL, alerta 1 ≥2 000 "
         "cél/mL, alerta 2 ≥100 000 cél/mL."
     )},

    {"codigo": "FITO_CYANOBACTERIA_BIOVOL", "nombre": "Cianobacteria (biovolumen)",
     "nombre_corto": "Cianobacteria biovolumen", "categoria_id": 3, "unidad_simbolo": "mm3/L",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de biovolumen de especies del phylum Cyanobacteria)",
     "es_eca": False,
     "observacion_tecnica": (
         "Sumatoria automática del biovolumen estimado de las especies de "
         "Cyanobacteria. Evaluación contra OMS 2021 (Toxic Cyanobacteria in "
         "Water, 2nd ed.): vigilancia inicial >10 colonias/mL o >50 filamentos/mL, "
         "alerta 1 ≥0,3 mm³/L, alerta 2 ≥4,0 mm³/L."
     )},

    {"codigo": "FITO_BACILLARIOPHYTA", "nombre": "Bacillariophyta",
     "nombre_corto": "Diatomeas", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Bacillariophyta)",
     "es_eca": False,
     "observacion_tecnica": "Sumatoria automática de las especies del phylum Bacillariophyta (diatomeas)."},

    {"codigo": "FITO_CHLOROPHYTA", "nombre": "Chlorophyta",
     "nombre_corto": "Algas verdes", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Chlorophyta)",
     "es_eca": False,
     "observacion_tecnica": "Sumatoria automática de las especies del phylum Chlorophyta (algas verdes)."},

    {"codigo": "FITO_OCHROPHYTA", "nombre": "Ochrophyta",
     "nombre_corto": "Algas doradas (Chrysophyta)", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Ochrophyta)",
     "es_eca": False,
     "observacion_tecnica": "Sumatoria automática de las especies del phylum Ochrophyta (Chrysophyta)."},

    {"codigo": "FITO_CHAROPHYTA", "nombre": "Charophyta",
     "nombre_corto": "Carofitas", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Charophyta)",
     "es_eca": False,
     "observacion_tecnica": "Sumatoria automática de las especies del phylum Charophyta."},

    {"codigo": "FITO_EUGLENOPHYTA", "nombre": "Euglenophyta",
     "nombre_corto": "Euglenoideos", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Euglenophyta)",
     "es_eca": False,
     "observacion_tecnica": "Sumatoria automática de las especies del phylum Euglenophyta."},

    {"codigo": "FITO_DINOPHYTA", "nombre": "Dinophyta",
     "nombre_corto": "Dinoflagelados", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Dinophyta)",
     "es_eca": False,
     "observacion_tecnica": "Sumatoria automática de las especies del phylum Dinophyta (dinoflagelados)."},

    {"codigo": "FITO_CRYPTOPHYTA", "nombre": "Cryptophyta",
     "nombre_corto": "Criptofitas", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Sedgewick-Rafter (sumatoria de especies del phylum Cryptophyta)",
     "es_eca": False,
     "observacion_tecnica": "Sumatoria automática de las especies del phylum Cryptophyta."},

    {"codigo": "P124", "nombre": "Clorofila A",
     "nombre_corto": "Cl-a", "categoria_id": 3, "unidad_simbolo": "ug/L",
     "metodo_referencia": "SM 10200 H acetona espectrofotometría",
     "requiere_preservacion": True, "tipo_preservacion": "Oscuridad -20°C", "tiempo_max_analisis_horas": 336,
     "observacion_tecnica": (
         "Solo regulado en Cat 4-E1 (lagunas y lagos) = 0,008 mg/L = 8 µg/L. "
         "NO regulado en Cat 4-E2 (ríos) ni en ninguna subcategoría de Cat 1 o Cat 3. "
         "Las migraciones 008 y 009 eliminaron el valor erróneo cargado para Cat 4-E2. "
         "Método: SM 10200 H (extracción con acetona 90%, espectrofotometría tricromática "
         "o fluorometría). El laboratorio típicamente reporta en µg/L."
     )},

    {"codigo": "P126", "nombre": "Zooplancton",
     "nombre_corto": "Zooplancton", "categoria_id": 3, "unidad_simbolo": "org/L",
     "metodo_referencia": "Red 64um concentración conteo",
     "requiere_preservacion": True, "tipo_preservacion": "Formaldehído 4% 4°C"},

    {"codigo": "P130", "nombre": "Perifiton",
     "nombre_corto": "Perifiton", "categoria_id": 3, "unidad_simbolo": "ind/cm2",
     "metodo_referencia": "APHA 10300 raspado substrato artificial",
     "requiere_preservacion": True, "tipo_preservacion": "Lugol 1% 4°C"},
]


def _seed_categorias(db) -> dict[int, str]:
    """Crea categorías y retorna mapeo {id_local → uuid real}."""
    print("  Creando/verificando categorias de parametros...")
    cat_map: dict[int, str] = {}
    for cat in CATEGORIAS:
        res = db.table("categorias_parametro").upsert(cat, on_conflict="nombre").execute()
        if res.data:
            cat_map[list(_CAT_NOMBRE.keys())[list(_CAT_NOMBRE.values()).index(cat["nombre"])]] = res.data[0]["id"]
    if len(cat_map) < len(CATEGORIAS):
        rows = db.table("categorias_parametro").select("id, nombre").execute().data or []
        nombre_to_uuid = {r["nombre"]: r["id"] for r in rows}
        for local_id, nombre in _CAT_NOMBRE.items():
            if local_id not in cat_map and nombre in nombre_to_uuid:
                cat_map[local_id] = nombre_to_uuid[nombre]
    print(f"  OK - {len(cat_map)} categorias listas\n")
    return cat_map


def _build_unidad_cache(db) -> dict:
    rows = db.table("unidades_medida").select("id, simbolo").execute().data
    return {r["simbolo"]: r["id"] for r in rows}


def run() -> None:
    db = get_admin_client()
    cat_map = _seed_categorias(db)
    cache = _build_unidad_cache(db)
    advertencias: list[str] = []

    filas: list[dict] = []
    for p in PARAMETROS:
        sim = p.get("unidad_simbolo", "")
        uid = cache.get(sim)
        if uid is None and sim:
            advertencias.append(f"Unidad no encontrada: '{sim}' para {p['codigo']}")
        cat_local = p.get("categoria_id")
        cat_uuid = cat_map.get(cat_local) if cat_local else None
        filas.append({
            "codigo":              p["codigo"],
            "nombre":              p["nombre"],
            "categoria_id":        cat_uuid,
            "unidad_id":           uid,
            "descripcion":         p.get("nombre_corto", ""),
            "metodo_analitico":    p.get("metodo_referencia"),
            "activo":              True,
            # Metadata ECA (migración 010)
            "es_eca":              p.get("es_eca", True),
            "observacion_tecnica": p.get("observacion_tecnica"),
        })

    if advertencias:
        print(f"  ADVERTENCIAS ({len(advertencias)}):")
        for a in advertencias:
            print(f"    {a}")

    ok, errores = upsert_batch(db, "parametros", filas, "codigo")
    imprimir_resumen("SEED: parametros", len(PARAMETROS), ok, errores)


if __name__ == "__main__":
    run()
