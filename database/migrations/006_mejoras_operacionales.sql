-- =============================================================================
-- 006: Mejoras operacionales — rangos físicos, validación, soft-delete,
--      secuencias atómicas, rol técnico, cualitativos, persistencia config
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. RANGOS FÍSICOS por parámetro (validación de entrada)
--    Estos NO son límites ECA — son cotas físicamente posibles.
--    Ej: pH ∈ [0,14], temperatura ∈ [-5, 100], conductividad ≥ 0.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS rango_min NUMERIC;
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS rango_max NUMERIC;

COMMENT ON COLUMN parametros.rango_min IS 'Cota física inferior aceptada (no es límite ECA)';
COMMENT ON COLUMN parametros.rango_max IS 'Cota física superior aceptada (no es límite ECA)';

-- Seeds: cotas físicas de los parámetros in-situ más comunes
UPDATE parametros SET rango_min = 0,    rango_max = 14    WHERE codigo = 'P001';  -- pH
UPDATE parametros SET rango_min = -5,   rango_max = 100   WHERE codigo = 'P002';  -- Temperatura °C
UPDATE parametros SET rango_min = 0,    rango_max = 100000 WHERE codigo = 'P003'; -- Conductividad µS/cm
UPDATE parametros SET rango_min = 0,    rango_max = 25    WHERE codigo = 'P004';  -- OD mg/L
UPDATE parametros SET rango_min = 0,    rango_max = 10000 WHERE codigo = 'P006';  -- Turbidez NTU
UPDATE parametros SET rango_min = 0,    rango_max = 100000 WHERE codigo = 'P008'; -- TDS mg/L
UPDATE parametros SET rango_min = -1000, rango_max = 1000 WHERE codigo = 'P009';  -- Potencial redox mV
UPDATE parametros SET rango_min = 0,    rango_max = 500   WHERE codigo = 'P011';  -- Color verdadero
-- El resto de parámetros no-negativos por defecto
UPDATE parametros SET rango_min = 0 WHERE rango_min IS NULL AND codigo NOT IN ('P002','P009');


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. ROL "tecnico_campo" — separar trabajo de campo de administración
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_rol_check;
ALTER TABLE usuarios ADD CONSTRAINT usuarios_rol_check
    CHECK (rol IN ('administrador', 'tecnico_campo', 'analista_lab', 'visualizador', 'visitante'));

COMMENT ON COLUMN usuarios.rol IS
    'administrador > analista_lab > tecnico_campo > visualizador > visitante';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. SOFT-DELETE para campañas — estado "archivada"
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE campanas DROP CONSTRAINT IF EXISTS campanas_estado_check;
ALTER TABLE campanas ADD CONSTRAINT campanas_estado_check
    CHECK (estado IN (
        'planificada','en_campo','en_laboratorio',
        'completada','anulada','archivada'
    ));

ALTER TABLE campanas ADD COLUMN IF NOT EXISTS archivada_at TIMESTAMPTZ;
ALTER TABLE campanas ADD COLUMN IF NOT EXISTS archivada_por UUID REFERENCES usuarios(id);
ALTER TABLE campanas ADD COLUMN IF NOT EXISTS motivo_archivado TEXT;

CREATE INDEX IF NOT EXISTS idx_campanas_estado ON campanas(estado);

COMMENT ON COLUMN campanas.archivada_at IS 'Fecha de archivado (soft-delete). NULL = no archivada.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. SECUENCIAS ATÓMICAS para códigos de campañas y muestras
--    Reemplaza el patrón "SELECT MAX + 1" sujeto a race conditions.
-- ─────────────────────────────────────────────────────────────────────────────

-- Función genérica: siguiente número correlativo por prefijo y año
CREATE OR REPLACE FUNCTION siguiente_codigo(p_tabla TEXT, p_prefijo TEXT, p_anio INT)
RETURNS INT
LANGUAGE plpgsql
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

