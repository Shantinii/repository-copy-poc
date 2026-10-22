from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repository_copy_core as repo

workbook = ROOT / "sample data excel.xlsx"
sheets = pd.read_excel(
    workbook,
    sheet_name=[
        "bi_patient data",
        "bi_visit data",
        "bi_diagnosis data",
    ],
)

def make_tables():
    return {
        "bi_patient_data": sheets["bi_patient data"].copy(),
        "bi_visit_data": sheets["bi_visit data"].copy(),
        "bi_diagnosis_data": sheets["bi_diagnosis data"].copy(),
    }

def expect_rejection(label, tables):
    try:
        repo.validate_dataset_relationships(tables)
    except repo.DatasetValidationError:
        print(f"PASS: {label} rejected")
    else:
        raise AssertionError(f"FAIL: {label} was accepted")

print("TEST 1: Reject duplicate patient primary key")
tables = make_tables()
tables["bi_patient_data"].loc[1, "DeID"] = (
    tables["bi_patient_data"].loc[0, "DeID"]
)
expect_rejection("duplicate patient DeID", tables)

print("\nTEST 2: Reject a visit linked to an unknown patient")
tables = make_tables()
tables["bi_visit_data"].loc[0, "DeID"] = -999999999
expect_rejection("unknown patient reference in visit", tables)

print("\nTEST 3: Reject a diagnosis linked to an unknown visit")
tables = make_tables()
tables["bi_diagnosis_data"].loc[0, "VisitID"] = -999999999
expect_rejection("unknown visit reference in diagnosis", tables)

print("\nAll negative tests passed.")
