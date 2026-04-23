"""
database/seeds/seed_ecas_matriciales.py
Tabla N°1 del DS 004-2017-MINAM — ECA de Amoniaco Total NH3 (mg/L) en función
de pH y T, aplicable a ECA-C4E1 (lagunas) y ECA-C4E2 (ríos costa/sierra) sobre
el parámetro P034 'Amoniaco libre (NH3 no ionizado)'.

UPSERT idempotente por (eca_id, parametro_id, variable_x, valor_x, variable_y, valor_y).
Requiere que seed_ecas.py (P034 existe, ECA-C4E1 y E2 existen) ya se haya ejecutado
y que migrations/011_eca_valores_matriciales.sql esté aplicada.

Ejecutar:
    cd lvca_agua && python -m database.seeds.seed_ecas_matriciales
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds._utils import upsert_batch, imprimir_resumen


# ─────────────────────────────────────────────────────────────────────────────
# Tabla N°1 — transcrita tal cual del Excel ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2
# Valores en mg NH3/L (amoniaco no ionizado en agua dulce).
# Eje X = pH, eje Y = temperatura en °C.
# ─────────────────────────────────────────────────────────────────────────────
PH_GRID: list[float] = [6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 10.0]
T_GRID:  list[float] = [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]

# Matriz[i][j] = valor para T_GRID[i] y PH_GRID[j]
TABLA_N1: list[list[float]] = [
    # pH    6       6.5     7.0     7.5     8.0     8.5     9.0     10.0
    [      231.0,  73.0,   23.1,   7.32,   2.33,   0.749,  0.25,   0.042 ],  # T 0
    [      153.0,  48.3,   15.3,   4.84,   1.54,   0.502,  0.172,  0.034 ],  # T 5
    [      102.0,  32.4,   10.3,   3.26,   1.04,   0.343,  0.121,  0.029 ],  # T 10
    [       69.7,  22.0,   6.98,   2.22,   0.715,  0.239,  0.089,  0.026 ],  # T 15
    [       48.0,  15.2,   4.82,   1.54,   0.499,  0.171,  0.067,  0.024 ],  # T 20
    [       33.5,  10.6,   3.37,   1.08,   0.354,  0.125,  0.053,  0.022 ],  # T 25
    [       23.7,  7.5,    2.39,   0.767,  0.256,  0.094,  0.043,  0.021 ],  # T 30
]

# ECAs a los que aplica (agua dulce Cat 4). No incluye Cat 4-E3 (estuarios/marinos,
# Tabla N°2 por salinidad) ni Cat 2 (marítimos) porque no aplican al PEIMS-LVCA.
ECA_CODIGOS: list[str] = ["ECA-C4E1", "ECA-C4E2"]
PARAM_CODIGO: str = "P034"  # Amoniaco libre (NH3 no ionizado)


def _construir_filas(eca_map: dict[str, str], param_id: str) -> list[dict]:
    """Genera la lista de filas a upsertar (56 × len(ECA_CODIGOS))."""
    filas: list[dict] = []
    for eca_codigo in ECA_CODIGOS:
        eca_id = eca_map.get(eca_codigo)
        if not eca_id:
            print(f"  ADVERTENCIA: ECA '{eca_codigo}' no encontrado — se omite")
            continue
        for i, t in enumerate(T_GRID):
            for j, ph in enumerate(PH_GRID):
                filas.append({
                    "eca_id":         eca_id,
                    "parametro_id":   param_id,
                    "variable_x":     "pH",
                    "valor_x":        ph,
                    "variable_y":     "temperatura_C",
                    "valor_y":        t,
                    "valor":          TABLA_N1[i][j],
                    "expresado_como": "NH3_libre",
                    "observacion":    "Tabla N°1 DS 004-2017-MINAM (agua dulce)",
                })
    return filas


def run() -> None:
    db = get_admin_client()

    # Resolver UUID del parámetro P034
    param_row = (
        db.table("parametros")
        .select("id, codigo")
        .eq("codigo", PARAM_CODIGO)
        .maybe_single()
        .execute()
    )
    if not param_row or not param_row.data:
        raise RuntimeError(
            f"Parámetro '{PARAM_CODIGO}' no existe en la BD. "
            "Ejecuta seed_parametros.py primero."
        )
    param_id = param_row.data["id"]

    # Resolver UUIDs de los ECAs
    ecas = db.table("ecas").select("id, codigo").in_("codigo", ECA_CODIGOS).execute().data or []
    eca_map = {e["codigo"]: e["id"] for e in ecas}
    if not eca_map:
        raise RuntimeError(
            f"No se encontraron los ECAs {ECA_CODIGOS} en la BD. "
            "Ejecuta seed_ecas.py primero."
        )

    filas = _construir_filas(eca_map, param_id)

    esperado = len(ECA_CODIGOS) * len(T_GRID) * len(PH_GRID)
    print(f"  Generadas {len(filas)} filas (esperado: {esperado})")

    ok, errores = upsert_batch(
        db,
        "eca_valores_matriciales",
        filas,
        "eca_id,parametro_id,variable_x,valor_x,variable_y,valor_y",
    )
    imprimir_resumen("SEED: eca_valores_matriciales (Tabla N°1 NH3)", len(filas), ok, errores)


if __name__ == "__main__":
    run()
