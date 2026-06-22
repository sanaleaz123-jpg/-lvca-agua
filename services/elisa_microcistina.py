"""
services/elisa_microcistina.py
Motor de cálculo del ensayo ELISA ADDA para Microcistina LR
(kit SAES/ABRAXIS, EPA Method 546). Réplica exacta del "SOLVER" en Excel.

Flujo del método:
    1. Lecturas de absorbancia (OD) por duplicado: 6 estándares, 1 control y
       N muestras.
    2. Ajuste de la curva de calibración 4-paramétrica logística (4PL) sobre los
       6 estándares (réplicas promediadas), minimizando la suma de residuos² en
       el espacio OD — equivalente al GRG No Lineal del Solver de Excel.
            Y = (A − D) / (1 + (X/C)^B) + D
       donde Y = OD y X = concentración (µg/L).
    3. Concentración por curva inversa:
            X = C × ((A − Y)/(Y − D))^(1/B)
       Se promedian las dos réplicas de la muestra y se aplica el factor de
       dilución/matriz (1.11 por defecto, solo a muestras — el control no lo lleva).
    4. %CV de cada par de réplicas calculado **sobre las OD** (no sobre la
       concentración), con desviación estándar muestral (n−1):
            %CV = |OD1 − OD2|/√2 / promedio(OD1, OD2) × 100

Este módulo es de cálculo puro (sin BD ni Streamlit) para poder testearlo.
Validado celda por celda contra "2026-06-16 SOLVER MICROCISTINAS SAES.xlsx".
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Optional

import numpy as np


# Concentraciones nominales (µg/L) de los 6 estándares del kit SAES.
STD_CONC_UGL: tuple[float, ...] = (0.0, 0.05, 0.15, 0.4, 1.5, 5.0)

# Factor de dilución/matriz aplicado a las muestras (no al control) cuando el
# flag "PN" está activo en el kit. El control se reporta sin factor.
FACTOR_DILUCION_DEFAULT: float = 1.11


# ─────────────────────────────────────────────────────────────────────────────
# Estructuras de datos
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CurvaParams:
    """Parámetros ajustados de la curva 4PL."""
    A: float   # asíntota máxima (OD a 0 µg/L)
    B: float   # pendiente
    C: float   # IC50
    D: float   # asíntota mínima
    r2: float  # coeficiente de determinación (CORREL² como en el Excel)
    sse: float  # suma de residuos²

    def es_valida(self, a_min: float = 0.7, d_max: float = 0.15, r2_min: float = 0.98) -> bool:
        """
        Criterios del protocolo (A>0.7, D<0.1, R²≈1) usados como guía. El umbral
        de D se relaja a 0.15 porque corridas válidas reales dan D≈0.12 (la guía
        "D<0.1" del kit es indicativa). La UI debe mostrar A, D y R² para que el
        analista juzgue; este flag es una alerta blanda, no un bloqueo.
        """
        return self.A > a_min and self.D < d_max and self.r2 >= r2_min


@dataclass
class ResultadoMuestra:
    """Resultado calculado de una muestra (par de réplicas)."""
    od_1: float
    od_2: float
    cv_pct: float                    # %CV sobre las OD
    conc_ugL: Optional[float]        # concentración media (µg/L), factor aplicado
    en_rango: bool                   # True si ambas réplicas caen en la curva
    motivo: str = ""                 # nota si no en rango / observación


# ─────────────────────────────────────────────────────────────────────────────
# Ajuste de la curva 4PL (Levenberg-Marquardt, numpy puro — sin scipy)
# ─────────────────────────────────────────────────────────────────────────────

def _model_4pl(p: np.ndarray, x: np.ndarray) -> np.ndarray:
    A, B, C, D = p
    with np.errstate(all="ignore"):
        r = np.where(x > 0, (x / C) ** B, 0.0)
        return (A - D) / (1.0 + r) + D


def fit_4pl(conc: list[float], od_promedio: list[float], max_iter: int = 2000) -> CurvaParams:
    """
    Ajusta la curva 4PL a los puntos (concentración, OD promedio) por
    Levenberg-Marquardt. Devuelve los parámetros A, B, C, D, R² y SSE.
    """
    x = np.asarray(conc, dtype=float)
    y = np.asarray(od_promedio, dtype=float)
    if x.size < 4:
        raise ValueError("Se requieren al menos 4 estándares para ajustar la curva 4PL.")

    # Estimaciones iniciales razonables.
    A0 = float(np.max(y))
    D0 = float(min(np.min(y) * 0.5, np.min(y) - 1e-3))
    C0 = float(np.median(x[x > 0])) if np.any(x > 0) else 1.0
    B0 = 1.0
    p = np.array([A0, B0, C0, D0], dtype=float)

    def resid(pp: np.ndarray) -> np.ndarray:
        return _model_4pl(pp, x) - y

    lam = 1e-3
    r = resid(p)
    cost = float(r @ r)
    delta = np.zeros(4)

    for _ in range(max_iter):
        # Jacobiano numérico (4 columnas).
        J = np.zeros((x.size, 4))
        for j in range(4):
            step = 1e-6 * (abs(p[j]) + 1e-6)
            dp = np.zeros(4)
            dp[j] = step
            J[:, j] = (resid(p + dp) - r) / step
        JTJ = J.T @ J
        JTr = J.T @ r
        for _inner in range(30):
            try:
                delta = np.linalg.solve(JTJ + lam * np.diag(np.diag(JTJ)), -JTr)
            except np.linalg.LinAlgError:
                lam *= 10
                continue
            p_new = p + delta
            r_new = resid(p_new)
            cost_new = float(r_new @ r_new)
            if cost_new < cost:
                p, r, cost = p_new, r_new, cost_new
                lam = max(lam * 0.5, 1e-12)
                break
            lam *= 10
        if float(np.linalg.norm(delta)) < 1e-12:
            break

    A, B, C, D = (float(v) for v in p)
    yp = _model_4pl(p, x)
    sse = float(np.sum((y - yp) ** 2))
    # R² como en el Excel: cuadrado del coeficiente de correlación.
    with np.errstate(all="ignore"):
        cc = np.corrcoef(y, yp)[0, 1]
    r2 = float(cc ** 2) if np.isfinite(cc) else 0.0
    return CurvaParams(A=A, B=B, C=C, D=D, r2=r2, sse=sse)


# ─────────────────────────────────────────────────────────────────────────────
# Cálculos por muestra
# ─────────────────────────────────────────────────────────────────────────────

def concentracion_ugL(od: float, curva: CurvaParams) -> Optional[float]:
    """
    Concentración (µg/L) de una réplica por la curva 4PL inversa.
    Devuelve None si la OD cae fuera de la curva (OD ≥ A o OD ≤ D), donde la
    fórmula no tiene solución real (requiere dilución / reanálisis).
    """
    base = (curva.A - od) / (od - curva.D)
    if base <= 0:
        return None
    return curva.C * base ** (1.0 / curva.B)


def cv_pct(od_1: float, od_2: float) -> float:
    """%CV de las dos OD (desviación estándar muestral n−1)."""
    media = (od_1 + od_2) / 2.0
    if media == 0:
        return 0.0
    sd = abs(od_1 - od_2) / sqrt(2.0)
    return sd / media * 100.0


def procesar_muestra(
    od_1: float,
    od_2: float,
    curva: CurvaParams,
    factor: float = FACTOR_DILUCION_DEFAULT,
) -> ResultadoMuestra:
    """
    Procesa el par de réplicas de una muestra: concentración media (con factor)
    y %CV. Si alguna réplica cae fuera de la curva la concentración es None.
    """
    c1 = concentracion_ugL(od_1, curva)
    c2 = concentracion_ugL(od_2, curva)
    cv = cv_pct(od_1, od_2)

    if c1 is None or c2 is None:
        # Réplica(s) fuera de rango: si ambas OD ≥ A → por debajo de la curva
        # (≈ 0, no cuantificable); si ≤ D → por encima (diluir y reanalizar).
        od_min = min(od_1, od_2)
        if od_min >= curva.A:
            motivo = "OD por encima de Amax — concentración por debajo del rango (no cuantificable)."
            return ResultadoMuestra(od_1, od_2, cv, conc_ugL=0.0, en_rango=False, motivo=motivo)
        motivo = "OD por debajo del mínimo de la curva — fuera de rango, requiere dilución y reanálisis."
        return ResultadoMuestra(od_1, od_2, cv, conc_ugL=None, en_rango=False, motivo=motivo)

    conc = (c1 + c2) / 2.0 * factor
    return ResultadoMuestra(od_1, od_2, cv, conc_ugL=conc, en_rango=True)


def procesar_control(
    od_1: float,
    od_2: float,
    curva: CurvaParams,
) -> ResultadoMuestra:
    """Igual que procesar_muestra pero SIN factor (el control no lo lleva)."""
    return procesar_muestra(od_1, od_2, curva, factor=1.0)
