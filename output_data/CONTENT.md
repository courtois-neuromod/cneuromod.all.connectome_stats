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
    `gate="all"` the within-task bins run ~1.7x the between-task bins; at
    `gate="gated"` the gap narrows to ~1.20x but no longer closes, since the
    six datasets added on 2026-09-04 entered the analysis. Read this table
    alongside `cross_context.tsv` rather than assuming the gate made the
    contrast duration-clean.
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
- `motion_strata/` — robustness-tier QC (motion) dependence check (CLAUDE.md,
  "Motion stratification"), written by `invoke run-motion-strata` from
  `analysis/motion_strata.py`, Pearson only, restricted throughout to the
  **QC-covered** population (gated **and** `fd_mean` present — `mario` and
  `harrypotter` have zero `fd_mean` coverage upstream, so they never enter
  this analysis):
  - `motion_strata.tsv` — `network × split × bin` -> `n, median, q25, q75,
    mean, sd, n_sessions`. `split` is `"cell"` (median split within each
    (subject, dataset) cell — the primary split, orthogonal to both by
    construction) or `"subject"` (plain within-subject median split, kept as a
    secondary comparison). `bin` is one of the six `{low-low, low-high,
    high-high}/{within-task, between-task}` labels, within-subject pairs only.
  - `motion_pair_histograms.tsv` — precomputed `(network, split, bin,
    bin_left, bin_right, count)` histograms backing the same six bins.
  - `motion_balance.tsv` — `bin × split` -> `n_pairs, median_min_duration_sec,
    median_min_tsnr, n_sessions`: the pairwise-minimum usable-duration **and**
    tSNR distribution across the six bins, the audit that the motion split is
    not secretly a duration or a pure-tSNR confound (`fd_mean` vs. `tsnr` is
    r=-0.68, so tSNR is expected to track the stratum; duration, r=-0.065, is
    not).
  - `motion_permutation.tsv` — `network` -> `observed_diff` (`median(low-low) -
    median(high-high)`, pooled over both task bins), `p_value` (two-sided,
    `motion_strata.n_permutations` shuffles of `motion_stratum` within each
    (subject, dataset) cell), `n_subjects_replicating`/`n_subjects_total`
    (how many of the 6 participants show `median(low-low) >
    median(high-high)` individually — the six-participants inference rule,
    CLAUDE.md, "Scientific objective").
  - `motion_sessions.tsv` — one row per QC-covered session: `dataset, subject,
    session, fd_mean, tsnr, usable_duration_sec, motion_stratum_cell,
    motion_stratum_subject` — for auditability.
- `figures/figure_motion/motion_bins.png`, `motion_bins_legend.png` — the six
  motion×task bins ("cell" split) × nine networks, grouped bar chart plus its
  legend strip, within-task bins grouped together and between-task bins
  grouped together (task outer, motion-pairing inner). This is the sole panel
  `figure_motion.ipynb` renders — the headline correlation (similarity)
  result. The duration/tSNR balance audit (`motion_balance.tsv`) and the
  permutation-test effect sizes (`motion_permutation.tsv`) are still computed
  by `run-motion-strata` but are reported as text (key stats and ranges), not
  as figure panels.
  **Standalone figure — deliberately not placed in `connectome_figure.svg`**;
  see CLAUDE.md, "Motion stratification".
- `tsnr_strata/` — robustness-tier QC (tSNR) dependence check (CLAUDE.md,
  "tSNR stratification"), written by `invoke run-tsnr-strata` from
  `analysis/tsnr_strata.py`, Pearson only, over the **same** QC-covered
  population as `motion_strata/` (gated **and** `fd_mean` present — the
  population definition is deliberately shared, so the two axes are directly
  comparable). Every table carries a `stratum_def` column alongside `split`:
  `"raw"` (median split on `tsnr`) or `"fd_residual"` (median split on `tsnr`
  residualized on `fd_mean` within the same cell — near-independent of the
  motion stratum, where `raw` is 72% concordant with it). Whole-brain `tsnr`
  only: the per-network `tsnr_{network}` columns are non-NaN for none of the
  covered sessions, because `atlas_tsnr` is populated upstream only for the
  three datasets the gate removes (see `source_data/CONTENT.md`).
  - `tsnr_strata.tsv` — `network × stratum_def × split × bin` -> `n, median,
    q25, q75, mean, sd, n_sessions`. `bin` is one of the six `{high-high,
    low-high, low-low}/{within-task, between-task}` labels — good-good first,
    since high tSNR is the good end — within-subject pairs only.
  - `tsnr_pair_histograms.tsv` — precomputed `(network, stratum_def, split,
    bin, bin_left, bin_right, count)` histograms backing the same six bins.
  - `tsnr_balance.tsv` — `bin × stratum_def × split` -> `n_pairs,
    median_min_duration_sec, median_min_tsnr, median_max_fd_mean,
    n_sessions`. Duration is the confound the 1800 s gate exists for
    (`tsnr` vs. usable duration is r=0.04 per session): the strata are
    balanced within the within-task bin (1.02x under `raw`) but not the
    between-task bin (1.15x under `raw`, 1.06x under `fd_residual`) — a gap
    that would raise high-high similarity, i.e. it points against the observed
    negative effect rather than explaining it. `median_max_fd_mean` is the
    motion coupling, and comparing the two `stratum_def` values shows how much
    of it residualizing removes (0.107→0.131 across bins for `raw`,
    0.116→0.128 for `fd_residual` — shrunk, never eliminated).
  - `tsnr_permutation.tsv` — `network × stratum_def` -> `observed_diff`
    (`median(high-high) - median(low-low)`, pooled over both task bins — the
    same "better quality is positive" sign convention as the motion table),
    `p_value` (two-sided, `tsnr_strata.n_permutations` shuffles of
    `tsnr_stratum` within each (subject, dataset) cell),
    `n_subjects_replicating`/`n_subjects_total` (how many of the 6
    participants show `median(high-high) > median(low-low)` individually —
    note this counts the *positive* direction, so where `observed_diff` is
    negative the count agreeing with the pooled sign is the complement).
  - `tsnr_sessions.tsv` — one row per QC-covered session: `dataset, subject,
    session, fd_mean, tsnr, usable_duration_sec`, plus
    `tsnr_stratum_{cell,subject}_{raw,fd_residual}` — for auditability.
