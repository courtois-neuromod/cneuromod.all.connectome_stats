# CNeuroMod Connectome Statistics

_why don't you have a cup of relaxing jasmine tea?_

Computes and summarizes functional connectome statistics across the
[Courtois NeuroMod](https://www.cneuromod.ca/) datasets. The pipeline reads
parcelled BOLD timeseries from the `cneuromod.all` Datalad superdataset, builds a
within-network connectome per session, and aggregates them into group-level
statistics and a composed multi-panel figure.

Built on the [`invoke`](https://www.pyinvoke.org/) task runner, with reusable
tasks from [`airoh`](https://pypi.org/project/airoh/).

> ⚠️ **Status: scaffolding.** The pipeline is wired end to end, the smoke test
> passes, and `fetch` retrieves real data — but the analysis steps are still
> **stubs**: `run-connectomes` and `run-group-stats` report what they would do
> and write nothing. The figure panels are placeholders. See **Current state**
> below.

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

- **Partial correlation is the primary measure**, with **Pearson correlation
  computed on exactly the same time series** as a comparator. Everything
  downstream runs identically for both — the interesting quantity is the
  *difference* between them.
- **The session is the unit of analysis**, restricted to sessions carrying
  roughly 30 minutes or more of usable data (~1,200 volumes). Runs are
  z-scored individually and only then concatenated within a session. Run-level
  estimates are a secondary unit, for working out how much data a stable
  estimate needs.
- **Estimation is per network, not whole-brain.** `schaefer1000`'s parcels are
  grouped into the 7 Yeo networks (~150 parcels each), and the precision matrix
  is estimated independently within each — seven matrices per session.

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
| `fetch-timeseries` | ✅ implemented — installs each `{dataset}/timeseries` subdataset and pulls the `schaefer1000` files |
| `fetch-qa-figures` | ✅ implemented — symlinks or clones the qa_figures QC tables (no credentials needed) |
| `run-connectomes` | 🚧 **stub** — will compute per-session, per-network partial and Pearson matrices; prints its plan, writes nothing |
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

- Parcellation: **`schaefer1000`**, grouped into the 7 Yeo networks.
- Measure: **partial correlation** from the sample covariance and its inverse,
  with **no regularizer** in the primary analysis; **Pearson correlation** on
  the same time series as the comparator. Both stored raw and Fisher-z.
- Unit: the **session** (≳30 min usable), runs z-scored individually before
  being concatenated. Run-level estimates are secondary.
- Estimation: **independently within each network** — the primary analysis never
  inverts a 1000 × 1000 covariance matrix.
- Every matrix ships its numerical diagnostics: rank, condition number, minimum
  eigenvalue, number of samples and number of parcels.

**Genuinely still open:** the QC criteria that define "usable" data (which
motion and tSNR thresholds, and how censored volumes count toward the 30
minutes), and the mapping between the QC tables' entities and the timeseries
`.h5` run keys — see [`source_data/CONTENT.md`](source_data/CONTENT.md).

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
| `fetch`             | Gets all source data: the superdataset, the timeseries assets, and the qa_figures QC tables |
| `fetch-cneuromod`   | Makes the cneuromod.all superdataset available (symlink via `--source`, else clone) |
| `fetch-timeseries`  | Retrieves the parcelled `schaefer1000` timeseries; `--dataset`/`--subject` narrow it |
| `fetch-qa-figures`  | Makes the cneuromod.all.qa_figures QC tables available (symlink via `--source`, else clone; no credentials needed) |
| `run`               | Runs the full pipeline in order; `--force` cleans first  |
| `run-connectomes`   | Builds per-session, per-network partial and Pearson connectomes (**stub**) |
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

Use `invoke --list` or `invoke --help <task>` for descriptions and usage.

---

## 📁 Folder Structure

| Folder / File  | Description                              |
| -------------- | ---------------------------------------- |
| `analysis/`    | Pure Python analysis logic, called by invoke tasks |
| `notebooks/`   | Jupyter notebooks for visualization (one per figure) |
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
