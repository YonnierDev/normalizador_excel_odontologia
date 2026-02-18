# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
from datetime import datetime
import re
import unicodedata

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / 'excel_dentos' / '03_informe_ventas'
OUTPUT_DIR = BASE_DIR / 'excel_generado'

MONTH_MAP = {
    1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
    5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
    9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE',
}

# Rango de semanas (actualiza aquí cuando cambie el mes)
WEEK_RANGES = {
    'SEMANA1': (datetime(2026, 2, 2).date(), datetime(2026, 2, 7).date()),
    'SEMANA2': (datetime(2026, 2, 9).date(), datetime(2026, 2, 14).date()),
    'SEMANA3': (datetime(2026, 2, 16).date(), datetime(2026, 2, 21).date()),
    'SEMANA4': (datetime(2026, 2, 23).date(), datetime(2026, 2, 28).date()),
}

# Columna destino en el maestro para el valor de ingreso_clinica
# Ajusta si necesitas otra columna.
TARGET_COL = 'Recaudo (venta día)'


def _week_from_date(d):
    if not d:
        return pd.NA
    for name, (start, end) in WEEK_RANGES.items():
        if start <= d <= end:
            return name
    return pd.NA


def _find_input(prefix: str = 'informe de ventas') -> Path:
    if not INPUT_DIR.exists():
        raise FileNotFoundError(f"El directorio {INPUT_DIR} no existe.")
    candidates = []
    for f in INPUT_DIR.glob('*.xlsx'):
        if f.name.lower().startswith(prefix.lower()):
            candidates.append(f)
    if not candidates:
        raise FileNotFoundError(
            f"No se encontró ningún archivo .xlsx que comience con '{prefix}' en {INPUT_DIR}"
        )
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _find_master() -> Path:
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError(f"No existe el directorio {OUTPUT_DIR}. Ejecuta el script 01 primero.")
    candidates = list(OUTPUT_DIR.glob('formato_odontologia_*.xlsx'))
    if not candidates:
        raise FileNotFoundError("No se encontró formato_odontologia_*.xlsx en excel_generado")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _norm_col(name: str) -> str:
    if name is None:
        return ''
    s = str(name).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def _norm_text(txt: str) -> str:
    if pd.isna(txt):
        return ''
    s = str(txt).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s)
    return s


def _find_col(df, candidates):
    norm_map = {_norm_col(c): c for c in df.columns}
    for cand in candidates:
        key = _norm_col(cand)
        if key in norm_map:
            return norm_map[key]
    return None


def normalize_doc(doc):
    if pd.isna(doc):
        return ''
    if isinstance(doc, (int, float)):
        try:
            return str(int(round(doc)))
        except Exception:
            return str(doc).strip()
    s = str(doc).strip()
    if not s:
        return ''
    s = s.replace(' ', '')
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')
    s = re.sub(r'[^0-9eE\+\-\.]', '', s)
    if 'e' in s.lower():
        try:
            from decimal import Decimal
            return str(int(Decimal(s)))
        except Exception:
            pass
    if re.match(r'^\d+\.0+$', s):
        return s.split('.')[0]
    if '.' in s:
        try:
            return str(int(float(s)))
        except Exception:
            return s.split('.')[0]
    if re.match(r'^\d{12,}$', s):
        s = s[-11:]
    if re.match(r'^\d{11}$', s):
        if s.startswith('1'):
            return s[:-1]
        return s[1:]
    return s


def _parse_val(val):
    if pd.isna(val):
        return 0
    s = str(val).strip()
    if not s:
        return 0
    s = re.sub(r'[^0-9\.,\-]', '', s)
    if not s:
        return 0
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        if re.match(r'^\d+\.0+$', s):
            s = s.split('.')[0]
        else:
            s = s.replace('.', '')
    try:
        return int(float(s))
    except Exception:
        return 0


def _next_id_start(df):
    if 'id_registro' not in df.columns:
        return 0
    nums = df['id_registro'].astype(str).str.extract(r'(\d+)$')[0].dropna()
    if nums.empty:
        return 0
    return nums.astype(int).max()


