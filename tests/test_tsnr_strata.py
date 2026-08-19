"""Tests for analysis/tsnr_strata.py, offline against synthetic fixtures.

Follows tests/test_motion_strata.py's two fixture patterns: plain in-memory
frames for the pure functions, real h5 files for the path-taking ones.
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.connectome_store import write_dataset_connectomes
from analysis.tsnr_strata import (
    TSNR_SPLITS,
    assign_tsnr_strata,
    qc_covered_mask,
    tsnr_balance,
    tsnr_pair_bin_labels,
    tsnr_pair_bins,
    tsnr_permutation,
    tsnr_sessions_table,
    tsnr_summary,
)

DEFINITIONS = ("raw", "fd_residual")


def _write_connectome(path, dataset, subjects, sessions, fd_mean, tsnr=None,
                      usable=None, duration=None, n_edges=3,
                      parcellation="cneuromod2026", seed=0):
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
    """3 subjects x 6 sessions, with tSNR spanning a clean split within each
    (subject, dataset) cell and fd_mean varying independently of it, so the
    `raw` and `fd_residual` definitions are both well defined.
    """
    connectome_dir = tmp_path / "connectomes"
    connectome_dir.mkdir()
    subjects, sessions, fd_means, tsnrs = [], [], [], []
    for subject in ("01", "02", "03"):
        for session_index in range(n_per_subject):
            subjects.append(subject)
            sessions.append(f"{session_index + 1:03d}")
            fd_means.append(0.05 + 0.02 * session_index)
            tsnrs.append(60.0 - 3.0 * session_index + (2.0 if session_index % 2 else -2.0))
    path = connectome_dir / "friends_cneuromod2026.h5"
    _write_connectome(path, "friends", subjects, sessions, fd_means, tsnr=tsnrs)
    return [path]


def test_qc_covered_population_is_keyed_on_fd_mean_not_tsnr():
    # The tSNR analysis deliberately shares the motion analysis's population
    # definition, so a session with tSNR but no fd_mean stays uncovered.
    index_frame = pd.DataFrame({
        "usable_duration_sec": [2000.0, 2000.0],
        "duration_sec": [2000.0, 2000.0],
        "fd_mean": [0.1, np.nan],
        "tsnr": [40.0, 40.0],
    })
    assert list(qc_covered_mask(index_frame, 1800)) == [True, False]


def test_assign_tsnr_strata_splits_high_above_the_median():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 6,
        "dataset": ["friends"] * 6,
        "tsnr": [35.0, 40.0, 45.0, 50.0, 55.0, 60.0],
    })
    result = assign_tsnr_strata(index_frame)
    assert list(result["tsnr_stratum"]) == ["low", "low", "low", "high", "high", "high"]


def test_assign_tsnr_strata_residual_differs_from_raw_when_motion_drives_tsnr():
    fd_mean = np.array([0.05, 0.10, 0.15, 0.20, 0.25, 0.30])
    wobble = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    index_frame = pd.DataFrame({
        "subject": ["01"] * 6,
        "dataset": ["friends"] * 6,
        "fd_mean": fd_mean,
        "tsnr": 100.0 - 200.0 * fd_mean + wobble,
    })
    raw = assign_tsnr_strata(index_frame)["tsnr_stratum"]
    residual = assign_tsnr_strata(index_frame, residualize_on="fd_mean")["tsnr_stratum"]
    assert list(raw) == ["high", "high", "high", "low", "low", "low"]
    assert list(residual) == ["high", "low", "high", "low", "high", "low"]


def test_tsnr_pair_bin_labels_lead_with_the_good_pairing():
    labels = tsnr_pair_bin_labels()
    assert labels[0] == "high-high/within-task"
    assert set(labels) == {
        "low-low/within-task", "low-low/between-task",
        "low-high/within-task", "low-high/between-task",
        "high-high/within-task", "high-high/between-task",
    }


def test_tsnr_pair_bins_restricted_to_within_subject_pairs():
    index_frame = pd.DataFrame({
        "subject": ["01", "01", "02"],
        "dataset": ["friends", "movie10", "friends"],
        "tsnr_stratum": ["high", "high", "low"],
    })
    labels, triu_mask = tsnr_pair_bins(index_frame)
    assert labels[0, 1] == "high-high/between-task"
    assert not triu_mask[0, 2]
    assert not triu_mask[1, 2]
    assert triu_mask.sum() == 1


def test_tsnr_summary_covers_every_definition_and_split():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _synthetic_paths(Path(tmp))
        result = tsnr_summary(paths, ["A"], "pearson", min_usable_seconds=100)

    bins = result["tsnr_bins"]
    assert set(bins["stratum_def"]) == set(DEFINITIONS)
    assert set(bins["split"]) == {"cell", "subject"}
    for definition in DEFINITIONS:
        for split in ("cell", "subject"):
            subset = bins[(bins["stratum_def"] == definition) & (bins["split"] == split)]
            assert set(subset["bin"]) == set(tsnr_pair_bin_labels())
    assert set(result["histograms"]["analysis"]) == {"tsnr"}
    assert set(result["histograms"]["stratum_def"]) == set(DEFINITIONS)


def test_tsnr_summary_skips_when_too_few_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "friends_cneuromod2026.h5"
        _write_connectome(path, "friends", ["01"], ["001"], fd_mean=[0.1])
        result = tsnr_summary([path], ["A"], "pearson", min_usable_seconds=100)

    assert len(result["tsnr_bins"]) == 0
    assert len(result["histograms"]) == 0
    assert "stratum_def" in result["tsnr_bins"].columns


def test_tsnr_balance_reports_duration_tsnr_and_the_motion_confound():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 8,
        "dataset": ["friends"] * 8,
        "fd_mean": [0.20, 0.21, 0.22, 0.23, 0.05, 0.06, 0.07, 0.08],
        "usable_duration_sec": [2000.0, 2100.0, 2200.0, 2300.0] * 2,
        "duration_sec": [2000.0, 2100.0, 2200.0, 2300.0] * 2,
        "tsnr": [40.0, 41.0, 42.0, 43.0, 60.0, 61.0, 62.0, 63.0],
    })
    result = tsnr_balance(index_frame, min_usable_seconds=100, splits=(TSNR_SPLITS[0],))
    assert set(result["stratum_def"]) == set(DEFINITIONS)
    for column in ("median_min_duration_sec", "median_min_tsnr", "median_max_fd_mean"):
        assert column in result.columns

    raw = result[result["stratum_def"] == "raw"].set_index("bin")
    # High-tSNR pairs are the good end on both axes here, by construction.
    assert (raw.loc["high-high/within-task", "median_min_tsnr"]
            > raw.loc["low-low/within-task", "median_min_tsnr"])
    assert (raw.loc["high-high/within-task", "median_max_fd_mean"]
            < raw.loc["low-low/within-task", "median_max_fd_mean"])


def test_tsnr_permutation_returns_one_row_per_network_and_definition():
    with tempfile.TemporaryDirectory() as tmp:
        paths = _synthetic_paths(Path(tmp))
        result = tsnr_permutation(
            paths, ["A"], "pearson", min_usable_seconds=100, n_permutations=50, seed=0,
        )

    assert len(result) == 2
    assert list(result["stratum_def"]) == list(DEFINITIONS)
    for _, row in result.iterrows():
        assert row["network"] == "A"
        assert row["n_permutations"] == 50
        assert 0.0 <= row["p_value"] <= 1.0
        assert 0 <= row["n_subjects_replicating"] <= row["n_subjects_total"]
        assert row["n_subjects_total"] == 3


def test_tsnr_permutation_handles_too_few_sessions():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "friends_cneuromod2026.h5"
        _write_connectome(path, "friends", ["01"], ["001"], fd_mean=[0.1])
        result = tsnr_permutation([path], ["A"], "pearson", min_usable_seconds=100)

    assert len(result) == 2
    assert result["observed_diff"].isna().all()
    assert (result["n_subjects_total"] == 0).all()


def test_tsnr_sessions_table_has_one_column_per_split_and_definition():
    index_frame = pd.DataFrame({
        "dataset": ["friends"] * 8,
        "subject": ["01"] * 8,
        "session": [f"{i:03d}" for i in range(8)],
        "fd_mean": [0.05, 0.06, 0.07, 0.08, 0.20, 0.21, 0.22, 0.23],
        "tsnr": [60.0, 61.0, 62.0, 63.0, 40.0, 41.0, 42.0, 43.0],
        "usable_duration_sec": [2000.0] * 8,
        "duration_sec": [2000.0] * 8,
    })
    result = tsnr_sessions_table(index_frame, min_usable_seconds=100)
    assert len(result) == 8
    for split in ("cell", "subject"):
        for definition in DEFINITIONS:
            assert f"tsnr_stratum_{split}_{definition}" in result.columns
