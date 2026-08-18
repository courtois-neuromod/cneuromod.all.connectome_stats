"""Tests for analysis/parcel_networks.py."""

import numpy as np
import pandas as pd
import pytest

from analysis.parcel_networks import edge_pairs, network_parcels


def _labels(networks):
    """Build a minimal labels frame: `networks` is a list of network names,
    one row per name (so len(networks) == number of parcels)."""
    return pd.DataFrame({
        "index": range(1, len(networks) + 1),
        "name": [f"p{i}" for i in range(len(networks))],
        "network": networks,
    })


def test_network_parcels_covers_every_parcel_exactly_once():
    labels = _labels(["A", "A", "B", "B", "B"])
    grouped = network_parcels(labels, ["A", "B"])

    all_indices = np.concatenate(list(grouped.values()))
    assert sorted(all_indices) == [0, 1, 2, 3, 4]
    assert list(grouped["A"]) == [0, 1]
    assert list(grouped["B"]) == [2, 3, 4]


def test_network_parcels_preserves_config_order():
    labels = _labels(["B", "A"])
    grouped = network_parcels(labels, ["A", "B"])
    assert list(grouped.keys()) == ["A", "B"]


def test_network_parcels_raises_on_unlisted_network():
    labels = _labels(["A", "C"])
    with pytest.raises(ValueError, match="not in network_order"):
        network_parcels(labels, ["A", "B"])


def test_network_parcels_raises_when_a_configured_network_is_absent():
    labels = _labels(["A", "A"])
    with pytest.raises(ValueError, match="no parcels"):
        network_parcels(labels, ["A", "B"])


def test_edge_pairs_matches_tril_indices():
    pairs = edge_pairs(np.arange(4))
    rows, cols = np.tril_indices(4, k=-1)
    assert np.array_equal(pairs, np.column_stack([rows, cols]))


def test_edge_pairs_length_is_p_choose_2():
    pairs = edge_pairs(np.arange(6))
    assert pairs.shape == (6 * 5 // 2, 2)
