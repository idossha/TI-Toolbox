"""
Low-level mesh I/O, colormap, and vertex-processing utilities.

This module is the single source of truth for:
- Binary STL reading and writing
- PLY writing (with per-vertex colors or scalars)
- Scalar-to-color mapping (simple blue-red and matplotlib colormaps)
- Vertex deduplication / face remapping
"""

from __future__ import annotations

import struct
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Binary STL
# ---------------------------------------------------------------------------


def read_binary_stl(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Read vertices and faces from a binary STL file.

    Duplicate vertices (common in STL) are merged so the returned arrays
    use shared vertex indices.

    Args:
        path: Path to the binary STL file.

    Returns:
        Tuple of (vertices, faces) where vertices is [N, 3] float64 and
        faces is [M, 3] int64 with indices into the vertex array.
    """
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    vertex_map: dict[tuple[float, float, float], int] = {}

    with open(path, "rb") as f:
        # Skip 80-byte header
        f.read(80)
        num_triangles = struct.unpack("<I", f.read(4))[0]

        for _ in range(num_triangles):
            # Skip normal vector (3 floats = 12 bytes)
            f.read(12)

            face_indices: list[int] = []
            for _ in range(3):
                v = struct.unpack("<fff", f.read(12))
                if v not in vertex_map:
                    vertex_map[v] = len(vertices)
                    vertices.append(v)
                face_indices.append(vertex_map[v])

            faces.append((face_indices[0], face_indices[1], face_indices[2]))

            # Skip attribute byte count (2 bytes)
            f.read(2)

    return np.array(vertices, dtype=np.float64), np.array(faces, dtype=np.int64)


def write_binary_stl(
    path: str,
    vertices: np.ndarray,
    faces: np.ndarray,
    normals: Optional[np.ndarray] = None,
    header_text: str = "TI-Toolbox Mesh",
) -> None:
    """Write a binary STL file from vertices and faces.

    Args:
        path: Output file path.
        vertices: Array of shape [N, 3] with vertex coordinates.
        faces: Array of shape [M, 3] with vertex indices for each triangle.
        normals: Optional array of shape [M, 3] with per-face normals.
            If *None*, normals are computed from the triangle edges.
        header_text: ASCII text written into the 80-byte STL header.
    """
    vertices = np.asarray(vertices, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int64)
    n_faces = len(faces)

    with open(path, "wb") as f:
        # 80-byte header
        header = header_text.encode("ascii")[:80].ljust(80, b"\x00")
        f.write(header)

        # Number of triangles
        f.write(struct.pack("<I", n_faces))

        for i, face in enumerate(faces):
            v0 = vertices[face[0]]
            v1 = vertices[face[1]]
            v2 = vertices[face[2]]

            if normals is not None:
                normal = normals[i]
            else:
                edge1 = v1 - v0
                edge2 = v2 - v0
                normal = np.cross(edge1, edge2)
                length = np.linalg.norm(normal)
                if length > 1e-12:
                    normal = normal / length
                else:
                    normal = np.array([0.0, 0.0, 1.0])

            f.write(
                struct.pack(
                    "<fff", float(normal[0]), float(normal[1]), float(normal[2])
                )
            )
            f.write(struct.pack("<fff", float(v0[0]), float(v0[1]), float(v0[2])))
            f.write(struct.pack("<fff", float(v1[0]), float(v1[1]), float(v1[2])))
            f.write(struct.pack("<fff", float(v2[0]), float(v2[1]), float(v2[2])))
            f.write(struct.pack("<H", 0))


# ---------------------------------------------------------------------------
# PLY Writers
# ---------------------------------------------------------------------------


def write_ply_with_colors(
    path: str,
    vertices: np.ndarray,
    faces: np.ndarray,
    colors: np.ndarray,
    comment: str = "",
) -> None:
    """Write an ASCII PLY file with per-vertex RGB colors.

    Args:
        path: Output file path.
        vertices: Array of shape [N, 3] vertex coordinates.
        faces: Array of shape [M, 3] face indices.
        colors: Array of shape [N, 3] RGB values in 0-255 range.
        comment: Optional comment line written into the header.
    """
    n_vertices = len(vertices)
    n_faces = len(faces)

    with open(path, "w") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        if comment:
            f.write(f"comment {comment}\n")
        f.write(f"element vertex {n_vertices}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write("property uchar red\n")
        f.write("property uchar green\n")
        f.write("property uchar blue\n")
        f.write(f"element face {n_faces}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")

        for i in range(n_vertices):
            x, y, z = vertices[i]
            r, g, b = colors[i].astype(int)
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {r} {g} {b}\n")

        for face in faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")


def write_ply_with_scalars(
    path: str,
    vertices: np.ndarray,
    faces: np.ndarray,
    scalars: np.ndarray,
    scalar_name: str = "scalar",
    comment: str = "",
) -> None:
    """Write an ASCII PLY file with a per-vertex scalar property.

    Args:
        path: Output file path.
        vertices: Array of shape [N, 3] vertex coordinates.
        faces: Array of shape [M, 3] face indices.
        scalars: Array of shape [N] scalar values.
        scalar_name: Name for the scalar property in the PLY header.
        comment: Optional comment line written into the header.
    """
    n_vertices = len(vertices)
    n_faces = len(faces)

    with open(path, "w") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        if comment:
            f.write(f"comment {comment}\n")
        f.write(f"element vertex {n_vertices}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write(f"property float {scalar_name}\n")
        f.write(f"element face {n_faces}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")

        for i in range(n_vertices):
            x, y, z = vertices[i]
            s = scalars[i]
            f.write(f"{x:.6f} {y:.6f} {z:.6f} {s:.6f}\n")

        for face in faces:
            f.write(f"3 {face[0]} {face[1]} {face[2]}\n")


# ---------------------------------------------------------------------------
# Color-mapping
# ---------------------------------------------------------------------------


def simple_colormap(
    values: np.ndarray,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> np.ndarray:
    """Map scalar values to a simple blue-to-red linear ramp.

    Args:
        values: 1-D array of scalar values.
        vmin: Floor for normalization (default: nanmin of *values*).
        vmax: Ceiling for normalization (default: nanmax of *values*).

    Returns:
        Array of shape [N, 3] with uint8 RGB values.
    """
    if vmin is None:
        vmin = float(np.nanmin(values))
    if vmax is None:
        vmax = float(np.nanmax(values))

    if vmax == vmin:
        colors = np.zeros((len(values), 3), dtype=np.uint8)
        colors[:, 2] = 255  # All blue
        return colors

    normalized = (values - vmin) / (vmax - vmin)
    normalized = np.clip(normalized, 0, 1)

    colors = np.zeros((len(values), 3), dtype=np.uint8)
    colors[:, 0] = (normalized * 255).astype(np.uint8)  # Red channel
    colors[:, 2] = ((1 - normalized) * 255).astype(np.uint8)  # Blue channel

    return colors


def field_to_colormap(
    values: np.ndarray,
    cmap_name: str = "viridis",
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
) -> np.ndarray:
    """Map scalar values to RGB using a matplotlib colormap.

    Falls back to :func:`simple_colormap` when matplotlib is unavailable.

    Args:
        values: 1-D array of scalar values.
        cmap_name: Matplotlib colormap name (e.g. ``"viridis"``, ``"jet"``).
        vmin: Floor for normalization (default: nanmin of *values*).
        vmax: Ceiling for normalization (default: nanmax of *values*).

    Returns:
        Array of shape [N, 3] with uint8 RGB values.
    """
    try:
        import matplotlib.cm as cm
    except ImportError:
        return simple_colormap(values, vmin, vmax)

    if vmin is None:
        vmin = float(np.nanmin(values))
    if vmax is None:
        vmax = float(np.nanmax(values))

    if vmax == vmin:
        normalized = np.zeros_like(values)
    else:
        normalized = (values - vmin) / (vmax - vmin)
        normalized = np.clip(normalized, 0, 1)

    cmap = cm.get_cmap(cmap_name)
    colors_rgba = cmap(normalized)
    colors_rgb = (colors_rgba[:, :3] * 255).astype(np.uint8)

    return colors_rgb


# ---------------------------------------------------------------------------
# Vertex processing
# ---------------------------------------------------------------------------


def deduplicate_vertices(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Merge duplicate vertices and remap face indices.

    Uses :func:`numpy.unique` with rounding to find coincident vertices
    (exact floating-point match after round-trip through float64).

    Args:
        vertices: Array of shape [N, 3].
        faces: Array of shape [M, 3] indexing into *vertices*.

    Returns:
        Tuple of (unique_vertices, remapped_faces).
    """
    unique_verts, inverse = np.unique(vertices, axis=0, return_inverse=True)
    remapped_faces = inverse[faces]
    return unique_verts, remapped_faces
