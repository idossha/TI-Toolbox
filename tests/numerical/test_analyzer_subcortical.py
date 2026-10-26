"""Analyzer subcortical (volume-atlas) targets: which voxels a named label selects (2026-10-21).

Pins: ``Analyzer.analyze_subcortical`` measures exactly the voxels of the named label,
resampled onto the field grid, in subject space and through the MNI mask path. Before
2026-10-21 the Analyzer's Subcortical mode exited 1 ("not implemented").

Where the numbers come from: authored. The field is ``1 + i + 4j + 16k`` on a 2 mm grid at
the origin; the atlas is a 1 mm grid at the origin, so field voxel (i, j, k) sits on atlas
voxel (2i, 2j, 2k). Label 205 fills atlas block [2:4, 4:6, 4:8], which holds the centres of
field voxels (1, 2, 2) and (1, 2, 3) only: values 42 and 58, mean 50, 2 x 8 mm^3. Label 203
fills atlas block [0:2, 0:2, 0:2] (field voxel (0, 0, 0), value 1). Names come from the
bundled FreeSurferColorLUT.txt (203 parasubiculum, 205 subiculum), so "subiculum" must pick
205, not the lower-numbered "parasubiculum" that contains it.

Run with real libraries: simnibs_python -m pytest tests/numerical/test_analyzer_subcortical.py -q.
The nonlinear MNI warp itself is pinned in test_custom_masks.py / test_analyzer_masks.py.
"""

import numpy as np
import pytest


def _fixture(tmp_path, monkeypatch):
    import nibabel as nib
    from tit.analyzer.analyzer import Analyzer

    analyzer = object.__new__(Analyzer)
    analyzer.space = "voxel"
    analyzer.field_name = "TI_max"
    analyzer.tissue_type = "GM"  # Analyzer.__init__'s default; voxel runs record it
    analyzer.m2m_path = tmp_path / "unused"
    analyzer.field_path = tmp_path / "field.nii"
    analyzer._log_handler = None
    analyzer.output_dir = str(tmp_path)
    monkeypatch.setattr(analyzer, "_resolve_output_dir", lambda **kw: str(tmp_path))
    monkeypatch.setattr(
        analyzer,
        "_voxel_tissue_mask",
        lambda shape, affine: np.ones(shape, dtype=bool),
    )
    i, j, k = np.indices((4, 4, 4))
    field = (1 + i + 4 * j + 16 * k).astype(np.float32)
    nib.save(nib.Nifti1Image(field, np.diag([2.0, 2.0, 2.0, 1.0])), analyzer.field_path)
    labels = np.zeros((8, 8, 8), dtype=np.int16)
    labels[0:2, 0:2, 0:2] = 203
    labels[2:4, 4:6, 4:8] = 205
    atlas = tmp_path / "hippoSubfields.nii"
    nib.save(nib.Nifti1Image(labels, np.eye(4)), atlas)
    return analyzer, atlas


def test_subject_atlas_label_selects_its_own_voxels(tmp_path, monkeypatch):
    analyzer, atlas = _fixture(tmp_path, monkeypatch)
    result = analyzer.analyze_subcortical(str(atlas), "subiculum")
    assert result.analysis_type == "subcortical"
    assert result.region_name == "subiculum"
    assert result.n_elements == 2
    assert result.roi_mean == pytest.approx(50.0)
    assert result.total_area_or_volume == pytest.approx(16.0)


def test_mni_atlas_goes_through_the_mni_mask_path(tmp_path, monkeypatch):
    """Identity registration stand-in: the MNI branch is taken, the voxels are unchanged."""
    from tit.opt import masks

    analyzer, atlas = _fixture(tmp_path, monkeypatch)
    spaces = []

    def identity_prepare(path, space, m2m, output_dir, *, binary=False, cache_dir=None):
        spaces.append(space)
        return path

    monkeypatch.setattr(masks, "prepare_mask", identity_prepare)
    result = analyzer.analyze_subcortical(str(atlas), ["subiculum"], "mni")
    assert spaces == ["mni"]
    assert result.n_elements == 2
    assert result.roi_mean == pytest.approx(50.0)


def test_a_shipped_mni_atlas_id_resolves_to_its_packaged_file():
    from tit.analyzer.analyzer import Analyzer

    path = Analyzer._resolve_mni_atlas("HarvardOxford-sub-maxprob-thr25-1mm.nii.gz")
    assert path.name == "HarvardOxford-sub-maxprob-thr25-1mm.nii.gz"
    assert path.is_file()
