"""Copy approved cohort datasets into isolated clinical project schemas.

This script is separate from mysql_repository_copy_poc.py.
It copies no data unless the destination tables are empty. If all destination
tables already match the source exactly, it reports that state without writing.
Any partial or conflicting destination state is rejected.

It prints counts and validation results only, never clinical row values or secrets.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from typing import Any

import mysql.connector
from dotenv import dotenv_values

from repository_copy_core import (
    AuthorizationError as CoreAuthorizationError,
    CopyRequest,
    ValidationReport,
    validate_copy_row_counts,
    validate_project_dataset,
)


ROOT_ENV = ".env"
SOURCE_SCHEMA = "haven_poc_source"
DESTINATION_SCHEMA = "haven_poc_clinical_001"

LEGACY_CORE_DATASET_IDS = ("DS_PATIENT", "DS_VISIT", "DS_DIAGNOSIS")


import argparse
import json
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROJECT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,49}$")
DATASET_ID_RE = re.compile(r"^DS_[A-Z0-9_]+$")
FILTER_OPERATORS = {"eq", "ne", "lt", "lte", "gt", "gte", "in", "between", "is_null"}
COLUMN_MAP_PATH = Path(__file__).resolve().parent.parent / "docs" / "approved_column_map.json"
COLUMN_MAP_APPROVED_STATUS = "APPROVED_FOR_FILTERING"
COLUMN_APPROVED_STATUS = "APPROVED_FOR_FILTERING"


class CopyValidationError(RuntimeError):
    """Raised when source or destination validation fails."""


def load_approved_column_map() -> dict[tuple[str, str], dict[str, Any]]:
    """Load and validate the approved column map; fail closed on any issue."""
    try:
        with COLUMN_MAP_PATH.open("r", encoding="utf-8") as map_file:
            document = json.load(map_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise CopyValidationError("Approved column map is missing or invalid; filters are blocked") from exc

    if not isinstance(document, dict) or document.get("document_type") != "DRAFT_APPROVED_COLUMN_MAP":
        raise CopyValidationError("Approved column map has an unexpected document type; filters are blocked")
    if document.get("status") != COLUMN_MAP_APPROVED_STATUS:
        raise CopyValidationError("Column map is not approved for filtering; filters are blocked")
    columns = document.get("columns")
    if not isinstance(columns, list):
        raise CopyValidationError("Approved column map has no valid columns list; filters are blocked")

    result: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in columns:
        if not isinstance(entry, dict):
            raise CopyValidationError("Approved column map contains an invalid entry; filters are blocked")
        dataset_id = entry.get("dataset_id")
        column_name = entry.get("column_name")
        if not isinstance(dataset_id, str) or not isinstance(column_name, str) or not dataset_id or not column_name:
            raise CopyValidationError("Approved column map contains an entry without dataset/column identifiers")
        key = (dataset_id, column_name)
        if key in result:
            raise CopyValidationError("Approved column map contains duplicate dataset/column entries")
        operators = entry.get("permitted_filter_operators")
        if not isinstance(operators, list) or any(not isinstance(op, str) or op not in FILTER_OPERATORS for op in operators):
            raise CopyValidationError("Approved column map contains invalid permitted operators")
        result[key] = entry
    return result


def validate_filter_against_column_map(dataset_id: str, column_name: str, operator: str) -> None:
    """Require explicit column approval and operator approval before accepting a filter."""
    column_map = load_approved_column_map()
    entry = column_map.get((dataset_id, column_name))
    if entry is None:
        raise CopyValidationError(f"Column {dataset_id}.{column_name} is not present in the approved column map")
    if entry.get("approval_status") != COLUMN_APPROVED_STATUS:
        raise CopyValidationError(f"Column {dataset_id}.{column_name} is not approved for filtering")
    if operator not in entry.get("permitted_filter_operators", []):
        raise CopyValidationError(f"Operator {operator} is not approved for {dataset_id}.{column_name}")


def validate_dynamic_request(project_id: str, dataset_ids_raw: str, cohort_raw: str) -> int:
    """Validate a structured request only; this function never connects to MySQL."""
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise CopyValidationError("project_id must start with a lowercase letter and contain only lowercase letters, digits, _ or - (max 50 characters)")
    ids = [part.strip() for part in dataset_ids_raw.split(",")]
    if not ids or any(not item for item in ids):
        raise CopyValidationError("Provide one or more comma-separated dataset IDs")
    if any(not DATASET_ID_RE.fullmatch(item) for item in ids):
        raise CopyValidationError("Dataset IDs must use the registered DS_* format")
    if len(ids) != len(set(ids)):
        raise CopyValidationError("Duplicate dataset IDs are not allowed")
    unknown = sorted(set(ids) - DATASET_REGISTRY.keys())
    if unknown:
        raise CopyValidationError("Unknown dataset ID(s): " + ", ".join(unknown))
    # Accept inline JSON or @path-to-JSON-file. The file form avoids Windows
    # PowerShell quoting issues. File contents are parsed as data, never executed.
    if cohort_raw.startswith("@"):
        cohort_path = cohort_raw[1:]
        if not cohort_path:
            raise CopyValidationError("--cohort-json @file requires a file path")
        try:
            with open(cohort_path, "r", encoding="utf-8") as cohort_file:
                cohort_raw = cohort_file.read()
        except OSError as exc:
            raise CopyValidationError("Could not read the --cohort-json file") from exc
    try:
        cohort = json.loads(cohort_raw)
    except json.JSONDecodeError as exc:
        raise CopyValidationError("--cohort-json must contain valid JSON or @path-to-JSON-file") from exc
    if not isinstance(cohort, dict) or set(cohort) - {"filters", "limit", "cohort_id"}:
        raise CopyValidationError("Cohort JSON must be an object containing only filters, limit, and cohort_id")
    if "cohort_id" in cohort and not isinstance(cohort["cohort_id"], str):
        raise CopyValidationError("cohort_id must be a string")
    if "limit" in cohort and (isinstance(cohort["limit"], bool) or not isinstance(cohort["limit"], int) or not 1 <= cohort["limit"] <= 1000000):
        raise CopyValidationError("limit must be an integer from 1 to 1000000")
    filters = cohort.get("filters", [])
    if not isinstance(filters, list):
        raise CopyValidationError("filters must be a list")
    for index, item in enumerate(filters):
        if not isinstance(item, dict) or set(item) - {"dataset_id", "column", "operator", "value"}:
            raise CopyValidationError(f"Filter {index} has unsupported fields")
        if not all(isinstance(item.get(key), str) and item[key] for key in ("dataset_id", "column", "operator")):
            raise CopyValidationError(f"Filter {index} requires dataset_id, column, and operator")
        if item["dataset_id"] not in DATASET_REGISTRY:
            raise CopyValidationError(f"Filter {index} references an unknown dataset")
        if item["dataset_id"] not in ids:
            raise CopyValidationError("Every cohort filter must target a selected dataset")
        if item["operator"] not in FILTER_OPERATORS:
            raise CopyValidationError(f"Filter {index} uses an unsupported operator")
        validate_filter_against_column_map(item["dataset_id"], item["column"], item["operator"])
        if item["operator"] == "is_null" and "value" in item:
            raise CopyValidationError(f"Filter {index}: is_null must not include value")
        if item["operator"] != "is_null" and "value" not in item:
            raise CopyValidationError(f"Filter {index} requires value")
    print("REQUEST VALIDATION PASSED (syntax and registry preflight).")
    print(f"Project ID: {project_id}")
    unresolved = []
    for dataset_id in ids:
        spec = DATASET_REGISTRY[dataset_id]
        pk = ", ".join(spec["primary_key"]) if spec["primary_key"] else "not required for append-only cohort copy"
        print(f"  {dataset_id}: source={spec['source_table']}; primary_key={pk}; key_status={spec['key_status']}")
        if spec["key_status"] == "unresolved":
            unresolved.append(dataset_id)
    print(f"Cohort filters supplied: {len(filters)}")
    if filters:
        print("Filter syntax was checked against the approved column map; filters are not executed by the copy engine.")
    if "cohort_id" in cohort:
        print("Approved cohort ID supplied; database approval is checked during execution.")
    if unresolved:
        print("BLOCKED FOR COPYING: primary-key metadata unresolved for: " + ", ".join(unresolved))
    print("Request validation itself performed no database connection or writes.")
    return 0


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COPY_LOG_PATH = PROJECT_ROOT / "logs" / "repository_copy.log"
DATASET_CATALOG_CANDIDATES = (
    PROJECT_ROOT / "docs" / "dataset_catalog.json",
    PROJECT_ROOT / "dataset_catalog.json",
)


def _resolve_dataset_catalog_path() -> Path:
    for candidate in DATASET_CATALOG_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise CopyValidationError(
        "dataset_catalog.json was not found in docs/ or the repository root"
    )


DATASET_CATALOG_PATH = _resolve_dataset_catalog_path()


def load_dataset_registry(catalog_path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    """Build the executable dataset registry from dataset_catalog.json."""
    path = Path(catalog_path) if catalog_path is not None else DATASET_CATALOG_PATH
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CopyValidationError("dataset_catalog.json is missing or invalid") from exc

    if isinstance(document, dict):
        document = document.get("datasets")
    if not isinstance(document, list) or not document:
        raise CopyValidationError("dataset_catalog.json must contain a non-empty dataset list")

    registry: dict[str, dict[str, Any]] = {}
    used_tables: set[str] = set()
    for index, item in enumerate(document):
        if not isinstance(item, dict):
            raise CopyValidationError(f"Dataset catalogue entry {index} must be an object")
        dataset_id = item.get("dataset_id")
        source_table = item.get("source_table")
        display_label = item.get("display_label")
        source_worksheet = item.get("source_worksheet")
        source_schema = item.get("source_schema", SOURCE_SCHEMA)

        if not isinstance(dataset_id, str) or not DATASET_ID_RE.fullmatch(dataset_id):
            raise CopyValidationError(f"Dataset catalogue entry {index} has an invalid dataset_id")
        if dataset_id in registry:
            raise CopyValidationError(f"Duplicate dataset_id in dataset_catalog.json: {dataset_id}")
        if not isinstance(source_table, str) or not IDENTIFIER_RE.fullmatch(source_table):
            raise CopyValidationError(f"Dataset {dataset_id} has an invalid source_table")
        if source_table in used_tables:
            raise CopyValidationError(f"Duplicate source_table in dataset_catalog.json: {source_table}")
        if not isinstance(display_label, str) or not display_label.strip():
            raise CopyValidationError(f"Dataset {dataset_id} has an invalid display_label")
        if not isinstance(source_worksheet, str) or not source_worksheet:
            raise CopyValidationError(f"Dataset {dataset_id} has an invalid source_worksheet")
        if source_schema != SOURCE_SCHEMA:
            raise CopyValidationError(f"Dataset {dataset_id} has an unsupported source_schema")

        primary_key = item.get("primary_key")
        if primary_key is not None:
            if not isinstance(primary_key, list) or not primary_key or any(
                not isinstance(column, str) or not IDENTIFIER_RE.fullmatch(column)
                for column in primary_key
            ):
                raise CopyValidationError(f"Dataset {dataset_id} has invalid primary_key metadata")
            primary_key = tuple(primary_key)

        key_status = item.get("key_status", "catalogue_only")
        if not isinstance(key_status, str) or not key_status:
            raise CopyValidationError(f"Dataset {dataset_id} has invalid key_status")

        registry[dataset_id] = {
            "display_label": display_label,
            "source_worksheet": source_worksheet,
            "source_schema": source_schema,
            "source_table": source_table,
            "primary_key": primary_key,
            "key_status": key_status,
        }
        used_tables.add(source_table)

    return registry


# Every requested dataset and destination table is resolved from this catalogue.
DATASET_REGISTRY = load_dataset_registry()

# Phase 2 safety primitives for request tracking and dynamic copying.
import hashlib
from contextlib import contextmanager


def canonical_request_hash(project_id: str, dataset_ids_raw: str, cohort_raw: str) -> tuple[str, list[str], dict[str, Any]]:
    """Return a stable hash for an equivalent project/dataset/cohort request."""
    dataset_ids = sorted({part.strip() for part in dataset_ids_raw.split(",") if part.strip()})
    if not dataset_ids:
        raise CopyValidationError("At least one dataset ID is required for a copy request")
    try:
        cohort = json.loads(cohort_raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise CopyValidationError("Cohort request must be valid JSON") from exc
    canonical = json.dumps(
        {"project_id": project_id, "dataset_ids": dataset_ids, "cohort": cohort},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), dataset_ids, cohort


def project_lock_name(project_id: str) -> str:
    """Generate the project-specific MySQL advisory lock name."""
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise CopyValidationError("Invalid project ID for advisory lock")

    lock_name = f"copy_{project_id}"

    if len(lock_name) > 64:
        raise CopyValidationError("Advisory lock name exceeds MySQL limit")

    return lock_name


def acquire_project_lock(
    connection: Any,
    project_id: str,
    timeout_seconds: int = 10,
) -> bool:
    """Acquire a project-specific MySQL advisory lock."""
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 0 <= timeout_seconds <= 60
    ):
        raise CopyValidationError("Invalid advisory lock timeout")

    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT GET_LOCK(%s, %s)",
            (project_lock_name(project_id), timeout_seconds),
        )
        row = cursor.fetchone()
        return bool(row and row[0] == 1)

    finally:
        cursor.close()


def release_project_lock(connection: Any, project_id: str) -> bool:
    """Release a project lock on the same MySQL connection that acquired it."""
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT RELEASE_LOCK(%s)", (project_lock_name(project_id),))
        row = cursor.fetchone()
        return bool(row and row[0] == 1)
    finally:
        cursor.close()


def claim_copy_job(connection: Any, project_id: str, request_hash: str,
                   dataset_ids: list[str], cohort: dict[str, Any]) -> str:
    """Claim an idempotent job after acquiring the project lock.

    Returns 'claimed', 'already_completed', or 'already_running'. Failed jobs can
    be retried by resetting their status to running and incrementing attempt_count.
    Requires the reviewed control_copy_jobs migration to have been applied.
    """
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT status FROM control_copy_jobs WHERE project_id = %s AND request_hash = %s FOR UPDATE",
            (project_id, request_hash),
        )
        existing = cursor.fetchone()
        if existing:
            status = existing[0]
            if status == "completed":
                return "already_completed"
            if status == "running":
                return "already_running"
            if status != "failed":
                raise CopyValidationError("Unknown copy-job status; request blocked")
            cursor.execute(
                "UPDATE control_copy_jobs SET status='running', attempt_count=attempt_count+1, "
                "started_at=CURRENT_TIMESTAMP, completed_at=NULL, last_error=NULL "
                "WHERE project_id=%s AND request_hash=%s AND status='failed'",
                (project_id, request_hash),
            )
            return "claimed" if cursor.rowcount == 1 else "already_running"
        cursor.execute(
            "INSERT INTO control_copy_jobs "
            "(project_id, request_hash, dataset_ids, cohort_request, status) "
            "VALUES (%s, %s, %s, %s, 'running')",
            (project_id, request_hash, json.dumps(dataset_ids), json.dumps(cohort, sort_keys=True)),
        )
        return "claimed"
    finally:
        cursor.close()


def finish_copy_job(connection: Any, project_id: str, request_hash: str,
                    *, success: bool, error: str | None = None) -> None:
    """Persist a terminal job state; caller controls commit/rollback policy."""
    status = "completed" if success else "failed"
    safe_error = None if success else (str(error or "Copy failed")[:1000])
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE control_copy_jobs SET status=%s, completed_at=CASE WHEN %s='completed' "
            "THEN CURRENT_TIMESTAMP ELSE NULL END, last_error=%s "
            "WHERE project_id=%s AND request_hash=%s AND status='running'",
            (status, status, safe_error, project_id, request_hash),
        )
        if cursor.rowcount != 1:
            raise CopyValidationError("Could not update the expected running copy job")
    finally:
        cursor.close()


def write_copy_completion_log(
    project_id: str,
    cohort_id: str,
    table_counts: list[tuple[str, int, int]],
) -> None:
    """Append one structured JSON record after a successful copy."""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "repository_copy_completed",
        "status": "completed",
        "project_id": project_id,
        "cohort_id": cohort_id,
        "datasets": [
            {
                "dataset_id": dataset_id,
                "source_rows": expected,
                "destination_rows": actual,
            }
            for dataset_id, expected, actual in table_counts
        ],
        "total_rows": sum(actual for _, _, actual in table_counts),
    }

    try:
        COPY_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with COPY_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(
            f"COPY LOG WARNING: {type(exc).__name__}",
            file=sys.stderr,
        )


def quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise CopyValidationError("Unexpected SQL identifier in schema metadata")
    return f"`{identifier}`"


def qualified_table(schema: str, table: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def validate_relationships(
    patient_columns: tuple[str, ...],
    patient_rows: list[tuple[Any, ...]],
    visit_columns: tuple[str, ...],
    visit_rows: list[tuple[Any, ...]],
    diagnosis_columns: tuple[str, ...],
    diagnosis_rows: list[tuple[Any, ...]],
) -> None:
    patient_pos = {name: i for i, name in enumerate(patient_columns)}
    visit_pos = {name: i for i, name in enumerate(visit_columns)}
    diagnosis_pos = {name: i for i, name in enumerate(diagnosis_columns)}

    patient_ids = {row[patient_pos["DeID"]] for row in patient_rows}
    visit_pairs = {
        (row[visit_pos["DeID"]], row[visit_pos["VisitID"]])
        for row in visit_rows
    }

    for row in visit_rows:
        deid = row[visit_pos["DeID"]]
        if deid is not None and deid not in patient_ids:
            raise CopyValidationError("A visit references a missing patient")

    for row in diagnosis_rows:
        deid = row[diagnosis_pos["DeID"]]
        visit_id = row[diagnosis_pos["VisitID"]]
        if deid is not None and deid not in patient_ids:
            raise CopyValidationError("A diagnosis references a missing patient")
        # MySQL composite foreign keys do not require a match if any component
        # is NULL. Match that behavior, while validating complete pairs.
        if deid is not None and visit_id is not None:
            if (deid, visit_id) not in visit_pairs:
                raise CopyValidationError("A diagnosis references a missing visit")



def authorize_dynamic_request(
    project_id: str,
    dataset_ids_raw: str,
    *,
    return_allowlist: bool = False,
) -> int | dict[str, set[str]] | None:
    """Check database approvals, write an audit event, and optionally return them.

    The default integer return preserves the existing CLI contract. The API may
    request the database-derived allowlist so it can call the shared core
    validator directly without trusting dataset IDs supplied by the caller.
    """
    dataset_ids = [part.strip() for part in dataset_ids_raw.split(",")]
    env = dotenv_values(ROOT_ENV)
    user = env.get("DB_USER", "haven_loader")
    password = env.get("DB_PASSWORD")
    host = env.get("DB_HOST", "127.0.0.1")
    try:
        port = int(env.get("DB_PORT", "3308"))
    except (TypeError, ValueError):
        print("AUTHORIZATION ERROR: DB_PORT in .env must be an integer", file=sys.stderr)
        if return_allowlist:
            raise CopyValidationError("Project authorization lookup failed")
        return 2
    if not password:
        print("AUTHORIZATION ERROR: DB_PASSWORD is missing from .env", file=sys.stderr)
        if return_allowlist:
            raise CopyValidationError("Project authorization lookup failed")
        return 2
    if port != 3308:
        print("AUTHORIZATION ERROR: refusing registry connection; DB_PORT must be 3308", file=sys.stderr)
        if return_allowlist:
            raise CopyValidationError("Project authorization lookup failed")
        return 2

    connection = None
    outcome = "rejected"
    details = "Authorization check did not complete"
    approved_dataset_ids: set[str] = set()
    try:
        connection = mysql.connector.connect(
            host=host, port=port, user=user, password=password,
            database=SOURCE_SCHEMA, connection_timeout=5,
            autocommit=False, charset="utf8mb4",
        )
        cursor = connection.cursor()
        cursor.execute("SELECT @@port, DATABASE()")
        server_port, active_schema = cursor.fetchone()
        if server_port != 3308 or active_schema != SOURCE_SCHEMA:
            raise CopyValidationError("Registry connection did not reach the approved local source schema")

        cursor.execute(
            "SELECT approval_status FROM control_research_projects WHERE project_id = %s",
            (project_id,),
        )
        project_row = cursor.fetchone()
        if not project_row or project_row[0] != "approved":
            details = "Project is missing or not approved"
            print(f"AUTHORIZATION REJECTED: {details}.", file=sys.stderr)
        else:
            cursor.execute(
                "SELECT dataset_id, approval_status "
                "FROM control_project_dataset_approvals "
                "WHERE project_id = %s AND dataset_id IN (" + ",".join(["%s"] * len(dataset_ids)) + ")",
                tuple([project_id, *dataset_ids]),
            )
            approvals = {row[0]: row[1] for row in cursor.fetchall()}
            approved_dataset_ids = {
                dataset_id for dataset_id, status in approvals.items()
                if status == "approved"
            }
            not_approved = []
            for dataset_id in dataset_ids:
                copy_request = CopyRequest(
                    project_id=project_id,
                    dataset_id=dataset_id,
                )
                try:
                    validate_project_dataset(
                        copy_request.project_id,
                        copy_request.dataset_id,
                        allowlist={project_id: approved_dataset_ids},
                    )
                except CoreAuthorizationError:
                    not_approved.append(dataset_id)
            if not_approved:
                details = "Dataset approval missing or not approved: " + ", ".join(not_approved)
                print(f"AUTHORIZATION REJECTED: {details}.", file=sys.stderr)
            else:
                outcome = "approved"
                details = "Project and all requested dataset approvals verified; preflight only, no copy performed"
                print("AUTHORIZATION PASSED: project and requested datasets are approved.")

        cursor.execute(
            "INSERT INTO control_copy_audit "
            "(project_id, dataset_ids, event_type, outcome, details) "
            "VALUES (%s, %s, %s, %s, %s)",
            (project_id, json.dumps(dataset_ids), "authorization_check", outcome, details),
        )
        connection.commit()
        if return_allowlist:
            return {project_id: approved_dataset_ids} if outcome == "approved" else None
        return 0 if outcome == "approved" else 2
    except (mysql.connector.Error, CopyValidationError) as exc:
        if connection is not None:
            connection.rollback()
        print(f"AUTHORIZATION ERROR: {type(exc).__name__}; request blocked.", file=sys.stderr)
        if return_allowlist:
            raise CopyValidationError("Project authorization lookup failed") from exc
        return 2
    finally:
        if connection is not None:
            connection.close()


def project_schema_name(project_id: str) -> str:
    """Return a safe, deterministic schema name for a validated project ID."""
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise CopyValidationError("Invalid project ID for destination schema")
    schema = f"repo_project_{project_id}"
    if len(schema) > 64:
        raise CopyValidationError("Project ID is too long for a MySQL schema name")
    return schema


def get_schema_context(project_id: str) -> dict[str, Any]:
    """Return column names and data types for registered tables in a project schema.

    The helper reads INFORMATION_SCHEMA.COLUMNS only. It does not read clinical
    records. Table names are restricted to the validated dataset catalogue.
    """
    schema = project_schema_name(project_id)
    registered_tables = sorted(
        {spec["source_table"] for spec in DATASET_REGISTRY.values()}
    )
    if not registered_tables:
        raise CopyValidationError("No registered dataset tables are available")

    placeholders = ", ".join(["%s"] * len(registered_tables))
    connection = _open_copy_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN ({placeholders}) "
            "ORDER BY TABLE_NAME, ORDINAL_POSITION",
            (schema, *registered_tables),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()

    tables: dict[str, list[dict[str, str]]] = {}
    for table_name, column_name, data_type in rows:
        tables.setdefault(str(table_name), []).append(
            {
                "column_name": str(column_name),
                "data_type": str(data_type),
            }
        )

    if not tables:
        raise CopyValidationError(
            f"No registered dataset tables were found in project schema {schema}"
        )

    return {
        "project_id": project_id,
        "schema": schema,
        "tables": tables,
    }


def validate_copy_dataset_dependencies(dataset_ids: list[str]) -> None:
    """Validate dependencies and confirm every selected table supports cohort scoping."""
    selected = set(dataset_ids)
    if "DS_VISIT" in selected and "DS_PATIENT" not in selected:
        raise CopyValidationError("DS_VISIT requires DS_PATIENT to preserve the patient foreign key")
    if "DS_DIAGNOSIS" in selected and not {"DS_PATIENT", "DS_VISIT"}.issubset(selected):
        raise CopyValidationError("DS_DIAGNOSIS requires DS_PATIENT and DS_VISIT to preserve foreign keys")

    connection = _open_copy_connection()
    try:
        cursor = connection.cursor()
        try:
            for dataset_id in dataset_ids:
                table = DATASET_REGISTRY[dataset_id]["source_table"]
                cursor.execute(
                    "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME='DeID'",
                    (SOURCE_SCHEMA, table),
                )
                if int(cursor.fetchone()[0]) != 1:
                    raise CopyValidationError(
                        f"{dataset_id} cannot be cohort-copied: source table is missing the DeID column"
                    )
        finally:
            cursor.close()
    finally:
        connection.close()


def _open_copy_connection() -> Any:
    env = dotenv_values(ROOT_ENV)
    user = env.get("CLINICAL_COPY_DB_USER", "haven_clinical_copy")
    password = env.get("CLINICAL_COPY_DB_PASSWORD")
    host = env.get("DB_HOST", "127.0.0.1")
    try:
        port = int(env.get("DB_PORT", "3308"))
    except (TypeError, ValueError) as exc:
        raise CopyValidationError("DB_PORT in .env must be an integer") from exc
    if not password:
        raise CopyValidationError("CLINICAL_COPY_DB_PASSWORD is missing from .env")
    if port != 3308:
        raise CopyValidationError("Refusing copy connection: DB_PORT must be 3308")
    conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password,
        database=SOURCE_SCHEMA, connection_timeout=5,
        autocommit=False, charset="utf8mb4",
    )
    cur = conn.cursor()
    try:
        cur.execute("SELECT @@port, DATABASE(), CURRENT_USER()")
        server_port, active_schema, active_user = cur.fetchone()
        if server_port != 3308 or active_schema != SOURCE_SCHEMA or active_user != f"{user}@localhost":
            raise CopyValidationError("Copy connection identity check failed")
    finally:
        cur.close()
    return conn


def _open_schema_provisioner_connection() -> Any:
    """Open a separate, tightly controlled account used only for schema provisioning."""
    env = dotenv_values(ROOT_ENV)
    user = env.get("SCHEMA_PROVISIONER_DB_USER")
    password = env.get("SCHEMA_PROVISIONER_DB_PASSWORD")
    host = env.get("DB_HOST", "127.0.0.1")
    try:
        port = int(env.get("DB_PORT", "3308"))
    except (TypeError, ValueError) as exc:
        raise CopyValidationError("DB_PORT in .env must be an integer") from exc
    if not user or not password:
        raise CopyValidationError(
            "SCHEMA_PROVISIONER_DB_USER and SCHEMA_PROVISIONER_DB_PASSWORD are required; "
            "schema creation is intentionally separate from the copy account"
        )
    if not re.fullmatch(r"[A-Za-z0-9_]+", user):
        raise CopyValidationError("Invalid schema-provisioner username")
    if port != 3308:
        raise CopyValidationError("Refusing schema-provisioning connection: DB_PORT must be 3308")
    conn = mysql.connector.connect(
        host=host, port=port, user=user, password=password,
        connection_timeout=5, autocommit=True, charset="utf8mb4",
    )
    cur = conn.cursor()
    try:
        cur.execute("SELECT @@port, CURRENT_USER()")
        server_port, active_user = cur.fetchone()
        if server_port != 3308 or active_user != f"{user}@localhost":
            raise CopyValidationError("Schema-provisioner connection identity check failed")
    finally:
        cur.close()
    return conn


def provision_project_schema(project_id: str, copy_user: str) -> str:
    """Create a project schema; the copy account's namespace-scoped grants are preconfigured by an admin."""
    schema = project_schema_name(project_id)
    if not re.fullmatch(r"[A-Za-z0-9_]+", copy_user):
        raise CopyValidationError("Invalid copy-account username")
    conn = _open_schema_provisioner_connection()
    cur = conn.cursor()
    created = False
    try:
        cur.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (schema,))
        if cur.fetchone():
            raise CopyValidationError(
                f"Destination schema {schema} already exists; refusing to merge or overwrite data"
            )
        cur.execute(f"CREATE DATABASE {quote_identifier(schema)} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        created = True
        # Do not issue GRANT here. The provisioner deliberately has no GRANT OPTION.
        # An administrator preconfigures haven_clinical_copy's privileges on repo_project_*.*.
        return schema
    except Exception:
        if created:
            try:
                cur.execute(f"DROP DATABASE IF EXISTS {quote_identifier(schema)}")
            except Exception:
                pass
        raise
    finally:
        cur.close()
        conn.close()


def drop_project_schema_after_failure(schema: str) -> None:
    """Remove a schema created by this job after a failed copy; never call for pre-existing schemas."""
    conn = _open_schema_provisioner_connection()
    cur = conn.cursor()
    try:
        cur.execute(f"DROP DATABASE IF EXISTS {quote_identifier(schema)}")
    finally:
        cur.close()
        conn.close()


def _cohort_id_from_request(cohort: dict[str, Any]) -> str:
    """Dynamic copy uses a pre-approved cohort record, not requester-supplied SQL filters."""
    if set(cohort) != {"cohort_id"}:
        raise CopyValidationError(
            "Actual copying requires --cohort-json containing only a trusted cohort_id, e.g. {\"cohort_id\":\"cohort_001\"}; "
            "inline filters and limits are not executed"
        )
    cohort_id = cohort.get("cohort_id")
    if not isinstance(cohort_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", cohort_id):
        raise CopyValidationError("cohort_id must be a valid approved cohort identifier")
    return cohort_id


def _create_project_tables(connection: Any, schema: str, dataset_ids: list[str]) -> None:
    """Create selected allowlisted tables and the known core foreign keys."""
    cursor = connection.cursor()
    try:
        for dataset_id in dataset_ids:
            table = DATASET_REGISTRY[dataset_id]["source_table"]
            cursor.execute(
                f"CREATE TABLE {qualified_table(schema, table)} LIKE {qualified_table(SOURCE_SCHEMA, table)}"
            )
        selected = set(dataset_ids)
        if "DS_VISIT" in selected:
            cursor.execute(
                f"ALTER TABLE {qualified_table(schema, 'bi_visit_data')} "
                f"ADD CONSTRAINT fk_visit_patient FOREIGN KEY (DeID) "
                f"REFERENCES {qualified_table(schema, 'bi_patient_data')} (DeID)"
            )
        if "DS_DIAGNOSIS" in selected:
            cursor.execute(
                f"ALTER TABLE {qualified_table(schema, 'bi_diagnosis_data')} "
                f"ADD CONSTRAINT fk_diagnosis_patient FOREIGN KEY (DeID) "
                f"REFERENCES {qualified_table(schema, 'bi_patient_data')} (DeID)"
            )
            cursor.execute(
                f"ALTER TABLE {qualified_table(schema, 'bi_diagnosis_data')} "
                f"ADD CONSTRAINT fk_diagnosis_visit_pair FOREIGN KEY (DeID, VisitID) "
                f"REFERENCES {qualified_table(schema, 'bi_visit_data')} (DeID, VisitID)"
            )
    finally:
        cursor.close()


def _copy_cohort_table(connection: Any, schema: str, table: str, project_id: str, cohort_id: str) -> tuple[int, int]:
    """Copy cohort rows entirely inside MySQL; no clinical rows enter Python memory."""
    cursor = connection.cursor()
    try:
        source_table = qualified_table(SOURCE_SCHEMA, table)
        destination_table = qualified_table(schema, table)
        cohort_members = qualified_table(SOURCE_SCHEMA, "control_approved_cohort_members")
        cohort_predicate = (
            f"WHERE `DeID` IN (SELECT `DeID` FROM {cohort_members} "
            "WHERE `project_id`=%s AND `cohort_id`=%s)"
        )
        cursor.execute(f"SELECT COUNT(*) FROM {source_table} {cohort_predicate}", (project_id, cohort_id))
        expected = int(cursor.fetchone()[0])
        cursor.execute(
            f"INSERT INTO {destination_table} SELECT * FROM {source_table} {cohort_predicate}",
            (project_id, cohort_id),
        )
        cursor.execute(f"SELECT COUNT(*) FROM {destination_table}")
        actual = int(cursor.fetchone()[0])
        return expected, actual
    finally:
        cursor.close()


def run_dynamic_copy_job(project_id: str, dataset_ids_raw: str, cohort_raw: str) -> int:
    """Run a cohort-scoped dynamic copy with project lock, idempotency, and cleanup."""
    cohort_text = cohort_raw
    if cohort_text.startswith("@"):
        try:
            cohort_text = Path(cohort_text[1:]).read_text(encoding="utf-8")
        except OSError as exc:
            raise CopyValidationError("Could not read the --cohort-json file") from exc
    request_hash, dataset_ids, cohort = canonical_request_hash(project_id, dataset_ids_raw, cohort_text)
    cohort_id = _cohort_id_from_request(cohort)
    validate_copy_dataset_dependencies(dataset_ids)

    env = dotenv_values(ROOT_ENV)
    copy_user = env.get("CLINICAL_COPY_DB_USER", "haven_clinical_copy")
    connection = _open_copy_connection()
    lock_acquired = False
    job_claimed = False
    schema_created = False
    schema = project_schema_name(project_id)
    try:
        lock_acquired = acquire_project_lock(connection, project_id, timeout_seconds=10)
        if not lock_acquired:
            print("REQUEST BLOCKED: another job currently holds this project's lock.", file=sys.stderr)
            return 2

        claim_result = claim_copy_job(connection, project_id, request_hash, dataset_ids, cohort)
        connection.commit()
        if claim_result == "already_completed":
            print("DUPLICATE REQUEST: this identical request is already completed; no copy performed.")
            return 0
        if claim_result == "already_running":
            print("REQUEST BLOCKED: this identical request is already running.", file=sys.stderr)
            return 2
        job_claimed = True

        cursor = connection.cursor()
        try:
            cursor.execute(
                "SELECT approval_status FROM control_approved_cohorts "
                "WHERE project_id=%s AND cohort_id=%s",
                (project_id, cohort_id),
            )
            cohort_row = cursor.fetchone()
            if not cohort_row or cohort_row[0] != "approved":
                raise CopyValidationError("Cohort is missing, not approved, or not approved for this project")
            cursor.execute(
                "SELECT COUNT(*) FROM control_approved_cohort_members WHERE project_id=%s AND cohort_id=%s",
                (project_id, cohort_id),
            )
            member_count = int(cursor.fetchone()[0])
            if member_count == 0:
                raise CopyValidationError("Approved cohort contains no members; copy blocked")
        finally:
            cursor.close()

        schema = provision_project_schema(project_id, copy_user)
        schema_created = True
        _create_project_tables(connection, schema, dataset_ids)
        connection.commit()  # DDL commits implicitly; establish a clean DML transaction below.
        connection.start_transaction()

        table_counts: list[tuple[str, int, int]] = []
        copy_order = (
            "DS_PATIENT",
            "DS_VISIT",
            "DS_DIAGNOSIS",
            "DS_ENDOSCOPY_PROCEDURE",
            "DS_MEDICATION",
            "DS_NEUROLOGY_PROCEDURE",
            "DS_OPERATION_PROCEDURE",
            "DS_RADIOLOGY_PROCEDURE",
            "DS_LABORATORY_PROCEDURE",
            "DS_VITAL_SIGNS",
        )
        for dataset_id in copy_order:
            if dataset_id not in dataset_ids:
                continue
            table = DATASET_REGISTRY[dataset_id]["source_table"]
            expected, actual = _copy_cohort_table(connection, schema, table, project_id, cohort_id)
            table_counts.append((dataset_id, expected, actual))

        validation_report: ValidationReport = validate_copy_row_counts(
            {dataset_id: (expected, actual) for dataset_id, expected, actual in table_counts}
        )
        if not validation_report.passed:
            raise CopyValidationError("Dynamic dataset row-count validation failed")

        connection.commit()
        finish_copy_job(connection, project_id, request_hash, success=True)
        connection.commit()
        job_claimed = False
        write_copy_completion_log(
            project_id,
            cohort_id,
            table_counts,
        )
        print("DYNAMIC COPY COMPLETED.")
        print(f"Project: {project_id}; destination schema: {schema}; cohort: {cohort_id}")
        for dataset_id, expected, actual in table_counts:
            print(f"  {dataset_id}: source cohort rows={expected}; destination rows={actual}; validation=PASS")
        print("No clinical row values were printed.")
        return 0
    except Exception as exc:
        try:
            connection.rollback()
        except Exception:
            pass
        if schema_created:
            try:
                drop_project_schema_after_failure(schema)
                schema_created = False
            except Exception as cleanup_exc:
                print(
                    f"CLEANUP WARNING: destination schema could not be removed ({type(cleanup_exc).__name__}). "
                    "Do not retry until the schema has been inspected.",
                    file=sys.stderr,
                )
        if job_claimed:
            try:
                finish_copy_job(
                    connection, project_id, request_hash, success=False,
                    error=f"{type(exc).__name__}: {str(exc)[:900]}",
                )
                connection.commit()
                job_claimed = False
            except Exception:
                try:
                    connection.rollback()
                except Exception:
                    pass
        print(f"COPY FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        if connection is not None:
            if lock_acquired:
                try:
                    release_project_lock(connection, project_id)
                except Exception:
                    pass
            connection.close()


def _legacy_table_state(connection: Any, table: str, primary_key: tuple[str, ...]) -> tuple[int, int, bool]:
    """Compare source and destination in SQL without fetching clinical rows."""
    cursor = connection.cursor()
    try:
        source = qualified_table(SOURCE_SCHEMA, table)
        destination = qualified_table(DESTINATION_SCHEMA, table)
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
            (SOURCE_SCHEMA, table),
        )
        source_columns = [row[0] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
            (DESTINATION_SCHEMA, table),
        )
        destination_columns = [row[0] for row in cursor.fetchall()]
        if not source_columns or source_columns != destination_columns:
            raise CopyValidationError(f"Source/destination columns differ for {table}")
        if not set(primary_key).issubset(source_columns):
            raise CopyValidationError(f"Primary-key columns are missing for {table}")

        cursor.execute(f"SELECT COUNT(*) FROM {source}")
        source_count = int(cursor.fetchone()[0])
        cursor.execute(f"SELECT COUNT(*) FROM {destination}")
        destination_count = int(cursor.fetchone()[0])

        key_join = " AND ".join(
            f"s.{quote_identifier(col)}=d.{quote_identifier(col)}" for col in primary_key
        )
        all_equal = " AND ".join(
            f"s.{quote_identifier(col)} <=> d.{quote_identifier(col)}" for col in source_columns
        )
        cursor.execute(
            f"SELECT COUNT(*) FROM {source} s LEFT JOIN {destination} d ON {key_join} "
            f"WHERE " + " OR ".join(
                [f"d.{quote_identifier(primary_key[0])} IS NULL", f"NOT ({all_equal})"]
            )
        )
        mismatches = int(cursor.fetchone()[0])
        exact_match = source_count == destination_count and mismatches == 0
        return source_count, destination_count, exact_match
    finally:
        cursor.close()


def run_legacy_copy(check_only: bool = False) -> int:
    """Legacy three-table copy using SQL-side validation and INSERT...SELECT."""
    env = dotenv_values(ROOT_ENV)
    user = env.get("CLINICAL_COPY_DB_USER", "haven_clinical_copy")
    password = env.get("CLINICAL_COPY_DB_PASSWORD")
    host = env.get("DB_HOST", "127.0.0.1")
    try:
        port = int(env.get("DB_PORT", "3308"))
    except (TypeError, ValueError):
        raise CopyValidationError("DB_PORT in .env must be an integer")
    if not password or port != 3308:
        raise CopyValidationError("Clinical copy credentials are missing or DB_PORT is not 3308")

    connection = mysql.connector.connect(
        host=host, port=port, user=user, password=password,
        database=DESTINATION_SCHEMA, connection_timeout=5,
        autocommit=False, charset="utf8mb4",
    )
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT @@port, DATABASE(), CURRENT_USER()")
        server_port, active_schema, active_user = cursor.fetchone()
        cursor.close()
        if server_port != 3308 or active_schema != DESTINATION_SCHEMA or active_user != f"{user}@localhost":
            raise CopyValidationError("MySQL connection identity check failed")

        table_specs = [
            (DATASET_REGISTRY[dataset_id]["source_table"], DATASET_REGISTRY[dataset_id]["primary_key"])
            for dataset_id in LEGACY_CORE_DATASET_IDS
        ]
        states = {
            table: _legacy_table_state(connection, table, key)
            for table, key in table_specs
        }
        all_empty = all(destination_count == 0 for _, destination_count, _ in states.values())
        all_exact = all(exact for _, _, exact in states.values())
        if check_only:
            if all_empty or all_exact:
                print("Preflight validation passed; no rows changed.")
                return 0
            raise CopyValidationError("Destination is partially populated or differs from source")

        if all_exact:
            print("Destination already matches the source exactly; no rows changed.")
            return 0
        if not all_empty:
            raise CopyValidationError("Destination is partially populated or differs from source; no changes made")

        cursor = connection.cursor()
        try:
            for table, _ in table_specs:
                source = qualified_table(SOURCE_SCHEMA, table)
                destination = qualified_table(DESTINATION_SCHEMA, table)
                cursor.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
                    (SOURCE_SCHEMA, table),
                )
                columns = [row[0] for row in cursor.fetchall()]
                column_sql = ", ".join(quote_identifier(col) for col in columns)
                cursor.execute(
                    f"INSERT INTO {destination} ({column_sql}) SELECT {column_sql} FROM {source}"
                )
        finally:
            cursor.close()

        for table, key in table_specs:
            source_count, destination_count, exact = _legacy_table_state(connection, table, key)
            if source_count != destination_count or not exact:
                raise CopyValidationError(f"Post-copy validation failed for {table}")
        connection.commit()
        print("Clinical data copy committed and validated.")
        return 0
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


class CopyAPIHandler(BaseHTTPRequestHandler):
    """Local HTTP interface for the frontend copy request."""
    server_version = "ClinicalRepositoryCopy/1.0"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        allowed_origin = dotenv_values(ROOT_ENV).get("COPY_API_ALLOWED_ORIGIN")
        origin = self.headers.get("Origin")
        if allowed_origin and origin == allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        allowed_origin = dotenv_values(ROOT_ENV).get("COPY_API_ALLOWED_ORIGIN")
        origin = self.headers.get("Origin")
        if allowed_origin and origin == allowed_origin:
            self.send_header("Access-Control-Allow-Origin", allowed_origin)
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/api/copy":
            self._send_json(404, {"status": "error", "message": "Route not found"})
            return
        token = dotenv_values(ROOT_ENV).get("COPY_API_TOKEN")
        supplied = self.headers.get("Authorization", "")
        if not token or not hmac.compare_digest(supplied, f"Bearer {token}"):
            self._send_json(401, {"status": "error", "message": "Unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65536:
                raise CopyValidationError("Request body must be between 1 and 65536 bytes")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise CopyValidationError("Request body must be a JSON object")
            project_id = payload.get("project_id")
            dataset_ids = payload.get("dataset_ids")
            cohort = payload.get("cohort")
            if not isinstance(project_id, str) or not isinstance(dataset_ids, list) or not dataset_ids:
                raise CopyValidationError("project_id and a non-empty dataset_ids array are required")
            if any(not isinstance(item, str) for item in dataset_ids) or not isinstance(cohort, dict):
                raise CopyValidationError("dataset_ids must contain strings and cohort must be an object")
            dataset_ids_raw = ",".join(dataset_ids)
            cohort_raw = json.dumps(cohort)
            validate_dynamic_request(project_id, dataset_ids_raw, cohort_raw)
            if authorize_dynamic_request(project_id, dataset_ids_raw) != 0:
                self._send_json(403, {"status": "rejected", "message": "Project or dataset authorization failed"})
                return
            result = run_dynamic_copy_job(project_id, dataset_ids_raw, cohort_raw)
            if result == 0:
                self._send_json(200, {"status": "completed", "project_id": project_id})
            else:
                self._send_json(409, {"status": "failed", "message": "Copy job did not complete"})
        except (CopyValidationError, json.JSONDecodeError, ValueError) as exc:
            self._send_json(400, {"status": "error", "message": str(exc)})
        except Exception as exc:
            self._send_json(500, {"status": "error", "message": f"Copy request failed ({type(exc).__name__})"})

    def log_message(self, format: str, *args: Any) -> None:
        print("COPY API: " + (format % args))


def run_api_server() -> int:
    """Retired stdlib API entry point; use the FastAPI app in scripts/api.py."""
    raise CopyValidationError(
        "The legacy HTTP API is disabled. Start the FastAPI service with: "
        "uvicorn scripts.api:app --host 127.0.0.1 --port 8090"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Clinical repository copy service")
    parser.add_argument("--project-id")
    parser.add_argument("--dataset-ids")
    parser.add_argument("--cohort-json", help='JSON object or @path; actual copy requires {"cohort_id":"..."}')
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--api", action="store_true", help="Start the local HTTP API for frontend requests")
    args = parser.parse_args()

    try:
        if args.api:
            return run_api_server()
        if args.project_id or args.dataset_ids or args.cohort_json:
            if not all((args.project_id, args.dataset_ids, args.cohort_json)):
                raise CopyValidationError("--project-id, --dataset-ids and --cohort-json are all required")
            validate_dynamic_request(args.project_id, args.dataset_ids, args.cohort_json)
            if authorize_dynamic_request(args.project_id, args.dataset_ids) != 0:
                return 2
            return run_dynamic_copy_job(args.project_id, args.dataset_ids, args.cohort_json)
        return run_legacy_copy(check_only=args.check_only)
    except CopyValidationError as exc:
        print(f"VALIDATION ERROR: {exc}", file=sys.stderr)
        return 2
    except mysql.connector.Error as exc:
        print(f"MYSQL ERROR: {type(exc).__name__}; operation blocked.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
