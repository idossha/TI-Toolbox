"""DTI route round trip against real nibabel/scipy: QSIPrep ACPC grid -> m2m T1 -> SimNIBS.

Pins (2026-09-27, DECISIONS "DTI via DIPY on QSIPrep output"):
* ``qsiprep_anat_affines`` equals nibabel's own reorientation (``io_orientation`` +
  ``inv_ornt_aff``) and QSIPrep's deoblique rule, for oblique and permuted grids.
* An ITK ``Euler3DTransform`` written by scipy (``Rotation.as_euler("ZXY")``,
  ``savemat``) reads back through ``read_itk_transform`` to the map that was written.
* A fibre phantom placed on a 2 mm LPS ACPC grid with a 20 deg pitch comes back on the
  1 mm oblique RAS m2m grid through the chain with V1 within 3 deg (median) of the
  analytic field, and ``max|G - G_true| < 1e-6``. The ACPC tensors are evaluated from
  the analytic field, not produced by the resampler under test.
* What is stored is read back by SimNIBS's ``correct_FSL`` (pasted verbatim) as the
  world tensor.
* With DIPY installed, the WLS fit on world-frame gradients returns the world tensor.

Reproduce: ``simnibs_python -m pytest tests/numerical/test_dti_roundtrip.py``
(or the host venv with real scipy/nibabel). The CHN real-data leg is
tests/numerical/test_dti_real.py.
"""

import numpy as np
import pytest

from tit.pre.qsi import tensor_math as tm

EVALS = np.array([1.7e-3, 0.3e-3, 0.3e-3])


def _rotation(deg_xyz) -> np.ndarray:
    """Rz @ Ry @ Rx (numpy only: parametrize runs before the real scipy is swapped in)."""
    out = np.eye(3)
    for axis, deg in enumerate(deg_xyz):
        c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
        i, j = [k for k in range(3) if k != axis]
        r = np.eye(3)
        r[i, i], r[i, j], r[j, i], r[j, j] = c, -s, s, c
        out = r @ out
    return out


def _rigid(deg_xyz, shift) -> np.ndarray:
    out = np.eye(4)
    out[:3, :3] = _rotation(deg_xyz)
    out[:3, 3] = shift
    return out


def _fibre_dir(world: np.ndarray) -> np.ndarray:
    """Analytic, smoothly bending fibre direction at world points (..., 3)."""
    x, y, z = world[..., 0], world[..., 1], world[..., 2]
    v = np.stack(
        [np.ones_like(x), 0.5 * np.sin(y / 9.0), 0.4 * np.cos(z / 11.0 + x / 30.0)], -1
    )
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def _tensor_at(world: np.ndarray) -> np.ndarray:
    v1 = _fibre_dir(world)
    helper = np.where(np.abs(v1[..., :1]) < 0.9, [1.0, 0, 0], [0, 1.0, 0])
    v2 = np.cross(v1, helper)
    v2 /= np.linalg.norm(v2, axis=-1, keepdims=True)
    v3 = np.cross(v1, v2)
    basis = np.stack([v1, v2, v3], -1)
    return np.einsum("...ik,k,...jk->...ij", basis, EVALS, basis)


def _world_of(affine, shape):
    ijk = np.indices(shape).reshape(3, -1).T.astype(float)
    return (ijk @ affine[:3, :3].T + affine[:3, 3]).reshape(tuple(shape) + (3,))


def _oblique_raw_affine() -> np.ndarray:
    affine = np.eye(4)
    affine[:3, :3] = _rotation([3.0, -1.5, 2.0])  # det > 0: SimNIBS x-flip branch
    affine[:3, 3] = [-20.0, -22.0, -18.0]
    return affine


RAW_SHAPE = (40, 44, 36)


