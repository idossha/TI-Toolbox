"""Building the four scene payloads from a subject's real files (plan §2).

What this module extracts, and from where:

===============  ==========================================================
part / payload   source
===============  ==========================================================
``skin``         ``m2m_<id>/<id>.msh``, ``crop_mesh(tags=[1005])``
``gm``           ``m2m_<id>/<id>.msh``, ``crop_mesh(tags=[1002])``
electrodes       ``m2m_<id>/eeg_positions/<net>.csv`` (``Electrode,x,y,z,name``)
region labels    ``m2m_<id>/segmentation/{lh,rh}.<id>_<atlas>.annot``
                 + ``m2m_<id>/surfaces/{lh,rh}.central.gii``
volume legend    ``m2m_<id>/segmentation/labeling_LUT.txt``
===============  ==========================================================

**The alignment problem, and how it is solved.** A ``.annot`` file has one
label per vertex of the *central* surface -- 245 762 per hemisphere on
``sub-ernie``. The head mesh's grey-matter surface is a different, coarser
triangulation of the same anatomy: 168 952 vertices, and 76 k after §S3
simplification. The label array therefore cannot be handed over as-is; it has
neither the right length nor the right order, and a renderer that assumed it
did would highlight a region several centimetres from the one the user
clicked. :func:`build_labels` instead

1. **decodes the ``gm`` payload the surface route actually serves** (not a
   re-derived vertex list -- a re-derivation is exactly where the two orders
   could silently diverge),
2. finds each of those vertices' nearest central-surface vertex, and
3. copies that vertex's region across only when it is within
   :data:`LABEL_RADIUS_MM`.

Step 3 matters because the head mesh's GM tag covers cerebellum and brainstem
as well as cortex, and the cortical atlases cover none of it: measured on
``sub-ernie``, 7.35 % of GM vertices are more than 5 mm from any central
surface vertex (max 45.7 mm). Those come back label ``0`` = "no region"
rather than borrowing whatever cortical label happens to be least far away.

Every heavy import (``simnibs``, ``nibabel``, ``scipy``) is function-local:
all three are ``MagicMock``-ed in ``tests/conftest.py``, so a module-level
import would make ``tit.scene`` unimportable in the host suite, and the routes
that only need ``tvsc``/``simplify`` would pay for a SimNIBS import they never
use.
"""

from __future__ import annotations

import csv
import io
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from tit.paths import PathManager
from tit.scene import cache, gifti, tvsc
from tit.scene.simplify import simplify_to_budget

__all__ = [
    "PART_TAGS",
    "MAX_TRIANGLES",
    "MAX_BYTES",
    "LABEL_RADIUS_MM",
    "BUILDER_VERSION",
    "FOCUS_FLOOR_PART",
    "SceneUnavailable",
    "head_mesh_path",
    "surface_sources",
    "surface_fingerprint",
    "labels_fingerprint",
    "label_sources",
    "signed_volume",
    "orient_outward",
    "focus_bbox",
    "build_surfaces",
    "build_labels",
    "read_net",
    "volume_legend",
    "atlas_region_count",
    "parse_electrode_csv",
    "parse_lut_text",
    "labels_from_nearest",
]

#: SimNIBS surface element tags. 1000 + tissue index; 5 = skin, 2 = grey
#: matter (``simnibs.mesh_tools.mesh_io.ElementTags``).
PART_TAGS: dict[str, int] = {"skin": 1005, "gm": 1002}

#: Decision S3's budget, per surface.
MAX_TRIANGLES = 150_000
MAX_BYTES = 3 * 1024 * 1024

#: A GM vertex further than this from every central-surface vertex is left
#: unlabelled. Chosen from the measured bimodal distribution on ``sub-ernie``
#: (91 % of vertices under 2 mm; the next mode -- cerebellum and brainstem,
#: which no cortical atlas covers -- starts past 5 mm), so anything in 2-5 mm
#: gives the same answer to within 1.8 % of vertices. Recorded in every labels
#: sidecar as ``radius_mm`` alongside the resulting ``labelled_fraction``.
LABEL_RADIUS_MM = 3.0

#: What ``uint16`` 0 means on the wire: this vertex belongs to no region.
NO_REGION = 0

