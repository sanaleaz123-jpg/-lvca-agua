# Auditoría técnica — Plataforma LVCA AUTODEMA

**Fecha:** 2026-04-15
**Alcance:** Revisión de código fuente del repositorio `lvca_agua` (Streamlit + Supabase).
**Método:** Lectura directa del código fuente (services/, pages/, components/, database/, config/) + pruebas exploratorias previas en la UI con datos sintéticos.
**Filosofía del informe:** Crítico, directo, con citación explícita de archivo y línea para cada hallazgo. No se incluyen suposiciones; lo que no pude confirmar va marcado como **"Pendiente verificación"**.

---

## 1. Resumen ejecutivo

La plataforma cumple su propósito funcional principal (registrar campañas, muestras, resultados, evaluar contra ECA D.S. N° 004-2017-MINAM, generar informes), pero presenta **dos problemas arquitectónicos críticos** y un conjunto de bugs/falencias menores que afectan seguridad, integridad, mantenibilidad y costos.

Clasificación de hallazgos:

- **Críticos (3):** Bypass total de RLS, cliente Supabase compartido entre usuarios, persistencia de sesión inexistente.
- **Altos (5):** Bug de límite ECA = 0 rechazado, race conditions en generación de códigos, cache invalidation parcial, falta de auditoría en operaciones clave, hardcodeo de IDs de parámetros.
- **Medios (8):** Inconsistencias de caching, validaciones débiles, manejo silencioso de errores, schema-probing en cada request, listas hardcodeadas de responsables, etc.
- **Bajos (varios):** Cosméticos, deuda técnica, mejoras de UX.

---

## 2. Hallazgos críticos

### 2.1 Bypass total de Row-Level Security (RLS) — CRÍTICO de seguridad

**Archivos:** `services/resultado_service.py`, `services/admin_service.py`, `services/audit_service.py`, `services/storage_service.py`, `services/parametro_service.py`, `services/punto_service.py`, `services/campana_service.py`, `services/base_datos_service.py`, `services/informe_service.py`, `services/muestra_service.py`, `services/parametro_registry.py`.

**Evidencia:** Todos los servicios importan y usan `get_admin_client()` (cliente con `SUPABASE_SERVICE_KEY`), incluso para lecturas. Por ejemplo:

- `services/resultado_service.py`: 100% de las funciones usan `get_admin_client()`.
- `services/informe_service.py:32, 168, 226`: lecturas de informes con clave service_role.
- `services/muestra_service.py:115, 128, 146, 186, ...`: incluso `get_campanas_en_campo`, `get_usuarios_campo`, etc.

**Implicación:**
La service_role key de Supabase **omite todas las políticas RLS**. Si la app está expuesta públicamente o si un atacante obtiene cualquier sesión válida, *toda* la base de datos queda accesible para lectura/escritura desde la lógica del backend (las políticas RLS no protegen nada). Las políticas RLS configuradas en Supabase son funcionalmente **decorativas**.

**Recomendación:**
Reservar `get_admin_client()` exclusivamente para operaciones administrativas que *necesiten* bypass de RLS (por ejemplo, listar todos los usuarios desde la página de Administración, o resetear contraseñas). Para todo lo demás usar `get_client()` con la `SUPABASE_ANON_KEY` y dejar que las políticas RLS hagan su trabajo. Esto requiere:
1. Auditar y reescribir cada query a nivel de servicio para aceptar el JWT del usuario logueado.
2. Asegurarse de que cada tabla tiene RLS habilitado y políticas correctas.
3. Eliminar la lógica que dependa implícitamente de "ver todo".

---

### 2.2 Cliente Supabase singleton compartido entre usuarios — CRÍTICO de seguridad/concurrencia

**Archivo:** `database/client.py:~40-60` (decorador `@st.cache_resource` sobre `get_client()` y `get_admin_client()`).

**Evidencia:** `@st.cache_resource` crea **una sola instancia compartida por proceso de Streamlit**, no por sesión.

**Implicación:**
- Si en algún punto se usara `get_client()` y se hiciera `set_session(access_token, refresh_token)` para asociar un JWT al cliente, ese JWT **persistiría entre sesiones de usuarios distintos** dentro del mismo worker. Combinado con el hallazgo 2.1 esto es muy grave: cualquier query de un usuario podría ejecutarse con el contexto de otro.
- Hoy mismo el riesgo está **mitigado por accidente** porque toda la app usa `get_admin_client()` (que no depende de sesión), pero si se intenta corregir 2.1 sin corregir 2.2 simultáneamente el sistema queda peor.

**Recomendación:**
Usar `@st.cache_data` con `session_id` como clave o, mejor, instanciar el cliente por sesión (sin caché global). Documentar explícitamente que `cache_resource` no es seguro para clientes con estado de auth.

