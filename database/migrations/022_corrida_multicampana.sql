-- =============================================================================
-- 022: La corrida ELISA pasa a ser a NIVEL DE PLACA (puede abarcar varias
--      campañas). El kit se usa una sola vez, por lo que se juntan muestras de
--      varios días/campañas en una misma placa.
--
-- Cambios:
--   1. elisa_microcistina_corridas: campana_id deja de ser único/obligatorio
--      (una corrida ya no pertenece a una sola campaña).
--   2. resultados_laboratorio.corrida_id: vincula cada resultado de microcistina
--      con la placa donde se midió (de ahí el reporte saca curva y control).
--   3. microcistina_reportes: código de reporte correlativo POR CAMPAÑA
--      (antes vivía en la corrida; ahora una corrida sirve a varias campañas).
--
-- Requiere haber aplicado 021. Ejecutar en: Supabase Dashboard > SQL Editor.
-- =============================================================================


-- 1. Corrida ya no es 1:1 con campaña ----------------------------------------
ALTER TABLE elisa_microcistina_corridas
    DROP CONSTRAINT IF EXISTS elisa_microcistina_corridas_campana_id_key;
ALTER TABLE elisa_microcistina_corridas
    ALTER COLUMN campana_id DROP NOT NULL;

COMMENT ON COLUMN elisa_microcistina_corridas.campana_id IS
'Opcional/legacy: una corrida es una PLACA que puede abarcar varias campañas. '
'El vínculo real corrida↔muestra está en resultados_laboratorio.corrida_id.';


-- 2. Vínculo resultado → placa ------------------------------------------------
ALTER TABLE resultados_laboratorio
    ADD COLUMN IF NOT EXISTS corrida_id UUID
        REFERENCES elisa_microcistina_corridas(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_resultados_corrida
    ON resultados_laboratorio(corrida_id);

COMMENT ON COLUMN resultados_laboratorio.corrida_id IS
'Placa ELISA (elisa_microcistina_corridas) donde se midió este resultado. '
'NULL para parámetros que no son microcistina.';


-- 3. Código de reporte por campaña -------------------------------------------
CREATE TABLE IF NOT EXISTS microcistina_reportes (
    campana_id      UUID PRIMARY KEY REFERENCES campanas(id) ON DELETE CASCADE,
    codigo_reporte  TEXT,                          -- "LVCA - 001-MC-2026"
    fecha_emision   DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE microcistina_reportes IS
'Código de reporte correlativo y fecha de emisión por campaña (el Reporte de '
'Ensayo se emite por campaña aunque la placa abarque varias).';


-- Verificación
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='resultados_laboratorio' AND column_name='corrida_id') THEN
        RAISE EXCEPTION 'resultados_laboratorio.corrida_id no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name='microcistina_reportes') THEN
        RAISE EXCEPTION 'microcistina_reportes no fue creada';
    END IF;
    RAISE NOTICE '✓ Migración 022 (corrida multi-campaña) aplicada';
END $$;