#: Mixed into every cache fingerprint this module computes
#: (:func:`tit.scene.cache.fingerprint`'s ``version``). Bump it whenever this
#: module changes the *bytes* -- or the sidecar fields -- it emits for a
#: payload. The fingerprint's other input is the size and mtime of the source
#: files, which cannot see a change in the code that read them: without this
#: salt a cache entry an older builder wrote is served for ever from an
#: unchanged mesh.
#:
#: ``"1"``
#:     first release (lane SCA).
#: ``"2"``
#:     surfaces are oriented outward (:func:`orient_outward`) and every part's
#:     sidecar carries ``focus_bbox`` (:func:`focus_bbox`). Measured on
#:     ``sub-ernie`` before this: the served ``gm`` surface enclosed
#:     -1 316 329 mm3 -- a *negative* signed volume, i.e. every triangle wound
#:     inward -- against skin's +4 841 347 mm3.
#: ``"3"``
#:     the GIfTI labels payload carries the grey-matter triangles as well as
#:     the aligned per-vertex labels, so Tetravox can render and pick cortical
#:     regions directly instead of relying on the retired desktop renderer to
#:     combine a labels-only payload with a separately fetched surface.
BUILDER_VERSION = "3"

#: Whose lowest vertex marks the bottom of "the head" for :func:`focus_bbox`.
#: The grey matter's floor is the bottom of the cerebellum and brainstem;
#: below it the skin surface is neck and shoulders, which no pane of this kind
#: is ever framing for.
FOCUS_FLOOR_PART = "gm"


class SceneUnavailable(Exception):
    """A scene payload cannot be built, with a reason a user can act on.

    Raised (never a bare ``FileNotFoundError``) so the route layer can turn it
    into a 404 whose ``detail`` names the missing file -- a subject with no
    head model yet is the normal case, not a server error (decision S6: the
    page still works without the pane).
    """


# ── source files ─────────────────────────────────────────────────────────────


def head_mesh_path(pm: PathManager, sid: str) -> Path:
    """``m2m_<id>/<id>.msh``, or raise :class:`SceneUnavailable`."""
    path = Path(pm.m2m(sid)) / f"{sid}.msh"
    if not path.is_file():
        raise SceneUnavailable(
            f"No head model for {sid}: {path} does not exist (run charm first)"
        )
    return path


def surface_sources(pm: PathManager, sid: str) -> list[str]:
    """Files whose size+mtime fingerprint the ``skin``/``gm`` payloads."""
    return [str(Path(pm.m2m(sid)) / f"{sid}.msh")]


def surface_fingerprint(pm: PathManager, sid: str) -> str:
    """The cache fingerprint of this subject's surface payloads.

    One definition, called by the builder *and* by the route that looks the
    result up: computing it in two places is how a builder-version bump would
    reach one of them and not the other, and the symptom would be a route
    that rebuilds on every request.
    """
    return cache.fingerprint(surface_sources(pm, sid), BUILDER_VERSION)


def annot_paths(pm: PathManager, sid: str, atlas_id: str) -> dict[str, str]:
    """``{"lh": path, "rh": path}`` for one cortical atlas; only what exists.

    Discovery goes through :class:`tit.atlas.mesh.MeshAtlasManager` so the
    scene sees exactly the atlases ``GET /api/catalog/atlases`` lists -- one
    definition of "which atlases does this subject have".

    *atlas_id* is checked twice before it reaches the filesystem, and both
    checks matter: ``MeshAtlasManager.find_atlas_file`` interpolates it into a
    ``glob`` pattern, and a glob pattern *does* walk ``..`` segments, so an id
    of ``../../../../etc/x`` would otherwise let a caller aim ``read_annot``
    at any ``lh.*.annot`` on the machine. :func:`tit.catalog.is_safe_name`
    rules out every separator and traversal segment; membership in
    ``list_atlases()`` then rules out anything this subject does not have.
    Returns ``{}`` (which every caller turns into a readable 404) rather than
    raising, because "this subject has no such atlas" is a normal answer.
    """
    from tit.atlas import MeshAtlasManager
    from tit.catalog import is_safe_name

    if not is_safe_name(atlas_id):
        return {}
    manager = MeshAtlasManager(os.path.join(pm.m2m(sid), "segmentation"))
    if atlas_id not in manager.list_atlases():
        return {}
    found: dict[str, str] = {}
    for hemi in ("lh", "rh"):
        path = manager.find_atlas_file(atlas_id, hemi)
        if path and os.path.isfile(path):
            found[hemi] = path
    return found


