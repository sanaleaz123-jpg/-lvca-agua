"""
scripts/auditar_ecas_vs_excel.py
Audita los valores ECA almacenados en la BD (tabla eca_valores) contra los
valores oficiales del Excel ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx.

Reporta:
  - Coincidencias exactas
  - Discrepancias de valor
  - ECAs que regulan parámetros que el DS oficial NO regula ("ghost values")
  - Parámetros que el DS regula pero la BD no tiene

Este script es SOLO DE LECTURA — no modifica la BD. Tras el reporte, el
usuario decide qué corregir manualmente o con un script de reconciliación.

Ejecutar:
    cd lvca_agua && python -m scripts.auditar_ecas_vs_excel
"""

from __future__ import annotations

import sys, os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.client import get_admin_client


# ─────────────────────────────────────────────────────────────────────────────
# 1. Valores oficiales del DS para las 4 subcategorías del PEIMS-LVCA.
#    Transcritos del Excel ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx.
#    None = "no regulado" en esa subcategoría (** en el Excel).
#    Las categorías A1 y A3 no están en el Excel — se marcan como "sin_dato".
# ─────────────────────────────────────────────────────────────────────────────
# Llave: codigo_parametro. Valor: {cat_sub → (valor_min, valor_max, unidad_oficial)}
OFICIAL: dict[str, dict[str, tuple]] = {
    "P001":  {  # pH (unidad pH)
        "A2":  (5.5, 9.0, "pH"),
        "D1":  (6.5, 8.5, "pH"),
        "E1":  (6.5, 9.0, "pH"),
        "E2":  (6.5, 9.0, "pH"),
    },
    "P003":  {  # Conductividad (µS/cm)
        "A2":  (None, 1600.0, "uS/cm"),
        "D1":  (None, 2500.0, "uS/cm"),
        "E1":  (None, 1000.0, "uS/cm"),
        "E2":  (None, 1000.0, "uS/cm"),
    },
    "P004":  {  # OD (mg O2/L) — valor mínimo
        "A2":  (5.0, None, "mg O2/L"),
        "D1":  (4.0, None, "mg O2/L"),
        "E1":  (5.0, None, "mg O2/L"),
        "E2":  (5.0, None, "mg O2/L"),
    },
    # P002 Temperatura: Δ3 respecto a línea base — NO es valor absoluto. Se omite del audit.
    # P006 Turbidez (UNT)
    "P006":  {
        "A2":  (None, 100.0, "UNT"),
        "D1":  ("NO_REGULADO", None, "UNT"),
        "E1":  ("NO_REGULADO", None, "UNT"),
        "E2":  ("NO_REGULADO", None, "UNT"),
    },
    # P028 SST (mg/L) — solo Cat 4
    "P028":  {
        "A2":  ("NO_REGULADO", None, "mg/L"),   # en realidad Cat 1 tiene TDS=1000 pero no es SST
        "D1":  ("NO_REGULADO", None, "mg/L"),
        "E1":  (None, 25.0, "mg/L"),
        "E2":  (None, 100.0, "mg/L"),            # E2-Costa/Sierra. Selva=400 (no aplica LVCA)
    },
    # P041 Sulfatos
    "P041":  {
        "A2":  (None, 500.0,  "mg SO4/L"),
        "D1":  (None, 1000.0, "mg SO4/L"),
        "E1":  ("NO_REGULADO", None, "mg SO4/L"),
        "E2":  ("NO_REGULADO", None, "mg SO4/L"),
    },
    # P019 DBO5
    "P019":  {
        "A2":  (None, 5.0,  "mg O2/L"),
        "D1":  (None, 15.0, "mg O2/L"),
        "E1":  (None, 5.0,  "mg O2/L"),
        "E2":  (None, 10.0, "mg O2/L"),
    },
    # P031 Nitratos — ojo: expresión distinta por categoría (ver Nota 6 del Excel)
    "P031":  {
        "A2":  (None, 50.0,  "mg NO3-/L (ion)"),
        "D1":  (None, 100.0, "mg N/L (suma NO3-N + NO2-N)"),
        "E1":  (None, 13.0,  "mg NO3-/L (ion)"),
        "E2":  (None, 13.0,  "mg NO3-/L (ion)"),
    },
    # P032 Nitritos
    "P032":  {
        "A2":  (None, 3.0,  "mg NO2-/L (ion)"),
        "D1":  (None, 10.0, "mg N/L (como N)"),
        "E1":  ("NO_REGULADO", None, "mg NO2-/L"),
        "E2":  ("NO_REGULADO", None, "mg NO2-/L"),
    },
    # P033 Amoniaco / N amoniacal total (Nessler)
    "P033":  {
        "A2":  (None, 1.5, "mg N/L (N-NH3 total)"),
        "D1":  ("NO_REGULADO", None, "—"),   # Cat 3 no regula amoniaco
        "E1":  ("NO_REGULADO", None, "—"),   # Cat 4 regula NH3 libre via P034, no N total
        "E2":  ("NO_REGULADO", None, "—"),
    },
    # P036 Fósforo Total
    "P036":  {
        "A2":  (None, 0.15,  "mg P/L"),
        "D1":  ("NO_REGULADO", None, "mg P/L"),
        "E1":  (None, 0.035, "mg P/L"),   # lagunas — MÁS restrictivo
        "E2":  (None, 0.05,  "mg P/L"),   # ríos
    },
    # P042 Cloruros
    "P042":  {
        "A2":  (None, 250.0, "mg/L"),
        "D1":  (None, 500.0, "mg/L"),
        "E1":  ("NO_REGULADO", None, "mg/L"),
        "E2":  ("NO_REGULADO", None, "mg/L"),
    },
    # P011 Color verdadero (Pt/Co)
    "P011":  {
        "A2":  (None, 100.0, "Pt/Co"),
        "D1":  (None, 100.0, "Pt/Co"),
        "E1":  (None, 20.0,  "Pt/Co"),
        "E2":  (None, 20.0,  "Pt/Co"),
    },
    # P063 Arsénico total
    "P063":  {
        "A2":  (None, 0.01, "mg As/L"),
        "D1":  (None, 0.10, "mg As/L"),
        "E1":  (None, 0.15, "mg As/L"),
        "E2":  (None, 0.15, "mg As/L"),
    },
    # P074 Hierro total
    "P074":  {
        "A2":  (None, 1.0, "mg Fe/L"),
        "D1":  (None, 5.0, "mg Fe/L"),
        "E1":  ("NO_REGULADO", None, "mg Fe/L"),
        "E2":  ("NO_REGULADO", None, "mg Fe/L"),
    },
    # P077 Manganeso total
    "P077":  {
        "A2":  (None, 0.4, "mg Mn/L"),
        "D1":  (None, 0.2, "mg Mn/L"),   # más restrictivo por fitotoxicidad
        "E1":  ("NO_REGULADO", None, "mg Mn/L"),
        "E2":  ("NO_REGULADO", None, "mg Mn/L"),
    },
    # P091 Microcistina-LR — solo A2
    "P091":  {
        "A2":  (None, 1.0, "ug/L"),   # 0.001 mg/L = 1 ug/L
        "D1":  ("NO_REGULADO", None, "ug/L"),
        "E1":  ("NO_REGULADO", None, "ug/L"),
        "E2":  ("NO_REGULADO", None, "ug/L"),
    },
    # P124 Clorofila A — solo E1 (lagunas)
    "P124":  {
        "A2":  ("NO_REGULADO", None, "ug/L"),
        "D1":  ("NO_REGULADO", None, "ug/L"),
        "E1":  (None, 8.0, "ug/L"),    # 0.008 mg/L = 8 ug/L
        "E2":  ("NO_REGULADO", None, "ug/L"),
    },
    # P025 Dureza — no aplica en A2, D1, E1, E2 (solo aparece en A1=500)
    "P025":  {
        "A2":  ("NO_REGULADO", None, "mg CaCO3/L"),
        "D1":  ("NO_REGULADO", None, "mg CaCO3/L"),
        "E1":  ("NO_REGULADO", None, "mg CaCO3/L"),
        "E2":  ("NO_REGULADO", None, "mg CaCO3/L"),
    },
    # P038 Fosfatos — no ECA (ver Nota 5 del Excel)
    "P038":  {
        "A2":  ("NO_REGULADO", None, "—"),
        "D1":  ("NO_REGULADO", None, "—"),
        "E1":  ("NO_REGULADO", None, "—"),
        "E2":  ("NO_REGULADO", None, "—"),
    },
}


