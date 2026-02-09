# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
from datetime import datetime
import re
import unicodedata

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / 'excel_dentos' / '02_citas_con_pagos'
OUTPUT_DIR = BASE_DIR / 'excel_generado'
EXPECTED_RECAUDO_ROWS = None  # Desactivado: ahora se reporta sin validar fijo
# Filtros por etapas (actívalos uno a uno para depurar)
APPLY_FAC_ANUL = True       # fac_anulada == NO
APPLY_ANTICIPO = True       # excluir forma_pago con "anticipo"
APPLY_DEDUPE = True         # deduplicar por clave
EXPAND_MASTER = True        # crear filas nuevas si faltan pagos (solo caso factura igual con forma/valor distinto)

# Debug opcional: filtra y muestra solo un día (YYYY-MM-DD). Deja en None para modo normal.
DEBUG_DAY = None
DEBUG_DOC = None

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

def _week_from_date(d):
    if not d:
        return pd.NA
    for name, (start, end) in WEEK_RANGES.items():
        if start <= d <= end:
            return name
    return pd.NA

# Busca el primer archivo de pagos
def _find_input(prefix: str) -> Path:
    candidates = []
    if not INPUT_DIR.exists():
         raise FileNotFoundError(f"El directorio {INPUT_DIR} no existe.")
    
    for f in INPUT_DIR.glob('*.xlsx'):
        name = f.name.lower()
        # Se asume que el archivo contiene 'reporte' o algo, pero usaremos el prefijo dado por el usuario si aplica
        # El usuario no especificó prefijo exacto, pero dijo "excel que vamos a poner en... 02_citas_con_pagos"
        # Asumiremos cualquier xlsx por ahora o filtramos.
        # "las siguientes columnas del excel que vamos a poner en..."
        candidates.append(f)
    if not candidates:
        raise FileNotFoundError(f"No se encontró ningún archivo .xlsx en {INPUT_DIR}")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]

# Busca el archivo maestro más reciente en outputs
def _find_master() -> Path:
    candidates = []
    if not OUTPUT_DIR.exists():
        raise FileNotFoundError(f"No existe el directorio {OUTPUT_DIR}. Ejecuta el script 01 primero.")

    for f in OUTPUT_DIR.glob('formato_odontologia_*.xlsx'):
        candidates.append(f)
    
    if not candidates:
        raise FileNotFoundError("No se encontró el archivo maestro formato_odontologia_*.xlsx en excel_generado")
    
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]

def normalize_doc(doc):
    if pd.isna(doc):
        return ''
    # Manejar numéricos y notación científica correctamente
    if isinstance(doc, (int, float)):
        try:
            return str(int(round(doc)))
        except Exception:
            return str(doc).strip()
    s = str(doc).strip()
    if not s:
        return ''
    # Normalizar separadores y limpiar
    s = s.replace(' ', '')
    # Si viene con coma decimal, convertir a punto
    if ',' in s and '.' not in s:
        s = s.replace(',', '.')
    # Limpiar caracteres no numéricos relevantes
    s = re.sub(r'[^0-9eE\+\-\.]', '', s)
    # Notación científica
    if 'e' in s.lower():
        try:
            from decimal import Decimal
            return str(int(Decimal(s)))
        except Exception:
            pass
    # Decimal simple
    if re.match(r'^\d+\.0+$', s):
        return s.split('.')[0]
    # Otros casos con punto
    if '.' in s:
        try:
            return str(int(float(s)))
        except Exception:
            return s.split('.')[0]
    # Si tiene más de 11 dígitos, recortar a 11 (nos quedamos con los últimos 11)
    if re.match(r'^\d{12,}$', s):
        s = s[-11:]
    # Si quedó con 11 dígitos:
    # - Si empieza con 1: eliminar el último dígito
    # - Si no empieza con 1: eliminar el primer dígito
    if re.match(r'^\d{11}$', s):
        if s.startswith('1'):
            return s[:-1]
        return s[1:]
    return s

def _norm_col(name: str) -> str:
    if name is None:
        return ''
    s = str(name).strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'[^a-z0-9]', '', s)
    return s

