"""Analyzer custom mask membership and units (2026-09-09).

Authored asymmetric landmarks: the mask at world (12, 26, 42) selects one
24 mm3 voxel or one 7 mm2 surface node. Expectations come from those authored
coordinates and dimensions, independently of resampling. Run with real libraries:
simnibs_python -m pytest tests/numerical/test_analyzer_masks.py -q.
Optimizer nonlinear deformation itself is pinned in test_custom_masks.py.
"""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


def analyzer_fixture(tmp_path, monkeypatch, space):
    import nibabel as nib
    from tit.analyzer.analyzer import Analyzer

    analyzer = object.__new__(Analyzer)
    analyzer.space = space
    analyzer.field_name = "TI_max"
    analyzer.m2m_path = tmp_path / "unused"
    analyzer.field_path = tmp_path / "field.nii"
    analyzer._log_handler = None
    analyzer.output_dir = str(tmp_path)
    monkeypatch.setattr(analyzer, "_resolve_output_dir", lambda **kw: str(tmp_path))
    monkeypatch.setattr(analyzer, "_get_normal_stats", lambda *args: None)
    affine = np.diag([2.0, 3.0, 4.0, 1.0])
    affine[:3, 3] = [10, 20, 30]
    data = np.ones((3, 4, 5), dtype=np.float32)
    data[1, 2, 3] = 9
    nib.save(nib.Nifti1Image(data, affine), analyzer.field_path)
    # A different grid: one positive mask voxel has world center (12,26,42).
    mask = np.zeros((5, 7, 9), dtype=np.float32)
    mask[2, 6, 6] = 0.2
    mask[0, 0, 0] = -4
    mask_affine = np.diag([1.0, 1.0, 2.0, 1.0])
    mask_affine[:3, 3] = [10, 20, 30]
    mask_path = tmp_path / "mask.nii"
    nib.save(nib.Nifti1Image(mask, mask_affine), mask_path)
    monkeypatch.setattr(
        analyzer,
        "_voxel_tissue_mask",
        lambda img, shape, affine: np.ones(shape, dtype=bool),
    )
    return analyzer, mask_path


def test_voxel_mask_resamples_positive_membership_and_retains_volume(
    tmp_path, monkeypatch
):
    analyzer, mask = analyzer_fixture(tmp_path, monkeypatch, "voxel")
    result = analyzer.analyze_mask(str(mask))
    assert result.n_elements == 1
    assert result.roi_mean == 9
    assert result.total_area_or_volume == pytest.approx(
        2 * 3 * 4, abs=1e-12
    )  # determinant rounding
    assert result.analysis_type == "mask"
    assert list(tmp_path.glob("*.csv"))


def test_mesh_mask_samples_subject_nodes_and_retains_surface_area(
    tmp_path, monkeypatch
):
    analyzer, mask = analyzer_fixture(tmp_path, monkeypatch, "mesh")
    surface = SimpleNamespace(
        nodes=SimpleNamespace(
            node_coord=np.array([[12, 26, 42], [10, 20, 30], [100, 200, 300]])
        )
    )
    monkeypatch.setattr(analyzer, "_load_surface_mesh", lambda: surface)
    monkeypatch.setattr(
        analyzer, "_field_values", lambda mesh: np.array([9.0, 2.0, 4.0])
    )
    monkeypatch.setattr(analyzer, "_node_areas", lambda mesh: np.array([7.0, 3.0, 5.0]))
    result = analyzer.analyze_mask(str(mask))
    assert result.n_elements == 1
    assert result.roi_mean == 9
    assert result.total_area_or_volume == 7


def test_voxel_mask_rejects_no_overlap_with_selected_tissue(tmp_path, monkeypatch):
    analyzer, mask = analyzer_fixture(tmp_path, monkeypatch, "voxel")
    monkeypatch.setattr(
        analyzer,
        "_voxel_tissue_mask",
        lambda img, shape, affine: np.zeros(shape, dtype=bool),
    )
    with pytest.raises(ValueError, match="selected tissue"):
        analyzer.analyze_mask(str(mask))


def _check_analyzer_mni_mask(tmp_path):
    monkeypatch = pytest.MonkeyPatch()
    import nibabel as nib
    from tests.numerical.test_custom_masks import save

    analyzer, mask = analyzer_fixture(tmp_path, monkeypatch, "voxel")
    shape = (7, 8, 9)
    m2m = tmp_path / "m2m_subject"
    (m2m / "toMNI").mkdir(parents=True)
    save(nib.Nifti1Image(np.zeros(shape, np.float32), np.eye(4)), m2m / "T1.nii.gz")
    deformation = np.moveaxis(np.indices(shape).astype(np.float32), 0, -1)
    deformation[..., 0] += 1.2
    save(
        nib.Nifti1Image(deformation, np.eye(4)),
        m2m / "toMNI" / "Conform2MNI_nonl.nii.gz",
    )
    mask_data = np.zeros(shape, np.float32)
    mask_data[3, 3, 4] = 0.2
    nib.save(nib.Nifti1Image(mask_data, np.eye(4)), mask)
    field = np.ones(shape, np.float32)
    field[2, 3, 4] = 9
    nib.save(nib.Nifti1Image(field, np.eye(4)), analyzer.field_path)
    analyzer.m2m_path = m2m
    result = analyzer.analyze_mask(str(mask), "mni")
    assert result.n_elements == 1
    assert result.roi_mean == 9
    assert result.total_area_or_volume == 1


def test_analyzer_mni_mask_uses_subject_nonlinear_registration(tmp_path):
    import subprocess
    import sys

    probe = subprocess.run(
        [sys.executable, "-c", "import simnibs"], capture_output=True
    )
    if probe.returncode:
        pytest.skip("Real SimNIBS is required; run in the toolbox container")
    code = "import runpy,sys; from pathlib import Path; runpy.run_path(sys.argv[1])['_check_analyzer_mni_mask'](Path(sys.argv[2]))"
    result = subprocess.run(
        [sys.executable, "-c", code, __file__, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
