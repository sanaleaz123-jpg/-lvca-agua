-- PASO 1: Agregar columnas faltantes a puntos_muestreo
-- Ejecutar en Supabase > SQL Editor

ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS departamento      TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS provincia         TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS distrito          TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS accesibilidad     TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS representatividad TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS finalidad         TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS sistema_hidrico   TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS lugar_muestreo    TEXT;
