-- =============================================================================
-- LVCA AUTODEMA — Esquema completo para Supabase (PostgreSQL)
-- Gestión de Calidad de Agua · Cuenca Chili-Quilca · D.S. N° 004-2017-MINAM
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- Orden de creación respeta dependencias entre tablas.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. USUARIOS (perfiles vinculados a Supabase Auth)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS usuarios (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    auth_id         UUID UNIQUE,                          -- UUID de Supabase Auth (auth.users.id)
    nombre          TEXT NOT NULL DEFAULT '',
    apellido        TEXT NOT NULL DEFAULT '',
    rol             TEXT NOT NULL DEFAULT 'visitante'
                        CHECK (rol IN ('administrador', 'visualizador', 'visitante')),
    institucion     TEXT DEFAULT '',
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usuarios_auth_id ON usuarios(auth_id);
CREATE INDEX IF NOT EXISTS idx_usuarios_rol     ON usuarios(rol);

COMMENT ON TABLE usuarios IS 'Perfiles de usuario vinculados a Supabase Auth';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. UNIDADES DE MEDIDA (150 unidades — seed)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS unidades_medida (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    simbolo         TEXT NOT NULL UNIQUE,                  -- mg/L, pH, NTU, etc.
    nombre          TEXT NOT NULL,
    descripcion     TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE unidades_medida IS '150 unidades de medida para parámetros de calidad de agua';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. CATEGORÍAS DE PARÁMETRO (5 categorías — seed)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categorias_parametro (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    nombre          TEXT NOT NULL UNIQUE,                  -- Fisicoquimico, Metales, etc.
    descripcion     TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE categorias_parametro IS 'Fisicoquimico, Metales, Plaguicidas, Microbiologico, Hidrobiologico';


-- ─────────────────────────────────────────────────────────────────────────────
-- 4. PARÁMETROS (154 parámetros — seed)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS parametros (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    codigo          TEXT NOT NULL UNIQUE,                  -- P001, P002, ..., P154
    nombre          TEXT NOT NULL,
    categoria_id    UUID REFERENCES categorias_parametro(id),
    unidad_id       UUID REFERENCES unidades_medida(id),
    descripcion     TEXT,
    metodo_analitico TEXT,
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parametros_categoria ON parametros(categoria_id);
CREATE INDEX IF NOT EXISTS idx_parametros_activo    ON parametros(activo);

COMMENT ON TABLE parametros IS '154 parámetros de calidad de agua D.S. N° 004-2017-MINAM';


-- ─────────────────────────────────────────────────────────────────────────────
-- 5. ECAs — Estándares de Calidad Ambiental (6 ECAs — seed)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ecas (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    codigo          TEXT NOT NULL UNIQUE,                  -- ECA-C1A1, ECA-C4E2, etc.
    nombre          TEXT NOT NULL,
    descripcion     TEXT,
    categoria       TEXT,                                  -- Cat. 1, Cat. 3, Cat. 4
    subcategoria    TEXT,                                  -- A1, A2, D1, E1, E2, etc.
    norma_legal     TEXT DEFAULT 'D.S. N° 004-2017-MINAM',
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ecas IS 'Estándares de Calidad Ambiental para Agua — D.S. N° 004-2017-MINAM';


-- ─────────────────────────────────────────────────────────────────────────────
-- 6. VALORES LÍMITE ECA (~120 valores — seed)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eca_valores (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    eca_id          UUID NOT NULL REFERENCES ecas(id) ON DELETE CASCADE,
    parametro_id    UUID NOT NULL REFERENCES parametros(id) ON DELETE CASCADE,
    valor_minimo    NUMERIC(18,6),                        -- NULL si no hay límite inferior
    valor_maximo    NUMERIC(18,6),                        -- NULL si no hay límite superior
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(eca_id, parametro_id)
);

CREATE INDEX IF NOT EXISTS idx_eca_valores_eca    ON eca_valores(eca_id);
CREATE INDEX IF NOT EXISTS idx_eca_valores_param  ON eca_valores(parametro_id);

COMMENT ON TABLE eca_valores IS 'Valores límite por ECA y parámetro (valor_minimo y/o valor_maximo)';


-- ─────────────────────────────────────────────────────────────────────────────
-- 7. PUNTOS DE MUESTREO (12 puntos — seed)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS puntos_muestreo (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    codigo              TEXT NOT NULL UNIQUE,              -- PM-01 a PM-12
    nombre              TEXT NOT NULL,
    descripcion         TEXT,
    tipo                TEXT DEFAULT 'rio'
                            CHECK (tipo IN ('laguna', 'rio', 'canal')),
    utm_este            NUMERIC(12,2),
    utm_norte           NUMERIC(12,2),
    utm_zona            TEXT DEFAULT '19S',
    latitud             NUMERIC(12,8),                    -- WGS84 (calculado por pyproj)
    longitud            NUMERIC(12,8),                    -- WGS84
    altitud_msnm        NUMERIC(8,2),
    cuenca              TEXT,
    subcuenca           TEXT,
    eca_id              UUID REFERENCES ecas(id),
    entidad_responsable TEXT,
    activo              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_puntos_eca    ON puntos_muestreo(eca_id);
CREATE INDEX IF NOT EXISTS idx_puntos_activo ON puntos_muestreo(activo);

COMMENT ON TABLE puntos_muestreo IS '12 puntos de monitoreo AUTODEMA — Cuenca Chili-Quilca';

-- Campos adicionales para ficha de campo
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS departamento TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS provincia TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS distrito TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS accesibilidad TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS representatividad TEXT;


-- ─────────────────────────────────────────────────────────────────────────────
-- 8. CAMPAÑAS DE MONITOREO
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campanas (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    codigo                  TEXT NOT NULL UNIQUE,          -- CAMP-2025-001
    nombre                  TEXT NOT NULL,
    fecha_inicio            DATE NOT NULL,
    fecha_fin               DATE,
    frecuencia              TEXT DEFAULT 'mensual'
                                CHECK (frecuencia IN (
                                    'mensual','bimestral','trimestral',
                                    'semestral','anual','extraordinaria'
                                )),
    estado                  TEXT NOT NULL DEFAULT 'planificada'
                                CHECK (estado IN (
                                    'planificada','en_campo','en_laboratorio',
                                    'completada','anulada'
                                )),
    responsable_campo       TEXT,
    responsable_laboratorio TEXT,
    observaciones           TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_campanas_estado ON campanas(estado);
CREATE INDEX IF NOT EXISTS idx_campanas_fecha  ON campanas(fecha_inicio DESC);

COMMENT ON TABLE campanas IS 'Campañas de monitoreo de calidad de agua';


-- ─────────────────────────────────────────────────────────────────────────────
-- 9. CAMPANA_PUNTOS (relación N:M campañas ↔ puntos)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS campana_puntos (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campana_id          UUID NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    punto_muestreo_id   UUID NOT NULL REFERENCES puntos_muestreo(id) ON DELETE CASCADE,
    UNIQUE(campana_id, punto_muestreo_id)
);

CREATE INDEX IF NOT EXISTS idx_cp_campana ON campana_puntos(campana_id);
CREATE INDEX IF NOT EXISTS idx_cp_punto   ON campana_puntos(punto_muestreo_id);

COMMENT ON TABLE campana_puntos IS 'Puntos de muestreo incluidos en cada campaña';


-- ─────────────────────────────────────────────────────────────────────────────
-- 10. MUESTRAS DE CAMPO
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS muestras (
    id                      UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    codigo                  TEXT NOT NULL UNIQUE,          -- LVCA-2025-001
    campana_id              UUID NOT NULL REFERENCES campanas(id) ON DELETE CASCADE,
    punto_muestreo_id       UUID NOT NULL REFERENCES puntos_muestreo(id),

    -- Tipo y momento de recolección
    tipo_muestra            TEXT DEFAULT 'simple'
                                CHECK (tipo_muestra IN (
                                    'simple','compuesta','duplicada',
                                    'blanco_campo','blanco_viaje'
                                )),
    fecha_muestreo          DATE NOT NULL,
    hora_recoleccion        TEXT,                          -- HH:MM

    -- Personal
    tecnico_campo_id        UUID REFERENCES usuarios(id),

    -- Condiciones de campo
    clima                   TEXT,
    caudal_estimado         TEXT,                          -- Ej: "2.5 m3/s"
    nivel_agua              TEXT,                          -- Ej: "normal", "alto", "bajo"
    preservante             TEXT,
    temperatura_transporte  NUMERIC(5,2),                  -- °C
    observaciones_campo     TEXT,

    -- Estado y cadena de custodia
    estado                  TEXT NOT NULL DEFAULT 'recolectada'
                                CHECK (estado IN (
                                    'recolectada','en_transporte',
                                    'en_laboratorio','analizada'
                                )),

    -- Recepción en laboratorio
    receptor_lab_id         UUID REFERENCES usuarios(id),
    fecha_recepcion_lab     TIMESTAMPTZ,
    estado_frasco_recepcion TEXT
                                CHECK (estado_frasco_recepcion IS NULL OR
                                       estado_frasco_recepcion IN (
                                    'integro','fisura_leve','tapa_floja',
                                    'derrame_parcial','roto'
                                )),
    observaciones_recepcion TEXT,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_muestras_campana   ON muestras(campana_id);
CREATE INDEX IF NOT EXISTS idx_muestras_punto     ON muestras(punto_muestreo_id);
CREATE INDEX IF NOT EXISTS idx_muestras_fecha     ON muestras(fecha_muestreo DESC);
CREATE INDEX IF NOT EXISTS idx_muestras_estado    ON muestras(estado);

COMMENT ON TABLE muestras IS 'Muestras de campo con cadena de custodia';


-- ─────────────────────────────────────────────────────────────────────────────
-- 11. MEDICIONES IN SITU (parámetros medidos en campo)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS mediciones_insitu (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    muestra_id      UUID NOT NULL REFERENCES muestras(id) ON DELETE CASCADE,
    parametro       TEXT NOT NULL,                         -- ph, temperatura, conductividad, etc.
    valor           NUMERIC(18,6),
    unidad          TEXT,
    equipo          TEXT,
    numero_serie    TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(muestra_id, parametro)
);

CREATE INDEX IF NOT EXISTS idx_insitu_muestra ON mediciones_insitu(muestra_id);

COMMENT ON TABLE mediciones_insitu IS 'pH, temperatura, conductividad, OD, turbidez, TDS, salinidad medidos en campo';


-- ─────────────────────────────────────────────────────────────────────────────
-- 12. RESULTADOS DE LABORATORIO
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS resultados_laboratorio (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    muestra_id      UUID NOT NULL REFERENCES muestras(id) ON DELETE CASCADE,
    parametro_id    UUID NOT NULL REFERENCES parametros(id),
    valor_numerico  NUMERIC(18,6),                        -- resultado cuantitativo
    valor_texto     TEXT,                                  -- resultado cualitativo (Ausencia/Presencia)
    observaciones   TEXT,
    analista_id     UUID REFERENCES usuarios(id),
    fecha_analisis  DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(muestra_id, parametro_id)
);

CREATE INDEX IF NOT EXISTS idx_resultados_muestra    ON resultados_laboratorio(muestra_id);
CREATE INDEX IF NOT EXISTS idx_resultados_parametro  ON resultados_laboratorio(parametro_id);
CREATE INDEX IF NOT EXISTS idx_resultados_fecha      ON resultados_laboratorio(fecha_analisis DESC);
CREATE INDEX IF NOT EXISTS idx_resultados_analista   ON resultados_laboratorio(analista_id);

COMMENT ON TABLE resultados_laboratorio IS 'Resultados analíticos por muestra y parámetro';


-- =============================================================================
-- TRIGGERS: actualizar updated_at automáticamente
-- =============================================================================

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER set_updated_at_usuarios
    BEFORE UPDATE ON usuarios
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_campanas
    BEFORE UPDATE ON campanas
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_muestras
    BEFORE UPDATE ON muestras
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE OR REPLACE TRIGGER set_updated_at_resultados
    BEFORE UPDATE ON resultados_laboratorio
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- =============================================================================
-- ROW LEVEL SECURITY (RLS)
-- =============================================================================

-- Habilitar RLS en todas las tablas
ALTER TABLE usuarios               ENABLE ROW LEVEL SECURITY;
ALTER TABLE unidades_medida         ENABLE ROW LEVEL SECURITY;
ALTER TABLE categorias_parametro    ENABLE ROW LEVEL SECURITY;
ALTER TABLE parametros              ENABLE ROW LEVEL SECURITY;
ALTER TABLE ecas                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE eca_valores             ENABLE ROW LEVEL SECURITY;
ALTER TABLE puntos_muestreo         ENABLE ROW LEVEL SECURITY;
ALTER TABLE campanas                ENABLE ROW LEVEL SECURITY;
ALTER TABLE campana_puntos          ENABLE ROW LEVEL SECURITY;
ALTER TABLE muestras                ENABLE ROW LEVEL SECURITY;
ALTER TABLE mediciones_insitu       ENABLE ROW LEVEL SECURITY;
ALTER TABLE resultados_laboratorio  ENABLE ROW LEVEL SECURITY;

-- ── Políticas para usuarios ──────────────────────────────────────────────────
-- Los usuarios autenticados pueden leer su propio perfil
CREATE POLICY "usuarios_select_own" ON usuarios
    FOR SELECT USING (auth.uid() = auth_id);

-- Los usuarios autenticados pueden leer todos los perfiles (para selectores)
CREATE POLICY "usuarios_select_authenticated" ON usuarios
    FOR SELECT USING (auth.role() = 'authenticated');

-- ── Políticas de lectura pública para datos maestros ─────────────────────────
-- Cualquier usuario autenticado puede leer datos maestros
CREATE POLICY "unidades_select" ON unidades_medida
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "categorias_select" ON categorias_parametro
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "parametros_select" ON parametros
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "ecas_select" ON ecas
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "eca_valores_select" ON eca_valores
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "puntos_select" ON puntos_muestreo
    FOR SELECT USING (auth.role() = 'authenticated');

-- ── Políticas para datos operativos ──────────────────────────────────────────
CREATE POLICY "campanas_select" ON campanas
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "campana_puntos_select" ON campana_puntos
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "muestras_select" ON muestras
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "insitu_select" ON mediciones_insitu
    FOR SELECT USING (auth.role() = 'authenticated');

CREATE POLICY "resultados_select" ON resultados_laboratorio
    FOR SELECT USING (auth.role() = 'authenticated');

-- ── NOTA IMPORTANTE ──────────────────────────────────────────────────────────
-- La aplicación usa get_admin_client() (service_role key) para todas las
-- operaciones de escritura (INSERT/UPDATE/DELETE), lo que OMITE RLS.
-- Las políticas de SELECT protegen la lectura desde el cliente anon.
-- Si en el futuro se necesitan políticas de escritura más granulares,
-- agregar políticas INSERT/UPDATE por rol consultando la tabla usuarios.


-- =============================================================================
-- VERIFICACIÓN FINAL
-- =============================================================================
DO $$
DECLARE
    tablas TEXT[] := ARRAY[
        'usuarios', 'unidades_medida', 'categorias_parametro', 'parametros',
        'ecas', 'eca_valores', 'puntos_muestreo', 'campanas', 'campana_puntos',
        'muestras', 'mediciones_insitu', 'resultados_laboratorio'
    ];
    t TEXT;
BEGIN
    FOREACH t IN ARRAY tablas LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = t
        ) THEN
            RAISE EXCEPTION 'Tabla % no fue creada correctamente', t;
        END IF;
    END LOOP;
    RAISE NOTICE '✓ Las 12 tablas fueron creadas correctamente.';
END $$;
