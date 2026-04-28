"""
scripts/renumerar_colca_regulado_camp2.py
One-off: reasigna codigos LVCA-2026-013/014/015 (Condoroma, Tuti, Huambo —
Campana 2 Colca Regulado, fecha real 2026-03-11/12) a 006/007/008, y corre
los codigos 006-012 hacia 009-015.

Mapping:
    LVCA-2026-013 (Condoroma)   -> LVCA-2026-006
    LVCA-2026-014 (Tuti)        -> LVCA-2026-007
    LVCA-2026-015 (Huambo)      -> LVCA-2026-008
    LVCA-2026-006 (Pane 04-22)  -> LVCA-2026-009
    LVCA-2026-007 (Esp  04-22)  -> LVCA-2026-010
    LVCA-2026-008 (Sumb 04-22)  -> LVCA-2026-011
    LVCA-2026-009 (AgBl 04-23)  -> LVCA-2026-012
    LVCA-2026-010 (Fray 04-23)  -> LVCA-2026-013
    LVCA-2026-011 (PaGr 04-23)  -> LVCA-2026-014
    LVCA-2026-012 (Blan 04-23)  -> LVCA-2026-015

Uso:
    cd c:\\proyectos\\lvca_agua
    python -m scripts.renumerar_colca_regulado_camp2
"""

from __future__ import annotations

import sys

from database.client import get_admin_client


MAPPING = {
    "LVCA-2026-013": "LVCA-2026-006",
    "LVCA-2026-014": "LVCA-2026-007",
    "LVCA-2026-015": "LVCA-2026-008",
    "LVCA-2026-006": "LVCA-2026-009",
    "LVCA-2026-007": "LVCA-2026-010",
    "LVCA-2026-008": "LVCA-2026-011",
    "LVCA-2026-009": "LVCA-2026-012",
    "LVCA-2026-010": "LVCA-2026-013",
    "LVCA-2026-011": "LVCA-2026-014",
    "LVCA-2026-012": "LVCA-2026-015",
}


def main() -> int:
    db = get_admin_client()

    codigos_origen = list(MAPPING.keys())
    muestras = (
        db.table("muestras")
        .select("id, codigo, fecha_muestreo, hora_recoleccion")
        .in_("codigo", codigos_origen)
        .execute()
        .data
        or []
    )

    if len(muestras) != len(codigos_origen):
        encontrados = {m["codigo"] for m in muestras}
        faltantes = set(codigos_origen) - encontrados
        print(f"ERROR: faltan muestras en BD: {sorted(faltantes)}")
        return 1

    cod_a_id = {m["codigo"]: m["id"] for m in muestras}

    print(f"Renumerando {len(muestras)} muestras...")
    for orig, dest in MAPPING.items():
        print(f"  {orig} -> {dest}")

    # Paso 1 — codigos temporales para liberar slots
    for orig, _ in MAPPING.items():
        mid = cod_a_id[orig]
        tmp = f"__TMP_{mid}"
        db.table("muestras").update({"codigo": tmp}).eq("id", mid).execute()

    # Paso 2 — codigos definitivos
    for orig, dest in MAPPING.items():
        mid = cod_a_id[orig]
        db.table("muestras").update({"codigo": dest}).eq("id", mid).execute()

    # Verificacion
    final = (
        db.table("muestras")
        .select("codigo")
        .in_("codigo", list(MAPPING.values()))
        .execute()
        .data
        or []
    )
    if len(final) != len(MAPPING):
        print(f"ERROR: tras renumerar solo aparecen {len(final)} de {len(MAPPING)} codigos finales")
        return 2

    print(f"OK: {len(MAPPING)} muestras renumeradas correctamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
