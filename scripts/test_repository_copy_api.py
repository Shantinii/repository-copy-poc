"""Copy-engine unit tests for the dynamic clinical repository workflow across all 10 datasets.

Run from the repository root:
    python -m pytest -q scripts/test_repository_copy_api.py

These tests cover catalogue, cohort-copy SQL construction, project locks, and
copy-job state using mocked database operations. They do not connect to MySQL
or read clinical records. FastAPI endpoint tests are in test_api_fastapi.py.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Keep these unit tests runnable when mysql-connector-python is not installed.
# Any unexpected database connection attempt fails the test immediately.
try:
    import mysql.connector  # noqa: F401
except ModuleNotFoundError:
    mysql_module = types.ModuleType("mysql")
    connector_module = types.ModuleType("mysql.connector")

    class ConnectorError(Exception):
        pass

    def no_database_connection(*_args, **_kwargs):
        raise AssertionError("This unit test must not open a MySQL connection")

    connector_module.Error = ConnectorError
    connector_module.connect = no_database_connection
    mysql_module.connector = connector_module
    sys.modules["mysql"] = mysql_module
    sys.modules["mysql.connector"] = connector_module

import clinical_repository_copy as crc  # noqa: E402



ALL_DATASET_IDS = list(crc.DATASET_REGISTRY)
ALL_SOURCE_TABLES = {
    dataset_id: spec["source_table"]
    for dataset_id, spec in crc.DATASET_REGISTRY.items()
}


class RecordingCursor:
    def __init__(self, fetchone_values=(), rowcount=1):
        self.fetchone_values = list(fetchone_values)
        self.rowcount = rowcount
        self.calls = []
        self.closed = False

    def execute(self, statement, params=None):
        self.calls.append((" ".join(statement.split()), params))

    def fetchone(self):
        if not self.fetchone_values:
            return None
        return self.fetchone_values.pop(0)

    def close(self):
        self.closed = True


class RecordingConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True



def test_catalogue_registry_contains_all_ten_dataset_tables():
    document = json.loads(crc.DATASET_CATALOG_PATH.read_text(encoding="utf-8"))
    catalogue = {item["dataset_id"]: item["source_table"] for item in document}

    assert len(catalogue) == 10
    assert set(catalogue) == set(ALL_DATASET_IDS)
    assert catalogue == ALL_SOURCE_TABLES
    assert len(set(catalogue.values())) == 10
    assert all(
        spec["source_schema"] == crc.SOURCE_SCHEMA
        for spec in crc.DATASET_REGISTRY.values()
    )


def test_catalogue_loader_rejects_duplicate_dataset_ids(tmp_path):
    entry = {
        "dataset_id": "DS_PATIENT",
        "display_label": "Patient Demographics",
        "source_worksheet": "bi_patient data",
        "source_table": "bi_patient_data",
    }
    path = tmp_path / "dataset_catalog.json"
    path.write_text(json.dumps([entry, entry]), encoding="utf-8")

    with pytest.raises(crc.CopyValidationError, match="Duplicate dataset_id"):
        crc.load_dataset_registry(path)


def test_catalogue_loader_rejects_unsafe_table_names(tmp_path):
    entry = {
        "dataset_id": "DS_PATIENT",
        "display_label": "Patient Demographics",
        "source_worksheet": "bi_patient data",
        "source_table": "bi_patient_data;DROP_TABLE",
    }
    path = tmp_path / "dataset_catalog.json"
    path.write_text(json.dumps([entry]), encoding="utf-8")

    with pytest.raises(crc.CopyValidationError, match="invalid source_table"):
        crc.load_dataset_registry(path)


def test_project_schema_is_deterministic_and_project_scoped():
    schema_a = crc.project_schema_name("project_alpha")
    schema_b = crc.project_schema_name("project_beta")

    assert schema_a == "repo_project_project_alpha"
    assert schema_a != schema_b
    with pytest.raises(crc.CopyValidationError):
        crc.project_schema_name("Project Alpha")


def test_request_validation_accepts_all_ten_registered_datasets(capsys):
    result = crc.validate_dynamic_request(
        "project_alpha", ",".join(ALL_DATASET_IDS), '{"cohort_id":"cohort_001"}'
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "REQUEST VALIDATION PASSED" in output
    for dataset_id, source_table in ALL_SOURCE_TABLES.items():
        assert dataset_id in output
        assert source_table in output


def test_request_hash_is_stable_for_dataset_and_json_order():
    first = crc.canonical_request_hash(
        "project_alpha", ",".join(ALL_DATASET_IDS),
        '{"cohort_id":"cohort_001","limit":5}',
    )
    second = crc.canonical_request_hash(
        "project_alpha", ",".join(reversed(ALL_DATASET_IDS)),
        '{"limit":5,"cohort_id":"cohort_001"}',
    )

    assert first == second


def test_actual_copy_requires_only_an_approved_cohort_id():
    assert crc._cohort_id_from_request({"cohort_id": "cohort_001"}) == "cohort_001"
    with pytest.raises(crc.CopyValidationError):
        crc._cohort_id_from_request({"cohort_id": "cohort_001", "filters": []})
    with pytest.raises(crc.CopyValidationError):
        crc._cohort_id_from_request({"filters": []})


def test_project_schema_creation_creates_all_ten_selected_tables():
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)

    crc._create_project_tables(connection, "repo_project_alpha", ALL_DATASET_IDS)

    create_statements = [sql for sql, _ in cursor.calls if sql.startswith("CREATE TABLE")]
    created_targets = {
        sql.split("CREATE TABLE ", 1)[1].split(" LIKE ", 1)[0]
        for sql in create_statements
    }
    expected_targets = {
        f"`repo_project_alpha`.`{table}`" for table in ALL_SOURCE_TABLES.values()
    }

    assert len(create_statements) == 10
    assert created_targets == expected_targets
    assert sum(sql.startswith("ALTER TABLE") for sql, _ in cursor.calls) == 3
    assert cursor.closed


def test_selected_dataset_creation_does_not_create_unselected_tables():
    selected = ["DS_PATIENT", "DS_RADIOLOGY_PROCEDURE", "DS_VITAL_SIGNS"]
    cursor = RecordingCursor()
    connection = RecordingConnection(cursor)

    crc._create_project_tables(connection, "repo_project_alpha", selected)

    create_statements = [sql for sql, _ in cursor.calls if sql.startswith("CREATE TABLE")]
    created_targets = {
        sql.split("CREATE TABLE ", 1)[1].split(" LIKE ", 1)[0]
        for sql in create_statements
    }
    assert created_targets == {
        f"`repo_project_alpha`.`{ALL_SOURCE_TABLES[dataset_id]}`"
        for dataset_id in selected
    }
    assert len(create_statements) == len(selected)


def test_all_ten_source_tables_are_checked_for_cohort_key(monkeypatch):
    cursor = RecordingCursor(fetchone_values=[(1,)] * len(ALL_DATASET_IDS))
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(crc, "_open_copy_connection", lambda: connection)

    crc.validate_copy_dataset_dependencies(ALL_DATASET_IDS)

    assert len(cursor.calls) == 10
    checked_tables = [params[1] for _, params in cursor.calls]
    assert checked_tables == [ALL_SOURCE_TABLES[dataset_id] for dataset_id in ALL_DATASET_IDS]
    assert all("COLUMN_NAME='DeID'" in sql for sql, _ in cursor.calls)
    assert cursor.closed
    assert connection.closed


def test_missing_deid_in_any_selected_dataset_blocks_the_ten_dataset_copy(monkeypatch):
    responses = [(1,)] * 9 + [(0,)]
    cursor = RecordingCursor(fetchone_values=responses)
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(crc, "_open_copy_connection", lambda: connection)

    with pytest.raises(crc.CopyValidationError, match="DS_VITAL_SIGNS.*DeID"):
        crc.validate_copy_dataset_dependencies(ALL_DATASET_IDS)

    assert len(cursor.calls) == 10
    assert cursor.closed
    assert connection.closed


@pytest.mark.parametrize("dataset_id", ALL_DATASET_IDS)
def test_cohort_copy_uses_the_correct_source_and_destination_table(dataset_id):
    table = ALL_SOURCE_TABLES[dataset_id]
    cursor = RecordingCursor(fetchone_values=[(7,), (7,)])
    connection = RecordingConnection(cursor)

    result = crc._copy_cohort_table(
        connection, "repo_project_alpha", table, "project_alpha", "cohort_001"
    )

    assert result == (7, 7)
    assert len(cursor.calls) == 3
    count_sql, count_params = cursor.calls[0]
    insert_sql, insert_params = cursor.calls[1]
    destination_count_sql, _ = cursor.calls[2]

    assert f"`haven_poc_source`.`{table}`" in count_sql
    assert f"`repo_project_alpha`.`{table}`" in insert_sql
    assert f"`haven_poc_source`.`{table}`" in insert_sql
    assert "control_approved_cohort_members" in count_sql
    assert "control_approved_cohort_members" in insert_sql
    assert count_params == insert_params == ("project_alpha", "cohort_001")
    assert f"`repo_project_alpha`.`{table}`" in destination_count_sql
    assert cursor.closed


def test_project_lock_is_deterministic_and_bounded():
    lock_a = crc.project_lock_name("project_alpha")
    lock_b = crc.project_lock_name("project_beta")

    assert lock_a == "copy_project_alpha"
    assert lock_a == crc.project_lock_name("project_alpha")
    assert lock_a != lock_b
    assert len(lock_a) <= 64


def test_acquire_and_release_project_lock_use_mysql_lock_calls():
    acquire_cursor = RecordingCursor(fetchone_values=[(1,)])
    release_cursor = RecordingCursor(fetchone_values=[(1,)])
    connection = Mock()
    connection.cursor.side_effect = [acquire_cursor, release_cursor]

    assert crc.acquire_project_lock(connection, "project_alpha") is True
    assert crc.release_project_lock(connection, "project_alpha") is True

    assert "GET_LOCK" in acquire_cursor.calls[0][0]
    assert acquire_cursor.calls[0][1] == ("copy_project_alpha", 10)

    assert "RELEASE_LOCK" in release_cursor.calls[0][0]
    assert release_cursor.calls[0][1] == ("copy_project_alpha",)


def test_copy_job_claim_prevents_duplicate_completed_job():
    cursor = RecordingCursor(fetchone_values=[("completed",)])
    connection = RecordingConnection(cursor)

    result = crc.claim_copy_job(
        connection, "project_alpha", "a" * 64, ALL_DATASET_IDS, {"cohort_id": "cohort_001"}
    )

    assert result == "already_completed"
    assert not any("INSERT INTO control_copy_jobs" in call[0] for call in cursor.calls)


def test_copy_job_claim_blocks_running_duplicate():
    cursor = RecordingCursor(fetchone_values=[("running",)])
    connection = RecordingConnection(cursor)

    result = crc.claim_copy_job(
        connection, "project_alpha", "b" * 64, ALL_DATASET_IDS, {"cohort_id": "cohort_001"}
    )

    assert result == "already_running"


def test_copy_job_claim_creates_new_job_for_all_ten_datasets():
    cursor = RecordingCursor(fetchone_values=[None])
    connection = RecordingConnection(cursor)

    result = crc.claim_copy_job(
        connection, "project_alpha", "c" * 64, ALL_DATASET_IDS, {"cohort_id": "cohort_001"}
    )

    assert result == "claimed"
    insert_calls = [call for call in cursor.calls if "INSERT INTO control_copy_jobs" in call[0]]
    assert len(insert_calls) == 1
    assert json.loads(insert_calls[0][1][2]) == ALL_DATASET_IDS


def test_finish_copy_job_updates_only_running_job():
    cursor = RecordingCursor(rowcount=1)
    connection = RecordingConnection(cursor)

    crc.finish_copy_job(connection, "project_alpha", "d" * 64, success=True)

    assert "UPDATE control_copy_jobs" in cursor.calls[0][0]
    assert cursor.calls[0][1][0] == "completed"
    assert cursor.closed


def test_write_copy_completion_log_creates_structured_json(tmp_path, monkeypatch):
    import json

    log_path = tmp_path / "logs" / "repository_copy.log"
    monkeypatch.setattr(crc, "COPY_LOG_PATH", log_path)

    table_counts = [
        ("DS_PATIENT", 100, 100),
        ("DS_MEDICATION", 28, 28),
    ]

    crc.write_copy_completion_log(
        "project_alpha",
        "cohort_001",
        table_counts,
    )

    assert log_path.exists()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])

    assert entry["event"] == "repository_copy_completed"
    assert entry["status"] == "completed"
    assert entry["project_id"] == "project_alpha"
    assert entry["cohort_id"] == "cohort_001"
    assert entry["total_rows"] == 128
    assert entry["timestamp"].endswith("+00:00")

    assert entry["datasets"] == [
        {
            "dataset_id": "DS_PATIENT",
            "source_rows": 100,
            "destination_rows": 100,
        },
        {
            "dataset_id": "DS_MEDICATION",
            "source_rows": 28,
            "destination_rows": 28,
        },
    ]


def test_copy_logging_failure_does_not_raise_error(tmp_path, monkeypatch, capsys):
    blocked_parent = tmp_path / "not_a_directory"
    blocked_parent.write_text("blocking file", encoding="utf-8")

    monkeypatch.setattr(
        crc,

        "COPY_LOG_PATH",
        blocked_parent / "repository_copy.log",
    )

    crc.write_copy_completion_log(
        "project_alpha",
        "cohort_001",
        [("DS_PATIENT", 100, 100)],
    )

    captured = capsys.readouterr()
    assert "COPY LOG WARNING:" in captured.err
