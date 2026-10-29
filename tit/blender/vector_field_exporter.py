"""
Exporter for TI/mTI (and optional CH1, CH2, SUM, TI_normal) vector arrows to PLY.
Vectors are placed at face barycenters of the central surface mesh.

Entry point: ``run_vectors(config: VectorConfig)``
"""

from __future__ import annotations

import json
import logging
import os

import numpy as np
import simnibs
import trimesh
from scipy.spatial.transform import Rotation

from tit.blender.config import (
    VectorConfig,
    carrier_mesh_paths,
    central_surface_path,
)
from tit.calc import envelope, envelope_max

logger = logging.getLogger(__name__)

# Baseline visualization scaling so that user-facing defaults of 1.00 produce
# a practical visual size without requiring large/small numeric inputs.
BASE_VECTOR_SCALE = 1.0
BASE_VECTOR_LENGTH = 1.0
BASE_LENGTH_SCALE = 10.0
BASE_VECTOR_WIDTH = 0.10


# ──────────────────────────────────────────────────────────────────────────────
# Config helpers
# ──────────────────────────────────────────────────────────────────────────────


def _read_conductivity(sid: str, sim: str) -> str:
    """Read conductivity type from the simulation's config.json.

    Returns one of ``"scalar"``, ``"vn"``, ``"dir"``, or ``"mc"``.
    Raises if the config is missing — a completed simulation always has one.

    Raises:
        FileNotFoundError: If the simulation has no ``documentation/config.json``.
        ValueError: If the record holds no conductivity, which spells the carrier
            meshes' names (``<sid>_TDCS_<channel>_<conductivity>.msh``).
    """
    from tit.paths import get_path_manager

    pm = get_path_manager()
    config_path = os.path.join(pm.simulation(sid, sim), "documentation", "config.json")
    with open(config_path) as f:
        data = json.load(f)
    cond = data.get("conductivity") if isinstance(data, dict) else None
    if not isinstance(cond, str) or not cond:
        raise ValueError(
            f"No conductivity recorded in {config_path}; it names the carrier meshes "
            "(high_Frequency/mesh/<sid>_TDCS_<channel>_<conductivity>.msh)."
        )
    return cond


# ──────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ──────────────────────────────────────────────────────────────────────────────


def create_arrow(
    position,
    direction,
    magnitude,
    *,
    vector_scale=0.4,
    base_length=1.0,
    shaft_width=0.05,
    length_mode: str = "linear",
    length_scale: float = 1.0,
    anchor: str = "tail",
):
    """Create a small arrow mesh for a vector with configurable length mapping."""
    # Determine arrow length from magnitude
    if length_mode == "linear":
        scaled_length = max(1e-9, float(length_scale) * float(magnitude))
    else:
        magnitude_scale_factor = 0.005
        scaled_length = base_length * (1.0 + magnitude_scale_factor * float(magnitude))

    shaft_length = scaled_length * 0.8
    shaft_radius = shaft_width * 0.5
    head_length = scaled_length * 0.2
    head_radius = shaft_width * 1.5

    shaft = trimesh.creation.cylinder(radius=shaft_radius, height=shaft_length)
    head = trimesh.creation.cone(radius=head_radius, height=head_length)

    # Position cone so its base connects to shaft end
    head.apply_translation([0, 0, shaft_length / 2.0])

    arrow = trimesh.util.concatenate([shaft, head])

    # Global scale
    arrow.apply_scale(vector_scale)

    actual_shaft_len = shaft_length * vector_scale
    actual_head_len = head_length * vector_scale

    # Orientation (align +Z to direction)
    dir_norm = np.linalg.norm(direction)
    if dir_norm > 1e-12:
        ndir = direction / dir_norm
        z = np.array([0.0, 0.0, 1.0])
        axis = np.cross(z, ndir)
        angle = np.arccos(np.clip(np.dot(z, ndir), -1.0, 1.0))
        if np.linalg.norm(axis) > 1e-12:
            axis = axis / np.linalg.norm(axis)
            rot = Rotation.from_rotvec(angle * axis)
            T = np.eye(4)
            T[:3, :3] = rot.as_matrix()
            arrow.apply_transform(T)
        elif ndir[2] < 0:
            # Anti-parallel to +Z: the cross product vanishes, so turn half a circle about x.
            arrow.apply_transform(np.diag([1.0, -1.0, -1.0, 1.0]))
    else:
        ndir = np.array([0.0, 0.0, 1.0])

    if anchor == "head":
        tip_position = ndir * (actual_shaft_len / 2.0 + actual_head_len)
        arrow.apply_translation(position - tip_position)
    else:
        tail_position = -ndir * (actual_shaft_len / 2.0)
        arrow.apply_translation(position - tail_position)

    return arrow


