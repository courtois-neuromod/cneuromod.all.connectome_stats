"""Tests for analysis/inventory_summary.py — the rollups of asset_inventory's
per-run table into session/subject/dataset/gap tables."""

import pandas as pd

from analysis.inventory_summary import (
    inventory_gaps,
    summarize_datasets,
    summarize_sessions,
    summarize_subjects,
)


def _raw_row(dataset="d", subject="01", session="001", task="t", run="1", n_volumes=10):
    return {"dataset": dataset, "subject": subject, "session": session, "task": task,
            "run": run, "n_volumes": n_volumes, "tr_seconds": 1.49,
            "duration_sec": n_volumes * 1.49}


def test_summarize_sessions_without_connectome_index():
    run_inventory = pd.DataFrame([
        {**_raw_row(session="001"), "in_timeseries": True, "in_qc": True, "match_level": "exact"},
        {**_raw_row(session="001", run="2"), "in_timeseries": False, "in_qc": False,
         "match_level": "unmatched"},
    ])
    sessions = summarize_sessions(run_inventory)
    assert len(sessions) == 1
    row = sessions.iloc[0]
    assert row["n_raw_runs"] == 2
    assert row["n_timeseries_runs"] == 1
    assert not row["has_connectome"]


def test_summarize_sessions_with_connectome_index_and_gate():
    run_inventory = pd.DataFrame([
        {**_raw_row(session="001"), "in_timeseries": True, "in_qc": True, "match_level": "exact"},
    ])
    connectome_index = pd.DataFrame([
        {"dataset": "d", "subject": "01", "session": "001",
         "duration_sec": 2000.0, "usable_duration_sec": 1900.0},
    ])
    sessions = summarize_sessions(run_inventory, connectome_index, min_usable_seconds=1800)
    row = sessions.iloc[0]
    assert row["has_connectome"]
    assert row["passes_gate"]


def test_summarize_subjects_rolls_up_sessions():
    run_inventory = pd.DataFrame([
        {**_raw_row(session="001"), "in_timeseries": True, "in_qc": True, "match_level": "exact"},
        {**_raw_row(session="002"), "in_timeseries": True, "in_qc": True, "match_level": "exact"},
    ])
    subjects = summarize_subjects(run_inventory)
    assert len(subjects) == 1
    assert subjects.iloc[0]["n_sessions"] == 2
    assert subjects.iloc[0]["n_raw_runs"] == 2


def test_summarize_datasets_and_gaps_flag_missing_assets(tmp_path):
    run_inventory = pd.DataFrame([
        {**_raw_row(dataset="mario3"), "in_timeseries": False, "in_qc": False,
         "match_level": "unmatched"},
    ])
    dataset_status = [{"dataset": "mario3", "subject": "01",
                        "registered": True, "content_present": False}]
    coverage = summarize_datasets(run_inventory, dataset_status, connectome_dir=tmp_path,
                                   parcellation="cneuromod2026", qa_root=None)
    row = coverage.iloc[0]
    assert row["timeseries_registered"]
    assert row["timeseries_content_subjects"] == 0
    assert not row["connectome_file_present"]

    gaps = inventory_gaps(run_inventory, coverage)
    reasons = set(gaps["reason"])
    assert "timeseries_content_missing" in reasons
    assert "no_connectome_file" in reasons
    assert "unmatched_entities" in reasons
