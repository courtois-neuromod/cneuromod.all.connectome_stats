"""Tests for analysis/connectome_store.py."""

import numpy as np
import pandas as pd

from analysis.connectome_store import (
    load_diagnostics,
    load_index,
    load_measure,
    load_network_geometry,
    write_dataset_connectomes,
)


def _sample(n_entities, n_edges_a, n_edges_b):
    index = pd.DataFrame({
        "level": ["session"] * n_entities,
        "dataset": ["movie10"] * n_entities,
        "subject": ["01"] * n_entities,
        "session": [f"{i:03d}" for i in range(n_entities)],
    })
    networks = {"A": np.array([0, 1, 2]), "B": np.array([3, 4])}
    edges = {"A": np.array([[1, 0], [2, 0], [2, 1]]), "B": np.array([[1, 0]])}
    measures = {
        "pearson": {
            "A": np.random.default_rng(0).normal(size=(n_entities, n_edges_a)).astype(np.float32),
            "B": np.random.default_rng(1).normal(size=(n_entities, n_edges_b)).astype(np.float32),
        },
    }
    diagnostics = {
        "pearson": {
            "A": np.ones((n_entities, 6), dtype=np.float32),
            "B": np.ones((n_entities, 6), dtype=np.float32) * 2,
        },
    }
    return index, networks, edges, measures, diagnostics


def test_write_and_read_round_trip(tmp_path):
    index, networks, edges, measures, diagnostics = _sample(4, 3, 1)
    path = tmp_path / "movie10.h5"

    write_dataset_connectomes(
        path, index, networks, edges, measures, diagnostics,
        parcellation="schaefer1000", tr_seconds=1.5, labels_checksum="abc123",
    )

    loaded_index = load_index(path)
    assert list(loaded_index["session"]) == list(index["session"])
    assert list(loaded_index["subject"]) == ["01", "01", "01", "01"]

    loaded_measure = load_measure(path, "pearson", "A")
    assert np.allclose(loaded_measure, measures["pearson"]["A"])

    loaded_diag = load_diagnostics(path, "pearson", "B")
    assert loaded_diag.shape == (4, 6)

    parcels, edge_array = load_network_geometry(path, "A")
    assert list(parcels) == [0, 1, 2]
    assert edge_array.shape == (3, 2)


def test_root_attributes_are_recorded(tmp_path):
    index, networks, edges, measures, diagnostics = _sample(2, 3, 1)
    path = tmp_path / "movie10.h5"
    write_dataset_connectomes(
        path, index, networks, edges, measures, diagnostics,
        parcellation="cneuromod2026", tr_seconds=1.5, labels_checksum="xyz",
    )

    import h5py
    with h5py.File(path, "r") as handle:
        assert handle.attrs["parcellation"] == "cneuromod2026"
        assert handle.attrs["tr_seconds"] == 1.5
        assert handle.attrs["labels_checksum"] == "xyz"
        assert "pearson" in list(handle.attrs["measures"])


def test_row_alignment_between_index_and_measures(tmp_path):
    index, networks, edges, measures, diagnostics = _sample(5, 3, 1)
    path = tmp_path / "movie10.h5"
    write_dataset_connectomes(
        path, index, networks, edges, measures, diagnostics,
        parcellation="schaefer1000", tr_seconds=1.5, labels_checksum="abc",
    )
    loaded_index = load_index(path)
    loaded_measure = load_measure(path, "pearson", "A")
    assert len(loaded_index) == loaded_measure.shape[0]
