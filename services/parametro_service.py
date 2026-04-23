"""
services/parametro_service.py
Lógica de negocio para gestión de parámetros, categorías y valores ECA.

Funciones públicas:
    get_parametros(filtro_categoria, busqueda)  → lista filtrada
    get_parametro(parametro_id)                 → detalle con joins
    crear_parametro(datos)                      → insert
    actualizar_parametro(parametro_id, datos)   → update
    toggle_parametro(parametro_id, activo)      → activar/desactivar
    get_categorias()                            → lista de categorías
    get_unidades()                              → lista de unidades
    get_ecas()                                  → lista de ECAs activos
    get_valores_eca(eca_id)                     → límites por parámetro
    guardar_valor_eca(eca_id, parametro_id, min, max) → upsert límite
    eliminar_valor_eca(eca_id, parametro_id)    → borra un límite
"""

from __future__ import annotations

from typing import Optional

from database.client import get_admin_client
from services.audit_service import registrar_cambio, registrar_cambios_multiples
from services.cache import cached
from services.parametro_registry import invalidar_cache_parametros


# ─────────────────────────────────────────────────────────────────────────────
# Parámetros
# ─────────────────────────────────────────────────────────────────────────────

@cached(ttl=300)
def get_parametros(
    filtro_categoria: Optional[str] = None,
    busqueda: Optional[str] = None,
    solo_activos: bool = False,
) -> list[dict]:
    """Retorna parámetros con categoría y unidad, filtros opcionales."""
    db = get_admin_client()
    query = (
        db.table("parametros")
        .select(
            "id, codigo, nombre, descripcion, metodo_analitico, activo, "
            "es_eca, observacion_tecnica, "   # migración 010
            "forma_analitica, "               # migración 012
            "categorias_parametro(id, nombre), "
            "unidades_medida(id, simbolo, nombre)"
        )
        .order("codigo")
    )

    if solo_activos:
        query = query.eq("activo", True)

    data = query.execute().data or []

    # Filtros en memoria (Supabase no soporta ilike en FK fácilmente)
    if filtro_categoria:
        data = [
            p for p in data
            if (p.get("categorias_parametro") or {}).get("id") == filtro_categoria
        ]

    if busqueda:
        term = busqueda.lower()
        data = [
            p for p in data
            if term in (p.get("codigo") or "").lower()
            or term in (p.get("nombre") or "").lower()
            or term in (p.get("descripcion") or "").lower()
        ]

    return data


def get_parametro(parametro_id: str) -> dict | None:
    """Detalle de un parámetro con joins."""
    db = get_admin_client()
    res = (
        db.table("parametros")
        .select(
            "id, codigo, nombre, descripcion, metodo_analitico, activo, "
            "categoria_id, unidad_id, "
            "es_eca, observacion_tecnica, "   # migración 010
            "forma_analitica, "               # migración 012
            "categorias_parametro(id, nombre), "
            "unidades_medida(id, simbolo, nombre)"
        )
        .eq("id", parametro_id)
        .maybe_single()
        .execute()
    )
    return res.data


def crear_parametro(datos: dict) -> dict:
    """Inserta un nuevo parámetro. Retorna el registro creado."""
    db = get_admin_client()
    fila = {
        "codigo":           datos["codigo"],
        "nombre":           datos["nombre"],
        "descripcion":      datos.get("descripcion") or None,
        "categoria_id":     datos.get("categoria_id") or None,
        "unidad_id":        datos.get("unidad_id") or None,
        "metodo_analitico": datos.get("metodo_analitico") or None,
        "activo":           True,
    }
    res = db.table("parametros").insert(fila).execute()
    creado = res.data[0]
    registrar_cambio(
        tabla="parametros",
        registro_id=creado["id"],
        accion="crear",
        valor_nuevo=f"{datos['codigo']} — {datos['nombre']}",
    )
    invalidar_cache_parametros()
    return creado


def actualizar_parametro(parametro_id: str, datos: dict) -> dict:
    """Actualiza campos de un parámetro existente."""
    db = get_admin_client()

    # Leer valores anteriores para auditoría
    anterior = (
        db.table("parametros")
        .select("nombre, descripcion, categoria_id, unidad_id, metodo_analitico")
        .eq("id", parametro_id)
        .single()
        .execute()
    ).data or {}

    campos = {}
    for key in ("nombre", "descripcion", "categoria_id", "unidad_id", "metodo_analitico"):
        if key in datos:
            campos[key] = datos[key] or None

    res = (
        db.table("parametros")
        .update(campos)
        .eq("id", parametro_id)
        .execute()
    )

    # Registrar cambios en audit log
    cambios = {
        k: (anterior.get(k), v)
        for k, v in campos.items()
        if str(anterior.get(k)) != str(v)
    }
    if cambios:
        registrar_cambios_multiples(
            tabla="parametros",
            registro_id=parametro_id,
            accion="editar",
            cambios=cambios,
        )

    invalidar_cache_parametros()
    return res.data[0]


def toggle_parametro(parametro_id: str, activo: bool) -> None:
    """Activa o desactiva un parámetro."""
    db = get_admin_client()
    db.table("parametros").update({"activo": activo}).eq("id", parametro_id).execute()
    registrar_cambio(
        tabla="parametros",
        registro_id=parametro_id,
        accion="activar" if activo else "desactivar",
        campo="activo",
        valor_anterior=str(not activo),
        valor_nuevo=str(activo),
    )
    invalidar_cache_parametros()


