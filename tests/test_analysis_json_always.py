"""Every finished analysis is listed by the catalog, with metadata from its own run (2026-10-22).

What this pins
    ``tit.catalog`` lists an analysis only when its folder holds ``results.csv`` *and*
    ``analysis.json`` -- "the pair :mod:`tit.analyzer` writes wherever it was told to write"
    (``catalog._find_analysis_dirs``). Before this fix the analyzer wrote ``analysis.json`` only
    inside ``_visualize_mesh`` / ``_visualize_voxel``, so with ``visualize=False`` -- the default of
    ``Analyzer.analyze_*`` and of ``run_group_analysis`` -- the run was invisible to the app, and a
    re-run of the same ROI with another field paired the new ``results.csv`` with the stale
    ``analysis.json`` of the earlier run (the Results page then showed the old field's name next to
    the new field's numbers).

Where the expectations come from
    The request: the field the second Analyzer was built with (``TI_avg``), the sphere passed to
    ``analyze_sphere``, the space the Analyzer was built in. The directory compared against is
    found by walking the project on disk for ``results.csv``, not from the catalog. The fixtures
    are authored: a 4x5x6 voxel grid with an identity affine (``nibabel.load`` patched, as in
    ``tests/test_analyzer_empty_roi.py``) and a 1000-node surface on a 10 mm grid.

Run: .venv/bin/python -m pytest tests/test_analysis_json_always.py -q -p no:cacheprovider
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tit import catalog
from tit.paths import get_path_manager

SID = "101"
SIM = "M1"


def _touch(path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A finished TI simulation with a TI mesh, its central surface and two GM field NIfTIs."""
    pm = get_path_manager(str(tmp_path))
    _touch(Path(pm.m2m(SID)) / f"{SID}.msh")
    _touch(pm.ti_mesh(SID, SIM))
    _touch(pm.ti_central_surface(SID, SIM))
    niftis = Path(pm.simulation(SID, SIM)) / "TI" / "niftis"
    _touch(niftis / f"grey_{SIM}_TI_subject_TI_max.nii.gz")
    _touch(niftis / f"grey_{SIM}_TI_subject_TI_avg.nii.gz")
    return tmp_path


def _field_grid() -> np.ndarray:
    """Positive everywhere, so every sphere inside the grid has statistics."""
    return np.linspace(0.1, 1.0, 4 * 5 * 6).reshape(4, 5, 6)


def _fake_nib_load(arrays: dict[str, np.ndarray]):
    def load(path):
        arr = arrays[Path(str(path)).name]
        return SimpleNamespace(
            get_fdata=lambda: arr.astype(float),
            dataobj=arr,
            affine=np.eye(4),
            shape=arr.shape,
        )

    return load


def _surface(values: np.ndarray):
    axis = np.arange(-50.0, 50.0, 10.0)
    coords = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1).reshape(-1, 3)
    return SimpleNamespace(
        nodes=SimpleNamespace(node_coord=coords),
        field={"TI_max": SimpleNamespace(value=np.asarray(values, dtype=float))},
        nodes_areas=lambda: np.ones(len(coords)),
    )


def _analyzer(space: str, field: str | None = None):
    from tit.analyzer.analyzer import Analyzer

    with patch("tit.analyzer.analyzer.add_file_handler"):
        return Analyzer(SID, SIM, space=space, field=field)


def _result_dirs(project: Path) -> list[Path]:
    """Every folder holding a results.csv, read off disk (not from the catalog)."""
    return sorted(p.parent for p in project.rglob("results.csv"))


def _csv_metric(path: Path, metric: str) -> str:
    with open(path, newline="") as fh:
        return {row[0]: row[1] for row in csv.reader(fh)}[metric]


def _voxel_sphere(
    field: str | None, center=(2.0, 2.0, 2.0), radius=1.5, visualize: bool = False
):
    """``visualize`` defaults to False, as ``Analyzer.analyze_sphere`` does."""
    analyzer = _analyzer("voxel", field)
    arrays = {analyzer.field_path.name: _field_grid()}
    with (
        patch("nibabel.load", _fake_nib_load(arrays)),
        # matplotlib and nibabel are mocked on the host: the pictures are not under test.
        patch("tit.analyzer.analyzer.save_histogram"),
        patch("tit.analyzer.analyzer.save_nifti_roi_overlay"),
        patch("tit.analyzer.scene.write_voxel_scene"),
    ):
        analyzer.analyze_sphere(center, radius, visualize=visualize)
    return analyzer


def test_a_voxel_analysis_without_visualize_is_listed_with_its_own_metadata(
    project: Path,
) -> None:
    analyzer = _voxel_sphere(None)
    pm = get_path_manager(str(project))

    dirs = _result_dirs(project)
    assert len(dirs) == 1, dirs
    run_dir = dirs[0]
    meta = json.loads((run_dir / "analysis.json").read_text())
    assert meta["field_name"] == analyzer.field_name == "TI_max"
    assert meta["space"] == "voxel"
    assert meta["analysis_type"] == "spherical"
    assert meta["coordinate_space"] == "subject"
    assert meta["center"] == [2.0, 2.0, 2.0] and meta["radius"] == 1.5

    listed = catalog.analyses(pm, SID, SIM)
    assert [Path(a["csv"]).parent for a in listed] == [run_dir]
    assert listed[0]["field"] == "TI_max"
    assert listed[0]["name"] == run_dir.name


