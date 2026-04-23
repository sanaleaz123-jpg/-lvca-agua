"""
services/cumplimiento_service.py
Motor de evaluación de cumplimiento ECA — produce un veredicto en 4 estados
para un resultado de laboratorio contra el estándar vigente del DS 004-2017-MINAM.

Reemplaza la lógica binaria "cumple/no cumple" por una clasificación más fiel
al marco normativo:

    cumple                  — el valor está dentro del umbral del ECA.
    excede                  — el valor excede el umbral (incumplimiento presunto).
    excede_excepcion_art6   — excede pero hay excepción ANA Art. 6 aprobada
                              (condición natural no antrópica). Requiere el
                              cambio #7 — por ahora solo queda el hook.
    no_verificable          — no se puede emitir juicio. Razones posibles:
                              * parámetro no ECA (es_eca=False)
                              * ECA no contempla este parámetro
                              * límite del método (LC) superior al ECA
                              * faltan mediciones in situ (pH/T para NH3 Cat 4)
                              * unidad del lab no convertible a la especie ECA
                              * punto dentro de zona de mezcla (Art. 7 — #7)

El servicio es PURO: recibe datos ya cargados y retorna el veredicto. Eso lo
hace fácil de testear sin BD. Un wrapper futuro puede tomar un resultado_id,
armar el contexto desde la BD y llamar aquí.
"""

from __future__ import annotations

from typing import Optional
from dataclasses import dataclass

from services.conversion_especies import convertir_a_especie_eca


# ─────────────────────────────────────────────────────────────────────────────
# Estados (enum ligero con strings estables para persistir si algún día se
# cachea el veredicto en resultados_laboratorio).
# ─────────────────────────────────────────────────────────────────────────────
class EstadoECA:
    CUMPLE                = "cumple"
    EXCEDE                = "excede"
    EXCEDE_EXCEPCION_ART6 = "excede_excepcion_art6"
    NO_VERIFICABLE        = "no_verificable"
    NO_APLICA             = "no_aplica"  # parámetro fuera del alcance del ECA


ESTADOS_TERMINALES = {
    EstadoECA.CUMPLE,
    EstadoECA.EXCEDE,
    EstadoECA.EXCEDE_EXCEPCION_ART6,
}


# ─────────────────────────────────────────────────────────────────────────────
# Contexto de entrada — todo lo necesario para evaluar sin tocar BD
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ContextoEvaluacion:
    # Resultado de laboratorio
    valor_lab:       Optional[float] = None
    cualificador:    Optional[str]   = None   # <LMD | <LCM | Ausencia | Presencia | ND | Trazas

    # Parámetro (desde parametros + unidades_medida)
    parametro_codigo:       str  = ""
    parametro_nombre:       str  = ""
    parametro_es_eca:       bool = True
    parametro_unidad_simbolo: str = ""
    parametro_lmd:          Optional[float] = None
    parametro_lcm:          Optional[float] = None
    parametro_forma_analitica: str = "no_aplica"   # total | disuelta | no_aplica

    # Valor ECA aplicable (desde eca_valores)
    eca_codigo:             Optional[str]   = None
    eca_valor_minimo:       Optional[float] = None
    eca_valor_maximo:       Optional[float] = None
    eca_expresado_como:     Optional[str]   = None
    eca_forma_analitica:    str  = "no_aplica"   # total | disuelta | no_aplica

    # Mediciones in situ (desde mediciones_insitu)
    ph:               Optional[float] = None
    temperatura_celsius: Optional[float] = None

    # Flags de excepción (cambio #7 — pendiente; por ahora siempre False)
    dentro_zona_mezcla:       bool = False
    tiene_excepcion_art6:     bool = False


@dataclass
class VeredictoECA:
    estado:              str
    motivo:              str
    valor_lab_original:  Optional[float]
    valor_comparado:     Optional[float]
    unidad_comparada:    Optional[str]
    eca_valor_minimo:    Optional[float]
    eca_valor_maximo:    Optional[float]
    detalles:            dict


# ─────────────────────────────────────────────────────────────────────────────
# Motor
# ─────────────────────────────────────────────────────────────────────────────

