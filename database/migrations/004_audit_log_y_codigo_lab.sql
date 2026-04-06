-- =============================================================================
-- 004: Tabla audit_log + campo codigo_laboratorio en muestras
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. AUDIT LOG — Registro de cambios en parámetros, puntos de muestreo, etc.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    tabla           TEXT NOT NULL,                -- 'parametros', 'puntos_muestreo', etc.
    registro_id     TEXT NOT NULL,                -- UUID del registro afectado
    accion          TEXT NOT NULL                 -- 'crear', 'editar', 'eliminar', 'desactivar', 'activar'
                        CHECK (accion IN ('crear','editar','eliminar','desactivar','activar')),
    campo           TEXT,                         -- campo modificado (NULL para crear/eliminar)
    valor_anterior  TEXT,                         -- valor previo (JSON si es complejo)
    valor_nuevo     TEXT,                         -- valor nuevo
    usuario_id      TEXT,                         -- UUID o nombre del usuario que hizo el cambio
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_tabla     ON audit_log(tabla);
CREATE INDEX IF NOT EXISTS idx_audit_registro  ON audit_log(registro_id);
CREATE INDEX IF NOT EXISTS idx_audit_fecha     ON audit_log(created_at DESC);

COMMENT ON TABLE audit_log IS 'Registro de auditoría para cambios en parámetros y puntos de muestreo';

-- RLS: lectura para autenticados
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "audit_log_select" ON audit_log
    FOR SELECT USING (auth.role() = 'authenticated');


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. CÓDIGO DE LABORATORIO en muestras (único por muestra)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE muestras ADD COLUMN IF NOT EXISTS codigo_laboratorio TEXT;

-- Constraint de unicidad (ignora NULLs — solo aplica cuando el campo tiene valor)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'muestras_codigo_laboratorio_unique'
    ) THEN
        ALTER TABLE muestras
            ADD CONSTRAINT muestras_codigo_laboratorio_unique UNIQUE (codigo_laboratorio);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_muestras_codigo_lab ON muestras(codigo_laboratorio)
    WHERE codigo_laboratorio IS NOT NULL;

COMMENT ON COLUMN muestras.codigo_laboratorio IS 'Código único asignado por el laboratorio receptor';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Campos adicionales en puntos_muestreo (si faltan)
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS sistema_hidrico TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS lugar_muestreo TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS finalidad TEXT;

-- Ampliar CHECK de tipo para incluir todos los tipos usados
ALTER TABLE puntos_muestreo DROP CONSTRAINT IF EXISTS puntos_muestreo_tipo_check;
ALTER TABLE puntos_muestreo ADD CONSTRAINT puntos_muestreo_tipo_check
    CHECK (tipo IN ('laguna','rio','canal','manantial','pozo','embalse','bocatoma','desarenador','otro'));


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'audit_log'
    ) THEN
        RAISE EXCEPTION 'Tabla audit_log no fue creada';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'muestras' AND column_name = 'codigo_laboratorio'
    ) THEN
        RAISE EXCEPTION 'Columna codigo_laboratorio no fue agregada a muestras';
    END IF;

    RAISE NOTICE 'Migración 004 aplicada correctamente.';
END $$;
