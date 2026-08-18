"""Tests for analysis/group_stats.py, offline against synthetic fixtures."""

import h5py
import numpy as np
import pandas as pd

from analysis.connectome_store import write_dataset_connectomes
from analysis.group_stats import (
    DOMAIN_DATASETS,
    GATES,
    _gate_mask_for,
    cross_context_summary,
    domain_cross_context_summary,
    duration_balance,
    network_quality,
    similarity_histogram,
    usable_sessions,
)


def test_usable_sessions_gate_and_report():
    index_frame = pd.DataFrame({
        "dataset": ["floc", "floc", "movie10", "movie10"],
        "usable_duration_sec": [300.0, 700.0, np.nan, 900.0],
        "duration_sec": [400.0, 750.0, 1200.0, 950.0],
        "qc_matched": [True, True, False, True],
    })

    mask, report = usable_sessions(index_frame, min_usable_seconds=600)

    # floc: 300 < 600 (fail), 700 >= 600 (pass).
    # movie10 row 2: usable NaN -> falls back to duration_sec (1200) -> pass.
    assert list(mask) == [False, True, True, True]

    report = report.set_index("dataset")
    assert report.loc["floc", "n_sessions"] == 2
    assert report.loc["floc", "n_passing"] == 1
    assert report.loc["movie10", "n_passing"] == 2
    assert report.loc["movie10", "qc_coverage"] == 0.5


def test_usable_sessions_fallback_matches_duration_when_unmatched():
    index_frame = pd.DataFrame({
        "dataset": ["mario"],
        "usable_duration_sec": [np.nan],
        "duration_sec": [123.4],
        "qc_matched": [False],
    })
    mask, report = usable_sessions(index_frame, min_usable_seconds=100)
    assert mask[0]
    assert report.loc[0, "median_usable_duration_sec"] == 123.4


def test_network_quality_returns_zero_n_without_raising_on_all_nan():
    index_frame = pd.DataFrame({
        "dataset": ["floc", "floc"],
        "tsnr_Vis": [np.nan, np.nan],
        "tsnr_SomMot": [10.0, 20.0],
    })

    result = network_quality(index_frame, network_order=["Vis", "SomMot", "Missing"])
    result = result.set_index("network")

    assert result.loc["Vis", "n_tsnr"] == 0
    assert np.isnan(result.loc["Vis", "median_tsnr"])
    assert result.loc["SomMot", "n_tsnr"] == 2
    assert result.loc["SomMot", "median_tsnr"] == 15.0
    assert result.loc["Missing", "n_tsnr"] == 0
    assert result.loc["Missing", "datasets"] == ""


def test_similarity_histogram_counts_sum_to_input_length():
    values = np.array([-0.9, -0.1, 0.0, 0.5, 0.5, 0.99, np.nan])
    frame = similarity_histogram(values, bins=10)
    assert frame["count"].sum() == 6  # NaN dropped


def test_similarity_histogram_empty_input():
    frame = similarity_histogram(np.array([]), bins=10)
    assert len(frame) == 0
    assert list(frame.columns) == ["bin_left", "bin_right", "count"]


def test_gates_include_qc_covered_and_low_motion():
    assert GATES == ("all", "gated", "qc_covered", "low_motion")


def test_gate_mask_for_low_motion_is_subset_of_qc_covered():
    index_frame = pd.DataFrame({
        "subject": ["01"] * 8,
        "dataset": ["friends"] * 8,
        "usable_duration_sec": [2000.0] * 4 + [100.0] + [2000.0] * 3,
        "duration_sec": [2000.0] * 8,
        "fd_mean": [0.05, 0.06, 0.07, 0.08, 0.1, 0.20, 0.21, 0.22],
    })
    qc_mask = _gate_mask_for(index_frame, min_usable_seconds=1800, gate_name="qc_covered")
    low_motion_mask = _gate_mask_for(index_frame, min_usable_seconds=1800, gate_name="low_motion")

    # The 5th row fails the usable-duration gate -> excluded from qc_covered too.
    assert not qc_mask[4]
    assert (low_motion_mask <= qc_mask).all()
    assert low_motion_mask.sum() < qc_mask.sum()


def test_gate_mask_for_tolerates_missing_fd_mean_column():
    index_frame = pd.DataFrame({
        "subject": ["01", "01"],
        "dataset": ["friends", "friends"],
        "usable_duration_sec": [2000.0, 2000.0],
        "duration_sec": [2000.0, 2000.0],
    })
    assert not _gate_mask_for(index_frame, 1800, "qc_covered").any()
    assert not _gate_mask_for(index_frame, 1800, "low_motion").any()


