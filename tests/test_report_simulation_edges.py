"""Simulation report edge cases: mTI files, NaN and 4-D volumes, glob characters in names,
carrier-only controls, and figures from degenerate volumes.

Pins (2026-10-22, package p03):

* an mTI simulation is read from ``mTI/niftis`` even when a stale ``TI/niftis`` volume sits beside it,
  and is reported as multichannel with carrier i on pair i;
* the grey-matter maximum is located with NaN voxels ignored (``np.argmax`` returned the first NaN);
* a subject envelope saved as ``(X, Y, Z, 1)`` reads like its 3-D twin (it crashed the peak lookup
  with a matmul shape mismatch);
* a simulation named with glob characters (``a[1]``) still finds its envelope;
* a carrier-only control (ΔF = 0, no envelope) is reported as one: no "Temporal interference", no
  "TI envelope", no envelope read from a stale TI volume;
* the figure of a uniform envelope (median = 99.9th percentile) and of a constant T1 gets finite,
  ordered colour limits and a finite grey background (both divided zero by zero before).

Every expected number comes from the arrays built here: the maximum and its voxel are placed by
hand and mapped through the hand-written affine; median and percentiles of a handful of values are
worked out by hand.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

# `drawn` is a fixture: the figure tests below request it by name.
from tests.test_report_simulation_centre import SHAPE, cortex, cube, drawn, figure
from tests.test_report_simulation_modes import (
    NET,
    NET_MTI,
    carrier_rows,
    visible_text,
    write_run,
)
from tests.test_reporting_runs import CAP
from tit.reporting.generators import simulation as sim
from tit.sim.config import Montage, MontageMode

NET_FILE = "EEG10-10_UI_Jurak_2007.csv"
#: 2 mm voxels with an offset: voxel (i, j, k) is world (2i - 10, 2j + 5, 2k + 3).
AFFINE = np.array([[2.0, 0, 0, -10], [0, 2.0, 0, 5], [0, 0, 2.0, 3], [0, 0, 0, 1]])


def _with_volumes(d: Path, vols: dict[str, np.ndarray], affine=AFFINE) -> dict:
    """``collect(d)`` with these NIfTIs (path relative to *d* -> data) on disk."""
    imgs = {}
    for rel, data in vols.items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).touch()
        imgs[(d / rel).name] = SimpleNamespace(dataobj=data, affine=affine)
    with patch("nibabel.load", side_effect=lambda p: imgs[Path(p).name]):
        return sim.collect(d)


def _ti(name="M"):
    return Montage(
        name=name, mode=MontageMode.NET, electrode_pairs=NET, eeg_net=NET_FILE
    )


def _grey(peak_ijk=(2, 1, 2), peak=0.5) -> np.ndarray:
    gm = np.zeros((3, 3, 3), np.float32)
    gm[0, 1, 0], gm[1, 1, 1], gm[2, 2, 2] = 0.1, 0.2, 0.3
    gm[peak_ijk] = peak
    return gm


# ── (a) mTI ──────────────────────────────────────────────────────────────


def test_mti_reads_its_own_volume_not_a_stale_ti_one(tmp_path):
    montage = Montage(
        name="M", mode=MontageMode.NET, electrode_pairs=NET_MTI, eeg_net=NET_FILE
    )
    d = write_run(tmp_path, montage, intensities=[1.0, 1.0, 1.0, 1.0])
    stale = _grey((0, 0, 1), 0.9)  # left by an older TI run of the same folder
    rec = _with_volumes(
        d,
        {
            "mTI/niftis/grey_M_mTI_subject_mTI_max.nii.gz": _grey((2, 1, 0), 0.7),
            "TI/niftis/grey_M_TI_subject_TI_max.nii.gz": stale,
        },
    )
    assert rec["mode"] == "mTI" and rec["niftis"]["grey"].endswith(
        "grey_M_mTI_subject_mTI_max.nii.gz"
    )
    assert rec["envelope"]["max"] == pytest.approx(0.7)
    assert rec["envelope"]["peak_world"] == [2 * 2 - 10, 2 * 1 + 5, 2 * 0 + 3]
    with patch(CAP, return_value=None):
        page = sim.build_html(rec, None, "X")
    assert '<div class="kind">mTI simulation</div>' in page
    assert (
        "Multichannel temporal interference with AF3–PO10 and AF4–Oz and F3–P4 and F4–P3"
        in page
    )
    assert [r[:2] for r in carrier_rows(page)] == [
        ["X_TDCS_1", "E1+ AF3 · E1- PO10"],
        ["X_TDCS_2", "E2+ AF4 · E2- Oz"],
        ["X_TDCS_3", "E3+ F3 · E3- P4"],
        ["X_TDCS_4", "E4+ F4 · E4- P3"],
    ]


# ── (b) NaN, (c) 4-D, (d) glob characters ────────────────────────────────


def test_peak_ignores_nan_voxels(tmp_path):
    gm = _grey((2, 1, 2), 0.5)
    gm[0, 0, 0] = np.nan  # np.argmax returns the first NaN
    env = _with_volumes(
        write_run(tmp_path, _ti()), {"TI/niftis/grey_M_TI_subject_TI_max.nii.gz": gm}
    )["envelope"]
    assert env["max"] == 0.5
    assert env["peak_world"] == [2 * 2 - 10, 2 * 1 + 5, 2 * 2 + 3]
    # the positive voxels are 0.1, 0.2, 0.3, 0.5: median (0.2 + 0.3) / 2
    assert env["median"] == pytest.approx(0.25)


def test_a_single_frame_4d_envelope_reads_like_its_3d_twin(tmp_path):
    gm = _grey((1, 2, 0), 0.6)
    env = _with_volumes(
        write_run(tmp_path, _ti()),
        {"TI/niftis/grey_M_TI_subject_TI_max.nii.gz": gm[..., None]},
    )["envelope"]
    assert env["max"] == pytest.approx(0.6)
    assert env["peak_world"] == [2 * 1 - 10, 2 * 2 + 5, 2 * 0 + 3]


def test_glob_characters_in_the_simulation_name(tmp_path):
    d = write_run(tmp_path, _ti("a[1]"))
    rec = _with_volumes(
        d, {"TI/niftis/grey_a[1]_TI_subject_TI_max.nii.gz": _grey((0, 2, 1), 0.4)}
    )
    assert rec["niftis"]["grey"].endswith("grey_a[1]_TI_subject_TI_max.nii.gz")
    assert rec["envelope"]["peak_world"] == [2 * 0 - 10, 2 * 2 + 5, 2 * 1 + 3]


# ── (e) carrier-only control ─────────────────────────────────────────────


def test_a_carrier_only_control_is_not_reported_as_temporal_interference(tmp_path):
    d = write_run(tmp_path, _ti(), carrier_only=True, output_fields=["hf_peak"])
    # a TI volume left by an earlier run of the same folder: a carrier-only run computes none
    rec = _with_volumes(d, {"TI/niftis/grey_M_TI_subject_TI_max.nii.gz": _grey()})
    assert rec["envelope"] is None and rec["niftis"] == {}
    with patch(CAP, return_value=None):
        page = sim.build_html(rec, None, "X")
    text = visible_text(page)
    assert "Temporal interference" not in text and "temporal interference" not in text
    assert "TI envelope" not in text and "TI simulation" not in text
    headline = page.split('<h2 id="verdict-h">', 1)[1].split("</h2>", 1)[0]
    assert headline == "M: carrier-only control, no envelope (ΔF = 0)"
    assert '<div class="kind">Carrier-only control</div>' in page
    assert (
        "Carrier-only control with AF3–PO10 and AF4–Oz at 1 mA per channel (2 mA total)"
        in page
    )
    assert (
        "ref-grossman2017_ti" not in page
    )  # the envelope paper is not cited for a run without one


# ── figures from degenerate volumes ──────────────────────────────────────


def test_a_uniform_envelope_gets_ordered_colour_limits(tmp_path, drawn):
    g = cortex()
    g[g > 0] = 0.5  # every grey voxel equal: median == 99.9th percentile
    rec, out = figure(tmp_path, g)
    assert rec["envelope"]["median"] == rec["envelope"]["p99_9"] == 0.5
    assert out is not None and len(drawn) == 3
    for panel in drawn:
        assert (
            panel.lo < panel.hi <= 0.5
        )  # coloured at the top of the scale, never 0 / 0
        assert np.isfinite(panel.grey).all()


def test_a_constant_t1_gets_a_finite_background(tmp_path, drawn):
    g = cortex()
    cube(g, (30, 15, 15), 2, 1.0)
    _, out = figure(tmp_path, g, t1=np.full(SHAPE, 7.0, np.float32))
    assert out is not None and len(drawn) == 3
    for panel in drawn:
        assert (
            np.isfinite(panel.grey).all()
            and panel.grey.min() >= 0
            and panel.grey.max() <= 1
        )
