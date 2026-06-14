# PROMPT TÉCNICO COMPLETO — PLATAFORMA LVCA
# Para usar en Claude Code (VS Code)
# Fecha: 2026-04-20

---

## CONTEXTO DEL PROYECTO

Eres el desarrollador principal de la **PLATAFORMA LVCA**, aplicación web de vigilancia de calidad de agua del Laboratorio de Vigilancia de Calidad de Agua (LVCA) de PEIMS-AUTODEMA.

- **Stack**: Python 3.11 · Streamlit · Supabase (PostgreSQL) · python-docx · ReportLab · Folium/streamlit-folium · Plotly · Pandas
- **Deploy**: Streamlit Cloud — https://lvca-agua.streamlit.app
- **Idioma UI**: Español (Perú), sin excepción en ningún label, título, mensaje o placeholder
- **Normativa ECA**: D.S. N°004-2017-MINAM
- **Institución**: PEIMS / LVCA / AUTODEMA — Arequipa, Perú

Implementa los cambios en el orden indicado. Para cada modificación, muestra el código o SQL original antes de cambiarlo. No elimines funcionalidades operativas existentes. Haz commit semántico por cada bloque completado.

---

## PARTE 1 — CORRECCIONES CRÍTICAS (implementar primero)

### 1.1 Corregir unidad de Temperatura: "gC" → "°C"

Este error está en la base de datos (tabla de unidades o en el seed de la tabla `parametros`). Se propaga a: tab In situ, módulo Resultados, encabezado de columna en Base de Datos, y listado de Parámetros.

**Acción**:
```sql
-- Buscar en todas las tablas donde aparece la unidad
SELECT table_name, column_name 
FROM information_schema.columns 
WHERE table_schema = 'public';

-- Corregir en la tabla que corresponda (probablemente 'parametros' o 'unidades')
UPDATE parametros SET unidad = '°C' WHERE codigo = 'P002';
-- O si hay tabla separada de unidades:
UPDATE unidades SET simbolo = '°C' WHERE simbolo = 'gC';
```

Verificar que el cambio se refleje en todos los módulos sin necesidad de cambios en código Python.

---

### 1.2 Corregir límite ECA de Clorofila A para Categoría 4 E1

El parámetro Clorofila A tiene asignado ≤ 0.008 ug/L en Cat. 4 E1 (Lagunas y Lagos). Ese límite corresponde a Cat. 1 A1. Según el Anexo I del D.S. N°004-2017-MINAM, Cat. 4 E1 **no tiene límite definido** para Clorofila A.

```sql
-- Identificar el registro erróneo
SELECT * FROM eca_valores 
WHERE parametro_codigo = 'P-CloA' -- ajustar al código real
AND categoria_eca_id = (SELECT id FROM categorias_eca WHERE codigo = '4E1');

-- Eliminar o setear como NULL el límite incorrecto
UPDATE eca_valores 
SET limite_maximo = NULL, limite_minimo = NULL
WHERE parametro_codigo = 'P-CloA'
AND categoria_eca_id = (SELECT id FROM categorias_eca WHERE codigo = '4E1');
-- Alternativa: DELETE si el registro no debe existir
```

Verificar también Cat. 4 E2 (Ríos de Sierra) por el mismo problema.

---

### 1.3 Implementar generación de documentos en módulo Informes

**Estado actual**: El módulo Informes solo muestra una tabla de excedencias. No genera ningún archivo descargable.

**Implementar** en `pages/Informes.py`:

#### 1.3.1 Informe por campaña (DOCX con python-docx)

```python
def generar_informe_campana_docx(campana_id: str, datos: dict) -> bytes:
    """
    Genera el informe mensual LVCA en formato DOCX.
    Estructura obligatoria:
    1. Portada: logos PEIMS+LVCA, nombre campaña, fecha, responsables
    2. Tabla de excedencias ECA con semáforo de color
    3. Tabla consolidada de resultados por punto (matriz puntos x parámetros)
    4. Observaciones y conclusiones (campo editable antes de generar)
    
    Estilos:
    - Fuente: Arial 10pt para cuerpo, Arial 12pt bold para títulos de sección
    - Tablas: bordes negros 0.5pt, encabezados con fondo gris #D9D9D9
    - Sin colores decorativos salvo el semáforo ECA:
        Excede: fondo #FFCCCC texto rojo
        Cumple: fondo #CCFFCC texto verde
        Sin datos: sin fondo
    - Encabezado de página: "PEIMS / LVCA | Monitoreo Calidad de Agua | [Campaña]"
    - Pie de página: "Página X de Y | Fecha de generación: DD/MM/AAAA"
    """
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    import io
    
    doc = Document()
    # ... implementación completa
    
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
```

Agregar en la UI:
```python
# En pages/Informes.py, tab "Informe por campaña"
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    campana_sel = st.selectbox("Seleccionar campaña", campanas)
with col2:
    if st.button("📄 Generar DOCX", type="primary"):
        docx_bytes = generar_informe_campana_docx(campana_sel.id, datos)
        st.download_button(
            label="⬇️ Descargar Informe",
            data=docx_bytes,
            file_name=f"INF_MENSUAL_{campana_sel.codigo}_{fecha_hoy}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
```

#### 1.3.2 Informe por punto (PDF con ReportLab)

```python
def generar_ficha_punto_pdf(punto_codigo: str, periodo: dict) -> bytes:
    """
    Genera ficha técnica del punto de monitoreo en PDF.
    Contenido:
    1. Header: banda azul #1565C0 con logos y nombre
    2. Datos del punto: nombre, código, ECA, coordenadas, altitud
    3. Gráfico de tendencia del último año por parámetro (imagen embebida)
    4. Tabla histórica de resultados (últimas 6 campañas)
    5. Estado ECA con badge de color
    
    Usar ReportLab con platypus para layout tipo ficha.
    Tamaño A4, márgenes 2cm todos los lados.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    import io
    
    buffer = io.BytesIO()
    # ... implementación completa
    return buffer.getvalue()
```

---

## PARTE 2 — CORRECCIONES MEDIAS

### 2.1 Campo "Código Lab." en Base de Datos

El campo aparece como "None" en todas las muestras. 

**Opción A** (recomendada si no se usa actualmente): Ocultar la columna en la vista consulta:
```python
# En pages/BaseDatos.py, función de construcción de DataFrame
columnas_a_mostrar = [c for c in df.columns if c != 'codigo_laboratorio_externo']
st.dataframe(df[columnas_a_mostrar])
```

**Opción B** (si se va a usar): Agregar campo editable en Recepción en Lab:
```python
# En tab Recepción en Lab, agregar input por muestra:
codigo_lab = st.text_input(
    "Código de laboratorio externo (opcional)",
    placeholder="Ej: LAB-2026-0045",
    key=f"codigo_lab_{muestra_id}"
)
```

---

### 2.2 Supervisor/Jefe en Documento CC — corregir default

```python
# En pages/Muestras.py, tab Documento CC
# Buscar el usuario con rol supervisor/encargada del LVCA
def get_supervisor_default():
    response = supabase.table('usuarios')\
        .select('id, nombre, apellido')\
        .in_('rol', ['Supervisor', 'Encargado LVCA', 'Administrador'])\
        .eq('activo', True)\
        .execute()
    
    usuarios = response.data
    # Preferir a Ana Lucía Paz si existe
    for u in usuarios:
        if 'paz' in u.get('apellido', '').lower() or 'ana' in u.get('nombre', '').lower():
            return f"{u['nombre']} {u['apellido']}"
    # Fallback al primer supervisor
    if usuarios:
        return f"{usuarios[0]['nombre']} {usuarios[0]['apellido']}"
    return "Ing. Ana Lucía Paz Alcázar"  # valor hardcodeado como último recurso

supervisor_default = get_supervisor_default()
supervisor = st.selectbox("Supervisor/Jefe", opciones_usuarios, index=...)
```

