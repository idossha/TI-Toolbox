"""The ROI plate: three orthogonal slices with the ROI centred and filling the view.

Why this exists
---------------
A number about an ROI is only as good as the ROI.  A mask that landed in the
wrong hemisphere, kept an island 40 mm away, or came back empty from a transform
produces a *self-consistent* result about the wrong voxels — the optimisation
converges, the focality ratio is finite, the analyzer's table is full.  The plate
is the one artefact that makes that visible, so it is written at the **start** of
every optimizer and analyzer run, for every ROI, in every space.

Two rules, each with the failure it prevents:

* **A picture never fails a job.**  Everything here is wrapped.  matplotlib may be
  absent, the T1 unreadable, the directory read-only; none of that is a reason to
  refuse to run an optimisation.  A failure is one log line.
* **An empty mask is not a missing picture.**  When the transform produced nothing
  there is no plate, but there *is* a JSON that says so and a terminal line — that
  is a real failure the user must see, not a silently skipped figure.

Framing
-------
The user's requirement is that the ROI be **centred in the point of view and fill
it**.  :func:`plan_framing` turns a mask into a :class:`FramingPlan` that says
where the cursor goes and how far the view reaches, by these rules
(:data:`RULES` names each one; the chosen one is recorded in the sidecar):

``single``
    One connected region.  Cursor at its centroid, snapped to the nearest
    in-mask voxel when the centroid falls outside the mask (a C-shaped
    hippocampus's centroid sits in the ventricle).  Zoom so the region's bounding
    box fills :data:`FILL_FRACTION` of the panel.
``union``
    Several regions whose union spans no more than :data:`SPAN_LIMIT_MM`
    (bilateral thalami, a two-label union).  One row: cursor at the centroid of
    the union, snapped to the nearest in-mask voxel of the **largest** region;
    zoom to the union's bounding box.
``per-region``
    Several regions whose union spans more than :data:`SPAN_LIMIT_MM`, where one
    zoom would shrink each region to nothing.  One row of A/B/C per region,
    largest first, each with its own snapped centroid and its own zoom, each
    labelled with its name and voxel count.  At most :data:`MAX_ROWS` rows; the
    rest are counted in the sidecar's ``omitted_regions``.
``sphere``
    A spherical ROI.  Cursor at the sphere's centre (not the mask centroid — the
    centre is what the user typed), radius drives the zoom.  Several spheres fall
    back to ``union`` / ``per-region`` on their centres.
``empty``
    Nothing in the mask.  No plate.

Renderers
---------
One entry point, :func:`write_roi_plate`, two renderers behind it:

* **Tetravox** (``--job``, offscreen) when its executable is on this host — the
  same renderer the user inspects with, so the plate and the viewer cannot
  disagree, and the RAD/NEU badge is stamped by construction.
* **matplotlib**, which is what the container has.  It reproduces the framing
  exactly: the same three panels, the same cursor, the same zoom, the same green
  40 % fill with an opaque outline, the same inferno field masked to the ROI.

The container always writes the matplotlib plate and, beside it, a
``*.plate-request.json``.  Electron's main process runs Tetravox for each request
when a job finishes and overwrites the PNG in place (see
``desktop/src/main/roiPlates.ts``).  If Tetravox is absent the matplotlib plate is
the plate.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

logger = logging.getLogger(__name__)

#: A union wider than this in any axis gets one row per region instead of one
#: shared zoom.  60 mm is a little under the width of both thalami plus the third
#: ventricle: anything that spans more is two structures, not one target, and a
#: zoom that holds both leaves each of them too small to judge an outline by.
SPAN_LIMIT_MM = 60.0

#: The fraction of the panel the ROI's bounding box fills.  0.60 leaves enough
#: anatomy around the outline to tell whether it followed the structure.
FILL_FRACTION = 0.60

#: Millimetres of guaranteed anatomy outside the bounding box, whatever the zoom.
MARGIN_MM = 4.0

#: Rows in a per-region plate before the rest are only counted.
MAX_ROWS = 4

#: A connected component smaller than this fraction of the largest one, or than
#: this many voxels, is an *island*, not a region: a real segmentation label has
#: dozens of single-voxel specks from the nearest-neighbour resampling, and
#: treating each as a region turns a thalamus into a 62-row plate.  Islands are
#: still drawn, in the largest region's colour, and counted in the sidecar --
#: they are exactly what `tit/atlas/islands.py` exists to remove, so seeing them
#: is the point.
MIN_REGION_FRACTION = 0.02
MIN_REGION_VOXELS = 10

#: Region fills, green first (the colour the confirmation plate has always used).
PALETTE = ["#4caf50", "#e69f00", "#56b4e9", "#cc79a7", "#009e73", "#d55e00"]

#: One panel's width in pixels, and the panel aspect (height / width) — the
#: prototype's 1600x1200 window in a 2x2 layout, i.e. 800x600 panes.
PANEL_PX = 533
PANEL_ASPECT = 0.75

#: Colormap for a field masked to the ROI.  Same perceptually-uniform family as
#: viridis, but its dark-to-warm ramp separates the field from the grey T1.
FIELD_COLORMAP = "inferno"

#: threshold.lo as a fraction of the plate's p99.9 (never of its max: a whole-brain
#: TI field's max is one cortical voxel and 20 % of it hides the field).
FIELD_FLOOR_FRACTION = 0.20

#: What a field's colour bar is labelled with.
FIELD_UNIT = "V/m"

PLATE_PNG = "roi_plate.png"
PLATE_JSON = "roi_plate.json"
FIELD_PLATE_PNG = "roi_field_plate.png"
FIELD_PLATE_JSON = "roi_field_plate.json"
REQUEST_SUFFIX = ".plate-request.json"
SCENE_SUFFIX = ".tetravox.json"
JOB_SUFFIX = ".tetravox-job.json"

#: Set to ``1`` to skip the plate entirely (a batch that wants no pictures).
DISABLE_ENV = "TIT_NO_ROI_PLATE"

#: An explicit Tetravox executable, for a host run or a test.
TETRAVOX_ENV = "TIT_TETRAVOX"

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


def _snap(point, voxels, affine):
    """*point* (world mm) if it is on an in-mask voxel, else the nearest one.

    A C-shaped structure's centroid is outside it.  Snapping is what makes
    "cursor at the centroid" a rule that always lands *in* the ROI, which is what
    a person checking an outline needs.
    """
    import numpy as np
    import nibabel as nib

    world = nib.affines.apply_affine(affine, voxels)
    distances = np.linalg.norm(world - np.asarray(point, dtype=float), axis=1)
    return [float(v) for v in world[int(np.argmin(distances))]]


def _region(name, voxels, affine, color, value=1) -> Region:
    import numpy as np
    import nibabel as nib

    world = nib.affines.apply_affine(affine, voxels)
    centroid = world.mean(axis=0)
    # The bounding box is of voxel *edges*, not centres, so a one-voxel region
    # still has a non-zero span and the zoom below stays finite.
    half = np.abs(affine[:3, :3]).sum(axis=0) / 2.0
    return Region(
        name=name,
        voxels=int(len(voxels)),
        centroid_ras=[float(v) for v in centroid],
        cursor_ras=_snap(centroid, voxels, affine),
        bbox_min_ras=[float(v) for v in world.min(axis=0) - half],
        bbox_max_ras=[float(v) for v in world.max(axis=0) + half],
        color=color,
        value=int(value),
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

    region_map, ids, kind = _region_map(values)
    regions: list[Region] = []
    for value in ids:
        voxels = np.argwhere(region_map == value)
        if not len(voxels):
            continue
        regions.append(
            _region(f"region {value}", voxels, affine, PALETTE[0], value=value)
        )
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
        cursor = _union_cursor(regions, region_map, affine, spheres)
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


def _union_cursor(regions, region_map, affine, spheres):
    """Centroid of the union, snapped into the **largest** region.

    Snapping into the union's nearest voxel would put the cursor on whichever
    region happened to be closest to the midpoint between them; the largest
    region is the one a reader is most likely to be checking.
    """
    import numpy as np

    weights = np.array([r.voxels for r in regions], dtype=float)
    centroids = np.array([r.centroid_ras for r in regions], dtype=float)
    centre = (centroids * weights[:, None]).sum(axis=0) / weights.sum()
    if spheres:
        return [float(v) for v in centre]
    largest = regions[0]
    voxels = np.argwhere(region_map == largest.value)
    if not len(voxels):
        voxels = np.argwhere(region_map > 0)
    return _snap(centre, voxels, affine)


# --------------------------------------------------------------------------- #
# The matplotlib renderer (the one the container has)
# --------------------------------------------------------------------------- #


def _axis_mm(affine, shape, axis):
    """Voxel-centre coordinates along one axis of a RAS-aligned grid."""
    import numpy as np

    step = float(affine[axis, axis])
    start = float(affine[axis, 3])
    return start + step * np.arange(shape[axis], dtype=float)


def _slice(volume, plane, index):
    """The 2-D array of *volume* at *index* along *plane*, oriented for imshow.

    Returned with the panel's horizontal axis last, so ``imshow`` draws
    horizontal-across / vertical-up once ``origin="lower"`` is set.
    """
    import numpy as np

    horizontal, vertical, _ = _PANEL_AXES[plane]
    taken = np.take(
        volume, index, axis={"axial": 2, "coronal": 1, "sagittal": 0}[plane]
    )
    # `taken`'s axes are the two remaining canonical axes in ascending order.
    remaining = [
        a for a in (0, 1, 2) if a != {"axial": 2, "coronal": 1, "sagittal": 0}[plane]
    ]
    if remaining.index(horizontal) == 0:
        taken = taken.T  # rows must be the vertical axis
    return taken


def _extent(affine, shape, plane):
    """(left, right, bottom, top) in millimetres for ``imshow``."""
    horizontal, vertical, _ = _PANEL_AXES[plane]
    h = _axis_mm(affine, shape, horizontal)
    v = _axis_mm(affine, shape, vertical)
    hstep = abs(float(affine[horizontal, horizontal])) / 2.0
    vstep = abs(float(affine[vertical, vertical])) / 2.0
    left, right = h[0] - hstep, h[-1] + hstep
    if plane == "sagittal":
        left, right = right, left  # A left, P right
    return (left, right, v[0] - vstep, v[-1] + vstep)


def _index_of(affine, shape, axis, value):
    import numpy as np

    coords = _axis_mm(affine, shape, axis)
    return int(np.clip(np.argmin(np.abs(coords - value)), 0, shape[axis] - 1))


def _render_matplotlib(
    *,
    destination,
    mask,
    affine,
    background,
    plan,
    field=None,
    field_window=None,
    field_label="",
):
    """The plate, drawn with matplotlib to the framing *plan*."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import to_rgba

    rows = plan.rows
    width_in = 3 * PANEL_PX / 160.0
    height_in = len(rows) * PANEL_PX * PANEL_ASPECT / 160.0 + (
        0.35 if len(rows) > 1 else 0.0
    )
    figure, axes = plt.subplots(
        len(rows), 3, figsize=(width_in, height_in), facecolor="white", squeeze=False
    )
    letters = "ABCDEFGHIJKL"
    for row_index, row in enumerate(rows):
        for panel_index, (axis, plane) in enumerate(PANELS):
            ax = axes[row_index][panel_index]
            _draw_panel(
                ax,
                plane=plane,
                row=row,
                mask=mask,
                affine=affine,
                background=background,
                field=field,
                field_window=field_window,
                letter=letters[row_index * 3 + panel_index],
            )
        if len(rows) > 1:
            axes[row_index][0].set_ylabel(
                row.label, color="black", fontsize=8, labelpad=4
            )
    if field is not None and field_window is not None:
        _colorbar(figure, axes, field_window, field_label)
    figure.subplots_adjust(
        left=0.02 if len(rows) == 1 else 0.06,
        right=0.98,
        top=0.98,
        bottom=0.02,
        wspace=0.02,
        hspace=0.06,
    )
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(str(destination), dpi=160, facecolor="white")
    plt.close(figure)


