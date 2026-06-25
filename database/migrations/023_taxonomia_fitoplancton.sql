-- =============================================================================
-- 023: Catálogo de taxonomía de fitoplancton (gestionable desde la app)
--
--      Mueve la taxonomía (antes constante en código,
--      services/fitoplancton_service.TAXONOMIA_FITOPLANCTON) a una tabla, y le
--      añade la jerarquía completa División / Clase / Orden / Familia que el
--      Reporte de Ensayo de fitoplancton necesita mostrar.
--
--      Las especies nuevas se agregan desde pages/11_Catalogo_Fitoplancton.py
--      con verificación contra AlgaeBase (API con clave) o GBIF (respaldo libre);
--      la clasificación verificada y su clave de origen se guardan aquí.
--
--      Compatibilidad: services/taxonomia_fitoplancton_service.get_taxonomia()
--      reconstruye el mismo shape {division: [ {nombre, unidad, ...}, ... ]} que
--      consumían fitoplancton_service, reporte_hidrobiologico_service y
--      components/fitoplancton_form, por lo que el resto del código no cambia de
--      contrato.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
--              (o: python -m scripts.apply_migration database/migrations/023_taxonomia_fitoplancton.sql)
-- =============================================================================

CREATE TABLE IF NOT EXISTS taxonomia_fitoplancton (
    id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    -- Jerarquía taxonómica. `division` = filo (clave de TAXONOMIA_FITOPLANCTON).
    division             TEXT NOT NULL,
    clase                TEXT,
    orden                TEXT,
    familia              TEXT,
    -- `especie` es el nombre mostrado/identificador del método (con "sp.").
    especie              TEXT NOT NULL UNIQUE,
    -- Metadatos de conteo (idénticos a los de la constante original).
    unidad               TEXT NOT NULL DEFAULT 'celula'
                             CHECK (unidad IN ('celula', 'colonia', 'filamento')),
    celulas_por_unidad   INTEGER NOT NULL DEFAULT 1 CHECK (celulas_por_unidad >= 1),
    volumen_celula_um3   NUMERIC NOT NULL DEFAULT 0 CHECK (volumen_celula_um3 >= 0),
    -- Trazabilidad de la verificación taxonómica.
    algaebase_id         TEXT,
    gbif_key             BIGINT,
    fuente_verificacion  TEXT,           -- 'algaebase' | 'gbif' | 'manual' | 'seed'
    -- Orden de presentación dentro del filo (para conservar el orden del lab).
    orden_visual         INTEGER NOT NULL DEFAULT 0,
    activo               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE taxonomia_fitoplancton IS
    'Catálogo de taxones de fitoplancton del método de conteo (Sedgewick-Rafter / Utermöhl). Jerarquía verificada contra AlgaeBase/GBIF. Reemplaza la constante TAXONOMIA_FITOPLANCTON.';

-- Búsqueda y agrupación por filo (la UI y el reporte iteran por division).
CREATE INDEX IF NOT EXISTS idx_taxonomia_fito_division
    ON taxonomia_fitoplancton (division);
CREATE INDEX IF NOT EXISTS idx_taxonomia_fito_activo
    ON taxonomia_fitoplancton (activo);

-- updated_at automático (misma función compartida del schema base).
CREATE OR REPLACE TRIGGER set_updated_at_taxonomia_fito
    BEFORE UPDATE ON taxonomia_fitoplancton
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- RLS: lectura para autenticados; escritura por service_role / rol admin
-- (sigue la convención de la migración 019). Lectura abierta a authenticated.
ALTER TABLE taxonomia_fitoplancton ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS taxonomia_fito_select ON taxonomia_fitoplancton;
CREATE POLICY taxonomia_fito_select
    ON taxonomia_fitoplancton FOR SELECT
    USING (TRUE);
