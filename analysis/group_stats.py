"""Group-level statistics: the two headline analyses (CLAUDE.md, "Scientific
objective").

Analysis B (cross-context): does within-subject connectome similarity exceed
between-subject similarity, and does task context lower it less than subject
identity does? All datasets, split same-/different-subject x same-/different-
dataset. Analysis A (longitudinal): is that similarity stable across five
years of acquisition? `friends` only, split by season lag — the only
task-homogeneous dataset available, so season isolates drift (scanner,
subject state, elapsed time) from cognitive context.

`domain_cross_context_summary` is a robustness-tier check on Analysis B: the
same within-/between-task contrast, restricted one domain at a time to
`DOMAIN_DATASETS` (movies, videogames, stories) — sets of datasets sharing a
naturalistic-stimulus domain, so "between-task" means a much more homogeneous
swap than "friends vs. retinotopy".

Pure functions, no invoke context — follows the `analysis/qc_join.py`,
`analysis/similarity.py` precedent. `run-group-stats` (tasks.py) is the only
caller; it does the I/O and writes the tidy TSVs under output_data/group_stats/.
"""

import numpy as np
import pandas as pd

from analysis.connectome_store import load_index, load_measure
from analysis.domain_titles import attach_titles, session_titles
from analysis.friends_seasons import attach_seasons, season_index, session_seasons
from analysis.similarity import (
    collect_pair_values,
    common_edge_mask,
    fisher_z,
    load_stacked_measure,
    pair_bin_labels,
    pair_bins,
    pair_frame,
    similarity_matrix,
    summarize_bins,
)

GATES = ("all", "gated", "qc_covered", "low_motion", "high_tsnr")


def usable_sessions(index_frame, min_usable_seconds):
    """Boolean mask on the usable-data gate, plus a per-dataset report.

    `usable_duration_sec` is NaN for sessions with no motion QC match (mario,
    harrypotter — see CLAUDE.md, "The QC measures asset"); those sessions fall
    back to `duration_sec` so the gate is defined everywhere, not just where
    QC matched.
    """
    usable = index_frame["usable_duration_sec"].fillna(index_frame["duration_sec"])
    passing = usable >= min_usable_seconds

    rows = []
    for dataset, group in index_frame.groupby("dataset", sort=False):
        group_usable = usable.loc[group.index]
        group_passing = passing.loc[group.index]
        rows.append({
            "dataset": dataset,
            "n_sessions": len(group),
            "n_passing": int(group_passing.sum()),
            "median_usable_duration_sec": float(group_usable.median()),
            "qc_coverage": float(group["qc_matched"].mean()) if "qc_matched" in group else np.nan,
        })
    return passing.to_numpy(), pd.DataFrame(rows)


def network_quality(index_frame, network_order):
    """Per network: median `tsnr_{network}`, coverage count, contributing datasets.

    Returns NaN median with `n_tsnr=0` rather than raising when a network has
    no coverage — most `atlas_tsnr` tables are still empty upstream (see
    CLAUDE.md, "The QC measures asset").
    """
    rows = []
    for network in network_order:
        column = f"tsnr_{network}"
        if column not in index_frame.columns:
            rows.append({"network": network, "median_tsnr": np.nan, "n_tsnr": 0, "datasets": ""})
            continue
        values = index_frame[column]
        finite = values.notna()
        datasets = ",".join(sorted(index_frame.loc[finite, "dataset"].unique()))
        rows.append({
            "network": network,
            "median_tsnr": float(values[finite].median()) if finite.any() else np.nan,
            "n_tsnr": int(finite.sum()),
            "datasets": datasets,
        })
    return pd.DataFrame(rows)


def similarity_histogram(values, bins):
    """Tidy `(bin_left, bin_right, count)` histogram of one array of similarity values."""
    values = np.asarray(values)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return pd.DataFrame({"bin_left": pd.Series(dtype=float),
                              "bin_right": pd.Series(dtype=float),
                              "count": pd.Series(dtype=int)})
    counts, edges = np.histogram(values, bins=bins, range=(-1.0, 1.0))
    return pd.DataFrame({"bin_left": edges[:-1], "bin_right": edges[1:], "count": counts})


