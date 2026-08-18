"""Tests for analysis/motion_strata.py, offline against synthetic fixtures."""

import numpy as np
import pandas as pd

from analysis.connectome_store import write_dataset_connectomes
from analysis.motion_strata import (
    MOTION_SPLITS,
    assign_motion_strata,
    motion_balance,
    motion_pair_bin_labels,
    motion_pair_bins,
    motion_permutation,
    motion_sessions_table,
    motion_summary,
    qc_covered_mask,
)


def test_qc_covered_mask_requires_gate_and_fd_mean():
    index_frame = pd.DataFrame({
        "usable_duration_sec": [2000.0, 100.0, 2000.0, np.nan],
        "duration_sec": [2000.0, 100.0, 2000.0, 2000.0],
        "fd_mean": [0.1, 0.1, np.nan, 0.1],
    })
    mask = qc_covered_mask(index_frame, min_usable_seconds=1800)
    assert list(mask) == [True, False, False, True]


def test_assign_motion_strata_splits_on_group_median():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 6,
        "dataset": ["friends"] * 6,
        "fd_mean": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
    })
    result = assign_motion_strata(index_frame, split_by=("subject", "dataset"), min_cell=4)
    # median = 0.175 -> three <=median are "low", three >median are "high".
    assert list(result["motion_stratum"]) == ["low", "low", "low", "high", "high", "high"]


def test_assign_motion_strata_drops_cells_below_min_cell():
    index_frame = pd.DataFrame({
        "subject": ["01", "01", "01", "02", "02", "02", "02"],
        "dataset": ["friends"] * 7,
        "fd_mean": [0.1, 0.2, 0.3, 0.1, 0.2, 0.3, 0.4],
    })
    result = assign_motion_strata(index_frame, split_by=("subject", "dataset"), min_cell=4)
    # sub-01 has only 3 covered sessions (< min_cell=4) -> all NaN.
    assert result.loc[result["subject"] == "01", "motion_stratum"].isna().all()
    # sub-02 has 4 -> stratified.
    assert result.loc[result["subject"] == "02", "motion_stratum"].notna().all()


def test_assign_motion_strata_leaves_missing_fd_mean_unassigned():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 5,
        "dataset": ["friends"] * 5,
        "fd_mean": [0.1, 0.2, 0.3, 0.4, np.nan],
    })
    result = assign_motion_strata(index_frame, split_by=("subject", "dataset"), min_cell=4)
    assert result["motion_stratum"].iloc[-1] is None
    assert result["motion_stratum"].iloc[:4].notna().all()


def test_motion_pair_bin_labels_has_six_entries():
    labels = motion_pair_bin_labels()
    assert len(labels) == 6
    assert set(labels) == {
        "low-low/within-task", "low-low/between-task",
        "low-high/within-task", "low-high/between-task",
        "high-high/within-task", "high-high/between-task",
    }


def test_motion_pair_bins_restricted_to_within_subject_pairs():
    index_frame = pd.DataFrame({
        "subject": ["01", "01", "02"],
        "dataset": ["friends", "movie10", "friends"],
        "motion_stratum": ["low", "high", "low"],
    })
    labels, triu_mask = motion_pair_bins(index_frame)
    # Pair (0,1): within-subject, different dataset, low/high -> low-high/between-task.
    assert labels[0, 1] == "low-high/between-task"
    # Pair (0,2) and (1,2): between-subject -> excluded from triu_mask.
    assert not triu_mask[0, 2]
    assert not triu_mask[1, 2]
    assert triu_mask[0, 1]
    assert triu_mask.sum() == 1


def _write_connectome(path, dataset, subjects, sessions, fd_mean, tsnr=None,
                       usable=None, duration=None, n_edges=3, parcellation="cneuromod2026", seed=0):
    n_entities = len(subjects)
    usable = usable if usable is not None else [3600.0] * n_entities
    duration = duration if duration is not None else usable
    tsnr = tsnr if tsnr is not None else [50.0] * n_entities
    index = pd.DataFrame({
        "level": ["session"] * n_entities,
        "dataset": [dataset] * n_entities,
        "subject": subjects,
        "session": sessions,
        "usable_duration_sec": usable,
        "duration_sec": duration,
        "fd_mean": fd_mean,
        "tsnr": tsnr,
    })
    networks = {"A": np.array([0, 1, 2])}
    edges = {"A": np.array([[1, 0], [2, 0], [2, 1]])[:n_edges]}
    rng = np.random.default_rng(seed)
    measures = {"pearson": {"A": rng.normal(size=(n_entities, n_edges)).astype(np.float32)}}
    diagnostics = {"pearson": {"A": np.ones((n_entities, 6), dtype=np.float32)}}
    write_dataset_connectomes(
        path, index, networks, edges, measures, diagnostics,
        parcellation=parcellation, tr_seconds=1.5, labels_checksum="abc",
    )


