-- =============================================================================
-- 017: Consolidar categorías de parámetros (eliminar duplicados)
--
-- Estado actual antes de la migración:
--   La tabla categorias_parametro tiene SEIS filas:
--     "Campo"               vs  "Parámetros de Campo"
--     "Fisicoquimico"       vs  "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)"
--     "Hidrobiologico"      vs  "Parámetros Hidrobiológicos"
--
--   Los parámetros están repartidos entre ambas versiones de cada par, lo que
--   provoca que el filtro de la página Parámetros muestre opciones que no
--   coinciden con la columna "Categoría" de la tabla.
--
-- Resultado tras esta migración:
--   Sólo quedan las TRES versiones "largas" (canónicas para mostrar en UI):
--     - "Parámetros de Campo"
--     - "Parámetros Físico-Químicos (Inorgánicos / Orgánicos)"
--     - "Parámetros Hidrobiológicos"
--
--   Todos los parámetros que apuntaban a las versiones cortas se reasignan a
--   sus equivalentes largas. Las filas con nombre corto se eliminan.
--
-- El módulo services/parametro_registry.py mantiene el mapeo (LARGO → corto)
-- via _CAT_NORMALIZE para que el código interno siga usando "Campo",
-- "Fisicoquimico", "Hidrobiologico" sin cambios.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================

-- 1) Asegurar que las 3 categorías canónicas con nombres largos existan.
INSERT INTO categorias_parametro (nombre, descripcion) VALUES
    ('Parámetros de Campo',
     'Mediciones in situ con equipos de campo'),
    ('Parámetros Físico-Químicos (Inorgánicos / Orgánicos)',
     'Parámetros físicos, químicos y metales analizados en laboratorio'),
    ('Parámetros Hidrobiológicos',
     'Organismos acuáticos indicadores de calidad')
ON CONFLICT (nombre) DO NOTHING;

-- 2) Reasignar los parámetros que apuntan a las categorías "cortas" hacia
--    sus equivalentes "largas".
WITH cat_pairs AS (
    SELECT
        src.id  AS old_id,
        target.id AS new_id
    FROM categorias_parametro src
    JOIN categorias_parametro target ON
        (src.nombre = 'Campo'           AND target.nombre = 'Parámetros de Campo') OR
        (src.nombre = 'Fisicoquimico'   AND target.nombre = 'Parámetros Físico-Químicos (Inorgánicos / Orgánicos)') OR
        (src.nombre = 'Hidrobiologico'  AND target.nombre = 'Parámetros Hidrobiológicos')
)
UPDATE parametros p
SET categoria_id = cp.new_id
FROM cat_pairs cp
WHERE p.categoria_id = cp.old_id;

-- 3) Eliminar las filas legacy con nombres cortos (ya quedan sin parámetros).
DELETE FROM categorias_parametro
WHERE nombre IN ('Campo', 'Fisicoquimico', 'Hidrobiologico');

-- 4) Refrescar las descripciones de las canónicas (idempotente).
UPDATE categorias_parametro SET descripcion = 'Mediciones in situ con equipos de campo'
    WHERE nombre = 'Parámetros de Campo';
UPDATE categorias_parametro SET descripcion = 'Parámetros físicos, químicos y metales analizados en laboratorio'
    WHERE nombre = 'Parámetros Físico-Químicos (Inorgánicos / Orgánicos)';
UPDATE categorias_parametro SET descripcion = 'Organismos acuáticos indicadores de calidad'
    WHERE nombre = 'Parámetros Hidrobiológicos';

-- =============================================================================
-- Verificación rápida (opcional, ejecutar después):
--   SELECT cp.nombre, COUNT(p.id) AS n_parametros
--   FROM categorias_parametro cp
--   LEFT JOIN parametros p ON p.categoria_id = cp.id
--   GROUP BY cp.nombre ORDER BY cp.nombre;
-- Debe mostrar SÓLO las 3 filas con nombres largos.
-- =============================================================================
