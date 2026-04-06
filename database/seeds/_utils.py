"""
database/seeds/_utils.py
Utilidades compartidas por todos los scripts de seed.
"""

from __future__ import annotations
from supabase import Client


def upsert_batch(
    db: Client,
    tabla: str,
    filas: list[dict],
    conflict_col: str,
    label: str = "",
) -> tuple[int, list[str]]:
    """
    Inserta o actualiza en lotes de 50 filas.
    Retorna (total_ok, lista_errores).
    """
    ok = 0
    errores: list[str] = []
    LOTE = 50

    for i in range(0, len(filas), LOTE):
        lote = filas[i : i + LOTE]
        try:
            db.table(tabla).upsert(lote, on_conflict=conflict_col).execute()
            ok += len(lote)
        except Exception as exc:
            # Reintento fila a fila para localizar el error
            for fila in lote:
                try:
                    db.table(tabla).upsert(fila, on_conflict=conflict_col).execute()
                    ok += 1
                except Exception as e2:
                    clave = fila.get(conflict_col, "?")
                    msg = f"{tabla}[{clave}]: {e2}"
                    errores.append(msg)

    return ok, errores


def imprimir_resumen(titulo: str, total: int, ok: int, errores: list[str]) -> None:
    ancho = 62
    print(f"\n{'─' * ancho}")
    print(f"  {titulo}  ({total} registros)")
    print(f"{'─' * ancho}")
    print(f"  ✓ Insertados/actualizados : {ok}")
    if errores:
        print(f"  ✗ Errores               : {len(errores)}")
        for e in errores[:10]:
            print(f"      {e}")
        if len(errores) > 10:
            print(f"      ... y {len(errores)-10} más")
    print(f"{'─' * ancho}")
