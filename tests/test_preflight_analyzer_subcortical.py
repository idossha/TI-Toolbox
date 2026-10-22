"""Preflight refuses subcortical analyzer targets the runner cannot run (2026-10-22).

What this pins
    ``_check_analyzer`` checked the atlas for cortical targets only. Dataset 000's
    ``sub-ernie`` m2m has no ``segmentation/`` folder, so charm's ``labeling.nii.gz`` -- the
    default subcortical atlas -- is absent; a subcortical job was accepted and died in the
    runner with ``FileNotFoundError``. Now: a missing subject-space volume atlas is one
    ``MissingInput`` at the path the runner would read; an MNI atlas id the manifest does not
    ship (or ships no more) is refused; a region name no label of the atlas's lookup table
    carries is refused before the job starts.

Where the expectations come from
    The runner itself, not a retyped path list: every "missing" case is closed by placing a
    file exactly at the reported ``expected_path`` and checking that
    ``Analyzer._resolve_voxel_atlas`` (the runner's resolver) then returns that very file and
    the preflight goes quiet. Region names come from the shipped lookup tables
    (``resources/atlas/FreeSurferColorLUT.txt`` row 9 "Left-Thalamus",
    ``HarvardOxford-sub-maxprob-thr25-1mm_LUT.txt`` row 4 "Left-Thalamus") and from
    ``resources/atlas/manifest.json`` (``not_shipped``: "MorelMNI152_labeling_1mm.nii.gz").

Run: .venv/bin/python -m pytest tests/test_preflight_analyzer_subcortical.py -q -p no:cacheprovider
"""

from __future__ import annotations

from pathlib import Path
import pytest

from tit.jobs.preflight import preflight
from tit.paths import get_path_manager

SID = "ernie"
SIM = "AF3_PO10_and_AF4_Oz"


def _touch(path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """sub-ernie as Dataset 000 has it: a head model with no segmentation/ folder."""
    pm = get_path_manager(str(tmp_path))
    _touch(Path(pm.m2m(SID)) / f"{SID}.msh")
    _touch(pm.ti_mesh(SID, SIM))
    _touch(pm.ti_central_surface(SID, SIM))
    _touch(
        Path(pm.simulation(SID, SIM)) / "TI" / "niftis" / f"grey_{SIM}_TI_max.nii.gz"
    )
    assert not Path(pm.segmentation(SID)).exists()
    return tmp_path


def _config(space="voxel", **overrides) -> dict:
    return {
        "mode": "single",
        "subject_id": SID,
        "simulation": SIM,
        "space": space,
        "analysis_type": "subcortical",
        "atlas": "labeling.nii.gz",
        "region": ["Left-Thalamus"],
        "coordinate_space": "subject",
        **overrides,
    }


def _runner_resolves(project: Path, atlas: str) -> Path:
    from tit.analyzer.analyzer import Analyzer

    analyzer = object.__new__(Analyzer)
    analyzer._pm = get_path_manager(str(project))
    analyzer.subject_id = SID
    return analyzer._resolve_voxel_atlas(atlas)


@pytest.mark.parametrize("space", ["voxel", "mesh"])
def test_missing_charm_labeling_is_one_missing_input_at_the_runners_path(
    project: Path, space: str
) -> None:
    found = preflight("analyzer", _config(space), str(project))
    assert len(found) == 1
    item = found[0]
    pm = get_path_manager()
    assert item.expected_path == str(
        Path(pm.m2m(SID)) / "segmentation" / "labeling.nii.gz"
    )
    assert "charm" in item.how_to_fix and SID in item.how_to_fix
    # Before the fix the runner fails exactly here.
    with pytest.raises(FileNotFoundError):
        _runner_resolves(project, "labeling.nii.gz")
    _touch(item.expected_path)
    assert _runner_resolves(project, "labeling.nii.gz") == Path(item.expected_path)


def test_freesurfer_volume_reported_where_the_runner_searches_first(
    project: Path,
) -> None:
    atlas = "aparc.DKTatlas+aseg.mgz"
    found = preflight(
        "analyzer", _config(atlas=atlas, region=["Left-Thalamus"]), str(project)
    )
    assert len(found) == 1
    expected = Path(found[0].expected_path)
    assert expected.name == atlas and "FastSurfer" in found[0].how_to_fix
    # Put the file there, and only there: the runner reads it and the preflight is satisfied.
    _touch(expected)
    assert _runner_resolves(project, atlas) == expected
    assert preflight("analyzer", _config(atlas=atlas), str(project)) == []


def test_region_absent_from_the_lookup_table_is_refused(project: Path) -> None:
    atlas = "aparc.DKTatlas+aseg.mgz"
    pm = get_path_manager(str(project))
    _touch(Path(pm.fastsurfer_mri(SID)) / atlas)
    regions = ["Left-Thalamus", "NoSuchStructure", "17", "lh.insula"]
    found = preflight("analyzer", _config(atlas=atlas, region=regions), str(project))
    # "17" is a label number (only the volume can say), "lh.insula" is ctx-lh-insula.
    assert [m.what for m in found] == [f"region 'NoSuchStructure' in atlas {atlas!r}"]
    assert found[0].expected_path == str(Path(pm.fastsurfer_mri(SID)) / atlas)


def test_mni_atlas_not_in_the_manifest_is_refused(project: Path) -> None:
    found = preflight(
        "analyzer",
        _config(coordinate_space="mni", atlas="NotAnAtlas_MNI.nii.gz"),
        str(project),
    )
    assert [m.expected_path for m in found] == ["NotAnAtlas_MNI.nii.gz"]
    assert "manifest.json" in found[0].how_to_fix


def test_mni_atlas_the_manifest_no_longer_ships_is_refused(project: Path) -> None:
    found = preflight(
        "analyzer",
        _config(coordinate_space="mni", atlas="MorelMNI152_labeling_1mm.nii.gz"),
        str(project),
    )
    assert len(found) == 1 and "no longer shipped" in found[0].how_to_fix


def test_shipped_mni_atlas_checks_region_names_against_its_table(
    project: Path,
) -> None:
    atlas = "HarvardOxford-sub-maxprob-thr25-1mm.nii.gz"
    ok = _config(coordinate_space="mni", atlas=atlas, region=["Left-Thalamus"])
    assert preflight("analyzer", ok, str(project)) == []
    bad = _config(coordinate_space="mni", atlas=atlas, region=["Left-Thalamus", "Pons"])
    assert [m.what for m in preflight("analyzer", bad, str(project))] == [
        f"region 'Pons' in atlas {atlas!r}"
    ]


def test_group_mni_atlas_is_reported_once_not_per_subject(project: Path) -> None:
    pm = get_path_manager(str(project))
    _touch(Path(pm.m2m("101")) / "101.msh")
    _touch(pm.ti_mesh("101", SIM))
    _touch(pm.ti_central_surface("101", SIM))
    _touch(
        Path(pm.simulation("101", SIM)) / "TI" / "niftis" / f"grey_{SIM}_TI_max.nii.gz"
    )
    cfg = _config(
        mode="group",
        subject_id=None,
        subject_ids=[SID, "101"],
        coordinate_space="mni",
        atlas="NotAnAtlas_MNI.nii.gz",
    )
    assert len(preflight("analyzer", cfg, str(project))) == 1
