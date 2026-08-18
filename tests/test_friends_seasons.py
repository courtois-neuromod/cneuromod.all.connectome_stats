"""Tests for analysis/friends_seasons.py."""

import h5py
import numpy as np
import pandas as pd

from analysis.friends_seasons import (
    attach_seasons,
    season_from_task,
    season_index,
    session_seasons,
)


def _write_h5(path, session_tasks):
    """`session_tasks`: `{session: [task, ...]}`, one run key per task."""
    array = np.zeros((3, 2), dtype=np.float32)
    with h5py.File(path, "w") as handle:
        for session, tasks in session_tasks.items():
            for i, task in enumerate(tasks):
                handle.create_dataset(
                    f"ses-{session}/ses-{session}_task-{task}_run-{i}_timeseries",
                    data=array,
                )


def test_season_from_task_parses_episode_and_rejects_other_task():
    assert season_from_task("s01e02a") == "s01"
    assert season_from_task("s06e24d") == "s06"
    assert season_from_task("multi") is None
    assert season_from_task("bourne01") is None


def test_season_index():
    assert season_index("s01") == 1
    assert season_index("s06") == 6


def test_session_seasons_marks_pure_and_boundary_sessions(tmp_path):
    root = tmp_path / "friends" / "timeseries" / "timeseries" / "cneuromod2026" / "sub-01"
    root.mkdir(parents=True)
    _write_h5(
        root / "sub-01_task-friends_timeseries.h5",
        {
            "001": ["s01e01a", "s01e01b"],
            "002": ["s01e02a"],
            "003": ["s01e05d", "s02e01a"],  # boundary session
        },
    )

    frame = session_seasons(tmp_path, "cneuromod2026")
    frame = frame.sort_values("session").reset_index(drop=True)

    assert list(frame["session"]) == ["001", "002", "003"]
    assert list(frame["season"]) == ["s01", "s01", "s01"]
    assert list(frame["n_seasons"]) == [1, 1, 2]


def test_session_seasons_filters_by_subject(tmp_path):
    for subject in ("01", "02"):
        root = (
            tmp_path / "friends" / "timeseries" / "timeseries" / "cneuromod2026"
            / f"sub-{subject}"
        )
        root.mkdir(parents=True)
        _write_h5(
            root / f"sub-{subject}_task-friends_timeseries.h5",
            {"001": ["s01e01a"]},
        )

    frame = session_seasons(tmp_path, "cneuromod2026", subjects={"01"})
    assert list(frame["subject"]) == ["01"]


def test_attach_seasons_drops_boundary_and_unmatched_rows():
    index_frame = pd.DataFrame({
        "subject": ["01", "01", "01", "02"],
        "session": ["001", "002", "003", "999"],
    })
    season_frame = pd.DataFrame({
        "subject": ["01", "01", "01"],
        "session": ["001", "002", "003"],
        "season": ["s01", "s01", "s01"],
        "n_seasons": [1, 1, 2],
    })

    merged, dropped = attach_seasons(index_frame, season_frame)

    assert list(merged["session"]) == ["001", "002"]
    assert dropped == {"boundary": 1, "unmatched": 1}


def test_attach_seasons_keeps_boundary_rows_when_not_dropping():
    index_frame = pd.DataFrame({"subject": ["01"], "session": ["003"]})
    season_frame = pd.DataFrame({
        "subject": ["01"], "session": ["003"], "season": ["s01"], "n_seasons": [2],
    })

    merged, dropped = attach_seasons(index_frame, season_frame, drop_mixed=False)

    assert list(merged["session"]) == ["003"]
    assert dropped == {"boundary": 0, "unmatched": 0}
