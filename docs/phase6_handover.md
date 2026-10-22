# Phase 6 Handover: Documentation and Integration

**Project:** Data Safe Haven for Research on AI in Medicine
**Status:** Proposed integration design; review required
**Scope:** Local proof of concept (POC), using approved sample data only

## 1. Purpose

This document records the current repository-copy implementation, proposes an interface for frontend/backend integration, defines a preliminary data-access boundary for the LLM component, and sets out an end-to-end demonstration plan.

The interface and integration design below are proposals. They have not yet been agreed with the integration team or the integration team. This POC is not approved for production use with real clinical data.

## 2. Current implementation

### 2.1 Workbook audit and source loading

The audited workbook contains ten populated worksheets. The current POC scope is limited to three:

- `bi_patient data`, loaded as `bi_patient_data`
- `bi_visit data`, loaded as `bi_visit_data`
- `bi_diagnosis data`, loaded as `bi_diagnosis_data`

The source loader checks required keys and relationships, removes entirely empty columns, creates source tables, and refuses to overwrite existing source tables. The selected sample contains 100 rows per table. These counts describe the current sample dataset, not a production dataset.

### 2.2 MySQL clinical repository copy

The current script is `scripts/clinical_repository_copy.py`.

- Source schema: `haven_poc_source`
- Destination schema: `haven_poc_clinical_001`
- Approved tables: `bi_patient_data`, `bi_visit_data`, `bi_diagnosis_data`
- Approved local MySQL port: `3308`
- Invocation: `python scripts/clinical_repository_copy.py`
- Read-only preflight: `python scripts/clinical_repository_copy.py --check-only`

The script uses a fixed schema and table allowlist. It checks the configured connection identity, table/key structure, and patient/visit/diagnosis relationships. It copies data only when all destination tables are empty. If the destination already matches the source, it reports that state without writing. A partial or conflicting destination is rejected. It reports counts and validation outcomes rather than clinical row values.

This script is a local command-line workflow, not an HTTP API. It does not accept a researcher request, verify a real payment, call the frontend, publish a dataset through a separate approval service, or expose an LLM query endpoint.

### 2.3 Separate synthetic SQLite demonstration

`scripts/repository_copy_poc.py` is a separate synthetic-data demonstration. Its README describes payment-event handling, duplicate prevention, and JSON Lines audit logging using local SQLite files under `.poc_runtime/`. It does not connect to MySQL, a hospital system, or a payment provider.

Do not treat the synthetic workflow as proof that payment verification or the full clinical MySQL workflow has been integrated.

### 2.4 Tests and known limitations

Automated unit and functional tests, plus selected live MySQL tests, have been run. The repeatable runner is `scripts/run_phase5_tests.ps1`. The test destination `haven_poc_clinical_test` is used for live destructive/conflict tests; do not use the main destination `haven_poc_clinical_001` as a test target.

Phase 5 security items remain open. In particular, the loader account has broad `DROP` permission on the source schema; the intended researcher/LLM account is not provisioned; audit-log ACL and retention need review; and live loader failure recovery under restricted privileges has not been demonstrated. Do not claim that all access-control and audit requirements are complete.

## 3. Proposed architecture

1. **I Explore frontend:** A researcher chooses a dataset/project and submits a request.
2. **Backend request service:** Authenticates the user and validates project approval, dataset entitlement, and verified payment status using trusted backend/provider evidence. The browser must not be trusted to assert that payment succeeded.
3. **Copy-job coordinator:** Creates or retrieves an idempotent job record and assigns a unique request/job identifier.
4. **Repository copy service:** Executes an approved copy operation with fixed server-side mappings and allowlists. It does not accept arbitrary schema or table names from the browser.
5. **Validation and publication gate:** Confirms expected tables, schema, row counts, keys, relationships, and integrity checks. Data is not made available to the researcher or LLM until validation and authorisation pass.
6. **Published project repository:** Holds the approved dataset for the project.
7. **LLM service:** Uses a separate read-only identity and a controlled query interface limited to approved published data.

This architecture is a proposal. Only the existing script-level copy and validation behaviour described in Section 2 is currently implemented in this repository.

## 4. Proposed frontend/backend interface contract

The following is a proposed contract for discussion, not an existing API specification.

### 4.1 Submit a request

**Proposed endpoint:** `POST /api/v1/repository-requests`

The authenticated backend should derive the researcher identity from the session/token rather than trusting a user ID supplied by the browser.

Example request body:

```json
{
  "project_id": "project-demo-001",
  "dataset_id": "approved-dataset-001"
}
```

Do not accept destination schema names, raw SQL, table names, payment status, or arbitrary file paths from the client.

The backend must independently verify project approval, dataset entitlement, and payment status against the authoritative systems. If payment verification is not integrated, the request must remain in a non-authorised state and the demo must label payment as simulated.

### 4.2 Proposed response

For an accepted request, return a job identifier and status, for example:

```json
{
  "request_id": "generated-by-server",
  "status": "pending_validation"
}
```

The identifier above is illustrative. A real implementation must generate it server-side.

**Proposed status endpoint:** `GET /api/v1/repository-requests/{request_id}`

Suggested states:

- `pending_authorisation`
- `pending_validation`
- `copying`
- `validating`
- `published`
- `rejected`
- `failed`

The API should return a safe status and non-sensitive error code. It must not return database credentials, SQL text, raw exception messages, clinical row values, or internal server paths.

### 4.3 Idempotency and retries

- Use a server-generated request/job ID and a uniqueness rule tied to the relevant project, dataset, and verified entitlement/payment event.
- Repeated submissions must not create duplicate copies or bypass authorisation.
- Retry only failures classified as retryable.
- A partial or conflicting destination must remain unpublished and require a controlled recovery path.
- Record status transitions and outcomes without including patient-level data or secrets in logs.

