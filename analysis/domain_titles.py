"""Recover a naturalistic-stimulus "title" from session h5 keys, across datasets.

Generalizes `analysis/friends_seasons.py`'s season derivation — kept there,
scoped to the longitudinal claim — to the "movies" domain figure (CLAUDE.md,
"Domain-restricted robustness figures"): `friends` seasons and `movie10`
titles (`bourne`/`wolf`/`life`/`figures`) both live in the source h5 key's
task entity, never in the connectome-store index (which collapses multi-run
sessions' `task` to `"multi"`). Pure functions, no invoke context — follows
the `analysis/friends_seasons.py` precedent.
"""

import re
from pathlib import Path

import pandas as pd

from analysis.timeseries_layout import parcellation_subdir
from analysis.timeseries_reader import list_entities, session_runs

TITLE_PATTERNS = {
    "friends": re.compile(r"^(s\d{2})e\d{2}"),
    "movie10": re.compile(r"^([a-z]+?)\d+$"),
}


def title_from_task(dataset, task):
    """The title/season prefix from one run's task entity, or `None`.

    `None` both for a `dataset` with no known pattern and for a `task` that
    does not match its dataset's pattern.
    """
    pattern = TITLE_PATTERNS.get(dataset)
    if pattern is None:
        return None
    match = pattern.match(task)
    return match.group(1) if match else None


def session_titles(cneuromod_root, parcellation, datasets, subjects=None):
    """One row per session across `datasets`: `dataset, subject, session, title, n_titles`.

    `title` is the sole title if every run entity in the session agrees;
    otherwise the lexicographically first one, and `n_titles` (> 1) marks it
    as a boundary session for `attach_titles` to drop — same convention as
    `friends_seasons.session_seasons`. Reads only h5 key names via
    `list_entities`, no timeseries arrays loaded. A `dataset` absent from
    `TITLE_PATTERNS` contributes no rows.
    """
    subdir = parcellation_subdir(parcellation)
    rows = []
    for dataset in datasets:
        if dataset not in TITLE_PATTERNS:
            continue
        dataset_root = Path(cneuromod_root) / dataset / "timeseries" / subdir
        for subject_dir in sorted(dataset_root.glob("sub-*")):
            subject = subject_dir.name.removeprefix("sub-")
            if subjects and subject not in subjects:
                continue
            # p.exists() follows the symlink target: a broken/unfetched annex
            # link glob-matches but must not be opened (mirrors connectomes.py).
            h5_paths = [p for p in sorted(subject_dir.glob("*_timeseries.h5")) if p.exists()]
            if not h5_paths:
                continue
            entities = list_entities(h5_paths[0])
            for session, session_entities in session_runs(entities).items():
                titles = sorted({
                    title_from_task(dataset, entity["task"])
                    for entity in session_entities
                    if title_from_task(dataset, entity["task"]) is not None
                })
                if not titles:
                    continue
                rows.append({
                    "dataset": dataset,
                    "subject": subject,
                    "session": session,
                    "title": titles[0],
                    "n_titles": len(titles),
                })
    return pd.DataFrame(rows)


def attach_titles(index_frame, title_frame, drop_mixed=True):
    """Left-merge `title`/`n_titles` onto `index_frame` by `dataset, subject, session`.

    Same shape as `friends_seasons.attach_seasons`: drops boundary sessions
    (`n_titles > 1`) when `drop_mixed`, and always drops rows with no title
    match. Merging on `dataset` too (unlike `attach_seasons`, single-dataset)
    keeps `friends` and `movie10` session numbers from colliding. Returns
    `(frame, dropped_counts)` with keys `boundary` and `unmatched`.
    """
    assert index_frame["session"].astype(str).str.len().eq(3).all()
    assert title_frame["session"].astype(str).str.len().eq(3).all()

    merged = index_frame.merge(
        title_frame, on=["dataset", "subject", "session"], how="left", indicator=True
    )
    unmatched = int((merged["_merge"] == "left_only").sum())
    merged = merged[merged["_merge"] == "both"].drop(columns="_merge")

    boundary = 0
    if drop_mixed:
        is_boundary = merged["n_titles"] > 1
        boundary = int(is_boundary.sum())
        merged = merged[~is_boundary]

    return merged.reset_index(drop=True), {"boundary": boundary, "unmatched": unmatched}
