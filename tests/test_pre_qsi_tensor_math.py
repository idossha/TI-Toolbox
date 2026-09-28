"""tit.pre.qsi.tensor_math: frames, ITK parsing, QSIPrep deoblique, chain composition.

Where the numbers come from (2026-09-27):
* The SimNIBS read-back is SimNIBS 4.6 ``cond_utils.cond2elmdata`` (``correct_FSL``)
  pasted verbatim below as ``_simnibs_reads`` -- the reader the stored tensor must
  satisfy, independent of our inverse.
* ITK Euler and deoblique expectations are hand-derived in each test.
* The chain test builds ``X`` from a chosen ``G_true`` exactly as QSIPrep composes
  its transforms (prototype dti_eval proto/synth_roundtrip.py), then inverts.
Real-library (nibabel) agreement of the deoblique step and the full resampling round
trip are in tests/numerical/test_dti_roundtrip.py.
"""

import numpy as np
import pytest

from tit.pre.qsi import tensor_math as tm


def _simnibs_reads(stored6: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """SimNIBS 4.6 cond2elmdata, correct_FSL branch, verbatim."""
    tensors = tm.sym(stored6)
    M = affine[:3, :3] / np.linalg.norm(affine[:3, :3], axis=0)[:, None]
    R = np.eye(3)
    if np.linalg.det(M) > 0:
        R[0, 0] = -1
    M = M.dot(R)
    tensors = tensors.dot(M.T)
    return M.dot(tensors.transpose(2, 1, 0)).transpose(2, 0, 1)


def _rot(axis: int, deg: float) -> np.ndarray:
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))
    i, j = [k for k in range(3) if k != axis]
    r = np.eye(3)
    r[i, i], r[i, j], r[j, i], r[j, j] = c, -s, s, c
    return r


AFFINES = {
    "ras_iso_det+": np.diag([1.0, 1.0, 1.0, 1.0]),
    "psr_det-": np.array(
        [[0, 0, 1.0, -90], [-1.0, 0, 0, 120], [0, 1.0, 0, -100], [0, 0, 0, 1]]
    ),
    "lps_aniso_det-": np.diag([-0.9, -0.9, 1.3, 1.0]),
    "oblique_aniso_det+": np.block(
        [
            [_rot(0, 12) @ _rot(2, -7) @ np.diag([1.0, 1.2, 2.5]), np.zeros((3, 1))],
            [np.zeros((1, 3)), np.ones((1, 1))],
        ]
    ),
}


@pytest.mark.parametrize("name", sorted(AFFINES))
def test_world_to_simnibs_is_read_back_exactly(name):
    affine = AFFINES[name]
    rng = np.random.default_rng(3)
    a = rng.normal(size=(50, 3, 3))
    world = a @ a.transpose(0, 2, 1) + 1e-3 * np.eye(3)
    stored = tm.world_to_simnibs(world, affine)
    assert np.abs(_simnibs_reads(stored, affine) - world).max() < 1e-12
    assert np.abs(tm.simnibs_to_world(stored, affine) - world).max() < 1e-12


def test_simnibs_matrix_flips_x_only_for_positive_determinant():
    # RAS identity: det > 0, so SimNIBS flips x (FSL's radiological convention).
    assert np.allclose(tm.simnibs_fsl_matrix(np.eye(4)), np.diag([-1.0, 1, 1]))
    # LAS: det < 0, the matrix is used as is.
    las = np.diag([-2.0, 2.0, 2.0, 1.0])
    assert np.allclose(tm.simnibs_fsl_matrix(las), np.diag([-1.0, 1.0, 1.0]))


def test_itk_euler_rotation_about_z_with_translation():
    # 90 deg about z, t = (1, 2, 3) LPS, centre 0. RAS (1, 0, 0) = LPS (-1, 0, 0)
    # -> rotate -> (0, -1, 0) -> + t -> (1, 1, 3) LPS = RAS (-1, -1, 3).
    x = tm.itk_euler_to_ras([0, 0, np.pi / 2, 1, 2, 3], [0, 0, 0])
    assert np.allclose(x @ [1, 0, 0, 1], [-1, -1, 3, 1])


def test_itk_euler_order_is_z_x_y():
    # ax = ay = 90 deg: Ry sends LPS x to -z, then Rx sends -z to +y. The opposite
    # order (Ry after Rx) would leave x on -z.
    x = tm.itk_euler_to_ras([np.pi / 2, np.pi / 2, 0, 0, 0, 0], [0, 0, 0])
    # RAS x = LPS -x -> LPS -y = RAS +y
    assert np.allclose(x[:3, :3] @ [1, 0, 0], [0, 1, 0])


