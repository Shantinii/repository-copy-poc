
from pathlib import Path
import os
import sys
import getpass
import mysql.connector
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import repository_copy_core as repo

load_dotenv(ROOT / ".env")

TABLES = repo.EXPECTED_TABLES
SOURCE_SCHEMA = "haven_poc_source"
DEST_SCHEMA = "haven_poc_clinical_test"


def read_rows(cursor, schema, table):
    # Table names and schemas come only from constants above.
    cursor.execute(
        f"SELECT * FROM `{schema}`.`{table}` "
        f"ORDER BY " + {
            "bi_patient_data": "`DeID`",
            "bi_visit_data": "`VisitID`",
            "bi_diagnosis_data": "`diagnosisid`",
        }[table]
    )
    return [tuple(row) for row in cursor.fetchall()]


def main():
    connection = mysql.connector.connect(
        host="127.0.0.1",
        port=3308,
        user=os.environ["TEST_DB_USER"],
        password=getpass.getpass("Test database password: "),
        database=DEST_SCHEMA,
        connection_timeout=5,
    )

    try:
        cursor = connection.cursor()
        source = {
            table: read_rows(cursor, SOURCE_SCHEMA, table)
            for table in TABLES
        }
        destination = {
            table: read_rows(cursor, DEST_SCHEMA, table)
            for table in TABLES
        }

        print("Destination counts:")
        for table in TABLES:
            print(f"{table}: {len(destination[table])}")

        expected_counts = {
            "bi_patient_data": 1,
            "bi_visit_data": 0,
            "bi_diagnosis_data": 0,
        }
        actual_counts = {
            table: len(destination[table])
            for table in TABLES
        }

        if actual_counts != expected_counts:
            raise AssertionError(
                "Test stopped: disposable destination is not in the "
                f"expected partial state. Actual counts: {actual_counts}"
            )

        try:
            state = repo.validate_destination_state(source, destination)
        except repo.DatasetValidationError as exc:
            message = str(exc).lower()
            if "partial" not in message:
                raise AssertionError(
                    "Destination was rejected, but not for the expected "
                    f"partial-state reason: {exc}"
                ) from exc
            print(
                "PASS: partial destination rejected; "
                "no database writes attempted."
            )
        else:
            raise AssertionError(
                f"FAIL: partial destination was accepted as {state}."
            )
        cursor.close()
    finally:
        connection.close()


if __name__ == "__main__":
    main()
