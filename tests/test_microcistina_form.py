"""
tests/test_microcistina_form.py
Pruebas del render del mapa de la placa (HTML puro, sin Streamlit).

`_placa_html` es una función pura que genera el mapa 8×12 de pocillos circulares;
se puede testear sin runtime de Streamlit.
"""

import re

import numpy as np

from services.elisa_microcistina import STD_CONC_UGL, CurvaParams, _model_4pl
from services.microcistina_import import mapa_placa, parse_placa_cruda
from components.microcistina_form import (
    _CONC_STOPS,
    _grad,
    _lum,
    _placa_html,
)

CURVA = CurvaParams(A=1.2, B=1.0, C=0.4, D=0.08, r2=1.0, sse=0.0)


def _od(c: float) -> float:
    return float(_model_4pl(
        np.array([CURVA.A, CURVA.B, CURVA.C, CURVA.D]), np.array([float(c)]))[0])


def _grid(n: int):
    g = [[0.0] * 12 for _ in range(8)]
    mp = mapa_placa()
    for i, (r, c1, c2) in enumerate(mp["std"]):
        g[r][c1] = g[r][c2] = _od(STD_CONC_UGL[i])
    cr, cc1, cc2 = mp["control"]
    g[cr][cc1] = g[cr][cc2] = _od(0.75)
    for k in range(1, n + 1):
        r, c1, c2 = mp["samples"][k]
        g[r][c1] = g[r][c2] = _od(0.4)
    return g


def _imp(n: int):
    imp = parse_placa_cruda(_grid(n))
    imp.muestras = imp.muestras[:n]
    return imp


class TestPlacaHtml:
    def test_96_pocillos_y_estructura(self):
        html = _placa_html(_imp(9), 9, usar_conc=False)
        assert html.count("mc-well") + html.count("mc-empty") == 96
        # 6 estándares + 1 control + 9 muestras = 16 roles × 2 réplicas = 32 con dato.
        assert html.count("mc-well") == 32
        assert html.count("mc-empty") == 64
        for lab in ("ST0", "ST5", "CT", "S1", "S9"):
            assert lab in html

    def test_chips_de_leyenda_por_vista(self):
        od = _placa_html(_imp(9), 9, usar_conc=False)
        cc = _placa_html(_imp(9), 9, usar_conc=True)
        # En OD no aparece el chip "Estándar" (van coloreados en el gradiente).
        assert "Estándar" not in od
        assert "Estándar" in cc and "Sobre rango" in cc

    def test_pocillo_sobre_rango_en_rojo(self):
        # Una muestra con OD muy baja (≤ D) → conc None → "sobre rango" → color fijo.
        g = _grid(9)
        mp = mapa_placa()
        r, c1, c2 = mp["samples"][9]
        g[r][c1] = g[r][c2] = 0.02   # S9 satura por debajo de D
        imp = parse_placa_cruda(g)
        imp.muestras = imp.muestras[:9]
        cc = _placa_html(imp, 9, usar_conc=True)
        assert "#7f1d1d" in cc       # color de "sobre rango"

    def test_grad_y_lum(self):
        assert re.fullmatch(r"#[0-9a-f]{6}", _grad(_CONC_STOPS, 0.3))
        assert _lum("#ffffff") > 0.9 and _lum("#000000") < 0.1