def central_surface_paths(pm: PathManager, sid: str) -> dict[str, str]:
    """``{"lh": path, "rh": path}`` for the central surfaces that exist."""
    root = Path(pm.m2m(sid)) / "surfaces"
    return {
        hemi: str(root / f"{hemi}.central.gii")
        for hemi in ("lh", "rh")
        if (root / f"{hemi}.central.gii").is_file()
    }


def label_sources(pm: PathManager, sid: str, atlas_id: str) -> list[str]:
    """Every file a labels payload depends on, for its fingerprint.

    The head mesh is included because the labels are aligned to the ``gm``
    surface built from it: a new ``charm`` run changes the vertex order, and a
    labels file that survived it would be aligned to nothing.
    """
    sources = list(surface_sources(pm, sid))
    sources += [annot_paths(pm, sid, atlas_id).get(h, f"{h}.missing.annot") for h in ("lh", "rh")]
    sources += [central_surface_paths(pm, sid).get(h, f"{h}.missing.gii") for h in ("lh", "rh")]
    return sources


def labels_fingerprint(pm: PathManager, sid: str, atlas_id: str) -> str:
    """The cache fingerprint of one atlas' labels payload, salted like the rest.

    The labels are positions copied out of the ``gm`` payload, so a builder
    version that changes ``gm`` has to invalidate these too -- otherwise the
    sidecar's ``aligned_to_fingerprint`` names a surface entry that no longer
    exists.
    """
    return cache.fingerprint(label_sources(pm, sid, atlas_id), BUILDER_VERSION)


# ── pure parsers (no simnibs / nibabel / scipy) ──────────────────────────────


def parse_electrode_csv(text: str) -> dict[str, list[dict[str, Any]]]:
    """Split an ``eeg_positions/*.csv`` into electrodes, reference, fiducials.

    Rows are ``<type>,<x>,<y>,<z>,<name>`` with ``<type>`` one of
    ``Electrode`` / ``ReferenceElectrode`` / ``Fiducial`` (measured on
    ``sub-ernie``'s ``EEG10-10_UI_Jurak_2007.csv``: 75 / 1 / 4). Coordinates
    are the head mesh's own world millimetres -- the same space the surfaces
    are served in, which is what makes an electrode marker land *on* the skin
    rather than floating (pinned by
    ``tests/test_scene_realdata.py::test_every_electrode_sits_on_the_skin``).

    A malformed row is skipped rather than failing the whole net: these files
    are written by charm and occasionally carry a trailing blank line.
    """
    out: dict[str, list[dict[str, Any]]] = {
        "electrodes": [],
        "reference": [],
        "fiducials": [],
    }
    bucket = {
        "electrode": "electrodes",
        "referenceelectrode": "reference",
        "fiducial": "fiducials",
    }
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        key = bucket.get(row[0].strip().lower())
        if key is None:
            continue
        try:
            world = [float(row[1]), float(row[2]), float(row[3])]
        except ValueError:
            continue
        if not all(np.isfinite(world)):
            continue
        out[key].append({"name": row[4].strip(), "world": world})
    return out


def _parse_lut_line(line: str) -> tuple[str, str, tuple[str, ...] | None] | None:
    """``(id, name, rgb)`` from one FreeSurfer-style colour-table line.

    Column-order agnostic: the first token is the integer id, every remaining
    non-integer token is part of the name and the first three remaining
    integers are R, G, B. Real tables in the wild put the alpha column in
    different places and pad names with tabs, which is why the split is by
    token class rather than by position.
    """
    parts = line.split()
    if len(parts) < 2:
        return None
    label_id = parts[0]
    if not label_id.lstrip("-").isdigit():
        return None
    rest = parts[1:]
    name_tokens = [p for p in rest if not p.lstrip("-").isdigit()]
    int_tokens = [p for p in rest if p.lstrip("-").isdigit()]
    if not name_tokens:
        return None
    rgb = tuple(int_tokens[:3]) if len(int_tokens) >= 3 else None
    return label_id, " ".join(name_tokens), rgb


