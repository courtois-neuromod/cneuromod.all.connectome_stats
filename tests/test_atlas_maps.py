"""Tests for `analysis.atlas_maps` — the display-only network masks.

Offline: `classify_region` and `network_label_ids` are pure functions over
region names, so a synthetic label table exercises them without the atlas.
"""

import pandas as pd
import pytest

from analysis.atlas_maps import atlas_paths, classify_region, network_label_ids


@pytest.mark.parametrize(
    "region_name, expected",
    [
        ("7Networks_LH_Vis_1", "Vis"),
        ("7Networks_RH_SalVentAttn_12", "SalVentAttn"),
        ("7Networks_RH_Default_3", "Default"),
        ("Cereb-A-L", "cerebellum"),
        ("PUT-DA-lh", "subcortex"),
        ("lAMY-rh", "subcortex"),
        ("aGP-lh", "subcortex"),
        ("7Networks_LH_NotANetwork_1", None),
        ("something-else", None),
    ],
)
def test_classify_region(region_name, expected):
    assert classify_region(region_name) == expected


def test_network_label_ids_groups_by_network(tmp_path):
    labels = pd.DataFrame({
        "index": [1, 2, 3, 4, 5],
        "name": ["7Networks_LH_Vis_1", "7Networks_RH_Vis_2", "Cereb-A-L",
                 "THA-DP-lh", "unassignable"],
    })
    labels_tsv = tmp_path / "labels.tsv"
    labels.to_csv(labels_tsv, sep="\t", index=False)

    ids = network_label_ids(labels_tsv)

    assert ids == {"Vis": [1, 2], "cerebellum": [3], "subcortex": [4]}


def test_atlas_paths_points_at_anat_atlases():
    dseg_path, labels_path = atlas_paths("/somewhere/cneuromod.all")

    assert dseg_path.parent == labels_path.parent
    assert dseg_path.parent.parts[-3:-1] == ("anat", "atlases")
    assert dseg_path.name.endswith("_dseg.nii.gz")
    assert labels_path.suffix == ".tsv"
