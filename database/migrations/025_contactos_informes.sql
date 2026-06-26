-- =============================================================================
-- 025: Libreta de contactos y bitácora de envíos de informes por correo.
--
--      - contactos_informes: libreta reutilizable de destinatarios (nombre,
--        correo, entidad) que la página de Informes muestra con casillas.
--      - informes_envios: bitácora de cada envío (a quién, qué adjuntos,
--        cuándo, por quién, estado) para mostrar el historial por campaña.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
--   (o: python -m scripts.apply_migration database/migrations/025_contactos_informes.sql)
-- =============================================================================

CREATE TABLE IF NOT EXISTS contactos_informes (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nombre      TEXT NOT NULL,
    correo      TEXT NOT NULL UNIQUE,
    entidad     TEXT,
    activo      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE contactos_informes IS
'Libreta de destinatarios para el envío de informes por correo desde la página de Informes.';

CREATE OR REPLACE TRIGGER set_updated_at_contactos_informes
    BEFORE UPDATE ON contactos_informes
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


CREATE TABLE IF NOT EXISTS informes_envios (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campana_id    UUID REFERENCES campanas(id) ON DELETE CASCADE,
    destinatarios TEXT NOT NULL,          -- correos separados por coma
    asunto        TEXT,
    adjuntos      TEXT,                    -- nombres de archivo separados por coma
    estado        TEXT NOT NULL DEFAULT 'enviado',   -- 'enviado' | 'error'
    error         TEXT,
    enviado_por   UUID REFERENCES usuarios(id) ON DELETE SET NULL,
    enviado_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE informes_envios IS
'Bitácora de envíos de informes por correo, por campaña.';

CREATE INDEX IF NOT EXISTS idx_informes_envios_campana
    ON informes_envios (campana_id, enviado_at DESC);


-- RLS: lectura abierta a autenticados (escritura por service_role / app).
ALTER TABLE contactos_informes ENABLE ROW LEVEL SECURITY;
ALTER TABLE informes_envios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS contactos_informes_select ON contactos_informes;
CREATE POLICY contactos_informes_select ON contactos_informes FOR SELECT USING (TRUE);

DROP POLICY IF EXISTS informes_envios_select ON informes_envios;
CREATE POLICY informes_envios_select ON informes_envios FOR SELECT USING (TRUE);


-- Verificación
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='contactos_informes') THEN
        RAISE EXCEPTION 'contactos_informes no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='informes_envios') THEN
        RAISE EXCEPTION 'informes_envios no fue creada';
    END IF;
    RAISE NOTICE '✓ Migración 025 (contactos_informes, informes_envios) aplicada';
END $$;