def write_ply_arrows(
    output_file,
    positions,
    vectors,
    magnitudes,
    colors,
    *,
    length_mode: str = "linear",
    length_scale: float = 1.0,
    anchor: str = "tail",
    vector_scale: float = 0.4,
    base_length: float = 1.0,
    shaft_width: float = 0.05,
):
    """Write multiple arrows as a colored PLY file (ASCII, RGBA)."""
    total = len(positions)
    if total == 0:
        return

    all_vertices = []
    all_faces = []
    all_colors = []

    for i in range(total):
        arrow = create_arrow(
            positions[i],
            vectors[i],
            magnitudes[i],
            vector_scale=vector_scale,
            base_length=base_length,
            shaft_width=shaft_width,
            length_mode=length_mode,
            length_scale=length_scale,
            anchor=anchor,
        )
        start = len(all_vertices)
        all_vertices.extend(arrow.vertices)
        for f in arrow.faces:
            all_faces.append([start + int(f[0]), start + int(f[1]), start + int(f[2])])
        for _ in range(len(arrow.vertices)):
            all_colors.append(colors[i])

    if not all_vertices:
        return

    with open(output_file, "w") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(all_vertices)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write("property uchar alpha\n")
        f.write(f"element face {len(all_faces)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for v, c in zip(all_vertices, all_colors):
            f.write(
                f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f} {int(c[0])} {int(c[1])} {int(c[2])} {int(c[3])}\n"
            )
        for face in all_faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")


# ──────────────────────────────────────────────────────────────────────────────
# Mesh data helpers
# ──────────────────────────────────────────────────────────────────────────────


def _surface_normals_for_mesh(m):
    """Per-element unit normals from each element's first three nodes (the triangle winding).

    A degenerate (zero-area) triangle has no normal and gets a zero row, so its ``TI_normal``
    arrow is 0.
    """
    node_coords = m.nodes.node_coord
    element_nodes = m.elm.node_number_list - 1
    normals = []
    for element in element_nodes:
        nodes = node_coords[element[:3]]
        edge1 = nodes[1] - nodes[0]
        edge2 = nodes[2] - nodes[0]
        normal = np.cross(edge1, edge2)
        norm = np.linalg.norm(normal)
        normals.append(normal / norm if norm > 1e-12 else np.zeros(3))
    return np.array(normals)


def _get_surface_face_barycenters(surface_mesh):
    """Get barycenters of triangular faces in a surface mesh."""
    triangular_elements = surface_mesh.elm.elm_type == 2
    if not np.any(triangular_elements):
        triangular_elements = np.ones(
            len(surface_mesh.elm.node_number_list), dtype=bool
        )

    triangle_nodes = surface_mesh.elm.node_number_list[triangular_elements] - 1
    triangle_nodes = triangle_nodes[:, :3]
    node_coords = surface_mesh.nodes.node_coord
    return np.mean(node_coords[triangle_nodes], axis=1)


def _interpolate_field_to_surface(volumetric_mesh, target_positions, field_name="E"):
    """Interpolate an element field of a volumetric mesh to target positions.

    The field is averaged to the nodes with SimNIBS ``Msh.elm2node_matrix`` and each target
    takes its nearest node's value.
    """
    from scipy.spatial import cKDTree

    if field_name not in volumetric_mesh.field:
        raise ValueError(f"Field '{field_name}' not found in volumetric mesh")

    field_elm = volumetric_mesh.field[field_name].value
    M = volumetric_mesh.elm2node_matrix()
    vol_field_nodes = np.zeros((M.shape[0], 3))
    for i in range(3):
        vol_field_nodes[:, i] = M.dot(field_elm[:, i])

    tree = cKDTree(volumetric_mesh.nodes.node_coord)
    _, indices = tree.query(target_positions)
    return vol_field_nodes[indices]


