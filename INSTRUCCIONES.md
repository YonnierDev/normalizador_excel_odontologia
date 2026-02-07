# Instrucciones de Uso

## Estructura del Proyecto

El proyecto se ha organizado para procesar archivos de Excel de manera secuencial.

### 1. Insumos (Carpeta `excel_dentos`)
Debes colocar los archivos descargados en las carpetas numeradas correspondientes:

- **`excel_dentos/01_citas_detallado/`**:
  - Coloca aquí el archivo que comienza con **"citas detallado"**.
  - *Ejemplo*: `citas detallado enero.xlsx`

- **`excel_dentos/02_citas_con_pagos/`**:
  - (Próximamente) Para archivo de pagos.

### 2. Ejecución
Para procesar los archivos, ejecuta los scripts en orden:

1. **Paso 1**: Generar reporte de mercadeo desde citas.
   ```bash
   python scripts/01_mercadeo_citas.py
   ```
2. **Paso 2**: Cruzar información de pagos y efectividad.
   ```bash
   python scripts/02_mercadeo_pagos.py
   ```

### 3. Normalizacion de documentos (cedulas)
Los scripts normalizan el numero de documento para reducir errores manuales de digitacion:

- Se conserva cualquier documento con menos de 10 digitos (no se descarta).
- Si el documento llega con mas de 11 digitos, se recorta a los ultimos 11.
- Si queda con 11 digitos:
  - Si empieza con 1, se elimina el ultimo digito.
  - Si no empieza con 1, se elimina el primer digito.

Esto ayuda a corregir errores comunes (por ejemplo, formatos en notacion cientifica o un digito extra).
Si los errores manuales son muy frecuentes o muy inconsistentes, no siempre se podra recuperar la informacion exacta, por lo que es importante revisar los reportes de correcciones en consola.

### 4. Salida (Carpeta `excel_generado`)
El archivo resultante se generará en la carpeta `excel_generado/` con el nombre:
- `formato_odontologia_[MES].xlsx`

Este archivo se actualizará automáticamente si vuelves a correr el script con datos nuevos o corregidos.