def test_a_rerun_with_another_field_lists_the_new_field_not_the_stale_one(
    project: Path,
) -> None:
    # The earlier run visualized, so its folder already holds an analysis.json (TI_max).
    _voxel_sphere(None, visualize=True)
    pm = get_path_manager(str(project))
    first = catalog.analyses(pm, SID, SIM)
    assert [a["field"] for a in first] == ["TI_max"]

    _voxel_sphere("TI_avg")  # the same sphere, another field

    # The field is part of the folder's identity (2026-10-22): the TI_avg run is a second
    # folder, and neither folder pairs one run's numbers with the other's metadata.
    dirs = _result_dirs(project)
    assert len(dirs) == 2, dirs
    listed = catalog.analyses(pm, SID, SIM)
    assert sorted(a["field"] for a in listed) == ["TI_avg", "TI_max"]
    for folder in dirs:
        meta = json.loads((folder / "analysis.json").read_text())
        assert _csv_metric(folder / "results.csv", "field_name") == meta["field_name"]
    by_field = {a["field"]: Path(a["csv"]).parent for a in listed}
    assert by_field["TI_avg"].name == f"{by_field['TI_max'].name}_TI_avg"


def test_a_mesh_analysis_without_visualize_is_listed(project: Path) -> None:
    pm = get_path_manager(str(project))
    analyzer = _analyzer("mesh")
    with patch("simnibs.read_msh", return_value=_surface(np.linspace(0.1, 1.0, 1000))):
        analyzer.analyze_sphere((0.0, 0.0, 0.0), 12.0)

    dirs = _result_dirs(project)
    assert len(dirs) == 1, dirs
    meta = json.loads((dirs[0] / "analysis.json").read_text())
    assert meta["space"] == "mesh" and meta["field_name"] == "TI_max"
    assert meta["radius"] == 12.0 and meta["center"] == [0.0, 0.0, 0.0]
    listed = catalog.analyses(pm, SID, SIM)
    assert [Path(a["csv"]).parent for a in listed] == dirs
    assert listed[0]["field"] == "TI_max"


def test_a_cortical_analysis_records_its_atlas_and_regions(project: Path) -> None:
    """``roi`` in the catalog is built from analysis.json's ``regions`` (or ``atlas``)."""
    from tit.analyzer.analyzer import Analyzer

    analyzer = _analyzer("mesh")
    surface = _surface(np.linspace(0.1, 1.0, 1000))
    roi_mask = np.zeros(1000, dtype=bool)
    roi_mask[:10] = True
    analyzer._analyze_mesh_roi(
        surface,
        surface.field["TI_max"].value,
        np.ones(1000),
        roi_mask,
        region_name="lh.insula",
        analysis_type="cortical",
        atlas="DK40",
        region_labels=["lh.insula"],
    )
    assert isinstance(analyzer, Analyzer)
    dirs = _result_dirs(project)
    assert len(dirs) == 1, dirs
    meta = json.loads((dirs[0] / "analysis.json").read_text())
    assert meta["atlas"] == "DK40" and meta["regions"] == ["lh.insula"]
    assert meta["analysis_type"] == "cortical" and meta["center"] is None
    listed = catalog.analyses(get_path_manager(str(project)), SID, SIM)
    assert [a["roi"] for a in listed] == ["lh.insula"]


def test_group_analysis_with_the_default_visualize_lists_every_subject_run(
    project: Path,
) -> None:
    from tit.analyzer.group import run_group_analysis

    pm = get_path_manager(str(project))
    field_name = f"grey_{SIM}_TI_subject_TI_max.nii.gz"
    with (
        patch("nibabel.load", _fake_nib_load({field_name: _field_grid()})),
        patch("tit.analyzer.analyzer.add_file_handler"),
        patch("tit.analyzer.group.add_file_handler"),
        # matplotlib is mocked on the host; the bar chart is not what this test is about.
        patch("tit.analyzer.group._generate_comparison_plot", return_value=None),
    ):
        run_group_analysis(
            [SID],
            SIM,
            space="voxel",
            analysis_type="spherical",
            center=(2.0, 2.0, 2.0),
            radius=1.5,
            output_dir=str(project / "group_out"),
        )

    subject_dirs = [d for d in _result_dirs(project) if "group_out" not in d.parts]
    assert len(subject_dirs) == 1, subject_dirs
    listed = catalog.analyses(pm, SID, SIM)
    assert [Path(a["csv"]).parent for a in listed] == subject_dirs
    assert listed[0]["field"] == "TI_max"