def _nibabel_anat_affines(affine, shape):
    import nibabel as nib

    ornt = nib.orientations.ornt_transform(
        nib.io_orientation(affine), nib.orientations.axcodes2ornt(("L", "P", "S"))
    )
    a_lps = affine @ nib.orientations.inv_ornt_aff(ornt, shape)
    zooms = np.sqrt((a_lps[:3, :3] ** 2).sum(0))
    a_anat = a_lps.copy()
    a_anat[:3, :3] = np.diag(zooms * np.sign(np.diag(a_lps[:3, :3])))
    return a_lps, a_anat


@pytest.mark.parametrize(
    "affine",
    [
        _oblique_raw_affine(),
        np.array(
            [[0, 0, 1.0, -90], [-1.0, 0, 0, 120], [0, 1.0, 0, -100], [0, 0, 0, 1]]
        ),
        np.block(
            [
                [_rotation([10, -20, 15]) @ np.diag([0.9, 1.1, 1.3]), np.ones((3, 1))],
                [np.zeros((1, 3)), np.ones((1, 1))],
            ]
        ),
    ],
)
def test_deoblique_matches_nibabel(affine):
    ours = tm.qsiprep_anat_affines(affine, RAW_SHAPE)
    theirs = _nibabel_anat_affines(affine, RAW_SHAPE)
    assert np.allclose(ours[0], theirs[0]) and np.allclose(ours[1], theirs[1])


def _write_itk_euler(path, x_ras, centre_lps=(4.0, -3.0, 7.0)):
    """X (RAS) -> an ITK Euler3DTransform .mat, as ANTs writes it (LPS)."""
    import scipy.io as sio
    from scipy.spatial.transform import Rotation

    flip = np.diag([-1.0, -1.0, 1.0, 1.0])
    x = flip @ x_ras @ flip
    az, ax, ay = Rotation.from_matrix(x[:3, :3]).as_euler("ZXY")
    c = np.asarray(centre_lps)
    t = x[:3, 3] - c + x[:3, :3] @ c  # y = R (p - c) + c + t
    sio.savemat(
        str(path),
        {
            "Euler3DTransform_double_3_3": np.array([[ax], [ay], [az], *t[:, None]]),
            "fixed": c[:, None],
        },
        format="4",
    )


@pytest.fixture(scope="module")
def chain_case(tmp_path_factory):
    from tit.pre.qsi.dti_extractor import read_itk_transform

    raw_affine = _oblique_raw_affine()
    a_lps, a_anat = _nibabel_anat_affines(raw_affine, RAW_SHAPE)
    anat_to_raw = a_lps @ np.linalg.inv(a_anat)
    raw_to_acpc = _rigid([20.0, -4.0, 6.0], [3.5, -14.0, 9.0])  # the 20 deg pitch
    g_true = np.linalg.inv(raw_to_acpc)
    xfm = tmp_path_factory.mktemp("xfm") / "from-ACPC_to-anat_mode-image_xfm.mat"
    x_written = raw_to_acpc @ anat_to_raw
    _write_itk_euler(xfm, x_written)
    x_read = read_itk_transform(xfm)
    g = tm.acpc_to_t1_world(raw_affine, RAW_SHAPE, x_read)
    return raw_affine, raw_to_acpc, g_true, g, x_written, x_read


def test_itk_file_reads_back(chain_case):
    *_, x_written, x_read = chain_case
    assert np.abs(x_read - x_written).max() < 1e-9


def test_chain_recovers_known_map(chain_case):
    _, _, g_true, g, *_ = chain_case
    assert np.abs(g - g_true).max() < 1e-6


def _simnibs_reads(stored6, affine):
    """SimNIBS 4.6 cond2elmdata, correct_FSL branch, verbatim."""
    tensors = tm.sym(stored6)
    M = affine[:3, :3] / np.linalg.norm(affine[:3, :3], axis=0)[:, None]
    R = np.eye(3)
    if np.linalg.det(M) > 0:
        R[0, 0] = -1
    M = M.dot(R)
    tensors = tensors.dot(M.T)
    return M.dot(tensors.transpose(2, 1, 0)).transpose(2, 0, 1)


