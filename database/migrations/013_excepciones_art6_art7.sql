-- =============================================================================
-- 013: Art. 6 (excepciones por condiciones naturales) y Art. 7 (zona de mezcla)
--      Fuente: DS 004-2017-MINAM, Arts. 6 y 7 + Excel notas 15 y 16.
--
-- Cambio #7 del plan: habilita que el motor de cumplimiento distinga:
--   (a) Art. 7 - Zona de mezcla → NO_VERIFICABLE para ese punto.
--   (b) Art. 6 - Excepción natural aprobada → EXCEDE_EXCEPCION_ART6 en vez de EXCEDE.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Art. 7 — zona de mezcla (flag por punto)
--    El cumplimiento ECA se verifica FUERA de la zona de mezcla definida por
--    ANA. Si un punto está dentro, no se emite veredicto.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS dentro_zona_mezcla BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS zona_mezcla_observacion TEXT;

COMMENT ON COLUMN puntos_muestreo.dentro_zona_mezcla IS
'TRUE si el punto está dentro de una zona de mezcla definida por ANA (Art. 7 '
'del DS 004-2017-MINAM). En ese caso el motor de cumplimiento marca el resultado '
'como NO_VERIFICABLE — el ECA se verifica fuera de la zona de mezcla.';

COMMENT ON COLUMN puntos_muestreo.zona_mezcla_observacion IS
'Descripción textual: ubicación respecto al vertimiento, resolución ANA, '
'distancia al punto de descarga, etc.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Art. 6 — excepciones por condiciones naturales
--    Tabla separada porque la excepción aplica por (punto × parámetro) y
--    requiere trazabilidad al estudio técnico y a la R.J. de ANA que aprobó.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS excepciones_art6 (
    id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    punto_muestreo_id    UUID NOT NULL REFERENCES puntos_muestreo(id) ON DELETE CASCADE,
    parametro_id         UUID NOT NULL REFERENCES parametros(id) ON DELETE CASCADE,
    vigente              BOOLEAN NOT NULL DEFAULT TRUE,
    rj_ana_sustento      TEXT,                      -- Ej. "R.J. N° 123-2024-ANA"
    fecha_aprobacion     DATE,
    fecha_vencimiento    DATE,                      -- NULL = indefinida
    causa_natural        TEXT,                      -- Ej. "mineralización geológica"
    descripcion          TEXT,
    registrado_por       UUID REFERENCES usuarios(id),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (punto_muestreo_id, parametro_id)
);

CREATE INDEX IF NOT EXISTS idx_excepciones_art6_punto   ON excepciones_art6(punto_muestreo_id);
CREATE INDEX IF NOT EXISTS idx_excepciones_art6_param   ON excepciones_art6(parametro_id);
CREATE INDEX IF NOT EXISTS idx_excepciones_art6_vigente ON excepciones_art6(vigente);

COMMENT ON TABLE excepciones_art6 IS
'Excepciones aprobadas por ANA bajo el Art. 6 del DS 004-2017-MINAM: cuerpos de '
'agua que superan el ECA por condiciones naturales (geología, mineralización, '
'desbalance natural de nutrientes). Requiere estudio técnico-científico aprobado. '
'El motor de cumplimiento clasifica estos casos como EXCEDE_EXCEPCION_ART6.';


-- Trigger updated_at
CREATE OR REPLACE TRIGGER set_updated_at_excepciones_art6
    BEFORE UPDATE ON excepciones_art6
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. RLS — lectura pública para usuarios autenticados
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE excepciones_art6 ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "excepciones_art6_select" ON excepciones_art6;
CREATE POLICY "excepciones_art6_select" ON excepciones_art6
    FOR SELECT USING (auth.role() = 'authenticated');


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='puntos_muestreo' AND column_name='dentro_zona_mezcla') THEN
        RAISE EXCEPTION 'puntos_muestreo.dentro_zona_mezcla no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='public' AND table_name='excepciones_art6') THEN
        RAISE EXCEPTION 'Tabla excepciones_art6 no fue creada';
    END IF;
    RAISE NOTICE 'Migracion 013 aplicada. Art.6 (excepciones_art6) y Art.7 (puntos_muestreo.dentro_zona_mezcla) listos.';
END $$;
