"""The two connectome measures, computed on a fixed edge geometry.

Settled in CLAUDE.md: `partial_ledoitwolf` (nilearn's default-shrinkage
partial correlation, an established regularized estimator) is primary,
Pearson correlation is the comparator, and everything downstream must run
identically for both.

Edge geometry is fixed per network (see `analysis/parcel_networks.py`):
a parcel missing or constant in a given session is dropped before
estimation, and the resulting smaller connectome is scattered back into the
full `p × p` layout with NaN in the affected edges, so every stored vector has
the same length regardless of how many parcels actually contributed.
"""

import numpy as np

DIAGNOSTIC_COLUMNS = [
    "n_samples", "n_parcels", "n_parcels_valid",
    "rank", "condition_number", "min_eigenvalue",
]


def _make_measure(kind, cov_estimator):
    from nilearn.connectome import ConnectivityMeasure

    return ConnectivityMeasure(
        kind=kind,
        cov_estimator=cov_estimator,
        vectorize=True,
        discard_diagonal=True,
        standardize=False,
    )


def _pearson_measure():
    from sklearn.covariance import EmpiricalCovariance

    return _make_measure("correlation", EmpiricalCovariance(store_precision=False))


def _partial_ledoitwolf_measure():
    from sklearn.covariance import LedoitWolf

    return _make_measure("partial correlation", LedoitWolf(store_precision=False))


MEASURES = {
    "pearson": _pearson_measure,
    "partial_ledoitwolf": _partial_ledoitwolf_measure,
}


def _full_edge_index(row, col):
    """0-based position of edge (row, col), row > col, in `tril_indices(p, k=-1)` order."""
    return row * (row - 1) // 2 + col


def _covariance_diagnostics(data):
    covariance = np.cov(data, rowvar=False)
    covariance = np.atleast_2d(covariance)
    eigenvalues = np.linalg.eigvalsh(covariance)
    return {
        "rank": float(np.linalg.matrix_rank(covariance)),
        "condition_number": float(np.linalg.cond(covariance)),
        "min_eigenvalue": float(eigenvalues.min()),
    }


def connectome(data, kind):
    """Compute one network's connectome vector and diagnostics for one entity.

    `data` is `(n_samples, n_parcels)`, already standardized, with NaN in
    columns for parcels invalid in this session (see
    `analysis.timeseries_reader.standardize_run`). Returns
    `(vector, diagnostics)`: `vector` has length `n_parcels * (n_parcels - 1) / 2`
    (the network's fixed edge geometry) with NaN for edges touching an invalid
    or dropped parcel; `diagnostics` is a dict with `DIAGNOSTIC_COLUMNS` keys.
    """
    n_samples, n_parcels = data.shape
    n_edges = n_parcels * (n_parcels - 1) // 2
    vector = np.full(n_edges, np.nan, dtype=np.float32)
    diagnostics = {
        "n_samples": float(n_samples),
        "n_parcels": float(n_parcels),
        "n_parcels_valid": 0.0,
        "rank": np.nan, "condition_number": np.nan, "min_eigenvalue": np.nan,
    }

    valid = ~np.isnan(data).any(axis=0)
    n_valid = int(valid.sum())
    diagnostics["n_parcels_valid"] = float(n_valid)
    if n_valid < 2 or n_samples < 2:
        return vector, diagnostics

    valid_indices = np.flatnonzero(valid)
    sub = data[:, valid]

    measure = MEASURES[kind]()
    sub_vector = measure.fit_transform([sub])[0]

    rows_sub, cols_sub = np.tril_indices(n_valid, k=-1)
    full_rows = valid_indices[rows_sub]
    full_cols = valid_indices[cols_sub]
    full_slots = _full_edge_index(full_rows, full_cols)
    vector[full_slots] = sub_vector.astype(np.float32)

    diagnostics.update(_covariance_diagnostics(sub))
    return vector, diagnostics
