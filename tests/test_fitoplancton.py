"""
tests/test_fitoplancton.py
Pruebas unitarias de los cálculos regulatorios de fitoplancton.

Estas funciones sustentan los informes de vigilancia (densidad celular,
alertas OMS de cianobacterias) y deben permanecer correctas: un error aquí
comprometería informes oficiales. Son funciones puras — no tocan la BD —, así
que las pruebas corren sin Supabase.
"""

import pytest

from services.fitoplancton_service import (
    METODO_UTERMOHL,
    calcular_densidad_sedgewick_rafter,
    calcular_densidad_utermohl,
    calcular_y_agrupar_por_filo,
    evaluar_alerta_oms_2021,
    evaluar_alerta_oms_cianobacterias,
    evaluar_alerta_oms_clorofila,
    total_biovolumen_filo,
    total_cel_ml_filo,
    total_unidades_ml_filo,
)


# ── Densidad Sedgewick-Rafter ────────────────────────────────────────────────
class TestSedgewickRafter:
    def test_formula_basica(self):
        # cel/mL = (C*1000)/(A*D*F) * (Vc/Vs)
        # C=100, A=1000, D=1, F=1, Vc=10, Vs=100  →  100 * 0.1 = 10.0
        r = calcular_densidad_sedgewick_rafter(
            conteos_brutos={"X": 100},
            vol_muestra_ml=100, vol_concentrado_ml=10,
            area_campo_mm2=1000, num_campos=1,
        )
        assert r["X"]["cel_ml"] == pytest.approx(10.0)
        assert r["X"]["cel_l"] == pytest.approx(10000.0)
        assert r["X"]["conteo_bruto"] == 100

    def test_camara_completa_directa(self):
        # A=1, F=1, Vc=Vs  →  cel/mL = C*1000
        r = calcular_densidad_sedgewick_rafter(
            {"X": 50}, vol_muestra_ml=1, vol_concentrado_ml=1,
            area_campo_mm2=1, num_campos=1,
        )
        assert r["X"]["cel_ml"] == pytest.approx(50000.0)

    def test_conteo_cero_excluido(self):
        r = calcular_densidad_sedgewick_rafter(
            {"A": 0, "B": 5}, vol_muestra_ml=1, vol_concentrado_ml=1,
            area_campo_mm2=1, num_campos=1,
        )
        assert "A" not in r
        assert "B" in r

    @pytest.mark.parametrize("override", [
        {"vol_muestra_ml": 0},
        {"area_campo_mm2": 0},
        {"num_campos": 0},
        {"profundidad_mm": 0},
    ])
    def test_division_por_cero_lanza(self, override):
        base = dict(
            conteos_brutos={"X": 1}, vol_muestra_ml=1,
            vol_concentrado_ml=1, area_campo_mm2=1, num_campos=1,
        )
        base.update(override)
        with pytest.raises(ValueError):
            calcular_densidad_sedgewick_rafter(**base)

    def test_concentrado_mayor_que_muestra_lanza(self):
        # Vc > Vs es físicamente imposible y dispararía densidades infladas.
        with pytest.raises(ValueError):
            calcular_densidad_sedgewick_rafter(
                {"X": 1}, vol_muestra_ml=10, vol_concentrado_ml=20,
                area_campo_mm2=1, num_campos=1,
            )


