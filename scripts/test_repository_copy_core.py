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

tables = {
    "bi_patient_data": sheets["bi_patient data"],
    "bi_visit_data": sheets["bi_visit data"],
    "bi_diagnosis_data": sheets["bi_diagnosis data"],
}

print("TEST 1: Validate workbook table relationships")
report = repo.validate_dataset_relationships(tables)
print(report)
assert report.passed, "Dataset relationship validation failed"
print("PASS\n")

print("TEST 2: Reject an unapproved project/dataset")
try:
    repo.validate_project_dataset(
        "unapproved_project",
        "dataset_demo_001",
    )
except repo.AuthorizationError:
    print("PASS: unapproved project rejected\n")
else:
    raise AssertionError("Unapproved project was accepted")

print("TEST 3: Reject an unsuccessful payment status")
request = repo.CopyRequest(
    project_id="project_demo_001",
    dataset_id="dataset_demo_001",
    payment_id="test-payment-001",
    payment_status="failed",
)

try:
    repo.validate_request(request)
except repo.PaymentValidationError:
    print("PASS: failed payment rejected\n")
else:
    raise AssertionError("Failed payment was accepted")

print("TEST 4: Accept an allowlisted request with successful status")
request = repo.CopyRequest(
    project_id="project_demo_001",
    dataset_id="dataset_demo_001",
    payment_id="test-payment-002",
    payment_status="succeeded",
)

repo.validate_request(request)
print("PASS: request validation accepted the supplied status")
print("NOTE: this does not verify a real payment.\n")

print("All four functional tests passed.")
