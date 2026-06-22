-- =============================================================================
-- 021: Ensayo ELISA de Microcistina LR (kit SAES/ABRAXIS, EPA Method 546)
--      Soporta el "motor ELISA" en la plataforma (reemplazo del SOLVER en Excel):
--      curva de calibración 4PL por corrida, control de calidad (QCS) y las
--      lecturas de absorbancia (OD) por duplicado de cada muestra.
--
-- Cálculo en services/elisa_microcistina.py (ajuste 4PL + concentración + %CV).
-- El reporte de ensayo se genera desde estos datos.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================


-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Corrida ELISA por campaña
--    Una corrida = una placa/curva de calibración. Para v1 se asume una corrida
--    por campaña (UNIQUE). Guarda la curva ajustada, el control y los criterios
--    de aceptación del QCS (configurables, precargados con los valores del kit).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS elisa_microcistina_corridas (
    id                  UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    campana_id          UUID NOT NULL UNIQUE REFERENCES campanas(id) ON DELETE CASCADE,

    -- Metadatos de la corrida
    codigo_reporte      TEXT,                          -- Ej. "LVCA - 001-MC-2026" (correlativo)
    fecha_ensayo        DATE,
    kit_lote            TEXT,                          -- Ej. "520011SAES" / "529911QL"
    factor_dilucion     NUMERIC NOT NULL DEFAULT 1.11, -- factor PN aplicado a muestras

    -- Curva de calibración: OD crudas de los 6 estándares por duplicado.
    -- JSONB: [[od1,od2], ...] en orden Std0(0), Std1(0.05) ... Std5(5.0 ug/L).
    std_od              JSONB,

    -- Parámetros 4PL ajustados (Y=(A-D)/(1+(X/C)^B)+D) y bondad de ajuste.
    param_a             NUMERIC,
    param_b             NUMERIC,
    param_c             NUMERIC,
    param_d             NUMERIC,
    r2                  NUMERIC,
    sse                 NUMERIC,

    -- Control de calidad (QCS): OD del control por duplicado + resultados.
    control_od_1        NUMERIC,
    control_od_2        NUMERIC,
    control_conc_1      NUMERIC,                       -- ug/L (calculada)
    control_conc_2      NUMERIC,                       -- ug/L (calculada)
    control_conc_prom   NUMERIC,                       -- ug/L (promedio)
    control_cv          NUMERIC,                       -- %CV sobre las OD del control

    -- Criterios de aceptación del QCS (configurables; default = kit actual).
    qcs_nominal         NUMERIC NOT NULL DEFAULT 0.750,  -- ug/L nominal del control
    qcs_tolerancia      NUMERIC NOT NULL DEFAULT 0.185,  -- +/- ug/L (0.565 - 0.935)
    cv_max              NUMERIC NOT NULL DEFAULT 15,      -- %CV máximo aceptable

    observaciones       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_elisa_corridas_campana
    ON elisa_microcistina_corridas(campana_id);

COMMENT ON TABLE elisa_microcistina_corridas IS
'Corrida ELISA de microcistina por campaña: curva 4PL ajustada, control de '
'calidad y criterios de aceptación. Una corrida por campaña (v1).';

COMMENT ON COLUMN elisa_microcistina_corridas.std_od IS
'OD crudas de los 6 estándares por duplicado: [[od1,od2],...] en orden '
'Std0(0)..Std5(5.0 ug/L). Concentraciones nominales en services/elisa_microcistina.py.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Lecturas OD por duplicado + %CV en cada resultado de laboratorio.
--    Aplica a microcistina (P091): valor_numerico guarda la concentración media
--    (ug/L, ya con factor); od_1/od_2 son las absorbancias y cv_pct el %CV.
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE resultados_laboratorio ADD COLUMN IF NOT EXISTS od_1   NUMERIC;
ALTER TABLE resultados_laboratorio ADD COLUMN IF NOT EXISTS od_2   NUMERIC;
ALTER TABLE resultados_laboratorio ADD COLUMN IF NOT EXISTS cv_pct NUMERIC;

COMMENT ON COLUMN resultados_laboratorio.od_1 IS
'Absorbancia (OD) réplica 1 — ensayos ELISA (microcistina). NULL en otros parámetros.';
COMMENT ON COLUMN resultados_laboratorio.cv_pct IS
'%CV de las dos OD (no de la concentración). Criterio fabricante <= 15%.';


-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Límites del método para Microcistina LR (P091), en su unidad (ug/L).
--    L.D.M = 0.016 ug/L (0.000016 mg/L); L.C.M = 0.05 ug/L (0.00005 mg/L).
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE parametros SET lmd = 0.016, lcm = 0.05 WHERE codigo = 'P091';


-- ─────────────────────────────────────────────────────────────────────────────
-- Nota RLS: al hacer el cutover a RLS (ver 019), agregar
-- 'elisa_microcistina_corridas' a la lista de tablas con política de escritura
-- por rol. Hoy la app escribe con service_role (omite RLS), igual que el resto.
-- ─────────────────────────────────────────────────────────────────────────────

-- Verificación
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = 'elisa_microcistina_corridas') THEN
        RAISE EXCEPTION 'Tabla elisa_microcistina_corridas no fue creada';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'resultados_laboratorio' AND column_name = 'cv_pct') THEN
        RAISE EXCEPTION 'resultados_laboratorio.cv_pct no fue creada';
    END IF;
    RAISE NOTICE '✓ Migración 021 ELISA microcistina aplicada';
END $$;
