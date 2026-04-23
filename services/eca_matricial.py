"""
services/eca_matricial.py
Lookup y cálculos para ECAs con dependencia bi-variable.

Caso de uso principal: NH3 libre en Cat 4 (E1 y E2) según Tabla N°1 del DS
004-2017-MINAM, que varía con pH y temperatura.

Funciones públicas:
    redondear_proximo_superior(valor, grilla)      — utilitaria de redondeo
    lookup_eca_matricial(eca_codigo, param_codigo, valor_x, valor_y)
                                                   — consulta en eca_valores_matriciales
    fraccion_nh3_libre(ph, t_celsius)              — equilibrio químico NH3/NH4+
    calcular_nh3_libre_desde_n_total(n_total, ph, t_celsius)
                                                   — convierte N amoniacal total -> NH3 libre
    evaluar_nh3_cat4(n_total_mg_l, ph, t_celsius, eca_codigo)
                                                   — orquestador alto nivel
"""

from __future__ import annotations

from typing import Optional
from database.client import get_admin_client


# ─────────────────────────────────────────────────────────────────────────────
# Grilla oficial de la Tabla N°1 (DS 004-2017-MINAM)
# ─────────────────────────────────────────────────────────────────────────────
GRILLA_PH: list[float] = [6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 10.0]
GRILLA_T:  list[float] = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]


def redondear_proximo_superior(valor: float, grilla: list[float]) -> Optional[float]:
    """
    Devuelve el elemento más pequeño de la grilla que sea >= valor.

    Semántica del DS: "redondear al próximo superior" en pH y T para aplicar
    la condición más extrema (más restrictiva). Ejemplos del DS:
        pH 7,8 -> 8,0
        T  14  -> 15
        pH 8,2 -> 8,5

    Si valor es menor que el mínimo de la grilla, retorna el mínimo (regla del
    DS: "si pH < 6 o T < 0, aplicar pH 6 y T 0").
    Si valor excede el máximo de la grilla, retorna None (fuera de alcance).
    """
    if valor <= grilla[0]:
        return grilla[0]
    for g in grilla:
        if g >= valor:
            return g
    return None  # valor > grilla[-1]


# ─────────────────────────────────────────────────────────────────────────────
# Lookup en BD (eca_valores_matriciales)
# ─────────────────────────────────────────────────────────────────────────────