def parse_lut_text(text: str) -> list[dict[str, Any]]:
    """``[{id, name, color}]`` from a FreeSurfer-style colour table.

    Rule-for-rule the same column-order-agnostic parse as
    :func:`tit.opt.roi_spec._parse_lut_line`, which the optimizer's ROI picker
    uses -- ``tests/test_scene_build.py::test_the_lut_parse_matches_the_roi_pickers``
    drives both over the same lines so the scene legend and the ROI dropdown
    cannot start disagreeing about what a label is called.

    **Why it is copied rather than imported.** ``tit.opt.roi_spec`` pulls in
    ``tit.opt.__init__``, which imports the ex/flex engines and through them
    ``simnibs``: measured 3197 ms in the dev container, against 45 ms for
    ``tit.catalog``. Paying three seconds on the first legend request -- more
    than the whole 2.5 s warm-cache budget of decision S8 -- to reuse twelve
    lines is the wrong trade, and a scene service has no business importing an
    optimizer.

    ``color`` is ``"#rrggbb"``, or ``None`` when the table carries no RGB
    columns.
    """
    entries: list[dict[str, Any]] = []
    seen: set[int] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parsed = _parse_lut_line(line)
        if parsed is None:
            continue
        label_id, name, rgb = parsed
        value = int(label_id)
        if value in seen:
            continue
        seen.add(value)
        color = None
        if rgb is not None:
            try:
                color = "#%02x%02x%02x" % tuple(int(c) & 0xFF for c in rgb)
            except (TypeError, ValueError):
                color = None
        entries.append({"id": value, "name": name, "color": color})
    return entries


def labels_from_nearest(
    nn_index: np.ndarray,
    nn_distance: np.ndarray,
    reference_label: np.ndarray,
    radius: float,
) -> np.ndarray:
    """Per-vertex ``uint16`` wire labels from a nearest-neighbour lookup.

    Pure array arithmetic, deliberately separated from the ``scipy`` KD-tree
    that produces ``nn_index``/``nn_distance``: this is the step where an
    off-by-one or a forgotten radius check turns into "clicking a region
    highlights the wrong one", and it is testable on the host where ``scipy``
    is mocked.
    """
    labels = np.asarray(reference_label, dtype=np.uint16)[
        np.asarray(nn_index, dtype=np.int64)
    ]
    labels = np.where(
        np.asarray(nn_distance, dtype=np.float64) <= radius, labels, NO_REGION
    )
    return labels.astype(np.uint16)


# ── builders ─────────────────────────────────────────────────────────────────


# -- orientation --------------------------------------------------------------


def signed_volume(vertices: np.ndarray, triangles: np.ndarray) -> float:
    """The volume a closed triangle surface encloses (mm3), signed by winding.

    The divergence theorem on the field ``x``: ``V = (1/3) * closed-integral
    of x . n dA``, which for a triangle soup is
    ``sum_t (a - p) . ((b - a) x (c - a)) / 6``. **Positive** when the
    right-hand (counter-clockwise) normals point *out* of the enclosed volume,
    negative when they point in -- and that sign is the criterion
    :func:`orient_outward` acts on. It is independent of the reference point
    ``p`` for a closed surface (the area-weighted normals of a closed surface
    sum to zero), so ``p`` is taken to be the vertex centroid, which is what
    keeps the number meaningful when the surface has a small hole: the head
    mesh's skin is cut off at the neck, and ernie's served ``gm`` has 3 370
    boundary edges after simplification.

    This is deliberately *not* the criterion the renderer or the pick uses.
    It is an independent one: a rasteriser asks "is the nearest fragment
    front-facing", this asks "does the surface enclose a positive volume", and
    the two agree only if the winding really is right.
    """
    v = np.asarray(vertices, dtype=np.float64)
    t = np.asarray(triangles, dtype=np.int64)
    if t.size == 0 or v.size == 0:
        return 0.0
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    return float(
        np.einsum("ij,ij->i", a - v.mean(axis=0), np.cross(b - a, c - a)).sum() / 6.0
    )