def eliminar_parametro(parametro_id: str) -> str:
    """
    Elimina un parámetro. Si tiene resultados de laboratorio vinculados,
    lo marca como inactivo en lugar de borrarlo (evita pérdida de datos).

    Retorna 'eliminado' o 'desactivado'.
    """
    db = get_admin_client()

    # Leer datos para auditoría
    param_data = (
        db.table("parametros")
        .select("codigo, nombre")
        .eq("id", parametro_id)
        .maybe_single()
        .execute()
    ).data or {}
    param_desc = f"{param_data.get('codigo', '')} — {param_data.get('nombre', '')}"

    # Verificar resultados vinculados
    r_count = (
        db.table("resultados_laboratorio")
        .select("id", count="exact")
        .eq("parametro_id", parametro_id)
        .execute()
    )
    if (r_count.count or 0) > 0:
        # No eliminar — marcar como inactivo
        db.table("parametros").update({"activo": False}).eq("id", parametro_id).execute()
        registrar_cambio(
            tabla="parametros",
            registro_id=parametro_id,
            accion="desactivar",
            valor_anterior=param_desc,
            valor_nuevo=f"Desactivado (tiene {r_count.count} resultado(s) vinculado(s))",
        )
        invalidar_cache_parametros()
        return "desactivado"

    # Sin resultados: eliminar valores ECA y el parámetro
    db.table("eca_valores").delete().eq("parametro_id", parametro_id).execute()
    db.table("parametros").delete().eq("id", parametro_id).execute()
    registrar_cambio(
        tabla="parametros",
        registro_id=parametro_id,
        accion="eliminar",
        valor_anterior=param_desc,
    )
    invalidar_cache_parametros()
    return "eliminado"


# ─────────────────────────────────────────────────────────────────────────────
# Categorías y unidades
# ─────────────────────────────────────────────────────────────────────────────

def get_categorias() -> list[dict]:
    """Todas las categorías de parámetro."""
    db = get_admin_client()
    res = (
        db.table("categorias_parametro")
        .select("id, nombre, descripcion")
        .order("nombre")
        .execute()
    )
    return res.data or []


def get_unidades() -> list[dict]:
    """Todas las unidades de medida."""
    db = get_admin_client()
    res = (
        db.table("unidades_medida")
        .select("id, simbolo, nombre")
        .order("simbolo")
        .execute()
    )
    return res.data or []


def crear_unidad(simbolo: str, nombre: str) -> dict:
    """Crea una nueva unidad de medida. Retorna el registro creado."""
    db = get_admin_client()
    fila = {"simbolo": simbolo.strip(), "nombre": nombre.strip()}
    res = db.table("unidades_medida").insert(fila).execute()
    invalidar_cache_parametros()
    return res.data[0]


# ─────────────────────────────────────────────────────────────────────────────
# ECAs y valores límite
# ─────────────────────────────────────────────────────────────────────────────

def get_ecas() -> list[dict]:
    """ECAs activos."""
    db = get_admin_client()
    res = (
        db.table("ecas")
        .select("id, codigo, nombre, categoria, subcategoria, descripcion, activo")
        .eq("activo", True)
        .order("codigo")
        .execute()
    )
    return res.data or []


def get_valores_eca(eca_id: str) -> list[dict]:
    """
    Valores límite de un ECA con datos del parámetro.
    Retorna lista de {id, parametro_id, valor_minimo, valor_maximo,
                      parametro_codigo, parametro_nombre, unidad}.
    """
    db = get_admin_client()
    res = (
        db.table("eca_valores")
        .select(
            "id, parametro_id, valor_minimo, valor_maximo, "
            "expresado_como, "                # migración 010
            "forma_analitica, "               # migración 012
            "parametros(codigo, nombre, es_eca, forma_analitica, unidades_medida(simbolo))"
        )
        .eq("eca_id", eca_id)
        .execute()
    )
    items = []
    for r in (res.data or []):
        prm = r.get("parametros") or {}
        items.append({
            "id":                      r["id"],
            "parametro_id":            r["parametro_id"],
            "valor_minimo":            r["valor_minimo"],
            "valor_maximo":            r["valor_maximo"],
            "expresado_como":          r.get("expresado_como"),
            "eca_forma_analitica":     r.get("forma_analitica"),
            "parametro_codigo":        prm.get("codigo", ""),
            "parametro_nombre":        prm.get("nombre", ""),
            "parametro_es_eca":        prm.get("es_eca", True),
            "parametro_forma_analitica": prm.get("forma_analitica"),
            "unidad":                  (prm.get("unidades_medida") or {}).get("simbolo", ""),
        })
    items.sort(key=lambda x: x["parametro_codigo"])
    return items


def guardar_valor_eca(
    eca_id: str,
    parametro_id: str,
    valor_minimo: Optional[float],
    valor_maximo: Optional[float],
) -> None:
    """Upsert de un valor límite ECA."""
    db = get_admin_client()
    fila = {
        "eca_id":       eca_id,
        "parametro_id": parametro_id,
        "valor_minimo": valor_minimo,
        "valor_maximo": valor_maximo,
    }
    db.table("eca_valores").upsert(
        fila, on_conflict="eca_id,parametro_id"
    ).execute()
    invalidar_cache_parametros()


def eliminar_valor_eca(valor_id: str) -> None:
    """Elimina un registro de eca_valores por su ID."""
    db = get_admin_client()
    db.table("eca_valores").delete().eq("id", valor_id).execute()
    invalidar_cache_parametros()
