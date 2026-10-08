"""A flex/ex report on a cortical (``.annot``) target: the file is read as an annotation.

Regression: the report sent every ROI source to the volume atlas reader, and ``nib.load`` stops
on a FreeSurfer annotation with "Cannot work out file type".  Needs real nibabel (this directory
swaps it in; the host dispatch test is in ``tests/test_reporting_runs.py``).
"""

import json

import numpy as np

from tit.reporting.generators import common


def test_roi_summary_reads_a_real_annot(tmp_path):
    from nibabel.freesurfer import write_annot

    annot = tmp_path / "lh.CHN_DK40.annot"
    ctab = np.array([[25, 5, 25, 0, 0], [25, 100, 40, 0, 1]], dtype=np.int32)
    write_annot(str(annot), np.array([0, 1, 1, 0]), ctab, ["unknown", "insula"], fill_ctab=True)
    (tmp_path / "roi.tetravox.json").write_text(json.dumps({"meta": {
        "roi": "lh.insula", "source": [str(annot)], "label": [1], "space": "subject",
        "voxels": 2, "unit": "vertices", "volume_mm3": None}}))

    roi = common.roi_summary(tmp_path)

    assert roi["name"] == "lh.insula"
    assert roi["atlas"] == "CHN_DK40 (lh)"
    assert roi["vertices"] == 2
