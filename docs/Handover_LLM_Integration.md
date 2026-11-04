# Schema Metadata Helper

## 1. Get Schema Context

```python
from clinical_repository_copy import get_schema_context

schema_context = get_schema_context("proj_101")
```

Reads column names and data types from `INFORMATION_SCHEMA.COLUMNS` for the specified project schema.

Returns metadata only, not clinical records.

## 2. Dataset Catalogue

The runtime catalogue is `docs/dataset_catalog.json`.

It maps all 10 dataset IDs to their source tables. Use the catalogue instead of hardcoding table names.

## 3. Access Control

The current helper uses `CLINICAL_COPY_DB_USER`.

Before enabling LLM database access:

- Create a dedicated read-only database account.
- Restrict access to approved project schemas.
- Enforce project authorisation for every query.
- Keep source database and copy-service credentials inaccessible to the LLM.

A separate HTTP metadata endpoint has not been implemented.

## 4. Related Files

- `scripts/clinical_repository_copy.py`
- `docs/dataset_catalog.json`
- `scripts/test_schema_context.py`
- `docs/repository_copy_design.md`

**Status:** Schema metadata helper implemented. Dedicated read-only LLM database access remains pending.