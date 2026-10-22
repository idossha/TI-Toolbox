"""Re-converting Dataset 000 sub-101's T1w DICOMs reproduces the committed BIDS T1w.

Gated on ``TIT_DATASET_000`` (a Dataset 000 copy; mount it ``:ro`` in the image) and on
``dcm2niix`` being on PATH. The 240 ``.dcm`` files of ``sourcedata/sub-101/T1w`` are
copied into a scratch project and run through
``tit.pre.dicom2nifti.run_dicom_to_nifti``; the expected output is the reference
conversion committed in Dataset 000 (``sub-101/anat/sub-101_T1w.nii.gz``, written by
dcm2niix v1.0.20211006, the image's version): 240 x 512 x 512 voxels of 0.8 x 0.5 x 0.5
mm, RAS, with the series description ``anat-T1w_acq-MPRAGE``. The same series with its
``.dcm`` extensions stripped (a PACS export) must convert identically: the DICOM Part 10
``DICM`` prefix identifies it.

    TIT_DATASET_000=/data/000 simnibs_python -m pytest \\
        tests/numerical/test_dicom_regeneration_realdata.py -q -p no:cacheprovider
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path

import numpy as np
import pytest

_DATASET = os.environ.get("TIT_DATASET_000", "")
ROOT = Path(_DATASET)
SOURCE = ROOT / "sourcedata" / "sub-101" / "T1w"
REFERENCE = ROOT / "sub-101" / "anat" / "sub-101_T1w.nii.gz"

pytestmark = [
    pytest.mark.host_numerical,
    pytest.mark.skipif(
        not (_DATASET and SOURCE.is_dir() and REFERENCE.is_file()),
        reason="skipping: set TIT_DATASET_000 to a Dataset 000 copy with sub-101 DICOMs",
    ),
    pytest.mark.skipif(
        shutil.which("dcm2niix") is None,
        reason="skipping: dcm2niix is not on PATH (it is in the toolbox image)",
    ),
]


def _mtimes(root: Path) -> dict[str, int]:
    return {str(p): p.stat().st_mtime_ns for p in [root, *sorted(root.rglob("*"))]}


def _convert(tmp_path: Path, strip_extension: bool) -> Path:
    from tit.paths import get_path_manager, reset_path_manager
    from tit.pre.dicom2nifti import run_dicom_to_nifti

    project = tmp_path / "project"
    target = project / "sourcedata" / "sub-101" / "T1w"
    dicoms = sorted(p for p in SOURCE.rglob("*.dcm") if not p.name.startswith("."))
    assert len(dicoms) == 240
    target.mkdir(parents=True)
    for path in dicoms:
        name = path.stem if strip_extension else path.name
        shutil.copyfile(path, target / name)

    reset_path_manager()
    get_path_manager(str(project))
    try:
        run_dicom_to_nifti(str(project), "101", logger=logging.getLogger("dicom"))
    finally:
        reset_path_manager()
    return project / "sub-101" / "anat"


@pytest.fixture(scope="module")
def reference():
    import nibabel as nib

    img = nib.load(str(REFERENCE))
    return img, np.asarray(img.dataobj)


@pytest.mark.parametrize("strip_extension", [False, True], ids=["dcm", "no-extension"])
def test_conversion_reproduces_the_reference_t1w(tmp_path, reference, strip_extension):
    import nibabel as nib

    before = _mtimes(SOURCE)
    anat = _convert(tmp_path, strip_extension)
    assert _mtimes(SOURCE) == before, "the conversion changed Dataset 000"

    # Exactly the BIDS pair: no sub-101_T1wa.nii.gz collision or _Eq_/_Tilt_ volume.
    assert sorted(p.name for p in anat.iterdir()) == [
        "sub-101_T1w.json",
        "sub-101_T1w.nii.gz",
    ]
    img = nib.load(str(anat / "sub-101_T1w.nii.gz"))
    assert img.shape == (240, 512, 512)
    assert nib.aff2axcodes(img.affine) == ("R", "A", "S")
    assert img.header.get_zooms() == pytest.approx((0.8, 0.5, 0.5), abs=1e-4)

    ref_img, ref_data = reference
    np.testing.assert_allclose(img.affine, ref_img.affine, atol=1e-4)
    np.testing.assert_array_equal(np.asarray(img.dataobj), ref_data)

    sidecar = json.loads((anat / "sub-101_T1w.json").read_text())
    assert sidecar["SeriesDescription"] == "anat-T1w_acq-MPRAGE"
