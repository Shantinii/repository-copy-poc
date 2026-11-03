from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "sample data excel.xlsx"


def find_sheet(sheets, fragment):
    matches = [
        (name, df)
        for name, df in sheets.items()
        if fragment.lower() in name.lower()
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one sheet matching {fragment!r}; "
            f"found {len(matches)}"
        )
    return matches[0]


def complete_pairs(df):
    """Return distinct complete (DeID, VisitID) pairs."""
    if not {"DeID", "VisitID"}.issubset(df.columns):
        return set()
    return set(
        df[["DeID", "VisitID"]]
        .dropna()
        .itertuples(index=False, name=None)
    )


def main():
    if not WORKBOOK.exists():
        raise FileNotFoundError(f"Workbook not found: {WORKBOOK}")

    sheets = pd.read_excel(WORKBOOK, sheet_name=None)
    _, patients = find_sheet(sheets, "patient data")
    _, visits = find_sheet(sheets, "visit data")

    if "DeID" not in patients.columns:
        raise ValueError("Patient worksheet is missing DeID.")

    if not {"DeID", "VisitID"}.issubset(visits.columns):
        raise ValueError("Visit worksheet must contain DeID and VisitID.")

    patient_ids = set(patients["DeID"].dropna())
    visit_ids = set(visits["VisitID"].dropna())
    visit_pairs = complete_pairs(visits)

    visit_patient_counts = (
        visits.dropna(subset=["DeID", "VisitID"])
        .groupby("VisitID")["DeID"]
        .nunique()
    )
    multiple_patient_visits = int((visit_patient_counts > 1).sum())

    print("RELATIONSHIP SUMMARY (counts only)")
    print(f"Worksheets inspected: {len(sheets)}")
    print(f"Patient rows: {len(patients)}")
    print(f"Unique patient DeID values: {len(patient_ids)}")
    print(f"Visit rows: {len(visits)}")
    print(f"Unique VisitID values: {len(visit_ids)}")
    print(f"Distinct reference patient-visit pairs: {len(visit_pairs)}")
    print(f"Visit IDs mapped to multiple patients: {multiple_patient_visits}")
    print()

    for name, df in sheets.items():
        print(f"SHEET: {name}")

        if "DeID" in df.columns:
            values = df["DeID"].dropna()
            value_set = set(values)
            print(
                f"  DeID: missing={int(df['DeID'].isna().sum())}, "
                f"unmatched_distinct_to_patients={len(value_set - patient_ids)}, "
                f"unmatched_rows_to_patients={int((~values.isin(patient_ids)).sum())}"
            )

        if "VisitID" in df.columns:
            values = df["VisitID"].dropna()
            value_set = set(values)
            print(
                f"  VisitID: missing={int(df['VisitID'].isna().sum())}, "
                f"unmatched_distinct_to_visits={len(value_set - visit_ids)}, "
                f"unmatched_rows_to_visits={int((~values.isin(visit_ids)).sum())}"
            )

        if {"DeID", "VisitID"}.issubset(df.columns):
            complete_df = df.dropna(subset=["DeID", "VisitID"])
            pairs = complete_pairs(df)
            unmatched_pairs = pairs - visit_pairs

            reference_index = pd.MultiIndex.from_tuples(
                list(visit_pairs), names=["DeID", "VisitID"]
            )
            row_index = pd.MultiIndex.from_frame(
                complete_df[["DeID", "VisitID"]]
            )
            unmatched_pair_rows = int(
                (~row_index.isin(reference_index)).sum()
            )

            individually_valid_pairs = {
                pair for pair in pairs
                if pair[0] in patient_ids and pair[1] in visit_ids
            }
            individually_valid_mismatches = (
                individually_valid_pairs - visit_pairs
            )

            incomplete_rows = int(
                df[["DeID", "VisitID"]].isna().any(axis=1).sum()
            )

            print(
                "  Patient-visit pairs: "
                f"incomplete_rows={incomplete_rows}, "
                f"distinct_complete_pairs={len(pairs)}, "
                f"unmatched_distinct_pairs={len(unmatched_pairs)}, "
                f"unmatched_pair_rows={unmatched_pair_rows}, "
                f"individually_valid_but_mismatched_distinct_pairs="
                f"{len(individually_valid_mismatches)}"
            )

        print()

    print("Validation complete. Counts only; no individual identifier values were printed.")


if __name__ == "__main__":
    main()
