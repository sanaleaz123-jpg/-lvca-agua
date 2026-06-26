"""
services/email_service.py
Envío de informes por correo (SMTP) y bitácora de envíos.

El transporte se configura por variables de entorno / st.secrets
(config/settings): SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_TLS,
SMTP_SSL, SMTP_FROM, SMTP_FROM_NAME. La contraseña NUNCA se guarda en el código.

Funciones públicas:
    smtp_configurado() -> bool
    enviar_correo(destinatarios, asunto, cuerpo, adjuntos) -> None   (lanza en error)
    enviar_correo_prueba(destinatario) -> None
    registrar_envio(...) -> None
    get_envios(campana_id, limite) -> list[dict]
"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional

from database.client import get_db
from services.logging_config import get_logger

logger = get_logger(__name__)

# Tipo de un adjunto: (nombre_archivo, contenido_bytes, mime_type)
Adjunto = tuple[str, bytes, str]


def _cfg():
    """Lee la configuración SMTP en el momento del envío (no al importar)."""
    from config import settings
    return settings


def smtp_configurado() -> bool:
    """True si hay host, usuario y contraseña SMTP cargados."""
    s = _cfg()
    return bool(s.SMTP_HOST and s.SMTP_USER and s.SMTP_PASSWORD)


def _construir_mensaje(
    destinatarios: list[str], asunto: str, cuerpo: str, adjuntos: list[Adjunto],
) -> EmailMessage:
    s = _cfg()
    msg = EmailMessage()
    remitente = s.SMTP_FROM or s.SMTP_USER
    msg["From"] = f"{s.SMTP_FROM_NAME} <{remitente}>" if s.SMTP_FROM_NAME else remitente
    msg["To"] = ", ".join(destinatarios)
    msg["Subject"] = asunto or "Informe LVCA"
    msg.set_content(cuerpo or "")
    for nombre, contenido, mime in (adjuntos or []):
        maintype, _, subtype = (mime or "application/octet-stream").partition("/")
        msg.add_attachment(
            contenido, maintype=maintype or "application",
            subtype=subtype or "octet-stream", filename=nombre,
        )
    return msg


def _enviar(msg: EmailMessage) -> None:
    """Abre la conexión SMTP (SSL o STARTTLS) y envía el mensaje."""
    s = _cfg()
    if not smtp_configurado():
        raise ValueError(
            "El servidor de correo no está configurado. Define SMTP_HOST, "
            "SMTP_USER y SMTP_PASSWORD en el archivo .env o en los secrets de "
            "Streamlit."
        )
    ctx = ssl.create_default_context()
    if s.SMTP_SSL:
        with smtplib.SMTP_SSL(s.SMTP_HOST, s.SMTP_PORT, context=ctx, timeout=30) as srv:
            srv.login(s.SMTP_USER, s.SMTP_PASSWORD)
            srv.send_message(msg)
    else:
        with smtplib.SMTP(s.SMTP_HOST, s.SMTP_PORT, timeout=30) as srv:
            srv.ehlo()
            if s.SMTP_TLS:
                srv.starttls(context=ctx)
                srv.ehlo()
            srv.login(s.SMTP_USER, s.SMTP_PASSWORD)
            srv.send_message(msg)


def enviar_correo(
    destinatarios: list[str], asunto: str, cuerpo: str,
    adjuntos: Optional[list[Adjunto]] = None,
) -> None:
    """Envía un correo con adjuntos. Lanza excepción con mensaje claro si falla."""
    destinatarios = [d.strip() for d in (destinatarios or []) if d and d.strip()]
    if not destinatarios:
        raise ValueError("No hay destinatarios para el envío.")
    try:
        msg = _construir_mensaje(destinatarios, asunto, cuerpo, adjuntos or [])
        _enviar(msg)
    except (ValueError,):
        raise
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            "Autenticación SMTP rechazada: revisa el usuario/contraseña "
            f"(o usa una contraseña de aplicación). Detalle: {exc}"
        ) from exc
    except Exception as exc:
        logger.error("Fallo SMTP al enviar correo: %s", exc, exc_info=True)
        raise RuntimeError(f"No se pudo enviar el correo: {exc}") from exc


def enviar_correo_prueba(destinatario: str) -> None:
    """Envía un correo mínimo para validar la configuración SMTP."""
    enviar_correo(
        [destinatario],
        "Prueba de configuración — LVCA AUTODEMA",
        "Este es un correo de prueba del sistema de informes LVCA. "
        "Si lo recibes, la configuración SMTP es correcta.",
        adjuntos=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bitácora de envíos (informes_envios)
# ─────────────────────────────────────────────────────────────────────────────

def registrar_envio(
    campana_id: str, destinatarios: list[str], asunto: str,
    adjuntos: list[str], enviado_por: Optional[str],
    estado: str = "enviado", error: Optional[str] = None,
) -> None:
    """Guarda una fila en la bitácora de envíos (best-effort)."""
    try:
        db = get_db()
        db.table("informes_envios").insert({
            "campana_id": campana_id,
            "destinatarios": ", ".join(destinatarios),
            "asunto": asunto,
            "adjuntos": ", ".join(adjuntos),
            "estado": estado,
            "error": error,
            "enviado_por": enviado_por,
        }).execute()
    except Exception:
        logger.warning("No se pudo registrar el envío en informes_envios.", exc_info=True)


def get_envios(campana_id: str, limite: int = 5) -> list[dict]:
    """Últimos envíos de la campaña (para mostrar el historial)."""
    try:
        db = get_db()
        res = (
            db.table("informes_envios").select("*")
            .eq("campana_id", campana_id)
            .order("enviado_at", desc=True).limit(limite).execute()
        )
        return res.data or []
    except Exception:
        return []
