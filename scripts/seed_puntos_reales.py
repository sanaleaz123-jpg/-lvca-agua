"""
scripts/seed_puntos_reales.py
Carga los 12 puntos de muestreo reales del programa de monitoreo AUTODEMA.
Desactiva/elimina puntos que no están en la lista.

Ejecutar una sola vez:
    python scripts/seed_puntos_reales.py
"""

import math
import sys
import os

# Agregar el directorio raíz al path para importar módulos del proyecto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.client import get_admin_client


# ─────────────────────────────────────────────────────────────────────────────
# Conversión UTM → Lat/Lon (WGS84)
# ─────────────────────────────────────────────────────────────────────────────

def utm_to_latlon(easting: float, northing: float, zone: int, southern: bool = True):
    """Convierte coordenadas UTM a latitud/longitud WGS84."""
    if southern:
        northing = northing - 10_000_000

    a = 6_378_137.0
    f = 1 / 298.257223563
    e = math.sqrt(2 * f - f ** 2)
    e2 = e ** 2
    k0 = 0.9996
    x = easting - 500_000
    y = northing
    lon0 = (zone - 1) * 6 - 180 + 3

    M = y / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))

    phi1 = mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
    phi1 += (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
    phi1 += (151 * e1 ** 3 / 96) * math.sin(6 * mu)

    N1 = a / math.sqrt(1 - e2 * math.sin(phi1) ** 2)
    T1 = math.tan(phi1) ** 2
    C1 = e2 / (1 - e2) * math.cos(phi1) ** 2
    R1 = a * (1 - e2) / (1 - e2 * math.sin(phi1) ** 2) ** 1.5
    D = x / (N1 * k0)
    ep2 = e2 / (1 - e2)

    lat = phi1 - (N1 * math.tan(phi1) / R1) * (
        D ** 2 / 2
        - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
        + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720
    )

    lon = (
        D
        - (1 + 2 * T1 + C1) * D ** 3 / 6
        + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120
    ) / math.cos(phi1)

    return round(math.degrees(lat), 8), round(lon0 + math.degrees(lon), 8)


# ─────────────────────────────────────────────────────────────────────────────
# Datos reales de los 12 puntos de muestreo AUTODEMA
# ─────────────────────────────────────────────────────────────────────────────

PUNTOS_REALES = [
    {
        "codigo": "134Pañe3E",
        "nombre": "Represa El Pañe",
        "cuenca": "Colca - Camana",
        "subcuenca": "Chili Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "4 E1",
        "utm_zona": "19 L",
        "utm_este": 278106,
        "utm_norte": 8294236,
        "altitud_msnm": 4600,
        "zona_num": 19,
    },
    {
        "codigo": "134EBamp3E",
        "nombre": "Represa Bamputañe",
        "cuenca": "Quilca - Chili - Vito",
        "subcuenca": "Chili Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "1 A2",
        "utm_zona": "19 L",
        "utm_este": 282787,
        "utm_norte": 8293198,
        "altitud_msnm": 4550,
        "zona_num": 19,
    },
    {
        "codigo": "134EDesp3E",
        "nombre": "Dique de los Españoles",
        "cuenca": "Colca - Camana",
        "subcuenca": "Chili Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "4 E1",
        "utm_zona": "19 L",
        "utm_este": 280415,
        "utm_norte": 8254877,
        "altitud_msnm": 4441,
        "zona_num": 19,
    },
    {
        "codigo": "132EPill3E",
        "nombre": "Represa Pillones",
        "cuenca": "Quilca - Chili - Vito",
        "subcuenca": "Chili Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "4 E1",
        "utm_zona": "19 L",
        "utm_este": 262019,
        "utm_norte": 8250567,
        "altitud_msnm": 4421,
        "zona_num": 19,
    },
    {
        "codigo": "132EChal3E",
        "nombre": "Represa Chalhuanca",
        "cuenca": "Quilca - Chili - Vito",
        "subcuenca": "Chili Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "4 E1",
        "utm_zona": "19 L",
        "utm_este": 249931,
        "utm_norte": 8252391,
        "altitud_msnm": 4421,
        "zona_num": 19,
    },
    {
        "codigo": "132RSumb4",
        "nombre": "Rio Sumbay",
        "cuenca": "Quilca - Chili - Vito",
        "subcuenca": "Chili Regulado",
        "tipo": "rio",
        "matriz": "ADR",
        "eca_codigo": "4 E2",
        "utm_zona": "19 L",
        "utm_este": 247270,
        "utm_norte": 8222414,
        "altitud_msnm": 3891,
        "zona_num": 19,
    },
    {
        "codigo": "132EFray3E",
        "nombre": "Represa Frayle",
        "cuenca": "Quilca - Chili - Vito",
        "subcuenca": "Chili Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "4 E1",
        "utm_zona": "19 K",
        "utm_este": 265892,
        "utm_norte": 8213365,
        "altitud_msnm": 4108,
        "zona_num": 19,
    },
    {
        "codigo": "132EABla3",
        "nombre": "Represa Aguada Blanca",
        "cuenca": "Quilca - Chili - Vito",
        "subcuenca": "Chili Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "4 E1",
        "utm_zona": "19 K",
        "utm_este": 249333,
        "utm_norte": 8202376,
        "altitud_msnm": 3670,
        "zona_num": 19,
    },
    {
        "codigo": "134ECond3",
        "nombre": "Represa Condoroma",
        "cuenca": "Colca - Camana",
        "subcuenca": "Colca Regulado",
        "tipo": "laguna",
        "matriz": "ADL",
        "eca_codigo": "1 A2",
        "utm_zona": "19 L",
        "utm_este": 254878,
        "utm_norte": 8296213,
        "altitud_msnm": 4434,
        "zona_num": 19,
    },
    {
        "codigo": "134ETuti",
        "nombre": "Bocatoma Tuti",
        "cuenca": "Colca - Camana",
        "subcuenca": "Colca Regulado",
        "tipo": "canal",
        "matriz": "ADR",
        "eca_codigo": "3 D1",
        "utm_zona": "19 L",
        "utm_este": 227624,
        "utm_norte": 8280844,
        "altitud_msnm": 3850,
        "zona_num": 19,
    },
    {
        "codigo": "134RHuam",
        "nombre": "Desarenador Huambo",
        "cuenca": "Colca - Camana",
        "subcuenca": "Colca Regulado",
        "tipo": "canal",
        "matriz": "ADR",
        "eca_codigo": "3 D1",
        "utm_zona": "18 L",
        "utm_este": 810970,
        "utm_norte": 8253514,
        "altitud_msnm": 3616,
        "zona_num": 18,
    },
    {
        "codigo": "132RSigu3",
        "nombre": "Bocatoma Pitay",
        "cuenca": "Colca - Camana",
        "subcuenca": "Colca Regulado",
        "tipo": "canal",
        "matriz": "ADR",
        "eca_codigo": "3 D1",
        "utm_zona": "18 K",
        "utm_este": 815385,
        "utm_norte": 8207055,
        "altitud_msnm": 1684,
        "zona_num": 18,
    },
]

# ECAs según D.S. N° 004-2017-MINAM
ECAS_DEFINICION = {
    "1 A2": {
        "codigo": "1 A2",
        "nombre": "Cat. 1-A2: Aguas para consumo humano - Convencional",
        "categoria": "1 - Poblacional y recreacional",
        "subcategoria": "A2 - Convencional",
        "descripcion": "Aguas que pueden ser potabilizadas con tratamiento convencional",
    },
    "3 D1": {
        "codigo": "3 D1",
        "nombre": "Cat. 3-D1: Riego de vegetales",
        "categoria": "3 - Riego de vegetales y bebida de animales",
        "subcategoria": "D1 - Riego de vegetales",
        "descripcion": "Aguas utilizadas para riego de vegetales de tallo bajo y alto",
    },
    "4 E1": {
        "codigo": "4 E1",
        "nombre": "Cat. 4-E1: Lagunas y lagos",
        "categoria": "4 - Conservación del ambiente acuático",
        "subcategoria": "E1 - Lagunas y lagos",
        "descripcion": "Ecosistemas lénticos: lagunas, lagos y embalses",
    },
    "4 E2": {
        "codigo": "4 E2",
        "nombre": "Cat. 4-E2: Ríos costa y sierra",
        "categoria": "4 - Conservación del ambiente acuático",
        "subcategoria": "E2 - Ríos costa y sierra",
        "descripcion": "Ecosistemas lóticos: ríos de costa y sierra",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Ejecución
# ─────────────────────────────────────────────────────────────────────────────

def main():
    db = get_admin_client()
    codigos_reales = {p["codigo"] for p in PUNTOS_REALES}

    print("=" * 60)
    print("SEED: Puntos de muestreo reales AUTODEMA")
    print("=" * 60)

    # ── 1. Crear/actualizar ECAs ──────────────────────────────────────────
    print("\n1. Verificando ECAs...")
    eca_map: dict[str, str] = {}  # codigo → id

    ecas_existentes = db.table("ecas").select("id, codigo").execute()
    for e in (ecas_existentes.data or []):
        eca_map[e["codigo"]] = e["id"]

    for cod, datos in ECAS_DEFINICION.items():
        if cod in eca_map:
            print(f"   ECA '{cod}' ya existe (id={eca_map[cod][:8]}...)")
        else:
            res = db.table("ecas").insert({
                "codigo": datos["codigo"],
                "nombre": datos["nombre"],
                "categoria": datos["categoria"],
                "subcategoria": datos["subcategoria"],
                "descripcion": datos["descripcion"],
                "activo": True,
            }).execute()
            eca_map[cod] = res.data[0]["id"]
            print(f"   ECA '{cod}' creado (id={eca_map[cod][:8]}...)")

    # ── 2. Limpiar puntos antiguos ────────────────────────────────────────
    print("\n2. Limpiando puntos antiguos...")
    puntos_actuales = (
        db.table("puntos_muestreo")
        .select("id, codigo, nombre")
        .execute()
    )

    n_eliminados = 0
    for p in (puntos_actuales.data or []):
        if p["codigo"] not in codigos_reales:
            # Verificar si tiene muestras
            m_count = (
                db.table("muestras")
                .select("id", count="exact")
                .eq("punto_muestreo_id", p["id"])
                .execute()
            )
            if (m_count.count or 0) > 0:
                # Tiene muestras, solo desactivar
                db.table("puntos_muestreo").update({"activo": False}).eq("id", p["id"]).execute()
                print(f"   Desactivado: {p['codigo']} — {p['nombre']} (tiene muestras)")
            else:
                # Sin muestras, eliminar vínculos y punto
                db.table("campana_puntos").delete().eq("punto_muestreo_id", p["id"]).execute()
                db.table("puntos_muestreo").delete().eq("id", p["id"]).execute()
                print(f"   Eliminado: {p['codigo']} — {p['nombre']}")
                n_eliminados += 1

    print(f"   Total eliminados: {n_eliminados}")

    # ── 3. Insertar/actualizar los 12 puntos reales ───────────────────────
    print("\n3. Insertando/actualizando 12 puntos reales...")

    # Recargar puntos actuales
    puntos_actuales = (
        db.table("puntos_muestreo")
        .select("id, codigo")
        .execute()
    )
    codigos_existentes = {p["codigo"]: p["id"] for p in (puntos_actuales.data or [])}

    for pt in PUNTOS_REALES:
        # Calcular lat/lon desde UTM
        lat, lon = utm_to_latlon(
            pt["utm_este"], pt["utm_norte"],
            pt["zona_num"], southern=True,
        )

        eca_id = eca_map.get(pt["eca_codigo"])

        fila = {
            "codigo": pt["codigo"],
            "nombre": pt["nombre"],
            "descripcion": f"{pt['matriz']} — {pt['nombre']}",
            "tipo": pt["tipo"],
            "cuenca": pt["cuenca"],
            "subcuenca": pt["subcuenca"],
            "utm_este": pt["utm_este"],
            "utm_norte": pt["utm_norte"],
            "utm_zona": pt["utm_zona"],
            "latitud": lat,
            "longitud": lon,
            "altitud_msnm": pt["altitud_msnm"],
            "eca_id": eca_id,
            "entidad_responsable": "AUTODEMA",
            "activo": True,
        }

        if pt["codigo"] in codigos_existentes:
            # Actualizar
            punto_id = codigos_existentes[pt["codigo"]]
            fila.pop("codigo")  # no actualizar el código
            db.table("puntos_muestreo").update(fila).eq("id", punto_id).execute()
            print(f"   Actualizado: {pt['codigo']} — {pt['nombre']} ({lat:.6f}, {lon:.6f})")
        else:
            # Insertar
            db.table("puntos_muestreo").insert(fila).execute()
            print(f"   Insertado:   {pt['codigo']} — {pt['nombre']} ({lat:.6f}, {lon:.6f})")

    # ── 4. Resumen ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    total = (
        db.table("puntos_muestreo")
        .select("id", count="exact")
        .eq("activo", True)
        .execute()
    )
    print(f"Total puntos activos en la base de datos: {total.count}")
    print("=" * 60)
    print("\nListo. Los 12 puntos reales de monitoreo están cargados.")


if __name__ == "__main__":
    main()
