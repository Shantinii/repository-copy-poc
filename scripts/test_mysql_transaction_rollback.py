
import getpass

import mysql.connector


HOST = "127.0.0.1"
PORT = 3308
USER = "haven_clinical_test"
SOURCE_SCHEMA = "haven_poc_source"
DEST_SCHEMA = "haven_poc_clinical_test"
TABLE = "bi_patient_data"


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
    )

    try:
        cursor = connection.cursor()

        # Confirm the connected account and capture the baseline.
        cursor.execute("SELECT CURRENT_USER()")
        current_user = cursor.fetchone()[0]
        if current_user != "haven_clinical_test@localhost":
            raise RuntimeError("Unexpected database account; test stopped.")

        cursor.execute(
            f"SELECT COUNT(*) FROM `{TABLE}`"
        )
        before_count = cursor.fetchone()[0]

        try:
            # Insert one source patient not already in the test destination.
            cursor.execute(
                f"""
                INSERT INTO `{DEST_SCHEMA}`.`{TABLE}`
                SELECT s.*
                FROM `{SOURCE_SCHEMA}`.`{TABLE}` AS s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM `{DEST_SCHEMA}`.`{TABLE}` AS d
                    WHERE d.`DeID` = s.`DeID`
                )
                LIMIT 1
                """
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "Could not insert exactly one test row; "
                    "rollback initiated."
                )

            print("Temporary insert succeeded.")

            # Simulate a failure after the insert.
            raise RuntimeError("Intentional rollback-test failure")

        except RuntimeError as exc:
            connection.rollback()
            if str(exc) == "Intentional rollback-test failure":
                print(f"Simulated failure handled: {exc}")
            else:
                raise

        # Verify the transaction left no additional row behind.
        cursor.execute(
            f"SELECT COUNT(*) FROM `{TABLE}`"
        )
        after_count = cursor.fetchone()[0]

        print(f"Patient row count before: {before_count}")
        print(f"Patient row count after:  {after_count}")

        if after_count != before_count:
            raise RuntimeError(
                "FAIL: row count changed after rollback."
            )

        print("PASS: transaction rolled back; row count unchanged.")

    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
