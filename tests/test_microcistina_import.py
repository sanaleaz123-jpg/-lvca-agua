"""
tests/test_microcistina_import.py
Pruebas de la importación de placas ELISA con cantidad variable de muestras.

Cubren la distribución fija de la placa (`mapa_placa`), la detección automática
del número de muestras cargadas (`detectar_n_muestras`) y el recorte que hace
`parse_placa_cruda` sobre una placa con pocillos vacíos al final. Cálculo puro,
sin BD ni Streamlit.
"""

import numpy as np

import pytest

from services.elisa_microcistina import STD_CONC_UGL, CurvaParams, _model_4pl
from services.microcistina_import import (
    CAPACIDAD_MUESTRAS,
    detectar_n_muestras,
    mapa_placa,
    parse_grid_text,
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

    def test_curva_es_opcional(self):
        # El umbral es fijo; la curva ya no es necesaria.
        assert detectar_n_muestras(_grid(30)) == 30

    def test_muestra_saturada_baja_od_no_se_descarta(self):
        # Regresión: una muestra real muy tóxica satura con OD baja (cerca del
        # mínimo de la curva D, p.ej. 0.05) pero por encima del baseline. NO debe
        # contarse como pozo vacío ni descartarse (antes el umbral D*0.5 la perdía).
        g = _grid(9)                      # S1..S9 con OD alta
        mapa = mapa_placa()
        r, c1, c2 = mapa["samples"][10]
        g[r][c1] = g[r][c2] = 0.05        # S10 saturada, OD baja pero > baseline
        assert detectar_n_muestras(g) == 10

    def test_una_replica_con_senal_no_se_descarta(self):
        # Un pozo se cuenta vacío solo si AMBAS réplicas están bajo el baseline.
        g = _grid(9)
        mapa = mapa_placa()
        r, c1, c2 = mapa["samples"][10]
        g[r][c1], g[r][c2] = 0.0, 0.5     # una réplica con señal
        assert detectar_n_muestras(g) == 10


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


# ── Pegado de placa parcial (parse_grid_text) ────────────────────────────────
# Placa real pegada por el usuario: 8 filas × 4 columnas (estándares + control
# + 9 muestras). Las columnas 5-12 no se corrieron.
_TEXTO_PARCIAL = """
0.959 1.002 0.919 0.866
0.861 0.806 0.85 0.92
0.725 0.737 0.932 0.96
0.551 0.572 0.572 0.456
0.392 0.387 0.466 0.426
0.246 0.255 0.469 0.446
0.49 0.48 0.467 0.499
0.225 0.218 0.51 0.507
"""


class TestParseGridTextParcial:
    def test_rellena_a_8x12(self):
        grid = parse_grid_text(_TEXTO_PARCIAL)
        assert len(grid) == 8 and all(len(r) == 12 for r in grid)
        # Columnas 1-4 con datos; 5-12 rellenadas como vacías (0.0).
        assert grid[0][0] == 0.959 and grid[0][3] == 0.866
        assert all(grid[r][c] == 0.0 for r in range(8) for c in range(4, 12))

    def test_detecta_9_muestras_en_placa_de_4_columnas(self):
        imp = parse_placa_cruda(parse_grid_text(_TEXTO_PARCIAL))
        assert imp.n_muestras_detectadas == 9
        # El control (col 1-2, fila G) se leyó.
        assert imp.control_od == (0.49, 0.48)

    def test_solo_columna_de_estandares_lee_una_muestra(self):
        # "Solo estándar": col 1-2 (8 filas). S1 (fila H) es real; el resto vacío.
        solo_std = "\n".join(" ".join(fila.split()[:2])
                             for fila in _TEXTO_PARCIAL.strip().splitlines())
        grid = parse_grid_text(solo_std)
        assert all(grid[r][c] == 0.0 for r in range(8) for c in range(2, 12))
        imp = parse_placa_cruda(grid)
        assert imp.n_muestras_detectadas == 1  # solo S1 (fila H, col 1-2)

    def test_menos_de_6_filas_falla(self):
        with pytest.raises(ValueError):
            parse_grid_text("0.9 1.0\n0.8 0.8\n0.7 0.7\n0.6 0.6\n0.5 0.5")

    def test_mas_de_8_filas_falla(self):
        fila = "0.9 1.0 0.9 0.8"
        with pytest.raises(ValueError):
            parse_grid_text("\n".join([fila] * 9))

    def test_ignora_encabezado_de_columnas(self):
        texto = "1 2 3 4\n" + _TEXTO_PARCIAL.strip()
        grid = parse_grid_text(texto)
        assert len(grid) == 8
        assert grid[0][0] == 0.959
