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

from tit.blender.config import VectorConfig
from tit.calc import get_TI_vectors, get_mTI_vectors

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
    """
    from tit.paths import get_path_manager

    pm = get_path_manager()
    config_path = os.path.join(pm.simulation(sid, sim), "documentation", "config.json")
    with open(config_path) as f:
        data = json.load(f)
    return data["conductivity"]


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


def _barycenters_for_mesh(m):
    """Compute element barycenters for a SimNIBS mesh."""
    try:
        return m.elements_baricenters().value
    except Exception:
        node_coords = m.nodes.node_coord
        element_nodes = m.elm.node_number_list - 1
        return np.mean(node_coords[element_nodes], axis=1)


def _surface_normals_for_mesh(m):
    """Approximate per-element surface normals for triangular elements."""
    try:
        node_coords = m.nodes.node_coord
        element_nodes = m.elm.node_number_list - 1
        normals = []
        for element in element_nodes:
            nodes = node_coords[element[:3]]
            edge1 = nodes[1] - nodes[0]
            edge2 = nodes[2] - nodes[0]
            normal = np.cross(edge1, edge2)
            norm = np.linalg.norm(normal)
            if norm > 1e-12:
                normal = normal / norm
            else:
                normal = np.array([0.0, 0.0, 1.0])
            normals.append(normal)
        return np.array(normals)
    except Exception:
        return np.tile(np.array([0.0, 0.0, 1.0]), (len(m.elm.node_number_list), 1))


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
    """Interpolate a field from a volumetric mesh to target positions.

    Uses node-based interpolation via elm2node_matrix when available,
    falls back to nearest-element interpolation.
    """
    if field_name not in volumetric_mesh.field:
        raise ValueError(f"Field '{field_name}' not found in volumetric mesh")

    field_elm = volumetric_mesh.field[field_name].value

    try:
        from scipy.spatial import cKDTree

        M = volumetric_mesh.elm2node_matrix()
        vol_field_nodes = np.zeros((M.shape[0], 3))
        for i in range(3):
            vol_field_nodes[:, i] = M.dot(field_elm[:, i])

        vol_node_positions = volumetric_mesh.nodes.node_coord
        tree = cKDTree(vol_node_positions)
        _, indices = tree.query(target_positions)
        return vol_field_nodes[indices]
    except Exception:
        from scipy.spatial import cKDTree

        elm_positions = _barycenters_for_mesh(volumetric_mesh)
        tree = cKDTree(elm_positions)
        _, indices = tree.query(target_positions)

        field_values = np.zeros((len(target_positions), 3))
        for i in range(len(target_positions)):
            field_values[i] = field_elm[indices[i]]
        return field_values


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


def _load_meshes(config: VectorConfig):
    """Load SimNIBS volumetric meshes and the central surface mesh.

    Returns:
        Tuple of (m1, m2, m3_or_None, m4_or_None, central_surface_mesh).
    """
    for p in [config.mesh1, config.mesh2]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Mesh file not found: {p}")

    m1 = simnibs.read_msh(config.mesh1)
    m2 = simnibs.read_msh(config.mesh2)
    m3 = m4 = None

    if config.is_mti:
        for p in [config.mesh3, config.mesh4]:
            if not os.path.exists(p):
                raise FileNotFoundError(f"mTI mesh file not found: {p}")
        m3 = simnibs.read_msh(config.mesh3)
        m4 = simnibs.read_msh(config.mesh4)

    if not os.path.exists(config.central_surface):
        raise FileNotFoundError(
            f"Central surface mesh not found: {config.central_surface}"
        )

    try:
        central = simnibs.read_msh(config.central_surface)
    except Exception as exc:
        raise RuntimeError(f"Failed to load central surface mesh: {exc}") from exc

    logger.info(
        "Using central surface for vector positions: %s", config.central_surface
    )

    # Validate E fields
    for idx, m in enumerate([m1, m2] + ([m3, m4] if config.is_mti else []), start=1):
        if "E" not in m.field:
            raise ValueError(f"E field not found in mesh {idx}")

    return m1, m2, m3, m4, central


def _compute_fields(config, m1, m2, m3, m4, positions):
    """Interpolate E fields and compute TI / mTI vectors.

    Returns:
        Dict with keys: E1, E2, TI, E_sum (or None), TI_normal (or None).
    """
    logger.info(
        "Interpolating E fields to %d surface face barycenters...", len(positions)
    )
    E1 = _interpolate_field_to_surface(m1, positions, "E")
    E2 = _interpolate_field_to_surface(m2, positions, "E")
    E3 = E4 = None
    if config.is_mti:
        E3 = _interpolate_field_to_surface(m3, positions, "E")
        E4 = _interpolate_field_to_surface(m4, positions, "E")

    # Align sizes
    arrays = [positions, E1, E2]
    if config.is_mti:
        arrays += [E3, E4]
    min_len = min(len(a) for a in arrays)
    positions = positions[:min_len]
    E1 = E1[:min_len]
    E2 = E2[:min_len]
    if config.is_mti:
        E3 = E3[:min_len]
        E4 = E4[:min_len]

    # Compute TI / mTI
    if config.is_mti:
        TI = get_mTI_vectors(E1, E2, E3, E4)
        E_sum = (E1 + E2 + E3 + E4) if config.export_sum else None
    else:
        TI = get_TI_vectors(E1, E2)
        E_sum = (E1 + E2) if config.export_sum else None

    logger.info("Interpolated E fields to %d face barycenters", len(positions))

    return {
        "positions": positions,
        "E1": E1,
        "E2": E2,
        "TI": TI,
        "E_sum": E_sum,
    }


def _compute_ti_normal(config, central_mesh, m1, TI):
    """Compute TI_normal by projecting TI onto surface normals.

    Returns:
        TI_normal array or None.
    """
    if not config.export_ti_normal:
        return None

    try:
        surf_normals = _surface_normals_for_mesh(central_mesh)
        triangular_elements = central_mesh.elm.elm_type == 2
        if not np.any(triangular_elements):
            triangular_elements = np.ones(
                len(central_mesh.elm.node_number_list), dtype=bool
            )
        triangle_normals = surf_normals[triangular_elements]

        # Align normals with TI count
        if len(triangle_normals) > len(TI):
            surf_normals = triangle_normals[: len(TI)]
        elif len(triangle_normals) < len(TI):
            default_normal = np.array([0.0, 0.0, 1.0])
            pad = np.tile(default_normal, (len(TI) - len(triangle_normals), 1))
            surf_normals = np.vstack([triangle_normals, pad])
        else:
            surf_normals = triangle_normals
    except Exception:
        # Fallback to TDCS mesh normals
        surf_normals = _surface_normals_for_mesh(m1)
        if len(surf_normals) > len(TI):
            surf_normals = surf_normals[: len(TI)]
        elif len(surf_normals) < len(TI):
            default_normal = np.array([0.0, 0.0, 1.0])
            pad = np.tile(default_normal, (len(TI) - len(surf_normals), 1))
            surf_normals = np.vstack([surf_normals, pad])

    return np.sum(TI * surf_normals, axis=1, keepdims=True) * surf_normals


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


def _resolve_paths(config: VectorConfig) -> None:
    """Resolve all paths from subject_id + simulation_name via PathManager."""
    from tit.paths import get_path_manager

    pm = get_path_manager()
    sid = config.subject_id
    sim = config.simulation_name
    sim_base = pm.simulation(sid, sim)
    hf_dir = os.path.join(sim_base, "high_Frequency", "mesh")
    cond = _read_conductivity(sid, sim)

    config.mesh1 = os.path.join(hf_dir, f"{sid}_TDCS_1_{cond}.msh")
    config.mesh2 = os.path.join(hf_dir, f"{sid}_TDCS_2_{cond}.msh")

    # Auto-detect mTI when TDCS meshes 3 and 4 exist
    m3 = os.path.join(hf_dir, f"{sid}_TDCS_3_{cond}.msh")
    m4 = os.path.join(hf_dir, f"{sid}_TDCS_4_{cond}.msh")
    if os.path.exists(m3) and os.path.exists(m4):
        config.mesh3 = m3
        config.mesh4 = m4

    config.central_surface = pm.ti_central_surface(sid, sim)
    config.output_dir = os.path.join(
        pm.ti_toolbox(), "visual_exports", f"sub-{sid}", sim, "vectors"
    )


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
    _resolve_paths(config)
    from tit.telemetry import track_event
    from tit import constants as _const

    track_event(_const.TELEMETRY_OP_BLENDER_VECTORS, {"status": "start"})

    logger.info("Starting vector field export")

    # 1 -- Load meshes
    m1, m2, m3, m4, central = _load_meshes(config)

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
    fields = _compute_fields(config, m1, m2, m3, m4, positions)

    # 3 -- TI_normal (optional)
    TI_normal = _compute_ti_normal(config, central, m1, fields["TI"])
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
