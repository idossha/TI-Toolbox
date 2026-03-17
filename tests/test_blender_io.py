"""Unit tests for tit/blender/io.py -- mesh I/O, colormap, and vertex utilities.

Covers:
- Binary STL write/read round-trip
- PLY writing (with colors and with scalars)
- simple_colormap and field_to_colormap
- deduplicate_vertices
"""

import struct

import numpy as np
import pytest

from tit.blender.io import (
    deduplicate_vertices,
    field_to_colormap,
    read_binary_stl,
    simple_colormap,
    write_binary_stl,
    write_ply_with_colors,
    write_ply_with_scalars,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def triangle_mesh():
    """A single-triangle mesh: 3 vertices, 1 face."""
    vertices = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float64
    )
    faces = np.array([[0, 1, 2]], dtype=np.int64)
    return vertices, faces


@pytest.fixture()
def quad_mesh():
    """A two-triangle quad: 4 vertices, 2 faces."""
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int64)
    return vertices, faces


# ---------------------------------------------------------------------------
# Binary STL round-trip
# ---------------------------------------------------------------------------


class TestBinarySTL:
    """write_binary_stl / read_binary_stl round-trip tests."""

    def test_single_triangle_roundtrip(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        path = str(tmp_path / "tri.stl")

        write_binary_stl(path, vertices, faces)
        v_out, f_out = read_binary_stl(path)

        assert v_out.shape == (3, 3)
        assert f_out.shape == (1, 3)
        np.testing.assert_allclose(v_out, vertices, atol=1e-5)
        np.testing.assert_array_equal(f_out, faces)

    def test_multi_face_roundtrip(self, tmp_path, quad_mesh):
        vertices, faces = quad_mesh
        path = str(tmp_path / "quad.stl")

        write_binary_stl(path, vertices, faces)
        v_out, f_out = read_binary_stl(path)

        assert v_out.shape == (4, 3)
        assert f_out.shape == (2, 3)
        # Vertex positions should survive the round-trip
        np.testing.assert_allclose(
            np.sort(v_out, axis=0), np.sort(vertices, axis=0), atol=1e-5
        )

    def test_with_explicit_normals(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        normals = np.array([[0.0, 0.0, 1.0]], dtype=np.float64)
        path = str(tmp_path / "norm.stl")

        write_binary_stl(path, vertices, faces, normals=normals)
        v_out, f_out = read_binary_stl(path)

        assert v_out.shape == (3, 3)
        assert f_out.shape == (1, 3)
        np.testing.assert_allclose(v_out, vertices, atol=1e-5)

    def test_stl_file_size(self, tmp_path, quad_mesh):
        """Binary STL has: 80-byte header + 4-byte count + 50 bytes per face."""
        vertices, faces = quad_mesh
        path = str(tmp_path / "size.stl")
        write_binary_stl(path, vertices, faces)

        import os

        expected_size = 80 + 4 + (50 * len(faces))
        assert os.path.getsize(path) == expected_size

    def test_header_text(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        path = str(tmp_path / "hdr.stl")
        write_binary_stl(path, vertices, faces, header_text="MyMesh")

        with open(path, "rb") as f:
            header = f.read(80)
        assert header.startswith(b"MyMesh")

    def test_degenerate_face_computes_normal(self, tmp_path):
        """A degenerate (zero-area) face should still produce a valid STL."""
        vertices = np.array(
            [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float64
        )
        faces = np.array([[0, 1, 2]], dtype=np.int64)
        path = str(tmp_path / "degen.stl")

        write_binary_stl(path, vertices, faces)
        # Should not raise; the fallback normal [0, 0, 1] is used.
        v_out, f_out = read_binary_stl(path)
        assert f_out.shape == (1, 3)


# ---------------------------------------------------------------------------
# PLY writers
# ---------------------------------------------------------------------------


class TestWritePlyWithColors:
    """write_ply_with_colors produces valid ASCII PLY."""

    def test_header_and_body(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        colors = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.uint8)
        path = str(tmp_path / "color.ply")

        write_ply_with_colors(path, vertices, faces, colors)

        with open(path) as f:
            lines = f.readlines()

        assert lines[0].strip() == "ply"
        assert lines[1].strip() == "format ascii 1.0"
        # Find vertex and face element counts in header
        header_text = "".join(lines)
        assert "element vertex 3" in header_text
        assert "element face 1" in header_text
        assert "property uchar red" in header_text
        assert "end_header" in header_text

    def test_vertex_count_matches(self, tmp_path, quad_mesh):
        vertices, faces = quad_mesh
        colors = np.array(
            [[255, 0, 0], [0, 255, 0], [0, 0, 255], [128, 128, 0]], dtype=np.uint8
        )
        path = str(tmp_path / "quad.ply")

        write_ply_with_colors(path, vertices, faces, colors)

        with open(path) as f:
            lines = f.readlines()

        # Count data lines after end_header
        header_end = next(i for i, l in enumerate(lines) if "end_header" in l)
        data_lines = lines[header_end + 1 :]
        # 4 vertex lines + 2 face lines
        assert len(data_lines) == 4 + 2

    def test_comment_included(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        colors = np.zeros((3, 3), dtype=np.uint8)
        path = str(tmp_path / "comment.ply")

        write_ply_with_colors(path, vertices, faces, colors, comment="test mesh")

        with open(path) as f:
            text = f.read()
        assert "comment test mesh" in text

    def test_no_comment_when_empty(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        colors = np.zeros((3, 3), dtype=np.uint8)
        path = str(tmp_path / "nocomment.ply")

        write_ply_with_colors(path, vertices, faces, colors, comment="")

        with open(path) as f:
            text = f.read()
        assert "comment" not in text


class TestWritePlyWithScalars:
    """write_ply_with_scalars produces valid ASCII PLY."""

    def test_header_contains_scalar_property(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        scalars = np.array([0.1, 0.5, 0.9], dtype=np.float64)
        path = str(tmp_path / "scalar.ply")

        write_ply_with_scalars(path, vertices, faces, scalars, scalar_name="intensity")

        with open(path) as f:
            text = f.read()

        assert "property float intensity" in text
        assert "element vertex 3" in text
        assert "element face 1" in text

    def test_default_scalar_name(self, tmp_path, triangle_mesh):
        vertices, faces = triangle_mesh
        scalars = np.array([1.0, 2.0, 3.0])
        path = str(tmp_path / "default_scalar.ply")

        write_ply_with_scalars(path, vertices, faces, scalars)

        with open(path) as f:
            text = f.read()
        assert "property float scalar" in text

    def test_data_line_count(self, tmp_path, quad_mesh):
        vertices, faces = quad_mesh
        scalars = np.array([0.0, 1.0, 2.0, 3.0])
        path = str(tmp_path / "quad_scalar.ply")

        write_ply_with_scalars(path, vertices, faces, scalars)

        with open(path) as f:
            lines = f.readlines()

        header_end = next(i for i, l in enumerate(lines) if "end_header" in l)
        data_lines = lines[header_end + 1 :]
        # 4 vertex lines + 2 face lines
        assert len(data_lines) == 4 + 2


# ---------------------------------------------------------------------------
# Colormaps
# ---------------------------------------------------------------------------


class TestSimpleColormap:
    """simple_colormap blue-to-red ramp."""

    def test_output_shape(self):
        values = np.array([0.0, 0.5, 1.0])
        result = simple_colormap(values)
        assert result.shape == (3, 3)

    def test_output_dtype(self):
        values = np.array([0.0, 1.0])
        result = simple_colormap(values)
        assert result.dtype == np.uint8

    def test_values_in_range(self):
        values = np.linspace(0, 100, 50)
        result = simple_colormap(values)
        assert np.all(result >= 0)
        assert np.all(result <= 255)

    def test_min_is_blue(self):
        values = np.array([0.0, 50.0, 100.0])
        result = simple_colormap(values)
        # Minimum value should have high blue, low red
        assert result[0, 2] > result[0, 0]  # blue > red for min

    def test_max_is_red(self):
        values = np.array([0.0, 50.0, 100.0])
        result = simple_colormap(values)
        # Maximum value should have high red, low blue
        assert result[2, 0] > result[2, 2]  # red > blue for max

    def test_constant_values_all_blue(self):
        values = np.array([5.0, 5.0, 5.0])
        result = simple_colormap(values)
        # When all values equal, all blue (edge case: vmax == vmin)
        np.testing.assert_array_equal(result[:, 2], 255)
        np.testing.assert_array_equal(result[:, 0], 0)

    def test_custom_vmin_vmax(self):
        values = np.array([5.0, 10.0])
        result = simple_colormap(values, vmin=0.0, vmax=20.0)
        assert result.shape == (2, 3)
        # 5/20 = 0.25 red; 10/20 = 0.5 red
        assert result[1, 0] > result[0, 0]

    def test_values_beyond_vmin_vmax_clamped(self):
        values = np.array([-10.0, 200.0])
        result = simple_colormap(values, vmin=0.0, vmax=100.0)
        # -10 clamped to 0 (all blue), 200 clamped to 1 (all red)
        assert result[0, 2] == 255  # blue channel maxed
        assert result[1, 0] == 255  # red channel maxed

    def test_monotonic_red_increases(self):
        values = np.linspace(0, 1, 10)
        result = simple_colormap(values)
        red_channel = result[:, 0].astype(int)
        # Red should be non-decreasing
        assert np.all(np.diff(red_channel) >= 0)


class TestFieldToColormap:
    """field_to_colormap with matplotlib (mocked) or fallback."""

    def test_output_shape(self):
        values = np.array([0.0, 0.5, 1.0])
        result = field_to_colormap(values)
        assert result.shape == (3, 3)

    def test_output_dtype_uint8(self):
        values = np.array([0.0, 1.0, 2.0])
        result = field_to_colormap(values)
        assert result.dtype == np.uint8

    def test_values_in_range(self):
        values = np.linspace(0, 10, 20)
        result = field_to_colormap(values)
        assert np.all(result >= 0)
        assert np.all(result <= 255)

    def test_custom_vmin_vmax(self):
        values = np.array([1.0, 2.0, 3.0])
        result = field_to_colormap(values, vmin=0.0, vmax=5.0)
        assert result.shape == (3, 3)

    def test_constant_values(self):
        values = np.array([3.0, 3.0, 3.0])
        result = field_to_colormap(values)
        # All same value, so all same color
        assert result.shape == (3, 3)
        np.testing.assert_array_equal(result[0], result[1])
        np.testing.assert_array_equal(result[1], result[2])


# ---------------------------------------------------------------------------
# Vertex deduplication
# ---------------------------------------------------------------------------


class TestDeduplicateVertices:
    """deduplicate_vertices merges duplicates and remaps faces."""

    def test_no_duplicates_noop(self, triangle_mesh):
        vertices, faces = triangle_mesh
        v_out, f_out = deduplicate_vertices(vertices, faces)
        assert v_out.shape == vertices.shape
        assert f_out.shape == faces.shape
        # np.unique may reorder rows; verify the same set of vertices exists
        np.testing.assert_array_equal(np.sort(v_out, axis=0), np.sort(vertices, axis=0))
        # Face indices should still reference valid vertices
        assert np.all(f_out >= 0)
        assert np.all(f_out < len(v_out))

    def test_duplicates_merged(self):
        # Two triangles sharing an edge, but with duplicate vertex entries
        vertices = np.array(
            [
                [0.0, 0.0, 0.0],  # 0
                [1.0, 0.0, 0.0],  # 1
                [0.0, 1.0, 0.0],  # 2
                [1.0, 0.0, 0.0],  # 3 — duplicate of 1
                [0.0, 1.0, 0.0],  # 4 — duplicate of 2
                [1.0, 1.0, 0.0],  # 5
            ],
            dtype=np.float64,
        )
        faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

        v_out, f_out = deduplicate_vertices(vertices, faces)

        # Should have only 4 unique vertices
        assert v_out.shape[0] == 4
        assert f_out.shape == (2, 3)

        # The two faces should reference valid indices
        assert np.all(f_out >= 0)
        assert np.all(f_out < len(v_out))

        # Face 0 and Face 1 should share 2 vertex indices
        shared = set(f_out[0].tolist()) & set(f_out[1].tolist())
        assert len(shared) == 2

    def test_all_same_vertex(self):
        # Pathological case: all vertices identical
        vertices = np.array(
            [[1.0, 2.0, 3.0]] * 6,
            dtype=np.float64,
        )
        faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)

        v_out, f_out = deduplicate_vertices(vertices, faces)

        assert v_out.shape[0] == 1
        # All face indices should be 0
        np.testing.assert_array_equal(f_out, np.zeros_like(f_out))

    def test_preserves_vertex_coordinates(self, quad_mesh):
        vertices, faces = quad_mesh
        v_out, f_out = deduplicate_vertices(vertices, faces)
        # Already unique, so same number of vertices; order may differ due to np.unique
        assert v_out.shape == vertices.shape
        np.testing.assert_array_equal(np.sort(v_out, axis=0), np.sort(vertices, axis=0))
