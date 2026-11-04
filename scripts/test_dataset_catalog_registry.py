"""Tests for the dataset_catalog.json-driven repository-copy registry."""

import json
from pathlib import Path

import pytest

import clinical_repository_copy as crc


def test_catalog_loads_all_ten_dataset_definitions():
    registry = crc.load_dataset_registry()
    assert len(registry) == 10
    assert registry["DS_RADIOLOGY_PROCEDURE"]["source_table"] == "stg_ds_radiology_procedure"
    assert registry["DS_VITAL_SIGNS"]["source_table"] == "stg_ds_vital_signs"


def test_registry_uses_source_table_from_catalog(tmp_path):
    catalog = [{
        "dataset_id": "DS_EXAMPLE",
        "display_label": "Example Dataset",
        "source_worksheet": "example sheet",
        "source_schema": "haven_poc_source",
        "source_table": "stg_example_dataset",
        "primary_key": None,
        "key_status": "cohort_key_required",
    }]
    path = tmp_path / "dataset_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    registry = crc.load_dataset_registry(path)

    assert registry["DS_EXAMPLE"]["source_table"] == "stg_example_dataset"


def test_catalog_rejects_duplicate_dataset_ids(tmp_path):
    item = {
        "dataset_id": "DS_EXAMPLE",
        "display_label": "Example Dataset",
        "source_worksheet": "example sheet",
        "source_schema": "haven_poc_source",
        "source_table": "stg_example_dataset",
    }
    path = tmp_path / "dataset_catalog.json"
    path.write_text(json.dumps([item, item]), encoding="utf-8")

    with pytest.raises(crc.CopyValidationError, match="Duplicate dataset_id"):
        crc.load_dataset_registry(path)


def test_catalog_rejects_unsafe_source_table_names(tmp_path):
    item = {
        "dataset_id": "DS_EXAMPLE",
        "display_label": "Example Dataset",
        "source_worksheet": "example sheet",
        "source_schema": "haven_poc_source",
        "source_table": "example; DROP DATABASE test",
    }
    path = tmp_path / "dataset_catalog.json"
    path.write_text(json.dumps([item]), encoding="utf-8")

    with pytest.raises(crc.CopyValidationError, match="invalid source_table"):
        crc.load_dataset_registry(path)
