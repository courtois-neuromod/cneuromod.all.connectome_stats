"""Tests for analysis/inventory_dashboard.py — the HTML rendering of the five
run-inventory tables. Offline, against synthetic frames in the TSVs' shape."""

import pandas as pd

from analysis.inventory_dashboard import render_dashboard

RENDER_KWARGS = {"parcellation": "cneuromod2026", "min_usable_seconds": 1800,
                 "generated_at": "2026-09-07T12:00:00"}


def _frames(dataset="movie10"):
    run_inventory = pd.DataFrame([
        {"dataset": dataset, "subject": "01", "session": "001", "task": "t", "run": "1",
         "n_volumes": 10, "tr_seconds": 1.49, "duration_sec": 14.9,
         "in_timeseries": True, "match_level": "exact", "in_qc": True},
        {"dataset": dataset, "subject": "01", "session": "001", "task": "t", "run": "2",
         "n_volumes": 10, "tr_seconds": 1.49, "duration_sec": 14.9,
         "in_timeseries": False, "match_level": "unmatched", "in_qc": False},
    ])
    sessions = pd.DataFrame([
        {"dataset": dataset, "subject": "01", "session": "001", "n_raw_runs": 2,
         "n_timeseries_runs": 1, "n_qc_runs": 1, "raw_duration_sec": 29.8,
         "usable_duration_sec": 1900.0, "passes_gate": True, "has_connectome": True},
    ])
    subjects = pd.DataFrame([
        {"dataset": dataset, "subject": "01", "n_sessions": 1, "n_raw_runs": 2,
         "n_timeseries_runs": 1, "n_qc_runs": 1, "raw_duration_sec": 29.8},
    ])
    dataset_coverage = pd.DataFrame([
        {"dataset": dataset, "bids_installed": True, "timeseries_registered": True,
         "timeseries_content_subjects": 1, "qc_table_populated": True,
         "atlas_tsnr_populated": False, "connectome_file_present": True},
    ])
    gaps = pd.DataFrame([{"dataset": dataset, "subject": "", "session": "",
                          "reason": "atlas_tsnr_empty"}])
    return run_inventory, sessions, subjects, dataset_coverage, gaps


def test_render_dashboard_covers_every_section():
    page = render_dashboard(*_frames(), **RENDER_KWARGS)
    for heading in ["Headline", "Dataset &times; asset", "Run coverage per dataset",
                    "Join strength", "Gaps"]:
        assert heading in page
    assert "movie10" in page
    assert "cneuromod2026" in page
    assert "atlas_tsnr_empty" in page
    # Headline counts: 2 raw runs, 1 matched into timeseries, 1 gated session.
    assert "raw BIDS runs" in page and ">2<" in page
    assert "sessions past the 1800s gate" in page
    # Self-contained: no external resource of any kind.
    assert "http://" not in page and "https://" not in page


def test_render_dashboard_reads_boolean_columns_round_tripped_as_text():
    """A TSV round trip can hand back "True"/"False" strings rather than bools."""
    run_inventory, sessions, subjects, coverage, gaps = _frames()
    run_inventory["in_timeseries"] = run_inventory["in_timeseries"].astype(str)
    sessions["passes_gate"] = sessions["passes_gate"].astype(str)
    page = render_dashboard(run_inventory, sessions, subjects, coverage, gaps,
                            **RENDER_KWARGS)
    assert "50%" in page  # 1 of 2 runs matched into timeseries
    assert "100%" in page  # 1 of 1 session past the gate


def test_render_dashboard_handles_empty_inventory():
    empty = pd.DataFrame()
    page = render_dashboard(empty, empty, empty, empty, empty, **RENDER_KWARGS)
    assert "No dataset found." in page
    assert "No run found." in page
    assert "No gap found." in page


def test_render_dashboard_escapes_table_values():
    frames = _frames(dataset="<script>bad</script>")
    page = render_dashboard(*frames, **RENDER_KWARGS)
    assert "<script>bad</script>" not in page
    assert "&lt;script&gt;bad&lt;/script&gt;" in page
