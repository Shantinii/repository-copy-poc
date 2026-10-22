"""Copy the approved patient, visit, and diagnosis tables into the clinical POC schema.

This script is separate from mysql_repository_copy_poc.py.
It copies no data unless the destination tables are empty. If all destination
tables already match the source exactly, it reports that state without writing.
Any partial or conflicting destination state is rejected.

It prints counts and validation results only, never clinical row values or secrets.
"""
from __future__ import annotations

import re
import sys
from typing import Any

import mysql.connector
from dotenv import dotenv_values


ROOT_ENV = ".env"
SOURCE_SCHEMA = "haven_poc_source"
DESTINATION_SCHEMA = "haven_poc_clinical_001"

# Fixed allowlist: do not accept schema or table names from command-line input.
TABLES = (
    {
        "name": "bi_patient_data",
        "primary_key": ("DeID",),
    },
    {
        "name": "bi_visit_data",
        "primary_key": ("VisitID",),
    },
    {
        "name": "bi_diagnosis_data",
        "primary_key": ("diagnosisid",),
    },
)

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class CopyValidationError(RuntimeError):
    """Raised when source or destination validation fails."""


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise CopyValidationError("Unexpected SQL identifier in schema metadata")
    return f"`{identifier}`"


def qualified_table(schema: str, table: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def fetch_table(
    cursor: Any, schema: str, table: str, order_by: tuple[str, ...]
) -> tuple[tuple[str, ...], list[tuple[Any, ...]]]:
    order_sql = ", ".join(quote_identifier(col) for col in order_by)
    cursor.execute(
        f"SELECT * FROM {qualified_table(schema, table)} ORDER BY {order_sql}"
    )
    columns = tuple(item[0] for item in cursor.description)
    rows = [tuple(row) for row in cursor.fetchall()]
    return columns, rows


def row_key(
    columns: tuple[str, ...], row: tuple[Any, ...], key_columns: tuple[str, ...]
) -> tuple[Any, ...]:
    positions = {name: index for index, name in enumerate(columns)}
    try:
        key = tuple(row[positions[name]] for name in key_columns)
    except KeyError as exc:
        raise CopyValidationError("A required primary-key column is missing") from exc
    if any(value is None for value in key):
        raise CopyValidationError("A primary-key value is NULL")
    return key


def validate_unique_keys(
    table_name: str,
    columns: tuple[str, ...],
    rows: list[tuple[Any, ...]],
    key_columns: tuple[str, ...],
) -> set[tuple[Any, ...]]:
    keys = [row_key(columns, row, key_columns) for row in rows]
    if len(keys) != len(set(keys)):
        raise CopyValidationError(f"Duplicate primary keys detected in {table_name}")
    return set(keys)


def validate_relationships(
    patient_columns: tuple[str, ...],
    patient_rows: list[tuple[Any, ...]],
    visit_columns: tuple[str, ...],
    visit_rows: list[tuple[Any, ...]],
    diagnosis_columns: tuple[str, ...],
    diagnosis_rows: list[tuple[Any, ...]],
) -> None:
    patient_pos = {name: i for i, name in enumerate(patient_columns)}
    visit_pos = {name: i for i, name in enumerate(visit_columns)}
    diagnosis_pos = {name: i for i, name in enumerate(diagnosis_columns)}

    patient_ids = {row[patient_pos["DeID"]] for row in patient_rows}
    visit_pairs = {
        (row[visit_pos["DeID"]], row[visit_pos["VisitID"]])
        for row in visit_rows
    }

    for row in visit_rows:
        deid = row[visit_pos["DeID"]]
        if deid is not None and deid not in patient_ids:
            raise CopyValidationError("A visit references a missing patient")

    for row in diagnosis_rows:
        deid = row[diagnosis_pos["DeID"]]
        visit_id = row[diagnosis_pos["VisitID"]]
        if deid is not None and deid not in patient_ids:
            raise CopyValidationError("A diagnosis references a missing patient")
        # MySQL composite foreign keys do not require a match if any component
        # is NULL. Match that behavior, while validating complete pairs.
        if deid is not None and visit_id is not None:
            if (deid, visit_id) not in visit_pairs:
                raise CopyValidationError("A diagnosis references a missing visit")


def main() -> int:
    args = set(sys.argv[1:])
    if args - {"--check-only"}:
        print("Usage: python clinical_repository_copy.py [--check-only]")
        return 2
    check_only = "--check-only" in args

    env = dotenv_values(ROOT_ENV)
    user = env.get("CLINICAL_COPY_DB_USER", "haven_clinical_copy")
    password = env.get("CLINICAL_COPY_DB_PASSWORD")
    host = env.get("DB_HOST", "127.0.0.1")
    port_text = env.get("DB_PORT", "3308")

    if not password:
        print("ERROR: CLINICAL_COPY_DB_PASSWORD is missing from .env")
        return 2
    try:
        port = int(port_text)
    except (TypeError, ValueError):
        print("ERROR: DB_PORT in .env must be an integer")
        return 2
    if port != 3308:
        print("ERROR: Refusing to connect because DB_PORT is not the approved local port 3308")
        return 2

    connection = None
    try:
        connection = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=DESTINATION_SCHEMA,
            connection_timeout=5,
            autocommit=False,
            charset="utf8mb4",
        )

        cursor = connection.cursor()
        cursor.execute("SELECT @@port, DATABASE(), CURRENT_USER()")
        server_port, active_schema, active_user = cursor.fetchone()
        if (
            server_port != 3308
            or active_schema != DESTINATION_SCHEMA
            or active_user != f"{user}@localhost"
        ):
            raise CopyValidationError("MySQL connection identity check failed")

        source_data: dict[str, tuple[tuple[str, ...], list[tuple[Any, ...]]]] = {}
        destination_data: dict[str, tuple[tuple[str, ...], list[tuple[Any, ...]]]] = {}

        # Confirm the fixed source and destination tables exist and can be read.
        for table in TABLES:
            name = table["name"]
            source_data[name] = fetch_table(
                cursor, SOURCE_SCHEMA, name, table["primary_key"]
            )
            destination_data[name] = fetch_table(
                cursor, DESTINATION_SCHEMA, name, table["primary_key"]
            )

            source_columns, source_rows = source_data[name]
            dest_columns, dest_rows = destination_data[name]
            if source_columns != dest_columns:
                raise CopyValidationError(f"Source/destination columns differ for {name}")
            validate_unique_keys(
                name, source_columns, source_rows, table["primary_key"]
            )

        patient_columns, patient_rows = source_data["bi_patient_data"]
        visit_columns, visit_rows = source_data["bi_visit_data"]
        diagnosis_columns, diagnosis_rows = source_data["bi_diagnosis_data"]
        validate_relationships(
            patient_columns,
            patient_rows,
            visit_columns,
            visit_rows,
            diagnosis_columns,
            diagnosis_rows,
        )

        destination_counts = {
            name: len(rows) for name, (_, rows) in destination_data.items()
        }
        source_counts = {name: len(rows) for name, (_, rows) in source_data.items()}

        if check_only:
            if all(count == 0 for count in destination_counts.values()):
                print("Preflight validation passed.")
                print("Source tables, column layouts, primary keys, and relationships: valid")
                print("Destination tables exist and are empty.")
                print("CHECK ONLY: no rows were inserted or changed.")
                return 0
            if destination_counts == source_counts and all(
                source_data[table["name"]] == destination_data[table["name"]]
                for table in TABLES
            ):
                print("Preflight validation passed.")
                print("Destination already matches the source exactly.")
                print("CHECK ONLY: no rows were inserted or changed.")
                return 0
            raise CopyValidationError(
                "Destination is partially populated or differs from source; no changes made"
            )

        if all(count == 0 for count in destination_counts.values()):
            # Insert in dependency order. All writes are on one InnoDB transaction.
            for table in TABLES:
                name = table["name"]
                columns, rows = source_data[name]
                if not rows:
                    continue
                column_sql = ", ".join(quote_identifier(col) for col in columns)
                placeholders = ", ".join(["%s"] * len(columns))
                insert_sql = (
                    f"INSERT INTO {qualified_table(DESTINATION_SCHEMA, name)} "
                    f"({column_sql}) VALUES ({placeholders})"
                )
                cursor.executemany(insert_sql, rows)

            # Re-read and compare all values before committing.
            for table in TABLES:
                name = table["name"]
                source_columns, source_rows = source_data[name]
                dest_columns, dest_rows = fetch_table(
                    cursor, DESTINATION_SCHEMA, name, table["primary_key"]
                )
                if source_columns != dest_columns or source_rows != dest_rows:
                    raise CopyValidationError(
                        f"Post-copy value validation failed for {name}"
                    )

            # Validate destination relationships using the same key-level checks.
            dest_patient = fetch_table(
                cursor, DESTINATION_SCHEMA, "bi_patient_data", ("DeID",)
            )
            dest_visit = fetch_table(
                cursor, DESTINATION_SCHEMA, "bi_visit_data", ("VisitID",)
            )
            dest_diagnosis = fetch_table(
                cursor,
                DESTINATION_SCHEMA,
                "bi_diagnosis_data",
                ("diagnosisid",),
            )
            validate_relationships(
                dest_patient[0],
                dest_patient[1],
                dest_visit[0],
                dest_visit[1],
                dest_diagnosis[0],
                dest_diagnosis[1],
            )
            connection.commit()
            print("Clinical data copy committed and validated.")
            for table in TABLES:
                name = table["name"]
                print(f"{name}: {source_counts[name]} source rows; destination values match")
            print("Primary-key and patient/visit/diagnosis relationship checks: passed")
            return 0

        if destination_counts == source_counts:
            # A rerun is accepted only when every row matches exactly.
            all_match = True
            for table in TABLES:
                name = table["name"]
                if source_data[name] != destination_data[name]:
                    all_match = False
                    break
            if all_match:
                connection.rollback()
                print("Destination already matches the source exactly; no rows changed.")
                for table in TABLES:
                    name = table["name"]
                    print(f"{name}: {source_counts[name]} rows verified")
                return 0

        raise CopyValidationError(
            "Destination is partially populated or differs from source; no changes made"
        )

    except Exception as exc:
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
        if isinstance(exc, mysql.connector.Error):
            print(f"ERROR: MySQL operation failed ({type(exc).__name__}).")
            print("Check the account grants, destination tables, and local MySQL service.")
        elif isinstance(exc, CopyValidationError):
            print(f"VALIDATION ERROR: {exc}")
        else:
            print(f"ERROR: operation failed ({type(exc).__name__}).")
        return 1
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