def test_duration_balance_median_is_pairwise_minimum_not_mean():
    # 2 datasets, 2 subjects, mixed durations. sub-01/floc row 0 fails a 600s
    # gate; the other three pass.
    index_frame = pd.DataFrame({
        "subject": ["sub-01", "sub-01", "sub-01", "sub-02"],
        "dataset": ["floc", "floc", "movie10", "movie10"],
        "usable_duration_sec": [300.0, 700.0, 900.0, 800.0],
        "duration_sec": [400.0, 750.0, 950.0, 850.0],
    })

    result = duration_balance(index_frame, min_usable_seconds=600).set_index(["gate", "bin"])
    median_col = "median_min_duration_sec"

    # gate="all": all 4 sessions, 6 pairs.
    assert result.loc[("all", "within-subject / within-dataset"), median_col] == 300
    assert result.loc[("all", "within-subject / within-dataset"), "n_pairs"] == 1
    assert result.loc[("all", "within-subject / between-dataset"), median_col] == 500
    assert result.loc[("all", "within-subject / between-dataset"), "n_pairs"] == 2
    assert result.loc[("all", "between-subject / within-dataset"), median_col] == 800
    assert result.loc[("all", "between-subject / between-dataset"), median_col] == 500
    assert result.loc[("all",), "n_sessions"].iloc[0] == 4

    # gate="gated": the 300s session is dropped, leaving 3 sessions, 3 pairs —
    # the within-subject/within-dataset bin becomes empty since it needed the
    # dropped session's floc/floc pair.
    assert result.loc[("gated", "within-subject / within-dataset"), "n_pairs"] == 0
    assert np.isnan(result.loc[("gated", "within-subject / within-dataset"), median_col])
    assert result.loc[("gated", "within-subject / between-dataset"), median_col] == 700
    assert result.loc[("gated", "between-subject / within-dataset"), median_col] == 800
    assert result.loc[("gated", "between-subject / between-dataset"), median_col] == 700
    assert result.loc[("gated",), "n_sessions"].iloc[0] == 3


def test_duration_balance_fallback_matches_duration_when_unmatched():
    # sub-01/floc's usable_duration_sec is NaN; the pair-min for that session
    # must fall back to duration_sec (500), not be dropped or treated as 0.
    index_frame = pd.DataFrame({
        "subject": ["sub-01", "sub-01", "sub-02"],
        "dataset": ["floc", "movie10", "movie10"],
        "usable_duration_sec": [np.nan, 600.0, 700.0],
        "duration_sec": [500.0, 650.0, 750.0],
    })

    result = duration_balance(index_frame, min_usable_seconds=100).set_index(["gate", "bin"])

    assert result.loc[("all", "within-subject / between-dataset"), "median_min_duration_sec"] == 500


def test_duration_balance_custom_group_column_relabels_bins():
    index_frame = pd.DataFrame({
        "subject": ["sub-01", "sub-01", "sub-02"],
        "dataset": ["movie10", "movie10", "movie10"],
        "title": ["bourne", "wolf", "bourne"],
        "usable_duration_sec": [600.0, 700.0, 800.0],
        "duration_sec": [600.0, 700.0, 800.0],
    })

    result = duration_balance(index_frame, min_usable_seconds=100, group_column="title")

    assert set(result["bin"]) == {
        "within-subject / within-title", "within-subject / between-title",
        "between-subject / within-title", "between-subject / between-title",
    }


