"""
services/conversion_especies.py
Conversión entre especies químicas reportadas por el laboratorio y la especie
oficial que el DS 004-2017-MINAM exige para comparar contra el ECA.

Fuente de verdad:
    ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx (notas técnicas 3, 4, 6, 7, 9, 19)

Cuándo usar:
    Desde resultado_service.py, antes de comparar resultado de laboratorio
    con eca_valores.valor_maximo/minimo:

        >>> from services.conversion_especies import convertir_a_especie_eca
        >>> conv = convertir_a_especie_eca(
        ...     valor_lab=2.0,
        ...     unidad_simbolo="mg N-NO3/L",
        ...     expresado_como_eca="ion_NO3",
        ... )
        >>> if conv["puede_comparar"]:
        ...     cumple = conv["valor_convertido"] <= eca_valor_maximo
        ... else:
        ...     registrar_no_verificable(conv["motivo"])

Contexto (no se maneja aquí):
    - La conversión NH3_libre (Cat 4) depende de pH y T (Tabla N°1 del DS).
      Este helper detecta el caso y devuelve puede_comparar=False con motivo —
      la implementación matricial es el cambio #4 del plan (pendiente).
    - forma_analitica (total vs disuelta) no está modelada aún (cambio #9
      pendiente). Este helper no la valida.
"""

from __future__ import annotations
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Factores de conversión estequiométrica (masa molar de la especie / masa N o P)
# Fuente: pesos atómicos estándar IUPAC.
# ─────────────────────────────────────────────────────────────────────────────

# N = 14,007  →  NO3⁻ = 62,004  →  62,004/14,007 = 4,427
FACTOR_NO3_DESDE_N = 4.43

# N = 14,007  →  NO2⁻ = 46,005  →  46,005/14,007 = 3,285
FACTOR_NO2_DESDE_N = 3.28

# N = 14,007  →  NH3 = 17,031  →  17,031/14,007 = 1,216
FACTOR_NH3_DESDE_N = 1.22

# N = 14,007  →  NH4⁺ = 18,039  →  18,039/14,007 = 1,288
FACTOR_NH4_DESDE_N = 1.29

# P = 30,974  →  PO4³⁻ = 94,971  →  94,971/30,974 = 3,066
FACTOR_PO4_DESDE_P = 3.06


# ─────────────────────────────────────────────────────────────────────────────
# Mapa (unidad del resultado de laboratorio → "forma" interna)
# Solo incluye las unidades que aparecen en seed_parametros.py. Si llega una
# unidad no mapeada se retorna puede_comparar=False con motivo explícito.
# ─────────────────────────────────────────────────────────────────────────────
UNIDAD_A_FORMA_LAB: dict[str, str] = {
    "mg N-NO3/L":  "N_NO3",
    "mg N-NO2/L":  "N_NO2",
    "mg N-NH4/L":  "N_amoniacal_total",   # método Nessler SM 4500-NH3 B (P033)
    "mg NH3/L":    "NH3_libre",            # derivado de P033 + pH + T (P034)
    "mg P/L":      "P_total",
    "mg/L":        "sin_forma",            # unidad genérica
    "mg Fe/L":     "metal_total",
    "mg Mn/L":     "metal_total",
    "mg As/L":     "metal_total",
    "mg O2/L":     "sin_forma",
    "mg SO4/L":    "sin_forma",
    "mg CaCO3/L":  "sin_forma",
    "ug/L":        "sin_forma",
    "pH":          "sin_forma",
    "°C":          "sin_forma",
    "uS/cm":       "sin_forma",
    "NTU":         "sin_forma",
    "UCV":         "sin_forma",
}


# ─────────────────────────────────────────────────────────────────────────────
# Tabla de conversión: (forma_lab → expresado_como_eca) = factor multiplicativo
# Un valor None indica que la conversión no es numéricamente posible (se marca
# puede_comparar=False con motivo).
# ─────────────────────────────────────────────────────────────────────────────
_TABLA: dict[tuple[str, str], Optional[float]] = {
    # Nitratos
    ("N_NO3", "ion_NO3"):               FACTOR_NO3_DESDE_N,
    ("N_NO3", "N_NO3"):                 1.0,
    ("N_NO3", "suma_NO3N_NO2N_como_N"): 1.0,   # aproximación: solo NO3 si NO2 es despreciable
    # Nitritos
    ("N_NO2", "ion_NO2"):               FACTOR_NO2_DESDE_N,
    ("N_NO2", "N_NO2"):                 1.0,
    ("N_NO2", "suma_NO3N_NO2N_como_N"): 1.0,
    # Amoniaco — Nessler mide N amoniacal total (NH3 + NH4+). Parámetro P033.
    ("N_amoniacal_total", "N_amoniacal_total"): 1.0,
    # Amoniaco libre (P034, derivado): una vez calculado como NH3 libre, es comparación directa.
    # El cálculo pH×T → NH3 libre vive en otro módulo (pendiente cambio #4).
    ("NH3_libre", "NH3_libre"): 1.0,
    # Advertencia: si el lab reportó N amoniacal total y el ECA exige NH3 libre, la conversión
    # NO es lineal (depende de pH y T) — se bloquea abajo con motivo explícito.
    # Fósforo
    ("P_total", "P_total"): 1.0,
    # Metales (unidad del elemento)
    ("metal_total", "metal_total"): 1.0,
    # Pass-through para todo lo demás
    ("sin_forma", "sin_conversion"): 1.0,
}


