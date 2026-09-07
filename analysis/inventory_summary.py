"""Rollups of `analysis/asset_inventory.py`'s per-run table into the session,
subject, dataset and gap-focused tables `run-inventory` (tasks.py) writes.

Split out from `analysis/asset_inventory.py` to keep each module near
CLAUDE.md's ~200-line guideline: that module discovers and joins the four
assets; this one only aggregates the result it produces.
"""

import numpy as np
import pandas as pd

from analysis.qc_measures import available_datasets
from analysis.similarity import discover_connectome_files


def summarize_sessions(run_inventory, connectome_index=None, min_usable_seconds=None):
    """Per `(dataset, subject, session)` rollup of raw/timeseries/QC coverage,
    plus connectome presence and gate status when `connectome_index` is given.
    """
    if run_inventory.empty:
        columns = ["dataset", "subject", "session", "n_raw_runs", "n_timeseries_runs",
                   "n_qc_runs", "raw_duration_sec", "has_connectome",
                   "usable_duration_sec", "passes_gate"]
        return pd.DataFrame(columns=columns)

    grouped = run_inventory.groupby(["dataset", "subject", "session"], dropna=False)
    sessions = grouped.agg(
        n_raw_runs=("run", "size"),
        n_timeseries_runs=("in_timeseries", "sum"),
        n_qc_runs=("in_qc", "sum"),
        raw_duration_sec=("duration_sec", "sum"),
    ).reset_index()

    if connectome_index is None or connectome_index.empty:
        sessions["has_connectome"] = False
        sessions["usable_duration_sec"] = np.nan
        sessions["passes_gate"] = False
        return sessions

    connectome = connectome_index.copy()
    connectome["session"] = connectome["session"].astype(str)
    connectome = connectome.drop_duplicates(subset=["dataset", "subject", "session"])
    usable = connectome["usable_duration_sec"].fillna(connectome["duration_sec"])
    connectome["passes_gate"] = (
        usable >= min_usable_seconds if min_usable_seconds is not None else False
    )
    connectome["has_connectome"] = True

    sessions["session"] = sessions["session"].astype(str)
    merged = sessions.merge(
        connectome[["dataset", "subject", "session", "usable_duration_sec",
                     "passes_gate", "has_connectome"]],
        on=["dataset", "subject", "session"], how="left",
    )
    merged["has_connectome"] = merged["has_connectome"].fillna(False)
    merged["passes_gate"] = merged["passes_gate"].fillna(False)
    return merged


def summarize_subjects(run_inventory):
    """Per `(dataset, subject)` rollup of `summarize_sessions`'s row shape."""
    if run_inventory.empty:
        columns = ["dataset", "subject", "n_sessions", "n_raw_runs",
                   "n_timeseries_runs", "n_qc_runs", "raw_duration_sec"]
        return pd.DataFrame(columns=columns)
    grouped = run_inventory.groupby(["dataset", "subject"], dropna=False)
    return grouped.agg(
        n_sessions=("session", "nunique"),
        n_raw_runs=("run", "size"),
        n_timeseries_runs=("in_timeseries", "sum"),
        n_qc_runs=("in_qc", "sum"),
        raw_duration_sec=("duration_sec", "sum"),
    ).reset_index()


def summarize_datasets(run_inventory, dataset_status, connectome_dir=None, parcellation=None,
                        qa_root=None):
    """Per-dataset asset-level status: is each of the four assets present at all.

    `dataset_status` is the `status_rows` list
    `analysis.asset_inventory.build_run_inventory` returns (per-subject
    timeseries registration/fetch status, rolled up here to per-dataset
    booleans).
    """
    datasets = sorted(set(run_inventory["dataset"]) if not run_inventory.empty else set())
    status_frame = pd.DataFrame(dataset_status) if dataset_status else pd.DataFrame(
        columns=["dataset", "registered", "content_present"]
    )
    for dataset in status_frame["dataset"].unique() if not status_frame.empty else []:
        if dataset not in datasets:
            datasets.append(dataset)
    datasets = sorted(set(datasets))

    qc_populated = set(available_datasets(qa_root, kind="qc")) if qa_root is not None else set()
    tsnr_populated = set(available_datasets(qa_root, kind="atlas_tsnr")) if qa_root is not None \
        else set()

    connectome_files = set()
    if connectome_dir is not None and parcellation is not None and connectome_dir.is_dir():
        paths, _skipped = discover_connectome_files(connectome_dir, parcellation)
        connectome_files = {p.stem.rsplit(f"_{parcellation}", 1)[0] for p in paths}

    raw_datasets = set(run_inventory["dataset"]) if not run_inventory.empty else set()
    rows = []
    for dataset in datasets:
        dataset_rows = status_frame[status_frame["dataset"] == dataset]
        rows.append({
            "dataset": dataset,
            "bids_installed": dataset in raw_datasets,
            "timeseries_registered": bool(dataset_rows["registered"].any())
            if not dataset_rows.empty else False,
            "timeseries_content_subjects": int(dataset_rows["content_present"].sum())
            if not dataset_rows.empty else 0,
            "qc_table_populated": dataset in qc_populated,
            "atlas_tsnr_populated": dataset in tsnr_populated,
            "connectome_file_present": dataset in connectome_files,
        })
    return pd.DataFrame(rows)


def inventory_gaps(run_inventory, dataset_coverage):
    """Only the rows where an expected asset is absent, with a `reason` code."""
    reasons = []
    if not dataset_coverage.empty:
        for _, row in dataset_coverage.iterrows():
            if row["timeseries_registered"] and row["timeseries_content_subjects"] == 0:
                reasons.append({"dataset": row["dataset"], "subject": "", "session": "",
                                 "reason": "timeseries_content_missing"})
            if not row["qc_table_populated"]:
                reasons.append({"dataset": row["dataset"], "subject": "", "session": "",
                                 "reason": "qc_table_empty"})
            if not row["atlas_tsnr_populated"]:
                reasons.append({"dataset": row["dataset"], "subject": "", "session": "",
                                 "reason": "atlas_tsnr_empty"})
            if not row["connectome_file_present"]:
                reasons.append({"dataset": row["dataset"], "subject": "", "session": "",
                                 "reason": "no_connectome_file"})

    if not run_inventory.empty:
        unmatched = run_inventory[run_inventory["match_level"] == "unmatched"]
        for _, row in unmatched.iterrows():
            reasons.append({"dataset": row["dataset"], "subject": row["subject"],
                             "session": row["session"], "reason": "unmatched_entities"})

    return pd.DataFrame(reasons, columns=["dataset", "subject", "session", "reason"])