def _synthetic_paths(tmp_path, n_per_subject=6):
    """One dataset per subject-pair-of-sessions layout: 3 subjects x 6 sessions each,
    fd_mean spanning a clean low/high split within each (subject, dataset) cell.
    """
    connectome_dir = tmp_path / "connectomes"
    connectome_dir.mkdir()
    subjects, sessions, fd_means = [], [], []
    for subject in ("01", "02", "03"):
        for session_index in range(n_per_subject):
            subjects.append(subject)
            sessions.append(f"{session_index + 1:03d}")
            fd_means.append(0.05 + 0.02 * session_index)
    path = connectome_dir / "friends_cneuromod2026.h5"
    _write_connectome(path, "friends", subjects, sessions, fd_means)
    return [path]


def test_motion_summary_returns_six_bins_per_network_per_split():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        paths = _synthetic_paths(Path(tmp))
        result = motion_summary(paths, ["A"], "pearson", min_usable_seconds=100)

    bins = result["motion_bins"]
    assert set(bins["split"]) == {"cell", "subject"}
    for split in ("cell", "subject"):
        split_bins = bins[bins["split"] == split]
        assert set(split_bins["bin"]) == set(motion_pair_bin_labels())
    assert set(result["histograms"]["analysis"]) == {"motion"}


def test_motion_summary_skips_when_too_few_sessions():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "friends_cneuromod2026.h5"
        _write_connectome(path, "friends", ["01"], ["001"], fd_mean=[0.1])
        result = motion_summary([path], ["A"], "pearson", min_usable_seconds=100)

    assert len(result["motion_bins"]) == 0
    assert len(result["histograms"]) == 0


def test_motion_balance_reports_pair_min_duration_and_tsnr():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 8,
        "dataset": ["friends"] * 8,
        "fd_mean": [0.05, 0.06, 0.07, 0.08, 0.20, 0.21, 0.22, 0.23],
        "usable_duration_sec": [2000.0, 2100.0, 2200.0, 2300.0, 2000.0, 2100.0, 2200.0, 2300.0],
        "duration_sec": [2000.0, 2100.0, 2200.0, 2300.0, 2000.0, 2100.0, 2200.0, 2300.0],
        "tsnr": [60.0, 61.0, 62.0, 63.0, 40.0, 41.0, 42.0, 43.0],
    })
    result = motion_balance(index_frame, min_usable_seconds=100, splits=(MOTION_SPLITS[0],))
    assert set(result["bin"]) == set(motion_pair_bin_labels())
    assert (result["n_pairs"] >= 0).all()
    low_low = result[result["bin"] == "low-low/within-task"]
    high_high = result[result["bin"] == "high-high/within-task"]
    assert low_low["median_min_tsnr"].iloc[0] > high_high["median_min_tsnr"].iloc[0]


def test_motion_permutation_returns_one_row_per_network_with_valid_p():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        paths = _synthetic_paths(Path(tmp))
        result = motion_permutation(
            paths, ["A"], "pearson", min_usable_seconds=100, n_permutations=50, seed=0,
        )

    assert len(result) == 1
    row = result.iloc[0]
    assert row["network"] == "A"
    assert row["n_permutations"] == 50
    assert 0.0 <= row["p_value"] <= 1.0
    assert 0 <= row["n_subjects_replicating"] <= row["n_subjects_total"]
    assert row["n_subjects_total"] == 3  # all 3 synthetic subjects have both bins populated


def test_motion_permutation_handles_too_few_sessions():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "friends_cneuromod2026.h5"
        _write_connectome(path, "friends", ["01"], ["001"], fd_mean=[0.1])
        result = motion_permutation([path], ["A"], "pearson", min_usable_seconds=100)

    assert len(result) == 1
    assert np.isnan(result.iloc[0]["observed_diff"])
    assert np.isnan(result.iloc[0]["p_value"])
    assert result.iloc[0]["n_subjects_total"] == 0


def test_motion_sessions_table_has_one_column_per_split():
    index_frame = pd.DataFrame({
        "dataset": ["friends"] * 8,
        "subject": ["01"] * 8,
        "session": [f"{i:03d}" for i in range(8)],
        "fd_mean": [0.05, 0.06, 0.07, 0.08, 0.20, 0.21, 0.22, 0.23],
        "tsnr": [50.0] * 8,
        "usable_duration_sec": [2000.0] * 8,
        "duration_sec": [2000.0] * 8,
    })
    result = motion_sessions_table(index_frame, min_usable_seconds=100)
    assert "motion_stratum_cell" in result.columns
    assert "motion_stratum_subject" in result.columns
    assert len(result) == 8
