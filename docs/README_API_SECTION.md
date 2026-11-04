## Clinical Repository-Copy API

The FastAPI service exposes `POST /api/repository/copy`.

It validates project approval, dataset approval, and cohort approval against MySQL before calling the copy engine. Requested dataset IDs are not treated as proof of approval.

### 1. Start the API

Run from the repository root:

```bash
source ../.venv/bin/activate
python -m uvicorn scripts.api:app --host 127.0.0.1 --port 8090
```

Open `http://127.0.0.1:8090/docs` for the API interface.

### 2. Request

The endpoint requires a server-to-server bearer token. Keep `COPY_API_TOKEN` on the backend. Never expose it in browser JavaScript.

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

The cohort must already be approved for the project in MySQL. The caller cannot provide destination schemas, source tables, SQL statements, or payment status.

### 3. Payment Verification

Payment verification is currently unavailable. `get_verified_payment_status()` in `scripts/api.py` fails closed with HTTP 503 until a trusted server-to-server verifier is connected.

The verifier must confirm that the payment belongs to the project and covers all requested datasets. Do not bypass this check by returning `succeeded`.

### 4. Install Dependencies and Run Tests

```bash
python -m pip install -r requirements.txt

python -m pytest -q scripts/test_api_fastapi.py scripts/test_repository_copy_api.py scripts/test_dataset_catalog_registry.py scripts/test_schema_context.py
```

**Test limitation:** API tests mock database and payment operations. They do not verify live MySQL copying or payment-provider integration.