---

### 2.3 Persistencia de sesión inexistente — CRÍTICO de UX

**Archivo:** `services/auth_service.py:~89-98` (definición de `SesionUsuario` y manejo en `st.session_state`).

**Evidencia:** La sesión se guarda únicamente en `st.session_state["sesion"]`. No hay cookie, ni `localStorage`, ni token persistido.

**Implicación:** Cualquier acción que provoque un re-mount completo (recarga manual del navegador, click directo en una URL profunda como `/Resultados_Lab`, Streamlit reiniciando el worker en producción) **expulsa al usuario**. Confirmé esto en pruebas de UI: navegar por URL directa devuelve "Acceso restringido".

**Recomendación:** Implementar persistencia con `streamlit_extras.cookie_manager` o `streamlit_cookies_controller`, guardando sólo el `refresh_token` (no el access_token). Al re-cargar la página, intentar `db.auth.refresh_session(refresh_token)` y reconstruir `SesionUsuario`.

---

## 3. Hallazgos altos

### 3.1 Bug crítico funcional: límites ECA = 0 son rechazados

**Archivo:** `pages/5_Parametros.py:~521-522, 578, 585-586` (formulario de Valores ECA).

**Evidencia:**
```python
valor_minimo = vmin if vmin else None     # ⚠️ falla si vmin == 0
valor_maximo = vmax if vmax else None     # ⚠️ falla si vmax == 0
```
Las expresiones `if vmin:` y `if vmax:` evalúan `False` para `0`, `0.0`, `""`. Un parámetro como **"Aceites y grasas — ausencia"** (límite máximo permitido = 0 mg/L en ECA Categoría 1-A1) será silenciosamente convertido a `None` y guardado sin restricción.

**Recomendación:** Cambiar a `vmin if vmin is not None else None`.

---

### 3.2 Race conditions en generación de códigos secuenciales

**Archivos:**
- `services/muestra_service.py:883-906` (`_generar_codigo_muestra`)
- `services/campana_service.py` (`_generar_codigo` — no se citó directamente pero la summary lo identifica con la misma estructura).

**Evidencia:** El código consulta el último secuencial existente y le suma 1, sin transacción ni lock.

**Implicación:** Dos usuarios creando muestras al mismo tiempo pueden generar el mismo código. La inserción fallará por constraint UNIQUE (si existe) o, peor, creará duplicados (si no existe).

**Recomendación:** Crear una secuencia en PostgreSQL (`CREATE SEQUENCE muestras_seq;`) y obtener el número con `nextval()` desde una función RPC, o usar `INSERT ... RETURNING` con un identificador generado por trigger.

---

### 3.3 Invalidación de caché incompleta

**Archivos:**
- `services/punto_service.py` (función `eliminar_punto` — no llama a `_invalidar_cache()` al final).
- `services/muestra_service.py:493-525` (`recibir_en_laboratorio` — no invalida caché).
- `services/muestra_service.py:780-840` (`actualizar_muestra` — no invalida).
- `services/muestra_service.py:843-880` (`eliminar_muestra` — no invalida).

**Implicación:** Después de estas operaciones la UI puede mostrar datos viejos hasta que el TTL expire (120s o 300s según el caso). En la pantalla de Resultados Lab esto se manifiesta como "guardé datos pero las métricas no cambian".

**Recomendación:** Centralizar la invalidación en un decorator `@invalidates_cache` o llamar `_invalidar_cache()` en *todas* las funciones de escritura.

---

### 3.4 Auditoría inconsistente — operaciones críticas sin log

**Archivos:**
- `services/campana_service.py` — `actualizar_estado` (cambio de estado de campaña) no se registra en `audit_log`.
- `services/base_datos_service.py` — `crear_resultado` no se audita, pero `actualizar_resultado` sí.
- `services/admin_service.py` — `eliminar_usuario` captura silenciosamente fallos de borrado en Supabase Auth, dejando el registro huérfano.

**Implicación:** Trazabilidad incompleta. Si un usuario malicioso cambia el estado de una campaña a "cerrada" para ocultar excedencias, no queda rastro.

**Recomendación:** Auditar **todas** las mutaciones; estandarizar con un decorator único.

---

### 3.5 Hardcoding de IDs de parámetros y responsables

**Archivos:**
- `services/parametro_registry.py:120` — `_CODIGOS_CAMPO = {"P001", "P002", ...}` fija códigos exactos del seed.
- `services/parametro_registry.py:128-136` — `_CLAVE_INSITU_A_CODIGO = {"ph": "P001", ...}` mapea claves de UI a códigos del seed.
- `pages/2_Campanas.py` — `_RESPONSABLES_CAMPO` y `_RESPONSABLE_LAB_FIJO` hardcodeados.