def orient_outward(
    vertices: np.ndarray, triangles: np.ndarray
) -> tuple[np.ndarray, bool]:
    """``(triangles wound outward, whether they had to be flipped)``.

    Why this exists, measured on ``sub-ernie`` on 2026-09-04 (lane FIX-A,
    ``dev/notes/v3-scene-ia/fix-a-notes.md`` §5.1, reproduced by CL1): the head
    mesh's tag-1005 (skin) surface elements come out of ``crop_mesh`` wound
    outward (signed volume ``+4 841 347 mm3``, 99.5 % of triangle normals
    pointing away from the centroid) and its tag-1002 (grey matter) elements
    come out wound **inward** (``-1 309 124 mm3``, 32.6 %). Nothing in the head
    mesh promises a consistent convention between tissue boundaries, so the
    builder establishes one rather than each consumer guessing.

    What the inward winding broke: any translucent shell renderer or normal
    consumer that assumes outward faces will composite or shade an inverted
    ``gm`` surface inside-out. The scene service establishes the convention at
    the source instead of making each downstream renderer guess.

    A flip swaps two of the three indices, so the vertex positions -- and
    therefore every per-vertex label, electrode alignment and cache-fingerprint
    property -- are untouched.
    """
    t = np.asarray(triangles, dtype=np.int64)
    if signed_volume(vertices, t) >= 0.0:
        return t, False
    return t[:, [0, 2, 1]], True


def focus_bbox(vertices: np.ndarray, floor_z: float) -> list[float]:
    """``[x0,y0,z0,x1,y1,z1]`` over the vertices at or above *floor_z*.

    The framing hint decision S7's pane needs, and the reason it is computed
    here rather than in the renderer: only the server has the anatomy. A head
    model's skin surface runs down the neck to the shoulders -- ``sub-ernie``'s
    reaches ``z = -128.9 mm`` while its grey matter starts at ``-50.7`` -- so a
    pane that frames the manifest's ``bbox`` spends about a fifth of its height
    on neck. *floor_z* is the lowest grey-matter vertex
    (:data:`FOCUS_FLOOR_PART`), i.e. the bottom of the cerebellum and
    brainstem, which is the lowest point of the head anyone picking electrodes
    or regions is looking at.

    Returns the part's **full** box when nothing is below the floor (the grey
    matter's own contribution is always its whole box), so a caller can union
    the parts' ``focus_bbox`` exactly the way it unions their ``bbox``.
    """
    v = np.asarray(vertices, dtype=np.float64)
    kept = v[v[:, 2] >= floor_z]
    if len(kept) == 0:  # pragma: no cover - a part entirely below the floor
        kept = v
    return [round(float(x), 3) for x in (*kept.min(axis=0), *kept.max(axis=0))]


def _read_surface(mesh, tag: int) -> tuple[np.ndarray, np.ndarray, bool]:
    """``(vertices, triangles, flipped)`` for one SimNIBS surface tag.

    The triangles come back wound outward whatever the mesh's own convention
    for that tag was; ``flipped`` says whether that took a flip, and is
    recorded in the payload's sidecar so a change of convention upstream is
    visible rather than silently absorbed.
    """
    cropped = mesh.crop_mesh(tags=[tag])
    vertices = np.asarray(cropped.nodes.node_coord, dtype=np.float64)
    element_nodes = np.asarray(cropped.elm.node_number_list)
    is_triangle = np.asarray(cropped.elm.elm_type) == 2
    triangles = element_nodes[is_triangle][:, :3].astype(np.int64) - 1  # 1-based
    triangles, flipped = orient_outward(vertices, triangles)
    return vertices, triangles, flipped


