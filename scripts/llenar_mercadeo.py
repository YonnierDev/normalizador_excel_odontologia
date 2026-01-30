# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
from datetime import date
import re

SRC = Path('excel/Citas detallado enero 2026.xlsx')
DEST = Path('excel/Formato Odontología.xlsx')
OUTPUT = Path('excel/Formato Odontologia_Mercadeo_semana2.xlsx')
SHEET = 'Datos Mercadeo'

DEST_COLS = [
    'id_registro', 'Numero_Documento', 'Paciente', 'Municipio', 'Convenio', 'Fecha',
    'Año', 'Mes', 'Semana', 'Agente', 'Profesional_Asignado', 'Especialidad',
    'Canal_Captacion', 'Tipo_Cita', 'Programados', 'Asistido', 'Efectivo',
    'cotizacion', 'Admisionado', 'Admisión_Efectiva', 'Asesor_Comercial',
    'Odontologo_Venta', 'Venta_Primer_Pago', 'Cartera (2do pago)',
    'Recaudo (venta día)', 'Tratamiento (Venta total de cotizado)',
    'Valor ejecutado', 'Total venta (Efectivo + cotización)'
]

def load_source():
    src = pd.read_excel(SRC)
    src['Fecha'] = pd.to_datetime(src['fecha'], errors='coerce')
    mask = (src['Fecha'].dt.date >= date(2026, 1, 13)) & (src['Fecha'].dt.date <= date(2026, 1, 17))
    src = src.loc[mask].copy()

    name_cols = ['nombre1', 'nombre2', 'apellido1', 'apellido2']
    src['Paciente'] = src[name_cols].fillna('').astype(str).agg(' '.join, axis=1)
    src['Paciente'] = src['Paciente'].str.replace(r'\s+', ' ', regex=True).str.strip()

    src['Numero_Documento'] = src['documento']
    src['Convenio'] = src['Tarifario'].fillna('PARTICULAR')
    src['Año'] = src['Fecha'].dt.year
    src['Mes'] = 'ENERO'
    src['Semana'] = 'SEMANA2'
    src['Agente'] = src['usuario']
    src['Profesional_Asignado'] = src['doctor']
    src['Especialidad'] = src['unidad']
    src['Canal_Captacion'] = src['sucursal']
    src['Tipo_Cita'] = src['tipocita']
    src['Programados'] = 1

    src['Asistido'] = src['asistio'].fillna('').str.upper().str.startswith('SI').astype(int)
    src['Efectivo'] = ((src['Asistido'] == 1) & (src['Tipo_Cita'].str.upper() != 'VALORACION')).astype(int)
    src['cotizacion'] = (src['Tipo_Cita'].str.upper() == 'VALORACION').astype(int)

    return src

def next_id_start(dest_df):
    nums = dest_df['id_registro'].astype(str).str.extract(r'(\d+)$')[0].dropna().astype(int)
    return nums.max() if not nums.empty else 0


def build_new_rows(src, start_from):
    n = len(src)
    ids = [f"ODON-{str(start_from + i + 1).zfill(7)}" for i in range(n)]
    src = src.copy()
    src['id_registro'] = ids

    for col in DEST_COLS:
        if col not in src.columns:
            src[col] = pd.NA

    return src[DEST_COLS]


def main():
    dest = pd.read_excel(DEST, sheet_name=SHEET)
    dest_keep = dest[dest['Semana'] != 'SEMANA2'].copy()

    src = load_source()
    start = next_id_start(dest)
    new_rows = build_new_rows(src, start)

    out = pd.concat([dest_keep, new_rows], ignore_index=True)
    out.to_excel(OUTPUT, sheet_name=SHEET, index=False)
    print(f"Generado: {OUTPUT} con {len(new_rows)} filas para SEMANA2")


if __name__ == '__main__':
    main()
