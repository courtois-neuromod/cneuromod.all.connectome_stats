# 📁 Output Data Contents

Once the pipeline is run, this folder will contain the following.

⚠️ **The analysis steps are still stubs.** `run-connectomes` and
`run-group-stats` currently print what they would do and write nothing, so only
the figure-layout and notebook outputs below actually appear today. The entries
marked _(pending)_ describe the intended outputs.

- `connectomes/` _(pending)_ — per-session, per-network connectomes, one set per
  cneuromod.all dataset, written by `invoke run-connectomes`: for each session
  that clears the usable-data criterion, seven within-network **partial
  correlation** matrices and seven **Pearson** matrices (raw and Fisher-z), each
  with its numerical diagnostics (rank, condition number, minimum eigenvalue,
  n samples, n parcels) and the session's QC summary.
- `group_stats/` _(pending)_ — group-level summaries aggregated across subjects
  and datasets, written by `invoke run-group-stats`: session × session
  similarity, within- versus between-subject and same-/different-task contrasts,
  and fingerprinting outcomes (accuracy, true-subject rank, identification
  margin) — computed identically for both measures.
- `figures/figure_connectomes/overview.png` — the montage's large left panel.
  A placeholder until the analysis steps land.
- `figures/figure_connectomes/distribution.png` — the montage's smaller right
  panel. Also a placeholder.
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