def _draw_panel(
    ax, *, plane, row, mask, affine, background, field, field_window, letter
):
    import numpy as np
    from matplotlib.colors import to_rgba

    shape = mask.shape
    normal = {"axial": 2, "coronal": 1, "sagittal": 0}[plane]
    horizontal, vertical, edges = _PANEL_AXES[plane]
    index = _index_of(affine, shape, normal, row.cursor_ras[normal])
    extent = _extent(affine, shape, plane)
    ax.set_facecolor("black")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    if background is not None:
        grey = _slice(background, plane, index)
        finite = grey[np.isfinite(grey)]
        top = float(np.percentile(finite, 99.9)) if finite.size else 1.0
        ax.imshow(
            grey,
            cmap="gray",
            origin="lower",
            extent=extent,
            vmin=0.0,
            vmax=max(top, 1e-6),
            interpolation="bilinear",
        )

    if field is not None and field_window is not None:
        lo, hi = field_window
        layer = _slice(field, plane, index).astype(float)
        inside = _slice(mask, plane, index) > 0
        ax.imshow(
            np.ma.masked_where(~(inside & (layer >= lo)), layer),
            cmap=FIELD_COLORMAP,
            origin="lower",
            extent=extent,
            vmin=lo,
            vmax=hi,
            alpha=0.85,
            interpolation="bilinear",
        )
    else:
        for region in row.regions:
            inside = _slice(mask, plane, index) == region.value
            if not inside.any():
                continue
            rgba = np.zeros(inside.shape + (4,), dtype=float)
            rgba[inside] = to_rgba(region.color, 0.40)
            ax.imshow(rgba, origin="lower", extent=extent, interpolation="nearest")

    for region in row.regions:
        inside = (_slice(mask, plane, index) == region.value).astype(float)
        if inside.any():
            ax.contour(
                inside,
                levels=[0.5],
                colors=[region.color],
                linewidths=1.2,
                origin="lower",
                extent=extent,
            )

    half_w = row.width_mm / 2.0
    half_h = row.width_mm * PANEL_ASPECT / 2.0
    centre_h, centre_v = row.cursor_ras[horizontal], row.cursor_ras[vertical]
    if plane == "sagittal":
        ax.set_xlim(centre_h + half_w, centre_h - half_w)  # A left, P right
    else:
        ax.set_xlim(centre_h - half_w, centre_h + half_w)
    ax.set_ylim(centre_v - half_h, centre_v + half_h)

    ax.axvline(centre_h, color="#e0a030", linewidth=0.6, alpha=0.8)
    ax.axhline(centre_v, color="#e0a030", linewidth=0.6, alpha=0.8)

    _annotate(ax, plane, row, edges, letter)