---

### 2.3 Cuenca y Sistema Hídrico — convertir a dropdowns

```python
# En pages/Puntos.py, formulario Nuevo punto y Editar punto
CUENCAS_VALIDAS = [
    "Quilca-Chili-Vitor",
    "Colca-Camaná",
]
SISTEMAS_HIDRICOS_VALIDOS = [
    "Chili Regulado",
    "Colca Regulado",
]

cuenca = st.selectbox("Cuenca *", CUENCAS_VALIDAS)
sistema_hidrico = st.selectbox("Sistema Hídrico", SISTEMAS_HIDRICOS_VALIDOS)
```

También actualizar la query de puntos existentes para normalizar valores inconsistentes:
```sql
UPDATE puntos_muestreo 
SET cuenca = 'Quilca-Chili-Vitor'
WHERE cuenca IN ('Chili', 'Quilca-Chili', 'Quilca Chili Vitor');

UPDATE puntos_muestreo 
SET sistema_hidrico = 'Chili Regulado'
WHERE sistema_hidrico IN ('Chili regulado', 'chili regulado', 'Sistema Chili');
```

---

### 2.4 Crear usuarios del equipo LVCA

```sql
-- Primero verificar/crear los roles necesarios
INSERT INTO roles (nombre, descripcion, permisos) VALUES
('Solo lectura', 'Puede ver todos los módulos sin editar', '{"view": true, "edit": false, "create": false, "validate": false}'),
('Técnico', 'Registra muestras e ingresa mediciones in situ', '{"view": true, "edit": true, "create": true, "validate": false}'),
('Analista', 'Ingresa y edita resultados de laboratorio', '{"view": true, "edit": true, "create": true, "validate": false}'),
('Supervisor', 'Valida resultados y genera documentos oficiales', '{"view": true, "edit": true, "create": true, "validate": true}')
ON CONFLICT (nombre) DO NOTHING;

-- Crear usuarios del equipo
-- NOTA: Las contraseñas iniciales deben cambiarse en el primer login
-- Usar Supabase Auth para crear los usuarios de autenticación primero,
-- luego insertar en la tabla de perfil
INSERT INTO usuarios (auth_id, nombre, apellido, email, rol, institucion, activo) VALUES
('[UUID-ANA]',    'Ana Lucía',   'Paz Alcázar',     'alpazcazar@autodema.gob.pe', 'Supervisor', 'PEIMS / AUTODEMA', true),
('[UUID-ALF]',    'Alfonso',     'Torres Espirilla', 'atorrese@autodema.gob.pe',  'Técnico',    'PEIMS / AUTODEMA', true),
('[UUID-JP]',     'Jean Pierre', 'Madariaga',        'jpmadariaga@autodema.gob.pe','Analista',  'PEIMS / AUTODEMA', true),
('[UUID-MARIO]',  'Mario',       'Jucharo Layme',    'mjucharo@autodema.gob.pe',  'Solo lectura','PEIMS / AUTODEMA', true);

-- Actualizar usuario Adrian Llacho existente
UPDATE usuarios 
SET institucion = 'PEIMS / AUTODEMA'
WHERE email = 'sanaleaz123@gmail.com';
-- Cambiar email requiere actualizar también en Supabase Auth
```

---

### 2.5 Color verdadero duplicado en tabla ECA Cat. 1 A2

```sql
-- Verificar duplicados
SELECT * FROM eca_valores 
WHERE parametro_codigo LIKE '%color%' 
AND categoria_eca_id = (SELECT id FROM categorias_eca WHERE codigo = '1A2');

-- Consolidar en una sola entrada con unidad estándar U Pt-Co
-- Según DS 004-2017-MINAM Cat 1 A2: Color ≤ 20 U Pt-Co
DELETE FROM eca_valores 
WHERE parametro_codigo LIKE '%color%'
AND unidad = 'UCV'
AND categoria_eca_id = (SELECT id FROM categorias_eca WHERE codigo = '1A2');
```

---

## PARTE 3 — ORTOGRAFÍA Y NOMENCLATURA

### 3.1 Corregir tildes faltantes en títulos de página

Buscar en todo el proyecto con `grep -r "Administracion\|Parametros" --include="*.py"`:

```python
# Todos los st.title(), st.header(), st.subheader() afectados:
# "Administracion" → "Administración"
# "Parametros y ECAs" → "Parámetros y ECAs"
# "Parametros medidos en campo" → "Parámetros medidos en campo"
# Cualquier otra instancia sin tilde
```

### 3.2 Unificar "Perifiton" en toda la plataforma

```bash
# Buscar todas las instancias
grep -rn "Perifoton\|Perifiton\|perifoton\|perifiton" --include="*.py" --include="*.sql"
```

```sql
-- En BD
UPDATE parametros SET nombre = 'Perifiton' WHERE nombre ILIKE '%perifoton%';
UPDATE parametros SET nombre = 'Perifiton' WHERE nombre = 'Perifoton';
```

```python
# En código Python, reemplazar todos los strings
# "Perifoton" → "Perifiton" en labels, tabs, textos de UI
```

### 3.3 Subtítulo del Geoportal

```python
# En pages/Geoportal.py
st.caption("Monitoreo de Calidad de Agua — Sistemas Chili Regulado y Colca Regulado · AUTODEMA")
# Reemplazar cualquier variante de "Cuenca Chili-Quilca" que aparezca
```

---

## PARTE 4 — EQUIPOS EN IN SITU

### 4.1 Verificar y corregir selector de equipos

```python
# En pages/Muestras.py, tab In situ
# Verificar que la query trae equipos activos de la BD
def cargar_equipos():
    response = supabase.table('equipos')\
        .select('id, codigo_serie, nombre, parametros_medidos')\
        .eq('activo', True)\
        .execute()
    return response.data

equipos = cargar_equipos()
# Si equipos está vacío, verificar que existan en BD:
```

```sql
-- Verificar existencia
SELECT * FROM equipos WHERE activo = true;

-- Si no existen, insertar los equipos del LVCA
INSERT INTO equipos (codigo_serie, nombre, marca, modelo, parametros_medidos, activo) VALUES
('21G102303/N', 'YSI ProDSS', 'YSI', 'ProDSS', 
 ARRAY['pH', 'Temperatura', 'Conductividad', 'Oxígeno Disuelto', 'Salinidad', 'TDS'], true),
('9208180023', 'Turbidímetro Palintest', 'Palintest', 'Turbimeter 550', 
 ARRAY['Turbidez'], true)
ON CONFLICT (codigo_serie) DO UPDATE SET activo = true;
```

---

## PARTE 5 — REDISEÑO COMPLETO DEL GEOPORTAL

### Referencia visual obligatoria
**Sistema de Soporte a las Decisiones Hídricas — SNIRH ANA**
URL de referencia: `https://snirh.ana.gob.pe/ssdh/cuenca?UH=132`

El rediseño debe replicar con exactitud el patrón visual, layout y componentes de ese sistema, adaptando el contenido a calidad de agua en lugar de balance hídrico.

---

### 5.1 ARQUITECTURA DE PÁGINA

El módulo `pages/Geoportal.py` debe reescribirse completamente con esta estructura:

