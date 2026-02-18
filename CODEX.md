# CODEX.md

## Project Snapshot
ETL pipeline for Dentos Excel files. Consolidates appointments, payments, and sales into a monthly master:
`excel_generado/formato_odontologia_[MES].xlsx`.

Match key used across scripts:
- `doc_norm + Fecha_dia`

## Run Order
```bash
python scripts/01_mercadeo_citas.py
python scripts/02_mercadeo_pagos.py
python "scripts/prueba _informe_ventas.py"
```

## Input / Output Folders
- `excel_dentos/01_citas_detallado/`
- `excel_dentos/02_citas_con_pagos/`
- `excel_dentos/prueba_informe_ventas/`
- `excel_generado/`

## Script Roles
- `scripts/01_mercadeo_citas.py`
  - Builds/updates master from detailed appointments.
  - Sets core fields (id, paciente, fecha, semana, especialidad, etc.).

- `scripts/02_mercadeo_pagos.py`
  - Enriches master with payments.
  - Writes: `Recaudo (venta dia)`, `Efectivo`, `Factura`, `Metodo_Pago`, `Asesor_Comercial`.
  - Filters enabled:
    - exclude `fac_anulada == SI`
    - exclude `forma_pago` with `anticipo`/`anticpo`
  - Dedup key:
    - `doc_norm + Fecha_dia + factura + forma_pago + valor_pagado_num`
  - Current business rule:
    - if `factura` is empty: do NOT write `Recaudo`, but can keep `Efectivo`.

- `scripts/prueba _informe_ventas.py`
  - Reads sales report (radiografia only).
  - Updates `Recaudo (venta dia)` when empty.

## Document Normalization (Critical)
Applied in all scripts:
1. trim spaces and symbols, handle scientific notation
2. remove `.0` suffix
3. if digits > 11: keep last 11
4. if digits == 11:
   - starts with `1` -> remove last digit
   - otherwise -> remove first digit
5. if digits < 10: keep as-is

## Monthly Maintenance
- Update `WEEK_RANGES` per month in scripts using weekly labels.
- Validate totals by day before running full month.

## Quick Validation Checklist
- Inputs are in correct folders.
- Date formats parse correctly.
- `doc_norm` match rate is acceptable.
- No unexpected growth of rows in master.
- Daily totals (manual vs script) are aligned.