# ── Densidad Utermöhl (cámara de sedimentación) ──────────────────────────────
class TestUtermohl:
    def test_formula_basica(self):
        # cel/mL = C * A_cámara / (A_contada * V_sed)
        # C=200, A_cámara=300, A_contada=15, V_sed=10  →  200*300/(15*10)=400
        r = calcular_densidad_utermohl(
            {"X": 200}, vol_sedimentado_ml=10, area_camara_mm2=300, area_contada_mm2=15,
        )
        assert r["X"]["cel_ml"] == pytest.approx(400.0)
        assert r["X"]["cel_l"] == pytest.approx(400000.0)
        assert r["X"]["conteo_bruto"] == 200

    def test_conteo_cero_excluido(self):
        r = calcular_densidad_utermohl(
            {"A": 0, "B": 5}, vol_sedimentado_ml=10, area_camara_mm2=300, area_contada_mm2=15,
        )
        assert "A" not in r and "B" in r

    @pytest.mark.parametrize("override", [
        {"vol_sedimentado_ml": 0},
        {"area_camara_mm2": 0},
        {"area_contada_mm2": 0},
    ])
    def test_division_por_cero_lanza(self, override):
        base = dict(conteos_brutos={"X": 1}, vol_sedimentado_ml=10,
                    area_camara_mm2=300, area_contada_mm2=15)
        base.update(override)
        with pytest.raises(ValueError):
            calcular_densidad_utermohl(**base)

    def test_area_contada_mayor_que_camara_lanza(self):
        with pytest.raises(ValueError):
            calcular_densidad_utermohl(
                {"X": 1}, vol_sedimentado_ml=10, area_camara_mm2=15, area_contada_mm2=300,
            )

    def test_agrupar_por_filo_utermohl_aplica_celulas_por_unidad(self):
        # Dolichospermum: filamento, 50 células/unidad.
        # unidad_ml = 100*300/(15*10) = 200 ; cel_ml_equiv = 200*50 = 10000.
        res = calcular_y_agrupar_por_filo(
            {"Cyanobacteria": {"Dolichospermum sp.": 100}},
            metodo=METODO_UTERMOHL,
            vol_sedimentado_ml=10, area_camara_mm2=300, area_contada_mm2=15,
        )
        esp = res["Cyanobacteria"]["Dolichospermum sp."]
        assert esp["unidad_ml"] == pytest.approx(200.0)
        assert esp["cel_ml_equiv"] == pytest.approx(10000.0)


# ── Reporte de Ensayo de fitoplancton (.docx) ────────────────────────────────
class TestReporteFitoplancton:
    def _estacion(self):
        return {
            "id": "m1", "codigo": "LVCA-2026-001",
            "fecha_muestreo": "2026-05-28", "hora_recoleccion": "13:40",
            "fecha_recepcion_lab": "2026-05-29", "punto_muestreo_id": "p1",
            "puntos_muestreo": {
                "codigo": "PM-02", "nombre": "Laguna Pañe",
                "descripcion": "Represa El Pañe", "utm_este": 278106,
                "utm_norte": 8294236, "altitud_msnm": 4600,
            },
            "datos_fitoplancton": {
                "metadatos": {"metodo": "sedgewick_rafter", "num_campos": 100,
                              "area_campo_mm2": 1000, "fecha_analisis": "2026-05-30"},
                "resultados": {
                    "Cyanobacteria": {
                        "Dolichospermum sp.": {"conteo_bruto": 10, "cel_ml_equiv": 500.0},
                    },
                },
            },
        }

    def test_genera_docx_bytes(self, monkeypatch):
        import services.reporte_fitoplancton_service as svc
        campana = {"codigo": "CAMP-2026-001", "nombre": "Campaña de prueba"}
        monkeypatch.setattr(svc, "_cargar_estaciones",
                            lambda cid: (campana, [self._estacion()]))
        monkeypatch.setattr(svc, "get_codigo_reporte_fito",
                            lambda *a, **k: "LVCA - 001-FITO-2026")
        data = svc.generar_docx_fitoplancton_campana("x", {})
        assert isinstance(data, (bytes, bytearray)) and data[:2] == b"PK"

    def test_sin_analisis_lanza(self, monkeypatch):
        import services.reporte_fitoplancton_service as svc
        monkeypatch.setattr(svc, "_cargar_estaciones", lambda cid: ({}, []))
        with pytest.raises(ValueError):
            svc.generar_docx_fitoplancton_campana("x", {})


