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

The schema convention is `repo_project_{project_id}`. Do not change it without coordinating the backend and database.

## 4. Response Codes

| Code | Meaning |
|---|---|
| 200 | Copy completed |
| 400 | Invalid request |
| 401 | Invalid service token |
| 402 | Payment not verified |
| 403 | Project or dataset not approved |
| 409 | Copy job did not complete |
| 503 | Payment verifier or required service unavailable |

## 5. Pending Integration

1. Connect a trusted server-to-server payment verifier.
2. Deploy the API to an internal network address accessible to the backend.
3. Configure network routing, TLS/reverse proxy, and backend authentication.

The API currently runs locally at `127.0.0.1:8090`. The payment verifier is not configured, so requests fail closed with HTTP 503.

## 6. Relevant Files

- `scripts/api.py`
- `scripts/clinical_repository_copy.py`
- `scripts/repository_copy_core.py`
- `docs/dataset_catalog.json`
- `docs/README_API_SECTION.md`

## 7. Security

The frontend must call the API through a trusted backend. Do not expose API tokens, MySQL credentials, source database access, or copy-service credentials to the browser.