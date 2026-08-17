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

## Parcelled BOLD timeseries

`invoke fetch-timeseries` retrieves the parcelled timeseries this project reads,
for the parcellation named by `parcellation:` in `invoke.yaml` (**`schaefer1000`**).
As of **2026-08-17**, 12 `{dataset}/timeseries` submodules are registered in
`cneuromod.all`: `floc`, `movie10`, `friends`, `things`, `hcptrt`,
`harrypotter`, `mario`, `mario3`, `mariostars`, `petit-prince`, `retinotopy`
and `shinobi`. The fetch **discovers** them — it processes every dataset
carrying a `timeseries` directory, so a thirteenth needs no code change.

Layout, per dataset:

```
cneuromod.all/{dataset}/timeseries/timeseries/schaefer1000/sub-0X/
    sub-0X_task-{dataset}_space-MNI152NLin2009cAsym_atlas-Schaefer2018_desc-1000Parcels7Networks_timeseries.h5
    sub-0X_task-{dataset}_space-MNI152NLin2009cAsym_atlas-Schaefer2018_desc-1000Parcels7Networks_dseg.nii.gz
    sub-0X_task-{dataset}_space-MNI152NLin2009cAsym_label-GMfromTemplate_desc-indivFunc_mask.nii.gz
```

There is **one `.h5` per subject**, holding every session and run as separate 2D
`(timepoints, parcels)` arrays keyed `ses-XXX/ses-XXX_task-..._run-N_timeseries`.
That is the finest unit the annex stores, so `--subject` can narrow a fetch but
there is nothing session-level to request; selecting sessions is a read-time
concern for `run-connectomes`.

Three other parcellations ship in every repo and are **not** fetched:
`cneuromod2026` (1134 parcels, adding subcortical and cerebellar), `voxel_mni`
and `voxel_native` (voxelwise, much larger). The parcellation atlases ship
**inside** the timeseries repos, so `anat/atlases` is not needed.

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
  proportions in 0–1. `run` and `session` are often blank for naturalistic
  datasets (e.g. `friends` task `s01e02a` has no run index).
- `tables/atlas_tsnr/{dataset}.tsv` — tSNR per network, one row per
  (run × region group): `group, tsnr_mean, n_parcels` plus the same entities.
  11 groups: the 7 Yeo networks (`cortex_<Network>`), `cerebellum`, and
  `subcortex_{PUT,THA,CAU}`. Weight by `n_parcels` (in-FOV count) when pooling
  groups.

**Coverage is partial, and downstream code must tolerate it** — this is an
upstream credentialed-content gap, not a bug here. As of **2026-08-17**: 17 of
21 per-run tables are populated (`anat`, `emotion-videos`, `langlocalizer`,
`mario` are empty 1-byte files); only **3** `atlas_tsnr` tables are populated
(`things`, `retinotopy`, `floc`) — the other 17 are empty; and `friends.tsv`
has `fd_prop_gt02/gt05` blank throughout. `analysis.qc_measures.available_datasets`
reports only the non-empty tables, and the loaders skip empty ones rather than
raising.

Joining these entities against the timeseries `.h5` run keys
(`ses-XXX/ses-XXX_task-..._run-N_timeseries`) is deliberately **not** done
here — the entity conventions differ per dataset (blank `run`, task-encoded
segments), and that mapping belongs with `run-connectomes`, once its method
is settled.

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
