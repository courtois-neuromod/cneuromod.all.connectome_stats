# 📁 Output Data Contents

Once the pipeline is run, this folder will contain the following.

⚠️ **`run-group-stats` is still a stub.** It currently prints what it would do
and writes nothing, so `group_stats/` below is _(pending)_. `run-connectomes`
is implemented — see `connectomes/` below.

- `connectomes/{dataset}_{parcellation}.h5` — one file per cneuromod.all
  dataset **and** parcellation, written by `invoke run-connectomes`. The
  parcellation suffix disambiguates a real `cneuromod2026` run from a
  `schaefer1000` smoke artifact writing to the same dataset name (they used to
  collide on one path, silently clobbering whichever ran last). **Every**
  session found gets a row (session-level
  only — no per-run rows) — there is no usable-data gate here; that happens in
  `run-group-stats`, so it can be varied without recomputing (CLAUDE.md,
  "Record QC, never gate on it"). Per entity: two measures (`pearson`,
  `partial_ledoitwolf`), each computed independently within every network of
  the configured parcellation (7 Yeo networks for schaefer1000; those plus
  `cerebellum` and `subcortex` for cneuromod2026), raw float32 coefficients
  only (Fisher-z is `arctanh` of the raw values, computed where used — this
  amends CLAUDE.md's original "store both raw and Fisher-z"). Layout:

  ```
  /index/<column>                     one array per metadata column
  /networks/<network>/parcels         0-based h5 column indices (fixed geometry)
  /networks/<network>/edges           (n_edges, 2) parcel pairs per edge slot
  /measures/<measure>/<network>       (n_entities, n_edges) float32
  /diagnostics/<measure>/<network>    (n_entities, 6): n_samples, n_parcels,
                                       n_parcels_valid, rank, condition_number,
                                       min_eigenvalue
  ```

  Row *i* of every measure/diagnostics array is row *i* of `/index` — that
  alignment *is* the join key, there is no separate index column. A parcel
  invalid in a given session (NaN or constant) is dropped before
  estimation and its edges scattered back as NaN, so vector length never
  varies (see `analysis/connectome_estimators.py`). Read via
  `analysis/connectome_store.py`.
- `group_stats/` _(pending)_ — group-level summaries aggregated across subjects
  and datasets, written by `invoke run-group-stats`: session × session
  similarity, within- versus between-subject and same-/different-task contrasts,
  and fingerprinting outcomes (accuracy, true-subject rank, identification
  margin) — computed identically for both measures.
- `figures/figure_connectomes/overview.png` — the montage's large left panel.
  A placeholder until `run-group-stats` lands.
- `figures/figure_connectomes/distribution.png` — the montage's smaller right
  panel. Also a placeholder.
- `figures/qc_similarity/{measure}_similarity.png` — exploratory QC, **not**
  part of the montage and **not** `run-group-stats`: a 3×3 grid (one panel per
  network, in `invoke.yaml`'s `network_order`) of session-pair connectome
  similarity, split into same-/different-subject × same-/different-dataset
  bins, one PNG per measure (`pearson`, `partial_ledoitwolf`). Written by
  `notebooks/qc_similarity.ipynb` from `analysis/similarity.py`, reading
  `connectomes/{dataset}_{parcellation}.h5` directly — it has no usable-data
  gate (the FD/duration criteria are still open), so treat it as a sanity
  check, not the headline result. Also writes
  `figures/qc_similarity/pair_summary.tsv` (measure × network × bin summary
  stats).
- `figures/qc_friends_seasons/{measure}_season_bins.png` — tier-3 robustness
  check (CLAUDE.md, "Tier-3 robustness: friends seasons as a temporal-stability
  control"), **not** part of the montage and **not** `run-group-stats`: the
  same 3×3 grid as `qc_similarity`, but restricted to `friends` and split
  same-/different-subject × same-/different-**season** instead of dataset.
  Season is re-derived from the source timeseries h5 key names (not stored in
  the connectome index) and boundary sessions are dropped. Written by
  `notebooks/qc_friends_seasons.ipynb` from `analysis/friends_seasons.py` and
  `analysis/similarity.py`. Also writes
  `figures/qc_friends_seasons/{measure}_season_lag.png` (median similarity vs.
  season lag and vs. binned session gap — the drift curve — plotted for
  within- **and** between-subject pairs on the same axes, so a shared,
  scanner-wide drift would show up as movement in the between-subject curve
  too, not just the within-subject one),
  `figures/qc_friends_seasons/season_pair_summary.tsv` (measure × network ×
  season-bin summary stats) and
  `figures/qc_friends_seasons/season_lag_summary.tsv` (measure × network ×
  pair_type × season-lag summary stats).
- `figures/panel_sizes.json` — the `{panel: (width_mm, height_mm)}` box each
  panel is placed in inside `connectome_figure.svg`, written by
  `invoke run-figure-layout`. Read by the notebook via `airoh.figures.panel_size`
  so each panel renders at exactly its placed size.
- `connectome_figure.svg` — hand-authored in Inkscape, the single source of
  truth for panel layout. A pipeline **source**, not an output, despite living
  here: its `<image>` links are relative paths that resolve from this directory.
  See `CLAUDE.md`, "Figures: the Inkscape montage pattern".
- `connectome_figure.png` — the composed montage, rendered from
  `connectome_figure.svg` by `invoke compose-figure` via the Inkscape CLI
  (skipped with a warning if Inkscape isn't installed).
- `PROVENANCE.json` — what produced everything above: the project's git commit,
  the environment, the input manifest it consumed, and a checksum of every
  output file. Written by `invoke run`.

📝 Note: each notebook writes into a folder named after itself under `figures/`
(`figures/figure_connectomes/`), not directly under `output_data/`. That folder
doubles as the "already ran" marker `run-notebooks` checks, so a notebook that
wrote anywhere else would re-run on every `invoke run`.

📝 Note: csv, tsv, png and h5 files in this folder are **ignored by Git** (see
`.gitignore`), so outputs won't be tracked by default. `connectome_figure.svg`
and `PROVENANCE.json` are the deliberate exceptions: the SVG is hand-authored
source, not a generated output, and `PROVENANCE.json` is small and is the record
of where the untracked results came from. It changes on every run, by design.
