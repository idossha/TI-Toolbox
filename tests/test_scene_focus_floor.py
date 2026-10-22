"""The grey matter's framing box is its whole box, and the skin is cut at that same floor.

What this pins
    :func:`tit.scene.build.build_surfaces` writes, per part, a ``bbox`` and a ``focus_bbox``
    (the part's box with everything below the grey matter's floor cut off). The grey matter's
    own ``focus_bbox`` must equal its ``bbox`` -- :func:`tit.scene.build.focus_bbox` promises
    "the grey matter's own contribution is always its whole box" -- and the skin must be cut
    at the floor that ``bbox`` reports, not at a different one.

    The defect (Dataset 000 real-data leg on idossha/ti-toolbox:v3.1.1, 2026-10-22):
    ``sub-101``'s grey matter had ``focus_bbox`` z0 = -92.335 but ``bbox`` z0 = -92.396. The
    floor came from the extracted float64 vertices and the boxes from the published float32
    ones; its lowest vertex survives simplification, and ``float32(-92.3963462661399)`` is
    -92.39634704589844, 7.8e-7 mm *below* the float64 floor, so the floor cut the grey
    matter's own lowest vertex out of its focus box (container probe: the source floor,
    the surviving vertex index and both roundings printed from the real mesh).

    Two consequences of the fix: a sidecar the previous builder ("4") cached for an unchanged
    mesh is not what the scene route finds (only the builder version can expire it), and
    each part's ``build_ms`` still counts its own simplification, which now runs in a loop of
    its own before the floor is read.

Where the numbers come from
    Hand-made octahedra, not a real mesh (``simnibs`` is a ``MagicMock`` here, so
    ``read_msh`` is replaced by a fake that crops these arrays). The floor value is sub-101's
    real float64 grey-matter floor; that it rounds *down* in float32 is checked by NumPy's own
    cast before anything else runs. Every expected box is computed here from the arrays (and,
    for what was published, from the cached ``.tvsc`` bytes read back with ``tvsc.decode``),
    never from the sidecar under test. The second case lowers the grey matter's published
    floor 0.1 mm below its input minimum, the shape of a simplifier that places vertices off
    the input (centroid or quadric placement), so the rule holds whatever the simplifier does.
    The stale sidecar carries the real leg's measured boxes; the build times come from a fake
    clock that moves only in the mesh read and in each simplification.

How to run it
    ``python -m pytest tests/test_scene_focus_floor.py -q -p no:cacheprovider``

Deliberately elsewhere
    Winding and the neck crop on a sphere: ``tests/test_scene_orientation.py``. The same
    property on real meshes: ``tests/test_scene_realdata.py``
    (``dev/run_realdata_tests.sh``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tit.paths import get_path_manager
from tit.scene import build, cache, tvsc
from tit.scene.simplify import SimplifyResult

#: sub-101's lowest grey-matter vertex z (mm), float64, read from its head mesh in the image.
SUB101_GM_FLOOR = -92.3963462661399
#: The skin's top and its neck, far above and below the brain.
SKIN_TOP, NECK = 110.0, -180.0


def _octahedron(
    ring_z: float, bottom_z: float, top_z: float, rx: float, ry: float
) -> tuple[np.ndarray, np.ndarray]:
    """Six vertices, eight triangles: a ring of four at *ring_z* plus a top and a bottom."""
    vertices = np.array(
        [
            [rx, 0.0, ring_z],
            [0.0, ry, ring_z],
            [-rx, 0.0, ring_z],
            [0.0, -ry, ring_z],
            [0.0, 0.0, top_z],
            [0.0, 0.0, bottom_z],
        ]
    )
    ring = [(0, 1), (1, 2), (2, 3), (3, 0)]
    triangles = np.array(
        [(a, b, 4) for a, b in ring] + [(b, a, 5) for a, b in ring], dtype=np.int64
    )
    return vertices, triangles


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


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, head: dict) -> Path:
    pm = get_path_manager(str(tmp_path))
    Path(pm.m2m("101")).mkdir(parents=True)
    (Path(pm.m2m("101")) / "101.msh").write_bytes(b"a fake mesh with a real shape")
    monkeypatch.setattr(
        sys.modules["simnibs.mesh_tools.mesh_io"],
        "read_msh",
        lambda _p: _FakeMesh(head),
    )
    return tmp_path


def _published_vertices(project: Path, part: str) -> np.ndarray:
    """The vertices of the cached ``.tvsc`` payload, read back by the format's decoder."""
    fp = build.surface_fingerprint(get_path_manager(), "101")
    entry = cache.find_cached(project, "101", part, fp)
    assert entry is not None, f"{part} was not published"
    return tvsc.decode(entry.path.read_bytes()).positions.astype(np.float64)


