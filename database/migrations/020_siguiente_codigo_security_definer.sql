-- =============================================================================
-- 020_siguiente_codigo_security_definer.sql
-- Hace que siguiente_codigo() funcione bajo RLS (cliente autenticado).
--
-- PROBLEMA
--   siguiente_codigo() crea secuencias (CREATE SEQUENCE) y usa nextval/setval.
--   Es SECURITY INVOKER (corre con los permisos de quien la llama). El rol
--   `authenticated` NO puede crear secuencias en el schema public, así que al
--   crear una campaña/muestra con un año/prefijo nuevo fallaría con "permission
--   denied" en cuanto la app use el cliente de usuario (RLS).
--
-- SOLUCIÓN
--   Recrear la función como SECURITY DEFINER (corre con los permisos del dueño,
--   que sí puede crear/usar secuencias) y otorgar EXECUTE a authenticated.
--   Es seguro: la función solo calcula correlativos, no expone datos.
--
-- SEGURIDAD DE APLICACIÓN
--   Aditiva y sin cambio de comportamiento mientras la app use service_role.
--   Idempotente (CREATE OR REPLACE + GRANT). Aplicar ANTES de activar RLS.
-- =============================================================================

CREATE OR REPLACE FUNCTION siguiente_codigo(p_tabla TEXT, p_prefijo TEXT, p_anio INT)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_seq_name TEXT;
    v_next     INT;
BEGIN
    -- Una secuencia por (tabla, prefijo, año). Se crea on-demand.
    v_seq_name := format('seq_%s_%s_%s', lower(p_tabla), lower(p_prefijo), p_anio);

    IF NOT EXISTS (
        SELECT 1 FROM pg_class
        WHERE relkind = 'S' AND relname = v_seq_name
    ) THEN
        EXECUTE format('CREATE SEQUENCE %I START 1', v_seq_name);

        -- Sincronizar con códigos existentes para no colisionar con datos previos
        EXECUTE format(
            'SELECT COALESCE(MAX(CAST(SPLIT_PART(codigo, %L, 3) AS INT)), 0)
             FROM %I
             WHERE codigo LIKE %L',
            '-', p_tabla, p_prefijo || '-' || p_anio || '-%'
        ) INTO v_next;

        IF v_next > 0 THEN
            EXECUTE format('SELECT setval(%L, %s)', v_seq_name, v_next);
        END IF;
    END IF;

    EXECUTE format('SELECT nextval(%L)', v_seq_name) INTO v_next;
    RETURN v_next;
END;
$$;

-- Permitir que los usuarios autenticados la ejecuten (la lógica corre como dueño).
GRANT EXECUTE ON FUNCTION siguiente_codigo(TEXT, TEXT, INT) TO authenticated;

DO $$
BEGIN
    RAISE NOTICE '✓ siguiente_codigo() ahora es SECURITY DEFINER y ejecutable por authenticated.';
END $$;

-- =============================================================================
-- ROLLBACK (descomentar para revertir a SECURITY INVOKER)
-- =============================================================================
-- Vuelve a aplicar la versión de la migración 006 (sin SECURITY DEFINER) y, si
-- quieres, revoca el permiso:
--   REVOKE EXECUTE ON FUNCTION siguiente_codigo(TEXT, TEXT, INT) FROM authenticated;
