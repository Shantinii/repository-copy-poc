$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][scriptblock]$Command
    )
    Write-Host ""
    Write-Host "=== $Label ===" -ForegroundColor Cyan
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE. Stop here and review the output."
    }
}

Write-Host "PHASE 5 TEST RUNNER" -ForegroundColor Green
Write-Host "Database-backed tests write only to haven_poc_clinical_test."
Write-Host "They do not target haven_poc_source or haven_poc_clinical_001."

Invoke-Checked "Loader pytest tests" {
    python -m pytest -q .\scripts\test_loader_data_preservation.py .\scripts\test_loader_safety.py
}
Invoke-Checked "Repository-copy core tests" {
    python .\scripts\test_repository_copy_core.py
}
Invoke-Checked "Repository-copy failure tests" {
    python .\scripts\test_repository_copy_failures.py
}
Invoke-Checked "Destination-state unit tests" {
    python .\scripts\test_destination_state.py
}

Write-Host ""
Write-Host "=== Reset disposable MySQL destination to expected partial baseline ===" -ForegroundColor Cyan
@'
import getpass
import mysql.connector

p = getpass.getpass("Test database password: ")
c = mysql.connector.connect(
    host="127.0.0.1", port=3308,
    user="haven_clinical_test", password=p,
    database="haven_poc_clinical_test",
    autocommit=False, connection_timeout=5,
)
try:
    q = c.cursor()
    q.execute("SELECT @@port, DATABASE(), CURRENT_USER()")
    identity = q.fetchone()
    expected = (3308, "haven_poc_clinical_test", "haven_clinical_test@localhost")
    if identity != expected:
        raise RuntimeError(f"Safety stop: unexpected connection identity {identity!r}")

    q.execute("SELECT COUNT(*) FROM haven_poc_source.bi_patient_data")
    if q.fetchone()[0] < 2:
        raise RuntimeError("Safety stop: source patient table needs at least two rows.")

    q.execute("DELETE FROM haven_poc_clinical_test.bi_diagnosis_data")
    q.execute("DELETE FROM haven_poc_clinical_test.bi_visit_data")
    q.execute("DELETE FROM haven_poc_clinical_test.bi_patient_data")
    q.execute("""
        INSERT INTO haven_poc_clinical_test.bi_patient_data
        SELECT s.*
        FROM haven_poc_source.bi_patient_data AS s
        ORDER BY s.DeID
        LIMIT 1
    """)
    if q.rowcount != 1:
        raise RuntimeError("Safety stop: could not establish the one-patient baseline.")
    c.commit()
    print("PASS: disposable destination reset to 1 patient, 0 visits, 0 diagnoses.")
    q.close()
except Exception:
    c.rollback()
    raise
finally:
    c.close()
'@ | python -
if ($LASTEXITCODE -ne 0) {
    throw "Could not establish the disposable MySQL test baseline. Stop here."
}

Invoke-Checked "Live MySQL partial-destination rejection" {
    python .\scripts\test_mysql_destination_state.py
}
Invoke-Checked "Live MySQL transaction rollback" {
    python .\scripts\test_mysql_transaction_rollback.py
}
Invoke-Checked "Live MySQL conflict rejection and retry" {
    python .\scripts\test_mysql_conflict_and_retry.py
}

Write-Host ""
Write-Host "PHASE 5 TEST RUN COMPLETED SUCCESSFULLY." -ForegroundColor Green
Write-Host "The disposable test schema now contains an exact source copy."
Write-Host "The main clinical destination was not targeted."
