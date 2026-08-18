"""Motion-stratified robustness check (CLAUDE.md, "Respect the analysis
hierarchy" — robustness tier, QC dependence): does session-to-session
connectome similarity depend on head motion, and does claim 2's
within-task > between-task ordering survive when motion is held down?

No session in the gated population reaches `fd_mean > 0.3` (max 0.248), so
this is a *relative* split, not an absolute-threshold one, and `fd_mean`
coverage (mario, harrypotter both entirely unmatched upstream) rules out the
domain stratification — this runs pooled over all FD-covered datasets. See
CLAUDE.md, "Motion stratification", for the full empirical basis (motion is
subject- and dataset-specific, `fd_mean` vs `tsnr` r=-0.68, `fd_mean` vs
usable duration r=-0.065).

Pure functions, no invoke context — follows the `analysis/group_stats.py`
precedent. `run-motion-strata` (tasks.py) is the only caller.
"""

import numpy as np
import pandas as pd

from analysis.group_stats import similarity_histogram
from analysis.similarity import (
    collect_pair_values,
    fisher_z,
    load_stacked_measure,
    similarity_matrix,
    summarize_bins,
)

# (split name, group-by columns, minimum covered sessions per group before it
# is dropped rather than stratified). "cell" is the primary split — orthogonal
# to subject and dataset by construction, since motion is strongly specific to
# both (CLAUDE.md, "Motion stratification"). "subject" is the plain
# within-subject median split, kept as a secondary comparison in the same
# tables via the `split` column — not a second code path.
MOTION_SPLITS = (
    ("cell", ("subject", "dataset"), 4),
    ("subject", ("subject",), 4),
)


def qc_covered_mask(index_frame, min_usable_seconds):
    """Gated (`usable_duration_sec >= min_usable_seconds`) AND `fd_mean` present.

    This is the population every function here stratifies over — never the
    raw gated population, since `fd_mean` coverage is itself partial (mario,
    harrypotter: 0%; see CLAUDE.md, "The QC measures asset"). Tolerates a
    missing `fd_mean` column (e.g. a caller with no QC join at all) by
    treating every row as uncovered, rather than raising.
    """
    usable = index_frame["usable_duration_sec"].fillna(index_frame["duration_sec"])
    gated = usable >= min_usable_seconds
    if "fd_mean" not in index_frame.columns:
        return np.zeros(len(index_frame), dtype=bool)
    return (gated & index_frame["fd_mean"].notna()).to_numpy()


def assign_motion_strata(index_frame, split_by=("subject", "dataset"), min_cell=4):
    """Add `motion_stratum` (`"low"`/`"high"`/`None`): below/above the median
    `fd_mean` within each `split_by` group.

    `None` where `fd_mean` is missing, or the group has fewer than `min_cell`
    covered sessions — a too-small group cannot be split meaningfully, so it
    is dropped rather than assigned. Ties go to `"low"` (`<=` median).
    """
    frame = index_frame.copy()
    frame["motion_stratum"] = pd.array([None] * len(frame), dtype=object)
    if "fd_mean" not in frame.columns:
        return frame
    covered = frame["fd_mean"].notna()
    for _key, group in frame[covered].groupby(list(split_by), sort=False):
        if len(group) < min_cell:
            continue
        median = group["fd_mean"].median()
        labels = np.where(group["fd_mean"].to_numpy() <= median, "low", "high")
        frame.loc[group.index, "motion_stratum"] = labels
    return frame


def motion_pair_bin_labels():
    """The six `"{motion-pair} / {within|between}-task"` labels."""
    motion_bins = ("low-low", "low-high", "high-high")
    task_bins = ("within-task", "between-task")
    return [f"{motion}/{task}" for motion in motion_bins for task in task_bins]


