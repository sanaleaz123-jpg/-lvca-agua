"""
database/seeds/seed_puntos.py
12 puntos de muestreo del Proyecto Majes-Siguas / cuenca Chili-Quilca - AUTODEMA.
UPSERT idempotente por 'codigo'. Convierte UTM zona 19S a WGS84 con pyproj.

Puntos incluidos:
    PM-01  Embalse Pillones - Presa
    PM-02  Laguna Pañe - espejo de agua
    PM-03  Embalse El Frayle - Presa
    PM-04  Embalse Bamputañe - Presa
    PM-05  Bocatoma La Tomilla II - Rio Chili
    PM-06  Rio Chili - Puente Añashuayco
    PM-07  Rio Chili - Puente San Isidro
    PM-08  Rio Chili - Puente Grau (aguas abajo)
    PM-09  Laguna de Salinas
    PM-10  Canal Madre Majes - Bocatoma Pitay
    PM-11  Rio Siguas - Puente Reparticion
    PM-12  Rio Colca - Cabanaconde

Ejecutar:
    cd lvca_agua && python -m database.seeds.seed_puntos
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds._utils import upsert_batch, imprimir_resumen

try:
    from pyproj import Transformer
    _transformer = Transformer.from_crs("EPSG:32719", "EPSG:4326", always_xy=True)
    _PYPROJ_OK = True
except ImportError:
    _transformer = None
    _PYPROJ_OK = False
    print("  ADVERTENCIA: pyproj no instalado. Se usaran lat/lon manuales del registro.")


def _utm19s_a_wgs84(este: float, norte: float) -> tuple[float | None, float | None]:
    if _transformer:
        lon, lat = _transformer.transform(este, norte)
        return round(lat, 8), round(lon, 8)
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# 12 PUNTOS DE MUESTREO  -  Cuenca Chili-Quilca / Proyecto Majes-Siguas
# Coordenadas UTM WGS84 Zona 19S  (EPSG:32719)
# ─────────────────────────────────────────────────────────────────────────────
PUNTOS: list[dict] = [
    {
        "codigo": "PM-01",
        "nombre": "Embalse Pillones - Presa",
        "descripcion": (
            "Espejo de agua principal del embalse Pillones. Punto de monitoreo "
            "aguas abajo de la presa, cuenca alta rio Sumbay. "
            "Altitud 4352 msnm. Cuenca Chili."
        ),
        "tipo": "laguna",
        "utm_este":  263843.0,
        "utm_norte": 8245291.0,
        "altitud_msnm": 4352.0,
        "cuenca": "Chili",
        "subcuenca": "Sumbay - Pillones",
        "codigo_eca": "ECA-C4E1",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-02",
        "nombre": "Laguna Pane - espejo de agua",
        "descripcion": (
            "Laguna Pañe, principal reservorio hídrico del sistema de embalses "
            "de AUTODEMA. Altitud 4596 msnm. Cuenca Chili, provincia Caylloma."
        ),
        "tipo": "laguna",
        "utm_este":  271654.0,
        "utm_norte": 8246127.0,
        "altitud_msnm": 4596.0,
        "cuenca": "Chili",
        "subcuenca": "Pane",
        "codigo_eca": "ECA-C4E1",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-03",
        "nombre": "Embalse El Frayle - Presa",
        "descripcion": (
            "Embalse El Frayle, sistema de regulacion de caudales del rio Chili. "
            "Punto de monitoreo aguas arriba de la presa. Altitud 4178 msnm."
        ),
        "tipo": "laguna",
        "utm_este":  259176.0,
        "utm_norte": 8247082.0,
        "altitud_msnm": 4178.0,
        "cuenca": "Chili",
        "subcuenca": "Frayle",
        "codigo_eca": "ECA-C4E1",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-04",
        "nombre": "Embalse Bamputane - Presa",
        "descripcion": (
            "Embalse Bamputañe, componente del sistema hidrologico AUTODEMA. "
            "Altitud 4494 msnm. Cuenca alta Chili, Caylloma."
        ),
        "tipo": "laguna",
        "utm_este":  274329.0,
        "utm_norte": 8246408.0,
        "altitud_msnm": 4494.0,
        "cuenca": "Chili",
        "subcuenca": "Bamputane",
        "codigo_eca": "ECA-C4E1",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-05",
        "nombre": "Bocatoma La Tomilla II - Rio Chili aguas arriba",
        "descripcion": (
            "Punto de captacion de la Bocatoma La Tomilla II de SEDAPAR. "
            "Monitoreo de calidad de agua para consumo humano aguas arriba "
            "de la toma. Altitud 2447 msnm. ECA Cat. 1 A2."
        ),
        "tipo": "rio",
        "utm_este":  226487.0,
        "utm_norte": 8188934.0,
        "altitud_msnm": 2447.0,
        "cuenca": "Chili",
        "subcuenca": "Chili Medio",
        "codigo_eca": "ECA-C1A2",
        "entidad_responsable": "AUTODEMA / SEDAPAR",
    },
    {
        "codigo": "PM-06",
        "nombre": "Rio Chili - Puente Anashuayco",
        "descripcion": (
            "Rio Chili a la altura del Puente Añashuayco, aguas arriba de "
            "la ciudad de Arequipa. Punto de monitoreo de baseline. "
            "Altitud 2466 msnm."
        ),
        "tipo": "rio",
        "utm_este":  225783.0,
        "utm_norte": 8190124.0,
        "altitud_msnm": 2466.0,
        "cuenca": "Chili",
        "subcuenca": "Chili Alto urbano",
        "codigo_eca": "ECA-C4E2",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-07",
        "nombre": "Rio Chili - Puente San Isidro",
        "descripcion": (
            "Rio Chili a la altura del Puente San Isidro, sector urbano de "
            "Arequipa. Punto de monitoreo de impacto urbano. Altitud 2370 msnm."
        ),
        "tipo": "rio",
        "utm_este":  228645.0,
        "utm_norte": 8187203.0,
        "altitud_msnm": 2370.0,
        "cuenca": "Chili",
        "subcuenca": "Chili Urbano",
        "codigo_eca": "ECA-C4E2",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-08",
        "nombre": "Rio Chili - Puente Grau aguas abajo",
        "descripcion": (
            "Rio Chili aguas abajo del Puente Grau, sector de salida de la "
            "ciudad de Arequipa. Monitoreo de efecto acumulado de vertimientos. "
            "Altitud 2328 msnm."
        ),
        "tipo": "rio",
        "utm_este":  230923.0,
        "utm_norte": 8184871.0,
        "altitud_msnm": 2328.0,
        "cuenca": "Chili",
        "subcuenca": "Chili Bajo urbano",
        "codigo_eca": "ECA-C4E2",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-09",
        "nombre": "Laguna de Salinas",
        "descripcion": (
            "Laguna de Salinas, humedal altoandino en la reserva nacional Salinas "
            "y Aguada Blanca. Alta concentracion de sales y habitats de flamencos. "
            "Altitud 4316 msnm. Limite Arequipa - Moquegua."
        ),
        "tipo": "laguna",
        "utm_este":  280193.0,
        "utm_norte": 8144058.0,
        "altitud_msnm": 4316.0,
        "cuenca": "Quilca - Camana",
        "subcuenca": "Salinas",
        "codigo_eca": "ECA-C4E1",
        "entidad_responsable": "AUTODEMA / SERNANP",
    },
    {
        "codigo": "PM-10",
        "nombre": "Canal Madre Majes - Bocatoma Pitay",
        "descripcion": (
            "Canal Madre del Proyecto Majes-Siguas a la altura de la bocatoma "
            "Pitay. Punto de control de calidad del agua de riego para el "
            "Proyecto Especial Majes-Siguas. Altitud 1243 msnm."
        ),
        "tipo": "canal",
        "utm_este":  190384.0,
        "utm_norte": 8203842.0,
        "altitud_msnm": 1243.0,
        "cuenca": "Quilca - Camana",
        "subcuenca": "Majes - Siguas",
        "codigo_eca": "ECA-C3D1",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-11",
        "nombre": "Rio Siguas - Puente Reparticion",
        "descripcion": (
            "Rio Siguas a la altura del Puente La Reparticion, Valle de Majes. "
            "Monitoreo de calidad del agua superficial aguas abajo de "
            "la irrigacion. Altitud 1063 msnm."
        ),
        "tipo": "rio",
        "utm_este":  194876.0,
        "utm_norte": 8192367.0,
        "altitud_msnm": 1063.0,
        "cuenca": "Quilca - Camana",
        "subcuenca": "Siguas",
        "codigo_eca": "ECA-C4E2",
        "entidad_responsable": "AUTODEMA",
    },
    {
        "codigo": "PM-12",
        "nombre": "Rio Colca - Cabanaconde",
        "descripcion": (
            "Rio Colca a la altura del poblado de Cabanaconde, Canon del Colca. "
            "Punto de monitoreo hidrologico y biologico en zona de turismo. "
            "Altitud 3287 msnm. Provincia Caylloma."
        ),
        "tipo": "rio",
        "utm_este":  215623.0,
        "utm_norte": 8259431.0,
        "altitud_msnm": 3287.0,
        "cuenca": "Colca - Majes",
        "subcuenca": "Colca Alto",
        "codigo_eca": "ECA-C4E2",
        "entidad_responsable": "AUTODEMA / ANA",
    },
]


def run() -> None:
    assert len(PUNTOS) == 12, f"ERROR: se esperan 12 puntos, hay {len(PUNTOS)}"
    db = get_admin_client()

    # Mapa ECA codigo → id
    eca_map = {r["codigo"]: r["id"]
               for r in db.table("ecas").select("id,codigo").execute().data}

    filas: list[dict] = []
    for p in PUNTOS:
        lat, lon = _utm19s_a_wgs84(p["utm_este"], p["utm_norte"])
        filas.append({
            "codigo":              p["codigo"],
            "nombre":              p["nombre"],
            "descripcion":         p.get("descripcion"),
            "tipo":                p.get("tipo", "rio"),
            "utm_este":            p["utm_este"],
            "utm_norte":           p["utm_norte"],
            "utm_zona":            "19S",
            "latitud":             lat,
            "longitud":            lon,
            "altitud_msnm":        p.get("altitud_msnm"),
            "cuenca":              p.get("cuenca"),
            "subcuenca":           p.get("subcuenca"),
            "eca_id":              eca_map.get(p.get("codigo_eca", "")),
            "entidad_responsable": p.get("entidad_responsable"),
            "activo":              True,
        })
        coord_str = f"({lat:.5f}, {lon:.5f})" if lat else "(pyproj no disponible)"
        print(f"  {p['codigo']}  {p['nombre'][:45]:<45}  {coord_str}")

    ok, errores = upsert_batch(db, "puntos_muestreo", filas, "codigo")
    imprimir_resumen("SEED: puntos_muestreo", len(PUNTOS), ok, errores)


if __name__ == "__main__":
    run()
