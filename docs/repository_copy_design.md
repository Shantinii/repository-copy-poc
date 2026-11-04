# Data Safe Haven: Repository Copy Design

**Status:** Local POC. Trusted payment integration and live API-to-MySQL validation remain pending.

**Purpose:** Copy approved cohort data into project-specific MySQL schemas with project, dataset, and cohort validation.

## 1. Workflow

1. Researcher selects datasets in I Explore.
2. Backend submits the copy request after payment.
3. API validates the request and dataset IDs.
4. Trusted payment verification confirms the project and requested datasets.
5. API checks project, dataset, and cohort approvals in MySQL.
6. Copy engine creates the project schema and copies approved cohort records using `INSERT ... SELECT`.
7. Row counts and copy status are validated before returning the result.

Payment verification and data-access approval are separate checks. Browser-supplied payment status is never trusted.

## 2. Storage Design

The POC uses **Option A: Separate MySQL schema per project**.

Schema convention: `repo_project_{project_id}`.

Isolation depends on database permissions and server controls. Institutional IT and security approval is required.

## 3. Clinical Repository Implementation

**Database configuration**
- Source schema: `haven_poc_source`
- Destination: `repo_project_{project_id}`
- Port: `3308`

**Main files**
- `scripts/api.py` — FastAPI copy endpoint.
- `scripts/clinical_repository_copy.py` — approval checks, cohort copying, locking, and row-count validation.
- `scripts/repository_copy_core.py` — shared validation helpers.
- `docs/dataset_catalog.json` — mapping of 10 dataset IDs to source tables.

**Registered datasets**

`DS_PATIENT`, `DS_VISIT`, `DS_DIAGNOSIS`, `DS_ENDOSCOPY_PROCEDURE`, `DS_MEDICATION`, `DS_NEUROLOGY_PROCEDURE`, `DS_OPERATION_PROCEDURE`, `DS_RADIOLOGY_PROCEDURE`, `DS_LABORATORY_PROCEDURE`, `DS_VITAL_SIGNS`.

The first three map to `bi_*_data` tables. The remaining seven map to `stg_ds_*` tables.

**API request**

```json
{
  "project_id": "proj_101",
  "payment_id": "pay_99823",
  "approved_datasets": [
    "DS_PATIENT",
    "DS_VISIT",
    "DS_DIAGNOSIS"
  ],
  "cohort_id": "cohort_001"
}
```

The API independently checks dataset and cohort approvals. Callers cannot supply destination schemas, source tables, SQL, or payment status.

## 4. Implemented Controls

- Bearer-token API authentication.
- Request and dataset-catalogue validation.
- MySQL project and dataset approval checks.
- Approved-cohort validation.
- Project advisory locking and copy-job idempotency.
- Server-side cohort copying.
- Source and destination row-count checks.
- Copy-failure cleanup and JSON audit logging.

## 5. Test Evidence

The four API and registry test modules returned **41 passed** on 4 November 2026.

Tests use mocked database and payment operations where applicable. They do not establish live MySQL API integration or payment-provider verification.

An earlier local copy test verified 840 expected rows and 840 copied rows. This predates the latest changes and does not validate the current assembled snapshot.

The synthetic-data POC is a separate execution path. Its simulated payment and database tests do not establish payment integration for the clinical API.

## 6. Outstanding Work

1. Connect a trusted server-to-server payment verifier. The API currently fails closed with HTTP 503.
2. Test the updated API against a disposable MySQL project.
3. Confirm cohort-key and relationship semantics for all 10 datasets, especially the seven staging tables.
4. Verify restricted database permissions and failure-cleanup access.
5. Configure internal API deployment and backend connectivity.
6. Establish a separate read-only, project-scoped database boundary for LLM access.
7. Obtain institutional IT, security, and data-governance approval before using real clinical data.

## 7. Current Scope

The API endpoint, request validation, shared validation logic, dataset registry, and automated tests are implemented.

Trusted payment verification, live API-to-MySQL validation, full dataset cohort-key approval, publication controls, and LLM read-only access remain outstanding.

**This is a local POC, not a production-ready or institutionally approved system for real clinical data.**