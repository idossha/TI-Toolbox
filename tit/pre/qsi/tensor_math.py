"""Tensor and transform algebra for the DTI -> SimNIBS path (numpy only).

Conventions:

* "world" is scanner RAS in mm (the NIfTI sform), the frame SimNIBS meshes live in.
  A tensor field held in memory is always a world-frame ``(..., 3, 3)`` array.
* SimNIBS ``cond2elmdata(correct_FSL=True)`` reads a stored 6-vector ``S`` as
  ``T_world = M S M^T`` with ``M`` from :func:`simnibs_fsl_matrix`. We store
  ``S = inv(M) T_world inv(M)^T`` with *that exact* ``M``, so the round trip is exact
  for any output affine, isotropic or not.
* An ITK/ANTs transform named ``from-A_to-B`` maps points of B (the fixed image) to A.
  ITK stores it in LPS as ``y = R (x - c) + c + t``.
"""

from __future__ import annotations

import numpy as np

#: FSL / SimNIBS upper-triangle order: xx xy xz yy yz zz.
FSL_ORDER = ((0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2))

_LPS_FLIP = np.diag([-1.0, -1.0, 1.0, 1.0])


def sym(t6: np.ndarray) -> np.ndarray:
    """``(..., 6)`` upper triangle in FSL order -> ``(..., 3, 3)`` symmetric tensors."""
    t6 = np.asarray(t6)
    out = np.empty(t6.shape[:-1] + (3, 3), dtype=np.float64)
    for k, (i, j) in enumerate(FSL_ORDER):
        out[..., i, j] = out[..., j, i] = t6[..., k]
    return out


def unsym(tensors: np.ndarray) -> np.ndarray:
    """``(..., 3, 3)`` -> ``(..., 6)`` upper triangle in FSL order."""
    return np.stack([tensors[..., i, j] for i, j in FSL_ORDER], axis=-1)