def _gate_mask_for(index_frame, min_usable_seconds, gate_name):
    """Boolean row mask for one `GATES` entry.

    `qc_covered`/`low_motion`/`high_tsnr` delegate the stratum to
    `analysis.motion_strata`/`analysis.tsnr_strata` rather than
    reimplementing it — see CLAUDE.md, "Motion stratification" and "tSNR
    stratification". The meaningful contrast for the headline tables is
    `low_motion`/`high_tsnr` vs. `qc_covered`, not vs. `gated`: both
    necessarily drop mario/harrypotter (no QC coverage), and comparing them
    against `gated` would confound an acquisition-quality effect with that
    change in dataset composition. `high_tsnr` uses the `raw` tSNR
    definition, whose stratum is 72% concordant with `low_motion` — the two
    gates are coupled, not independent checks.
    """
    if gate_name == "all":
        return np.ones(len(index_frame), dtype=bool)
    usable = index_frame["usable_duration_sec"].fillna(index_frame["duration_sec"])
    gated_mask = (usable >= min_usable_seconds).to_numpy()
    if gate_name == "gated":
        return gated_mask

    from analysis.motion_strata import assign_motion_strata, qc_covered_mask
    from analysis.tsnr_strata import assign_tsnr_strata

    qc_mask = qc_covered_mask(index_frame, min_usable_seconds)
    if gate_name == "qc_covered":
        return qc_mask

    strata_for = {
        "low_motion": (assign_motion_strata, "motion_stratum", "low"),
        "high_tsnr": (assign_tsnr_strata, "tsnr_stratum", "high"),
    }
    if gate_name not in strata_for:
        raise ValueError(f"Unknown gate {gate_name!r}")
    assign, stratum_column, keep = strata_for[gate_name]
    stratum = np.full(len(index_frame), None, dtype=object)
    stratum[qc_mask] = assign(
        index_frame[qc_mask].reset_index(drop=True)
    )[stratum_column].to_numpy()
    return stratum == keep


def duration_balance(index_frame, min_usable_seconds, group_column="dataset"):
    """Per gate x cross-context bin: pair min-usable-duration distribution.

    Justifies the usable-data gate as a duration-composition choice, not a
    similarity-tuned one — see CLAUDE.md, "Settled analysis decisions". Reuses
    the same pair-binning machinery as `cross_context_summary`, but with
    per-session usable duration standing in for a similarity matrix: the pair
    "value" is `min(usable_i, usable_j)`, so the median row is the pairwise
    minimum, not a mean. `group_column` matches `cross_context_summary`'s
    same-/different-task axis (e.g. `"title"` for the movies domain).
    """
    bin_labels = pair_bin_labels(group_column)
    usable = index_frame["usable_duration_sec"].fillna(index_frame["duration_sec"]).to_numpy()
    rows = []
    for gate_name in GATES:
        row_mask = _gate_mask_for(index_frame, min_usable_seconds, gate_name)
        sub_index = index_frame[row_mask].reset_index(drop=True)
        sub_usable = usable[row_mask]
        if len(sub_index) < 2:
            continue
        pair_min_duration = np.minimum.outer(sub_usable, sub_usable)
        bins_ = pair_bins(sub_index, group_column=group_column, group_name=group_column)
        values_by_bin = collect_pair_values(pair_min_duration, bins_, bin_labels=bin_labels)
        summary = summarize_bins(values_by_bin, bin_labels=bin_labels)
        summary["gate"] = gate_name
        summary["n_sessions"] = len(sub_index)
        rows.append(summary)

    result = pd.concat(rows, ignore_index=True)
    result = result.rename(columns={"n": "n_pairs", "median": "median_min_duration_sec"})
    return result[["gate", "bin", "n_pairs", "median_min_duration_sec", "q25", "q75", "n_sessions"]]


