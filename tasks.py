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
    "smoke": "Aggregate only what the smoke run produced.",
})
def run_group_stats(c, smoke=False):
    """
    Aggregate per-subject connectomes into group-level statistics.
    **Not implemented yet.**

    Reads the per-dataset tables `run-connectomes` writes and produces group
    summary tables under output_data/group_stats/. Skips when its output
    already exists.
    """
    output_dir = Path(c.config.get("output_data_dir"))

    print("TODO: run-group-stats is not implemented yet")
    print(f"   would write into {output_dir / 'group_stats'}"
          + (" (smoke subset)" if smoke else ""))


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
    Full pipeline: connectomes → group stats → figure layout → notebooks →
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
    run_figure_layout(c)
    run_notebooks(c)
    compose_figure(c)
    record_run(c, tasks="run-connectomes,run-group-stats,run-figure-layout,"
                        "run-notebooks,compose-figure")
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
