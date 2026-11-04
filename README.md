# Data Safe Haven: Repository-Copy POC

## Purpose

Local POC for copying approved clinical cohorts into project-specific MySQL schemas through an authenticated API.

## Implemented

- FastAPI endpoint: `POST /api/repository/copy`.
- Dynamic registry for 10 datasets: `docs/dataset_catalog.json`.
- Cohort-scoped MySQL copying using `INSERT ... SELECT`.
- Project locking, copy-job idempotency, row-count checks, and JSON logging.
- API success manifest.
- Schema metadata helper: `get_schema_context(project_id)`.

## Run Locally (WSL)

From the repository root:

```bash
python -m pip install -r requirements.txt
python -m uvicorn scripts.api:app --host 127.0.0.1 --port 8090
```

Open `http://127.0.0.1:8090/docs` for the API interface.

The local address is not accessible to remote machines.

## Run Tests

```bash
python -m pytest -q scripts/test_api_fastapi.py scripts/test_repository_copy_api.py scripts/test_dataset_catalog_registry.py scripts/test_schema_context.py
```

The tests mock database and payment operations. Passing tests do not confirm live MySQL integration or payment verification.

## Pending

- Connect a trusted server-to-server payment verifier. The API currently returns HTTP 503 until configured.
- Configure an internal deployment address for backend access.
- Create a separate read-only, project-scoped database account for LLM access. The current metadata helper uses the clinical copy connection.
- Confirm cohort-key relationships for all datasets.
- Obtain institutional IT, security, and data-governance approval before using real clinical data.

**Status:** Local POC. Not production-ready or approved for real clinical-data use.

## Handover Documents

- `docs/HANDOVER_FRONTEND_INTEGRATION.md` — API integration.
- `docs/HANDOVER_LLM_INTEGRATION.md` — Schema metadata and read-only access.
- `docs/HANDOVER_STATUS.md` — Implementation status and pending work.
- `docs/repository_copy_design.md` — Architecture and security design.

Do not commit `.env` files, credentials, API tokens, workbooks, clinical data, database exports, or generated logs.