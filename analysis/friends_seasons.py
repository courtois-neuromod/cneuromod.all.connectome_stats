"""Recover the friends season from session h5 keys, as a time axis.

Season is a tier-3 robustness control (CLAUDE.md, "Respect the analysis
hierarchy"): `friends` is the most task-homogeneous dataset available (every
run is a Friends episode), and its six seasons were acquired in order across
most of the project, so splitting by season isolates drift (scanner, subject
state, elapsed time) from cognitive context. Pure functions, no invoke
context — follows the `analysis/qc_join.py` precedent. Season is not stored in
`output_data/connectomes/friends_*.h5` (the index collapses multi-run sessions'
`task` to `"multi"`), so it is re-derived here from the source timeseries h5
key names alone — cheap, no timeseries loaded.
"""

import re
from pathlib import Path

import pandas as pd

from analysis.timeseries_layout import parcellation_subdir
from analysis.timeseries_reader import list_entities, session_runs

_SEASON_PATTERN = re.compile(r"^(s\d{2})e\d{2}")


def season_from_task(task):
    """`"s01"` from `"s01e02a"`; `None` if `task` is not a season/episode entity."""
    match = _SEASON_PATTERN.match(task)
    return match.group(1) if match else None


def season_index(season):
    """`"s03"` -> `3`."""
    return int(season[1:])


def session_seasons(cneuromod_root, parcellation, subjects=None):
    """One row per friends session: `subject, session, season, n_seasons`.

    `season` is the sole season if every run entity in the session agrees;
    otherwise the lexicographically first one, and `n_seasons` (> 1) marks it
    as a boundary session for `attach_seasons` to drop. Reads only h5 key
    names via `list_entities` — no timeseries arrays are loaded.
    """
    subdir = parcellation_subdir(parcellation)
    friends_root = Path(cneuromod_root) / "friends" / "timeseries" / subdir
    rows = []
    for subject_dir in sorted(friends_root.glob("sub-*")):
        subject = subject_dir.name.removeprefix("sub-")
        if subjects and subject not in subjects:
            continue
        h5_paths = sorted(subject_dir.glob("*_timeseries.h5"))
        if not h5_paths:
            continue
        entities = list_entities(h5_paths[0])
        for session, session_entities in session_runs(entities).items():
            seasons = sorted({
                season_from_task(entity["task"])
                for entity in session_entities
                if season_from_task(entity["task"]) is not None
            })
            if not seasons:
                continue
            rows.append({
                "subject": subject,
                "session": session,
                "season": seasons[0],
                "n_seasons": len(seasons),
            })
    return pd.DataFrame(rows)


def attach_seasons(index_frame, season_frame, drop_mixed=True):
    """Left-merge `season`/`n_seasons` onto `index_frame` by `subject, session`.

    Both sides carry zero-padded 3-digit `session` strings already (asserted,
    not re-padded — a mismatch here means an upstream convention changed).
    Drops boundary sessions (`n_seasons > 1`) when `drop_mixed`, and always
    drops rows with no season match. Returns `(frame, dropped_counts)` with
    keys `boundary` and `unmatched`.
    """
    assert index_frame["session"].astype(str).str.len().eq(3).all()
    assert season_frame["session"].astype(str).str.len().eq(3).all()

    merged = index_frame.merge(
        season_frame, on=["subject", "session"], how="left", indicator=True
    )
    unmatched = int((merged["_merge"] == "left_only").sum())
    merged = merged[merged["_merge"] == "both"].drop(columns="_merge")

    boundary = 0
    if drop_mixed:
        is_boundary = merged["n_seasons"] > 1
        boundary = int(is_boundary.sum())
        merged = merged[~is_boundary]

    return merged.reset_index(drop=True), {"boundary": boundary, "unmatched": unmatched}