COMMENT ON FUNCTION siguiente_codigo IS
    'Genera el siguiente correlativo atómico para (tabla, prefijo, año). Sin race conditions.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. VALIDACIÓN de resultados de laboratorio
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE resultados_laboratorio ADD COLUMN IF NOT EXISTS validado BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE resultados_laboratorio ADD COLUMN IF NOT EXISTS validado_por UUID REFERENCES usuarios(id);
ALTER TABLE resultados_laboratorio ADD COLUMN IF NOT EXISTS validado_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_resultados_validado ON resultados_laboratorio(validado);

COMMENT ON COLUMN resultados_laboratorio.validado IS
    'Resultado revisado y firmado por supervisor. Una vez validado, requiere desbloqueo para editar.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. CUALIFICADOR para resultados — manejo de "<LMD", "Ausencia", "Presencia"
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE resultados_laboratorio ADD COLUMN IF NOT EXISTS cualificador TEXT
    CHECK (cualificador IS NULL OR cualificador IN ('<LMD','<LCM','>LCM','Ausencia','Presencia','ND','Trazas'));

COMMENT ON COLUMN resultados_laboratorio.cualificador IS
    'Cualificador analítico: <LMD (limite deteccion), <LCM (limite cuantificacion), Ausencia, Presencia, ND, Trazas.';

-- Limites de detección y cuantificación por parámetro (referencial)
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS lmd NUMERIC;  -- Límite mínimo de detección
ALTER TABLE parametros ADD COLUMN IF NOT EXISTS lcm NUMERIC;  -- Límite mínimo de cuantificación

COMMENT ON COLUMN parametros.lmd IS 'Limite minimo de deteccion del metodo analitico';
COMMENT ON COLUMN parametros.lcm IS 'Limite minimo de cuantificacion del metodo analitico';


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. PERSISTENCIA de configuración de cadena de custodia por campaña
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cadena_custodia_config (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campana_id      UUID UNIQUE REFERENCES campanas(id) ON DELETE CASCADE,
    config          JSONB NOT NULL,                    -- urgencia, equipos, personal, observaciones, etc.
    actualizado_por UUID REFERENCES usuarios(id),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cadena_config_campana ON cadena_custodia_config(campana_id);

COMMENT ON TABLE cadena_custodia_config IS
    'Persiste configuración de cadena de custodia por campaña para no re-llenar cada vez';


-- ─────────────────────────────────────────────────────────────────────────────
-- 8. AMPLIAR audit_log para soportar tablas operacionales (campanas, muestras, resultados)
-- ─────────────────────────────────────────────────────────────────────────────
-- audit_log.accion ya soporta crear/editar/eliminar/desactivar/activar.
-- Agregamos 'cambio_estado' para transiciones de campaña/muestra y 'validar' para resultados.
ALTER TABLE audit_log DROP CONSTRAINT IF EXISTS audit_log_accion_check;
ALTER TABLE audit_log ADD CONSTRAINT audit_log_accion_check
    CHECK (accion IN ('crear','editar','eliminar','desactivar','activar',
                       'cambio_estado','validar','desvalidar','archivar','restaurar'));


-- ─────────────────────────────────────────────────────────────────────────────
-- VERIFICACIÓN
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='parametros' AND column_name='rango_min') THEN
        RAISE EXCEPTION 'parametros.rango_min no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='campanas' AND column_name='archivada_at') THEN
        RAISE EXCEPTION 'campanas.archivada_at no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='resultados_laboratorio' AND column_name='validado') THEN
        RAISE EXCEPTION 'resultados_laboratorio.validado no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_proc WHERE proname='siguiente_codigo') THEN
        RAISE EXCEPTION 'Funcion siguiente_codigo() no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name='cadena_custodia_config') THEN
        RAISE EXCEPTION 'Tabla cadena_custodia_config no fue creada';
    END IF;
    RAISE NOTICE 'Migracion 006 aplicada correctamente.';
END $$;
