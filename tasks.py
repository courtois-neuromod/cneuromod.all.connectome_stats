from pathlib import Path

from invoke import task


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _dataset_dir(c, name):
    """Where a `datasets:` entry is made available under source_data/."""
    return Path(c.config.get("datasets", {}).get(name, {})["output_dir"])


def _cneuromod_dir(c):
    """Where the cneuromod.all superdataset is made available under source_data/."""
    return _dataset_dir(c, "cneuromod_all")


def _qa_figures_dir(c):
    """Where the cneuromod.all.qa_figures checkout is made available under source_data/."""
    return _dataset_dir(c, "qa_figures")


def _list_datasets(c, marker):
    """Return sorted cneuromod.all dataset names that carry a `marker` subdataset.

    A "dataset" is a top-level directory of the superdataset (``floc``,
    ``movie10``, …). The marker directory only has to *exist* — it may still be
    an un-installed Datalad mountpoint, since content retrieval is `fetch`'s job.
    Returns an empty list when the superdataset is not present at all, so the
    stubs below degrade to a message rather than a traceback.
    """
    root = _cneuromod_dir(c)
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and not child.name.startswith(".") and (child / marker).is_dir()
    )


def _select_datasets(c, requested, smoke):
    """Resolve which datasets a run task should process."""
    from analysis.timeseries_layout import parse_labels

    if requested:
        return parse_labels(requested)
    if smoke:
        return [c.config.get("smoke_dataset", "movie10")]
    return _list_datasets(c, c.config.get("timeseries_marker", "timeseries"))


def _prefetch_into(root, subdir, match, failures):
    """Retrieve every timeseries file under `subdir`, one glob pattern at a time.

    Mutates `failures` in place — the caller's running set of paths this
    environment could not retrieve — adding what newly failed and dropping
    anything that has since succeeded. Returns the per-dataset counts.
    """
    from airoh.datalad import prefetch_pattern

    from analysis.timeseries_layout import timeseries_patterns

    counts = {"present": 0, "fetched": 0, "skipped": 0, "failed": 0}
    for pattern in timeseries_patterns():
        present, fetched, skipped, new_failures, resolved = prefetch_pattern(
            root, pattern, subdir=subdir, skip_set=failures, match=match,
        )
        counts["present"] += present
        counts["fetched"] += fetched
        counts["skipped"] += skipped
        counts["failed"] += len(new_failures)
        failures |= new_failures
        failures -= resolved
    return counts


def montage_dpi(c):
    """
    The DPI the montage is composed at, from `figures:` in invoke.yaml.

    This project has a single montage, so the first entry's `dpi` is the
    answer; a project with several would need to decide which one a given
    notebook's panels belong to. Defaults to 300, matching
    `airoh.figures.compose_figure`.
    """
    for entry in (c.config.get("figures") or {}).values():
        return entry.get("dpi", 300)
    return 300


# --------------------------------------------------------------------------- #
# Fetch
# --------------------------------------------------------------------------- #
@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink "
              "instead of cloning (defaults to the `source:` key in "
              "invoke.yaml, i.e. ../cneuromod.all).",
})
def fetch_cneuromod(c, source=None):
    """
    Make the cneuromod.all Datalad superdataset available under source_data/.

    Symlinks an existing local checkout, or `datalad clone`s the remote when
    none is found. This retrieves the dataset *tree* only — no annexed file
    content — so it is cheap and safe to repeat. No-op when the checkout is
    already in place.
    """
    from airoh.datalad import install_dataset
    install_dataset(c, "cneuromod_all", source=source)


@task(help={
    "source": "Path to an existing local cneuromod.all.qa_figures checkout to "
              "symlink instead of cloning (defaults to the `source:` key in "
              "invoke.yaml, i.e. ../git/cneuromod.all.qa_figures).",
})
def fetch_qa_figures(c, source=None):
    """
    Make the cneuromod.all.qa_figures repository available under source_data/.

    Unlike cneuromod.all, this dataset holds no annexed content — every tracked
    file is a plain git blob — so installing the tree *is* retrieving the data;
    no content-fetch step follows it. Coverage of the per-network tSNR tables is
    partial (see source_data/CONTENT.md). No-op when the checkout is already in
    place.
    """
    from airoh.datalad import install_dataset
    install_dataset(c, "qa_figures", source=source)


@task
def fetch_atlas(c):
    """
    Retrieve the MNI group atlas the montage's glass-brain network key is drawn
    from (`anat/atlases`, display only).

    This is the single place in the project that touches `anat/atlases`, a
    deliberate exception to the rule in CLAUDE.md, "The parcel -> network
    lookup". It exists because a glass brain needs a group-space map, while the
    individualized `_dseg.nii.gz` the parcel -> network lookup reads is in each
    subject's own functional space. That lookup is unaffected: it still reads
    the timeseries repos, never this file. See `analysis/atlas_maps.py`.

    Tolerant like every other content fetch — warns and skips if the annexed
    dseg cannot be retrieved, in which case the notebook simply omits the
    glass-brain key panel.
    """
    from airoh.datalad import get_data

    from analysis.atlas_maps import atlas_paths

    dseg_path, labels_path = atlas_paths(_cneuromod_dir(c))
    if dseg_path.is_file() and labels_path.is_file():
        print(f"🫧 {dseg_path.name} already present — nothing to fetch")
        return

    root = _cneuromod_dir(c)
    for path in (dseg_path, labels_path):
        get_data(c, "cneuromod_all", path=str(path.relative_to(root)), strict=False)


