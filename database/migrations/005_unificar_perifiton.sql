-- =============================================================================
-- 005: Unificar nomenclatura "Perifiton" en la tabla parametros
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
--
-- CONTEXTO:
--   El código Python actual (database/seeds/seed_parametros.py L142-143) ya usa
--   "Perifiton" con "i" como forma canónica. Sin embargo, si la BD de
--   producción fue poblada con un seed anterior que usaba "Perifoton", esta
--   migración normaliza esas filas al valor correcto.
--
--   Se aplica case-insensitive vía ILIKE para cubrir variantes: "perifoton",
--   "Perifoton", "PERIFOTON", etc. También actualiza nombre_corto si existe
--   esa columna (depende de schema real).
--
-- SEGURO:
--   - Usa ILIKE en vez de = para evitar fallar si la fila ya está correcta.
--   - No hace nada si no hay filas erróneas.
--   - No afecta registros relacionados (resultados_laboratorio, eca_valores)
--     porque usan parametro_id (UUID), no el nombre.
-- =============================================================================

-- 1) Normalizar nombre canónico
UPDATE parametros
SET nombre = 'Perifiton'
WHERE nombre ILIKE '%perifoton%';

-- 2) Normalizar nombre_corto si la columna existe
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'parametros' AND column_name = 'nombre_corto'
    ) THEN
        UPDATE parametros
        SET nombre_corto = 'Perifiton'
        WHERE nombre_corto ILIKE '%perifoton%';
    END IF;
END $$;

-- 3) Verificación
DO $$
DECLARE
    n_erroneos INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_erroneos
    FROM parametros
    WHERE nombre ILIKE '%perifoton%' AND nombre <> 'Perifiton';

    IF n_erroneos > 0 THEN
        RAISE EXCEPTION 'Quedan % fila(s) con variante errónea de Perifiton', n_erroneos;
    END IF;

    RAISE NOTICE 'Migración 005 aplicada. Todas las variantes de Perifoton normalizadas a Perifiton.';
END $$;
