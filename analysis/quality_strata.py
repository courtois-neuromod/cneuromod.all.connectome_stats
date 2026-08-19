"""Shared machinery for QC-stratified robustness checks (CLAUDE.md, "Respect
the analysis hierarchy" — robustness tier, QC dependence).

Two analyses are built on this core, each asking the same question of a
different acquisition-quality axis: does session-to-session connectome
similarity depend on it, and does claim 2's within-task > between-task
ordering survive when it is held at its better value?

- `analysis/motion_strata.py` — head motion (`fd_mean`, better = *low*).
- `analysis/tsnr_strata.py` — temporal SNR (`tsnr`, better = *high*).

Everything here is parameterized by the QC column, the name of the stratum
column it produces, and which stratum value is the *good* one, so the two
analyses are configuration rather than two code paths. `observed_diff` is
always `median(good-good) - median(bad-bad)`, so a positive value means
"better acquisition quality, higher similarity" on either axis.

Pure functions, no invoke context — follows the `analysis/group_stats.py`
precedent.
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
# to subject and dataset by construction, since both QC axes are strongly
# specific to both. "subject" is the plain within-subject median split, kept as
# a secondary comparison in the same tables via the `split` column.
DEFAULT_SPLITS = (
    ("cell", ("subject", "dataset"), 4),
    ("subject", ("subject",), 4),
)

# The column every analysis defines its covered population by. Both axes have
# identical coverage in practice (246/246 gated sessions), and sharing one
# definition is what makes the per-axis gates in `group_stats.GATES` directly
# comparable — see CLAUDE.md, "tSNR stratification".
COVERAGE_COLUMN = "fd_mean"

TASK_BINS = ("within-task", "between-task")


def qc_covered_mask(index_frame, min_usable_seconds, column=COVERAGE_COLUMN):
    """Gated (`usable_duration_sec >= min_usable_seconds`) AND `column` present.

    This is the population every function here stratifies over — never the
    raw gated population, since QC coverage is itself partial (mario,
    harrypotter: 0%; see CLAUDE.md, "The QC measures asset"). Tolerates a
    missing `column` (e.g. a caller with no QC join at all) by treating every
    row as uncovered, rather than raising.
    """
    usable = index_frame["usable_duration_sec"].fillna(index_frame["duration_sec"])
    gated = usable >= min_usable_seconds
    if column not in index_frame.columns:
        return np.zeros(len(index_frame), dtype=bool)
    return (gated & index_frame[column].notna()).to_numpy()


def _cell_residuals(values, predictor):
    """`values` with a within-cell OLS fit on `predictor` removed.

    Falls back to mean-centering when the predictor has no variance or the
    cell is too small to fit a slope — a degenerate cell must still yield a
    usable ordering, not NaN.
    """
    finite = np.isfinite(values) & np.isfinite(predictor)
    result = np.full(len(values), np.nan)
    if finite.sum() < 3 or np.std(predictor[finite]) == 0:
        result[finite] = values[finite] - values[finite].mean()
        return result
    slope, intercept = np.polyfit(predictor[finite], values[finite], 1)
    result[finite] = values[finite] - (slope * predictor[finite] + intercept)
    return result


def assign_strata(index_frame, column, stratum_column, split_by=("subject", "dataset"),
                  min_cell=4, residualize_on=None):
    """Add `stratum_column` (`"low"`/`"high"`/`None`): below/above the median
    `column` within each `split_by` group.

    `None` where `column` is missing, or the group has fewer than `min_cell`
    covered sessions — a too-small group cannot be split meaningfully, so it
    is dropped rather than assigned. Ties go to `"low"` (`<=` median).

    With `residualize_on` set, the split is on `column` residualized on that
    predictor *within the same group* (`_cell_residuals`), which makes the
    stratum orthogonal to the predictor by construction rather than by
    assumption — see CLAUDE.md, "tSNR stratification", for why that matters
    when the two QC axes correlate at r = -0.68.
    """
    frame = index_frame.copy()
    frame[stratum_column] = pd.array([None] * len(frame), dtype=object)
    if column not in frame.columns:
        return frame
    if residualize_on is not None and residualize_on not in frame.columns:
        return frame
    covered = frame[column].notna()
    for _key, group in frame[covered].groupby(list(split_by), sort=False):
        if len(group) < min_cell:
            continue
        values = group[column].to_numpy(dtype=float)
        if residualize_on is not None:
            values = _cell_residuals(values, group[residualize_on].to_numpy(dtype=float))
        median = np.nanmedian(values)
        labels = np.where(values <= median, "low", "high")
        frame.loc[group.index, stratum_column] = labels
    return frame


def stratum_pair_names(good_stratum):
    """The three stratum pairings, good-good first, mixed always `"low-high"`."""
    bad_stratum = "high" if good_stratum == "low" else "low"
    return (f"{good_stratum}-{good_stratum}", "low-high", f"{bad_stratum}-{bad_stratum}")


def pair_bin_labels(good_stratum):
    """The six `"{stratum-pair}/{within|between}-task"` labels, good-good first."""
    return [
        f"{pairing}/{task}"
        for pairing in stratum_pair_names(good_stratum)
        for task in TASK_BINS
    ]


def pair_bins(index_frame, stratum_column, group_column="dataset", good_stratum="low"):
    """`(n, n)` bin-label array from stratum pairing x task equality, restricted
    to within-subject pairs — mirrors `similarity.pair_bins`'s return contract
    so `collect_pair_values`/`summarize_bins` reuse it unchanged.
    """
    subject = index_frame["subject"].to_numpy()
    stratum = index_frame[stratum_column].to_numpy()
    group = index_frame[group_column].to_numpy()

    n = len(index_frame)
    same_subject = subject[:, None] == subject[None, :]
    same_group = group[:, None] == group[None, :]
    low_low = (stratum[:, None] == "low") & (stratum[None, :] == "low")
    high_high = (stratum[:, None] == "high") & (stratum[None, :] == "high")
    mixed = ~low_low & ~high_high

    by_name = {"low-low": low_low, "high-high": high_high, "low-high": mixed}
    labels = np.empty((n, n), dtype=object)
    for pairing in stratum_pair_names(good_stratum):
        labels[by_name[pairing] & same_group] = f"{pairing}/within-task"
        labels[by_name[pairing] & ~same_group] = f"{pairing}/between-task"

    triu_mask = np.triu(np.ones((n, n), dtype=bool), k=1) & same_subject
    return labels, triu_mask


def _definition_passes(definitions):
    """Normalize the `stratum_def` axis to `[(def_name_or_None, residualize_on)]`.

    `None` means a single unnamed definition — the analysis emits no
    `stratum_def` column at all, which is what keeps the motion tables to the
    shape they had before this core was extracted.
    """
    return [(None, None)] if definitions is None else list(definitions)


def _tag(frame, def_name):
    if def_name is not None:
        frame["stratum_def"] = def_name
    return frame


def strata_summary(paths, network_order, measure, min_usable_seconds, column,
                   stratum_column, good_stratum, analysis, n_bins=60,
                   group_column="dataset", splits=DEFAULT_SPLITS, definitions=None,
                   coverage_column=COVERAGE_COLUMN):
    """Per network x definition x split x bin similarity summary, plus histograms.

    Restricted to the QC-covered population (`qc_covered_mask`) throughout.
    Returns `{"bins": frame, "histograms": frame}`.
    """
    bin_labels = pair_bin_labels(good_stratum)
    bin_rows = []
    hist_rows = []

    for network in network_order:
        index_frame, matrix = load_stacked_measure(paths, measure, network)
        qc_mask = qc_covered_mask(index_frame, min_usable_seconds, column=coverage_column)
        qc_index = index_frame[qc_mask].reset_index(drop=True)
        z_matrix = fisher_z(matrix[qc_mask])
        if len(qc_index) < 2:
            continue

        for def_name, residualize_on in _definition_passes(definitions):
            for split_name, split_by, min_cell in splits:
                stratum_frame = assign_strata(
                    qc_index, column, stratum_column, split_by=split_by,
                    min_cell=min_cell, residualize_on=residualize_on,
                )
                valid = stratum_frame[stratum_column].notna().to_numpy()
                sub_index = stratum_frame[valid].reset_index(drop=True)
                sub_matrix = z_matrix[valid]
                if len(sub_index) < 2:
                    continue

                similarity = similarity_matrix(sub_matrix)
                bins_ = pair_bins(sub_index, stratum_column, group_column=group_column,
                                  good_stratum=good_stratum)
                values_by_bin = collect_pair_values(similarity, bins_, bin_labels=bin_labels)

                summary = summarize_bins(values_by_bin, bin_labels=bin_labels)
                summary["network"] = network
                summary["split"] = split_name
                summary["measure"] = measure
                summary["n_sessions"] = len(sub_index)
                bin_rows.append(_tag(summary, def_name))

                for bin_label, values in values_by_bin.items():
                    hist = similarity_histogram(values, n_bins)
                    hist["network"] = network
                    hist["split"] = split_name
                    hist["bin"] = bin_label
                    hist["analysis"] = analysis
                    hist_rows.append(_tag(hist, def_name))

    bin_columns = ["bin", "n", "median", "q25", "q75", "mean", "sd",
                   "network", "split", "measure", "n_sessions"]
    hist_columns = ["bin_left", "bin_right", "count", "network", "split", "bin", "analysis"]
    if definitions is not None:
        bin_columns.append("stratum_def")
        hist_columns.append("stratum_def")
    return {
        "bins": pd.concat(bin_rows, ignore_index=True) if bin_rows
                else pd.DataFrame(columns=bin_columns),
        "histograms": pd.concat(hist_rows, ignore_index=True) if hist_rows
                      else pd.DataFrame(columns=hist_columns),
    }


def strata_balance(index_frame, min_usable_seconds, column, stratum_column, good_stratum,
                   balance_columns, group_column="dataset", splits=DEFAULT_SPLITS,
                   definitions=None, coverage_column=COVERAGE_COLUMN):
    """Per definition x split x bin: a pair-extremum summary of each balance column.

    Modelled on `group_stats.duration_balance`. `balance_columns` is
    `[(source, output_name, "min"|"max")]`, where source `"usable"` means
    `usable_duration_sec` falling back to `duration_sec`. The direction picks
    the *worse* end of each pair, so every column reports what actually limits
    the pair. Restricted to the QC-covered population throughout — never the
    raw `index_frame`, which would let sessions failing the usable-data gate
    into the stratification.
    """
    qc_mask = qc_covered_mask(index_frame, min_usable_seconds, column=coverage_column)
    qc_index = index_frame[qc_mask].reset_index(drop=True)
    bin_labels = pair_bin_labels(good_stratum)
    usable = qc_index["usable_duration_sec"].fillna(qc_index["duration_sec"])

    def _source_values(source):
        return (usable if source == "usable" else qc_index[source]).to_numpy(dtype=float)

    sources = {source: _source_values(source) for source, _, _ in balance_columns}

    rows = []
    for def_name, residualize_on in _definition_passes(definitions):
        for split_name, split_by, min_cell in splits:
            stratum_frame = assign_strata(
                qc_index, column, stratum_column, split_by=split_by,
                min_cell=min_cell, residualize_on=residualize_on,
            )
            valid = stratum_frame[stratum_column].notna().to_numpy()
            sub_index = stratum_frame[valid].reset_index(drop=True)
            if len(sub_index) < 2:
                continue
            bins_ = pair_bins(sub_index, stratum_column, group_column=group_column,
                              good_stratum=good_stratum)

            summary = None
            for source, output_name, direction in balance_columns:
                values = sources[source][valid]
                outer = np.minimum.outer if direction == "min" else np.maximum.outer
                by_bin = collect_pair_values(outer(values, values), bins_, bin_labels=bin_labels)
                part = summarize_bins(by_bin, bin_labels=bin_labels)
                if summary is None:
                    part = part.rename(columns={"n": "n_pairs", "median": output_name})
                    summary = part[["bin", "n_pairs", output_name]]
                else:
                    part = part.rename(columns={"median": output_name})[["bin", output_name]]
                    summary = summary.merge(part, on="bin")

            summary["split"] = split_name
            summary["n_sessions"] = len(sub_index)
            rows.append(_tag(summary, def_name))

    columns = ["bin", "n_pairs", *[name for _, name, _ in balance_columns], "split", "n_sessions"]
    if definitions is not None:
        columns.append("stratum_def")
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=columns)


def _pure_strata_masks(stratum, triu_mask, good_stratum):
    """Good-good / bad-bad pair masks, pooled over both task bins (quality axis only).

    `triu_mask` already restricts to within-subject pairs (the caller builds
    it that way), so this only adds the stratum equality.
    """
    bad_stratum = "high" if good_stratum == "low" else "low"
    good = triu_mask & (stratum[:, None] == good_stratum) & (stratum[None, :] == good_stratum)
    bad = triu_mask & (stratum[:, None] == bad_stratum) & (stratum[None, :] == bad_stratum)
    return good, bad


def _subject_replication(similarity, stratum, subject, triu_mask, good_stratum):
    """`(n_replicating, n_subjects)`: subjects where `median(good-good) >
    median(bad-bad)` holds individually, out of subjects with both bins
    populated — with only six participants, inference must show the effect
    replicates across individuals (CLAUDE.md, "Scientific objective").
    """
    n_replicating = 0
    n_subjects = 0
    for one_subject in sorted(set(subject)):
        subject_mask = (subject[:, None] == one_subject) & (subject[None, :] == one_subject)
        good, bad = _pure_strata_masks(stratum, triu_mask & subject_mask, good_stratum)
        good_values = similarity[good]
        bad_values = similarity[bad]
        if len(good_values) == 0 or len(bad_values) == 0:
            continue
        n_subjects += 1
        if np.median(good_values) > np.median(bad_values):
            n_replicating += 1
    return n_replicating, n_subjects


def strata_permutation(paths, network_order, measure, min_usable_seconds, column,
                       stratum_column, good_stratum, n_permutations=1000, seed=0,
                       split_by=("subject", "dataset"), min_cell=4, definitions=None,
                       coverage_column=COVERAGE_COLUMN):
    """Two-sided permutation test on `median(good-good) - median(bad-bad)` per
    network x definition, plus per-subject replication
    (`n_subjects_replicating`/`n_subjects_total`).

    Shuffles the stratum within each `split_by` cell (the exchangeability that
    stratification buys), pooled across both task bins since acquisition
    quality, not task, is the axis under test here. Restricted to
    within-subject pairs. The similarity matrix itself never changes across
    permutations, only which pairs count as good-good/bad-bad, so this reuses
    one `similarity_matrix` call per network rather than recomputing it
    `n_permutations` times.
    """
    rng = np.random.default_rng(seed)
    rows = []

    for network in network_order:
        index_frame, matrix = load_stacked_measure(paths, measure, network)
        qc_mask = qc_covered_mask(index_frame, min_usable_seconds, column=coverage_column)
        qc_index = index_frame[qc_mask].reset_index(drop=True)
        z_matrix = fisher_z(matrix[qc_mask])

        for def_name, residualize_on in _definition_passes(definitions):
            stratum_frame = assign_strata(
                qc_index, column, stratum_column, split_by=split_by,
                min_cell=min_cell, residualize_on=residualize_on,
            )
            valid = stratum_frame[stratum_column].notna().to_numpy()
            sub_index = stratum_frame[valid].reset_index(drop=True)
            sub_matrix = z_matrix[valid]
            if len(sub_index) < 4:
                rows.append(_tag_row({
                    "network": network, "observed_diff": np.nan,
                    "p_value": np.nan, "n_permutations": n_permutations,
                    "n_subjects_replicating": 0, "n_subjects_total": 0,
                }, def_name))
                continue

            subject = sub_index["subject"].to_numpy()
            same_subject = subject[:, None] == subject[None, :]
            n_sessions = len(sub_index)
            triu_mask = np.triu(np.ones((n_sessions, n_sessions), dtype=bool), k=1) & same_subject
            similarity = similarity_matrix(sub_matrix)

            group_keys = pd.Series(
                list(zip(*[sub_index[one_column] for one_column in split_by], strict=True))
            )
            stratum = sub_index[stratum_column].to_numpy()

            def _observed_diff(stratum_values, similarity=similarity, triu_mask=triu_mask):
                good, bad = _pure_strata_masks(stratum_values, triu_mask, good_stratum)
                good_values = similarity[good]
                bad_values = similarity[bad]
                if len(good_values) == 0 or len(bad_values) == 0:
                    return np.nan
                return float(np.median(good_values) - np.median(bad_values))

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

            n_replicating, n_subjects = _subject_replication(
                similarity, stratum, subject, triu_mask, good_stratum
            )

            rows.append(_tag_row({
                "network": network, "observed_diff": observed_diff,
                "p_value": p_value, "n_permutations": n_permutations,
                "n_subjects_replicating": n_replicating, "n_subjects_total": n_subjects,
            }, def_name))

    return pd.DataFrame(rows)


def _tag_row(row, def_name):
    if def_name is not None:
        row["stratum_def"] = def_name
    return row


def sessions_table(index_frame, min_usable_seconds, column, stratum_column,
                   splits=DEFAULT_SPLITS, definitions=None,
                   report_columns=("fd_mean", "tsnr"), coverage_column=COVERAGE_COLUMN):
    """One row per QC-covered session: entities, `report_columns`,
    `usable_duration_sec`, plus one stratum column per split x definition —
    for auditability.

    Stratum columns are named `{stratum_column}_{split}` when there is a single
    unnamed definition, and `{stratum_column}_{split}_{def}` otherwise.
    """
    usable = index_frame["usable_duration_sec"].fillna(index_frame["duration_sec"])
    qc_mask = qc_covered_mask(index_frame, min_usable_seconds, column=coverage_column)
    result = index_frame.loc[
        qc_mask, ["dataset", "subject", "session", *report_columns]
    ].reset_index(drop=True)
    result["usable_duration_sec"] = usable[qc_mask].reset_index(drop=True)

    sub_index = index_frame[qc_mask].reset_index(drop=True)
    for def_name, residualize_on in _definition_passes(definitions):
        for split_name, split_by, min_cell in splits:
            stratum_frame = assign_strata(
                sub_index, column, stratum_column, split_by=split_by,
                min_cell=min_cell, residualize_on=residualize_on,
            )
            suffix = split_name if def_name is None else f"{split_name}_{def_name}"
            result[f"{stratum_column}_{suffix}"] = stratum_frame[stratum_column].to_numpy()

    return result