```python
# pages/Geoportal.py — estructura completa

import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import Optional

# ─── CSS Global del módulo ───────────────────────────────────────────────────
def inject_geoportal_css():
    st.markdown("""
    <style>
    /* ── Paleta SNIRH-ANA ── */
    :root {
        --azul-principal:  #1565C0;
        --azul-oscuro:     #0D47A1;
        --azul-medio:      #1976D2;
        --azul-claro:      #E3F2FD;
        --azul-claro2:     #BBDEFB;
        --verde:           #2E7D32;
        --teal:            #00796B;
        --rojo:            #C62828;
        --naranja:         #E65100;
        --morado:          #6A1B9A;
        --rosa:            #C2185B;
        --gris-fondo:      #F5F5F5;
        --gris-borde:      #E0E0E0;
        --gris-texto:      #757575;
        --texto-principal: #212121;
        --blanco:          #FFFFFF;
    }

    /* ── Reset Streamlit ── */
    .main > div { padding-top: 0 !important; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    header[data-testid="stHeader"] { display: none; }

    /* ── Header del Geoportal ── */
    .geo-header {
        background: var(--azul-oscuro);
        color: white;
        padding: 10px 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        height: 52px;
        position: sticky;
        top: 0;
        z-index: 1000;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }
    .geo-header-ambito {
        font-size: 15px;
        font-weight: 600;
        color: white;
        display: flex;
        align-items: center;
        gap: 6px;
        cursor: pointer;
    }
    .geo-header-ambito::after {
        content: '▾';
        font-size: 12px;
        opacity: 0.8;
    }
    .geo-header-titulo {
        font-size: 14px;
        font-weight: 500;
        color: #90CAF9;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .geo-header-logos {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    /* ── Layout split 50/50 ── */
    .geo-split-container {
        display: flex;
        height: calc(100vh - 52px);
        overflow: hidden;
    }
    .geo-panel-mapa {
        width: 50%;
        min-width: 50%;
        position: relative;
        overflow: hidden;
    }
    .geo-panel-datos {
        width: 50%;
        min-width: 50%;
        overflow-y: auto;
        background: var(--gris-fondo);
        border-left: 1px solid var(--gris-borde);
    }

    /* ── Toolbar vertical del mapa ── */
    .geo-mapa-toolbar {
        position: absolute;
        right: 12px;
        top: 50%;
        transform: translateY(-50%);
        background: white;
        border-radius: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.2);
        display: flex;
        flex-direction: column;
        z-index: 500;
    }
    .geo-mapa-toolbar button {
        width: 36px;
        height: 36px;
        border: none;
        background: transparent;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 16px;
        color: #424242;
        transition: background 0.15s;
        border-radius: 4px;
    }
    .geo-mapa-toolbar button:hover {
        background: var(--azul-claro);
        color: var(--azul-principal);
    }
    .geo-mapa-toolbar hr {
        margin: 2px 4px;
        border-color: var(--gris-borde);
    }

    /* ── Tabs de navegación ── */
    .geo-tabs-nav {
        background: white;
        border-bottom: 1px solid var(--gris-borde);
        display: flex;
        padding: 0 16px;
        position: sticky;
        top: 0;
        z-index: 100;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .geo-tab {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 12px 16px;
        font-size: 13px;
        font-weight: 500;
        color: var(--gris-texto);
        cursor: pointer;
        border-bottom: 3px solid transparent;
        margin-bottom: -1px;
        transition: color 0.15s, border-color 0.15s;
        white-space: nowrap;
    }
    .geo-tab:hover {
        color: var(--azul-principal);
    }
    .geo-tab.active {
        color: var(--azul-principal);
        border-bottom-color: var(--azul-principal);
        font-weight: 600;
    }
    .geo-tab-icon {
        font-size: 15px;
    }

    /* ── Sub-tabs tipo chip card (estilo SSDH) ── */
    .geo-chip-cards {
        display: flex;
        gap: 12px;
        padding: 16px;
        background: white;
        border-bottom: 1px solid var(--gris-borde);
        overflow-x: auto;
    }
    .geo-chip-card {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        width: 130px;
        min-width: 130px;
        height: 90px;
        background: white;
        border: 1.5px solid var(--gris-borde);
        border-radius: 6px;
        cursor: pointer;
        transition: border-color 0.15s, background 0.15s;
        padding: 12px 8px;
        position: relative;
    }
    .geo-chip-card:hover {
        border-color: var(--azul-medio);
        background: var(--azul-claro);
    }
    .geo-chip-card.active {
        border-color: var(--azul-principal);
        background: var(--azul-claro);
    }
    .geo-chip-card.active::after {
        content: '✓';
        position: absolute;
        top: 6px;
        right: 8px;
        font-size: 11px;
        color: var(--azul-principal);
        font-weight: bold;
    }
    .geo-chip-card-icon {
        font-size: 32px;
        color: var(--azul-principal);
        margin-bottom: 8px;
    }
    .geo-chip-card-text {
        font-size: 12px;
        text-align: center;
        color: var(--texto-principal);
        line-height: 1.3;
    }

    /* ── KPI Cards Tipo A (compactas con acento lateral) ── */
    .geo-kpi-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        padding: 16px;
    }
    .geo-kpi-card {
        background: var(--blanco);
        border-radius: 6px;
        padding: 14px 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        border-left: 4px solid var(--azul-principal);
        display: flex;
        flex-direction: column;
        position: relative;
        min-height: 80px;
    }
    .geo-kpi-card-icon {
        position: absolute;
        top: 12px;
        right: 12px;
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 18px;
        opacity: 0.85;
    }
    .geo-kpi-card-label {
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: var(--gris-texto);
        margin-bottom: 6px;
    }
    .geo-kpi-card-value {
        font-size: 26px;
        font-weight: 700;
        color: var(--texto-principal);
        line-height: 1;
    }
    .geo-kpi-card-unit {
        font-size: 12px;
        font-weight: 400;
        color: var(--gris-texto);
        margin-left: 4px;
    }

    /* Variantes de color para KPI cards */
    .geo-kpi-card.azul   { border-left-color: #1565C0; }
    .geo-kpi-card.verde  { border-left-color: #2E7D32; }
    .geo-kpi-card.teal   { border-left-color: #00796B; }
    .geo-kpi-card.rojo   { border-left-color: #C62828; }
    .geo-kpi-card.naranja{ border-left-color: #E65100; }
    .geo-kpi-card.morado { border-left-color: #6A1B9A; }

    .geo-kpi-card.azul    .geo-kpi-card-icon { background: #E3F2FD; color: #1565C0; }
    .geo-kpi-card.verde   .geo-kpi-card-icon { background: #E8F5E9; color: #2E7D32; }
    .geo-kpi-card.teal    .geo-kpi-card-icon { background: #E0F2F1; color: #00796B; }
    .geo-kpi-card.rojo    .geo-kpi-card-icon { background: #FFEBEE; color: #C62828; }
    .geo-kpi-card.naranja .geo-kpi-card-icon { background: #FFF3E0; color: #E65100; }
    .geo-kpi-card.morado  .geo-kpi-card-icon { background: #F3E5F5; color: #6A1B9A; }

    /* ── KPI Cards Tipo B (descriptivas con borde inferior) ── */
    .geo-kpi-grid-b {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        padding: 0 16px 16px;
    }
    .geo-kpi-card-b {
        background: var(--blanco);
        border-radius: 6px;
        padding: 14px 16px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        border-bottom: 3px solid var(--azul-principal);
        display: flex;
        flex-direction: column;
        min-height: 120px;
    }
    .geo-kpi-card-b-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 10px;
    }
    .geo-kpi-card-b-title {
        font-size: 13px;
        font-weight: 600;
        color: var(--azul-principal);
    }
    .geo-kpi-card-b-icon {
        font-size: 20px;
        color: var(--gris-texto);
    }
    .geo-kpi-card-b-content {
        font-size: 12px;
        color: var(--texto-principal);
        flex: 1;
        line-height: 1.5;
    }
    .geo-kpi-card-b-footer {
        font-size: 10px;
        color: var(--gris-texto);
        font-style: italic;
        margin-top: 8px;
        border-top: 1px solid var(--gris-borde);
        padding-top: 6px;
    }

    /* ── Secciones del panel ── */
    .geo-section {
        padding: 16px;
    }
    .geo-section-title {
        font-size: 14px;
        font-weight: 600;
        color: var(--texto-principal);
        margin-bottom: 12px;
        padding-bottom: 6px;
        border-bottom: 1px solid var(--gris-borde);
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .geo-section-subtitle {
        font-size: 11px;
        color: var(--gris-texto);
        margin-left: auto;
        font-weight: 400;
    }

    /* ── Tabla de datos estilo SNIRH ── */
    .geo-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 12px;
        background: white;
        border-radius: 6px;
        overflow: hidden;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .geo-table thead th {
        background: #F5F5F5;
        color: #424242;
        font-weight: 600;
        padding: 10px 12px;
        text-align: left;
        border-bottom: 2px solid var(--gris-borde);
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    .geo-table tbody tr {
        border-bottom: 1px solid #F0F0F0;
        transition: background 0.1s;
    }
    .geo-table tbody tr:hover {
        background: var(--azul-claro);
    }
    .geo-table tbody td {
        padding: 9px 12px;
        color: var(--texto-principal);
    }

    /* ── Badges ECA ── */
    .badge-cumple  { background:#E8F5E9; color:#1B5E20; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; }
    .badge-excede  { background:#FFEBEE; color:#B71C1C; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; }
    .badge-leve    { background:#FFF8E1; color:#E65100; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; }
    .badge-sindata { background:#F5F5F5; color:#757575; padding:3px 10px; border-radius:12px; font-size:11px; font-weight:600; }

    /* ── Iconos de acción en tabla (estilo círculo verde SNIRH) ── */
    .geo-action-btn {
        width: 28px;
        height: 28px;
        border-radius: 50%;
        border: 2px solid var(--teal);
        background: white;
        color: var(--teal);
        font-size: 13px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        transition: background 0.15s;
        margin: 0 2px;
    }
    .geo-action-btn:hover {
        background: var(--teal);
        color: white;
    }

    /* ── Botones de reporte (estilo SNIRH) ── */
    .geo-btn-primary {
        background: var(--azul-principal);
        color: white;
        border: none;
        padding: 8px 20px;
        border-radius: 4px;
        font-size: 13px;
        font-weight: 500;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
        transition: background 0.15s;
    }
    .geo-btn-primary:hover { background: var(--azul-oscuro); }
    .geo-btn-secondary {
        background: #607D8B;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 13px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .geo-btn-xls {
        background: var(--teal);
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        font-size: 13px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }

    /* ── Nota de fuente ── */
    .geo-fuente {
        font-size: 10px;
        color: var(--gris-texto);
        font-style: italic;
        text-align: right;
        margin-top: 8px;
    }

    /* ── Separador de sección ── */
    .geo-divider {
        height: 1px;
        background: var(--gris-borde);
        margin: 0 16px;
    }

    /* ── Ocultar elementos Streamlit innecesarios en este módulo ── */
    .stDeployButton, .stToolbar { display: none; }
    </style>
    """, unsafe_allow_html=True)
```

