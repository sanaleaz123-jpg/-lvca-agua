-- =============================================================================
-- 024: Código de reporte correlativo del Reporte de Ensayo de FITOPLANCTON,
--      por campaña (espejo de microcistina_reportes de la migración 022).
--
--      El correlativo es "LVCA - NNN-FITO-AAAA" (001, 002, 003 …) y se genera
--      en services/reporte_fitoplancton_service.get_codigo_reporte_fito().
--
-- Requiere haber aplicado 022. Ejecutar en: Supabase Dashboard > SQL Editor.
--              (o: python -m scripts.apply_migration database/migrations/024_fitoplancton_reportes.sql)
-- =============================================================================

CREATE TABLE IF NOT EXISTS fitoplancton_reportes (
    campana_id      UUID PRIMARY KEY REFERENCES campanas(id) ON DELETE CASCADE,
    codigo_reporte  TEXT,                          -- "LVCA - 001-FITO-2026"
    fecha_emision   DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE fitoplancton_reportes IS
'Código de reporte correlativo y fecha de emisión del Reporte de Ensayo de '
'fitoplancton, uno por campaña.';

-- RLS: lectura abierta a autenticados; escritura por service_role (admin).
ALTER TABLE fitoplancton_reportes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS fitoplancton_reportes_select ON fitoplancton_reportes;
CREATE POLICY fitoplancton_reportes_select
    ON fitoplancton_reportes FOR SELECT
    USING (TRUE);

-- Verificación
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name='fitoplancton_reportes') THEN
        RAISE EXCEPTION 'fitoplancton_reportes no fue creada';
    END IF;
    RAISE NOTICE '✓ Migración 024 (fitoplancton_reportes) aplicada';
END $$;