def _map_magnitude_to_colors_magscale(
    magnitudes,
    *,
    all_magnitudes_full,
    blue_pct: float,
    green_pct: float,
    red_pct: float,
):
    """Map magnitudes to RGBA colors using percentile-based blue-green-red scale."""
    blue_pct = float(min(max(blue_pct, 0.0), 100.0))
    green_pct = float(min(max(green_pct, 0.0), 100.0))
    red_pct = float(min(max(red_pct, 0.0), 100.0))
    if green_pct < blue_pct:
        green_pct = blue_pct
    if red_pct < green_pct:
        red_pct = green_pct

    mag_blue = np.percentile(all_magnitudes_full, blue_pct)
    mag_green = np.percentile(all_magnitudes_full, green_pct)
    mag_red = np.percentile(all_magnitudes_full, red_pct)

    def map_one(mag):
        if mag <= mag_blue:
            return np.array([0, 0, 255, 255], dtype=np.uint8)
        if mag <= mag_green:
            denom = mag_green - mag_blue
            t = 0.0 if denom <= 0 else float((mag - mag_blue) / denom)
            r, g, b = 0, int(255 * t), int(255 * (1.0 - t))
            return np.array([r, g, b, 255], dtype=np.uint8)
        if mag <= mag_red:
            denom = mag_red - mag_green
            t = 1.0 if denom <= 0 else float((mag - mag_green) / denom)
            r, g, b = int(255 * t), int(255 * (1.0 - t)), 0
            return np.array([r, g, b, 255], dtype=np.uint8)
        return np.array([255, 0, 0, 255], dtype=np.uint8)

    return np.array([map_one(m) for m in magnitudes])


# ──────────────────────────────────────────────────────────────────────────────
# Core export logic
# ──────────────────────────────────────────────────────────────────────────────


def _load_meshes(config: VectorConfig, carrier_paths: list[str]):
    """Load every channel's SimNIBS volume mesh and the central surface mesh.

    Returns:
        Tuple of (channel meshes in channel order, central_surface_mesh).
    """
    for p in carrier_paths:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Mesh file not found: {p}")

    if not os.path.exists(config.central_surface):
        raise FileNotFoundError(
            f"Central surface mesh not found: {config.central_surface}"
        )

    meshes = [simnibs.read_msh(p) for p in carrier_paths]

    try:
        central = simnibs.read_msh(config.central_surface)
    except Exception as exc:
        raise RuntimeError(f"Failed to load central surface mesh: {exc}") from exc

    logger.info(
        "Using central surface for vector positions: %s", config.central_surface
    )

    # Validate E fields
    for idx, m in enumerate(meshes, start=1):
        if "E" not in m.field:
            raise ValueError(f"E field not found in mesh {idx}")

    return meshes, central


def _compute_fields(config, meshes, positions):
    """Interpolate every channel's E field and compute the TI / mTI vectors.

    The envelope is :func:`tit.calc.envelope_max` over ALL channels (paired
    positionally, as ``tit/sim/mTI.py`` computes ``mTI_max``); ``E1``/``E2`` are
    the first two channels and ``E_sum`` the sum of every channel.

    Returns:
        Dict with keys: positions, channels (every channel's E), E1, E2, TI,
        E_sum (or None).
    """
    logger.info(
        "Interpolating E fields to %d surface face barycenters...", len(positions)
    )
    channels = [_interpolate_field_to_surface(m, positions, "E") for m in meshes]

    lengths = [len(E) for E in channels]
    if any(n != len(positions) for n in lengths):
        raise ValueError(
            f"interpolated channel fields have {lengths} rows for "
            f"{len(positions)} arrow positions; expected one per position"
        )

    amp, direction = envelope_max(channels, return_direction=True)
    TI = amp[:, None] * direction
    E_sum = np.sum(channels, axis=0) if config.export_sum else None

    logger.info("Interpolated E fields to %d face barycenters", len(positions))

    return {
        "positions": positions,
        "channels": channels,
        "E1": channels[0],
        "E2": channels[1],
        "TI": TI,
        "E_sum": E_sum,
    }


def _compute_ti_normal(config, central_mesh, channels):
    """``TI_normal`` arrows: the envelope along each face normal, along that normal.

    The quantity the simulation writes as ``TI_normal``
    (:func:`tit.calc.envelope` of every channel field along the normal), not
    the projection of the ``TI`` vector: the envelope is not linear in the
    fields, so the two differ wherever the fields are oblique to the surface.
    The faces are the ones :func:`_get_surface_face_barycenters` places the
    arrows on, so there is one normal per arrow.

    Returns:
        ``(N, 3)`` arrows or None.

    Raises:
        ValueError: the channel fields are not one per central-surface face.
    """
    if not config.export_ti_normal:
        return None

    surf_normals = _surface_normals_for_mesh(central_mesh)
    triangular_elements = central_mesh.elm.elm_type == 2
    if np.any(triangular_elements):
        surf_normals = surf_normals[triangular_elements]
    if len(surf_normals) != len(channels[0]):
        raise ValueError(
            f"TI_normal: {len(surf_normals)} central-surface faces for "
            f"{len(channels[0])} arrows; expected one arrow per face"
        )
    return envelope(channels, surf_normals)[:, None] * surf_normals


