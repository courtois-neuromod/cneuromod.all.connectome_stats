"""Parcellation-agnostic parcel-to-network partition.

The partition is read from a small `source_data/{parcellation}_networks.tsv`
lookup table (columns `index`, `name`, `network`) written by `fetch-parcel-labels`
— never fetched or derived inside `run-connectomes` itself, which must only
read what is already on disk. See CLAUDE.md, "The parcel→network lookup".
"""

from pathlib import Path

import numpy as np
import pandas as pd

LABEL_COLUMNS = ["index", "name", "network"]


def load_parcel_labels(path):
    """Read a `{parcellation}_networks.tsv` lookup table.

    `index` is the 1-based parcel label as it appears in the `_dseg.nii.gz`
    volumes (0 is background and is never a row here).
    """
    path = Path(path)
    frame = pd.read_csv(path, sep="\t", dtype={"index": int, "name": str, "network": str})
    missing = [column for column in LABEL_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"{path} is missing column(s): {missing}")
    return frame


def network_parcels(labels, network_order):
    """Group a labels table into 0-based h5 column indices, in `network_order`.

    Row order of `labels` is assumed to already be h5 column order — i.e. row 0
    is timeseries column 0, and so on. Raises if any network in `network_order`
    is missing, or if a row's `network` value falls outside `network_order`
    (the partition would then not cover every parcel exactly once).
    """
    frame = labels.reset_index(drop=True)
    unexpected = sorted(set(frame["network"]) - set(network_order))
    if unexpected:
        raise ValueError(f"labels reference network(s) not in network_order: {unexpected}")

    grouped = {}
    for network in network_order:
        columns = frame.index[frame["network"] == network].to_numpy(dtype=np.int64)
        if columns.size == 0:
            raise ValueError(f"network '{network}' has no parcels in the labels table")
        grouped[network] = columns
    return grouped


def edge_pairs(parcel_indices):
    """Lower-triangle (row, col) index pairs for one network's parcels.

    Matches `numpy.tril_indices(p, k=-1)` order — the same order nilearn's
    `ConnectivityMeasure(vectorize=True, discard_diagonal=True)` produces — so
    edge slot *i* here is edge slot *i* in every stored measure vector.
    """
    n_parcels = len(parcel_indices)
    rows, cols = np.tril_indices(n_parcels, k=-1)
    return np.column_stack([rows, cols]).astype(np.int64)


# --------------------------------------------------------------------------- #
# Building the lookup table (used by `fetch-parcel-labels` only)
# --------------------------------------------------------------------------- #
def build_schaefer1000_labels():
    """Derive the schaefer1000 labels table from nilearn's bundled atlas.

    7 Yeo cortical networks only, matching this parcellation's 1000 cortical
    parcels. Network is the 3rd underscore-separated field of each region name
    (e.g. `7Networks_LH_Vis_1` -> `Vis`).
    """
    from nilearn.datasets import fetch_atlas_schaefer_2018

    atlas = fetch_atlas_schaefer_2018(n_rois=1000, yeo_networks=7, resolution_mm=2)
    names = [
        label.decode() if isinstance(label, bytes) else label
        for label in atlas["labels"]
    ]
    # Some nilearn versions prepend a "Background" entry (label 0); others
    # return exactly the 1000 region names starting at label 1. Detect rather
    # than assume, so this survives either.
    if names and names[0] == "Background":
        names = names[1:]

    rows = []
    for position, name in enumerate(names, start=1):
        network = name.split("_")[2]
        rows.append({"index": position, "name": name, "network": network})
    return pd.DataFrame(rows, columns=LABEL_COLUMNS)


# Known parcel counts per network, from qa_figures' per-network tSNR tables
# (see the implementation plan's "On the cneuromod2026 switch"). Any labels
# table that disagrees is almost certainly reading label values with the wrong
# offset convention — see `build_cneuromod2026_labels`'s docstring — so
# `fetch-parcel-labels` asserts against this rather than writing a silently
# wrong lookup table.
CNEUROMOD2026_EXPECTED_COUNTS = {
    "Vis": 162, "SomMot": 194, "DorsAttn": 122, "SalVentAttn": 121,
    "Limbic": 60, "Cont": 128, "Default": 209,
    "cerebellum": 88, "subcortex": 50,
}


def build_cneuromod2026_labels(dseg_path, cortical_labels=None):
    """Derive the cneuromod2026 labels table from one subject's `_dseg.nii.gz`.

    **Documented assumption, not yet verified against real data** (no S3
    credentials were available while writing this): the atlas is built by
    concatenating three source atlases and the *label values* encode which
    block a parcel belongs to —

    - `1..1000` — Schaefer2018 cortical, in the *same numbering* nilearn's own
      1000-region/7-network atlas uses (up to 4 values absent: TIMESERIES.md
      puts the cortical count at 996, not 1000).
    - `1001..1050` — Tian2020 S3 subcortical (50 parcels, offset by the
      cortical block's max possible value, not its actual count).
    - `1051..1138` — Nettekoven2024 Asym128 cerebellar (88 of 128 parcels
      survive individual masking; same offset convention).

    If this assumption is wrong, the resulting per-network parcel counts will
    not match `CNEUROMOD2026_EXPECTED_COUNTS`, and this function raises rather
    than returning a silently mis-mapped table — run
    `invoke fetch-parcel-labels` yourself against a real dseg once you have S3
    credentials and treat that assertion as the check.
    """
    import nibabel

    if cortical_labels is None:
        cortical_labels = build_schaefer1000_labels()
    cortical_by_index = dict(zip(cortical_labels["index"], cortical_labels["name"]))

    image = nibabel.load(str(dseg_path))
    values = np.unique(np.asarray(image.dataobj))
    values = sorted(int(value) for value in values if value != 0)

    rows = []
    for value in values:
        if value <= 1000:
            name = cortical_by_index.get(value)
            if name is None:
                raise ValueError(
                    f"{dseg_path}: cortical label {value} has no schaefer1000 name "
                    "— the label-value assumption in build_cneuromod2026_labels is wrong"
                )
            network = name.split("_")[2]
        elif value <= 1050:
            name = f"subcortex_Tian_{value - 1000}"
            network = "subcortex"
        else:
            name = f"cerebellum_Nettekoven_{value - 1050}"
            network = "cerebellum"
        rows.append({"index": value, "name": name, "network": network})

    frame = pd.DataFrame(rows, columns=LABEL_COLUMNS)
    counts = frame.groupby("network").size().to_dict()
    if counts != CNEUROMOD2026_EXPECTED_COUNTS:
        raise ValueError(
            "cneuromod2026 label parsing produced unexpected per-network counts "
            f"{counts}, expected {CNEUROMOD2026_EXPECTED_COUNTS}. The label-value "
            "offset convention assumed in build_cneuromod2026_labels is likely "
            "wrong for this dseg — inspect it directly before trusting this table."
        )
    return frame