---

### 5.2 LAYOUT PRINCIPAL — split 50/50

```python
def render_geoportal():
    inject_geoportal_css()
    
    # ── Header del Geoportal ──────────────────────────────────────────────
    ambito_sel = st.session_state.get('geo_ambito', 'Todos los sistemas')
    
    st.markdown(f"""
    <div class="geo-header">
        <div class="geo-header-ambito">🗺️ {ambito_sel}</div>
        <div class="geo-header-titulo">
            💧 Vigilancia de Calidad del Agua — LVCA
        </div>
        <div class="geo-header-logos">
            <!-- Logos PEIMS + LVCA como imágenes base64 o st.image -->
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ── Split 50/50 con st.columns ────────────────────────────────────────
    col_mapa, col_datos = st.columns([1, 1], gap="small")
    
    with col_mapa:
        render_panel_mapa()
    
    with col_datos:
        render_panel_datos()
```

---

### 5.3 PANEL IZQUIERDO — Mapa interactivo

```python
def render_panel_mapa():
    """
    Mapa Folium con las siguientes capas y comportamiento:
    
    BASEMAP: Esri WorldImagery (satellite) como default
    CAPA 1: Puntos de monitoreo — círculos con radio proporcional 
            al número de parámetros evaluados (igual que SNIRH)
            Color según estado ECA:
              Cumple ECA:       #2E7D32 (verde oscuro)
              Excedencia leve:  #43A047 (verde claro, 1-10% sobre límite)  
              Excedencia media: #FB8C00 (naranja, 10-50% sobre límite)
              Excedencia alta:  #C62828 (rojo, >50% sobre límite)
              Sin datos:        #9E9E9E (gris)
    CAPA 2: Cuencas hidrográficas — polígonos con borde verde #43A047, 
            relleno transparente, grosor 1.5px
    CAPA 3: Mapa de calor ECA — heatmap Folium basado en densidad 
            de excedencias activas
    
    Popup al clickear un punto:
    - Encabezado azul con código y nombre del punto
    - Tabla: Cuenca | ECA | UTM | Altitud | Nivel embalse
    - Sección roja "N excedencia(s):" con lista de parámetros excedidos 
      (valor actual / límite unidad)
    - Cumplimiento: X% (Y/Z parámetros)
    
    Control de capas: checkbox en esquina superior derecha
    - ○ Calles  ● Satélite
    - ☑ Cuencas hidrográficas
    - ☑ Mapa de calor ECA
    - ☑ Puntos de monitoreo
    
    Minimap: en esquina inferior derecha, 15% del tamaño del mapa
    Escala: en esquina inferior izquierda
    
    Altura del mapa: calc(100vh - 52px) — usar height en px calculado
    """
    
    import folium
    from folium.plugins import HeatMap, MiniMap, MousePosition
    from streamlit_folium import st_folium
    
    m = folium.Map(
        location=[-15.8, -71.2],  # Centro cuenca Chili-Colca
        zoom_start=9,
        tiles=None,
        width='100%',
        height=700  # Ajustar según cálculo de viewport
    )
    
    # Basemaps
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri WorldImagery',
        name='Satélite',
        overlay=False,
        control=True
    ).add_to(m)
    
    folium.TileLayer(
        tiles='OpenStreetMap',
        name='Calles',
        overlay=False,
        control=True
    ).add_to(m)
    
    # Agregar puntos con popup estilo SNIRH
    fg_puntos = folium.FeatureGroup(name='Puntos de monitoreo', show=True)
    
    for punto in puntos_data:
        color = get_color_eca(punto['estado_eca'])
        radio = max(8, min(20, punto['n_parametros'] * 1.2))  # radio proporcional
        
        # Construir HTML del popup
        excedencias_html = ""
        if punto['excedencias']:
            items = "".join([
                f"<li>{e['parametro']}: <b style='color:#C62828'>{e['valor']}</b> / {e['limite']} {e['unidad']}</li>"
                for e in punto['excedencias']
            ])
            excedencias_html = f"""
            <div style='color:#C62828; font-weight:600; margin-top:8px;'>
                {len(punto['excedencias'])} excedencia(s):
            </div>
            <ul style='margin:4px 0; padding-left:16px; font-size:12px;'>{items}</ul>
            """
        
        popup_html = f"""
        <div style='width:280px; font-family:sans-serif; font-size:13px;'>
            <div style='background:{color}; color:white; padding:8px 12px; 
                        border-radius:4px 4px 0 0; font-weight:600;'>
                {punto['codigo']} · {punto['nombre']}
            </div>
            <div style='padding:10px 12px; background:white;'>
                <table style='width:100%; font-size:12px;'>
                    <tr><td style='color:#757575;'>Cuenca:</td>
                        <td><b>{punto['cuenca']}</b></td></tr>
                    <tr><td style='color:#757575;'>Sistema Hídrico:</td>
                        <td><b>{punto['sistema_hidrico']}</b></td></tr>
                    <tr><td style='color:#757575;'>Tipo:</td>
                        <td>{punto['tipo']}</td></tr>
                    <tr><td style='color:#757575;'>ECA:</td>
                        <td>{punto['eca']}</td></tr>
                    <tr><td style='color:#757575;'>UTM (19S):</td>
                        <td>{punto['utm_e']} E / {punto['utm_n']} N</td></tr>
                    <tr><td style='color:#757575;'>Altitud:</td>
                        <td>{punto['altitud']} msnm</td></tr>
                    <tr><td style='color:#757575;'>Nivel embalse:</td>
                        <td>{punto.get('nivel_embalse', '—')}</td></tr>
                </table>
                {excedencias_html}
                <div style='margin-top:8px; font-size:12px;'>
                    Cumple: <b>{punto['pct_cumplimiento']:.0f}%</b> 
                    ({punto['n_cumplen']}/{punto['n_evaluados']})
                </div>
            </div>
        </div>
        """
        
        folium.CircleMarker(
            location=[punto['lat'], punto['lon']],
            radius=radio,
            color='white',
            weight=1.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.85,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{punto['codigo']} — {punto['nombre']}"
        ).add_to(fg_puntos)
    
    fg_puntos.add_to(m)
    
    # Heatmap de excedencias
    if excedencias_coords:
        fg_heat = folium.FeatureGroup(name='Mapa de calor ECA', show=True)
        HeatMap(excedencias_coords, radius=25, blur=15, 
                gradient={'0.4':'blue','0.65':'lime','1':'red'}).add_to(fg_heat)
        fg_heat.add_to(m)
    
    # Minimap
    MiniMap(
        tile_layer='OpenStreetMap',
        position='bottomright',
        width=160,
        height=120,
        zoom_level_offset=-5
    ).add_to(m)
    
    # Control de capas
    folium.LayerControl(position='topright', collapsed=False).add_to(m)
    
    # Leyenda ECA (igual que SNIRH)
    leyenda_html = """
    <div style='position:absolute; bottom:20px; left:10px; z-index:999;
                background:white; padding:12px 16px; border-radius:6px;
                box-shadow:0 2px 8px rgba(0,0,0,0.2); font-family:sans-serif;
                font-size:12px; min-width:170px;'>
        <div style='font-weight:700; margin-bottom:8px; font-size:13px;'>
            Estado ECA
        </div>
        <div style='font-size:10px; color:#757575; margin-bottom:8px;'>
            D.S. N° 004-2017-MINAM
        </div>
        <div style='display:flex; align-items:center; gap:8px; margin:4px 0;'>
            <span style='width:12px;height:12px;border-radius:50%;background:#2E7D32;display:inline-block;'></span>
            Cumple ECA
        </div>
        <div style='display:flex; align-items:center; gap:8px; margin:4px 0;'>
            <span style='width:12px;height:12px;border-radius:50%;background:#43A047;display:inline-block;'></span>
            Excedencia leve
        </div>
        <div style='display:flex; align-items:center; gap:8px; margin:4px 0;'>
            <span style='width:12px;height:12px;border-radius:50%;background:#FB8C00;display:inline-block;'></span>
            Excedencia media
        </div>
        <div style='display:flex; align-items:center; gap:8px; margin:4px 0;'>
            <span style='width:12px;height:12px;border-radius:50%;background:#C62828;display:inline-block;'></span>
            Excedencia alta
        </div>
        <div style='display:flex; align-items:center; gap:8px; margin:4px 0;'>
            <span style='width:12px;height:12px;border-radius:50%;background:#9E9E9E;display:inline-block;'></span>
            Sin datos recientes
        </div>
        <div style='margin-top:8px; font-size:10px; color:#9E9E9E; font-style:italic;'>
            Radio = N° parámetros evaluados
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(leyenda_html))
    
    st_folium(m, height=700, use_container_width=True, returned_objects=[])
```