def build_surfaces(pm: PathManager, sid: str) -> dict[str, dict]:
    """Build, cache and describe both surface parts for *sid*.

    Both parts come out of **one** ``read_msh`` (measured 1.26 s for a 184 MB
    mesh, versus 0.03-0.10 s per crop): building them separately would double
    the only expensive step and the ~600 MB of RSS it needs.

    Returns ``{part: sidecar-dict}``; the bytes are in the cache.
    """
    from simnibs.mesh_tools import mesh_io

    mesh_path = head_mesh_path(pm, sid)
    fp = surface_fingerprint(pm, sid)
    started = time.perf_counter()
    mesh = mesh_io.read_msh(str(mesh_path))
    read_ms = (time.perf_counter() - started) * 1000.0

    # Both parts are extracted before either is simplified, because the focus
    # box of one is defined by the floor of the other (:func:`focus_bbox`) --
    # and because it lets the 184 MB mesh be released before the memory the
    # clustering needs is allocated.
    extracted: dict[str, tuple[np.ndarray, np.ndarray, bool, float]] = {}
    for part, tag in PART_TAGS.items():
        part_started = time.perf_counter()
        vertices, triangles, flipped = _read_surface(mesh, tag)
        if triangles.size == 0:
            raise SceneUnavailable(
                f"{mesh_path.name} has no tag-{tag} ({part}) surface elements"
            )
        extract_ms = (time.perf_counter() - part_started) * 1000.0
        extracted[part] = (vertices, triangles, flipped, extract_ms)
    del mesh

    floor_source = extracted.get(FOCUS_FLOOR_PART)
    floor_z = (
        float(floor_source[0][:, 2].min()) if floor_source is not None else -np.inf
    )

    metas: dict[str, dict] = {}
    for part, (vertices, triangles, flipped, extract_ms) in extracted.items():
        part_started = time.perf_counter()
        result = simplify_to_budget(vertices, triangles, MAX_TRIANGLES, MAX_BYTES)
        # One extraction, one simplification, two serialisations (decision E7).
        # `tvsc` is the frozen compatibility payload and `gii` is what the
        # Tetravox embed reads; both are the SAME vertices and triangles, which
        # keeps the compatibility path honest until it is dropped from
        # `cache.FORMATS`.
        blobs = {
            "tvsc": tvsc.encode(result.vertices, result.triangles),
            "gii": gifti.encode_surface(result.vertices, result.triangles),
        }
        blob = blobs["tvsc"]
        build_ms = read_ms + extract_ms + (time.perf_counter() - part_started) * 1000.0
        bbox = np.concatenate(
            [result.vertices.min(axis=0), result.vertices.max(axis=0)]
        )
        meta = {
            "part": part,
            "tag": PART_TAGS[part],
            "vertices": int(len(result.vertices)),
            "triangles": int(len(result.triangles)),
            "source_vertices": int(len(vertices)),
            "source_triangles": int(len(triangles)),
            "simplified": bool(result.simplified),
            "cell_mm": round(result.cell, 4),
            "simplify_rounds": int(result.rounds),
            "max_deviation_mm": round(
                float(result.max_deviation), 4
            ),
            "within_budget": bool(
                len(result.triangles) <= MAX_TRIANGLES and len(blob) <= MAX_BYTES
            ),
            # Per-serialisation payload size, so the manifest and a reader can
            # say what a `format=gii` request will actually cost without
            # stat-ing the cache.
            "format_bytes": {name: len(data) for name, data in blobs.items()},
            "bbox": [round(float(v), 3) for v in bbox],
            # The framing hint (S7): this part's box with the neck cut off at
            # the grey matter's floor. Unioned across parts by the manifest,
            # exactly the way `bbox` is.
            "focus_bbox": focus_bbox(result.vertices, floor_z),
            # Winding: `signed_volume` of what is actually published, so the
            # sidecar records the property rather than the intention.
            # `winding_flipped` says the mesh's own convention for this tag
            # was inward -- true of `gm`, false of `skin`, on every subject
            # measured.
            "winding_flipped": bool(flipped),
            "signed_volume_mm3": round(
                signed_volume(result.vertices, result.triangles), 1
            ),
            # Both parts come out of one read_msh, so both build_ms values
            # include the same mesh read; mesh_read_ms says how much of it
            # that was, which is what makes the two numbers decomposable.
            "mesh_read_ms": round(read_ms, 1),
            "build_ms": round(build_ms, 1),
        }
        metas[part] = _publish_formats(pm.project_dir, sid, part, fp, blobs, meta)
    return metas


#: The serialisation the byte routes serve when a caller names none, and the
#: one whose size the manifest's ``bytes`` reports. Publishing it **last** is
#: what keeps that number stable: the sidecar is shared between formats and
#: :func:`tit.scene.cache.publish` stamps it with the payload it just wrote, so
#: the last write wins. Moving this constant to ``"gii"`` is the whole of "the
#: manifest now describes the GIfTI payload".
DEFAULT_FORMAT = "tvsc"


def _publish_formats(
    project_dir, sid: str, key: str, fp: str, blobs: dict[str, bytes], meta: dict
) -> dict:
    """Publish every serialisation of one artifact; return the sidecar.

    :data:`DEFAULT_FORMAT` goes last so the shared sidecar's ``bytes`` is its
    size, not whichever format happened to be written second.
    """
    order = [name for name in blobs if name != DEFAULT_FORMAT] + [DEFAULT_FORMAT]
    published = None
    for name in order:
        published = cache.publish(
            project_dir, sid, key, fp, blobs[name], meta, ext=name
        )
    assert published is not None  # `order` always ends with DEFAULT_FORMAT
    return published.meta


