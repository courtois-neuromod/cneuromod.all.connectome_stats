"""Orchestrate `run-connectomes` for one dataset.

Discovers the dataset's subject `.h5` files already on disk (never fetches),
builds one session-level entity per session (runs standardized then
concatenated), computes every configured measure per network per entity,
joins QC, and hands the result to `analysis.connectome_store`. See CLAUDE.md,
"Settled analysis decisions", for the standardize-then-concatenate rule and
the fixed-edge-geometry rule. Session-level is the sole unit of analysis —
this is a data-quality assessment, not a study of estimators or of how
estimate quality scales with duration.
"""

import numpy as np
import pandas as pd

from analysis.connectome_estimators import DIAGNOSTIC_COLUMNS, connectome
from analysis.parcel_networks import edge_pairs, network_parcels
from analysis.qc_join import aggregate_session_qc, join_network_tsnr, join_run_qc
from analysis.timeseries_layout import parcellation_subdir
from analysis.timeseries_reader import list_entities, load_run, session_runs, standardize_run


def _subject_dirs(cneuromod_root, dataset, parcellation, subjects=None):
    base = cneuromod_root / dataset / "timeseries" / parcellation_subdir(parcellation)
    if not base.is_dir():
        return base, []
    dirs = sorted(p for p in base.glob("sub-*") if p.is_dir())
    if subjects:
        wanted = set(subjects)
        dirs = [p for p in dirs if p.name in wanted]
    return base, dirs


def _append_entity_measures(data, networks, measures, measure_vectors, diag_vectors):
    for network, parcel_indices in networks.items():
        sub = data[:, parcel_indices]
        for measure in measures:
            vector, diagnostics = connectome(sub, measure)
            measure_vectors[measure][network].append(vector)
            diag_vectors[measure][network].append(
                [diagnostics[column] for column in DIAGNOSTIC_COLUMNS]
            )


def build_dataset_connectomes(
    cneuromod_root, dataset, parcellation, network_order, labels,
    measures, tr_seconds, qa_root=None, subjects=None, on_subject_done=None,
):
    """Compute every entity's connectomes for one dataset.

    `on_subject_done(subject, subject_index, n_subjects, n_sessions)`, if
    given, is called after each subject directory finishes — a progress hook
    for the caller (see `tasks.run_connectomes`); this stays a plain callback
    so this module can still be exercised with pure function calls in tests.

    Returns `(index_frame, networks, edges, measure_arrays, diagnostic_arrays)`
    ready for `analysis.connectome_store.write_dataset_connectomes`, or `None`
    when the dataset has no `.h5` content on disk yet, or none of it has been
    fetched (caller should point at `invoke fetch-timeseries`).
    """
    _base, subject_dirs = _subject_dirs(cneuromod_root, dataset, parcellation, subjects)
    if not subject_dirs:
        return None

    networks = network_parcels(labels, network_order)
    edges = {name: edge_pairs(idx) for name, idx in networks.items()}

    rows = []
    qc_run_rows = []
    measure_vectors = {m: {n: [] for n in networks} for m in measures}
    diag_vectors = {m: {n: [] for n in networks} for m in measures}
    n_subjects = len(subject_dirs)

    for subject_index, subject_dir in enumerate(subject_dirs, start=1):
        subject = subject_dir.name.removeprefix("sub-")
        h5_files = [p for p in sorted(subject_dir.glob("*_timeseries.h5")) if p.exists()]
        if not h5_files:
            print(f"⚠️  {dataset}/sub-{subject}: no fetched '{parcellation}' .h5 content "
                  "on disk — run `invoke fetch-timeseries`. Skipping.")
            if on_subject_done is not None:
                on_subject_done(subject, subject_index, n_subjects, 0)
            continue
        h5_path = h5_files[0]
        entities = list_entities(h5_path)
        if not entities:
            if on_subject_done is not None:
                on_subject_done(subject, subject_index, n_subjects, 0)
            continue

        run_arrays = {}
        for entity in entities:
            raw = load_run(h5_path, entity["key"])
            standardized, _ = standardize_run(raw)
            run_arrays[entity["key"]] = standardized
            qc_run_rows.append({
                "dataset": dataset, "subject": subject, "task": entity["task"],
                "session": entity["session"], "run": entity["run"] or "",
                "n_volumes": standardized.shape[0],
            })

        n_sessions = 0
        for session, session_entities in session_runs(entities).items():
            arrays = [run_arrays[e["key"]] for e in session_entities]
            concatenated = np.concatenate(arrays, axis=0)
            tasks = sorted({e["task"] for e in session_entities})
            rows.append({
                "level": "session", "dataset": dataset, "subject": subject,
                "task": tasks[0] if len(tasks) == 1 else "multi", "session": session,
                "run": "", "run_ids": ",".join(e["run"] or "" for e in session_entities),
                "n_runs": len(session_entities), "n_volumes": concatenated.shape[0],
            })
            _append_entity_measures(concatenated, networks, measures, measure_vectors, diag_vectors)
            n_sessions += 1

        if on_subject_done is not None:
            on_subject_done(subject, subject_index, n_subjects, n_sessions)

    if not rows:
        return None

    index_frame = pd.DataFrame(rows)
    index_frame["duration_sec"] = index_frame["n_volumes"] * tr_seconds
    qc_run_frame = pd.DataFrame(qc_run_rows)
    qc_run_frame["duration_sec"] = qc_run_frame["n_volumes"] * tr_seconds
    index_frame = _join_qc(index_frame, qc_run_frame, dataset, qa_root, tr_seconds, list(networks))

    measure_arrays = {
        measure: {network: np.stack(vectors) for network, vectors in per_network.items()}
        for measure, per_network in measure_vectors.items()
    }
    diagnostic_arrays = {
        measure: {network: np.array(vectors) for network, vectors in per_network.items()}
        for measure, per_network in diag_vectors.items()
    }
    return index_frame, networks, edges, measure_arrays, diagnostic_arrays