def _annotate(ax, plane, row, edges, letter):
    """Panel letter, orientation letters, the RAD/NEU badge, RAS and a scale bar."""
    small = dict(color="white", fontsize=6, transform=ax.transAxes)
    ax.text(
        0.03,
        0.90,
        letter,
        color="white",
        fontsize=16,
        weight="bold",
        transform=ax.transAxes,
        va="center",
    )
    ax.text(0.99, 0.97, "NEU", ha="right", va="top", **small)
    ax.text(0.01, 0.50, edges[0], ha="left", va="center", **small)
    ax.text(0.99, 0.50, edges[1], ha="right", va="center", **small)
    ax.text(0.50, 0.01, edges[2], ha="center", va="bottom", **small)
    ax.text(0.50, 0.97, edges[3], ha="center", va="top", **small)
    x, y, z = row.cursor_ras
    ax.text(0.01, 0.07, plane.upper(), ha="left", va="bottom", **small)
    ax.text(0.01, 0.02, f"RAS {x:.1f} {y:.1f} {z:.1f}", ha="left", va="bottom", **small)
    # A scale bar in axes fractions: 10 mm when the view is tight, 20 mm otherwise.
    bar_mm = 10.0 if row.width_mm < 80.0 else 20.0
    fraction = bar_mm / row.width_mm
    ax.plot(
        [0.97 - fraction, 0.97],
        [0.05, 0.05],
        color="white",
        linewidth=2,
        transform=ax.transAxes,
        solid_capstyle="butt",
    )
    ax.text(0.97, 0.07, f"{bar_mm:.0f} mm", ha="right", va="bottom", **small)


