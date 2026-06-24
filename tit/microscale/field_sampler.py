#!/usr/bin/env simnibs_python
"""Sample SimNIBS E-fields at neuron compartments and build quasipotentials.

This module is the NEURON-free heart of :mod:`tit.microscale`.  It only needs
NumPy for the coupling math; SimNIBS is imported lazily inside
:func:`load_field` / :func:`sample_at` so the quasipotential helpers can be unit
tested without the heavy stack.

Units and coordinate conventions
--------------------------------
* SimNIBS meshes use **millimetres**; NEURON morphologies use **micrometres**.
  Convert with :func:`mm_to_um` / :func:`um_to_mm` and keep a single frame
  (SimNIBS subject space) throughout.  A 1000x error here silently places the
  neuron in the wrong tissue.
* SimNIBS reports ``E`` in **V/m**.  Note ``1 V/m == 1 mV/mm``, so dotting a
  V/m field with a displacement expressed in **mm** yields a potential directly
  in **mV** -- which is exactly the unit NEURON's ``e_extracellular`` wants.
  The quasipotential helpers below take coordinates in micrometres and fold in
  the 1e-3 mm-per-um factor explicitly.

Coupling (quasi-static approximation)
-------------------------------------
The extracellular potential at a compartment is the line integral of the field
from a reference point to that compartment, ``V_e = -∫ E·dl``.  Two
approximations are provided:

* :func:`uniform_quasipotential` -- the quasi-uniform assumption: the field is
  constant over the (small) cell, taken at the soma.  ``V_e = -E·(x - x_soma)``.
  This is the standard first-order coupling (Wang et al. 2022) and the default.
* :func:`path_quasipotential` -- the full-field integral along the morphology,
  for when curvature/boundaries make the uniform assumption too coarse.
"""

from __future__ import annotations

import numpy as np

#: Millimetres per micrometre.  ``E`` in V/m equals mV/mm, so multiplying a
#: micrometre displacement by this factor converts a V/m field directly to mV.
_MM_PER_UM: float = 1.0e-3


def mm_to_um(coords_mm: np.ndarray) -> np.ndarray:
    """Convert millimetre coordinates to micrometres.

    Parameters
    ----------
    coords_mm : ndarray
        Coordinates in mm (SimNIBS subject space), shape ``(..., 3)``.

    Returns
    -------
    ndarray
        Coordinates in um (NEURON space), same shape.
    """
    return np.asarray(coords_mm, dtype=float) * 1000.0


def um_to_mm(coords_um: np.ndarray) -> np.ndarray:
    """Convert micrometre coordinates to millimetres.

    Parameters
    ----------
    coords_um : ndarray
        Coordinates in um (NEURON space), shape ``(..., 3)``.

    Returns
    -------
    ndarray
        Coordinates in mm (SimNIBS subject space), same shape.
    """
    return np.asarray(coords_um, dtype=float) / 1000.0


def uniform_quasipotential(
    e_vec: np.ndarray,
    seg_coords_um: np.ndarray,
    soma_coord_um: np.ndarray,
) -> np.ndarray:
    """Quasipotential under the quasi-uniform field assumption.

    The field ``e_vec`` (V/m) is treated as constant over the cell and the
    extracellular potential at each segment is ``V_e = -E·(x - x_soma)``.  With
    displacements in micrometres and ``E`` in V/m (== mV/mm), the result is in
    **mV** (NEURON ``e_extracellular`` units).

    Parameters
    ----------
    e_vec : ndarray, shape (3,)
        Field vector at the soma in V/m.
    seg_coords_um : ndarray, shape (M, 3)
        Segment centre coordinates in um.
    soma_coord_um : ndarray, shape (3,)
        Soma (reference) coordinate in um.

    Returns
    -------
    ndarray, shape (M,)
        Extracellular potential per segment in mV.
    """
    e_vec = np.asarray(e_vec, dtype=float).reshape(3)
    seg = np.asarray(seg_coords_um, dtype=float).reshape(-1, 3)
    soma = np.asarray(soma_coord_um, dtype=float).reshape(3)
    # displacement (um) -> mm via _MM_PER_UM, then dot V/m == mV/mm -> mV
    disp_mm = (seg - soma) * _MM_PER_UM
    return -(disp_mm @ e_vec)


