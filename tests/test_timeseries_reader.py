"""Tests for analysis/timeseries_reader.py."""

import h5py
import numpy as np
import pytest

from analysis.timeseries_reader import (
    invalid_columns,
    list_entities,
    load_run,
    parse_run_key,
    session_runs,
    standardize_run,
)


def test_parse_run_key_with_run_segment():
    entity = parse_run_key("ses-001/ses-001_task-bourne01_run-1_timeseries")
    assert entity == {
        "key": "ses-001/ses-001_task-bourne01_run-1_timeseries",
        "session": "001", "task": "bourne01", "run": "1",
    }


def test_parse_run_key_without_run_segment():
    """friends' keys carry no run segment at all."""
    entity = parse_run_key("ses-001/ses-001_task-s01e02a_timeseries")
    assert entity["run"] is None
    assert entity["task"] == "s01e02a"
    assert entity["session"] == "001"


def test_parse_run_key_rejects_unmatched_string():
    with pytest.raises(ValueError):
        parse_run_key("not-a-timeseries-key")


def test_session_runs_groups_and_sorts_by_run():
    entities = [
        parse_run_key("ses-001/ses-001_task-b_run-2_timeseries"),
        parse_run_key("ses-001/ses-001_task-a_run-1_timeseries"),
        parse_run_key("ses-002/ses-002_task-c_timeseries"),
    ]
    grouped = session_runs(entities)
    assert list(grouped.keys()) == ["001", "002"]
    assert [e["run"] for e in grouped["001"]] == ["1", "2"]


def test_invalid_columns_flags_nan_and_constant():
    array = np.array([[1.0, 2.0, np.nan], [2.0, 2.0, 1.0], [3.0, 2.0, 1.0]])
    assert list(invalid_columns(array)) == [False, True, True]


def test_standardize_run_has_zero_mean_unit_variance_on_valid_columns():
    rng = np.random.default_rng(0)
    array = rng.normal(loc=5.0, scale=3.0, size=(200, 4)).astype(np.float32)
    standardized, invalid = standardize_run(array)

    assert not invalid.any()
    assert np.allclose(standardized.mean(axis=0), 0, atol=1e-4)
    assert np.allclose(standardized.std(axis=0), 1, atol=1e-2)


def test_standardize_run_marks_invalid_columns_as_nan():
    array = np.ones((50, 3), dtype=np.float32)
    array[:, 0] = np.arange(50)  # the only valid (non-constant) column
    standardized, invalid = standardize_run(array)

    assert list(invalid) == [False, True, True]
    assert np.isnan(standardized[:, 1]).all()
    assert np.isnan(standardized[:, 2]).all()
    assert not np.isnan(standardized[:, 0]).any()


def test_list_entities_and_load_run_round_trip(tmp_path):
    path = tmp_path / "sub-01_timeseries.h5"
    array = np.arange(12, dtype=np.float32).reshape(3, 4)
    with h5py.File(path, "w") as handle:
        handle.create_dataset(
            "ses-001/ses-001_task-a_run-1_timeseries", data=array,
        )
        handle.create_dataset(
            "ses-001/ses-001_task-b_timeseries", data=array * 2,
        )

    entities = list_entities(path)
    assert {(e["session"], e["task"], e["run"]) for e in entities} == {
        ("001", "a", "1"), ("001", "b", None),
    }

    loaded = load_run(path, "ses-001/ses-001_task-a_run-1_timeseries")
    assert np.array_equal(loaded, array)
    assert loaded.dtype == np.float32
