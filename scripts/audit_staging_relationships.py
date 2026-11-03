#!/usr/bin/env python3
"""Read-only, null-token-aware relationship audit for the 10 staging tables.

- Reads only from haven_poc_source staging tables.
- Treats NULL, empty/whitespace strings, and the literal token "NULL"
  (case-insensitive) as missing identifiers for audit purposes only.
- Does not update, delete, or rewrite any source/staging values.
- Reports aggregate counts only; never prints patient/visit identifiers.

Run from the project root:
    python scripts/audit_staging_relationships.py
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
SCHEMA = "haven_poc_source"

TABLES = {
    "patient": "stg_ds_patient",
    "visit": "stg_ds_visit",
    "diagnosis": "stg_ds_diagnosis",
    "endoscopy": "stg_ds_endoscopy_procedure",
    "medication": "stg_ds_medication",
    "neurology": "stg_ds_neurology_procedure",
    "operation": "stg_ds_operation_procedure",
    "radiology": "stg_ds_radiology_procedure",
    "laboratory": "stg_ds_laboratory_procedure",
    "vital_signs": "stg_ds_vital_signs",
}
CHILD_TABLES = [
    "diagnosis", "endoscopy", "medication", "neurology", "operation",
    "radiology", "laboratory", "vital_signs",
]


def qi(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def normalise_identifier(value):
    """Return None for null-like markers; otherwise a trimmed string."""
    if value is None:
        return None
    value = str(value).strip()
    if value == "" or value.upper() == "NULL":
        return None
    return value


def load_table(cursor, table_name):
    cursor.execute(f"SHOW COLUMNS FROM {qi(table_name)}")
    column_names = [row[0] for row in cursor.fetchall()]
    lookup = {name.casefold(): name for name in column_names}
    cursor.execute(f"SELECT * FROM {qi(table_name)}")
    rows = cursor.fetchall()
    return column_names, lookup, rows


def get_field(row, column_names, lookup, field_name):
    actual = lookup.get(field_name.casefold())
    if actual is None:
        return None
    return normalise_identifier(row[column_names.index(actual)])


def identifier_summary(values, parent_ids=None):
    valid = [v for v in values if v is not None]
    counts = Counter(valid)
    result = {
        "rows": len(values),
        "missing_null_or_blank": len(values) - len(valid),
        "valid_rows": len(valid),
        "distinct_valid_ids": len(counts),
        "duplicate_rows_beyond_first": sum(n - 1 for n in counts.values() if n > 1),
    }
    if parent_ids is not None:
        matched = [v for v in valid if v in parent_ids]
        unmatched = [v for v in valid if v not in parent_ids]
        result.update({
            "matched_rows": len(matched),
            "unmatched_rows": len(unmatched),
            "distinct_matched_ids": len(set(matched)),
            "distinct_unmatched_ids": len(set(unmatched)),
        })
    return result


def print_summary(label, summary):
    print(f"\n{label}")
    for key, value in summary.items():
        print(f"  {key}: {value}")


def main() -> int:
    load_dotenv(ENV_FILE)
    host = os.getenv("DB_HOST")
    port_raw = os.getenv("DB_PORT", "3308")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not host or not user or password is None:
        raise RuntimeError("DB_HOST, DB_USER, and DB_PASSWORD must be set in .env.")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError("DB_PORT must be an integer.") from exc
    if host != "127.0.0.1" or port != 3308:
        raise RuntimeError("Refusing connection: expected DB_HOST=127.0.0.1 and DB_PORT=3308.")

    conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password,
        database=SCHEMA, charset="utf8mb4", use_unicode=True,
    )
    try:
        conn.start_transaction(readonly=True)
        cursor = conn.cursor()
        cursor.execute("SELECT @@port, DATABASE()")
        actual_port, actual_schema = cursor.fetchone()
        if actual_port != 3308 or actual_schema != SCHEMA:
            raise RuntimeError("MySQL server/schema identity check failed.")

        data = {}
        for key, table in TABLES.items():
            columns, lookup, rows = load_table(cursor, table)
            data[key] = {"table": table, "columns": columns, "lookup": lookup, "rows": rows}

        def values(dataset, field):
            item = data[dataset]
            return [get_field(row, item["columns"], item["lookup"], field) for row in item["rows"]]

        patient_deids = values("patient", "DeID")
        patient_ids = {v for v in patient_deids if v is not None}
        visit_ids_values = values("visit", "VisitID")
        visit_ids = {v for v in visit_ids_values if v is not None}

        print("READ-ONLY STAGING RELATIONSHIP AUDIT")
        print(f"Schema: {SCHEMA}; MySQL port: {actual_port}")
        print('Audit rule: empty values and literal "NULL" (case-insensitive) are treated as missing for checks only.')
        print("No row-level identifiers are displayed. No database values are changed.")

        print_summary("PATIENT DeID identifier quality", identifier_summary(patient_deids))
        visit_deids = values("visit", "DeID")
        print_summary("VISIT VisitID identifier quality", identifier_summary(visit_ids_values))
        print_summary("VISIT DeID -> PATIENT DeID", identifier_summary(visit_deids, patient_ids))

        print("\nCHILD DATASET RELATIONSHIP CHECKS")
        for dataset in CHILD_TABLES:
            print(f"\n{dataset} ({data[dataset]['table']})")
            deids = values(dataset, "DeID")
            visitids = values(dataset, "VisitID")
            print("  DeID -> PATIENT DeID")
            for key, value in identifier_summary(deids, patient_ids).items():
                print(f"    {key}: {value}")
            print("  VisitID -> VISIT VisitID")
            for key, value in identifier_summary(visitids, visit_ids).items():
                print(f"    {key}: {value}")

        diagnosis_ids = values("diagnosis", "diagnosisid")
        print_summary("DIAGNOSIS diagnosisid identifier quality", identifier_summary(diagnosis_ids))

        print("\nIMPORTANT INTERPRETATION")
        print("Unmatched identifiers are reported, not treated as proof of bad data.")
        print("Do not add foreign-key constraints or remove records until the source sampling scope is confirmed.")
        print('The literal text "NULL" remains unchanged in staging; this rule applies only to this audit.')
        return 0
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
