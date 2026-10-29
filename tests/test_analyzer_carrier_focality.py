"""Carrier (stimulation-intensity) focality beside the modulation focality (2026-10-29).

What this pins
    An analysis of a modulation field (TI_max, mTI_max, TI_avg, TI_normal) also reports,
    over the *same* ROI and GM elements and weights as ``roi_focality``:
    ``hf_focality`` = mean_ROI(hf_peak) / mean_GM(hf_peak), ``rms_focality`` on
    E_rms = sqrt(hf_sar / 2), ``ti_selectivity`` = roi_focality / hf_focality and the
    ``hf_focality_*_area`` hot-spot extents on hf_peak. A carrier field the simulation did
    not write leaves its metrics ``None`` with ``carrier_note`` naming the missing field; an
    analysis of a carrier field reports none of them, with a note saying why.

Where the expectations come from
    Hand arithmetic on authored fields, written out beside each assertion: piecewise-constant
    fields (ROI vs rest) on nodes/voxels of authored areas/volumes, so every weighted mean is
    a two-term sum. A node where the analysed field is 0 carries a huge carrier value to prove
    the carrier means skip it exactly as the modulation means do.

Run: .venv/bin/python -m pytest tests/test_analyzer_carrier_focality.py -q -p no:cacheprovider
(numpy is real on the host; nibabel is replaced by in-memory images here.) The real-library
check is tests/numerical/test_analyzer_carrier_focality_real.py.
"""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

from tit.analyzer.analyzer import CARRIER_RESULT_KEYS, Analyzer, rms_from_hf_sar

# Ten surface nodes on a line (x = 0..9); the ROI sphere about x = 1.5, r = 2 holds
# x = 0..3. Node 9 has TI = 0 (outside "positive GM") but a carrier of 1000.
X = np.arange(10.0)
AREAS = np.array([1.0, 2.0, 3.0, 4.0, 1.0, 1.0, 2.0, 2.0, 3.0, 5.0])
ROI = X <= 3.5
TI = np.where(ROI, 2.0, 1.0)
TI[9] = 0.0
HF = np.where(ROI, 3.0, 1.0)
HF[9] = 1000.0
ERMS = np.where(ROI, 4.0, 1.0)
HF_SAR = 2.0 * ERMS**2  # hf_sar = sum |E_c|^2 = 2 E_rms^2
HF_SAR[9] = 1e6


def _hand_means(values: np.ndarray) -> tuple[float, float]:
    """Area-weighted ROI and positive-GM means of a piecewise field, as explicit sums."""
    gm = TI > 0
    roi = ROI & gm
    return (
        float((values[roi] * AREAS[roi]).sum() / AREAS[roi].sum()),
        float((values[gm] * AREAS[gm]).sum() / AREAS[gm].sum()),
    )


def _mesh(tmp_path: Path, field: str = "TI_max", **fields) -> Analyzer:
    analyzer = object.__new__(Analyzer)
    analyzer.space = "mesh"
    analyzer.field_name = field
    analyzer.tissue_type = "GM"
    analyzer.field_path = tmp_path / "sim_TI.msh"
    analyzer.output_dir = str(tmp_path / "out")
    analyzer._pm = SimpleNamespace(ensure=lambda p: Path(p).mkdir(parents=True) or p)
    analyzer._is_mti = field == "mTI_max"
    analyzer._surface_mesh = SimpleNamespace(
        nodes=SimpleNamespace(node_coord=np.c_[X, np.zeros(10), np.zeros(10)]),
        field={k: SimpleNamespace(value=v) for k, v in fields.items()},
        nodes_areas=lambda: AREAS,
    )
    analyzer._surface_mesh_path = tmp_path / "sim_TI_central.msh"
    analyzer._get_normal_stats = lambda *a: None
    return analyzer


def _sphere(analyzer: Analyzer):
    return analyzer.analyze_sphere((1.5, 0.0, 0.0), 2.0)


def _csv(tmp_path: Path) -> dict:
    with open(tmp_path / "out" / "results.csv", newline="") as fh:
        return {row["Metric"]: row["Value"] for row in csv.DictReader(fh)}


def test_rms_from_hf_sar_is_the_rms_of_two_carriers() -> None:
    # E1 = (3, 0, 0), E2 = (0, 4, 0) V/m zero-to-peak: hf_sar = 9 + 16 = 25, and the RMS of
    # two sinusoids at distinct frequencies is sqrt((9 + 16) / 2) = sqrt(12.5).
    assert rms_from_hf_sar(np.array([25.0])) == pytest.approx([np.sqrt(12.5)])


