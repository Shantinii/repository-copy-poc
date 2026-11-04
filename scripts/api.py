"""FastAPI entry point for the clinical repository-copy service.

Run from the repository root with:
    uvicorn scripts.api:app --host 127.0.0.1 --port 8090

Payment verification is deliberately fail-closed until a trusted payment
provider/backend verifier is connected in get_verified_payment_status().
"""
from __future__ import annotations

import hmac
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Allow imports to work both with `uvicorn scripts.api:app` from the repo root
# and with `uvicorn api:app` from the scripts directory.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import clinical_repository_copy as clinical_copy  # noqa: E402

ROOT_ENV = PROJECT_ROOT / ".env"
PROJECT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,49}$")
DATASET_ID_PATTERN = re.compile(r"^DS_[A-Z0-9_]+$")
COHORT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

app = FastAPI(title="Data Safe Haven Repository Copy API", version="1.0.0")


class CopyRepositoryRequest(BaseModel):
    """Request a copy of selected datasets for an approved project.

    `approved_datasets` contains dataset IDs requested by the caller. It is
    not proof of approval; the API checks each ID against MySQL control records.
    `cohort_id` is required by the existing clinical copy engine.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, max_length=50)
    payment_id: str = Field(min_length=1, max_length=200)
    approved_datasets: list[str] = Field(min_length=1)
    cohort_id: str = Field(min_length=1, max_length=128)

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, value: str) -> str:
        if not PROJECT_ID_PATTERN.fullmatch(value):
            raise ValueError("project_id has an invalid format")
        return value

    @field_validator("approved_datasets")
    @classmethod
    def validate_dataset_ids(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("approved_datasets must contain at least one dataset ID")
        if any(not isinstance(item, str) or not DATASET_ID_PATTERN.fullmatch(item) for item in value):
            raise ValueError("approved_datasets contains an invalid dataset ID")
        if len(value) != len(set(value)):
            raise ValueError("Duplicate dataset IDs are not allowed")
        return value

    @field_validator("cohort_id")
    @classmethod
    def validate_cohort_id(cls, value: str) -> str:
        if not COHORT_ID_PATTERN.fullmatch(value):
            raise ValueError("cohort_id has an invalid format")
        return value


class PaymentVerificationUnavailable(RuntimeError):
    """Raised when no trusted payment verifier has been integrated."""


def get_verified_payment_status(
    payment_id: str,
    project_id: str,
    dataset_ids: list[str],
) -> str:
    """Return payment status from a trusted provider/backend integration.

    Replace this function body with the payment provider's authenticated
    server-to-server lookup. It must verify that payment_id belongs to this
    project and covers the requested datasets, then return the provider's
    authoritative status (for example, "succeeded"). Never read payment
    status from the request body or trust a browser-supplied success flag.
    """
    raise PaymentVerificationUnavailable(
        "Trusted payment verification is not configured; copy request blocked"
    )


def require_service_token(authorization: str | None) -> None:
    token = dotenv_values(ROOT_ENV).get("COPY_API_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="Copy API token is not configured")
    expected = f"Bearer {token}"
    supplied = authorization or ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/api/repository/copy")
def copy_repository(
    request: CopyRepositoryRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """Validate payment and database approvals before starting the copy job."""
    require_service_token(authorization)

    dataset_ids_raw = ",".join(request.approved_datasets)
    cohort_raw = json.dumps({"cohort_id": request.cohort_id}, separators=(",", ":"))

    # Syntax/catalogue/cohort preflight performs no database connection.
    try:
        clinical_copy.validate_dynamic_request(
            request.project_id,
            dataset_ids_raw,
            cohort_raw,
        )
    except clinical_copy.CopyValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Payment is checked against a trusted server-side source before MySQL access.
    try:
        payment_status = get_verified_payment_status(
            request.payment_id,
            request.project_id,
            request.approved_datasets,
        )
    except PaymentVerificationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Payment verification service failed") from exc

    # The core helper accepts one dataset per CopyRequest. One verified payment
    # event is checked once for the dataset bundle.
    from repository_copy_core import (  # imported in the endpoint as requested
        CopyRequest as CoreCopyRequest,
        PaymentValidationError,
        validate_payment_event,
        validate_project_dataset,
    )

    payment_request = CoreCopyRequest(
        project_id=request.project_id,
        dataset_id=request.approved_datasets[0],
        payment_id=request.payment_id,
        payment_status=payment_status,
    )
    try:
        validate_payment_event(payment_request)
    except PaymentValidationError as exc:
        raise HTTPException(status_code=402, detail="Payment is not verified as successful") from exc

    # This function reads the approved project/dataset rows and writes the
    # existing authorization audit event. return_allowlist=True is the small
    # compatibility update required in clinical_repository_copy.py below.
    try:
        allowlist = clinical_copy.authorize_dynamic_request(
            request.project_id,
            dataset_ids_raw,
            return_allowlist=True,
        )
    except clinical_copy.CopyValidationError as exc:
        raise HTTPException(status_code=503, detail="Project authorization lookup failed") from exc

    if not isinstance(allowlist, dict):
        raise HTTPException(status_code=403, detail="Project or dataset authorization failed")

    try:
        for dataset_id in request.approved_datasets:
            validate_project_dataset(
                request.project_id,
                dataset_id,
                allowlist=allowlist,
            )
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Project or dataset authorization failed") from exc

    # Existing engine performs cohort approval, locking, idempotency, SQL copy,
    # row-count validation, and failure cleanup.
    result = clinical_copy.run_dynamic_copy_job(
        request.project_id,
        dataset_ids_raw,
        cohort_raw,
    )
    if result != 0:
        raise HTTPException(status_code=409, detail="Copy job did not complete")

    env = dotenv_values(ROOT_ENV)
    database_host = env.get("DB_HOST", "127.0.0.1")
    try:
        database_port = int(env.get("DB_PORT", "3308"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Database port configuration is invalid") from exc
    if not database_host or database_port != 3308:
        raise HTTPException(status_code=503, detail="Database connection details are not configured for the local POC")

    available_tables = [
        clinical_copy.DATASET_REGISTRY[dataset_id]["source_table"]
        for dataset_id in request.approved_datasets
    ]

    return {
        "status": "SUCCESS",
        "project_id": request.project_id,
        "target_schema": clinical_copy.project_schema_name(request.project_id),
        "database_host": database_host,
        "database_port": database_port,
        "available_tables": available_tables,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
