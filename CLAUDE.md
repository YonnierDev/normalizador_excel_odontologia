# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ETL pipeline (Python/pandas) that consolidates Dentos dental clinic data (appointments from Excel + invoicing from JSON) into a standardized monthly master report at `excel_generado/formato_odontologia_[MES].xlsx`.

`excelFormatos/` is the **git repository root** (single branch). All code and data lives here.

### Invoicing / Billing Logic
- **Facturación is tracked per week** for most specialties.
- **Odontología General is reported monthly** — data is captured at the month level, not per session.
- Data is currently updated through **week 2 of February 2026**.

## Run Commands

Scripts must run sequentially from `excelFormatos/`:

```bash
python scripts/01_mercadeo_citas.py
python scripts/02_mercadeo_pagos.py
python scripts/03_facturacion_json.py
```

No tests exist. No `requirements.txt`—dependencies are **pandas** and **openpyxl**.

## Architecture

Three active scripts execute in order:

1. **01_mercadeo_citas.py** — Reads `excel_dentos/01_citas_detallado/`. Builds/updates master sheet `Datos Mercadeo` from detailed appointments. Sets core fields (id, paciente, fecha, semana, especialidad). Maps specialties and assigns weekly labels via `WEEK_RANGES`.
2. **02_mercadeo_pagos.py** — Reads `excel_dentos/02_citas_con_pagos/`. Enriches `Datos Mercadeo` with exact invoiced values: `Recaudo`, `Efectivo`, `Factura`, `Metodo_Pago`, `Asesor_Comercial`. Has configurable flags (`APPLY_FAC_ANUL`, `APPLY_ANTICIPO`, `APPLY_DEDUPE`, `EXPAND_MASTER`) and debug filters (`DEBUG_DAY`, `DEBUG_DOC`).
3. **03_facturacion_json.py** — Reads **all** JSON files from `export_json/facturacion_json/`. Writes two new sheets into the master Excel without touching `Datos Mercadeo`:
   - `facturacion`: one row per payment with columns: `Fecha, Año, Mes, Semana, Tipo_factura, Tipo_Doc, Paciente, Recaudo (venta dia), Total_Documentos_JSON, Total_Listado_JSON`
   - `facturacion_control`: one row per day with reconciliation status comparing listado sum vs `total_documentos` from JSON metadata. Exclusion states: `OK`, `EXCLUIDO_POR_DIFERENCIA`, `DIFERENCIA_SIN_MATCH`, `LISTADO_MENOR_A_TOTAL`, `SIN_TOTAL_DOCUMENTOS`.
   - Uses `WEEK_RANGES_BY_MONTH` (multi-month dict covering Jan–Apr 2026) — no monthly manual update needed until May 2026.
   - **Abril 2026 is provisional** — validate week ranges with gerencia before monthly close.
   - Patient matching is by name (`tercero`) — JSON files have no document number (cédula).

**Inactive scripts:**
- `prueba _informe_ventas.py` — Experimental prototype (radiografia only). Not in use.
- `03_anticipos.py` — Replaced by `03_facturacion_json.py`. Empty placeholder, ignore.

**Match key (scripts 01 & 02):** `doc_norm + Fecha_dia` (normalized document number + date).

## Document Normalization (Critical Business Logic)

Applied identically in scripts 01 and 02—keep synchronized:

1. Trim spaces/symbols, handle scientific notation, remove `.0` suffix
2. If digits > 11 → keep last 11
3. If digits == 11 → starts with `1`: remove last digit; otherwise: remove first digit
4. If digits < 10 → keep as-is

## Monthly Maintenance

`WEEK_RANGES` is hard-coded in scripts 01 and 02 and **must be updated for each new month**. Example:

```python
WEEK_RANGES = {
    'SEMANA1': (date(2026, 2, 2), date(2026, 2, 7)),
    'SEMANA2': (date(2026, 2, 9), date(2026, 2, 14)),
    ...
}
```

Script 03 uses `WEEK_RANGES_BY_MONTH` (multi-month dict) — update only when adding a new month beyond April 2026.

## JSON Payment Export System

Daily payment data is extracted from DentOS via a **Greasemonkey userscript running in Firefox**:

- **Script:** `export_json/script_web/exportacion_pagos_dentos.js`
- **Runs on:** `https://previred.clinicos.co/cuadrecaja/` (DentOS "Cuadre de caja" module)
- **Adds two buttons** to the DentOS UI:
  - `Exportar dia` — exports current day's Listado de pagos as one JSON
  - `Exportar semana` — iterates working days: Mostrar → Detalles → wait → scroll → export per day
- **Output:** One JSON file per working day → `export_json/facturacion_json/listado_pagos_YYYY-MM-DD.json`

### JSON structure per file:
```json
{
  "fuente": "DentOS/cuadrecaja",
  "fecha_iso": "2026-02-03",
  "mes_tag": "2026-02",
  "registros": 16,
  "total_valor": 4117000,
  "total_documentos": 4117000,
  "listado_pagos": [
    {
      "codigo_tipo_doc": "FAC-588(+)",
      "tipo_doc": "Factura de contado",
      "fecha": "03/02/2026",
      "tercero": "NOMBRE PACIENTE",
      "valor": 44000,
      "valor_raw": "44,000.00"
    }
  ]
}
```

- `codigo_tipo_doc` prefixes: `FAC-` = invoice (Factura de contado), `REC-` = cash receipt (Recibo de caja)
- `tercero` = patient full name (no document number — matching must be done by name)
- `total_documentos` = sum from DentOS "Totales por documentos" table — used for reconciliation in `facturacion_control`
- These JSONs are the **source of truth for exact invoiced amounts**

## Repository Structure

```
excelFormatos/               ← git repo root
├── scripts/
│   ├── 01_mercadeo_citas.py
│   ├── 02_mercadeo_pagos.py
│   └── 03_facturacion_json.py
├── excel_dentos/
│   ├── 01_citas_detallado/
│   └── 02_citas_con_pagos/
├── export_json/
│   ├── facturacion_json/    ← daily JSON files
│   └── script_web/
│       └── exportacion_pagos_dentos.js
├── excel_generado/          ← output Excel files
├── .gitignore               ← excludes __pycache__/, *.py[cod]
├── CLAUDE.md
├── CODEX.md
└── INSTRUCCIONES.md
```

## Key Conventions

- All user-facing text and documentation is in **Spanish**.
- Column matching uses fuzzy regex-based detection to handle varying Excel column names.
- The master output sheet is named `'Datos Mercadeo'` and has 33 columns.
- Output files auto-version with `.1`, `.2` suffixes if duplicates exist.
- `INSTRUCCIONES.md` contains the canonical user documentation.
- `CODEX.md` contains architecture decisions and operational notes for developers.
