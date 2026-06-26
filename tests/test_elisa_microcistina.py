"""
tests/test_elisa_microcistina.py
Pruebas unitarias del motor de cálculo ELISA ADDA para Microcistina LR
(kit SAES/ABRAXIS, EPA Method 546).

Estas fórmulas sustentan los resultados de toxina cianobacteriana en informes
oficiales: un error aquí compromete decisiones sanitarias. El módulo
`services/elisa_microcistina.py` es de cálculo puro (sin BD ni Streamlit), por
lo que estas pruebas corren sin Supabase.
"""

import pytest

from services.elisa_microcistina import (
    FACTOR_DILUCION_DEFAULT,
    STD_CONC_UGL,
    CurvaParams,
    _model_4pl,
    concentracion_ugL,
    cv_pct,
    fit_4pl,
    procesar_control,
    procesar_muestra,
)


def _curva(A=2.0, B=1.0, C=1.0, D=0.1, r2=1.0, sse=0.0) -> CurvaParams:
    """Curva 4PL sencilla y conocida para verificar la inversa."""
    return CurvaParams(A=A, B=B, C=C, D=D, r2=r2, sse=sse)


# ── %CV sobre las OD (desviación muestral n−1) ───────────────────────────────
class TestCV:
    def test_replicas_identicas_cv_cero(self):
        assert cv_pct(1.0, 1.0) == 0.0

    def test_media_cero_devuelve_cero(self):
        assert cv_pct(0.0, 0.0) == 0.0

    def test_valor_conocido(self):
        # media=1.0, sd=|1.1-0.9|/√2 = 0.1414 → %CV = 14.142
        assert cv_pct(1.1, 0.9) == pytest.approx(0.2 / 2 ** 0.5 / 1.0 * 100)

    def test_simetrico(self):
        assert cv_pct(0.9, 1.1) == pytest.approx(cv_pct(1.1, 0.9))


# ── Concentración por curva 4PL inversa ──────────────────────────────────────
class TestConcentracionInversa:
    def test_punto_en_rango(self):
        # A=2, B=1, C=1, D=0.1; od=1.05 → base=(0.95/0.95)=1 → conc=C*1=1.0
        assert concentracion_ugL(1.05, _curva()) == pytest.approx(1.0)

    def test_od_por_encima_de_amax_sin_solucion(self):
        # od ≥ A → numerador ≤ 0 → base ≤ 0 → None
        assert concentracion_ugL(2.0, _curva()) is None
        assert concentracion_ugL(2.5, _curva()) is None

    def test_od_por_debajo_de_dmin_sin_solucion(self):
        # od < D → (od-D) < 0 → base < 0 → None
        assert concentracion_ugL(0.05, _curva()) is None

    def test_inversa_consistente_con_modelo(self):
        # Generamos una OD desde el modelo a una concentración conocida y la
        # recuperamos con la inversa.
        curva = _curva(A=1.2, B=1.0, C=0.4, D=0.05)
        import numpy as np
        x_conocido = 0.3
        od = float(_model_4pl(np.array([curva.A, curva.B, curva.C, curva.D]),
                              np.array([x_conocido]))[0])
        assert concentracion_ugL(od, curva) == pytest.approx(x_conocido, rel=1e-6)


# ── Procesamiento de muestra (par de réplicas + factor) ──────────────────────
class TestProcesarMuestra:
    def test_en_rango_con_factor_por_defecto(self):
        r = procesar_muestra(1.05, 1.05, _curva())
        assert r.en_rango is True
        assert r.conc_ugL == pytest.approx(1.0 * FACTOR_DILUCION_DEFAULT)
        assert r.cv_pct == 0.0
        assert r.motivo == ""

    def test_factor_explicito(self):
        r = procesar_muestra(1.05, 1.05, _curva(), factor=1.0)
        assert r.conc_ugL == pytest.approx(1.0)

    def test_control_sin_factor(self):
        r = procesar_control(1.05, 1.05, _curva())
        assert r.conc_ugL == pytest.approx(1.0)

    def test_por_encima_del_estandar_mas_alto_diluir(self):
        # Una réplica con OD ≤ D → muy concentrada: conc None, pedir dilución.
        r = procesar_muestra(0.05, 0.05, _curva())
        assert r.conc_ugL is None
        assert r.en_rango is False
        assert "diluir" in r.motivo.lower()

    def test_senal_por_encima_de_amax_cuenta_como_cero(self):
        # Ambas réplicas con OD ≥ Amax → poca toxina; concentración ~0.
        r = procesar_muestra(2.5, 2.5, _curva())
        assert r.en_rango is False
        assert r.conc_ugL == pytest.approx(0.0)
        assert "Amax" in r.motivo


# ── Ajuste de la curva 4PL ───────────────────────────────────────────────────
class TestFit4PL:
    def test_requiere_al_menos_4_estandares(self):
        with pytest.raises(ValueError):
            fit_4pl([0.0, 0.5, 1.0], [1.2, 0.8, 0.4])

    def test_recupera_curva_desde_datos_sin_ruido(self):
        import numpy as np
        verdad = _curva(A=1.2, B=1.0, C=0.4, D=0.05)
        x = np.asarray(STD_CONC_UGL, dtype=float)
        y = _model_4pl(np.array([verdad.A, verdad.B, verdad.C, verdad.D]), x)

        ajuste = fit_4pl(list(STD_CONC_UGL), list(y))

        # El ajuste reproduce los datos casi perfectamente.
        assert ajuste.r2 > 0.999
        y_pred = _model_4pl(np.array([ajuste.A, ajuste.B, ajuste.C, ajuste.D]), x)
        assert np.allclose(y_pred, y, atol=1e-2)
        # Y recupera los parámetros con holgura razonable.
        assert ajuste.A == pytest.approx(verdad.A, abs=0.05)
        assert ajuste.D == pytest.approx(verdad.D, abs=0.05)
        assert ajuste.C == pytest.approx(verdad.C, abs=0.10)


# ── Criterio de validez del protocolo ────────────────────────────────────────
class TestEsValida:
    def test_curva_buena(self):
        assert _curva(A=1.2, B=1.0, C=0.4, D=0.05, r2=0.999).es_valida() is True

    def test_amax_bajo_invalida(self):
        assert _curva(A=0.5, D=0.05, r2=0.999).es_valida() is False

    def test_r2_bajo_invalida(self):
        assert _curva(A=1.2, D=0.05, r2=0.90).es_valida() is False
