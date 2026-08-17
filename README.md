# CNeuroMod Connectome Statistics

_why don't you have a cup of relaxing jasmine tea?_

Computes and summarizes functional connectome statistics across the
[Courtois NeuroMod](https://www.cneuromod.ca/) datasets. The pipeline reads
parcelled BOLD timeseries from the `cneuromod.all` Datalad superdataset, builds a
connectome per subject and run, and aggregates them into group-level statistics
and a composed multi-panel figure.

Built on the [`invoke`](https://www.pyinvoke.org/) task runner, with reusable
tasks from [`airoh`](https://pypi.org/project/airoh/).

> ⚠️ **Status: scaffolding.** The pipeline is wired end to end and the smoke test
> passes, but the analysis steps are **stubs** — `fetch-timeseries`,
> `run-connectomes` and `run-group-stats` report what they would do and write
> nothing. The figure panels are placeholders. See **Current state** below.

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

#### Credentials for a full fetch

Most CNeuroMod data is openly accessible, but **not all of it has been
configured that way yet**. Content on a credentialed remote fails per-file for
anyone without access, so retrieval is deliberately **tolerant**: it warns,
skips, and carries on rather than aborting.

For a full fetch, expose your CNeuroMod credentials as environment variables in
your shell before running:

```bash
export CNEUROMOD_USERNAME=...   # your CNeuroMod credentials
export CNEUROMOD_PASSWORD=...
invoke fetch
```

A fetch that came back partly empty most likely means you lack access to that
content, not that the pipeline is broken. See
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
| `fetch-timeseries` | 🚧 **stub** — the data is not reachable yet, see below |
| `run-connectomes` | 🚧 **stub** — prints its plan, writes nothing |
| `run-group-stats` | 🚧 **stub** — prints its plan, writes nothing |
| `run-figure-layout` | ✅ implemented (from `airoh.figures`) |
| `run-notebooks` | ✅ implemented — renders **placeholder** panels |
| `compose-figure` | ✅ implemented (needs the optional Inkscape binary) |
| `verify`, `clean*` | ✅ implemented |

**Why `fetch-timeseries` is a stub.** The `courtois-neuromod/*.timeseries`
repositories exist on GitHub (14 of them: `floc.timeseries`,
`movie10.timeseries`, `friends.timeseries`, …) but are **not registered as
submodules of `cneuromod.all`**. The `{dataset}/timeseries` path this project is
configured to read therefore does not resolve in any checkout — not locally, not
on `origin/main`. Once they land upstream, the stub gets its real body and the
`timeseries_marker` / `parcellation` keys in `invoke.yaml` take effect.

**Still to decide:** which parcellation to build connectomes from
(`schaefer1000`, `cneuromod2026`, `voxel_mni`, `voxel_native` all ship in each
repo), and the connectome and group-statistic methods themselves. `invoke.yaml`
defaults to `schaefer1000` provisionally.

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
| `fetch`             | Gets all source data: the superdataset, then the timeseries assets |
| `fetch-cneuromod`   | Makes the cneuromod.all superdataset available (symlink via `--source`, else clone) |
| `fetch-timeseries`  | Retrieves the parcelled timeseries assets (**stub** — not reachable yet) |
| `run`               | Runs the full pipeline in order; `--force` cleans first  |
| `run-connectomes`   | Builds a connectome per subject and run (**stub**)       |
| `run-group-stats`   | Aggregates connectomes into group statistics (**stub**)  |
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
