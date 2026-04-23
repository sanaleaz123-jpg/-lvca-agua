"""
scripts/reconciliar_ecas_oficiales.py
Aplica los valores oficiales del DS 004-2017-MINAM (transcritos del Excel
ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx) a la tabla eca_valores de la BD,
tocando AMBOS juegos de ECAs existentes:

    - Códigos canónicos : 'ECA-C1A2', 'ECA-C3D1', 'ECA-C4E1', 'ECA-C4E2'
    - Códigos antiguos  : '1 A2', '3 D1', '4 E1', '4 E2'

Así, no importa a cuál apunte cada punto_muestreo.eca_id, la evaluación ECA
siempre usa los valores oficiales del DS.

Operaciones:
    UPDATE   sobre discrepancias de valor
    DELETE   sobre "fantasmas" (BD regula pero DS dice no regulado)
    UPSERT   sobre faltantes (DS regula pero la BD no tiene fila)

Incluye expresado_como y forma_analitica cuando el parámetro lo requiere.

Uso:
    cd lvca_agua
    python -m scripts.reconciliar_ecas_oficiales          # dry-run (solo reporta)
    python -m scripts.reconciliar_ecas_oficiales --apply  # ejecuta cambios

IMPORTANTE: no toca la P034 matricial NH3 (eca_valores_matriciales).
"""

from __future__ import annotations

import sys, os
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.client import get_admin_client
from database.seeds._valores_oficiales_ds import OFICIAL, especie_para


_SUBS_LVCA = {"A2", "D1", "E1", "E2"}


def _mapear_cat_sub(eca_row: dict) -> Optional[str]:
    """Copia de la lógica en auditar_ecas_vs_excel.py — soporta ambos juegos."""
    codigo = (eca_row.get("codigo") or "").upper().strip()
    sub = (eca_row.get("subcategoria") or "").upper().strip()
    if codigo.startswith("ECA-C"):
        tail = codigo.split("C", 1)[-1]
        if len(tail) >= 3:
            cand = tail[1:].strip()
            if cand in _SUBS_LVCA:
                return cand
    for src in (sub, codigo.split(" ", 1)[-1] if " " in codigo else ""):
        prefix = (src or "").replace(" ", "")[:2]
        if prefix in _SUBS_LVCA:
            return prefix
    return None


def _forma_analitica_param(param_codigo: str) -> str:
    """Heurística: parámetros físicos/cualitativos = 'no_aplica'; resto = 'total'."""
    no_aplica = {"P001", "P002", "P003", "P004", "P006", "P011", "P019", "P091",
                 "P120", "P124", "P126", "P130"}
    if param_codigo in no_aplica:
        return "no_aplica"
    return "total"


def _payload_valor(param_codigo: str, cat_sub: str, vmin, vmax) -> dict:
    """Construye el dict de columnas que se escribirán en eca_valores."""
    payload = {
        "valor_minimo":    vmin,
        "valor_maximo":    vmax,
        "expresado_como":  especie_para(param_codigo, cat_sub),
        "forma_analitica": _forma_analitica_param(param_codigo),
    }
    return payload


def _valores_difieren(bd_min, bd_max, ofi_min, ofi_max) -> bool:
    def _eq(a, b):
        if a is None and b is None: return True
        if a is None or b is None:  return False
        return abs(float(a) - float(b)) <= 0.0005
    return not (_eq(bd_min, ofi_min) and _eq(bd_max, ofi_max))


