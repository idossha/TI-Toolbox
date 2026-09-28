"""DTI advisories, slice orientation and the report size budget, on synthetic phantoms.

Pins (2026-09-28, ARCHITECTURE.md §14; report proposal §4.4). Every expectation comes from how the
phantom was built, not from the code under test:

* ``canonical`` + ``oriented`` put a marker planted at world left on image left, for RAS, LAS and
  PSR grids (nibabel builds the grids);
* ``flip_test`` scores the gradient table as written best on a curved-fibre phantom, and finds
  ``flip x`` when the phantom's tensors were mirrored in x;
* ``tract_orientation`` gives 1.0 in the corpus-callosum box and 0.0 in the corticospinal box for
  a field of pure left–right fibres;
* ``residual_shift`` recovers a planted 3 mm posterior shift of FA against WM (coarse-to-fine search);
* ``vn_eigenvalues`` equals SimNIBS 4.6 ``cond2elmdata(normalize=True)`` on random tensors
  (skipped without SimNIBS: run it in the image);
* the rendered report of a phantom stays under the 2.5 MB budget.

Reproduce: ``simnibs_python -m pytest tests/numerical/test_dti_advisories.py`` (or any Python with
real numpy, scipy, nibabel, matplotlib and Pillow; the SimNIBS comparison needs the image).
"""

import numpy as np
import pytest

from tit.pre.qsi import tensor_math as tm

EVALS = np.array([1.7e-3, 0.3e-3, 0.3e-3])


def _prolate(v: np.ndarray) -> np.ndarray:
    """World tensors (..., 3, 3) with principal axis *v* (unit, (..., 3)) and EVALS."""
    v = v / np.linalg.norm(v, axis=-1, keepdims=True)
    return EVALS[1] * np.eye(3) + (EVALS[0] - EVALS[1]) * v[..., :, None] * v[..., None, :]


def _world(shape, affine) -> np.ndarray:
    ijk = np.indices(shape, dtype=float).reshape(3, -1)
    return ((affine[:3, :3] @ ijk).T + affine[:3, 3]).reshape(tuple(shape) + (3,))


@pytest.mark.parametrize("codes", [("R", "A", "S"), ("L", "A", "S"), ("P", "S", "R")])
def test_marker_at_world_left_lands_on_image_left(codes):
    import nibabel as nib
    from nibabel.orientations import apply_orientation, axcodes2ornt, inv_ornt_aff, io_orientation, ornt_transform

    from tit.plotting import slices as sl

    ras_aff = np.diag([1.0, 1.0, 1.0, 1.0])
    ras_aff[:3, 3] = [-20, -25, -15]
    ras = np.zeros((41, 51, 31))
    ras[5, 40, 15] = 1  # world x = -15 (left), y = +15 (anterior)
    tr = ornt_transform(io_orientation(ras_aff), axcodes2ornt(codes))
    data = apply_orientation(ras, tr)
    affine = ras_aff @ inv_ornt_aff(tr, ras.shape)
    assert nib.aff2axcodes(affine) == codes
    canon, canon_aff = sl.canonical(data, affine)
    i, j, k = np.argwhere(canon)[0]
    assert (canon_aff @ [i, j, k, 1])[:3].tolist() == [-15.0, 15.0, 0.0]
    row, col = np.argwhere(sl.oriented(canon, 2, k))[0]
    assert col < canon.shape[0] / 2 and row < canon.shape[1] / 2  # left on the left, anterior up


