# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
from datetime import datetime
import re
import unicodedata

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / 'excel_dentos' / '02_citas_con_pagos'
OUTPUT_DIR = BASE_DIR / 'excel_generado'

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

        # Lógica de Actualización
        # 1. Deduplicar pagos:
        # - Para pagos normales con FACTURA: doc + fecha + factura + forma_pago + valor
        # - Si FACTURA viene vacía: NO deduplicar (se suman repetidos)
        # - Para forma_pago = "Descuento/Descontar de anticipo": se EXCLUYE del recaudo (no suma)
        # Esto evita duplicar el mismo pago cuando hay factura, pero permite sumar repetidos sin factura.
        factura_col = _find_col(df_pagos, ['factura', 'n_factura', 'numero_factura'])
        forma_col = _find_col(
            df_pagos,
            ['forma_pago', 'forma de pago', 'medio_pago', 'medio de pago', 'metodo_pago', 'metodo de pago', 'tipo_pago'],
        )

        # Separar anticipo si existe columna de forma de pago
        if forma_col:
            forma_norm = df_pagos[forma_col].fillna('').astype(str).str.lower()
            forma_norm = forma_norm.apply(_norm_col)
            is_anticipo = forma_norm.isin({
                _norm_col('Descuento de anticipo'),
                _norm_col('Descontar de anticipo'),
            })
        else:
            is_anticipo = pd.Series([False] * len(df_pagos), index=df_pagos.index)

        df_normal = df_pagos[~is_anticipo].copy()
        df_anticipo = df_pagos[is_anticipo].copy()

        # Dedupe normal:
        # - Si hay factura: dedup por doc+fecha+factura+forma+valor
        # - Si no hay factura: NO se deduplica (se mantienen repetidos)
        if factura_col:
            factura_series = df_normal[factura_col].fillna('').astype(str).str.strip()
            has_factura = factura_series != ''

            df_with_factura = df_normal[has_factura].copy()
            df_no_factura = df_normal[~has_factura].copy()

            dedup_subset_normal = ['doc_norm', 'Fecha_dt', 'valor_pagado']
            dedup_subset_normal.append(factura_col)
            if forma_col:
                dedup_subset_normal.append(forma_col)
            df_with_factura = df_with_factura.drop_duplicates(
                subset=[c for c in dedup_subset_normal if c in df_with_factura.columns]
            )

            # Sin factura: se dejan todos los registros (no dedupe)
            df_normal = pd.concat([df_with_factura, df_no_factura], ignore_index=True)
        else:
            # Sin columna factura: no deduplicar para evitar perder pagos
            df_normal = df_normal.copy()

        # Dedupe anticipo (excluye forma de pago)
        dedup_subset_anticipo = ['doc_norm', 'Fecha_dt', 'valor_pagado']
        if factura_col:
            dedup_subset_anticipo.append(factura_col)
        df_anticipo = df_anticipo.drop_duplicates(subset=[c for c in dedup_subset_anticipo if c in df_anticipo.columns])

        # Unimos los pagos limpios (excluyendo anticipos del recaudo)
        df_pagos_clean = df_normal.copy()

        # 2. Agrupar pagos por Paciente y Fecha (Dia)
        # Calculamos el total pagado por día por paciente
        # Clave: (doc_norm, fecha_date) -> {total_valor: float, facturadores: set, pagado: bool}
        daily_payments = {}
        
        for _, row in df_pagos_clean.iterrows():
            doc = row['doc_norm']
            if not doc: continue
            
            # Fecha sin hora para agrupar por día
            if pd.isna(row['Fecha_dt']): continue
            day_key = (doc, row['Fecha_dt'].date())
            
            valor = row.get('valor_pagado', 0)
            try: valor = float(valor)
            except: valor = 0
            
            facturador = row.get('facturador', '')
            
            if day_key not in daily_payments:
                daily_payments[day_key] = {'total': 0.0, 'facturadores': set(), 'has_payment': False}
            
            daily_payments[day_key]['total'] += valor
            if valor > 0:
                daily_payments[day_key]['has_payment'] = True
            if pd.notna(facturador) and str(facturador).strip():
                daily_payments[day_key]['facturadores'].add(str(facturador).strip())

        # 3. Asignar al Maestro
        # Convertir columna a objeto para evitar FutureWarning si estaba vacía (float/NaN)
        df_master['Asesor_Comercial'] = df_master['Asesor_Comercial'].astype(object)
        
        # Para evitar duplicar el recaudo si el paciente tiene varias citas el mismo día en el maestro,
        # asignaremos el valor TOTAL solo a la PRIMERA fila que encontremos para ese paciente/día.
        # Las siguientes filas del mismo día quedarán en 0.
        
        assigned_keys = set() # Para rastrear (doc, dia) ya asignados
        
        updates_asesor = 0
        updates_efectivo = 0
        updates_recaudo = 0 # Nuevo contador

        for idx, row in df_master.iterrows():
            doc = row['doc_norm']
            if pd.isna(row['Fecha_dt']): continue
            fecha_cita_date = row['Fecha_dt'].date()
            
            key = (doc, fecha_cita_date)
            
            if key in daily_payments:
                info = daily_payments[key]
                
                # Asesor: Asignamos el facturador (o facturadores unidos)
                if info['facturadores']:
                    # Unimos por si hay mas de uno distinto
                    facturador_str = " / ".join(list(info['facturadores']))
                    df_master.at[idx, 'Asesor_Comercial'] = facturador_str
                    updates_asesor += 1
                
                # Efectividad: 1 si hubo algun pago en el dia > 0
                if info['has_payment']:
                    df_master.at[idx, 'Efectivo'] = 1
                    updates_efectivo += 1
                
                # Recaudo: SOLO asignar si no hemos asignado ya a este (doc, dia)
                # "ese valor se tomaria como un solo pago asi se ponga el recaudo varias veces"
                if key not in assigned_keys:
                    if info['total'] > 0:
                        df_master.at[idx, 'Recaudo (venta día)'] = info['total']
                        updates_recaudo += 1
                    assigned_keys.add(key)
                else:
                    # Ya asignamos el recaudo de este día a una fila previa. 
                    # Dejamos en blanco o 0 (ya seteado por defecto o inicializado)
                    pass

        # Limpieza de columnas temporales
        df_master.drop(columns=['doc_norm', 'Fecha_dt'], inplace=True)
        
        # Rellenar vacíos en Efectivo con 0
        df_master['Efectivo'] = df_master['Efectivo'].fillna(0).astype(int)
        
        # Guardar con formato
        output_path = master_path
        # Sobreescribir el mismo maestro
        # Usamos ExcelWriter con engine openpyxl para dar formato a la columna de moneda
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df_master.to_excel(writer, index=False, sheet_name='Datos Mercadeo')
            ws = writer.sheets['Datos Mercadeo']
            
            # Aplicar formato moneda a 'Recaudo (venta día)'
            tgt_col = 'Recaudo (venta día)'
            if tgt_col in df_master.columns:
                # pandas es 0-indexed, openpyxl es 1-indexed
                col_idx = df_master.columns.get_loc(tgt_col) + 1
                
                # Iterar filas (saltando header)
                for row in ws.iter_rows(min_row=2, min_col=col_idx, max_col=col_idx):
                    for cell in row:
                        # Formato contabilidad/moneda
                        cell.number_format = '"$"#,##0_-' 

        # df_master.to_excel(output_path, index=False) # Eliminado en favor del bloque anterior
        
        print("Proceso completado.")
        print(f"Filas actualizadas con Asesor Comercial: {updates_asesor}")
        print(f"Filas marcadas como Efectivo: {updates_efectivo}")
        print(f"Filas con Recaudo asignado (único por día): {updates_recaudo}")
        print(f"Archivo actualizado: {output_path}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