def reconciliar(apply: bool = False) -> None:
    db = get_admin_client()

    # Carga completa
    ecas = db.table("ecas").select("id, codigo, subcategoria").execute().data or []
    params = db.table("parametros").select("id, codigo").execute().data or []
    cod_to_pid = {p["codigo"]: p["id"] for p in params}
    pid_to_codigo = {p["id"]: p["codigo"] for p in params}
    vals = db.table("eca_valores").select(
        "id, eca_id, parametro_id, valor_minimo, valor_maximo"
    ).execute().data or []

    # Mapa: (eca_id, parametro_id) -> fila
    val_existente: dict[tuple, dict] = {(v["eca_id"], v["parametro_id"]): v for v in vals}

    # Agrupar ECAs por cat_sub (cada cat_sub tiene potencialmente 2 ECAs: canónico + antiguo)
    ecas_por_catsub: dict[str, list[dict]] = {}
    for e in ecas:
        cs = _mapear_cat_sub(e)
        if cs in _SUBS_LVCA:
            ecas_por_catsub.setdefault(cs, []).append(e)

    updates: list[tuple] = []   # (fila_id, eca_codigo, p_cod, bd_str, ofi_str, payload)
    deletes: list[tuple] = []   # (fila_id, eca_codigo, p_cod, bd_str)
    inserts: list[tuple] = []   # (eca_codigo, p_cod, payload, ofi_str)

    for p_cod, catsub_map in OFICIAL.items():
        p_id = cod_to_pid.get(p_cod)
        if not p_id:
            continue

        for cs, spec in catsub_map.items():
            ofi_min, ofi_max, _unid = spec
            ecas_cs = ecas_por_catsub.get(cs, [])

            for e in ecas_cs:
                clave = (e["id"], p_id)
                fila = val_existente.get(clave)

                # CASO NO_REGULADO: si existe fila con valor → DELETE
                if ofi_min == "NO_REGULADO":
                    if fila and (fila.get("valor_minimo") is not None
                                 or fila.get("valor_maximo") is not None):
                        bd_str = _describir(fila.get("valor_minimo"), fila.get("valor_maximo"))
                        deletes.append((fila["id"], e["codigo"], p_cod, bd_str))
                    continue

                # Caso normal: verificar coincidencia
                if fila is None:
                    # INSERT
                    payload = _payload_valor(p_cod, cs, ofi_min, ofi_max)
                    payload["eca_id"] = e["id"]
                    payload["parametro_id"] = p_id
                    ofi_str = _describir(ofi_min, ofi_max)
                    inserts.append((e["codigo"], p_cod, payload, ofi_str))
                else:
                    if _valores_difieren(fila.get("valor_minimo"), fila.get("valor_maximo"),
                                          ofi_min, ofi_max):
                        payload = _payload_valor(p_cod, cs, ofi_min, ofi_max)
                        bd_str = _describir(fila.get("valor_minimo"), fila.get("valor_maximo"))
                        ofi_str = _describir(ofi_min, ofi_max)
                        updates.append((fila["id"], e["codigo"], p_cod, bd_str, ofi_str, payload))

    # ── Reporte ──────────────────────────────────────────────────────────────
    modo = "APLICACIÓN" if apply else "DRY-RUN (sin cambios)"
    print("=" * 88)
    print(f"  RECONCILIACIÓN DE VALORES ECA — {modo}")
    print("=" * 88)
    print(f"  Operaciones previstas:")
    print(f"    UPDATE  : {len(updates)}")
    print(f"    DELETE  : {len(deletes)}")
    print(f"    INSERT  : {len(inserts)}")
    print()

    if updates:
        print("─" * 88)
        print("UPDATE (ajustar al valor oficial DS)")
        print("─" * 88)
        for _fid, eca, pc, bd, ofi, _ in sorted(updates, key=lambda x: (x[1], x[2])):
            print(f"  {eca:12s} {pc:5s}  {bd:22s} → {ofi}")
        print()

    if deletes:
        print("─" * 88)
        print("DELETE (el DS no regula — eliminar fila fantasma)")
        print("─" * 88)
        for _fid, eca, pc, bd in sorted(deletes, key=lambda x: (x[1], x[2])):
            print(f"  {eca:12s} {pc:5s}  (tenía {bd} — no debería existir)")
        print()

    if inserts:
        print("─" * 88)
        print("INSERT (el DS regula pero la BD no tenía fila)")
        print("─" * 88)
        for eca, pc, _payload, ofi in sorted(inserts, key=lambda x: (x[0], x[1])):
            print(f"  {eca:12s} {pc:5s}  → {ofi}")
        print()

    if not apply:
        print("  Para APLICAR estos cambios ejecuta:")
        print("    python -m scripts.reconciliar_ecas_oficiales --apply")
        return

    # ── Aplicar ──────────────────────────────────────────────────────────────
    print("─" * 88)
    print("EJECUTANDO CAMBIOS...")
    print("─" * 88)

    ok_u = ok_d = ok_i = 0
    errores: list[str] = []

    # UPDATES
    for fid, eca, pc, _bd, _ofi, payload in updates:
        try:
            db.table("eca_valores").update(payload).eq("id", fid).execute()
            ok_u += 1
        except Exception as exc:
            errores.append(f"UPDATE {eca}/{pc}: {exc}")

    # DELETES
    for fid, eca, pc, _bd in deletes:
        try:
            db.table("eca_valores").delete().eq("id", fid).execute()
            ok_d += 1
        except Exception as exc:
            errores.append(f"DELETE {eca}/{pc}: {exc}")

    # INSERTS (upsert por si existe alguna fila residual por la misma clave)
    for eca, pc, payload, _ofi in inserts:
        try:
            db.table("eca_valores").upsert(
                payload, on_conflict="eca_id,parametro_id"
            ).execute()
            ok_i += 1
        except Exception as exc:
            errores.append(f"INSERT {eca}/{pc}: {exc}")

    print(f"  UPDATE:  {ok_u}/{len(updates)}")
    print(f"  DELETE:  {ok_d}/{len(deletes)}")
    print(f"  INSERT:  {ok_i}/{len(inserts)}")
    if errores:
        print(f"\n  ERRORES ({len(errores)}):")
        for e in errores:
            print(f"    {e}")
    else:
        print(f"\n  Sin errores. Los 2 juegos de ECAs (canónico y antiguo) quedan alineados.")


def _describir(vmin, vmax) -> str:
    if vmin is not None and vmax is not None:
        return f"[{vmin}–{vmax}]"
    if vmax is not None:
        return f"≤ {vmax}"
    if vmin is not None:
        return f"≥ {vmin}"
    return "sin límite"


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    reconciliar(apply=apply)
