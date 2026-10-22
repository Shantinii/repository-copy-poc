# Data Safe Haven - Repository Copy Design

**Status:** Preliminary proposal  
**Purpose:** Transfer an approved dataset into a project repository after successful payment.

## 1. Objective

Transfer only authorised data, verify its integrity, restrict access by project, and record each transfer for auditing.

## 2. Proposed Workflow

1. Researcher selects a dataset and completes payment.
2. Backend verifies payment and checks for duplicate requests.
3. Backend confirms project approval and dataset access rights.
4. A unique transfer job is created.
5. Approved data is securely copied to temporary storage.
6. The system validates the data and file integrity.
7. Validated data is published to the project repository.
8. Access is granted to authorised researchers.
9. Transfer status and audit details are recorded.

Payment alone does not grant access to the data warehouse.

![Dataset transfer workflow](mermaid-diagram.png)

## 3.A Transfer Method Comparison

| Option | Advantages | Limitations |
|---|---|---|
| **A. Backend-managed transfer** | Automated, auditable, supports validation and retries. | Requires backend development and repository access. |
| **B. Secure download link** | Simple for a small proof of concept (POC). | Requires download and import; links need protection. |
| **C. Scheduled/batch transfer** | Suitable for multiple or large transfers. | Delayed delivery and more complex job management. |

## 3.B Comparison of repository storage and transfer options

There are three options to consider. Options A and B describe where data is stored, while Option C describes how data is transferred. Option C can be used together with A or B.

| Criteria | Option A: Separate MySQL Schema | Option B: Separate MySQL Instance | Option C: Export and Import |
|---|---|---|---|
| **How it works** | Each project has its own schema on the same MySQL server. | Each project runs on a separate MySQL instance. | Approved data is exported to a temporary file and imported into the project repository. |
| **Example** | One MySQL server with separate schemas for Project A and Project B. | Project A and Project B each have their own MySQL instance. | Export selected data using `mysqldump`, then import it into the destination database. |
| **Main benefit** | Simple to set up and manage for a POC. | Provides more separation between projects. | Flexible when moving data between different database environments. |
| **Main limitation** | Projects share the same server, so server-level problems may affect all projects. | More expensive and requires more maintenance. Shared infrastructure can still create risks. | Temporary files must be protected, checked, and deleted securely. |
| **After payment** | Copy approved data into the project's schema. | Copy approved data into the project's instance. | Export approved data, transfer it securely, and import it into the project repository. |
| **Suitability for this POC** | A practical starting option, subject to IT and security approval. | Consider if stronger isolation is required. | Useful if a file-based transfer is needed. |

### References

