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
    Datos consolidados de una campaña para el informe. Evalúa cada resultado
    con el motor de cumplimiento (5 estados: cumple, excede, excede_art6,
    no_verificable, no_aplica) aplicando conversión de especies, matricial
    NH3, forma analítica, zona de mezcla, excepciones Art. 6 y línea base Δ3.

    Retorna dict con:
        campana            — fila de la campaña
        puntos             — puntos vinculados
        muestras           — muestras de la campaña
        resultados         — filas con estado, motivo, valor_comparado, etc.
        excedencias        — subconjunto con estado in {excede, excede_art6}
        por_estado         — contadores por estado (para métricas agregadas)
        total_resultados   — int
        total_excedencias  — int
    """
    from services.cumplimiento_service import evaluar, ContextoEvaluacion, EstadoECA

    db = get_admin_client()

    campana = (
        db.table("campanas")
        .select("*")
        .eq("id", campana_id)
        .single()
        .execute()
        .data
    )

    # Puntos vinculados (con flag zona mezcla)
    pts_res = (
        db.table("campana_puntos")
        .select(
            "puntos_muestreo(id, codigo, nombre, tipo, cuenca, eca_id, "
            "dentro_zona_mezcla, ecas(codigo, nombre))"
        )
        .eq("campana_id", campana_id)
        .execute()
    )
    puntos = [
        r["puntos_muestreo"]
        for r in (pts_res.data or [])
        if r.get("puntos_muestreo")
    ]
    puntos.sort(key=lambda x: x.get("codigo", ""))

    punto_by_id = {p["id"]: p for p in puntos if p.get("id")}

    # Muestras (con fecha para Δ3 temperatura)
    m_res = (
        db.table("muestras")
        .select(
            "id, codigo, fecha_muestreo, estado, "
            "punto_muestreo_id, "
            "puntos_muestreo(codigo, nombre, eca_id, dentro_zona_mezcla, "
            "  ecas(codigo))"
        )
        .eq("campana_id", campana_id)
        .order("fecha_muestreo")
        .execute()
    )
    muestras = m_res.data or []
    muestra_ids = [m["id"] for m in muestras]

    # Mediciones in situ por muestra (pH, T para evaluación matricial NH3 y Δ3)
    mediciones_por_muestra: dict[str, dict[str, float]] = {}
    if muestra_ids:
        try:
            ins_res = (
                db.table("mediciones_insitu")
                .select("muestra_id, parametro, valor")
                .in_("muestra_id", muestra_ids)
                .execute()
            )
            for r in (ins_res.data or []):
                key = (r.get("parametro") or "").lower().strip()
                if r.get("valor") is None:
                    continue
                mediciones_por_muestra.setdefault(r["muestra_id"], {})[key] = float(r["valor"])
        except Exception:
            pass

    # Resultados con metadata extendida de parámetro (es_eca, forma_analitica, lmd, lcm)
    resultados_raw = []
    if muestra_ids:
        try:
            r_res = (
                db.table("resultados_laboratorio")
                .select(
                    "muestra_id, parametro_id, valor_numerico, valor_texto, "
                    "cualificador, fecha_analisis, "
                    "parametros(id, codigo, nombre, es_eca, forma_analitica, "
                    "  lmd, lcm, unidades_medida(simbolo))"
                )
                .in_("muestra_id", muestra_ids)
                .order("fecha_analisis")
                .execute()
            )
            resultados_raw = r_res.data or []
        except Exception:
            # Fallback pre-migraciones 010/012
            r_res = (
                db.table("resultados_laboratorio")
                .select(
                    "muestra_id, parametro_id, valor_numerico, valor_texto, "
                    "fecha_analisis, "
                    "parametros(id, codigo, nombre, unidades_medida(simbolo))"
                )
                .in_("muestra_id", muestra_ids)
                .execute()
            )
            resultados_raw = r_res.data or []

    # Límites ECA con expresado_como y forma_analitica
    eca_ids = {p.get("eca_id") for p in puntos if p.get("eca_id")}
    limites: dict[tuple, dict] = {}   # (eca_id, parametro_id) -> {valor_min, valor_max, expresado_como, forma_analitica}
    if eca_ids:
        try:
            lim_res = (
                db.table("eca_valores")
                .select(
                    "eca_id, parametro_id, valor_minimo, valor_maximo, "
                    "expresado_como, forma_analitica"
                )
                .in_("eca_id", list(eca_ids))
                .execute()
            )
        except Exception:
            lim_res = (
                db.table("eca_valores")
                .select("eca_id, parametro_id, valor_minimo, valor_maximo")
                .in_("eca_id", list(eca_ids))
                .execute()
            )
        for l in (lim_res.data or []):
            limites[(l["eca_id"], l["parametro_id"])] = l

    # Excepciones Art. 6 por punto (vigentes)
    excepciones_art6: set[tuple[str, str]] = set()  # (punto_id, parametro_id)
    punto_ids = {m.get("punto_muestreo_id") for m in muestras if m.get("punto_muestreo_id")}
    if punto_ids:
        try:
            from datetime import date as _date
            exc_res = (
                db.table("excepciones_art6")
                .select("punto_muestreo_id, parametro_id, fecha_vencimiento")
                .in_("punto_muestreo_id", list(punto_ids))
                .eq("vigente", True)
                .execute()
            )
            hoy = _date.today().isoformat()
            for r in (exc_res.data or []):
                venc = r.get("fecha_vencimiento")
                if venc is None or venc >= hoy:
                    excepciones_art6.add((r["punto_muestreo_id"], r["parametro_id"]))
        except Exception:
            pass

    # Construir filas con motor de cumplimiento
    filas_resultado = []
    excedencias = []
    por_estado: dict[str, int] = {}

    for r in resultados_raw:
        prm = r.get("parametros") or {}
        m_info = next((mm for mm in muestras if mm["id"] == r["muestra_id"]), {}) or {}
        pt_info = m_info.get("puntos_muestreo") or {}
        eca_id = pt_info.get("eca_id")
        p_id = r.get("parametro_id") or prm.get("id")
        lim = limites.get((eca_id, p_id), {})

        mediciones = mediciones_por_muestra.get(r["muestra_id"], {})

        # ContextoEvaluacion
        ctx = ContextoEvaluacion(
            valor_lab=r.get("valor_numerico"),
            cualificador=r.get("cualificador"),
            parametro_codigo=prm.get("codigo", ""),
            parametro_nombre=prm.get("nombre", ""),
            parametro_es_eca=bool(prm.get("es_eca", True)),
            parametro_unidad_simbolo=(prm.get("unidades_medida") or {}).get("simbolo", ""),
            parametro_lmd=prm.get("lmd"),
            parametro_lcm=prm.get("lcm"),
            parametro_forma_analitica=prm.get("forma_analitica") or "no_aplica",
            eca_codigo=(pt_info.get("ecas") or {}).get("codigo"),
            eca_valor_minimo=lim.get("valor_minimo"),
            eca_valor_maximo=lim.get("valor_maximo"),
            eca_expresado_como=lim.get("expresado_como"),
            eca_forma_analitica=lim.get("forma_analitica") or "no_aplica",
            ph=mediciones.get("ph"),
            temperatura_celsius=(
                mediciones.get("temperatura")
                or mediciones.get("temperatura_agua")
                or mediciones.get("temperatura del agua")
            ),
            fecha_muestreo=m_info.get("fecha_muestreo"),
            punto_id=pt_info.get("id") or m_info.get("punto_muestreo_id"),
            dentro_zona_mezcla=bool(pt_info.get("dentro_zona_mezcla")),
            tiene_excepcion_art6=(m_info.get("punto_muestreo_id"), p_id) in excepciones_art6,
        )
        vered = evaluar(ctx)

        fila = {
            "muestra_codigo":    m_info.get("codigo", ""),
            "punto_codigo":      pt_info.get("codigo", ""),
            "punto_nombre":      pt_info.get("nombre", ""),
            "parametro_codigo":  prm.get("codigo", ""),
            "parametro_nombre":  prm.get("nombre", ""),
            "unidad":            ctx.parametro_unidad_simbolo,
            "valor":             r.get("valor_numerico"),
            "valor_texto":       r.get("valor_texto") or "",
            "cualificador":      r.get("cualificador") or "",
            "lim_min":           ctx.eca_valor_minimo,
            "lim_max":           ctx.eca_valor_maximo,
            "estado_eca":        vered.estado,
            "motivo":            vered.motivo,
            "valor_comparado":   vered.valor_comparado,
            "unidad_comparada":  vered.unidad_comparada or ctx.parametro_unidad_simbolo,
            "eca_rango_max":    vered.eca_valor_maximo,
            "eca_rango_min":    vered.eca_valor_minimo,
            "fecha_muestreo":    (m_info.get("fecha_muestreo") or "")[:10],
            "fecha_analisis":    (r.get("fecha_analisis") or "")[:10],
        }
        filas_resultado.append(fila)
        por_estado[vered.estado] = por_estado.get(vered.estado, 0) + 1
        if vered.estado in (EstadoECA.EXCEDE, EstadoECA.EXCEDE_EXCEPCION_ART6):
            excedencias.append(fila)

    return {
        "campana":           campana,
        "puntos":            puntos,
        "muestras":          muestras,
        "resultados":        filas_resultado,
        "excedencias":       excedencias,
        "por_estado":        por_estado,
        "total_resultados":  len(filas_resultado),
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

        # Mapa de estados → etiqueta legible
        _ETIQ_ESTADO = {
            "cumple":                "Cumple",
            "excede":                "EXCEDE",
            "excede_excepcion_art6": "Excede (Art. 6)",
            "no_verificable":        "No verificable",
            "no_aplica":             "No aplica",
        }

        # Hoja 2: Resultados
        if resumen["resultados"]:
            df_res = pd.DataFrame(resumen["resultados"])
            df_res = df_res.drop(
                columns=["parametro_codigo", "valor_comparado",
                         "unidad_comparada", "eca_rango_min", "eca_rango_max"],
                errors="ignore",
            )
            df_res["estado_eca"] = df_res["estado_eca"].map(_ETIQ_ESTADO).fillna(df_res["estado_eca"])
            df_res = df_res.rename(columns={
                "muestra_codigo":   "Muestra",
                "punto_codigo":     "Punto",
                "punto_nombre":     "Nombre punto",
                "parametro_nombre": "Parámetro",
                "unidad":           "Unidad",
                "valor":            "Valor",
                "valor_texto":      "Valor texto",
                "cualificador":     "Cualificador",
                "lim_min":          "Lím. mín.",
                "lim_max":          "Lím. máx.",
                "estado_eca":       "Estado ECA",
                "motivo":           "Motivo",
                "fecha_muestreo":   "Fecha muestreo",
                "fecha_analisis":   "Fecha análisis",
            })
            df_res.to_excel(writer, sheet_name="Resultados", index=False)

        # Hoja 3: Excedencias (incluye Excede y Art. 6)
        if resumen["excedencias"]:
            df_exc = pd.DataFrame(resumen["excedencias"])
            df_exc = df_exc.drop(
                columns=["parametro_codigo", "valor_comparado",
                         "unidad_comparada", "eca_rango_min", "eca_rango_max"],
                errors="ignore",
            )
            df_exc["estado_eca"] = df_exc["estado_eca"].map(_ETIQ_ESTADO).fillna(df_exc["estado_eca"])
            df_exc = df_exc.rename(columns={
                "muestra_codigo":   "Muestra",
                "punto_codigo":     "Punto",
                "punto_nombre":     "Nombre punto",
                "parametro_nombre": "Parámetro",
                "unidad":           "Unidad",
                "valor":            "Valor",
                "cualificador":     "Cualificador",
                "lim_min":          "Lím. mín.",
                "lim_max":          "Lím. máx.",
                "estado_eca":       "Estado ECA",
                "motivo":           "Motivo",
                "fecha_muestreo":   "Fecha muestreo",
                "fecha_analisis":   "Fecha análisis",
            })
            df_exc.to_excel(writer, sheet_name="Excedencias", index=False)

        # Hoja 4bis: Resumen por estado (conteos)
        por_estado = resumen.get("por_estado", {})
        if por_estado:
            df_est = pd.DataFrame([
                {"Estado": _ETIQ_ESTADO.get(k, k), "Cantidad": v}
                for k, v in por_estado.items()
            ])
            df_est.to_excel(writer, sheet_name="Resumen por estado", index=False)

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

    # Resumen numérico + desglose por estado
    elementos.append(Paragraph("Resumen", subtitulo_style))
    por_estado = resumen.get("por_estado", {})
    resumen_data = [
        ["Puntos monitoreados:",  str(len(resumen["puntos"]))],
        ["Muestras tomadas:",     str(len(resumen["muestras"]))],
        ["Resultados registrados:", str(resumen["total_resultados"])],
    ]
    t2 = Table(resumen_data, colWidths=[5*cm, 12*cm])
    t2.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elementos.append(t2)
    elementos.append(Spacer(1, 0.4*cm))

    # Desglose por estado (5 categorías del motor de cumplimiento)
    estado_labels = {
        "cumple":                ("Cumple",            colors.HexColor("#d4edda")),
        "excede":                ("Excede",            colors.HexColor("#f8d7da")),
        "excede_excepcion_art6": ("Excede (Art. 6)",  colors.HexColor("#fff3cd")),
        "no_verificable":        ("No verificable",   colors.HexColor("#e2e3e5")),
        "no_aplica":             ("No aplica",         colors.HexColor("#ede7f6")),
    }
    elementos.append(Paragraph("Desglose por estado ECA", subtitulo_style))
    estado_rows = [["Estado", "Cantidad"]]
    estado_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]
    for idx, (estado_key, (label, color)) in enumerate(estado_labels.items(), start=1):
        cantidad = por_estado.get(estado_key, 0)
        estado_rows.append([label, str(cantidad)])
        estado_styles.append(("BACKGROUND", (0, idx), (0, idx), color))
    t_estado = Table(estado_rows, colWidths=[6*cm, 3*cm], repeatRows=1)
    t_estado.setStyle(TableStyle(estado_styles))
    elementos.append(t_estado)
    elementos.append(Spacer(1, 0.5*cm))

    # Tabla de excedencias (incluye Excede y Art. 6)
    if resumen["excedencias"]:
        elementos.append(Paragraph("Excedencias ECA Detectadas", subtitulo_style))
        header = ["Punto", "Parámetro", "Valor", "Unidad", "ECA máx.", "Estado", "Fecha"]
        rows = [header]
        for e in resumen["excedencias"][:80]:
            estado_key = e.get("estado_eca", "")
            estado_label = estado_labels.get(estado_key, (estado_key, colors.white))[0]
            valor_view = e.get("valor_comparado")
            if valor_view is None:
                valor_view = e.get("valor")
            eca_max = e.get("eca_rango_max") if e.get("eca_rango_max") is not None else e.get("lim_max")
            rows.append([
                e.get("punto_codigo", ""),
                e.get("parametro_nombre", "")[:28],
                f"{valor_view:.4f}" if isinstance(valor_view, (int, float)) else "—",
                (e.get("unidad_comparada") or e.get("unidad", ""))[:14],
                f"{eca_max:.4f}" if isinstance(eca_max, (int, float)) else "—",
                estado_label,
                e.get("fecha_muestreo") or e.get("fecha_analisis", ""),
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

    # ── Anexo: fotografías de campo ──────────────────────────────────────
    try:
        from reportlab.platypus import Image as PdfImage, PageBreak
        from services.storage_service import get_fotos_campo, download_imagen

        muestras_con_fotos: list[tuple[dict, list[dict]]] = []
        for m in resumen.get("muestras", [])[:30]:  # tope: 30 muestras
            fotos = get_fotos_campo(m["id"])
            if fotos:
                muestras_con_fotos.append((m, fotos))

        if muestras_con_fotos:
            elementos.append(PageBreak())
            elementos.append(Paragraph("Anexo — Fotografías de Campo", subtitulo_style))
            elementos.append(Paragraph(
                f"Se incluyen fotografías de {len(muestras_con_fotos)} muestra(s).",
                styles["Normal"],
            ))
            elementos.append(Spacer(1, 0.4 * cm))

            for muestra, fotos in muestras_con_fotos:
                elementos.append(Paragraph(
                    f"<b>{muestra.get('codigo', '')}</b> — "
                    f"{(muestra.get('puntos_muestreo') or {}).get('codigo', '')} "
                    f"({muestra.get('fecha_muestreo', '')[:10]})",
                    styles["Normal"],
                ))
                # Máx 4 fotos por muestra para no inflar el PDF
                for foto in fotos[:4]:
                    img_bytes = download_imagen(foto.get("url", ""))
                    if not img_bytes:
                        continue
                    try:
                        img = PdfImage(BytesIO(img_bytes), width=8 * cm, height=6 * cm)
                        elementos.append(img)
                        elementos.append(Paragraph(
                            f"<i>{foto.get('name', '')}</i>",
                            ParagraphStyle("PieFoto", parent=styles["Normal"],
                                           fontSize=7, textColor=colors.grey),
                        ))
                        elementos.append(Spacer(1, 0.3 * cm))
                    except Exception:
                        # Imagen corrupta o formato no soportado — saltar
                        continue
                elementos.append(Spacer(1, 0.4 * cm))
    except Exception:
        # Si Storage no está disponible, omitir el anexo silenciosamente
        pass

    # Pie
    elementos.append(Spacer(1, 1*cm))
    elementos.append(Paragraph(
        f"Generado: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC — "
        "Sistema LVCA / AUTODEMA",
        ParagraphStyle("Pie", parent=styles["Normal"], fontSize=7, textColor=colors.grey),
    ))

    doc.build(elementos)
    return output.getvalue()