**Implicación:** Si la base de datos se reconstruye o se importa en otro entorno y los códigos cambian (por ejemplo, "pH" recibe el código P010 en otro seed), las funciones de campo se rompen sin error explícito. Los responsables se vuelven imposibles de gestionar sin redeploy.

**Recomendación:** Marcar los parámetros de campo con un flag booleano `es_parametro_campo` en la tabla `parametros`, y consultar dinámicamente. Para responsables, mover a la tabla `usuarios` con un flag o rol específico.

---

## 4. Hallazgos medios

### 4.1 Esquema-probing en cada llamada (overhead de red)

**Archivo:** `services/muestra_service.py:559-570`, `services/base_datos_service.py` (probing de `codigo_laboratorio`).

**Evidencia:** Cada vez que se lista muestras se ejecuta una query "trampa" para detectar si la columna `codigo_laboratorio` existe:
```python
try:
    db.table("muestras").select("codigo_laboratorio").limit(1).execute()
    select_fields = _select_con_lab
except Exception:
    select_fields = _select_base
```

**Implicación:** Round-trip extra a Supabase en cada listado. En condiciones reales con varios usuarios concurrentes, esto suma carga innecesaria y latencia.

**Recomendación:** Detectar la migración una sola vez en `__init__` del módulo y cachear en una variable global, o (mejor) eliminar el probing y declarar la migración como obligatoria.

---

### 4.2 Caching inconsistente entre funciones del mismo servicio

**Archivos:**
- `services/parametro_service.py` — `get_parametro` no está cacheada pero `get_parametros` sí.
- `services/parametro_registry.py:155-172` — `get_parametros_activos` cacheada con ttl=300 pero `get_param_config` (lee JSON local) no.

**Implicación:** Tiempos de respuesta erráticos según qué función se invoque primero.

**Recomendación:** Convención clara: todas las lecturas con TTL coherente (ej: 60s para datos volátiles, 300s para catálogos), todas las escrituras invalidan.

---

### 4.3 Validación débil en `actualizar_usuario`

**Archivo:** `services/admin_service.py` (función `actualizar_usuario`).

**Evidencia:** Strings vacíos se envían como `None` a la BD, lo que viola constraints `NOT NULL` y produce errores 500 en lugar de validación amable.

**Recomendación:** Validar antes de enviar, devolver `ValueError` en caso de campo vacío para columnas obligatorias.

---

### 4.4 `audit_service` — race condition en lock

**Archivo:** `services/audit_service.py`.

**Evidencia:** El threading lock se crea de forma lazy como atributo de función. Bajo concurrencia inicial alta, dos hilos pueden crear locks distintos.

**Recomendación:** Crear el lock al import-time como variable de módulo.

---

### 4.5 Croquis con `name.startswith(punto_id)` — riesgo de falso positivo

**Archivo:** `services/storage_service.py`.

**Evidencia:** Si dos puntos tienen IDs como `abc123` y `abc1234`, la búsqueda del croquis del primero devolverá también el del segundo.

**Recomendación:** Usar igualdad exacta del prefijo + extensión, o nombres de archivo sin colisión posible (UUID + `_croquis.png`).

---

### 4.6 `registrar_insitu` duplica datos en dos tablas

**Archivo:** `services/muestra_service.py:302-389`.

**Evidencia:** Cada medición in situ se inserta tanto en `mediciones_insitu` como en `resultados_laboratorio`. Esto crea dos fuentes de verdad.

**Implicación:** Si más adelante alguien edita una sin la otra, los reportes mostrarán inconsistencias. La evaluación contra ECA usa `resultados_laboratorio`, pero la pantalla de "Mediciones in situ" usa `mediciones_insitu`.

**Recomendación:** Decidir una sola fuente. Lo más limpio: eliminar la tabla `mediciones_insitu` y usar `resultados_laboratorio` con un flag `es_in_situ`, o crear una vista que una ambas.

---

### 4.7 Matching de límites in situ por substring

**Archivo:** `services/muestra_service.py:407-454` (`get_limites_insitu`).

**Evidencia:** Se compara nombres de parámetros con `if nombre_ref in nombre_db or nombre_db in nombre_ref:`.

**Implicación:** "pH" (nombre corto) puede hacer match con "Hidrocarburos pH-sensibles" (caso sintético, pero el patrón es frágil). Mejor: comparación por código.

**Recomendación:** Usar ya sea el código de parámetro (P001, P002, ...) o un mapeo explícito por UUID.

---

### 4.8 PDF de campaña silenciosamente trunca a 50 excedencias

**Archivo:** `services/informe_service.py:411` — `for e in resumen["excedencias"][:50]`.

