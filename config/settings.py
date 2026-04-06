"""
config/settings.py
Carga todas las variables de entorno y expone constantes de configuración.
En Streamlit Cloud las variables se definen en st.secrets (secrets.toml);
en desarrollo local se leen desde el archivo .env.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Buscar .env en la raíz del proyecto (un nivel arriba de config/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _require(key: str) -> str:
    """Lee una variable de entorno; lanza ValueError si falta."""
    value = os.environ.get(key, "").strip()
    if not value:
        raise ValueError(
            f"Variable de entorno requerida no encontrada: '{key}'. "
            f"Revisa tu archivo .env o los secrets de Streamlit Cloud."
        )
    return value


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL: str       = _require("SUPABASE_URL")
SUPABASE_ANON_KEY: str  = _require("SUPABASE_ANON_KEY")   # cliente web / Auth
SUPABASE_SERVICE_KEY: str = _optional("SUPABASE_SERVICE_KEY")  # solo seeds/admin

# ── SMTP ──────────────────────────────────────────────────────────────────────
SMTP_HOST: str     = _optional("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int     = int(_optional("SMTP_PORT", "587"))
SMTP_USER: str     = _optional("SMTP_USER")
SMTP_PASSWORD: str = _optional("SMTP_PASSWORD")

# ── App ───────────────────────────────────────────────────────────────────────
APP_ENV: str = _optional("APP_ENV", "production")
IS_DEV: bool = APP_ENV == "development"

# ── Constantes de negocio ─────────────────────────────────────────────────────
APP_NOMBRE  = "LVCA – Gestión de Calidad de Agua"
APP_ENTIDAD = "AUTODEMA – Arequipa"
APP_VERSION = "1.0.0"

# Correos de entidades reguladoras (destinos de notificaciones)
EMAIL_ANA    = _optional("EMAIL_ANA",    "ana@ana.gob.pe")
EMAIL_ALA    = _optional("EMAIL_ALA",    "ala.chili@ana.gob.pe")
EMAIL_SEDAPAR = _optional("EMAIL_SEDAPAR","calidad@sedapar.com.pe")
EMAIL_SUNASS = _optional("EMAIL_SUNASS", "oirs@sunass.gob.pe")
