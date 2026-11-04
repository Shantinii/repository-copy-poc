## Clinical repository-copy API

The local FastAPI service exposes `POST /api/repository/copy`. It accepts a project, a payment reference, the requested dataset IDs, and an already-approved cohort ID. Dataset IDs supplied by the caller are requests, not proof of approval. The API reads project and dataset approval records from MySQL and validates the resulting allowlist with `repository_copy_core.py` before calling the existing clinical copy engine.

### Start locally (WSL)

Activate the repository virtual environment, then run from the repository root:

```bash
source ../.venv/bin/activate
python -m uvicorn scripts.api:app --host 127.0.0.1 --port 8090
```

Open `http://127.0.0.1:8090/docs` for the local OpenAPI interface. Keep the Uvicorn terminal running while using the API.

### Request

The endpoint requires a server-to-server bearer token in the `Authorization` header. Do not put `COPY_API_TOKEN` in browser JavaScript or expose it to the frontend. Tusha's backend should call this service.

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

`cohort_id` is required by the current copy engine. The cohort must already be approved for the project in the MySQL control records. Destination schema names, source table names, SQL, and payment status are not accepted from the caller.

`DB_PORT` is configurable as an integer from `1` to `65535`; its default is `3308`. The API and copy engine verify the connected server port against this configured value.

### Local POC payment testing

For local POC testing only, set `ALLOW_MOCK_PAYMENT=true` in the local `.env` file. The API then returns a simulated `succeeded` status and proceeds to project/dataset authorisation and the copy workflow. This does not verify a real payment, payment ownership, or dataset coverage.

When the flag is false or unset, the API remains fail-closed and returns HTTP 503 until a trusted server-to-server payment verifier is connected. Do not enable mock payment outside the local POC environment.

### Install and test

The required dependencies, including `httpx`, are already listed in `requirements.txt`. Install them with `python -m pip install -r requirements.txt`.

```bash
python -m pip install -r requirements.txt
python -m pytest -q scripts/test_api_fastapi.py scripts/test_repository_copy_api.py scripts/test_dataset_catalog_registry.py scripts/test_schema_context.py scripts/test_database_port_config.py
```

The API tests mock database and payment operations. They do not prove live MySQL copying or payment-provider integration.
