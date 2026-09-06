"""Real-data proof of the two things only real data can prove (lane SCA).

What this pins
    1. **Region labels are aligned to the ``gm`` surface that is served.** For
       every region of a real atlas, the centroid of the GM vertices carrying
       that region's ``uint16`` label must fall inside the bounding box the
       ``.annot`` file gives for the same region, read independently from the
       central surface. Without it, a pane highlights the wrong gyrus and
       nothing else in the suite notices.
    2. **Electrodes are in the surfaces' space and units.** Every electrode of
       a real net must be within 15 mm of the served skin surface. A space or
       millimetre/metre mistake is invisible until a user sees markers
       floating beside the head.
    Plus the §S3 budget on a real mesh, which the synthetic suite cannot
    measure.

How to run it
    Inside the dev container, where ``simnibs``/``nibabel``/``scipy`` are real::

        docker exec -e TIT_SCENE_TESTDATA=/mnt/000 ti-toolbox-<stack>-tit-1 \\
          bash -lc 'cd /ti-toolbox && simnibs_python -m pytest -q tests/test_scene_realdata.py'

    ``TIT_SCENE_SUBJECT`` picks the subject (default ``ernie``);
    ``TIT_SCENE_ATLAS`` the atlas (default ``DK40``). With
    ``TIT_SCENE_TESTDATA`` unset every test here skips with a printed reason,
    which is the state CI must be in -- this suite writes a scene cache into
    the project it is pointed at.

Where the numbers come from
    Nothing is retyped. Each expectation is either a budget decision S3 states
    (150 000 triangles, 3 MB), a tolerance stated with what it absorbs
    (15 mm electrode-to-skin, 1 mm bounding-box margin), or a value read from
    the ``.annot``/``.gii`` pair by ``nibabel`` -- a different reader than the
    builder's KD-tree path. Measured results are printed so a run can be
    pasted into ``dev/notes/v3-scene-ia/sca-notes.md``.

Deliberately elsewhere
    Format bytes, clustering properties, cache semantics and route behaviour
    are the four synthetic suites (``tests/test_scene_{tvsc,simplify,cache,
    routes,build}.py``), which run everywhere.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

ENV_ROOT = "TIT_SCENE_TESTDATA"
DEFAULT_SUBJECT = "ernie"
DEFAULT_ATLAS = "DK40"

#: An electrode is placed on the scalp, and the served skin surface has ~2 mm
#: vertex spacing, so nearest-*vertex* distance overstates the true
#: surface distance by up to ~1 mm. 15 mm absorbs that plus the couple of
#: millimetres of gel/cap thickness charm models, and is still an order of
#: magnitude tighter than any space or unit error could survive: a
#: metre/millimetre mix-up is off by 10^3, an LPS/RAS flip by tens of mm.
ELECTRODE_TO_SKIN_MM = 15.0

#: The GM surface's vertices are a subset of the head mesh's, and the annot's
#: are the central surface's -- two different triangulations of one anatomy.
#: 1 mm covers a centroid sitting just outside a thin region's own box because
#: the two surfaces do not coincide exactly.
BBOX_MARGIN_MM = 1.0

#: A region needs enough vertices for a centroid to mean anything; below this
#: a single stray vertex dominates. 20 is ~0.03 % of the served GM surface.
MIN_REGION_VERTICES = 20


def _real_modules_or_skip() -> None:
    """Undo ``tests/conftest.py``'s mocks for this module, or skip.

    ``conftest.pytest_configure`` puts ``MagicMock``s in ``sys.modules`` for
    ``simnibs``/``nibabel``/``scipy`` so the host suite runs without them. This
    module is the one that needs the real thing, so it drops those entries and
    lets the import machinery find the installed packages -- which only exist
    inside the SimNIBS container.
    """
    for name in list(sys.modules):
        root = name.split(".")[0]
        if root in {"simnibs", "nibabel", "scipy"} and isinstance(
            sys.modules[name], MagicMock
        ):
            del sys.modules[name]
    for name in ("simnibs", "nibabel", "scipy.spatial"):
        try:
            module = __import__(name)
        except Exception as exc:  # noqa: BLE001
            print(f"skipping: {name} is not importable here ({exc})")
            pytest.skip(f"{name} is not installed (run inside the SimNIBS container)")
        if getattr(module, "__file__", None) is None:
            print(f"skipping: {name} is still a mock, not the real package")
            pytest.skip(f"{name} is mocked, not real")


@pytest.fixture(scope="module")
def project_root() -> str:
    root = os.environ.get(ENV_ROOT)
    if not root:
        print(f"skipping: {ENV_ROOT} is unset (no real BIDS project to read)")
        pytest.skip(f"{ENV_ROOT} is unset")
    if not Path(root).is_dir():
        print(f"skipping: {ENV_ROOT}={root} is not a directory")
        pytest.skip(f"{ENV_ROOT}={root} does not exist")
    _real_modules_or_skip()
    return root


@pytest.fixture(scope="module")
def subject() -> str:
    return os.environ.get("TIT_SCENE_SUBJECT", DEFAULT_SUBJECT)


@pytest.fixture(scope="module")
def atlas() -> str:
    return os.environ.get("TIT_SCENE_ATLAS", DEFAULT_ATLAS)


@pytest.fixture(scope="module")
def pm(project_root: str):
    from tit.paths import get_path_manager

    return get_path_manager(project_root)


@dataclass(frozen=True)
class Payload:
    """One decoded surface, whichever serialisation it arrived in.

    The same three arrays :class:`tit.scene.tvsc.TvscPayload` carries, so every
    test below reads a payload without knowing which format it came from --
    which is the point: decision E7 changes the *serialisation* and nothing
    else, and a proof that only ever ran against ``TVSC1`` would not say so.
    """

    positions: np.ndarray
    indices: np.ndarray
    labels: np.ndarray | None
    #: Present for a GIfTI payload that carried a ``<LabelTable>``: key -> name.
    label_table: dict[int, str] | None = None

    @property
    def vertex_count(self) -> int:
        return int(self.positions.shape[0])

    @property
    def triangle_count(self) -> int:
        return int(self.indices.shape[0])


def _decode(path: Path, fmt: str) -> Payload:
    """Decode a cached payload with a reader that is not the writer.

    ``tvsc`` goes through :func:`tit.scene.tvsc.decode` (this repository's own
    reader, which the byte-level suite already pins against fixtures) and
    ``gii`` through **nibabel**, deliberately: the writer is hand-rolled XML in
    :mod:`tit.scene.gifti`, so a round trip through our own parser would prove
    only that it agrees with itself. nibabel is the third-party reader that
    says the bytes really are GIfTI.
    """
    if fmt == "tvsc":
        from tit.scene import tvsc

        payload = tvsc.decode(path.read_bytes())
        return Payload(payload.positions, payload.indices, payload.labels)

    import nibabel as nib

    image = nib.load(str(path))
    by_intent = {int(d.intent): d for d in image.darrays}
    positions = np.asarray(by_intent[1008].data, dtype=np.float32)
    triangle = by_intent.get(1009)
    indices = (
        np.asarray(triangle.data, dtype=np.uint32)
        if triangle is not None
        else np.zeros((0, 3), dtype=np.uint32)
    )
    label = by_intent.get(1002)
    labels = np.asarray(label.data, dtype=np.uint16) if label is not None else None
    table = image.labeltable.get_labels_as_dict() if label is not None else None
    return Payload(positions, indices, labels, table)


@pytest.fixture(scope="module", params=["tvsc", "gii"], ids=lambda f: f"format={f}")
def scene_format(request) -> str:
    """Every alignment proof below runs once per serialisation (decision E7).

    Both come out of **one** build, from the same vertices and triangles, so a
    disagreement between the two parameters is a serialisation bug and nothing
    else -- which is exactly the failure a format change introduces.
    """
    return request.param


@pytest.fixture(scope="module")
def surfaces(pm, subject: str, scene_format: str) -> dict:
    """Both surface payloads, built for real and decoded from the cache."""
    from tit.scene import build, cache

    metas = build.build_surfaces(pm, subject)
    fingerprint = build.surface_fingerprint(pm, subject)
    out = {}
    for part, meta in metas.items():
        entry = cache.find_cached(
            pm.project_dir, subject, part, fingerprint, scene_format
        )
        assert entry is not None, f"{part} was built but not published as {scene_format}"
        out[part] = {"meta": meta, "payload": _decode(entry.path, scene_format)}
        print(
            f"[{subject}] {part} ({scene_format}): {meta['source_triangles']} -> "
            f"{meta['triangles']} triangles, {meta['vertices']} vertices, "
            f"{meta['format_bytes'][scene_format]} bytes, "
            f"cell {meta['cell_mm']} mm, max deviation "
            f"{meta['max_deviation_mm']} mm, {meta['build_ms']} ms"
        )
    return out


@pytest.fixture(scope="module")
def labels(pm, subject: str, atlas: str, surfaces: dict, scene_format: str) -> dict:
    from tit.scene import build, cache

    meta = build.build_labels(pm, subject, atlas)
    entry = cache.find_cached(
        pm.project_dir,
        subject,
        build._labels_key(atlas),
        meta["fingerprint"],
        scene_format,
    )
    assert entry is not None
    print(
        f"[{subject}] {atlas} ({scene_format}): {meta['regions']} regions over "
        f"{meta['vertices']} vertices, {meta['labelled_fraction'] * 100:.1f} % "
        f"labelled within {meta['radius_mm']} mm, {meta['build_ms']} ms, "
        f"{meta['format_bytes'][scene_format]} bytes"
    )
    return {"meta": meta, "payload": _decode(entry.path, scene_format)}


# ── §S3 budgets, on a real mesh ──────────────────────────────────────────────


def test_both_surfaces_meet_the_s3_budget(surfaces: dict) -> None:
    """150 000 triangles and 3 MB per surface (decision S3)."""
    from tit.scene import build

    assert set(surfaces) == {"skin", "gm"}
    for part, entry in surfaces.items():
        meta = entry["meta"]
        assert meta["triangles"] <= build.MAX_TRIANGLES, part
        # The budget is a *wire* budget, so it applies to every serialisation
        # the route can hand out, not only to the one `bytes` happens to name.
        for name, size in meta["format_bytes"].items():
            assert size <= build.MAX_BYTES, f"{part} as {name}: {size} bytes"
        assert meta["within_budget"] is True, part
        assert meta["triangles"] > 1000, f"{part} collapsed to nothing"


def test_the_skin_surface_is_shipped_untouched(surfaces: dict) -> None:
    """Measured at 77 032 triangles -- already inside the budget, so no error."""
    meta = surfaces["skin"]["meta"]
    assert meta["simplified"] is False
    assert meta["triangles"] == meta["source_triangles"]
    assert meta["max_deviation_mm"] == 0.0


def test_simplifying_gm_reports_a_deviation_in_the_millimetre_range(
    surfaces: dict,
) -> None:
    """Sanity band, not a pinned value.

    The exact figure is measured against an independent ``cKDTree`` in
    ``test_every_served_gm_vertex_is_an_untouched_mesh_vertex`` below and
    printed for the lane notes; pinning it here would fail on the next subject
    rather than on a regression. What is asserted is that it exists, is
    positive, and is single-digit millimetres -- a clustering bug that merged
    across the hemispheres would put it in the tens.
    """
    meta = surfaces["gm"]["meta"]
    assert meta["simplified"] is True
    assert meta["cell_mm"] > 0
    assert 0.0 < meta["max_deviation_mm"] < 10.0


# -- orientation and framing, on real anatomy --------------------------------


def _enclosed_volume(positions, indices, ref=(0.0, 0.0, 0.0)) -> float:
    """``sum (a-r).((b-r) x (c-r)) / 6`` -- the tetrahedron form about *ref*.

    A second expression for what :func:`tit.scene.build.signed_volume`
    computes, written here so the assertion is not the implementation checking
    itself: three shifted corners and one triple product, rather than one
    shifted corner and a cross product of edges.

    Both are exactly the enclosed volume, and exactly independent of *ref*,
    for a **closed** surface. Neither is for an open one, and these are open:
    the head mesh is cut off below the neck, and grid clustering leaves the
    simplified ``gm`` with boundary and non-manifold edges. That is what
    :func:`_reference_spread` measures, and it is what the agreement between
    the two expressions is then judged against -- rather than a tolerance
    picked to make the numbers fit.
    """
    v = np.asarray(positions, dtype=np.float64) - np.asarray(ref, dtype=np.float64)
    t = np.asarray(indices, dtype=np.int64).reshape(-1, 3)
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _reference_spread(positions, indices) -> float:
    """How much this surface's "enclosed volume" depends on the reference point.

    Zero for a closed surface. For an open one it is the size of the question
    the holes leave open, as a fraction of the volume -- and therefore the
    only honest tolerance for comparing two expressions that place their
    reference points differently.
    """
    v = np.asarray(positions, dtype=np.float64)
    refs = [(0.0, 0.0, 0.0), tuple(v.mean(axis=0)), tuple(v.min(axis=0)), tuple(v.max(axis=0))]
    values = [_enclosed_volume(positions, indices, r) for r in refs]
    return (max(values) - min(values)) / abs(np.mean(values))


def _boundary_edges(indices) -> int:
    """Undirected edges used by exactly one triangle -- the surface's holes."""
    t = np.asarray(indices, dtype=np.int64).reshape(-1, 3)
    edges = np.sort(np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int((counts == 1).sum())


def test_both_served_surfaces_are_wound_outward(surfaces: dict) -> None:
    """The defect fixed on 2026-09-04, on the mesh that produced it.

    Measured on ``sub-ernie`` before the fix, on the bytes the container
    served: ``skin`` enclosed **+4 841 347 mm3** and ``gm`` **-1 316 329** --
    every grey-matter triangle wound inward. The renderer orders two
    translucent shells by culling ``gl.FRONT`` first (decision B5), so an
    inverted ``gm`` composited its near wall under its far one.

    The signed volume is the criterion because it is independent of the
    renderer: it asks what the surface encloses, not what a rasteriser makes
    of it. The bands are wide on purpose -- a real head's brain is 1.0-1.8 L
    and its head-and-neck 3-8 L -- because what is being pinned is the *sign*,
    and a magnitude far outside the band would mean the surface is not closed
    enough for the question to have an answer.
    """
    volumes = {}
    for part, entry in surfaces.items():
        payload = entry["payload"]
        volume = _enclosed_volume(payload.positions, payload.indices)
        volumes[part] = volume
        sidecar = float(entry["meta"]["signed_volume_mm3"])
        spread = _reference_spread(payload.positions, payload.indices)
        gap = abs(sidecar - volume) / abs(volume)
        print(
            f"[{part}] encloses {volume:,.1f} mm3; sidecar says {sidecar:,.1f} "
            f"({gap * 100:.2f} % apart, against a {spread * 100:.2f} % "
            f"reference spread over {_boundary_edges(payload.indices)} boundary "
            f"edges); winding_flipped={entry['meta']['winding_flipped']}"
        )
        assert volume > 0, f"{part} is wound inward ({volume:,.1f} mm3)"
        assert sidecar > 0, f"{part}'s sidecar reports an inward winding"
        # The two expressions may differ by no more than the holes leave open.
        assert gap <= spread + 1e-6, (
            f"{part}: the two volume expressions differ by {gap * 100:.2f} %, "
            f"more than the {spread * 100:.2f} % its open boundary can explain"
        )
    assert (
        surfaces["gm"]["meta"]["winding_flipped"] is True
    ), "the head mesh's gm tag came out outward -- the convention this fix compensates for changed"
    assert surfaces["skin"]["meta"]["winding_flipped"] is False
    assert 0.5e6 < volumes["gm"] < 2.5e6, "gm does not enclose a brain-sized volume"
    assert 2.0e6 < volumes["skin"] < 1.0e7, "skin does not enclose a head-sized volume"
    assert volumes["gm"] < volumes["skin"], "the brain is inside the head"


def test_the_framing_box_drops_the_neck_and_keeps_the_head(surfaces: dict) -> None:
    """``focus_bbox`` is the framing hint decision S7's pane needs.

    ``sub-ernie``'s skin runs to ``z = -128.9 mm`` (neck and shoulders) while
    its grey matter starts at ``-50.7``, so a pane framing ``bbox`` spends
    about a fifth of its height on neck.
    """
    gm = surfaces["gm"]["meta"]
    skin = surfaces["skin"]["meta"]
    floor = gm["bbox"][2]

    assert gm["focus_bbox"] == gm["bbox"], "grey matter has nothing below its own floor"
    assert skin["bbox"][2] < floor, "this subject's skin does not extend below the brain"
    assert skin["focus_bbox"][2] >= floor
    # Only the floor moves: the head is not cropped at the sides or the vertex.
    assert skin["focus_bbox"][3:] == skin["bbox"][3:]
    assert skin["focus_bbox"][:2] == pytest.approx(skin["bbox"][:2], abs=25.0)

    full = skin["bbox"][5] - skin["bbox"][2]
    focused = skin["focus_bbox"][5] - skin["focus_bbox"][2]
    print(
        f"[skin] z {skin['bbox'][2]} -> {skin['bbox'][5]} ({full:.1f} mm) becomes "
        f"{skin['focus_bbox'][2]} -> {skin['focus_bbox'][5]} ({focused:.1f} mm): "
        f"{(1 - focused / full) * 100:.1f} % of the framed height was neck"
    )
    assert focused < full


def test_the_payloads_decode_to_a_drawable_mesh(surfaces: dict) -> None:
    for part, entry in surfaces.items():
        payload = entry["payload"]
        assert payload.vertex_count == entry["meta"]["vertices"], part
        assert payload.triangle_count == entry["meta"]["triangles"], part
        assert payload.indices.max() < payload.vertex_count, part
        assert np.isfinite(payload.positions).all(), part
        assert payload.labels is None, part


# ── the alignment proof ──────────────────────────────────────────────────────


def _annot_region_boxes(pm, subject: str, atlas: str) -> dict[tuple[str, int], dict]:
    """``(hemi, annot row) -> {bbox, n}`` read independently with nibabel.

    This is the second reader: it never touches the builder's KD-tree, its
    clustering, or the cached payload -- only the ``.annot`` file and the
    central surface it was made for.
    """
    import nibabel as nib
    import nibabel.freesurfer.io as fsio

    from tit.scene import build

    annots = build.annot_paths(pm, subject, atlas)
    centrals = build.central_surface_paths(pm, subject)
    boxes: dict[tuple[str, int], dict] = {}
    for hemi, annot_path in annots.items():
        rows, _ctab, _names = fsio.read_annot(annot_path)
        coords = np.asarray(nib.load(centrals[hemi]).darrays[0].data, dtype=np.float64)
        rows = np.asarray(rows)
        for row in np.unique(rows):
            if row < 0:
                continue
            members = coords[rows == row]
            if len(members) == 0:
                continue
            boxes[(hemi, int(row))] = {
                "lo": members.min(axis=0),
                "hi": members.max(axis=0),
                "n": len(members),
            }
    return boxes


def test_the_labels_payload_is_aligned_to_the_served_gm_surface(
    surfaces: dict, labels: dict, scene_format: str
) -> None:
    """One uint16 per served vertex, in the served order, same positions."""
    gm = surfaces["gm"]["payload"]
    payload = labels["payload"]
    assert payload.labels is not None
    assert payload.vertex_count == gm.vertex_count
    if scene_format == "gii":
        assert payload.triangle_count == gm.triangle_count
        np.testing.assert_array_equal(payload.indices, gm.indices)
    else:
        assert payload.triangle_count == 0
    np.testing.assert_array_equal(payload.positions, gm.positions)
    assert labels["meta"]["aligned_to"] == "gm"


def test_the_gifti_label_table_is_the_atlas_and_starts_with_no_region(
    labels: dict, scene_format: str
) -> None:
    """The `<LabelTable>` trap, on real data (decision E7).

    The engine remaps a `NIFTI_INTENT_LABEL` array to a **dense index** -- the
    row's *position* in the table -- and maps a value the table does not name
    to dense **0**. So the row at position 0 has to be the "no region" one: put
    a real region there and every unlabelled vertex is painted that region's
    colour, which is a whole cortex in one colour and looks entirely plausible.

    Read back through nibabel, which is not the writer.
    """
    if scene_format != "gii":
        pytest.skip("the label table only exists in the GIfTI serialisation")
    table = labels["payload"].label_table
    assert table is not None, "the GIfTI labels payload carried no <LabelTable>"
    keys = list(table)
    assert keys[0] == 0 and table[0] == "unlabelled", (
        f"the first row of the table is {keys[0]}/{table.get(keys[0])!r}, "
        "so an unlabelled vertex would take that region's colour"
    )
    named = {row["label"]: row["name"] for row in labels["meta"]["legend"]}
    assert {k: v for k, v in table.items() if k != 0} == named
    values = np.asarray(labels["payload"].labels)
    unknown = sorted(set(np.unique(values).tolist()) - set(table))
    assert unknown == [], f"labels {unknown} appear in the payload but not in the table"
    print(
        f"[{scene_format}] label table: {len(table)} rows, "
        f"{len(named)} regions + 'unlabelled'"
    )


def test_every_region_lands_where_the_annot_says_it_is(
    pm, subject: str, atlas: str, surfaces: dict, labels: dict
) -> None:
    """The whole point of the lane: a pick must highlight the right region.

    For each region with enough vertices, the centroid of the GM vertices
    carrying its wire label must fall inside the region's own bounding box as
    read from the ``.annot``. A one-region shift, a hemisphere swap, or a
    vertex-order mismatch moves that centroid centimetres outside.
    """
    positions = surfaces["gm"]["payload"].positions.astype(np.float64)
    values = np.asarray(labels["payload"].labels)
    boxes = _annot_region_boxes(pm, subject, atlas)

    checked = 0
    failures: list[str] = []
    for entry in labels["meta"]["legend"]:
        members = positions[values == entry["label"]]
        if len(members) < MIN_REGION_VERTICES:
            continue
        box = boxes.get((entry["hemi"], entry["id"]))
        if box is None:
            continue
        checked += 1
        centroid = members.mean(axis=0)
        inside = np.all(centroid >= box["lo"] - BBOX_MARGIN_MM) and np.all(
            centroid <= box["hi"] + BBOX_MARGIN_MM
        )
        if not inside:
            failures.append(
                f"{entry['hemi']}.{entry['name']}: centroid "
                f"{np.round(centroid, 1).tolist()} outside "
                f"{np.round(box['lo'], 1).tolist()}..{np.round(box['hi'], 1).tolist()}"
            )

    print(f"[{subject}] {atlas}: {checked} regions checked, {len(failures)} outside")
    assert checked >= 20, f"only {checked} regions had enough vertices to check"
    assert failures == []


def test_the_bounding_box_check_can_actually_fail(
    pm, subject: str, atlas: str, surfaces: dict, labels: dict
) -> None:
    """The negative control: pairing a region with its *mirror* must fail.

    A bounding-box assertion passes trivially if the boxes are large. Feeding
    each left-hemisphere region's centroid to the same region's right-hemisphere
    box must reject nearly all of them -- otherwise the test above proves
    nothing.
    """
    positions = surfaces["gm"]["payload"].positions.astype(np.float64)
    values = np.asarray(labels["payload"].labels)
    boxes = _annot_region_boxes(pm, subject, atlas)
    by_name = {
        (entry["hemi"], entry["name"]): entry for entry in labels["meta"]["legend"]
    }

    compared = 0
    wrongly_accepted = 0
    for (hemi, name), entry in by_name.items():
        if hemi != "lh":
            continue
        mirror = by_name.get(("rh", name))
        if mirror is None:
            continue
        box = boxes.get(("rh", mirror["id"]))
        members = positions[values == entry["label"]]
        if box is None or len(members) < MIN_REGION_VERTICES:
            continue
        compared += 1
        centroid = members.mean(axis=0)
        if np.all(centroid >= box["lo"] - BBOX_MARGIN_MM) and np.all(
            centroid <= box["hi"] + BBOX_MARGIN_MM
        ):
            wrongly_accepted += 1

    print(
        f"[{subject}] mirror control: {compared} lh regions tested against their "
        f"rh boxes, {wrongly_accepted} would have passed"
    )
    assert compared >= 20
    assert wrongly_accepted <= compared * 0.1


def test_unlabelled_vertices_are_the_structures_no_cortical_atlas_covers(
    surfaces: dict, labels: dict
) -> None:
    """Cerebellum and brainstem come back 0, and they are *below* the cortex.

    Measured on ``sub-ernie``: 7.35 % of GM vertices are >5 mm from any central
    surface vertex, and the GM tag reaches 22 mm lower than the central
    surfaces do. If unlabelled vertices were scattered through the cortex
    instead, the radius rule would be broken rather than doing its job.
    """
    positions = surfaces["gm"]["payload"].positions.astype(np.float64)
    values = np.asarray(labels["payload"].labels)
    unlabelled = positions[values == 0]
    labelled = positions[values != 0]

    fraction = len(unlabelled) / len(positions)
    print(
        f"unlabelled {fraction * 100:.1f} % of vertices, mean z "
        f"{unlabelled[:, 2].mean():.1f} vs labelled {labelled[:, 2].mean():.1f}"
    )
    assert 0.0 < fraction < 0.30
    assert unlabelled[:, 2].mean() < labelled[:, 2].mean()


# ── electrodes are in the same space and units as the surfaces ───────────────


def test_every_electrode_sits_on_the_skin(pm, subject: str, surfaces: dict) -> None:
    """The one test that catches a space or a units mistake.

    Nearest-vertex distance from each electrode to the *served* skin payload,
    for every net the subject has. Anything but the head mesh's own world
    millimetres puts these in the hundreds or thousands.
    """
    from scipy.spatial import cKDTree

    from tit.scene import build

    skin = surfaces["skin"]["payload"].positions.astype(np.float64)
    tree = cKDTree(skin)

    nets = pm.list_eeg_caps(subject)
    assert nets, f"{subject} has no EEG nets to check"
    worst = 0.0
    for net in nets:
        parsed = build.read_net(pm, subject, net)
        points = np.asarray([e["world"] for e in parsed["electrodes"]], dtype=np.float64)
        if len(points) == 0:
            continue
        distance, _index = tree.query(points)
        print(
            f"[{subject}] {net}: {len(points)} electrodes, skin distance "
            f"mean {distance.mean():.2f} max {distance.max():.2f} mm"
        )
        worst = max(worst, float(distance.max()))
        assert distance.max() <= ELECTRODE_TO_SKIN_MM, net
    assert worst > 0.0, "has electrodes to check"


def test_the_reference_and_fiducials_are_in_the_same_space(
    pm, subject: str, surfaces: dict
) -> None:
    """Fiducials are landmarks *on* the head too -- a cheap second witness."""
    from scipy.spatial import cKDTree

    from tit.scene import build

    tree = cKDTree(surfaces["skin"]["payload"].positions.astype(np.float64))
    fiducials = Path(pm.eeg_positions(subject)) / "Fiducials.csv"
    if not fiducials.is_file():
        pytest.skip("skipping: this subject has no Fiducials.csv")
    parsed = build.parse_electrode_csv(fiducials.read_text())
    points = np.asarray([f["world"] for f in parsed["fiducials"]], dtype=np.float64)
    assert len(points) >= 3
    distance, _ = tree.query(points)
    print(f"[{subject}] fiducials: max skin distance {distance.max():.2f} mm")
    assert distance.max() <= ELECTRODE_TO_SKIN_MM


# ── the volume legend ────────────────────────────────────────────────────────


def test_the_volume_legend_names_the_tissue_labels(pm, subject: str) -> None:
    from tit.scene import build

    legend = build.volume_legend(pm, subject)["entries"]
    assert len(legend) > 10
    by_id = {entry["id"]: entry for entry in legend}
    # Every SimNIBS charm labelling carries these two.
    assert 2 in by_id and "White-Matter" in by_id[2]["name"]
    assert all(entry["color"] is None or entry["color"].startswith("#") for entry in legend)


def test_every_served_gm_vertex_is_an_untouched_mesh_vertex(
    pm, subject: str, surfaces: dict
) -> None:
    """The property that lets labels and electrodes stay registered.

    Grid clustering keeps a *representative member* of each cell rather than
    the cell's centroid, so the served surface is a subset of the mesh's own
    vertices with bit-identical coordinates. This re-reads the head mesh (the
    writer never gets to say what it wrote) and checks two things: exact set
    membership, and the one-sided Hausdorff distance from the full mesh
    surface to the served one -- the honest "how much did simplification move
    the surface" number, printed for the lane notes.
    """
    from scipy.spatial import cKDTree
    from simnibs.mesh_tools import mesh_io

    from tit.scene import build

    mesh = mesh_io.read_msh(str(build.head_mesh_path(pm, subject)))
    original = np.asarray(
        mesh.crop_mesh(tags=[build.PART_TAGS["gm"]]).nodes.node_coord, dtype=np.float32
    )
    served = surfaces["gm"]["payload"].positions

    # Exact membership: every served coordinate triple is one the mesh has.
    original_rows = {row.tobytes() for row in np.ascontiguousarray(original)}
    served_rows = {row.tobytes() for row in np.ascontiguousarray(served)}
    assert served_rows <= original_rows, "a served vertex is not a mesh vertex"

    distance, _ = cKDTree(served.astype(np.float64)).query(original.astype(np.float64))
    meta = surfaces["gm"]["meta"]
    print(
        f"[{subject}] gm simplification at cell {meta['cell_mm']} mm: "
        f"{len(original)} -> {len(served)} vertices; distance from an original "
        f"vertex to the nearest served one: mean {distance.mean():.3f} "
        f"p95 {np.percentile(distance, 95):.3f} p99 {np.percentile(distance, 99):.3f} "
        f"max {distance.max():.3f} mm (reported max_deviation "
        f"{meta['max_deviation_mm']} mm)"
    )
    # The reported number is the one-sided Hausdorff distance; ``cKDTree`` here
    # is the independent reader that has to agree with it. float32 payload
    # positions against float64 mesh coordinates is the whole tolerance.
    assert meta["max_deviation_mm"] == pytest.approx(float(distance.max()), abs=1e-3)
