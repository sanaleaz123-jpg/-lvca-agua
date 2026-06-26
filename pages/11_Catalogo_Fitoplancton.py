"""
pages/11_Catalogo_Fitoplancton.py
Página standalone del catálogo de taxonomía de fitoplancton.

El catálogo se gestiona normalmente desde la pestaña "Catálogo fitoplancton"
dentro de Parámetros / ECAs (pages/5_Parametros.py). Esta página se conserva
como acceso directo por URL y reutiliza el mismo componente para no duplicar
lógica. Ya no aparece en la barra de navegación.

Acceso mínimo: administrador.
"""

from __future__ import annotations

from components.auth_guard import require_rol
from components.catalogo_fitoplancton_ui import render_catalogo_fitoplancton
from components.ui_styles import aplicar_estilos, page_header, top_nav


@require_rol("administrador")
def main() -> None:
    aplicar_estilos()
    top_nav()
    page_header(
        "Catálogo de fitoplancton",
        "Taxonomía del método de conteo — verificada contra AlgaeBase / GBIF",
    )

    render_catalogo_fitoplancton()


main()