def _write_connectome(path, dataset, subjects, sessions, n_edges=3, usable=None,
                       duration=None, parcellation="cneuromod2026", seed=0):
    """One connectome file with a single network `A`, for `cross_context_summary`."""
    n_entities = len(subjects)
    usable = usable if usable is not None else [3600.0] * n_entities
    duration = duration if duration is not None else usable
    index = pd.DataFrame({
        "level": ["session"] * n_entities,
        "dataset": [dataset] * n_entities,
        "subject": subjects,
        "session": sessions,
        "usable_duration_sec": usable,
        "duration_sec": duration,
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


def _write_timeseries_h5(path, session_tasks):
    """`session_tasks`: `{session: [task, ...]}`, one run key per task."""
    array = np.zeros((3, 2), dtype=np.float32)
    with h5py.File(path, "w") as handle:
        for session, tasks in session_tasks.items():
            for i, task in enumerate(tasks):
                handle.create_dataset(
                    f"ses-{session}/ses-{session}_task-{task}_run-{i}_timeseries",
                    data=array,
                )


def test_cross_context_summary_default_group_column_is_dataset(tmp_path):
    a = tmp_path / "friends.h5"
    b = tmp_path / "movie10.h5"
    _write_connectome(a, "friends", ["01", "02"], ["001", "001"], seed=0)
    _write_connectome(b, "movie10", ["01", "02"], ["001", "001"], seed=1)

    result = cross_context_summary([a, b], ["A"], "pearson", min_usable_seconds=100)

    assert set(result["cross_context"]["bin"]) == {
        "within-subject / within-dataset", "within-subject / between-dataset",
        "between-subject / within-dataset", "between-subject / between-dataset",
    }


def test_cross_context_summary_title_frame_filters_and_relabels_bins(tmp_path):
    path = tmp_path / "movie10.h5"
    _write_connectome(
        path, "movie10", ["01", "01", "02"], ["001", "002", "001"],
        usable=[3600.0, 3600.0, 3600.0],
    )
    title_frame = pd.DataFrame({
        "dataset": ["movie10", "movie10"],
        "subject": ["01", "02"],
        "session": ["001", "001"],
        "title": ["bourne", "wolf"],
        "n_titles": [1, 1],
    })

    result = cross_context_summary(
        [path], ["A"], "pearson", min_usable_seconds=100,
        group_column="title", title_frame=title_frame,
    )
    bins = result["cross_context"]

    assert set(bins["bin"]) == {
        "within-subject / within-title", "within-subject / between-title",
        "between-subject / within-title", "between-subject / between-title",
    }
    # sub-01/ses-002 has no title match and must be dropped: 2 sessions left,
    # 1 pair total, both gates.
    total_pairs = bins[bins["gate"] == "all"]["n"].sum()
    assert total_pairs == 1


def test_domain_cross_context_summary_movies_uses_title_others_use_dataset(tmp_path):
    connectome_dir = tmp_path / "connectomes"
    connectome_dir.mkdir()
    _write_connectome(
        connectome_dir / "friends_cneuromod2026.h5", "friends",
        ["01", "02"], ["001", "001"],
    )
    _write_connectome(
        connectome_dir / "movie10_cneuromod2026.h5", "movie10",
        ["01", "02"], ["001", "001"],
    )
    _write_connectome(
        connectome_dir / "mario_cneuromod2026.h5", "mario",
        ["01", "02"], ["001", "001"],
    )
    _write_connectome(
        connectome_dir / "shinobi_cneuromod2026.h5", "shinobi",
        ["01", "02"], ["001", "001"],
    )
    paths = sorted(connectome_dir.glob("*.h5"))

    for dataset, task in (("friends", "s01e01a"), ("movie10", "bourne01")):
        root = (
            tmp_path / dataset / "timeseries" / "timeseries" / "cneuromod2026" / "sub-01"
        )
        root.mkdir(parents=True)
        _write_timeseries_h5(root / f"sub-01_task-{dataset}_timeseries.h5", {"001": [task]})
        root2 = (
            tmp_path / dataset / "timeseries" / "timeseries" / "cneuromod2026" / "sub-02"
        )
        root2.mkdir(parents=True)
        _write_timeseries_h5(root2 / f"sub-02_task-{dataset}_timeseries.h5", {"001": [task]})

    result = domain_cross_context_summary(
        paths, "cneuromod2026", tmp_path, ["A"], "pearson", min_usable_seconds=100,
    )
    bins = result["cross_context"]

    assert set(bins["domain"]) == {"movies", "videogames"}
    assert "stories" not in set(bins["domain"])  # no harrypotter/petit-prince file present

    movies_bins = set(bins[bins["domain"] == "movies"]["bin"])
    assert movies_bins == {
        "within-subject / within-title", "within-subject / between-title",
        "between-subject / within-title", "between-subject / between-title",
    }
    videogame_bins = set(bins[bins["domain"] == "videogames"]["bin"])
    assert videogame_bins == {
        "within-subject / within-dataset", "within-subject / between-dataset",
        "between-subject / within-dataset", "between-subject / between-dataset",
    }


def test_domain_cross_context_summary_skips_domains_with_no_files(tmp_path):
    connectome_dir = tmp_path / "connectomes"
    connectome_dir.mkdir()
    _write_connectome(
        connectome_dir / "mario_cneuromod2026.h5", "mario", ["01", "02"], ["001", "001"],
    )
    paths = sorted(connectome_dir.glob("*.h5"))

    result = domain_cross_context_summary(
        paths, "cneuromod2026", tmp_path, ["A"], "pearson", min_usable_seconds=100,
    )

    assert set(result["cross_context"]["domain"]) == {"videogames"}


def test_domain_datasets_covers_the_three_named_domains():
    assert set(DOMAIN_DATASETS) == {"movies", "videogames", "stories"}
    assert DOMAIN_DATASETS["movies"] == ("friends", "movie10")
    assert DOMAIN_DATASETS["videogames"] == ("mario", "mario3", "mariostars", "shinobi")
    assert DOMAIN_DATASETS["stories"] == ("harrypotter", "petit-prince")
