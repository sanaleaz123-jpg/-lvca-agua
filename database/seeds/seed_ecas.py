"""
database/seeds/seed_ecas.py
6 ECAs del D.S. N 004-2017-MINAM con sus valores limite por parametro.
UPSERT idempotente por 'codigo' (ecas) y por (eca_id, parametro_id) (eca_valores).
Requiere que seed_parametros.py se haya ejecutado primero.

ECAs incluidos:
    ECA-C1A1  →  Categoria 1 A1  (agua potable por desinfeccion)
    ECA-C1A2  →  Categoria 1 A2  (agua potable con tratamiento convencional)
    ECA-C1A3  →  Categoria 1 A3  (agua potable con tratamiento avanzado)
    ECA-C3D1  →  Categoria 3 D1  (riego de cultivos)
    ECA-C4E1  →  Categoria 4 E1  (conservacion lagunas y lagos)
    ECA-C4E2  →  Categoria 4 E2  (conservacion rios)

Ejecutar:
    cd lvca_agua && python -m database.seeds.seed_ecas
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds._utils import upsert_batch, imprimir_resumen

# ─────────────────────────────────────────────────────────────────────────────
# 6 ECAs  (D.S. N 004-2017-MINAM)
# ─────────────────────────────────────────────────────────────────────────────
ECAS: list[dict] = [
    {
        "codigo": "ECA-C1A1",
        "nombre": "ECA Agua - Categoria 1 A1",
        "categoria": "Categoria 1",
        "subcategoria": "A1",
        "descripcion": (
            "Aguas superficiales destinadas a la produccion de agua potable "
            "mediante desinfeccion. Rios de cabecera de cuenca con calidad "
            "natural excepcional."
        ),
        "norma_legal": "D.S. N 004-2017-MINAM Anexo I",
        "activo": True,
    },
    {
        "codigo": "ECA-C1A2",
        "nombre": "ECA Agua - Categoria 1 A2",
        "categoria": "Categoria 1",
        "subcategoria": "A2",
        "descripcion": (
            "Aguas superficiales destinadas a la produccion de agua potable "
            "con tratamiento convencional: coagulacion, floculacion, "
            "sedimentacion, filtracion y desinfeccion."
        ),
        "norma_legal": "D.S. N 004-2017-MINAM Anexo I",
        "activo": True,
    },
    {
        "codigo": "ECA-C1A3",
        "nombre": "ECA Agua - Categoria 1 A3",
        "categoria": "Categoria 1",
        "subcategoria": "A3",
        "descripcion": (
            "Aguas superficiales destinadas a la produccion de agua potable "
            "con tratamiento avanzado: procesos fisicos, quimicos y biologicos "
            "que permiten eliminar contaminantes no removibles por tratamiento "
            "convencional."
        ),
        "norma_legal": "D.S. N 004-2017-MINAM Anexo I",
        "activo": True,
    },
    {
        "codigo": "ECA-C3D1",
        "nombre": "ECA Agua - Categoria 3 D1 Riego de cultivos",
        "categoria": "Categoria 3",
        "subcategoria": "D1",
        "descripcion": (
            "Agua para riego no restringido de cultivos alimenticios de "
            "consumo crudo, tallo alto y bajo, y pastos naturales o cultivados. "
            "Aplicable a irrigaciones del Proyecto Majes-Siguas AUTODEMA."
        ),
        "norma_legal": "D.S. N 004-2017-MINAM Anexo I",
        "activo": True,
    },
    {
        "codigo": "ECA-C4E1",
        "nombre": "ECA Agua - Categoria 4 E1 Lagunas y lagos",
        "categoria": "Categoria 4",
        "subcategoria": "E1",
        "descripcion": (
            "Conservacion del ambiente acuatico en lagunas y lagos. "
            "Aplicable a embalses altoandinos: Pillones, Pane, Frayle, "
            "Bamputane y Laguna de Salinas en la cuenca del Chili."
        ),
        "norma_legal": "D.S. N 004-2017-MINAM Anexo I",
        "activo": True,
    },
    {
        "codigo": "ECA-C4E2",
        "nombre": "ECA Agua - Categoria 4 E2 Rios",
        "categoria": "Categoria 4",
        "subcategoria": "E2",
        "descripcion": (
            "Conservacion del ambiente acuatico en rios de la region natural "
            "Costa y Sierra. Aplicable al rio Chili, rio Siguas y rio Colca "
            "en la cuenca hidrologica Chili-Quilca."
        ),
        "norma_legal": "D.S. N 004-2017-MINAM Anexo I",
        "activo": True,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# VALORES LIMITE POR ECA  (fuente: D.S. N 004-2017-MINAM Anexo I)
#
# Campos:
#   eca_codigo    str   codigo del ECA (clave foranea resuelta por codigo)
#   param_codigo  str   codigo del parametro (clave foranea resuelta por codigo)
#   valor_minimo  float valor minimo permitido (None si no aplica)
#   valor_maximo  float valor maximo permitido (None si no aplica)
#   valor_limite  str   valor cualitativo ("Ausencia", "<LMD", etc.)
#   observacion   str   nota aclaratoria
# ─────────────────────────────────────────────────────────────────────────────
ECA_VALORES: list[dict] = [

    # ══════════════════════════════════════════════════════════
    # ECA Categoria 1 A1  -  Desinfeccion
    # ══════════════════════════════════════════════════════════
    # Fisicoquimico in-situ
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P001", "valor_minimo": 6.5,  "valor_maximo": 8.5},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P002", "valor_maximo": 25.0, "observacion": "Delta T max 3 °C sobre condicion natural"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P003", "valor_maximo": 1500.0},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P004", "valor_minimo": 6.0},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P006", "valor_maximo": 5.0},
    # Fisicoquimico lab
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P011", "valor_maximo": 15.0},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P019", "valor_maximo": 3.0},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P020", "valor_maximo": 10.0},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P028", "valor_maximo": 25.0},
    # Nutrientes
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P031", "valor_maximo": 13.0,  "observacion": "mg N-NO3/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P032", "valor_maximo": 3.0,   "observacion": "mg N-NO2/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P033", "valor_maximo": 1.5,   "observacion": "mg N-NH4/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P036", "valor_maximo": 0.1,   "observacion": "mg P/L total"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P040", "valor_maximo": 2.4,   "observacion": "mg B/L"},
    # Iones
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P041", "valor_maximo": 250.0},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P042", "valor_maximo": 250.0},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P043", "valor_maximo": 1.5},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P044", "valor_maximo": 0.07},
    # Organicos
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P051", "valor_maximo": 0.5},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P052", "valor_maximo": 0.2},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P053", "valor_maximo": 0.003},
    # Metales
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P061", "valor_maximo": 0.2,   "observacion": "mg Al/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P062", "valor_maximo": 0.006, "observacion": "mg Sb/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P063", "valor_maximo": 0.01,  "observacion": "mg As/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P064", "valor_maximo": 0.7,   "observacion": "mg Ba/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P065", "valor_maximo": 0.04,  "observacion": "mg Be/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P068", "valor_maximo": 0.003, "observacion": "mg Cd/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P071", "valor_maximo": 0.05,  "observacion": "mg Cr VI/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P072", "valor_maximo": 2.0,   "observacion": "mg Cu/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P074", "valor_maximo": 0.3,   "observacion": "mg Fe/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P077", "valor_maximo": 0.1,   "observacion": "mg Mn/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P078", "valor_maximo": 0.001, "observacion": "mg Hg/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P079", "valor_maximo": 0.07,  "observacion": "mg Mo/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P080", "valor_maximo": 0.07,  "observacion": "mg Ni/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P081", "valor_maximo": 0.01,  "observacion": "mg Pb/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P083", "valor_maximo": 0.04,  "observacion": "mg Se/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P086", "valor_maximo": 0.0007,"observacion": "mg Tl/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P088", "valor_maximo": 0.1,   "observacion": "mg V/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P089", "valor_maximo": 3.0,   "observacion": "mg Zn/L"},
    {"eca_codigo": "ECA-C1A1", "param_codigo": "P090", "valor_maximo": 0.01,  "observacion": "mg Ag/L"},

    # ══════════════════════════════════════════════════════════
    # ECA Categoria 1 A2  -  Tratamiento convencional
    # ══════════════════════════════════════════════════════════
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P001", "valor_minimo": 5.5,   "valor_maximo": 9.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P002", "valor_maximo": 25.0,  "observacion": "Delta T max 3 °C"},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P003", "valor_maximo": 1600.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P004", "valor_minimo": 5.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P006", "valor_maximo": 100.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P011", "valor_maximo": 100.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P019", "valor_maximo": 5.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P020", "valor_maximo": 20.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P028", "valor_maximo": 100.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P031", "valor_maximo": 13.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P032", "valor_maximo": 3.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P033", "valor_maximo": 1.5},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P036", "valor_maximo": 0.2},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P040", "valor_maximo": 2.4},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P041", "valor_maximo": 300.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P042", "valor_maximo": 250.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P043", "valor_maximo": 1.5},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P044", "valor_maximo": 0.07},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P051", "valor_maximo": 1.7},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P052", "valor_maximo": 0.2},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P053", "valor_maximo": 0.01},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P061", "valor_maximo": 0.9},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P062", "valor_maximo": 0.006},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P063", "valor_maximo": 0.01},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P064", "valor_maximo": 0.7},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P068", "valor_maximo": 0.01},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P071", "valor_maximo": 0.05},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P072", "valor_maximo": 2.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P074", "valor_maximo": 1.0},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P077", "valor_maximo": 0.4},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P078", "valor_maximo": 0.002},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P080", "valor_maximo": 0.07},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P081", "valor_maximo": 0.05},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P083", "valor_maximo": 0.04},
    {"eca_codigo": "ECA-C1A2", "param_codigo": "P089", "valor_maximo": 3.0},

    # ══════════════════════════════════════════════════════════
    # ECA Categoria 1 A3  -  Tratamiento avanzado
    # ══════════════════════════════════════════════════════════
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P001", "valor_minimo": 5.5,   "valor_maximo": 9.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P002", "valor_maximo": 25.0,  "observacion": "Delta T max 3 °C"},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P003", "valor_maximo": 1600.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P004", "valor_minimo": 4.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P006", "valor_maximo": 500.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P019", "valor_maximo": 10.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P020", "valor_maximo": 30.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P028", "valor_maximo": 500.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P031", "valor_maximo": 13.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P033", "valor_maximo": 1.5},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P036", "valor_maximo": 1.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P040", "valor_maximo": 2.4},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P063", "valor_maximo": 0.15},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P068", "valor_maximo": 0.01},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P071", "valor_maximo": 0.05},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P074", "valor_maximo": 5.0},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P078", "valor_maximo": 0.002},
    {"eca_codigo": "ECA-C1A3", "param_codigo": "P081", "valor_maximo": 0.05},

    # ══════════════════════════════════════════════════════════
    # ECA Categoria 3 D1  -  Riego de cultivos
    # ══════════════════════════════════════════════════════════
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P001", "valor_minimo": 6.5,   "valor_maximo": 8.4},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P003", "valor_maximo": 2000.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P004", "valor_minimo": 4.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P006", "valor_maximo": 25.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P019", "valor_maximo": 15.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P028", "valor_maximo": 150.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P031", "valor_maximo": 13.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P033", "valor_maximo": 1.5},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P036", "valor_maximo": 5.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P040", "valor_maximo": 1.0,   "observacion": "Suelos sensibles. Suelos tolerantes: 4 mg B/L"},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P041", "valor_maximo": 300.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P042", "valor_maximo": 100.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P043", "valor_maximo": 1.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P044", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P051", "valor_maximo": 1.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P053", "valor_maximo": 0.001},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P060", "valor_maximo": 6.0,   "observacion": "RAS - relacion adsorcion sodio"},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P061", "valor_maximo": 5.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P062", "valor_maximo": 0.05},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P063", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P064", "valor_maximo": 0.7},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P065", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P068", "valor_maximo": 0.01},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P069", "valor_maximo": 0.05},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P070", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P072", "valor_maximo": 0.2},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P074", "valor_maximo": 5.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P075", "valor_maximo": 2.5},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P077", "valor_maximo": 0.2},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P078", "valor_maximo": 0.001},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P079", "valor_maximo": 0.01},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P080", "valor_maximo": 0.2},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P081", "valor_maximo": 5.0},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P083", "valor_maximo": 0.02},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P085", "valor_maximo": 200.0, "observacion": "mg Na/L"},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P088", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C3D1", "param_codigo": "P089", "valor_maximo": 2.0},

    # ══════════════════════════════════════════════════════════
    # ECA Categoria 4 E1  -  Conservacion lagunas y lagos
    # ══════════════════════════════════════════════════════════
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P001", "valor_minimo": 6.5,   "valor_maximo": 9.0},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P002", "valor_maximo": 22.0,  "observacion": "Delta T max 3 °C"},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P004", "valor_minimo": 5.0},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P006", "valor_maximo": 25.0},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P019", "valor_maximo": 5.0},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P031", "valor_maximo": 13.0},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P033", "valor_maximo": 0.02},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P036", "valor_maximo": 0.035},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P040", "valor_maximo": 0.5},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P044", "valor_maximo": 0.022},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P051", "valor_maximo": 0.5},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P053", "valor_maximo": 0.001},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P062", "valor_maximo": 0.006},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P063", "valor_maximo": 0.15,  "observacion": "mg As/L ecosistema acuatico"},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P064", "valor_maximo": 0.7},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P068", "valor_maximo": 0.004},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P071", "valor_maximo": 0.011},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P072", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P074", "valor_maximo": 1.0},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P077", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P078", "valor_maximo": 0.0001},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P080", "valor_maximo": 0.052},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P081", "valor_maximo": 1.0},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P083", "valor_maximo": 0.005},
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P089", "valor_maximo": 0.12},
    # Clorofila-a limite troficos
    {"eca_codigo": "ECA-C4E1", "param_codigo": "P124", "valor_maximo": 8.0,   "observacion": "ug/L clorofila-a estado mesotrofico"},

    # ══════════════════════════════════════════════════════════
    # ECA Categoria 4 E2  -  Conservacion rios
    # ══════════════════════════════════════════════════════════
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P001", "valor_minimo": 6.5,   "valor_maximo": 9.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P002", "valor_maximo": 25.0,  "observacion": "Delta T max 3 °C sobre condicion natural"},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P003", "valor_maximo": 2000.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P004", "valor_minimo": 5.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P006", "valor_maximo": 25.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P019", "valor_maximo": 10.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P028", "valor_maximo": 400.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P031", "valor_maximo": 13.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P033", "valor_maximo": 0.02},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P036", "valor_maximo": 0.05},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P040", "valor_maximo": 0.5},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P044", "valor_maximo": 0.022},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P051", "valor_maximo": 0.5},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P053", "valor_maximo": 0.001},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P062", "valor_maximo": 0.006},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P063", "valor_maximo": 0.15,  "observacion": "mg As/L proteccion vida acuatica"},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P064", "valor_maximo": 0.7},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P068", "valor_maximo": 0.004},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P071", "valor_maximo": 0.011},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P072", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P074", "valor_maximo": 1.0},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P077", "valor_maximo": 0.1},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P078", "valor_maximo": 0.0001},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P080", "valor_maximo": 0.052},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P081", "valor_maximo": 1.0,   "observacion": "mg Pb/L"},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P083", "valor_maximo": 0.005},
    {"eca_codigo": "ECA-C4E2", "param_codigo": "P089", "valor_maximo": 0.12},
]


def _build_maps(db) -> tuple[dict, dict]:
    eca_map = {r["codigo"]: r["id"]
               for r in db.table("ecas").select("id,codigo").execute().data}
    param_map = {r["codigo"]: r["id"]
                 for r in db.table("parametros").select("id,codigo").execute().data}
    return eca_map, param_map


def run() -> None:
    db = get_admin_client()

    # 1. ECAs
    ok_e, err_e = upsert_batch(db, "ecas", ECAS, "codigo")
    imprimir_resumen("SEED: ecas", len(ECAS), ok_e, err_e)

    # 2. Valores limite
    eca_map, param_map = _build_maps(db)
    filas_v: list[dict] = []
    sin_eca: list[str] = []
    sin_param: list[str] = []

    for v in ECA_VALORES:
        eca_id = eca_map.get(v["eca_codigo"])
        param_id = param_map.get(v["param_codigo"])
        if not eca_id:
            sin_eca.append(v["eca_codigo"])
            continue
        if not param_id:
            sin_param.append(f"{v['eca_codigo']}/{v['param_codigo']}")
            continue
        filas_v.append({
            "eca_id":       eca_id,
            "parametro_id": param_id,
            "valor_minimo": v.get("valor_minimo"),
            "valor_maximo": v.get("valor_maximo"),
        })

    if sin_eca:
        print(f"  ADVERTENCIA: ECAs no encontrados -> {set(sin_eca)}")
    if sin_param:
        print(f"  ADVERTENCIA: Parametros no encontrados -> {sin_param[:5]}")

    ok_v, err_v = upsert_batch(db, "eca_valores", filas_v, "eca_id,parametro_id")
    imprimir_resumen("SEED: eca_valores", len(ECA_VALORES), ok_v, err_v)


if __name__ == "__main__":
    run()