def convertir_a_especie_eca(
    *,
    valor_lab: Optional[float],
    unidad_simbolo: str,
    expresado_como_eca: Optional[str],
    ph: Optional[float] = None,
    temperatura_celsius: Optional[float] = None,
    eca_codigo: Optional[str] = None,
) -> dict:
    """
    Convierte un resultado de laboratorio a la especie oficial del ECA.

    Parámetros:
        valor_lab: resultado numérico del laboratorio (None si es cualitativo).
        unidad_simbolo: unidad del parámetro (columna unidades_medida.simbolo).
        expresado_como_eca: especie oficial del DS (eca_valores.expresado_como).
            Si es None se asume "sin_conversion".
        ph, temperatura_celsius: mediciones in situ. Requeridas cuando la conversión
            es Nessler (N amoniacal total) → NH3 libre (Cat 4 del DS).
        eca_codigo: 'ECA-C4E1' o 'ECA-C4E2'. Requerido junto con pH y T para
            desencadenar el lookup matricial de Tabla N°1.

    Retorna dict:
        valor_convertido: float | None   valor listo para comparar con ECA
        factor:           float | None   factor multiplicativo aplicado (o None si no aplica)
        puede_comparar:   bool           True si se puede comparar con ECA
        motivo:           str            explicación (siempre, útil para UI)
        eca_matricial:    dict | None    presente solo cuando se aplicó lookup matricial
    """
    # Caso 1: valor_lab ausente → no hay nada que convertir.
    if valor_lab is None:
        return {
            "valor_convertido": None,
            "factor": None,
            "puede_comparar": False,
            "motivo": "Resultado de laboratorio no disponible",
        }

    # Caso 2: ECA sin especie declarada → se asume comparación directa.
    especie = expresado_como_eca or "sin_conversion"

    # Caso 3: lookup de la forma en que el laboratorio reportó.
    forma_lab = UNIDAD_A_FORMA_LAB.get(unidad_simbolo)
    if forma_lab is None:
        return {
            "valor_convertido": None,
            "factor": None,
            "puede_comparar": False,
            "motivo": f"Unidad '{unidad_simbolo}' no mapeada en conversion_especies",
        }

    # Caso 4: ECA exige NH3 libre pero el lab reportó N amoniacal total (Nessler).
    # La conversión NO es lineal — depende de pH y T (equilibrio NH3/NH4+).
    # Si recibimos pH, T y el código del ECA, delegamos al helper matricial.
    if especie == "NH3_libre" and forma_lab == "N_amoniacal_total":
        if ph is None or temperatura_celsius is None or eca_codigo is None:
            return {
                "valor_convertido": None,
                "factor": None,
                "puede_comparar": False,
                "motivo": (
                    "Cat 4 exige NH3 no ionizado (Tabla N°1 del DS 004-2017-MINAM). "
                    "El lab entregó N amoniacal total (Nessler). Para comparar se "
                    "requieren las mediciones in situ de pH, T y el código del ECA "
                    "(ECA-C4E1 o ECA-C4E2) — faltan parámetros."
                ),
            }

        # Importación diferida para evitar ciclo al arrancar el módulo.
        from services.eca_matricial import evaluar_nh3_cat4

        eva = evaluar_nh3_cat4(
            n_amoniacal_total_mg_l=valor_lab,
            ph=ph,
            t_celsius=temperatura_celsius,
            eca_codigo=eca_codigo,
        )
        if not eva["puede_comparar"]:
            return {
                "valor_convertido": None,
                "factor": None,
                "puede_comparar": False,
                "motivo": eva["motivo"],
                "eca_matricial": eva,
            }
        return {
            "valor_convertido": eva["nh3_libre_mg_l"],
            "factor": eva["fraccion_nh3"] * 1.22,  # factor efectivo (frac × N→NH3)
            "puede_comparar": True,
            "motivo": eva["motivo"],
            "eca_matricial": eva,
        }

    # Caso 5: lookup en tabla de factores
    factor = _TABLA.get((forma_lab, especie))
    if factor is None:
        return {
            "valor_convertido": None,
            "factor": None,
            "puede_comparar": False,
            "motivo": (
                f"Sin factor de conversión: el laboratorio reportó en forma "
                f"'{forma_lab}' pero el ECA se expresa como '{especie}'. "
                f"Revisar método analítico o eca_valores.expresado_como."
            ),
        }

    return {
        "valor_convertido": valor_lab * factor,
        "factor": factor,
        "puede_comparar": True,
        "motivo": (
            "Comparación directa" if factor == 1.0
            else f"Convertido de {forma_lab} a {especie} con factor ×{factor}"
        ),
    }