_SUBS_LVCA = {"A2", "D1", "E1", "E2"}


def _mapear_cat_sub(eca_row: dict) -> str | None:
    """
    Retorna una clave normalizada 'A2'/'D1'/'E1'/'E2' a partir de la fila de ECA.
    Soporta ambos juegos de códigos existentes en la BD:
      - Canónicos  : 'ECA-C1A2', 'ECA-C3D1', 'ECA-C4E1', 'ECA-C4E2'
      - Antiguos   : '1 A2', '3 D1', '4 E1', '4 E2' con subcategoria 'A2 - Convencional', etc.
    """
    codigo = (eca_row.get("codigo") or "").upper().strip()
    sub = (eca_row.get("subcategoria") or "").upper().strip()

    # Canónicos
    if codigo.startswith("ECA-C"):
        tail = codigo.split("C", 1)[-1]  # "1A2", "3D1", ...
        if len(tail) >= 3:
            cand = tail[1:].strip()
            if cand in _SUBS_LVCA:
                return cand

    # Antiguos: mirar los primeros 2 chars de subcategoria o del codigo después del espacio
    for src in (sub, codigo.split(" ", 1)[-1] if " " in codigo else ""):
        prefix = (src or "").replace(" ", "")[:2]
        if prefix in _SUBS_LVCA:
            return prefix
    return None