def test_phantom_round_trip(chain_case):
    from tit.pre.qsi.dti_extractor import resample_tensor

    raw_affine, raw_to_acpc, g_true, g, *_ = chain_case
    # 2 mm LPS ACPC grid covering the raw grid's footprint in ACPC space.
    corners = _world_of(raw_affine, RAW_SHAPE).reshape(-1, 3)
    acpc_pts = corners @ raw_to_acpc[:3, :3].T + raw_to_acpc[:3, 3]
    lo, hi = acpc_pts.min(0) - 4, acpc_pts.max(0) + 4
    acpc_affine = np.diag([-2.0, -2.0, 2.0, 1.0])
    acpc_affine[:3, 3] = [hi[0], hi[1], lo[2]]
    acpc_shape = tuple(int(n) for n in np.ceil((hi - lo) / 2) + 1)

    # ACPC tensors from the analytic field: T_acpc(q) = R_P T_raw(G q) R_P^T.
    q = _world_of(acpc_affine, acpc_shape)
    p = q @ g_true[:3, :3].T + g_true[:3, 3]
    acpc_tensors = tm.rotate(_tensor_at(p), raw_to_acpc[:3, :3])
    valid = np.ones(acpc_shape, bool)

    tensors, got_valid = resample_tensor(
        acpc_tensors, acpc_affine, valid, g, RAW_SHAPE, raw_affine
    )
    assert got_valid.mean() > 0.95, "the raw grid lies inside the ACPC grid"

    truth = _tensor_at(_world_of(raw_affine, RAW_SHAPE))[got_valid]
    _, vecs = tm.eig_desc(tensors[got_valid])
    _, true_vecs = tm.eig_desc(truth)
    cos = np.abs(np.einsum("ni,ni->n", vecs[:, :, 0], true_vecs[:, :, 0]))
    angle = np.degrees(np.arccos(np.clip(cos, 0, 1)))
    # Trilinear on 2 mm of a field bending over ~9 mm: the median absorbs interpolation,
    # the 95th percentile bounds the tail near the grid edge.
    assert np.median(angle) < 3.0
    assert np.percentile(angle, 95) < 8.0

    stored = tm.world_to_simnibs(tensors[got_valid], raw_affine)
    read_back = _simnibs_reads(stored, raw_affine)
    assert np.abs(read_back - tensors[got_valid]).max() < 1e-12


def test_dipy_wls_fit_returns_world_tensor(tmp_path):
    pytest.importorskip("dipy", reason="skipping: dipy is not installed here")
    import nibabel as nib

    from tit.pre.qsi.dti_extractor import fit_tensor

    rng = np.random.default_rng(7)
    dirs = rng.normal(size=(30, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    bvals = np.r_[0, 0, [1000.0] * 30, [3000.0] * 10]
    bvecs = np.vstack([np.zeros((2, 3)), dirs, dirs[:10]])
    shape = (6, 5, 4)
    world = _world_of(np.diag([-2.0, -2.0, 2.0, 1.0]), shape)
    truth = _tensor_at(world)
    adc = np.einsum("vi,xyzij,vj->xyzv", bvecs, truth, bvecs)
    signal = 1000.0 * np.exp(-bvals * adc)
    affine = np.diag([-2.0, -2.0, 2.0, 1.0])
    nib.save(
        nib.Nifti1Image(signal.astype(np.float32), affine), str(tmp_path / "dwi.nii")
    )
    nib.save(
        nib.Nifti1Image(np.ones(shape, np.uint8), affine), str(tmp_path / "mask.nii")
    )
    np.savetxt(tmp_path / "dwi.b", np.column_stack([bvecs, bvals]))

    fitted, _, mask = fit_tensor(
        tmp_path / "dwi.nii", tmp_path / "dwi.b", tmp_path / "mask.nii"
    )
    assert mask.all()
    # Noise-free signal: only the b <= 1500 shells are used and the fit is exact.
    assert np.abs(fitted - truth).max() < 1e-8
