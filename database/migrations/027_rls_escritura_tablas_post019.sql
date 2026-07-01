-- =============================================================================
-- 027_rls_escritura_tablas_post019.sql
-- Completa el RLS de las tablas creadas DESPUÉS de la migración 019.
--
-- PROBLEMA QUE CORRIGE
--   La migración 019 creó las políticas de ESCRITURA (`_app_write`) solo para
--   las tablas que existían entonces. Las tablas creadas luego (021, 022, 023,
--   024, 025) quedaron con RLS activo pero SIN política de escritura, así que al
--   activar el cutover (LVCA_RLS=1) el cliente autenticado no puede insertar y
--   Postgres devuelve:
--       new row violates row-level security policy for table "<tabla>"
--   Ese es el error al Registrar ELISA (tabla elisa_microcistina_corridas).
--   La propia migración 021 ya lo había advertido (ver su nota "Nota RLS").
--
--   Además, elisa_microcistina_corridas y microcistina_reportes (021/022) nunca
--   recibieron política de LECTURA: con RLS activo, get_corrida() devolvía vacío,
--   la app creía que no había placa y forzaba un INSERT (justo lo bloqueado).
--
-- MODELO DE PERMISOS (igual que 019, vía app_rol_nivel())
--   administrador 5 · analista_lab 4 · tecnico_campo 3 · visualizador 2 · visitante 1
--     - Datos/reportes de laboratorio ....... analista_lab (>=4)
--     - Catálogo de taxonomía (referencia) .. administrador (>=5)
--   La LECTURA queda abierta a cualquier usuario autenticado (USING TRUE), igual
--   que en las tablas hermanas de 023/024/025.
--
-- Requiere haber aplicado 019 (define app_rol_nivel()). Es ADITIVA, IDEMPOTENTE
-- (DROP POLICY IF EXISTS) y SIN EFECTO mientras LVCA_RLS=0 (service_role omite
-- RLS). Al final hay un bloque de ROLLBACK comentado.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
--   (o: python -m scripts.apply_migration database/migrations/027_rls_escritura_tablas_post019.sql)
-- =============================================================================


-- ── Guard: la función de nivel de rol debe existir (la crea la migración 019) ─
DO $$
BEGIN
    IF to_regprocedure('public.app_rol_nivel()') IS NULL THEN
        RAISE EXCEPTION
            'Falta app_rol_nivel(): aplica primero database/migrations/019_rls_escritura_por_rol.sql';
    END IF;
END $$;


-- ── 1. Tablas sin NINGUNA política (021/022): habilitar RLS + lectura abierta ─
--     elisa_microcistina_corridas y microcistina_reportes se crearon sin RLS en
--     SQL; el RLS se activó luego desde el dashboard dejándolas sin políticas.
--     Se les da SELECT abierto a autenticados (como sus tablas hermanas).
DO $$
DECLARE
    t text;
    pol text;
BEGIN
    FOREACH t IN ARRAY ARRAY['elisa_microcistina_corridas', 'microcistina_reportes']
    LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
            pol := t || '_select';
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pol, t);
            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR SELECT USING (TRUE)', pol, t
            );
        END IF;
    END LOOP;
END $$;


-- ── 2. Políticas de ESCRITURA por tabla y nivel mínimo (patrón de 019) ────────
--     Una sola política FOR ALL por tabla cubre INSERT/UPDATE/DELETE; la lectura
--     no se toca (las políticas permisivas se combinan con OR).
DO $$
DECLARE
    r record;
    pol text;
BEGIN
    FOR r IN
        SELECT tabla, nivel FROM (VALUES
            -- Laboratorio / reportes de ensayo → analista_lab
            ('elisa_microcistina_corridas', 4),
            ('microcistina_reportes',        4),
            ('fitoplancton_reportes',        4),
            -- Distribución de informes (libreta + bitácora de envíos) → analista_lab
            ('contactos_informes',           4),
            ('informes_envios',              4),
            -- Catálogo de referencia (página admin) → administrador
            ('taxonomia_fitoplancton',       5)
        ) AS t(tabla, nivel)
    LOOP
        IF to_regclass('public.' || r.tabla) IS NOT NULL THEN
            pol := r.tabla || '_app_write';
            EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', pol, r.tabla);
            EXECUTE format(
                'CREATE POLICY %I ON public.%I FOR ALL '
                || 'USING (app_rol_nivel() >= %s) WITH CHECK (app_rol_nivel() >= %s)',
                pol, r.tabla, r.nivel, r.nivel
            );
        END IF;
    END LOOP;
END $$;


-- ── Verificación ─────────────────────────────────────────────────────────────
DO $$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n FROM pg_policies
    WHERE schemaname = 'public'
      AND policyname LIKE '%\_app\_write' ESCAPE '\'
      AND tablename IN (
          'elisa_microcistina_corridas', 'microcistina_reportes',
          'fitoplancton_reportes', 'contactos_informes',
          'informes_envios', 'taxonomia_fitoplancton'
      );
    IF n < 1 THEN
        RAISE EXCEPTION 'No se crearon políticas de escritura (¿tablas ausentes?)';
    END IF;
    RAISE NOTICE '✓ Migración 027: % políticas de escritura post-019 creadas', n;
END $$;


-- =============================================================================
-- ROLLBACK (descomentar y ejecutar para revertir SOLO lo de esta migración)
-- =============================================================================
-- DO $$
-- DECLARE p record;
-- BEGIN
--     FOR p IN
--         SELECT policyname, tablename FROM pg_policies
--         WHERE schemaname='public'
--           AND tablename IN (
--               'elisa_microcistina_corridas','microcistina_reportes',
--               'fitoplancton_reportes','contactos_informes',
--               'informes_envios','taxonomia_fitoplancton')
--           AND (policyname LIKE '%\_app\_write' ESCAPE '\'
--                OR policyname IN ('elisa_microcistina_corridas_select',
--                                  'microcistina_reportes_select'))
--     LOOP
--         EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', p.policyname, p.tablename);
--     END LOOP;
-- END $$;
