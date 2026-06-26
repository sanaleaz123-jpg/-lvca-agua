-- =============================================================================
-- 026: Índices compuestos de rendimiento
--
--      El esquema base (database/schema.sql) ya tiene índices de una sola
--      columna en las claves más usadas:
--        muestras(campana_id), muestras(punto_muestreo_id),
--        muestras(fecha_muestreo), muestras(estado),
--        resultados_laboratorio(muestra_id), resultados_laboratorio(parametro_id),
--        resultados_laboratorio(fecha_analisis), y el UNIQUE(muestra_id,
--        parametro_id) que ya indexa esa combinación.
--
--      Esta migración añade SOLO los índices COMPUESTOS que faltan y que
--      coinciden con patrones de consulta reales de la app, para que sigan
--      siendo rápidos a medida que crecen los datos. Es idempotente
--      (CREATE INDEX IF NOT EXISTS) y no altera datos.
--
-- Ejecutar en: Supabase Dashboard > SQL Editor > New query
-- =============================================================================

-- 1. Cascada campaña → punto (filtro por AMBAS columnas a la vez).
--    Usado por resultado_service.get_muestras(campana_id, punto_id),
--    muestra_service.get_puntos_de_campana_activa y
--    base_datos_service.get_datos_consolidados.
CREATE INDEX IF NOT EXISTS idx_muestras_campana_punto
    ON muestras (campana_id, punto_muestreo_id);

-- 2. "Último valor de un parámetro en un rango de fechas" del Geoportal.
--    Usado por mapa_service.get_ultimo_valor_parametro_por_punto y
--    get_datos_mensuales_parametro (filtran por parametro_id y ordenan/filtran
--    por fecha_analisis).
CREATE INDEX IF NOT EXISTS idx_resultados_parametro_fecha
    ON resultados_laboratorio (parametro_id, fecha_analisis DESC);

-- Nota: tras crearlos, conviene correr ANALYZE para refrescar las estadísticas
-- del planificador (Supabase lo hace en segundo plano, pero es inmediato así):
ANALYZE muestras;
ANALYZE resultados_laboratorio;
