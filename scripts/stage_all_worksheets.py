#!/usr/bin/env python3
"""
Safely stage all 10 worksheets from the approved sample workbook into
haven_poc_source without changing the three existing source tables.

This is a raw staging load:
- Reads the workbook without modifying it.
- Preserves every worksheet column, including columns whose header is blank
  and columns whose data is entirely blank.
- Uses TEXT staging columns so type inference cannot silently truncate or
  coerce clinical values. Valid date/type normalization belongs in a later,
  validated transformation step.
- Maps blank headers to deterministic placeholders and records the original
  worksheet, column position, and header in a JSON manifest.
- Refuses to overwrite existing staging tables.
- Never drops or modifies the existing bi_patient_data, bi_visit_data, or
  bi_diagnosis_data tables.
- Requires --load to create tables and insert rows. Without --load, performs
  preflight checks only.

Run from the project root:
    python scripts/stage_all_worksheets.py
    python scripts/stage_all_worksheets.py --load
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import mysql.connector
from dotenv import load_dotenv
from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "sample data excel.xlsx"
ENV_FILE = ROOT / ".env"
SOURCE_SCHEMA = "haven_poc_source"
EXPECTED_SHEETS = [
    "bi_patient data",
    "bi_visit data",
    "bi_diagnosis data",
    "bi_endoscopy_procedure d",
    "bi_medication data",
    "bi_neurology_procedure d",
    "bi_operation_procedure sample d",
    "bi_radiology_procedure d",
    "bi_laboratory_procedure ",
    "vitalsign data",
]
DATASET_IDS = {
    "bi_patient data": "DS_PATIENT",
    "bi_visit data": "DS_VISIT",
    "bi_diagnosis data": "DS_DIAGNOSIS",
    "bi_endoscopy_procedure d": "DS_ENDOSCOPY_PROCEDURE",
    "bi_medication data": "DS_MEDICATION",
    "bi_neurology_procedure d": "DS_NEUROLOGY_PROCEDURE",
    "bi_operation_procedure sample d": "DS_OPERATION_PROCEDURE",
    "bi_radiology_procedure d": "DS_RADIOLOGY_PROCEDURE",
    "bi_laboratory_procedure ": "DS_LABORATORY_PROCEDURE",
    "vitalsign data": "DS_VITAL_SIGNS",
}
DISPLAY_LABELS = {
    "bi_patient data": "Patient Demographics",
    "bi_visit data": "Visits",
    "bi_diagnosis data": "Diagnoses",
    "bi_endoscopy_procedure d": "Endoscopy Procedures",
    "bi_medication data": "Medications",
    "bi_neurology_procedure d": "Neurology Procedures",
    "bi_operation_procedure sample d": "Operation Procedures",
    "bi_radiology_procedure d": "Radiology Procedures",
    "bi_laboratory_procedure ": "Laboratory Procedures",
    "vitalsign data": "Vital Signs",
}
EXISTING_TABLES_TO_PRESERVE = {
    "bi_patient_data",
    "bi_visit_data",
    "bi_diagnosis_data",
}


def quote_identifier(identifier: str) -> str:
    """Quote a MySQL identifier, escaping embedded backticks."""
    return "`" + identifier.replace("`", "``") + "`"


def staging_table_name(sheet_name: str) -> str:
    return "stg_" + DATASET_IDS[sheet_name].lower()


def fail(message: str) -> None:
    raise RuntimeError(message)


def serialise_cell(value: Any) -> str | None:
    """Convert a source cell to a loss-minimising text representation."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        # Avoid serialising integral numeric cells as e.g. '123.0'.
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def read_workbook() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not WORKBOOK.is_file():
        fail(f"Workbook not found: {WORKBOOK}")
    if not ENV_FILE.is_file():
        fail(f".env file not found: {ENV_FILE}")

    workbook = load_workbook(WORKBOOK, read_only=True, data_only=True)
    try:
        actual_sheets = workbook.sheetnames
        if actual_sheets != EXPECTED_SHEETS:
            fail(
                "Workbook sheet names/order do not match the approved source. "
                f"Expected {EXPECTED_SHEETS!r}; found {actual_sheets!r}"
            )

        datasets: list[dict[str, Any]] = []
        manifest_columns: list[dict[str, Any]] = []

        for sheet_name in EXPECTED_SHEETS:
            worksheet = workbook[sheet_name]
            rows = worksheet.iter_rows(values_only=True)
            try:
                raw_headers = next(rows)
            except StopIteration:
                fail(f"Worksheet is empty and has no header row: {sheet_name!r}")

            headers: list[str] = []
            used_headers: set[str] = set()
            for position, raw_header in enumerate(raw_headers, start=1):
                if raw_header is None or str(raw_header).strip() == "":
                    db_header = f"__source_column_{position:03d}"
                    original_header = None if raw_header is None else str(raw_header)
                else:
                    original_header = str(raw_header)
                    db_header = original_header

                if db_header in used_headers:
                    fail(
                        f"Duplicate mapped column name in worksheet {sheet_name!r}: "
                        f"{db_header!r}. No data has been written."
                    )
                used_headers.add(db_header)
                headers.append(db_header)
                manifest_columns.append(
                    {
                        "dataset_id": DATASET_IDS[sheet_name],
                        "source_sheet": sheet_name,
                        "source_column_position": position,
                        "source_header_original": original_header,
                        "staging_column_name": db_header,
                        "blank_header_mapped": original_header is None
                        or original_header.strip() == "",
                    }
                )

            records: list[tuple[str | None, ...]] = []
            for row in rows:
                # Retain worksheet row count, including rows whose cells are all blank.
                padded = list(row[: len(headers)])
                if len(padded) < len(headers):
                    padded.extend([None] * (len(headers) - len(padded)))
                records.append(tuple(serialise_cell(value) for value in padded))

            datasets.append(
                {
                    "sheet_name": sheet_name,
                    "dataset_id": DATASET_IDS[sheet_name],
                    "display_label": DISPLAY_LABELS[sheet_name],
                    "table_name": staging_table_name(sheet_name),
                    "headers": headers,
                    "records": records,
                    "row_count": len(records),
                    "column_count": len(headers),
                    "all_blank_columns": [
                        headers[idx]
                        for idx in range(len(headers))
                        if all(record[idx] is None or record[idx] == "" for record in records)
                    ],
                }
            )

        return datasets, manifest_columns
    finally:
        workbook.close()


