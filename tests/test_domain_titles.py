"""Tests for analysis/domain_titles.py."""

import h5py
import numpy as np
import pandas as pd

from analysis.domain_titles import attach_titles, session_titles, title_from_task


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


def test_title_from_task_friends_season():
    assert title_from_task("friends", "s01e02a") == "s01"
    assert title_from_task("friends", "multi") is None


def test_title_from_task_movie10_title():
    assert title_from_task("movie10", "bourne01") == "bourne"
    assert title_from_task("movie10", "wolf17") == "wolf"
    assert title_from_task("movie10", "life05") == "life"
    assert title_from_task("movie10", "figures02") == "figures"


def test_title_from_task_unknown_dataset_returns_none():
    assert title_from_task("mario", "level01") is None


def test_session_titles_marks_pure_and_boundary_sessions(tmp_path):
    root = tmp_path / "movie10" / "timeseries" / "timeseries" / "cneuromod2026" / "sub-01"
    root.mkdir(parents=True)
    _write_h5(
        root / "sub-01_task-movie10_timeseries.h5",
        {
            "001": ["bourne01", "bourne02"],
            "002": ["wolf01"],
            "003": ["life05", "bourne06"],  # boundary session
        },
    )

    frame = session_titles(tmp_path, "cneuromod2026", ["movie10"])
    frame = frame.sort_values("session").reset_index(drop=True)

    assert list(frame["dataset"]) == ["movie10"] * 3
    assert list(frame["session"]) == ["001", "002", "003"]
    assert list(frame["title"]) == ["bourne", "wolf", "bourne"]
    assert list(frame["n_titles"]) == [1, 1, 2]


def test_session_titles_spans_multiple_datasets(tmp_path):
    friends_root = tmp_path / "friends" / "timeseries" / "timeseries" / "cneuromod2026" / "sub-01"
    friends_root.mkdir(parents=True)
    _write_h5(friends_root / "sub-01_task-friends_timeseries.h5", {"001": ["s01e01a"]})

    movie_root = tmp_path / "movie10" / "timeseries" / "timeseries" / "cneuromod2026" / "sub-01"
    movie_root.mkdir(parents=True)
    _write_h5(movie_root / "sub-01_task-movie10_timeseries.h5", {"001": ["wolf03"]})

    frame = session_titles(tmp_path, "cneuromod2026", ["friends", "movie10"])
    frame = frame.sort_values("dataset").reset_index(drop=True)

    assert list(frame["dataset"]) == ["friends", "movie10"]
    assert list(frame["title"]) == ["s01", "wolf"]


def test_session_titles_skips_dataset_without_a_pattern(tmp_path):
    root = tmp_path / "mario" / "timeseries" / "timeseries" / "cneuromod2026" / "sub-01"
    root.mkdir(parents=True)
    _write_h5(root / "sub-01_task-mario_timeseries.h5", {"001": ["level01"]})

    frame = session_titles(tmp_path, "cneuromod2026", ["mario"])
    assert len(frame) == 0


def test_attach_titles_drops_boundary_and_unmatched_rows_and_keys_on_dataset():
    index_frame = pd.DataFrame({
        "dataset": ["friends", "friends", "movie10", "movie10"],
        "subject": ["01", "01", "01", "02"],
        "session": ["001", "002", "001", "999"],
    })
    title_frame = pd.DataFrame({
        "dataset": ["friends", "friends", "movie10"],
        "subject": ["01", "01", "01"],
        "session": ["001", "002", "001"],
        "title": ["s01", "s01", "bourne"],
        "n_titles": [1, 2, 1],
    })

    merged, dropped = attach_titles(index_frame, title_frame)

    pairs = list(zip(merged["dataset"], merged["session"]))
    assert pairs == [("friends", "001"), ("movie10", "001")]
    assert dropped == {"boundary": 1, "unmatched": 1}


def test_attach_titles_same_session_number_across_datasets_does_not_collide():
    index_frame = pd.DataFrame({
        "dataset": ["friends", "movie10"],
        "subject": ["01", "01"],
        "session": ["001", "001"],
    })
    title_frame = pd.DataFrame({
        "dataset": ["friends", "movie10"],
        "subject": ["01", "01"],
        "session": ["001", "001"],
        "title": ["s01", "bourne"],
        "n_titles": [1, 1],
    })

    merged, dropped = attach_titles(index_frame, title_frame)

    assert dropped == {"boundary": 0, "unmatched": 0}
    assert sorted(merged["title"]) == ["bourne", "s01"]
