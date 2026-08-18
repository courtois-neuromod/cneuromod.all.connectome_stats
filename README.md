# CNeuroMod Connectome Statistics

_why don't you have a cup of relaxing jasmine tea?_

Computes and summarizes functional connectome statistics across the
[Courtois NeuroMod](https://www.cneuromod.ca/) datasets. The pipeline reads
parcelled BOLD timeseries from the `cneuromod.all` Datalad superdataset, builds a
within-network connectome per session, and aggregates them into group-level
statistics and a composed multi-panel figure.

Built on the [`invoke`](https://www.pyinvoke.org/) task runner, with reusable
tasks from [`airoh`](https://pypi.org/project/airoh/).

> ⚠️ **Status: `run-connectomes` is implemented; `run-group-stats` is still a
> stub.** The pipeline is wired end to end, the smoke test passes, `fetch`
> retrieves real data, and `run-connectomes` writes real per-network
> connectomes. `run-group-stats` still reports what it would do and writes
> nothing, and the figure panels are placeholders. See **Current state** below.

---

## 🔬 What this measures

The question is whether functional brain organization carries a **stable,
subject-specific component** across extremely heterogeneous cognitive contexts
and across a longitudinal acquisition spanning roughly five years. CNeuroMod
gives us six deeply sampled individuals, scanned several times a week across
many different experiments — very different stimuli, tasks and cognitive
constraints — at 2 mm isotropic resolution and TR = 1.5 s, already preprocessed
and denoised upstream.

The hypothesis is that **conditional dependencies between regions are
substantially more stable across contexts than ordinary bivariate
correlations**. That is not a claim that task activity is a contaminant sitting
on top of some privileged "intrinsic" process — task and unconstrained activity
are both brain activity. It is narrower: partial correlation conditions out
fluctuations shared across many regions at once, so it should be less sensitive
to the large-scale common signal that changing experimental constraints,
physiology and noise all induce.

So:

- **Partial correlation is the primary measure** (unregularized empirical
  inverse covariance), with **Pearson correlation computed on exactly the same
  time series** as a comparator, plus a Ledoit-Wolf shrinkage variant of the
  partial correlation to check whether the unregularized inverse is well
  conditioned. Everything downstream runs identically for all three — the
  interesting quantity is the *difference* between the partial and Pearson
  measures.
- **The session is the unit of analysis**, restricted (at the group-stats
  stage, not at connectome-computation time) to sessions carrying roughly 30
  minutes or more of usable data (~1,200 volumes). Runs are z-scored
  individually and only then concatenated within a session. Run-level
  estimates are a secondary unit, for working out how much data a stable
  estimate needs. `run-connectomes` computes both levels for every session and
  run found — it never filters; that happens downstream, so exclusion
  thresholds can be varied without recomputing.
- **Estimation is per network, not whole-brain.** The primary parcellation,
  `cneuromod2026` (1134 parcels: cortex + subcortex + cerebellum), is grouped
  into the 7 Yeo cortical networks plus `cerebellum` and `subcortex` — nine
  matrices per entity. `schaefer1000` (its 7 cortical networks only) is what
  the smoke test still exercises, since it needs no S3 credentials on this
  machine.

The headline analyses are within- versus between-subject connectome similarity,
same-subject/different-task versus different-subject/same-task similarity, and
subject fingerprinting both leave-one-session-out and leave-one-task-out. With
only six participants, identification *margin* and *rank* matter more than raw
accuracy, and inference leans on permutation and participant-level resampling
rather than treating sessions as independent subjects.

---

## 🚀 Quick Start

### **Step 1**: Install dependencies

```bash
uv sync
```

This creates a `.venv` and installs all dependencies from `pyproject.toml`.
Prefix commands with `uv run` (e.g. `uv run invoke run`), or activate the
environment and call `invoke` directly.

---

### **Step 2**: Fetch the source data

```bash
invoke fetch
```

Makes the `cneuromod.all` Datalad superdataset available under `source_data/`,
then retrieves the timeseries assets the analysis reads.

`cneuromod.all` is normally **symlinked** to a checkout you already have rather
than cloned. The default source is `../cneuromod.all`; override it per-run or
set the `source:` key under `datasets:` in `invoke.yaml`:

```bash
invoke fetch-cneuromod --source ~/git/cneuromod.all   # symlink an existing checkout
invoke fetch --source ~/git/cneuromod.all             # same, via the umbrella task
invoke fetch --dataset floc --subject 01              # narrow the timeseries retrieval
```

Only the dataset *tree* is retrieved this way — annexed file content comes
separately. Most data files show up as broken symlinks until explicitly
fetched; that is normal for Datalad, not a bug.

`fetch` also retrieves `cneuromod.all.qa_figures`, a much smaller sibling
repository holding per-run QC measures (head motion, tSNR) that the group-stats
step will use. It has no annexed content, so installing its tree already *is*
the data — no credentials needed:

```bash
invoke fetch-qa-figures --source ~/git/cneuromod.all.qa_figures   # symlink an existing checkout
invoke fetch --qa-figures-source ~/git/cneuromod.all.qa_figures   # same, via the umbrella task
```

#### Credentials for a full fetch

**Timeseries content currently requires credentials for every dataset**,
including `floc`. Each `*.timeseries` repository stores its content on a single
S3 remote that denies anonymous reads; unlike the `*.fmriprep` datasets, they
are not yet published to the anonymous CONP mirror. Retrieval is therefore
deliberately **tolerant**: it warns, skips, and carries on rather than aborting.

For a full fetch, export S3 credentials before running — git-annex reads the
standard AWS variable names for this remote:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
invoke fetch
```

Filenames appear regardless of credentials (the git tree is public); only the
file *contents* need access. A fetch that came back empty means you lack access
to that content, not that the pipeline is broken. See
[`source_data/CONTENT.md`](source_data/CONTENT.md) for the full access notes.

`fetch` also runs `invoke fetch-parcel-labels`, which writes
`source_data/{parcellation}_networks.tsv` — the parcel-to-network lookup table
`run-connectomes` needs (neither `.timeseries` repo ships one). For
`schaefer1000` this needs no credentials (it comes from nilearn). For
`cneuromod2026` it reads one subject's already-fetched `_dseg.nii.gz`, so it
warns and does nothing until `fetch-timeseries --parcellation cneuromod2026`
has pulled that subject's content with real S3 credentials.

---

### **Step 3**: Run the full pipeline

```bash
invoke run
```

Runs the analysis steps in order, then the figure layout, the notebooks and the
composed montage. **`run` never pulls data** — it reads only what `invoke fetch`
already retrieved, which is what keeps it fast, offline-capable and honest about
its inputs. Run `invoke fetch` first.

Steps that have already produced output are skipped automatically. That caching
is by file existence, not by content: **a step you just edited will still be
skipped**, because its old output is sitting right there. When results start
looking stale, force a clean rebuild:

```bash
invoke run --force    # clean everything, then run from scratch
```

To redo a single step, remove its outputs and run again:

```bash
invoke clean-connectomes
invoke run
```

`invoke run` also writes `output_data/PROVENANCE.json`, recording the project's
git commit, the environment, the inputs it consumed and a checksum of every
output — so a result stays traceable to whatever produced it.

---

### **Step 4**: Check that everything still agrees

```bash
invoke verify
```

Compares the project against its own documentation: the task list in this
README, the dependency files, the paths the docs mention, each data folder
against its `CONTENT.md`, config keys, the size and type of what git tracks, and
the linter. It exits non-zero if anything has drifted.

Run it before committing. It is deliberately not part of `invoke run` —
reproducing results should never depend on the documentation being tidy.

Two more checks worth running before a commit:

```bash
invoke run-smoke   # behavioural: does the pipeline run end to end
ruff check .       # the linter on its own
pytest             # unit tests
```

---

### **Step 5**: Clean outputs

```bash
invoke clean          # remove all computed outputs
invoke clean-{name}   # remove outputs of one specific step
invoke clean-source   # remove fetched source data (never touched by `clean`)
```

---

## 📌 Current state

The plumbing is real; the science is not wired up yet.

| Piece | State |
| --- | --- |
| `fetch-cneuromod` | ✅ implemented — symlinks or clones the superdataset |
| `fetch-timeseries` | ✅ implemented — installs each `{dataset}/timeseries` subdataset and pulls the configured parcellation's files |
| `fetch-qa-figures` | ✅ implemented — symlinks or clones the qa_figures QC tables (no credentials needed) |
| `fetch-parcel-labels` | ✅ implemented — builds the parcel -> network lookup table (see "The parcel -> network lookup" in `source_data/CONTENT.md`) |
| `run-connectomes` | ✅ implemented — per-session, per-network Pearson + regularized partial correlation |
| `run-group-stats` | 🚧 **stub** — will compute similarity and fingerprinting summaries; prints its plan, writes nothing |
| `run-figure-layout` | ✅ implemented (from `airoh.figures`) |
| `run-notebooks` | ✅ implemented — renders **placeholder** panels |
| `compose-figure` | ✅ implemented (needs the optional Inkscape binary) |
| `verify`, `clean*` | ✅ implemented |

**The timeseries submodules have landed.** 12 `{dataset}/timeseries` submodules
are now registered in `cneuromod.all` (`floc`, `movie10`, `friends`, `things`,
`hcptrt`, `harrypotter`, `mario`, `mario3`, `mariostars`, `petit-prince`,
`retinotopy`, `shinobi`), so `fetch-timeseries` has a real body. Their **content
is credentialed** for now — see "Credentials for a full fetch" above and
[`source_data/CONTENT.md`](source_data/CONTENT.md).

**The method is settled** — see "What this measures" above. In short:

- Parcellation: **`cneuromod2026`** (1134 parcels), grouped into the 7 Yeo
  cortical networks plus `cerebellum` and `subcortex`. This reverses the
  project's original schaefer1000-only choice — see `CLAUDE.md`, "Settled
  analysis decisions", for why. The code stays parcellation-agnostic;
  `schaefer1000` (7 cortical networks) keeps working and is what `run-smoke`
  uses.
- Measures, computed identically for both: **partial correlation** with
  **Ledoit-Wolf shrinkage** (`partial_ledoitwolf`, primary — an established,
  regularized estimator); and **Pearson correlation** (`pearson`, the
  comparator). The unregularized empirical inverse was tried and dropped: with
  short runs, `n_samples` can be smaller than `n_parcels` in the larger
  networks, making the sample covariance exactly singular. This is a
  data-quality assessment, not an estimator comparison, so there was no reason
  to keep an estimator that breaks on this project's own data. Stored as raw
  float32 coefficients only — Fisher-z is `arctanh` of the raw values, computed
  where used (amends the original "store both raw and Fisher-z").
- Unit: `run-connectomes` computes **session-level only** (runs z-scored
  individually then concatenated), for every session found — it never filters.
  There is no per-run connectome. The ≳30-minute usable-data gate is a
  `run-group-stats` concern, so exclusion thresholds can be varied without
  recomputing connectomes (CLAUDE.md, "Record QC, never gate on it").
- Estimation: **independently within each network** — the primary analysis never
  inverts a 1000 × 1000+ covariance matrix. A parcel invalid in a given
  session (NaN or constant) is dropped before estimation and its edges are
  scattered back as NaN, so every stored vector has the same fixed length.
- Every matrix ships its numerical diagnostics: rank, condition number, minimum
  eigenvalue, number of samples and number of parcels (valid and total).

**Genuinely still open:** the QC criteria that define "usable" data (which
motion and tSNR thresholds, and how censored volumes count toward the 30
minutes). The mapping between the QC tables' entities and the timeseries `.h5`
run keys is now implemented (`analysis/qc_join.py`) as a best-effort join —
see [`source_data/CONTENT.md`](source_data/CONTENT.md) for its coverage gaps.

---

## 🧠 Design principles

- **Fetch retrieves, run reads.** No `run-*` step ever calls `datalad get`. A
  step that finds its input missing says so and points at `invoke fetch`.
- **Analysis in code, visualization in notebooks.** Heavy computation lives in
  `analysis/` Python modules run by `invoke` tasks. Notebooks only read results
  and produce figure panels — so they stay fast.
- **Idempotent steps.** Each `run-{name}` task checks whether its outputs exist
  and skips if they do. The flip side: caching is by existence, so
  `invoke run --force` is how you rebuild after editing something.
- **Mirrored clean tasks.** Every `run-{name}` has a matching `clean-{name}`.
  The top-level `clean` calls them all, and only ever touches `output_data/`.
- **Tolerant retrieval.** CNeuroMod content is partly credentialed; an
  inaccessible file warns and is skipped rather than aborting the fetch.
- **Recorded provenance.** `fetch` and `run` write `MANIFEST.json` and
  `PROVENANCE.json` — what the inputs actually were, and what produced the
  outputs.
- **Hand-authored montage, single source of truth for layout.**
  `output_data/connectome_figure.svg` places each notebook panel by relative
  path; `run-figure-layout` reads those boxes into `panel_sizes.json` so
  notebooks render every panel at exactly the size it will be placed at, and
  `compose-figure` renders the montage with Inkscape (optional — skipped with a
  warning if not installed). See `CLAUDE.md`, "Figures: the Inkscape montage
  pattern".

---

## 🧰 Task Overview

| Task                | Description                                              |
| ------------------- | -------------------------------------------------------- |
| `fetch`             | Gets all source data: the superdataset, the timeseries assets, the qa_figures QC tables, and the parcel labels |
| `fetch-cneuromod`   | Makes the cneuromod.all superdataset available (symlink via `--source`, else clone) |
| `fetch-timeseries`  | Retrieves the parcelled timeseries for the configured (or `--parcellation`) parcellation; `--dataset`/`--subject` narrow it |
| `fetch-qa-figures`  | Makes the cneuromod.all.qa_figures QC tables available (symlink via `--source`, else clone; no credentials needed) |
| `fetch-parcel-labels` | Builds `source_data/{parcellation}_networks.tsv`, the parcel -> network lookup table |
| `run`               | Runs the full pipeline in order; `--force` cleans first  |
| `run-connectomes`   | Computes per-session, per-network Pearson + regularized partial-correlation connectomes |
| `run-group-stats`   | Aggregates connectomes into similarity and fingerprinting summaries (**stub**) |
| `run-figure-layout` | Writes the montage's panel geometry to `output_data/figures/panel_sizes.json`; always re-runs |
| `run-notebooks`     | Executes notebooks and saves panels to `output_data/figures/` |
| `compose-figure`    | Renders `connectome_figure.svg` to PNG with Inkscape (optional binary) |
| `run-smoke`         | Fast end-to-end pass to check the pipeline is wired correctly |
| `verify`            | Checks that code, config, data and docs still agree      |
| `clean`             | Removes all generated outputs                            |
| `clean-connectomes` | Removes the per-dataset connectome tables                |
| `clean-group-stats` | Removes the group-level statistics tables                |
| `clean-figures`     | Removes the figures dir (panels, notebook sentinels, panel_sizes.json) |
| `clean-figure`      | Removes the composed montage PNG (never the hand-authored SVG) |
| `clean-source`      | Removes all fetched source data; routes to each `clean-{name}` |
| `clean-cneuromod`   | Removes the fetched cneuromod.all superdataset           |
| `clean-qa-figures`  | Removes the fetched cneuromod.all.qa_figures checkout    |
| `clean-parcel-labels` | Removes the built `{parcellation}_networks.tsv` labels files |

Use `invoke --list` or `invoke --help <task>` for descriptions and usage.

---

## 📁 Folder Structure

| Folder / File  | Description                              |
| -------------- | ---------------------------------------- |
| `analysis/`    | Pure Python analysis logic, called by invoke tasks |
| `notebooks/`   | Jupyter notebooks for visualization (one per figure, plus `qc_similarity.ipynb` and `qc_friends_seasons.ipynb` — exploratory QC, not montage panels) |
| `tests/`       | Unit tests (`pytest`)                    |
| `source_data/` | Source datasets — see [`source_data/CONTENT.md`](source_data/CONTENT.md) |
| `output_data/` | Generated results and figures — see [`output_data/CONTENT.md`](output_data/CONTENT.md) |
| `tasks.py`     | Project-specific invoke tasks            |
| `invoke.yaml`  | Config: paths, data sources, parameters  |

---

## 🧭 Tips

* Use `invoke --complete` for tab-completion support
* Configure paths and data sources in `invoke.yaml`
* Never run `git submodule update --init --recursive` or `datalad install -r`
  inside `cneuromod.all` — submodules re-expose their own sub-submodules, and
  recursive cloning triggers a massive, redundant retrieval

---

### Uncle Airoh

When working in this project, Claude Code responds as **Uncle Airoh**: patient,
warm, and wise. Errors are explained gently, tradeoffs are framed as learning
opportunities, and a calming cup of jasmine tea is always on offer when things
get heated.
