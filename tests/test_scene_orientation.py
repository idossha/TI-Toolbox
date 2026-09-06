"""What the scene builder *emits*: outward winding, a head-shaped framing box,
and a cache that cannot serve either from an older builder (lane CL1).

The defect this module was written for, measured on the running container on
2026-09-04 against the bytes ``GET /api/scene/surface`` actually served for
``sub-ernie``:

===========  ====================  ==========================================
part         signed volume (mm3)   triangles whose normal points away from the
                                   surface's own centroid
===========  ====================  ==========================================
``skin``     **+4 841 347**        99.5 %
``gm``       **-1 316 329**        30.9 %
===========  ====================  ==========================================

A *negative* enclosed volume means every triangle is wound inward. Any
translucent shell renderer or normal consumer that assumes outward faces would
therefore composite or shade ``gm`` inside-out, so the scene builder fixes the
convention before either TVSC compatibility bytes or Tetravox GIfTI bytes are
served.

Where the numbers come from
    Nothing here reads a real mesh: ``simnibs`` is a ``MagicMock`` in this
    suite, so :func:`tit.scene.build.build_surfaces` is driven through a fake
    ``read_msh`` returning surfaces this module generates in closed form. The
    orientation of each fixture is established **without** the code under test
    -- a UV sphere's outward normal is radial, which is a fact about spheres,
    not about :func:`tit.scene.build.orient_outward` -- and the volume a
    fixture encloses is arithmetic (a cube of side ``s`` encloses ``s**3``).
    The same properties on the real ernie/101/MNI152 meshes are
    ``tests/test_scene_realdata.py``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tit.paths import get_path_manager
from tit.scene import build, cache, tvsc


# ── fixtures whose orientation is known before the code under test runs ──────


def _uv_sphere(
    radii: tuple[float, float, float],
    centre: tuple[float, float, float] = (0.0, 0.0, 0.0),
    n_theta: int = 32,
    n_phi: int = 64,
) -> tuple[np.ndarray, np.ndarray]:
    """A closed ellipsoid, wound **outward**, with the winding derived not chosen.

    Parameterised by ``theta`` (polar, from +z) and ``phi``. For a sphere
    ``d/dtheta x d/dphi = sin(theta) * r_hat`` -- outward wherever
    ``sin(theta) > 0``, i.e. everywhere between the poles -- so the quad
    ``(i,j), (i,j+1), (i+1,j+1), (i+1,j)`` splits into the two triangles
    ``(a, d, b)`` and ``(b, d, c)``, whose edge pairs reproduce that cross
    product's sign. Scaling by positive radii is orientation-preserving.
    """
    theta = np.linspace(0.0, np.pi, n_theta + 1)
    phi = np.linspace(0.0, 2.0 * np.pi, n_phi, endpoint=False)
    tt, pp = np.meshgrid(theta, phi, indexing="ij")
    points = np.stack(
        [
            radii[0] * np.sin(tt) * np.cos(pp) + centre[0],
            radii[1] * np.sin(tt) * np.sin(pp) + centre[1],
            radii[2] * np.cos(tt) + centre[2],
        ],
        axis=-1,
    ).reshape(-1, 3)

    def vid(i: int, j: int) -> np.ndarray:
        return i * n_phi + (j % n_phi)

    i = np.repeat(np.arange(n_theta), n_phi)
    j = np.tile(np.arange(n_phi), n_theta)
    a, b, c, d = vid(i, j), vid(i, j + 1), vid(i + 1, j + 1), vid(i + 1, j)
    triangles = np.concatenate(
        [np.stack([a, d, b], axis=1), np.stack([b, d, c], axis=1)]
    ).astype(np.int64)
    return points, triangles


def _volume_by_tetrahedra(vertices: np.ndarray, triangles: np.ndarray) -> float:
    """``sum a.(b x c) / 6`` -- the enclosed volume, written a second way.

    Algebraically the same number :func:`tit.scene.build.signed_volume`
    produces and a different expression: the tetrahedron form about the
    origin, with no centroid shift and no ``(b - a)``/``(c - a)`` edges. A sign
    error in either would show up as a disagreement.
    """
    a, b, c = (vertices[triangles[:, k]] for k in range(3))
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _outward_fraction(vertices: np.ndarray, triangles: np.ndarray) -> float:
    """Fraction of triangles whose normal points away from the vertex centroid.

    Exact for a star-shaped surface about its centroid (a sphere), indicative
    for a folded one -- the same two criteria lane FIX-A measured on the real
    payloads. Zero-area triangles are excluded rather than counted as
    disagreements: a UV sphere's poles are ``n_phi`` coincident vertices, so
    one row of its quads collapses, and a degenerate triangle has no side to
    face.
    """
    a, b, c = (vertices[triangles[:, k]] for k in range(3))
    normals = np.cross(b - a, c - a)
    radial = (a + b + c) / 3.0 - vertices.mean(axis=0)
    real = np.linalg.norm(normals, axis=1) > 1e-9
    if not real.any():  # pragma: no cover - a fixture with no area at all
        return 0.0
    return float((np.einsum("ij,ij->i", normals[real], radial[real]) > 0).mean())


#: The synthetic head: an outward-wound scalp with a neck, and a grey matter
#: wound **inward** the way SimNIBS's tag-1002 elements really come out.
GM_CENTRE_Z = 10.0
GM_RADIUS = 40.0
GM_FLOOR_Z = GM_CENTRE_Z - GM_RADIUS  # -30.0
NECK_STRETCH = 3.0


def _fake_head() -> dict[int, tuple[np.ndarray, np.ndarray]]:
    skin_v, skin_t = _uv_sphere((70.0, 80.0, 90.0), (0.0, 0.0, GM_CENTRE_Z))
    # A neck: everything below the grey matter's floor is pulled down, which is
    # monotone in z and so leaves the winding alone. Skin then runs to
    # z = -180 while the brain stops at -30, the same shape ernie has
    # (-128.9 against -50.7).
    below = skin_v[:, 2] < GM_FLOOR_Z
    skin_v[below, 2] = GM_FLOOR_Z + (skin_v[below, 2] - GM_FLOOR_Z) * NECK_STRETCH

    gm_v, gm_t = _uv_sphere(
        (GM_RADIUS, GM_RADIUS, GM_RADIUS), (0.0, 0.0, GM_CENTRE_Z)
    )
    return {
        build.PART_TAGS["skin"]: (skin_v, skin_t),
        # Inward: the defect, reproduced.
        build.PART_TAGS["gm"]: (gm_v, gm_t[:, [0, 2, 1]]),
    }


class _FakeCropped:
    def __init__(self, vertices: np.ndarray, triangles: np.ndarray) -> None:
        self.nodes = SimpleNamespace(node_coord=vertices)
        # SimNIBS packs a triangle into the first 3 of 4 columns, 1-based.
        self.elm = SimpleNamespace(
            node_number_list=np.column_stack(
                [triangles + 1, np.zeros(len(triangles), dtype=np.int64)]
            ),
            elm_type=np.full(len(triangles), 2),
        )


class _FakeMesh:
    def __init__(self, by_tag: dict[int, tuple[np.ndarray, np.ndarray]]) -> None:
        self._by_tag = by_tag

    def crop_mesh(self, tags):  # noqa: ANN001 - mirrors simnibs' signature
        vertices, triangles = self._by_tag[tags[0]]
        return _FakeCropped(vertices.copy(), triangles.copy())


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project whose one subject's head mesh is the synthetic head above."""
    pm = get_path_manager(str(tmp_path))
    Path(pm.m2m("ernie")).mkdir(parents=True)
    (Path(pm.m2m("ernie")) / "ernie.msh").write_bytes(b"a fake mesh with a real shape")
    head = _fake_head()
    monkeypatch.setattr(
        sys.modules["simnibs.mesh_tools.mesh_io"],
        "read_msh",
        lambda _path: _FakeMesh(head),
    )
    return tmp_path


