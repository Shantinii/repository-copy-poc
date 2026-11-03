import sys
from collections import Counter
from pathlib import Path

import mysql.connector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stage_all_worksheets as loader


def main():
    datasets, _ = loader.read_workbook()
    host, port, user, password = loader.validate_db_config()

    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=loader.SOURCE_SCHEMA,
        charset="utf8mb4",
        use_unicode=True,
    )

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT @@port, DATABASE()")
        actual_port, actual_schema = cursor.fetchone()

        if actual_port != 3308 or actual_schema != "haven_poc_source":
            raise RuntimeError("Database identity check failed.")

        print("READ-ONLY WORKBOOK VS STAGING COMPARISON")
        print("=" * 75)

        all_match = True

        for item in datasets:
            table = item["table_name"]

            cursor.execute("""
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """, ("haven_poc_source", table))

            actual_columns = [row[0] for row in cursor.fetchall()]
            columns_match = actual_columns == item["headers"]

            cursor.execute(
                f"SELECT * FROM {loader.quote_identifier(table)}"
            )
            actual_rows = [tuple(row) for row in cursor.fetchall()]

            expected = Counter(item["records"])
            actual = Counter(actual_rows)

            missing = sum((expected - actual).values())
            extra = sum((actual - expected).values())

            matched = columns_match and missing == 0 and extra == 0
            all_match = all_match and matched

            print(f"\n{table}")
            print(f"  Workbook rows:       {item['row_count']}")
            print(f"  Staging rows:        {len(actual_rows)}")
            print(f"  Column order match:  {columns_match}")
            print(f"  Missing rows:        {missing}")
            print(f"  Extra rows:          {extra}")
            print(f"  Exact content match: {matched}")

        print("\n" + "=" * 75)
        print(
            "OVERALL RESULT:",
            "ALL TEN TABLES MATCH" if all_match else "MISMATCH FOUND",
        )

        return 0 if all_match else 1

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
