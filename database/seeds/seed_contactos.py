"""
database/seeds/seed_contactos.py
Libreta de destinatarios para el envio de informes por correo (tabla
contactos_informes, migracion 025). Carga los correos oficiales de las
personas/entidades que reciben los informes desde la pagina de Informes.

UPSERT idempotente por 'correo' (columna UNIQUE): re-ejecutable sin duplicar.
Los correos se normalizan a minusculas, igual que services.contactos_service.

Ejecutar:
    cd lvca_agua && python -m database.seeds.seed_contactos
"""

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from database.client import get_admin_client
from database.seeds._utils import upsert_batch, imprimir_resumen


# ─────────────────────────────────────────────────────────────────────────────
# Destinatarios oficiales de informes  -  AUTODEMA / SEDAPAR / SUNASS / ANA
# ─────────────────────────────────────────────────────────────────────────────
CONTACTOS: list[dict] = [
    {"nombre": "Felix Elias Valdivia Roldan",                                 "correo": "fevaldivia@autodema.gob.pe",       "entidad": "AUTODEMA"},
    {"nombre": "Jurgen Bedoya Brandacher",                                    "correo": "jbedoya@sedapar.pe",               "entidad": "SEDAPAR"},
    {"nombre": "Jurgen Bedoya Brandacher",                                    "correo": "jurgenbedoya@gmail.com",           "entidad": "SEDAPAR"},
    {"nombre": "Ydelfonso Jorge Palma Cruz",                                  "correo": "ypalma@autodema.gob.pe",           "entidad": "AUTODEMA"},
    {"nombre": "Henry Alayo Calizaya",                                        "correo": "halayo@sunass.gob.pe",             "entidad": "SUNASS"},
    {"nombre": "Saul Alire Benavides",                                        "correo": "salire@sunass.gob.pe",             "entidad": "SUNASS"},
    {"nombre": "Johnny Carlos Castro Patino",                                 "correo": "jcastro@ana.gob.pe",               "entidad": "ANA"},
    {"nombre": "Andres Arqque Huayapa",                                       "correo": "aarqque@sedapar.com.pe",           "entidad": "SEDAPAR"},
    {"nombre": "Carmen Elvira Muniz Delgado",                                 "correo": "cmuniz@sedapar.com.pe",            "entidad": "SEDAPAR"},
    {"nombre": "Valentin Ruben Orcon Zamora",                                 "correo": "vorcon@autodema.gob.pe",           "entidad": "AUTODEMA"},
    {"nombre": "Ana Lucia Paz Alcazar",                                       "correo": "apaz@autodema.gob.pe",             "entidad": "AUTODEMA"},
    {"nombre": "Laboratorio de Vigilancia de la Calidad del Agua AUTODEMA",   "correo": "lvca.vigilancia@autodema.gob.pe",  "entidad": "AUTODEMA"},
    {"nombre": "Eliana Fani Colque Pocco",                                    "correo": "ecolque@sedapar.com.pe",           "entidad": "SEDAPAR"},
    {"nombre": "Adrian Llacho Huarza",                                        "correo": "sanaleaz123@gmail.com",            "entidad": "AUTODEMA"},
]


def run() -> None:
    db = get_admin_client()

    filas: list[dict] = []
    for c in CONTACTOS:
        filas.append({
            "nombre":  c["nombre"].strip(),
            "correo":  c["correo"].strip().lower(),
            "entidad": (c.get("entidad") or "").strip() or None,
            "activo":  True,
        })
        print(f"  {c['nombre'][:45]:<45}  {c['correo']}")

    ok, errores = upsert_batch(db, "contactos_informes", filas, "correo")
    imprimir_resumen("SEED: contactos_informes", len(CONTACTOS), ok, errores)


if __name__ == "__main__":
    run()
