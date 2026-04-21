-- =============================================================================
-- 007: Corregir unidad de Temperatura "gC" → "°C"
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
--
-- CONTEXTO:
--   El símbolo "gC" (una transcripción incorrecta de "grados Celsius") se
--   introdujo en el seed inicial de unidades_medida y se propagó a P002
--   Temperatura. Se ve en: Parámetros y ECAs (columna Unidad), tab In situ,
--   Resultados, Base de Datos.
--
--   El símbolo canónico es "°C" (signo de grado + C). Este cambio:
--     1. Corrige el registro en unidades_medida → el símbolo nuevo se refleja
--        automáticamente en toda la app porque parametros.unidad_id apunta
--        por UUID (el label cambia, la relación no).
--     2. Normaliza cualquier registro histórico en mediciones_insitu.unidad
--        (campo TEXT copiado en el momento de la medición).
--
--   Los seeds Python (seed_unidades.py, seed_parametros.py, seed_ecas.py)
--   se actualizaron en este mismo commit para que un re-seed no reintroduzca
--   el error.
--
-- SEGURO:
--   - Idempotente: si ya es "°C", el UPDATE no hace nada.
--   - No rompe integridad referencial (FK es por UUID).
--   - No afecta resultados_laboratorio: esa tabla no almacena unidad.
-- =============================================================================

-- 1) Corregir el símbolo en la tabla maestra de unidades
UPDATE unidades_medida
SET simbolo = '°C'
WHERE simbolo = 'gC';

-- 2) Corregir el símbolo copiado en mediciones in situ históricas
UPDATE mediciones_insitu
SET unidad = '°C'
WHERE unidad = 'gC';

-- 3) Verificación
DO $$
DECLARE
    n_gc_unidades    INTEGER;
    n_gc_mediciones  INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_gc_unidades
    FROM unidades_medida
    WHERE simbolo = 'gC';

    SELECT COUNT(*) INTO n_gc_mediciones
    FROM mediciones_insitu
    WHERE unidad = 'gC';

    IF n_gc_unidades > 0 OR n_gc_mediciones > 0 THEN
        RAISE EXCEPTION
            'Quedan referencias a "gC" (unidades_medida: %, mediciones_insitu: %)',
            n_gc_unidades, n_gc_mediciones;
    END IF;

    RAISE NOTICE 'Migración 007 aplicada. Símbolo "gC" normalizado a "°C" en unidades_medida y mediciones_insitu.';
END $$;
