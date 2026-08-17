"""Tests for the timeseries path helpers in analysis/timeseries_layout.py."""

from pathlib import Path

import pytest

from analysis.timeseries_layout import (
    parcellation_subdir,
    parse_labels,
    subject_filter,
    timeseries_patterns,
)


def test_parcellation_subdir_is_relative_to_the_repo_root():
    assert parcellation_subdir("schaefer1000") == "timeseries/schaefer1000"


@pytest.mark.parametrize("filename", [
    "sub-01_task-floc_space-MNI152NLin2009cAsym_atlas-Schaefer2018"
    "_desc-1000Parcels7Networks_timeseries.h5",
    "sub-01_task-floc_space-MNI152NLin2009cAsym_atlas-Schaefer2018"
    "_desc-1000Parcels7Networks_dseg.nii.gz",
    "sub-01_task-floc_space-MNI152NLin2009cAsym_label-GMfromTemplate"
    "_desc-indivFunc_mask.nii.gz",
])
def test_every_real_filename_matches_some_pattern(filename):
    assert any(Path(filename).match(pattern) for pattern in timeseries_patterns())


def test_patterns_ignore_the_atlas_entity():
    """Upstream writes atlas-Schaefer2018, the docs say Schaefer18 — neither
    appears in a pattern, so the drift cannot break retrieval."""
    assert not any("Schaefer" in pattern for pattern in timeseries_patterns())


@pytest.mark.parametrize("raw", ["1", "01", "sub-01", " sub-01 "])
def test_subject_labels_normalize_to_the_sub_prefixed_form(raw):
    assert parse_labels(raw, prefix="sub-") == ["sub-01"]


def test_parse_labels_splits_and_drops_blanks():
    assert parse_labels("01,,03", prefix="sub-") == ["sub-01", "sub-03"]
    assert parse_labels("floc, movie10") == ["floc", "movie10"]


@pytest.mark.parametrize("value", [None, "", "  ", ","])
def test_parse_labels_is_empty_for_no_value(value):
    assert parse_labels(value, prefix="sub-") == []


def test_subject_filter_is_none_when_nothing_is_requested():
    assert subject_filter([]) is None


def test_subject_filter_keeps_only_the_requested_subjects():
    match = subject_filter(["sub-01", "sub-03"])
    base = Path("movie10/timeseries/timeseries/schaefer1000")

    assert match(base / "sub-01" / "sub-01_task-movie10_desc-x_timeseries.h5")
    assert match(base / "sub-03" / "sub-03_task-movie10_desc-x_timeseries.h5")
    assert not match(base / "sub-02" / "sub-02_task-movie10_desc-x_timeseries.h5")


def test_subject_filter_excludes_files_above_the_subject_level():
    """voxel_mni's shared mask has no sub-XX component: it is not one
    subject's data, so a subject restriction must leave it out."""
    match = subject_filter(["sub-01"])
    shared = Path("movie10/timeseries/timeseries/voxel_mni/task-movie10_desc-x_mask.nii.gz")

    assert not match(shared)
