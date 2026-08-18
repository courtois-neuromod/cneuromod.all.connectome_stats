"""Tests for analysis/qc_join.py."""

import pandas as pd

from analysis.qc_join import (
    aggregate_session_qc,
    join_network_tsnr,
    join_run_qc,
    normalize_entities,
)


def _write_qc_table(root, dataset, rows):
    path = root / "output_data" / "tables" / f"{dataset}.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)


def _write_atlas_tsnr_table(root, dataset, rows):
    path = root / "output_data" / "tables" / "atlas_tsnr" / f"{dataset}.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, sep="\t", index=False)


def test_normalize_entities_pads_session_and_strips_prefixes():
    frame = pd.DataFrame({
        "dataset": ["things"], "subject": ["sub-01"], "session": ["ses-1"],
        "task": ["things"], "run": ["run-1"],
    })
    normalized = normalize_entities(frame)
    assert normalized.loc[0, "subject"] == "01"
    assert normalized.loc[0, "session"] == "001"
    assert normalized.loc[0, "run"] == "1"


def test_normalize_entities_strips_float_like_run():
    """qa_figures exports run as a float-like string ("1.0") for some
    subject/session combinations even in datasets CONTENT.md documents as
    blank-run (e.g. movie10) — the join must not be fooled by the ".0"."""
    frame = pd.DataFrame({
        "dataset": ["movie10"], "subject": ["02"], "session": ["001"],
        "task": ["life01"], "run": ["1.0"],
    })
    assert normalize_entities(frame).loc[0, "run"] == "1"


def test_normalize_entities_blank_run_stays_blank():
    frame = pd.DataFrame({
        "dataset": ["movie10"], "subject": ["01"], "session": ["001"],
        "task": ["life01"], "run": [None],
    })
    normalized = normalize_entities(frame)
    assert normalized.loc[0, "run"] == ""


def test_join_run_qc_matches_and_flags_unmatched(tmp_path):
    _write_qc_table(tmp_path, "things", [
        {"dataset": "things", "subject": "01", "session": "01", "task": "things",
         "run": "1", "fd_mean": 0.1, "fd_num": 2, "fd_perc": 1.0,
         "fd_prop_gt02": 0.0, "fd_prop_gt05": 0.0, "tsnr": 30.0},
    ])
    entities = pd.DataFrame([
        {"dataset": "things", "subject": "01", "session": "001", "task": "things", "run": "1"},
        {"dataset": "things", "subject": "01", "session": "001", "task": "things", "run": "2"},
    ])
    joined = join_run_qc(entities, tmp_path, datasets=["things"])

    assert joined.loc[0, "qc_matched"]
    assert joined.loc[0, "fd_mean"] == 0.1
    assert not joined.loc[1, "qc_matched"]
    assert pd.isna(joined.loc[1, "fd_mean"])


def test_join_run_qc_tolerates_empty_table(tmp_path):
    entities = pd.DataFrame([
        {"dataset": "mario", "subject": "01", "session": "001", "task": "mario", "run": ""},
    ])
    joined = join_run_qc(entities, tmp_path, datasets=["mario"])
    assert not joined.loc[0, "qc_matched"]
    assert pd.isna(joined.loc[0, "fd_mean"])


def test_join_network_tsnr_pools_subcortex_by_n_parcels(tmp_path):
    _write_atlas_tsnr_table(tmp_path, "things", [
        {"group": "cortex_Vis", "tsnr_mean": 40.0, "n_parcels": 162,
         "dataset": "things", "subject": "01", "session": "01", "task": "things", "run": "1"},
        {"group": "subcortex_PUT", "tsnr_mean": 10.0, "n_parcels": 8,
         "dataset": "things", "subject": "01", "session": "01", "task": "things", "run": "1"},
        {"group": "subcortex_THA", "tsnr_mean": 20.0, "n_parcels": 14,
         "dataset": "things", "subject": "01", "session": "01", "task": "things", "run": "1"},
    ])
    entities = pd.DataFrame([
        {"dataset": "things", "subject": "01", "session": "001", "task": "things", "run": "1"},
    ])
    joined = join_network_tsnr(entities, tmp_path, ["Vis", "subcortex"], datasets=["things"])

    assert joined.loc[0, "tsnr_Vis"] == 40.0
    expected_subcortex = (10.0 * 8 + 20.0 * 14) / (8 + 14)
    assert abs(joined.loc[0, "tsnr_subcortex"] - expected_subcortex) < 1e-9


def test_join_network_tsnr_nan_when_unmatched(tmp_path):
    entities = pd.DataFrame([
        {"dataset": "mario", "subject": "01", "session": "001", "task": "mario", "run": ""},
    ])
    joined = join_network_tsnr(entities, tmp_path, ["Vis"], datasets=["mario"])
    assert pd.isna(joined.loc[0, "tsnr_Vis"])


def test_aggregate_session_qc_is_volume_weighted():
    run_qc = pd.DataFrame([
        {"dataset": "things", "subject": "01", "session": "001", "n_volumes": 100,
         "fd_mean": 0.1, "fd_num": 5, "qc_matched": True},
        {"dataset": "things", "subject": "01", "session": "001", "n_volumes": 300,
         "fd_mean": 0.3, "fd_num": 15, "qc_matched": True},
    ])
    session = aggregate_session_qc(run_qc, tr_seconds=1.5, value_columns=["fd_mean"])
    expected_fd_mean = (0.1 * 100 + 0.3 * 300) / 400
    assert abs(session.loc[0, "fd_mean"] - expected_fd_mean) < 1e-9
    assert session.loc[0, "n_volumes"] == 400
    assert session.loc[0, "duration_sec"] == 400 * 1.5
    assert session.loc[0, "usable_duration_sec"] == 400 * 1.5 - 20 * 1.5
