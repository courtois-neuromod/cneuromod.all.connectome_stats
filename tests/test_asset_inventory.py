"""Tests for analysis/bids_inventory.py and analysis/asset_inventory.py.

Offline, synthetic `tmp_path` trees, in the style of tests/test_qc_join.py.
Covers each entity-join hazard CLAUDE.md documents by name: zero-padded vs.
bare run, absent run entity, session-less layout, `_part-`/`_echo-` dedupe,
and each `match_level` tier.
"""

import json

import pandas as pd

from analysis.asset_inventory import _tiered_join, dataset_universe, join_inventory
from analysis.bids_inventory import canonical_run, list_raw_runs


def _write_bold(bids_dir, subject, session, task, run=None, part=None, echo=None,
                 n_volumes=10, tr=1.49):
    entities = f"sub-{subject}"
    if session:
        entities += f"_ses-{session}"
    entities += f"_task-{task}"
    if run is not None:
        entities += f"_run-{run}"
    if echo is not None:
        entities += f"_echo-{echo}"
    if part is not None:
        entities += f"_part-{part}"
    entities += "_bold"

    func_dir = bids_dir / f"sub-{subject}"
    if session:
        func_dir = func_dir / f"ses-{session}"
    func_dir = func_dir / "func"
    func_dir.mkdir(parents=True, exist_ok=True)

    (func_dir / f"{entities}.nii.gz").write_bytes(b"")
    sidecar = {"RepetitionTime": tr,
               "time": {"samples": {"AcquisitionNumber": list(range(n_volumes))}}}
    (func_dir / f"{entities}.json").write_text(json.dumps(sidecar))


# --------------------------------------------------------------------------- #
# canonical_run
# --------------------------------------------------------------------------- #
def test_canonical_run_normalizes_zero_padded_bare_and_float_like():
    assert canonical_run("01") == "1"
    assert canonical_run("1") == "1"
    assert canonical_run("1.0") == "1"
    assert canonical_run("run-01") == "1"
    assert canonical_run(None) == ""
    assert canonical_run("") == ""


# --------------------------------------------------------------------------- #
# list_raw_runs
# --------------------------------------------------------------------------- #
def test_list_raw_runs_session_organized_layout(tmp_path):
    bids_dir = tmp_path / "movie10" / "bids"
    _write_bold(bids_dir, "01", "004", "wolf07", run=None, n_volumes=20)
    frame = list_raw_runs(tmp_path, "movie10")
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["subject"] == "01"
    assert row["session"] == "004"
    assert row["task"] == "wolf07"
    assert row["run"] == ""
    assert row["n_volumes"] == 20


def test_list_raw_runs_session_less_layout(tmp_path):
    """harrypotter's raw layout has no `ses-` component at all."""
    bids_dir = tmp_path / "harrypotter" / "bids"
    _write_bold(bids_dir, "01", None, "harrypotter", run="03")
    frame = list_raw_runs(tmp_path, "harrypotter")
    assert len(frame) == 1
    row = frame.iloc[0]
    assert row["session"] == ""
    assert row["run"] == "3"


def test_list_raw_runs_dedupes_part_and_echo(tmp_path):
    """mario's `_part-mag`/`_part-phase` and emotion-videos' `_echo-*` are one
    run split across multiple files — must collapse to a single row."""
    bids_dir = tmp_path / "mario" / "bids"
    _write_bold(bids_dir, "05", "017", "mario", run="03", part="mag")
    _write_bold(bids_dir, "05", "017", "mario", run="03", part="phase")
    frame = list_raw_runs(tmp_path, "mario")
    assert len(frame) == 1
    assert frame.iloc[0]["run"] == "3"


def test_list_raw_runs_missing_bids_dir_returns_empty(tmp_path):
    frame = list_raw_runs(tmp_path, "nonexistent")
    assert frame.empty


# --------------------------------------------------------------------------- #
# _tiered_join / join_inventory — one case per match_level
# --------------------------------------------------------------------------- #
def _raw_row(dataset="d", subject="01", session="001", task="t", run="1", n_volumes=10):
    return {"dataset": dataset, "subject": subject, "session": session, "task": task,
            "run": run, "n_volumes": n_volumes, "tr_seconds": 1.49,
            "duration_sec": n_volumes * 1.49}


def test_tiered_join_exact_match():
    raw = pd.DataFrame([_raw_row(run="01")])
    other = pd.DataFrame([{"dataset": "d", "subject": "01", "session": "001",
                            "task": "t", "run": "1"}])
    matched, levels = _tiered_join(raw, other)
    assert matched[0]
    assert levels[0] == "exact"


def test_tiered_join_no_run_tier_movie10_style():
    """movie10: raw carries no run entity, h5 always synthesizes run="1" —
    unique on (dataset, subject, session, task) on both sides."""
    raw = pd.DataFrame([_raw_row(task="bourne01", run="")])
    other = pd.DataFrame([{"dataset": "d", "subject": "01", "session": "001",
                            "task": "bourne01", "run": "1"}])
    matched, levels = _tiered_join(raw, other)
    assert matched[0]
    assert levels[0] == "no_run"


def test_tiered_join_no_session_tier_session_less_layout():
    """harrypotter: raw has no session, h5 synthesizes ses-001 — matched on
    (dataset, subject, task, run) instead."""
    raw = pd.DataFrame([_raw_row(session="", run="03")])
    other = pd.DataFrame([{"dataset": "d", "subject": "01", "session": "001",
                            "task": "t", "run": "3"}])
    matched, levels = _tiered_join(raw, other)
    assert matched[0]
    assert levels[0] == "no_session"


def test_tiered_join_unmatched_when_no_tier_resolves():
    raw = pd.DataFrame([_raw_row(task="orphan")])
    other = pd.DataFrame([{"dataset": "d", "subject": "01", "session": "001",
                            "task": "other", "run": "1"}])
    matched, levels = _tiered_join(raw, other)
    assert not matched[0]
    assert levels[0] == "unmatched"


def test_tiered_join_ambiguous_key_falls_through_to_next_tier():
    """Two raw runs share (session, task) with different run values; the h5
    side only has one entity at that (session, task) — no_run must NOT claim
    it (ambiguous on the raw side), so the unique run keeps its exact match
    while the ambiguous one stays unmatched."""
    raw = pd.DataFrame([_raw_row(run="1"), _raw_row(run="2")])
    other = pd.DataFrame([{"dataset": "d", "subject": "01", "session": "001",
                            "task": "t", "run": "1"}])
    matched, levels = _tiered_join(raw, other)
    assert matched[0] and levels[0] == "exact"
    assert not matched[1]


def test_join_inventory_adds_in_qc_independently_of_timeseries():
    raw = pd.DataFrame([_raw_row()])
    timeseries = pd.DataFrame(columns=["dataset", "subject", "session", "task", "run"])
    qc = pd.DataFrame([{"dataset": "d", "subject": "01", "session": "001",
                         "task": "t", "run": "1"}])
    result = join_inventory(raw, timeseries, qc)
    assert not result.loc[0, "in_timeseries"]
    assert result.loc[0, "match_level"] == "unmatched"
    assert result.loc[0, "in_qc"]


def test_dataset_universe_excludes_non_functional(tmp_path):
    (tmp_path / "anat" / "bids").mkdir(parents=True)
    (tmp_path / "movie10" / "bids").mkdir(parents=True)
    (tmp_path / "friends" / "timeseries").mkdir(parents=True)
    names = dataset_universe(tmp_path)
    assert names == ["friends", "movie10"]