def _published(project: Path, part: str) -> tuple[np.ndarray, np.ndarray, dict]:
    pm = get_path_manager()
    entry = cache.find_cached(
        project, "ernie", part, build.surface_fingerprint(pm, "ernie")
    )
    assert entry is not None, f"{part} was not published"
    payload = tvsc.decode(entry.path.read_bytes())
    vertices = payload.positions.astype(np.float64)
    triangles = payload.indices.reshape(-1, 3).astype(np.int64)
    return vertices, triangles, entry.meta


# ── the pure criterion ───────────────────────────────────────────────────────


def test_signed_volume_of_a_cube_is_the_cube_of_its_side() -> None:
    """Arithmetic, not a fixture: a 3 mm cube encloses 27 mm3, either way up."""
    side = 3.0
    corners = np.array(
        [[x, y, z] for x in (0.0, side) for y in (0.0, side) for z in (0.0, side)]
    )
    # Faces wound outward, written out rather than generated.
    quads = [
        (0, 1, 3, 2),  # x = 0, normal -x
        (4, 6, 7, 5),  # x = s, normal +x
        (0, 4, 5, 1),  # y = 0, normal -y
        (2, 3, 7, 6),  # y = s, normal +y
        (0, 2, 6, 4),  # z = 0, normal -z
        (1, 5, 7, 3),  # z = s, normal +z
    ]
    triangles = np.array(
        [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))], dtype=np.int64
    )
    assert _outward_fraction(corners, triangles) == 1.0
    assert build.signed_volume(corners, triangles) == pytest.approx(side**3)
    assert build.signed_volume(corners, triangles[:, [0, 2, 1]]) == pytest.approx(
        -(side**3)
    )


