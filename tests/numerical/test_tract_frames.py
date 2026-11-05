"""tit.tract recovers a planted world fibre direction through every voxel frame (image).

Pins (2026-11-04), on synthetic volumes built here, for an LPS, a PSR (ernie's tensor grid)
and an oblique anisotropic affine, with an oblique planted direction
``d = (0.48, -0.6, 0.64)``:

* ``dti_reference``, the frame check's own tensor fit on QSIPrep-style files (DWI NIfTI,
  world-RAS ``.b`` table, brain mask; no m2m tensor) of a tensor ``l1 d d^T + l2 (I - d d^T)``,
  returns ``+/- d`` and its FA (closed form for two equal minor eigenvalues), on
  b <= 1500 when such a shell exists and on the lowest shell for a b0 + b3000 scan, and a
  straight streamline along ``d`` scores coherence 1;
* the tracker (``fit_csd`` on DWI simulated in world coordinates as
  ``S0 exp(-b g^T D g)``, then ``track_sh``) runs along ``+/- d``.

Expected values are the planted direction and the FA formula; DIPY is the tracker. SimNIBS
and DIPY run in a child interpreter (``tests/conftest.py`` mocks them in-process). Reproduce::

    docker run --rm --platform linux/amd64 --entrypoint simnibs_python -v "$PWD":/ti-toolbox \\
      -w /ti-toolbox idossha/ti-toolbox:v3.1.3 -m pytest tests/numerical/test_tract_frames.py -q

Deliberately elsewhere: the world -> voxel direction algebra alone (host,
``tests/test_tract_geometry.py``).
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

_SETUP = """
import numpy as np
from tit.pre.qsi import tensor_math as tm
from tit.tract import tracking as tr
from tit.tract.config import TrackConfig

d = np.array([0.48, -0.6, 0.64])
l1, l2 = 1.7e-3, 0.3e-3
D = l1 * np.outer(d, d) + l2 * (np.eye(3) - np.outer(d, d))
rot = np.linalg.qr(np.random.default_rng(5).normal(size=(3, 3)))[0]
lin = {
    "LPS": np.diag([-1.0, -1.0, 1.0]),
    "PSR": np.array([[0, 0, 1.0], [-1.0, 0, 0], [0, 1.0, 0]]),
    "oblique": rot @ np.diag([1.0, 1.25, 1.5]),
}
def affine(m):
    a = np.eye(4); a[:3, :3] = m; a[:3, 3] = [10.0, -20.0, 5.0]; return a
def directions(sl):
    v = np.array([s[-1] - s[0] for s in sl if len(s) > 4])
    return np.abs(v @ d) / np.linalg.norm(v, axis=1)
cfg = TrackConfig(n_seeds=300, step_mm=0.5, min_length_mm=5.0, max_length_mm=250.0,
                  max_angle=30.0)
"""


def _child(code: str) -> str:
    pytest.importorskip("dipy", reason="skipping: needs the image (SimNIBS, DIPY)")
    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(_SETUP + code)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": os.getcwd()},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


def test_frame_check_reference_is_the_planted_direction_from_the_dwi_alone():
    # dti_reference fits its own tensor on the QSIPrep-style files (no m2m tensor): b0 +
    # b1000 + b3000 uses b <= 1500; a b0 + b3000 scan falls back to the lowest shell.
    out = _child("""
import tempfile, os
import nibabel as nib
rng = np.random.default_rng(2)
g = rng.normal(size=(60, 3)); g /= np.linalg.norm(g, axis=1, keepdims=True)
evals = np.array([l1, l2, l2])
fa_exact = np.sqrt(0.5) * np.sqrt(2 * (l1 - l2) ** 2) / np.sqrt(np.sum(evals ** 2))
shape = (12, 12, 12)
tmp = tempfile.mkdtemp()
for shells, bmax, used in (((1000.0, 3000.0), 1500.0, [1000.0]), ((3000.0,), 3100.0, [3000.0])):
    bvals = np.r_[np.zeros(4), np.repeat(shells, 30)]
    bvecs = np.vstack([np.zeros((4, 3)), np.tile(g[:30], (len(shells), 1))])
    signal = 1000.0 * np.exp(-bvals * np.einsum("ni,ij,nj->n", bvecs, D, bvecs))
    np.savetxt(os.path.join(tmp, "dwi.b"), np.column_stack([bvecs, bvals]))
    for name, m in lin.items():
        A = affine(m)
        nib.save(nib.Nifti1Image(np.broadcast_to(signal, shape + (len(bvals),)).astype(np.float32), A),
                 os.path.join(tmp, "dwi.nii.gz"))
        nib.save(nib.Nifti1Image(np.ones(shape, np.uint8), A), os.path.join(tmp, "mask.nii.gz"))
        (e1, fa, aff), rec = tr.dti_reference(os.path.join(tmp, "dwi.nii.gz"),
                                              os.path.join(tmp, "dwi.b"),
                                              os.path.join(tmp, "mask.nii.gz"))
        assert np.allclose(np.abs(e1.reshape(-1, 3) @ d), 1.0, atol=1e-5), name
        assert np.allclose(fa, fa_exact, rtol=1e-4), (name, fa.flat[0], fa_exact)
        assert rec["bmax"] == bmax and rec["shells_b"] == used, rec
        # a straight streamline along d scores |t . e1| = 1
        centre = aff[:3, :3] @ (np.array(shape) / 2) + aff[:3, 3]
        line = centre + np.outer(np.linspace(-3, 3, 13), d)
        assert tr.coherence([line], e1, fa, aff)["median_abs_cos"] > 0.9999
        print(shells, name, round(float(fa.flat[0]), 5), rec["bmax"])
