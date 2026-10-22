"""Every region name the toolbox offers resolves to its own label in a voxel analysis (2026-10-22).

What this pins
    1. Shipped MNI atlases (``resources/atlas/manifest.json``): for every label present in each
       volume, the name its colour table gives resolves through
       :meth:`Analyzer._find_voxel_region_id` to that label -- including names that are
       substrings of other names (Glasser ``L-2`` inside ``L-23d``, ``L-a24`` inside
       ``L-a24pr``) and Harvard-Oxford names with commas.
    2. A name several present labels contain (a bare ``insula`` in a DKT volume holding
       ``ctx-lh-insula`` and ``ctx-rh-insula``) is refused with both candidates named, not
       resolved to the lowest id -- that measured the left insula only, while the same name in
       mesh space measures both. ``lh.insula`` still resolves to one label.
    3. A label number absent from the volume is refused with the sentence the runner prints
       ("has no voxels"), through the same island filter and check the runner applies.
    4. Dataset 000 (``TIT_DATASET_000``): on sub-ernie's real ``aparc.DKTatlas+aseg.mgz``
       (copied to tmp_path), every DK40 region ``lh.<name>`` / ``rh.<name>`` resolves to the id
       FreeSurfer's colour table gives ``ctx-lh-<name>`` / ``ctx-rh-<name>``; the DK regions
       the volume lacks are exactly :data:`Analyzer.DKT_VOLUME_LACKS`, and preflight refuses
       each of them at submit while accepting the rest.

Where the numbers come from
    The colour tables themselves, read by the minimal parser below (id = first token, name =
    second), and the label ids present in each volume (``numpy.unique`` of the nibabel array).
    The DK region list is FreeSurfer's own ``ctx-lh-*`` rows 1001-1035 in
    ``resources/atlas/FreeSurferColorLUT.txt``.

Run (host with real numpy/scipy/nibabel, or the image)::

    .venv/bin/python -m pytest tests/numerical/test_region_resolution_matrix.py -q -p no:cacheprovider
    TIT_DATASET_000=/Users/idohaber/datasets/000 ... for case 4.
"""

from __future__ import annotations

import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

REPO = Path(__file__).resolve().parents[2]
ATLAS_DIR = REPO / "resources" / "atlas"
DATASET = os.environ.get("TIT_DATASET_000", "")
ERNIE_DKT = (
    Path(
        DATASET,
        "derivatives",
        "freesurfer",
        "sub-ernie",
        "mri",
        "aparc.DKTatlas+aseg.mgz",
    )
    if DATASET
    else None
)


def _lut_table(path: Path) -> dict[int, str]:
    """``{id: name}`` from a colour table: first token the id, second the name."""
    out = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts or line.lstrip().startswith("#") or not parts[0].isdigit():
            continue
        out[int(parts[0])] = parts[1]
    return out


def _present_ids(path: Path) -> list[int]:
    import nibabel as nib

    data = np.asarray(nib.load(str(path)).dataobj)
    return [int(v) for v in np.unique(data.astype(np.int64)) if v != 0]


@pytest.fixture
def cached_segstats(monkeypatch):
    """The runner's own LUT and segstats readers, read once per atlas (they are pure)."""
    import tit.analyzer.analyzer as analyzer_mod

    real_lut, real_stats = (
        analyzer_mod.resolve_lut_for_atlas,
        analyzer_mod.compute_segstats,
    )
    lut = lru_cache(maxsize=None)(real_lut)
    stats = lru_cache(maxsize=None)(lambda path: real_stats(path, lut(path)))
    monkeypatch.setattr(analyzer_mod, "resolve_lut_for_atlas", lut)
    monkeypatch.setattr(
        analyzer_mod, "compute_segstats", lambda path, _lut: stats(path)
    )


def _manifest_atlases() -> list[dict]:
    return json.loads((ATLAS_DIR / "manifest.json").read_text())["atlases"]


@pytest.mark.parametrize("entry", _manifest_atlases(), ids=lambda e: e["id"])
def test_every_shipped_mni_region_name_resolves_to_its_own_label(
    entry, cached_segstats
) -> None:
    from tit.analyzer.analyzer import Analyzer

    volume = ATLAS_DIR / entry["file"]
    table = _lut_table(ATLAS_DIR / entry["labels"])
    present = _present_ids(volume)
    assert len(present) == entry["regions"], "manifest region count = labels in volume"
    assert set(present) <= set(table), "every label in the volume has a name"
    wrong = {}
    for rid in present:
        got = Analyzer._find_voxel_region_id(None, volume, table[rid])
        if got != rid:
            wrong[table[rid]] = (rid, got)
    assert wrong == {}


def test_the_matrix_includes_names_shadowed_by_longer_names() -> None:
    """The precedence case exists in the shipped tables: Glasser's L-2 is inside L-23d."""
    glasser = [
        n.lower() for n in _lut_table(ATLAS_DIR / "MNI_Glasser_HCP_v1.0.txt").values()
    ]
    shadowed = [a for a in glasser if any(a != b and a in b for b in glasser)]
    assert "l-2" in shadowed and "l-a24" in shadowed
    ho = _lut_table(
        ATLAS_DIR / "HarvardOxford-cortl-maxprob-thr25-1mm_LUT.txt"
    ).values()
    assert any("," in name for name in ho)


