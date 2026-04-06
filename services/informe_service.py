"""
services/informe_service.py
Lógica de negocio para generación de informes y exportación de datos.

Funciones públicas:
    get_resumen_campana(campana_id)             → datos para informe de campaña
    get_resumen_punto(punto_id, fecha_desde, fecha_hasta) → historial de un punto
    get_datos_exportacion(campana_id)            → DataFrame listo para Excel
    generar_pdf_campana(campana_id)              → bytes del PDF
"""

from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

import pandas as pd

from database.client import get_admin_client


# ─────────────────────────────────────────────────────────────────────────────
# Resumen de campaña (para informe)
# ─────────────────────────────────────────────────────────────────────────────

def get_resumen_campana(campana_id: str) -> dict:
    """
    Datos consolidados de una campaña para el informe:
        campana, puntos, muestras, resultados (con ECA), excedencias
    """
    db = get_admin_client()

    # Campaña
    campana = (
        db.table("campanas")
        .select("*")
        .eq("id", campana_id)
        .single()
        .execute()
        .data
    )

    # Puntos vinculados
    pts_res = (
        db.table("campana_puntos")
        .select("puntos_muestreo(id, codigo, nombre, tipo, cuenca, eca_id, ecas(codigo, nombre))")
        .eq("campana_id", campana_id)
        .execute()
    )
    puntos = [
        r["puntos_muestreo"]
        for r in (pts_res.data or [])
        if r.get("puntos_muestreo")
    ]
    puntos.sort(key=lambda x: x.get("codigo", ""))

    # Muestras
    m_res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, estado, "
            "puntos_muestreo(codigo, nombre)"
        )
        .eq("campana_id", campana_id)
        .order("fecha_muestreo")
        .execute()
    )
    muestras = m_res.data or []
    muestra_ids = [m["id"] for m in muestras]

    # Resultados con parámetro y unidad
    resultados = []
    if muestra_ids:
        r_res = (
            db.table("resultados_laboratorio")
            .select(
                "muestra_id, valor_numerico, valor_texto, fecha_analisis, "
                "parametros(codigo, nombre, unidades_medida(simbolo)), "
                "muestras(codigo, punto_muestreo_id, puntos_muestreo(codigo, nombre, eca_id))"
            )
            .in_("muestra_id", muestra_ids)
            .order("fecha_analisis")
            .execute()
        )
        resultados = r_res.data or []

    # Límites ECA para evaluar excedencias
    eca_ids = {p.get("eca_id") for p in puntos if p.get("eca_id")}
    param_ids = {
        (r.get("parametros") or {}).get("codigo", "")
        for r in resultados
    }

    limites: dict[tuple, dict] = {}
    if eca_ids:
        lim_res = (
            db.table("eca_valores")
            .select("eca_id, parametro_id, valor_minimo, valor_maximo, parametros(codigo)")
            .in_("eca_id", list(eca_ids))
            .execute()
        )
        for l in (lim_res.data or []):
            p_cod = (l.get("parametros") or {}).get("codigo", "")
            limites[(l["eca_id"], p_cod)] = l

    # Construir filas de resultados con estado ECA
    filas_resultado = []
    excedencias = []
    for r in resultados:
        prm = r.get("parametros") or {}
        m = r.get("muestras") or {}
        pt = m.get("puntos_muestreo") or {}
        eca_id = pt.get("eca_id")
        p_cod = prm.get("codigo", "")
        lim = limites.get((eca_id, p_cod), {})

        valor = r.get("valor_numerico")
        estado = "sin_dato"
        if valor is not None:
            if lim.get("valor_maximo") is None and lim.get("valor_minimo") is None:
                estado = "sin_limite"
            elif (lim.get("valor_maximo") is not None and valor > lim["valor_maximo"]) or \
                 (lim.get("valor_minimo") is not None and valor < lim["valor_minimo"]):
                estado = "excede"
            else:
                estado = "cumple"

        fila = {
            "muestra_codigo":    m.get("codigo", ""),
            "punto_codigo":      pt.get("codigo", ""),
            "punto_nombre":      pt.get("nombre", ""),
            "parametro_codigo":  p_cod,
            "parametro_nombre":  prm.get("nombre", ""),
            "unidad":            (prm.get("unidades_medida") or {}).get("simbolo", ""),
            "valor":             valor,
            "valor_texto":       r.get("valor_texto") or "",
            "lim_min":           lim.get("valor_minimo"),
            "lim_max":           lim.get("valor_maximo"),
            "estado_eca":        estado,
            "fecha_analisis":    (r.get("fecha_analisis") or "")[:10],
        }
        filas_resultado.append(fila)
        if estado == "excede":
            excedencias.append(fila)

    return {
        "campana":      campana,
        "puntos":       puntos,
        "muestras":     muestras,
        "resultados":   filas_resultado,
        "excedencias":  excedencias,
        "total_resultados": len(filas_resultado),
        "total_excedencias": len(excedencias),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Historial de un punto
# ─────────────────────────────────────────────────────────────────────────────

def get_resumen_punto(
    punto_id: str,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
) -> dict:
    """Resultados de un punto en un rango de fechas."""
    db = get_admin_client()

    punto = (
        db.table("puntos_muestreo")
        .select("id, codigo, nombre, tipo, cuenca, ecas(codigo, nombre)")
        .eq("id", punto_id)
        .single()
        .execute()
        .data
    )

    query = (
        db.table("muestras")
        .select("id")
        .eq("punto_muestreo_id", punto_id)
    )
    if fecha_desde:
        query = query.gte("fecha_muestreo", fecha_desde)
    if fecha_hasta:
        query = query.lte("fecha_muestreo", fecha_hasta)

    m_res = query.execute()
    muestra_ids = [m["id"] for m in (m_res.data or [])]

    resultados = []
    if muestra_ids:
        r_res = (
            db.table("resultados_laboratorio")
            .select(
                "valor_numerico, fecha_analisis, "
                "parametros(codigo, nombre, unidades_medida(simbolo)), "
                "muestras(codigo)"
            )
            .in_("muestra_id", muestra_ids)
            .not_.is_("valor_numerico", "null")
            .order("fecha_analisis")
            .execute()
        )
        for r in (r_res.data or []):
            prm = r.get("parametros") or {}
            resultados.append({
                "fecha":      (r.get("fecha_analisis") or "")[:10],
                "muestra":    (r.get("muestras") or {}).get("codigo", ""),
                "parametro":  prm.get("nombre", ""),
                "codigo":     prm.get("codigo", ""),
                "valor":      r["valor_numerico"],
                "unidad":     (prm.get("unidades_medida") or {}).get("simbolo", ""),
            })

    return {"punto": punto, "resultados": resultados}


# ─────────────────────────────────────────────────────────────────────────────
# Exportación a Excel
# ─────────────────────────────────────────────────────────────────────────────

def generar_excel_campana(campana_id: str) -> bytes:
    """Genera un archivo Excel con los datos de una campaña."""
    resumen = get_resumen_campana(campana_id)
    campana = resumen["campana"]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Hoja 1: Info de campaña
        info = pd.DataFrame([{
            "Código":       campana.get("codigo", ""),
            "Nombre":       campana.get("nombre", ""),
            "Estado":       campana.get("estado", ""),
            "Fecha inicio": campana.get("fecha_inicio", ""),
            "Fecha fin":    campana.get("fecha_fin", ""),
            "Frecuencia":   campana.get("frecuencia", ""),
            "Resp. campo":  campana.get("responsable_campo", ""),
            "Resp. lab":    campana.get("responsable_laboratorio", ""),
        }])
        info.to_excel(writer, sheet_name="Campaña", index=False)

        # Hoja 2: Resultados
        if resumen["resultados"]:
            df_res = pd.DataFrame(resumen["resultados"])
            df_res = df_res.drop(columns=["parametro_codigo"], errors="ignore")
            df_res["estado_eca"] = df_res["estado_eca"].map({
                "cumple": "Cumple", "excede": "EXCEDE",
                "sin_limite": "SIN ECA", "sin_dato": "Sin dato",
            }).fillna(df_res["estado_eca"])
            df_res = df_res.rename(columns={
                "muestra_codigo":   "Muestra",
                "punto_codigo":     "Punto",
                "punto_nombre":     "Nombre punto",
                "parametro_nombre": "Parámetro",
                "unidad":           "Unidad",
                "valor":            "Valor",
                "valor_texto":      "Valor texto",
                "lim_min":          "Lím. mín.",
                "lim_max":          "Lím. máx.",
                "estado_eca":       "Estado ECA",
                "fecha_analisis":   "Fecha análisis",
            })
            df_res.to_excel(writer, sheet_name="Resultados", index=False)

        # Hoja 3: Excedencias
        if resumen["excedencias"]:
            df_exc = pd.DataFrame(resumen["excedencias"])
            df_exc = df_exc.drop(columns=["parametro_codigo"], errors="ignore")
            df_exc = df_exc.rename(columns={
                "muestra_codigo":   "Muestra",
                "punto_codigo":     "Punto",
                "punto_nombre":     "Nombre punto",
                "parametro_nombre": "Parámetro",
                "unidad":           "Unidad",
                "valor":            "Valor",
                "lim_min":          "Lím. mín.",
                "lim_max":          "Lím. máx.",
                "fecha_analisis":   "Fecha análisis",
            })
            df_exc.to_excel(writer, sheet_name="Excedencias", index=False)

        # Hoja 4: Puntos
        if resumen["puntos"]:
            pts_data = []
            for p in resumen["puntos"]:
                pts_data.append({
                    "Código":  p.get("codigo", ""),
                    "Nombre":  p.get("nombre", ""),
                    "Tipo":    p.get("tipo", ""),
                    "Cuenca":  p.get("cuenca", ""),
                    "ECA":     (p.get("ecas") or {}).get("codigo", ""),
                })
            pd.DataFrame(pts_data).to_excel(writer, sheet_name="Puntos", index=False)

    return output.getvalue()


def generar_excel_punto(punto_id: str, fecha_desde: str, fecha_hasta: str) -> bytes:
    """Genera un Excel con el historial de resultados de un punto."""
    resumen = get_resumen_punto(punto_id, fecha_desde, fecha_hasta)
    punto = resumen["punto"]

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        info = pd.DataFrame([{
            "Código": punto.get("codigo", ""),
            "Nombre": punto.get("nombre", ""),
            "Tipo":   punto.get("tipo", ""),
            "Cuenca": punto.get("cuenca", ""),
            "ECA":    (punto.get("ecas") or {}).get("codigo", ""),
        }])
        info.to_excel(writer, sheet_name="Punto", index=False)

        if resumen["resultados"]:
            df = pd.DataFrame(resumen["resultados"])
            df = df.drop(columns=["codigo"], errors="ignore")
            df = df.rename(columns={
                "fecha":     "Fecha",
                "muestra":   "Muestra",
                "parametro": "Parámetro",
                "valor":     "Valor",
                "unidad":    "Unidad",
            })
            df.to_excel(writer, sheet_name="Resultados", index=False)

    return output.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Generación de PDF
# ─────────────────────────────────────────────────────────────────────────────

def generar_pdf_campana(campana_id: str) -> bytes:
    """Genera un informe PDF resumido de una campaña."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    resumen = get_resumen_campana(campana_id)
    campana = resumen["campana"]

    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    styles = getSampleStyleSheet()
    titulo_style = ParagraphStyle(
        "TituloInforme", parent=styles["Title"], fontSize=16, spaceAfter=12,
    )
    subtitulo_style = ParagraphStyle(
        "Subtitulo", parent=styles["Heading2"], fontSize=12, spaceAfter=8,
    )

    elementos = []

    # Título
    elementos.append(Paragraph("Informe de Campaña de Monitoreo", titulo_style))
    elementos.append(Paragraph("AUTODEMA — Laboratorio de Calidad de Agua", styles["Normal"]))
    elementos.append(Spacer(1, 0.5*cm))

    # Info campaña
    elementos.append(Paragraph("Datos de la Campaña", subtitulo_style))
    info_data = [
        ["Código:", campana.get("codigo", "")],
        ["Nombre:", campana.get("nombre", "")],
        ["Estado:", campana.get("estado", "").replace("_", " ").capitalize()],
        ["Periodo:", f"{campana.get('fecha_inicio', '')} a {campana.get('fecha_fin', '')}"],
        ["Frecuencia:", (campana.get("frecuencia") or "").capitalize()],
        ["Resp. campo:", campana.get("responsable_campo") or "—"],
        ["Resp. laboratorio:", campana.get("responsable_laboratorio") or "—"],
    ]
    t = Table(info_data, colWidths=[5*cm, 12*cm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t)
    elementos.append(Spacer(1, 0.5*cm))

    # Resumen numérico
    elementos.append(Paragraph("Resumen", subtitulo_style))
    resumen_data = [
        ["Puntos monitoreados:", str(len(resumen["puntos"]))],
        ["Muestras tomadas:", str(len(resumen["muestras"]))],
        ["Resultados registrados:", str(resumen["total_resultados"])],
        ["Excedencias ECA:", str(resumen["total_excedencias"])],
    ]
    t2 = Table(resumen_data, colWidths=[5*cm, 12*cm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t2)
    elementos.append(Spacer(1, 0.5*cm))

    # Tabla de excedencias
    if resumen["excedencias"]:
        elementos.append(Paragraph("Excedencias ECA Detectadas", subtitulo_style))
        header = ["Punto", "Parámetro", "Valor", "Lím. máx.", "Unidad", "Fecha"]
        rows = [header]
        for e in resumen["excedencias"][:50]:  # limitar a 50
            rows.append([
                e.get("punto_codigo", ""),
                e.get("parametro_nombre", "")[:30],
                f"{e['valor']:.4f}" if e.get("valor") is not None else "—",
                f"{e['lim_max']:.4f}" if e.get("lim_max") is not None else "—",
                e.get("unidad", ""),
                e.get("fecha_analisis", ""),
            ])
        t3 = Table(rows, repeatRows=1)
        t3.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        elementos.append(t3)
    else:
        elementos.append(Paragraph(
            "No se detectaron excedencias ECA en esta campaña.",
            styles["Normal"],
        ))

    # Pie
    elementos.append(Spacer(1, 1*cm))
    elementos.append(Paragraph(
        f"Generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC — "
        "Sistema LVCA / AUTODEMA",
        ParagraphStyle("Pie", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
    ))

    doc.build(elementos)
    return output.getvalue()