def test_signed_volume_does_not_depend_on_where_the_surface_sits() -> None:
    """A closed surface's enclosed volume is a property of the surface."""
    vertices, triangles = _uv_sphere((20.0, 20.0, 20.0))
    here = build.signed_volume(vertices, triangles)
    far = build.signed_volume(vertices + np.array([500.0, -900.0, 4000.0]), triangles)
    assert here == pytest.approx(far, rel=1e-9)
    # And it is the sphere's volume, to the accuracy of a 32x64 tessellation.
    assert here == pytest.approx(4 / 3 * np.pi * 20.0**3, rel=0.01)


def test_signed_volume_agrees_with_an_independently_written_expression() -> None:
    vertices, triangles = _uv_sphere((70.0, 80.0, 90.0), (5.0, -3.0, 11.0))
    assert build.signed_volume(vertices, triangles) == pytest.approx(
        _volume_by_tetrahedra(vertices, triangles), rel=1e-9
    )


def test_orient_outward_flips_an_inward_surface_and_says_so() -> None:
    vertices, triangles = _uv_sphere((40.0, 40.0, 40.0))
    inward = triangles[:, [0, 2, 1]]
    assert _outward_fraction(vertices, inward) == 0.0

    fixed, flipped = build.orient_outward(vertices, inward)
    assert flipped is True
    assert _outward_fraction(vertices, fixed) == 1.0
    assert build.signed_volume(vertices, fixed) > 0


def test_orient_outward_leaves_an_outward_surface_alone() -> None:
    vertices, triangles = _uv_sphere((40.0, 40.0, 40.0))
    fixed, flipped = build.orient_outward(vertices, triangles)
    assert flipped is False
    assert np.array_equal(fixed, triangles)


def test_orienting_moves_no_vertex_and_keeps_every_triangle() -> None:
    """A flip permutes indices; positions, labels and counts are untouched.

    This is what lets the fix land without disturbing the label transfer or
    the electrode alignment, both of which are keyed on vertex position.
    """
    vertices, triangles = _uv_sphere((40.0, 40.0, 40.0))
    fixed, _ = build.orient_outward(vertices, triangles[:, [0, 2, 1]])
    assert fixed.shape == triangles.shape
    assert {frozenset(t) for t in fixed.tolist()} == {
        frozenset(t) for t in triangles.tolist()
    }


# ── what the builder publishes ───────────────────────────────────────────────