def _load_reference_labels(
    pm: PathManager, sid: str, atlas_id: str
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    """Central-surface points, their wire labels, and the legend.

    ``legend`` entries carry the ``id``/``name``/``color`` the frozen contract
    names, plus ``hemi`` and the ``label`` value that actually appears in the
    ``uint16`` payload. ``id`` is the ``.annot`` row index within that
    hemisphere -- the same integer ``GET /api/catalog/atlases/regions`` and
    ``FlexConfig.AtlasROI.label`` use, so a pick maps straight onto a config.
    """
    import nibabel as nib
    import nibabel.freesurfer.io as fsio

    annots = annot_paths(pm, sid, atlas_id)
    centrals = central_surface_paths(pm, sid)
    if not annots:
        raise SceneUnavailable(
            f"{sid} has no {atlas_id} annotation in m2m_{sid}/segmentation/"
        )
    missing = sorted(set(annots) - set(centrals))
    if missing:
        raise SceneUnavailable(
            f"{sid} has a {atlas_id} annotation for {missing} but no matching "
            f"central surface in m2m_{sid}/surfaces/"
        )

    points: list[np.ndarray] = []
    wire: list[np.ndarray] = []
    legend: list[dict[str, Any]] = []
    next_label = 1
    for hemi in ("lh", "rh"):
        if hemi not in annots:
            continue
        annot_labels, ctab, names = fsio.read_annot(annots[hemi])
        gifti = nib.load(centrals[hemi])
        coords = _gifti_points(gifti)
        if len(coords) != len(annot_labels):
            raise SceneUnavailable(
                f"{sid} {hemi}.{atlas_id}: {len(annot_labels)} annotation labels "
                f"but {len(coords)} central-surface vertices -- the annotation "
                f"was not made for this surface"
            )
        # annot row index -> wire label, 0 for 'unknown' and for rows this
        # hemisphere never uses.
        row_to_wire = np.zeros(len(names) + 1, dtype=np.uint16)
        for row, raw_name in enumerate(names):
            name = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else str(raw_name)
            if name == "unknown":
                continue
            row_to_wire[row] = next_label
            rgba = ctab[row]
            legend.append(
                {
                    "label": next_label,
                    "id": int(row),
                    "hemi": hemi,
                    "name": name,
                    "color": "#%02x%02x%02x"
                    % (int(rgba[0]) & 0xFF, int(rgba[1]) & 0xFF, int(rgba[2]) & 0xFF),
                }
            )
            next_label += 1
        rows = np.asarray(annot_labels, dtype=np.int64)
        rows[rows < 0] = len(names)  # -1 = no ctab row -> the zero slot
        points.append(np.asarray(coords, dtype=np.float64))
        wire.append(row_to_wire[rows])
    return np.vstack(points), np.concatenate(wire), legend


def atlas_region_count(pm: PathManager, sid: str, atlas_id: str) -> int:
    """How many named regions one cortical atlas has, over both hemispheres.

    Read straight from the ``.annot`` colour tables rather than cached: 85 ms
    for all three of ``sub-ernie``'s atlases (measured 2026-09-04), which the
    manifest can afford, and a cached count would be one more thing that can
    go stale against the annotation files.
    """
    import nibabel.freesurfer.io as fsio

    total = 0
    for path in annot_paths(pm, sid, atlas_id).values():
        try:
            _labels, _ctab, names = fsio.read_annot(path)
        except (OSError, ValueError):  # pragma: no cover - unreadable annot
            continue
        total += sum(
            1
            for raw in names
            if (raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)) != "unknown"
        )
    return total


def _gifti_points(gifti) -> np.ndarray:
    """The POINTSET darray of a GIFTI surface (intent 1008), by intent code."""
    for darray in gifti.darrays:
        if int(getattr(darray, "intent", -1)) == 1008:  # NIFTI_INTENT_POINTSET
            return np.asarray(darray.data)
    return np.asarray(gifti.darrays[0].data)


