# -*- coding: utf-8 -*-
import json
import re
from datetime import date
from itertools import combinations
from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
JSON_DIR = BASE_DIR / "export_json" / "facturacion_json"
OUTPUT_DIR = BASE_DIR / "excel_generado"
SHEET_FACTURACION = "facturacion"
SHEET_CONTROL = "facturacion_control"

MONTH_MAP = {
    1: "ENERO",
    2: "FEBRERO",
    3: "MARZO",
    4: "ABRIL",
    5: "MAYO",
    6: "JUNIO",
    7: "JULIO",
    8: "AGOSTO",
    9: "SEPTIEMBRE",
    10: "OCTUBRE",
    11: "NOVIEMBRE",
    12: "DICIEMBRE",
}

# Semanas clinicas (4 por mes). Ajusta aqui cuando cambien reglas de negocio.
WEEK_RANGES_BY_MONTH = {
    (2026, 1): {
        "SEMANA1": (date(2026, 1, 2), date(2026, 1, 10)),
        "SEMANA2": (date(2026, 1, 12), date(2026, 1, 17)),
        "SEMANA3": (date(2026, 1, 19), date(2026, 1, 24)),
        "SEMANA4": (date(2026, 1, 26), date(2026, 1, 31)),
    },
    (2026, 2): {
        "SEMANA1": (date(2026, 2, 2), date(2026, 2, 7)),
        "SEMANA2": (date(2026, 2, 9), date(2026, 2, 14)),
        "SEMANA3": (date(2026, 2, 16), date(2026, 2, 21)),
        "SEMANA4": (date(2026, 2, 23), date(2026, 2, 28)),
    },
    (2026, 3): {
        "SEMANA1": (date(2026, 3, 2), date(2026, 3, 7)),
        "SEMANA2": (date(2026, 3, 9), date(2026, 3, 14)),
        "SEMANA3": (date(2026, 3, 16), date(2026, 3, 21)),
        "SEMANA4": (date(2026, 3, 23), date(2026, 3, 31)),
    },
    (2026, 4): {
        "SEMANA1": (date(2026, 4, 1), date(2026, 4, 11)),
        "SEMANA2": (date(2026, 4, 13), date(2026, 4, 18)),
        "SEMANA3": (date(2026, 4, 20), date(2026, 4, 25)),
        "SEMANA4": (date(2026, 4, 27), date(2026, 4, 30)),
    },
}



def _find_output_master(prefix: str) -> Path | None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = [f for f in OUTPUT_DIR.glob("*.xlsx") if f.name.lower().startswith(prefix.lower())]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _parse_valor(v):
    if pd.isna(v):
        return 0
    if isinstance(v, (int, float)):
        return int(round(v))
    s = str(v).strip().replace(",", "")
    try:
        return int(round(float(s)))
    except Exception:
        return 0


def _parse_codigo(codigo: str):
    txt = "" if pd.isna(codigo) else str(codigo).strip()
    m = re.search(r"([A-Za-z]+)\s*-\s*(\d+)", txt)
    if not m:
        return "", ""
    return m.group(1).upper(), m.group(2)


def _semana_clinica(fecha_dt):
    if pd.isna(fecha_dt):
        return "SIN_SEMANA"
    d = fecha_dt.date()
    ranges = WEEK_RANGES_BY_MONTH.get((d.year, d.month), {})
    for semana, (start, end) in ranges.items():
        if start <= d <= end:
            return semana
    return "SIN_SEMANA"



def _read_json_files():
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(JSON_DIR.glob("listado_pagos_*.json"))
    if not files:
        raise FileNotFoundError(f"No se encontraron JSON en: {JSON_DIR}")

    rows = []
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        listado = data.get("listado_pagos", []) or []
        total_documentos = _parse_valor(data.get("total_documentos", 0))
        total_listado_json = _parse_valor(data.get("total_valor", 0))

        for it in listado:
            rows.append(
                {
                    "Fecha_raw": it.get("fecha", data.get("fecha_consulta", "")),
                    "Codigo_Tipo_Doc": it.get("codigo_tipo_doc", ""),
                    "Tipo_Doc": it.get("tipo_doc", ""),
                    "Tercero": it.get("tercero", ""),
                    "Valor_raw": it.get("valor", it.get("valor_raw", 0)),
                    "Archivo_JSON": f.name,
                    "Total_Documentos_JSON": total_documentos,
                    "Total_Listado_JSON": total_listado_json,
                }
            )

    return files, pd.DataFrame(rows)


def _find_docs_to_exclude(doc_sums: pd.Series, diff: int):
    if diff <= 0 or doc_sums.empty:
        return []

    exact = doc_sums[doc_sums == diff]
    if not exact.empty:
        return [exact.index[0]]

    doc_items = list(doc_sums.items())
    for r in (2, 3):
        for combo in combinations(doc_items, r):
            if sum(v for _, v in combo) == diff:
                return [k for k, _ in combo]

    return []


