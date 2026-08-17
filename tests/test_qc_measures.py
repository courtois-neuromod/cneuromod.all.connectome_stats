"""Tests for the QC table reader in analysis/qc_measures.py."""

from analysis.qc_measures import (
    atlas_tsnr_table_path,
    available_datasets,
    load_atlas_tsnr,
    load_qc_measures,
    qc_table_path,
)


def _make_qa_root(tmp_path):
    tables_dir = tmp_path / "output_data" / "tables"
    atlas_dir = tables_dir / "atlas_tsnr"
    atlas_dir.mkdir(parents=True)

    (tables_dir / "floc.tsv").write_text(
        "dataset\tsubject\tsession\ttask\trun\tfd_mean\ttsnr\n"
        "floc\t01\t001\tfLoc\t1\t0.08\t35.9\n"
        "floc\t02\t001\tfLoc\t1\t0.05\t40.1\n"
    )
    (tables_dir / "empty.tsv").write_text("\n")

    (atlas_dir / "floc.tsv").write_text(
        "group\ttsnr_mean\tn_parcels\tdataset\tsubject\tsession\ttask\trun\n"
        "cerebellum\t36.0\t88\tfloc\t01\t001\tfLoc\t1\n"
        "cortex_Cont\t48.1\t128\tfloc\t01\t001\tfLoc\t1\n"
    )
    (atlas_dir / "empty.tsv").write_text("\n")

    return tmp_path


def test_qc_table_path_and_atlas_tsnr_table_path(tmp_path):
    assert qc_table_path(tmp_path, "floc") == tmp_path / "output_data/tables/floc.tsv"
    assert (
        atlas_tsnr_table_path(tmp_path, "floc")
        == tmp_path / "output_data/tables/atlas_tsnr/floc.tsv"
    )


def test_available_datasets_skips_empty_tables(tmp_path):
    qa_root = _make_qa_root(tmp_path)
    assert available_datasets(qa_root) == ["floc"]
    assert available_datasets(qa_root, kind="atlas_tsnr") == ["floc"]


def test_load_qc_measures_skips_empty_and_keeps_entity_strings(tmp_path):
    qa_root = _make_qa_root(tmp_path)
    df = load_qc_measures(qa_root)

    assert df.dtypes["subject"].kind == "O"
    assert df.dtypes["session"].kind == "O"
    assert list(df["subject"]) == ["01", "02"]


def test_load_atlas_tsnr_returns_expected_groups(tmp_path):
    qa_root = _make_qa_root(tmp_path)
    df = load_atlas_tsnr(qa_root)

    assert set(df["group"]) == {"cerebellum", "cortex_Cont"}


def test_loaders_return_empty_frame_when_nothing_is_available(tmp_path):
    (tmp_path / "output_data" / "tables" / "atlas_tsnr").mkdir(parents=True)
    (tmp_path / "output_data" / "tables" / "only_empty.tsv").write_text("\n")

    assert load_qc_measures(tmp_path).empty
    assert load_atlas_tsnr(tmp_path).empty
