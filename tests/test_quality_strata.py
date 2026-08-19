"""Tests for analysis/quality_strata.py — the QC-column-parameterized core
shared by the motion and tSNR robustness checks. Offline, synthetic fixtures.
"""

import numpy as np
import pandas as pd

from analysis.quality_strata import (
    _cell_residuals,
    assign_strata,
    pair_bin_labels,
    pair_bins,
    qc_covered_mask,
    sessions_table,
    stratum_pair_names,
)


def test_qc_covered_mask_honours_the_column_argument():
    index_frame = pd.DataFrame({
        "usable_duration_sec": [2000.0, 2000.0, 100.0],
        "duration_sec": [2000.0, 2000.0, 100.0],
        "fd_mean": [0.1, np.nan, 0.1],
        "tsnr": [np.nan, 40.0, 40.0],
    })
    assert list(qc_covered_mask(index_frame, 1800, column="fd_mean")) == [True, False, False]
    assert list(qc_covered_mask(index_frame, 1800, column="tsnr")) == [False, True, False]


def test_qc_covered_mask_is_all_false_when_column_absent():
    index_frame = pd.DataFrame({
        "usable_duration_sec": [2000.0, 2000.0],
        "duration_sec": [2000.0, 2000.0],
    })
    assert not qc_covered_mask(index_frame, 1800, column="tsnr").any()


def test_assign_strata_splits_either_direction_on_the_same_data():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 6,
        "dataset": ["friends"] * 6,
        "fd_mean": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
        "tsnr": [60.0, 55.0, 50.0, 45.0, 40.0, 35.0],
    })
    motion = assign_strata(index_frame, "fd_mean", "motion_stratum")
    tsnr = assign_strata(index_frame, "tsnr", "tsnr_stratum")
    # Both label by the *value* (low/high), not by quality — so a perfectly
    # anti-correlated pair of columns yields exactly mirrored labels.
    assert list(motion["motion_stratum"]) == ["low", "low", "low", "high", "high", "high"]
    assert list(tsnr["tsnr_stratum"]) == ["high", "high", "high", "low", "low", "low"]


def test_assign_strata_residualizes_within_the_cell():
    # tsnr is an exact linear function of fd_mean plus an alternating wobble;
    # residualizing on fd_mean must recover the wobble, not the trend.
    fd_mean = np.array([0.05, 0.10, 0.15, 0.20, 0.25, 0.30])
    wobble = np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0])
    index_frame = pd.DataFrame({
        "subject": ["01"] * 6,
        "dataset": ["friends"] * 6,
        "fd_mean": fd_mean,
        "tsnr": 100.0 - 200.0 * fd_mean + wobble,
    })
    raw = assign_strata(index_frame, "tsnr", "tsnr_stratum")
    residual = assign_strata(index_frame, "tsnr", "tsnr_stratum", residualize_on="fd_mean")
    assert list(raw["tsnr_stratum"]) == ["high", "high", "high", "low", "low", "low"]
    assert list(residual["tsnr_stratum"]) == ["high", "low", "high", "low", "high", "low"]


def test_assign_strata_residualization_falls_back_on_constant_predictor():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 4,
        "dataset": ["friends"] * 4,
        "fd_mean": [0.1, 0.1, 0.1, 0.1],
        "tsnr": [40.0, 45.0, 50.0, 55.0],
    })
    result = assign_strata(index_frame, "tsnr", "tsnr_stratum", residualize_on="fd_mean")
    # Mean-centering preserves the ordering, so the split matches the raw one.
    assert list(result["tsnr_stratum"]) == ["low", "low", "high", "high"]


def test_assign_strata_leaves_unassigned_when_predictor_column_absent():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 4,
        "dataset": ["friends"] * 4,
        "tsnr": [40.0, 45.0, 50.0, 55.0],
    })
    result = assign_strata(index_frame, "tsnr", "tsnr_stratum", residualize_on="fd_mean")
    assert result["tsnr_stratum"].isna().all()


def test_cell_residuals_removes_a_clean_linear_trend():
    predictor = np.array([1.0, 2.0, 3.0, 4.0])
    values = 3.0 * predictor + 7.0
    assert np.allclose(_cell_residuals(values, predictor), 0.0, atol=1e-9)


def test_cell_residuals_ignores_non_finite_entries():
    predictor = np.array([1.0, 2.0, 3.0, np.nan])
    values = np.array([2.0, 4.0, 6.0, 8.0])
    result = _cell_residuals(values, predictor)
    assert np.isnan(result[3])
    assert np.allclose(result[:3], 0.0, atol=1e-9)


def test_stratum_pair_names_puts_the_good_pairing_first():
    assert stratum_pair_names("low") == ("low-low", "low-high", "high-high")
    assert stratum_pair_names("high") == ("high-high", "low-high", "low-low")


def test_pair_bin_labels_order_follows_good_stratum():
    assert pair_bin_labels("low")[0] == "low-low/within-task"
    assert pair_bin_labels("high")[0] == "high-high/within-task"
    assert set(pair_bin_labels("low")) == set(pair_bin_labels("high"))


def test_pair_bins_label_the_same_pairs_whichever_stratum_is_good():
    index_frame = pd.DataFrame({
        "subject": ["01", "01", "01"],
        "dataset": ["friends", "friends", "movie10"],
        "tsnr_stratum": ["high", "high", "low"],
    })
    labels_good_high, triu = pair_bins(index_frame, "tsnr_stratum", good_stratum="high")
    labels_good_low, _ = pair_bins(index_frame, "tsnr_stratum", good_stratum="low")
    assert labels_good_high[0, 1] == "high-high/within-task"
    assert labels_good_high[0, 2] == "low-high/between-task"
    # `good_stratum` reorders the label list; it must not relabel any pair.
    assert (labels_good_high == labels_good_low).all()
    assert triu.sum() == 3


def test_sessions_table_names_columns_by_split_and_definition():
    index_frame = pd.DataFrame({
        "dataset": ["friends"] * 6,
        "subject": ["01"] * 6,
        "session": [f"{i:03d}" for i in range(6)],
        "fd_mean": [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
        "tsnr": [60.0, 55.0, 50.0, 45.0, 40.0, 35.0],
        "usable_duration_sec": [2000.0] * 6,
        "duration_sec": [2000.0] * 6,
    })
    unnamed = sessions_table(index_frame, 100, column="tsnr", stratum_column="tsnr_stratum")
    assert "tsnr_stratum_cell" in unnamed.columns
    assert not [c for c in unnamed.columns if c.endswith("_raw")]

    named = sessions_table(
        index_frame, 100, column="tsnr", stratum_column="tsnr_stratum",
        definitions=(("raw", None), ("fd_residual", "fd_mean")),
    )
    for split in ("cell", "subject"):
        for definition in ("raw", "fd_residual"):
            assert f"tsnr_stratum_{split}_{definition}" in named.columns