def _box(vertices: np.ndarray) -> list[float]:
    return [round(float(x), 3) for x in (*vertices.min(axis=0), *vertices.max(axis=0))]


def test_sub101s_floor_rounds_below_itself_in_float32() -> None:
    """The precondition, from NumPy's cast alone: the published floor is lower."""
    assert float(np.float32(SUB101_GM_FLOOR)) < SUB101_GM_FLOOR
    assert SUB101_GM_FLOOR - float(np.float32(SUB101_GM_FLOOR)) < 1e-6


def test_a_floor_that_float32_rounds_down_stays_in_the_grey_matters_own_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """sub-101's case: the grey matter's lowest vertex is published, rounded down."""
    gm_v, gm_t = _octahedron(-20.0, SUB101_GM_FLOOR, 41.0, 60.0, 75.0)
    # The skin's ring sits exactly at the grey matter's floor (same float64 value), so it is
    # at the floor after both are published and must stay in the skin's focus box.
    skin_v, skin_t = _octahedron(SUB101_GM_FLOOR, NECK, SKIN_TOP, 70.0, 80.0)
    project = _project(
        tmp_path,
        monkeypatch,
        {
            build.PART_TAGS["gm"]: (gm_v, gm_t),
            build.PART_TAGS["skin"]: (skin_v, skin_t),
        },
    )

    metas = build.build_surfaces(get_path_manager(), "101")

    gm_published = _published_vertices(project, "gm")
    gm_floor = float(gm_published[:, 2].min())
    assert gm_floor == float(np.float32(SUB101_GM_FLOOR)), "the lowest vertex is served"
    assert metas["gm"]["bbox"] == _box(gm_published)
    assert metas["gm"]["bbox"][2] == -92.396
    assert metas["gm"]["focus_bbox"] == metas["gm"]["bbox"]

    skin_published = _published_vertices(project, "skin")
    kept = skin_published[skin_published[:, 2] >= gm_floor]
    assert len(kept) == 5, "the ring at the floor and the top are kept, the neck is cut"
    assert metas["skin"]["focus_bbox"] == _box(kept)
    assert metas["skin"]["focus_bbox"] == [-70.0, -80.0, -92.396, 70.0, 80.0, SKIN_TOP]
    # The skin is still cropped: its box runs down the neck, its focus box does not.
    assert metas["skin"]["bbox"][2] == NECK
    assert metas["skin"]["focus_bbox"][3:] == metas["skin"]["bbox"][3:]


