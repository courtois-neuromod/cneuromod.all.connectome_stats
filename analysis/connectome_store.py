"""Read/write `output_data/connectomes/{dataset}.h5`.

Layout (see the implementation plan, "Output layout"):

    /index/<column>                     1-D arrays, one per metadata column
    /networks/<network>/parcels         int32, 0-based h5 column indices
    /networks/<network>/edges           int32 (n_edges, 2), (row, col) pairs
    /measures/<measure>/<network>       float32 (n_entities, n_edges)
    /diagnostics/<measure>/<network>    float32 (n_entities, 6)

Row *i* of every measure/diagnostics array corresponds to row *i* of `/index`
— that alignment is the index mechanism, there is no separate join key.
"""

import h5py
import numpy as np
import pandas as pd

_STRING_DTYPE = h5py.special_dtype(vlen=str)


def _write_column(group, name, values):
    array = np.asarray(values)
    if array.dtype.kind in ("U", "O"):
        group.create_dataset(name, data=np.asarray(array, dtype=object), dtype=_STRING_DTYPE)
    else:
        group.create_dataset(name, data=array)


def write_dataset_connectomes(
    path, index_frame, networks, edges, measures, diagnostics,
    parcellation, tr_seconds, labels_checksum,
):
    """Write one dataset's full connectome file.

    `networks`: `{network: parcel_indices}` (0-based h5 columns, fixed geometry).
    `edges`: `{network: (n_edges, 2) int array}`.
    `measures`: `{measure: {network: (n_entities, n_edges) float32}}`.
    `diagnostics`: `{measure: {network: (n_entities, 6) float32}}`, columns in
    `analysis.connectome_estimators.DIAGNOSTIC_COLUMNS` order.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        handle.attrs["parcellation"] = parcellation
        handle.attrs["tr_seconds"] = tr_seconds
        handle.attrs["measures"] = list(measures.keys())
        handle.attrs["labels_checksum"] = labels_checksum

        index_group = handle.create_group("index")
        for column in index_frame.columns:
            _write_column(index_group, column, index_frame[column].to_numpy())

        networks_group = handle.create_group("networks")
        for network, parcel_indices in networks.items():
            group = networks_group.create_group(network)
            group.create_dataset("parcels", data=np.asarray(parcel_indices, dtype=np.int32))
            group.create_dataset("edges", data=np.asarray(edges[network], dtype=np.int32))

        measures_group = handle.create_group("measures")
        diagnostics_group = handle.create_group("diagnostics")
        for measure, per_network in measures.items():
            measure_group = measures_group.create_group(measure)
            diag_measure_group = diagnostics_group.create_group(measure)
            for network, array in per_network.items():
                measure_group.create_dataset(network, data=np.asarray(array, dtype=np.float32))
                diag_measure_group.create_dataset(
                    network, data=np.asarray(diagnostics[measure][network], dtype=np.float32)
                )


def load_index(path):
    """Read `/index` back into a DataFrame."""
    with h5py.File(path, "r") as handle:
        columns = {}
        for name, dataset in handle["index"].items():
            values = dataset[()]
            if values.dtype.kind == "O":
                values = np.array([v.decode() if isinstance(v, bytes) else v for v in values])
            columns[name] = values
    return pd.DataFrame(columns)


def load_measure(path, measure, network):
    """Read one `(n_entities, n_edges)` measure array."""
    with h5py.File(path, "r") as handle:
        return handle[f"measures/{measure}/{network}"][()]


def load_diagnostics(path, measure, network):
    """Read one `(n_entities, len(DIAGNOSTIC_COLUMNS))` diagnostics array."""
    with h5py.File(path, "r") as handle:
        return handle[f"diagnostics/{measure}/{network}"][()]


def load_network_geometry(path, network):
    """Read one network's `(parcels, edges)` fixed geometry."""
    with h5py.File(path, "r") as handle:
        group = handle[f"networks/{network}"]
        return group["parcels"][()], group["edges"][()]
