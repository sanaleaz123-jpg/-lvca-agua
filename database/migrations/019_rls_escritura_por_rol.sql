-- =============================================================================
-- 019_rls_escritura_por_rol.sql
-- Completa el RLS: políticas de ESCRITURA (INSERT/UPDATE/DELETE) por rol.
--
-- CONTEXTO
--   schema.sql ya habilita RLS y define políticas de LECTURA (authenticated).
--   Las ESCRITURAS hoy van por el cliente service_role, que OMITE RLS. Esta
--   migración agrega las políticas de escritura por rol para poder migrar la
--   app al cliente autenticado del usuario (defensa en profundidad).
--
-- SEGURIDAD DE APLICACIÓN (producción)
--   Es ADITIVA y SIN EFECTO mientras la app siga usando service_role:
--   service_role ignora RLS, así que aplicar esto NO cambia el comportamiento
--   actual. Activa la protección solo cuando el código pase al cliente de
--   usuario (ver runbook 019). Es idempotente (se puede reaplicar) y
--   reversible (al final hay un bloque de ROLLBACK comentado).
--
-- MODELO DE PERMISOS (por rol, según ROL_JERARQUIA de la app)
--   administrador 5 · analista_lab 4 · tecnico_campo 3 · visualizador 2 · visitante 1
--     - Configuración / referencia ...... escribe administrador (>=5)
--     - Campañas / muestras / in-situ ... escribe tecnico_campo (>=3)
--     - Resultados de laboratorio ....... escribe analista_lab (>=4)
--     - audit_log ....................... INSERT por cualquier autenticado
--   La LECTURA permanece abierta a cualquier usuario autenticado (sin cambios).
-- =============================================================================

-- ── Helper: nivel jerárquico del usuario actual ──────────────────────────────
-- SECURITY DEFINER para poder leer `usuarios` sin disparar el RLS de esa misma
-- tabla (evita recursión en sus propias políticas). STABLE: un valor por query.
CREATE OR REPLACE FUNCTION app_rol_nivel()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT COALESCE((
        CASE (SELECT rol FROM usuarios WHERE auth_id = auth.uid() LIMIT 1)
            WHEN 'administrador' THEN 5
            WHEN 'analista_lab'  THEN 4
            WHEN 'tecnico_campo' THEN 3
            WHEN 'visualizador'  THEN 2
            WHEN 'visitante'     THEN 1
            ELSE 0
        END
    ), 0);
$$;

COMMENT ON FUNCTION app_rol_nivel() IS
    'Nivel jerárquico (0-5) del rol del usuario autenticado, leído de usuarios.rol.';


-- ── Políticas de escritura por tabla y nivel mínimo ──────────────────────────
-- Se crean de forma dinámica y guardada (solo si la tabla existe), idempotente
-- (DROP POLICY IF EXISTS). Una sola política FOR ALL por tabla cubre
-- INSERT/UPDATE/DELETE; la LECTURA no se toca (las políticas permisivas se
-- combinan con OR, así que las de SELECT existentes siguen mandando en lectura).
DO $$
DECLARE
    r record;
    pol text;
BEGIN
    FOR r IN
        SELECT tabla, nivel FROM (VALUES
            -- Configuración / referencia → administrador
            ('usuarios',                5),
            ('unidades_medida',         5),
            ('categorias_parametro',    5),
            ('parametros',              5),
            ('ecas',                    5),
            ('eca_valores',             5),
            ('eca_valores_matriciales', 5),
            ('puntos_muestreo',         5),
            ('cadena_custodia_config',  5),
            ('equipos_medicion',        5),
            ('linea_base_temperatura',  5),
            ('excepciones_art6',        5),
            -- Operativo de campo → tecnico_campo
            ('campanas',                3),
            ('campana_puntos',          3),
            ('muestras',                3),
            ('mediciones_insitu',       3),
            -- Laboratorio → analista_lab
            ('resultados_laboratorio',  4)
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


-- ── audit_log: INSERT por cualquier usuario autenticado, sin update/delete ────
-- (La app registra auditoría en nombre de la acción del usuario. La lectura ya
--  está cubierta por audit_log_select de la migración 004.)
DO $$
BEGIN
    IF to_regclass('public.audit_log') IS NOT NULL THEN
        DROP POLICY IF EXISTS audit_log_app_insert ON public.audit_log;
        CREATE POLICY audit_log_app_insert ON public.audit_log
            FOR INSERT WITH CHECK (auth.role() = 'authenticated');
    END IF;
END $$;


-- ── Verificación ─────────────────────────────────────────────────────────────
DO $$
DECLARE
    n integer;
BEGIN
    SELECT count(*) INTO n FROM pg_policies
    WHERE schemaname = 'public' AND policyname LIKE '%\_app\_write' ESCAPE '\';
    RAISE NOTICE '✓ Políticas de escritura por rol creadas: %', n;
END $$;


-- =============================================================================
-- ROLLBACK (descomentar y ejecutar para revertir)
-- =============================================================================
-- DO $$
-- DECLARE p record;
-- BEGIN
--     FOR p IN
--         SELECT policyname, tablename FROM pg_policies
--         WHERE schemaname='public'
--           AND (policyname LIKE '%\_app\_write' ESCAPE '\'
--                OR policyname = 'audit_log_app_insert')
--     LOOP
--         EXECUTE format('DROP POLICY IF EXISTS %I ON public.%I', p.policyname, p.tablename);
--     END LOOP;
-- END $$;
-- DROP FUNCTION IF EXISTS app_rol_nivel();