def test_a_simplified_floor_below_the_input_floor_is_the_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A simplifier whose grey matter reaches 0.1 mm below its input minimum.

    The floor every part is cut at is the grey matter's published floor, so the grey
    matter keeps its whole box and a skin vertex between the two floors stays framed.
    """
    gm_v, gm_t = _octahedron(-20.0, -50.0, 41.0, 60.0, 75.0)
    skin_v, skin_t = _octahedron(-50.05, NECK, SKIN_TOP, 70.0, 80.0)
    project = _project(
        tmp_path,
        monkeypatch,
        {
            build.PART_TAGS["gm"]: (gm_v, gm_t),
            build.PART_TAGS["skin"]: (skin_v, skin_t),
        },
    )
    real = build.simplify_to_budget

    def lowering(vertices, triangles, max_triangles, max_bytes=None):  # noqa: ANN001
        result = real(vertices, triangles, max_triangles, max_bytes)
        if not np.array_equal(vertices, gm_v):
            return result
        moved = result.vertices.copy()
        moved[np.argmin(moved[:, 2]), 2] -= np.float32(0.1)
        return SimplifyResult(
            vertices=moved,
            triangles=result.triangles,
            source_index=result.source_index,
            cell=result.cell,
            max_deviation=result.max_deviation,
            rounds=result.rounds,
        )

    monkeypatch.setattr(build, "simplify_to_budget", lowering)

    metas = build.build_surfaces(get_path_manager(), "101")

    gm_published = _published_vertices(project, "gm")
    gm_floor = float(gm_published[:, 2].min())
    assert gm_floor == pytest.approx(-50.1, abs=1e-5)
    assert metas["gm"]["bbox"][2] == -50.1
    assert metas["gm"]["focus_bbox"] == metas["gm"]["bbox"]

    skin_published = _published_vertices(project, "skin")
    assert skin_published[:, 2].min() == NECK
    assert metas["skin"]["focus_bbox"] == [-70.0, -80.0, -50.05, 70.0, 80.0, SKIN_TOP]
    assert metas["skin"]["bbox"][2] == NECK


def _sub101_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[int, tuple[np.ndarray, np.ndarray]]]:
    gm = _octahedron(-20.0, SUB101_GM_FLOOR, 41.0, 60.0, 75.0)
    skin = _octahedron(SUB101_GM_FLOOR, NECK, SKIN_TOP, 70.0, 80.0)
    head = {build.PART_TAGS["gm"]: gm, build.PART_TAGS["skin"]: skin}
    return _project(tmp_path, monkeypatch, head), head


def test_a_sidecar_the_previous_builder_cached_is_not_served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unchanged mesh keeps its source fingerprint; only the builder version expires the
    sidecar builder "4" (the one before this fix) cached with sub-101's cropped focus box.
    """
    project, head = _sub101_head(tmp_path, monkeypatch)
    pm = get_path_manager()
    gm_v, gm_t = head[build.PART_TAGS["gm"]]
    stale_fp = cache.fingerprint(build.surface_sources(pm, "101"), "4")
    # The defect as the real leg measured it: focus z0 -92.335 against a bbox z0 -92.396.
    stale = {
        "bbox": [-60.0, -75.0, -92.396, 60.0, 75.0, 41.0],
        "focus_bbox": [-60.0, -75.0, -92.335, 60.0, 75.0, 41.0],
    }
    cache.publish(project, "101", "gm", stale_fp, tvsc.encode(gm_v, gm_t), stale)
    assert cache.find_cached(project, "101", "gm", stale_fp) is not None

    # What the scene route looks the part up by (tit/server/routes/scene.py _surface_ready).
    served_fp = build.surface_fingerprint(pm, "101")
    assert cache.find_cached(project, "101", "gm", served_fp) is None, "stale served"

    build.build_surfaces(pm, "101")

    served = cache.find_cached(project, "101", "gm", served_fp)
    assert served.meta["focus_bbox"] == served.meta["bbox"]
    assert served.meta["bbox"][2] == -92.396
    assert cache.find_cached(project, "101", "gm", stale_fp) is None, "not expired"


def test_each_parts_build_time_is_the_read_plus_its_own_simplification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simplification now runs before the floor, in its own loop; its time stays its part's.

    A clock that moves only in the one mesh read (1 s) and in each part's simplification
    (grey matter 2 s, skin 3 s) gives every sidecar time by hand: ``build_ms`` is the shared
    read plus the part's own work, ``mesh_read_ms`` the read alone.
    """
    _project_dir, head = _sub101_head(tmp_path, monkeypatch)
    gm_v, _gm_t = head[build.PART_TAGS["gm"]]
    clock = [0.0]

    def reading(_path):  # noqa: ANN001, ANN202 - stands in for mesh_io.read_msh
        clock[0] += 1.0
        return _FakeMesh(head)

    real = build.simplify_to_budget

    def timed(
        vertices, triangles, max_triangles, max_bytes=None
    ):  # noqa: ANN001, ANN202
        clock[0] += 2.0 if np.array_equal(vertices, gm_v) else 3.0
        return real(vertices, triangles, max_triangles, max_bytes)

    monkeypatch.setattr(sys.modules["simnibs.mesh_tools.mesh_io"], "read_msh", reading)
    monkeypatch.setattr(build, "simplify_to_budget", timed)
    monkeypatch.setattr(build, "time", SimpleNamespace(perf_counter=lambda: clock[0]))

    metas = build.build_surfaces(get_path_manager(), "101")

    assert {part: meta["build_ms"] for part, meta in metas.items()} == {
        "gm": 3000.0,
        "skin": 4000.0,
    }
    assert {meta["mesh_read_ms"] for meta in metas.values()} == {1000.0}
