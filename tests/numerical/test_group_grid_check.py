"""Two groups compared voxel by voxel must be on one grid, and the refusal names the subject.

What this pins (package c1_5, 2026-10-22): the permutation group comparison
(``tit.stats.permutation.run_group_comparison``) and the NIfTI group loader behind the
NIfTI-average runner (``tit.stats.nifti.load_grouped_subjects_ti_toolbox``) checked the voxel
grid within each group only. Group 2 on a grid of the same shape 2 mm away was stacked beside
group 1, and the t-map / difference map compared voxels that are not the same points, saved
with group 1's affine; a group on another shape failed on a numpy broadcast error naming no
one. Now every subject of a later group is checked against the first group's reference grid
as it loads: the error names the first subject on another grid, its file, both affines and
the reference group, and the comparison writes no map.

Where the numbers come from: the affines are written here by hand (2 mm isotropic, an
origin; group 2 moved +2 mm along y), so the offset the error must report, ``+0.000,
+2.000, +0.000 mm``, is that hand translation, and the shapes are the arrays written here.
Files are real NIfTIs written with nibabel into the documented simulation layout
(``derivatives/SimNIBS/sub-<id>/Simulations/<sim>/TI/niftis``), not built through
``PathManager``.

Needs only real numpy/scipy/nibabel (``host_numerical``): the refusal happens while loading,
before any plot.

Reproduce:
  host:      ``.venv/bin/python -m pytest tests/numerical/test_group_grid_check.py -q -m host_numerical``
  container: ``simnibs_python -m pytest tests/numerical/test_group_grid_check.py -q``
Deliberately elsewhere: the grid checker itself (``test_sci02_grid_consistency.py``), the
NIfTI-average runner end to end (``test_nifti_average_runner.py``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

SIM = "M1"
PATTERN = "grey_{simulation_name}_TI_MNI_MNI_TI_max.nii.gz"
SHAPE = (6, 7, 8)
AFFINE = np.array(
    [
        [2.0, 0.0, 0.0, -90.0],
        [0.0, 2.0, 0.0, -126.0],
        [0.0, 0.0, 2.0, -72.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)
SHIFTED = AFFINE.copy()
SHIFTED[1, 3] += 2.0  # 2 mm along y: same shape, not the same points
#: The offset ``_check_same_grid`` prints for SHIFTED vs AFFINE, from the hand translation.
SHIFT_TEXT = "origin (offset +0.000, +2.000, +0.000 mm)"


def _write(project: Path, sid: str, value: float, affine=AFFINE, shape=SHAPE) -> Path:
    import nibabel as nib

    folder = (
        project / "derivatives" / "SimNIBS" / f"sub-{sid}" / "Simulations" / SIM / "TI"
    )
    (folder / "niftis").mkdir(parents=True, exist_ok=True)
    path = folder / "niftis" / PATTERN.format(simulation_name=SIM)
    nib.save(nib.Nifti1Image(np.full(shape, value, np.float32), affine), str(path))
    return path


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    from tit.paths import get_path_manager

    root = tmp_path / "proj"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    get_path_manager(str(root))
    return root


def _comparison(analysis_name: str):
    from tit.stats.config import GroupComparisonConfig

    rows = [("r1", 1), ("r2", 1), ("n1", 0), ("n2", 0)]
    return GroupComparisonConfig(
        analysis_name=analysis_name,
        subjects=[
            GroupComparisonConfig.Subject(subject_id=s, simulation_name=SIM, response=r)
            for s, r in rows
        ],
        n_permutations=20,
        n_jobs=1,
        nifti_file_pattern=PATTERN,
    )


def _maps_written(project: Path) -> list[Path]:
    return sorted(project.glob("derivatives/ti-toolbox/**/*.nii*"))


@pytest.mark.parametrize(
    ("shifted", "named"),
    [(("n1", "n2"), "n1"), (("n1",), "n1"), (("n2",), "n2")],
    ids=["all-of-group-2", "first-of-group-2", "second-of-group-2"],
)
def test_group_comparison_refuses_group_2_on_a_shifted_grid(
    project: Path, shifted: tuple[str, ...], named: str
) -> None:
    """``all-of-group-2`` is the silent case: each group is on one grid, the two are not."""
    from tit.stats.permutation import run_group_comparison

    for i, sid in enumerate(("r1", "r2", "n1", "n2")):
        _write(project, sid, 1.0 + i, SHIFTED if sid in shifted else AFFINE)
    files_before = sorted(str(p) for p in project.rglob("*.nii*"))

    with pytest.raises(ValueError) as exc:
        run_group_comparison(_comparison("shifted"))
    message = str(exc.value)
    assert message.startswith(f"Subject {named} is on a different voxel grid")
    assert SHIFT_TEXT in message
    assert f"sub-{named}/Simulations/{SIM}" in message  # its file
    assert "Responders (subject r1)" in message  # the reference grid's group
    assert _maps_written(project) == []
    assert sorted(str(p) for p in project.rglob("*.nii*")) == files_before


def test_group_comparison_refuses_group_2_of_another_shape(project: Path) -> None:
    from tit.stats.permutation import run_group_comparison

    for i, sid in enumerate(("r1", "r2", "n1", "n2")):
        shape = (7, 7, 8) if sid.startswith("n") else SHAPE
        _write(project, sid, 1.0 + i, shape=shape)

    with pytest.raises(ValueError) as exc:
        run_group_comparison(_comparison("other_shape"))
    message = str(exc.value)
    assert message.startswith(
        f"Subject n1 has shape (7, 7, 8), but the group reference has shape {SHAPE}"
    )
    assert _maps_written(project) == []


@pytest.mark.parametrize(
    ("affine", "shape"),
    [(SHIFTED, SHAPE), (AFFINE, (6, 7, 9))],
    ids=["shifted-affine", "other-shape"],
)
def test_grouped_loader_refuses_a_later_group_on_another_grid(
    project: Path, affine, shape
) -> None:
    from tit.stats.nifti import load_grouped_subjects_ti_toolbox

    _write(project, "a1", 1.0)
    _write(project, "a2", 2.0)
    _write(project, "b1", 3.0, affine, shape)
    configs = [
        {"subject_id": "a1", "simulation_name": SIM, "group": "A"},
        {"subject_id": "a2", "simulation_name": SIM, "group": "A"},
        {"subject_id": "b1", "simulation_name": SIM, "group": "B"},
    ]
    with pytest.raises(ValueError, match="^Subject b1 ") as exc:
        load_grouped_subjects_ti_toolbox(configs, nifti_file_pattern=PATTERN)
    assert "group 'A' (subject a1)" in str(exc.value)


def test_grouped_loader_stacks_groups_on_one_grid(project: Path) -> None:
    """The control: on one grid (to float noise) both groups load, in order, on AFFINE."""
    from tit.stats.nifti import load_grouped_subjects_ti_toolbox

    jitter = AFFINE.copy()
    jitter[:3, 3] += 1e-6  # a round-trip's float noise is the same grid
    _write(project, "a1", 1.0)
    _write(project, "b1", 3.0, jitter)
    _write(project, "b2", 5.0)
    groups, template, ids = load_grouped_subjects_ti_toolbox(
        [
            {"subject_id": "a1", "simulation_name": SIM, "group": "A"},
            {"subject_id": "b1", "simulation_name": SIM, "group": "B"},
            {"subject_id": "b2", "simulation_name": SIM, "group": "B"},
        ],
        nifti_file_pattern=PATTERN,
    )
    assert ids == {"A": ["a1"], "B": ["b1", "b2"]}
    assert groups["B"].shape == SHAPE + (2,)
    assert float(groups["B"][..., 1].mean()) == 5.0
    assert np.allclose(template.affine, AFFINE, atol=0)
