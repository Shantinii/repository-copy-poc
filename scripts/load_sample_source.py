"""
Load the approved three-sheet sample workbook into MySQL schema
`haven_poc_source`.

Safety properties:
- Reads DB_HOST, DB_USER, DB_PASSWORD from the project .env file.
- Connects only to the explicitly named haven_poc_source schema.
- Refuses to run if any target table already exists.
- Validates key uniqueness and relationships before connecting to MySQL.
- Uses parameterised inserts and a transaction.
- Does not print workbook row values.
- Does not alter the existing project schemas.

Review before first execution. The database user must have privileges to create
tables and insert rows in haven_poc_source. Prefer a dedicated loader account
with privileges limited to this schema.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import mysql.connector
import pandas as pd
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "sample data excel.xlsx"
ENV_FILE = ROOT / ".env"
SOURCE_SCHEMA = "haven_poc_source"

SHEET_TO_TABLE = {
    "bi_patient data": "bi_patient_data",
    "bi_visit data": "bi_visit_data",
    "bi_diagnosis data": "bi_diagnosis_data",
}

# Only entirely empty columns are excluded. All other source columns are retained.
KEY_COLUMNS = {
    "bi_patient_data": ["DeID"],
    "bi_visit_data": ["VisitID"],
    "bi_diagnosis_data": ["diagnosisid"],
}

REQUIRED_COLUMNS = {
    "bi_patient_data": {"DeID"},
    "bi_visit_data": {"DeID", "VisitID"},
    "bi_diagnosis_data": {"DeID", "VisitID", "diagnosisid"},
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def mysql_type(series: pd.Series, column: str) -> str:
    """Choose a conservative MySQL type from the inspected pandas dtype."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "DATETIME"
    if pd.api.types.is_bool_dtype(series):
        return "TINYINT(1)"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series):
        # Source contains nulls in float columns; DOUBLE safely preserves
        # the workbook's numeric representation without assuming integer semantics.
        return "DOUBLE"
    # TEXT avoids arbitrary VARCHAR lengths and truncation of source text.
    return "TEXT"


def sql_identifier(name: str) -> str:
    """Quote an identifier after restricting it to known safe characters."""
    if not name or not all(ch.isalnum() or ch == "_" for ch in name):
        fail(f"Unsafe SQL identifier encountered: {name!r}")
    return f"`{name}`"


