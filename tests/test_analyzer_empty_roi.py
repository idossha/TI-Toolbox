"""An ROI with no positive field values is one clear error, in mesh and voxel alike (2026-10-22).

What this pins
    Before: a voxel analysis of an empty ROI died inside numpy ("zero-size array to reduction
    operation maximum which has no identity"); a mesh analysis "succeeded" with
    roi_mean = gm_mean = gm_max = 0, wrote a results.csv of zeros and exited 0. Now every empty
    ROI -- a sphere outside the head or between nodes, an atlas label the volume does not
    contain, a tissue that does not overlap the region, a field that is <= 0 throughout the
    region -- raises ``ValueError`` naming the region and the space/tissue, writes nothing into
    the analysis output folder, and the runner exits 1 with that sentence. A group run names
    the subject whose ROI was empty.

Where the expectations come from
    The fixtures are authored: a surface of nodes on a 10 mm grid inside a 100 mm cube (the
    "head"), a 4x5x6 voxel grid with an identity affine, and spheres placed by hand 500 mm away
    or between nodes. Which elements a sphere contains is decided by the authored coordinates
    (Euclidean distance), not by the code under test. The wording contract is the spec's: the
    message names the region and the space or tissue, matching ``_analyze_mask_file``'s
    existing "does not overlap" sentence.

Run: .venv/bin/python -m pytest tests/test_analyzer_empty_roi.py -q -p no:cacheprovider
Real-library leg (nibabel field, runner subprocess): tests/numerical/test_analyzer_p06_real.py.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from tit.paths import get_path_manager

SID = "101"
SIM = "M1"


def _touch(path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


def _snapshot(root: Path) -> set[str]:
    """Every file and folder under *root* except the analyzer's own log folder."""
    return {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if "logs" not in p.relative_to(root).parts
    }


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A finished 2-pair TI simulation: TI mesh, central surface, GM and WM NIfTIs."""
    pm = get_path_manager(str(tmp_path))
    _touch(Path(pm.m2m(SID)) / f"{SID}.msh")
    _touch(pm.ti_mesh(SID, SIM))
    _touch(pm.ti_central_surface(SID, SIM))
    niftis = Path(pm.simulation(SID, SIM)) / "TI" / "niftis"
    _touch(niftis / f"grey_{SIM}_TI_subject_TI_max.nii.gz")
    _touch(niftis / f"white_{SIM}_TI_subject_TI_max.nii.gz")
    return tmp_path


def _surface(values: np.ndarray):
    """Nodes on a 10 mm grid filling [-50, 40]^3 (1000 nodes), unit areas."""
    axis = np.arange(-50.0, 50.0, 10.0)
    coords = np.stack(np.meshgrid(axis, axis, axis, indexing="ij"), -1).reshape(-1, 3)
    assert len(coords) == len(values)
    return SimpleNamespace(
        nodes=SimpleNamespace(node_coord=coords),
        field={"TI_max": SimpleNamespace(value=np.asarray(values, dtype=float))},
        nodes_areas=lambda: np.ones(len(coords)),
    )


def _analyzer(space: str, tissue: str = "GM"):
    from tit.analyzer.analyzer import Analyzer

    with patch("tit.analyzer.analyzer.add_file_handler"):
        return Analyzer(SID, SIM, space=space, tissue_type=tissue)


def _fake_nib_load(arrays: dict[str, np.ndarray]):
    """``nibabel.load`` returning the authored array for each file name (identity affine)."""

    def load(path):
        arr = arrays[Path(str(path)).name]
        return SimpleNamespace(
            get_fdata=lambda: arr.astype(float),
            dataobj=arr,
            affine=np.eye(4),
            shape=arr.shape,
        )

    return load


# -- mesh ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "center, radius, label",
    [
        ((500.0, 500.0, 500.0), 10.0, "outside the head"),
        # (5, 5, 5) is 8.66 mm from its nearest grid node: a 1 mm sphere holds no node.
        # (Radius 0 itself is refused before any analysis: test_analyzer_sphere_validation.)
        ((5.0, 5.0, 5.0), 1.0, "between nodes"),
    ],
)
def test_mesh_sphere_with_no_node_is_a_value_error_and_writes_nothing(
    project: Path, center, radius, label
) -> None:
    values = np.linspace(0.1, 1.0, 1000)  # positive everywhere: gm_mean is not 0
    analyzer = _analyzer("mesh")
    before = _snapshot(project)
    with patch("simnibs.read_msh", return_value=_surface(values)):
        with pytest.raises(ValueError) as err:
            analyzer.analyze_sphere(center, radius)
    message = str(err.value)
    region = analyzer._sphere_region_name([(*center, radius)])
    assert region in message, label
    assert "mesh" in message and "surface" in message
    assert "zero-size" not in message
    assert _snapshot(project) == before  # no Analyses/ folder, no results.csv of zeros


def test_mesh_roi_whose_field_is_never_positive_is_a_value_error(project: Path) -> None:
    """The sphere holds nodes, but the field is <= 0 on every one of them."""
    surface = _surface(np.full(1000, 0.5))
    coords = surface.nodes.node_coord
    inside = np.linalg.norm(coords - np.array([0.0, 0.0, 0.0]), axis=1) <= 12.0
    assert inside.sum() == 7  # the centre node and its six 10 mm neighbours
    values = surface.field["TI_max"].value
    values[inside] = np.array([0.0, -0.2, 0.0, -1.0, 0.0, -0.3, 0.0])
    analyzer = _analyzer("mesh")
    before = _snapshot(project)
    with patch("simnibs.read_msh", return_value=surface):
        with pytest.raises(ValueError, match="TI_max") as err:
            analyzer.analyze_sphere((0.0, 0.0, 0.0), 12.0)
    assert "sphere_x0.00_y0.00_z0.00_r12.0" in str(err.value)
    assert _snapshot(project) == before


def test_mesh_roi_with_positive_nodes_still_reports_whole_gm_statistics(
    project: Path,
) -> None:
    """Control: the guard does not fire for a non-empty ROI, and gm_* are the whole surface."""
    values = np.linspace(0.1, 1.0, 1000)
    analyzer = _analyzer("mesh")
    with patch("simnibs.read_msh", return_value=_surface(values)):
        result = analyzer.analyze_sphere((0.0, 0.0, 0.0), 12.0)
    assert result.n_elements == 7
    assert result.gm_max == pytest.approx(1.0)
    assert result.gm_mean == pytest.approx(0.55)  # mean of linspace(0.1, 1, 1000)


# -- voxel --------------------------------------------------------------------------------------


def _field_grid() -> np.ndarray:
    """A 4x5x6 field, positive everywhere, distinct values (1..120)."""
    return np.arange(1, 121, dtype=float).reshape(4, 5, 6)


@pytest.mark.parametrize(
    "center, radius",
    # (1.5, 1.5, 1.5) is 0.866 mm from every voxel centre around it.
    [((500.0, 500.0, 500.0), 10.0), ((1.5, 1.5, 1.5), 0.5)],
)
def test_voxel_sphere_with_no_voxel_is_a_value_error_not_a_numpy_crash(
    project: Path, center, radius
) -> None:
    analyzer = _analyzer("voxel")
    field = _field_grid()
    before = _snapshot(project)
    with patch("nibabel.load", _fake_nib_load({analyzer.field_path.name: field})):
        with pytest.raises(ValueError) as err:
            analyzer.analyze_sphere(center, radius)
    message = str(err.value)
    assert "zero-size" not in message
    assert analyzer._sphere_region_name([(*center, radius)]) in message
    assert "GM" in message and "voxel" in message
    assert _snapshot(project) == before


def test_voxel_tissue_disjoint_from_the_region_names_the_tissue(project: Path) -> None:
    """WM analysis: the white_ NIfTI is positive only at x == 0; the sphere sits at x == 3."""
    analyzer = _analyzer("voxel", tissue="WM")
    assert analyzer.field_path.name.startswith("white_")
    field = np.zeros((4, 5, 6))
    field[0] = 1.0
    with patch("nibabel.load", _fake_nib_load({analyzer.field_path.name: field})):
        with pytest.raises(ValueError) as err:
            analyzer.analyze_sphere((3.0, 2.0, 2.0), 1.0)
    message = str(err.value)
    assert "WM" in message and "sphere_x3.00_y2.00_z2.00_r1.0" in message


def test_voxel_cortical_label_absent_from_the_atlas_names_label_and_atlas(
    project: Path, tmp_path: Path, monkeypatch
) -> None:
    # scipy is mocked on the host; the island filter is not what this test is about.
    monkeypatch.setenv("TIT_ROI_KEEP_ISLANDS", "1")
    analyzer = _analyzer("voxel")
    atlas_path = _touch(tmp_path / "atlas" / "custom_atlas.nii.gz")
    labels = np.zeros((4, 5, 6), dtype=np.int16)
    labels[1:3, 1:4, 1:5] = 17
    before = _snapshot(project)
    with (
        patch(
            "nibabel.load",
            _fake_nib_load(
                {analyzer.field_path.name: _field_grid(), atlas_path.name: labels}
            ),
        ),
        patch.dict(sys.modules, {"nibabel.processing": MagicMock()}),
    ):
        with pytest.raises(ValueError) as err:
            analyzer.analyze_cortex(str(atlas_path), "9999")
    message = str(err.value)
    assert "9999" in message and "custom_atlas.nii.gz" in message
    assert "zero-size" not in message
    assert _snapshot(project) == before


def test_subcortical_label_absent_from_the_atlas_names_label_and_atlas(
    project: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TIT_ROI_KEEP_ISLANDS", "1")
    analyzer = _analyzer("voxel")
    atlas_path = _touch(tmp_path / "atlas" / "labels.nii.gz")
    labels = np.zeros((4, 5, 6), dtype=np.int16)
    labels[1:3, 1:4, 1:5] = 10
    before = _snapshot(project)
    with patch("nibabel.load", _fake_nib_load({atlas_path.name: labels})):
        with pytest.raises(ValueError) as err:
            analyzer.analyze_subcortical(str(atlas_path), ["10", "4242"])
    message = str(err.value)
    assert "4242" in message and "labels.nii.gz" in message
    assert _snapshot(project) == before


def test_voxel_roi_whose_field_is_never_positive_is_a_value_error(
    project: Path,
) -> None:
    analyzer = _analyzer("voxel")
    field = _field_grid()
    field[1:3, 1:3, 1:3] = -1.0  # the sphere below covers only these 8 voxels
    with patch("nibabel.load", _fake_nib_load({analyzer.field_path.name: field})):
        with pytest.raises(ValueError, match="TI_max"):
            analyzer.analyze_sphere((1.5, 1.5, 1.5), 0.9)


# -- group --------------------------------------------------------------------------------------


def test_group_analysis_names_the_subject_whose_roi_is_empty(project: Path) -> None:
    from tit.analyzer import group
    from tit.analyzer.analyzer import Analyzer

    class _Analyzer(Analyzer):  # keeps the real sphere check the group runs up front
        def __init__(self, sid, *args, **kwargs):
            self.sid = sid

        def analyze_sphere(self, **kwargs):
            if self.sid == "102":
                raise ValueError(
                    "sphere_x500.00_y0.00_z0.00_r5.0 does not overlap positive TI_max "
                    "values on the gray-matter surface (mesh space)"
                )
            return SimpleNamespace(
                roi_mean=1.0,
                roi_max=1.0,
                roi_min=1.0,
                roi_focality=1.0,
                gm_mean=1.0,
                gm_max=1.0,
                normal_mean=None,
                normal_max=None,
                normal_focality=None,
            )

    with (
        patch.object(group, "Analyzer", _Analyzer),
        patch.object(group, "add_file_handler"),
    ):
        with pytest.raises(ValueError) as err:
            group.run_group_analysis(
                ["101", "102"],
                SIM,
                analysis_type="spherical",
                center=(500.0, 0.0, 0.0),
                radius=5.0,
                output_dir=str(project / "group_out"),
            )
    message = str(err.value)
    assert "102" in message and "101" not in message.replace(SIM, "")
    assert "does not overlap" in message


# -- runner -------------------------------------------------------------------------------------


def test_runner_exits_1_with_the_sentence_for_an_empty_mesh_roi(
    project: Path, tmp_path: Path, monkeypatch, capsys
) -> None:
    from tit.analyzer import __main__ as runner

    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "project_dir": str(project),
                "mode": "single",
                "subject_id": SID,
                "simulation": SIM,
                "space": "mesh",
                "analysis_type": "spherical",
                "center": [500.0, 500.0, 500.0],
                "radius": 10.0,
                "visualize": True,
            }
        )
    )
    monkeypatch.setattr(sys, "argv", ["tit.analyzer", str(config)])
    logger = logging.getLogger("tit.analyzer")
    handlers = list(logger.handlers)
    sim_dir = Path(get_path_manager(str(project)).simulation(SID, SIM))
    before = _snapshot(sim_dir)  # the runner's own log folder is created outside it
    try:
        with (
            patch("simnibs.read_msh", return_value=_surface(np.ones(1000))),
            patch("tit.analyzer.analyzer.add_file_handler"),
        ):
            with pytest.raises(SystemExit) as exc:
                runner.main()
    finally:
        for handler in logger.handlers[:]:
            if handler not in handlers:
                logger.removeHandler(handler)
    assert exc.value.code == 1
    out = capsys.readouterr()
    text = out.out + out.err
    assert "Analysis failed" in text
    assert "sphere_x500.00_y500.00_z500.00_r10.0" in text
    assert _snapshot(sim_dir) == before
