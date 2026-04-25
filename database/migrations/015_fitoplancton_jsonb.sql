-- =============================================================================
-- 015: Submódulo Hidrobiológico — Fitoplancton (Sedgewick-Rafter)
--      Persiste el análisis cuantitativo de fitoplancton por muestra como un
--      único documento JSONB en muestras.datos_fitoplancton.
--
-- Estructura del JSON:
--   {
--     "metadatos": {
--       "vol_muestra_ml":      <float>,
--       "vol_concentrado_ml":  <float>,
--       "area_campo_mm2":      <float>,
--       "num_campos":          <int>,
--       "fecha_analisis":      "YYYY-MM-DD",
--       "analista_id":         "<uuid>"
--     },
--     "resultados": {
--       "Cyanobacteria": {
--         "Oscillatoria sp.": { "conteo_bruto": 12, "cel_ml": 12.0, "cel_l": 12000.0 },
--         ...
--       },
--       "Bacillariophyta": { ... },
--       ...
--     }
--   }
--
-- Decisión de diseño: una sola columna JSONB en muestras (no 59 columnas, no
-- tabla normalizada) — el análisis Sedgewick-Rafter es un documento único por
-- muestra y la taxonomía de método NO pertenece a parametros (no es ECA).
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================

ALTER TABLE muestras
    ADD COLUMN IF NOT EXISTS datos_fitoplancton JSONB;

COMMENT ON COLUMN muestras.datos_fitoplancton IS
    'Análisis cuantitativo de fitoplancton (método Sedgewick-Rafter): metadatos del recuento + densidades por especie en cel/mL y cel/L. NULL si la muestra no tuvo análisis hidrobiológico.';

-- Índice GIN para queries futuras tipo "muestras con presencia de Microcystis"
CREATE INDEX IF NOT EXISTS idx_muestras_datos_fitoplancton
    ON muestras USING GIN (datos_fitoplancton);