def _join_qc(index_frame, qc_run_frame, dataset, qa_root, tr_seconds, network_names):
    """Attach session-level QC covariates, aggregated from per-run QC tables.

    Every session's connectome is stored once; QC (motion, tSNR) is only
    tabulated per run upstream (qa_figures), so `qc_run_frame` — one row per
    run, built purely to drive this aggregation — never itself becomes an
    output row.
    """
    tsnr_columns = [f"tsnr_{network}" for network in network_names]
    if qa_root is None:
        for column in ["fd_mean", "fd_num", "fd_perc", "fd_prop_gt02", "fd_prop_gt05",
                        "tsnr", "usable_duration_sec", "qc_matched", *tsnr_columns]:
            index_frame[column] = np.nan if column != "qc_matched" else False
        return index_frame

    run_qc = join_run_qc(qc_run_frame, qa_root, datasets=[dataset])
    run_qc = join_network_tsnr(run_qc, qa_root, network_names, datasets=[dataset])
    run_qc["usable_duration_sec"] = np.where(
        run_qc["fd_num"].notna(),
        run_qc["duration_sec"] - run_qc["fd_num"] * tr_seconds,
        np.nan,
    )

    session_qc = aggregate_session_qc(
        run_qc, tr_seconds,
        value_columns=["fd_mean", "fd_num", "fd_perc", "fd_prop_gt02", "fd_prop_gt05",
                        "tsnr", *tsnr_columns],
    )
    session_merge_keys = ["dataset", "subject", "session"]
    merge_frame = index_frame.copy()
    merge_frame["session"] = merge_frame["session"].astype(str).str.zfill(3)
    merged = merge_frame.merge(
        session_qc.drop(columns=["n_volumes", "duration_sec"]),
        on=session_merge_keys, how="left",
    )
    merged["session"] = index_frame["session"]
    merged["qc_matched"] = merged["qc_matched"].fillna(False).astype(bool)
    return merged