def _vortex_field(flip_x: bool):
    """Prolate tensors along circles about z (a curved tract), all WM with high FA."""
    shape = (48, 48, 8)
    affine = np.eye(4)
    affine[:3, 3] = [-23.5, -23.5, -3.5]
    w = _world(shape, affine)
    r = np.hypot(w[..., 0], w[..., 1])
    v = np.stack([-w[..., 1], w[..., 0], 0.15 * np.ones(shape)], -1)
    t = _prolate(v)
    if flip_x:  # what a gradient table with the x sign wrong does to every tensor
        f = np.diag([-1.0, 1.0, 1.0])
        t = f @ t @ f
    t[(r < 6) | (r > 21)] = 0
    labels = np.where((r >= 6) & (r <= 21), 1, 0).astype(np.uint8)
    fa = np.zeros(shape, np.float32)
    fa[labels == 1] = tm.fa_md(EVALS[None])[0][0]
    return tm.unsym(t).astype(np.float32), affine, fa, labels


def test_flip_test_prefers_the_table_as_written():
    from tit.pre.qsi.dti_advisories import IDENTITY, flip_test

    t6w, affine, fa, labels = _vortex_field(flip_x=False)
    result = flip_test(t6w, affine, fa, labels)
    assert result["best"] == IDENTITY and len(result["scores"]) == 24


def test_flip_test_finds_a_planted_x_flip():
    from tit.pre.qsi.dti_advisories import flip_test

    result = flip_test(*_vortex_field(flip_x=True))
    assert result["best"] == "xyz flip x"


def test_tract_orientation_on_pure_left_right_fibres():
    from tit.pre.qsi.dti_advisories import tract_orientation

    shape = (70, 50, 60)
    affine = np.eye(4)
    affine[:3, 3] = [-35, -40, -20]
    mni = _world(shape, affine).astype(np.float32)
    t6w = np.broadcast_to(tm.unsym(_prolate(np.array([1.0, 0.0, 0.0]))), shape + (6,)).astype(np.float32)
    out = tract_orientation(t6w, mni)
    assert out["cc"]["n"] > 0 and out["cc"]["frac_expected"] == 1.0
    assert out["cst"]["n"] > 0 and out["cst"]["frac_expected"] == 0.0


def test_residual_shift_recovers_a_planted_posterior_shift():
    from scipy.ndimage import gaussian_filter

    from tit.pre.qsi.dti_advisories import residual_shift

    shape = (100, 120, 100)
    affine = np.eye(4)
    affine[:3, 3] = [-50, -60, -40]
    mni = _world(shape, affine).astype(np.float32)
    brain = np.linalg.norm(mni / [48, 58, 48], axis=-1) < 1
    noise = gaussian_filter(np.random.default_rng(1).standard_normal(shape), 2.5)
    wm = brain & (noise > 0)
    labels = np.where(wm, 1, np.where(brain, 2, 0)).astype(np.uint8)
    fa = np.zeros(shape, np.float32)
    fa[:, :-3, :] = 0.1 + 0.6 * wm[:, 3:, :]  # FA(p) = WM(p + 3 mm anterior): FA sits 3 mm posterior
    out = residual_shift(fa, labels, affine, mni)
    assert len(out) == 6
    for region in out.values():
        assert (region["best_ap_mm"], region["best_si_mm"]) == (3.0, 0.0)


_VN_VS_SIMNIBS = """
import numpy as np
from simnibs.mesh_tools import mesh_io
from simnibs.utils.cond_utils import cond2elmdata
from tit.pre.qsi import tensor_math as tm
from tit.pre.qsi.dti_advisories import MAX_COND, MAX_RATIO, vn_eigenvalues

rng = np.random.default_rng(3)
c_wm = 0.126
mesh = mesh_io.Msh(mesh_io.Nodes(np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float) + 2.0),
                   mesh_io.Elements(tetrahedra=np.array([[1, 2, 3, 4]])))
mesh.elm.tag1 = mesh.elm.tag2 = np.array([1])
affine = np.eye(4)
worst = 0.0
for _ in range(40):
    q, _ = np.linalg.qr(rng.standard_normal((3, 3)))
    evals = np.sort(rng.uniform(0.05e-3, 2.5e-3, 3))[::-1]
    volume = np.broadcast_to(tm.world_to_simnibs(q @ np.diag(evals) @ q.T, affine), (6, 6, 6, 6)).copy()
    cond = cond2elmdata(mesh, [c_wm] * 10, anisotropy_volume=volume, affine=affine, aniso_tissues=[1],
                        normalize=True, max_ratio=MAX_RATIO, max_cond=MAX_COND)
    simnibs = np.sort(np.linalg.eigvalsh(cond.value[0].reshape(3, 3)))[::-1]
    ours = vn_eigenvalues(evals[None], c_wm)[0]
    np.testing.assert_allclose(ours, simnibs, rtol=1e-6)
    worst = max(worst, float(np.max(np.abs(ours / simnibs - 1))))
print("max relative difference", worst)
"""


