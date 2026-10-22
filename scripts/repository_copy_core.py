"""
Data Safe Haven: repository-copy core (initial integration module).

Purpose
-------
Provide reusable validation functions for the first three-table dataset:
  * bi_patient data
  * bi_visit data
  * bi_diagnosis data

This module does NOT:
  * connect to MySQL;
  * verify a real payment with a payment provider;
  * authenticate users or establish researcher permissions;
  * copy records or grant database access;
  * claim production readiness.

Integrate these functions into the existing repository-copy workflow only after
the project team confirms the trusted payment-event contract, database schemas,
and access-control design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


# Candidate source table names from the approved sample workbook.
# Confirm/normalise names when creating the MySQL schema.
PATIENT_TABLE = "bi_patient_data"
VISIT_TABLE = "bi_visit_data"
DIAGNOSIS_TABLE = "bi_diagnosis_data"

REQUIRED_COLUMNS = {
    PATIENT_TABLE: {"DeID"},
    VISIT_TABLE: {"DeID", "VisitID"},
    DIAGNOSIS_TABLE: {"DeID", "VisitID", "diagnosisid"},
}

# Explicit allowlist for the initial POC. Replace these demo values with
# centrally managed configuration before integration; never accept arbitrary
# schema/table names from a frontend request.
APPROVED_PROJECT_DATASETS = {
    "project_demo_001": {"dataset_demo_001"},
}

EXPECTED_TABLES = (
    PATIENT_TABLE,
    VISIT_TABLE,
    DIAGNOSIS_TABLE,
)


from enum import Enum


class DestinationState(str, Enum):
    EMPTY = "empty"
    EXACT_MATCH = "exact_match"


def validate_destination_state(
    source_tables: Mapping[str, Sequence[tuple[Any, ...]]],
    destination_tables: Mapping[str, Sequence[tuple[Any, ...]]],
) -> DestinationState:
    """
    Allow an empty destination or an exact match.
    Reject partial, missing, extra, or conflicting destination data.
    """
    expected = set(EXPECTED_TABLES)

    if set(source_tables) != expected or set(destination_tables) != expected:
        raise DatasetValidationError(
            "Source and destination must contain exactly the approved tables."
        )

    source_rows = {
        name: list(source_tables[name]) for name in EXPECTED_TABLES
    }
    destination_rows = {
        name: list(destination_tables[name]) for name in EXPECTED_TABLES
    }

    if all(not rows for rows in destination_rows.values()):
        return DestinationState.EMPTY

    if all(
        destination_rows[name] == source_rows[name]
        for name in EXPECTED_TABLES
    ):
        return DestinationState.EXACT_MATCH

    raise DatasetValidationError(
        "Destination is partially populated or differs from source; no changes made."
    )


class RepositoryCopyError(Exception):
    """Base exception for repository-copy validation errors."""


class AuthorizationError(RepositoryCopyError):
    """Raised when a project/dataset pair is not allowlisted."""


class PaymentValidationError(RepositoryCopyError):
    """Raised when a payment event is not in an accepted state."""


class DatasetValidationError(RepositoryCopyError):
    """Raised when dataset tables or relationships fail validation."""


@dataclass(frozen=True)
class CopyRequest:
    """Minimal request model; payment status must come from a trusted backend."""

    project_id: str
    dataset_id: str
    payment_id: str
    payment_status: str


@dataclass(frozen=True)
class ValidationReport:
    """Counts-only result, suitable for logs or test output."""

    patient_rows: int
    visit_rows: int
    diagnosis_rows: int
    visit_patient_orphans: int
    diagnosis_patient_orphans: int
    diagnosis_visit_pair_orphans: int

    @property
    def passed(self) -> bool:
        return (
            self.visit_patient_orphans == 0
            and self.diagnosis_patient_orphans == 0
            and self.diagnosis_visit_pair_orphans == 0
        )


def validate_project_dataset(
    project_id: str,
    dataset_id: str,
    allowlist: Mapping[str, set[str]] = APPROVED_PROJECT_DATASETS,
) -> None:
    """Reject project/dataset pairs not explicitly approved."""
    if not project_id or not dataset_id:
        raise AuthorizationError("Project ID and dataset ID are required.")

    if dataset_id not in allowlist.get(project_id, set()):
        raise AuthorizationError(
            "The requested project/dataset pair is not approved."
        )


def validate_payment_event(request: CopyRequest) -> None:
    """
    Validate the shape and status of a payment event.

    IMPORTANT: this checks a value only. The caller must obtain payment status
    from a trusted server-side payment verification process, not from the UI.
    """
    if not request.payment_id:
        raise PaymentValidationError("Payment ID is required.")

    if request.payment_status.strip().lower() != "succeeded":
        raise PaymentValidationError("Payment is not confirmed as successful.")


def validate_request(
    request: CopyRequest,
    allowlist: Mapping[str, set[str]] = APPROVED_PROJECT_DATASETS,
) -> None:
    """Run the basic request checks before any copy is attempted."""
    validate_project_dataset(
        request.project_id,
        request.dataset_id,
        allowlist=allowlist,
    )
    validate_payment_event(request)


def validate_table_columns(
    tables: Mapping[str, Any],
) -> None:
    """
    Check required columns in table-like objects.

    Each value in `tables` must expose a `.columns` attribute, such as a
    pandas DataFrame. This function does not print row values.
    """
    for table_name, required in REQUIRED_COLUMNS.items():
        if table_name not in tables:
            raise DatasetValidationError(
                f"Required table is missing: {table_name}"
            )

        actual = set(tables[table_name].columns)
        missing = required - actual
        if missing:
            raise DatasetValidationError(
                f"{table_name} is missing required columns: "
                + ", ".join(sorted(missing))
            )


def _non_null_set(values: Any) -> set[Any]:
    """Return non-null values from a pandas-like Series without requiring pandas."""
    return set(values.dropna().tolist())


def validate_dataset_relationships(
    tables: Mapping[str, Any],
) -> ValidationReport:
    """
    Validate candidate primary keys and relationships for the initial cohort.

    Expects pandas-like DataFrames with the normalised table names above.
    Prints/returns counts only; it does not emit individual clinical values.
    """
    validate_table_columns(tables)

    patients = tables[PATIENT_TABLE]
    visits = tables[VISIT_TABLE]
    diagnoses = tables[DIAGNOSIS_TABLE]

    # Candidate primary keys must be non-null and unique.
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
    visit_ids = _non_null_set(visits["VisitID"])

    visit_patient_orphans = int((~visits["DeID"].isin(patient_ids)).sum())
    diagnosis_patient_orphans = int(
        (~diagnoses["DeID"].isin(patient_ids)).sum()
    )

    visit_pairs = set(
        visits[["DeID", "VisitID"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    )
    diagnosis_pairs: Sequence[tuple[Any, Any]] = (
        diagnoses[["DeID", "VisitID"]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
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
            f"diagnosis_visit_pair_orphans="
            f"{report.diagnosis_visit_pair_orphans}"
        )

    return report



def preflight_copy_request(
    request: CopyRequest,
    tables: Mapping[str, Any],
    allowlist: Mapping[str, set[str]] = APPROVED_PROJECT_DATASETS,
) -> ValidationReport:
    """
    Run request and dataset preflight checks before a database copy.

    The caller should only proceed when the returned report has `passed=True`.
    This function does not perform a copy or grant access.
    """
    validate_request(request, allowlist=allowlist)
    report = validate_dataset_relationships(tables)

    if not report.passed:
        raise DatasetValidationError(
            "Dataset relationship validation failed. "
            f"visit_patient_orphans={report.visit_patient_orphans}, "
            f"diagnosis_patient_orphans={report.diagnosis_patient_orphans}, "
            f"diagnosis_visit_pair_orphans={report.diagnosis_visit_pair_orphans}"
        )

    return report
