# Instrucciones de Uso

## Estructura del Proyecto

El proyecto se ha organizado para procesar archivos de Excel de manera secuencial.

### 1. Insumos (Carpeta `excel_dentos`)
Debes colocar los archivos descargados en las carpetas numeradas correspondientes:

- **`excel_dentos/01_citas_detallado/`**:
  - Coloca aquí el archivo que comienza con **"citas detallado"**.
  - *Ejemplo*: `citas detallado enero.xlsx`

- **`excel_dentos/02_pacientes_con_pagos/`**:
  - (Próximamente) Para archivo de pagos.

### 2. Ejecución
Para procesar los archivos, ejecuta los scripts en orden:

1. **Paso 1**: Generar reporte de mercadeo desde citas.
   ```bash
   python scripts/01_mercadeo_citas.py
   ```

### 3. Salida (Carpeta `excel_generado`)
El archivo resultante se generará en la carpeta `excel_generado/` con el nombre:
- `formato_odontologia_[MES].xlsx`

Este archivo se actualizará automáticamente si vuelves a correr el script con datos nuevos o corregidos.
