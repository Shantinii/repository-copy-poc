import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import stage_all_worksheets as loader


def create_test_workbook(path, headers=None, sheet_names=None):
    names = sheet_names or loader.EXPECTED_SHEETS
    workbook = Workbook()

    first = workbook.active
    first.title = names[0]

    for name in names[1:]:
        workbook.create_sheet(name)

    for sheet in workbook.worksheets:
        columns = headers or ["DeID", "Value", None]

        for index, value in enumerate(columns, start=1):
            sheet.cell(row=1, column=index, value=value)

        sheet.append(["00123", "sample", "retained"])

    workbook.save(path)
    workbook.close()


def configure_paths(monkeypatch, tmp_path, workbook):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_ONLY=1\n", encoding="utf-8")

    monkeypatch.setattr(loader, "WORKBOOK", workbook)
    monkeypatch.setattr(loader, "ENV_FILE", env_file)


def test_reads_all_ten_worksheets(monkeypatch, tmp_path):
    workbook = tmp_path / "sample.xlsx"
    create_test_workbook(workbook)
    configure_paths(monkeypatch, tmp_path, workbook)

    datasets, manifest = loader.read_workbook()

    assert len(datasets) == 10
    assert len({item["dataset_id"] for item in datasets}) == 10

    for item in datasets:
        assert item["row_count"] == 1
        assert item["column_count"] == 3
        assert item["records"][0][0] == "00123"

    assert len(manifest) == 30


def test_preserves_blank_headers_and_maps_them(monkeypatch, tmp_path):
    workbook = tmp_path / "sample.xlsx"
    create_test_workbook(workbook)
    configure_paths(monkeypatch, tmp_path, workbook)

    datasets, manifest = loader.read_workbook()

    assert datasets[0]["headers"][2] == "__source_column_003"
    assert manifest[2]["blank_header_mapped"] is True


def test_rejects_unexpected_sheet_names(monkeypatch, tmp_path):
    workbook = tmp_path / "sample.xlsx"
    create_test_workbook(
        workbook,
        sheet_names=["unexpected_sheet"]
    )
    configure_paths(monkeypatch, tmp_path, workbook)

    with pytest.raises(RuntimeError, match="sheet names/order"):
        loader.read_workbook()


def test_rejects_duplicate_column_headers(monkeypatch, tmp_path):
    workbook = tmp_path / "sample.xlsx"
    create_test_workbook(
        workbook,
        headers=["DeID", "DeID", "Value"]
    )
    configure_paths(monkeypatch, tmp_path, workbook)

    with pytest.raises(RuntimeError, match="Duplicate mapped column"):
        loader.read_workbook()


def test_serialises_values_without_unnecessary_conversion():
    assert loader.serialise_cell(None) is None
    assert loader.serialise_cell(True) == "1"
    assert loader.serialise_cell(123.0) == "123"
    assert loader.serialise_cell(12.5) == "12.5"
    assert loader.serialise_cell(Decimal("12.50")) == "12.50"
    assert loader.serialise_cell(date(2026, 1, 2)) == "2026-01-02"
    assert loader.serialise_cell(
        datetime(2026, 1, 2, 10, 30)
    ) == "2026-01-02 10:30:00"