def motion_pair_bins(index_frame, group_column="dataset"):
    """`(n, n)` bin-label array from motion-stratum pairing x task equality,
    restricted to within-subject pairs — mirrors `similarity.pair_bins`'s
    return contract so `collect_pair_values`/`summarize_bins` reuse it
    unchanged.
    """
    subject = index_frame["subject"].to_numpy()
    stratum = index_frame["motion_stratum"].to_numpy()
    group = index_frame[group_column].to_numpy()

    n = len(index_frame)
    same_subject = subject[:, None] == subject[None, :]
    same_group = group[:, None] == group[None, :]
    stratum_i = stratum[:, None]
    stratum_j = stratum[None, :]
    low_low = (stratum_i == "low") & (stratum_j == "low")
    high_high = (stratum_i == "high") & (stratum_j == "high")
    low_high = ~low_low & ~high_high

    labels = np.empty((n, n), dtype=object)
    labels[low_low & same_group] = "low-low/within-task"
    labels[low_low & ~same_group] = "low-low/between-task"
    labels[low_high & same_group] = "low-high/within-task"
    labels[low_high & ~same_group] = "low-high/between-task"
    labels[high_high & same_group] = "high-high/within-task"
    labels[high_high & ~same_group] = "high-high/between-task"

    triu_mask = np.triu(np.ones((n, n), dtype=bool), k=1) & same_subject
    return labels, triu_mask


def motion_summary(paths, network_order, measure, min_usable_seconds, n_bins=60,
                    group_column="dataset", splits=MOTION_SPLITS):
    """Per network x split x motion-task bin similarity summary, plus histograms.

    Restricted to the QC-covered population (`qc_covered_mask`) throughout.
    Returns `{"motion_bins": frame, "histograms": frame}`.
    """
    bin_labels = motion_pair_bin_labels()
    bin_rows = []
    hist_rows = []

    for network in network_order:
        index_frame, matrix = load_stacked_measure(paths, measure, network)
        qc_mask = qc_covered_mask(index_frame, min_usable_seconds)
        qc_index = index_frame[qc_mask].reset_index(drop=True)
        z_matrix = fisher_z(matrix[qc_mask])
        if len(qc_index) < 2:
            continue

        for split_name, split_by, min_cell in splits:
            stratum_frame = assign_motion_strata(qc_index, split_by=split_by, min_cell=min_cell)
            valid = stratum_frame["motion_stratum"].notna().to_numpy()
            sub_index = stratum_frame[valid].reset_index(drop=True)
            sub_matrix = z_matrix[valid]
            if len(sub_index) < 2:
                continue

            similarity = similarity_matrix(sub_matrix)
            bins_ = motion_pair_bins(sub_index, group_column=group_column)
            values_by_bin = collect_pair_values(similarity, bins_, bin_labels=bin_labels)

            summary = summarize_bins(values_by_bin, bin_labels=bin_labels)
            summary["network"] = network
            summary["split"] = split_name
            summary["measure"] = measure
            summary["n_sessions"] = len(sub_index)
            bin_rows.append(summary)

            for bin_label, values in values_by_bin.items():
                hist = similarity_histogram(values, n_bins)
                hist["network"] = network
                hist["split"] = split_name
                hist["bin"] = bin_label
                hist["analysis"] = "motion"
                hist_rows.append(hist)

    empty_bins = pd.DataFrame(columns=[
        "bin", "n", "median", "q25", "q75", "mean", "sd",
        "network", "split", "measure", "n_sessions",
    ])
    empty_hist = pd.DataFrame(columns=[
        "bin_left", "bin_right", "count", "network", "split", "bin", "analysis",
    ])
    return {
        "motion_bins": pd.concat(bin_rows, ignore_index=True) if bin_rows else empty_bins,
        "histograms": pd.concat(hist_rows, ignore_index=True) if hist_rows else empty_hist,
    }


