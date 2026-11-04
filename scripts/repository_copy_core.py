"""Shared validation core for the Data Safe Haven repository-copy workflow.

This module contains reusable request, authorization, payment, and data-validation
helpers. It does not connect to MySQL, verify payments with a payment provider,
copy records, or grant database access. Callers must supply authorization data
retrieved from trusted server-side records.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


PATIENT_TABLE = "bi_patient_data"
VISIT_TABLE = "bi_visit_data"
DIAGNOSIS_TABLE = "bi_diagnosis_data"

REQUIRED_COLUMNS = {
    PATIENT_TABLE: {"DeID"},
    VISIT_TABLE: {"DeID", "VisitID"},
    DIAGNOSIS_TABLE: {"DeID", "VisitID", "diagnosisid"},
}

# Retained only for the original standalone unit tests. The clinical copy
# workflow must pass its database-derived approval mapping explicitly.
APPROVED_PROJECT_DATASETS = {
    "project_demo_001": {"dataset_demo_001"},
}

EXPECTED_TABLES = (PATIENT_TABLE, VISIT_TABLE, DIAGNOSIS_TABLE)


class RepositoryCopyError(Exception):
    """Base exception for repository-copy validation errors."""


class AuthorizationError(RepositoryCopyError):
    """Raised when a project/dataset pair is not allowlisted."""


class PaymentValidationError(RepositoryCopyError):
    """Raised when a payment event is not in an accepted state."""


class DatasetValidationError(RepositoryCopyError):
    """Raised when dataset tables, relationships, or row counts fail validation."""


class DestinationState(str, Enum):
    EMPTY = "empty"
    EXACT_MATCH = "exact_match"


@dataclass(frozen=True)
class CopyRequest:
    """One dataset within a project copy request.

    Payment fields are optional because the current clinical copy API has no
    confirmed trusted payment-event table. They must be populated from a
    trusted server-side payment verification process before validate_payment_event
    or validate_request is called.
    """

    project_id: str
    dataset_id: str
    payment_id: str | None = None
    payment_status: str | None = None


@dataclass(frozen=True)
class ValidationReport:
    """Counts-only validation result for legacy relationships and dynamic copies."""

    patient_rows: int = 0
    visit_rows: int = 0
    diagnosis_rows: int = 0
    visit_patient_orphans: int = 0
    diagnosis_patient_orphans: int = 0
    diagnosis_visit_pair_orphans: int = 0
    dataset_row_counts: tuple[tuple[str, int, int], ...] = ()

    @property
    def passed(self) -> bool:
        relationships_valid = (
            self.visit_patient_orphans == 0
            and self.diagnosis_patient_orphans == 0
            and self.diagnosis_visit_pair_orphans == 0
        )
        row_counts_valid = all(
            source_rows == destination_rows
            for _, source_rows, destination_rows in self.dataset_row_counts
        )
        return relationships_valid and row_counts_valid


def validate_destination_state(
    source_tables: Mapping[str, Sequence[tuple[Any, ...]]],
    destination_tables: Mapping[str, Sequence[tuple[Any, ...]]],
) -> DestinationState:
    """Allow an empty destination or an exact match; reject every other state."""
    expected = set(EXPECTED_TABLES)
    if set(source_tables) != expected or set(destination_tables) != expected:
        raise DatasetValidationError(
            "Source and destination must contain exactly the approved tables."
        )

    source_rows = {name: list(source_tables[name]) for name in EXPECTED_TABLES}
    destination_rows = {name: list(destination_tables[name]) for name in EXPECTED_TABLES}

    if all(not rows for rows in destination_rows.values()):
        return DestinationState.EMPTY
    if all(destination_rows[name] == source_rows[name] for name in EXPECTED_TABLES):
        return DestinationState.EXACT_MATCH
    raise DatasetValidationError(
        "Destination is partially populated or differs from source; no changes made."
    )


def validate_project_dataset(
    project_id: str,
    dataset_id: str,
    allowlist: Mapping[str, set[str]] = APPROVED_PROJECT_DATASETS,
) -> None:
    """Reject project/dataset pairs not present in the supplied approval mapping."""
    if not isinstance(project_id, str) or not project_id:
        raise AuthorizationError("Project ID is required.")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise AuthorizationError("Dataset ID is required.")
    if dataset_id not in allowlist.get(project_id, set()):
        raise AuthorizationError("The requested project/dataset pair is not approved.")


def validate_payment_event(request: CopyRequest) -> None:
    """Validate payment fields obtained from a trusted server-side source."""
    if not request.payment_id:
        raise PaymentValidationError("Payment ID is required.")
    if (
        not isinstance(request.payment_status, str)
        or request.payment_status.strip().lower() != "succeeded"
    ):
        raise PaymentValidationError("Payment is not confirmed as successful.")


def validate_request(
    request: CopyRequest,
    allowlist: Mapping[str, set[str]] = APPROVED_PROJECT_DATASETS,
) -> None:
    """Validate project/dataset approval and a trusted successful payment event."""
    validate_project_dataset(request.project_id, request.dataset_id, allowlist=allowlist)
    validate_payment_event(request)


def validate_table_columns(tables: Mapping[str, Any]) -> None:
    """Check required columns in pandas-like tables without printing row values."""
    for table_name, required in REQUIRED_COLUMNS.items():
        if table_name not in tables:
            raise DatasetValidationError(f"Required table is missing: {table_name}")
        missing = required - set(tables[table_name].columns)
        if missing:
            raise DatasetValidationError(
                f"{table_name} is missing required columns: "
                + ", ".join(sorted(missing))
            )


def _non_null_set(values: Any) -> set[Any]:
    return set(values.dropna().tolist())


def validate_dataset_relationships(tables: Mapping[str, Any]) -> ValidationReport:
    """Validate candidate keys and relationships for the original three-table sample."""
    validate_table_columns(tables)
    patients = tables[PATIENT_TABLE]
    visits = tables[VISIT_TABLE]
    diagnoses = tables[DIAGNOSIS_TABLE]

    key_specs = (
        (patients, "DeID", "patient DeID"),
        (visits, "VisitID", "visit VisitID"),
        (diagnoses, "diagnosisid", "diagnosis diagnosisid"),
    )
    for frame, column, label in key_specs:
        values = frame[column]
        if values.isna().any():
            raise DatasetValidationError(f"{label} contains null values.")
        if values.duplicated().any():
            raise DatasetValidationError(f"{label} contains duplicates.")

    patient_ids = _non_null_set(patients["DeID"])
    visit_patient_orphans = int((~visits["DeID"].isin(patient_ids)).sum())
    diagnosis_patient_orphans = int((~diagnoses["DeID"].isin(patient_ids)).sum())

    visit_pairs = set(
        visits[["DeID", "VisitID"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    diagnosis_pairs = diagnoses[["DeID", "VisitID"]].drop_duplicates().itertuples(
        index=False, name=None
    )
    diagnosis_visit_pair_orphans = sum(
        1 for pair in diagnosis_pairs if pair not in visit_pairs
    )

    report = ValidationReport(
        patient_rows=len(patients),
        visit_rows=len(visits),
        diagnosis_rows=len(diagnoses),
        visit_patient_orphans=visit_patient_orphans,
        diagnosis_patient_orphans=diagnosis_patient_orphans,
        diagnosis_visit_pair_orphans=diagnosis_visit_pair_orphans,
    )
    if not report.passed:
        raise DatasetValidationError(
            "Dataset relationship validation failed. "
            f"visit_patient_orphans={report.visit_patient_orphans}, "
            f"diagnosis_patient_orphans={report.diagnosis_patient_orphans}, "
            f"diagnosis_visit_pair_orphans={report.diagnosis_visit_pair_orphans}"
        )
    return report


def validate_copy_row_counts(
    dataset_rows: Mapping[str, tuple[int, int]],
) -> ValidationReport:
    """Build a counts-only report for the dynamically selected dataset tables."""
    if not dataset_rows:
        raise DatasetValidationError("No dataset row counts were supplied for validation.")

    report_rows: list[tuple[str, int, int]] = []
    for dataset_id, counts in sorted(dataset_rows.items()):
        if not isinstance(dataset_id, str) or not dataset_id:
            raise DatasetValidationError("Dataset ID is invalid in the row-count report.")
        if not isinstance(counts, tuple) or len(counts) != 2:
            raise DatasetValidationError(f"Invalid row counts supplied for {dataset_id}.")
        source_rows, destination_rows = counts
        for value in counts:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DatasetValidationError(f"Invalid row count supplied for {dataset_id}.")
        report_rows.append((dataset_id, source_rows, destination_rows))

    return ValidationReport(dataset_row_counts=tuple(report_rows))


def preflight_copy_request(
    request: CopyRequest,
    tables: Mapping[str, Any],
    allowlist: Mapping[str, set[str]] = APPROVED_PROJECT_DATASETS,
) -> ValidationReport:
    """Run request and three-table relationship checks before a copy."""
    validate_request(request, allowlist=allowlist)
    return validate_dataset_relationships(tables)
