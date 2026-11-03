#!/usr/bin/env python3
"""Read-only diagnostic for identifier mismatches in the staged workbook.

Compares current matching with a conservative numeric-format diagnostic
(e.g. "123.0" versus "123") and checks child VisitID/DeID pair consistency.
It prints aggregate counts only, never actual identifiers, and does not modify data.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
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
CHILDREN = ["diagnosis", "endoscopy", "medication", "neurology", "operation",
            "radiology", "laboratory", "vital_signs"]

def qi(s):
    return "`" + s.replace("`", "``") + "`"

def clean(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if not s or s.upper() == "NULL" else s

def numeric_equivalent(v):
    """Diagnostic only: normalise integer-valued numeric strings, preserving leading zeros."""
    s = clean(v)
    if s is None or (len(s) > 1 and s.startswith("0") and s[1].isdigit()):
        return s
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return s
    if not d.is_finite() or d != d.to_integral_value():
        return s
    return str(int(d))

def load_table(cur, table):
    cur.execute(f"SHOW COLUMNS FROM {qi(table)}")
    cols = [r[0] for r in cur.fetchall()]
    lookup = {c.casefold(): i for i, c in enumerate(cols)}
    cur.execute(f"SELECT * FROM {qi(table)}")
    return cols, lookup, cur.fetchall()

def field(table_data, row, name):
    idx = table_data[1].get(name.casefold())
    return clean(row[idx]) if idx is not None else None

def main():
    host = os.getenv("DB_HOST")
    port = int(os.getenv("DB_PORT", "3308"))
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not host or not user or password is None:
        raise RuntimeError("DB_HOST, DB_USER, and DB_PASSWORD must be set in .env.")
    if host != "127.0.0.1" or port != 3308:
        raise RuntimeError("Refusing connection: expected DB_HOST=127.0.0.1 and DB_PORT=3308.")
    conn = mysql.connector.connect(host=host, port=port, user=user,
        password=password, database=SCHEMA, charset="utf8mb4", use_unicode=True)
    try:
        conn.start_transaction(readonly=True)
        cur = conn.cursor()
        cur.execute("SELECT @@port, DATABASE()")
        actual_port, actual_schema = cur.fetchone()
        if actual_port != 3308 or actual_schema != SCHEMA:
            raise RuntimeError("MySQL server/schema identity check failed.")
        d = {k: load_table(cur, t) for k, t in TABLES.items()}

        def vals(ds, col):
            cols, lookup, rows = d[ds]
            if col.casefold() not in lookup:
                return [None] * len(rows)
            return [field(d[ds], r, col) for r in rows]

        p_deid = vals("patient", "DeID")
        v_id = vals("visit", "VisitID")
        v_deid = vals("visit", "DeID")
        p_set = {x for x in p_deid if x is not None}
        v_set = {x for x in v_id if x is not None}
        p_num = {numeric_equivalent(x) for x in p_set}
        v_num = {numeric_equivalent(x) for x in v_set}

        print("READ-ONLY IDENTIFIER MISMATCH DIAGNOSTIC")
        print(f"Schema: {actual_schema}; MySQL port: {actual_port}")
        print("Identifiers are not printed. No database values are changed.")
        print("\n1) Does numeric formatting explain any mismatches?")
        for ds in CHILDREN:
            c_deid, c_visit = vals(ds, "DeID"), vals(ds, "VisitID")
            deid_valid = [x for x in c_deid if x is not None]
            visit_valid = [x for x in c_visit if x is not None]
            deid_exact = sum(x in p_set for x in deid_valid)
            deid_num = sum(numeric_equivalent(x) in p_num for x in deid_valid)
            visit_exact = sum(x in v_set for x in visit_valid)
            visit_num = sum(numeric_equivalent(x) in v_num for x in visit_valid)
            print(f"\n{ds}:")
            print(f"  DeID: exact_matches={deid_exact}/{len(deid_valid)}; numeric_format_matches={deid_num}/{len(deid_valid)}")
            print(f"  VisitID: exact_matches={visit_exact}/{len(visit_valid)}; numeric_format_matches={visit_num}/{len(visit_valid)}")

        print("\n2) Visit-to-patient mapping consistency")
        # Map each visit ID to the set of DeIDs associated with it in the visit table.
        visit_to_patients = defaultdict(set)
        for vid, did in zip(v_id, v_deid):
            if vid is not None and did is not None:
                visit_to_patients[vid].add(did)
        visit_ids_multi_patient = sum(1 for ids in visit_to_patients.values() if len(ids) > 1)
        print(f"  visit rows: {len(v_id)}")
        print(f"  visits with a matched patient DeID: {sum(1 for vid, did in zip(v_id, v_deid) if vid is not None and did in p_set)}")
        print(f"  distinct VisitIDs associated with multiple DeIDs in visit table: {visit_ids_multi_patient}")

        print("\n3) Child rows with internally consistent DeID + VisitID")
        print("   A row is consistent only if its DeID matches the patient table and its VisitID matches a visit whose DeID is the same.")
        for ds in CHILDREN:
            c_deid, c_visit = vals(ds, "DeID"), vals(ds, "VisitID")
            both_present = 0
            patient_match = 0
            visit_match = 0
            pair_match = 0
            for did, vid in zip(c_deid, c_visit):
                if did is None or vid is None:
                    continue
                both_present += 1
                if did in p_set:
                    patient_match += 1
                if vid in v_set:
                    visit_match += 1
                if vid in visit_to_patients and did in visit_to_patients[vid]:
                    pair_match += 1
            print(f"  {ds}: rows_with_both_ids={both_present}; DeID_matches_patient={patient_match}; VisitID_matches_visit={visit_match}; matching_patient_visit_pair={pair_match}")

        print("\n4) Identifier string-shape indicators (aggregate only)")
        for ds in ["patient", "visit", *CHILDREN]:
            for col in (["DeID"] if ds == "patient" else
                        ["VisitID", "DeID"] if ds == "visit" else ["DeID", "VisitID"]):
                values = vals(ds, col)
                valid = [x for x in values if x is not None]
                if not valid:
                    continue
                decimal_suffix = sum(1 for x in valid if x.endswith(".0") and numeric_equivalent(x) != x)
                print(f"  {ds}.{col}: valid={len(valid)}; integer_decimal_suffix={decimal_suffix}")
        print("\nInterpretation: numeric-format matching is diagnostic only. Do not rewrite identifiers or add constraints based on this report alone.")
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