---

### 5.4 PANEL DERECHO — Tab: Estadísticas

```python
def render_tab_estadisticas(stats: dict):
    """
    Replica exacta del tab 'Estadísticas' del SSDH-ANA
    adaptado a calidad de agua LVCA.
    """
    
    # ── FILA 1: KPI cards compactas (4 columnas) ─────────────────────────
    st.markdown("""
    <div class="geo-kpi-grid">
        <div class="geo-kpi-card azul">
            <div class="geo-kpi-card-icon">📍</div>
            <div class="geo-kpi-card-label">Puntos monitoreados</div>
            <div class="geo-kpi-card-value">{n_puntos}</div>
        </div>
        <div class="geo-kpi-card verde">
            <div class="geo-kpi-card-icon">📋</div>
            <div class="geo-kpi-card-label">Campañas activas</div>
            <div class="geo-kpi-card-value">{n_campanas}</div>
        </div>
        <div class="geo-kpi-card teal">
            <div class="geo-kpi-card-icon">🔬</div>
            <div class="geo-kpi-card-label">Parámetros analizados</div>
            <div class="geo-kpi-card-value">{n_params}</div>
        </div>
        <div class="geo-kpi-card rojo">
            <div class="geo-kpi-card-icon">⚠️</div>
            <div class="geo-kpi-card-label">Excedencias activas</div>
            <div class="geo-kpi-card-value">{n_excedencias}</div>
        </div>
    </div>
    """.format(**stats), unsafe_allow_html=True)
    
    # ── FILA 2: KPI cards descriptivas (4 columnas) ──────────────────────
    # Construir listas de puntos con excedencias y conformes
    puntos_exceden_html = "<br>".join([
        f"<b>{p['codigo']}</b>: {', '.join(p['params_exceden'])}"
        for p in stats['puntos_con_excedencias'][:4]
    ]) or "Ninguno"
    
    puntos_cumplen_html = "<br>".join([
        f"<b>{p['codigo']}</b>: {p['nombre']}"
        for p in stats['puntos_conformes'][:4]
    ]) or "Sin datos suficientes"
    
    fecha_fuente = f"LVCA-AUTODEMA · {stats['fecha_actualizacion']}"
    
    st.markdown(f"""
    <div class="geo-kpi-grid-b">
        <div class="geo-kpi-card-b" style="border-bottom-color:#C62828;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Puntos con excedencias</div>
                <div class="geo-kpi-card-b-icon">⚠️</div>
            </div>
            <div class="geo-kpi-card-b-content">{puntos_exceden_html}</div>
            <div class="geo-kpi-card-b-footer">Fuente: {fecha_fuente}</div>
        </div>
        <div class="geo-kpi-card-b" style="border-bottom-color:#2E7D32;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Cumplen ECA</div>
                <div class="geo-kpi-card-b-icon">✅</div>
            </div>
            <div class="geo-kpi-card-b-content">{puntos_cumplen_html}</div>
            <div class="geo-kpi-card-b-footer">Fuente: {fecha_fuente}</div>
        </div>
        <div class="geo-kpi-card-b" style="border-bottom-color:#1565C0;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Último monitoreo</div>
                <div class="geo-kpi-card-b-icon">📅</div>
            </div>
            <div class="geo-kpi-card-b-content">
                <b>{stats['ultima_fecha']}</b><br>
                {stats['ultima_campana']}
            </div>
            <div class="geo-kpi-card-b-footer">Fuente: {fecha_fuente}</div>
        </div>
        <div class="geo-kpi-card-b" style="border-bottom-color:#00796B;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Cobertura de análisis</div>
                <div class="geo-kpi-card-b-icon">📊</div>
            </div>
            <div class="geo-kpi-card-b-content">
                <div style="font-size:24px; font-weight:700; color:#00796B;">
                    {stats['pct_avance']:.1f}%
                </div>
                <div style="background:#E0F2F1; border-radius:4px; height:6px; margin-top:6px;">
                    <div style="background:#00796B; width:{stats['pct_avance']:.0f}%; 
                                height:6px; border-radius:4px;"></div>
                </div>
                <div style="font-size:11px; color:#757575; margin-top:4px;">
                    {stats['n_resultados']}/{stats['n_esperados']} resultados
                </div>
            </div>
            <div class="geo-kpi-card-b-footer">Fuente: {fecha_fuente}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="geo-divider"></div>', unsafe_allow_html=True)
    
    # ── ESTADÍSTICOS LVCA (igual a "Estadísticos ANA" del SSDH) ──────────
    st.markdown("""
    <div class="geo-section">
        <div class="geo-section-title">
            📊 Estadísticos LVCA
            <span class="geo-section-subtitle">
                Consultados al {fecha}
            </span>
        </div>
    </div>
    """.format(fecha=stats['fecha_actualizacion']), unsafe_allow_html=True)
    
    # Grid 4 columnas para estadísticos secundarios (estilo "Principales Embalses")
    st.markdown("""
    <div class="geo-kpi-grid">
        <div class="geo-kpi-card-b" style="border-bottom-color:#1976D2;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Puntos Chili Regulado 🌊</div>
            </div>
            <div class="geo-kpi-card-b-content">
                {n_chili_monitoreados} Monitoreados<br>
                {n_chili_total} Total en sistema<br>
                {n_chili_exceden} Con excedencias
            </div>
            <div class="geo-kpi-card-b-footer">Fuente: LVCA-AUTODEMA</div>
        </div>
        <div class="geo-kpi-card-b" style="border-bottom-color:#0097A7;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Puntos Colca Regulado 🌊</div>
            </div>
            <div class="geo-kpi-card-b-content">
                {n_colca_monitoreados} Monitoreados<br>
                {n_colca_total} Total en sistema<br>
                {n_colca_exceden} Con excedencias
            </div>
            <div class="geo-kpi-card-b-footer">Fuente: LVCA-AUTODEMA</div>
        </div>
        <div class="geo-kpi-card-b" style="border-bottom-color:#5E35B1;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Muestras activas 🔬</div>
            </div>
            <div class="geo-kpi-card-b-content">
                {n_muestras_lab} En laboratorio<br>
                {n_muestras_campo} En campo<br>
                {n_muestras_total} Total campaña activa
            </div>
            <div class="geo-kpi-card-b-footer">Fuente: LVCA-AUTODEMA</div>
        </div>
        <div class="geo-kpi-card-b" style="border-bottom-color:#EF6C00;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Parámetros críticos ⚠️</div>
            </div>
            <div class="geo-kpi-card-b-content">
                {params_criticos}
            </div>
            <div class="geo-kpi-card-b-footer">Fuente: LVCA-AUTODEMA</div>
        </div>
    </div>
    """.format(**stats), unsafe_allow_html=True)
```