def _colorbar(figure, axes, window, label):
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    mappable = ScalarMappable(norm=Normalize(*window), cmap=FIELD_COLORMAP)
    bar = figure.colorbar(
        mappable,
        ax=axes.ravel().tolist(),
        fraction=0.02,
        pad=0.01,
        location="right",
    )
    bar.set_label(label or "field", fontsize=7)
    bar.ax.tick_params(labelsize=6)


# --------------------------------------------------------------------------- #
# The Tetravox renderer, and the request the container leaves for it
# --------------------------------------------------------------------------- #


def tetravox_executable() -> str | None:
    """The Tetravox binary on this host, or ``None`` (the container's answer)."""
    configured = os.environ.get(TETRAVOX_ENV, "").strip()
    if configured:
        return configured if Path(configured).is_file() else None
    for candidate in (
        Path.home() / "Applications/Tetravox.app/Contents/MacOS/Tetravox",
        Path("/Applications/Tetravox.app/Contents/MacOS/Tetravox"),
    ):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("tetravox")


def build_job(request: dict) -> dict:
    """The Tetravox ``--job`` document for a single-row plate request.

    The ROI is listed **twice** in ``scene.files`` and patched by index: a
    ``VolumeLayer`` has one opacity and one ``labelMode``, so a 40 % fill under an
    opaque outline needs two layers of the same file (Tetravox 0.5.2; see
    ``docs/dev/notes/tetravox-integration-options.md`` §5).  A field, when there
    is one, goes *between* them so the outline stays on top — layer order is the
    order of ``scene.files`` and nothing reorders it.
    """
    row = request["rows"][0]
    mask_path = request["mask"]
    colors = {str(k): v for k, v in (request.get("region_colors") or {}).items()}
    visible = sorted(int(k) for k in colors) or None
    files = [request["background"], mask_path]
    field_index = None
    if request.get("field"):
        files.append(request["field"])
        field_index = len(files) - 1
    files.append(mask_path)
    outline_index = len(files) - 1

    actions: list[dict] = [
        {
            "type": "set",
            "layout": "2x2",
            "cursor": [round(v, 3) for v in row["cursor_ras"]],
            "annotations": {
                "colorbar": True,
                "orientationLabels": True,
                "crosshair": True,
                "scaleBar": True,
                "cornerInfo": True,
            },
        },
        {
            "type": "set",
            "layer": 0,
            "patch": {
                "colormap": "gray",
                "opacity": 1.0,
                "visible": True,
                # Explicit, because a T1's max is a scalp-fat voxel: an auto
                # window off the maximum washes the brain out to flat white.
                "scale": {
                    "kind": "linear",
                    "lo": 0.0,
                    "hi": request.get("background_window", [0.0, 1.0])[1],
                },
                "showColorbar": False,
            },
        },
        {
            "type": "set",
            "layer": 1,
            "patch": {
                "visible": True,
                "opacity": 0.4,
                "labelMode": "fill",
                "interpolation": "nearest",
                # The plate's own palette, not the file's LUT: a binary mask's
                # value 1 is blue in every LUT, and a two-region plate must show
                # two colours whatever the atlas called them.
                "labelColors": {k: v for k, v in colors.items()},
                "visibleLabels": visible,
                "showColorbar": False,
                "showIn3D": False,
            },
        },
    ]
    if field_index is not None:
        lo, hi = request["field_window"]
        actions.append(
            {
                "type": "set",
                "layer": field_index,
                "patch": {
                    "colormap": FIELD_COLORMAP,
                    "opacity": 0.85,
                    "visible": True,
                    "interpolation": "linear",
                    "scale": {"kind": "linear", "lo": lo, "hi": hi},
                    # `clamp` (the default) paints every voxel below `lo` in the
                    # colormap's bottom colour, which is a black wash over the T1.
                    "threshold": {"lo": lo, "hi": hi, "softEdge": 0.0, "mode": "hide"},
                    "showColorbar": True,
                },
            }
        )
    actions.append(
        {
            "type": "set",
            "layer": outline_index,
            "patch": {
                "visible": True,
                "opacity": 1.0,
                "labelMode": "outline",
                "outlineWidthPx": 2,
                "interpolation": "nearest",
                "labelColors": {k: v for k, v in colors.items()},
                "visibleLabels": visible,
                "showColorbar": False,
                "showIn3D": False,
            },
        }
    )
    for _, plane in PANELS:
        actions.append(
            {"type": "set", "view": plane, "mmPerPx": round(row["mm_per_px"], 4)}
        )
    actions.append(
        {
            "type": "screenshot",
            "out": request["png"],
            "view": "figure",
            "width": PANEL_PX,
            "dpi": 300,
            "background": "white",
            "include": {
                "colorbar": request.get("field") is not None,
                "orientationLabels": True,
                "crosshair": True,
                "scaleBar": True,
                "cornerInfo": True,
            },
            "figure": {
                "panels": ["axial", "coronal", "sagittal"],
                "columns": 3,
                "gutterMm": 3,
                "labels": "upper",
                "background": "white",
            },
        }
    )
    actions.append({"type": "save-scene", "out": request["scene"]})
    return {
        "version": 1,
        "scene": {"files": files, "preset": "plain"},
        "window": {"width": 1600, "height": 1200},
        "actions": actions,
    }


