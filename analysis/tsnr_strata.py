"""tSNR-stratified robustness check (CLAUDE.md, "Respect the analysis
hierarchy" — robustness tier, QC dependence): does session-to-session
connectome similarity depend on acquisition signal quality, and does claim 2's
within-task > between-task ordering survive when tSNR is held high?

The companion to `analysis/motion_strata.py` on the other QC axis, and thin
configuration over the same `analysis/quality_strata.py` core. Two facts shape
it (CLAUDE.md, "tSNR stratification"):

- **Whole-brain tSNR only.** The stored session index carries `tsnr_{network}`
  for every network, but `tables/atlas_tsnr/` is populated upstream only for
  `floc`, `retinotopy` and `things` — exactly the three datasets the 1800 s
  gate removes — so those columns are non-NaN for 0 of the 246 QC-covered
  sessions. A per-network stratification would be all-NaN today.
- **Two stratum definitions, not one.** `tsnr` and `fd_mean` correlate at
  r=-0.68, and a raw tSNR median split agrees with the motion stratum on 72%
  of sessions, so a raw-only analysis would largely re-run the motion result.
  `fd_residual` splits on tSNR residualized on `fd_mean` within the same cell,
  which is near-independent of the motion stratum (~chance agreement) and
  therefore answers "does signal quality matter *beyond* motion". Both run in
  one code path, distinguished by the `stratum_def` column.

High tSNR is the *good* stratum, so `observed_diff` is
`median(high-high) - median(low-low)` — the same "better quality, higher
similarity is positive" sign convention as the motion analysis.
`run-tsnr-strata` (tasks.py) is the only caller.
"""

from analysis.qc_measures import TSNR_COLUMN
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

TSNR_SPLITS = DEFAULT_SPLITS

# (definition name, column to residualize tSNR on within each cell).
TSNR_DEFINITIONS = (
    ("raw", None),
    ("fd_residual", "fd_mean"),
)

TSNR_STRATUM = "tsnr_stratum"
GOOD_STRATUM = "high"

# Pair-min usable duration, pair-min tSNR (the stratifying axis itself) and
# pair-max `fd_mean` — the motion confound, reported alongside for the same
# reason the motion table reports tSNR: the two axes are coupled and must
# never be presented as independent.
TSNR_BALANCE_COLUMNS = (
    ("usable", "median_min_duration_sec", "min"),
    (TSNR_COLUMN, "median_min_tsnr", "min"),
    ("fd_mean", "median_max_fd_mean", "max"),
)

__all__ = [
    "TSNR_SPLITS", "TSNR_DEFINITIONS", "qc_covered_mask", "assign_tsnr_strata",
    "tsnr_pair_bin_labels", "tsnr_pair_bins", "tsnr_summary", "tsnr_balance",
    "tsnr_permutation", "tsnr_sessions_table",
]


def assign_tsnr_strata(index_frame, split_by=("subject", "dataset"), min_cell=4,
                       residualize_on=None):
    """Add `tsnr_stratum` (`"low"`/`"high"`/`None`): below/above the median
    `tsnr` within each `split_by` group. Ties go to `"low"`.

    With `residualize_on="fd_mean"`, splits on tSNR residualized on head
    motion within the same group instead — the `fd_residual` definition.
    """
    return assign_strata(index_frame, TSNR_COLUMN, TSNR_STRATUM, split_by=split_by,
                         min_cell=min_cell, residualize_on=residualize_on)


def tsnr_pair_bin_labels():
    """The six `"{tsnr-pair}/{within|between}-task"` labels, good-good first."""
    return pair_bin_labels(GOOD_STRATUM)


def tsnr_pair_bins(index_frame, group_column="dataset"):
    """`(n, n)` bin-label array from tSNR-stratum pairing x task equality,
    restricted to within-subject pairs.
    """
    return pair_bins(index_frame, TSNR_STRATUM, group_column=group_column,
                     good_stratum=GOOD_STRATUM)


def tsnr_summary(paths, network_order, measure, min_usable_seconds, n_bins=60,
                 group_column="dataset", splits=TSNR_SPLITS, definitions=TSNR_DEFINITIONS):
    """Per network x definition x split x bin similarity summary, plus histograms.

    Returns `{"tsnr_bins": frame, "histograms": frame}`.
    """
    result = strata_summary(
        paths, network_order, measure, min_usable_seconds,
        column=TSNR_COLUMN, stratum_column=TSNR_STRATUM, good_stratum=GOOD_STRATUM,
        analysis="tsnr", n_bins=n_bins, group_column=group_column,
        splits=splits, definitions=definitions,
    )
    return {"tsnr_bins": result["bins"], "histograms": result["histograms"]}


def tsnr_balance(index_frame, min_usable_seconds, group_column="dataset",
                 splits=TSNR_SPLITS, definitions=TSNR_DEFINITIONS):
    """Per definition x split x bin: pair-min usable duration, pair-min tSNR and
    pair-max `fd_mean`.
    """
    return strata_balance(
        index_frame, min_usable_seconds, column=TSNR_COLUMN,
        stratum_column=TSNR_STRATUM, good_stratum=GOOD_STRATUM,
        balance_columns=TSNR_BALANCE_COLUMNS, group_column=group_column,
        splits=splits, definitions=definitions,
    )


def tsnr_permutation(paths, network_order, measure, min_usable_seconds,
                     n_permutations=1000, seed=0, split_by=("subject", "dataset"),
                     min_cell=4, definitions=TSNR_DEFINITIONS):
    """Two-sided permutation test on `median(high-high) - median(low-low)` per
    network x definition, plus per-subject replication.
    """
    return strata_permutation(
        paths, network_order, measure, min_usable_seconds, column=TSNR_COLUMN,
        stratum_column=TSNR_STRATUM, good_stratum=GOOD_STRATUM,
        n_permutations=n_permutations, seed=seed, split_by=split_by,
        min_cell=min_cell, definitions=definitions,
    )


def tsnr_sessions_table(index_frame, min_usable_seconds, splits=TSNR_SPLITS,
                        definitions=TSNR_DEFINITIONS):
    """One row per QC-covered session: entities, `fd_mean`, `tsnr`,
    `usable_duration_sec`, plus one `tsnr_stratum_{split}_{def}` column per
    split x definition — for auditability.
    """
    return sessions_table(index_frame, min_usable_seconds, column=TSNR_COLUMN,
                          stratum_column=TSNR_STRATUM, splits=splits,
                          definitions=definitions)