def test_uniform_carrier_has_focality_one_and_selectivity_equal_to_ti_focality(
    tmp_path: Path,
) -> None:
    flat = np.full(10, 0.7)
    r = _sphere(_mesh(tmp_path, TI_max=TI, hf_peak=flat, hf_sar=flat))
    assert r.hf_focality == pytest.approx(1.0)
    assert r.rms_focality == pytest.approx(1.0)
    assert r.ti_selectivity == pytest.approx(r.roi_focality)
    assert r.carrier_note is None


def test_designed_mesh_fields_give_the_hand_ratios(tmp_path: Path) -> None:
    r = _sphere(_mesh(tmp_path, TI_max=TI, hf_peak=HF, hf_sar=HF_SAR))
    ti_roi, ti_gm = _hand_means(TI)
    hf_roi, hf_gm = _hand_means(HF)
    rms_roi, rms_gm = _hand_means(ERMS)
    # ROI areas 1+2+3+4 = 10, rest (nodes 4-8) 1+1+2+2+3 = 9; node 9 (TI = 0) is out:
    # TI 2 vs 1 -> GM mean 29/19; hf_peak 3 vs 1 -> 39/19; E_rms 4 vs 1 -> 49/19.
    assert (ti_roi, ti_gm) == pytest.approx((2.0, 29 / 19))
    assert (hf_roi, hf_gm) == pytest.approx((3.0, 39 / 19))
    assert (rms_roi, rms_gm) == pytest.approx((4.0, 49 / 19))
    assert r.roi_focality == pytest.approx(38 / 29)
    assert (r.hf_roi_mean, r.hf_gm_mean) == pytest.approx((hf_roi, hf_gm))
    assert r.hf_focality == pytest.approx(57 / 39)
    assert (r.rms_roi_mean, r.rms_gm_mean) == pytest.approx((rms_roi, rms_gm))
    assert r.rms_focality == pytest.approx(76 / 49)
    # (38/29) / (57/39) = 38*39 / (29*57) = 1482/1653: here the carrier is the more focal one.
    assert r.ti_selectivity == pytest.approx(1482 / 1653)
    # hf_peak hot spot: the 99.9th percentile of {3 (area 10), 1 (area 9)} is 3, every cutoff
    # 1.5 ... 2.85 keeps only the ROI's 10 mm^2 = 0.1 cm^2.
    for pct in (50, 75, 90, 95):
        assert getattr(r, f"hf_focality_{pct}_area") == pytest.approx(0.1)
    assert r.carrier_note is None
    row = _csv(tmp_path)
    for key in CARRIER_RESULT_KEYS[:-1]:
        assert float(row[key]) == pytest.approx(getattr(r, key)), key
    assert "carrier_note" not in row  # None is not written


def test_mti_analysis_reads_the_mti_surface_carriers(tmp_path: Path) -> None:
    r = _sphere(_mesh(tmp_path, field="mTI_max", mTI_max=TI, hf_peak=HF, hf_sar=HF_SAR))
    assert r.field_name == "mTI_max"
    assert r.hf_focality == pytest.approx(57 / 39)
    assert r.ti_selectivity == pytest.approx(1482 / 1653)


def test_ti_normal_selectivity_uses_the_normal_fields_focality(tmp_path: Path) -> None:
    analyzer = _mesh(tmp_path, field="TI_normal", hf_peak=HF, hf_sar=HF_SAR)
    normal = np.where(ROI, 3.0, 1.0)
    normal[9] = 0.0
    analyzer._field_values = lambda surface: normal
    r = _sphere(analyzer)
    # TI_normal 3 vs 1 on the same nodes as hf_peak 3 vs 1: identical focality, selectivity 1.
    assert r.roi_focality == pytest.approx(57 / 39)
    assert r.ti_selectivity == pytest.approx(1.0)


def test_a_missing_hf_sar_leaves_only_the_rms_metrics_out(tmp_path: Path) -> None:
    r = _sphere(_mesh(tmp_path, TI_max=TI, hf_peak=HF))
    assert r.hf_focality == pytest.approx(57 / 39)
    assert r.rms_roi_mean is r.rms_gm_mean is r.rms_focality is None
    assert "hf_sar is not on the central surface" in r.carrier_note
    assert _csv(tmp_path)["carrier_note"] == r.carrier_note


