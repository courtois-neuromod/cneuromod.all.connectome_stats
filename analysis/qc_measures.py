"""Reader for the per-run QC tables in the cneuromod.all.qa_figures checkout.

Pure functions, no invoke context — mirrors analysis/timeseries_layout.py's
style. Coverage of these tables is partial (see source_data/CONTENT.md): some
per-dataset tables are empty 1-byte files, and callers must tolerate that
rather than treating it as an error.
"""

from pathlib import Path

import pandas as pd

ENTITY_COLUMNS = ["dataset", "subject", "session", "task", "run"]

MOTION_COLUMNS = [
    "fd_mean", "fd_num", "fd_perc", "fd_prop_gt02", "fd_prop_gt05",
]

TSNR_COLUMN = "tsnr"

REGION_GROUPS = [
    "cortex_Vis", "cortex_SomMot", "cortex_DorsAttn", "cortex_SalVentAttn",
    "cortex_Limbic", "cortex_Cont", "cortex_Default",
    "cerebellum", "subcortex_PUT", "subcortex_THA", "subcortex_CAU",
]

_QC_ENTITY_DTYPES = {"subject": str, "session": str, "run": str}


def qc_table_path(qa_root, dataset):
    """Path to a dataset's per-run QC table (motion, tSNR, ...)."""
    return Path(qa_root) / "output_data" / "tables" / f"{dataset}.tsv"


def atlas_tsnr_table_path(qa_root, dataset):
    """Path to a dataset's per-network tSNR table."""
    return Path(qa_root) / "output_data" / "tables" / "atlas_tsnr" / f"{dataset}.tsv"


def _table_dir(qa_root, kind):
    return (
        Path(qa_root) / "output_data" / "tables"
        if kind == "qc" else
        Path(qa_root) / "output_data" / "tables" / "atlas_tsnr"
    )


def _is_populated(path):
    """True when `path` holds more than a stray newline.

    Upstream's "empty" tables are not zero-byte: they are a single `\\n`
    (1 byte), so a plain `st_size > 0` check does not catch them.
    """
    return bool(path.read_text().strip())


def available_datasets(qa_root, kind="qc"):
    """Names whose table is present and non-empty, for the given `kind`.

    `kind` is "qc" for the per-run tables, or "atlas_tsnr" for the per-network
    tSNR tables. Coverage differs sharply between the two — see
    source_data/CONTENT.md.
    """
    table_dir = _table_dir(qa_root, kind)
    if not table_dir.is_dir():
        return []
    return sorted(
        path.stem for path in table_dir.glob("*.tsv") if _is_populated(path)
    )


def _load_tables(qa_root, datasets, kind, path_fn):
    names = datasets if datasets is not None else available_datasets(qa_root, kind=kind)
    frames = []
    for name in names:
        path = path_fn(qa_root, name)
        if not path.is_file() or not _is_populated(path):
            continue
        frames.append(pd.read_csv(path, sep="\t", dtype=_QC_ENTITY_DTYPES))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_qc_measures(qa_root, datasets=None):
    """Concatenate the per-run QC tables for `datasets` (default: all available).

    Entity columns (subject, session, run) are read as strings, so zero-padded
    labels like "01" survive rather than becoming integers.
    """
    return _load_tables(qa_root, datasets, kind="qc", path_fn=qc_table_path)


def load_atlas_tsnr(qa_root, datasets=None):
    """Concatenate the per-network tSNR tables for `datasets` (default: all available)."""
    return _load_tables(qa_root, datasets, kind="atlas_tsnr", path_fn=atlas_tsnr_table_path)