- [AWS: Multi-tenant architectures](https://docs.aws.amazon.com/solutions/multi-tenant-architectures-on-aws/)
- [Microsoft: Storage and data approaches for multitenant solutions](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/storage-data)
- [Microsoft: Azure SQL Database tenancy patterns](https://learn.microsoft.com/en-us/azure/azure-sql/database/saas-tenancy-app-design-patterns)
- [MySQL: `mysqldump` documentation](https://dev.mysql.com/doc/refman/8.4/en/mysqldump.html)

**Note:** These references explain related database and transfer approaches. They do not confirm that another healthcare platform uses this exact workflow.


### Recommendation

**Option A is preferred** when the backend can securely access the repository. It automates copying, validation and audit logging.

If the repository is on a researcher's own computer, Option B may be more practical because the backend may not have direct access to that device.

## 4. Storage Options

| Option | Advantages | Limitations |
|---|---|---|
| **A. Separate MySQL schema per project** | Easier to demonstrate using the existing MySQL server; supports project-specific permissions. | Shares server infrastructure; isolation depends on correct permissions and configuration. |
| **B. Separate MySQL instance per project** | Greater separation of database processes and configuration. | Higher setup and maintenance effort. |
| **C. Controlled export/import** | Flexible across different database destinations. | Temporary files require secure handling; failed imports need recovery procedures. |

**Storage recommendation:** Consider a separate MySQL schema per project for the initial POC, subject to IT/security approval. This is separate from the decision about how data is transferred.

## 5. Security and Failure Handling

- **Payment failure:** Reject the transfer and log the event.
- **Unauthorised request:** Block access and record the rejection.
- **Interrupted transfer:** Retry safely without creating duplicate copies.
- **Validation failure:** Quarantine the data and prevent publication.
- **Repository write failure:** Mark the job as failed and allow a controlled retry.

Additional controls:

- Verify payment on the server.
- Use restricted service accounts and least-privilege permissions.
- Copy only approved records and columns.
- Encrypt data during transfer and protect temporary storage.
- Validate row counts, required columns and file integrity.
- Keep incomplete datasets inaccessible.
- Log transfer IDs, dataset versions, timestamps, status and validation results.
- Never log credentials or patient-level data.

## 6. POC Validation Plan

Use synthetic or explicitly authorised test data.

1. Simulate a successful payment and create a transfer job.
2. Copy an approved dataset into a test repository.
3. Check row counts, required columns and integrity.
4. Repeat the same request to test duplicate prevention.
5. Test unauthorised access and interrupted transfers.
6. Confirm failed transfers remain inaccessible.
7. Check that audit logs record outcomes without sensitive data.

## 7. MySQL POC Implementation

The MySQL repository copy POC was implemented using synthetic data in a local Ubuntu MySQL server running in WSL.

### 7.1 Implementation Completed

- Created two project-specific schemas:
  - `haven_poc_project_001`
  - `haven_poc_project_002`
- Configured separate application accounts with access restricted to their respective schemas.
- Implemented project-to-schema mapping and dataset authorisation allowlists.
- Added payment-status checks to reject unsuccessful payment events.
- Implemented copy-job tracking using the `copy_jobs` table.
- Added duplicate-payment handling and duplicate-record prevention.
- Implemented row-count validation before completing a copy job.
- Added transaction rollback for simulated copy failures.
- Implemented MySQL advisory locks to handle concurrent requests using the same payment ID.
- Added JSON Lines audit logging for copy starts, completions, failures, duplicates, and rejected requests.

### 7.2 Testing Completed

- **Successful copy:** Project 001 copied and validated 3 synthetic records.
- **Successful copy:** Project 002 copied and validated 2 synthetic records.
- **Duplicate handling:** Replayed payment events were identified and ignored.
- **Concurrency:** Simultaneous requests using the same payment ID were handled without duplicate copies.
- **Rollback:** A simulated failure did not leave the temporary test record in the destination.
- **Payment validation:** Unsuccessful payment events were rejected.
- **Authorisation:** Unauthorised project and dataset combinations were rejected.
- **Schema isolation:** Each project account was denied access to the other project's schema.
- **Audit logging:** All 27 audit entries were valid JSON during verification.

### 7.3 Clinical Sample-Data Repository Workflow

A separate clinical sample-data workflow has been implemented using the local MySQL server. This workflow is distinct from the synthetic repository-copy POC described in Sections 7.1 and 7.2.

**Schemas**

- Source schema: `haven_poc_source`
- Destination schema: `haven_poc_clinical_001`

**Approved tables**

The workflow is restricted to three tables:

- `bi_patient_data`
- `bi_visit_data`
- `bi_diagnosis_data`

**Source data preparation**

The source loader reads the selected worksheets from the sample Excel workbook, removes entirely empty columns, checks required columns and key uniqueness, and validates patient, visit, and diagnosis relationships before loading the data into the source schema. It refuses to overwrite existing source tables.

**Repository copy controls**

- The copy script uses a fixed source schema, destination schema, and table allowlist.
- The script checks primary keys, column names and ordering, and patient, visit, and diagnosis relationships.
- Data is copied only when all destination tables are empty.
- If the destination already matches the source exactly, the script reports the match without inserting rows.
- Partial or conflicting destination data is rejected.
- A check-only mode performs preflight validation without inserting or changing rows.
- The workflow checks the configured local MySQL connection, port, schema, and database account.
- Database credentials are read from the local `.env` file rather than embedded in the script.
- The copy operation validates the destination data before committing and attempts a rollback if an exception occurs.

**Testing completed**

- The source workbook contained 100 rows in each of the three selected tables.
- Initial relationship checks reported zero orphan references.
- The clinical destination was populated and subsequently verified as an exact match to the source.
- A check-only run confirmed the exact-match state without writing data.
- Unit tests covered empty, exact-match, partial, and conflicting destination states.
- Additional tests covered duplicate patient keys and invalid patient/visit/diagnosis references.
- A separate database test verified rollback behaviour in the disposable test schema.

These tests demonstrate the current local POC behaviour. They do not establish production readiness or prove that every failure scenario in the complete clinical copy workflow has been tested.

## 8. Limitations and Next Steps

The project currently contains two distinct implementations: a synthetic-data repository-copy POC and a clinical sample-data repository workflow. Both run locally, but they have different scopes and must be evaluated separately.

### 8.1 Current Limitations

- **Sample data:** The clinical workflow has been tested with a sample workbook. It has not been integrated with the hospital's live data warehouse.
- **Payment verification:** The clinical workflow does not verify real payments. The payment-status checks described in Section 7.1 belong to the separate synthetic POC.
- **Researcher access:** The clinical workflow does not yet implement the complete researcher-facing approval and access-granting process.
- **Audit logging:** The clinical copy script reports validation and copy outcomes, but a complete clinical transfer audit trail has not been demonstrated.
- **Isolation:** The clinical source and destination schemas share a MySQL server. Schema separation and restricted database accounts do not provide full infrastructure isolation.
- **Failure recovery:** A separate disposable-database test demonstrated transaction rollback. Further testing is required for connection failures, partial operations, retries, and recovery across the complete clinical workflow.
- **Schema validation:** The current workflow checks column names and ordering, keys, and relationships. Additional validation of data types, nullability, indexes, and database constraints is still required.
- **Governance:** The workflow has not been approved for production use with real clinical data.

### 8.2 Next Steps

1. Review the source-to-destination column mapping and confirm the approved dataset scope.
2. Extend schema validation to cover data types, nullability, indexes, and integrity constraints.
3. Test failure handling and recovery without modifying the existing clinical destination.
4. Implement and verify a complete audit trail for clinical transfer requests, validation results, and outcomes.
5. Integrate the repository workflow with the I Explore frontend and the approved request and payment-verification process.
6. Review least-privilege permissions, credential handling, access controls, backup, recovery, and deletion procedures.
7. Confirm how temporary project repositories will be isolated and how access will be granted and revoked.
8. Obtain institutional IT, security, and data-governance approval before processing real clinical data.

The current implementation is a local proof of concept. It demonstrates selected data preparation, validation, copying, and destination-state safeguards. It does not establish production readiness, complete end-to-end integration, or approval to process real hospital data.
