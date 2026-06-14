"""
tests/test_token_refresh.py
Pruebas de la lógica de expiración de JWT usada por el cutover de RLS.

Cubre la parte pura (decodificar el claim `exp`) y que _asegurar_token_vigente
NO intente renovar cuando el token todavía está vigente (no debe tocar la red).
"""

import base64
import json

from database.client import _jwt_exp, _asegurar_token_vigente, _MARGEN_REFRESCO_SEG


def _fake_jwt(exp: float | None) -> str:
    """Construye un JWT de juguete con el claim exp indicado (firma irrelevante)."""
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').decode().rstrip("=")
    body = {"sub": "u1"}
    if exp is not None:
        body["exp"] = exp
    payload = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    return f"{header}.{payload}.firma_irrelevante"


class _Sesion:
    """Sustituto mínimo de SesionUsuario para las pruebas."""
    def __init__(self, access_token: str, refresh_token: str = "r"):
        self.access_token = access_token
        self.refresh_token = refresh_token


class TestJwtExp:
    def test_lee_exp(self):
        assert _jwt_exp(_fake_jwt(9999999999)) == 9999999999.0

    def test_token_malformado_devuelve_none(self):
        assert _jwt_exp("no-es-un-jwt") is None
        assert _jwt_exp("") is None

    def test_sin_exp_devuelve_none(self):
        assert _jwt_exp(_fake_jwt(None)) is None


class TestAsegurarTokenVigente:
    def test_token_vigente_no_renueva(self):
        # exp muy en el futuro → devuelve los mismos tokens sin tocar la red.
        futuro = 10_000_000_000.0  # año 2286
        s = _Sesion(_fake_jwt(futuro), refresh_token="r123")
        access, refresh = _asegurar_token_vigente(s)
        assert access == s.access_token
        assert refresh == "r123"

    def test_sin_refresh_token_no_renueva(self):
        # Sin refresh_token no hay forma de renovar: devuelve lo que hay.
        s = _Sesion(_fake_jwt(0), refresh_token="")
        access, refresh = _asegurar_token_vigente(s)
        assert refresh == ""
        assert access == s.access_token

    def test_margen_es_positivo(self):
        # Sanity: el margen de refresco proactivo está configurado.
        assert _MARGEN_REFRESCO_SEG > 0