def test_vn_conductivity_equals_simnibs():
    """40 random tensors (eigenvalues 0.05-2.5e-3 mm^2/s, so both clamps bind sometimes) through the
    real ``cond2elmdata(normalize=True)`` on a one-element mesh; the constant grid makes SimNIBS's
    trilinear interpolation exact. Runs in a subprocess because the host conftest mocks simnibs."""
    import subprocess
    import sys
    from pathlib import Path

    if subprocess.run([sys.executable, "-c", "import simnibs.utils.cond_utils"], capture_output=True).returncode:
        pytest.skip("skipping: real SimNIBS unavailable; run with simnibs_python in the image")
    result = subprocess.run([sys.executable, "-c", _VN_VS_SIMNIBS], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    print(result.stdout)


def test_phantom_report_is_under_budget(tmp_path):
    pytest.importorskip("matplotlib")
    pytest.importorskip("PIL")
    from tit.pre.qsi.dti_advisories import DtiVolumes, tissue_stats
    from tit.reporting.generators import dti_qc as gen
    from tit.plotting.dti_qc import render_all

    shape = (130, 150, 130)
    affine = np.eye(4)
    affine[:3, 3] = [-65, -85, -55]
    mni = _world(shape, affine).astype(np.float32)
    r = np.linalg.norm(mni / [60, 72, 60], axis=-1)
    labels = np.select([r < 0.6, r < 0.85, r < 1.0], [1, 2, 3], 0).astype(np.uint8)
    rng = np.random.default_rng(0)
    v = rng.standard_normal(shape + (3,))
    t6w = np.where((labels > 0)[..., None], tm.unsym(_prolate(v)), 0).astype(np.float32)
    t1 = np.select([labels == 1, labels == 2, labels == 3], [1.0, 0.6, 0.2], 0.0).astype(np.float32)
    vols = DtiVolumes.from_arrays(affine, t1, labels, t6w, mni)
    images = render_all(vols)
    w, _ = tm.eig_desc(tm.sym(t6w[labels > 0]))
    fa, md = tm.fa_md(w)
    qc = {"ncc_chain": 0.98, "chain_vs_ncc_mm": 0.04, "pct_pd": 100.0, "pct_wm_covered": 100.0, "pct_gm_covered": 100.0,
          "pct_wmgm_zero": 0.0, "wm_md_median": 0.8e-3, "wm_fa_median": 0.4, "n_out_of_brain": 0, "passed": True, "failures": [],
          "thresholds": {"min_ncc": 0.9, "max_chain_vs_ncc_mm": 1.0, "min_pct_pd": 99.0, "max_pct_wmgm_zero": 5.0,
                         "wm_md_range": [0.5e-3, 1.1e-3], "max_out_of_brain": 0},
          "metrics": {"fa_bins": np.linspace(0, 1, 51).tolist(), "md_bins": np.linspace(0, 3e-3, 61).tolist(),
                      "tissue": tissue_stats(fa, md, labels[labels > 0])}}
    html = gen.build_html(qc, images, "phantom")
    assert "Passed all 6 blocking checks" in html
    assert len(html.encode()) < gen.SIZE_BUDGET
