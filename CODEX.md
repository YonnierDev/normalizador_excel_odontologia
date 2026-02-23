# CODEX.md

## Estado actual (2026)
Pipeline ETL para DentOS con 3 flujos:
1) citas base (mercadeo)
2) pagos sobre citas
3) facturacion desde JSON de caja

Archivo maestro:
- `excel_generado/formato_odontologia_[MES].xlsx`

## Orden de ejecucion
```bash
python scripts/01_mercadeo_citas.py
python scripts/02_mercadeo_pagos.py
python scripts/03_facturacion_json.py
```

## Estructura de carpetas
- Entradas citas: `excel_dentos/01_citas_detallado/`
- Entradas pagos: `excel_dentos/02_citas_con_pagos/`
- JSON caja: `export_json/facturacion_json/`
- Userscript web: `export_json/script_web/exportacion_pagos_dentos.js`
- Salidas: `excel_generado/`

## Script 01 (citas)
Archivo: `scripts/01_mercadeo_citas.py`
- Hoja destino: `Datos Mercadeo`
- Columnas activas actuales:
  - `id_registro, Numero_Documento, Paciente, Municipio, Convenio, Fecha, Mes, Semana, Agente, Profesional_Asignado, Especialidad, Canal_Captacion, Tipo_Cita, Programados, Asistido, Efectivo`
- No genera columnas de facturacion en esta hoja.
- Semanas: rango FEBRERO (actual en archivo).

## Script 02 (pagos sobre citas)
Archivo: `scripts/02_mercadeo_pagos.py`
- Match principal: `doc_norm + Fecha_dia`
- Filtros activos:
  - excluir `fac_anulada == SI`
  - excluir `forma_pago` con `anticipo/anticpo`
- Dedup activo por clave de pago.
- Estado actual: sigue con logica historica (incluye campos de facturacion) y esta en revision para simplificar solo a efectividad en hoja mercadeo.

## Script 03 (facturacion JSON)
Archivo: `scripts/03_facturacion_json.py`
- Lee todos los `listado_pagos_*.json` de `export_json/facturacion_json`.
- Genera/actualiza hojas:
  - `facturacion`
  - `facturacion_control`
- Compara por dia:
  - suma `listado_pagos` vs `total_documentos` (del JSON)
  - detecta diferencia y excluye documento(s) cuando hay match exacto
  - deja trazabilidad en `facturacion_control`.
- Columnas de `facturacion` (actuales):
  - `Fecha, Year, Mes, Semana, Tipo_factura, Tipo_Doc, Paciente, Recaudo (venta dia), Total_Documentos_JSON, Total_Listado_JSON`

## Normalizacion de documento (scripts 01/02)
Regla base:
1. limpiar espacios/simbolos
2. resolver notacion cientifica
3. quitar sufijo `.0`
4. si >11 digitos: conservar ultimos 11
5. si 11 digitos:
   - inicia con `1` -> quitar ultimo digito
   - si no -> quitar primer digito
6. si <10 digitos: conservar

## Semanas clinicas acordadas para 2026 (script 03)
- Enero:
  - Semana1: 02-10
  - Semana2: 12-17
  - Semana3: 19-24
  - Semana4: 26-31
- Marzo:
  - Semana1: 02-07
  - Semana2: 09-14
  - Semana3: 16-21
  - Semana4: 23-31
- Abril (provisional):
  - Semana1: 01-11
  - Semana2: 13-18
  - Semana3: 20-25
  - Semana4: 27-30

## Nota operacional
Abril 2026 esta marcado como provisional y debe validarse con gerencia antes de cierre mensual.