def main():
    try:
        master_path = _find_master()
        input_path = _find_input()
        print(f"Leyendo Maestro: {master_path.name}")
        print(f"Leyendo Informe Ventas: {input_path.name}")

        df_master = pd.read_excel(master_path)
        df_src = pd.read_excel(input_path)

        # Columnas fuente
        fecha_col = _find_col(df_src, ['fechaop', 'fecha_op', 'fecha'])
        concepto_col = _find_col(df_src, ['concepto'])
        doc_col = _find_col(df_src, ['documento', 'num_documento', 'num_doc', 'cedula'])
        pac_col = _find_col(df_src, ['nombre_paciente', 'paciente'])
        doctor_col = _find_col(df_src, ['nombre_doctor', 'doctor'])
        ingreso_col = _find_col(df_src, ['ingreso_clinica', 'ingreso clinica'])

        missing = [c for c in [fecha_col, concepto_col, doc_col, pac_col, doctor_col, ingreso_col] if c is None]
        if missing:
            raise ValueError("No se encontraron todas las columnas requeridas en el informe de ventas.")

        # Filtrar por concepto que contenga RADIOGRAFIA
        concepto_norm = df_src[concepto_col].fillna('').astype(str).map(_norm_text)
        df_src = df_src[concepto_norm.str.contains('radiografia', na=False)].copy()

        # Fechas y doc
        df_src['Fecha_dt'] = pd.to_datetime(df_src[fecha_col], errors='coerce')
        df_src['Fecha_dia'] = df_src['Fecha_dt'].dt.date
        df_src['doc_norm'] = df_src[doc_col].apply(normalize_doc)
        df_src['ingreso_num'] = df_src[ingreso_col].apply(_parse_val)

        # Dedupe suave para evitar duplicados exactos
        df_src['concepto_norm'] = concepto_norm
        df_src = df_src.drop_duplicates(subset=['doc_norm', 'Fecha_dia', 'concepto_norm', 'ingreso_num'])

        # Preparar maestro
        df_master['doc_norm'] = df_master['Numero_Documento'].apply(normalize_doc)
        df_master['Fecha_dt'] = pd.to_datetime(df_master['Fecha'], format='%d/%m/%Y', errors='coerce')
        df_master['Fecha_dia'] = df_master['Fecha_dt'].dt.date

        # Crear columna destino si no existe
        if TARGET_COL not in df_master.columns:
            df_master[TARGET_COL] = pd.NA

        # Índice por clave
        key_to_rows = {}
        for idx, row in df_master.iterrows():
            if pd.isna(row['Fecha_dt']):
                continue
            key = (row['doc_norm'], row['Fecha_dt'].date())
            key_to_rows.setdefault(key, []).append(idx)

        # Agrupar ventas por clave
        ventas_by_key = {}
        for _, row in df_src.iterrows():
            if not row['doc_norm'] or pd.isna(row['Fecha_dt']):
                continue
            key = (row['doc_norm'], row['Fecha_dia'])
            ventas_by_key.setdefault(key, []).append(row)

        rows_to_append = []
        next_id = _next_id_start(df_master)
        for key, ventas in ventas_by_key.items():
            if key not in key_to_rows:
                # crear filas nuevas al final
                for v in ventas:
                    next_id += 1
                    new_row = {col: pd.NA for col in df_master.columns}
                    new_row['id_registro'] = f"ODON-{str(next_id).zfill(7)}"
                    new_row['Numero_Documento'] = key[0]
                    pac = str(v[pac_col]).strip()
                    new_row['Paciente'] = pac if pac else pd.NA
                    dt = v['Fecha_dt']
                    if pd.notna(dt):
                        new_row['Fecha'] = dt.strftime('%d/%m/%Y')
                        new_row['Año'] = dt.year
                        new_row['Mes'] = MONTH_MAP.get(dt.month, pd.NA)
                        new_row['Semana'] = _week_from_date(dt.date())
                    doc_name = str(v[doctor_col]).strip()
                    if doc_name:
                        new_row['Profesional_Asignado'] = doc_name
                    new_row[TARGET_COL] = v['ingreso_num'] if v['ingreso_num'] else pd.NA
                    new_row['doc_norm'] = key[0]
                    new_row['Fecha_dt'] = dt
                    new_row['Fecha_dia'] = key[1]
                    rows_to_append.append(new_row)
            else:
                rows = key_to_rows[key]
                needed = len(ventas) - len(rows)
                if needed > 0:
                    template = df_master.loc[rows[0]].copy()
                    for _ in range(needed):
                        rows_to_append.append(template.copy())

        rows_added = len(rows_to_append)
        if rows_to_append:
            df_master = pd.concat([df_master, pd.DataFrame(rows_to_append)], ignore_index=True)
            # Recalcular índice por clave
            key_to_rows = {}
            for idx, row in df_master.iterrows():
                if pd.isna(row['Fecha_dt']):
                    continue
                key = (row['doc_norm'], row['Fecha_dt'].date())
                key_to_rows.setdefault(key, []).append(idx)

        # Asignar valores al maestro (sin sobrescribir si ya hay valor)
        updates = 0
        updates_total = 0
        updates_rows = []
        for key, ventas in ventas_by_key.items():
            rows = key_to_rows.get(key, [])
            if not rows:
                continue
            for i, v in enumerate(ventas):
                if i >= len(rows):
                    break
                idx = rows[i]
                if pd.isna(df_master.at[idx, TARGET_COL]) or df_master.at[idx, TARGET_COL] == 0:
                    val = v['ingreso_num']
                    df_master.at[idx, TARGET_COL] = val
                    updates += 1
                    updates_total += int(val) if val else 0
                    updates_rows.append({
                        'doc': key[0],
                        'fecha': v['Fecha_dt'].strftime('%d/%m/%Y') if pd.notna(v['Fecha_dt']) else '',
                        'paciente': str(v[pac_col]).strip(),
                        'valor': int(val) if val else 0,
                    })
                doc_name = str(v[doctor_col]).strip()
                if doc_name and (pd.isna(df_master.at[idx, 'Profesional_Asignado']) or not str(df_master.at[idx, 'Profesional_Asignado']).strip()):
                    df_master.at[idx, 'Profesional_Asignado'] = doc_name

        # Limpiar columnas temporales
        df_master.drop(columns=['doc_norm', 'Fecha_dt', 'Fecha_dia'], inplace=True)

        output_path = master_path
        df_master.to_excel(output_path, index=False)

        print("Proceso completado.")
        print(f"Filas nuevas agregadas al maestro: {rows_added}")
        print(f"Filas actualizadas en {TARGET_COL}: {updates}")
        if updates_rows:
            print(f"Total agregado en {TARGET_COL}: {updates_total}")
            print("[DETALLE] Filas actualizadas (doc, fecha, paciente, valor):")
            print(pd.DataFrame(updates_rows).to_string(index=False))
        print(f"Archivo actualizado: {output_path}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()