---

### 5.5 PANEL DERECHO — Tab: Tendencias

```python
def render_tab_tendencias(datos_hist: pd.DataFrame, punto_sel: str, param_sel: str):
    """
    Implementar gráficos estilo SNIRH SSDH.
    """
    
    # Sub-tabs: Serie temporal / Comparar puntos / Estacionalidad / Estado ECA
    # Usar st.session_state para el sub-tab activo
    
    # ── GRÁFICO SERIE TEMPORAL (área + línea, igual que Balance hídrico SSDH) ──
    
    def plot_serie_temporal(df, param, limite_max=None, limite_min=None):
        """
        Gráfico de área rellena semitransparente con puntos circulares.
        Réplica exacta del gráfico de Balance hídrico del SSDH-ANA.
        """
        fig = go.Figure()
        
        # Serie principal — área rellena azul
        fig.add_trace(go.Scatter(
            x=df['fecha'],
            y=df[param],
            name=param,
            mode='lines+markers',
            line=dict(color='#1565C0', width=2.5),
            marker=dict(size=6, color='#1565C0', symbol='circle',
                       line=dict(color='white', width=1.5)),
            fill='tozeroy',
            fillcolor='rgba(21, 101, 192, 0.15)',  # azul semitransparente
        ))
        
        # Línea de límite máximo ECA
        if limite_max is not None:
            fig.add_hline(
                y=limite_max,
                line=dict(color='#C62828', width=1.5, dash='dash'),
                annotation_text=f"ECA máx: {limite_max}",
                annotation_position="right",
                annotation_font=dict(color='#C62828', size=11)
            )
        
        # Línea de límite mínimo ECA
        if limite_min is not None:
            fig.add_hline(
                y=limite_min,
                line=dict(color='#2E7D32', width=1.5, dash='dash'),
                annotation_text=f"ECA mín: {limite_min}",
                annotation_position="right",
                annotation_font=dict(color='#2E7D32', size=11)
            )
        
        fig.update_layout(
            height=320,
            margin=dict(l=40, r=80, t=30, b=40),
            paper_bgcolor='white',
            plot_bgcolor='white',
            font=dict(family='sans-serif', size=12),
            xaxis=dict(
                title='',
                showgrid=False,
                tickformat='%b %Y',
                tickangle=-30,
            ),
            yaxis=dict(
                title=param,
                showgrid=True,
                gridcolor='#F5F5F5',
                gridwidth=1,
                zeroline=False,
            ),
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=-0.3,
                xanchor='center',
                x=0.5,
                font=dict(size=11)
            ),
            hovermode='x unified',
        )
        
        # Nota de fuente debajo del gráfico
        return fig
    
    # ── GRÁFICO COMPARAR PUNTOS (barras horizontales igual que SSDH) ──────
    
    def plot_comparar_puntos(df_ultimo_valor, param, limite_max=None, limite_min=None):
        """
        Barras horizontales por punto, una barra por punto con el 
        último valor disponible. Líneas verticales de ECA.
        """
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            y=df_ultimo_valor['punto_nombre'],
            x=df_ultimo_valor['valor'],
            orientation='h',
            marker_color='#1565C0',
            text=df_ultimo_valor['valor'].round(3),
            textposition='outside',
            textfont=dict(size=11),
        ))
        
        if limite_max:
            fig.add_vline(
                x=limite_max,
                line=dict(color='#C62828', width=1.5, dash='dash'),
                annotation_text=f"ECA máx: {limite_max}",
                annotation_position='top',
                annotation_font=dict(color='#C62828', size=10)
            )
        
        if limite_min:
            fig.add_vline(
                x=limite_min,
                line=dict(color='#2E7D32', width=1.5, dash='dash'),
                annotation_text=f"ECA mín: {limite_min}",
                annotation_position='bottom',
                annotation_font=dict(color='#2E7D32', size=10)
            )
        
        fig.update_layout(
            height=max(250, len(df_ultimo_valor) * 40),
            margin=dict(l=20, r=80, t=20, b=30),
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(
                title=f'{param} ({unidad})',
                showgrid=True,
                gridcolor='#F5F5F5',
            ),
            yaxis=dict(showgrid=False),
        )
        
        return fig
    
    # ── GRÁFICO ESTACIONALIDAD (barras verticales por mes) ────────────────
    
    def plot_estacionalidad(df_mensual, param):
        """
        Distribución mensual promedio.
        Barras azules con valores encima. Meses en eje X (Ene-Dic).
        Réplica del gráfico de Distribución mensual de precipitación del SSDH.
        """
        meses = ['Ene','Feb','Mar','Abr','May','Jun',
                 'Jul','Ago','Sep','Oct','Nov','Dic']
        
        fig = go.Figure()
        
        fig.add_trace(go.Bar(
            x=meses,
            y=df_mensual['promedio'],
            marker_color='#1976D2',
            text=df_mensual['promedio'].round(2),
            textposition='outside',
            textfont=dict(size=10, color='#424242'),
        ))
        
        fig.update_layout(
            height=280,
            margin=dict(l=40, r=20, t=20, b=40),
            paper_bgcolor='white',
            plot_bgcolor='white',
            xaxis=dict(title='Mes', showgrid=False),
            yaxis=dict(
                title=f'{param} ({unidad})',
                showgrid=True,
                gridcolor='#F5F5F5',
                zeroline=True,
                zerolinecolor='#E0E0E0',
            ),
            bargap=0.3,
        )
        
        return fig
```

