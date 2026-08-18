"""Tests for analysis/similarity.py."""

import numpy as np
import pandas as pd

from analysis.connectome_store import write_dataset_connectomes
from analysis.similarity import (
    collect_pair_values,
    common_edge_mask,
    discover_connectome_files,
    load_stacked_measure,
    pair_bins,
    similarity_matrix,
)


def _write(path, subjects, sessions, dataset, n_edges, parcellation="cneuromod2026", seed=0):
    n_entities = len(subjects)
    index = pd.DataFrame({
        "level": ["session"] * n_entities,
        "dataset": [dataset] * n_entities,
        "subject": subjects,
        "session": sessions,
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


def test_discover_and_stack_round_trip(tmp_path):
    _write(tmp_path / "movie10.h5", ["01", "02"], ["001", "001"], "movie10", n_edges=3)
    _write(tmp_path / "friends.h5", ["01", "03"], ["001", "001"], "friends", n_edges=3)

    paths, skipped = discover_connectome_files(tmp_path, "cneuromod2026")
    assert skipped == []
    assert len(paths) == 2

    index_frame, matrix = load_stacked_measure(paths, "pearson", "A")
    assert matrix.shape == (4, 3)
    assert len(index_frame) == 4
    assert list(index_frame["dataset"]) == ["friends", "friends", "movie10", "movie10"]


def test_discover_skips_mismatched_parcellation_and_truncated_file(tmp_path):
    _write(tmp_path / "movie10.h5", ["01"], ["001"], "movie10", n_edges=3,
           parcellation="schaefer1000")
    _write(tmp_path / "friends.h5", ["01"], ["001"], "friends", n_edges=3)

    import h5py
    truncated = tmp_path / "things.h5"
    with h5py.File(truncated, "w") as handle:
        handle.attrs["parcellation"] = "cneuromod2026"
        handle.create_group("index")

    paths, skipped = discover_connectome_files(tmp_path, "cneuromod2026")
    assert paths == [tmp_path / "friends.h5"]
    skipped_paths = {p for p, _ in skipped}
    assert skipped_paths == {tmp_path / "movie10.h5", truncated}


def test_common_edge_mask_drops_edge_nan_in_one_session():
    matrix = np.array([
        [1.0, np.nan, 3.0],
        [1.0, 2.0, 3.0],
        [1.0, 2.0, 3.0],
    ], dtype=np.float32)
    mask = common_edge_mask(matrix)
    assert list(mask) == [True, False, True]


def test_similarity_matrix_matches_corrcoef_and_has_unit_diagonal():
    rng = np.random.default_rng(0)
    matrix = rng.normal(size=(5, 10)).astype(np.float32)
    similarity = similarity_matrix(matrix)
    expected = np.corrcoef(matrix)
    assert np.allclose(similarity, expected, atol=1e-5)
    assert np.allclose(np.diag(similarity), 1.0, atol=1e-5)


def test_pair_bins_assigns_all_four_labels_without_double_counting():
    index_frame = pd.DataFrame({
        "subject": ["01", "01", "02", "02"],
        "dataset": ["movie10", "friends", "movie10", "friends"],
    })
    labels, triu_mask = pair_bins(index_frame)
    similarity = np.zeros((4, 4))
    values = collect_pair_values(similarity, (labels, triu_mask))

    total_pairs = sum(len(v) for v in values.values())
    assert total_pairs == 6  # 4 choose 2

    assert labels[0, 1] == "within-subject / between-dataset"
    assert labels[0, 2] == "between-subject / within-dataset"
    assert labels[0, 3] == "between-subject / between-dataset"
    assert labels[1, 2] == "between-subject / between-dataset"
    assert labels[1, 3] == "between-subject / within-dataset"
    assert labels[2, 3] == "within-subject / between-dataset"
