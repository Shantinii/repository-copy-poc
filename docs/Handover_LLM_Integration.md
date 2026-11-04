# Schema Metadata Helper

## 1. Get Schema Context

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
from clinical_repository_copy import get_schema_context

schema_context = get_schema_context("proj_101")
```

Reads column names and data types from `INFORMATION_SCHEMA.COLUMNS` for the specified project schema. Returns metadata only, not clinical records.

The project schema is resolved using `repo_project_{project_id}`.

## 2. Dataset Catalogue

The runtime catalogue is `docs/dataset_catalog.json`.

It maps all 10 dataset IDs to their source tables. Use the catalogue instead of hardcoding table names.

## 3. Read-Only Database Access

The schema-context helper uses the dedicated account configured with:

- `LLM_DB_USER` (default username: `haven_llm_reader`)
- `LLM_DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`

It does not use `CLINICAL_COPY_DB_USER` and does not select `haven_poc_source` as its default database. The MySQL account must receive `SELECT` only on each explicitly approved project schema. Do not grant access to `haven_poc_source` or other project schemas.

The supplied provisioning SQL grants access to `repo_project_proj_101` only. Repeat a project-specific grant only after that project schema has been approved for LLM access. Replace the password placeholder with a unique secret and keep it outside Git.

The LLM may use the returned schema metadata to construct its data dictionary (`luchan`). The helper does not return clinical row values. Hari's query execution must remain restricted to approved project schemas and approved tables.

A separate HTTP metadata endpoint has not been implemented.

## 4. Related Files

- `scripts/clinical_repository_copy.py`
- `docs/dataset_catalog.json`
- `scripts/test_schema_context.py`
- `docs/repository_copy_design.md`
- `docs/llm_reader_provisioning.sql`

**Status:** The schema metadata helper is implemented to use a dedicated read-only LLM connection. MySQL account provisioning, credential configuration, and live metadata-query verification remain pending until the SQL is run and tested locally.