""")
    print(out)


def test_csd_tracks_along_the_planted_direction():
    out = _child("""
rng = np.random.default_rng(1)
g = rng.normal(size=(60, 3)); g /= np.linalg.norm(g, axis=1, keepdims=True)
bvecs = np.vstack([np.zeros((6, 3)), g]); bvals = np.r_[np.zeros(6), np.full(60, 3000.0)]
signal = 1000.0 * np.exp(-bvals * np.einsum("ni,ij,nj->n", bvecs, D, bvecs))
shape = (24, 24, 24)
data = np.broadcast_to(signal, shape + (66,)).astype(np.float32)
wm = np.ones(shape, bool); none = np.zeros(shape, bool)
for name, m in lin.items():
    A = affine(m)
    shm, info = tr.fit_csd(data, A, bvals, bvecs, wm, wm, sh_order=8, n_jobs=1)
    sl, _ = tr.track_sh(shm, wm, none, none, A, wm, cfg, n_seeds=300, n_jobs=1,
                        return_all=True)
    cos = directions(sl)
    assert len(cos) > 50 and np.median(cos) > 0.995, (name, len(cos), np.median(cos))
    print(name, len(cos), round(float(np.median(cos)), 5))
""")
    print(out)


def test_act_keeps_a_tract_leaving_the_mask_through_the_brain_stem_only():
    # A WM slab with fibres along z, grey matter on top (z >= 34), and a DWI brain mask
    # that stops at z = 10, the way CHN's mask stops above the bottom of the brain stem.
    # Below the mask: brain stem (aseg 16), or CSF. Streamlines must be kept in the first
    # case only, and only with the inferior exit (without it, the old behaviour, none are).
    out = _child("""
rng = np.random.default_rng(1)
g = rng.normal(size=(60, 3)); g /= np.linalg.norm(g, axis=1, keepdims=True)
bvecs = np.vstack([np.zeros((6, 3)), g]); bvals = np.r_[np.zeros(6), np.full(60, 3000.0)]
dz = np.array([0.0, 0.0, 1.0])
Dz = l1 * np.outer(dz, dz) + l2 * (np.eye(3) - np.outer(dz, dz))
signal = 1000.0 * np.exp(-bvals * np.einsum("ni,ij,nj->n", bvecs, Dz, bvecs))
shape = (16, 16, 40)
data = np.broadcast_to(signal, shape + (66,)).astype(np.float32)
A = affine(lin["LPS"])
i, j, k = np.indices(shape)
side = (i < 2) | (i > 13) | (j < 2) | (j > 13)  # CSF walls: no escape sideways
brain = k >= 10
gm = (k >= 34) & ~side
aseg = np.where(k < 10, 16, 2)
cfg2 = TrackConfig(n_seeds=200, step_mm=0.5, min_length_mm=5.0, max_length_mm=250.0)
shm, _ = tr.fit_csd(data, A, bvals, bvecs, brain, brain & ~gm & ~side, n_jobs=1)
seeds = brain & ~gm & ~side & (k < 30)
results = {}
for case, wm, csf in (
    ("brainstem", ~gm & ~side, side),            # WM continues below the mask
    ("csf", ~gm & ~side & brain, side | ~brain),  # the tract ends in CSF below the mask
):
    for use_exit in (False, True):
        ex = tr.inferior_exit(np.where(csf & ~side, 24, aseg), brain) if use_exit else None
        sl, _ = tr.track_sh(shm, wm, gm, csf, A, seeds, cfg2, n_seeds=200, n_jobs=1,
                            exit_mask=ex)
        lowest = min((s[:, 2].min() for s in sl), default=np.nan)
        results[(case, use_exit)] = len(sl)
        if sl:  # kept streamlines end where ACT says they may: ENDPOINT at both ends
            # (end_states reads the state back one step along the last segment; the step
            # that stopped DIPY may turn, so a few per cent are misread)
            st = tr.end_states(sl, tr.act_criterion(wm, gm, csf, ex), A)
            assert np.mean(st == "ENDPOINT") > 0.95, np.unique(st, return_counts=True)
        print(case, use_exit, len(sl), lowest)
assert results[("brainstem", True)] > 100   # kept: they leave through the brain-stem exit
assert results[("brainstem", False)] == 0   # the defect: dropped at the mask edge
assert results[("csf", True)] == 0          # still rejected: ending in CSF is invalid
assert results[("csf", False)] == 0
""")
    print(out)
