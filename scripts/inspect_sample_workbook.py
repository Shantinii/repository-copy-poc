from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "sample data excel.xlsx"

if not WORKBOOK.exists():
    raise FileNotFoundError(f"Workbook not found: {WORKBOOK}")

print(f"Workbook: {WORKBOOK.name}")
print("=" * 70)

sheets = pd.read_excel(WORKBOOK, sheet_name=None)

for sheet_name, df in sheets.items():
    print(f"\nSHEET: {sheet_name}")
    print(f"Rows: {len(df)} | Columns: {len(df.columns)}")
    print("\nColumn summary:")

    for col in df.columns:
        missing = int(df[col].isna().sum())
        unique = int(df[col].nunique(dropna=True))
        print(
            f"  {col!r} | dtype={df[col].dtype} "
            f"| missing={missing} | unique={unique}"
        )

    key_columns = [
        col for col in df.columns
        if str(col).strip().lower() in {
            "deid", "visitid", "patientid", "id"
        }
    ]

    for col in key_columns:
        non_null = df[col].dropna()
        duplicates = int(non_null.duplicated().sum())
        print(
            f"KEY CHECK: {col!r} | "
            f"non-null={len(non_null)} | duplicate values={duplicates}"
        )

print("\nInspection complete. No individual row values were printed.")
