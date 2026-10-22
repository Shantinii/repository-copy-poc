import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import load_sample_source as loader


class FakeCursor:
    def __init__(
    self, schema, user, existing=(), fail_insert=False, fail_create=None
):
        self.schema = schema
        self.user = user
        self.existing = list(existing)
        self.fail_insert = fail_insert
        self.created = []
        self.dropped = []
        self.insert_attempts = 0
        self.one = None
        self.many = None
        self.fail_create = fail_create

    def execute(self, sql, params=None):
        self.one = None
        self.many = None
        statement = sql.strip()

        if statement.startswith("SELECT @@port"):
            self.one = (3308, self.schema, f"{self.user}@localhost")
        elif "GET_LOCK" in statement or "RELEASE_LOCK" in statement:
            self.one = (1,)
        elif statement == "SELECT DATABASE()":
            self.one = (self.schema,)
        elif "FROM information_schema.TABLES" in statement:
            self.many = [(name,) for name in self.existing]
        elif statement.startswith("CREATE TABLE"):
            name = statement.split("`")[1]
            if name == self.fail_create:
                raise RuntimeError(f"simulated create failure: {name}")
            self.created.append(name)
        elif statement.startswith("DROP TABLE IF EXISTS"):
            name = statement.split("`")[1]
            self.dropped.append(name)

    def executemany(self, sql, rows):
        self.insert_attempts += 1
        if self.fail_insert:
            raise RuntimeError("simulated insert failure")

    def fetchone(self):
        result, self.one = self.one, None
        return result

    def fetchall(self):
        result, self.many = self.many or [], None
        return result

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self.fake_cursor = cursor
        self.rollbacks = 0
        self.commits = 0

    def cursor(self):
        return self.fake_cursor

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        self.commits += 1

    def close(self):
        pass


@pytest.fixture
def setup_loader(monkeypatch):
    schema = "haven_poc_source_test"
    user = "test_loader"

    tables = {
        "bi_patient_data": pd.DataFrame({"DeID": [1]}),
        "bi_visit_data": pd.DataFrame({"DeID": [1], "VisitID": [10]}),
        "bi_diagnosis_data": pd.DataFrame(
            {"DeID": [1], "VisitID": [10], "diagnosisid": [100]}
        ),
    }

    monkeypatch.setattr(loader, "SOURCE_SCHEMA", schema)
    monkeypatch.setattr(loader, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(loader, "prepare_tables", lambda: tables)

    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_PORT", "3308")
    monkeypatch.setenv("DB_USER", user)
    monkeypatch.setenv("DB_PASSWORD", "test-only")
    monkeypatch.setattr(sys, "argv", ["load_sample_source.py"])

    return schema, user


def test_failed_insert_rolls_back_and_drops_only_created_tables(
    monkeypatch, setup_loader
):
    schema, user = setup_loader
    cursor = FakeCursor(schema, user, fail_insert=True)
    connection = FakeConnection(cursor)
    monkeypatch.setattr(
        loader.mysql.connector, "connect", lambda **kwargs: connection
    )

    with pytest.raises(RuntimeError, match="simulated insert failure"):
        loader.main()

    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert cursor.created == [
        "bi_patient_data", "bi_visit_data", "bi_diagnosis_data"
    ]
    assert cursor.dropped == [
        "bi_diagnosis_data", "bi_visit_data", "bi_patient_data"
    ]


def test_existing_tables_are_rejected_without_create_or_drop(
    monkeypatch, setup_loader
):
    schema, user = setup_loader
    cursor = FakeCursor(schema, user, existing=["bi_patient_data"])
    connection = FakeConnection(cursor)
    monkeypatch.setattr(
        loader.mysql.connector, "connect", lambda **kwargs: connection
    )

    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        loader.main()

    assert cursor.created == []
    assert cursor.dropped == []
    assert cursor.insert_attempts == 0
    assert connection.commits == 0
    assert connection.rollbacks == 1
def test_failed_second_create_drops_only_first_created_table(
    monkeypatch, setup_loader
):
    schema, user = setup_loader
    cursor = FakeCursor(schema, user, fail_create="bi_visit_data")
    connection = FakeConnection(cursor)

    monkeypatch.setattr(loader.mysql.connector, "connect", lambda **kwargs: connection)

    with pytest.raises(RuntimeError, match="simulated create failure"):
        loader.main()

    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert cursor.created == ["bi_patient_data"]
    assert cursor.dropped == ["bi_patient_data"]
    assert cursor.insert_attempts == 0

def test_failed_first_create_does_not_drop_any_tables(
    monkeypatch, setup_loader
):
    schema, user = setup_loader
    cursor = FakeCursor(schema, user, fail_create="bi_patient_data")
    connection = FakeConnection(cursor)

    monkeypatch.setattr(
        loader.mysql.connector, "connect", lambda **kwargs: connection
    )

    with pytest.raises(RuntimeError, match="simulated create failure"):
        loader.main()

    assert connection.rollbacks == 1
    assert connection.commits == 0
    assert cursor.created == []
    assert cursor.dropped == []
    assert cursor.insert_attempts == 0