def _filter_and_sample(config, fields):
    """Apply non-zero, top-percent, and random-sampling filters.

    Mutates nothing; returns a new dict with the sampled arrays.
    """
    positions = fields["positions"]
    E1 = fields["E1"]
    E2 = fields["E2"]
    TI = fields["TI"]
    E_sum = fields["E_sum"]
    TI_normal = fields.get("TI_normal")

    # Filter non-zero TI
    mag_TI = np.linalg.norm(TI, axis=1)
    nz = mag_TI > 1e-10
    positions = positions[nz]
    E1 = E1[nz]
    E2 = E2[nz]
    TI = TI[nz]
    mag_TI = mag_TI[nz]
    if E_sum is not None:
        E_sum = E_sum[nz]
    if TI_normal is not None:
        TI_normal = TI_normal[nz]

    # Top-percent filter
    if config.top_percent is not None:
        pct = max(0.0, min(100.0, float(config.top_percent)))
        if pct > 0.0 and len(mag_TI) > 0:
            cutoff = np.percentile(mag_TI, 100.0 - pct)
            mask = mag_TI >= cutoff
            positions = positions[mask]
            E1 = E1[mask]
            E2 = E2[mask]
            TI = TI[mask]
            mag_TI = mag_TI[mask]
            if E_sum is not None:
                E_sum = E_sum[mask]
            if TI_normal is not None:
                TI_normal = TI_normal[mask]

    # Sampling
    np.random.seed(config.seed)
    if config.all_nodes:
        idx = np.arange(len(positions))
    else:
        sel_count = min(int(config.count), len(positions))
        if sel_count <= 0:
            raise ValueError("No vectors remaining after filtering")
        idx = np.random.choice(len(positions), sel_count, replace=False)

    return {
        "positions": positions[idx],
        "E1": E1[idx],
        "E2": E2[idx],
        "TI": TI[idx],
        "E_sum": E_sum[idx] if E_sum is not None else None,
        "TI_normal": TI_normal[idx] if TI_normal is not None else None,
    }


def _compute_colors(config, sampled, full_magnitudes):
    """Compute RGBA color arrays for each channel.

    Returns:
        Dict with keys ch1, ch2, ti, sum, ti_normal -- each is an [N, 4] uint8 array
        or None.
    """
    pos = sampled["positions"]
    n = len(pos)

    mag_E1_s = np.linalg.norm(sampled["E1"], axis=1)
    mag_E2_s = np.linalg.norm(sampled["E2"], axis=1)
    mag_TI_s = np.linalg.norm(sampled["TI"], axis=1)
    mag_E_sum_s = (
        np.linalg.norm(sampled["E_sum"], axis=1)
        if sampled["E_sum"] is not None
        else None
    )
    mag_TI_normal_s = (
        np.linalg.norm(sampled["TI_normal"], axis=1)
        if sampled["TI_normal"] is not None
        else None
    )

    BLUE = (0, 0, 255, 255)
    GREEN = (0, 255, 0, 255)
    RED = (255, 0, 0, 255)
    YELLOW = (255, 255, 0, 255)
    CYAN = (0, 255, 255, 255)

    if config.color == VectorConfig.Color.MAGSCALE:
        all_full = np.concatenate(full_magnitudes) if full_magnitudes else mag_TI_s
        kw = dict(
            all_magnitudes_full=all_full,
            blue_pct=config.blue_percentile,
            green_pct=config.green_percentile,
            red_pct=config.red_percentile,
        )
        ch1_colors = _map_magnitude_to_colors_magscale(mag_E1_s, **kw)
        ch2_colors = _map_magnitude_to_colors_magscale(mag_E2_s, **kw)
        ti_colors = _map_magnitude_to_colors_magscale(mag_TI_s, **kw)
        sum_colors = (
            _map_magnitude_to_colors_magscale(mag_E_sum_s, **kw)
            if mag_E_sum_s is not None
            else None
        )
        ti_normal_colors = (
            _map_magnitude_to_colors_magscale(mag_TI_normal_s, **kw)
            if mag_TI_normal_s is not None
            else None
        )
    else:
        ch1_colors = np.tile(np.array(RED), (n, 1))
        ch2_colors = np.tile(np.array(BLUE), (n, 1))
        ti_colors = np.tile(np.array(GREEN), (n, 1))
        sum_colors = (
            np.tile(np.array(YELLOW), (n, 1)) if sampled["E_sum"] is not None else None
        )
        ti_normal_colors = (
            np.tile(np.array(CYAN), (n, 1))
            if sampled["TI_normal"] is not None
            else None
        )

    return {
        "ch1": ch1_colors,
        "ch2": ch2_colors,
        "ti": ti_colors,
        "sum": sum_colors,
        "ti_normal": ti_normal_colors,
    }


