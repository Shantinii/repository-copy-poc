from datetime import datetime

import numpy as np
import pandas as pd

import load_sample_source as loader


def test_nulls_convert_to_sql_null():
    assert loader.normalise_value(float("nan")) is None
    assert loader.normalise_value(pd.NA) is None
    assert loader.normalise_value(pd.NaT) is None


def test_dates_convert_to_python_datetime():
    value = pd.Timestamp("2026-03-14 09:25:30")
    result = loader.normalise_value(value)
    assert isinstance(result, datetime)
    assert result == datetime(2026, 3, 14, 9, 25, 30)


def test_numeric_values_are_preserved():
    assert loader.normalise_value(np.int64(12345)) == 12345
    assert loader.normalise_value(np.float64(12.75)) == 12.75


def test_identifier_strings_preserve_leading_zeros():
    assert loader.normalise_value("00123") == "00123"
    assert loader.mysql_type(pd.Series(["00123"], dtype="object"), "Postcode") == "TEXT"


def test_mysql_type_inference():
    assert loader.mysql_type(pd.Series([1, 2], dtype="int64"), "n") == "BIGINT"
    assert loader.mysql_type(pd.Series([1.5, 2.5]), "n") == "DOUBLE"
    assert loader.mysql_type(
        pd.Series(pd.to_datetime(["2026-01-01"])), "dt"
    ) == "DATETIME"
    assert loader.mysql_type(pd.Series([True, False]), "flag") == "TINYINT(1)"


def test_real_workbook_has_valid_relationships():
    tables = loader.prepare_tables()
    assert set(tables) == {
        "bi_patient_data", "bi_visit_data", "bi_diagnosis_data"
    }
    assert all(len(frame) == 100 for frame in tables.values())

    report = __import__(
        "repository_copy_core"
    ).validate_dataset_relationships(tables)
    assert report.passed, report


def test_workbook_postcode_is_currently_inferred_as_integer():
    tables = loader.prepare_tables()
    postcode = tables["bi_patient_data"]["Posscode"]
    assert pd.api.types.is_integer_dtype(postcode.dtype)
    assert loader.mysql_type(postcode, "Posscode") == "BIGINT"


def test_waiting_time_current_inference_is_text():
    tables = loader.prepare_tables()
    waiting = tables["bi_visit_data"]["Waiting_time"]
    assert waiting.notna().sum() == 49
    assert waiting.nunique(dropna=True) == 1
    assert loader.mysql_type(waiting, "Waiting_time") == "TEXT"