@task(help={
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the "
               "fetch to (default: every dataset carrying a timeseries "
               "subdataset).",
    "subject": "Comma-separated subject labels (e.g. 01,03) to restrict the "
               "fetch to.",
    "strict": "Raise if a timeseries subdataset fails to install. Content "
              "retrieval stays tolerant either way.",
    "parcellation": "Which parcellation's files to fetch (default: the "
                    "configured `parcellation`).",
})
def fetch_timeseries(c, dataset=None, subject=None, strict=False, parcellation=None):
    """
    Retrieve the parcelled BOLD timeseries assets for the configured
    `parcellation`.

    For each selected dataset: install `{dataset}/{timeseries_marker}` with
    `airoh.datalad.install_subdataset` — a subdataset nested inside another
    subdataset, which plain `git submodule` cannot reach, hence `datalad get -n`
    — then retrieve the `.h5` timeseries, the `_dseg.nii.gz` parcellation and
    the grey-matter mask via `airoh.datalad.prefetch_pattern`.

    Two different tolerances, deliberately. Installing a subdataset only needs
    the public git tree, so a failure there means the retrieval route is broken
    and `--strict` (used by `run-smoke`) makes it fatal. Pulling annexed content
    hits a credentialed S3 remote that not everyone can reach, so it always
    warns and skips — see source_data/CONTENT.md, "Access requirements".

    Paths that failed are remembered in `source_data/.fetch_failures.json` and
    not retried on the next call; a path that later succeeds is dropped from
    that cache.
    """
    from airoh.datalad import install_subdataset, load_known_failures, save_known_failures

    from analysis.timeseries_layout import parcellation_subdir, parse_labels, subject_filter

    root = _cneuromod_dir(c)
    marker = c.config.get("timeseries_marker", "timeseries")
    parcellation = parcellation or c.config.get("parcellation")
    source_dir = Path(c.config.get("source_data_dir"))

    names = _select_datasets(c, dataset, smoke=False)
    if not names:
        print(f"⚠️  No dataset carries a '{marker}' subdataset under {root}.")
        print("   Run `invoke fetch-cneuromod` first — this step reads the "
              "superdataset, it does not create it.")
        return

    match = subject_filter(parse_labels(subject, prefix="sub-"))
    failures = load_known_failures(source_dir)
    totals = {"present": 0, "fetched": 0, "skipped": 0, "failed": 0}

    print(f"📥 Fetching '{parcellation}' timeseries for {len(names)} dataset(s): "
          f"{', '.join(names)}")

    for name in names:
        install_subdataset(f"{name}/{marker}", root, strict=strict)
        subdir = f"{name}/{marker}/{parcellation_subdir(parcellation)}"
        counts = _prefetch_into(root, subdir, match, failures)

        for key, value in counts.items():
            totals[key] += value
        print(f"   {name}: {counts['present']} present, {counts['fetched']} fetched, "
              f"{counts['skipped']} skipped (known failures), {counts['failed']} failed")

    save_known_failures(source_dir, failures)
    print(f"📦 timeseries totals — {totals['present']} present, "
          f"{totals['fetched']} fetched, {totals['skipped']} skipped, "
          f"{totals['failed']} failed")
    if totals["failed"] or totals["skipped"]:
        print("   Inaccessible content is expected without CNeuroMod S3 "
              "credentials; see source_data/CONTENT.md.")


@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink "
              "instead of cloning.",
    "qa_figures_source": "Path to an existing local cneuromod.all.qa_figures "
                         "checkout to symlink instead of cloning.",
    "dataset": "Comma-separated dataset names to restrict the fetch to.",
    "subject": "Comma-separated subject labels to restrict the fetch to.",
    "strict": "Raise if a timeseries subdataset fails to install. Content "
              "retrieval stays tolerant either way.",
})
def fetch(c, source=None, qa_figures_source=None, dataset=None, subject=None, strict=False):
    """
    Retrieve all source data: the cneuromod.all superdataset, the timeseries
    assets the analysis steps read, and the qa_figures QC tables.

    Records what each asset actually resolved to in source_data/MANIFEST.json,
    so the inputs a later run consumed stay identifiable — including the commit
    of a symlinked external checkout. See CLAUDE.md, "Recording asset versions".
    """
    from airoh.provenance import record_sources

    fetch_cneuromod(c, source=source)
    fetch_timeseries(c, dataset=dataset, subject=subject, strict=strict)
    fetch_atlas(c)
    fetch_qa_figures(c, source=qa_figures_source)
    fetch_parcel_labels(c)
    record_sources(c)
    print("✅ fetch complete.")


# --------------------------------------------------------------------------- #
# Analysis steps (chunk = dataset)
# --------------------------------------------------------------------------- #
def _parcellation_config(c, parcellation=None):
    """Resolve a parcellation's network order and labels-file path from `invoke.yaml`."""
    parcellation = parcellation or c.config.get("parcellation")
    entry = c.config.get("parcellations", {}).get(parcellation)
    if entry is None:
        raise ValueError(f"No `parcellations.{parcellation}` entry in invoke.yaml")
    return parcellation, entry["network_order"], Path(entry["labels_file"])


