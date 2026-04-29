"""
database/seeds/_valores_oficiales_ds.py
Valores oficiales del DS 004-2017-MINAM para las 4 subcategorías del PEIMS-LVCA
(A2, D1, E1, E2), transcritos del Excel ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx.

Fuente de verdad única para:
    - scripts/auditar_ecas_vs_excel.py  (comparación)
    - scripts/reconciliar_ecas_oficiales.py  (aplicación)
    - seed_ecas.py en futuras actualizaciones

Formato:
    OFICIAL[parametro_codigo][cat_sub] = (valor_min, valor_max, unidad_texto)

Convenciones:
    "NO_REGULADO" en valor_min  →  el DS NO regula este parámetro en esa subcat.
                                   Si la BD tiene una fila, debe eliminarse.
    None / None                 →  sin dato (no audita ni reconcilia)
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Valores del DS 004-2017-MINAM (Anexo I) — 4 subcategorías del PEIMS-LVCA
# ─────────────────────────────────────────────────────────────────────────────
OFICIAL: dict[str, dict[str, tuple]] = {
    "P001":  {  # pH
        "A2":  (5.5, 9.0, "pH"),
        "D1":  (6.5, 8.5, "pH"),
        "E1":  (6.5, 9.0, "pH"),
        "E2":  (6.5, 9.0, "pH"),
    },
    # P002 Temperatura: Δ3 respecto a línea base — NO valor absoluto. Fuera del audit.
    "P003":  {  # Conductividad
        "A2":  (None, 1600.0, "uS/cm"),
        "D1":  (None, 2500.0, "uS/cm"),
        "E1":  (None, 1000.0, "uS/cm"),
        "E2":  (None, 1000.0, "uS/cm"),
    },
    "P004":  {  # OD (valor mínimo)
        "A2":  (5.0, None, "mg O2/L"),
        "D1":  (4.0, None, "mg O2/L"),
        "E1":  (5.0, None, "mg O2/L"),
        "E2":  (5.0, None, "mg O2/L"),
    },
    "P006":  {  # Turbidez
        "A2":  (None, 100.0, "UNT"),
        "D1":  ("NO_REGULADO", None, "UNT"),
        "E1":  ("NO_REGULADO", None, "UNT"),
        "E2":  ("NO_REGULADO", None, "UNT"),
    },
    "P010":  {  # Color verdadero (Pt/Co) — código P010 tras consolidación (migración 018)
        "A2":  (None, 100.0, "Pt/Co"),
        "D1":  (None, 100.0, "Pt/Co"),
        "E1":  (None, 20.0,  "Pt/Co"),
        "E2":  (None, 20.0,  "Pt/Co"),
    },
    "P019":  {  # DBO5
        "A2":  (None, 5.0,  "mg O2/L"),
        "D1":  (None, 15.0, "mg O2/L"),
        "E1":  (None, 5.0,  "mg O2/L"),
        "E2":  (None, 10.0, "mg O2/L"),
    },
    "P025":  {  # Dureza — solo Cat 1-A1 regula (500). Las 4 del LVCA: no regulado.
        "A2":  ("NO_REGULADO", None, "mg CaCO3/L"),
        "D1":  ("NO_REGULADO", None, "mg CaCO3/L"),
        "E1":  ("NO_REGULADO", None, "mg CaCO3/L"),
        "E2":  ("NO_REGULADO", None, "mg CaCO3/L"),
    },
    "P028":  {  # SST (mg/L) — solo Cat 4
        "A2":  ("NO_REGULADO", None, "mg/L"),
        "D1":  ("NO_REGULADO", None, "mg/L"),
        "E1":  (None, 25.0,  "mg/L"),
        "E2":  (None, 100.0, "mg/L"),          # E2 costa/sierra (selva 400 no aplica LVCA)
    },
    "P031":  {  # Nitratos — ojo: especies distintas por categoría
        "A2":  (None, 50.0,  "mg NO3-/L (ion)"),
        "D1":  (None, 100.0, "mg N/L (suma NO3-N + NO2-N)"),
        "E1":  (None, 13.0,  "mg NO3-/L (ion)"),
        "E2":  (None, 13.0,  "mg NO3-/L (ion)"),
    },
    "P032":  {  # Nitritos
        "A2":  (None, 3.0,  "mg NO2-/L (ion)"),
        "D1":  (None, 10.0, "mg N/L (como N)"),
        "E1":  ("NO_REGULADO", None, "mg NO2-/L"),
        "E2":  ("NO_REGULADO", None, "mg NO2-/L"),
    },
    "P033":  {  # Amoniaco / N amoniacal total (Nessler)
        "A2":  (None, 1.5, "mg N/L (N-NH3 total)"),
        "D1":  ("NO_REGULADO", None, "—"),
        "E1":  ("NO_REGULADO", None, "—"),   # Cat 4 regula NH3 libre via P034 (matricial)
        "E2":  ("NO_REGULADO", None, "—"),
    },
    "P036":  {  # Fósforo Total
        "A2":  (None, 0.15,  "mg P/L"),
        "D1":  ("NO_REGULADO", None, "mg P/L"),
        "E1":  (None, 0.035, "mg P/L"),      # lagunas — muy restrictivo
        "E2":  (None, 0.05,  "mg P/L"),
    },
    "P038":  {  # Fosfatos — NO ECA (el DS regula Fósforo Total, no PO4)
        "A2":  ("NO_REGULADO", None, "—"),
        "D1":  ("NO_REGULADO", None, "—"),
        "E1":  ("NO_REGULADO", None, "—"),
        "E2":  ("NO_REGULADO", None, "—"),
    },
    "P041":  {  # Sulfatos
        "A2":  (None, 500.0,  "mg SO4/L"),
        "D1":  (None, 1000.0, "mg SO4/L"),
        "E1":  ("NO_REGULADO", None, "mg SO4/L"),
        "E2":  ("NO_REGULADO", None, "mg SO4/L"),
    },
    "P042":  {  # Cloruros
        "A2":  (None, 250.0, "mg/L"),
        "D1":  (None, 500.0, "mg/L"),
        "E1":  ("NO_REGULADO", None, "mg/L"),
        "E2":  ("NO_REGULADO", None, "mg/L"),
    },
    "P063":  {  # Arsénico total
        "A2":  (None, 0.01, "mg As/L"),
        "D1":  (None, 0.10, "mg As/L"),
        "E1":  (None, 0.15, "mg As/L"),
        "E2":  (None, 0.15, "mg As/L"),
    },
    "P074":  {  # Hierro total (ojo: nombre del param es "Hierro disuelto" pero DS exige total)
        "A2":  (None, 1.0, "mg Fe/L"),
        "D1":  (None, 5.0, "mg Fe/L"),
        "E1":  ("NO_REGULADO", None, "mg Fe/L"),
        "E2":  ("NO_REGULADO", None, "mg Fe/L"),
    },
    "P077":  {  # Manganeso total
        "A2":  (None, 0.4, "mg Mn/L"),
        "D1":  (None, 0.2, "mg Mn/L"),       # más restrictivo por fitotoxicidad
        "E1":  ("NO_REGULADO", None, "mg Mn/L"),
        "E2":  ("NO_REGULADO", None, "mg Mn/L"),
    },
    "P091":  {  # Microcistina-LR — solo A2 = 1 ug/L (= 0.001 mg/L)
        "A2":  (None, 1.0, "ug/L"),
        "D1":  ("NO_REGULADO", None, "ug/L"),
        "E1":  ("NO_REGULADO", None, "ug/L"),
        "E2":  ("NO_REGULADO", None, "ug/L"),
    },
    "P124":  {  # Clorofila A — solo E1
        "A2":  ("NO_REGULADO", None, "ug/L"),
        "D1":  ("NO_REGULADO", None, "ug/L"),
        "E1":  (None, 8.0, "ug/L"),          # 0.008 mg/L = 8 ug/L
        "E2":  ("NO_REGULADO", None, "ug/L"),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Especie química oficial (expresado_como) por (parámetro × subcategoría).
# Solo se declara donde importa (nutrientes y metales con forma analítica);
# None significa "comparación directa por unidad tal cual".
# ─────────────────────────────────────────────────────────────────────────────
ESPECIE_OFICIAL: dict[str, dict[str, str | None]] = {
    "P031": {  # Nitratos
        "A2": "ion_NO3",
        "D1": "suma_NO3N_NO2N_como_N",
        "E1": "ion_NO3",
        "E2": "ion_NO3",
    },
    "P032": {  # Nitritos
        "A2": "ion_NO2",
        "D1": "N_NO2",
    },
    "P033": {  # N amoniacal total (solo Cat 1)
        "A2": "N_amoniacal_total",
    },
    "P036": {  # P total
        "A2": "P_total",
        "E1": "P_total",
        "E2": "P_total",
    },
    "P063": {p: "metal_total" for p in ("A2", "D1", "E1", "E2")},
    "P074": {p: "metal_total" for p in ("A2", "D1")},
    "P077": {p: "metal_total" for p in ("A2", "D1")},
}


def especie_para(param_codigo: str, cat_sub: str) -> str | None:
    """Retorna la especie oficial declarada por el DS para (param, cat_sub), o None."""
    return ESPECIE_OFICIAL.get(param_codigo, {}).get(cat_sub)