---

### 5.6 PANEL DERECHO — Tab: Estado ECA (Indicadores)

```python
def render_tab_estado_eca(stats: dict):
    """
    Replica el tab 'Indicadores' del SSDH-ANA con gauge charts.
    """
    
    # ── GAUGE de cumplimiento general ECA ────────────────────────────────
    def plot_gauge_cumplimiento(pct: float):
        """
        Velocímetro/gauge de cumplimiento ECA.
        Colores graduales: rojo → naranja → amarillo → verde.
        Réplica del gauge 'Disponibilidad hídrica per cápita' del SSDH.
        Implementar con plotly go.Indicator tipo 'gauge'.
        """
        fig = go.Figure(go.Indicator(
            mode="gauge+number",
            value=pct,
            number={
                'suffix': '%',
                'font': {'size': 36, 'color': '#212121', 'family': 'sans-serif'},
            },
            gauge={
                'axis': {
                    'range': [0, 100],
                    'tickwidth': 1,
                    'tickcolor': '#757575',
                    'tickfont': {'size': 11},
                },
                'bar': {'color': '#212121', 'thickness': 0.04},  # aguja
                'bgcolor': 'white',
                'borderwidth': 0,
                'steps': [
                    {'range': [0,  50], 'color': '#FFCDD2'},   # rojo claro
                    {'range': [50, 70], 'color': '#FFE0B2'},   # naranja claro
                    {'range': [70, 85], 'color': '#FFF9C4'},   # amarillo claro
                    {'range': [85, 100],'color': '#C8E6C9'},   # verde claro
                ],
                'threshold': {
                    'line': {'color': '#424242', 'width': 4},
                    'thickness': 0.75,
                    'value': pct,
                },
            },
            domain={'x': [0, 1], 'y': [0, 1]},
        ))
        
        fig.update_layout(
            height=220,
            margin=dict(l=20, r=20, t=30, b=20),
            paper_bgcolor='white',
            font=dict(family='sans-serif'),
        )
        
        return fig
    
    # Layout 2 columnas para indicadores
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="geo-kpi-card-b" style="border-bottom-color:#1565C0; padding:16px;">
            <div class="geo-kpi-card-b-header">
                <div class="geo-kpi-card-b-title">Índice de cumplimiento ECA</div>
                <div>🗺️ ℹ️</div>
            </div>
            <div style="font-size:11px; color:#757575; margin-bottom:8px;">
                Cuenca Chili-Quilca · Colca-Camaná
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        fig_gauge = plot_gauge_cumplimiento(stats['pct_cumplimiento'])
        st.plotly_chart(fig_gauge, use_container_width=True, 
                        config={'displayModeBar': False})
        
        st.markdown(f"""
        <div class="geo-fuente">Fuente: LVCA-AUTODEMA · D.S. N°004-2017-MINAM</div>
        """, unsafe_allow_html=True)
    
    with col2:
        # Donut chart de distribución de estados
        fig_donut = go.Figure(go.Pie(
            labels=['Cumple ECA', 'Con excedencias', 'Sin datos'],
            values=[stats['n_cumplen'], stats['n_exceden'], stats['n_sin_datos']],
            hole=0.55,
            marker_colors=['#2E7D32', '#C62828', '#BDBDBD'],
            textfont={'size': 11},
            hovertemplate='%{label}: %{value} puntos (%{percent})<extra></extra>',
        ))
        
        fig_donut.update_layout(
            height=220,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor='white',
            showlegend=True,
            legend=dict(
                orientation='v',
                font=dict(size=11),
                yanchor='middle',
                y=0.5,
            ),
            annotations=[dict(
                text=f"<b>{stats['n_total']}</b><br>puntos",
                x=0.5, y=0.5,
                font=dict(size=13, color='#212121'),
                showarrow=False,
            )],
        )
        
        st.plotly_chart(fig_donut, use_container_width=True,
                       config={'displayModeBar': False})
    
    # ── TABLA de estado por punto (igual que tabla de presas SSDH) ────────
    st.markdown("""
    <div class="geo-section">
        <div class="geo-section-title">Estado ECA por punto de muestreo</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Construir tabla HTML estilo SNIRH con iconos de acción circulares
    filas_html = ""
    for p in puntos_estado:
        badge_class = {
            'cumple': 'badge-cumple',
            'leve': 'badge-leve',
            'excede': 'badge-excede',
            'sin_datos': 'badge-sindata',
        }.get(p['estado_key'], 'badge-sindata')
        
        filas_html += f"""
        <tr>
            <td><b>{p['codigo']}</b></td>
            <td>{p['nombre']}</td>
            <td><span style='font-size:11px;color:#757575;'>{p['eca']}</span></td>
            <td>{p['ultimo_monitoreo']}</td>
            <td>{p['n_evaluados']}</td>
            <td><span class="{badge_class}">{p['estado_label']}</span></td>
            <td>
                <button class="geo-action-btn" title="Ver gráfico">📈</button>
                <button class="geo-action-btn" title="Exportar">📥</button>
                <button class="geo-action-btn" title="Ver en mapa">📍</button>
            </td>
        </tr>
        """
    
    st.markdown(f"""
    <div style="padding:0 16px 16px;">
        <table class="geo-table">
            <thead>
                <tr>
                    <th>Código</th>
                    <th>Punto</th>
                    <th>ECA</th>
                    <th>Último monitoreo</th>
                    <th>Parámetros</th>
                    <th>Estado</th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>{filas_html}</tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)
```

---

### 5.7 PANEL DERECHO — Tab: Reportes

