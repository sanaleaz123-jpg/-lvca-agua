-- =============================================================================
-- 016: Parámetros agregados por phylum de fitoplancton
--
-- Añade 9 parámetros hidrobiológicos que se calculan automáticamente al guardar
-- un análisis Sedgewick-Rafter (services/fitoplancton_service.py:guardar_analisis_fitoplancton).
-- Cada uno representa la sumatoria de todas las especies del phylum:
--
--   - 1 fila por phylum en cel/mL  (8 phyla)
--   - 1 fila adicional para Cyanobacteria en biovolumen (mm³/L) — para
--     evaluar la tabla OMS 2021 además de la OMS 1999.
--
-- Códigos: convención FITO_<PHYLUM>[_VARIANTE]. No tienen significado para el
-- usuario final — son slugs internos. La columna `codigo` sigue siendo NOT
-- NULL UNIQUE en parametros (decisión de schema base).
--
-- ECA: ninguno aplica (DS 004-2017-MINAM no regula conteos por phylum).
-- Por eso es_eca=false. La evaluación cualitativa de Cyanobacteria se hace
-- contra umbrales OMS 1999 (cel/mL) y OMS 2021 (biovolumen) directamente
-- desde la UI usando services/fitoplancton_service.py.
--
-- El parámetro existente "Fitoplancton" (P120, cel/mL) se mantiene como total
-- general (suma de todos los phyllum) y también se calcula automáticamente
-- en guardar_analisis_fitoplancton.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================

-- Asegura las unidades necesarias.
INSERT INTO unidades_medida (simbolo, nombre)
VALUES
    ('cel/mL', 'células por mililitro'),
    ('mm3/L', 'milímetros cúbicos por litro')
ON CONFLICT (simbolo) DO NOTHING;

-- Categoría hidrobiológica (nombre canónico largo — ver migración 017 para el
-- contexto de la consolidación de nombres de categorías).
INSERT INTO categorias_parametro (nombre, descripcion)
VALUES ('Parámetros Hidrobiológicos', 'Organismos acuáticos indicadores de calidad')
ON CONFLICT (nombre) DO NOTHING;

-- Inserta los 9 parámetros. on_conflict por código → idempotente.
WITH cat AS (
    SELECT id FROM categorias_parametro WHERE nombre = 'Parámetros Hidrobiológicos' LIMIT 1
), uni_cel AS (
    SELECT id FROM unidades_medida WHERE simbolo = 'cel/mL' LIMIT 1
), uni_biovol AS (
    SELECT id FROM unidades_medida WHERE simbolo = 'mm3/L' LIMIT 1
)
INSERT INTO parametros (codigo, nombre, descripcion, categoria_id, unidad_id, metodo_analitico, activo, es_eca, observacion_tecnica)
VALUES
    ('FITO_CYANOBACTERIA_CEL', 'Cianobacteria', 'Cianobacteria',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Cyanobacteria)',
     true, false,
     'Sumatoria automática de todas las especies de Cyanobacteria registradas en el análisis Sedgewick-Rafter de la muestra. Se evalúa contra la tabla OMS 1999 (Drinking-water Alert Levels Framework): vigilancia inicial ≥200 cél/mL, alerta 1 ≥2 000 cél/mL, alerta 2 ≥100 000 cél/mL.'),

    ('FITO_CYANOBACTERIA_BIOVOL', 'Cianobacteria (biovolumen)', 'Cianobacteria biovolumen',
     (SELECT id FROM cat), (SELECT id FROM uni_biovol),
     'Sedgewick-Rafter (sumatoria de biovolumen de especies del phylum Cyanobacteria)',
     true, false,
     'Sumatoria automática del biovolumen estimado de todas las especies de Cyanobacteria. Se evalúa contra la tabla OMS 2021 (Toxic Cyanobacteria in Water, 2nd ed., Chorus & Welker): vigilancia inicial >10 colonias/mL o >50 filamentos/mL, alerta 1 ≥0,3 mm³/L, alerta 2 ≥4,0 mm³/L.'),

    ('FITO_BACILLARIOPHYTA', 'Bacillariophyta', 'Diatomeas',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Bacillariophyta)',
     true, false,
     'Sumatoria automática de todas las especies del phylum Bacillariophyta (diatomeas) registradas en el análisis Sedgewick-Rafter.'),

    ('FITO_CHLOROPHYTA', 'Chlorophyta', 'Algas verdes',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Chlorophyta)',
     true, false,
     'Sumatoria automática de todas las especies del phylum Chlorophyta (algas verdes) registradas en el análisis Sedgewick-Rafter.'),

    ('FITO_OCHROPHYTA', 'Ochrophyta', 'Algas doradas (Chrysophyta)',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Ochrophyta)',
     true, false,
     'Sumatoria automática de todas las especies del phylum Ochrophyta (algas doradas / Chrysophyta) registradas en el análisis Sedgewick-Rafter.'),

    ('FITO_CHAROPHYTA', 'Charophyta', 'Carofitas (desmidiáceas y zignematales)',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Charophyta)',
     true, false,
     'Sumatoria automática de todas las especies del phylum Charophyta registradas en el análisis Sedgewick-Rafter.'),

    ('FITO_EUGLENOPHYTA', 'Euglenophyta', 'Euglenoideos',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Euglenophyta)',
     true, false,
     'Sumatoria automática de todas las especies del phylum Euglenophyta registradas en el análisis Sedgewick-Rafter.'),

    ('FITO_DINOPHYTA', 'Dinophyta', 'Dinoflagelados',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Dinophyta)',
     true, false,
     'Sumatoria automática de todas las especies del phylum Dinophyta (dinoflagelados) registradas en el análisis Sedgewick-Rafter.'),

    ('FITO_CRYPTOPHYTA', 'Cryptophyta', 'Criptofitas',
     (SELECT id FROM cat), (SELECT id FROM uni_cel),
     'Sedgewick-Rafter (sumatoria de especies del phylum Cryptophyta)',
     true, false,
     'Sumatoria automática de todas las especies del phylum Cryptophyta registradas en el análisis Sedgewick-Rafter.')
ON CONFLICT (codigo) DO UPDATE SET
    nombre              = EXCLUDED.nombre,
    descripcion         = EXCLUDED.descripcion,
    categoria_id        = EXCLUDED.categoria_id,
    unidad_id           = EXCLUDED.unidad_id,
    metodo_analitico    = EXCLUDED.metodo_analitico,
    activo              = EXCLUDED.activo,
    es_eca              = EXCLUDED.es_eca,
    observacion_tecnica = EXCLUDED.observacion_tecnica;

-- Asegurar que P120 (Fitoplancton) esté marcado como NO ECA — antes podía
-- haber quedado con es_eca=true por default. Su valor se calcula como
-- sumatoria de todos los phyla en cel/mL.
UPDATE parametros
SET es_eca = false,
    metodo_analitico = COALESCE(metodo_analitico,
        'Utermohl/Sedgewick-Rafter (sumatoria de todos los phyla)'),
    observacion_tecnica = COALESCE(observacion_tecnica,
        'Total de fitoplancton (cel/mL): sumatoria automática de las densidades calculadas para todos los phyla. Se calcula al guardar el análisis Sedgewick-Rafter en Resultados de laboratorio → Hidrobiológico.')
WHERE codigo = 'P120';
