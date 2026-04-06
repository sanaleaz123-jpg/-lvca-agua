-- Migración: desactivar parámetros no utilizados por AUTODEMA
-- Ejecutar en Supabase > SQL Editor

-- 1. Desactivar TODOS los parámetros primero
UPDATE parametros SET activo = false;

-- 2. Activar solo los que sí se usan
UPDATE parametros SET activo = true WHERE codigo IN (
    -- CAMPO (in situ)
    'P001',  -- pH
    'P002',  -- Temperatura del agua
    'P003',  -- Conductividad eléctrica
    'P004',  -- Oxígeno disuelto
    'P006',  -- Turbidez
    'P033',  -- Nitrógeno amoniacal / Amonio (campo y lab)

    -- FISICOQUÍMICO (laboratorio)
    'P011',  -- Color verdadero
    'P019',  -- DBO5
    'P025',  -- Dureza total
    'P028',  -- SST
    'P031',  -- Nitratos
    'P032',  -- Nitritos
    'P036',  -- Fósforo total
    'P038',  -- Fosfatos totales
    'P041',  -- Sulfatos
    'P042',  -- Cloruros
    'P074',  -- Hierro total
    'P077',  -- Manganeso total
    'P124',  -- Clorofila A

    -- HIDROBIOLÓGICO
    'P120',  -- Fitoplancton
    'P126',  -- Zooplancton
    'P130'   -- Perifiton
);

-- 3. Agregar Microcistina LR si no existe (verificar primero en parametros)
-- Primero necesitamos el id de la categoría Fisicoquimico y unidad ug/L:
DO $$
DECLARE
    cat_id  UUID;
    unid_id UUID;
BEGIN
    SELECT id INTO cat_id  FROM categorias_parametro WHERE nombre = 'Fisicoquimico' LIMIT 1;
    SELECT id INTO unid_id FROM unidades_medida        WHERE simbolo = 'ug/L'        LIMIT 1;

    -- Si no existe la unidad ug/L, crearla
    IF unid_id IS NULL THEN
        INSERT INTO unidades_medida (simbolo, nombre)
        VALUES ('ug/L', 'Microgramos por litro')
        RETURNING id INTO unid_id;
    END IF;

    -- Insertar Microcistina LR solo si no existe
    IF NOT EXISTS (SELECT 1 FROM parametros WHERE codigo = 'P091') THEN
        INSERT INTO parametros (codigo, nombre, descripcion, categoria_id, unidad_id, metodo_analitico, activo)
        VALUES (
            'P091',
            'Microcistina LR',
            'Cianotoxina producida por cianobacterias, indicador de floraciones algales',
            cat_id,
            unid_id,
            'ELISA o HPLC-MS/MS',
            true
        );
    ELSE
        UPDATE parametros SET activo = true WHERE codigo = 'P091';
    END IF;
END $$;
