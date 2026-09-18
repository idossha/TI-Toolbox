"""The ROI scene: one small ``*.tetravox.json`` that points at the files a job already has.

Why this exists
---------------
A number about an ROI is only as good as the ROI.  A mask that landed in the
wrong hemisphere, kept an island 40 mm away, or came back empty from a transform
produces a *self-consistent* result about the wrong voxels — the optimisation
converges, the focality ratio is finite, the analyzer's table is full.  So every
optimizer and every analyzer run leaves behind something a person can open and
look at, written at the **start** of the run, for every ROI, in every space.

What it leaves behind is **one file per target**::

    roi.tetravox.json         the scene: the subject's own T1 plus the ROI layer

(An analysis writes no ROI-only scene: its one ``scene.tetravox.json`` shows the
field masked to the ROI over the anatomy -- :mod:`tit.analyzer.scene`, built on
the same helpers.)

A scene is the format Tetravox's own *File ▸ Save Scene* writes and *Open in
Tetravox* reads, so the artefact is the viewer's own document, not a picture of
one.  It is a few kilobytes and it **references files that already exist** — the
subject's ``m2m/T1.nii.gz``, the atlas the target names, the hemisphere's central
surface and its ``.annot``.  Nothing is
rasterised, resampled or duplicated to make it, with exactly one exception: an
**MNI** target is not the ROI that runs, so the transformed mask is written once,
as a compressed ``uint8`` ``roi_mask.nii.gz`` on the *atlas's* voxel grid (about
100 KB), and the scene points at that.

Every dataset path is written **relative to the scene file** whenever it is inside
the project, which is what makes one file work both in the container that wrote it
and on the host that opens it: neither has to rewrite a path.

Framing
-------
The user's requirement is that the ROI be **centred in the point of view and fill
it**.  :func:`plan_framing` turns a mask into a :class:`FramingPlan` that says
where the cursor goes and how far the view reaches, by these rules
(:data:`RULES` names each one; the chosen one is recorded in the scene's ``meta``):

``single``
    One connected region.  Cursor at its centroid, snapped to the nearest
    in-mask voxel when the centroid falls outside the mask (a C-shaped
    hippocampus's centroid sits in the ventricle).  Zoom so the region's bounding
    box fills :data:`FILL_FRACTION` of the panel.
``union``
    Several regions whose union spans no more than :data:`SPAN_LIMIT_MM`
    (bilateral thalami, a two-label union).  Cursor at the centroid of the union,
    snapped to the nearest in-mask voxel of the **largest** region; zoom to the
    union's bounding box.
``per-region``
    Several regions whose union spans more than :data:`SPAN_LIMIT_MM`.  A scene
    has one cursor, so it is framed on the largest region; the others are listed
    in ``meta.regions`` with their own cursors.
``sphere``
    A spherical ROI.  Cursor at the sphere's centre (not the mask centroid — the
    centre is what the user typed), radius drives the zoom.
``empty``
    Nothing in the mask.  No scene, one terminal line, and that is the failure
    the user most needs to see.

Two rules, each with the failure it prevents:

* **A scene never fails a job.**  Everything here is wrapped: the T1 may be
  unreadable, the output directory read-only.  None of that is a reason to refuse
  to run an optimisation.  A failure is one log line.
* **It describes the ROI that will actually be used**, never a second computation
  of it.

The optional picture
--------------------
There is no renderer in this module and no matplotlib.  On a desktop with
Tetravox installed, ``desktop/src/main/roiPlates.ts`` runs it once per scene when
the job finishes and writes ``<scene>.png`` beside it.  No
Tetravox, no PNG — the scene is still there and *Open in Tetravox* still works.
"""

from __future__ import annotations

import gzip
import json
import logging
import math
import os
import shutil
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

logger = logging.getLogger(__name__)

#: A union wider than this in any axis is framed on its largest region instead of
#: on a zoom that holds both.  60 mm is a little under the width of both thalami
#: plus the third ventricle: anything that spans more is two structures, not one
#: target, and a zoom that holds both leaves each too small to judge an outline by.
SPAN_LIMIT_MM = 60.0

#: The fraction of the panel the ROI's bounding box fills.  0.60 leaves enough
#: anatomy around the outline to tell whether it followed the structure.
FILL_FRACTION = 0.60

#: Millimetres of guaranteed anatomy outside the bounding box, whatever the zoom.
MARGIN_MM = 4.0

#: Rows in a per-region framing before the rest are only listed in ``meta``.
MAX_ROWS = 4

