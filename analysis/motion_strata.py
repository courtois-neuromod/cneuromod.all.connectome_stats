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

Thin configuration over `analysis/quality_strata.py`, which holds the
machinery shared with `analysis/tsnr_strata.py`. Low motion is the *good*
stratum here, so `observed_diff` is `median(low-low) - median(high-high)`.
`run-motion-strata` (tasks.py) is the only caller.
"""

from analysis.quality_strata import (
    DEFAULT_SPLITS,
    assign_strata,
    pair_bin_labels,
    pair_bins,
    qc_covered_mask,
    sessions_table,
    strata_balance,
    strata_permutation,
    strata_summary,
)

# See `quality_strata.DEFAULT_SPLITS` — "cell" is the primary split (motion is
# strongly subject- and dataset-specific), "subject" the secondary comparison
# carried in the same tables via the `split` column, not a second code path.
MOTION_SPLITS = DEFAULT_SPLITS

MOTION_COLUMN = "fd_mean"
MOTION_STRATUM = "motion_stratum"
GOOD_STRATUM = "low"

# Pair-min usable duration AND pair-min tSNR: the motion stratum is
# substantially a tSNR stratum too (r=-0.68 — CLAUDE.md, "Motion
# stratification") and both must be reported together, never as independent
# axes.
MOTION_BALANCE_COLUMNS = (
    ("usable", "median_min_duration_sec", "min"),
    ("tsnr", "median_min_tsnr", "min"),
)

__all__ = [
    "MOTION_SPLITS", "qc_covered_mask", "assign_motion_strata",
    "motion_pair_bin_labels", "motion_pair_bins", "motion_summary",
    "motion_balance", "motion_permutation", "motion_sessions_table",
]


def assign_motion_strata(index_frame, split_by=("subject", "dataset"), min_cell=4):
    """Add `motion_stratum` (`"low"`/`"high"`/`None`): below/above the median
    `fd_mean` within each `split_by` group. Ties go to `"low"`.
    """
    return assign_strata(index_frame, MOTION_COLUMN, MOTION_STRATUM,
                         split_by=split_by, min_cell=min_cell)


def motion_pair_bin_labels():
    """The six `"{motion-pair}/{within|between}-task"` labels."""
    return pair_bin_labels(GOOD_STRATUM)


def motion_pair_bins(index_frame, group_column="dataset"):
    """`(n, n)` bin-label array from motion-stratum pairing x task equality,
    restricted to within-subject pairs.
    """
    return pair_bins(index_frame, MOTION_STRATUM, group_column=group_column,
                     good_stratum=GOOD_STRATUM)


def motion_summary(paths, network_order, measure, min_usable_seconds, n_bins=60,
                   group_column="dataset", splits=MOTION_SPLITS):
    """Per network x split x motion-task bin similarity summary, plus histograms.

    Restricted to the QC-covered population (`qc_covered_mask`) throughout.
    Returns `{"motion_bins": frame, "histograms": frame}`.
    """
    result = strata_summary(
        paths, network_order, measure, min_usable_seconds,
        column=MOTION_COLUMN, stratum_column=MOTION_STRATUM,
        good_stratum=GOOD_STRATUM, analysis="motion", n_bins=n_bins,
        group_column=group_column, splits=splits,
    )
    return {"motion_bins": result["bins"], "histograms": result["histograms"]}


def motion_balance(index_frame, min_usable_seconds, group_column="dataset",
                   splits=MOTION_SPLITS):
    """Per split x motion-task bin: pair-min usable duration AND pair-min tSNR."""
    return strata_balance(
        index_frame, min_usable_seconds, column=MOTION_COLUMN,
        stratum_column=MOTION_STRATUM, good_stratum=GOOD_STRATUM,
        balance_columns=MOTION_BALANCE_COLUMNS, group_column=group_column, splits=splits,
    )


def motion_permutation(paths, network_order, measure, min_usable_seconds,
                       n_permutations=1000, seed=0, split_by=("subject", "dataset"),
                       min_cell=4):
    """Two-sided permutation test on `median(low-low) - median(high-high)` per
    network, plus per-subject replication.
    """
    return strata_permutation(
        paths, network_order, measure, min_usable_seconds, column=MOTION_COLUMN,
        stratum_column=MOTION_STRATUM, good_stratum=GOOD_STRATUM,
        n_permutations=n_permutations, seed=seed, split_by=split_by, min_cell=min_cell,
    )


def motion_sessions_table(index_frame, min_usable_seconds, splits=MOTION_SPLITS):
    """One row per QC-covered session: entities, `fd_mean`, `tsnr`,
    `usable_duration_sec`, plus one `motion_stratum_{split_name}` column per
    entry in `splits` — for auditability.
    """
    return sessions_table(index_frame, min_usable_seconds, column=MOTION_COLUMN,
                          stratum_column=MOTION_STRATUM, splits=splits)
