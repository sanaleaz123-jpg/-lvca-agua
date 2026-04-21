-- =============================================================================
-- 009: FIX de migración 008 — eliminar Clorofila A de Cat 4 E1 y E2
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
--
-- PROBLEMA QUE RESUELVE:
--   La migración 008 usó WHERE codigo IN ('ECA-C4E1', 'ECA-C4E2') asumiendo
--   que esos eran los códigos en BD. En realidad la tabla `ecas` tiene
--   codigos en formato corto: "4 E1", "4 E2" (no "ECA-C4E1"). Por eso 008
--   no afectó ninguna fila y el verify pasó en falso.
--
--   Hallazgo importante: existe un desfase entre seed_ecas.py (codigo =
--   "ECA-C4E1") y la BD real (codigo = "4 E1"). Se abordará aparte.
--
-- ENFOQUE ROBUSTO:
--   Esta migración filtra por categoria + subcategoria en vez de por
--   codigo, así no depende del formato de nomenclatura. Sobrevive a los
--   dos formatos que existen ("Categoria 4"/"E1" del seed y
--   "4 - Conservación del ambiente acuático"/"E1 - Lagunas y lagos" de BD).
--
-- SEGURO:
--   - Idempotente: si no hay filas matching, el DELETE no hace nada.
--   - No afecta otras categorías (solo Cat 4, subcategorías E1 y E2).
-- =============================================================================

-- 1) Eliminar entradas de Clorofila A en Cat 4 E1 y Cat 4 E2 (robusto)
DELETE FROM eca_valores
WHERE parametro_id = (SELECT id FROM parametros WHERE codigo = 'P124')
  AND eca_id IN (
      SELECT id FROM ecas
      WHERE categoria ILIKE '%4%'
        AND (subcategoria ILIKE 'E1%' OR subcategoria ILIKE 'E2%')
  );

-- 2) Verificación con el mismo filtro robusto
DO $$
DECLARE
    n_residuales INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_residuales
    FROM eca_valores ev
    JOIN ecas       e ON e.id = ev.eca_id
    JOIN parametros p ON p.id = ev.parametro_id
    WHERE p.codigo = 'P124'
      AND e.categoria ILIKE '%4%'
      AND (e.subcategoria ILIKE 'E1%' OR e.subcategoria ILIKE 'E2%');

    IF n_residuales > 0 THEN
        RAISE EXCEPTION
            'Quedan % entradas de Clorofila A en Cat 4 E1/E2 tras el DELETE',
            n_residuales;
    END IF;

    RAISE NOTICE 'Migración 009 aplicada. Clorofila A eliminada de Cat 4 E1 y E2 (filtro robusto por categoria/subcategoria).';
END $$;
