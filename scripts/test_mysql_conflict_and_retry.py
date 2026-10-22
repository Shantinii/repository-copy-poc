import getpass
import sys
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import repository_copy_core as repo  # noqa: E402

HOST = "127.0.0.1"
PORT = 3308
USER = "haven_clinical_test"
SOURCE_SCHEMA = "haven_poc_source"
DEST_SCHEMA = "haven_poc_clinical_test"

PRIMARY_KEYS = {
    "bi_patient_data": "DeID",
    "bi_visit_data": "VisitID",
    "bi_diagnosis_data": "diagnosisid",
}
DELETE_ORDER = ("bi_diagnosis_data", "bi_visit_data", "bi_patient_data")
INSERT_ORDER = ("bi_patient_data", "bi_visit_data", "bi_diagnosis_data")


def read_table(cursor, schema, table):
    key = PRIMARY_KEYS[table]
    cursor.execute(
        f"SELECT * FROM `{schema}`.`{table}` ORDER BY `{key}`"
    )
    columns = tuple(item[0] for item in cursor.description)
    rows = [tuple(row) for row in cursor.fetchall()]
    return columns, rows


def read_all(cursor, schema):
    result = {}
    for table in repo.EXPECTED_TABLES:
        columns, rows = read_table(cursor, schema, table)
        result[table] = rows
    return result


def insert_source_rows(cursor, source_columns, source_rows):
    for table in INSERT_ORDER:
        columns = source_columns[table]
        rows = source_rows[table]
        if not rows:
            continue
        column_sql = ", ".join(f"`{column}`" for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = (
            f"INSERT INTO `{DEST_SCHEMA}`.`{table}` "
            f"({column_sql}) VALUES ({placeholders})"
        )
        cursor.executemany(sql, rows)


def clear_destination(cursor):
    for table in DELETE_ORDER:
        cursor.execute(f"DELETE FROM `{DEST_SCHEMA}`.`{table}`")


def counts(cursor):
    result = {}
    for table in repo.EXPECTED_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM `{DEST_SCHEMA}`.`{table}`")
        result[table] = cursor.fetchone()[0]
    return result


def main():
    password = getpass.getpass("Test database password: ")
    connection = mysql.connector.connect(
        host=HOST,
        port=PORT,
        user=USER,
        password=password,
        database=DEST_SCHEMA,
        connection_timeout=5,
        autocommit=False,
        charset="utf8mb4",
    )

    try:
        cursor = connection.cursor()
        cursor.execute("SELECT @@port, DATABASE(), CURRENT_USER()")
        identity = cursor.fetchone()
        expected_identity = (PORT, DEST_SCHEMA, f"{USER}@localhost")
        if identity != expected_identity:
            raise RuntimeError(
                f"Safety stop: unexpected connection identity {identity!r}"
            )

        connection.rollback()
        source_columns = {}
        source_rows = {}
        for table in repo.EXPECTED_TABLES:
            source_columns[table], source_rows[table] = read_table(
                cursor, SOURCE_SCHEMA, table
            )
            dest_columns, _ = read_table(cursor, DEST_SCHEMA, table)
            if source_columns[table] != dest_columns:
                raise RuntimeError(
                    f"Safety stop: source/destination columns differ for {table}"
                )

        initial_counts = counts(cursor)
        expected_initial = {
            "bi_patient_data": 1,
            "bi_visit_data": 0,
            "bi_diagnosis_data": 0,
        }
        if initial_counts != expected_initial:
            raise RuntimeError(
                "Safety stop: test destination is not in the expected baseline. "
                f"Found {initial_counts}"
            )

        print("Safety checks passed: test schema/account verified.")
        print("Test 1/2: conflicting destination rejection")

        # Build an exact destination inside one transaction, then deliberately
        # alter one destination value. The final rollback restores the baseline.
        connection.rollback()
        try:
            clear_destination(cursor)
            insert_source_rows(cursor, source_columns, source_rows)

            exact_rows = read_all(cursor, DEST_SCHEMA)
            repo.validate_destination_state(source_rows, exact_rows)
            print("  Exact source copy validated inside test transaction.")

            patient_columns = source_columns["bi_patient_data"]
            if "Gender" not in patient_columns:
                raise RuntimeError(
                    "Safety stop: expected Gender column is unavailable."
                )
            gender_index = patient_columns.index("Gender")
            patient_key_index = patient_columns.index("DeID")
            if not source_rows["bi_patient_data"]:
                raise RuntimeError("Safety stop: source patient table is empty.")

            patient_row = source_rows["bi_patient_data"][0]
            patient_id = patient_row[patient_key_index]
            original_gender = patient_row[gender_index]
            conflict_value = "__PHASE4_CONFLICT_TEST__"
            if original_gender == conflict_value:
                conflict_value = "__PHASE4_CONFLICT_TEST_2__"

            cursor.execute(
                f"UPDATE `{DEST_SCHEMA}`.`bi_patient_data` "
                "SET `Gender` = %s WHERE `DeID` = %s",
                (conflict_value, patient_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Safety stop: conflict mutation did not affect exactly one row."
                )

            conflicted_rows = read_all(cursor, DEST_SCHEMA)
            try:
                repo.validate_destination_state(source_rows, conflicted_rows)
            except repo.DatasetValidationError:
                print("  PASS: live MySQL conflict rejected.")
            else:
                raise RuntimeError(
                    "FAIL: conflicting destination was accepted."
                )
        finally:
            connection.rollback()

        restored_counts = counts(cursor)
        if restored_counts != expected_initial:
            raise RuntimeError(
                "FAIL: conflict test did not restore the original test baseline. "
                f"Found {restored_counts}"
            )
        print("  PASS: conflict-test transaction rolled back; baseline restored.")

        print("Test 2/2: retry after failure")
        # Simulate a retry from the known partial baseline. All changes are
        # confined to the disposable test schema; successful retry commits an
        # exact copy there.
        connection.rollback()
        clear_destination(cursor)
        insert_source_rows(cursor, source_columns, source_rows)
        retry_rows = read_all(cursor, DEST_SCHEMA)
        repo.validate_destination_state(source_rows, retry_rows)
        connection.commit()

        connection.rollback()
        final_rows = read_all(cursor, DEST_SCHEMA)
        repo.validate_destination_state(source_rows, final_rows)
        final_counts = {table: len(rows) for table, rows in final_rows.items()}
        expected_final = {
            table: len(source_rows[table]) for table in repo.EXPECTED_TABLES
        }
        if final_counts != expected_final:
            raise RuntimeError(
                f"FAIL: retry counts do not match source: {final_counts}"
            )

        print("  PASS: retry completed and exact-match validation passed.")
        print("Final test-schema row counts:")
        for table in repo.EXPECTED_TABLES:
            print(f"  {table}: {final_counts[table]}")
        print(
            "RESULT: live conflict rejection and successful retry both passed. "
            "The disposable test schema now contains an exact source copy."
        )
        cursor.close()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    main()
