"""Session-to-session connectome similarity, split by subject/dataset pairing.

Exploratory QC (CLAUDE.md, "Respect the analysis hierarchy" — mechanically the
embryo of the tier-1 primary analysis, but it has no usable-data gate, so it
must not be presented as the headline result). Pure functions, no invoke
context — follows the `analysis/qc_join.py` precedent.
"""

import h5py
import numpy as np
import pandas as pd

from analysis.connectome_store import load_index, load_measure

PAIR_BINS = [
    "within-subject / within-dataset",
    "within-subject / between-dataset",
    "between-subject / within-dataset",
    "between-subject / between-dataset",
]


def discover_connectome_files(connectome_dir, parcellation):
    """Find `*.h5` files under `connectome_dir` matching `parcellation`.

    Returns `(paths, skipped)`. `skipped` is `[(path, reason)]` for a file
    whose `parcellation` attribute does not match, or that has no `/measures`
    group (a truncated write, interrupted mid-file) — reported rather than
    silently dropped.
    """
    paths = []
    skipped = []
    for path in sorted(connectome_dir.glob("*.h5")):
        with h5py.File(path, "r") as handle:
            file_parcellation = handle.attrs.get("parcellation")
            if file_parcellation != parcellation:
                skipped.append((path, f"parcellation={file_parcellation!r}"))
                continue
            if "measures" not in handle:
                skipped.append((path, "no /measures group (truncated write?)"))
                continue
        paths.append(path)
    return paths, skipped


def load_stacked_measure(paths, measure, network):
    """Stack one measure/network's edge vectors across files.

    Returns `(index_frame, matrix)`: `index_frame` is the concatenated
    `/index` (row *i* matches `matrix[i]`), `matrix` is `(n_sessions,
    n_edges)` float32. Raises if `n_edges` differs across files — that would
    mean the files disagree on network geometry, which fixed edge geometry is
    supposed to rule out.
    """
    index_frames = []
    arrays = []
    n_edges = None
    for path in paths:
        index_frames.append(load_index(path))
        array = load_measure(path, measure, network)
        if n_edges is None:
            n_edges = array.shape[1]
        elif array.shape[1] != n_edges:
            raise ValueError(
                f"{path}: {network} has {array.shape[1]} edges, expected {n_edges}"
            )
        arrays.append(array)
    index_frame = pd.concat(index_frames, ignore_index=True)
    matrix = np.concatenate(arrays, axis=0).astype(np.float32)
    return index_frame, matrix


def fisher_z(matrix):
    """`arctanh`, clipped just inside +-1 so exact +-1 does not blow up to inf."""
    clipped = np.clip(matrix, -1 + 1e-7, 1 - 1e-7)
    return np.arctanh(clipped)


def common_edge_mask(matrix):
    """Edges finite in every session (fixed geometry leaves NaN for dropped parcels)."""
    return np.isfinite(matrix).all(axis=0)


def similarity_matrix(matrix):
    """`(n_sessions, n_sessions)` Pearson r between session edge vectors.

    Row-wise z-score over the valid edges, then `Z @ Z.T / n_edges` — the
    correlation-via-standardization identity, avoiding an explicit
    `np.corrcoef` loop over sessions.
    """
    valid = common_edge_mask(matrix)
    values = matrix[:, valid].astype(np.float64)
    n_edges = values.shape[1]
    centered = values - values.mean(axis=1, keepdims=True)
    scale = centered.std(axis=1, keepdims=True)
    z = centered / scale
    return (z @ z.T) / n_edges


def pair_bins(index_frame):
    """`(n, n)` bin-label array from `subject`/`dataset` equality, plus the
    strict upper triangle so each unordered pair is counted once.
    """
    subject = index_frame["subject"].to_numpy()
    dataset = index_frame["dataset"].to_numpy()
    same_subject = subject[:, None] == subject[None, :]
    same_dataset = dataset[:, None] == dataset[None, :]

    n = len(index_frame)
    labels = np.empty((n, n), dtype=object)
    labels[same_subject & same_dataset] = PAIR_BINS[0]
    labels[same_subject & ~same_dataset] = PAIR_BINS[1]
    labels[~same_subject & same_dataset] = PAIR_BINS[2]
    labels[~same_subject & ~same_dataset] = PAIR_BINS[3]

    triu_mask = np.triu(np.ones((n, n), dtype=bool), k=1)
    return labels, triu_mask


def collect_pair_values(similarity, bins):
    """`{bin_label: 1-D array}` of similarity values for the upper-triangle pairs."""
    labels, triu_mask = bins
    result = {}
    for bin_label in PAIR_BINS:
        mask = triu_mask & (labels == bin_label)
        result[bin_label] = similarity[mask]
    return result


def summarize_bins(values_by_bin):
    """`n`, `median`, `q25`, `q75`, `mean`, `sd` per bin, in `PAIR_BINS` order."""
    rows = []
    for bin_label in PAIR_BINS:
        values = values_by_bin.get(bin_label, np.array([]))
        rows.append({
            "bin": bin_label,
            "n": len(values),
            "median": np.median(values) if len(values) else np.nan,
            "q25": np.percentile(values, 25) if len(values) else np.nan,
            "q75": np.percentile(values, 75) if len(values) else np.nan,
            "mean": np.mean(values) if len(values) else np.nan,
            "sd": np.std(values) if len(values) else np.nan,
        })
    return pd.DataFrame(rows)