def _two_hemisphere_volume(tmp_path: Path) -> Path:
    """A label volume with ctx-lh-insula (1035) and ctx-rh-insula (2035) and its own LUT."""
    import nibabel as nib

    data = np.zeros((6, 6, 6), dtype=np.int32)
    data[1:3, 1:3, 1:3] = 1035
    data[3:5, 3:5, 3:5] = 2035
    path = tmp_path / "insula.nii.gz"
    nib.save(nib.Nifti1Image(data, np.eye(4)), str(path))
    (tmp_path / "insula_LUT.txt").write_text(
        "0 Unknown 0 0 0 0\n1035 ctx-lh-insula 1 2 3 0\n2035 ctx-rh-insula 3 2 1 0\n"
    )
    return path


def test_a_bare_name_in_both_hemispheres_is_refused_not_the_left_one(tmp_path) -> None:
    from tit.analyzer.analyzer import Analyzer

    volume = _two_hemisphere_volume(tmp_path)
    with pytest.raises(ValueError, match="matches 2 labels") as err:
        Analyzer._find_voxel_region_id(None, volume, "insula")
    assert "ctx-lh-insula (1035)" in str(err.value)
    assert "ctx-rh-insula (2035)" in str(err.value)
    assert Analyzer._find_voxel_region_id(None, volume, "lh.insula") == 1035
    assert Analyzer._find_voxel_region_id(None, volume, "rh.insula") == 2035


def test_a_label_number_absent_from_the_volume_is_refused(tmp_path) -> None:
    import nibabel as nib

    from tit.analyzer.analyzer import Analyzer
    from tit.atlas.islands import keep_main_components

    volume = _two_hemisphere_volume(tmp_path)
    arr = np.asarray(nib.load(str(volume)).dataobj)
    rid = Analyzer._find_voxel_region_id(arr, volume, "999")
    assert rid == 999 and 999 not in _present_ids(volume)
    one, _, _ = keep_main_components(arr == rid, what="999")
    with pytest.raises(ValueError, match=r"Region '999' \(label 999\) has no voxels"):
        Analyzer._require_label_voxels(one, "999", rid, volume)


def _dk_names() -> list[str]:
    table = _lut_table(ATLAS_DIR / "FreeSurferColorLUT.txt")
    names = [
        table[i].removeprefix("ctx-lh-")
        for i in range(1001, 1036)
        if i in table and table[i].startswith("ctx-lh-")
    ]
    assert len(names) >= 34, "has DK regions to check"
    return names


@pytest.mark.skipif(
    not (ERNIE_DKT and ERNIE_DKT.is_file()),
    reason="skipping: TIT_DATASET_000 unset or without freesurfer/sub-ernie's DKT volume",
)
def test_dk40_names_resolve_in_the_real_dkt_volume_and_missing_ones_are_refused_at_submit(
    tmp_path, cached_segstats
) -> None:
    from tit.analyzer.analyzer import Analyzer
    from tit.jobs import preflight
    from tit.paths import PathManager

    before = (ERNIE_DKT.stat().st_size, ERNIE_DKT.stat().st_mtime_ns)
    project = tmp_path / "project"
    mri = project / "derivatives" / "freesurfer" / "sub-ernie" / "mri"
    mri.mkdir(parents=True)
    volume = mri / ERNIE_DKT.name
    shutil.copyfile(ERNIE_DKT, volume)

    table = _lut_table(ATLAS_DIR / "FreeSurferColorLUT.txt")
    ids = {name: rid for rid, name in table.items()}
    present = set(_present_ids(volume))
    absent = set()
    for name in _dk_names():
        for hemi in ("lh", "rh"):
            rid = ids[f"ctx-{hemi}-{name}"]
            if rid in present:
                assert (
                    Analyzer._find_voxel_region_id(None, volume, f"{hemi}.{name}")
                    == rid
                )
            else:
                absent.add(name)
                with pytest.raises(ValueError, match="mesh space"):
                    Analyzer._find_voxel_region_id(None, volume, f"{hemi}.{name}")
    if "unknown" in absent:
        absent.discard("unknown")
    assert absent == set(Analyzer.DKT_VOLUME_LACKS)

    pm = PathManager(str(project))
    regions = [f"lh.{n}" for n in sorted(absent)] + ["lh.insula", "rh.precentral"]
    refused = preflight._analyzer_atlas(
        pm, "ernie", "voxel", {"atlas": "DK40", "region": regions}
    )
    assert sorted(m.what.split("'")[1] for m in refused) == sorted(
        f"lh.{n}" for n in absent
    )
    assert all(m.expected_path == str(volume) for m in refused)
    assert (ERNIE_DKT.stat().st_size, ERNIE_DKT.stat().st_mtime_ns) == before
