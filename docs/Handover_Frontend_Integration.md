# Frontend Integration Handover

## 1. API Endpoint

```http
POST /api/repository/copy
Content-Type: application/json
Authorization: Bearer <COPY_API_TOKEN>
```

The bearer token must remain on the backend. Never expose it in browser JavaScript.

## 2. Request Body

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

The API checks project, dataset, and cohort approvals. Do not send destination schema names, source table names, SQL statements, or browser-supplied payment status.

## 3. Successful Response

HTTP `200 OK` returns:

```json
{
  "status": "SUCCESS",
  "project_id": "proj_101",
  "target_schema": "repo_project_proj_101",
  "database_host": "127.0.0.1",
  "database_port": 3308,
  "available_tables": [
    "bi_patient_data",
    "bi_visit_data",
    "bi_diagnosis_data"
  ],
  "timestamp": "<UTC timestamp ending in Z>"
}
```

The schema convention is `repo_project_{project_id}`. For `project_id="proj_101"`, the schema is `repo_project_proj_101`. The schema helper must be called with `get_schema_context("proj_101")`, not `get_schema_context("101")`.

`DB_PORT` is configurable as an integer from `1` to `65535`. The default remains `3308`. The API and copy engine verify that the connected MySQL server reports the configured port.

## 4. Response Codes

| Code | Meaning |
|---|---|
| 200 | Copy completed |
| 400 | Invalid request |
| 401 | Invalid service token |
| 402 | Payment status is not successful |
| 403 | Project or dataset not approved |
| 409 | Copy job did not complete |
| 503 | Required service or configuration unavailable; also returned when mock payment is disabled and no trusted payment verifier is configured |

## 5. Local POC Payment Testing

The API supports simulated payment status for local POC testing through the `ALLOW_MOCK_PAYMENT` environment variable.

Add this setting to the local `.env` file:

```env
ALLOW_MOCK_PAYMENT=true
```

When enabled, `get_verified_payment_status()` returns `succeeded` so the local API request can proceed to project/dataset authorisation and the repository-copy workflow. A successful copy still requires valid service-token configuration, database connectivity, approved project and datasets, and an approved cohort.

This setting simulates payment only. It does not verify a real payment reference, payment ownership, or dataset coverage against a payment provider. Keep it disabled or unset outside local POC testing.

When the flag is false or unset, the API remains fail-closed and returns HTTP `503` if a trusted payment verifier is not configured.

## 6. Pending Integration

1. Connect a trusted server-to-server payment verifier.
2. Deploy the API to an internal network address accessible to the backend.
3. Configure network routing, TLS/reverse proxy, and backend authentication.

The API currently runs locally at `127.0.0.1:8090`. Remote frontend integration requires deployment and network access to the service.

## 7. Relevant Files

- `scripts/api.py`
- `scripts/clinical_repository_copy.py`
- `scripts/repository_copy_core.py`
- `docs/dataset_catalog.json`
- `docs/README_API_SECTION.md`

## 8. Security

The frontend must call the API through a trusted backend. Do not expose API tokens, MySQL credentials, source database access, or copy-service credentials to the browser.
