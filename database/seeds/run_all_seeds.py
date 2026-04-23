"""
database/seeds/run_all_seeds.py
Orquestador: ejecuta los 4 seeds en orden de dependencias.

Orden obligatorio:
    1. unidades_medida   (sin dependencias)
    2. parametros        (depende de unidades + crea categorias)
    3. ecas              (depende de parametros)
    4. puntos_muestreo   (depende de ecas)

Verificaciones incluidas:
    - Recuento final de registros en cada tabla
    - Aviso si el total no coincide con lo esperado

Ejecutar:
    cd lvca_agua && python -m database.seeds.run_all_seeds
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds import (
    seed_unidades,
    seed_parametros,
    seed_ecas,
    seed_ecas_matriciales,
    seed_puntos,
)

PASOS = [
    ("1/5  Unidades de medida (151)",               seed_unidades.run),
    ("2/5  Parametros (24+)",                       seed_parametros.run),
    ("3/5  ECAs y valores limite (6)",              seed_ecas.run),
    ("4/5  ECA valores matriciales (Tabla N°1)",    seed_ecas_matriciales.run),
    ("5/5  Puntos de muestreo (12)",                seed_puntos.run),
]

# Verificacion final: tabla -> cantidad esperada
TOTALES_ESPERADOS: dict[str, int] = {
    "unidades_medida":          151,
    "categorias_parametro":       3,
    "parametros":                24,
    "ecas":                       6,
    "eca_valores_matriciales":  112,  # 2 ECAs × 7 T × 8 pH (Tabla N°1)
    "puntos_muestreo":           12,
}


def _verificar_totales(db) -> None:
    print("\n  Verificacion de totales en Supabase:")
    todo_ok = True
    for tabla, esperado in TOTALES_ESPERADOS.items():
        try:
            res = db.table(tabla).select("id", count="exact").execute()
            real = res.count
            estado = "OK" if real >= esperado else f"ADVERTENCIA: se esperaban {esperado}"
            print(f"    {tabla:<30} {real:>4} registros  [{estado}]")
            if real < esperado:
                todo_ok = False
        except Exception as exc:
            print(f"    {tabla:<30} ERROR: {exc}")
            todo_ok = False
    return todo_ok


def main() -> None:
    ancho = 65
    print("\n" + "=" * ancho)
    print("  LVCA AUTODEMA - Carga de datos maestros")
    print("  D.S. N 004-2017-MINAM / Cuenca Chili-Quilca")
    print("=" * ancho)

    for titulo, fn in PASOS:
        print(f"\n  >> {titulo}")
        try:
            fn()
        except Exception as exc:
            print(f"\n  ERROR CRITICO en '{titulo}':")
            print(f"  {exc}")
            print("\n  Abortando. Corrige el error y vuelve a ejecutar.")
            sys.exit(1)

    db = get_admin_client()
    todo_ok = _verificar_totales(db)

    print("\n" + "=" * ancho)
    if todo_ok:
        print("  Carga completa y verificada.")
    else:
        print("  Carga completada con advertencias. Revisa los totales.")
    print("  Verifica los datos en el Table Editor de Supabase.")
    print("=" * ancho + "\n")


if __name__ == "__main__":
    main()