#: A connected component smaller than this fraction of the largest one, or than
#: this many voxels, is an *island*, not a region: a real segmentation label has
#: dozens of single-voxel specks from the nearest-neighbour resampling, and
#: treating each as a region turns a thalamus into a 62-region plan.  Islands are
#: still drawn, in the largest region's colour, and counted in ``meta`` -- they
#: are exactly what `tit/atlas/islands.py` exists to remove, so seeing them is
#: the point.
MIN_REGION_FRACTION = 0.02
MIN_REGION_VOXELS = 10

#: Region fills, green first (the colour the confirmation has always used).
PALETTE = ["#4caf50", "#e69f00", "#56b4e9", "#cc79a7", "#009e73", "#d55e00"]

#: One panel's width in pixels, and the panel aspect (height / width) — the
#: 1600x1200 window in a 2x2 layout, i.e. 800x600 panes.
PANEL_PX = 533
PANEL_ASPECT = 0.75

#: The one artefact per target.
SCENE_NAME = "roi.tetravox.json"
SCENE_SUFFIX = ".tetravox.json"

#: The one legitimate intermediate: an MNI target's transformed mask.
MNI_MASK_NAME = "roi_mask.nii.gz"

#: Set to ``1`` to skip the scene entirely (a batch that wants no artefacts).
DISABLE_ENV = "TIT_NO_ROI_PLATE"

RULES = ("single", "union", "per-region", "sphere", "empty")

#: (panel letter order, plane axis in a canonical RAS grid, its name).
PANELS = ((2, "axial"), (1, "coronal"), (0, "sagittal"))

#: For each panel: the canonical axes drawn horizontally and vertically, and the
#: four edge letters (left, right, bottom, top).  Neurological convention.
_PANEL_AXES = {
    "axial": (0, 1, ("L", "R", "P", "A")),
    "coronal": (0, 2, ("L", "R", "I", "S")),
    "sagittal": (1, 2, ("A", "P", "I", "S")),
}


def enabled() -> bool:
    return os.environ.get(DISABLE_ENV, "").strip().lower() not in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# Framing
# --------------------------------------------------------------------------- #


@dataclass
class Region:
    """One connected component or one label of the ROI, in world millimetres."""

    name: str
    voxels: int
    centroid_ras: list[float]
    cursor_ras: list[float]
    bbox_min_ras: list[float]
    bbox_max_ras: list[float]
    color: str = PALETTE[0]
    #: Voxel value selecting this region in the mask array (1 for a binary mask).
    value: int = 1
    #: The region's own member points in world millimetres, so the cursor rules
    #: need neither the array nor the affine they came from.  Not serialised.
    world: object = dataclass_field(default=None, repr=False, compare=False)

    @property
    def span_mm(self) -> list[float]:
        return [hi - lo for lo, hi in zip(self.bbox_min_ras, self.bbox_max_ras)]

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "voxels": self.voxels,
            "centroid_ras": [round(v, 2) for v in self.centroid_ras],
            "cursor_ras": [round(v, 2) for v in self.cursor_ras],
            "bbox_ras": [
                [round(v, 2) for v in self.bbox_min_ras],
                [round(v, 2) for v in self.bbox_max_ras],
            ],
            "color": self.color,
        }


@dataclass
class Row:
    """One A/B/C row of the plate: a cursor, a zoom and the regions drawn in it."""

    label: str
    cursor_ras: list[float]
    #: Millimetres across one panel's width.  The height follows PANEL_ASPECT.
    width_mm: float
    regions: list[Region]

    @property
    def mm_per_px(self) -> float:
        return self.width_mm / PANEL_PX

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "cursor_ras": [round(v, 2) for v in self.cursor_ras],
            "width_mm": round(self.width_mm, 2),
            "mm_per_px": round(self.mm_per_px, 4),
            "regions": [r.name for r in self.regions],
        }


@dataclass
class FramingPlan:
    """Where the cursor goes and how far the view reaches, and why."""

    rule: str
    regions: list[Region]
    rows: list[Row] = dataclass_field(default_factory=list)
    omitted_regions: list[str] = dataclass_field(default_factory=list)
    reason: str = ""
    #: Voxels below the island floor, folded into the largest region.
    island_voxels: int = 0
    #: The mask rewritten so each region owns one value -- the array the renderer
    #: draws, produced once here so a fill is always the region the sidecar counted.
    region_map: object | None = None

    @property
    def empty(self) -> bool:
        return self.rule == "empty"

    @property
    def cursor_ras(self) -> list[float]:
        return self.rows[0].cursor_ras if self.rows else [0.0, 0.0, 0.0]

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "reason": self.reason,
            "span_limit_mm": SPAN_LIMIT_MM,
            "fill_fraction": FILL_FRACTION,
            "island_voxels": self.island_voxels,
            "rows": [row.as_dict() for row in self.rows],
            "regions": [region.as_dict() for region in self.regions],
            "omitted_regions": self.omitted_regions,
        }


