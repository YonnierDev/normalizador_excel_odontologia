# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
from datetime import datetime
import re
import unicodedata

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / 'excel_dentos' / '02_citas_con_pagos'
OUTPUT_DIR = BASE_DIR / 'excel_generado'
EXPECTED_RECAUDO_ROWS = 25  # Ajusta o pon None para desactivar la validación
# Filtros por etapas (actívalos uno a uno para depurar)
APPLY_FAC_ANUL = True       # fac_anulada == NO
APPLY_ANTICIPO = True       # excluir forma_pago con "anticipo"
APPLY_DEDUPE = False        # deduplicar por clave

# Debug opcional: filtra y muestra solo un día (YYYY-MM-DD). Deja en None para modo normal.
DEBUG_DAY = None

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
    s = str(doc).strip()
    return s.split('.')[0] # Quitar decimales si vienen como float

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

def main():
    try:
        master_path = _find_master()
        input_path = _find_input('')
        
        print(f"Leyendo Maestro: {master_path.name}")
        print(f"Leyendo Pagos: {input_path.name}")

        df_master = pd.read_excel(master_path)
        df_pagos = pd.read_excel(input_path)

        # Normalizar documentos para el merge
        df_master['doc_norm'] = df_master['Numero_Documento'].apply(normalize_doc)
        df_pagos['doc_norm'] = df_pagos['documento'].apply(normalize_doc)
        
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

        # Dedupe por las columnas solicitadas (incluye documento)
        dedup_subset = ['doc_norm', 'Fecha_dia', 'valor_pagado_num']
        if factura_col:
            # Mantener factura vacía como valor válido (no se elimina)
            df_pagos[factura_col] = df_pagos[factura_col].astype(str).str.strip()
            dedup_subset.append(factura_col)
        if forma_col:
            df_pagos[forma_col] = df_pagos[forma_col].astype(str).str.strip()
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

        # Debug: mostrar conteos
        if DEBUG_DAY:
            print(f"[DEBUG] Fecha filtro: {DEBUG_DAY}")
            print(f"[DEBUG] Pagos leídos: {len(df_pagos)}")
            print(f"[DEBUG] Pagos después dedupe: {len(df_pagos_clean)}")

        # 2. Agrupar pagos por Paciente y Fecha (Día) SIN SUMAR
        # Clave: (doc_norm, fecha_date) -> {pagos: [{valor, facturador, factura_vacia}], facturadores: set()}
        daily_payments = {}
        for _, row in df_pagos_clean.iterrows():
            doc = row['doc_norm']
            if not doc:
                continue

            if pd.isna(row['Fecha_dt']):
                continue
            day_key = (doc, row['Fecha_dia'])

            valor = row.get('valor_pagado_num', 0)
            try:
                valor = float(valor)
            except:
                valor = 0

            if day_key not in daily_payments:
                daily_payments[day_key] = {'pagos': [], 'facturadores': set()}

            if valor > 0:
                factura_val = ''
                if factura_col:
                    factura_val = row.get(factura_col, '')
                factura_vacia = str(factura_val).strip() == ''
                daily_payments[day_key]['pagos'].append({
                    'valor': valor,
                    'factura_vacia': factura_vacia,
                    'facturador': row.get(facturador_col, '') if facturador_col else '',
                })
            if facturador_col:
                fact_val = row.get(facturador_col, '')
                if pd.notna(fact_val) and str(fact_val).strip():
                    daily_payments[day_key]['facturadores'].add(str(fact_val).strip())

        # 3. Asignar al Maestro
        # Convertir columna a objeto para evitar FutureWarning si estaba vacía (float/NaN)
        df_master['Asesor_Comercial'] = df_master['Asesor_Comercial'].astype(object)
        
        updates_asesor = 0
        updates_efectivo = 0
        updates_recaudo = 0 # Nuevo contador

        # Expandir maestro si faltan filas para pagos con factura vacía
        key_to_rows = {}
        for idx, row in df_master.iterrows():
            doc = row['doc_norm']
            if pd.isna(row['Fecha_dt']):
                continue
            key = (doc, row['Fecha_dt'].date())
            key_to_rows.setdefault(key, []).append(idx)

        rows_to_append = []
        for key, info in daily_payments.items():
            if key not in key_to_rows:
                continue
            rows = key_to_rows[key]
            needed = len(info['pagos']) - len(rows)
            if needed > 0:
                # Solo crear filas extra si hay pagos con factura vacía
                extra_pagos = [p for p in info['pagos'] if p['factura_vacia']]
                if extra_pagos:
                    template = df_master.loc[rows[0]].copy()
                    for _ in range(min(needed, len(extra_pagos))):
                        rows_to_append.append(template.copy())

        if rows_to_append:
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
                    # Asesor_Comercial: solo cuando se asigna recaudo
                    if info['facturadores']:
                        df_master.at[idx, 'Asesor_Comercial'] = " / ".join(sorted(info['facturadores']))
                        updates_asesor += 1

        # Limpieza de columnas temporales
        df_master.drop(columns=['doc_norm', 'Fecha_dt'], inplace=True)
        
        # Rellenar vacíos en Efectivo con 0
        df_master['Efectivo'] = df_master['Efectivo'].fillna(0).astype(int)
        
        # Guardar sin formato de moneda (valores crudos)
        output_path = master_path
        df_master.to_excel(output_path, index=False)
        
        print("Proceso completado.")
        print(f"Filas actualizadas con Asesor Comercial: {updates_asesor}")
        print(f"Filas marcadas como Efectivo: {updates_efectivo}")
        print(f"Filas con Recaudo asignado (único por día): {updates_recaudo}")
        print(f"Archivo actualizado: {output_path}")

        # Validación de conteo esperado
        if EXPECTED_RECAUDO_ROWS is not None:
            recaudo_count = df_master['Recaudo (venta día)'].notna().sum()
            if recaudo_count != EXPECTED_RECAUDO_ROWS:
                raise ValueError(
                    f"Recaudo filas esperadas: {EXPECTED_RECAUDO_ROWS}, encontradas: {recaudo_count}"
                )

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
