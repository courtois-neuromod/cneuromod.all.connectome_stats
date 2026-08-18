"""Read one subject's parcelled-timeseries `.h5`.

One file holds every session and run as separate 2-D `(timepoints, parcels)`
datasets, keyed `ses-XXX/ses-XXX_task-<task>[_run-N]_timeseries` — the run
segment is optional (`friends` omits it). There are no HDF5 attributes
anywhere in these files: no TR, no parcel names, so both are config, not read
from the data. See CLAUDE.md, "The timeseries assets".
"""

import re

import h5py
import numpy as np

_KEY_PATTERN = re.compile(
    r"ses-(?P<session>[^_/]+)_task-(?P<task>[^_]+?)(?:_run-(?P<run>[^_]+))?_timeseries$"
)


def parse_run_key(key):
    """Parse one h5 dataset key into its session/task/run entities.

    `run` is `None` when the key carries no `_run-N` segment (e.g. `friends`).
    """
    match = _KEY_PATTERN.search(key)
    if not match:
        raise ValueError(f"key does not match the expected timeseries naming: {key!r}")
    return {
        "key": key,
        "session": match.group("session"),
        "task": match.group("task"),
        "run": match.group("run"),
    }


def list_entities(h5_path):
    """Every run entity stored in one subject's `.h5`, parsed from its keys."""
    entities = []

    def visit(name, obj):
        if isinstance(obj, h5py.Dataset) and name.endswith("_timeseries"):
            entities.append(parse_run_key(name))

    with h5py.File(h5_path, "r") as handle:
        handle.visititems(visit)
    return entities


def load_run(h5_path, key):
    """Load one run's `(timepoints, parcels)` array as float32."""
    with h5py.File(h5_path, "r") as handle:
        return np.asarray(handle[key], dtype=np.float32)


def invalid_columns(array):
    """Boolean mask (length n_parcels) of columns that cannot be estimated on.

    A parcel is invalid for this run if any of its values are NaN, or if it is
    constant (zero variance) — both make correlation/precision estimation
    ill-defined for that column.
    """
    is_nan = np.isnan(array).any(axis=0)
    is_constant = np.nanstd(array, axis=0) == 0
    return is_nan | is_constant


def standardize_run(array):
    """Z-score each parcel's column within this run alone.

    Runs are already standardized upstream (TIMESERIES.md), so this is a
    safeguard, not the thing doing the work — but it must still happen before
    concatenation: run-specific means/scales would otherwise induce spurious
    correlations. Invalid columns (see `invalid_columns`) are zeroed here and
    must be dropped by the caller before estimation.

    Returns `(standardized, invalid_mask)`.
    """
    from nilearn.signal import clean

    invalid = invalid_columns(array)
    safe = np.where(invalid, 0.0, array)
    standardized = clean(safe, detrend=False, standardize="zscore_sample")
    standardized[:, invalid] = np.nan
    return standardized.astype(np.float32), invalid


def session_runs(entities):
    """Group run entities by session, each group sorted by run (blank last)."""
    sessions = {}
    for entity in entities:
        sessions.setdefault(entity["session"], []).append(entity)
    for session in sessions:
        sessions[session].sort(key=lambda e: (e["run"] is None, e["run"] or ""))
    return sessions