def test_itk_centre_is_a_fixed_point():
    centre_lps = np.array([10.0, -4.0, 7.0])
    x = tm.itk_euler_to_ras([0.3, -0.2, 0.9, 0, 0, 0], centre_lps)
    centre_ras = centre_lps * [-1, -1, 1]
    assert np.allclose(x @ np.r_[centre_ras, 1], np.r_[centre_ras, 1])


def test_itk_affine_parameters():
    # 12-parameter AffineTransform: identity matrix + translation (2, 0, -1) LPS.
    x = tm.itk_euler_to_ras([1, 0, 0, 0, 1, 0, 0, 0, 1, 2, 0, -1], [5, 5, 5])
    assert np.allclose(
        x, np.array([[1, 0, 0, -2], [0, 1, 0, 0], [0, 0, 1, -1], [0, 0, 0, 1]])
    )


def test_itk_rejects_unknown_parameter_count():
    with pytest.raises(ValueError):
        tm.itk_euler_to_ras([0, 0, 0], [0, 0, 0])


def test_deoblique_ras_grid_is_reoriented_to_lps():
    # RAS 1 mm, shape (10, 20, 30): LPS flips x and y, so the new origin is the old
    # voxel (9, 19, 0).
    affine = np.eye(4)
    affine[:3, 3] = [-5, -10, -15]
    a_lps, a_anat = tm.qsiprep_anat_affines(affine, (10, 20, 30))
    expected = np.array(
        [[-1, 0, 0, 4], [0, -1, 0, 9], [0, 0, 1, -15], [0, 0, 0, 1]], dtype=float
    )
    assert np.allclose(a_lps, expected)
    assert np.allclose(a_anat, expected)  # not oblique: nothing to replace


def test_deoblique_replaces_oblique_rotation_keeping_translation():
    affine = np.eye(4)
    affine[:3, :3] = _rot(2, 6) @ np.diag([-1.0, -1.0, 1.2])  # LPS-ish, oblique
    affine[:3, 3] = [3, 4, 5]
    a_lps, a_anat = tm.qsiprep_anat_affines(affine, (8, 8, 8))
    assert np.allclose(a_lps, affine)  # already LPS: no reorientation
    assert np.allclose(a_anat[:3, :3], np.diag([-1.0, -1.0, 1.2]))
    assert np.allclose(a_anat[:3, 3], [3, 4, 5])


def test_chain_recovers_known_map():
    affine = np.eye(4)
    affine[:3, :3] = _rot(0, 3) @ _rot(1, -2)  # oblique RAS raw T1
    affine[:3, 3] = [-90, -120, -100]
    shape = (176, 256, 256)
    a_lps, a_anat = tm.qsiprep_anat_affines(affine, shape)
    anat_to_raw = a_lps @ np.linalg.inv(a_anat)
    raw_to_acpc = np.eye(4)
    raw_to_acpc[:3, :3] = _rot(0, 20) @ _rot(1, -4) @ _rot(2, 6)
    raw_to_acpc[:3, 3] = [3.5, -14.0, 9.0]
    g_true = np.linalg.inv(raw_to_acpc)
    x = raw_to_acpc @ anat_to_raw  # QSIPrep's from-ACPC_to-anat, RAS
    g = tm.acpc_to_t1_world(affine, shape, x)
    assert np.abs(g - g_true).max() < 1e-12


def test_polar_rotation_of_rigid_map_is_its_rotation():
    rigid = np.eye(4)
    rigid[:3, :3] = _rot(1, 33)
    rigid[:3, 3] = [1, 2, 3]
    assert np.allclose(tm.polar_rotation(rigid), _rot(1, 33))


def test_fa_md_of_known_eigenvalues():
    fa, md = tm.fa_md(np.array([[1.7e-3, 0.3e-3, 0.3e-3], [1e-3, 1e-3, 1e-3]]))
    # FA = sqrt(1.5) * |lambda - mean| / |lambda|, mean = 2.3/3 e-3.
    dev = np.array([1.7, 0.3, 0.3]) - 2.3 / 3
    expected = np.sqrt(1.5) * np.linalg.norm(dev) / np.sqrt(1.7**2 + 0.18)
    assert fa[0] == pytest.approx(expected)
    assert fa[1] == pytest.approx(0.0)
    assert md == pytest.approx([0.7667e-3, 1e-3], rel=1e-3)
