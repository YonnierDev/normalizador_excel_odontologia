# Instrucciones de Uso

## Flujo actual (2026)
El proyecto se ejecuta en 3 pasos:
1) crear base de mercadeo desde citas,
2) cruzar pagos sobre el maestro,
3) cargar facturacion real desde JSON de caja.

Archivo maestro:
- `excel_generado/formato_odontologia_[MES].xlsx`

## Estructura de carpetas
- Citas detallado: `excel_dentos/01_citas_detallado/`
- Citas con pagos: `excel_dentos/02_citas_con_pagos/`
- JSON de caja: `export_json/facturacion_json/`
- Userscript web: `export_json/script_web/exportacion_pagos_dentos.js`
- Salidas Excel: `excel_generado/`

## Paso 0 (web): extraer JSON desde DentOS
1. Cargar el userscript `exportacion_pagos_dentos.js` en Greasemonkey.
2. Ir a `https://previred.clinicos.co/cuadrecaja/`.
3. Entrar a `Detalles` para ver `Listado de pagos`.
4. Botones disponibles:
   - `Exportar dia`: exporta solo la vista actual.
   - `Exportar semana`: recorre dias habiles, hace `Mostrar -> Detalles -> espera -> scroll -> export`.
5. Guardar los JSON en:
   - `export_json/facturacion_json/`

Nota:
- El JSON incluye `total_documentos` tomado de la tabla "Totales por documentos".

## Paso 1: citas base
Ejecutar:
```bash
python scripts/01_mercadeo_citas.py
```

Salida:
- Hoja `Datos Mercadeo` en el maestro.
- Columnas activas:
  - `id_registro, Numero_Documento, Paciente, Municipio, Convenio, Fecha, Mes, Semana, Agente, Profesional_Asignado, Especialidad, Canal_Captacion, Tipo_Cita, Programados, Asistido, Efectivo`

## Paso 2: pagos sobre maestro
Ejecutar:
```bash
python scripts/02_mercadeo_pagos.py
```

Reglas principales:
- Match por `doc_norm + Fecha_dia`.
- Excluye `fac_anulada == SI`.
- Excluye `forma_pago` con `anticipo/anticpo`.
- Dedup por clave de pago.

## Paso 3: facturacion desde JSON
Ejecutar:
```bash
python scripts/03_facturacion_json.py
```

Genera/actualiza hojas:
- `facturacion`
- `facturacion_control`

Columnas actuales de `facturacion`:
- `Fecha, Ano, Mes, Semana, Tipo_factura, Tipo_Doc, Paciente, Recaudo (venta dia), Total_Documentos_JSON, Total_Listado_JSON`

Control aplicado por dia:
- compara `sum(listado_pagos.valor)` vs `total_documentos`;
- si hay diferencia positiva, busca exclusion automatica;
- deja trazabilidad en `facturacion_control`.

## Normalizacion de documento (scripts 01/02)
Regla base:
1. limpiar espacios y simbolos;
2. resolver notacion cientifica;
3. quitar sufijo `.0`;
4. si tiene mas de 11 digitos: conservar ultimos 11;
5. si queda en 11 digitos:
   - inicia con `1`: quitar ultimo digito;
   - en otro caso: quitar primer digito;
6. si tiene menos de 10 digitos: conservar.

## Semanas clinicas 2026 (script 03)
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

Nota operativa:
- Abril 2026 queda sujeto a ajuste con gerencia.
