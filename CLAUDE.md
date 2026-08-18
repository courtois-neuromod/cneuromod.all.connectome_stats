# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**CNeuroMod Connectome Statistics** — computes and summarizes functional connectome statistics across the [Courtois NeuroMod](https://www.cneuromod.ca/) datasets. The pipeline reads parcelled BOLD timeseries from the `cneuromod.all` Datalad superdataset, builds a within-network connectome per session, and aggregates them into group-level statistics plus a composed multi-panel figure.

Built on the [`invoke`](https://www.pyinvoke.org/) task runner. The `airoh` pip package provides reusable invoke tasks; this repo customizes them via `tasks.py` and `invoke.yaml`.

### Scientific objective

The project establishes three claims about CNeuroMod's data quality as a functional-connectome resource, using functional connectomes built from six deeply sampled individuals, scanned several times per week across many distinct experiments (very different stimuli, tasks and cognitive constraints), at 2 mm isotropic and TR = 1.5 s, preprocessed and denoised upstream. Runs are typically ~10 minutes; sessions hold several runs, ~30–60 minutes total.

1. **Stable across five years of acquisition.** `friends` sessions compared across the six locally available seasons — the most task-homogeneous dataset available, so the between-season contrast isolates drift (scanner, subject state, elapsed time; session ordinal is the only available time axis, there are no acquisition dates) from cognitive context. Season lives in the source h5 key's task entity (`s01e02a` -> `s01`), not the stored connectome index (which collapses multi-run sessions' `task` to `"multi"`), so `analysis/friends_seasons.py` re-derives it from source h5 key names only, never by recomputing connectomes; sessions straddling a season boundary are dropped. Within-subject similarity decays gently with season lag against a clear between-subject floor.
2. **Captures a variety of functional brain states.** Across all datasets, within-subject/within-task similarity exceeds within-subject/between-task, which exceeds between-subject/within-task, which exceeds between-subject/between-task — in every network.
3. **Applies to all networks, with varying quality.** Both analyses above, reported per network and related to per-network tSNR where qa_figures covers it.

Pearson correlation, not partial correlation, is the measure behind all three claims — see "Why partial correlation was dropped" below. Both are still computed and stored by `run-connectomes` so the comparison stays reproducible.

**Get the interpretation right when writing code, comments or docstrings.** Task-related activity is *not* a contaminant superimposed on some privileged "intrinsic" process; task and unconstrained activity are both brain activity. Do not write "removes task confounds" or "recovers the intrinsic connectome" anywhere in this repo.

With only six participants, effects must be shown to replicate across all six individuals, not established via thousands of edge-wise tests. Inference must not treat sessions as independent subjects: prefer permutation tests and participant-level resampling.

### Why partial correlation was dropped

The original hypothesis was that partial correlation (conditioning out activity shared across regions) would be more stable across cognitive contexts than Pearson correlation, with subject fingerprinting as a headline outcome. The first real run (11 datasets, 829 sessions, cneuromod2026, both measures) settled it — partial correlation is not worth carrying as a headline measure. Median session-pair similarity, all datasets:

| measure | within-subj/within-task | within-subj/between-task | between-subj/within-task | between-subj/between-task |
|---|---|---|---|---|
| pearson (Vis) | 0.943 | 0.782 | 0.685 | 0.619 |
| pearson (Default) | 0.931 | 0.725 | 0.551 | 0.452 |
| partial (Vis) | 0.724 | 0.627 | 0.504 | 0.476 |
| partial (Default) | 0.638 | 0.541 | 0.425 | 0.392 |

Partial correlation's between-subject floor is barely below Pearson's, while its within-subject ceiling collapses — the dynamic range is roughly halved. It is modestly less task-sensitive in relative terms (weak, directional support for the original hypothesis), but that buys little against a large cost in reliability, and none of the three claims above need it. Fingerprinting was never implemented for either measure. This was tested and rejected, not unconsidered — do not re-litigate it without new data.

### Current state: run-connectomes and run-group-stats are implemented

`invoke run-smoke` passes, `fetch` retrieves real data, `run-connectomes` computes real per-session, per-network connectomes, and `run-group-stats` computes the two headline analyses plus a domain-restricted robustness check on claim 2 (`analysis/group_stats.py`) into `output_data/group_stats/*.tsv`, plotted by the six real montage panels in `notebooks/figure_connectomes.ipynb` — see "Domain-restricted cross-context figures" below.

`fetch-cneuromod`, `fetch-timeseries`, `fetch-parcel-labels`, `run-connectomes`, `run-group-stats`, `run-figure-layout`, `run-notebooks`, `compose-figure`, `verify` and every `clean-*` task are real.

### The timeseries assets

This project reads parcelled BOLD timeseries. As of **2026-08-17**, 12 `{dataset}/timeseries` submodules are registered in `cneuromod.all`: `floc`, `movie10`, `friends`, `things`, `hcptrt`, `harrypotter`, `mario`, `mario3`, `mariostars`, `petit-prince`, `retinotopy`, `shinobi`. `fetch-timeseries` discovers them via `_list_datasets` rather than reading that list.

Layout (shown for schaefer1000; cneuromod2026 is the same shape under a `cneuromod2026/` directory, with `atlas-cneuromod26` or `atlas-cneuromod2026` in the filename — both spellings occur):

```
cneuromod.all/{dataset}/timeseries/timeseries/schaefer1000/sub-0X/
    sub-0X_task-{dataset}_..._atlas-Schaefer2018_desc-1000Parcels7Networks_timeseries.h5
    sub-0X_task-{dataset}_..._atlas-Schaefer2018_desc-1000Parcels7Networks_dseg.nii.gz
    sub-0X_task-{dataset}_..._label-GMfromTemplate_desc-indivFunc_mask.nii.gz
```