def _apply_daily_comparison_exclusions(df: pd.DataFrame):
    if df.empty:
        return df.copy(), pd.DataFrame()

    work = df.copy()
    work["Excluir_Ajuste"] = False

    control_rows = []

    for fecha, g in work.groupby("Fecha", dropna=False):
        total_listado = int(g["Recaudo (venta dia)"].sum())
        total_documentos_vals = g["Total_Documentos_JSON"].dropna().astype(int)
        total_documentos = int(total_documentos_vals.iloc[0]) if not total_documentos_vals.empty else 0

        if total_documentos <= 0:
            control_rows.append(
                {
                    "Fecha": fecha,
                    "Total_Listado": total_listado,
                    "Total_Documentos": total_documentos,
                    "Diferencia": None,
                    "Documentos_Excluidos": "",
                    "Valor_Excluido": 0,
                    "Estado": "SIN_TOTAL_DOCUMENTOS",
                }
            )
            continue

        diff = total_listado - total_documentos
        excluded_docs = []
        excluded_val = 0
        status = "OK"

        if diff > 0:
            doc_sums = g.groupby("Codigo_Tipo_Doc")["Recaudo (venta dia)"].sum().sort_values(ascending=False)
            excluded_docs = _find_docs_to_exclude(doc_sums, diff)
            if excluded_docs:
                mask = (work["Fecha"] == fecha) & (work["Codigo_Tipo_Doc"].isin(excluded_docs))
                work.loc[mask, "Excluir_Ajuste"] = True
                excluded_val = int(work.loc[mask, "Recaudo (venta dia)"].sum())
                status = "EXCLUIDO_POR_DIFERENCIA"
            else:
                status = "DIFERENCIA_SIN_MATCH"
        elif diff < 0:
            status = "LISTADO_MENOR_A_TOTAL"

        control_rows.append(
            {
                "Fecha": fecha,
                "Total_Listado": total_listado,
                "Total_Documentos": total_documentos,
                "Diferencia": diff,
                "Documentos_Excluidos": " | ".join(excluded_docs),
                "Valor_Excluido": excluded_val,
                "Estado": status,
            }
        )

    control = pd.DataFrame(control_rows)
    filtered = work[~work["Excluir_Ajuste"]].copy()
    return filtered, control


def _build_facturacion(df_raw: pd.DataFrame):
    if df_raw.empty:
        cols = [
            "Fecha",
            "Año",
            "Mes",
            "Semana",
            "Tipo_factura",
            "Tipo_Doc",
            "Paciente",
            "Recaudo (venta dia)",
            "Total_Documentos_JSON",
            "Total_Listado_JSON",
        ]
        return pd.DataFrame(columns=cols), pd.DataFrame()

    df = df_raw.copy()
    df["Fecha_dt"] = pd.to_datetime(df["Fecha_raw"], format="%d/%m/%Y", errors="coerce")
    df["Fecha"] = df["Fecha_dt"].dt.strftime("%d/%m/%Y")
    df["Año"] = df["Fecha_dt"].dt.year
    df["Mes"] = df["Fecha_dt"].dt.month.map(MONTH_MAP).fillna("SIN_MES")
    df["Semana"] = df["Fecha_dt"].apply(_semana_clinica)
    df["Recaudo (venta dia)"] = df["Valor_raw"].apply(_parse_valor)

    parsed = df["Codigo_Tipo_Doc"].apply(_parse_codigo)
    df["Clase_Doc"] = parsed.apply(lambda t: t[0])
    df["Consecutivo_Doc"] = parsed.apply(lambda t: t[1])
    df["Tipo_factura"] = df["Codigo_Tipo_Doc"]
    df["Paciente"] = df["Tercero"]

    before = len(df)
    df = df.drop_duplicates(
        subset=["Fecha", "Codigo_Tipo_Doc", "Tipo_Doc", "Tercero", "Recaudo (venta dia)"]
    ).copy()
    removed = before - len(df)
    if removed:
        print(f"[LOG] Duplicados removidos: {removed}")

    df, control = _apply_daily_comparison_exclusions(df)

    df = df.sort_values(by=["Fecha_dt", "Codigo_Tipo_Doc", "Tercero"], ascending=[True, True, True])

    fact = df[
        [
            "Fecha",
            "Año",
            "Mes",
            "Semana",
            "Tipo_factura",
            "Tipo_Doc",
            "Paciente",
            "Recaudo (venta dia)",
            "Total_Documentos_JSON",
            "Total_Listado_JSON",
        ]
    ].reset_index(drop=True)

    return fact, control


def _write_sheets(df_fact: pd.DataFrame, df_control: pd.DataFrame, dest: Path):
    mode = "a" if dest.exists() else "w"
    with pd.ExcelWriter(dest, engine="openpyxl", mode=mode, if_sheet_exists="replace") as writer:
        df_fact.to_excel(writer, sheet_name=SHEET_FACTURACION, index=False)
        df_control.to_excel(writer, sheet_name=SHEET_CONTROL, index=False)


def main():
    print('[LOG] Nota: rangos de ABRIL 2026 estan provisionales y pendientes de ajuste con gerencia.')
    files, df_raw = _read_json_files()
    print(f"[LOG] JSON leidos: {len(files)}")
    print(f"[LOG] Filas detalle (entrada): {len(df_raw)}")

    df_fact, df_control = _build_facturacion(df_raw)
    total = int(df_fact["Recaudo (venta dia)"].sum()) if not df_fact.empty else 0
    excluded = int(df_control["Valor_Excluido"].fillna(0).sum()) if not df_control.empty else 0

    print(f"[LOG] Filas facturacion (salida): {len(df_fact)}")
    print(f"[LOG] Total Recaudo (venta dia): {total}")
    print(f"[LOG] Valor total excluido por diferencia: {excluded}")

    if not df_control.empty:
        print("[LOG] Control diario (fecha / diferencia / estado):")
        print(df_control[["Fecha", "Diferencia", "Estado", "Documentos_Excluidos"]].to_string(index=False))

    dest = _find_output_master("formato_odontologia")
    if dest is None:
        dest = OUTPUT_DIR / "formato_odontologia_FACTURACION.xlsx"

    _write_sheets(df_fact, df_control, dest)
    print(f"[OK] Hojas '{SHEET_FACTURACION}' y '{SHEET_CONTROL}' actualizadas en: {dest}")


if __name__ == "__main__":
    main()
