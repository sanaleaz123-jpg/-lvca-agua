"""
services/pdf_service.py
Conversión de documentos .docx a PDF mediante LibreOffice en modo headless.

Los Reportes de Ensayo (fitoplancton, microcistina) se construyen como .docx
con su formato oficial (membrete, logos, firmas). Para enviarlos SIEMPRE en PDF
sin perder ese formato, se convierten con LibreOffice.

Despliegue: en Streamlit Cloud (Linux) LibreOffice se instala vía `packages.txt`
(`libreoffice-writer`). En local se necesita LibreOffice instalado para probar
la exportación; si no está, `docx_a_pdf` lanza un error claro.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile


def _buscar_soffice() -> str | None:
    """Ruta al ejecutable de LibreOffice, o None si no está disponible."""
    for nombre in ("soffice", "libreoffice"):
        ruta = shutil.which(nombre)
        if ruta:
            return ruta
    for ruta in (
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/opt/libreoffice/program/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
    ):
        if os.path.exists(ruta):
            return ruta
    return None


def soffice_disponible() -> bool:
    return _buscar_soffice() is not None


def docx_a_pdf(docx_bytes: bytes, timeout: int = 120) -> bytes:
    """
    Convierte un .docx (bytes) a PDF (bytes) con LibreOffice headless,
    conservando el formato oficial del documento.

    Lanza RuntimeError si LibreOffice no está disponible o la conversión falla.
    Se usa un perfil de usuario aislado por conversión para evitar choques
    entre instancias concurrentes.
    """
    soffice = _buscar_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice no está disponible en el servidor: se requiere para "
            "exportar los informes a PDF. Revisa que 'libreoffice-writer' esté "
            "en packages.txt (o instálalo localmente para pruebas)."
        )

    with tempfile.TemporaryDirectory() as tmp:
        in_path = os.path.join(tmp, "informe.docx")
        with open(in_path, "wb") as f:
            f.write(docx_bytes)

        perfil = os.path.join(tmp, "profile")
        cmd = [
            soffice, "--headless", "--norestore", "--nolockcheck",
            f"-env:UserInstallation=file://{perfil}",
            "--convert-to", "pdf", "--outdir", tmp, in_path,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "La conversión a PDF con LibreOffice excedió el tiempo límite."
            ) from exc

        out_path = os.path.join(tmp, "informe.pdf")
        if not os.path.exists(out_path):
            detalle = (proc.stderr or proc.stdout or b"").decode("utf-8", "ignore")[:400]
            raise RuntimeError(
                f"LibreOffice no generó el PDF (código {proc.returncode}). "
                f"Detalle: {detalle or 'sin salida'}"
            )
        with open(out_path, "rb") as f:
            return f.read()
