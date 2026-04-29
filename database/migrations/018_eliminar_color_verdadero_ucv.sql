-- =============================================================================
-- 018: Eliminar el parámetro duplicado "Color verdadero" con unidad UCV (P011)
--
-- Estado actual:
--   La tabla parametros tiene DOS filas para "Color verdadero":
--     P010  Color verdadero  unidad: U Pt-Co  método: STANDARD METHODS
--     P011  Color verdadero  unidad: UCV      método: SM 2120 C espectrofotométrico
--
-- Decisión funcional: el ECA del DS 004-2017-MINAM expresa Color verdadero en
-- Unidades de Platino-Cobalto (Pt/Co), por lo tanto P010 (U Pt-Co) es la
-- versión que se conserva. P011 (UCV) se elimina para evitar el duplicado.
--
-- Seguridad: si P011 ya tiene resultados de laboratorio cargados en alguna
-- muestra la migración aborta — borrar destruiría datos históricos. En ese
-- caso primero hay que migrar manualmente esos resultados a P010 antes de
-- volver a ejecutar esta migración.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================

DO $$
DECLARE
    p011_id      UUID;
    p010_id      UUID;
    n_resultados INT;
    n_ecas       INT;
    n_excs       INT;
BEGIN
    SELECT id INTO p011_id FROM parametros WHERE codigo = 'P011';
    SELECT id INTO p010_id FROM parametros WHERE codigo = 'P010';

    IF p010_id IS NOT NULL THEN
        UPDATE parametros SET activo = true WHERE id = p010_id;
        RAISE NOTICE 'P010 (Color verdadero, U Pt-Co) activado.';
    ELSE
        RAISE NOTICE 'P010 no existe — se creará al ejecutar el seed (seed_parametros.py).';
    END IF;

    IF p011_id IS NULL THEN
        RAISE NOTICE 'P011 ya no existe en BD — no hay nada que eliminar.';
        RETURN;
    END IF;

    SELECT COUNT(*) INTO n_resultados
        FROM resultados_laboratorio WHERE parametro_id = p011_id;
    SELECT COUNT(*) INTO n_ecas
        FROM eca_valores WHERE parametro_id = p011_id;

    -- Excepciones Art. 6 referencian parametros (migración 013).
    BEGIN
        SELECT COUNT(*) INTO n_excs
            FROM excepciones_art6 WHERE parametro_id = p011_id;
    EXCEPTION WHEN undefined_table THEN
        n_excs := 0;
    END;

    IF n_resultados > 0 THEN
        RAISE EXCEPTION
            'P011 tiene % resultado(s) de laboratorio asociado(s). '
            'Migra esos resultados a P010 antes de volver a ejecutar esta migración. '
            'SQL sugerido (revisar antes de ejecutar): '
            'UPDATE resultados_laboratorio SET parametro_id = ''%s'' '
            'WHERE parametro_id = ''%s'';',
            n_resultados, p010_id, p011_id;
    END IF;

    -- Migrar los valores ECA de P011 a P010 (si P010 existe y la fila destino
    -- todavía no tiene un valor para ese ECA → la trasladamos; si ya hay uno,
    -- se mantiene el de P010 y la duplicada de P011 se borra).
    IF p010_id IS NOT NULL THEN
        UPDATE eca_valores ev
        SET parametro_id = p010_id
        WHERE ev.parametro_id = p011_id
        AND NOT EXISTS (
            SELECT 1 FROM eca_valores ev2
            WHERE ev2.parametro_id = p010_id AND ev2.eca_id = ev.eca_id
        );
        RAISE NOTICE 'Valores ECA migrados de P011 a P010 cuando no había duplicado.';
    END IF;

    -- Sin resultados — seguro borrar las dependencias restantes y la fila.
    DELETE FROM eca_valores      WHERE parametro_id = p011_id;
    BEGIN
        DELETE FROM excepciones_art6 WHERE parametro_id = p011_id;
    EXCEPTION WHEN undefined_table THEN
        NULL;
    END;
    DELETE FROM parametros       WHERE id = p011_id;

    RAISE NOTICE
        'P011 eliminado (había % valor(es) ECA originales y % excepción(es)). '
        'P010 queda como única fila Color verdadero.', n_ecas, n_excs;
END $$;
