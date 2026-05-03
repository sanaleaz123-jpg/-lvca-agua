"""
scripts/fix_campana_001_fecha.py

Corrige la fecha de la campaña CAMP-2026-001 — el usuario reportó que
la fecha real de monitoreo fue 2026-03-11 pero quedó registrada como
2026-04-11.

Actualiza:
  1. campanas.fecha_inicio  (2026-04-11 -> 2026-03-11)
  2. campanas.fecha_fin     (2026-04-11 -> 2026-03-11) si coinciden
  3. muestras.fecha_muestreo de TODAS las muestras de esa campaña
     que estén en 2026-04-11 -> 2026-03-11

NO toca fecha_analisis (la fecha del lab es real).

Modo seguro: PRINT primero qué va a actualizar, luego pide confirmación
'SI' por consola para ejecutar.

Uso:
    cd c:\\proyectos\\lvca_agua
    python -m scripts.fix_campana_001_fecha
"""

from __future__ import annotations

import sys
from datetime import date

from database.client import get_admin_client


CAMPANA_CODIGO = "CAMP-2026-001"
FECHA_VIEJA = date(2026, 4, 11)
FECHA_NUEVA = date(2026, 3, 11)


def main() -> int:
    db = get_admin_client()

    # 1. Localizar la campaña por código
    res_camp = (
        db.table("campanas")
        .select("id, codigo, nombre, fecha_inicio, fecha_fin")
        .eq("codigo", CAMPANA_CODIGO)
        .single()
        .execute()
    )
    camp = res_camp.data
    if not camp:
        print(f"ERROR: campaña {CAMPANA_CODIGO} no encontrada.", file=sys.stderr)
        return 1

    camp_id = camp["id"]
    print(f"\nCampaña encontrada: {camp['codigo']} — {camp['nombre']}")
    print(f"  id            = {camp_id}")
    print(f"  fecha_inicio  = {camp['fecha_inicio']}")
    print(f"  fecha_fin     = {camp['fecha_fin']}")

    # 2. Listar muestras a actualizar
    res_muestras = (
        db.table("muestras")
        .select("id, codigo, fecha_muestreo")
        .eq("campana_id", camp_id)
        .execute()
    )
    muestras = res_muestras.data or []
    muestras_a_tocar = [
        m for m in muestras
        if (m.get("fecha_muestreo") or "")[:10] == FECHA_VIEJA.isoformat()
    ]

    print(f"\nMuestras totales en la campaña: {len(muestras)}")
    print(f"Muestras con fecha_muestreo = {FECHA_VIEJA.isoformat()}: {len(muestras_a_tocar)}")
    for m in muestras_a_tocar[:10]:
        print(f"  - {m['codigo']}  ({m['fecha_muestreo']})")
    if len(muestras_a_tocar) > 10:
        print(f"  ... y {len(muestras_a_tocar) - 10} más")

    # 3. Resumen del cambio
    print(f"\n========== CAMBIOS PROPUESTOS ==========")
    if (camp["fecha_inicio"] or "")[:10] == FECHA_VIEJA.isoformat():
        print(f"  campanas.fecha_inicio: {camp['fecha_inicio']}  ->  {FECHA_NUEVA.isoformat()}")
    if (camp["fecha_fin"] or "")[:10] == FECHA_VIEJA.isoformat():
        print(f"  campanas.fecha_fin:    {camp['fecha_fin']}  ->  {FECHA_NUEVA.isoformat()}")
    print(f"  muestras.fecha_muestreo: {len(muestras_a_tocar)} filas -> {FECHA_NUEVA.isoformat()}")
    print(f"========================================\n")

    if not muestras_a_tocar and (camp["fecha_inicio"] or "")[:10] != FECHA_VIEJA.isoformat():
        print("Nada que actualizar — ¿ya está corregido?")
        return 0

    # 4. Confirmación interactiva
    confirm = input("Escribe 'SI' (en mayúsculas) para aplicar los cambios: ").strip()
    if confirm != "SI":
        print("Cancelado por el usuario.")
        return 0

    # 5. Aplicar
    update_camp: dict = {}
    if (camp["fecha_inicio"] or "")[:10] == FECHA_VIEJA.isoformat():
        update_camp["fecha_inicio"] = FECHA_NUEVA.isoformat()
    if (camp["fecha_fin"] or "")[:10] == FECHA_VIEJA.isoformat():
        update_camp["fecha_fin"] = FECHA_NUEVA.isoformat()
    if update_camp:
        db.table("campanas").update(update_camp).eq("id", camp_id).execute()
        print(f"  OK campanas actualizada con {update_camp}")

    n = 0
    for m in muestras_a_tocar:
        db.table("muestras").update(
            {"fecha_muestreo": FECHA_NUEVA.isoformat()}
        ).eq("id", m["id"]).execute()
        n += 1
    print(f"  OK {n} muestras actualizadas a fecha_muestreo = {FECHA_NUEVA.isoformat()}")

    print("\nListo. Recuerda hacer rerun del geoportal para ver los cambios.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
