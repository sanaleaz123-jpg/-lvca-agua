# Runbook — Completar RLS (migración 019)

Objetivo: que la app deje de operar con la llave `service_role` (que **omite
RLS**) y pase al **cliente autenticado del usuario**, con políticas de escritura
por rol como defensa en profundidad. Entorno: **solo producción** → se avanza en
fases aditivas, validando en cada paso, con rollback inmediato disponible.

## Estado actual (lo ya hecho en código)
- `database/migrations/019_rls_escritura_por_rol.sql` — helper `app_rol_nivel()`
  + políticas de escritura por rol. **Aditiva y sin efecto mientras se use
  service_role.**
- `database/client.py::get_user_client(access_token, refresh_token)` — cliente
  autenticado por usuario (no cacheado). **Aún no lo usa ningún servicio.**

Nada de lo anterior cambia el comportamiento de la app todavía.

---

## Fase 1 — Aplicar la migración 019 (seguro ahora)
1. Backup: en Supabase → Database → Backups, confirma respaldo reciente.
2. Ejecuta la migración. Opción A (recomendada): pega el contenido de
   `019_rls_escritura_por_rol.sql` en Supabase → SQL Editor y ejecútalo.
   Opción B (si tienes credenciales PostgreSQL en `.env`):
   `python -m scripts.apply_migration database/migrations/019_rls_escritura_por_rol.sql`
3. Verifica el aviso final `✓ Políticas de escritura por rol creadas: N`.
4. **Validación:** usa la app normalmente. NO debe cambiar nada (la app sigue
   en service_role). Si algo cambiara, ejecuta el bloque ROLLBACK del .sql.

> Por qué es seguro: `service_role` ignora RLS, así que las nuevas políticas no
> afectan ninguna lectura ni escritura actual. Solo quedan "listas".

---

## Fase 2 — Cutover del código (gradual, con interruptor)
La idea es introducir un **selector de cliente** controlado por una variable de
entorno `LVCA_RLS` (default `0` = comportamiento actual). Con `0` todo sigue
igual; con `1` la app usa el cliente del usuario y RLS entra en vigor. Si algo
falla en producción, se vuelve a `0` al instante (sin redeploy de código).

Pasos sugeridos:
1. Añadir un helper `get_db()` (en `database/client.py` o un módulo nuevo) que
   devuelva:
   - `get_user_client(sesion.access_token, sesion.refresh_token)` si `LVCA_RLS=1`
     y hay sesión, leyendo la sesión de `st.session_state["sesion"]`.
   - `get_admin_client()` en caso contrario (comportamiento actual).
2. Reemplazar `get_admin_client()` por `get_db()` en los servicios, **por
   módulos** (p. ej. primero `mapa_service` y lecturas del geoportal), no todo
   de golpe.
3. Mantener en `service_role` deliberadamente lo que debe seguir privilegiado:
   - `auth_service` (login) usa el cliente anónimo — no cambia.
   - `audit_service` puede seguir en service_role (la auditoría es del sistema).
   - seeds/scripts y operaciones de mantenimiento.
4. Validación por módulo con `LVCA_RLS=1` en una sesión de prueba por cada rol
   (admin, analista_lab, tecnico_campo, visualizador):
   - Lecturas: cada rol ve lo que debe.
   - Escrituras: cada rol puede guardar lo de su competencia y NO lo ajeno
     (p. ej. un visualizador no puede editar resultados).

### Checklist de validación de escritura por rol
| Rol           | Debe poder escribir                          | NO debe poder |
|---------------|----------------------------------------------|---------------|
| administrador | todo (config, campañas, muestras, resultados)| —             |
| analista_lab  | resultados_laboratorio                       | parámetros/ECAs/puntos |
| tecnico_campo | campañas, campana_puntos, muestras, in-situ  | resultados_laboratorio, config |
| visualizador  | nada                                         | cualquier escritura |

---

## Fase 3 — Endurecimiento (cuando Fase 2 esté validada)
- Quitar el selector y dejar el cliente de usuario como único camino de datos.
- Restringir `SUPABASE_SERVICE_KEY` a procesos de servidor/seed; idealmente que
  la app de Streamlit no la necesite salvo para audit/seeds.

---

## Rollback
- **DB:** ejecutar el bloque `ROLLBACK` comentado al final del .sql (elimina
  políticas `*_app_write`, `audit_log_app_insert` y la función `app_rol_nivel`).
- **Código:** poner `LVCA_RLS=0` (vuelve a service_role) — efecto inmediato.

## Riesgos conocidos
- Si un servicio escribe en una tabla **sin** política de escritura para el rol
  del usuario, la operación fallará bajo RLS. Por eso el cutover es por módulos y
  con checklist por rol.
- `get_user_client` no se cachea (un cliente por request): correcto para no
  mezclar identidades, con coste de creación pequeño.
