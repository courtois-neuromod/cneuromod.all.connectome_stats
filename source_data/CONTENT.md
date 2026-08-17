# 📁 Source Data Contents

After `invoke fetch` is complete, expect the following content:

- `cneuromod.all/` — the CNeuroMod Datalad superdataset, made available by
  `invoke fetch-cneuromod`. Normally a **symlink** to an existing local checkout
  (`../cneuromod.all` by default, overridable with `invoke fetch --source
  /path` or the `source:` key in `invoke.yaml`); cloned from GitHub only when no
  local checkout is found. Only the dataset *tree* is retrieved — annexed file
  content comes separately, and most data files appear as broken symlinks until
  explicitly fetched. That is expected and normal for Datalad.
- `MANIFEST.json` — what each declared asset actually resolved to: the real path
  behind a symlink, its size and checksum, and the commit of the repository it
  belongs to. Written by `invoke fetch`.

## ⚠️ Timeseries assets are not reachable yet

This project reads **parcelled BOLD timeseries**. The
`courtois-neuromod/*.timeseries` repositories exist on GitHub
(`floc.timeseries`, `movie10.timeseries`, `friends.timeseries`, … 14 in total),
but as of **2026-08-17** they are **not registered as submodules of
cneuromod.all**. Neither the local checkout nor `origin/main` lists a
`timeseries` submodule, so the `{dataset}/timeseries` path this project is
configured to read does not resolve in any checkout.

`invoke fetch-timeseries` is therefore a deliberate **stub**: it reports what it
would retrieve and exits cleanly. It is not broken, and neither is your
checkout. Once the submodules land upstream, the stub gets its real body and the
`timeseries_marker` / `parcellation` keys in `invoke.yaml` take effect.

Expected layout once available, per dataset:

```
cneuromod.all/{dataset}/timeseries/timeseries/{parcellation}/sub-0X/
    sub-0X_task-..._atlas-..._desc-...Parcels..._timeseries.h5   # (timepoints, parcels) per run
    sub-0X_task-..._atlas-..._desc-...Parcels..._dseg.nii.gz     # the parcellation itself
    sub-0X_task-..._label-...(GM)..._mask.nii.gz                 # grey-matter mask
```

Each `.h5` holds one 2D array per run, keyed
`ses-XXX/ses-XXX_task-..._run-N_timeseries`. Four parcellations ship in every
repo: `schaefer1000` (1000 cortical parcels), `cneuromod2026` (1134 parcels,
adding subcortical and cerebellar), `voxel_mni` and `voxel_native` (voxelwise,
much larger). The parcellation atlases ship **inside** the timeseries repos, so
`anat/atlases` is not needed.

## Access requirements

Most CNeuroMod data is openly accessible, but **not all of it has been
configured that way yet**. Content behind a credentialed remote fails per-file
for anyone without access.

- Retrieval is **tolerant by default**: an inaccessible file warns and is
  skipped, so one restricted dataset never aborts a whole fetch.
- A fetch that came back partly empty most likely means *you lack access to that
  content*, not that the pipeline is broken.
- For a full run, expose your CNeuroMod credentials as environment variables in
  your shell before calling `invoke fetch` — see the README, "Credentials for a
  full fetch".
- `floc` is openly accessible and is the smoke-test target, so a smoke failure
  unambiguously means broken plumbing rather than missing permissions.

📝 Note: `.h5`, `.nii.gz` and `.tsv` files are **ignored by Git** (see
`.gitignore`), so data assets are never tracked. `MANIFEST.json` is the
deliberate exception — it is the record of which inputs a run consumed.