def cross_context_summary(paths, network_order, measure, min_usable_seconds, n_bins=60,
                           group_column="dataset", title_frame=None):
    """Analysis B: same-/different-subject x same-/different-dataset, gated and ungated.

    `group_column`/`title_frame` let a caller narrow the same-/different-task
    axis below "dataset" — used by `domain_cross_context_summary` for the
    movies domain, where `friends` and `movie10` need title-level (season or
    movie) task identity, not just "friends vs. movie10". When `title_frame`
    is given (columns `dataset, subject, session, title, n_titles`, see
    `analysis.domain_titles.session_titles`), sessions are joined against it
    via `attach_titles` — dropping unmatched and boundary sessions — before
    binning by `group_column` (normally `"title"` in that case).

    Returns `{"cross_context": frame, "histograms": frame, "duration_balance": frame}`.
    """
    bin_labels = pair_bin_labels(group_column)
    bin_rows = []
    hist_rows = []
    balance_frame = None
    for network in network_order:
        index_frame, matrix = load_stacked_measure(paths, measure, network)
        if title_frame is not None:
            index_frame["_row"] = np.arange(len(index_frame))
            index_frame, _dropped = attach_titles(index_frame, title_frame)
            matrix = matrix[index_frame["_row"].to_numpy()]
            index_frame = index_frame.drop(columns="_row").reset_index(drop=True)
        if balance_frame is None:
            balance_frame = duration_balance(index_frame, min_usable_seconds, group_column)
        z_matrix = fisher_z(matrix)
        for gate_name in GATES:
            row_mask = _gate_mask_for(index_frame, min_usable_seconds, gate_name)
            sub_index = index_frame[row_mask].reset_index(drop=True)
            sub_matrix = z_matrix[row_mask]
            if len(sub_index) < 2:
                continue
            valid = common_edge_mask(sub_matrix)
            similarity = similarity_matrix(sub_matrix)
            bins_ = pair_bins(sub_index, group_column=group_column, group_name=group_column)
            values_by_bin = collect_pair_values(similarity, bins_, bin_labels=bin_labels)

            summary = summarize_bins(values_by_bin, bin_labels=bin_labels)
            summary["network"] = network
            summary["gate"] = gate_name
            summary["measure"] = measure
            summary["n_edges_valid"] = int(valid.sum())
            summary["n_edges_total"] = int(valid.size)
            bin_rows.append(summary)

            for bin_label, values in values_by_bin.items():
                hist = similarity_histogram(values, n_bins)
                hist["network"] = network
                hist["gate"] = gate_name
                hist["bin"] = bin_label
                hist["analysis"] = "cross_context"
                hist_rows.append(hist)

    return {
        "cross_context": pd.concat(bin_rows, ignore_index=True),
        "histograms": pd.concat(hist_rows, ignore_index=True),
        "duration_balance": balance_frame,
    }


# Robustness-tier check on Analysis B's generalizability (CLAUDE.md, "Respect
# the analysis hierarchy"): does the within-task/between-task contrast still
# hold when "between-task" means a much more homogeneous swap than "friends
# vs. retinotopy"? `movies` uses title-level task identity (friends season or
# movie10 title — see `analysis.domain_titles`) since `friends`/`movie10`
# alone would collapse to a two-dataset contrast; `videogames`/`stories` reuse
# dataset-level identity, exactly like the global cross-context analysis,
# just restricted to fewer datasets.
DOMAIN_DATASETS = {
    "movies": ("friends", "movie10"),
    "videogames": ("mario", "mario3", "mariostars", "shinobi"),
    "stories": ("harrypotter", "petit-prince"),
}


def _paths_for_datasets(paths, parcellation, datasets):
    names = set(datasets)
    return [p for p in paths if p.stem.rsplit(f"_{parcellation}", 1)[0] in names]


def domain_cross_context_summary(paths, parcellation, cneuromod_root, network_order, measure,
                                  min_usable_seconds, n_bins=60):
    """Analysis B, restricted one domain at a time to `DOMAIN_DATASETS`.

    A domain with no connectome file present in `paths` is skipped entirely
    (e.g. the smoke run, which only has `movie10`, contributes nothing to
    `videogames`/`stories`). Returns `{"cross_context", "histograms",
    "duration_balance"}`, each with an added `domain` column, concatenated
    across whichever domains are present.
    """
    results = {"cross_context": [], "histograms": [], "duration_balance": []}
    for domain, datasets in DOMAIN_DATASETS.items():
        domain_paths = _paths_for_datasets(paths, parcellation, datasets)
        if not domain_paths:
            continue
        if domain == "movies":
            title_frame = session_titles(cneuromod_root, parcellation, datasets)
            domain_result = cross_context_summary(
                domain_paths, network_order, measure, min_usable_seconds, n_bins,
                group_column="title", title_frame=title_frame,
            )
        else:
            domain_result = cross_context_summary(
                domain_paths, network_order, measure, min_usable_seconds, n_bins,
            )
        for key in results:
            frame = domain_result[key].copy()
            frame["domain"] = domain
            results[key].append(frame)

    empty = pd.DataFrame(columns=["domain"])
    return {
        key: (pd.concat(frames, ignore_index=True) if frames else empty)
        for key, frames in results.items()
    }