def build_labels(pm: PathManager, sid: str, atlas_id: str) -> dict:
    """Build and cache the ``uint16`` labels payload aligned to part ``gm``.

    The gm vertices are read back out of the **cached ``gm`` payload**, so the
    labels are aligned to the exact bytes ``GET /api/scene/surface?part=gm``
    serves. Deriving the vertex order a second time from the mesh would be the
    one place the two could silently disagree.
    """
    from scipy.spatial import cKDTree

    surface_fp = surface_fingerprint(pm, sid)
    cached_gm = cache.find_cached(pm.project_dir, sid, "gm", surface_fp)
    if cached_gm is None:
        build_surfaces(pm, sid)
        cached_gm = cache.find_cached(pm.project_dir, sid, "gm", surface_fp)
    if cached_gm is None:  # pragma: no cover - publish() would have raised
        raise SceneUnavailable(f"could not build the gm surface for {sid}")

    started = time.perf_counter()
    gm_payload = tvsc.decode(cached_gm.path.read_bytes())
    gm_vertices = gm_payload.positions.astype(np.float64)
    gm_triangles = gm_payload.indices
    points, wire, legend = _load_reference_labels(pm, sid, atlas_id)
    distance, index = cKDTree(points).query(gm_vertices, workers=-1)
    labels = labels_from_nearest(index, distance, wire, LABEL_RADIUS_MM)
    # Same alignment, two serialisations. The `gii` payload carries the GM
    # triangles plus the labels as a `NIFTI_INTENT_LABEL` array **with the
    # atlas' own `<LabelTable>`**: without triangles the Tetravox embed has no
    # surface to render or pick, without the table it reads the array as a
    # continuous scalar, and the row for `NO_REGION` has to come first because
    # an unnamed value maps to the table's first row (`tit/scene/gifti.py`).
    blobs = {
        "tvsc": tvsc.encode(gm_vertices.astype(np.float32), None, labels),
        "gii": gifti.encode_surface(
            gm_vertices.astype(np.float32),
            gm_triangles,
            labels,
            gifti.label_table_from_legend(legend),
        ),
    }
    blob = blobs["tvsc"]
    build_ms = (time.perf_counter() - started) * 1000.0

    fp = labels_fingerprint(pm, sid, atlas_id)
    meta = {
        "atlas": atlas_id,
        "aligned_to": "gm",
        "aligned_to_fingerprint": surface_fp,
        "vertices": int(len(gm_vertices)),
        "triangles": int(len(gm_triangles)) if gm_triangles is not None else 0,
        "regions": len(legend),
        "radius_mm": LABEL_RADIUS_MM,
        "labelled_fraction": round(float((labels != NO_REGION).mean()), 4),
        "legend": legend,
        "format_bytes": {name: len(data) for name, data in blobs.items()},
        "build_ms": round(build_ms, 1),
    }
    return _publish_formats(
        pm.project_dir, sid, _labels_key(atlas_id), fp, blobs, meta
    )


def _labels_key(atlas_id: str) -> str:
    """Cache key for one atlas' labels payload (``labels-DK40``)."""
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in atlas_id)
    return f"labels-{safe}"


def read_net(pm: PathManager, sid: str, net: str) -> dict:
    """One EEG net's electrode positions in the surfaces' own world space.

    Cheap enough (75-256 rows of CSV) that it is never cached: the cost is a
    file read, and a cache entry would only add a way to serve stale
    positions after an electrode file is regenerated.
    """
    if "/" in net or "\\" in net or net in ("", ".", ".."):
        raise SceneUnavailable(f"{net!r} is not a net file name")
    path = Path(pm.eeg_positions(sid)) / net
    if not path.is_file():
        raise SceneUnavailable(f"{sid} has no EEG net file {net}")
    parsed = parse_electrode_csv(path.read_text(encoding="utf-8", errors="replace"))
    return {"net": net, "space": "subject-ras", **parsed}


def volume_legend(pm: PathManager, sid: str, volume_id: str = "labeling") -> dict:
    """``{entries:[{id,name,color}]}`` for the subject's label volume."""
    if volume_id != "labeling":
        raise SceneUnavailable(f"unknown scene volume {volume_id!r}")
    lut = Path(pm.m2m(sid)) / "segmentation" / "labeling_LUT.txt"
    if not lut.is_file():
        raise SceneUnavailable(f"{sid} has no segmentation/labeling_LUT.txt")
    return {"id": volume_id, "entries": parse_lut_text(lut.read_text(encoding="utf-8", errors="replace"))}