```python
def render_tab_reportes():
    """
    Réplica del tab 'Reportes' del SSDH-ANA con vista previa PDF inline.
    """
    
    st.markdown("""
    <div class="geo-section">
        <h3 style="text-align:center; font-size:20px; color:#212121; 
                   font-weight:400; margin:8px 0 16px;">
            Reportes
        </h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Controles estilo SSDH
    col_nivel, col_camp, col_btns = st.columns([1, 2, 1.5])
    
    with col_nivel:
        nivel = st.selectbox("Nivel", 
            ["Campaña", "Punto de muestreo", "Sistema completo"],
            label_visibility="visible")
    
    with col_camp:
        campana_sel = st.selectbox("Campaña", 
            [c['nombre'] for c in campanas_lista],
            label_visibility="visible")
    
    with col_btns:
        st.markdown("<br>", unsafe_allow_html=True)
        col_g, col_p, col_x = st.columns(3)
        
        with col_g:
            generar = st.button("🔍 Generar", type="primary", 
                               use_container_width=True)
        with col_p:
            descargar_pdf = st.button("📥 PDF", use_container_width=True)
        with col_x:
            descargar_xls = st.button("📥 XLS", use_container_width=True)
    
    # Vista previa PDF inline (igual que SSDH)
    if 'pdf_bytes' in st.session_state:
        import base64
        b64 = base64.b64encode(st.session_state['pdf_bytes']).decode()
        
        st.markdown(f"""
        <div style="margin:16px; border:1px solid #E0E0E0; border-radius:6px; 
                    overflow:hidden; box-shadow:0 2px 8px rgba(0,0,0,0.1);">
            <iframe 
                src="data:application/pdf;base64,{b64}"
                width="100%"
                height="600px"
                style="border:none;"
            ></iframe>
        </div>
        """, unsafe_allow_html=True)
    
    # Estructura del PDF generado — header estilo SSDH-ANA
    # El PDF debe tener:
    # 1. Banda azul header con: ícono ola + "Vigilancia de Calidad del Agua — LVCA" 
    #    + logos PEIMS y AUTODEMA alineados a la derecha
    # 2. Título centrado: nombre de la campaña/punto
    # 3. Sección "Datos generales" con borde izquierdo azul + grid de KPI cards
    # 4. Mapa de ubicación (captura del mapa o imagen estática)
    # 5. Tabla consolidada de resultados con celdas de color según ECA
    # 6. Sección "Calidad del Agua" con grid 4 columnas:
    #    [Puntos monitoreados] [Campañas] [Excedencias activas] [Cumplimiento %]
    #    Igual al grid de la página 2 del reporte SSDH
```

---

### 5.8 NAVEGACIÓN POR TABS — Implementación con session_state

```python
# La navegación entre tabs del panel derecho debe usar session_state
# para no recargar el mapa (que es costoso)

TABS_GEOPORTAL = [
    {"id": "estadisticas", "icon": "📊", "label": "Estadísticas"},
    {"id": "datos",        "icon": "🗂️",  "label": "Datos"},
    {"id": "tendencias",   "icon": "📈",  "label": "Tendencias"},
    {"id": "estado_eca",   "icon": "🎯",  "label": "Estado ECA"},
    {"id": "reportes",     "icon": "📄",  "label": "Reportes"},
]

def render_panel_datos():
    tab_activo = st.session_state.get('geo_tab_activo', 'estadisticas')
    
    # Renderizar HTML de los tabs
    tabs_html = '<div class="geo-tabs-nav">'
    for tab in TABS_GEOPORTAL:
        clase = "geo-tab active" if tab['id'] == tab_activo else "geo-tab"
        tabs_html += f"""
        <div class="{clase}" 
             onclick="setGeoTab('{tab['id']}')"
             id="tab-{tab['id']}">
            <span class="geo-tab-icon">{tab['icon']}</span>
            {tab['label']}
        </div>
        """
    tabs_html += '</div>'
    st.markdown(tabs_html, unsafe_allow_html=True)
    
    # Usar st.radio oculto para capturar la selección de tab
    # (workaround para Streamlit sin callbacks JS)
    tab_sel = st.radio(
        "Tab", 
        [t['id'] for t in TABS_GEOPORTAL],
        format_func=lambda x: next(t['label'] for t in TABS_GEOPORTAL if t['id'] == x),
        horizontal=True,
        label_visibility="collapsed",
        key="geo_tab_radio"
    )
    st.session_state['geo_tab_activo'] = tab_sel
    
    # Renderizar contenido del tab activo
    if tab_sel == 'estadisticas':
        render_tab_estadisticas(stats)
    elif tab_sel == 'datos':
        render_tab_datos()
    elif tab_sel == 'tendencias':
        render_tab_tendencias(datos_hist, punto_sel, param_sel)
    elif tab_sel == 'estado_eca':
        render_tab_estado_eca(stats)
    elif tab_sel == 'reportes':
        render_tab_reportes()
```

---

## PARTE 6 — VERIFICACIONES FINALES

```python
# Checklist post-implementación a ejecutar en Claude Code:

# 1. Test de unidades
# grep -r "gC" --include="*.py" → debe devolver 0 resultados
# grep -r "gC" → verificar también en strings de consultas SQL

# 2. Test de ortografía  
# grep -rn "Administracion\b\|Parametros\b" --include="*.py"
# grep -rn "Perifoton\b\|perifoton\b" --include="*.py"

# 3. Test del split 50/50
# Verificar en navegador que el mapa ocupa exactamente el 50% izquierdo
# y el panel de datos el 50% derecho, sin scrollbar horizontal

# 4. Test de responsividad mínima
# El layout debe funcionar a 1280px de ancho mínimo
# Por debajo de 1024px puede colapsar a layout vertical

# 5. Test de popups del mapa
# Click en 132EABla3 → verificar que muestra datos reales de BD
# Verificar que el popup muestra las excedencias de Amonio, Fósforo, 
# Hierro y Manganeso con sus valores actuales

# 6. Test de gauge chart
# st.session_state simulando 88% → gauge debe apuntar a zona verde

# 7. Test de generación PDF
# Generar reporte de CAMP-2026-001 → verificar que el DOCX se descarga
# y contiene la tabla de excedencias con colores ECA
```

---

## NOTAS TÉCNICAS ADICIONALES

### Sobre st.markdown con HTML
Toda la UI del Geoportal usa `st.markdown(..., unsafe_allow_html=True)`.
Los componentes interactivos (selectores, botones de descarga) deben seguir
usando widgets nativos de Streamlit. El CSS se inyecta UNA sola vez en el 
init de la página, no en cada render.

### Sobre el mapa y el rendimiento
El mapa Folium debe renderizarse con `st_folium(..., returned_objects=[])`
para evitar que re-renderice en cada interacción. Usar `st.cache_data` para 
las queries de puntos con TTL de 5 minutos.

### Sobre la compatibilidad Streamlit Cloud
- No usar `streamlit-javascript` ni otros paquetes no estándar
- Los CSS con `position: sticky` pueden requerir `overflow: visible` en el 
  contenedor padre de Streamlit
- El iframe de PDF inline funciona con base64 embebido

### Fuentes de referencia visual
- Layout split 50/50: https://snirh.ana.gob.pe/ssdh/cuenca?UH=132
- KPI cards con acento lateral: Tab "Estadísticas" del SSDH
- Gauge charts: Tab "Indicadores" del SSDH  
- Gráfico de área rellena: Tab "Temáticas > Balance" del SSDH
- Barras verticales con valores: Tab "Resultados WEAP > Precipitación Areal"
- Tabla con iconos circulares de acción: Sección "Presas" del SSDH
- Reporte PDF embebido: Tab "Temáticas > Reportes" del SSDH