def motion_balance(index_frame, min_usable_seconds, group_column="dataset", splits=MOTION_SPLITS):
    """Per split x motion-task bin: pair-min usable duration AND pair-min tSNR.

    Modelled directly on `group_stats.duration_balance`, extended with a
    pair-min `tsnr` column since the motion stratum is substantially a tSNR
    stratum too (r=-0.68 — CLAUDE.md, "Motion stratification") and both must
    be reported together, never as independent axes. Restricted to the
    QC-covered population throughout, like every other motion table — never
    the raw `index_frame`, which would let sessions failing the usable-data
    gate into the stratification.
    """
    qc_mask = qc_covered_mask(index_frame, min_usable_seconds)
    qc_index = index_frame[qc_mask].reset_index(drop=True)
    bin_labels = motion_pair_bin_labels()
    usable = qc_index["usable_duration_sec"].fillna(qc_index["duration_sec"]).to_numpy()
    tsnr = qc_index["tsnr"].to_numpy()

    rows = []
    for split_name, split_by, min_cell in splits:
        stratum_frame = assign_motion_strata(qc_index, split_by=split_by, min_cell=min_cell)
        valid = stratum_frame["motion_stratum"].notna().to_numpy()
        sub_index = stratum_frame[valid].reset_index(drop=True)
        if len(sub_index) < 2:
            continue
        sub_usable = usable[valid]
        sub_tsnr = tsnr[valid]

        pair_min_duration = np.minimum.outer(sub_usable, sub_usable)
        pair_min_tsnr = np.minimum.outer(sub_tsnr, sub_tsnr)
        bins_ = motion_pair_bins(sub_index, group_column=group_column)
        duration_by_bin = collect_pair_values(pair_min_duration, bins_, bin_labels=bin_labels)
        tsnr_by_bin = collect_pair_values(pair_min_tsnr, bins_, bin_labels=bin_labels)

        duration_summary = summarize_bins(duration_by_bin, bin_labels=bin_labels)
        duration_summary = duration_summary.rename(
            columns={"n": "n_pairs", "median": "median_min_duration_sec"}
        )[["bin", "n_pairs", "median_min_duration_sec"]]
        tsnr_summary = summarize_bins(tsnr_by_bin, bin_labels=bin_labels)
        tsnr_summary = tsnr_summary.rename(columns={"median": "median_min_tsnr"})
        tsnr_summary = tsnr_summary[["bin", "median_min_tsnr"]]

        summary = duration_summary.merge(tsnr_summary, on="bin")
        summary["split"] = split_name
        summary["n_sessions"] = len(sub_index)
        rows.append(summary)

    empty = pd.DataFrame(columns=[
        "bin", "n_pairs", "median_min_duration_sec", "median_min_tsnr", "split", "n_sessions",
    ])
    return pd.concat(rows, ignore_index=True) if rows else empty


def _pure_motion_masks(stratum, triu_mask):
    """Low-low / high-high pair masks, pooled over both task bins (motion axis only).

    `triu_mask` already restricts to within-subject pairs (the caller builds
    it that way), so this only adds the motion-stratum equality.
    """
    stratum_i = stratum[:, None]
    stratum_j = stratum[None, :]
    low_low = triu_mask & (stratum_i == "low") & (stratum_j == "low")
    high_high = triu_mask & (stratum_i == "high") & (stratum_j == "high")
    return low_low, high_high


def _subject_replication(similarity, stratum, subject, triu_mask):
    """`(n_replicating, n_subjects)`: subjects where `median(low-low) >
    median(high-high)` holds individually, out of subjects with both bins
    populated (CLAUDE.md, "Motion stratification" — per-subject replication,
    the six-participants inference rule).
    """
    n_replicating = 0
    n_subjects = 0
    for one_subject in sorted(set(subject)):
        subject_mask = (subject[:, None] == one_subject) & (subject[None, :] == one_subject)
        low_low, high_high = _pure_motion_masks(stratum, triu_mask & subject_mask)
        low_low_values = similarity[low_low]
        high_high_values = similarity[high_high]
        if len(low_low_values) == 0 or len(high_high_values) == 0:
            continue
        n_subjects += 1
        if np.median(low_low_values) > np.median(high_high_values):
            n_replicating += 1
    return n_replicating, n_subjects


