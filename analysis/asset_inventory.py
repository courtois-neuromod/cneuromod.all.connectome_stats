"""Discovers and joins the four assets `run-inventory` depends on: raw BIDS,
timeseries `.h5`, qa_figures QC, and this project's own connectome outputs.
See CLAUDE.md, "Asset coverage inventory" (`run-inventory`) — this is
infrastructure, not an analysis tier: it makes no claim and feeds no figure.
The rollups this table feeds (`session_inventory.tsv`, etc.) live in
`analysis/inventory_summary.py`, kept separate to stay near CLAUDE.md's
~200-line-per-module guideline.

Pure functions, no invoke context, in the style of `analysis/qc_measures.py`.
The hard part is that the four sources disagree about entity formatting (run
zero-padding, run absent entirely, session-less layouts) — `_tiered_join`
resolves that with a three-tier best-effort match, recording which tier
matched in `match_level` rather than silently guessing (the same
warn-don't-abort posture `analysis/qc_join.py` already takes).
"""

import numpy as np
import pandas as pd

from analysis.bids_inventory import NON_FUNCTIONAL_DATASETS, canonical_run, list_raw_runs
from analysis.connectomes import subject_dirs
from analysis.qc_join import normalize_entities
from analysis.qc_measures import load_qc_measures
from analysis.timeseries_reader import list_entities

_JOIN_TIERS = [
    ("exact", ["dataset", "subject", "session_norm", "task", "run_norm"]),
    ("no_run", ["dataset", "subject", "session_norm", "task"]),
    ("no_session", ["dataset", "subject", "task", "run_norm"]),
]

TIMESERIES_COLUMNS = ["dataset", "subject", "session", "task", "run"]


def dataset_universe(cneuromod_root, timeseries_marker="timeseries"):
    """Every dataset carrying a `bids` and/or `{timeseries_marker}` mountpoint.

    Excludes `analysis/bids_inventory.NON_FUNCTIONAL_DATASETS` (structural-only
    trees such as `anat`, out of scope per CLAUDE.md's `anat/atlases` note).
    """
    root = cneuromod_root
    if not root.is_dir():
        return []
    names = set()
    for child in root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in NON_FUNCTIONAL_DATASETS:
            continue
        if (child / "bids").is_dir() or (child / timeseries_marker).is_dir():
            names.add(child.name)
    return sorted(names)


def list_timeseries_runs(cneuromod_root, dataset, parcellation):
    """Every run entity registered in `dataset`'s fetched timeseries `.h5` file(s).

    Returns `(DataFrame, status_rows)`. `status_rows` records, per subject
    directory found, whether the `.h5` is registered and whether its content
    has actually been fetched (`Path.exists()` on the annex symlink — CLAUDE.md
    verified this discriminates correctly).
    """
    _base, dirs = subject_dirs(cneuromod_root, dataset, parcellation)
    rows = []
    status_rows = []
    for subject_dir in dirs:
        subject = subject_dir.name.removeprefix("sub-")
        h5_files = sorted(subject_dir.glob("*_timeseries.h5"))
        fetched = [p for p in h5_files if p.exists()]
        status_rows.append({
            "dataset": dataset, "subject": subject,
            "registered": bool(h5_files), "content_present": bool(fetched),
        })
        if not fetched:
            continue
        for entity in list_entities(fetched[0]):
            rows.append({
                "dataset": dataset, "subject": subject,
                "session": entity["session"], "task": entity["task"],
                "run": canonical_run(entity["run"]),
            })
    frame = pd.DataFrame(rows, columns=TIMESERIES_COLUMNS) if rows else \
        pd.DataFrame(columns=TIMESERIES_COLUMNS)
    return frame, status_rows


def _normalize_join_frame(frame):
    frame = frame.copy()
    frame["session_norm"] = frame["session"].fillna("").astype(str).str.zfill(3)
    frame["run_norm"] = frame["run"].apply(canonical_run)
    return frame


def _unique_key_set(frame, keys):
    counts = frame.groupby(keys, dropna=False).size()
    return set(counts[counts == 1].index)


def _tiered_join(raw, other):
    """Match each row of `raw` against `other` across three tiers.

    Returns `(matched, match_level)`, numpy arrays aligned to `raw`'s row
    order. A tier only claims a row when the join key is unique on *both*
    sides at that tier — otherwise the match is ambiguous and left to the
    next, looser tier (or `"unmatched"`).
    """
    n = len(raw)
    matched = np.zeros(n, dtype=bool)
    levels = np.full(n, "unmatched", dtype=object)
    if other is None or other.empty or n == 0:
        return matched, levels

    raw_n = _normalize_join_frame(raw).reset_index(drop=True)
    other_n = _normalize_join_frame(other)

    for level, keys in _JOIN_TIERS:
        remaining = ~matched
        if not remaining.any():
            break
        if level == "exact":
            other_allowed = set(map(tuple, other_n[keys].itertuples(index=False, name=None)))
            raw_allowed = None
        else:
            other_allowed = _unique_key_set(other_n, keys)
            raw_allowed = _unique_key_set(raw_n, keys)
        for idx in np.nonzero(remaining)[0]:
            key = tuple(raw_n.loc[idx, keys])
            if key not in other_allowed:
                continue
            if raw_allowed is not None and key not in raw_allowed:
                continue
            matched[idx] = True
            levels[idx] = level
    return matched, levels


def join_inventory(raw, timeseries, qc):
    """Attach `in_timeseries`/`match_level` and `in_qc` to the raw run table."""
    result = raw.copy()
    matched_ts, levels_ts = _tiered_join(raw, timeseries)
    result["in_timeseries"] = matched_ts
    result["match_level"] = levels_ts

    matched_qc, _ = _tiered_join(raw, qc)
    result["in_qc"] = matched_qc
    return result


def _load_qc_entities(qa_root):
    qc = load_qc_measures(qa_root)
    if qc.empty:
        return qc
    qc = normalize_entities(qc)
    qc["run"] = qc["run"].apply(canonical_run)
    return qc[TIMESERIES_COLUMNS]


def build_run_inventory(cneuromod_root, qa_root, datasets, parcellation, skip_durations=False):
    """Master per-run inventory: one row per unique raw BIDS run, joined
    against timeseries and QC coverage. Returns `(run_inventory, status_rows)`.
    """
    raw_frames, ts_frames, status_rows = [], [], []
    for dataset in datasets:
        raw = list_raw_runs(cneuromod_root, dataset, skip_durations=skip_durations)
        if not raw.empty:
            raw_frames.append(raw)
        timeseries, dataset_status = list_timeseries_runs(cneuromod_root, dataset, parcellation)
        if not timeseries.empty:
            ts_frames.append(timeseries)
        status_rows.extend(dataset_status)

    raw_all = pd.concat(raw_frames, ignore_index=True) if raw_frames else pd.DataFrame()
    ts_all = pd.concat(ts_frames, ignore_index=True) if ts_frames else pd.DataFrame()
    qc_all = _load_qc_entities(qa_root) if qa_root is not None else pd.DataFrame()

    if raw_all.empty:
        return raw_all, status_rows
    return join_inventory(raw_all, ts_all, qc_all), status_rows
