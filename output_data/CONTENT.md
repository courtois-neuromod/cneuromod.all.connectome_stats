# 📁 Output Data Contents

Once the pipeline is run, this folder will contain the following.

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
- `group_stats/` — the two headline analyses (CLAUDE.md, "Scientific
  objective"), written by `invoke run-group-stats` from
  `analysis/group_stats.py`, Pearson only (`analysis_measure`), gated
  (`usable_duration_sec >= group_stats.min_usable_seconds`, default 1800 s) and
  ungated:
  - `cross_context.tsv` — analysis B (all datasets): `network × bin × gate` ->
    `n, median, q25, q75, mean, sd, n_edges_valid, n_edges_total`. Bins are the
    four same-/different-subject × same-/different-dataset labels.
  - `longitudinal_bins.tsv` — analysis A (`friends` only): same shape, bins are
    same-/different-subject × same-/different-**season**.
  - `longitudinal_lag.tsv` — analysis A: `network × pair_type × gate ×
    lag_type × lag_value` -> `n, median, q25, q75`. `lag_type` is `season`
    (0-5 season lag) or `session_gap_decile` (binned session-ordinal gap, the
    only time axis available — no acquisition dates are stored).
  - `network_quality.tsv` — per network: `median_tsnr`, `n_tsnr` (coverage
    count), contributing `datasets`, and within-subject median similarity from
    both analyses (`within_subject_median_cross_context`,
    `within_subject_median_longitudinal`, gated).
  - `session_gate.tsv` — per dataset: `n_sessions`, `n_passing` the 1800 s
    gate, `median_usable_duration_sec`, `qc_coverage` (fraction of sessions
    with a motion-QC match).
  - `pair_histograms.tsv` — precomputed `(analysis, network, gate, bin,
    bin_left, bin_right, count)` histogram counts backing the notebook's
    density grids, so ~343k pair-level values never get written out directly.
  - `duration_balance.tsv` — `gate × bin` -> `n_pairs, median_min_duration_sec,
    q25, q75, n_sessions`: the pairwise-minimum usable-duration distribution
    across the same four cross-context bins as `cross_context.tsv`, computed
    with `analysis/group_stats.py`'s `duration_balance`. This is the audit
    behind the 1800 s gate — see CLAUDE.md, "Settled analysis decisions": at
    `gate="all"` the within-task bins run ~1.6x the between-task bins; at
    `gate="gated"` they're within ~4% of each other.
  - `domain_cross_context.tsv`, `domain_pair_histograms.tsv`,
    `domain_duration_balance.tsv` — a robustness-tier check on analysis B
    (CLAUDE.md, "Domain-restricted cross-context figures"): the same shapes as
    `cross_context.tsv`/`pair_histograms.tsv`/`duration_balance.tsv`, each with
    an added `domain` column, computed once per domain in
    `analysis.group_stats.DOMAIN_DATASETS` (`movies`, `videogames`, `stories`)
    by `domain_cross_context_summary`. `movies` bins by title-level task
    identity (friends season or movie10 title, via `analysis/domain_titles.py`)
    rather than dataset, since `friends`/`movie10` alone would collapse to a
    two-value dataset contrast; `videogames`/`stories` bin by dataset, same
    axis as `cross_context.tsv`, just restricted to fewer datasets.
- `figures/figure_connectomes/longitudinal.png` — claim 1: within-subject
  Pearson similarity vs. friends season lag, one line per network, against the
  between-subject band.
- `figures/figure_connectomes/cross_context.png` — claim 2: the four bins ×
  nine networks, all datasets, gated.
- `figures/figure_connectomes/network_quality.png` — claim 3: per-network
  within-subject stability vs. median tSNR (falls back to a labelled ordering
  plot when tSNR coverage is too thin, with the caveat written to
  `network_quality_note.txt` rather than onto the panel).
- `figures/figure_connectomes/domain_movies.png`, `domain_videogames.png`,
  `domain_stories.png` — the same four-bin × nine-network chart as
  `cross_context.png`, one per domain in `domain_cross_context.tsv`. Placed in
  the headline montage at the user's request, despite being a robustness-tier
  check on claim 2, not a fourth headline claim (CLAUDE.md, "Domain-restricted
  cross-context figures").
- `figures/figure_connectomes/longitudinal_legend.png`,
  `cross_context_legend.png`, `domain_movies_legend.png`,
  `domain_videogames_legend.png` and `domain_stories_legend.png` — the legends
  for the panels above, each a standalone horizontal strip holding nothing but
  the key. The panels themselves are drawn bare (no legend, no title): both are
  montage-level furniture that crowds the data inside a panel-sized canvas, so
  they are placed once in `connectome_figure.svg` instead. The strips are
  montage elements like any other — linked by relative path and sized through
  `panel_size`. `network_quality.png` has a single series and so gets no strip.
- `figures/figure_connectomes/network_quality_note.txt` — the tSNR-coverage
  caveat for panel 3 as plain text, to be typeset as caption in the montage
  rather than drawn onto the panel. Empty when coverage is sufficient and the
  panel shows the real tSNR scatter.
- `figures/figure_connectomes/{analysis}_{measure}_histograms.png` — diagnostic
  3×3 density grids per analysis (`cross_context`, `longitudinal`), not montage
  panels, saved alongside the panels above (same "already ran" folder).
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