def _write_channel_ply(
    path, positions, vectors, magnitudes, colors, config, *, eff_params
):
    """Write a single channel's PLY arrow file."""
    write_ply_arrows(
        path,
        positions,
        vectors,
        magnitudes,
        colors,
        length_mode=str(config.length_mode),
        length_scale=eff_params["length_scale"],
        anchor=str(config.anchor),
        vector_scale=eff_params["vector_scale"],
        base_length=eff_params["vector_length"],
        shaft_width=eff_params["vector_width"],
    )


def _write_outputs(config, sampled, colors):
    """Write all requested PLY files to the output directory."""
    output_dir = config.output_dir
    os.makedirs(output_dir, exist_ok=True)

    # Effective visualization parameters
    eff = {
        "length_scale": float(config.length_scale) * BASE_LENGTH_SCALE,
        "vector_scale": float(config.vector_scale) * BASE_VECTOR_SCALE,
        "vector_width": float(config.vector_width) * BASE_VECTOR_WIDTH,
        "vector_length": float(config.vector_length) * BASE_VECTOR_LENGTH,
    }

    pos = sampled["positions"]
    exported = 0

    # CH1 and CH2 (optional)
    if config.export_ch1_ch2:
        mag_E1 = np.linalg.norm(sampled["E1"], axis=1)
        mag_E2 = np.linalg.norm(sampled["E2"], axis=1)
        _write_channel_ply(
            os.path.join(output_dir, "CH1.ply"),
            pos,
            sampled["E1"],
            mag_E1,
            colors["ch1"],
            config,
            eff_params=eff,
        )
        _write_channel_ply(
            os.path.join(output_dir, "CH2.ply"),
            pos,
            sampled["E2"],
            mag_E2,
            colors["ch2"],
            config,
            eff_params=eff,
        )
        exported += 2

    # TI / mTI (always)
    mag_TI = np.linalg.norm(sampled["TI"], axis=1)
    ti_filename = "mTI.ply" if config.is_mti else "TI.ply"
    _write_channel_ply(
        os.path.join(output_dir, ti_filename),
        pos,
        sampled["TI"],
        mag_TI,
        colors["ti"],
        config,
        eff_params=eff,
    )
    exported += 1

    # E_sum (optional)
    if sampled["E_sum"] is not None:
        mag_sum = np.linalg.norm(sampled["E_sum"], axis=1)
        _write_channel_ply(
            os.path.join(output_dir, "TI_sum.ply"),
            pos,
            sampled["E_sum"],
            mag_sum,
            colors["sum"],
            config,
            eff_params=eff,
        )
        exported += 1

    # TI_normal (optional)
    if sampled["TI_normal"] is not None:
        mag_tn = np.linalg.norm(sampled["TI_normal"], axis=1)
        _write_channel_ply(
            os.path.join(output_dir, "TI_normal.ply"),
            pos,
            sampled["TI_normal"],
            mag_tn,
            colors["ti_normal"],
            config,
            eff_params=eff,
        )
        exported += 1

    # Combined (optional)
    if config.export_combined:
        parts = [(pos, sampled["TI"], mag_TI, colors["ti"])]
        if config.export_ch1_ch2:
            parts.append(
                (
                    pos,
                    sampled["E1"],
                    np.linalg.norm(sampled["E1"], axis=1),
                    colors["ch1"],
                )
            )
            parts.append(
                (
                    pos,
                    sampled["E2"],
                    np.linalg.norm(sampled["E2"], axis=1),
                    colors["ch2"],
                )
            )
        if sampled["E_sum"] is not None:
            parts.append(
                (
                    pos,
                    sampled["E_sum"],
                    np.linalg.norm(sampled["E_sum"], axis=1),
                    colors["sum"],
                )
            )
        if sampled["TI_normal"] is not None:
            parts.append(
                (
                    pos,
                    sampled["TI_normal"],
                    np.linalg.norm(sampled["TI_normal"], axis=1),
                    colors["ti_normal"],
                )
            )

        all_pos = np.concatenate([p[0] for p in parts], axis=0)
        all_vec = np.concatenate([p[1] for p in parts], axis=0)
        all_mag = np.concatenate([p[2] for p in parts], axis=0)
        all_col = np.concatenate([p[3] for p in parts], axis=0)

        _write_channel_ply(
            os.path.join(output_dir, "combined.ply"),
            all_pos,
            all_vec,
            all_mag,
            all_col,
            config,
            eff_params=eff,
        )
        exported += 1

    return exported


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────


