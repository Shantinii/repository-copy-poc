# Repository-Copy POC: Handover Status

## 1. Implemented

| Component | File |
|---|---|
| FastAPI copy endpoint and validation | `scripts/api.py` |
| Shared validation logic | `scripts/repository_copy_core.py` |
| Dynamic 10-dataset registry | `docs/dataset_catalog.json` |
| Cohort-scoped SQL copy | `scripts/clinical_repository_copy.py` |
| Copy locking and idempotency | `scripts/clinical_repository_copy.py` |
| JSON completion logging | `scripts/clinical_repository_copy.py` |
| API success manifest | `scripts/api.py` |
| Schema metadata helper | `scripts/clinical_repository_copy.py` |

## 2. Test Results

Command:
```bash
python -m pytest -q scripts/test_api_fastapi.py scripts/test_repository_copy_api.py scripts/test_dataset_catalog_registry.py scripts/test_schema_context.py
```

**Result: 41 passed.**

Tests use mocked database and payment operations where applicable. They do not confirm live MySQL integration or real payment verification.

## 3. Pending

1. Connect a trusted payment verifier. The API currently returns HTTP 503 until configured.
2. Configure a network-accessible deployment address. The current server binds to `127.0.0.1:8090`.
3. Create a dedicated read-only, project-scoped database account for LLM access.
4. Confirm cohort-key relationships across all datasets.
5. Verify MySQL permissions and failure handling.
6. Test the full API copy flow against a disposable MySQL project.
7. Obtain institutional IT, security, and data-governance approval before using real clinical data.

## 4. Retained Supporting Files

Existing sample-loading, database-safety, and regression-test files remain in the repository. The five diagnostic scripts from the earlier cleanup request were not present in the supplied GitHub ZIP.

## 5. Schema Naming

The current convention is `repo_project_{project_id}`. Keep this convention unless code, grants, tests, and the API response are updated together.

## 6. POC Status

This is a local POC. It is not production-ready or approved for real clinical-data use.