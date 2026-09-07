"""Read the raw BIDS run inventory straight from a `{dataset}/bids` tree.

Pure functions, no invoke context — mirrors `analysis/qc_measures.py`'s
style. Every `{dataset}/bids` tree is an installed git tree (never annexed
content, per CLAUDE.md), so this is fully derivable offline: `*_bold.json`
sidecars are plain git blobs, readable without `datalad get`.

Mirrors `cneuromod.all.statistics`'s `analysis/statistics.py` (`_run_key`,
`_collect_run_map`, `_parse_run_info`), which was proven against this exact
data — reused here rather than re-derived, minus its `warnings.warn` calls
(this module returns data for a caller to report, per CLAUDE.md's
warn-don't-abort posture).
"""

import json
import re
from pathlib import Path

import pandas as pd

# Raw sidecars report 1.49s (see CLAUDE.md, "One thing to flag"), while
# `invoke.yaml`'s `tr_seconds` and CLAUDE.md's prose both say 1.5s. Recording
# the sidecar's own `tr_seconds` per run (rather than assuming the config
# value) is what lets a reader see this in `run_inventory.tsv` directly.
EXPECTED_TR = 1.49

# A dataset directory that is not a functional/BOLD dataset (structural only)
# and must never enter the inventory's dataset universe.
NON_FUNCTIONAL_DATASETS = {"anat"}

_STRIP_ENTITIES = re.compile(r"_(?:echo|part)-[^_]+")

_ENTITY_PATTERN = re.compile(
    r"sub-(?P<subject>[^_]+)"
    r"(?:_ses-(?P<session>[^_]+))?"
    r"_task-(?P<task>[^_]+?)"
    r"(?:_run-(?P<run>[^_]+))?"
    r"_bold$"
)

RUN_INVENTORY_COLUMNS = [
    "dataset", "subject", "session", "task", "run",
    "n_volumes", "tr_seconds", "duration_sec",
]


def canonical_run(value):
    """Normalize a run label to a bare integer string, `""` when absent.

    Handles the three raw-vs-h5-vs-qa_figures conventions CLAUDE.md documents:
    zero-padded (`"01"`), bare (`"1"`), and float-like (`"1.0"`).
    """
    if value is None:
        return ""
    text = str(value).strip().removeprefix("run-")
    text = re.sub(r"\.0$", "", text)
    if text in ("", "None", "nan"):
        return ""
    try:
        return str(int(text))
    except ValueError:
        return text


def _run_key(path):
    """Strip `_echo-*`/`_part-*` so multi-file runs (mario `part-`,
    emotion-videos `echo-`) collapse to one raw run."""
    stem = re.sub(r"\.nii(\.gz)?$", "", path.name)
    return _STRIP_ENTITIES.sub("", stem)


def _collect_run_map(bids_dir):
    """`{run_key: representative_path}` for every unique bold run under `bids_dir`.

    Two glob branches: session-organized layout, and the session-less layout
    (e.g. harrypotter) neither branch alone would cover.
    """
    run_map = {}
    for pattern in ("sub-*/ses-*/func/*_bold.nii*", "sub-*/func/*_bold.nii*"):
        for path in sorted(bids_dir.glob(pattern)):
            key = _run_key(path)
            run_map.setdefault(key, path)
    return run_map


def read_run_duration(bids_dir, rel_path):
    """`(n_volumes, tr_seconds)` from a run's BIDS sidecar JSON, or `(None, None)`."""
    nii_path = Path(bids_dir) / rel_path
    name = nii_path.name
    json_path = (
        nii_path.with_name(name[: -len(".nii.gz")] + ".json")
        if name.endswith(".nii.gz") else nii_path.with_suffix(".json")
    )
    if not json_path.is_file():
        return None, None
    try:
        meta = json.loads(json_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None, None

    tr = meta.get("RepetitionTime")
    acquisition_numbers = meta.get("time", {}).get("samples", {}).get("AcquisitionNumber", [])
    if acquisition_numbers:
        n_volumes = len(acquisition_numbers)
    else:
        shape = meta.get("dcmmeta_shape")
        n_volumes = shape[-1] if shape and len(shape) == 4 else None
    return n_volumes, tr


def list_raw_runs(cneuromod_root, dataset, skip_durations=False):
    """One row per unique raw BIDS run in `{dataset}/bids`.

    `--skip-durations` (tasks.py) skips reading sidecars — the only slow part
    (thousands of small JSON files) — leaving `n_volumes`/`tr_seconds`/
    `duration_sec` as `None`.
    """
    bids_dir = Path(cneuromod_root) / dataset / "bids"
    if not bids_dir.is_dir():
        return pd.DataFrame(columns=RUN_INVENTORY_COLUMNS)

    rows = []
    for key, path in _collect_run_map(bids_dir).items():
        match = _ENTITY_PATTERN.search(key)
        if not match:
            continue
        n_volumes = tr = None
        if not skip_durations:
            n_volumes, tr = read_run_duration(bids_dir, path.relative_to(bids_dir))
        rows.append({
            "dataset": dataset,
            "subject": match.group("subject"),
            "session": match.group("session") or "",
            "task": match.group("task"),
            "run": canonical_run(match.group("run")),
            "n_volumes": n_volumes,
            "tr_seconds": tr,
            "duration_sec": n_volumes * tr if n_volumes is not None and tr is not None else None,
        })
    if not rows:
        return pd.DataFrame(columns=RUN_INVENTORY_COLUMNS)
    return pd.DataFrame(rows, columns=RUN_INVENTORY_COLUMNS)