def path_quasipotential(
    e_per_seg: np.ndarray,
    seg_coords_um: np.ndarray,
    parent_index: np.ndarray,
    root: int = 0,
) -> np.ndarray:
    """Quasipotential by integrating the (spatially varying) field along the tree.

    Integrates ``V_e = -∫ E·dl`` from *root* outward along the morphology, using
    the midpoint field on each parent->child link.  The root's potential is 0.

    Parameters
    ----------
    e_per_seg : ndarray, shape (M, 3)
        Field vector at each segment in V/m.
    seg_coords_um : ndarray, shape (M, 3)
        Segment centre coordinates in um.
    parent_index : ndarray, shape (M,)
        Index of each segment's parent.  The root points to itself (or to a
        negative value); links are walked in increasing index order, so the
        morphology must be topologically sorted (parents before children), as
        NEURON's ``SectionList`` traversal provides.
    root : int, optional
        Index of the reference segment (potential 0).  Default 0.

    Returns
    -------
    ndarray, shape (M,)
        Extracellular potential per segment in mV.
    """
    e = np.asarray(e_per_seg, dtype=float).reshape(-1, 3)
    coords = np.asarray(seg_coords_um, dtype=float).reshape(-1, 3)
    parent = np.asarray(parent_index).reshape(-1).astype(int)
    n = coords.shape[0]
    v = np.zeros(n, dtype=float)

    for i in range(n):
        if i == root:
            continue
        p = parent[i]
        if p < 0 or p == i:
            # Disconnected/root-like node: leave at 0.
            continue
        # midpoint field on the link, displacement (um) -> mm
        e_mid = 0.5 * (e[i] + e[p])
        disp_mm = (coords[i] - coords[p]) * _MM_PER_UM
        v[i] = v[p] - (disp_mm @ e_mid)
    return v


def rotation_align(source_axis: np.ndarray, target_axis: np.ndarray) -> np.ndarray:
    """Rotation matrix that rotates *source_axis* onto *target_axis*.

    Used to orient a neuron model (built along a canonical local axis, e.g. the
    apical +z) so its principal axis follows the local cortical surface normal.
    Uses Rodrigues' formula; handles the antiparallel case.

    Parameters
    ----------
    source_axis, target_axis : ndarray, shape (3,)
        Direction vectors (need not be unit length; zero-length is rejected).

    Returns
    -------
    ndarray, shape (3, 3)
        Rotation matrix ``R`` with ``R @ source_unit ≈ target_unit``.
    """
    a = np.asarray(source_axis, dtype=float).reshape(3)
    b = np.asarray(target_axis, dtype=float).reshape(3)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        raise ValueError("axes must be non-zero")
    a = a / na
    b = b / nb
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = float(np.linalg.norm(v))
    if s == 0:
        # Parallel or antiparallel.
        if c > 0:
            return np.eye(3)
        # 180 deg: rotate about any axis perpendicular to a.
        perp = np.array([1.0, 0.0, 0.0])
        if abs(a[0]) > 0.9:
            perp = np.array([0.0, 1.0, 0.0])
        axis = np.cross(a, perp)
        axis /= np.linalg.norm(axis)
        k = _skew(axis)
        return np.eye(3) + 2.0 * (k @ k)
    k = _skew(v)
    return np.eye(3) + k + k @ k * ((1.0 - c) / (s * s))


def _skew(v: np.ndarray) -> np.ndarray:
    """Skew-symmetric cross-product matrix of a 3-vector."""
    x, y, z = v
    return np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])


