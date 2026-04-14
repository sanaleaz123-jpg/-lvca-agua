-- =============================================================================
-- 005: Soporte para muestreo a profundidad (columna de agua)
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Nuevas columnas en muestras para profundidad
-- ─────────────────────────────────────────────────────────────────────────────

-- Modo de muestreo: superficial (default) o columna de agua
ALTER TABLE muestras ADD COLUMN IF NOT EXISTS modo_muestreo TEXT DEFAULT 'superficial'
    CHECK (modo_muestreo IN ('superficial', 'columna'));

-- Tipo de profundidad: S (superficie), M (medio), F (fondo) — NULL para superficial
ALTER TABLE muestras ADD COLUMN IF NOT EXISTS profundidad_tipo TEXT
    CHECK (profundidad_tipo IS NULL OR profundidad_tipo IN ('S', 'M', 'F'));

-- Valor de la profundidad en metros (ingresado manualmente)
ALTER TABLE muestras ADD COLUMN IF NOT EXISTS profundidad_valor NUMERIC(8,2);

-- UUID compartido que agrupa las 3 muestras de una misma columna de agua
ALTER TABLE muestras ADD COLUMN IF NOT EXISTS grupo_profundidad UUID;

-- Profundidad total del punto (medida con ecosonda), en metros
ALTER TABLE muestras ADD COLUMN IF NOT EXISTS profundidad_total NUMERIC(8,2);

-- Profundidad Secchi (disco de Secchi), en metros
ALTER TABLE muestras ADD COLUMN IF NOT EXISTS profundidad_secchi NUMERIC(8,2);

-- Renombrar conceptualmente caudal_estimado → descarga (no se renombra la columna
-- para no romper datos existentes, pero el label en la UI cambiará)
-- El campo caudal_estimado se usará como "Descarga"
COMMENT ON COLUMN muestras.caudal_estimado IS 'Descarga (antes caudal estimado)';

-- Índice para agrupar muestras de profundidad
CREATE INDEX IF NOT EXISTS idx_muestras_grupo_prof ON muestras(grupo_profundidad)
    WHERE grupo_profundidad IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'muestras' AND column_name = 'modo_muestreo'
    ) THEN
        RAISE EXCEPTION 'Columna modo_muestreo no fue agregada a muestras';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'muestras' AND column_name = 'profundidad_tipo'
    ) THEN
        RAISE EXCEPTION 'Columna profundidad_tipo no fue agregada a muestras';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'muestras' AND column_name = 'grupo_profundidad'
    ) THEN
        RAISE EXCEPTION 'Columna grupo_profundidad no fue agregada a muestras';
    END IF;

    RAISE NOTICE 'Migración 005 aplicada correctamente.';
END $$;
