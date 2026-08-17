"""Where the parcelled timeseries live inside a `{dataset}.timeseries` repo.

Pure path construction and filtering — no I/O, no datalad. The retrieval
orchestration that uses these helpers lives in `tasks.py`, next to the other
fetch tasks; this module holds the part worth unit-testing.
"""

# Matched on the filename *suffix* rather than on the atlas entity, on purpose.
# Upstream writes `atlas-Schaefer2018` while TIMESERIES.md documents
# `atlas-Schaefer18`, and the two voxelwise parcellations carry no atlas entity
# at all — a suffix match is immune to all of that. It also picks up
# `voxel_mni`'s grey-matter mask, which sits at the parcellation root instead of
# under a `sub-XX/` directory.
_PATTERNS = ("*_timeseries.h5", "*_dseg.nii.gz", "*_mask.nii.gz")


def parcellation_subdir(parcellation):
    """Path to one parcellation's files, relative to a timeseries repo root.

    The repo has a `timeseries/` directory of its own, so the full path from
    the superdataset is `{dataset}/timeseries/timeseries/{parcellation}/`.
    """
    return f"timeseries/{parcellation}"


def timeseries_patterns():
    """Glob patterns for every file a parcellation directory contributes."""
    return list(_PATTERNS)


def parse_labels(value, prefix=""):
    """Split a comma-separated CLI value into normalized labels.

    With `prefix` given, each label is normalized to `{prefix}{label}` and
    zero-padded to two digits, so `1`, `01` and `sub-01` all become `sub-01`.
    Returns an empty list for None or an all-blank value.
    """
    if not value:
        return []
    labels = []
    for raw in value.split(","):
        label = raw.strip()
        if not label:
            continue
        if prefix:
            label = label.removeprefix(prefix)
            if label.isdigit():
                label = label.zfill(2)
            label = f"{prefix}{label}"
        labels.append(label)
    return labels


def subject_filter(subjects):
    """Build a `match(path) -> bool` predicate restricting to `subjects`.

    Returns None when no subjects were requested, which is what
    `airoh.datalad.prefetch_pattern` expects for "no extra filtering".

    A file is kept when any component of its path is one of the requested
    `sub-XX` directories. Files that live above the subject level — such as
    `voxel_mni`'s shared grey-matter mask — have no `sub-XX` component and are
    therefore excluded by a subject restriction, which is the right call: they
    are not that subject's data.
    """
    wanted = set(subjects)
    if not wanted:
        return None

    def match(path):
        return any(part in wanted for part in path.parts)

    return match