def prepare_tables() -> dict[str, pd.DataFrame]:
    if not WORKBOOK.is_file():
        fail(f"Workbook not found: {WORKBOOK}")
    if not ENV_FILE.is_file():
        fail(f".env file not found: {ENV_FILE}")

    loaded = pd.read_excel(WORKBOOK, sheet_name=list(SHEET_TO_TABLE))
    tables: dict[str, pd.DataFrame] = {}

    for sheet_name, table_name in SHEET_TO_TABLE.items():
        frame = loaded[sheet_name].copy()

        # Remove columns that are entirely empty; keep all other columns.
        frame = frame.dropna(axis=1, how="all")

        missing = REQUIRED_COLUMNS[table_name] - set(frame.columns)
        if missing:
            fail(
                f"{sheet_name} is missing required columns: "
                + ", ".join(sorted(missing))
            )

        for key in KEY_COLUMNS[table_name]:
            if frame[key].isna().any():
                fail(f"{table_name}.{key} contains null values.")
            if frame[key].duplicated().any():
                fail(f"{table_name}.{key} contains duplicate values.")

        tables[table_name] = frame

    patient_ids = set(tables["bi_patient_data"]["DeID"].dropna().tolist())
    visits = tables["bi_visit_data"]
    diagnoses = tables["bi_diagnosis_data"]

    if (~visits["DeID"].isin(patient_ids)).any():
        fail("Visit table contains a DeID absent from the patient table.")
    if (~diagnoses["DeID"].isin(patient_ids)).any():
        fail("Diagnosis table contains a DeID absent from the patient table.")

    visit_pairs = set(
        visits[["DeID", "VisitID"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    diagnosis_pairs = diagnoses[["DeID", "VisitID"]].drop_duplicates()
    if any(
        pair not in visit_pairs
        for pair in diagnosis_pairs.itertuples(index=False, name=None)
    ):
        fail("Diagnosis table contains a DeID/VisitID pair absent from visits.")

    return tables


def create_table_sql(table_name: str, frame: pd.DataFrame) -> str:
    columns: list[str] = []
    for column in frame.columns:
        col_type = mysql_type(frame[column], str(column))
        definition = f"{sql_identifier(str(column))} {col_type}"
        if column in KEY_COLUMNS[table_name]:
            definition += " NOT NULL"
        columns.append(definition)

    pk = KEY_COLUMNS[table_name]
    columns.append(
        "PRIMARY KEY (" + ", ".join(sql_identifier(k) for k in pk) + ")"
    )

    if table_name == "bi_visit_data":
        columns.append(
            "CONSTRAINT `fk_visit_patient` FOREIGN KEY (`DeID`) "
            "REFERENCES `bi_patient_data` (`DeID`)"
        )
    elif table_name == "bi_diagnosis_data":
        columns.append(
            "CONSTRAINT `fk_diagnosis_patient` FOREIGN KEY (`DeID`) "
            "REFERENCES `bi_patient_data` (`DeID`)"
        )
        # A composite parent key is required for the exact patient/visit pair.
        # It is added to the visit table below.
        columns.append(
            "CONSTRAINT `fk_diagnosis_visit_pair` "
            "FOREIGN KEY (`DeID`, `VisitID`) "
            "REFERENCES `bi_visit_data` (`DeID`, `VisitID`)"
        )

    if table_name == "bi_visit_data":
        columns.append("UNIQUE KEY `uq_visit_patient_pair` (`DeID`, `VisitID`)")

    return (
        f"CREATE TABLE {sql_identifier(table_name)} (\n  "
        + ",\n  ".join(columns)
        + "\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 "
        "COLLATE=utf8mb4_0900_ai_ci"
    )


def normalise_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    # Convert numpy scalar values to native Python scalars for connector.
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value


def main() -> int:
    load_dotenv(ENV_FILE)

    parser = argparse.ArgumentParser(description="Load the selected sample sheets into haven_poc_source.")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate workbook and connection, but do not create tables or load rows.",
    )
    args = parser.parse_args()

    db_host = os.getenv("DB_HOST")
    db_port_raw = os.getenv("DB_PORT", "3308")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if not db_host or not db_user or db_password is None:
        fail("DB_HOST, DB_USER, and DB_PASSWORD must be set in .env.")
    try:
        db_port = int(db_port_raw)
    except ValueError:
        fail("DB_PORT must be an integer if it is set in .env.")
    if not (1 <= db_port <= 65535):
        fail("DB_PORT must be between 1 and 65535.")

    if db_host != "127.0.0.1":
        fail("Refusing to connect: DB_HOST must be 127.0.0.1.")

    if db_port != 3308:
        fail("Refusing to connect: DB_PORT must be 3308.")

    tables = prepare_tables()

    print("Preflight validation passed.")
    for table_name, frame in tables.items():
        print(
            f"Prepared {table_name}: rows={len(frame)}, "
            f"columns={len(frame.columns)}"
        )
    print(f"Target schema: {SOURCE_SCHEMA}")
    print("No workbook record values will be printed.")

    connection = mysql.connector.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=SOURCE_SCHEMA,
        charset="utf8mb4",
        use_unicode=True,
        autocommit=False,
    )

    cursor = connection.cursor()
    created_tables: list[str] = []
    lock_acquired = False
    try:
        cursor.execute(
            "SELECT @@port, DATABASE(), CURRENT_USER()"
        )
        server_port, selected_schema, active_user = cursor.fetchone()

        if (
            server_port != 3308
            or selected_schema != SOURCE_SCHEMA
            or active_user != f"{db_user}@localhost"
        ):
            fail("MySQL server/schema/user identity check failed.")

        if db_host != "127.0.0.1":
            fail("Unexpected database host.")

        cursor.execute("SELECT GET_LOCK(%s, 10)", ("haven_poc_source_loader",))
        lock_result = cursor.fetchone()[0]
        if lock_result != 1:
            fail("Could not acquire source-loader lock; another load may be running.")
        lock_acquired = True

        cursor.execute("SELECT DATABASE()")
        selected_schema = cursor.fetchone()[0]
        if selected_schema != SOURCE_SCHEMA:
            fail(f"Connected to unexpected schema: {selected_schema!r}")

        # Refuse to overwrite or merge with any existing target tables.
        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME IN (%s, %s, %s)
            """,
            (
                SOURCE_SCHEMA,
                "bi_patient_data",
                "bi_visit_data",
                "bi_diagnosis_data",
            ),
        )
        existing = [row[0] for row in cursor.fetchall()]
        if existing:
            fail(
                "Refusing to overwrite existing target tables: "
                + ", ".join(existing)
            )

        if args.check_only:
            print("CHECK ONLY: workbook validation passed.")
            print(f"MySQL connection passed for schema {SOURCE_SCHEMA} on port {db_port}.")
            print("Target tables do not exist; no tables or rows were created.")
            return 0

        # MySQL DDL may commit implicitly. Track tables created by this run so
        # a failed load can remove only these newly created tables.
        cursor.execute(create_table_sql("bi_patient_data", tables["bi_patient_data"]))
        created_tables.append("bi_patient_data")
        cursor.execute(create_table_sql("bi_visit_data", tables["bi_visit_data"]))
        created_tables.append("bi_visit_data")
        cursor.execute(
            create_table_sql("bi_diagnosis_data", tables["bi_diagnosis_data"])
        )
        created_tables.append("bi_diagnosis_data")

        for table_name, frame in tables.items():
            columns = [str(c) for c in frame.columns]
            quoted_columns = ", ".join(sql_identifier(c) for c in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = (
                f"INSERT INTO {sql_identifier(table_name)} "
                f"({quoted_columns}) VALUES ({placeholders})"
            )
            rows = [
                tuple(normalise_value(value) for value in row)
                for row in frame.itertuples(index=False, name=None)
            ]
            cursor.executemany(insert_sql, rows)
            if cursor.rowcount != len(frame):
                fail(
                    f"Unexpected inserted row count for {table_name}: "
                    f"expected {len(frame)}, got {cursor.rowcount}"
                )

        # Check persisted row counts before committing.
        for table_name, frame in tables.items():
            cursor.execute(f"SELECT COUNT(*) FROM {sql_identifier(table_name)}")
            actual = int(cursor.fetchone()[0])
            if actual != len(frame):
                fail(
                    f"Row-count mismatch for {table_name}: "
                    f"expected {len(frame)}, got {actual}"
                )

        connection.commit()
        print("Load committed successfully.")
        for table_name, frame in tables.items():
            print(f"{table_name}: {len(frame)} rows loaded")
        print("Next step: run independent post-load key/relationship checks.")
        return 0

    except Exception:
        connection.rollback()
        # DDL may already be committed. Since all target tables were confirmed
        # absent while holding the loader lock, remove only tables created here.
        for table_name in reversed(created_tables):
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {sql_identifier(table_name)}")
            except mysql.connector.Error:
                pass
        raise
    finally:
        if lock_acquired:
            try:
                cursor.execute("SELECT RELEASE_LOCK(%s)", ("haven_poc_source_loader",))
                cursor.fetchone()
            except mysql.connector.Error:
                pass
        cursor.close()
        connection.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"LOAD FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