**One `.h5` per subject**, holding every session and run as separate 2D `(timepoints, parcels)` arrays keyed `ses-XXX/ses-XXX_task-..._run-N_timeseries` — `run` is optional in the key: `friends` keys carry no `_run-N` segment at all (`analysis/timeseries_reader.py`'s `parse_run_key` handles both). That is the annex's finest unit, so `--subject` narrows a fetch but there is nothing session-level to request — session selection is a read-time concern for `run-connectomes`.

There are no HDF5 attributes anywhere in these files — no TR, no parcel names. TR is config (`tr_seconds` in `invoke.yaml`, `1.5`).

`voxel_mni` and `voxel_native` (voxelwise, much larger) also ship in every repo and are deliberately not fetched.

### The parcel -> network lookup

Nothing in the timeseries repos maps parcels to networks — the `_dseg.nii.gz` carries bare integer labels, and there is no LUT, TSV or JSON anywhere in the trees. `fetch-parcel-labels` builds `source_data/{parcellation}_networks.tsv` (columns `index`, `name`, `network`) instead of fetching one, via `analysis/parcel_networks.py`:

- **`schaefer1000`** — `build_schaefer1000_labels()` reads nilearn's bundled `fetch_atlas_schaefer_2018(n_rois=1000, yeo_networks=7)`. No fetch beyond nilearn's own cache; network is the region name's 3rd underscore field (`7Networks_LH_Vis_1` -> `Vis`).
- **`cneuromod2026`** — `build_cneuromod2026_labels()` reads one already-fetched subject's individualized `_dseg.nii.gz` (from the timeseries repo, **never** `anat/atlases` — see the trap below) and decodes its integer label values. **This decoding rests on a documented, not-yet-verified assumption**: that label values `1..1000` are Schaefer's own cortical numbering (with up to 4 absent — TIMESERIES.md's composition is 996 cortical, not 1000), `1001..1050` are Tian subcortex, and `1051..1138` are Nettekoven cerebellum. No S3 credentials were available while writing this, so a real dseg has not yet been inspected to confirm it. The function asserts the resulting per-network counts against `CNEUROMOD2026_EXPECTED_COUNTS` (from qa_figures: Vis 162, SomMot 194, DorsAttn 122, SalVentAttn 121, Limbic 60, Cont 128, Default 209, cerebellum 88, subcortex 50 = 1134) and **raises rather than writing a silently wrong table** if they disagree — treat that assertion as the check once you have credentials to run it for real.

### The QC measures asset (qa_figures)

`run-connectomes` and `run-group-stats` need per-run quality-control
covariates — head motion and tSNR — for two concrete jobs: deciding which
sessions are usable (the `usable_duration_sec >= 1800` gate, a `run-group-stats`
decision — see "Settled analysis decisions" below), and checking at the
group level whether low-stability sessions are systematically lower-quality
acquisitions. Every session that enters the analysis carries its motion
summary alongside its connectomes (joined by `run-connectomes` via
`analysis/qc_join.py`), so that check is possible after the fact. Those covariates already exist,
computed, in a second source asset: `cneuromod.all.qa_figures`, wired in
alongside `cneuromod.all` via `datasets: qa_figures` in `invoke.yaml` and
`fetch-qa-figures`/`clean-qa-figures` in `tasks.py`.

Unlike `cneuromod.all`, this dataset has **no annexed content** — every tracked
file is a plain git blob (~33 MB total) — so installing the tree via
`airoh.datalad.install_dataset` already *is* the data; no content-fetch step
follows it, and no credentials are needed.

Two table families live under `output_data/tables/` inside the checkout, both
**per functional run**: `tables/{dataset}.tsv` (motion, tSNR and related QC
scalars) and `tables/atlas_tsnr/{dataset}.tsv` (tSNR per Yeo network plus
cerebellum/subcortex). `analysis/qc_measures.py` is the reader — pure functions
over these tables, no invoke context. Coverage is partial (several per-dataset
tables are empty), so callers must tolerate that; see
`source_data/CONTENT.md`, "QC measures (qa_figures)" for the exact gaps.

Joining these entities against the timeseries `.h5` run keys is now implemented in `analysis/qc_join.py`, deliberately kept out of `analysis/qc_measures.py` — that module stays a pure table reader. `normalize_entities` strips `sub-`/`ses-` prefixes, zero-pads session to 3 digits, and normalizes `run`; `join_run_qc`/`join_network_tsnr` merge on `dataset, subject, session, task, run` and are **best-effort**: unmatched rows keep NaN and get `qc_matched = False`, never a raised error. Two entity-convention gotchas this join handles, found empirically (not documented upstream): `run` is **not** uniformly blank for movie10/friends as an earlier version of `source_data/CONTENT.md` claimed — qa_figures exports it as a float-like string (`"1.0"`) for some subject/session combinations even within movie10, so `normalize_entities` strips a trailing `.0`; and `fd_prop_gt02/gt05` are blank for **both** movie10 and friends, not just friends.

Two traps to avoid:

- **Do not match on the atlas entity.** Upstream writes `atlas-Schaefer2018` while the repos' own `TIMESERIES.md` documents `atlas-Schaefer18`. `analysis/timeseries_layout.py` matches on the filename *suffix* (`*_timeseries.h5`, `*_dseg.nii.gz`, `*_mask.nii.gz`) precisely so that drift cannot break retrieval.
- **Do not point the pipeline at `anat/atlases` or at fMRIPrep BOLD.** The parcellations ship *inside* the timeseries repos, which is the whole reason this project reads them. This was checked explicitly for cneuromod2026's label ordering: `cneuromod_extract_tseries`'s `schaefer1000Tian50Nette128.yaml` config points its `parcellation:` key at `./atlases/...` (the `anat.atlases` submodule) — but the **individualized** `_dseg.nii.gz` this project needs already ships inside each `.timeseries` repo alongside the `.h5` (see "The timeseries assets" above), so `fetch-parcel-labels` reads that, never `anat/atlases`. Ask the user before changing this retrieval route.

### Timeseries content is credentialed

Each `{dataset}.timeseries` repo stores annexed content on **one** S3 special remote (`s3.unf-montreal.ca`, one bucket per dataset) that denies anonymous reads. Without credentials `datalad get` reports `No publicurl is configured for this remote` per file. git-annex reads `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` for it — *not* `CNEUROMOD_USERNAME`/`PASSWORD`, which an earlier version of the docs wrongly advertised.

The `*.fmriprep` datasets additionally publish to the CONP RIA store via an autoenabled anonymous `httpalso` remote (`https://sftp.conp.ca/...`); the `*.timeseries` datasets have not been published there yet. **That is an upstream gap this repo cannot fix** — it needs a push to the CONP server and an `initremote` recorded in each timeseries repo's `git-annex` branch. Nothing here needs to change when it lands: datalad enables autoenabled remotes on its own.

Consequence for `fetch-timeseries`: **two different tolerances, on purpose.** Installing a subdataset needs only the public git tree, so `--strict` makes a failure there fatal. Pulling content hits the credentialed remote, so it always warns and skips, `--strict` or not. Do not "simplify" this into one flag.

### Settled analysis decisions

These are decided. Implement them as written; do not reopen them unprompted.

- **Parcellation: `cneuromod2026`** (1134 parcels: cortex + subcortex + cerebellum), **reversing the project's original `schaefer1000`-only choice**, to line up with what the qa_figures QC tables cover. The code stays parcellation-agnostic — the network partition comes from the config-selected `parcellations:` entry in `invoke.yaml` and its labels file — so `schaefer1000` keeps working and is what the smoke test uses (see "Project-specific conventions" below).
- **Nine networks** for cneuromod2026: the 7 Yeo cortical networks, `cerebellum` (88 parcels), and `subcortex` (all 50 Tian parcels as one network) — this covers all 1134 parcels with no leftovers. `schaefer1000` keeps its 7 cortical networks.
- **Pearson only for results; `partial_ledoitwolf` computed and stored, not reported.** `run-connectomes` still computes both measures identically for every network — `pearson` and `partial_ledoitwolf` (nilearn's default-shrinkage partial correlation) — via `connectome_measures` in `invoke.yaml`, but `run-group-stats` reads only `analysis_measure: pearson`. See "Why partial correlation was dropped" above for the numbers behind this. The unregularized empirical inverse (`partial_empirical`) was tried earlier and dropped for a separate reason: for run-level data, `n_samples` can be smaller than `n_parcels` in the larger networks (Default has 209 parcels, SomMot 194 for cneuromod2026), making the sample covariance exactly singular — a routine failure, not an edge case.
- **Session-level only.** `run-connectomes` writes one connectome per session (runs z-scored, then concatenated — see "Standardize, then concatenate" below) for **every** session found. There is no run-level connectome output; the session is the sole unit of analysis (~1,200 volumes at TR = 1.5 s vs. ~150 parcels per cortical network — comfortably more observations than variables). Per-run QC (motion, tSNR) is still read and aggregated up to the session, since qa_figures only tabulates it per run — see "The QC measures asset (qa_figures)" above — but no per-run connectome is computed or stored.
- **Record QC, never gate on it, at connectome-computation time.** Every session found gets a connectome; all exclusion happens in `run-group-stats`, where it can be varied without recomputing. This keeps "exclusion thresholds must not be tuned against similarity contrasts" (below) honest.
- **Usable-data gate: `usable_duration_sec >= 1800` (30 minutes), everywhere.** Chosen a priori from QC, not tuned against similarity contrasts — but not on duration alone either. `run-group-stats`'s cross-context contrast (claim 2) compares within-dataset against between-dataset session pairs, and pair *duration* is itself a confound there: at the earlier 600 s gate, median pair min-duration was ~2661–2692 s for the two within-task bins versus ~1701–1706 s for the two between-task bins — a ~1.6x imbalance that similarity rises with, independent of any task effect. Raising the gate to 1800 s brings the four bins to within ~4% of each other (~2668–2784 s), so the contrast is interpretable as a task effect rather than a duration effect. This is a threshold chosen from an acquisition/design property (pair duration composition), computed with no reference to similarity values — not the forbidden kind of tuning. `run-group-stats` writes this comparison to `duration_balance.tsv` for both gates. The cost: `floc` (0/18 sessions survive), `retinotopy` (0/23) and `things` (0/141) leave claim 2 entirely — three of the ten task contexts, and the three least like the naturalistic datasets — so claim 2 now spans 7 contexts (`friends, harrypotter, hcptrt, mario, movie10, petit-prince, shinobi`), not 10. All 6 subjects are retained. At 1800 s, 559 of 829 sessions survive. `run-group-stats` still reports every headline table both gated and ungated (`gate="all"` in every TSV) as the standing sensitivity comparison.
- **float32, raw coefficients only.** Fisher-z is `arctanh` of the raw values, computed where used. This **amends** the original "store both raw and Fisher-z" decision.
- **Estimate independently within each network.** For a network of `p` parcels, build the `p × p` covariance and invert that. The primary analysis must **never silently attempt to invert a 1000+ × 1000+ covariance matrix** — it is both computationally and statistically wrong here. Cross-network edges are out of the primary analysis. A full regularized whole-brain precision matrix is a possible *later* secondary analysis.
- **Standardize, then concatenate.** Each run's parcel time series is z-scored *within the run* before runs from the same session are concatenated (`analysis/timeseries_reader.py`'s `standardize_run`). Never concatenate raw runs — run-specific means and scaling differences would themselves induce correlations. (Timeseries are already standardized upstream per TIMESERIES.md, so this is a safeguard, not the thing doing the work.)
- **Fixed edge geometry, always.** Edge slots per network come from the full parcellation partition and never vary. A parcel missing or constant in a given session is dropped before estimation (`analysis/connectome_estimators.py`'s `connectome` function); the resulting smaller matrix is scattered back into the full `p × p` layout with NaN in the affected rows/columns, so every stored vector has the same length and a `n_parcels_valid` diagnostic records what actually contributed. Without this, vectors would differ in length across subjects and could not be stacked. cneuromod2026 uses a **stricter** grey-matter mask (`GMfromFS`, FreeSurfer-derived) than schaefer1000 (`GMfromTemplate`), so subject-specific parcel dropping is *more* likely here, especially for small subcortical/cerebellar parcels — this makes the rule load-bearing, not defensive.
- **Record per-matrix numerical diagnostics**: `n_samples`, `n_parcels`, `n_parcels_valid`, `rank`, `condition_number`, `min_eigenvalue` — computed for **every** measure including Pearson, from the raw sample covariance regardless of which estimator produced the stored connectome. These are what tell us empirically whether a session's data is well behaved for connectome estimation, so they are part of the output, not debug logging.

### Domain-restricted cross-context figures

A robustness-tier check on claim 2 (CLAUDE.md, "Respect the analysis hierarchy" below): does the within-task/between-task contrast still hold when "between-task" is a much more homogeneous swap than "friends vs. retinotopy"? `analysis/group_stats.py`'s `domain_cross_context_summary` reruns `cross_context_summary`, one domain at a time, restricted to `DOMAIN_DATASETS`:

- **`movies`**: `friends` + `movie10`, at **title-level** task identity (friends season, e.g. `s01`; movie10 title, e.g. `bourne`/`wolf`/`life`/`figures`) — the dataset column alone can't distinguish these, since it collapses to just two values. `analysis/domain_titles.py` (new module, deliberately separate from `analysis/friends_seasons.py`, whose scope stays the claim-1 longitudinal control) re-derives the title from each dataset's source h5 key task entity — `friends` keys as `s01e02a` -> `s01`, `movie10` keys as `bourne01` -> `bourne` — the same "read h5 key names only, never recompute from timeseries" rule as `friends_seasons.py`. Mixed-title sessions are dropped, same convention as `friends_seasons.attach_seasons`.
- **`videogames`**: `mario`, `mario3`, `mariostars`, `shinobi` — dataset-level task identity, same axis as the global cross-context analysis, just restricted to fewer datasets.
- **`stories`**: `harrypotter`, `petit-prince` — dataset-level task identity.

`floc`, `things`, `hcptrt`, `retinotopy` don't fit a naturalistic-stimulus domain and are out of all three domain figures. A domain with no connectome file present is skipped rather than raising (e.g. the smoke run, `movie10`/schaefer1000 only, contributes to none of the three). Output: `domain_cross_context.tsv`, `domain_pair_histograms.tsv`, `domain_duration_balance.tsv` under `output_data/group_stats/`, each carrying a `domain` column alongside the usual `cross_context.tsv` shape, both gated and ungated like every other headline table.

**Placement is a deliberate exception to the tier rule below.** This is Robustness-tier by nature (a check on claim 2's generalizability, not a fourth headline claim), but at the user's explicit request the three panels (`domain_movies.png`, `domain_videogames.png`, `domain_stories.png`) are drawn by `notebooks/figure_connectomes.ipynb` and placed in the hand-authored `output_data/connectome_figure.svg` montage alongside the three headline panels — a future reader should not infer from montage placement alone that this is a fourth headline claim.

### Still open

Do not settle these unilaterally — raise them with the user:

- **Whether finer-grained usable-data criteria are worth adding** — e.g. per-run FD thresholds within a session, rather than the single session-level `usable_duration_sec >= 1800` gate. One standing rule: **exclusion thresholds must not be tuned against similarity contrasts.** Pick them a priori from QC, then report headline results with and without the worst-quality sessions.
- **Whether the cneuromod2026 label-ordering assumption in `build_cneuromod2026_labels` is correct.** It is asserted against known per-network counts and raises if wrong, but has not yet been checked against a real dseg (no S3 credentials were available while implementing it) — see "The parcel -> network lookup" above.

### Project-specific conventions

- **The chunk concept is the dataset.** `run-*` steps take a `--dataset` flag naming one or more top-level cneuromod.all datasets (`floc`, `movie10`, …), and iterate over them. `run-connectomes` also exposes `--subject` and `--parcellation`. **The chunk is not the statistical unit** — the dataset is how work is *divided*, while the session is what a connectome is *estimated from*. Session-level selection is a read-time concern inside `analysis/connectomes.py` (there is nothing session-level to fetch: one `.h5` holds every session of a subject), so it belongs in `analysis/`, not in a fetch flag.
- **Datasets are discovered, not hardcoded.** `_list_datasets(c, marker)` in `tasks.py` returns every top-level cneuromod.all directory carrying the given derivative subdataset. It returns an empty list when the superdataset is absent, so the stubs degrade to a message rather than a traceback.
- **The smoke target is `movie10` / `sub-02` / `schaefer1000`** (`smoke_dataset`, `smoke_subject`, `smoke_parcellation` in `invoke.yaml`). `sub-01`'s schaefer1000 content happens to be an unfetched/broken annex symlink on this machine while `sub-02`'s is present, hence sub-02. `smoke_parcellation` pins schaefer1000 regardless of the configured `parcellation` (cneuromod2026) so the smoke test keeps passing offline with data already on disk. `run-smoke` passes `strict=True`, which only makes a failed subdataset *install* fatal; missing content never fails it.
- **Never run `git submodule update --init --recursive` or `datalad install -r`** inside `cneuromod.all`. Submodules re-expose their own sub-submodules at differing versions; recursive cloning triggers a massive, redundant retrieval. Use `airoh.datalad.install_subdataset` (`datalad get -n`) to reach a nested subdataset.
- **CNeuroMod content is partly credentialed.** Retrieval must stay tolerant — warn and skip, never abort — except in the smoke test. A full fetch expects credentials in environment variables; see README.md, "Credentials for a full fetch".

## Persona

Respond as Uncle Airoh: patient, warm, and wise. Assume the user may be new to coding. Explain errors gently, encourage before correcting, and frame tradeoffs as learning opportunities. When things get heated, offer a calming cup of jasmine tea.

## Setup

This project uses `uv`. `pyproject.toml` is the single dependency file; no pip- or conda-specific dependency file is kept alongside it.

```bash
uv sync
```

## Common Commands

Prefix with `uv run`, or activate the environment and drop the prefix:

```bash
uv run invoke fetch             # Make cneuromod.all available, retrieve timeseries assets
uv run invoke fetch --source ~/git/cneuromod.all   # symlink an existing checkout
uv run invoke run               # Full pipeline (cached: skips steps whose output exists)
uv run invoke run --force       # Clean everything first, then run from scratch
uv run invoke run --dataset floc,movie10           # restrict to specific datasets
uv run invoke run-smoke         # Fast end-to-end check that the plumbing works
uv run invoke run-connectomes   # Build per-session connectomes per dataset
uv run invoke run-group-stats   # Aggregate into group statistics (stub)
uv run invoke fetch-parcel-labels  # Build the parcel -> network lookup table
uv run invoke run-notebooks     # Execute notebooks, save panels to output_data/figures/
uv run invoke run-figure-layout # Write the montage's panel geometry to panel_sizes.json (always re-runs)
uv run invoke compose-figure    # Render connectome_figure.svg to PNG with Inkscape (optional binary)
uv run invoke verify            # Check code, config, data and docs still agree
uv run invoke clean             # Remove output_data/ contents
uv run invoke clean-source      # Remove fetched source data (never touched by `clean`)
uv run invoke --list            # Show all available tasks

uv run ruff check .             # Linter
uv run pytest                   # Unit tests
```

## Architecture

**Always read `tasks.py` first** before proposing or implementing any pipeline change — it is the authoritative source of what tasks exist, how they are wired, and what parameters they accept.

**Execution flow:** `invoke run` triggers the project's analysis pipeline by calling each step in its body, in order. The permanent tasks — `fetch`, `run`, `verify`, `clean` — are always present; intermediate steps are project-specific.

**`pre=` chains do not fire when a task is called as a function.** A `pre=` list only runs when invoke executes that task from the command line. `run(c)` or `clean(c)` called from Python executes the body alone — so a `clean` whose real work lives entirely in `pre=` deletes nothing when `run --force` calls it, silently and with a success message. Umbrella tasks that other tasks call therefore do their work in the body. Keep `pre=` only where the task is a command-line entry point (`run-notebooks` depending on the step that produces its input), and remember that anything threading a flag through — `--force`, `--smoke`, a chunk selector — must call its steps directly, since a `pre=` chain has already run by the time the body sees the flag.

**Fetching data — download or symlink:** each data asset in `files:` gets its own `fetch-{name}` task wrapping `airoh.acquisition.fetch_data`, which makes the asset available in one of two ways: **download** from its `url` (default), or **symlink** to already-present data when a source path is given — via `invoke fetch-{name} --source /path` (add `--copy` for a real copy) or a per-asset `source:` key in `invoke.yaml`. The umbrella `fetch` task calls every `fetch-{name}` and exposes a per-asset `--{name}-source` flag that it routes to the matching one. This avoids re-downloading data that already lives on disk (a shared dataset, a sibling repo). Symlinks handle both files and whole directories, and the operation is idempotent. When wiring fetch tasks for a new project, prefer `fetch_data` over the lower-level `download_data`.

**One asset, one `--source`:** `fetch_data`'s `source` is a single path bound to the single asset named in the call — never a root directory joined with each asset's filename. That is why each asset gets its own `fetch-{name}` task with its own `--source`, and the umbrella `fetch` routes named `--{name}-source` flags rather than one shared `--source`. Do **not** forward a single shared `--source` to several `fetch_data` calls: it links every asset to the same path and fails silently, printing a success line per asset and exiting 0.

See **Data** below for datalad datasets, sensitive data, and recording asset versions.

- `invoke.yaml` — all path and data config (`output_data_dir`, `source_data_dir`, `notebooks_dir`, `files:` for data assets — each with `output_file` plus `url` to download and/or `source` to symlink)
- `tasks.py` — project-specific invoke tasks; imports reusable tasks from `airoh` (`airoh.acquisition` for data fetching, `airoh.utils` for general helpers)
- `analysis/` — pure Python analysis logic, called by tasks in `tasks.py`
- `notebooks/` — Jupyter notebooks executed by `run_notebooks` via `airoh.utils.run_notebooks`; notebooks receive `OUTPUT_DATA_DIR`, `SOURCE_DATA_DIR` and `FIGURES_DIR` as environment variables, and write into `FIGURES_DIR/{notebook_stem}/`, not directly under `output_data/`
- `source_data/CONTENT.md` and `output_data/CONTENT.md` — authoritative docs for what each data folder contains; update these when data assets change, do not duplicate their content elsewhere
- `.claude/skills/` — each skill exists twice: as a directory (the source you edit) and as a `.zip` (what gets copied into projects created from this template). **Re-zip after editing a skill**, or projects keep receiving the old version — this has already happened once: `cd .claude/skills && zip -qr <name>.zip <name> -x '*/.*'`

**Analysis vs. notebooks:** Heavy computation belongs in `analysis/` Python code, invoked by `run-{name}` tasks, which write results to `output_data/`. Notebooks are for visualization only — they read from `output_data/` and produce figures. This keeps notebooks fast and focused.

**Idempotent tasks:** Each `run-{name}` task must check whether its outputs already exist and skip execution if they do. This means `invoke run` can be called repeatedly during development of a later step — earlier steps are skipped automatically.

**Caching is by existence, and forcing is a sledgehammer.** A step skips when its output file is there; nothing compares timestamps or hashes against its inputs. That is a deliberate ceiling on complexity — a real dependency graph is more than this template wants to explain, and a cache nobody understands is worse than one that is occasionally too eager. The consequence is that **editing a script or a notebook does not invalidate anything**: the pipeline will happily skip the step you just changed. Two ways out, both explicit:

- `invoke clean-{name}` then `invoke run` — redo one step.
- `invoke run --force` — clean everything, then run from scratch.

When results start looking stale or inconsistent, reach for `--force` rather than trying to reason about what is cached. Do not add content-hash invalidation or a dependency graph to `run`; that is the workflow-engine road, and this template deliberately stops short of it.

**Notebook outputs must live in the notebook's own folder.** `run-notebooks` treats `{figures_base}/{notebook_stem}/` as the "already ran" marker for each notebook. A notebook that writes anywhere else never creates its marker and therefore re-runs on every single `invoke run`, however cheap the rest of the pipeline is.

**Figures: the Inkscape montage pattern.** `output_data/connectome_figure.svg` is hand-authored in Inkscape and is the **single source of truth for panel layout** — it links each notebook panel by relative path resolved from `output_data/` (e.g. `output_data/figures/figure_connectomes/overview.png`), and the box it places a panel in is that panel's true on-page size. `run-figure-layout` (`airoh.figures.figure_layout`) reads those boxes out of every entry in `invoke.yaml`'s `figures:` mapping and writes them to `output_data/figures/panel_sizes.json` on **every** `invoke run`; `figure_connectomes.ipynb` calls `airoh.figures.panel_size(name, default)` to render each panel at exactly that size, so placement is 1:1 and text is never stretched. `compose-figure` (`airoh.figures.compose_figure`) then renders the montage to `connectome_figure.png` via the Inkscape CLI, an optional system binary: a missing `inkscape` warns and skips the export rather than failing `invoke run`.

Resizing a box only fully takes effect after the panel it belongs to is re-rendered — and that panel is a notebook output, so it obeys the same existence-based caching as everything else (see **Caching is by existence**, above). `panel_sizes.json` and the composed montage update on every `invoke run` regardless, but a panel whose notebook did *not* re-run keeps its old pixel size, so Inkscape stretches it into the new box — precisely the problem this pattern exists to avoid. After resizing a box, run `invoke clean-figures && invoke run` (or `invoke run --force`) so the affected panel actually redraws at the new size.

Two rules that must be kept wherever a notebook renders a montage panel: **never** pass `bbox_inches="tight"` (it resizes the canvas after the fact, which is exactly what breaks the 1:1 guarantee) — use `layout="constrained"` to reclaim margins inside the fixed canvas instead — and always save at the montage's DPI, so saved pixels equal `figsize × dpi`. That DPI is not hardcoded in the notebook: `run-notebooks` reads it from `figures:` (→ `connectome_figure.dpi`, default 300) via the `montage_dpi` helper in `tasks.py` and exports it as `FIGURE_MONTAGE_DPI`, which the notebook reads. Composing the montage at a different resolution therefore re-sizes the panels with it, instead of silently breaking placement.

**Legends and titles are montage elements, not panel decoration.** A panel-sized
canvas has no room for a nine-network key or a two-line title on top of the
data — `cross_context.png` was unreadable for exactly this reason. So panels are
drawn bare (axes, ticks, axis labels, data) and each legend is saved as its own
horizontal strip next to the panel it belongs to (`{panel}_legend.png`), placed
in `connectome_figure.svg` like any other element and sized through
`panel_size` the same way. Titles are typeset once in the SVG. Prose that would
otherwise be drawn onto a panel (e.g. panel 3's tSNR-coverage caveat) is written
to a plain text file beside it, to become a caption. Keep this split when adding a panel:
`save_legend` in `figure_connectomes.ipynb` is the helper.

`run-figure-layout` is a deliberate exception to the existence-based caching described above: it always re-runs, because it is cheap and a box resized in Inkscape must take effect on the very next `invoke run`, not only after a `clean`.

**Task naming conventions:**
- Fetch tasks are named `fetch-{name}` (e.g. `fetch-cneuromod`), one per data asset; the umbrella `fetch` calls them all and routes a `--{name}-source` flag to each.
- Analysis tasks are named `run-{name}` (e.g. `run-preprocessing`, `run-model`).
- Cleaning tasks mirror them: `clean-{name}` removes only the outputs of the corresponding step. Granular clean tasks are what make a selective re-run possible, so every run step needs one.
- The top-level `clean` task calls all `clean-{name}` tasks for **analysis** steps in its body — it only ever touches `output_data/`. Source assets have their own mirrored `clean-{name}` tasks (e.g. `clean-cneuromod`) plus an umbrella `clean-source`, kept separate from `clean` since removing a source asset is a deliberate act (e.g. before re-pointing a stale symlink with `fetch-{name} --source`), not something `run --force` should ever do implicitly.
- The top-level `run` task calls all steps in its body, in order.
- `verify` checks the project against its own documentation; see **Verification**.

**Task parameters:** `run-{name}` tasks should expose chunk or subset parameters (e.g. a subject ID, a chunk index) so that individual pieces can be rerun in isolation. They should also support a `smoke` flag for a fast minimal run useful for testing the pipeline end-to-end without running the full analysis.

## Data

### Where data lives

`source_data/` holds inputs and nothing else; `output_data/` holds what the
pipeline computed. Neither is a scratch directory — a file that is neither a
declared input nor a produced output does not belong in either.

Both folders are **gitignored by default**, and that default is the right one:
data has its own distribution channel (a URL, a datalad dataset, a shared
filesystem), and git is bad at large binaries in a way that cannot be undone —
a big file committed once stays in the history forever. Track an output only
when it is small, diffable, and genuinely useful to read in a pull request: a
metrics table, yes; a NIfTI volume or a multi-megabyte figure, no. When a
project does start tracking outputs, keep a **guard line** in the folder's
`.gitignore` for the file types that must never be committed there, even if
nothing currently produces them:

```gitignore
# Guard: no step writes NIfTI here, but keep this so a stray volume can never
# be committed by accident.
*.nii.gz
```

`invoke verify` enforces the same idea mechanically — it fails on a tracked
file over ~10 MB or of a known-binary type — but a guard line documents the
intent at the place someone would otherwise break it.

### Datalad datasets, and plain assets

`--source` symlinks or copies a plain file or folder and does **not** run
`datalad get`. Symlinking a datalad dataset exposes only content that is
already present — un-fetched files are broken symlinks. So for a real datalad
dataset use `airoh.datalad` instead of `fetch_data`, configured under
`datasets:` in `invoke.yaml` (either `{name: output_dir}` or `{name: {output_dir,
url, source}}`):

- `install_dataset(c, name, source=None)` — make the checkout available:
  symlink an existing checkout at `source` (dataset tree only, does not
  `datalad get`), or `datalad clone` from `url`. No-op if `output_dir` already
  exists.
- `get_data(c, name, path=None, recursive=False, strict=False)` — retrieve
  content (the whole dataset, or just `path`). Tolerant of partial failures by
  default; `--strict` raises instead (use in the smoke test).
- `update_dataset(c, name, strict=False)` — advance an installed dataset's pin
  via `datalad update --merge`, without pulling content.
- For a plain git submodule (not datalad-backed), use
  `airoh.acquisition.ensure_submodule` instead.

A project with its own analysis-specific prefetch step (e.g. "get every file
matching this glob that a `run-*` step reads") composes it from
`airoh.datalad.prefetch_pattern` plus `load_known_failures`/
`save_known_failures` rather than reimplementing the glob/skip/get/reclassify
loop — see the `airoh` API reference for the full signatures.

Three things bite projects working with real datalad superdatasets:

- **Subdatasets nest.** A derivative folder is often a subdataset inside
  another subdataset, and plain `git submodule update --init` cannot reach one:
  it only sees the top level. `airoh.datalad.install_subdataset` (`datalad get
  -n <path>` under the hood) installs the intermediate dataset and the nested
  one in a single call, without pulling content, and without touching large
  sibling subdatasets.
- **Retrieval is partial and must be tolerant.** Content on credentialed
  remotes fails per-file for anyone without access. A fetch that aborts on the
  first inaccessible file is useless to collaborators with partial access:
  warn, skip, and carry on with whatever is reachable — every `airoh.datalad`
  retrieval function does this by default. Fail loudly only in the smoke test
  (`strict=True`), where an empty result means the plumbing is broken.
- **The annex version matters.** A repository in annex v10 format is simply
  refused by an older `git-annex`, and the failure looks like "no content
  anywhere" rather than an error. Pin it as a declared project dependency (the
  `git-annex` PyPI package bundles a recent binary) instead of writing a README
  note nobody reads.

**Gathering assets is a separate job from reproducing results.** `fetch`
retrieves; `run` reads what is already on disk and never pulls. That split is
what makes `run` fast, offline-capable, and honest about what it depends on. A
`run` that quietly re-fetches on demand is slow in a way nobody can diagnose,
and hides the fact that a result was produced from data that arrived halfway
through. If a step finds its input missing, it should say so and point at
`invoke fetch` — not fix it silently.

### Sensitive and restricted data

Never commit identifiable data, credentials, or anything under a data-use
agreement — not to this repository, not "temporarily". Git history is not
erasable in practice once pushed.

- Keep the gitignore-by-default posture for `source_data/`, and add a guard
  line for the formats that would carry identifiable content.
- Restricted content usually lives behind a credentialed remote. Retrieval will
  fail for some people by design; that is not a bug to work around.
- **Document the access requirements in `source_data/CONTENT.md`**: who can get
  this data, how, and what a person without access will see. A collaborator
  whose `fetch` came back empty otherwise cannot tell whether the pipeline is
  broken or they simply lack permission — and will file the wrong bug.
- Derived outputs inherit the sensitivity of their inputs. An aggregate table
  is usually fine to track; a per-participant one usually is not.

### Recording asset versions

`fetch` writes `source_data/MANIFEST.json` and `run` writes
`output_data/PROVENANCE.json` (see `airoh.provenance`). Between them they record
what each input actually resolved to — including the commit of a symlinked
external checkout — and what produced the current outputs: the project's own
commit and dirty flag, the environment, the manifest consumed, and a checksum
per output file. Both are small and git-tracked.

`PROVENANCE.json` changes on every run. That is the record working, not churn to
suppress; do not try to make it stable.

**These records attest, they do not retrieve.** They can tell you that a result
came from commit `abc123` of an input dataset with an uncommitted working tree —
which is exactly the question "why do my numbers differ from the paper's" needs
answered — but they cannot bring that state back. Retrieval is datalad's job,
and when this repository is aggregated as a submodule into a larger paper
project, datalad is what pins it. The records are what you get when datalad is
not in play, which is most of the time during day-to-day analysis.

## Verification

`invoke verify` checks that the code, config, data and documentation still agree.
It runs a flat list of independent checks — task list versus README, dependency
files against each other, paths named in the docs, each data folder against its
`CONTENT.md`, config keys, tracked file sizes, provenance freshness, the linter —
and exits non-zero if any of them fails. Configure it under `verify:` in
`invoke.yaml`.

**Run it before committing.** Documentation drift is invisible: nothing breaks
when the README lists a task that no longer exists, or a docstring describes
behaviour that was removed two commits ago, so it accumulates until a reader is
actively misled. These checks are the mechanical floor under the instruction to
keep CLAUDE.md and README.md current.

`verify` is deliberately **not** part of `run`. Reproducing results must not
depend on documentation hygiene, and a pipeline that refuses to compute because
a path in the README moved is a pipeline people route around.

The checks are mechanical, so they cannot evaluate a claim like "this step never
pulls data" or "the default threshold is 30". The `/verify` skill covers that
second layer: it runs these checks, then reads the prose against the code. Use
it after any change that alters what a step does, as opposed to what it is
called.

## Code style

**Module and function size:** Each module in `analysis/` covers a single concern; if a file grows past ~200 lines, consider splitting it. Each function should do one thing — aim for under ~30 lines; longer is a signal to extract a helper.

**Naming:** Prefer self-explanatory names over brevity: `n_subjects` not `n`, `output_path` not `p`, `group_means` not `gm`. Avoid abbreviations unless universally known in the domain (`df` for a DataFrame is fine).

**Linting:** `ruff`, configured under `[tool.ruff]` in `pyproject.toml` (line length 100, rules `E`/`F`/`W`/`I`). Run `uv run ruff check .` before committing. Never disable a lint rule without a comment explaining why.

**Testing:** Two baseline checks, and they cover different failures. `invoke run-smoke` is the behavioural one: does the pipeline run end to end and produce something. `invoke verify` is the structural one: do the code, config, data and docs still describe the same project. Run both before committing; neither substitutes for the other. Add unit tests in a tests directory, using the project's chosen test framework, when a function contains non-trivial logic, has edge cases the smoke test won't catch, or is shared across multiple steps. Unit tests are optional for simple glue/orchestration code but encouraged for any pure transformation or computation logic in `analysis/`. This project uses `pytest`; tests live in `tests/` — `analysis/parcel_networks.py`, `timeseries_reader.py`, `connectome_estimators.py`, `qc_join.py`, `connectome_store.py`, `similarity.py`, `friends_seasons.py`, `group_stats.py` and `domain_titles.py` each have real coverage now, all offline against synthetic fixtures.

**`run-group-stats` as the worked example for a new analysis step:** `analysis/group_stats.py` reads the per-session connectomes `run-connectomes` writes (`output_data/connectomes/{dataset}_{parcellation}.h5`, via `analysis/connectome_store.py`), applies the usable-data gate (`usable_duration_sec >= group_stats.min_usable_seconds` in `invoke.yaml`, see "Settled analysis decisions" above), and produces the two headline analyses — cross-context (all datasets) and longitudinal (`friends` only) — plus the domain-restricted robustness check (see "Domain-restricted cross-context figures" above) for `analysis_measure` (Pearson), gated and ungated, into ten tidy TSVs under `output_data/group_stats/`. `notebooks/figure_connectomes.ipynb` reads those TSVs and plots only; it does no similarity computation itself. Follow this same pattern for a new `run-{name}` step: real logic in a new `analysis/` module, the task body kept to argument handling plus the existence check that makes it idempotent, a matching `clean-{name}`, and a notebook that only plots.

**Respect the analysis hierarchy; do not flatten it.** A step belongs to exactly one tier:

1. **Primary** — the two headline analyses above: cross-context similarity (same-/different-subject x same-/different-dataset) and the friends longitudinal drift control, both per network, both gated and ungated.
2. **Robustness** — checks on the primary result: a further regularized estimator (e.g. graphical lasso) as a check on `partial_ledoitwolf`, removal of the group-average connectome, spatial-distance dependence and neighbouring-parcel exclusion, QC dependence, explicit early-versus-late temporal separation, a duration-matched sensitivity check on the cross-context/duration confound (similarity rises with session duration, which varies ~7x across datasets — median usable seconds range from floc 434 to harrypotter 5044 — so part of the between-task drop in claim 2 is a duration effect; report median duration alongside every per-dataset number rather than introducing a duration-correction model), and the domain-restricted cross-context comparisons (movies/videogames/stories — see "Domain-restricted cross-context figures" above), the one robustness check whose panels are placed in the headline montage rather than kept standalone.

A robustness analysis does not get promoted into the pipeline's main path because it was interesting to implement, and turning every possible branch into an equally weighted step is the failure mode to avoid here. When adding something, say which tier it is in.

**Adding a new analysis step:** add a function to `analysis/`, add a `run-{name}` task and a matching `clean-{name}` task in `tasks.py`, call both from the bodies of the top-level `run` and `clean` tasks (see the `pre=` warning above — a body call, not `pre=`), and create or extend a notebook in `notebooks/` for visualization.

**Evolving CLAUDE.md:** Run `invoke verify` after any structural change — it catches the mechanical half of this instruction (renamed tasks, moved paths, undocumented outputs) that is otherwise left to memory. Keep this file current as the project grows. It should always reflect the actual scope of the project — what it does, what data it uses, and what analysis steps it contains. When adding or removing a task, rename a folder, or change the pipeline structure, update CLAUDE.md in the same commit. Stale guidance here misleads future AI sessions and collaborators alike.

**Keeping README.md current:** README.md is the user-facing documentation for this project. Any structural or workflow change — new tasks, renamed folders, updated commands, new dependencies — must be reflected there in the same commit. The task list in README.md should match `invoke --list` exactly; if a task is added or removed, update README.md accordingly. For data folder contents, point to `source_data/CONTENT.md` and `output_data/CONTENT.md` rather than duplicating their content inline.