def _snap(point, world):
    """*point* (world mm) if it is on a member point, else the nearest one.

    A C-shaped structure's centroid is outside it.  Snapping is what makes
    "cursor at the centroid" a rule that always lands *in* the ROI, which is what
    a person checking an outline needs.

    *world* is an ``(N, 3)`` array of the region's own points in millimetres --
    voxel centres for a volume target, surface vertices for a cortical one -- so
    one rule serves both without either needing a rasterisation.
    """
    import numpy as np

    world = np.asarray(world, dtype=float)
    distances = np.linalg.norm(world - np.asarray(point, dtype=float), axis=1)
    return [float(v) for v in world[int(np.argmin(distances))]]


def _region(name, world, half, color, value=1, count=None) -> Region:
    """One region from its member points in world millimetres.

    *half* is half the extent of one member (half a voxel for a volume target,
    a fixed half-millimetre for a surface vertex), so the bounding box is of
    member *edges* rather than centres and a one-voxel region still has a
    non-zero span -- which is what keeps the zoom below finite.
    """
    import numpy as np

    world = np.asarray(world, dtype=float)
    centroid = world.mean(axis=0)
    half = np.asarray(half, dtype=float)
    return Region(
        name=name,
        voxels=int(len(world) if count is None else count),
        centroid_ras=[float(v) for v in centroid],
        cursor_ras=_snap(centroid, world),
        bbox_min_ras=[float(v) for v in world.min(axis=0) - half],
        bbox_max_ras=[float(v) for v in world.max(axis=0) + half],
        color=color,
        value=int(value),
        world=world,
    )


def _width_mm(regions) -> float:
    """Millimetres across a panel so every region's box fills FILL_FRACTION.

    One width for all three panels of a row, so the scale bar means the same
    thing in A, B and C — a reader comparing panels of one plate is comparing
    one structure, and two zooms would make that a trap.
    """
    lo = [min(r.bbox_min_ras[i] for r in regions) for i in range(3)]
    hi = [max(r.bbox_max_ras[i] for r in regions) for i in range(3)]
    span = [hi[i] - lo[i] for i in range(3)]
    # Each panel draws two of the three axes; the binding one is whichever needs
    # the widest view once the panel's aspect is taken into account.
    needed = 0.0
    for _, plane in PANELS:
        horizontal, vertical, _ = _PANEL_AXES[plane]
        needed = max(needed, span[horizontal], span[vertical] / PANEL_ASPECT)
    return needed / FILL_FRACTION + 2.0 * MARGIN_MM


def _region_map(values):
    """*values* rewritten so each region owns one value: labels, else components.

    One function decides what a "region" is, and both the framing and the
    renderer call it, so the fill drawn for a region is the region the sidecar
    counted.
    """
    import numpy as np

    distinct = [int(v) for v in np.unique(values) if v > 0]
    if len(distinct) > 1:
        return values.astype(np.int32), distinct, "labels"
    try:
        from scipy.ndimage import label as scipy_label

        labelled, count = scipy_label(values > 0)
        return labelled.astype(np.int32), list(range(1, int(count) + 1)), "components"
    except Exception:  # noqa: BLE001 - one region is a truthful degradation
        return (values > 0).astype(np.int32), [1], "components"


