"""Tests for the Phase 3 project-schema metadata helper."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

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


class RecordingCursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.closed = False

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        return self.rows

    def close(self):
        self.closed = True


class RecordingConnection:
    def __init__(self, cursor):
        self.recording_cursor = cursor
        self.closed = False

    def cursor(self):
        return self.recording_cursor

    def close(self):
        self.closed = True


def test_get_schema_context_returns_column_names_and_data_types(monkeypatch):
    rows = [
        ("bi_patient_data", "DeID", "varchar"),
        ("bi_patient_data", "Age", "int"),
        ("bi_visit_data", "VisitID", "varchar"),
    ]
    cursor = RecordingCursor(rows)
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(crc, "_open_copy_connection", lambda: connection)

    result = crc.get_schema_context("proj_101")

    assert result == {
        "project_id": "proj_101",
        "schema": "repo_project_proj_101",
        "tables": {
            "bi_patient_data": [
                {"column_name": "DeID", "data_type": "varchar"},
                {"column_name": "Age", "data_type": "int"},
            ],
            "bi_visit_data": [
                {"column_name": "VisitID", "data_type": "varchar"},
            ],
        },
    }
    query, params = cursor.calls[0]
    assert "INFORMATION_SCHEMA.COLUMNS" in query
    assert "TABLE_SCHEMA=%s" in query
    assert params[0] == "repo_project_proj_101"
    assert set(params[1:]) == {
        spec["source_table"] for spec in crc.DATASET_REGISTRY.values()
    }
    assert cursor.closed
    assert connection.closed


def test_get_schema_context_rejects_invalid_project_id(monkeypatch):
    connection_attempted = False

    def unexpected_connection():
        nonlocal connection_attempted
        connection_attempted = True
        raise AssertionError("Invalid project IDs must be rejected before connecting")

    monkeypatch.setattr(crc, "_open_copy_connection", unexpected_connection)

    with pytest.raises(crc.CopyValidationError):
        crc.get_schema_context("../other_schema")

    assert connection_attempted is False


def test_get_schema_context_rejects_schema_without_registered_tables(monkeypatch):
    cursor = RecordingCursor([])
    connection = RecordingConnection(cursor)
    monkeypatch.setattr(crc, "_open_copy_connection", lambda: connection)

    with pytest.raises(crc.CopyValidationError, match="No registered dataset tables"):
        crc.get_schema_context("proj_101")

    assert cursor.closed
    assert connection.closed
