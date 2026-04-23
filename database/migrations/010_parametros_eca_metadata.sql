-- =============================================================================
-- 010: Metadata ECA por parámetro — especie química, flag es_eca y nota técnica
--      Fuente de verdad: ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx
--
-- Cubre 3 cambios identificados en el análisis del Excel oficial:
--   (1) expresado_como en eca_valores — factor de conversión al comparar
--   (3) es_eca en parametros         — marca parámetros sin ECA en el DS
--   (8) observacion_tecnica          — nota oficial copiada del Excel
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. eca_valores.expresado_como
--    Especie química oficial con la que el DS 004-2017-MINAM expresa el valor.
--    Se usa en el backend para aplicar el factor de conversión correcto al
--    comparar contra el resultado del laboratorio (que puede estar en otra
--    unidad que la que exige el DS).
--
--    Valores posibles:
--      ion_NO3                -> valor en mg NO3-/L (Cat 1 y Cat 4)
--      ion_NO2                -> valor en mg NO2-/L (Cat 1)
--      N_NO3                  -> valor en mg N-NO3/L
--      N_NO2                  -> valor en mg N-NO2/L
--      suma_NO3N_NO2N_como_N  -> Cat 3-D1: suma de (NO3-N + NO2-N) como N
--      NH3_libre              -> Cat 4: NH3 no ionizado (depende pH y T, Tabla N°1)
--      N_amoniacal_total      -> Cat 1-A2: N total (NH3 + NH4+) como N
--      P_total                -> Cat 1 y Cat 4: fósforo total (orgánico + inorgánico)
--      metal_total            -> concentración total (regla general del DS)
--      metal_disuelto         -> concentración disuelta (excepción Cadmio Cat 4)
--      ion                    -> ion genérico (Cl-, SO4 2-, etc.)
--      sin_conversion         -> no requiere conversión
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE eca_valores ADD COLUMN IF NOT EXISTS expresado_como TEXT;

COMMENT ON COLUMN eca_valores.expresado_como IS
'Especie química oficial del valor ECA en el DS 004-2017-MINAM. '
'Determina el factor de conversión que debe aplicarse al comparar con un '
'resultado de laboratorio reportado en otra unidad. '
'Ver services/conversion_especies.py.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. parametros.es_eca
--    FALSE = el parámetro se captura (en campo o laboratorio) pero NO está
--    regulado por el DS 004-2017-MINAM. La plataforma NO debe comparar su
--    valor contra un umbral ni emitir juicio de cumplimiento/incumplimiento.
--
--    Casos conocidos (Notas 3 y 5 del Excel):
--      - Fosfatos (PO4 3-): el DS regula Fósforo Total, no ortofosfatos.
--      - NH4+ (amonio medido por ISE): el DS regula N amoniacal total (Cat 1)
--        o NH3 libre (Cat 4), no el ion NH4+ directamente.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS es_eca BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN parametros.es_eca IS
'FALSE = el parámetro se registra pero NO tiene valor ECA en el DS 004-2017-MINAM '
'(ej. Fosfatos PO4 3-, NH4+). La plataforma no debe comparar estos parámetros '
'contra ningún límite legal.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. parametros.observacion_tecnica
--    Nota oficial copiada del Excel ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx.
--    Incluye: conversiones de unidad, forma analítica (total vs disuelta),
--    dependencia de pH/T, y advertencias conocidas del DS.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS observacion_tecnica TEXT;

COMMENT ON COLUMN parametros.observacion_tecnica IS
'Nota técnica oficial del Excel ECA_DS-004-2017-MINAM_PEIMS-LVCA_v2.xlsx. '
'Se muestra en la UI junto al parámetro para advertir al usuario sobre '
'conversiones, formas analíticas y criterios del DS.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Marcado inicial de parámetros sin ECA
--    Fuera de seed_parametros.py para no depender del orden de ejecución.
-- ─────────────────────────────────────────────────────────────────────────────

-- P038 Fosfatos (PO4 3-): el DS NO regula fosfatos, solo Fósforo Total (P036).
UPDATE parametros SET es_eca = FALSE WHERE codigo = 'P038';

-- Nota: P033 (Amonio / Amoniaco, método Nessler SM 4500-NH3 B) mide el N
-- amoniacal total expresado como N. SÍ cumple con el ECA Cat 1-A2 (1,5 mg N/L).
-- NO se marca es_eca=FALSE. Su limitación (no distingue NH3 libre de NH4+) se
-- documenta en parametros.observacion_tecnica vía seed_parametros.py.


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='eca_valores' AND column_name='expresado_como') THEN
        RAISE EXCEPTION 'eca_valores.expresado_como no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='parametros' AND column_name='es_eca') THEN
        RAISE EXCEPTION 'parametros.es_eca no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='parametros' AND column_name='observacion_tecnica') THEN
        RAISE EXCEPTION 'parametros.observacion_tecnica no fue creada';
    END IF;
    RAISE NOTICE 'Migracion 010 aplicada. Campos añadidos: eca_valores.expresado_como, parametros.es_eca, parametros.observacion_tecnica.';
END $$;