def rotate(tensors: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """``matrix @ T @ matrix.T`` for every tensor in a field."""
    return np.einsum("ij,...jk,lk->...il", matrix, tensors, matrix)


def simnibs_fsl_matrix(affine: np.ndarray) -> np.ndarray:
    """Exactly SimNIBS 4.6 ``cond_utils.cond2elmdata`` with ``correct_FSL=True``.

    ``M = A[:3, :3] / colnorm[:, None]`` (rows divided by the column norms, as SimNIBS
    writes it), then ``M = M @ diag(-1, 1, 1)`` when ``det(M) > 0``.
    """
    lin = np.asarray(affine, dtype=np.float64)[:3, :3]
    matrix = lin / np.linalg.norm(lin, axis=0)[:, None]
    if np.linalg.det(matrix) > 0:
        matrix = matrix @ np.diag([-1.0, 1.0, 1.0])
    return matrix


def world_to_simnibs(tensors_world: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """World tensors -> the 6-vectors SimNIBS will read back as those world tensors."""
    return unsym(rotate(tensors_world, np.linalg.inv(simnibs_fsl_matrix(affine))))


def simnibs_to_world(t6: np.ndarray, affine: np.ndarray) -> np.ndarray:
    """Stored 6-vectors -> the world tensors SimNIBS builds from them."""
    return rotate(sym(t6), simnibs_fsl_matrix(affine))


def itk_euler_to_ras(params, center) -> np.ndarray:
    """ITK transform parameters -> 4x4 RAS point map.

    *params* is an ``Euler3DTransform`` (6 values: angles x, y, z in radians, then the
    translation; rotation ``R = Rz @ Rx @ Ry``, ITK's default ZXY order) or an
    ``AffineTransform`` (12 values: the matrix row-major, then the translation).
    *center* is the ITK fixed parameter. Both are in LPS; the result is in RAS.
    """
    p = np.asarray(params, dtype=np.float64).ravel()
    c = np.asarray(center, dtype=np.float64).ravel()[:3]
    if p.size == 6:
        ax, ay, az = p[:3]
        rx = np.array(
            [[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]]
        )
        ry = np.array(
            [[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]]
        )
        rz = np.array(
            [[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]]
        )
        rot, trans = rz @ rx @ ry, p[3:6]
    elif p.size == 12:
        rot, trans = p[:9].reshape(3, 3), p[9:12]
    else:
        raise ValueError(
            f"expected 6 (Euler) or 12 (affine) ITK parameters, got {p.size}"
        )
    lps = np.eye(4)
    lps[:3, :3] = rot
    lps[:3, 3] = c + trans - rot @ c
    return _LPS_FLIP @ lps @ _LPS_FLIP


def _axis_codes(affine: np.ndarray) -> list[tuple[int, int]]:
    """For each voxel axis, the (world axis, sign) it runs along.

    Same assignment as ``nibabel.io_orientation`` (5.x): take the nearest orthogonal
    matrix of the direction cosines, then, strongest voxel axis first, give each the
    world axis of its largest remaining entry. The two only differ from a naive argmax
    near 45 degrees of obliquity.
    """
    lin = affine[:3, :3] / np.linalg.norm(affine[:3, :3], axis=0)
    u, _, vt = np.linalg.svd(lin)
    near = u @ vt
    codes: list[tuple[int, int]] = [(0, 0)] * 3
    for voxel in np.argsort(np.min(-(near**2), axis=0), kind="stable"):
        col = near[:, voxel]
        world = int(np.argmax(np.abs(col)))
        codes[voxel] = (world, 1 if col[world] > 0 else -1)
        near[world, :] = 0
    return codes


def qsiprep_anat_affines(
    affine_raw: np.ndarray, shape
) -> tuple[np.ndarray, np.ndarray]:
    """Reproduce QSIPrep's ``Conform(deoblique_header=True)``: ``(A_lps, A_anat)``.

    QSIPrep reorients the input T1w to LPS (``A_lps``), then *replaces* an oblique
    affine with ``diag(zooms * sign(diag))`` keeping the translation column
    (``A_anat``). The voxel array is unchanged, so
    ``raw world = A_lps @ inv(A_anat) @ anat world``. No transform file records this
    step. Assumes one input T1w and no resize, QSIPrep's behaviour for a single T1w.
    """
    affine_raw = np.asarray(affine_raw, dtype=np.float64)
    target_sign = (-1, -1, 1)  # L, P, S
    new_to_old = np.zeros((4, 4))
    new_to_old[3, 3] = 1.0
    for old_axis, (world, sign) in enumerate(_axis_codes(affine_raw)):
        if sign == target_sign[world]:
            new_to_old[old_axis, world] = 1.0
        else:
            new_to_old[old_axis, world] = -1.0
            new_to_old[old_axis, 3] = shape[old_axis] - 1
    a_lps = affine_raw @ new_to_old
    zooms = np.linalg.norm(a_lps[:3, :3], axis=0)
    a_anat = a_lps.copy()
    a_anat[:3, :3] = np.diag(zooms * np.sign(np.diag(a_lps[:3, :3])))
    return a_lps, a_anat


def acpc_to_t1_world(affine_raw: np.ndarray, shape, acpc_to_anat_ras) -> np.ndarray:
    """4x4 map from QSIPrep ACPC world to raw-T1 (= charm m2m T1) world.

    ``G = A_lps @ inv(A_anat) @ inv(X)``, where *acpc_to_anat_ras* is ``X``, the RAS
    form of QSIPrep's ``from-ACPC_to-anat`` transform (it maps anat points to ACPC).
    """
    a_lps, a_anat = qsiprep_anat_affines(affine_raw, shape)
    return a_lps @ np.linalg.inv(a_anat) @ np.linalg.inv(acpc_to_anat_ras)


def polar_rotation(matrix: np.ndarray) -> np.ndarray:
    """Rotation factor of a 3x3 (or 4x4) linear map (exact for a rigid map)."""
    u, _, vt = np.linalg.svd(np.asarray(matrix)[:3, :3])
    return u @ vt


def eig_desc(tensors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Eigenvalues (descending) and matching eigenvectors (columns)."""
    vals, vecs = np.linalg.eigh(tensors)
    return vals[..., ::-1], vecs[..., :, ::-1]


def fa_md(eigenvalues: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fractional anisotropy and mean diffusivity from ``(..., 3)`` eigenvalues."""
    md = eigenvalues.mean(-1)
    num = np.sqrt(((eigenvalues - md[..., None]) ** 2).sum(-1))
    den = np.sqrt((eigenvalues**2).sum(-1))
    fa = np.where(den > 0, np.sqrt(1.5) * num / np.where(den > 0, den, 1.0), 0.0)
    return fa, md
