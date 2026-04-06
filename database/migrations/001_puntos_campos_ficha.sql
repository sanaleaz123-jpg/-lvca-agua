-- Migración: agregar campos de ficha de campo a puntos_muestreo
-- Ejecutar en Supabase > SQL Editor

ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS departamento      TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS provincia         TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS distrito          TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS accesibilidad     TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS representatividad TEXT;
ALTER TABLE puntos_muestreo ADD COLUMN IF NOT EXISTS finalidad         TEXT;