def plan_framing(
    mask,
    affine,
    *,
    names=None,
    spheres=None,
    span_limit_mm: float = SPAN_LIMIT_MM,
) -> FramingPlan:
    """Decide the cursor and the zoom for *mask* (a 3-D array in a RAS grid).

    Args:
        mask: integer array. Non-zero is in the ROI. Distinct positive values are
            treated as distinct regions; a binary mask is split into connected
            components instead.
        affine: the array's voxel-to-world (RAS, millimetres) affine.
        names: optional ``{value: name}`` for a labelled mask, or a list of names
            in descending-size order.
        spheres: optional ``[(centre_ras, radius_mm), ...]`` — a spherical ROI's
            cursor is its **centre** and its radius drives the zoom, because the
            centre is what the user typed and the mask is only its rasterisation.
        span_limit_mm: above this union span the plate gets one row per region.

    Returns:
        A :class:`FramingPlan`; ``rule == "empty"`` when nothing is in the mask.
    """
    import numpy as np

    array = np.asarray(mask)
    if array.ndim != 3:
        array = np.squeeze(array)
    values = np.rint(array).astype(np.int64)
    if not values.any():
        return FramingPlan(
            rule="empty", regions=[], reason="the mask has no non-zero voxels"
        )

    import nibabel as nib

    region_map, ids, kind = _region_map(values)
    half = np.abs(np.asarray(affine)[:3, :3]).sum(axis=0) / 2.0
    regions: list[Region] = []
    for value in ids:
        voxels = np.argwhere(region_map == value)
        if not len(voxels):
            continue
        world = nib.affines.apply_affine(affine, voxels)
        regions.append(_region(f"region {value}", world, half, PALETTE[0], value=value))
    regions.sort(key=lambda r: r.voxels, reverse=True)

    islands = 0
    if kind == "components" and len(regions) > 1:
        floor = max(MIN_REGION_VOXELS, MIN_REGION_FRACTION * regions[0].voxels)
        kept = [r for r in regions if r.voxels >= floor] or regions[:1]
        for region in regions[len(kept) :]:
            # Folded into the largest region so they still draw, in its colour.
            region_map[region_map == region.value] = kept[0].value
            islands += region.voxels
        regions = kept

    for index, region in enumerate(regions):
        region.color = PALETTE[index % len(PALETTE)]
        # A name dictionary is keyed by *label value*, which only a labelled mask
        # has; components are numbered, so only a positional list applies to them.
        lookup = names if kind == "labels" or not isinstance(names, dict) else None
        region.name = _name_for(lookup, index, region.value, f"region {region.value}")

    # A sphere's centre beats its rasterised centroid, and its radius beats its
    # bounding box: both are what the user typed, and a rasterised sphere's
    # bounding box is a voxel or two bigger on every side.
    if spheres:
        for centre, radius in spheres:
            centre = [float(v) for v in centre]
            target = min(
                regions,
                key=lambda r: sum((a - b) ** 2 for a, b in zip(r.centroid_ras, centre)),
            )
            target.cursor_ras = centre
            target.bbox_min_ras = [v - float(radius) for v in centre]
            target.bbox_max_ras = [v + float(radius) for v in centre]

    return _rows_for(regions, spheres, span_limit_mm, islands, region_map)


def _rows_for(regions, spheres, span_limit_mm, islands, region_map) -> FramingPlan:
    """The rule, the rows and the zoom for regions that are already named and coloured.

    One function, so a volume target and a cortical one are framed by exactly the
    same rules and a reader of ``meta.rule`` never has to ask which planner wrote it.
    """
    if len(regions) == 1:
        rule = "sphere" if spheres else "single"
        reason = (
            "one sphere: cursor at its centre, radius drives the zoom"
            if spheres
            else "one region: cursor at its centroid, snapped into the mask"
        )
        rows = [Row("A/B/C", regions[0].cursor_ras, _width_mm(regions), regions)]
        return FramingPlan(
            rule=rule,
            regions=regions,
            rows=rows,
            reason=reason,
            island_voxels=islands,
            region_map=region_map,
        )

    lo = [min(r.bbox_min_ras[i] for r in regions) for i in range(3)]
    hi = [max(r.bbox_max_ras[i] for r in regions) for i in range(3)]
    span = max(hi[i] - lo[i] for i in range(3))
    if span <= span_limit_mm:
        cursor = _union_cursor(regions, spheres)
        rows = [Row("A/B/C", cursor, _width_mm(regions), regions)]
        return FramingPlan(
            rule="union",
            regions=regions,
            rows=rows,
            reason=(
                f"{len(regions)} regions spanning {span:.0f} mm "
                f"(<= {span_limit_mm:.0f} mm): one row on the union"
            ),
            island_voxels=islands,
            region_map=region_map,
        )

    shown = regions[:MAX_ROWS]
    rows = [
        Row(f"{r.name} ({r.voxels} voxels)", r.cursor_ras, _width_mm([r]), [r])
        for r in shown
    ]
    return FramingPlan(
        rule="per-region",
        regions=regions,
        rows=rows,
        omitted_regions=[r.name for r in regions[MAX_ROWS:]],
        reason=(
            f"{len(regions)} regions spanning {span:.0f} mm "
            f"(> {span_limit_mm:.0f} mm): one row per region, largest first"
        ),
        island_voxels=islands,
        region_map=region_map,
    )


def _name_for(names, index, value, default):
    if isinstance(names, dict):
        return str(names.get(value, names.get(str(value), default)))
    if isinstance(names, (list, tuple)) and index < len(names):
        return str(names[index])
    return default


def _union_cursor(regions, spheres):
    """Centroid of the union, snapped into the **largest** region.

    Snapping into the union's nearest point would put the cursor on whichever
    region happened to be closest to the midpoint between them; the largest
    region is the one a reader is most likely to be checking.
    """
    import numpy as np

    weights = np.array([r.voxels for r in regions], dtype=float)
    centroids = np.array([r.centroid_ras for r in regions], dtype=float)
    centre = (centroids * weights[:, None]).sum(axis=0) / weights.sum()
    if spheres:
        return [float(v) for v in centre]
    return _snap(centre, regions[0].world)