def lookup_eca_matricial(
    eca_codigo: str,
    param_codigo: str,
    valor_x: float,
    valor_y: float,
    variable_x: str = "pH",
    variable_y: str = "temperatura_C",
) -> dict:
    """
    Busca en eca_valores_matriciales el valor ECA para el punto de grilla exacto
    (valor_x, valor_y). No redondea — eso es responsabilidad del caller.

    Retorna:
        {
            "valor": float | None,
            "expresado_como": str | None,
            "encontrado": bool,
            "motivo": str,
        }
    """
    db = get_admin_client()
    # Un solo query con joins ilativos vía códigos
    res = (
        db.table("eca_valores_matriciales")
        .select(
            "valor, expresado_como, "
            "ecas!inner(codigo), "
            "parametros!inner(codigo)"
        )
        .eq("ecas.codigo", eca_codigo)
        .eq("parametros.codigo", param_codigo)
        .eq("variable_x", variable_x)
        .eq("valor_x", valor_x)
        .eq("variable_y", variable_y)
        .eq("valor_y", valor_y)
        .maybe_single()
        .execute()
    )
    data = (res.data if res else None) or {}
    if not data:
        return {
            "valor": None,
            "expresado_como": None,
            "encontrado": False,
            "motivo": (
                f"No hay fila matricial para {eca_codigo}/{param_codigo} "
                f"en ({variable_x}={valor_x}, {variable_y}={valor_y})"
            ),
        }
    return {
        "valor": float(data["valor"]),
        "expresado_como": data.get("expresado_como"),
        "encontrado": True,
        "motivo": f"Punto exacto de Tabla N°1: {variable_x}={valor_x}, {variable_y}={valor_y}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Equilibrio químico NH3 ⇌ NH4+
# ─────────────────────────────────────────────────────────────────────────────

def fraccion_nh3_libre(ph: float, t_celsius: float) -> float:
    """
    Fracción de nitrógeno amoniacal que está como NH3 (no ionizado) en función
    de pH y T. Usa la ecuación de Emerson et al. (1975):

        pKa = 0,09018 + 2729,92 / T(K)
        f_NH3 = 1 / (1 + 10^(pKa - pH))

    Es la fórmula estándar citada por APHA SM 4500-NH3 y por USEPA. El DS no
    prescribe una fórmula específica — solo dice "equilibrio químico".
    """
    t_kelvin = t_celsius + 273.15
    pka = 0.09018 + 2729.92 / t_kelvin
    return 1.0 / (1.0 + 10.0 ** (pka - ph))


# Factor de conversión de nitrógeno (como N) a amoniaco (como NH3).
# Relación de masas molares: NH3 / N = 17,031 / 14,007 = 1,2159...
FACTOR_N_A_NH3 = 1.22


def calcular_nh3_libre_desde_n_total(
    n_amoniacal_total_mg_l: float,
    ph: float,
    t_celsius: float,
) -> dict:
    """
    Convierte un resultado de laboratorio de N amoniacal total (Nessler,
    SM 4500-NH3 B, en mg N/L) a NH3 libre (mg NH3/L) usando el equilibrio
    NH3/NH4+ a las condiciones de campo.

    Ejemplo del DS (Nota 3 del Excel):
        N total = 0,5 mg N/L, pH 7,8, T 14 °C
        fracción NH3 ≈ 1,1% del N total
        NH3 libre ≈ 0,5 × 0,011 ≈ 0,0055 mg N/L
                ≈ 0,0055 × 1,22 ≈ 0,0067 mg NH3/L
    """
    frac = fraccion_nh3_libre(ph, t_celsius)
    nh3_como_n = n_amoniacal_total_mg_l * frac
    nh3_como_nh3 = nh3_como_n * FACTOR_N_A_NH3
    return {
        "fraccion_nh3": frac,
        "nh3_como_n_mg_l": nh3_como_n,
        "nh3_libre_mg_l": nh3_como_nh3,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Orquestador de alto nivel: evaluación Cat 4 NH3
# ─────────────────────────────────────────────────────────────────────────────

def evaluar_nh3_cat4(
    n_amoniacal_total_mg_l: float,
    ph: float,
    t_celsius: float,
    eca_codigo: str,
    param_codigo: str = "P034",
) -> dict:
    """
    Evalúa el cumplimiento del ECA Cat 4 para NH3 libre, orquestando:
      1. Redondeo de pH y T al próximo superior — OPERACIÓN INTERNA EN MEMORIA:
         solo sirve para localizar la celda de la Tabla N°1 aplicable. Los
         valores pH y T medidos NO se modifican ni se persisten redondeados.
      2. Lookup del valor ECA en la Tabla N°1 seedeada (eca_valores_matriciales).
      3. Cálculo del NH3 libre usando los pH y T REALES (sin redondear) en el
         equilibrio químico NH3/NH4+.
      4. Comparación y diagnóstico.

    Ninguna operación de este helper escribe en la BD. Las mediciones in situ
    (muestras, mediciones_insitu) quedan tal cual se capturaron en campo.

    Retorna un dict con toda la información necesaria para la UI:
        {
            "puede_comparar":        bool,
            "motivo":                str,
            "ph_redondeado":         float | None,
            "t_redondeada":          float | None,
            "eca_valor_mg_nh3_l":    float | None,
            "fraccion_nh3":          float | None,
            "nh3_libre_mg_l":        float | None,
            "cumple":                bool | None,
            "eca_codigo":            str,
        }
    """
    resultado: dict = {
        "puede_comparar": False,
        "motivo": "",
        "ph_redondeado": None,
        "t_redondeada": None,
        "eca_valor_mg_nh3_l": None,
        "fraccion_nh3": None,
        "nh3_libre_mg_l": None,
        "cumple": None,
        "eca_codigo": eca_codigo,
    }

    if ph is None or t_celsius is None:
        resultado["motivo"] = (
            "Faltan mediciones in situ de pH y/o temperatura — requeridas "
            "por Tabla N°1 del DS 004-2017-MINAM para evaluar NH3 en Cat 4."
        )
        return resultado

    ph_r = redondear_proximo_superior(ph, GRILLA_PH)
    t_r = redondear_proximo_superior(t_celsius, GRILLA_T)
    if ph_r is None:
        resultado["motivo"] = (
            f"pH medido ({ph}) excede el máximo de la Tabla N°1 (10,0). "
            "Fuera del alcance del DS."
        )
        return resultado
    if t_r is None:
        resultado["motivo"] = (
            f"Temperatura medida ({t_celsius} °C) excede el máximo de la "
            "Tabla N°1 (30 °C). Fuera del alcance del DS."
        )
        return resultado

    resultado["ph_redondeado"] = ph_r
    resultado["t_redondeada"] = t_r

    lookup = lookup_eca_matricial(eca_codigo, param_codigo, ph_r, t_r)
    if not lookup["encontrado"]:
        resultado["motivo"] = lookup["motivo"]
        return resultado

    resultado["eca_valor_mg_nh3_l"] = lookup["valor"]

    calc = calcular_nh3_libre_desde_n_total(n_amoniacal_total_mg_l, ph, t_celsius)
    resultado["fraccion_nh3"] = calc["fraccion_nh3"]
    resultado["nh3_libre_mg_l"] = calc["nh3_libre_mg_l"]

    resultado["cumple"] = calc["nh3_libre_mg_l"] <= lookup["valor"]
    resultado["puede_comparar"] = True
    resultado["motivo"] = (
        f"pH={ph}→{ph_r}, T={t_celsius}→{t_r}°C. "
        f"ECA Tabla N°1 = {lookup['valor']} mg NH3/L. "
        f"Muestra: {calc['nh3_libre_mg_l']:.4f} mg NH3/L "
        f"(fracción NH3 = {calc['fraccion_nh3']*100:.2f}% del N total)."
    )
    return resultado
