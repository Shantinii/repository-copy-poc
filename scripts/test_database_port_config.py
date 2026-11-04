"""Tests for configurable MySQL DB_PORT handling; all connections are mocked."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

try:
    import mysql.connector  # noqa: F401
except ModuleNotFoundError:
    mysql_module = types.ModuleType("mysql")
    connector_module = types.ModuleType("mysql.connector")

    class ConnectorError(Exception):
        pass

    connector_module.Error = ConnectorError
    connector_module.connect = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("Unexpected MySQL connection")
    )
    mysql_module.connector = connector_module
    sys.modules["mysql"] = mysql_module
    sys.modules["mysql.connector"] = connector_module

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import clinical_repository_copy as crc  # noqa: E402


class FakeCursor:
    def __init__(self, port: int, user: str = "haven_clinical_copy"):
        self.port = port
        self.user = user
        self.calls = []
        self.closed = False

    def execute(self, statement, params=None):
        self.calls.append((statement, params))

    def fetchone(self):
        statement = self.calls[-1][0]
        if "DATABASE()" in statement and "CURRENT_USER()" in statement:
            return (self.port, crc.SOURCE_SCHEMA, f"{self.user}@localhost")
        if "DATABASE()" in statement:
            return (self.port, crc.SOURCE_SCHEMA)
        if "CURRENT_USER()" in statement:
            return (self.port, f"{self.user}@localhost")
        if "approval_status FROM control_research_projects" in statement:
            return ("approved",)
        return None

    def fetchall(self):
        return [("DS_PATIENT", "approved")]

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False
        self.committed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        self.closed = True


@pytest.mark.parametrize("port", [1, 3306, 3307, 3308, 65535])
def test_copy_connection_accepts_valid_configured_port(monkeypatch, port):
    user = "haven_clinical_copy"
    cursor = FakeCursor(port, user)
    connection = FakeConnection(cursor)
    connect = Mock(return_value=connection)
    monkeypatch.setattr(crc, "dotenv_values", lambda *_: {
        "CLINICAL_COPY_DB_USER": user,
        "CLINICAL_COPY_DB_PASSWORD": "test-password",
        "DB_PORT": str(port),
    })
    monkeypatch.setattr(crc.mysql.connector, "connect", connect)

    result = crc._open_copy_connection()

    assert result is connection
    assert connect.call_args.kwargs["port"] == port


@pytest.mark.parametrize("port", [1, 3306, 3307, 3308, 65535])
def test_schema_provisioner_accepts_valid_configured_port(monkeypatch, port):
    user = "haven_schema_provisioner"
    cursor = FakeCursor(port, user)
    connection = FakeConnection(cursor)
    connect = Mock(return_value=connection)
    monkeypatch.setattr(crc, "dotenv_values", lambda *_: {
        "SCHEMA_PROVISIONER_DB_USER": user,
        "SCHEMA_PROVISIONER_DB_PASSWORD": "test-password",
        "DB_PORT": str(port),
    })
    monkeypatch.setattr(crc.mysql.connector, "connect", connect)

    result = crc._open_schema_provisioner_connection()

    assert result is connection
    assert connect.call_args.kwargs["port"] == port


@pytest.mark.parametrize("port_value", ["0", "65536", "not-a-number"])
def test_all_engine_entry_points_reject_invalid_ports_before_connect(monkeypatch, port_value):
    connect = Mock(side_effect=AssertionError("MySQL must not be contacted for an invalid port"))
    monkeypatch.setattr(crc.mysql.connector, "connect", connect)
    monkeypatch.setattr(crc, "dotenv_values", lambda *_: {
        "DB_USER": "haven_loader",
        "DB_PASSWORD": "test-password",
        "CLINICAL_COPY_DB_USER": "haven_clinical_copy",
        "CLINICAL_COPY_DB_PASSWORD": "test-password",
        "SCHEMA_PROVISIONER_DB_USER": "haven_schema_provisioner",
        "SCHEMA_PROVISIONER_DB_PASSWORD": "test-password",
        "DB_PORT": port_value,
    })

    with pytest.raises(crc.CopyValidationError):
        crc._open_copy_connection()

    with pytest.raises(crc.CopyValidationError):
        crc._open_schema_provisioner_connection()

    with pytest.raises(crc.CopyValidationError):
        crc.run_legacy_copy()

    with pytest.raises(crc.CopyValidationError):
        crc.authorize_dynamic_request(
            "proj_101", "DS_PATIENT", return_allowlist=True
        )

    connect.assert_not_called()


@pytest.mark.parametrize("port", [3306, 3307, 3308, 65535])
def test_authorization_accepts_valid_configured_port(monkeypatch, port):
    user = "haven_loader"
    cursor = FakeCursor(port, user)
    connection = FakeConnection(cursor)
    connect = Mock(return_value=connection)
    monkeypatch.setattr(crc, "dotenv_values", lambda *_: {
        "DB_USER": user,
        "DB_PASSWORD": "test-password",
        "DB_PORT": str(port),
    })
    monkeypatch.setattr(crc.mysql.connector, "connect", connect)

    result = crc.authorize_dynamic_request(
        "proj_101", "DS_PATIENT", return_allowlist=True
    )

    assert result == {"proj_101": {"DS_PATIENT"}}
    assert connect.call_args.kwargs["port"] == port