def motion_permutation(paths, network_order, measure, min_usable_seconds,
                        n_permutations=1000, seed=0, split_by=("subject", "dataset"),
                        min_cell=4):
    """Two-sided permutation test on `median(low-low) - median(high-high)` per network,
    plus per-subject replication (`n_subjects_replicating`/`n_subjects_total`):
    with only six participants, inference must show the effect replicates
    across individuals, not rely on the pooled permutation p-value alone
    (CLAUDE.md, "Scientific objective").

    Shuffles `motion_stratum` within each `split_by` cell (the exchangeability
    that stratification buys — CLAUDE.md, "Motion stratification"), pooled
    across both task bins since motion, not task, is the axis under test here.
    Restricted to within-subject pairs, like every other motion table. The
    similarity matrix itself never changes across permutations, only which
    pairs count as low-low/high-high, so this reuses one `similarity_matrix`
    call per network rather than recomputing it `n_permutations` times.
    """
    rng = np.random.default_rng(seed)
    rows = []

    for network in network_order:
        index_frame, matrix = load_stacked_measure(paths, measure, network)
        qc_mask = qc_covered_mask(index_frame, min_usable_seconds)
        qc_index = index_frame[qc_mask].reset_index(drop=True)
        z_matrix = fisher_z(matrix[qc_mask])

        stratum_frame = assign_motion_strata(qc_index, split_by=split_by, min_cell=min_cell)
        valid = stratum_frame["motion_stratum"].notna().to_numpy()
        sub_index = stratum_frame[valid].reset_index(drop=True)
        sub_matrix = z_matrix[valid]
        if len(sub_index) < 4:
            rows.append({
                "network": network, "observed_diff": np.nan,
                "p_value": np.nan, "n_permutations": n_permutations,
                "n_subjects_replicating": 0, "n_subjects_total": 0,
            })
            continue

        subject = sub_index["subject"].to_numpy()
        same_subject = subject[:, None] == subject[None, :]
        n_sessions = len(sub_index)
        triu_mask = np.triu(np.ones((n_sessions, n_sessions), dtype=bool), k=1) & same_subject
        similarity = similarity_matrix(sub_matrix)

        group_keys = pd.Series(
            list(zip(*[sub_index[column] for column in split_by], strict=True))
        )
        stratum = sub_index["motion_stratum"].to_numpy()

        def _observed_diff(stratum_values):
            low_low, high_high = _pure_motion_masks(stratum_values, triu_mask)
            low_low_values = similarity[low_low]
            high_high_values = similarity[high_high]
            if len(low_low_values) == 0 or len(high_high_values) == 0:
                return np.nan
            return float(np.median(low_low_values) - np.median(high_high_values))

        observed_diff = _observed_diff(stratum)

        null_diffs = np.empty(n_permutations)
        for permutation_index in range(n_permutations):
            shuffled = (
                pd.Series(stratum)
                .groupby(group_keys, sort=False)
                .transform(lambda s: rng.permutation(s.to_numpy()))
                .to_numpy()
            )
            null_diffs[permutation_index] = _observed_diff(shuffled)

        finite_null = null_diffs[np.isfinite(null_diffs)]
        if np.isnan(observed_diff) or len(finite_null) == 0:
            p_value = np.nan
        else:
            p_value = float(np.mean(np.abs(finite_null) >= abs(observed_diff)))

        n_replicating, n_subjects = _subject_replication(similarity, stratum, subject, triu_mask)

        rows.append({
            "network": network, "observed_diff": observed_diff,
            "p_value": p_value, "n_permutations": n_permutations,
            "n_subjects_replicating": n_replicating, "n_subjects_total": n_subjects,
        })

    return pd.DataFrame(rows)


def motion_sessions_table(index_frame, min_usable_seconds, splits=MOTION_SPLITS):
    """One row per QC-covered session: entities, `fd_mean`, `tsnr`,
    `usable_duration_sec`, plus one `motion_stratum_{split_name}` column per
    entry in `splits` — for auditability.
    """
    usable = index_frame["usable_duration_sec"].fillna(index_frame["duration_sec"])
    qc_mask = qc_covered_mask(index_frame, min_usable_seconds)
    result = index_frame.loc[
        qc_mask, ["dataset", "subject", "session", "fd_mean", "tsnr"]
    ].reset_index(drop=True)
    result["usable_duration_sec"] = usable[qc_mask].reset_index(drop=True)

    sub_index = index_frame[qc_mask].reset_index(drop=True)
    for split_name, split_by, min_cell in splits:
        stratum_frame = assign_motion_strata(sub_index, split_by=split_by, min_cell=min_cell)
        result[f"motion_stratum_{split_name}"] = stratum_frame["motion_stratum"].to_numpy()

    return result