@task(help={
    "source": "Path to an existing labels TSV to symlink/copy instead of "
              "building one (columns: index, name, network).",
    "parcellation": "Which parcellation to build labels for (default: the "
                    "configured `parcellation`).",
    "subject": "cneuromod2026 only: which subject's dseg.nii.gz to read the "
              "label values from (default: the smoke subject).",
    "dataset": "cneuromod2026 only: which dataset's dseg.nii.gz to read "
              "(default: the smoke dataset).",
})
def fetch_parcel_labels(c, source=None, parcellation=None, subject=None, dataset=None):
    """
    Write `source_data/{parcellation}_networks.tsv`: the parcel -> network
    lookup table `run-connectomes` needs, since none ships in the timeseries
    repos (see CLAUDE.md, "The parcel->network lookup").

    schaefer1000: built from nilearn's bundled Schaefer-2018 atlas (7 Yeo
    cortical networks), no fetch beyond nilearn's own cache.

    cneuromod2026: built by reading one already-fetched subject's individualized
    `_dseg.nii.gz` from the timeseries repo (never `anat/atlases`) and decoding
    its integer label values under a documented assumption — see
    `analysis.parcel_networks.build_cneuromod2026_labels`. Requires
    `invoke fetch-timeseries --dataset ... --parcellation cneuromod2026` to
    have already pulled that subject's content.
    """
    from analysis.parcel_networks import build_cneuromod2026_labels, build_schaefer1000_labels
    from analysis.timeseries_layout import parcellation_subdir

    parcellation = parcellation or c.config.get("parcellation")
    entry = c.config.get("parcellations", {}).get(parcellation)
    if entry is None:
        raise ValueError(f"No `parcellations.{parcellation}` entry in invoke.yaml")
    labels_path = Path(entry["labels_file"])

    if labels_path.exists() and source is None:
        print(f"🫧 {labels_path} already exists — nothing to do")
        return

    if source is not None:
        from airoh.acquisition import fetch_data
        fetch_data(c, labels_path, source=source)
        print(f"🔗 Linked {labels_path} from {source}")
        return

    labels_path.parent.mkdir(parents=True, exist_ok=True)
    if parcellation == "schaefer1000":
        labels = build_schaefer1000_labels()
    else:
        dataset = dataset or c.config.get("smoke_dataset", "movie10")
        subject = f"sub-{(subject or c.config.get('smoke_subject', '02')).removeprefix('sub-')}"
        root = _cneuromod_dir(c)
        subdir = root / dataset / "timeseries" / parcellation_subdir(parcellation) / subject
        dseg_files = sorted(subdir.glob("*_dseg.nii.gz"))
        if not dseg_files:
            print(f"⚠️  No dseg found at {subdir} — run `invoke fetch-timeseries "
                  f"--dataset {dataset} --subject {subject.removeprefix('sub-')} "
                  f"--parcellation {parcellation}` first (needs S3 credentials).")
            return
        labels = build_cneuromod2026_labels(dseg_files[0])

    labels.to_csv(labels_path, sep="\t", index=False)
    print(f"📝 Wrote {labels_path}: {len(labels)} parcels, "
          f"{labels['network'].nunique()} networks")


@task
def clean_parcel_labels(c):
    """Remove every built `{parcellation}_networks.tsv` labels file."""
    for entry in c.config.get("parcellations", {}).values():
        path = Path(entry["labels_file"])
        if path.exists():
            path.unlink()
            print(f"🧹 Removed {path}")