def run_tetravox(request_path, executable=None, timeout: float = 180.0) -> bool:
    """Render one ``*.plate-request.json`` with Tetravox, overwriting its PNG.

    Returns ``True`` when Tetravox wrote the plate.  Every failure is ``False``
    and one log line: the matplotlib plate already on disk stays.
    """
    executable = executable or tetravox_executable()
    if not executable:
        return False
    request_path = Path(request_path)
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("plate request %s unreadable: %s", request_path, exc)
        return False
    if not request.get("tetravox", True):
        logger.info(
            "plate request %s is matplotlib-only: %s",
            request_path.name,
            request.get("tetravox_reason", ""),
        )
        return False
    out_dir = request_path.parent
    job_path = out_dir / (request_path.name[: -len(REQUEST_SUFFIX)] + JOB_SUFFIX)
    if not job_path.is_file():
        _write_json(job_path, build_job(request))
    try:
        completed = subprocess.run(
            [executable, "--job", str(job_path), "--out", str(out_dir), "--quiet"],
            capture_output=True,
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tetravox could not be run for %s: %s", request_path.name, exc)
        return False
    if completed.returncode != 0 or not (out_dir / request["png"]).is_file():
        logger.warning(
            "Tetravox did not render %s (exit %s); the matplotlib plate stands",
            request["png"],
            completed.returncode,
        )
        return False
    return True


# --------------------------------------------------------------------------- #
# The one entry point
# --------------------------------------------------------------------------- #


def write_roi_plate(
    *,
    mask_path: str,
    m2m: str,
    out_dir: str,
    field_path: str | None = None,
    names=None,
    spheres=None,
    title: str = "",
    extra: dict | None = None,
    stem: str | None = None,
) -> dict | None:
    """Write the ROI plate, its JSON sidecar, its scene twin and its request.

    Args:
        mask_path: a subject-space NIfTI, already transformed and island-cleaned
            by the caller — this function never re-derives the ROI, so the plate
            cannot disagree with the run about which voxels it is about.
        m2m: the subject's ``m2m_`` directory (its ``T1.nii.gz`` is the anatomy).
        out_dir: where the plate goes.
        field_path: when given, the plate is the **field** plate — the field
            masked to the ROI in inferno with a colour bar, the outline kept.
        names: region names, as :func:`plan_framing` takes them.
        spheres: ``[(centre_ras, radius_mm), ...]`` for a spherical ROI.
        title: what to call this ROI in the terminal line.
        extra: extra keys merged into the sidecar (``gm_overlap`` and friends).
        stem: output basename, defaulting to ``roi_plate`` / ``roi_field_plate``.

    Returns:
        The sidecar dict, or ``None`` when the plate was switched off or could
        not be written.  An **empty** mask returns the sidecar (with
        ``rule == "empty"`` and no ``image``), because that is the failure the
        user most needs to see.
    """
    if not enabled():
        return None
    stem = stem or (Path(FIELD_PLATE_PNG).stem if field_path else Path(PLATE_PNG).stem)
    destination = Path(out_dir)
    try:
        import nibabel as nib
        import numpy as np
        from nibabel.processing import resample_from_to

        mask_image = nib.as_closest_canonical(nib.load(str(mask_path)))
        mask = np.squeeze(np.asarray(mask_image.dataobj))
        affine = mask_image.affine
        # With no names, the sole region is called after the ROI rather than
        # "region 9" (its connected-component index, which means nothing).
        plan = plan_framing(
            mask,
            affine,
            names=names or [title or Path(mask_path).stem],
            spheres=spheres,
        )

        sidecar: dict = {
            "roi": title or Path(mask_path).name,
            "mask": str(mask_path),
            "cursor_rule": plan.rule,
            "cursor_ras": [round(v, 2) for v in plan.cursor_ras],
            "voxels": int(np.count_nonzero(mask)),
            "voxels_by_region": {r.name: r.voxels for r in plan.regions},
            "island_voxels": plan.island_voxels,
            "bounding_box_ras": (
                [
                    [
                        round(min(r.bbox_min_ras[i] for r in plan.regions), 2)
                        for i in range(3)
                    ],
                    [
                        round(max(r.bbox_max_ras[i] for r in plan.regions), 2)
                        for i in range(3)
                    ],
                ]
                if plan.regions
                else None
            ),
            "zoom_mm_per_px": (round(plan.rows[0].mm_per_px, 4) if plan.rows else None),
            "framing": plan.as_dict(),
            "renderer": "matplotlib",
            "image": None,
            "scene": None,
        }
        if extra:
            sidecar.update(extra)

        destination.mkdir(parents=True, exist_ok=True)
        if plan.empty:
            # A real failure, not a missing picture: no plate, a JSON that says
            # why, and one line the person watching the terminal will see.
            sidecar["error"] = plan.reason
            _write_json(destination / f"{stem}.json", sidecar)
            _announce(
                destination / f"{stem}.json", "json", f"ROI plate — {sidecar['roi']}"
            )
            print(
                f"ROI {sidecar['roi']}: the mask is EMPTY after transform — "
                f"no plate, see {stem}.json",
                flush=True,
            )
            return sidecar

        background = None
        background_window = None
        t1 = Path(m2m) / "T1.nii.gz"
        if t1.is_file():
            background = np.squeeze(
                np.asarray(
                    nib.as_closest_canonical(
                        resample_from_to(
                            nib.load(str(t1)), (mask.shape, affine), order=1
                        )
                    ).dataobj,
                    dtype=np.float32,
                )
            )
            if background.ndim != 3:
                background = None
            else:
                finite = background[np.isfinite(background) & (background > 0)]
                background_window = (
                    (0.0, float(np.percentile(finite, 99.9))) if finite.size else None
                )

        # The mask the renderer draws carries one value per region, so distinct
        # regions get distinct fills from one array.
        drawn = plan.region_map
        # The region map goes to disk as the plate's own ROI volume, and it is
        # what Tetravox loads. The plan's region values index *this* array, not
        # the source file's: a binary mask's components are numbered here, so
        # pointing Tetravox at the original would colour and reveal labels that
        # do not exist in it -- which is exactly how the first single-region
        # plate came out with no ROI on it at all.
        destination.mkdir(parents=True, exist_ok=True)
        drawn_path = destination / f"{stem}_roi.nii"
        nib.save(nib.Nifti1Image(drawn.astype(np.int16), affine), str(drawn_path))

        field = None
        field_for_tetravox = None
        field_window = None
        if field_path:
            field_image = nib.as_closest_canonical(
                resample_from_to(
                    nib.load(str(field_path)), (mask.shape, affine), order=1
                )
            )
            field = np.squeeze(np.asarray(field_image.dataobj, dtype=np.float32))
            inside = field[(drawn > 0) & np.isfinite(field)]
            if inside.size:
                hi = float(np.percentile(inside, 99.9))
                field_window = (FIELD_FLOOR_FRACTION * hi, hi)
                sidecar["field"] = {
                    "file": str(field_path),
                    "max_in_roi": round(float(np.nanmax(inside)), 6),
                    "p99_9_in_roi": round(hi, 6),
                    "threshold_floor": round(field_window[0], 6),
                    "voxels_in_roi": int(inside.size),
                    "colormap": FIELD_COLORMAP,
                    "unit": FIELD_UNIT,
                }
                # Tetravox cannot mask a volume by a label volume (the job API's
                # `IsolateSpec.labelVolume` needs a dataset id a job never sees),
                # so the field it draws is the field *already* masked here --
                # which is also the field the matplotlib plate draws, so the two
                # renderers cannot disagree about what "in the ROI" means.
                masked = np.where(drawn > 0, field, 0.0).astype(np.float32)
                field_for_tetravox = destination / f"{stem}_field-in-roi.nii"
                destination.mkdir(parents=True, exist_ok=True)
                nib.save(nib.Nifti1Image(masked, affine), str(field_for_tetravox))
            else:
                field = None

        png = destination / f"{stem}.png"
        _render_matplotlib(
            destination=png,
            mask=drawn,
            affine=affine,
            background=background,
            plan=plan,
            field=field,
            field_window=field_window,
            # The colour bar carries the unit, not the file name: a TI field's
            # NIfTI name is 40 characters of provenance and says nothing a
            # reader of the bar needs (Tetravox 0.5.2 has the same problem --
            # see docs/dev/notes/tetravox-integration-options.md §5).
            field_label=FIELD_UNIT if field_path else "",
        )
        sidecar["image"] = png.name

        request = _request(
            plan=plan,
            mask_path=str(drawn_path),
            background=str(t1) if t1.is_file() else None,
            background_window=background_window,
            field_path=str(field_for_tetravox) if field_for_tetravox else None,
            field_window=field_window,
            stem=stem,
        )
        request_path = destination / f"{stem}{REQUEST_SUFFIX}"
        _write_json(request_path, request)
        if request["tetravox"]:
            # The job document is written here, once, whoever ends up running
            # it: the container cannot run Tetravox, and Electron rewriting the
            # document itself would be a second implementation of the plate's
            # look that could drift from this one. It only rewrites the paths.
            _write_json(destination / f"{stem}{JOB_SUFFIX}", build_job(request))
        _announce(request_path, "json", f"ROI plate render request — {sidecar['roi']}")
        if request.get("tetravox") and run_tetravox(request_path):
            sidecar["renderer"] = "tetravox"
            sidecar["scene"] = f"{stem}{SCENE_SUFFIX}"

        _write_json(destination / f"{stem}.json", sidecar)
        _announce(png, "png", f"ROI plate — {sidecar['roi']}")
        _announce(
            destination / f"{stem}.json", "json", f"ROI plate values — {sidecar['roi']}"
        )
        if sidecar["scene"]:
            _announce(destination / sidecar["scene"], "json", "ROI plate scene")

        x, y, z = sidecar["cursor_ras"]
        overlap = extra.get("gm_overlap") if extra else None
        overlap_text = (
            "GM overlap unknown"
            if overlap is None
            else f"GM overlap {overlap * 100:.0f} %"
        )
        print(
            f"ROI {sidecar['roi']}: {sidecar['voxels']} voxels, "
            f"cursor ({x:g}, {y:g}, {z:g}) mm [{plan.rule}], {overlap_text} "
            f"-- see {png.name}",
            flush=True,
        )
        return sidecar
    except Exception as exc:  # noqa: BLE001 - a picture never fails a job
        logger.warning("ROI plate could not be written: %s", exc)
        return None


def _rgba(hex_color):
    """``"#4caf50"`` as Tetravox's 0..1 RGBA."""
    value = hex_color.lstrip("#")
    return [int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4)] + [1.0]


