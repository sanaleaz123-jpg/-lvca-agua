-- =============================================================================
-- 012: forma_analitica (total/disuelta) en parametros y eca_valores
--      Fuente: DS 004-2017-MINAM, Nota general del Anexo —
--      "Los valores están en concentraciones totales, salvo que se indique
--      lo contrario". Excepción conocida: Cadmio Disuelto en Cat 4.
--
-- Cambio #9 del plan: permite detectar discrepancia entre lo que mide el
-- laboratorio (parametros.forma_analitica) y lo que exige el DS para cada
-- ECA (eca_valores.forma_analitica). Si no coinciden, el motor de cumplimiento
-- marca NO_VERIFICABLE con motivo explícito.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. parametros.forma_analitica
--    Lo que el método analítico efectivamente mide. Default 'total' porque es
--    lo estándar (AAS, digestión ácida previa, ICP-MS, etc.).
--    Para métodos que miden solo la fracción disuelta (ej. filtración 0,45 µm
--    antes del análisis, ICP sin digestión), el admin debe cambiar a 'disuelta'.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS forma_analitica TEXT NOT NULL DEFAULT 'total'
    CHECK (forma_analitica IN ('total', 'disuelta', 'no_aplica'));

COMMENT ON COLUMN parametros.forma_analitica IS
'Fracción que el método analítico realmente mide: total, disuelta o no_aplica '
'(para parámetros como pH, T, conductividad donde no hay fracción aplicable).';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. eca_valores.forma_analitica
--    Lo que exige el DS 004-2017-MINAM para cada (ECA, parámetro). Default
--    'total' (regla general del DS). Para Cadmio Cat 4 debe marcarse 'disuelta'.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE eca_valores ADD COLUMN IF NOT EXISTS forma_analitica TEXT NOT NULL DEFAULT 'total'
    CHECK (forma_analitica IN ('total', 'disuelta', 'no_aplica'));

COMMENT ON COLUMN eca_valores.forma_analitica IS
'Fracción que el DS exige para este (ECA, parámetro). Default "total" (regla '
'general de la Nota del Anexo). Excepción conocida: Cadmio Disuelto en Cat 4.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Marcado inicial — parámetros sin fracción aplicable
--    pH, Temperatura, Conductividad, OD, Turbidez, Color, etc. no tienen
--    "forma total/disuelta". Se marcan 'no_aplica' para que el motor no
--    exija coherencia donde no corresponde.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE parametros SET forma_analitica = 'no_aplica'
WHERE codigo IN (
    'P001', 'P002', 'P003', 'P004', 'P006',   -- campo
    'P011',                                     -- color verdadero
    'P019',                                     -- DBO5 (método de oxidación, no aplica fracción)
    'P091',                                     -- microcistina (toxina disuelta por naturaleza)
    'P120', 'P124', 'P126', 'P130'             -- hidrobiológicos
);

-- El resto (nitratos, nitritos, N total, P total, sulfatos, cloruros, metales)
-- queda en default 'total'. Si el lab mide Fe o Mn filtrados (disuelto real),
-- el admin debe actualizarlo manualmente:
--     UPDATE parametros SET forma_analitica = 'disuelta' WHERE codigo = 'P074';


-- Sincronizar eca_valores: si el parámetro es no_aplica, el ECA también.
UPDATE eca_valores SET forma_analitica = 'no_aplica'
WHERE parametro_id IN (
    SELECT id FROM parametros WHERE forma_analitica = 'no_aplica'
);


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='parametros' AND column_name='forma_analitica') THEN
        RAISE EXCEPTION 'parametros.forma_analitica no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='eca_valores' AND column_name='forma_analitica') THEN
        RAISE EXCEPTION 'eca_valores.forma_analitica no fue creada';
    END IF;
    RAISE NOTICE 'Migracion 012 aplicada. Campos añadidos: parametros.forma_analitica, eca_valores.forma_analitica.';
END $$;