@task(help={
    "dataset": "Comma-separated dataset names to process (default: all with a "
               "timeseries subdataset).",
    "subject": "Comma-separated subject labels to restrict to.",
    "parcellation": "Which parcellation to read (default: the configured "
                    "`parcellation`).",
    "smoke": "Process only the smoke dataset/subject (fast end-to-end check).",
})
def run_connectomes(c, dataset=None, subject=None, parcellation=None, smoke=False):
    """
    Compute per-network, per-session connectomes (Pearson + regularized
    partial correlation) for the selected dataset(s).

    Reads only files already on disk — retrieval is `invoke fetch`'s job, this
    step never calls `datalad get`. Writes one `output_data/connectomes/
    {dataset}_{parcellation}.h5` per dataset (see analysis/connectome_store.py
    for the layout) and skips any dataset whose file already exists.
    """
    from analysis.connectome_store import write_dataset_connectomes
    from analysis.connectomes import build_dataset_connectomes
    from analysis.parcel_networks import load_parcel_labels
    from analysis.timeseries_layout import parse_labels

    output_dir = Path(c.config.get("output_data_dir")) / "connectomes"
    names = _select_datasets(c, dataset, smoke)
    if not names:
        print("⚠️  No dataset carries a timeseries subdataset — run `invoke fetch-cneuromod` first.")
        return

    parcellation, network_order, labels_path = _parcellation_config(c, parcellation)
    if smoke:
        parcellation = c.config.get("smoke_parcellation", parcellation)
        parcellation, network_order, labels_path = _parcellation_config(c, parcellation)
    if not labels_path.exists():
        print(f"⚠️  {labels_path} not found — run `invoke fetch-parcel-labels "
              f"--parcellation {parcellation}` first.")
        return
    labels = load_parcel_labels(labels_path)

    subjects = parse_labels(subject, prefix="sub-")
    if smoke and not subjects:
        subjects = [f"sub-{c.config.get('smoke_subject', '01')}"]
    measures = c.config.get("connectome_measures") or [
        "pearson", "partial_ledoitwolf",
    ]
    tr_seconds = c.config.get("tr_seconds", 1.5)
    qa_root = _qa_figures_dir(c)
    if not qa_root.is_dir():
        qa_root = None

    def _report_subject(subject, subject_index, n_subjects, n_sessions):
        print(f"   sub-{subject} ({subject_index}/{n_subjects}): "
              f"{n_sessions} session(s)", flush=True)

    for name in names:
        out_path = output_dir / f"{name}_{parcellation}.h5"
        if out_path.exists():
            print(f"🫧 {out_path} already exists — skipping {name}")
            continue

        print(f"⏳ {name}: computing connectomes...")
        result = build_dataset_connectomes(
            cneuromod_root=_cneuromod_dir(c), dataset=name, parcellation=parcellation,
            network_order=network_order, labels=labels, measures=measures,
            tr_seconds=tr_seconds, qa_root=qa_root, subjects=subjects or None,
            on_subject_done=_report_subject,
        )
        if result is None:
            print(f"⚠️  {name}: no '{parcellation}' timeseries on disk — "
                  f"run `invoke fetch-timeseries --dataset {name} "
                  f"--parcellation {parcellation}` first.")
            continue

        index_frame, networks, edges, measure_arrays, diagnostic_arrays = result
        write_dataset_connectomes(
            out_path, index_frame, networks, edges, measure_arrays, diagnostic_arrays,
            parcellation=parcellation, tr_seconds=tr_seconds,
            labels_checksum=_checksum_file(labels_path),
        )
        print(f"✅ {name}: {len(index_frame)} sessions "
              f"-> {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


def _checksum_file(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@task(help={
    "dataset": "Comma-separated dataset names to restrict analysis B to "
               "(default: every connectome file present).",
    "smoke": "Aggregate only what the smoke run produced.",
})
def run_group_stats(c, dataset=None, smoke=False):
    """
    Aggregate per-session connectomes into the two headline analyses (CLAUDE.md,
    "Scientific objective"): cross-context similarity (analysis B, all datasets)
    and the friends longitudinal drift control (analysis A). Both gated
    (`usable_duration_sec >= group_stats.min_usable_seconds`) and ungated.

    Also computes a robustness-tier check on analysis B: the same
    within-/between-task contrast restricted one domain at a time to
    `analysis.group_stats.DOMAIN_DATASETS` (movies, videogames, stories).

    Reads output_data/connectomes/{dataset}_{parcellation}.h5 (`run-connectomes`'s
    output) and writes ten tidy TSVs under output_data/group_stats/. Skips when
    cross_context.tsv already exists.
    """
    import numpy as np
    import pandas as pd

    from analysis.connectome_store import load_index
    from analysis.group_stats import (
        cross_context_summary,
        domain_cross_context_summary,
        longitudinal_summary,
        network_quality,
        usable_sessions,
    )
    from analysis.similarity import discover_connectome_files
    from analysis.timeseries_layout import parse_labels

    output_dir = Path(c.config.get("output_data_dir")) / "group_stats"
    out_path = output_dir / "cross_context.tsv"
    if out_path.exists():
        print(f"🫧 {out_path} already exists — skipping run-group-stats")
        return

    parcellation, network_order, _ = _parcellation_config(c, None)
    if smoke:
        parcellation = c.config.get("smoke_parcellation", parcellation)
        parcellation, network_order, _ = _parcellation_config(c, parcellation)

    measure = c.config.get("analysis_measure", "pearson")
    gate_config = c.config.get("group_stats", {})
    min_usable_seconds = gate_config.get("min_usable_seconds", 1800)
    n_bins = gate_config.get("similarity_bins", 60)

    connectome_dir = Path(c.config.get("output_data_dir")) / "connectomes"
    paths, skipped = discover_connectome_files(connectome_dir, parcellation)
    for path, reason in skipped:
        print(f"⚠️  skipping {path.name}: {reason}")
    names = parse_labels(dataset)
    if names:
        paths = [p for p in paths if p.stem.rsplit(f"_{parcellation}", 1)[0] in names]
    if not paths:
        print(f"⚠️  No connectome files for parcellation={parcellation} — "
              "run `invoke run-connectomes` first.")
        return

    print(f"⏳ analysis B (cross-context): {len(paths)} connectome file(s), "
          f"gate={min_usable_seconds}s")
    all_index = pd.concat([load_index(p) for p in paths], ignore_index=True)
    _, session_gate = usable_sessions(all_index, min_usable_seconds)
    cross_context_result = cross_context_summary(
        paths, network_order, measure, min_usable_seconds, n_bins
    )

    print("⏳ domain-restricted cross-context (movies, videogames, stories)")
    domain_result = domain_cross_context_summary(
        paths, parcellation, _cneuromod_dir(c), network_order, measure,
        min_usable_seconds, n_bins,
    )

    friends_paths = [p for p in paths if p.stem.startswith("friends_")]
    if len(friends_paths) == 1:
        print("⏳ analysis A (friends longitudinal)")
        longitudinal_result = longitudinal_summary(
            friends_paths[0], _cneuromod_dir(c), parcellation, network_order, measure,
            min_usable_seconds, n_bins,
        )
    else:
        print(f"⚠️  no single friends_{parcellation}.h5 found ({len(friends_paths)} "
              "candidates) — skipping analysis A (longitudinal tables will be empty)")
        longitudinal_result = None

    tsnr_quality = network_quality(all_index, network_order)
    cross_bins = cross_context_result["cross_context"]
    within_cross = cross_bins[
        (cross_bins["bin"] == "within-subject / within-dataset") & (cross_bins["gate"] == "gated")
    ][["network", "median", "n_edges_valid", "n_edges_total"]].rename(
        columns={"median": "within_subject_median_cross_context"}
    )
    network_quality_frame = tsnr_quality.merge(within_cross, on="network", how="left")

    if longitudinal_result is not None:
        long_bins = longitudinal_result["longitudinal_bins"]
        within_long = long_bins[
            (long_bins["bin"] == "within-subject / within-season") & (long_bins["gate"] == "gated")
        ][["network", "median"]].rename(columns={"median": "within_subject_median_longitudinal"})
        network_quality_frame = network_quality_frame.merge(within_long, on="network", how="left")
    else:
        network_quality_frame["within_subject_median_longitudinal"] = np.nan

    output_dir.mkdir(parents=True, exist_ok=True)
    empty_bins = pd.DataFrame(columns=[
        "bin", "n", "median", "q25", "q75", "mean", "sd",
        "network", "gate", "measure", "n_edges_valid", "n_edges_total",
    ])
    empty_lag = pd.DataFrame(columns=[
        "lag_value", "n", "median", "q25", "q75", "lag_type",
        "network", "gate", "measure", "pair_type",
    ])

    cross_context_result["cross_context"].to_csv(out_path, sep="\t", index=False)
    histograms = [cross_context_result["histograms"]]
    if longitudinal_result is not None:
        longitudinal_result["longitudinal_bins"].to_csv(
            output_dir / "longitudinal_bins.tsv", sep="\t", index=False)
        longitudinal_result["longitudinal_lag"].to_csv(
            output_dir / "longitudinal_lag.tsv", sep="\t", index=False)
        histograms.append(longitudinal_result["histograms"])
    else:
        empty_bins.to_csv(output_dir / "longitudinal_bins.tsv", sep="\t", index=False)
        empty_lag.to_csv(output_dir / "longitudinal_lag.tsv", sep="\t", index=False)

    network_quality_frame.to_csv(output_dir / "network_quality.tsv", sep="\t", index=False)
    session_gate.to_csv(output_dir / "session_gate.tsv", sep="\t", index=False)
    pd.concat(histograms, ignore_index=True).to_csv(
        output_dir / "pair_histograms.tsv", sep="\t", index=False)
    cross_context_result["duration_balance"].to_csv(
        output_dir / "duration_balance.tsv", sep="\t", index=False)

    domain_result["cross_context"].to_csv(
        output_dir / "domain_cross_context.tsv", sep="\t", index=False)
    domain_result["histograms"].to_csv(
        output_dir / "domain_pair_histograms.tsv", sep="\t", index=False)
    domain_result["duration_balance"].to_csv(
        output_dir / "domain_duration_balance.tsv", sep="\t", index=False)

    print(f"✅ run-group-stats: wrote 10 tables to {output_dir}")


@task(help={
    "dataset": "Comma-separated dataset names to restrict analysis to "
               "(default: every connectome file present).",
    "smoke": "Aggregate only what the smoke run produced.",
})
def run_motion_strata(c, dataset=None, smoke=False):
    """
    Robustness-tier check (CLAUDE.md, "Motion stratification"): does
    connectome similarity depend on head motion, and does claim 2's
    within-task > between-task ordering survive when motion is held down?

    Splits the QC-covered population (gated AND `fd_mean` present — mario and
    harrypotter have zero `fd_mean` coverage upstream, so they never enter
    this analysis) into low/high motion strata, below/above the median
    `fd_mean` within each (subject, dataset) cell — orthogonal to both by
    construction, since motion is strongly subject- and dataset-specific. The
    plain within-subject median split is written alongside it as a secondary
    `split` value in the same tables. Standalone figure, not placed in the
    headline montage — see CLAUDE.md.

    Reads output_data/connectomes/{dataset}_{parcellation}.h5 (`run-connectomes`'s
    output) and writes five tidy TSVs under output_data/motion_strata/. Skips
    when motion_strata.tsv already exists.
    """
    import pandas as pd

    from analysis.connectome_store import load_index
    from analysis.motion_strata import (
        motion_balance,
        motion_permutation,
        motion_sessions_table,
        motion_summary,
    )
    from analysis.similarity import discover_connectome_files
    from analysis.timeseries_layout import parse_labels

    output_dir = Path(c.config.get("output_data_dir")) / "motion_strata"
    out_path = output_dir / "motion_strata.tsv"
    if out_path.exists():
        print(f"🫧 {out_path} already exists — skipping run-motion-strata")
        return

    parcellation, network_order, _ = _parcellation_config(c, None)
    if smoke:
        parcellation = c.config.get("smoke_parcellation", parcellation)
        parcellation, network_order, _ = _parcellation_config(c, parcellation)

    measure = c.config.get("analysis_measure", "pearson")
    gate_config = c.config.get("group_stats", {})
    min_usable_seconds = gate_config.get("min_usable_seconds", 1800)
    n_bins = gate_config.get("similarity_bins", 60)
    n_permutations = c.config.get("motion_strata", {}).get("n_permutations", 1000)

    connectome_dir = Path(c.config.get("output_data_dir")) / "connectomes"
    paths, skipped = discover_connectome_files(connectome_dir, parcellation)
    for path, reason in skipped:
        print(f"⚠️  skipping {path.name}: {reason}")
    names = parse_labels(dataset)
    if names:
        paths = [p for p in paths if p.stem.rsplit(f"_{parcellation}", 1)[0] in names]
    if not paths:
        print(f"⚠️  No connectome files for parcellation={parcellation} — "
              "run `invoke run-connectomes` first.")
        return

    print(f"⏳ motion strata: {len(paths)} connectome file(s), gate={min_usable_seconds}s")
    all_index = pd.concat([load_index(p) for p in paths], ignore_index=True)
    sessions = motion_sessions_table(all_index, min_usable_seconds)
    if sessions.empty:
        print("⚠️  No QC-covered sessions (gated AND fd_mean present) — "
              "writing empty tables. Likely a smoke run or fd_mean-uncovered datasets only.")

    summary = motion_summary(paths, network_order, measure, min_usable_seconds, n_bins)
    balance = motion_balance(all_index, min_usable_seconds)
    permutation = motion_permutation(
        paths, network_order, measure, min_usable_seconds, n_permutations=n_permutations,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    summary["motion_bins"].to_csv(out_path, sep="\t", index=False)
    summary["histograms"].to_csv(output_dir / "motion_pair_histograms.tsv", sep="\t", index=False)
    balance.to_csv(output_dir / "motion_balance.tsv", sep="\t", index=False)
    permutation.to_csv(output_dir / "motion_permutation.tsv", sep="\t", index=False)
    sessions.to_csv(output_dir / "motion_sessions.tsv", sep="\t", index=False)

    print(f"✅ run-motion-strata: wrote 5 tables to {output_dir}")


@task(help={
    "dataset": "Comma-separated dataset names to restrict analysis to "
               "(default: every connectome file present).",
    "smoke": "Aggregate only what the smoke run produced.",
})
def run_tsnr_strata(c, dataset=None, smoke=False):
    """
    Robustness-tier check (CLAUDE.md, "tSNR stratification"): does connectome
    similarity depend on acquisition signal quality, and does claim 2's
    within-task > between-task ordering survive when tSNR is held high?

    The companion to `run-motion-strata` on the other QC axis, over the same
    QC-covered population (gated AND `fd_mean` present). Splits it into
    low/high tSNR strata, below/above the median within each (subject,
    dataset) cell, under two definitions carried side by side in a
    `stratum_def` column: `raw` tSNR, and `fd_residual` — tSNR residualized on
    `fd_mean` within the same cell, which is what separates a signal-quality
    effect from the motion effect the two axes share (r=-0.68). Whole-brain
    tSNR only: `atlas_tsnr` is empty upstream for every gated dataset, so the
    per-network columns are non-NaN for none of the covered sessions.
    Standalone figure, not placed in the headline montage — see CLAUDE.md.

    Reads output_data/connectomes/{dataset}_{parcellation}.h5 (`run-connectomes`'s
    output) and writes five tidy TSVs under output_data/tsnr_strata/. Skips
    when tsnr_strata.tsv already exists.
    """
    import pandas as pd

    from analysis.connectome_store import load_index
    from analysis.similarity import discover_connectome_files
    from analysis.timeseries_layout import parse_labels
    from analysis.tsnr_strata import (
        tsnr_balance,
        tsnr_permutation,
        tsnr_sessions_table,
        tsnr_summary,
    )

    output_dir = Path(c.config.get("output_data_dir")) / "tsnr_strata"
    out_path = output_dir / "tsnr_strata.tsv"
    if out_path.exists():
        print(f"🫧 {out_path} already exists — skipping run-tsnr-strata")
        return

    parcellation, network_order, _ = _parcellation_config(c, None)
    if smoke:
        parcellation = c.config.get("smoke_parcellation", parcellation)
        parcellation, network_order, _ = _parcellation_config(c, parcellation)

    measure = c.config.get("analysis_measure", "pearson")
    gate_config = c.config.get("group_stats", {})
    min_usable_seconds = gate_config.get("min_usable_seconds", 1800)
    n_bins = gate_config.get("similarity_bins", 60)
    n_permutations = c.config.get("tsnr_strata", {}).get("n_permutations", 1000)

    connectome_dir = Path(c.config.get("output_data_dir")) / "connectomes"
    paths, skipped = discover_connectome_files(connectome_dir, parcellation)
    for path, reason in skipped:
        print(f"⚠️  skipping {path.name}: {reason}")
    names = parse_labels(dataset)
    if names:
        paths = [p for p in paths if p.stem.rsplit(f"_{parcellation}", 1)[0] in names]
    if not paths:
        print(f"⚠️  No connectome files for parcellation={parcellation} — "
              "run `invoke run-connectomes` first.")
        return

    print(f"⏳ tSNR strata: {len(paths)} connectome file(s), gate={min_usable_seconds}s")
    all_index = pd.concat([load_index(p) for p in paths], ignore_index=True)
    sessions = tsnr_sessions_table(all_index, min_usable_seconds)
    if sessions.empty:
        print("⚠️  No QC-covered sessions (gated AND fd_mean present) — "
              "writing empty tables. Likely a smoke run or QC-uncovered datasets only.")

    summary = tsnr_summary(paths, network_order, measure, min_usable_seconds, n_bins)
    balance = tsnr_balance(all_index, min_usable_seconds)
    permutation = tsnr_permutation(
        paths, network_order, measure, min_usable_seconds, n_permutations=n_permutations,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    summary["tsnr_bins"].to_csv(out_path, sep="\t", index=False)
    summary["histograms"].to_csv(output_dir / "tsnr_pair_histograms.tsv", sep="\t", index=False)
    balance.to_csv(output_dir / "tsnr_balance.tsv", sep="\t", index=False)
    permutation.to_csv(output_dir / "tsnr_permutation.tsv", sep="\t", index=False)
    sessions.to_csv(output_dir / "tsnr_sessions.tsv", sep="\t", index=False)

    print(f"✅ run-tsnr-strata: wrote 5 tables to {output_dir}")


@task
def run_figure_layout(c):
    """
    Write every montage's panel geometry to figures_dir/panel_sizes.json.

    Read by the notebooks so every placed panel renders at exactly the physical
    size the montage allocates it. Always re-runs, never skipped: it is cheap,
    and a box resized in Inkscape must take effect on the very next
    `invoke run`.
    """
    from airoh.figures import figure_layout
    figure_layout(c)


@task(pre=[run_figure_layout])
def run_notebooks(c):
    """
    Generate figure panels from the tables in output_data/ using notebooks.

    `run-figure-layout` runs first because the notebooks size their placed
    panels from the geometry it writes — and `clean-figures` wipes that file
    along with the figures dir it lives in. (`run` calls both explicitly, in
    the same order; this `pre=` only covers invoking `run-notebooks` on its
    own.)

    Exports the montage's configured DPI as FIGURE_MONTAGE_DPI so notebooks
    save at it rather than hardcoding 300 — panel *pixels* must equal
    figsize × dpi for placement to stay 1:1, so the resolution has to come
    from the same config the montage is composed with.
    """
    import os

    from airoh.utils import ensure_dir_exist
    from airoh.utils import run_notebooks as airoh_run_notebooks

    notebooks_dir = Path(c.config.get("notebooks_dir"))
    figures_base = Path(c.config.get("figures_dir")).resolve()

    os.environ["FIGURE_MONTAGE_DPI"] = str(montage_dpi(c))

    ensure_dir_exist(c, "output_data_dir")
    airoh_run_notebooks(c, notebooks_dir, figures_base,
                        keys=["source_data_dir", "output_data_dir", "figures_dir"])


@task
def compose_figure(c):
    """
    Render the hand-authored connectome_figure.svg to PNG with Inkscape.

    Optional: Inkscape is only needed to recompose the final figure, never to
    reproduce a panel, so a missing binary warns and returns rather than
    failing the run.
    """
    from airoh.figures import compose_figure as airoh_compose_figure
    airoh_compose_figure(c)


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
@task(help={
    "dataset": "Comma-separated dataset names to process (default: all with a "
               "timeseries subdataset).",
    "force": "Delete every computed output first, then run from scratch.",
})
def run(c, dataset=None, force=False):
    """
    Full pipeline: connectomes → group stats → motion strata → figure layout → notebooks →
    composed figure.

    `run` does NOT pull data: it reads only what `invoke fetch` already
    retrieved, and no step calls `datalad get`. **Run `invoke fetch` first.**

    Steps are called directly rather than through `pre=`, so that flags like
    --force reach them: a `pre=` chain runs before this body, which would be
    too late.

    Every step caches by checking whether its output already exists, so a
    repeated `run` does nothing. That is deliberate — but it also means an
    edited script or notebook will NOT re-run on its own. `--force` is the
    sledgehammer: clean everything, then start over. To redo one step, call its
    `clean-{name}` task and run again. `run-figure-layout` is the one
    deliberate exception: it always re-runs (see its docstring).
    """
    from airoh.provenance import record_run

    if force:
        print("💥 --force: removing every computed output before running")
        clean(c)
    run_connectomes(c, dataset=dataset)
    run_group_stats(c)
    run_motion_strata(c)
    run_tsnr_strata(c)
    run_figure_layout(c)
    run_notebooks(c)
    compose_figure(c)
    record_run(c, tasks="run-connectomes,run-group-stats,run-motion-strata,"
                        "run-tsnr-strata,run-figure-layout,run-notebooks,compose-figure")
    print("all analyses completed")


@task
def run_smoke(c):
    """
    Smoke test: a minimal end-to-end pass over the whole pipeline.

    Calls the steps directly (rather than via `pre=`) so each can be given a
    reduced workload. The point is to exercise the plumbing quickly, not to
    produce real results. Unlike `run`, this is the one mode that fetches, so
    it can check retrieval too.

    `strict=True` makes a failed *subdataset install* fatal: that only needs the
    public git tree, so failing there means the retrieval route is genuinely
    broken. Annexed content stays tolerant even here, because no timeseries
    dataset is anonymously readable yet — see source_data/CONTENT.md.
    """
    from airoh.provenance import record_sources

    smoke_dataset = c.config.get("smoke_dataset", "movie10")
    smoke_subject = c.config.get("smoke_subject", "01")
    smoke_parcellation = c.config.get("smoke_parcellation", c.config.get("parcellation"))

    fetch_cneuromod(c)
    fetch_timeseries(c, dataset=smoke_dataset, subject=smoke_subject, strict=True,
                      parcellation=smoke_parcellation)
    fetch_qa_figures(c)
    fetch_parcel_labels(c, parcellation=smoke_parcellation, dataset=smoke_dataset,
                         subject=smoke_subject)
    record_sources(c)

    run_connectomes(c, smoke=True)
    run_group_stats(c, smoke=True)
    run_motion_strata(c, smoke=True)
    run_tsnr_strata(c, smoke=True)
    run_figure_layout(c)
    run_notebooks(c)
    compose_figure(c)
    print("✅ Smoke test complete.")


@task(help={
    "skip": "Comma-separated check names to skip.",
    "strict": "Treat warnings as failures.",
})
def verify(c, skip=None, strict=False):
    """
    Check that the code, config, data and docs still agree.

    Run this before committing. It is deliberately NOT part of `run`:
    reproducing results should never depend on documentation hygiene. See
    CLAUDE.md, "Verification", for what each check covers.
    """
    from airoh.verify import verify as airoh_verify
    airoh_verify(c, skip=skip, strict=strict)


# --------------------------------------------------------------------------- #
# Clean
# --------------------------------------------------------------------------- #
@task
def clean_connectomes(c):
    """Remove the per-dataset connectome tables."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "connectomes/*")


@task
def clean_group_stats(c):
    """Remove the group-level statistics tables."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "group_stats/*")


@task
def clean_motion_strata(c):
    """Remove the motion-stratified robustness tables."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "motion_strata/*")


@task
def clean_tsnr_strata(c):
    """Remove the tSNR-stratified robustness tables."""
    from airoh.utils import clean_folder
    clean_folder(c, "output_data_dir", "tsnr_strata/*")


@task
def clean_figures(c):
    """
    Remove the figures dir (per-notebook panels, the "already ran" sentinels,
    and panel_sizes.json).

    Leaving a notebook's sentinel folder behind would make the next `run`
    skip it even though its figures are gone, so the whole figures_dir tree
    is removed, not just the PNGs inside it.
    """
    from airoh.utils import clean_folder
    clean_folder(c, "figures_dir")


@task
def clean_figure(c):
    """
    Remove the composed montage PNG (connectome_figure.png).

    Never the SVG: that one is hand-authored in Inkscape and is a pipeline
    *source*, despite living in output_data/ (its relative image links
    resolve from there).
    """
    from airoh.figures import clean_figure as airoh_clean_figure
    airoh_clean_figure(c)


@task
def clean(c):
    """
    Remove all computed outputs.

    The steps are called in the body rather than declared as `pre=`, because a
    `pre=` chain only fires when invoke runs the task from the command line.
    Calling `clean(c)` from Python — which is what `run --force` does — would
    otherwise execute an empty function and silently delete nothing.
    """
    clean_connectomes(c)
    clean_group_stats(c)
    clean_motion_strata(c)
    clean_tsnr_strata(c)
    clean_figures(c)
    clean_figure(c)


@task
def clean_cneuromod(c):
    """
    Remove the fetched cneuromod.all superdataset (symlink or clone).

    Not called by `clean` or `run --force` — those only touch output_data/.
    Use this before re-fetching when you need to point a stale symlink
    somewhere new.
    """
    dest = _cneuromod_dir(c)
    if dest.is_symlink():
        dest.unlink()
        print(f"🧹 Removed symlink {dest}")
    elif dest.exists():
        print(f"⚠️  {dest} is a real clone, not a symlink — remove it manually "
              f"if you are sure: rm -rf {dest}")
    else:
        print(f"🫧 Nothing to clean — {dest} is not present")


@task
def clean_qa_figures(c):
    """
    Remove the fetched cneuromod.all.qa_figures checkout (symlink or clone).

    Not called by `clean` or `run --force` — those only touch output_data/.
    Use this before re-fetching when you need to point a stale symlink
    somewhere new.
    """
    dest = _qa_figures_dir(c)
    if dest.is_symlink():
        dest.unlink()
        print(f"🧹 Removed symlink {dest}")
    elif dest.exists():
        print(f"⚠️  {dest} is a real clone, not a symlink — remove it manually "
              f"if you are sure: rm -rf {dest}")
    else:
        print(f"🫧 Nothing to clean — {dest} is not present")


@task
def clean_source(c):
    """Remove all source data assets. Body calls each clean-{name} task."""
    clean_cneuromod(c)
    clean_qa_figures(c)
    clean_parcel_labels(c)
