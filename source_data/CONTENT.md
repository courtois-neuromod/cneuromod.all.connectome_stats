# 📁 Source Data Contents

After `invoke fetch` is complete, expect the following content:

- `cneuromod.all/` — the CNeuroMod Datalad superdataset, made available by
  `invoke fetch-cneuromod`. Normally a **symlink** to an existing local checkout
  (`../cneuromod.all` by default, overridable with `invoke fetch --source
  /path` or the `source:` key in `invoke.yaml`); cloned from GitHub only when no
  local checkout is found. Only the dataset *tree* is retrieved — annexed file
  content comes separately, and most data files appear as broken symlinks until
  explicitly fetched. That is expected and normal for Datalad.
- `cneuromod.all.qa_figures/` — per-run QC measures (head motion, tSNR), made
  available by `invoke fetch-qa-figures`. Normally a **symlink** to an existing
  local checkout (`../git/cneuromod.all.qa_figures` by default, overridable
  with `invoke fetch --qa-figures-source /path` or the `source:` key under
  `datasets: qa_figures` in `invoke.yaml`); cloned from GitHub only when no
  local checkout is found. See "QC measures (qa_figures)" below.
- `MANIFEST.json` — what each declared asset actually resolved to: the real path
  behind a symlink, its size and checksum, and the commit of the repository it
  belongs to. Written by `invoke fetch`.
- `schaefer1000_networks.tsv`, `cneuromod2026_networks.tsv` — parcel -> network
  lookup tables (`index`, `name`, `network`), written by
  `invoke fetch-parcel-labels`. Neither `.timeseries` repo ships a LUT itself,
  so this project builds one — see "The parcel -> network lookup" below.

## Parcelled BOLD timeseries

`invoke fetch-timeseries` retrieves the parcelled timeseries this project reads,
for the parcellation named by `parcellation:` in `invoke.yaml`. As of
**2026-08-17** the primary parcellation is **`cneuromod2026`** (1134 parcels:
cortex + subcortex + cerebellum), switched from `schaefer1000` to line up with
what the qa_figures QC tables cover — see CLAUDE.md, "Settled analysis
decisions". `run-smoke` still targets `schaefer1000` (see `smoke_parcellation`
in `invoke.yaml`), since it is already fetched on this machine and needs no
S3 credentials, while `cneuromod2026` does.

19 `{dataset}/timeseries` submodules are registered in `cneuromod.all`: `floc`, `movie10`, `friends`, `things`, `hcptrt`, `harrypotter`, `mario`,
`mario3`, `mariostars`, `petit-prince`, `retinotopy`, `shinobi`, `gamepad`,
`langlocalizer`, `multfs`, `mutemusic`, `narratives`, `ood` and `triplets`. The fetch **discovers** them — it processes every dataset carrying a
`timeseries` directory, so a twentieth needs no code change. The seven
registered on 2026-09-04 (`gamepad`, `langlocalizer`, `multfs`, `mutemusic`,
`narratives`, `ood`, `triplets`) are un-installed mountpoints here: no content
has been fetched for them, so they contribute to no result and every `run-*`
step warns and skips them.

Layout, per dataset (schaefer1000 shown; cneuromod2026 is the same shape under
a `cneuromod2026/` parcellation directory, with `atlas-cneuromod26` or
`atlas-cneuromod2026` in the filename — both spellings occur, and
`analysis/timeseries_layout.py` matches on filename suffix precisely to avoid
depending on that entity):

```
cneuromod.all/{dataset}/timeseries/timeseries/schaefer1000/sub-0X/
    sub-0X_task-{dataset}_space-MNI152NLin2009cAsym_atlas-Schaefer2018_desc-1000Parcels7Networks_timeseries.h5
    sub-0X_task-{dataset}_space-MNI152NLin2009cAsym_atlas-Schaefer2018_desc-1000Parcels7Networks_dseg.nii.gz
    sub-0X_task-{dataset}_space-MNI152NLin2009cAsym_label-GMfromTemplate_desc-indivFunc_mask.nii.gz
```

There is **one `.h5` per subject**, holding every session and run as separate 2D
`(timepoints, parcels)` arrays keyed `ses-XXX/ses-XXX_task-..._run-N_timeseries`
(`run` is optional — `friends` keys carry no `_run-N` segment at all). That is
the finest unit the annex stores, so `--subject` can narrow a fetch but there
is nothing session-level to request; selecting sessions is a read-time concern
for `run-connectomes`.

`voxel_mni` and `voxel_native` (voxelwise, much larger) also ship in every
repo and are **not** fetched. The parcellation atlases ship **inside** the
timeseries repos, so `anat/atlases` is never needed by this project's fetch.

### The parcel -> network lookup

Neither the `.h5` files nor anything else in a `.timeseries` repo names which
network a parcel belongs to — the `_dseg.nii.gz` carries bare integer labels.
`invoke fetch-parcel-labels` builds the lookup table instead of fetching one:

- **`schaefer1000`** — from nilearn's bundled Schaefer-2018 atlas
  (`nilearn.datasets.fetch_atlas_schaefer_2018`), no extra data pulled.
- **`cneuromod2026`** — by reading one already-fetched subject's individualized
  `_dseg.nii.gz` (never `anat/atlases`) and decoding its integer label values.
  This decoding rests on a **documented, not-yet-verified assumption** about
  how the atlas's three source blocks (Schaefer cortex, Tian subcortex,
  Nettekoven cerebellum) are numbered — see
  `analysis.parcel_networks.build_cneuromod2026_labels`'s docstring. It asserts
  the resulting per-network parcel counts against the composition documented
  in CLAUDE.md and raises rather than writing a silently wrong table if they
  disagree. **Requires S3 credentials** (via `invoke fetch-timeseries
  --parcellation cneuromod2026`) to have already pulled that subject's dseg —
  this environment had none while writing this, so the assumption has not yet
  been checked against real label values.

