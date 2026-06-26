"""
tests/test_eca_cumplimiento.py
Pruebas unitarias de la evaluación de cumplimiento ECA.

`ResultadoItem.estado_eca` (services/resultado_service.py) es el núcleo que decide
si un valor medido cumple o excede el Estándar de Calidad Ambiental. Es la lógica
que pinta el semáforo y alimenta las excedencias de los informes, por lo que sus
fronteras (límite mínimo, máximo, igualdad) deben quedar fijadas con pruebas.
La clase es pura (no toca BD).
"""

import pytest

from services.resultado_service import ResultadoItem


def _item(valor_numerico=None, valor_texto=None, lim_min=None, lim_max=None) -> ResultadoItem:
    return ResultadoItem(
        parametro_id="p1",
        codigo="P001",
        nombre="Parámetro de prueba",
        categoria="Físico-Químicos",
        unidad="mg/L",
        valor_numerico=valor_numerico,
        valor_texto=valor_texto,
        lim_min=lim_min,
        lim_max=lim_max,
    )


class TestEstadoECA:
    def test_dentro_de_rango_cumple(self):
        assert _item(5.0, lim_min=1.0, lim_max=10.0).estado_eca == "cumple"

    def test_por_encima_del_maximo_excede(self):
        assert _item(11.0, lim_min=1.0, lim_max=10.0).estado_eca == "excede"

    def test_por_debajo_del_minimo_excede(self):
        # Caso típico: oxígeno disuelto con mínimo regulado.
        assert _item(0.5, lim_min=1.0, lim_max=10.0).estado_eca == "excede"

    def test_igual_al_maximo_cumple(self):
        # El límite es inclusivo: valor == máx no excede.
        assert _item(10.0, lim_max=10.0).estado_eca == "cumple"

    def test_igual_al_minimo_cumple(self):
        assert _item(1.0, lim_min=1.0).estado_eca == "cumple"

    def test_solo_maximo_definido(self):
        assert _item(5.0, lim_max=10.0).estado_eca == "cumple"
        assert _item(10.1, lim_max=10.0).estado_eca == "excede"

    def test_solo_minimo_definido(self):
        # OD ≥ 5: por debajo excede, por encima cumple.
        assert _item(4.0, lim_min=5.0).estado_eca == "excede"
        assert _item(6.0, lim_min=5.0).estado_eca == "cumple"

    def test_sin_limites_es_sin_limite(self):
        assert _item(5.0).estado_eca == "sin_limite"

    def test_sin_valor_es_sin_dato(self):
        assert _item(valor_numerico=None, valor_texto=None).estado_eca == "sin_dato"
        assert _item(valor_numerico=None, valor_texto="").estado_eca == "sin_dato"

    def test_valor_textual_con_limites_cumple(self):
        # Un resultado cualitativo (p. ej. "Ausencia") no se compara
        # numéricamente: se considera 'cumple' (comportamiento actual).
        assert _item(valor_texto="Ausencia", lim_min=0.0, lim_max=10.0).estado_eca == "cumple"


class TestSemaforo:
    def test_mapa_de_colores(self):
        assert _item(5.0, lim_min=1.0, lim_max=10.0).semaforo == "🟢"
        assert _item(11.0, lim_max=10.0).semaforo == "🔴"
        assert _item(5.0).semaforo == "⚪"
        assert _item(valor_numerico=None).semaforo == "⬜"