def plan_spheres(spheres, *, names=None) -> FramingPlan:
    """The framing for a **spherical** target, from the centres and radii typed.

    A sphere has no file and needs none: its centre is the cursor and its radius
    is the zoom, both exactly as the user typed them, which is why this is the
    one target whose framing is not derived from voxels at all.  The scene it
    produces is the subject's T1 with the crosshair on the centre -- Tetravox
    0.5.2's ``ViewSpec`` has no sphere or marker primitive to draw the extent
    with (``packages/engine/src/scene/types.ts``: ``sphere`` appears only inside
    a mesh ``IsolateSpec``), so the crosshair and the scale bar are what say
    where and how big.
    """
    regions = [
        _region(
            _name_for(names, index, index + 1, f"sphere {index + 1}"),
            [[float(v) for v in centre]],
            (float(radius), float(radius), float(radius)),
            PALETTE[index % len(PALETTE)],
            value=index + 1,
            count=1,
        )
        for index, (centre, radius) in enumerate(spheres)
    ]
    if not regions:
        return FramingPlan(rule="empty", regions=[], reason="no sphere was given")
    plan = _rows_for(regions, list(spheres), SPAN_LIMIT_MM, 0, None)
    plan.rule = "sphere"
    return plan


def plan_surface(
    groups, *, names=None, span_limit_mm: float = SPAN_LIMIT_MM
) -> FramingPlan:
    """The same framing for a **cortical** target, from its surface vertices.

    *groups* is one ``(N, 3)`` array of world-millimetre vertices per region --
    the labelled vertices of the hemisphere's central surface.  A cortical target
    is a set of vertices, not voxels, and this is what lets the scene reference
    the ``.annot`` itself instead of a rasterisation of it: nothing is written to
    get a cursor.

    Half a millimetre of half-extent per vertex, because a vertex is a point and
    a zero-span bounding box would make the zoom infinite.
    """
    regions: list[Region] = []
    for index, points in enumerate(groups):
        if not len(points):
            continue
        name = _name_for(names, index, index + 1, f"region {index + 1}")
        regions.append(
            _region(name, points, (0.5, 0.5, 0.5), PALETTE[0], value=index + 1)
        )
    if not regions:
        return FramingPlan(
            rule="empty", regions=[], reason="the target covers no surface vertex"
        )
    regions.sort(key=lambda r: r.voxels, reverse=True)
    for index, region in enumerate(regions):
        region.color = PALETTE[index % len(PALETTE)]
    return _rows_for(regions, None, span_limit_mm, islands=0, region_map=None)


# --------------------------------------------------------------------------- #
# The scene
# --------------------------------------------------------------------------- #
#
# A Tetravox ViewSpec v2 -- exactly what File > Save Scene writes and what
# `Tetravox scene.tetravox.json` and a `--job` with `{"scene": {"path": ...}}`
# read (tetravox `packages/engine/src/scene/types.ts` ViewSpec, `docs/AUTOMATION.md`
# section 2.1).  Written by hand rather than through `tit/viewspec.py` because that
# module builds *server* scenes addressed by `/api/files/raw` URLs for the browser
# embed, and this one has to be openable as a file by a desktop application that
# never talks to the server.
#
# Unknown top-level keys are carried through by Tetravox's own reader
# (`packages/app/src/renderer/src/lib/scene.ts::parseScene` checks `version`,
# `datasets` and `layers` and nothing else), which is what lets `meta` hold the
# numbers the terminal line prints without a second sidecar file.