- `figures/figure_tsnr/tsnr_bins_raw.png` — the six tSNR×task bins ("cell"
  split) × nine networks under the `raw` definition (median split on `tsnr`
  itself), within-task bins grouped together and between-task bins grouped
  together (task outer, tSNR-pairing inner). This is the **primary, reported**
  panel `figure_tsnr.ipynb` renders — the headline correlation (similarity)
  result.
- `figures/figure_tsnr/tsnr_bins_fd_residual.png` — same layout, under the
  `fd_residual` definition (median split on `tsnr` residualized on `fd_mean`
  within cell). tSNR and `fd_mean` correlate at r=-0.68 — related, but not
  equivalent — so this is a **sensitivity-analysis** panel checking whether
  the `raw` result holds once head motion is regressed out, not a second
  headline result to report on its own.
- `figures/figure_tsnr/tsnr_bins_legend.png` — legend strip shared by both
  panels above, since the six bins are identical.
  The duration/tSNR/motion balance audit (`tsnr_balance.tsv`) and the
  permutation-test effect sizes (`tsnr_permutation.tsv`) are still computed by
  `run-tsnr-strata` but are reported as text (key stats and ranges), not as
  figure panels.
  **Standalone figures — deliberately not placed in `connectome_figure.svg`**;
  see CLAUDE.md, "tSNR stratification".
- `figures/figure_connectomes/network_maps.png` — the montage's network key:
  nine sagittal glass brains, one per network, each filled with its
  `NETWORK_COLORS` entry and named beside it, spanning the full page height
  down the left edge, stacked in decreasing panel-A stability (mean gated
  within-subject median similarity over season lags) so the key doubles as a
  ranking — only this panel is reordered; the rest keep `NETWORK_ORDER`.
  Every other panel inherits those colours (panel A's
  lines, panel C's points and labels, the bar panels' x-tick bubbles), which is
  why none of them repeats a nine-network legend. Drawn from the MNI group
  atlas via `analysis/atlas_maps.py` — display only, and the sole place this
  project reads `anat/atlases` (CLAUDE.md, "The parcel -> network lookup").
  Omitted with a warning when that atlas content is not retrieved.
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
  the key. `longitudinal_legend.png` holds a single entry (the between-subject
  band) — its nine networks are keyed by `network_maps.png` instead. The panels themselves are drawn bare (no legend, no title): both are
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
- `connectome_figure_caption.md` — hand-written caption for the montage, kept
  beside the hand-authored SVG rather than in a manuscript so the numbers it
  quotes stay next to the tables they came from. Not produced by any pipeline
  step, and not regenerated: every figure quoted in it was read from
  `group_stats/*.tsv` by hand, so re-check it after a rerun on different data.
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

📝 Note: csv, tsv and h5 files in this folder are **ignored by Git** (see
`.gitignore`), so most outputs won't be tracked by default. `connectome_figure.svg`,
`PROVENANCE.json` and the PNG figures (every panel under `figures/figure_connectomes/`
plus `connectome_figure.png`) are the deliberate exceptions: the SVG is
hand-authored source, not a generated output; `PROVENANCE.json` is small and is
the record of where the untracked results came from (it changes on every run,
by design); and the figures are the pipeline's actual visual output, small
enough in aggregate (~1.2 MB) to track and review across pipeline changes
(CLAUDE.md, "Where data lives"). `panel_sizes.json` stays untracked — it is
fully derived from the tracked `connectome_figure.svg` and regenerated on every run.
