# CODEX.md

## Estado actual (2026)
Pipeline ETL DentOS con 3 scripts:
1) citas base (`01_mercadeo_citas.py`)
2) pagos sobre maestro (`02_mercadeo_pagos.py`)
3) facturacion desde JSON de caja (`03_facturacion_json.py`)

Archivo maestro principal:
- `excel_generado/formato_odontologia_[MES].xlsx`

## Orden de ejecucion
```bash
python scripts/01_mercadeo_citas.py
python scripts/02_mercadeo_pagos.py
python scripts/03_facturacion_json.py
```

## Estructura de carpetas
- Citas detallado: `excel_dentos/01_citas_detallado/`
- Citas con pagos: `excel_dentos/02_citas_con_pagos/`
- JSON caja: `export_json/facturacion_json/`
- Userscript extracción: `export_json/script_web/exportacion_pagos_dentos.js`
- Salidas Excel: `excel_generado/`

## Script 01 (citas base)
Archivo: `scripts/01_mercadeo_citas.py`
- Hoja destino: `Datos Mercadeo`
- Columnas activas actuales:
  - `id_registro, Numero_Documento, Paciente, Municipio, Convenio, Fecha, Mes, Semana, Agente, Profesional_Asignado, Especialidad, Canal_Captacion, Tipo_Cita, Programados, Asistido, Efectivo`
- No llena columnas de facturación.

## Script 02 (pagos sobre maestro)
Archivo: `scripts/02_mercadeo_pagos.py`
- Match principal: `doc_norm + Fecha_dia`
- Filtros activos:
  - excluir `fac_anulada == SI`
  - excluir `forma_pago` con `anticipo/anticpo`
- Dedup activo por clave de pago.
- Estado funcional actual del archivo: mantiene lógica histórica con columnas de facturación (`Factura`, `Metodo_Pago`, `Asesor_Comercial`, `Recaudo (venta día)`) además de `Efectivo`.

## Script 03 (facturacion JSON)
Archivo: `scripts/03_facturacion_json.py`
- Lee todos los `listado_pagos_*.json` de `export_json/facturacion_json`.
- Genera/actualiza hojas:
  - `facturacion`
  - `facturacion_control`
- Compara por día:
  - `sum(listado_pagos.valor)` vs `total_documentos` (incluido en el JSON)
  - si hay diferencia positiva, busca documento(s) para exclusión automática
  - deja trazabilidad en `facturacion_control`
- Columnas actuales de `facturacion`:
  - `Fecha, Año, Mes, Semana, Tipo_factura, Tipo_Doc, Paciente, Recaudo (venta dia), Total_Documentos_JSON, Total_Listado_JSON`

## Userscript de extracción (web)
Archivo: `export_json/script_web/exportacion_pagos_dentos.js`
- Botón `Exportar dia`: extrae vista actual de `Listado de pagos` y genera 1 JSON.
- Botón `Exportar semana`: recorre días hábiles, hace `Mostrar -> Detalles -> espera -> scroll -> exportación` por día.
- JSON incluye `total_documentos` (tabla “Totales por documentos”).

## Normalización de documento (scripts 01/02)
Regla base:
1. limpiar espacios/símbolos
2. resolver notación científica
3. quitar sufijo `.0`
4. si >11 dígitos: conservar últimos 11
5. si 11 dígitos:
   - inicia con `1` -> quitar último dígito
   - en otro caso -> quitar primer dígito
6. si <10 dígitos: conservar

## Semanas clínicas acordadas 2026 (script 03)
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
Abril 2026 está marcado como provisional y se debe validar con gerencia antes de cierre mensual.
