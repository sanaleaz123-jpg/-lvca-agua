"""
tests/conftest.py
Asegura que la raíz del proyecto esté en sys.path para poder importar
`services...` al ejecutar pytest desde cualquier directorio.
"""

import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))
