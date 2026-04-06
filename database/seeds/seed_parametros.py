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
    {"nombre": "Campo",           "descripcion": "Mediciones in situ con equipos de campo"},
    {"nombre": "Fisicoquimico",   "descripcion": "Parámetros físicos, químicos y metales analizados en laboratorio"},
    {"nombre": "Hidrobiologico",  "descripcion": "Organismos acuáticos indicadores de calidad"},
]

_CAT_NOMBRE = {1: "Campo", 2: "Fisicoquimico", 3: "Hidrobiologico"}

PARAMETROS: list[dict] = [

    # ════════════════════════════════════════════════════════
    # CATEGORÍA 1 — CAMPO (mediciones in situ)
    # ════════════════════════════════════════════════════════

    {"codigo": "P001", "nombre": "pH",
     "nombre_corto": "pH", "categoria_id": 1, "unidad_simbolo": "pH",
     "metodo_referencia": "SM 4500-H+ B electrométrico", "es_in_situ": True},

    {"codigo": "P002", "nombre": "Temperatura del agua",
     "nombre_corto": "Temp. agua", "categoria_id": 1, "unidad_simbolo": "gC",
     "metodo_referencia": "SM 2550 B", "es_in_situ": True},

    {"codigo": "P003", "nombre": "Conductividad/TDS/Salinidad",
     "nombre_corto": "C.E./TDS/Sal.", "categoria_id": 1, "unidad_simbolo": "uS/cm",
     "metodo_referencia": "SM 2510 B", "es_in_situ": True},

    {"codigo": "P004", "nombre": "Oxígeno Disuelto",
     "nombre_corto": "OD", "categoria_id": 1, "unidad_simbolo": "mg O2/L",
     "metodo_referencia": "SM 4500-O G electrométrico", "es_in_situ": True},

    {"codigo": "P006", "nombre": "Turbidez",
     "nombre_corto": "Turbidez", "categoria_id": 1, "unidad_simbolo": "NTU",
     "metodo_referencia": "SM 2130 B", "es_in_situ": True},

    # ════════════════════════════════════════════════════════
    # CATEGORÍA 2 — FISICOQUÍMICO (laboratorio)
    # ════════════════════════════════════════════════════════

    {"codigo": "P011", "nombre": "Color verdadero",
     "nombre_corto": "Color V.", "categoria_id": 2, "unidad_simbolo": "UCV",
     "metodo_referencia": "SM 2120 C espectrofotométrico"},

    {"codigo": "P019", "nombre": "DBO5",
     "nombre_corto": "DBO5", "categoria_id": 2, "unidad_simbolo": "mg O2/L",
     "metodo_referencia": "SM 5210 B Winkler modificado",
     "requiere_preservacion": True, "tipo_preservacion": "Refrigeración 4°C", "tiempo_max_analisis_horas": 48},

    {"codigo": "P025", "nombre": "Dureza total",
     "nombre_corto": "Dureza", "categoria_id": 2, "unidad_simbolo": "mg CaCO3/L",
     "metodo_referencia": "SM 2340 C EDTA titulación"},

    {"codigo": "P028", "nombre": "Sólidos suspendidos totales SST",
     "nombre_corto": "SST", "categoria_id": 2, "unidad_simbolo": "mg/L",
     "metodo_referencia": "SM 2540 D gravimétrico filtro 0.45um",
     "requiere_preservacion": True, "tipo_preservacion": "Refrigeración 4°C", "tiempo_max_analisis_horas": 168},

    {"codigo": "P031", "nombre": "Nitratos",
     "nombre_corto": "NO3-N", "categoria_id": 2, "unidad_simbolo": "mg N-NO3/L",
     "metodo_referencia": "SM 4500-NO3 B reducción cadmio",
     "requiere_preservacion": True, "tipo_preservacion": "H2SO4 pH<2 4°C", "tiempo_max_analisis_horas": 48},

    {"codigo": "P032", "nombre": "Nitritos",
     "nombre_corto": "NO2-N", "categoria_id": 2, "unidad_simbolo": "mg N-NO2/L",
     "metodo_referencia": "SM 4500-NO2 B colorimétrico", "tiempo_max_analisis_horas": 48},

    {"codigo": "P033", "nombre": "Amonio / Amoniaco",
     "nombre_corto": "N-NH4", "categoria_id": 2, "unidad_simbolo": "mg N-NH4/L",
     "metodo_referencia": "SM 4500-NH3 B Nessler",
     "requiere_preservacion": True, "tipo_preservacion": "H2SO4 pH<2 4°C", "tiempo_max_analisis_horas": 28},

    {"codigo": "P036", "nombre": "Fósforo total",
     "nombre_corto": "P-Total", "categoria_id": 2, "unidad_simbolo": "mg P/L",
     "metodo_referencia": "SM 4500-P B E ácido ascórbico",
     "requiere_preservacion": True, "tipo_preservacion": "H2SO4 pH<2 4°C", "tiempo_max_analisis_horas": 672},

    {"codigo": "P038", "nombre": "Fosfatos",
     "nombre_corto": "Fosfatos", "categoria_id": 2, "unidad_simbolo": "mg/L",
     "metodo_referencia": "SM 4500-P B ácido ascórbico"},

    {"codigo": "P041", "nombre": "Sulfatos",
     "nombre_corto": "Sulfatos", "categoria_id": 2, "unidad_simbolo": "mg SO4/L",
     "metodo_referencia": "SM 4500-SO4 E gravimétrico"},

    {"codigo": "P042", "nombre": "Cloruros",
     "nombre_corto": "Cloruros", "categoria_id": 2, "unidad_simbolo": "mg/L",
     "metodo_referencia": "SM 4500-Cl B argentométrico Mohr"},

    {"codigo": "P074", "nombre": "Hierro disuelto",
     "nombre_corto": "Fe", "categoria_id": 2, "unidad_simbolo": "mg Fe/L",
     "metodo_referencia": "SM 3111 B llama AAS fenantrolina",
     "requiere_preservacion": True, "tipo_preservacion": "HNO3 pH<2 4°C", "tiempo_max_analisis_horas": 4320},

    {"codigo": "P077", "nombre": "Manganeso disuelto",
     "nombre_corto": "Mn", "categoria_id": 2, "unidad_simbolo": "mg Mn/L",
     "metodo_referencia": "SM 3111 B llama AAS",
     "requiere_preservacion": True, "tipo_preservacion": "HNO3 pH<2 4°C", "tiempo_max_analisis_horas": 4320},

    {"codigo": "P091", "nombre": "Microcistina LR",
     "nombre_corto": "Microcistina", "categoria_id": 2, "unidad_simbolo": "ug/L",
     "metodo_referencia": "ELISA o HPLC-MS/MS",
     "requiere_preservacion": True, "tipo_preservacion": "Oscuridad -20°C", "tiempo_max_analisis_horas": 720},

    # ════════════════════════════════════════════════════════
    # CATEGORÍA 3 — HIDROBIOLÓGICO
    # ════════════════════════════════════════════════════════

    {"codigo": "P120", "nombre": "Fitoplancton",
     "nombre_corto": "Fitoplancton", "categoria_id": 3, "unidad_simbolo": "cel/mL",
     "metodo_referencia": "Utermohl microscopio invertido",
     "requiere_preservacion": True, "tipo_preservacion": "Lugol 1% 4°C", "tiempo_max_analisis_horas": 168},

    {"codigo": "P124", "nombre": "Clorofila A",
     "nombre_corto": "Cl-a", "categoria_id": 3, "unidad_simbolo": "ug/L",
     "metodo_referencia": "SM 10200 H acetona espectrofotometría",
     "requiere_preservacion": True, "tipo_preservacion": "Oscuridad -20°C", "tiempo_max_analisis_horas": 336},

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
            "codigo":           p["codigo"],
            "nombre":           p["nombre"],
            "categoria_id":     cat_uuid,
            "unidad_id":        uid,
            "descripcion":      p.get("nombre_corto", ""),
            "metodo_analitico": p.get("metodo_referencia"),
            "activo":           True,
        })

    if advertencias:
        print(f"  ADVERTENCIAS ({len(advertencias)}):")
        for a in advertencias:
            print(f"    {a}")

    ok, errores = upsert_batch(db, "parametros", filas, "codigo")
    imprimir_resumen("SEED: parametros", len(PARAMETROS), ok, errores)


if __name__ == "__main__":
    run()