def _find_col(df, candidates):
    norm_map = { _norm_col(c): c for c in df.columns }
    for cand in candidates:
        key = _norm_col(cand)
        if key in norm_map:
            return norm_map[key]
    return None

def _parse_valor_pagado(val):
    if pd.isna(val):
        return 0
    s = str(val).strip()
    if not s:
        return 0
    # Quitar símbolos y espacios
    s = re.sub(r'[^0-9\.,\-]', '', s)
    if not s:
        return 0
    # Si tiene coma, asumir coma decimal y punto miles
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    else:
        # Sin coma: si termina en .0/.00 lo tratamos como decimal y quitamos solo la parte decimal
        if re.match(r'^\d+\.0+$', s):
            s = s.split('.')[0]
        else:
            # Sin coma: asumir puntos como miles
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
        input_path = _find_input('')
        
        print(f"Leyendo Maestro: {master_path.name}")
        print(f"Leyendo Pagos: {input_path.name}")

        df_master = pd.read_excel(master_path)
        df_pagos = pd.read_excel(input_path)

        # Asegurar columnas nuevas en maestro
        if 'Factura' not in df_master.columns:
            df_master['Factura'] = pd.NA
        if 'Metodo_Pago' not in df_master.columns:
            df_master['Metodo_Pago'] = pd.NA
        if 'Asesor_Comercial' not in df_master.columns:
            df_master['Asesor_Comercial'] = pd.NA
        # Forzar dtype object para evitar warnings al asignar texto
        for col in ['Factura', 'Metodo_Pago', 'Asesor_Comercial']:
            df_master[col] = df_master[col].astype(object)

        # Usar documento normalizado para el match
        df_master['doc_norm'] = df_master['Numero_Documento'].apply(normalize_doc)
        df_pagos['doc_norm'] = df_pagos['documento'].apply(normalize_doc)
        # Mantener paciente solo para logs
        df_master['paciente_raw'] = df_master['Paciente'].astype(str).str.strip()
        df_pagos['paciente_raw'] = df_pagos['paciente'].astype(str).str.strip()

        # Log de documentos corregidos (regla 11 dígitos -> 10)
        facturador_col = _find_col(df_pagos, ['facturador', 'asesor_comercial', 'asesor comercial'])
        df_pagos['doc_raw_str'] = df_pagos['documento'].astype(str).str.strip()
        df_pagos['doc_raw_digits'] = df_pagos['doc_raw_str'].str.replace(r'\D', '', regex=True)
        doc_changes = df_pagos[df_pagos['doc_raw_digits'].str.len() == 11].copy()
        if not doc_changes.empty:
            cols = ['doc_raw_str', 'doc_norm', 'paciente_raw']
            if facturador_col:
                cols.append(facturador_col)
            unique_changes = doc_changes[cols].drop_duplicates()
            print(f"[LOG] Documentos corregidos (11->10): {len(unique_changes)}")
            if facturador_col:
                counts = unique_changes[facturador_col].fillna('').astype(str).str.strip().value_counts()
                print("[LOG] Facturador con correcciones (Asesor_Comercial):")
                print(counts.to_string())
            print(unique_changes.head(20).to_string(index=False))
        
        # Convertir fechas para comparar
        # Asumiendo formato DD/MM/YYYY en maestro (es string según script 01)
        df_master['Fecha_dt'] = pd.to_datetime(df_master['Fecha'], format='%d/%m/%Y', errors='coerce')
        # Asumiendo fecha en pagos es datetime o string.
        df_pagos['Fecha_dt'] = pd.to_datetime(df_pagos['fecha'], errors='coerce')
        # Fecha sin hora para dedupe/agrupación por día
        df_pagos['Fecha_dia'] = df_pagos['Fecha_dt'].dt.date

        # Debug: filtrar solo un día si está configurado
        if DEBUG_DAY:
            debug_date = pd.to_datetime(DEBUG_DAY, errors='coerce')
            if pd.notna(debug_date):
                df_pagos = df_pagos[df_pagos['Fecha_dia'] == debug_date.date()].copy()
        # Debug: filtrar solo un documento si está configurado
        if DEBUG_DOC:
            df_pagos = df_pagos[df_pagos['documento'].astype(str).str.split('.').str[0].str.strip() == DEBUG_DOC].copy()

        # Normalizar valor_pagado a número (evita duplicados por formato)
        if 'valor_pagado' in df_pagos.columns:
            df_pagos['valor_pagado_num'] = df_pagos['valor_pagado'].apply(_parse_valor_pagado)
        else:
            df_pagos['valor_pagado_num'] = 0

        # Lógica de Actualización
        # 1. Filtrar y deduplicar pagos:
        # - fac_anulada: solo NO
        # - forma_pago: excluir "Descontar anticipo"
        # - Clave de pago: documento + fecha + factura + forma_pago + valor_pagado
        # - Si las columnas son idénticas, se deja una sola fila (no se duplica)
        factura_col = _find_col(df_pagos, ['factura', 'n_factura', 'numero_factura'])
        fac_anul_col = _find_col(df_pagos, ['fac_anul', 'fac_anulada', 'factura_anulada', 'factura anulada'])
        forma_col = _find_col(
            df_pagos,
            ['forma_pago', 'forma de pago', 'medio_pago', 'medio de pago', 'metodo_pago', 'metodo de pago', 'tipo_pago'],
        )

        # Excluir facturas anuladas (fac_anulada = SI)
        if APPLY_FAC_ANUL and fac_anul_col:
            fac_anul_norm = df_pagos[fac_anul_col].fillna('').astype(str).str.strip().str.upper()
            df_pagos = df_pagos[fac_anul_norm != 'SI'].copy()

        # Excluir forma_pago = "Descontar anticipo" (incluye variaciones/typos)
        if APPLY_ANTICIPO and forma_col:
            forma_norm = df_pagos[forma_col].fillna('').astype(str).str.lower().apply(_norm_col)
            is_anticipo = forma_norm.str.contains('anticipo') | forma_norm.str.contains('anticpo')
            df_pagos = df_pagos[~is_anticipo].copy()

        # Dedupe exacto por las 5 columnas:
        # fecha (día) + documento + factura + forma_pago + valor_pagado
        dedup_subset = ['doc_norm', 'Fecha_dia', 'valor_pagado_num']
        if factura_col:
            df_pagos[factura_col] = (
                df_pagos[factura_col]
                .fillna('')
                .astype(str)
                .str.strip()
                .replace({'nan': '', 'None': '', 'NONE': ''})
            )
            dedup_subset.append(factura_col)
        if forma_col:
            df_pagos[forma_col] = df_pagos[forma_col].astype(str)
            dedup_subset.append(forma_col)
        facturador_col = _find_col(df_pagos, ['facturador', 'asesor_comercial', 'asesor comercial'])
        if facturador_col:
            df_pagos[facturador_col] = df_pagos[facturador_col].astype(str).str.strip()
        if APPLY_DEDUPE:
            df_pagos_clean = df_pagos.drop_duplicates(
                subset=[c for c in dedup_subset if c in df_pagos.columns]
            )
        else:
            df_pagos_clean = df_pagos.copy()

        # (logs removidos)

        # Limpiar valores previos en maestro para las fechas/documentos que vamos a recalcular
        keys = set(zip(df_pagos_clean['doc_norm'], df_pagos_clean['Fecha_dia']))
        df_master['Fecha_dia'] = df_master['Fecha_dt'].dt.date
        mask = df_master.apply(lambda r: (r['doc_norm'], r['Fecha_dia']) in keys, axis=1)
        cols_clear = ['Recaudo (venta día)', 'Asesor_Comercial', 'Factura', 'Metodo_Pago', 'Efectivo']
        for col in cols_clear:
            if col in df_master.columns:
                df_master.loc[mask, col] = pd.NA

        # (logs removidos)

        # Debug: mostrar conteos
        if DEBUG_DAY:
            print(f"[DEBUG] Fecha filtro: {DEBUG_DAY}")
            print(f"[DEBUG] Pagos leídos: {len(df_pagos)}")
            print(f"[DEBUG] Pagos después dedupe: {len(df_pagos_clean)}")

        # 2. Agrupar pagos por Paciente y Fecha (Día) SIN SUMAR
        # Clave: (doc_norm, fecha_date) -> {pagos: [...], factura_counts: {factura: set((forma, valor))}}
        daily_payments = {}
        pagos_by_key = {}
        for _, row in df_pagos_clean.iterrows():
            doc = row['doc_norm']
            if not doc:
                continue

            if pd.isna(row['Fecha_dt']):
                continue
            day_key = (doc, row['Fecha_dia'])
            pagos_by_key.setdefault(day_key, []).append(row)

            valor = row.get('valor_pagado_num', 0)
            try:
                valor = float(valor)
            except:
                valor = 0

            if day_key not in daily_payments:
                daily_payments[day_key] = {'pagos': [], 'factura_counts': {}}

            if valor > 0:
                factura_val = ''
                if factura_col:
                    factura_val = row.get(factura_col, '')
                if pd.isna(factura_val) or str(factura_val).strip().lower() in ('nan', 'none'):
                    factura_val = ''
                factura_vacia = str(factura_val).strip() == ''
                forma_val = row.get(forma_col, '') if forma_col else ''
                daily_payments[day_key]['pagos'].append({
                    'valor': valor,
                    'factura_vacia': factura_vacia,
                    'facturador': row.get(facturador_col, '') if facturador_col else '',
                    'factura': str(factura_val).strip(),
                    'forma': str(forma_val).strip(),
                })
                # Track distinct (forma, valor) per factura
                factura_key = str(factura_val).strip()
                fv_set = daily_payments[day_key]['factura_counts'].setdefault(factura_key, set())
                fv_set.add((str(forma_val).strip(), valor))

        # 3. Asignar al Maestro
        # Convertir columna a objeto para evitar FutureWarning si estaba vacía (float/NaN)
        df_master['Asesor_Comercial'] = df_master['Asesor_Comercial'].astype(object)
        
        updates_asesor = 0
        updates_efectivo = 0
        updates_recaudo = 0 # Nuevo contador

        # Expandir maestro si faltan filas por:
        # - misma factura con forma/valor distintos
        # - pagos con factura vacía
        key_to_rows = {}
        for idx, row in df_master.iterrows():
            doc = row['doc_norm']
            if pd.isna(row['Fecha_dt']):
                continue
            key = (doc, row['Fecha_dt'].date())
            key_to_rows.setdefault(key, []).append(idx)

        rows_to_append = []

        # Log: documentos/fechas que no existen en el maestro
        missing_keys = []
        for key in daily_payments.keys():
            if key not in key_to_rows:
                missing_keys.append(key)
        if missing_keys:
            print(f"[LOG] Claves sin filas en maestro: {len(missing_keys)}")
            # Resumen por cédula (doc_norm) para revisar casos
            missing_docs = [k[0] for k in missing_keys if k and k[0]]
            if missing_docs:
                doc_counts = pd.Series(missing_docs).value_counts()
                print("[LOG] Cedulas sin match (conteo por doc):")
                print(doc_counts.head(50).to_string())
            samples = []
            for key in missing_keys:
                rows = pagos_by_key.get(key, [])
                if not rows:
                    continue
                r0 = rows[0]
                samples.append({
                    'doc_norm': key[0],
                    'fecha': key[1],
                    'paciente': str(r0.get('paciente', '')).strip(),
                })
            if samples:
                df_missing = pd.DataFrame(samples).drop_duplicates()
                print(df_missing.head(20).to_string(index=False))

        # Si no hay match en el maestro, agregar filas nuevas al final con datos mínimos
        rows_added_missing = 0
        if EXPAND_MASTER and missing_keys:
            next_id = _next_id_start(df_master)
            for key in missing_keys:
                pagos_list = pagos_by_key.get(key, [])
                for pago_row in pagos_list:
                    next_id += 1
                    new_row = {col: pd.NA for col in df_master.columns}
                    new_row['id_registro'] = f"ODON-{str(next_id).zfill(7)}"
                    new_row['Numero_Documento'] = key[0]
                    pac = str(pago_row.get('paciente', '')).strip()
                    new_row['Paciente'] = pac if pac else pd.NA
                    dt = pd.to_datetime(key[1], errors='coerce')
                    if pd.notna(dt):
                        new_row['Fecha'] = dt.strftime('%d/%m/%Y')
                        new_row['Año'] = dt.year
                        new_row['Mes'] = MONTH_MAP.get(dt.month, pd.NA)
                    new_row['Semana'] = _week_from_date(key[1])
                    new_row['doc_norm'] = key[0]
                    new_row['Fecha_dt'] = pd.to_datetime(key[1], errors='coerce')
                    new_row['Fecha_dia'] = key[1]
                    rows_to_append.append(new_row)
                    rows_added_missing += 1

        for key, info in daily_payments.items():
            if key not in key_to_rows:
                continue
            rows = key_to_rows[key]
            needed = len(info['pagos']) - len(rows)
            if needed > 0:
                # Expandir si hay facturas con múltiples (forma,valor) o pagos con factura vacía
                has_multi_for_factura = any(len(v) > 1 for v in info['factura_counts'].values())
                has_empty_factura = any(p.get('factura_vacia') for p in info['pagos'])
                if has_multi_for_factura or has_empty_factura:
                    template = df_master.loc[rows[0]].copy()
                    for _ in range(needed):
                        rows_to_append.append(template.copy())

        rows_added = len(rows_to_append)
        if EXPAND_MASTER and rows_to_append:
            df_master = pd.concat([df_master, pd.DataFrame(rows_to_append)], ignore_index=True)
            # Recalcular índice de filas por clave después de expandir
            key_to_rows = {}
            for idx, row in df_master.iterrows():
                doc = row['doc_norm']
                if pd.isna(row['Fecha_dt']):
                    continue
                key = (doc, row['Fecha_dt'].date())
                key_to_rows.setdefault(key, []).append(idx)

        for idx, row in df_master.iterrows():
            doc = row['doc_norm']
            if pd.isna(row['Fecha_dt']):
                continue
            fecha_cita_date = row['Fecha_dt'].date()
            key = (doc, fecha_cita_date)

            if key in daily_payments:
                info = daily_payments[key]

                # Recaudo: asignar un pago por fila (sin sumar)
                if info['pagos']:
                    pago = info['pagos'].pop(0)
                    valor_asignado = pago['valor']
                    try:
                        valor_asignado = int(valor_asignado)
                    except Exception:
                        pass
                    df_master.at[idx, 'Recaudo (venta día)'] = valor_asignado
                    df_master.at[idx, 'Efectivo'] = 1
                    updates_recaudo += 1
                    updates_efectivo += 1
                    # Factura y Metodo_Pago del pago asignado
                    df_master.at[idx, 'Factura'] = pago.get('factura', '')
                    df_master.at[idx, 'Metodo_Pago'] = pago.get('forma', '')
                    # Asesor_Comercial: solo el facturador de este pago
                    fact_name = str(pago.get('facturador', '')).strip()
                    if fact_name:
                        df_master.at[idx, 'Asesor_Comercial'] = fact_name
                        updates_asesor += 1

        # Limpieza de columnas temporales
        df_master.drop(columns=['doc_norm', 'paciente_raw', 'Fecha_dt', 'Fecha_dia'], inplace=True)
        print(f"Filas sin Recaudo: {df_master['Recaudo (venta día)'].isna().sum()}")
        
        # Rellenar vacíos en Efectivo con 0
        df_master['Efectivo'] = df_master['Efectivo'].fillna(0).astype(int)
        
        # Guardar sin formato de moneda (valores crudos)
        output_path = master_path
        df_master.to_excel(output_path, index=False)
        
        print("Proceso completado.")
        print(f"Filas nuevas agregadas al maestro: {rows_added} (sin match: {rows_added_missing})")
        print(f"Filas con Recaudo asignado: {updates_recaudo}")
        print(f"Filas con Asesor_Comercial asignado: {updates_asesor}")
        print(f"Filas marcadas como Efectivo: {updates_efectivo}")
        print(f"Archivo actualizado: {output_path}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