## QC measures (qa_figures)

`cneuromod.all.qa_figures` is a Datalad dataset with **no annexed content** —
every tracked file is a plain git blob, ~33 MB total. `invoke fetch-qa-figures`
installs the tree; that already **is** the data, so unlike `cneuromod.all` no
content-fetch step follows it, and **no credentials are needed** — it is a
plain public git repo.

Two table families under `output_data/tables/` inside the checkout, both
**per functional run**, read via `analysis/qc_measures.py`:

- `tables/{dataset}.tsv` — one row per run, 21 columns: entities `dataset,
  subject, session, task, run, task_grouped`; motion `fd_mean, fd_num,
  fd_perc, fd_prop_gt02, fd_prop_gt05`; and `tsnr, snr, gsr_x, gsr_y,
  dvars_std, dvars_vstd, aor, aqi, gcor, size_t`. `fd_prop_gt02/05` are
  proportions in 0–1, and are blank throughout for **both** `movie10` and
  `friends` (not just `friends`, as an earlier version of this doc claimed).
  `run` is inconsistent even within one dataset: `movie10` leaves it blank for
  some subject/session combinations and fills it as a float-like string
  (`"1.0"`) for others — `analysis/qc_join.py`'s entity join strips the
  trailing `.0` for exactly this reason. `session` is 2-digit for some
  datasets (`things`) and 3-digit for others (`floc`, `retinotopy`);
  `analysis/qc_join.py`'s `normalize_entities` zero-pads to 3 digits uniformly.
- `tables/atlas_tsnr/{dataset}.tsv` — tSNR per network, one row per
  (run × region group): `group, tsnr_mean, n_parcels` plus the same entities.
  11 groups: the 7 Yeo networks (`cortex_<Network>`), `cerebellum`, and
  `subcortex_{PUT,THA,CAU}`. Weight by `n_parcels` (in-FOV count) when pooling
  groups.

**Coverage is partial, and downstream code must tolerate it** — this is an
upstream credentialed-content gap, not a bug here. As of **2026-08-17**: 17 of
21 per-run tables are populated (`anat`, `emotion-videos`, `langlocalizer`,
`mario` are empty 1-byte files); only **3** `atlas_tsnr` tables are populated
(`things`, `retinotopy`, `floc`) — the other 17 are empty. `analysis.qc_measures.
available_datasets` reports only the non-empty tables, and the loaders skip
empty ones rather than raising.

**The `atlas_tsnr` gap is load-bearing for the analysis, not just tidiness.**
The three populated tables — `things`, `retinotopy`, `floc` — are exactly the
three datasets the `usable_duration_sec >= 1800` gate removes entirely
(CLAUDE.md, "Settled analysis decisions"). So although `run-connectomes` joins
per-network tSNR onto every session index as `tsnr_{network}`, those columns
are non-NaN for **0 of the 304 QC-covered sessions**. Any per-network tSNR
analysis — including a per-network version of `run-tsnr-strata` — is
impossible until the naturalistic datasets' `atlas_tsnr` tables are populated
upstream. `run-tsnr-strata` therefore uses the whole-brain `tsnr` scalar only,
and `group_stats.network_quality` reports per-network tSNR from those three
gate-excluded datasets purely as context. Nothing in this repository can close
this gap; it needs an upstream qa_figures export.

`analysis/qc_join.py` joins these entities against the timeseries `.h5` run
keys (`ses-XXX/ses-XXX_task-..._run-N_timeseries`), normalizing both sides
(prefix stripping, session zero-padding, the `run` float-string quirk above)
before matching on `dataset, subject, session, task, run`. The join is
**best-effort**: unmatched rows keep NaN in the QC columns and get
`qc_matched = False`, never a raised error — `run-connectomes` calls this for
every dataset, including the ones with no QC coverage at all.

## Access requirements

**Timeseries content currently requires CNeuroMod credentials — for every
dataset, including `floc`.** Each `{dataset}.timeseries` repository stores its
annexed content on a single S3 special remote (`s3.unf-montreal.ca`, one bucket
per dataset) that denies anonymous reads. Without credentials, `datalad get`
reports `No publicurl is configured for this remote` per file.

The `*.fmriprep` datasets additionally publish to the CONP RIA store
(`https://sftp.conp.ca/...`) via an autoenabled `httpalso` remote that *does*
serve anonymous downloads. The `*.timeseries` datasets have **not** been
published there yet. When they are, no change is needed here: datalad enables
that remote automatically and the fetch starts working without credentials.

For a full fetch, export S3 credentials before running — git-annex reads the
standard AWS variable names for this remote:

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
invoke fetch
```

What to expect either way:

- Installing a subdataset needs only the **public git tree**, which works
  anonymously over HTTPS. So filenames always appear, even with no credentials.
- Retrieving **content** is **tolerant**: an inaccessible file warns and is
  skipped, so one restricted dataset never aborts a whole fetch. Failed paths
  are recorded in `.fetch_failures.json` and not retried; delete that file to
  force a retry after obtaining access.
- A fetch that came back empty means *you lack access to that content*, not that
  the pipeline is broken.
- `invoke run-smoke` fails only if a subdataset **tree** cannot be installed —
  i.e. genuinely broken plumbing. Missing content does not fail it, precisely
  because no timeseries dataset is anonymously readable yet.

📝 Note: `.h5`, `.nii.gz` and `.tsv` files are **ignored by Git** (see
`.gitignore`), so data assets are never tracked, and so is the per-environment
`.fetch_failures.json`. `MANIFEST.json` is the deliberate exception — it is the
record of which inputs a run consumed.