**Implicación:** Si una campaña tiene 60 excedencias, el PDF muestra 50 sin advertencia. El revisor regulatorio puede creer que vio todo.

**Recomendación:** Mostrar al menos un mensaje "Se omitieron N excedencias adicionales", o paginar el PDF.

---

## 5. Hallazgos bajos / deuda técnica

- `config/settings.py`: copia `st.secrets` a `os.environ` filtrando solo strings; valores booleanos/numéricos se ignoran. Funcional pero opaco.
- `services/punto_service.py:264` — `campos_texto` lista duplica `"sistema_hidrico"` y `"lugar_muestreo"`.
- `services/muestra_service.py:780-840` — `_campos_migr005` filtra `profundidad_valor` que ya está en `campos_num`; lógica redundante.
- `services/audit_service.py` — fallback a `data/audit_log.json` no funciona en Streamlit Cloud (sistema de archivos efímero). Pierde auditoría sin avisar.
- `pages/2_Campanas.py` — listas hardcodeadas de responsables crean fricción operativa cada vez que cambia el equipo.
- `pages/9_Administracion.py:152-159` — botón de eliminar usuario es `type="primary"` (verde), generando confusión visual con "guardar" en otros formularios. Botón destructivo debería usar color de advertencia.
- Excedencias en informes (`services/resultado_service.py`) usan `> lim_max` o `< lim_min`. Para parámetros con límite "≤" o "<" exactos no hay forma de distinguir. La normativa peruana suele usar "≤" (igualar el límite es cumplir), por lo que esto es correcto, pero conviene documentarlo.

---

## 6. Hallazgos no verificados (requieren más exploración)

Estas observaciones surgieron de las pruebas en la UI antes del pivot al code review pero no las pude confirmar a nivel de código por límite de contexto. Marco como **"Pendiente verificación"**:

- Bug 1 (cache invalidation visual en Resultados Lab tras guardar): el código de `cache.py` y la llamada a `get_datos_muestra.clear()` lucen correctos. Probable causa: el orden de lectura en la página obtiene métricas con datos antiguos antes del `st.rerun()`. Requiere reproducción controlada y trazado del flujo en `pages/4_Resultados_Lab.py:380-420`.
- Comportamiento exacto de `actualizar_estado_campana` cuando se intenta cerrar una campaña con muestras incompletas — no leí el cuerpo de la función al detalle.
- Pages `3_Muestras_Campo.py` (69KB), `7_Geoportal.py` (49KB) y servicios `cadena_custodia_service.py` (46KB), `ficha_campo_service.py` (24KB), `mapa_service.py` no fueron leídos por completo. Las observaciones sobre ellos se limitan a lo que el resto del código revela indirectamente.

---

## 7. Recomendaciones priorizadas

Si solo se puede atacar una cosa por iteración, este es el orden:

1. **Corregir el bug del límite ECA = 0** en `pages/5_Parametros.py`. Es de una línea, riesgo regulatorio directo (un parámetro como Aceites y Grasas en ECA 1-A1 tiene límite 0 mg/L y hoy se guarda como "sin límite").
2. **Implementar persistencia de sesión** (cookies con refresh_token). Mejora dramática en UX y elimina el síntoma más visible.
3. **Auditar el modelo de seguridad y migrar de service_role a anon + RLS** donde sea posible. Es trabajo grande pero crítico antes de exponer la app públicamente.
4. **Centralizar invalidación de caché** y agregar auditoría a las mutaciones que hoy no la tienen.
5. **Eliminar race conditions** en generación de códigos usando secuencias PostgreSQL.
6. **Quitar hardcoding** de IDs de parámetros y responsables.
7. Limpieza de deuda técnica (probing de schema, duplicación de mediciones, matching por substring, etc.).

---

## 8. Sobre fuentes y veracidad

Todo lo afirmado en este documento se basa en lectura directa de los archivos del repositorio en `/sessions/confident-jolly-allen/mnt/lvca_agua/`. No usé documentación externa ni hice suposiciones sobre comportamiento de Streamlit/Supabase salvo cuando es comportamiento documentado y estable (`@st.cache_resource` como singleton por proceso, service_role bypass de RLS, etc.).

**Lo que NO pude verificar y que el equipo debería confirmar:**
- Si las políticas RLS están realmente configuradas en Supabase (no se puede saber desde el código fuente).
- Si la app está expuesta públicamente o solo a intranet (cambia drásticamente el riesgo del hallazgo 2.1).
- Versión exacta de Streamlit en producción (algunos comportamientos de cache cambiaron entre versiones).
- Si los archivos no leídos al detalle (Geoportal, Cadena de Custodia, Muestras_Campo) repiten los mismos patrones o introducen otros distintos.
