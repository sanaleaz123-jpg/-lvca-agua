"""
database/seeds/seed_unidades.py
150 unidades de medida -- RED YAKU / LVCA AUTODEMA.
UPSERT idempotente por 'simbolo'. Usa get_admin_client() (omite RLS).

Ejecutar:
    cd lvca_agua && python -m database.seeds.seed_unidades
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds._utils import upsert_batch, imprimir_resumen

# Nota: se evitan caracteres Unicode no-ASCII en los simbolos (uS en vez de µS)
# para maxima compatibilidad con Supabase/Postgres.
UNIDADES: list[dict] = [
    # ── 1. Concentracion general (15) ─────────────────────────────────────────
    {"simbolo": "mg/L",         "nombre": "Miligramos por litro"},
    {"simbolo": "ug/L",         "nombre": "Microgramos por litro"},
    {"simbolo": "ng/L",         "nombre": "Nanogramos por litro"},
    {"simbolo": "pg/L",         "nombre": "Picogramos por litro"},
    {"simbolo": "g/L",          "nombre": "Gramos por litro"},
    {"simbolo": "g/m3",         "nombre": "Gramos por metro cubico"},
    {"simbolo": "mg/m3",        "nombre": "Miligramos por metro cubico"},
    {"simbolo": "ug/m3",        "nombre": "Microgramos por metro cubico"},
    {"simbolo": "kg/m3",        "nombre": "Kilogramos por metro cubico"},
    {"simbolo": "mg/kg",        "nombre": "Miligramos por kilogramo"},
    {"simbolo": "ug/kg",        "nombre": "Microgramos por kilogramo"},
    {"simbolo": "g/kg",         "nombre": "Gramos por kilogramo"},
    {"simbolo": "ng/kg",        "nombre": "Nanogramos por kilogramo"},
    {"simbolo": "mg/g",         "nombre": "Miligramos por gramo"},
    {"simbolo": "ppm",          "nombre": "Partes por millon",            "descripcion": "mg/kg en solidos"},

    # ── 2. Nutrientes y compuestos especificos (12) ───────────────────────────
    {"simbolo": "mg N/L",       "nombre": "Miligramos de nitrogeno por litro"},
    {"simbolo": "mg P/L",       "nombre": "Miligramos de fosforo por litro"},
    {"simbolo": "mg C/L",       "nombre": "Miligramos de carbono por litro"},
    {"simbolo": "mg N-NO3/L",   "nombre": "Miligramos de nitrogeno nitrico por litro"},
    {"simbolo": "mg N-NO2/L",   "nombre": "Miligramos de nitrogeno nitroso por litro"},
    {"simbolo": "mg N-NH4/L",   "nombre": "Miligramos de nitrogeno amoniacal por litro"},
    {"simbolo": "mg P-PO4/L",   "nombre": "Miligramos de fosforo como ortofosfato por litro"},
    {"simbolo": "mg O2/L",      "nombre": "Miligramos de oxigeno por litro"},
    {"simbolo": "mg CaCO3/L",   "nombre": "Miligramos de carbonato de calcio por litro"},
    {"simbolo": "mg Cl2/L",     "nombre": "Miligramos de cloro por litro"},
    {"simbolo": "mg SiO2/L",    "nombre": "Miligramos de silice por litro"},
    {"simbolo": "mg SO4/L",     "nombre": "Miligramos de sulfato por litro"},

    # ── 3. Metales en mg/L (28) ───────────────────────────────────────────────
    {"simbolo": "mg Al/L",      "nombre": "Miligramos de aluminio por litro"},
    {"simbolo": "mg As/L",      "nombre": "Miligramos de arsenico por litro"},
    {"simbolo": "mg B/L",       "nombre": "Miligramos de boro por litro"},
    {"simbolo": "mg Ba/L",      "nombre": "Miligramos de bario por litro"},
    {"simbolo": "mg Be/L",      "nombre": "Miligramos de berilio por litro"},
    {"simbolo": "mg Ca/L",      "nombre": "Miligramos de calcio por litro"},
    {"simbolo": "mg Cd/L",      "nombre": "Miligramos de cadmio por litro"},
    {"simbolo": "mg Co/L",      "nombre": "Miligramos de cobalto por litro"},
    {"simbolo": "mg Cr/L",      "nombre": "Miligramos de cromo total por litro"},
    {"simbolo": "mg Cu/L",      "nombre": "Miligramos de cobre por litro"},
    {"simbolo": "mg Fe/L",      "nombre": "Miligramos de hierro por litro"},
    {"simbolo": "mg Hg/L",      "nombre": "Miligramos de mercurio por litro"},
    {"simbolo": "mg K/L",       "nombre": "Miligramos de potasio por litro"},
    {"simbolo": "mg Li/L",      "nombre": "Miligramos de litio por litro"},
    {"simbolo": "mg Mg/L",      "nombre": "Miligramos de magnesio por litro"},
    {"simbolo": "mg Mn/L",      "nombre": "Miligramos de manganeso por litro"},
    {"simbolo": "mg Mo/L",      "nombre": "Miligramos de molibdeno por litro"},
    {"simbolo": "mg Na/L",      "nombre": "Miligramos de sodio por litro"},
    {"simbolo": "mg Ni/L",      "nombre": "Miligramos de niquel por litro"},
    {"simbolo": "mg Pb/L",      "nombre": "Miligramos de plomo por litro"},
    {"simbolo": "mg Sb/L",      "nombre": "Miligramos de antimonio por litro"},
    {"simbolo": "mg Se/L",      "nombre": "Miligramos de selenio por litro"},
    {"simbolo": "mg Si/L",      "nombre": "Miligramos de silicio por litro"},
    {"simbolo": "mg Sn/L",      "nombre": "Miligramos de estano por litro"},
    {"simbolo": "mg Tl/L",      "nombre": "Miligramos de talio por litro"},
    {"simbolo": "mg V/L",       "nombre": "Miligramos de vanadio por litro"},
    {"simbolo": "mg Zn/L",      "nombre": "Miligramos de zinc por litro"},
    {"simbolo": "mg Ag/L",      "nombre": "Miligramos de plata por litro"},

    # ── 4. Metales en ug/L (20) ───────────────────────────────────────────────
    {"simbolo": "ug Al/L",      "nombre": "Microgramos de aluminio por litro"},
    {"simbolo": "ug As/L",      "nombre": "Microgramos de arsenico por litro"},
    {"simbolo": "ug B/L",       "nombre": "Microgramos de boro por litro"},
    {"simbolo": "ug Ba/L",      "nombre": "Microgramos de bario por litro"},
    {"simbolo": "ug Be/L",      "nombre": "Microgramos de berilio por litro"},
    {"simbolo": "ug Cd/L",      "nombre": "Microgramos de cadmio por litro"},
    {"simbolo": "ug Co/L",      "nombre": "Microgramos de cobalto por litro"},
    {"simbolo": "ug Cr/L",      "nombre": "Microgramos de cromo por litro"},
    {"simbolo": "ug Cu/L",      "nombre": "Microgramos de cobre por litro"},
    {"simbolo": "ug Fe/L",      "nombre": "Microgramos de hierro por litro"},
    {"simbolo": "ug Hg/L",      "nombre": "Microgramos de mercurio por litro"},
    {"simbolo": "ug Mn/L",      "nombre": "Microgramos de manganeso por litro"},
    {"simbolo": "ug Mo/L",      "nombre": "Microgramos de molibdeno por litro"},
    {"simbolo": "ug Ni/L",      "nombre": "Microgramos de niquel por litro"},
    {"simbolo": "ug Pb/L",      "nombre": "Microgramos de plomo por litro"},
    {"simbolo": "ug Sb/L",      "nombre": "Microgramos de antimonio por litro"},
    {"simbolo": "ug Se/L",      "nombre": "Microgramos de selenio por litro"},
    {"simbolo": "ug Sn/L",      "nombre": "Microgramos de estano por litro"},
    {"simbolo": "ug Tl/L",      "nombre": "Microgramos de talio por litro"},
    {"simbolo": "ug V/L",       "nombre": "Microgramos de vanadio por litro"},

    # ── 5. Fisicas y electricas (18) ──────────────────────────────────────────
    {"simbolo": "NTU",          "nombre": "Unidades Nefelometricas de Turbidez"},
    {"simbolo": "FTU",          "nombre": "Unidades de Turbidez Formazina"},
    {"simbolo": "UCV",          "nombre": "Unidades de Color Verdadero"},
    {"simbolo": "UCO",          "nombre": "Unidades de Color Aparente"},
    {"simbolo": "U Pt-Co",      "nombre": "Unidades Platino-Cobalto"},
    {"simbolo": "U Hazen",      "nombre": "Unidades Hazen"},
    {"simbolo": "pH",           "nombre": "Potencial de hidrogeno",       "descripcion": "Escala adimensional 0-14"},
    {"simbolo": "gC",           "nombre": "Grados Celsius"},
    {"simbolo": "K",            "nombre": "Kelvin"},
    {"simbolo": "uS/cm",        "nombre": "Microsiemens por centimetro"},
    {"simbolo": "mS/cm",        "nombre": "Milisiemens por centimetro"},
    {"simbolo": "S/m",          "nombre": "Siemens por metro"},
    {"simbolo": "mV",           "nombre": "Milivoltios",                  "descripcion": "Potencial redox ORP"},
    {"simbolo": "% sat",        "nombre": "Porcentaje de saturacion de oxigeno"},
    {"simbolo": "%",            "nombre": "Porcentaje"},
    {"simbolo": "m",            "nombre": "Metros"},
    {"simbolo": "cm",           "nombre": "Centimetros"},
    {"simbolo": "mm",           "nombre": "Milimetros"},

    # ── 6. Biologicas y microbiologicas (20) ──────────────────────────────────
    {"simbolo": "UFC/100mL",    "nombre": "Unidades Formadoras de Colonias por 100 mL"},
    {"simbolo": "NMP/100mL",    "nombre": "Numero Mas Probable por 100 mL"},
    {"simbolo": "UFC/mL",       "nombre": "Unidades Formadoras de Colonias por mL"},
    {"simbolo": "NMP/mL",       "nombre": "Numero Mas Probable por mL"},
    {"simbolo": "UFC/L",        "nombre": "Unidades Formadoras de Colonias por litro"},
    {"simbolo": "org/L",        "nombre": "Organismos por litro"},
    {"simbolo": "cel/mL",       "nombre": "Celulas por mililitro"},
    {"simbolo": "cel/L",        "nombre": "Celulas por litro"},
    {"simbolo": "ind/m2",       "nombre": "Individuos por metro cuadrado"},
    {"simbolo": "ind/cm2",      "nombre": "Individuos por centimetro cuadrado"},
    {"simbolo": "org/m3",       "nombre": "Organismos por metro cubico"},
    {"simbolo": "ind/100m",     "nombre": "Individuos por 100 metros de transecto"},
    {"simbolo": "ind/m3",       "nombre": "Individuos por metro cubico"},
    {"simbolo": "oog/10L",      "nombre": "Ooquistes por 10 litros"},
    {"simbolo": "quistes/L",    "nombre": "Quistes por litro"},
    {"simbolo": "huevos/L",     "nombre": "Huevos de helmintos por litro"},
    {"simbolo": "virus/L",      "nombre": "Unidades formadoras de placa viral por litro"},
    {"simbolo": "ug/mL",        "nombre": "Microgramos por mililitro"},
    {"simbolo": "g/m2",         "nombre": "Gramos por metro cuadrado",   "descripcion": "Biomasa bentica"},
    {"simbolo": "CPUE",         "nombre": "Captura por unidad de esfuerzo (ind/100m-red/h)"},

    # ── 7. Indices biologicos y ecologicos (15) ───────────────────────────────
    {"simbolo": "bits/ind",     "nombre": "Bits por individuo - diversidad Shannon H prima"},
    {"simbolo": "score BMWP",   "nombre": "Puntaje indice biotico BMWP/Col"},
    {"simbolo": "score ABI",    "nombre": "Puntaje Andean Biotic Index"},
    {"simbolo": "score IBF",    "nombre": "Puntaje indice biotico de familias Hilsenhoff"},
    {"simbolo": "score IBD",    "nombre": "Puntaje indice de diatomeas Bellinger"},
    {"simbolo": "score IBI",    "nombre": "Puntaje indice de integridad biotica"},
    {"simbolo": "% EPT",        "nombre": "Porcentaje Ephemeroptera-Plecoptera-Trichoptera"},
    {"simbolo": "S taxa",       "nombre": "Riqueza de especies (numero de taxa)"},
    {"simbolo": "N ind",        "nombre": "Abundancia (numero total de individuos)"},
    {"simbolo": "J'",           "nombre": "Equidad de Pielou"},
    {"simbolo": "D Simpson",    "nombre": "Indice de dominancia de Simpson"},
    {"simbolo": "ICA",          "nombre": "Indice de calidad de agua (0-100)"},
    {"simbolo": "ISQA",         "nombre": "Indice simplificado de calidad de agua"},
    {"simbolo": "pts habitat",  "nombre": "Puntuacion de evaluacion de habitat ripario"},
    {"simbolo": "adim",         "nombre": "Adimensional"},

    # ── 8. Caudal y volumen (7) ───────────────────────────────────────────────
    {"simbolo": "m3/s",         "nombre": "Metros cubicos por segundo"},
    {"simbolo": "L/s",          "nombre": "Litros por segundo"},
    {"simbolo": "m3/h",         "nombre": "Metros cubicos por hora"},
    {"simbolo": "L/min",        "nombre": "Litros por minuto"},
    {"simbolo": "m3",           "nombre": "Metros cubicos"},
    {"simbolo": "L",            "nombre": "Litros"},
    {"simbolo": "hm3",          "nombre": "Hectometros cubicos"},

    # ── 9. Radiactividad (5) ──────────────────────────────────────────────────
    {"simbolo": "Bq/L",         "nombre": "Becquerel por litro"},
    {"simbolo": "mBq/L",        "nombre": "Milbecquerel por litro"},
    {"simbolo": "pCi/L",        "nombre": "Picocurie por litro"},
    {"simbolo": "Bq/m3",        "nombre": "Becquerel por metro cubico"},
    {"simbolo": "uSv/anio",     "nombre": "Microsievert por anio"},

    # ── 10. Especiales y molares (10) ─────────────────────────────────────────
    {"simbolo": "mEq/L",        "nombre": "Miliequivalentes por litro"},
    {"simbolo": "mmol/L",       "nombre": "Milimoles por litro"},
    {"simbolo": "umol/L",       "nombre": "Micromoles por litro"},
    {"simbolo": "nmol/L",       "nombre": "Nanomoles por litro"},
    {"simbolo": "PSU",          "nombre": "Unidades practicas de salinidad"},
    {"simbolo": "msnm",         "nombre": "Metros sobre el nivel del mar"},
    {"simbolo": "Ausencia",     "nombre": "Ausencia",                    "descripcion": "Resultado cualitativo negativo"},
    {"simbolo": "Presencia",    "nombre": "Presencia",                   "descripcion": "Resultado cualitativo positivo"},
    {"simbolo": "UFC/g",        "nombre": "Unidades Formadoras de Colonias por gramo"},
    {"simbolo": "NMP/g",        "nombre": "Numero Mas Probable por gramo"},
]


def run() -> None:
    assert len(UNIDADES) == 150, f"ERROR: se esperan 150 unidades, hay {len(UNIDADES)}"
    db = get_admin_client()
    filas = [
        {"simbolo": u["simbolo"], "nombre": u["nombre"],
         "descripcion": u.get("descripcion"), "activo": True}
        for u in UNIDADES
    ]
    ok, errores = upsert_batch(db, "unidades_medida", filas, "simbolo")
    imprimir_resumen("SEED: unidades_medida", len(UNIDADES), ok, errores)


if __name__ == "__main__":
    run()
