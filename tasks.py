from pathlib import Path

from invoke import task


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _cneuromod_dir(c):
    """Where the cneuromod.all superdataset is made available under source_data/."""
    return Path(c.config.get("datasets", {}).get("cneuromod_all", {})["output_dir"])


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
    if requested:
        return [name.strip() for name in requested.split(",") if name.strip()]
    if smoke:
        return [c.config.get("smoke_dataset", "floc")]
    return _list_datasets(c, c.config.get("timeseries_marker", "timeseries"))


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
    "dataset": "Comma-separated cneuromod.all dataset names to restrict the "
               "fetch to (default: every dataset carrying a timeseries "
               "subdataset).",
    "subject": "Comma-separated subject labels (e.g. 01,03) to restrict the "
               "fetch to.",
})
def fetch_timeseries(c, dataset=None, subject=None):
    """
    Retrieve the parcelled BOLD timeseries assets. **Not implemented yet.**

    The intended shape, once the data is reachable: install each
    `{dataset}/{timeseries_marker}` subdataset with
    `airoh.datalad.install_subdataset` (a nested subdataset, so `datalad get -n`
    rather than plain `git submodule`), then `datalad get` the `.h5` timeseries,
    the `_dseg.nii.gz` parcellation and the grey-matter mask for the configured
    `parcellation`, via `airoh.datalad.prefetch_pattern`. Tolerant of partial
    access by default — inaccessible content warns and is skipped.

    ⚠️ Blocked: the `courtois-neuromod/*.timeseries` repositories exist on
    GitHub but are NOT registered as submodules of cneuromod.all, so the marker
    path does not resolve in any checkout. See source_data/CONTENT.md.
    """
    marker = c.config.get("timeseries_marker", "timeseries")
    parcellation = c.config.get("parcellation")
    available = _list_datasets(c, marker)

    print(f"TODO: fetch '{marker}' assets (parcellation: {parcellation})")
    if available:
        print(f"   {len(available)} dataset(s) carry a '{marker}' subdataset: "
              f"{', '.join(available)}")
    else:
        print(f"   No dataset carries a '{marker}' subdataset yet — the "
              f"*.timeseries repos are not registered in cneuromod.all.")
    if dataset or subject:
        print(f"   (requested dataset={dataset}, subject={subject})")


@task(help={
    "source": "Path to an existing local cneuromod.all checkout to symlink "
              "instead of cloning.",
    "dataset": "Comma-separated dataset names to restrict the fetch to.",
    "subject": "Comma-separated subject labels to restrict the fetch to.",
})
def fetch(c, source=None, dataset=None, subject=None):
    """
    Retrieve all source data: the cneuromod.all superdataset, then the
    timeseries assets the analysis steps read.

    Records what each asset actually resolved to in source_data/MANIFEST.json,
    so the inputs a later run consumed stay identifiable — including the commit
    of a symlinked external checkout. See CLAUDE.md, "Recording asset versions".
    """
    from airoh.provenance import record_sources

    fetch_cneuromod(c, source=source)
    fetch_timeseries(c, dataset=dataset, subject=subject)
    record_sources(c)
    print("✅ fetch complete.")


# --------------------------------------------------------------------------- #
# Analysis steps (chunk = dataset)
# --------------------------------------------------------------------------- #
@task(help={
    "dataset": "Comma-separated dataset names to process (default: all with a "
               "timeseries subdataset).",
    "smoke": "Process only the smoke dataset (fast end-to-end check).",
})
def run_connectomes(c, dataset=None, smoke=False):
    """
    Compute a connectome per subject and run from the parcelled timeseries.
    **Not implemented yet.**

    Reads only files already on disk — retrieval is `invoke fetch`'s job, so
    this step never calls `datalad get`. The intended output is one table per
    dataset under output_data/connectomes/, and the step will skip any dataset
    whose output already exists (existence-based caching, see CLAUDE.md).
    """
    output_dir = Path(c.config.get("output_data_dir"))
    names = _select_datasets(c, dataset, smoke)

    print("TODO: run-connectomes is not implemented yet")
    print(f"   would write into {output_dir / 'connectomes'}")
    print(f"   for dataset(s): {', '.join(names) if names else '(none available)'}")


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
    """
    smoke_dataset = c.config.get("smoke_dataset", "floc")
    smoke_subject = c.config.get("smoke_subject", "01")

    fetch(c, dataset=smoke_dataset, subject=smoke_subject)
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
def clean_source(c):
    """Remove all source data assets. Body calls each clean-{name} task."""
    clean_cneuromod(c)
