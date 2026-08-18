"""Join the qa_figures QC tables onto connectome entities (run or session rows).

Deliberately kept out of `analysis/qc_measures.py` so that module stays a pure
table reader — the entity-normalization and network-name mapping done here is
specific to how `run-connectomes` builds its entities. See CLAUDE.md, "The QC
measures asset (qa_figures)", for the coverage gaps this join must tolerate.
"""

import numpy as np
import pandas as pd

from analysis.qc_measures import MOTION_COLUMNS, load_atlas_tsnr, load_qc_measures

ENTITY_KEYS = ["dataset", "subject", "session", "task", "run"]

# Long-table `group` values that feed each of this project's network names.
# Cortical networks map 1:1 to a `cortex_<Network>` group; cerebellum maps
# directly; subcortex pools the three groups qa_figures actually covers (30 of
# the atlas's 50 Tian parcels — see CLAUDE.md) weighted by their `n_parcels`.
_NETWORK_GROUPS = {
    "cerebellum": ["cerebellum"],
    "subcortex": ["subcortex_PUT", "subcortex_THA", "subcortex_CAU"],
}


def _tsnr_groups_for(network):
    return _NETWORK_GROUPS.get(network, [f"cortex_{network}"])


def normalize_entities(frame):
    """Normalize entity columns to the qa_figures convention.

    Strips `sub-`/`ses-` prefixes, zero-pads session to 3 digits, and coerces
    `run` to a plain integer-like string with blank (not NaN) for "no run in
    this key". `run` coverage is *not* uniformly blank for movie10/friends as
    CONTENT.md's per-dataset summary implies — qa_figures exports it as a
    float-like string ("1.0") for some subject/session combinations even
    within the same dataset, so the trailing ".0" is stripped here too.
    """
    frame = frame.copy()
    frame["subject"] = frame["subject"].astype(str).str.removeprefix("sub-")
    frame["session"] = (
        frame["session"].astype(str).str.removeprefix("ses-").str.zfill(3)
    )
    run = frame["run"].fillna("").astype(str).str.removeprefix("run-")
    run = run.replace({"None": ""})
    run = run.str.replace(r"\.0$", "", regex=True)
    frame["run"] = run
    return frame


def join_run_qc(entities, qa_root, datasets=None):
    """Left-join per-run motion QC onto `entities` (one row per run entity).

    Unmatched rows keep NaN in the motion columns and get `qc_matched = False`.
    """
    entities = normalize_entities(entities)
    qc = load_qc_measures(qa_root, datasets=datasets)
    if qc.empty:
        result = entities.copy()
        for column in MOTION_COLUMNS + ["tsnr"]:
            result[column] = np.nan
        result["qc_matched"] = False
        return result

    qc = normalize_entities(qc)
    keep = ENTITY_KEYS + [c for c in MOTION_COLUMNS + ["tsnr"] if c in qc.columns]
    merged = entities.merge(qc[keep], on=ENTITY_KEYS, how="left", indicator=True)
    merged["qc_matched"] = merged["_merge"] == "both"
    return merged.drop(columns="_merge")


def join_network_tsnr(entities, qa_root, network_order, datasets=None):
    """Add one `tsnr_<network>` column per entry in `network_order`.

    NaN when the entity or the group is not covered by qa_figures (see
    CLAUDE.md — only 3 of 20 `atlas_tsnr` tables are populated, and subcortex
    coverage is partial even where the table exists).
    """
    entities = normalize_entities(entities)
    long = load_atlas_tsnr(qa_root, datasets=datasets)
    result = entities.copy()
    if long.empty:
        for network in network_order:
            result[f"tsnr_{network}"] = np.nan
        return result

    long = normalize_entities(long)
    for network in network_order:
        groups = long[long["group"].isin(_tsnr_groups_for(network))]
        if groups.empty:
            result[f"tsnr_{network}"] = np.nan
            continue
        weighted = groups.assign(_weighted=groups["tsnr_mean"] * groups["n_parcels"])
        pooled = weighted.groupby(ENTITY_KEYS, as_index=False).agg(
            _weighted_sum=("_weighted", "sum"), _weight_sum=("n_parcels", "sum"),
        )
        pooled[f"tsnr_{network}"] = pooled["_weighted_sum"] / pooled["_weight_sum"]
        result = result.merge(
            pooled[ENTITY_KEYS + [f"tsnr_{network}"]], on=ENTITY_KEYS, how="left",
        )
    return result


def aggregate_session_qc(run_qc, tr_seconds, value_columns=None):
    """Volume-weighted mean of run-level QC columns, grouped to one row per session.

    `value_columns` defaults to the motion columns plus `tsnr`; pass the
    per-network `tsnr_<network>` columns too so they get the same pooling.
    `usable_duration_sec` subtracts `fd_num * tr_seconds` from the session's
    total duration where FD is available (NaN otherwise) — a recorded
    covariate, never a filter (CLAUDE.md, "Record QC, never gate on it").
    """
    if value_columns is None:
        value_columns = MOTION_COLUMNS + ["tsnr"]
    frame = run_qc.copy()
    frame["duration_sec"] = frame["n_volumes"] * tr_seconds

    rows = []
    for (dataset, subject, session), group in frame.groupby(
        ["dataset", "subject", "session"], sort=False
    ):
        row = {"dataset": dataset, "subject": subject, "session": session}
        weights = group["n_volumes"].fillna(0)
        for column in value_columns:
            if column in group.columns:
                row[column] = weighted_mean_for(group, column, weights=weights)
        row["n_volumes"] = group["n_volumes"].sum()
        row["duration_sec"] = group["duration_sec"].sum()
        fd_num_total = group["fd_num"].sum() if "fd_num" in group.columns else np.nan
        row["usable_duration_sec"] = (
            row["duration_sec"] - fd_num_total * tr_seconds
            if pd.notna(fd_num_total) else np.nan
        )
        row["qc_matched"] = bool(group["qc_matched"].any())
        rows.append(row)
    return pd.DataFrame(rows)


def weighted_mean_for(group, column, weights):
    values = group[column]
    mask = values.notna() & (weights > 0)
    if not mask.any():
        return np.nan
    return float(np.average(values[mask], weights=weights[mask]))