def evaluar(ctx: ContextoEvaluacion) -> VeredictoECA:
    """
    Evalúa el cumplimiento ECA de un resultado de laboratorio.
    """
    detalles: dict = {
        "parametro_codigo": ctx.parametro_codigo,
        "eca_codigo":       ctx.eca_codigo,
    }

    # ── 1. Parámetro no regulado (es_eca=False) ──────────────────────────────
    if not ctx.parametro_es_eca:
        return VeredictoECA(
            estado=EstadoECA.NO_APLICA,
            motivo=(
                f"Parámetro {ctx.parametro_codigo} no está regulado por el "
                "DS 004-2017-MINAM (es_eca=False). Se captura con fines de "
                "caracterización pero no se emite juicio de cumplimiento."
            ),
            valor_lab_original=ctx.valor_lab,
            valor_comparado=None,
            unidad_comparada=None,
            eca_valor_minimo=None,
            eca_valor_maximo=None,
            detalles=detalles,
        )

    # ── 2. Sin eca aplicable para este (param, eca).
    #       Excepción: los ECAs matriciales (NH3_libre via Tabla N°1) no usan
    #       valor_minimo/maximo de eca_valores — el umbral lo aporta la
    #       conversión. Por eso sólo descartamos cuando tampoco hay especie
    #       matricial conocida.
    especie_matricial = ctx.eca_expresado_como in {"NH3_libre"}
    if (
        ctx.eca_valor_minimo is None
        and ctx.eca_valor_maximo is None
        and not especie_matricial
    ):
        return VeredictoECA(
            estado=EstadoECA.NO_APLICA,
            motivo=(
                f"El ECA {ctx.eca_codigo or 'asignado'} no regula el parámetro "
                f"{ctx.parametro_codigo}. Se captura sin comparación."
            ),
            valor_lab_original=ctx.valor_lab,
            valor_comparado=None,
            unidad_comparada=None,
            eca_valor_minimo=None,
            eca_valor_maximo=None,
            detalles=detalles,
        )

    # ── 2b. Coherencia de forma analítica (total vs disuelta).
    #        Si el laboratorio mide disuelta pero el DS exige total, no se puede
    #        comparar: faltaría la fracción particulada. A la inversa también
    #        es ambiguo: medir total donde el DS pide disuelta puede sobrestimar
    #        el incumplimiento. "no_aplica" en cualquiera de los dos lados se
    #        interpreta como "no requiere coherencia".
    pfa = (ctx.parametro_forma_analitica or "no_aplica").lower()
    efa = (ctx.eca_forma_analitica or "no_aplica").lower()
    if pfa != "no_aplica" and efa != "no_aplica" and pfa != efa:
        return VeredictoECA(
            estado=EstadoECA.NO_VERIFICABLE,
            motivo=(
                f"Discrepancia de forma analítica: el método mide '{pfa}' pero el ECA "
                f"exige '{efa}'. No es posible comparar — revisar protocolo de "
                f"preservación y análisis (filtración previa 0,45 µm si el DS exige disuelta, "
                f"o digestión ácida si exige total)."
            ),
            valor_lab_original=ctx.valor_lab,
            valor_comparado=None,
            unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo,
            eca_valor_maximo=ctx.eca_valor_maximo,
            detalles={**detalles, "parametro_forma": pfa, "eca_forma": efa},
        )

    # ── 3. Punto dentro de zona de mezcla (Art. 7) ──────────────────────────
    if ctx.dentro_zona_mezcla:
        return VeredictoECA(
            estado=EstadoECA.NO_VERIFICABLE,
            motivo=(
                "El punto de muestreo está DENTRO de la zona de mezcla (Art. 7 "
                "del DS 004-2017-MINAM). El cumplimiento ECA solo se verifica "
                "FUERA de la zona de mezcla definida por ANA."
            ),
            valor_lab_original=ctx.valor_lab,
            valor_comparado=None,
            unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo,
            eca_valor_maximo=ctx.eca_valor_maximo,
            detalles=detalles,
        )

    # ── 4. Manejo de cualificadores (<LMD, <LCM, Ausencia, etc.) ────────────
    vered = _evaluar_cualificador(ctx, detalles)
    if vered is not None:
        return vered

    # ── 5. Si no hay valor numérico y no hay cualificador → no verificable ──
    if ctx.valor_lab is None:
        return VeredictoECA(
            estado=EstadoECA.NO_VERIFICABLE,
            motivo="Resultado de laboratorio no disponible (ni valor numérico ni cualificador).",
            valor_lab_original=None,
            valor_comparado=None,
            unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo,
            eca_valor_maximo=ctx.eca_valor_maximo,
            detalles=detalles,
        )

    # ── 6. Aplicar conversión a la especie oficial del ECA ──────────────────
    conv = convertir_a_especie_eca(
        valor_lab=ctx.valor_lab,
        unidad_simbolo=ctx.parametro_unidad_simbolo,
        expresado_como_eca=ctx.eca_expresado_como,
        ph=ctx.ph,
        temperatura_celsius=ctx.temperatura_celsius,
        eca_codigo=ctx.eca_codigo,
    )
    detalles["conversion"] = {
        "factor":  conv.get("factor"),
        "motivo":  conv.get("motivo"),
    }
    if conv.get("eca_matricial"):
        detalles["eca_matricial"] = conv["eca_matricial"]

    if not conv["puede_comparar"]:
        return VeredictoECA(
            estado=EstadoECA.NO_VERIFICABLE,
            motivo=conv["motivo"],
            valor_lab_original=ctx.valor_lab,
            valor_comparado=None,
            unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo,
            eca_valor_maximo=ctx.eca_valor_maximo,
            detalles=detalles,
        )

    valor_comparado = conv["valor_convertido"]

    # ── 7. Si el ECA vino de Tabla matricial, el "valor ECA" efectivo ya no
    #      es ctx.eca_valor_maximo sino el de la celda de Tabla N°1.
    eca_max = ctx.eca_valor_maximo
    eca_min = ctx.eca_valor_minimo
    if conv.get("eca_matricial") and conv["eca_matricial"].get("eca_valor_mg_nh3_l") is not None:
        eca_max = conv["eca_matricial"]["eca_valor_mg_nh3_l"]

    # ── 8. Comparación ──────────────────────────────────────────────────────
    excede = False
    violacion = ""
    if eca_max is not None and valor_comparado > eca_max:
        excede = True
        violacion = f"{valor_comparado:g} > máximo ECA {eca_max:g}"
    if eca_min is not None and valor_comparado < eca_min:
        excede = True
        violacion = f"{valor_comparado:g} < mínimo ECA {eca_min:g}"

    if not excede:
        rango_desc = _describir_rango(eca_min, eca_max)
        return VeredictoECA(
            estado=EstadoECA.CUMPLE,
            motivo=f"{valor_comparado:g} {rango_desc} — cumple ECA.",
            valor_lab_original=ctx.valor_lab,
            valor_comparado=valor_comparado,
            unidad_comparada=_unidad_de_especie(ctx.eca_expresado_como) or ctx.parametro_unidad_simbolo,
            eca_valor_minimo=eca_min,
            eca_valor_maximo=eca_max,
            detalles=detalles,
        )

    # Excede. Diferenciar si tiene excepción Art. 6.
    if ctx.tiene_excepcion_art6:
        return VeredictoECA(
            estado=EstadoECA.EXCEDE_EXCEPCION_ART6,
            motivo=(
                f"Excede ({violacion}) pero el punto tiene excepción Art. 6 aprobada "
                "por ANA (condición natural no antrópica, DS 004-2017-MINAM Art. 6)."
            ),
            valor_lab_original=ctx.valor_lab,
            valor_comparado=valor_comparado,
            unidad_comparada=_unidad_de_especie(ctx.eca_expresado_como) or ctx.parametro_unidad_simbolo,
            eca_valor_minimo=eca_min,
            eca_valor_maximo=eca_max,
            detalles=detalles,
        )

    return VeredictoECA(
        estado=EstadoECA.EXCEDE,
        motivo=f"Excede ECA: {violacion}.",
        valor_lab_original=ctx.valor_lab,
        valor_comparado=valor_comparado,
        unidad_comparada=_unidad_de_especie(ctx.eca_expresado_como) or ctx.parametro_unidad_simbolo,
        eca_valor_minimo=eca_min,
        eca_valor_maximo=eca_max,
        detalles=detalles,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers privados
# ─────────────────────────────────────────────────────────────────────────────

def _evaluar_cualificador(ctx: ContextoEvaluacion, detalles: dict) -> Optional[VeredictoECA]:
    """
    Interpreta cualificadores de resultado (<LMD, <LCM, Ausencia, Presencia, ND, Trazas).
    Retorna un veredicto si el cualificador determina el resultado; None si hay que
    seguir con la comparación numérica.
    """
    q = (ctx.cualificador or "").strip()
    if not q:
        return None

    # Cualitativos binarios
    if q == "Ausencia":
        # Interpretación: microbiológicos suelen exigir "ausencia en X mL".
        # Sin contexto específico se considera cumplimiento.
        return VeredictoECA(
            estado=EstadoECA.CUMPLE,
            motivo="Resultado cualitativo 'Ausencia' — cumple.",
            valor_lab_original=None, valor_comparado=None, unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo, eca_valor_maximo=ctx.eca_valor_maximo,
            detalles=detalles,
        )
    if q == "Presencia":
        return VeredictoECA(
            estado=EstadoECA.EXCEDE,
            motivo="Resultado cualitativo 'Presencia' donde el ECA exige ausencia — excede.",
            valor_lab_original=None, valor_comparado=None, unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo, eca_valor_maximo=ctx.eca_valor_maximo,
            detalles=detalles,
        )

    # <LMD / ND: valor por debajo del límite de detección del método.
    if q in ("<LMD", "ND"):
        lmd = ctx.parametro_lmd
        eca_max = ctx.eca_valor_maximo
        if lmd is not None and eca_max is not None and lmd > eca_max:
            return VeredictoECA(
                estado=EstadoECA.NO_VERIFICABLE,
                motivo=(
                    f"Resultado '{q}' con LMD ({lmd:g}) > ECA máximo ({eca_max:g}). "
                    "El método analítico no tiene sensibilidad suficiente — "
                    "no se puede afirmar cumplimiento. Exige método más sensible."
                ),
                valor_lab_original=None, valor_comparado=None, unidad_comparada=None,
                eca_valor_minimo=ctx.eca_valor_minimo, eca_valor_maximo=eca_max,
                detalles={**detalles, "lmd": lmd},
            )
        return VeredictoECA(
            estado=EstadoECA.CUMPLE,
            motivo=(
                f"Resultado '{q}' (por debajo del límite de detección {lmd or '?'}). "
                "Cumple — valor real es menor que el ECA."
            ),
            valor_lab_original=None, valor_comparado=None, unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo, eca_valor_maximo=ctx.eca_valor_maximo,
            detalles={**detalles, "lmd": lmd},
        )

    # <LCM: valor detectado pero no cuantificable.
    if q == "<LCM":
        lcm = ctx.parametro_lcm
        eca_max = ctx.eca_valor_maximo
        if lcm is not None and eca_max is not None and lcm > eca_max:
            return VeredictoECA(
                estado=EstadoECA.NO_VERIFICABLE,
                motivo=(
                    f"Resultado '<LCM' con LCM ({lcm:g}) > ECA máximo ({eca_max:g}). "
                    "El método no puede cuantificar por debajo del umbral ECA."
                ),
                valor_lab_original=None, valor_comparado=None, unidad_comparada=None,
                eca_valor_minimo=ctx.eca_valor_minimo, eca_valor_maximo=eca_max,
                detalles={**detalles, "lcm": lcm},
            )
        return VeredictoECA(
            estado=EstadoECA.CUMPLE,
            motivo=(
                f"Resultado '<LCM' (detectado pero no cuantificable; LCM={lcm or '?'}). "
                "Cumple — valor real está bajo el ECA."
            ),
            valor_lab_original=None, valor_comparado=None, unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo, eca_valor_maximo=ctx.eca_valor_maximo,
            detalles={**detalles, "lcm": lcm},
        )

    if q == "Trazas":
        return VeredictoECA(
            estado=EstadoECA.NO_VERIFICABLE,
            motivo="Resultado cualificado como 'Trazas' — detectado sin cuantificación. No se puede emitir juicio ECA.",
            valor_lab_original=None, valor_comparado=None, unidad_comparada=None,
            eca_valor_minimo=ctx.eca_valor_minimo, eca_valor_maximo=ctx.eca_valor_maximo,
            detalles=detalles,
        )

    return None


def _describir_rango(vmin: Optional[float], vmax: Optional[float]) -> str:
    if vmin is not None and vmax is not None:
        return f"dentro de [{vmin:g}, {vmax:g}]"
    if vmax is not None:
        return f"≤ {vmax:g}"
    if vmin is not None:
        return f"≥ {vmin:g}"
    return ""


def _unidad_de_especie(especie: Optional[str]) -> Optional[str]:
    """
    Dada una especie ECA ('ion_NO3', 'N_amoniacal_total', ...) retorna la
    unidad legible para mostrar junto al valor convertido.
    """
    mapa = {
        "ion_NO3":               "mg NO3-/L",
        "ion_NO2":               "mg NO2-/L",
        "N_NO3":                 "mg N-NO3/L",
        "N_NO2":                 "mg N-NO2/L",
        "suma_NO3N_NO2N_como_N": "mg N/L",
        "NH3_libre":             "mg NH3/L",
        "N_amoniacal_total":     "mg N/L",
        "P_total":               "mg P/L",
        "metal_total":           "mg/L (total)",
        "metal_disuelto":        "mg/L (disuelto)",
    }
    return mapa.get(especie or "")