def _describir_limite(lim_min, lim_max) -> str:
    if lim_min is not None and lim_max is not None:
        return f"[{lim_min} – {lim_max}]"
    if lim_max is not None:
        return f"≤ {lim_max}"
    if lim_min is not None:
        return f"≥ {lim_min}"
    return "sin límite"


def auditar() -> None:
    db = get_admin_client()

    # 1. Todos los ECAs
    ecas = db.table("ecas").select(
        "id, codigo, categoria, subcategoria"
    ).execute().data or []

    # 2. Mapa parametro_id → codigo
    params = db.table("parametros").select("id, codigo, nombre").execute().data or []
    pid_to_codigo = {p["id"]: p["codigo"] for p in params}

    # 3. Todos los valores ECA
    vals = db.table("eca_valores").select(
        "eca_id, parametro_id, valor_minimo, valor_maximo"
    ).execute().data or []

    print("=" * 90)
    print("  AUDITORÍA DE VALORES ECA — BD vs Excel DS 004-2017-MINAM (4 subcategorías PEIMS)")
    print("=" * 90)
    print()

    # Agrupar por (eca_codigo_normalizado, parametro_codigo)
    # para ver todos los valores que coexisten (canónico vs antiguo)
    coincidencias = 0
    discrepancias: list[dict] = []
    fantasmas: list[dict] = []        # BD regula algo que el DS no regula
    faltantes: list[dict] = []        # DS regula pero BD no tiene

    # Agrupación de eca_id por catsub para poder detectar faltantes
    por_catsub: dict[str, list[dict]] = {}
    for e in ecas:
        cs = _mapear_cat_sub(e)
        if cs in ("A2", "D1", "E1", "E2"):
            por_catsub.setdefault(cs, []).append(e)

    for v in vals:
        eca_row = next((e for e in ecas if e["id"] == v["eca_id"]), None)
        if eca_row is None:
            continue
        cs = _mapear_cat_sub(eca_row)
        if cs not in ("A2", "D1", "E1", "E2"):
            continue  # fuera del alcance del Excel
        p_cod = pid_to_codigo.get(v["parametro_id"])
        if p_cod is None:
            continue

        spec = OFICIAL.get(p_cod, {}).get(cs)
        if spec is None:
            continue  # parametro no auditado

        ofi_min, ofi_max, _unid = spec
        bd_min = v.get("valor_minimo")
        bd_max = v.get("valor_maximo")

        # Caso: DS dice NO_REGULADO pero la BD tiene un valor → fantasma
        if ofi_min == "NO_REGULADO":
            if bd_min is not None or bd_max is not None:
                fantasmas.append({
                    "eca_codigo": eca_row["codigo"],
                    "cat_sub":    cs,
                    "parametro":  p_cod,
                    "bd_limite":  _describir_limite(bd_min, bd_max),
                    "ds_dice":    "NO regulado por el DS 004-2017-MINAM",
                })
            else:
                coincidencias += 1
            continue

        # Caso normal: comparar valores
        def _eq(a, b):
            if a is None and b is None: return True
            if a is None or b is None:  return False
            return abs(float(a) - float(b)) <= 0.0005

        ok_min = _eq(bd_min, ofi_min)
        ok_max = _eq(bd_max, ofi_max)
        if ok_min and ok_max:
            coincidencias += 1
        else:
            discrepancias.append({
                "eca_codigo": eca_row["codigo"],
                "cat_sub":    cs,
                "parametro":  p_cod,
                "bd":         _describir_limite(bd_min, bd_max),
                "ds_oficial": _describir_limite(ofi_min, ofi_max),
            })

    # Faltantes: DS regula (valor numérico) pero BD no tiene fila para (eca, param)
    # Solo los canónicos (ECA-C*) porque los antiguos no los actualizo.
    ecas_canonicos = {e["id"]: e["codigo"] for e in ecas if (e.get("codigo") or "").startswith("ECA-C")}
    vals_por_eca: dict[str, set[str]] = {}
    for v in vals:
        vals_por_eca.setdefault(v["eca_id"], set()).add(v["parametro_id"])

    for p_cod, dx in OFICIAL.items():
        p_id = next((p["id"] for p in params if p["codigo"] == p_cod), None)
        if not p_id:
            continue
        for cs, spec in dx.items():
            ofi_min, ofi_max, _ = spec
            if ofi_min == "NO_REGULADO" or (ofi_min is None and ofi_max is None):
                continue
            # Buscar si algún ECA canónico de este cs tiene fila para este parametro
            ecas_cs_canon = [e for e in ecas if (e.get("codigo") or "").startswith("ECA-C") and _mapear_cat_sub(e) == cs]
            for e in ecas_cs_canon:
                if p_id not in vals_por_eca.get(e["id"], set()):
                    faltantes.append({
                        "eca_codigo": e["codigo"],
                        "cat_sub":    cs,
                        "parametro":  p_cod,
                        "ds_oficial": _describir_limite(ofi_min, ofi_max),
                    })

    # ── Reporte ────────────────────────────────────────────────────────────
    print(f"Coincidencias:  {coincidencias}")
    print(f"Discrepancias:  {len(discrepancias)}")
    print(f"Fantasmas:      {len(fantasmas)} (BD regula, DS no regula)")
    print(f"Faltantes:      {len(faltantes)} (DS regula, BD no tiene)")
    print()

    if discrepancias:
        print("─" * 90)
        print("DISCREPANCIAS (valor BD ≠ valor DS oficial)")
        print("─" * 90)
        print(f"{'ECA':14s} {'Cat':4s} {'Par':5s} {'BD':25s} → {'DS oficial':25s}")
        for d in sorted(discrepancias, key=lambda x: (x["cat_sub"], x["parametro"], x["eca_codigo"])):
            print(f"{d['eca_codigo']:14s} {d['cat_sub']:4s} {d['parametro']:5s} {d['bd']:25s} → {d['ds_oficial']:25s}")
        print()

    if fantasmas:
        print("─" * 90)
        print("FANTASMAS (la BD tiene un ECA donde el DS dice NO regulado)")
        print("─" * 90)
        print(f"{'ECA':14s} {'Cat':4s} {'Par':5s} {'BD tiene':25s}  Nota DS")
        for f in sorted(fantasmas, key=lambda x: (x["cat_sub"], x["parametro"], x["eca_codigo"])):
            print(f"{f['eca_codigo']:14s} {f['cat_sub']:4s} {f['parametro']:5s} {f['bd_limite']:25s}  {f['ds_dice']}")
        print()

    if faltantes:
        print("─" * 90)
        print("FALTANTES (el DS regula este parámetro pero la BD no tiene fila para el ECA canónico)")
        print("─" * 90)
        print(f"{'ECA':14s} {'Cat':4s} {'Par':5s} {'DS exige':25s}")
        for f in sorted(faltantes, key=lambda x: (x["cat_sub"], x["parametro"], x["eca_codigo"])):
            print(f"{f['eca_codigo']:14s} {f['cat_sub']:4s} {f['parametro']:5s} {f['ds_oficial']:25s}")
        print()

    print("=" * 90)
    print("Notas: el DS oficial regula también Amoniaco libre NH3 Cat 4 via Tabla N°1 ")
    print("(matricial pH×T). Esta auditoría cubre solo valores escalares, no matriciales.")
    print("=" * 90)


if __name__ == "__main__":
    auditar()
