"""Per-network anatomical masks from the MNI group atlas — display only.

These masks exist for one purpose: drawing the nine glass-brain tiles that
serve as the montage's network key (`notebooks/figure_connectomes.ipynb`).
Nothing in the analysis path reads them.

**This is the one place in the repo that reads `anat/atlases`**, a deliberate,
user-approved exception to CLAUDE.md's "do not point the pipeline at
`anat/atlases`" rule. The reason it is unavoidable: the individualized
`_dseg.nii.gz` that ships in each timeseries repo — the file the parcel ->
network lookup reads, and which keeps reading it — is in each subject's own
functional space, so it cannot be projected onto a group glass brain. The
parcel -> network lookup route is untouched by this module.

The label scheme mirrors `cneuromod.all.qa_figures`'s `atlas_tsnr.ipynb`, which
draws the same nine maps: `7Networks_*` names carry the Yeo network in their
third underscore field, `Cereb-*` is cerebellum, and the Tian subcortical
structures make up `subcortex`.
"""

from pathlib import Path

import numpy as np
import pandas as pd

ATLAS_SPACE = "MNI152NLin2009cAsym"
ATLAS_DESC = (
    "Schaefer2018TianS3NettekovenAsym_desc-1000Parcels7Networks50Subcort128Cereb"
)
ATLAS_SUBDIR = f"tpl-{ATLAS_SPACE}"
ATLAS_NII = f"tpl-{ATLAS_SPACE}_res-01_atlas-{ATLAS_DESC}_dseg.nii.gz"
ATLAS_TSV = f"tpl-{ATLAS_SPACE}_atlas-{ATLAS_DESC}.tsv"

YEO_NETWORKS = ("Vis", "SomMot", "DorsAttn", "SalVentAttn", "Limbic", "Cont", "Default")
# Tian S3 subcortical prefixes, checked against the atlas TSV: every name
# that is neither `7Networks_*` nor `Cereb-*` starts with one of these.
SUBCORTEX_PREFIXES = (
    "PUT", "THA", "CAU", "HIP", "AMY", "lAMY", "mAMY", "NAc",
    "GP", "aGP", "pGP", "pTHA", "aTHA",
)


def atlas_paths(cneuromod_dir):
    """`(dseg.nii.gz, labels.tsv)` paths for the MNI group atlas, unchecked."""
    atlas_dir = Path(cneuromod_dir) / "anat" / "atlases" / ATLAS_SUBDIR
    return atlas_dir / ATLAS_NII, atlas_dir / ATLAS_TSV


def classify_region(region_name):
    """Map one atlas region name to a network name, or None if it belongs to none.

    Returns the same nine names this project uses everywhere else — the seven
    Yeo networks plus `cerebellum` and `subcortex` — not qa_figures' display
    labels ("Cerebellum", "Central structures").
    """
    if region_name.startswith("7Networks_"):
        network = region_name.split("_")[2]
        return network if network in YEO_NETWORKS else None
    if region_name.startswith("Cereb-"):
        return "cerebellum"
    structure = region_name.split("-")[0]
    return "subcortex" if structure in SUBCORTEX_PREFIXES else None


def network_label_ids(labels_tsv):
    """`{network: [label_id, ...]}` read from the atlas's own label table."""
    labels = pd.read_csv(labels_tsv, sep="\t").rename(
        columns={"index": "label_id", "name": "region_name"}
    )
    labels["network"] = labels["region_name"].map(classify_region)
    assigned = labels[labels["network"].notna()]
    return {
        network: group["label_id"].tolist()
        for network, group in assigned.groupby("network")
    }


def network_mask_images(dseg_path, labels_tsv, networks):
    """`{network: Nifti1Image}`, each a binary mask of that network's parcels.

    Networks with no matching label in the atlas are omitted rather than
    returned empty, so a caller can tell "not in this atlas" from "empty mask".
    """
    import nibabel as nib
    from nilearn.image import load_img

    atlas_img = load_img(str(dseg_path))
    atlas_data = np.asarray(atlas_img.dataobj)
    label_ids = network_label_ids(labels_tsv)

    masks = {}
    for network in networks:
        ids = label_ids.get(network)
        if not ids:
            continue
        mask = np.isin(atlas_data, ids)
        if mask.any():
            masks[network] = nib.Nifti1Image(mask.astype(np.int8), atlas_img.affine)
    return masks