def _rotation_about_axis(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotation matrix of *angle_rad* about *axis* (Rodrigues' formula).

    Parameters
    ----------
    axis : ndarray, shape (3,)
        Rotation axis (need not be unit length; zero-length is rejected).
    angle_rad : float
        Rotation angle in radians (right-hand rule about *axis*).

    Returns
    -------
    ndarray, shape (3, 3)
        Rotation matrix.
    """
    a = np.asarray(axis, dtype=float).reshape(3)
    n = np.linalg.norm(a)
    if n == 0:
        raise ValueError("axis must be non-zero")
    a = a / n
    k = _skew(a)
    return np.eye(3) + np.sin(angle_rad) * k + (1.0 - np.cos(angle_rad)) * (k @ k)


def place_morphology(
    local_coords_um: np.ndarray,
    soma_local_um: np.ndarray,
    target_um: np.ndarray,
    normal: np.ndarray,
    source_axis: np.ndarray = (0.0, 0.0, 1.0),
    azimuth_deg: float = 0.0,
) -> np.ndarray:
    """Place a neuron morphology at a target with a given orientation.

    Rotates the model's canonical axis onto *normal*, optionally spins the
    morphology about *normal* by *azimuth_deg* (to marginalize the unconstrained
    tangential angle), then translates so the soma lands on *target_um*.

    Parameters
    ----------
    local_coords_um : ndarray, shape (M, 3)
        Segment coordinates in the model's local frame (um).
    soma_local_um : ndarray, shape (3,)
        Soma coordinate in the local frame (um).
    target_um : ndarray, shape (3,)
        Where to place the soma in world space (um).
    normal : ndarray, shape (3,)
        Desired direction of the model's principal axis (e.g. cortical normal).
    source_axis : ndarray, shape (3,), optional
        The model's canonical axis in local space.  Default apical ``+z``.
    azimuth_deg : float, optional
        Additional rotation (degrees) about *normal* applied after the
        axis alignment.  Default ``0.0`` (no extra spin), so existing callers
        are unaffected.

    Returns
    -------
    ndarray, shape (M, 3)
        Segment coordinates in world space (um), soma at *target_um*.
    """
    local = np.asarray(local_coords_um, dtype=float).reshape(-1, 3)
    soma_local = np.asarray(soma_local_um, dtype=float).reshape(3)
    target = np.asarray(target_um, dtype=float).reshape(3)
    r = rotation_align(np.asarray(source_axis, dtype=float), normal)
    if azimuth_deg:
        # Spin about the (post-alignment) principal axis = the world normal.
        r = _rotation_about_axis(normal, np.radians(azimuth_deg)) @ r
    rotated = (local - soma_local) @ r.T
    return rotated + target


def load_field(mesh_path: str, field: str = "E"):
    """Read a SimNIBS mesh and return ``(mesh, field_values)``.

    Parameters
    ----------
    mesh_path : str
        Path to a ``.msh`` file (e.g. an HF pair mesh ``{sid}_TDCS_1_{cond}.msh``
        carrying per-element ``E`` vectors).
    field : str, optional
        Field name to extract.  Default ``"E"``.

    Returns
    -------
    tuple
        ``(mesh, values)`` where *values* is an ``(N, 3)`` (vector) or ``(N,)``
        (scalar) array.

    Raises
    ------
    KeyError
        If *field* is not present on the mesh.
    """
    from simnibs.mesh_tools import mesh_io

    mesh = mesh_io.read_msh(mesh_path)
    if field not in mesh.field:
        raise KeyError(
            f"Field {field!r} not in mesh {mesh_path!r}; available: "
            f"{list(mesh.field.keys())}"
        )
    return mesh, np.asarray(mesh.field[field].value)


def sample_at(mesh, coords_mm: np.ndarray, field: str = "E") -> np.ndarray:
    """Interpolate a mesh field at arbitrary coordinates.

    Uses SimNIBS's native scattered interpolation (linear within the tetrahedral
    FEM element containing each point); no ANTs/FSL needed.

    Parameters
    ----------
    mesh : simnibs Msh
        Mesh carrying *field* (as returned by :func:`load_field`).
    coords_mm : ndarray, shape (M, 3)
        Query coordinates in mm (SimNIBS subject space).
    field : str, optional
        Field name to sample.  Default ``"E"``.

    Returns
    -------
    ndarray
        Sampled values, shape ``(M, 3)`` for a vector field or ``(M,)`` for a
        scalar field.  Points outside the mesh are filled with 0.
    """
    coords = np.asarray(coords_mm, dtype=float).reshape(-1, 3)
    data = mesh.field[field]
    # ElementData/NodeData both expose interpolate_scattered in SimNIBS.
    values = data.interpolate_scattered(coords, out_fill=0.0)
    return np.asarray(values)
