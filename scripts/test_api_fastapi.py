"""Unit tests for the FastAPI repository-copy endpoint.

Run from the repository root:
    python -m pytest -q scripts/test_api_fastapi.py

All copy and authorization operations are mocked. These tests do not connect
 to MySQL or read clinical records.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Permit unit testing without opening MySQL when the connector is absent.
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

import api as api_module  # noqa: E402


VALID_PAYLOAD = {
    "project_id": "proj_101",
    "payment_id": "pay_99823",
    "approved_datasets": ["DS_PATIENT", "DS_VISIT", "DS_DIAGNOSIS"],
    "cohort_id": "cohort_001",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "dotenv_values",
        lambda *_args, **_kwargs: {"COPY_API_TOKEN": "test-token"},
    )
    monkeypatch.setattr(api_module.clinical_copy, "validate_dynamic_request", lambda *_args: 0)
    monkeypatch.setattr(
        api_module.clinical_copy,
        "authorize_dynamic_request",
        lambda project_id, _ids, return_allowlist=False: (
            {project_id: set(VALID_PAYLOAD["approved_datasets"])} if return_allowlist else 0
        ),
    )
    monkeypatch.setattr(api_module.clinical_copy, "run_dynamic_copy_job", lambda *_args: 0)
    monkeypatch.setattr(
        api_module.clinical_copy,
        "project_schema_name",
        lambda project_id: f"repo_project_{project_id}",
    )
    monkeypatch.setattr(api_module, "get_verified_payment_status", lambda *_args: "succeeded")
    return TestClient(api_module.app)


def test_api_rejects_missing_bearer_token(client):
    response = client.post("/api/repository/copy", json=VALID_PAYLOAD)
    assert response.status_code == 401


def test_api_fails_closed_when_payment_verifier_is_not_configured(client, monkeypatch):
    authorize = Mock()
    monkeypatch.setattr(api_module.clinical_copy, "authorize_dynamic_request", authorize)
    monkeypatch.setattr(
        api_module,
        "get_verified_payment_status",
        lambda *_args: (_ for _ in ()).throw(api_module.PaymentVerificationUnavailable("not configured")),
    )

    response = client.post(
        "/api/repository/copy",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 503
    authorize.assert_not_called()


def test_api_rejects_unsuccessful_payment_before_authorization(client, monkeypatch):
    authorize = Mock()
    monkeypatch.setattr(api_module.clinical_copy, "authorize_dynamic_request", authorize)
    monkeypatch.setattr(api_module, "get_verified_payment_status", lambda *_args: "pending")

    response = client.post(
        "/api/repository/copy",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 402
    authorize.assert_not_called()


def test_api_rejects_unapproved_project_dataset_before_copy(client, monkeypatch):
    copy_job = Mock(return_value=0)
    monkeypatch.setattr(
        api_module.clinical_copy,
        "authorize_dynamic_request",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(api_module.clinical_copy, "run_dynamic_copy_job", copy_job)

    response = client.post(
        "/api/repository/copy",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 403
    copy_job.assert_not_called()


def test_api_submits_authorized_request_to_existing_copy_engine(client, monkeypatch):
    copy_job = Mock(return_value=0)
    monkeypatch.setattr(api_module.clinical_copy, "run_dynamic_copy_job", copy_job)

    response = client.post(
        "/api/repository/copy",
        json=VALID_PAYLOAD,
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "status",
        "project_id",
        "target_schema",
        "database_host",
        "database_port",
        "available_tables",
        "timestamp",
    }
    assert payload["status"] == "SUCCESS"
    assert payload["project_id"] == "proj_101"
    assert payload["target_schema"] == "repo_project_proj_101"
    assert payload["database_host"] == "127.0.0.1"
    assert payload["database_port"] == 3308
    assert payload["available_tables"] == [
        api_module.clinical_copy.DATASET_REGISTRY[dataset_id]["source_table"]
        for dataset_id in VALID_PAYLOAD["approved_datasets"]
    ]
    assert payload["timestamp"].endswith("Z")
    copy_job.assert_called_once_with(
        "proj_101",
        "DS_PATIENT,DS_VISIT,DS_DIAGNOSIS",
        '{"cohort_id":"cohort_001"}',
    )
