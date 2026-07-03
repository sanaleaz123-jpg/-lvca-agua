"""
tests/test_microcistina_import.py
Pruebas de la importación de placas ELISA con cantidad variable de muestras.

Cubren la distribución fija de la placa (`mapa_placa`), la detección automática
del número de muestras cargadas (`detectar_n_muestras`) y el recorte que hace
`parse_placa_cruda` sobre una placa con pocillos vacíos al final. Cálculo puro,
sin BD ni Streamlit.
"""

import numpy as np

from services.elisa_microcistina import STD_CONC_UGL, CurvaParams, _model_4pl
from services.microcistina_import import (
    CAPACIDAD_MUESTRAS,
    detectar_n_muestras,
    mapa_placa,
    parse_placa_cruda,
)

# Curva 4PL conocida para fabricar ODs realistas.
CURVA = CurvaParams(A=1.2, B=1.0, C=0.4, D=0.08, r2=1.0, sse=0.0)


def _od(conc: float) -> float:
    """OD del modelo 4PL para una concentración dada."""
    return float(_model_4pl(
        np.array([CURVA.A, CURVA.B, CURVA.C, CURVA.D]), np.array([float(conc)]),
    )[0])


def _grid(n_muestras: int, sample_conc: float = 0.5, empty_od: float = 0.0):
    """Placa 8×12: estándares + control + `n_muestras` cargadas; resto vacío."""
    g = [[empty_od] * 12 for _ in range(8)]
    mapa = mapa_placa()
    for i, (r, c1, c2) in enumerate(mapa["std"]):
        v = _od(STD_CONC_UGL[i])
        g[r][c1] = g[r][c2] = v
    cr, cc1, cc2 = mapa["control"]
    v = _od(0.75)
    g[cr][cc1] = g[cr][cc2] = v
    for n in range(1, n_muestras + 1):
        r, c1, c2 = mapa["samples"][n]
        vv = _od(sample_conc)
        g[r][c1] = g[r][c2] = vv
    return g


# ── Distribución fija de la placa ────────────────────────────────────────────
class TestMapaPlaca:
    def test_capacidad_es_41(self):
        assert CAPACIDAD_MUESTRAS == 41

    def test_41_muestras_numeradas_1_a_41(self):
        assert set(mapa_placa()["samples"].keys()) == set(range(1, 42))

    def test_cubre_las_96_celdas_sin_colisiones(self):
        mapa = mapa_placa()
        posiciones = list(mapa["std"]) + [mapa["control"]] + list(mapa["samples"].values())
        cells = set()
        for (r, c1, c2) in posiciones:
            for c in (c1, c2):
                assert (r, c) not in cells, f"colisión en fila {r}, col {c}"
                cells.add((r, c))
        assert len(cells) == 96


# ── Detección automática del nº de muestras ──────────────────────────────────
class TestDetectarNMuestras:
    def test_placa_llena_devuelve_41(self):
        assert detectar_n_muestras(_grid(41), CURVA) == 41

    def test_cola_vacia_descuenta(self):
        # 30 cargadas, 11 pocillos vacíos al final.
        assert detectar_n_muestras(_grid(30), CURVA) == 30

    def test_una_sola_muestra(self):
        assert detectar_n_muestras(_grid(1), CURVA) == 1

    def test_placa_sin_muestras_minimo_uno(self):
        assert detectar_n_muestras(_grid(0), CURVA) == 1


# ── parse_placa_cruda: detección + grilla guardada ───────────────────────────
class TestParsePlacaCruda:
    def test_detecta_y_conserva_placa(self):
        imp = parse_placa_cruda(_grid(25))
        assert imp.n_muestras_detectadas == 25
        assert imp.placa_od is not None
        assert len(imp.placa_od) == 8 and all(len(f) == 12 for f in imp.placa_od)

    def test_muestras_cargadas_en_rango_y_sobrantes_vacias(self):
        imp = parse_placa_cruda(_grid(25))
        # La placa se procesa completa (41); la UI recorta a las cargadas.
        assert len(imp.muestras) == CAPACIDAD_MUESTRAS
        # Las 25 cargadas caen en rango; las sobrantes (OD 0 → "muy concentrada")
        # quedan sin concentración.
        cargadas = imp.muestras[:25]
        sobrantes = imp.muestras[25:]
        assert all(m.conc_ugL is not None for m in cargadas)
        assert all(m.conc_ugL is None for m in sobrantes)
