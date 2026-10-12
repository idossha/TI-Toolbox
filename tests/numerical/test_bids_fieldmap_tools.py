"""The DWI fieldmap layout that DICOM conversion writes, judged by the tools that read it.

Pins (2026-10-12): a tree produced by ``tit.pre.dicom2nifti.run_dicom_to_nifti``
(dcm2niix faked, as in tests/test_pre_dicom.py::TestReversePhaseEncodingFieldmap)
is accepted by readers that are not ours:

- sdcflows ``find_estimators`` (2.17.1) finds a PEPOLAR estimator from
  ``fmap/sub-001_dir-PA_epi`` and the DWI;
- QSIPrep 26.0.0's own ``collect_data`` + ``group_by_warpspace`` give the DWI an
  ``epi`` fieldmap, and pair ``dir-AP``/``dir-PA`` DWI series with each other;
- the BIDS validator reports no error (only when ``TIT_BIDS_VALIDATOR`` holds its
  command, e.g. ``deno run -A jsr:@bids/validator``: it downloads, so it is off by
  default).

Each leg skips with its reason when the tool is absent; none is in the image. To
run them::

    uv venv --python 3.12 /tmp/qsi && uv pip install --python /tmp/qsi/bin/python \\
        --no-deps qsiprep==26.0.0 && uv pip install --python /tmp/qsi/bin/python \\
        sdcflows pybids nibabel nipype templateflow niworkflows dipy pytest
    PYTHONPATH=. TIT_BIDS_VALIDATOR="deno run -A jsr:@bids/validator" \\
        /tmp/qsi/bin/python -m pytest tests/numerical/test_bids_fieldmap_tools.py
"""

import json
import os
import shlex
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from tests.test_pre_dicom import TestReversePhaseEncodingFieldmap as Layout
from tit.pre.dicom2nifti import run_dicom_to_nifti
from tit.pre.utils import ensure_bidsignore, ensure_dataset_descriptions


@pytest.fixture(autouse=True)
def _unmocked():
    """Take tests/conftest.py's MagicMock stand-ins (nilearn, pandas, ...) out of the way.

    sdcflows and QSIPrep import the real packages; the mocks go back afterwards.
    """
    mocked = {
        name: module
        for name, module in sys.modules.items()
        if isinstance(module, MagicMock)
    }
    for name in mocked:
        del sys.modules[name]
    yield
    sys.modules.update(mocked)


def _tree(root, both_in_dwi=False):
    Layout._sourcedata(root, *(("dwi",) if both_in_dwi else ("dwi", "fmap")))
    ensure_dataset_descriptions(str(root), ["root"])
    ensure_bidsignore(str(root))
    run_dicom_to_nifti(
        str(root),
        "001",
        logger=MagicMock(),
        runner=Layout._fake_dcm2niix(both_in_dwi=both_in_dwi),
    )
    return root


def test_sdcflows_finds_a_pepolar_estimator(tmp_path):
    wrangler = pytest.importorskip("sdcflows.utils.wrangler", reason="sdcflows absent")
    bids = pytest.importorskip("bids", reason="pybids absent")
    layout = bids.BIDSLayout(str(_tree(tmp_path)), validate=False)

    estimators = wrangler.find_estimators(layout=layout, subject="001", fmapless=False)

    assert [
        (e.method.name, sorted(s.path.name for s in e.sources)) for e in estimators
    ] == [("PEPOLAR", ["sub-001_dir-PA_epi.nii.gz", "sub-001_dwi.nii.gz"])]


def test_qsiprep_assigns_the_fmap_epi_to_the_dwi(tmp_path):
    os.environ.setdefault("TEMPLATEFLOW_HOME", str(tmp_path / "templateflow"))
    grouping = pytest.importorskip("qsiprep.utils.grouping", reason="qsiprep absent")
    qsi_bids = pytest.importorskip("qsiprep.utils.bids", reason="qsiprep absent")
    data, layout = qsi_bids.collect_data(
        str(_tree(tmp_path)), "001", bids_validate=False
    )

    [group] = grouping.group_by_warpspace(data["dwi"], layout, False)

    assert group["fieldmap_info"]["suffix"] == "epi"
    assert [p.split("/")[-1] for p in group["fieldmap_info"]["epi"]] == [
        "sub-001_dir-PA_epi.nii.gz"
    ]


def test_qsiprep_pairs_direction_named_dwi_series(tmp_path):
    os.environ.setdefault("TEMPLATEFLOW_HOME", str(tmp_path / "templateflow"))
    grouping = pytest.importorskip("qsiprep.utils.grouping", reason="qsiprep absent")
    qsi_bids = pytest.importorskip("qsiprep.utils.bids", reason="qsiprep absent")
    data, layout = qsi_bids.collect_data(
        str(_tree(tmp_path, both_in_dwi=True)), "001", bids_validate=False
    )

    groups = grouping.group_by_warpspace(data["dwi"], layout, False)

    assert {
        g["dwi_series"][0].split("/")[-1]: [
            p.split("/")[-1] for p in g["fieldmap_info"]["dwi"]
        ]
        for g in groups
    } == {
        "sub-001_dir-AP_dwi.nii.gz": ["sub-001_dir-PA_dwi.nii.gz"],
        "sub-001_dir-PA_dwi.nii.gz": ["sub-001_dir-AP_dwi.nii.gz"],
    }


@pytest.mark.parametrize("both_in_dwi", [False, True])
def test_bids_validator_reports_no_error(tmp_path, both_in_dwi):
    command = os.environ.get("TIT_BIDS_VALIDATOR")
    if not command:
        pytest.skip("TIT_BIDS_VALIDATOR is unset (the validator downloads)")
    root = _tree(tmp_path, both_in_dwi=both_in_dwi)

    result = subprocess.run(
        [*shlex.split(command), str(root), "--json"],
        capture_output=True,
        text=True,
        env={**os.environ, "NO_COLOR": "1"},
    )
    issues = json.loads(result.stdout)["issues"]["issues"]

    assert issues, "the validator reported nothing at all"
    assert [
        (i["code"], i.get("location")) for i in issues if i["severity"] == "error"
    ] == []