def test_every_published_surface_encloses_a_positive_volume(project: Path) -> None:
    """The regression: ``gm`` came off the mesh inward and must not be served so.

    Both criteria FIX-A measured on the container, on the bytes the cache
    holds, computed here by expressions this module owns.
    """
    metas = build.build_surfaces(get_path_manager(), "ernie")
    for part in ("skin", "gm"):
        vertices, triangles, meta = _published(project, part)
        volume = _volume_by_tetrahedra(vertices, triangles)
        assert volume > 0, f"{part} encloses {volume:,.1f} mm3 -- wound inward"
        assert meta["signed_volume_mm3"] == pytest.approx(volume, rel=1e-6)
        assert metas[part]["signed_volume_mm3"] > 0

    # The grey matter is a sphere here, so "away from the centroid" is exact.
    gm_v, gm_t, gm_meta = _published(project, "gm")
    assert _outward_fraction(gm_v, gm_t) == 1.0
    # And the sidecar records that the mesh's own convention for this tag was
    # inward, so a change upstream is visible rather than silently absorbed.
    assert gm_meta["winding_flipped"] is True
    assert _published(project, "skin")[2]["winding_flipped"] is False


def test_the_framing_box_cuts_the_neck_off_at_the_grey_matters_floor(
    project: Path,
) -> None:
    """``focus_bbox`` is the head; ``bbox`` is the head and the neck."""
    build.build_surfaces(get_path_manager(), "ernie")
    _, _, skin = _published(project, "skin")
    _, _, gm = _published(project, "gm")

    assert gm["bbox"][2] == pytest.approx(GM_FLOOR_Z, abs=1e-3)
    # Grey matter has nothing below its own floor, so its focus box is its box.
    assert gm["focus_bbox"] == gm["bbox"]

    # The scalp runs far below it and the focus box does not follow.
    assert skin["bbox"][2] < GM_FLOOR_Z - 100
    assert skin["focus_bbox"][2] >= GM_FLOOR_Z
    # Nothing else moves: the focus box is a z-floor, not a different box.
    assert skin["focus_bbox"][3:] == skin["bbox"][3:]

    height = skin["bbox"][5] - skin["bbox"][2]
    focused = skin["focus_bbox"][5] - skin["focus_bbox"][2]
    assert focused / height < 0.6, "the neck is most of the box being framed"


# ── the cache cannot outlive the builder that wrote it ───────────────────────


def test_the_fingerprint_changes_when_the_builder_does(project: Path) -> None:
    """The salt is what makes a code change reach an unchanged mesh."""
    pm = get_path_manager()
    sources = build.surface_sources(pm, "ernie")
    assert build.surface_fingerprint(pm, "ernie") == cache.fingerprint(
        sources, build.BUILDER_VERSION
    )
    assert build.surface_fingerprint(pm, "ernie") != cache.fingerprint(sources)
    assert build.surface_fingerprint(pm, "ernie") != cache.fingerprint(
        sources, "some other builder"
    )
    # Labels are positions copied out of the gm payload, so they are salted too.
    assert build.labels_fingerprint(pm, "ernie", "DK40") != cache.fingerprint(
        build.label_sources(pm, "ernie", "DK40")
    )


def test_an_entry_an_older_builder_wrote_is_never_served_and_is_deleted(
    project: Path,
) -> None:
    """A stale payload must not survive a builder change -- twice over.

    It is not *found* (the fingerprint no longer matches), and the rebuild's
    ``publish`` prunes it, so the cache does not grow a copy per version.
    """
    pm = get_path_manager()
    stale_fp = cache.fingerprint(build.surface_sources(pm, "ernie"))  # unsalted = v1
    vertices, triangles = _uv_sphere((1.0, 1.0, 1.0))
    stale = cache.publish(
        project,
        "ernie",
        "gm",
        stale_fp,
        tvsc.encode(vertices, triangles[:, [0, 2, 1]].astype(np.uint32)),
        {"part": "gm", "bbox": [0, 0, 0, 1, 1, 1], "build_ms": 0.0},
    )
    assert stale.path.is_file()

    current = build.surface_fingerprint(pm, "ernie")
    assert current != stale_fp
    assert cache.find_cached(project, "ernie", "gm", current) is None

    build.build_surfaces(pm, "ernie")
    assert cache.find_cached(project, "ernie", "gm", current) is not None
    assert not stale.path.exists(), "the old builder's payload is still on disk"
    assert not stale.sidecar.exists()