def _resolve_paths(config: VectorConfig) -> list[str]:
    """Resolve all paths from subject_id + simulation_name via PathManager.

    The surface and the carrier meshes follow the simulation's mode: an mTI run's
    own central surface and every one of its channels. An ``output_dir`` already on
    the config is kept -- the Plan card reports it as the destination.

    Returns:
        Every channel's carrier mesh path, in channel order.
    """
    from tit.paths import get_path_manager

    pm = get_path_manager()
    sid = config.subject_id
    sim = config.simulation_name
    cond = _read_conductivity(sid, sim)

    carriers = carrier_mesh_paths(sid, sim, cond)
    config.mesh1, config.mesh2 = carriers[0], carriers[1]
    if len(carriers) >= 4:
        config.mesh3, config.mesh4 = carriers[2], carriers[3]

    config.central_surface = central_surface_path(sid, sim)
    config.output_dir = (config.output_dir or "").strip()
    if not config.output_dir:
        config.output_dir = os.path.join(
            pm.ti_toolbox(), "visual_exports", f"sub-{sid}", sim, "vectors"
        )
    return carriers


def run_vectors(config: VectorConfig) -> None:
    """Export TI/mTI vector arrow PLY files from simulation meshes.

    This is the primary programmatic entry point.  It performs:

    1. Resolve any missing paths via PathManager (when subject_id is given)
    2. Load volumetric + central surface meshes
    3. Interpolate E fields to surface face barycenters
    4. Compute TI (or mTI) vectors, optional E_sum and TI_normal
    5. Filter and sample nodes
    6. Colorize arrows (RGB channel colors or magnitude-scale)
    7. Write PLY output files

    Args:
        config: A :class:`VectorConfig` with either ``subject_id`` +
            ``simulation_name`` or explicit paths.

    Raises:
        FileNotFoundError: If any required mesh file is missing.
        ValueError: If E fields are missing or no vectors remain after filtering.
    """
    carriers = _resolve_paths(config)
    from tit.telemetry import track_operation
    from tit import constants as _const

    with track_operation(_const.TELEMETRY_OP_BLENDER_VECTORS):
        logger.info("Starting vector field export")

        # 1 -- Load meshes
        meshes, central = _load_meshes(config, carriers)

        if config.anchor != VectorConfig.Anchor.HEAD:
            logger.info(
                "Using anchor='%s' -- for surface vectors, anchor='head' is recommended",
                config.anchor,
            )

        # 2 -- Compute positions and fields
        positions = _get_surface_face_barycenters(central)
        logger.info(
            "Using central surface face barycenters for vector positions (%d faces)",
            len(positions),
        )
        fields = _compute_fields(config, meshes, positions)

        # 3 -- TI_normal (optional)
        TI_normal = _compute_ti_normal(config, central, fields["channels"])
        fields["TI_normal"] = TI_normal

        # Pre-filter full magnitudes for color normalization (magscale mode)
        full_mag_stacks = [
            np.linalg.norm(fields["E1"], axis=1),
            np.linalg.norm(fields["E2"], axis=1),
            np.linalg.norm(fields["TI"], axis=1),
        ]
        if fields["E_sum"] is not None:
            full_mag_stacks.append(np.linalg.norm(fields["E_sum"], axis=1))
        if TI_normal is not None:
            full_mag_stacks.append(np.linalg.norm(TI_normal, axis=1))

        # 4 -- Filter and sample
        sampled = _filter_and_sample(config, fields)

        # 5 -- Colorize
        colors = _compute_colors(config, sampled, full_mag_stacks)

        # 6 -- Write outputs
        logger.info("Writing PLY files...")
        exported = _write_outputs(config, sampled, colors)

        logger.info("Converted %d vector PLY files", exported)
        logger.info("Output: %s", config.output_dir)
        logger.info("Done")