### 4.4 Execution boundary

The web frontend must not connect directly to MySQL. The backend should invoke a narrowly scoped service or worker. The existing script is not yet an API and has a fixed destination schema; it must not be called concurrently for arbitrary requests until a safe job model and destination mapping are implemented.

## 5. Proposed published-data boundary for the integration team's LLM

### 5.1 Principle

The LLM should access only the approved, validated, published dataset for the relevant project. It should not connect using the loader or copy-service account, and it should not have access to the source schema.

### 5.2 Initial POC allowlist

Subject to confirmation of the intended analytical questions and column-level approvals, the initial table allowlist can be limited to:

- `haven_poc_clinical_001.bi_patient_data`
- `haven_poc_clinical_001.bi_visit_data`
- `haven_poc_clinical_001.bi_diagnosis_data`

This is a provisional table-level boundary, not approval for every column. Review the source-to-destination mapping and data dictionary before enabling LLM access. Exclude direct identifiers, unnecessary sensitive fields, and columns not required for the approved research use.

### 5.3 Required controls

- Create a dedicated LLM/read-only database account only after the intended role, host, schema, and query path are confirmed.
- Grant `SELECT` only on explicitly approved published tables or views. Do not grant source-schema access, write privileges, DDL privileges, or access to other project schemas.
- Prefer approved views that expose only the minimum necessary columns over unrestricted table access.
- Do not allow the model to execute arbitrary SQL with broad database credentials. Use a controlled query service, allowlisted tables/columns, parameterised queries where applicable, query limits, timeouts, and result-size limits.
- Enforce project authorisation in the backend on every query. A schema name alone is not a complete project authorisation mechanism.
- Log the actor/service identity, project, approved query operation, timestamp, result status, and row count where appropriate. Do not log credentials or raw clinical records.
- Define output controls for small-cell disclosure, re-identification risk, and attempts to retrieve individual-level records before using real clinical data.
- Revoke access when project approval or entitlement ends.

The account `researcher_agent` was not present in the local MySQL instance during the latest checks. Do not assume it exists or create it until the interface and approved data scope are agreed.

## 6. Proposed end-to-end demonstration

Use synthetic or explicitly authorised sample data only. Keep all work on the approved local environment.

1. **Request:** Submit a project/dataset request through a test frontend or a documented mock request.
2. **Authorisation:** Demonstrate approved and rejected requests. If real payment verification is not connected, clearly label this step as simulated.
3. **Job creation:** Generate a unique request ID and show status transitions.
4. **Copy:** Run the copy service against a dedicated test destination, not `haven_poc_clinical_001`.
5. **Validation:** Verify approved tables, schema, keys, relationships, and row counts.
6. **Publication:** Mark the test dataset as published only after validation succeeds.
7. **Authorised query:** Query the published test dataset through the proposed read-only LLM/query identity.
8. **Denied query:** Demonstrate that source-schema access and unapproved tables/columns are denied.
9. **Failure and retry:** Demonstrate that a conflict or failed validation prevents publication and that a controlled retry does not duplicate data.
10. **Audit review:** Inspect logs for status and outcome records, ensuring they contain no secrets or clinical row values.

The existing test suite supports portions of the copy, validation, conflict, and rollback stages. The full request-to-authorised-query journey has not yet been demonstrated.

## 7. Decisions required from the integration team

### Frontend/backend integration owner

- What backend framework and service entry point will be used?
- Which component authenticates researchers and verifies project approval and payment?
- What request fields and status/error responses does the frontend need?
- How will requests be queued, deduplicated, retried, and tracked?
- How will the copy service be invoked without exposing database credentials to the frontend?
- What mechanism will publish a validated dataset and grant/revoke access?

### LLM integration owner

- Will the LLM connect through a backend query API or directly to a restricted database account?
- What analytical tasks and query types are required?
- Which tables and columns are necessary for those tasks?
- Are approved views needed to remove unnecessary or sensitive columns?
- What result-size, timeout, output disclosure, and audit controls are required?

### For project/IT/security owners

- Confirm the permitted local deployment topology and account ownership.
- Review least-privilege grants, especially the loader account's `DROP` permission.
- Decide audit-log access controls and retention.
- Approve data scope and publication rules before any real clinical data is used.

## 8. Handover checklist

- [x] Workbook scope and source relationships audited for the selected sample.
- [x] Source loader implemented with validation and overwrite protection.
- [x] Fixed-schema MySQL copy workflow implemented.
- [x] Automated and selected live MySQL tests run.
- [x] Copy design documentation exists.
- [ ] Update the main README from â€œInitial workspace setupâ€ to an accurate current status.
- [ ] Confirm the authoritative source-to-destination mapping.
- [ ] Review and resolve Phase 5 access-control and audit-log carryovers.
- [ ] Review the proposed interface with the frontend/backend integration owner.
- [ ] Confirm the LLM access method and column-level boundary with the LLM integration owner.
- [ ] Implement the agreed request API/job model and publication gate.
- [ ] Demonstrate the full request-to-authorised-query flow on a dedicated test destination.
- [ ] Obtain governance/security approval before production or real clinical-data use.

## 9. Current status statement

The repository demonstrates a local sample-data loading and MySQL repository-copy workflow with automated tests and selected live database checks. It also contains a separate synthetic SQLite workflow. Frontend/API integration, trusted payment verification, publication orchestration, the LLM query boundary, and the complete end-to-end demonstration remain pending. The POC is not production-ready and must not be described as approved for real clinical-data use.