def test_no_carrier_fields_means_every_carrier_metric_is_none(tmp_path: Path) -> None:
    r = _sphere(_mesh(tmp_path, TI_max=TI))
    assert all(getattr(r, k) is None for k in CARRIER_RESULT_KEYS[:-1])
    assert "hf_peak" in r.carrier_note and "hf_sar" in r.carrier_note
    assert "output fields" in r.carrier_note
    assert r.roi_focality == pytest.approx(38 / 29)  # the TI statistics are unaffected


def test_a_carrier_field_analysis_has_no_carrier_metrics(tmp_path: Path) -> None:
    hf = HF.copy()
    hf[9] = 0.0
    r = _sphere(_mesh(tmp_path, field="hf_peak", hf_peak=hf, hf_sar=HF_SAR))
    assert all(getattr(r, k) is None for k in CARRIER_RESULT_KEYS[:-1])
    assert "hf_peak is not a modulation field" in r.carrier_note


# -- voxel -------------------------------------------------------------------------------------

VOXEL = np.diag([2.0, 2.0, 2.0, 1.0])  # 8 mm^3 voxels


def _voxel(tmp_path: Path, written=("hf_peak", "hf_sar"), shape=(10, 1, 1)):
    analyzer = object.__new__(Analyzer)
    analyzer.space = "voxel"
    analyzer.field_name = "TI_max"
    analyzer.tissue_type = "GM"
    analyzer.field_path = tmp_path / "grey_sim_TI_subject_TI_max.nii.gz"
    analyzer.output_dir = str(tmp_path / "out")
    analyzer._pm = SimpleNamespace(ensure=lambda p: Path(p).mkdir(parents=True) or p)
    analyzer._surface_mesh = None
    analyzer._is_mti = False
    images = {analyzer.field_path.name: TI}
    for name, values in (("hf_peak", HF), ("hf_sar", HF_SAR)):
        if name in written:
            path = tmp_path / f"grey_sim_TI_subject_{name}.nii.gz"
            path.touch()
            images[path.name] = values if shape == (10, 1, 1) else np.ones(shape)

    def load(path):
        data = images[Path(path).name]
        return SimpleNamespace(
            get_fdata=lambda: np.asarray(data, dtype=float).reshape(
                data.shape if data.ndim == 3 else (10, 1, 1)
            ),
            affine=VOXEL,
        )

    return analyzer, load


def test_voxel_path_uses_the_same_voxels_and_volumes(tmp_path: Path) -> None:
    analyzer, load = _voxel(tmp_path)
    # Voxel i sits at x = 2i mm; the sphere about x = 3, r = 3.5 holds voxels 0..3, the ROI.
    with patch("nibabel.load", load):
        r = analyzer.analyze_sphere((3.0, 0.0, 0.0), 3.5)
    # Equal 8 mm^3 voxels: ROI 4 voxels, rest 5 positive voxels (voxel 9 has TI = 0).
    assert r.roi_focality == pytest.approx(2.0 / (13 / 9))
    assert r.hf_focality == pytest.approx(3.0 / (17 / 9))
    assert r.rms_focality == pytest.approx(4.0 / (21 / 9))
    assert r.ti_selectivity == pytest.approx((18 / 13) / (27 / 17))
    # Hot spot: the 4 ROI voxels, 32 mm^3 = 0.032 cm^3.
    assert r.hf_focality_50_area == pytest.approx(0.032)
    assert r.carrier_note is None


def test_voxel_missing_carrier_nifti_is_named(tmp_path: Path) -> None:
    analyzer, load = _voxel(tmp_path, written=("hf_peak",))
    with patch("nibabel.load", load):
        r = analyzer.analyze_sphere((3.0, 0.0, 0.0), 3.5)
    assert r.hf_focality is not None and r.rms_focality is None
    assert "grey_sim_TI_subject_hf_sar.nii.gz does not exist" in r.carrier_note


def test_voxel_carrier_on_another_grid_is_refused_by_name(tmp_path: Path) -> None:
    analyzer, load = _voxel(tmp_path, shape=(5, 2, 1))
    with patch("nibabel.load", load):
        r = analyzer.analyze_sphere((3.0, 0.0, 0.0), 3.5)
    assert r.hf_focality is None and r.rms_focality is None
    assert "has grid (5, 2, 1), not the (10, 1, 1)" in r.carrier_note
