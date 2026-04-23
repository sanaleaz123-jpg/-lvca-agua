-- =============================================================================
-- 011: Tabla matricial de valores ECA para parámetros con dependencia bi-variable
--      Fuente: DS 004-2017-MINAM Anexo, Tabla N°1 (NH3 en función de pH y T)
--
-- Cambio #4 del plan: implementa el ECA de Amoniaco libre (P034) en Cat 4
-- como lookup por pH y T, tal como lo exige el DS.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Tabla eca_valores_matriciales
--
--    Generalización de eca_valores para parámetros cuyo umbral ECA depende de
--    dos variables (ej. NH3 libre en función de pH y T). Convive con eca_valores:
--    la lógica de comparación prioriza la fila matricial si existe.
--
--    Semántica del lookup (regla del DS para la Tabla N°1):
--      1. Tomar variables_x e _y medidas (pH y T en °C).
--      2. Redondear cada una al "próximo superior" de la grilla (condición más
--         extrema = más restrictiva).
--      3. SELECT valor WHERE variable_x, valor_x, variable_y, valor_y.
--      4. Si las variables medidas caen bajo el mínimo de la grilla, aplicar
--         el mínimo (pH 6, T 0 °C). Si exceden el máximo, retornar error
--         (fuera de alcance del DS).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eca_valores_matriciales (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    eca_id          UUID NOT NULL REFERENCES ecas(id) ON DELETE CASCADE,
    parametro_id    UUID NOT NULL REFERENCES parametros(id) ON DELETE CASCADE,
    variable_x      TEXT NOT NULL,                   -- ej. 'pH'
    valor_x         NUMERIC(8,3) NOT NULL,           -- valor del punto en la grilla X
    variable_y      TEXT NOT NULL,                   -- ej. 'temperatura_C'
    valor_y         NUMERIC(8,3) NOT NULL,           -- valor del punto en la grilla Y
    valor           NUMERIC(18,6) NOT NULL,          -- ECA (mismas unidades que eca_valores.valor_maximo)
    expresado_como  TEXT,                            -- misma semántica que eca_valores.expresado_como
    observacion     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (eca_id, parametro_id, variable_x, valor_x, variable_y, valor_y)
);

CREATE INDEX IF NOT EXISTS idx_eca_matriciales_eca_param
    ON eca_valores_matriciales (eca_id, parametro_id);

CREATE INDEX IF NOT EXISTS idx_eca_matriciales_lookup
    ON eca_valores_matriciales (eca_id, parametro_id, valor_x, valor_y);

COMMENT ON TABLE eca_valores_matriciales IS
'ECAs que dependen de dos variables (p.ej. NH3 en Cat 4 según pH y T, Tabla N°1 del DS 004-2017-MINAM).
Convive con eca_valores: la lógica de verificación prioriza la fila matricial si existe.';

COMMENT ON COLUMN eca_valores_matriciales.variable_x IS
'Nombre de la primera variable independiente. Ej. "pH", "temperatura_C", "salinidad_gkg".';

COMMENT ON COLUMN eca_valores_matriciales.variable_y IS
'Nombre de la segunda variable independiente.';

COMMENT ON COLUMN eca_valores_matriciales.valor IS
'Valor ECA para el par (valor_x, valor_y). Aplicable al redondear las mediciones al próximo superior.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Row Level Security — lectura pública como el resto de datos maestros
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE eca_valores_matriciales ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "eca_matriciales_select" ON eca_valores_matriciales;
CREATE POLICY "eca_matriciales_select" ON eca_valores_matriciales
    FOR SELECT USING (auth.role() = 'authenticated');


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='public' AND table_name='eca_valores_matriciales'
    ) THEN
        RAISE EXCEPTION 'Tabla eca_valores_matriciales no fue creada';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE tablename='eca_valores_matriciales' AND indexname='idx_eca_matriciales_lookup'
    ) THEN
        RAISE EXCEPTION 'Indice idx_eca_matriciales_lookup no fue creado';
    END IF;
    RAISE NOTICE 'Migracion 011 aplicada. Tabla eca_valores_matriciales lista para seed (Tabla N°1 NH3).';
END $$;
