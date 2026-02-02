# -*- coding: utf-8 -*-
import pandas as pd
from pathlib import Path
from datetime import date
import re
import unicodedata

BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_DIR = BASE_DIR / 'excel'

# Busca el primer archivo que cumpla el prefijo, ignorando mayúsculas/minúsculas/acentos simples
def _find_first_excel(prefix: str) -> Path:
    candidates = []
    for f in EXCEL_DIR.glob('*.xlsx'):
        name = f.name.lower()
        if name.startswith(prefix.lower()):
            candidates.append(f)
    if not candidates:
        raise FileNotFoundError(f"No se encontró un archivo .xlsx que comience con '{prefix}' en {EXCEL_DIR}")
    # elige el más reciente por fecha de modificación
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]

# Fuente: cualquier archivo que empiece por "citas detallado"
SRC = _find_first_excel('citas detallado')
try:
    # Plantilla destino: cualquier archivo que empiece por "formato odontologia"
    DEST = _find_first_excel('formato odontologia')
except FileNotFoundError:
    DEST = None

# El archivo de salida se define dinámicamente según el mes y se versiona si existe
OUTPUT_DIR = EXCEL_DIR
SHEET = 'Datos Mercadeo'

DEST_COLS = [
    'id_registro', 'Numero_Documento', 'Paciente', 'Municipio', 'Convenio', 'Fecha',
    'Año', 'Mes', 'Semana', 'Agente', 'Profesional_Asignado', 'Especialidad',
    'Canal_Captacion', 'Tipo_Cita', 'Programados', 'Asistido', 'Efectivo',
    'cotizacion', 'Admisionado', 'Admisión_Efectiva', 'Asesor_Comercial',
    'Odontologo_Venta', 'Venta_Primer_Pago', 'Cartera (2do pago)',
    'Recaudo (venta día)', 'Tratamiento (Venta total de cotizado)',
    'Valor ejecutado', 'Total venta (Efectivo + cotización)',
    'Falta por recuperar cartera'
]

# Rango de semanas: edita aquí para cambiar fechas por mes.
WEEK_RANGES = {
    'Semana1': (date(2026, 1, 2), date(2026, 1, 10)),
    'Semana2': (date(2026, 1, 13), date(2026, 1, 17)),
    'Semana3': (date(2026, 1, 19), date(2026, 1, 24)),
    'Semana4': (date(2026, 1, 26), date(2026, 1, 31)),
}

MONTH_MAP = {
    1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
    5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
    9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE',
}


def load_source():
    src = pd.read_excel(SRC)
    src['Fecha_dt'] = pd.to_datetime(src['fecha'], errors='coerce')

    # Etiquetar semana según rango configurado
    src['Semana'] = pd.NA
    for name, (start, end) in WEEK_RANGES.items():
        mask = (src['Fecha_dt'].dt.date >= start) & (src['Fecha_dt'].dt.date <= end)
        src.loc[mask, 'Semana'] = name

    # Solo filas que cayeron en alguna semana
    src = src[src['Semana'].notna()].copy()

    name_cols = ['nombre1', 'nombre2', 'apellido1', 'apellido2']
    src['Paciente'] = src[name_cols].fillna('').astype(str).agg(' '.join, axis=1)
    src['Paciente'] = src['Paciente'].str.replace(r'\s+', ' ', regex=True).str.strip()

    src['Numero_Documento'] = src['documento']
    src['Convenio'] = src['Tarifario'].fillna('PARTICULAR')
    src['Año'] = src['Fecha_dt'].dt.year
    src['Mes'] = src['Fecha_dt'].dt.month.map(MONTH_MAP)
    src['Agente'] = src['usuario']
    src['Profesional_Asignado'] = src['doctor']

    # Normaliza texto (quita tildes, espacios extras, pone minúsculas)
    def _norm(txt: str) -> str:
        if pd.isna(txt):
            return ''
        txt = str(txt)
        txt = unicodedata.normalize('NFD', txt)
        txt = ''.join(c for c in txt if unicodedata.category(c) != 'Mn')
        txt = re.sub(r'\s+', ' ', txt).strip().lower()
        return txt

    # Mapeo permitido de unidad -> Especialidad
    especialidad_map = {
        'cirugia oral': 'Cirugia Oral',
        'cirujia oral': 'Cirugia Oral',  # variante
        'endodoncia': 'Endodoncia',
        'odontopediatria': 'Odontopediatria',
        'ortodoncia': 'Ortodoncia',
        'periodoncia': 'Periodoncia',
        'rehabilitacion': 'Rehabilitacion',
        'rehabilitacion oral': 'Rehabilitacion',
    }

    src['Especialidad'] = src['unidad'].apply(
        lambda x: especialidad_map.get(_norm(x), 'Odontologia General')
    )
    # Canal_Captacion ahora se deriva de tipocita:
    # - Valoracion redes sociales -> mismo texto
    # - Agente ia -> mismo texto
    # - Otros casos quedan vacíos
    src['Canal_Captacion'] = src['tipocita'].where(
        src['tipocita'].isin(['Valoracion redes sociales', 'Agente ia']),
        other=pd.NA,
    )

    # Tipo_Cita ahora se toma directo de 'finalidad' tal y como viene
    src['Tipo_Cita'] = src['finalidad']
    src['Programados'] = 1

    src['Asistido'] = src['asistio'].fillna('').str.upper().str.startswith('SI').astype(int)
    # Efectivo: 1 si asistio comienza con SI (cualquier variación), de lo contrario 0
    src['Efectivo'] = src['asistio'].fillna('').str.upper().str.startswith('SI').astype(int)

    # cotizacion NO se llena desde este archivo; queda vacío para ser integrado desde otra fuente
    src['cotizacion'] = pd.NA

    # Fecha en formato DD/MM/YYYY como texto
    src['Fecha'] = src['Fecha_dt'].dt.strftime('%d/%m/%Y')

    # Campo nuevo sin datos de origen
    src['Falta por recuperar cartera'] = pd.NA

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
    if DEST is not None:
        try:
            dest = pd.read_excel(DEST, sheet_name=SHEET)
        except FileNotFoundError:
            dest = pd.DataFrame(columns=DEST_COLS)
    else:
        dest = pd.DataFrame(columns=DEST_COLS)
    # Quitar semanas que vamos a recalcular (normalizando a minúsculas)
    weeks_lower = {w.lower() for w in WEEK_RANGES.keys()}
    dest_keep = dest[~dest['Semana'].astype(str).str.lower().isin(weeks_lower)].copy()
    dest_keep = dest_keep.reindex(columns=DEST_COLS)

    src = load_source()
    # Determinar mes para nombre de archivo
    month_label = src['Mes'].dropna().iloc[0] if not src['Mes'].dropna().empty else 'MES'

    start = next_id_start(dest)
    new_rows = build_new_rows(src, start)

    out = pd.concat([dest_keep, new_rows], ignore_index=True)
    # Crear nombre de salida versionado
    base_name = f"Formato_Odontologia_Mercadeo_script_{month_label}"
    candidate = OUTPUT_DIR / f"{base_name}.xlsx"
    idx = 1
    while candidate.exists():
        candidate = OUTPUT_DIR / f"{base_name}.{idx}.xlsx"
        idx += 1

    out.to_excel(candidate, sheet_name=SHEET, index=False)
    OUTPUT_PATH = candidate

    counts = new_rows['Semana'].value_counts().to_dict()
    print(f"Generado: {OUTPUT_PATH}")
    print("Filas nuevas por semana:", counts)


if __name__ == '__main__':
    main()
