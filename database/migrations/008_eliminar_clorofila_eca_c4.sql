-- =============================================================================
-- 008: Eliminar Clorofila A (P124) de ECA Cat 4 E1 y Cat 4 E2
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
--
-- CONTEXTO:
--   El D.S. N° 004-2017-MINAM (Anexo I) no define límite de Clorofila A
--   para las categorías:
--     - Cat 4 E1 (Conservación del ambiente acuático — Lagunas y lagos)
--     - Cat 4 E2 (Conservación del ambiente acuático — Ríos)
--
--   Sin embargo, en el seed histórico se incluyó una entrada para ECA-C4E1
--   con valor 8.0 ug/L como "referencia de estado mesotrófico" (criterio
--   limnológico, no normativo). Un seed aún más antiguo pudo haber tenido
--   0.008 ug/L (valor propio de Cat 1 A1) por confusión de escala.
--
--   Adoptamos interpretación estricta: SOLO mantenemos en eca_valores los
--   límites que el DS define explícitamente. Se elimina cualquier entrada
--   de Clorofila A en C4E1 y C4E2, independientemente del valor.
--
--   El seed Python (seed_ecas.py) también se actualizó en este mismo commit
--   para no reintroducir estas entradas en re-seeds futuros.
--
-- SEGURO:
--   - Idempotente: si no existe la entrada, el DELETE no hace nada.
--   - No afecta otras categorías (ej. si a futuro se agrega C1A1 con límite
--     de Clorofila A según el DS, esta migración no lo toca).
--   - No rompe integridad: ON DELETE CASCADE no aplica hacia arriba
--     (eca_valores es la "hoja" de la relación).
-- =============================================================================

-- 1) Eliminar entradas de Clorofila A en Cat 4 E1 y Cat 4 E2
DELETE FROM eca_valores
WHERE parametro_id = (SELECT id FROM parametros WHERE codigo = 'P124')
  AND eca_id IN (
      SELECT id FROM ecas WHERE codigo IN ('ECA-C4E1', 'ECA-C4E2')
  );

-- 2) Verificación
DO $$
DECLARE
    n_residuales INTEGER;
BEGIN
    SELECT COUNT(*) INTO n_residuales
    FROM eca_valores ev
    JOIN ecas       e ON e.id = ev.eca_id
    JOIN parametros p ON p.id = ev.parametro_id
    WHERE p.codigo = 'P124'
      AND e.codigo IN ('ECA-C4E1', 'ECA-C4E2');

    IF n_residuales > 0 THEN
        RAISE EXCEPTION
            'Quedan % entradas de Clorofila A en C4E1/C4E2 tras el DELETE',
            n_residuales;
    END IF;

    RAISE NOTICE 'Migración 008 aplicada. Clorofila A eliminada de ECA-C4E1 y ECA-C4E2.';
END $$;