def _request(
    *,
    plan,
    mask_path,
    background,
    background_window,
    field_path,
    field_window,
    stem,
) -> dict:
    """The host-side render request Electron picks up when the job finishes."""
    request = {
        "version": 1,
        "png": f"{stem}.png",
        "scene": f"{stem}{SCENE_SUFFIX}",
        "mask": mask_path,
        "background": background,
        "field": field_path,
        "field_window": [round(v, 6) for v in field_window] if field_window else None,
        "background_window": (
            [round(v, 3) for v in background_window] if background_window else None
        ),
        "region_colors": {r.value: _rgba(r.color) for r in plan.regions},
        "rows": [row.as_dict() for row in plan.rows],
        "rule": plan.rule,
        "tetravox": True,
    }
    if background is None or background_window is None:
        request["tetravox"] = False
        request["tetravox_reason"] = "no T1.nii.gz to draw the ROI on"
    elif len(plan.rows) > 1:
        # Tetravox 0.5.2's `figure` gives every panel the same cursor, so a plate
        # whose rows each have their own cursor cannot be one capture.
        request["tetravox"] = False
        request["tetravox_reason"] = (
            "a per-region plate needs one cursor per row; `figure` has one cursor "
            "for the whole capture (see docs/dev/notes/tetravox-integration-options.md §5)"
        )
    return request


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def _announce(path: Path, kind: str, label: str) -> None:
    try:
        from tit.jobs.events import emit_artifact

        emit_artifact(str(path), kind, label)
    except Exception as exc:  # noqa: BLE001 - outside a job there is no sink
        logger.debug("ROI plate artifact not announced: %s", exc)
