# Cuencas hidrográficas — GeoJSON

Cada archivo `.geojson` en este directorio se carga automáticamente como una capa
de polígono en el mapa del Geoportal, con outline verde brillante estilo SSDH/ANA.

## Formato esperado

```json
{
  "type": "Feature",
  "properties": {
    "nombre": "Nombre de la cuenca",
    "codigo": "UH-XXX",
    "fuente": "ANA SNIRH"
  },
  "geometry": {
    "type": "Polygon",
    "coordinates": [[[lon, lat], [lon, lat], ...]]
  }
}
```

## Reemplazar con datos oficiales

El archivo `Chili_Vitor_Quilca.geojson` es una **aproximación visual** del
contorno de la cuenca para mostrar el patrón. Para usar el límite oficial:

1. Descarga el GeoJSON oficial desde:
   - **ANA SNIRH IDE**: https://snirh.ana.gob.pe/signe (módulo de descarga de cuencas)
   - **Geoservidor MINAM**: https://geoservidor.minam.gob.pe (descarga shapefiles + conversión a GeoJSON)
2. Reemplaza el contenido de `Chili_Vitor_Quilca.geojson` con el archivo oficial
3. Asegúrate que las coordenadas estén en formato `[longitud, latitud]` (estándar GeoJSON)
4. La capa se actualizará al recargar la página del Geoportal

## Agregar más cuencas

Simplemente agrega otro `.geojson` en este directorio (ej. `Colca_Camana.geojson`)
y aparecerá automáticamente como otra capa con el mismo estilo. El nombre del archivo
(sin extensión, con `_` reemplazado por espacios) se usa como tooltip.