# ── Alerta OMS 1999 por células/mL ───────────────────────────────────────────
class TestOMSCianobacteriasCelML:
    def test_nulo_y_bajo_umbral_no_alertan(self):
        assert evaluar_alerta_oms_cianobacterias(None) is None
        assert evaluar_alerta_oms_cianobacterias(199.9) is None

    def test_umbral_vigilancia_inicial(self):
        # Exactamente 200 cél/mL ya dispara vigilancia inicial.
        assert evaluar_alerta_oms_cianobacterias(200)["nivel"] == "vigilancia_inicial"

    def test_alerta_1(self):
        assert evaluar_alerta_oms_cianobacterias(2000)["nivel"] == "alerta_1"
        assert evaluar_alerta_oms_cianobacterias(50000)["nivel"] == "alerta_1"

    def test_alerta_2(self):
        assert evaluar_alerta_oms_cianobacterias(100000)["nivel"] == "alerta_2"
        assert evaluar_alerta_oms_cianobacterias(1e9)["nivel"] == "alerta_2"


# ── Alerta OMS 2021 por biovolumen + unidades ────────────────────────────────
class TestOMS2021:
    def test_alerta_2_por_biovolumen(self):
        assert evaluar_alerta_oms_2021(4.0, 0, 0)["nivel"] == "alerta_2"

    def test_alerta_1_por_biovolumen(self):
        assert evaluar_alerta_oms_2021(0.3, 0, 0)["nivel"] == "alerta_1"
        assert evaluar_alerta_oms_2021(3.99, 0, 0)["nivel"] == "alerta_1"

    def test_vigilancia_por_unidades(self):
        # >10 colonias/mL  o  >50 filamentos/mL sin biovolumen suficiente.
        assert evaluar_alerta_oms_2021(0.0, 11, 0)["nivel"] == "vigilancia_inicial"
        assert evaluar_alerta_oms_2021(0.0, 0, 51)["nivel"] == "vigilancia_inicial"

    def test_sin_alerta_en_limites_no_excedidos(self):
        # colonias=10 (no >10), filamentos=50 (no >50), biovol<0.3 → sin alerta.
        assert evaluar_alerta_oms_2021(0.29, 10, 50) is None


# ── Alerta OMS 1999 por clorofila-a ──────────────────────────────────────────
class TestOMSClorofila:
    def test_nulo_y_bajo_umbral_no_alertan(self):
        assert evaluar_alerta_oms_clorofila(None) is None
        assert evaluar_alerta_oms_clorofila(0.99) is None

    def test_niveles(self):
        assert evaluar_alerta_oms_clorofila(1.0)["nivel"] == "vigilancia_inicial"
        assert evaluar_alerta_oms_clorofila(10)["nivel"] == "alerta_1"
        assert evaluar_alerta_oms_clorofila(50)["nivel"] == "alerta_2"


# ── Agrupación por filo y agregaciones ───────────────────────────────────────
class TestAgrupacionYTotales:
    def _muestra(self):
        # Dolichospermum sp.: filamento, 50 células/unidad, volumen 0 (sin calibrar).
        return calcular_y_agrupar_por_filo(
            {"Cyanobacteria": {"Dolichospermum sp.": 100}},
            vol_muestra_ml=100, vol_concentrado_ml=10,
            area_campo_mm2=1000, num_campos=1,
        )

    def test_aplica_celulas_por_unidad(self):
        esp = self._muestra()["Cyanobacteria"]["Dolichospermum sp."]
        assert esp["unidad"] == "filamento"
        assert esp["unidad_ml"] == pytest.approx(10.0)          # densidad SR
        assert esp["cel_ml_equiv"] == pytest.approx(500.0)      # × 50 cél/unidad
        assert esp["cel_l_equiv"] == pytest.approx(500000.0)

    def test_total_cel_ml_filo(self):
        assert total_cel_ml_filo(self._muestra(), "Cyanobacteria") == pytest.approx(500.0)

    def test_total_unidades_ml_filo_por_tipo(self):
        d = self._muestra()
        assert total_unidades_ml_filo(d, "Cyanobacteria", "filamento") == pytest.approx(10.0)
        assert total_unidades_ml_filo(d, "Cyanobacteria", "colonia") == 0.0

    def test_total_biovolumen_cero_sin_calibrar(self):
        # Cyanobacteria tiene volumen_celula_um3=0 → biovolumen 0.
        assert total_biovolumen_filo(self._muestra(), "Cyanobacteria") == 0.0
