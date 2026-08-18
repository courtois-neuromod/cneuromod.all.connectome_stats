"""Tests for analysis/connectome_estimators.py."""

import numpy as np
import pytest

from analysis.connectome_estimators import DIAGNOSTIC_COLUMNS, MEASURES, connectome


@pytest.fixture
def synthetic_data():
    rng = np.random.default_rng(0)
    n_samples, n_parcels = 300, 8
    latent = rng.normal(size=(n_samples, 2))
    loadings = rng.normal(size=(2, n_parcels))
    data = latent @ loadings + rng.normal(scale=0.3, size=(n_samples, n_parcels))
    return data.astype(np.float32)


@pytest.mark.parametrize("kind", list(MEASURES))
def test_vector_length_is_p_choose_2(synthetic_data, kind):
    vector, _ = connectome(synthetic_data, kind)
    p = synthetic_data.shape[1]
    assert vector.shape == (p * (p - 1) // 2,)


@pytest.mark.parametrize("kind", list(MEASURES))
def test_diagnostics_are_finite_and_well_formed(synthetic_data, kind):
    _, diagnostics = connectome(synthetic_data, kind)
    assert set(diagnostics) == set(DIAGNOSTIC_COLUMNS)
    assert diagnostics["n_parcels_valid"] == synthetic_data.shape[1]
    assert np.isfinite(diagnostics["condition_number"])
    assert np.isfinite(diagnostics["min_eigenvalue"])


def test_pearson_matches_manual_correlation(synthetic_data):
    vector, _ = connectome(synthetic_data, "pearson")
    manual = np.corrcoef(synthetic_data, rowvar=False)
    rows, cols = np.tril_indices(synthetic_data.shape[1], k=-1)
    assert np.allclose(vector, manual[rows, cols], atol=1e-4)


def test_dropped_parcel_leaves_vector_length_unchanged_with_nan_edges(synthetic_data):
    data = synthetic_data.copy()
    data[:, 3] = np.nan  # parcel 3 invalid for this run

    vector, diagnostics = connectome(data, "pearson")
    p = data.shape[1]
    rows, cols = np.tril_indices(p, k=-1)

    assert vector.shape == (p * (p - 1) // 2,)
    assert diagnostics["n_parcels_valid"] == p - 1

    touches_dropped = (rows == 3) | (cols == 3)
    assert np.isnan(vector[touches_dropped]).all()
    assert np.isfinite(vector[~touches_dropped]).all()


def test_too_few_valid_parcels_returns_all_nan_vector(synthetic_data):
    data = synthetic_data.copy()
    data[:, 1:] = np.nan  # only one valid parcel left

    vector, diagnostics = connectome(data, "partial_ledoitwolf")
    assert np.isnan(vector).all()
    assert diagnostics["n_parcels_valid"] == 1
    assert np.isnan(diagnostics["condition_number"])
