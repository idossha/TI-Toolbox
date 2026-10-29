"""Carrier focality and TI selectivity from real NIfTIs in the simulator's layout (2026-10-29).

What this pins
    A voxel ``Analyzer`` run of ``TI_max`` reads the same simulation's ``hf_peak`` and
    ``hf_sar`` NIfTIs (real files, real nibabel) and reports ``hf_focality``,
    ``rms_focality`` and ``ti_selectivity`` over exactly the voxels ``roi_focality`` used;
    its ``hf_focality_*_area`` equal the ``focality_*_area`` of an analysis of ``hf_peak``
    itself on the same ROI.

Where the numbers come from
    Two parallel channel fields ``E1 = a u``, ``E2 = b u`` (a, b > 0, authored below), for which
    the closed forms are textbook: TI_max = 2 min(a, b) (Grossman 2017, parallel fields),
    hf_peak = a + b, E_rms = sqrt((a^2 + b^2) / 2). The NIfTIs are written with
    ``tit.calc`` (what the simulator writes, hf_sar = 2 hf_power); the expectations are
    those closed forms averaged over a sphere mask computed here from the affine. Outside a
    "brain" box both fields are 0, so TI_max = 0 there and those voxels are in neither mean.

Needs only real numpy/nibabel (``host_numerical``); the host suite mocks nibabel.

Reproduce:
  host:      ``.venv/bin/python -m pytest tests/numerical/test_analyzer_carrier_focality_real.py -q -m host_numerical``
  container: ``simnibs_python -m pytest tests/numerical/test_analyzer_carrier_focality_real.py -q``
Deliberately elsewhere: the hand-sized mesh/voxel fixtures and the missing-field notes
(``tests/test_analyzer_carrier_focality.py``).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.host_numerical

SID, SIM = "101", "M1"
SHAPE = (12, 10, 8)
AFFINE = np.array(
    [
        [2.0, 0.0, 0.0, -10.0],
        [0.0, 2.0, 0.0, -8.0],
        [0.0, 0.0, 2.0, -6.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
)
CENTER, RADIUS = (2.0, 0.0, 0.0), 5.0


def _channels() -> tuple[np.ndarray, np.ndarray]:
    i, j, k = np.indices(SHAPE, dtype=float)
    a = 0.05 + 0.01 * (i + 2 * j + 3 * k)
    b = 0.45 - 0.006 * (2 * i + j + k)
    brain = np.zeros(SHAPE, dtype=bool)
    brain[1:11, 1:9, 1:7] = True
    return np.where(brain, a, 0.0), np.where(brain, b, 0.0)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    import nibabel as nib

    from tit.calc import envelope_max, hf_peak, hf_power
    from tit.paths import get_path_manager

    root = tmp_path / "proj"
    sub = root / "derivatives" / "SimNIBS" / f"sub-{SID}"
    niftis = sub / "Simulations" / SIM / "TI" / "niftis"
    niftis.mkdir(parents=True)
    (sub / f"m2m_{SID}").mkdir()
    (root / "dataset_description.json").write_text("{}")
    a, b = _channels()
    u = np.array([0.6, 0.0, 0.8])
    e1 = a.reshape(-1, 1) * u
    e2 = b.reshape(-1, 1) * u
    written = {
        "TI_max": envelope_max([e1, e2]),
        "hf_peak": hf_peak([e1, e2]),
        "hf_sar": 2.0 * hf_power([e1, e2]),  # the simulator's on-disk hf_sar
    }
    for name, values in written.items():
        nib.save(
            nib.Nifti1Image(values.reshape(SHAPE).astype(np.float64), AFFINE),
            str(niftis / f"grey_{SIM}_TI_subject_{name}.nii"),
        )
    get_path_manager(str(root))
    return root


def _sphere_mask() -> np.ndarray:
    ijk = np.indices(SHAPE).reshape(3, -1).T
    world = ijk @ AFFINE[:3, :3].T + AFFINE[:3, 3]
    return (np.linalg.norm(world - np.asarray(CENTER), axis=1) <= RADIUS).reshape(SHAPE)


def test_voxel_carrier_metrics_match_the_closed_forms(project: Path) -> None:
    from tit.analyzer.analyzer import Analyzer

    a, b = _channels()
    ti = 2.0 * np.minimum(a, b)
    peak = a + b
    rms = np.sqrt((a**2 + b**2) / 2.0)
    gm = ti > 0
    roi = _sphere_mask() & gm
    assert (
        0 < roi.sum() < gm.sum()
    )  # the sphere is a strict, non-empty part of the brain

    def focality(values):
        return values[roi].mean() / values[gm].mean()

    r = Analyzer(SID, SIM, space="voxel", field="TI_max").analyze_sphere(CENTER, RADIUS)
    assert r.n_elements == int(roi.sum())
    assert r.roi_focality == pytest.approx(focality(ti), rel=1e-12)
    assert r.hf_roi_mean == pytest.approx(peak[roi].mean(), rel=1e-12)
    assert r.hf_gm_mean == pytest.approx(peak[gm].mean(), rel=1e-12)
    assert r.hf_focality == pytest.approx(focality(peak), rel=1e-12)
    assert r.rms_roi_mean == pytest.approx(rms[roi].mean(), rel=1e-12)
    assert r.rms_focality == pytest.approx(focality(rms), rel=1e-12)
    assert r.ti_selectivity == pytest.approx(focality(ti) / focality(peak), rel=1e-12)
    assert r.carrier_note is None

    hf = Analyzer(SID, SIM, space="voxel", field="hf_peak").analyze_sphere(
        CENTER, RADIUS
    )
    for pct in (50, 75, 90, 95):
        assert getattr(r, f"hf_focality_{pct}_area") == pytest.approx(
            getattr(hf, f"focality_{pct}_area"), rel=1e-12
        ), pct
    assert hf.hf_focality is None and "not a modulation field" in hf.carrier_note