def validate_db_config() -> tuple[str, int, str, str]:
    load_dotenv(ENV_FILE)
    host = os.getenv("DB_HOST")
    port_raw = os.getenv("DB_PORT", "3308")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")

    if not host or not user or password is None:
        fail("DB_HOST, DB_USER, and DB_PASSWORD must be set in .env.")
    try:
        port = int(port_raw)
    except ValueError:
        fail("DB_PORT must be an integer.")
    if host != "127.0.0.1" or port != 3308:
        fail("Refusing connection: expected DB_HOST=127.0.0.1 and DB_PORT=3308.")
    return host, port, user, password


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely stage all 10 workbook worksheets.")
    parser.add_argument(
        "--load",
        action="store_true",
        help="Create new staging tables and load rows. Without this flag, run preflight only.",
    )
    args = parser.parse_args()

    datasets, manifest_columns = read_workbook()
    total_rows = sum(item["row_count"] for item in datasets)
    total_columns = sum(item["column_count"] for item in datasets)

    print("Workbook preflight passed.")
    print(f"Workbook: {WORKBOOK}")
    print(f"Worksheets: {len(datasets)}")
    print(f"Total data rows: {total_rows}")
    print(f"Total source columns: {total_columns}")
    for item in datasets:
        print(
            f"{item['dataset_id']} -> {item['table_name']}: "
            f"rows={item['row_count']}, columns={item['column_count']}, "
            f"all-blank columns={len(item['all_blank_columns'])}"
        )
    print("All source columns are retained; staging columns use TEXT.")
    print("Existing source tables will not be modified.")
    print("No cell values are printed.")

    host, port, user, password = validate_db_config()
    connection = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=SOURCE_SCHEMA,
        charset="utf8mb4",
        use_unicode=True,
        autocommit=False,
    )
    cursor = connection.cursor()
    lock_acquired = False
    created_tables: list[str] = []

    try:
        cursor.execute("SELECT @@port, DATABASE()")
        server_port, selected_schema = cursor.fetchone()
        if server_port != 3308 or selected_schema != SOURCE_SCHEMA:
            fail("MySQL server/schema identity check failed.")

        cursor.execute("SELECT GET_LOCK(%s, 10)", ("haven_poc_stage_all_worksheets",))
        if cursor.fetchone()[0] != 1:
            fail("Could not acquire staging-loader lock.")
        lock_acquired = True

        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            """,
            (SOURCE_SCHEMA,),
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

        missing_existing = EXISTING_TABLES_TO_PRESERVE - existing_tables
        if missing_existing:
            fail(
                "Expected existing source tables were not found; stop and inspect DB: "
                + ", ".join(sorted(missing_existing))
            )

        target_tables = {item["table_name"] for item in datasets}
        collisions = target_tables & existing_tables
        if collisions:
            fail(
                "Refusing to overwrite existing staging tables: "
                + ", ".join(sorted(collisions))
            )

        if not args.load:
            print("PREFLIGHT ONLY: MySQL connection and staging-table checks passed.")
            print("No tables or rows were created.")
            return 0

        # New staging tables only. All values are stored as text to preserve
        # source values while type/date profiling is carried out separately.
        for item in datasets:
            column_defs = [
                f"{quote_identifier(column)} LONGTEXT NULL"
                for column in item["headers"]
            ]
            create_sql = (
                f"CREATE TABLE {quote_identifier(item['table_name'])} ("
                + ", ".join(column_defs)
                + ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                " COLLATE=utf8mb4_0900_ai_ci"
            )
            cursor.execute(create_sql)
            created_tables.append(item["table_name"])

            columns_sql = ", ".join(quote_identifier(c) for c in item["headers"])
            placeholders = ", ".join(["%s"] * len(item["headers"]))
            insert_sql = (
                f"INSERT INTO {quote_identifier(item['table_name'])} "
                f"({columns_sql}) VALUES ({placeholders})"
            )
            if item["records"]:
                cursor.executemany(insert_sql, item["records"])

            cursor.execute(
                f"SELECT COUNT(*) FROM {quote_identifier(item['table_name'])}"
            )
            actual_rows = int(cursor.fetchone()[0])
            if actual_rows != item["row_count"]:
                fail(
                    f"Row-count mismatch for {item['table_name']}: "
                    f"expected {item['row_count']}, got {actual_rows}"
                )

            cursor.execute(
                f"SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (SOURCE_SCHEMA, item["table_name"]),
            )
            actual_columns = int(cursor.fetchone()[0])
            if actual_columns != item["column_count"]:
                fail(
                    f"Column-count mismatch for {item['table_name']}: "
                    f"expected {item['column_count']}, got {actual_columns}"
                )

        connection.commit()

        report_dir = ROOT / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = report_dir / "phase1_staging_manifest.json"
        manifest = {
            "source_workbook": WORKBOOK.name,
            "target_schema": SOURCE_SCHEMA,
            "load_mode": "raw_staging_text",
            "source_workbook_modified": False,
            "existing_tables_modified": False,
            "total_worksheets": len(datasets),
            "total_rows": total_rows,
            "total_columns": total_columns,
            "blank_headers": [
                col for col in manifest_columns if col["blank_header_mapped"]
            ],
            "column_mapping": manifest_columns,
            "datasets": [
                {
                    "dataset_id": item["dataset_id"],
                    "display_label": item["display_label"],
                    "source_sheet": item["sheet_name"],
                    "staging_table": item["table_name"],
                    "rows_loaded": item["row_count"],
                    "columns_loaded": item["column_count"],
                    "all_blank_columns_retained": item["all_blank_columns"],
                }
                for item in datasets
            ],
            "notes": [
                "Staging values are stored as LONGTEXT; date and semantic typing are not inferred in this step.",
                "No primary-key or foreign-key constraints were imposed.",
                "Blank source headers are mapped to __source_column_NNN and the original header/position is recorded.",
                "No source columns or records were intentionally dropped.",
            ],
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print("\nSTAGING LOAD COMPLETED.")
        for item in datasets:
            print(
                f"{item['table_name']}: rows={item['row_count']}, "
                f"columns={item['column_count']}"
            )
        print(f"Manifest written to: {manifest_path}")
        print("Existing bi_patient_data, bi_visit_data, and bi_diagnosis_data were preserved.")
        print("Next: independently compare source and staging values, then profile dates and relationships.")
        return 0

    except Exception:
        connection.rollback()
        # DDL can implicitly commit. Remove only staging tables created in this run.
        for table_name in reversed(created_tables):
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {quote_identifier(table_name)}")
            except mysql.connector.Error:
                pass
        raise
    finally:
        if lock_acquired:
            try:
                cursor.execute("SELECT RELEASE_LOCK(%s)", ("haven_poc_stage_all_worksheets",))
                cursor.fetchone()
            except mysql.connector.Error:
                pass
        cursor.close()
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"STAGING LOAD FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
