# Repository-Copy POC: Handover Status

## 1. Implemented

| Component | File |
|---|---|
| FastAPI copy endpoint and validation | `scripts/api.py` |
| Local mock-payment mode, controlled by `ALLOW_MOCK_PAYMENT` | `scripts/api.py` |
| Shared validation logic | `scripts/repository_copy_core.py` |
| Dynamic 10-dataset registry | `docs/dataset_catalog.json` |
| Cohort-scoped SQL copy | `scripts/clinical_repository_copy.py` |
| Copy locking and idempotency | `scripts/clinical_repository_copy.py` |
| JSON completion logging | `scripts/clinical_repository_copy.py` |
| API success manifest | `scripts/api.py` |
| Configurable MySQL port validation (1–65535; default 3308) | `scripts/api.py`, `scripts/clinical_repository_copy.py` |
| Schema metadata helper | `scripts/clinical_repository_copy.py` |

## 2. Test Results

The previous four-file test run returned **41 passed** before the configurable-port changes.

Isolated validation of the current replacement files returned:

- `scripts/test_api_fastapi.py`: **13 passed**.
- `scripts/test_database_port_config.py`: **17 passed**.

These automated tests use mocked API/database operations where applicable. The five-file suite returned 69 passed on 4 November 2026. Separately, the live local MySQL copy test for proj_102 returned HTTP 200 and all ten destination row counts matched the cohort-filtered source counts (see Section 7). Real payment verification remains pending.

## 3. Payment and Integration Status

1. Local POC testing can use simulated payment status by setting `ALLOW_MOCK_PAYMENT=true` in the local `.env` file.
2. With the flag false or unset, the API returns HTTP 503 when no trusted payment verifier is configured.
3. Trusted server-to-server payment verification remains pending. Mock payment does not verify a real transaction, payment ownership, or dataset coverage.
4. Local simulated test approvals were created for proj_101 (three datasets) and proj_102 (ten datasets). These are not institutional approvals and must not be used with real clinical data.
5. Configure a network-accessible deployment address. The current server binds to `127.0.0.1:8090`.
6. Create a dedicated read-only, project-scoped database account for LLM access.
7. Confirm cohort-key relationships across all datasets.
8. Verify MySQL permissions and failure handling.
9. See Section 7 for the local ten-dataset copy test results.
10. Obtain institutional IT, security, and data-governance approval before using real clinical data.

## 4. Retained Supporting Files

Existing sample-loading, database-safety, and regression-test files remain in the repository. The five diagnostic scripts from the earlier cleanup request were removed from the updated `main` branch.

## 5. Schema Naming

The current convention is `repo_project_{project_id}`. Keep this convention unless code, grants, tests, and the API response are updated together.

## 6. POC Status

This is a local POC. The mock-payment setting allows local request testing without a payment gateway, subject to the configured database approvals and copy workflow. It does not establish real payment verification, remote frontend integration, full LLM integration, production readiness, or approval for real clinical-data use.


## 7. Ten-Dataset Copy Verification

The local API returned HTTP 200 for proj_102. All ten destination tables were verified. Expected and copied row counts matched: patient 100, visit 100, diagnosis 100, endoscopy 100, medication 28, neurology 100, operation 100, radiology 24, laboratory 100, and vital signs 88. Payment was simulated using ALLOW_MOCK_PAYMENT=true. Cohort-key clinical validity and real payment verification remain subject to further review.