_BACKGROUND = [0.058823529411764705, 0.06666666666666667, 0.08627450980392157, 1.0]
_LIGHTING = {"ambient": 0.25, "headlight": True}
_ANNOTATIONS = {
    "orientationLabels": True,
    "cornerInfo": True,
    "conventionBadge": True,
    "scaleBar": True,
    "colorbars": True,
    "crosshair": True,
    "orientationCube": True,
}
#: (id, normal, up) per canonical slice pane, and the in-plane right axis the
#: camera's `center` offset is measured along -- `right = up x normal`, which is
#: +x for axial and coronal and -y (anterior to the left) for sagittal.
_SLICE_AXES = (
    ("axial", (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
    ("coronal", (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)),
    ("sagittal", (-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
)
#: The pane order of each Tetravox layout this module writes.
LAYOUT_CELLS = {
    "2x2": ["axial", "coronal", "sagittal", "view3d"],
    "1+3": ["view3d", "axial", "coronal", "sagittal"],
}
_DEFAULT_THRESHOLD = {
    "lo": None,
    "hi": None,
    "symmetric": False,
    "mode": "clamp",
    "softEdge": 0.0,
}


def _rgba(hex_color):
    """``"#4caf50"`` as Tetravox's 0..1 RGBA."""
    value = hex_color.lstrip("#")
    return [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)] + [1.0]


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def scene_path(target: str, scene_dir: str) -> str:
    """*target* as the scene addresses it: relative to the scene when it can be.

    A relative path is the one addressing that is correct in the container that
    wrote the scene **and** on the host that opens it, because both see the same
    project tree under different roots.  Anything outside the project (a bundled
    MNI atlas) keeps its absolute path -- it is not part of what gets re-rooted,
    and a `../../../..` chain out of the project would be wrong on both.
    """
    try:
        from tit.paths import get_path_manager

        project = get_path_manager().project_dir
    except Exception:  # noqa: BLE001 - outside a project there is no re-rooting
        project = None
    resolved = os.path.realpath(str(target))
    if project:
        root = os.path.realpath(str(project))
        if resolved == root or resolved.startswith(root.rstrip(os.sep) + os.sep):
            return os.path.relpath(resolved, os.path.realpath(str(scene_dir)))
    return resolved


def _volume_bounds(path: str):
    """The world bounding box of a NIfTI, from its header alone."""
    import nibabel as nib
    import numpy as np

    image = nib.load(str(path))
    shape = np.asarray(image.shape[:3], dtype=float)
    corners = np.array(
        [
            [i, j, k]
            for i in (-0.5, shape[0] - 0.5)
            for j in (-0.5, shape[1] - 0.5)
            for k in (-0.5, shape[2] - 0.5)
        ]
    )
    world = nib.affines.apply_affine(image.affine, corners)
    return [float(v) for v in world.min(axis=0)], [float(v) for v in world.max(axis=0)]


def _upper_window(path: str, *, percentile: float = 99.9) -> float:
    """A display ceiling for *path*, read off a strided sample of its voxels.

    A T1's maximum is a scalp-fat voxel; a window anchored on it washes the brain
    out to flat white, which is what made the first scenes unreadable.  Every
    fourth voxel is plenty for a percentile and costs a fraction of the read.
    """
    import nibabel as nib
    import numpy as np

    data = np.asarray(nib.load(str(path)).dataobj[::4, ::4, ::4], dtype=np.float32)
    finite = data[np.isfinite(data) & (data > 0)]
    return float(np.percentile(finite, percentile)) if finite.size else 1.0


def _dataset(index: int, path: str, scene_dir: str, kind: str, sidecars=None) -> dict:
    entry = {
        "id": f"ds{index}",
        "kind": kind,
        "name": os.path.basename(path),
        "path": scene_path(path, scene_dir),
        # Tetravox keys its "relocate this dataset" dialog on the fingerprint and
        # computes it itself on load; an empty one simply means "not recorded".
        "fingerprint": "",
    }
    if sidecars:
        entry["sidecars"] = sidecars
    return entry


def _base_layer(index: int, dataset_id: str, name: str, **rest) -> dict:
    """``LayerBase`` (Tetravox section 4.4) with *rest* layered over the defaults.

    A dict update rather than keyword defaults, so a caller may override any of
    them -- an `opacity=` for the 40 % fill, a `showColorbar=` for the field --
    without every override becoming a duplicate-keyword error.
    """
    layer = {
        "id": f"layer{index}",
        "datasetId": dataset_id,
        # The file's own basename, exactly as it is on disk: a name a person can
        # grep a log for beats a curated one they cannot look up.
        "name": name,
        "visible": True,
        "opacity": 1.0,
        "pickable": True,
        "showColorbar": False,
    }
    layer.update(rest)
    return layer


def _volume_layer(index, dataset_id, name, **rest) -> dict:
    defaults = {
        "kind": "volume",
        "volumeIndex": 0,
        "colormap": "gray",
        "scale": {"kind": "linear", "lo": 0.0, "hi": 1.0},
        "threshold": dict(_DEFAULT_THRESHOLD),
        "interpolation": "linear",
        "labelMode": "fill",
        "outlineWidthPx": 1,
        "showIn3D": False,
        "precision": "auto",
    }
    defaults.update(rest)
    return _base_layer(index, dataset_id, name, **defaults)


def build_scene(
    *,
    scene_dir: str,
    anatomy: str,
    roi_layers: list[dict],
    plan: FramingPlan,
    meta: dict,
) -> dict:
    """The ViewSpec for one target.  Pure but for reading volume headers.

    Args:
        scene_dir: the directory the scene file goes in (paths are relative to it).
        anatomy: the subject's own ``T1.nii.gz``.
        roi_layers: one entry per ROI source, each
            ``{"kind": "volume"|"surface", "path": ..., "labels": {value: colour},
            "annot": <path, surface only>}``.
        plan: the framing -- its first row gives the cursor and the zoom.
        meta: what goes in the scene's ``meta`` block (the numbers the terminal
            line prints, so nothing is lost by dropping the JSON sidecar).
    """
    datasets: list[dict] = []
    layers: list[dict] = [anatomy_layer(anatomy)]
    datasets.append(_dataset(0, anatomy, scene_dir, "volume"))

    # A label volume is listed twice and styled twice: a VolumeLayer has one
    # opacity and one `labelMode`, so a 40 % fill under an opaque outline is two
    # layers over one dataset.
    fills: list[dict] = []
    outlines: list[dict] = []
    for entry in roi_layers:
        index = len(datasets)
        path = entry["path"]
        colors = {str(k): _rgba(v) for k, v in entry["labels"].items()}
        visible = sorted(int(k) for k in entry["labels"])
        if entry["kind"] == "surface":
            annot = entry["annot"]
            datasets.append(
                _dataset(
                    index,
                    path,
                    scene_dir,
                    "surface",
                    sidecars={
                        # Relative to the **surface's** own directory: the one path
                        # in a scene that is never re-rooted (Tetravox section 4.6).
                        "fields": [
                            {"path": os.path.relpath(annot, os.path.dirname(path))}
                        ]
                    },
                )
            )
            fills.append(
                _base_layer(
                    index,
                    f"ds{index}",
                    os.path.basename(path),
                    kind="surface",
                    colorMode="annotation",
                    solidColor=_rgba(PALETTE[0]),
                    colormap="viridis",
                    scale={"kind": "linear", "lo": 0.0, "hi": 1.0},
                    threshold=dict(_DEFAULT_THRESHOLD),
                    annotation={
                        # The node field the worker creates is named after the file
                        # it attached, extension and all.
                        "name": os.path.basename(annot),
                        "mode": "both",
                        "outlineWidthPx": 2.0,
                        "visibleLabels": visible,
                    },
                    flatShading=False,
                    faceMode="cull",
                    edges=False,
                    edgeColor=[0.0, 0.0, 0.0, 1.0],
                    edgeWidthPx=1.0,
                    clip={"planes": []},
                    contoursIn2D=True,
                    contourWidthPx=2.0,
                    contourColor=_rgba(list(entry["labels"].values())[0]),
                )
            )
            continue
        datasets.append(_dataset(index, path, scene_dir, "volume"))
        common = dict(
            interpolation="nearest",
            # The plan's own palette, not the file's LUT: a binary mask's value 1
            # is blue in every LUT, and a two-region target must show two colours
            # whatever the atlas called them.
            labelColors=colors,
            visibleLabels=visible,
            showIn3D=False,
        )
        fills.append(
            _volume_layer(
                index,
                f"ds{index}",
                os.path.basename(path),
                opacity=0.4,
                labelMode="fill",
                **common,
            )
        )
        outlines.append(
            _volume_layer(
                len(roi_layers) + index,
                f"ds{index}",
                os.path.basename(path),
                labelMode="outline",
                outlineWidthPx=2,
                **common,
            )
        )
    layers.extend(fills)
    layers.extend(outlines)

    row = plan.rows[0]
    return assemble_scene(
        datasets=datasets,
        layers=layers,
        cursor=[float(v) for v in row.cursor_ras],
        mm_per_px=float(row.mm_per_px),
        bounds=_volume_bounds(anatomy),
        meta=meta,
    )


def anatomy_layer(anatomy: str, index: int = 0, dataset_id: str = "ds0") -> dict:
    """The grey T1 under everything, windowed so the brain is not washed out."""
    return _volume_layer(
        index,
        dataset_id,
        os.path.basename(anatomy),
        scale={"kind": "linear", "lo": 0.0, "hi": _upper_window(anatomy)},
    )


def assemble_scene(
    *,
    datasets: list[dict],
    layers: list[dict],
    cursor: list[float],
    mm_per_px: float,
    bounds,
    meta: dict,
    layout: str = "2x2",
    transparency: str = "twoPhase",
) -> dict:
    """A version-2 ViewSpec around *layers*: the panes framed on *cursor*.

    Shared by the ROI scene and the analysis scene (:mod:`tit.analyzer.scene`),
    so both frame the same way.  *bounds* is the ``(lo, hi)`` world box the
    slice cameras are centred against and the 3D camera is fitted to.
    """
    # Re-id the layers in the order they were finally stacked, so a reader of the
    # file sees layer0 at the bottom and nothing has to be sorted to draw it.
    for position, layer in enumerate(layers):
        layer["id"] = f"layer{position}"

    lo, hi = bounds
    centre = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    offset = [cursor[i] - centre[i] for i in range(3)]
    radius = max(1.0, 0.5 * math.dist(lo, hi))

    slices = []
    for slice_id, normal, up in _SLICE_AXES:
        right = _cross(up, normal)
        slices.append(
            {
                "id": slice_id,
                "mode": slice_id,
                "normal": list(normal),
                "up": list(up),
                # The camera's `center` is in-plane and relative to the **scene
                # bounds centre**, not to the cursor (Tetravox section 4.5: a pane
                # whose map followed the cursor would slide whenever the cursor
                # moved).  So "the ROI is centred" is this offset, computed here.
                "camera": {
                    "center": [
                        round(sum(offset[i] * right[i] for i in range(3)), 4),
                        round(sum(offset[i] * up[i] for i in range(3)), 4),
                    ],
                    "mmPerPx": round(mm_per_px, 6),
                },
            }
        )

    return {
        "version": 2,
        "datasets": datasets,
        "layers": layers,
        "activeLayerId": layers[1]["id"] if len(layers) > 1 else layers[0]["id"],
        "slices": slices,
        "view3d": {
            "id": "view3d",
            "camera": {
                "target": cursor,
                "distance": radius / math.sin(math.radians(35.0) * 0.5),
                "rotation": [0.3317, -0.6158, -0.6307, 0.3363],
                "fovYDeg": 35.0,
                "orthographic": False,
                "near": max(1.0, radius / 1000.0),
                "far": radius * 8.0,
            },
            "showSlicePlanes": False,
        },
        "layout": {"kind": layout, "cells": LAYOUT_CELLS[layout]},
        "cursor": cursor,
        "radiological": False,
        "background": list(_BACKGROUND),
        "lighting": dict(_LIGHTING),
        "annotations": dict(_ANNOTATIONS),
        "transparency": {"mode": transparency},
        # Not engine state, and deliberately the only sidecar: every number the
        # retired `roi_plate.json` carried lives here, in the file the user opens.
        "meta": meta,
    }


def write_roi_scene(
    *,
    out_dir: str,
    anatomy: str,
    roi_layers: list[dict],
    plan: FramingPlan,
    meta: dict,
    title: str = "",
) -> dict | None:
    """Write one ROI scene and announce it.  Never raises.

    Returns the ``meta`` block as written, or ``None`` when the scene was
    switched off or could not be written -- a job must not fail over an artefact
    a person looks at.
    """
    if not enabled():
        return None
    name = SCENE_NAME
    destination = Path(out_dir)
    try:
        destination.mkdir(parents=True, exist_ok=True)
        if plan.empty:
            print(
                f"ROI {title}: the target is EMPTY -- {plan.reason}; no scene written",
                flush=True,
            )
            logger.warning("ROI %s is empty: %s", title, plan.reason)
            return None
        scene = build_scene(
            scene_dir=str(destination),
            anatomy=anatomy,
            roi_layers=roi_layers,
            plan=plan,
            meta=meta,
        )
        path = destination / name
        path.write_text(json.dumps(scene, indent=1) + "\n", encoding="utf-8")
        _announce(path, "json", f"ROI scene — {title}" if title else "ROI scene")
        x, y, z = (round(v, 2) for v in plan.cursor_ras)
        overlap = meta.get("gm_overlap")
        overlap_text = (
            "GM overlap unknown"
            if overlap is None
            else f"GM overlap {overlap * 100:.0f} %"
        )
        print(
            f"ROI {title}: {meta.get('voxels', 0)} {meta.get('unit', 'voxels')}, "
            f"cursor ({x:g}, {y:g}, {z:g}) mm [{plan.rule}], {overlap_text} "
            f"-- see {name}",
            flush=True,
        )
        return meta
    except Exception as exc:  # noqa: BLE001 - a scene never fails a job
        logger.warning("ROI scene could not be written: %s", exc)
        return None


def write_mask_nii_gz(image, destination: Path) -> None:
    """Save a NIfTI as gzip, without nibabel's own gzip writer.

    nibabel writes a `.nii.gz` through a file object it seeks backwards in, which
    fails on a bind-mounted project inside the container.  Writing the plain
    `.nii` to a scratch file and compressing it with the standard library is the
    one thing that works on every mount this ships on.
    """
    import tempfile

    import nibabel as nib

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="roi-mask-") as scratch:
        plain = Path(scratch) / "mask.nii"
        nib.save(image, str(plain))
        with open(plain, "rb") as source, gzip.open(str(destination), "wb") as out:
            shutil.copyfileobj(source, out)


def _announce(path: Path, kind: str, label: str) -> None:
    try:
        from tit.jobs.events import emit_artifact

        emit_artifact(str(path), kind, label)
    except Exception as exc:  # noqa: BLE001 - outside a job there is no sink
        logger.debug("ROI scene artifact not announced: %s", exc)