def _lag_stats(group, lag_column):
    stats = group.groupby(lag_column)["similarity"].agg(
        n="count", median="median",
        q25=lambda s: np.percentile(s, 25), q75=lambda s: np.percentile(s, 75),
    ).reset_index().rename(columns={lag_column: "lag_value"})
    return stats


def longitudinal_summary(friends_path, cneuromod_root, parcellation, network_order,
                          measure, min_usable_seconds, n_bins=60):
    """Analysis A: `friends` only, same-/different-subject x same-/different-season,
    plus similarity-vs-lag curves (season lag and binned session gap).

    Returns `{"longitudinal_bins", "longitudinal_lag", "histograms", "dropped",
    "n_sessions"}`. Season is re-derived from source h5 key names, never
    recomputed from timeseries — see `analysis.friends_seasons`.
    """
    full_index = load_index(friends_path)
    full_index["_row"] = np.arange(len(full_index))
    season_frame = session_seasons(cneuromod_root, parcellation)
    filtered_index, dropped = attach_seasons(full_index, season_frame)
    row_indices = filtered_index["_row"].to_numpy()
    season_bin_labels = pair_bin_labels("season")

    bin_rows = []
    lag_rows = []
    hist_rows = []

    for network in network_order:
        array = load_measure(friends_path, measure, network)
        matrix = array[row_indices]
        z_matrix = fisher_z(matrix)

        for gate_name in GATES:
            row_mask = _gate_mask_for(filtered_index, min_usable_seconds, gate_name)
            sub_index = filtered_index[row_mask].reset_index(drop=True)
            sub_matrix = z_matrix[row_mask]
            if len(sub_index) < 2:
                continue
            valid = common_edge_mask(sub_matrix)
            similarity = similarity_matrix(sub_matrix)

            bins_ = pair_bins(sub_index, group_column="season", group_name="season")
            values_by_bin = collect_pair_values(similarity, bins_, bin_labels=season_bin_labels)
            summary = summarize_bins(values_by_bin, bin_labels=season_bin_labels)
            summary["network"] = network
            summary["gate"] = gate_name
            summary["measure"] = measure
            summary["n_edges_valid"] = int(valid.sum())
            summary["n_edges_total"] = int(valid.size)
            bin_rows.append(summary)

            for bin_label, values in values_by_bin.items():
                hist = similarity_histogram(values, n_bins)
                hist["network"] = network
                hist["gate"] = gate_name
                hist["bin"] = bin_label
                hist["analysis"] = "longitudinal"
                hist_rows.append(hist)

            pairs = pair_frame(similarity, sub_index, columns=("subject", "season", "session"))
            pairs["season_lag"] = (
                pairs["season_i"].map(season_index) - pairs["season_j"].map(season_index)
            ).abs()
            pairs["session_gap"] = (
                pairs["session_i"].astype(int) - pairs["session_j"].astype(int)
            ).abs()

            for pair_type, group in (
                ("within-subject", pairs[pairs["subject_i"] == pairs["subject_j"]]),
                ("between-subject", pairs[pairs["subject_i"] != pairs["subject_j"]]),
            ):
                season_stats = _lag_stats(group, "season_lag")
                season_stats["lag_type"] = "season"
                if len(group) >= 6:
                    gap_bin = pd.qcut(group["session_gap"], q=6, duplicates="drop")
                    session_stats = _lag_stats(group.assign(_gap_bin=gap_bin.cat.codes), "_gap_bin")
                    session_stats["lag_type"] = "session_gap_decile"
                else:
                    session_stats = pd.DataFrame(
                        columns=["lag_value", "n", "median", "q25", "q75", "lag_type"]
                    )
                lag_stats = pd.concat([season_stats, session_stats], ignore_index=True)
                lag_stats["network"] = network
                lag_stats["gate"] = gate_name
                lag_stats["measure"] = measure
                lag_stats["pair_type"] = pair_type
                lag_rows.append(lag_stats)

    return {
        "longitudinal_bins": pd.concat(bin_rows, ignore_index=True),
        "longitudinal_lag": pd.concat(lag_rows, ignore_index=True),
        "histograms": pd.concat(hist_rows, ignore_index=True) if hist_rows else pd.DataFrame(),
        "dropped": dropped,
        "n_sessions": len(filtered_index),
    }
