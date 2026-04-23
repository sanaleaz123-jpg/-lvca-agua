-- =============================================================================
-- 014: Línea base de temperatura por punto y mes — para evaluación Δ3
--      Fuente: DS 004-2017-MINAM, Anexo, Nota general —
--      "Δ3 = variación máxima ±3 °C respecto al promedio mensual multianual
--      del área evaluada" (serie 1-5 años, considerando estacionalidad).
--
-- Cambio #6 del plan: sin línea base histórica por estación, el criterio
-- Δ3 no es verificable y constituye no conformidad documental del programa
-- de monitoreo (Nota 8 del Excel oficial).
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Tabla linea_base_temperatura
--    Un registro por (punto, mes): promedio multianual de la temperatura del
--    agua para ese mes calendario, calculado sobre una serie histórica de
--    1 a 5 años del mismo punto.
--
--    Ejemplo:
--      punto PM-01 · mes 8 (agosto) · promedio 14.2 °C · n_anos 4 · anios 2020-2023
--      → cualquier medición agosto en PM-01 fuera de [11.2 , 17.2] es Δ>3
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS linea_base_temperatura (
    id                    UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    punto_muestreo_id     UUID NOT NULL REFERENCES puntos_muestreo(id) ON DELETE CASCADE,
    mes                   SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    promedio_multianual_c NUMERIC(6,2) NOT NULL,
    desviacion_std_c      NUMERIC(6,2),                  -- opcional, para análisis extendidos
    n_anos                SMALLINT CHECK (n_anos BETWEEN 1 AND 20),
    anio_inicio           SMALLINT,
    anio_fin              SMALLINT,
    observacion           TEXT,
    registrado_por        UUID REFERENCES usuarios(id),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (punto_muestreo_id, mes)
);

CREATE INDEX IF NOT EXISTS idx_linea_base_temp_punto ON linea_base_temperatura(punto_muestreo_id);
CREATE INDEX IF NOT EXISTS idx_linea_base_temp_mes   ON linea_base_temperatura(mes);

COMMENT ON TABLE linea_base_temperatura IS
'Promedio mensual multianual de temperatura del agua por punto de muestreo. '
'Base para evaluar el criterio Δ3 del DS 004-2017-MINAM (variación máxima '
'±3 °C). Sin al menos 1 año de serie, el criterio Δ3 no es verificable.';

COMMENT ON COLUMN linea_base_temperatura.promedio_multianual_c IS
'Media aritmética de la temperatura medida en el mismo mes durante n_anos años.';

COMMENT ON COLUMN linea_base_temperatura.n_anos IS
'Cantidad de años usados para calcular el promedio (serie 1-5 según el DS, '
'hasta 20 en la práctica). Si n_anos = 1 el promedio equivale a una única '
'medición — usable como referencia pero menos robusto.';


-- Trigger updated_at
CREATE OR REPLACE TRIGGER set_updated_at_linea_base_temp
    BEFORE UPDATE ON linea_base_temperatura
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. RLS
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE linea_base_temperatura ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "linea_base_temp_select" ON linea_base_temperatura;
CREATE POLICY "linea_base_temp_select" ON linea_base_temperatura
    FOR SELECT USING (auth.role() = 'authenticated');


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_schema='public' AND table_name='linea_base_temperatura') THEN
        RAISE EXCEPTION 'Tabla linea_base_temperatura no fue creada';
    END IF;
    RAISE NOTICE 'Migracion 014 aplicada. Tabla linea_base_temperatura lista para evaluación Δ3.';
END $$;
