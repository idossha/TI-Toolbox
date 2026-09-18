"""The one scene an analysis leaves behind: the field masked to its ROI.

An analysis folder is data plus **exactly one** ``scene.tetravox.json``::

    results.csv, analysis.json      the numbers
    roi_overlay.nii.gz              voxel: the field, zero outside the ROI
    roi_overlay.msh (+ .msh.opt)    mesh:  the surface with ``<field>_ROI`` node data
    scene.tetravox.json             this: the overlay over the anatomy, cursor on the ROI

The scene is a few kilobytes and **points at** the overlay the analysis wrote
anyway -- it copies nothing and rasterises nothing.  The overlay is the dataset
*because* it is the analysis's own product: a picture drawn from a different
file than the table came from would be a picture that could contradict it.

Voxel: the subject's T1 under the overlay, ``inferno`` scaled from the field's
display floor to its p99.9 inside the ROI (never the max: the max is one voxel),
zeros hidden so nothing but the ROI is painted.  Mesh: the whole cortex once,
translucent and unpickable, and once more coloured by ``<field>_ROI`` with every
node outside the ROI (exactly ``0``) hidden -- so what shows is the ROI's field
inside a see-through cortex, which ``transparency: peel`` renders in order.  A
bare ``.msh`` open cannot carry that intent (Tetravox ignores ``View[n].Visible``
on open), which is why it travels in the scene.

Framing reuses :mod:`tit.figures.roi_plate` -- the cursor lands on the ROI's
centroid, snapped into it, and the zoom fills the panel -- and the file is
assembled by the same function the ROI scene uses, so both look alike.  Like
every artefact a person looks at, this never fails a job: a failure is one log
line.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

#: The one scene per analysis.
SCENE_NAME = "scene.tetravox.json"

#: Colormap for the field inside the ROI: its dark-to-warm ramp separates the
#: field from the grey T1 and from the translucent cortex alike.
FIELD_COLORMAP = "inferno"

#: The scale's floor as a fraction of the field's p99.9 inside the ROI.
FIELD_FLOOR_FRACTION = 0.20

#: What a field's colour bar is labelled with.
FIELD_UNIT = "V/m"

#: ``threshold.lo`` that hides exactly the zeros an overlay has outside the ROI:
#: a field the analyzer reports is never this small, and ``0`` is not "below 0".
ZERO_EPSILON = 1e-6


def _hide_below(lo: float, hi: float | None = None) -> dict:
    """A ``hide`` threshold: nothing below *lo* is drawn.

    ``clamp`` (the default) would paint everything below *lo* in the colormap's
    bottom colour -- a black wash over the anatomy.  A **mesh** layer needs a
    finite *hi* (Tetravox 0.5.2 floors the ramp width at 1e-6 of ``hi - lo``,
    so an open ``hi`` -- 3.4e38 -- makes the ramp swallow every value and the
    layer vanishes); a volume layer is fine with ``None``.
    """
    return {"lo": lo, "hi": hi, "symmetric": False, "mode": "hide", "softEdge": 0.0}


def _window(roi_values) -> tuple[float, float]:
    """``(floor, p99.9)`` of the field inside the ROI, the colour bar's range."""
    import numpy as np

    values = np.asarray(roi_values, dtype=float)
    values = values[np.isfinite(values) & (values > 0)]
    hi = float(np.percentile(values, 99.9)) if values.size else 1.0
    return round(FIELD_FLOOR_FRACTION * hi, 6), round(hi, 6)


def write_voxel_scene(
    *,
    out_dir: str,
    anatomy: str,
    overlay: str,
    roi_mask,
    affine,
    roi_values,
    field_name: str,
    region_name: str,
    meta: dict,
) -> str | None:
    """The scene for a voxel analysis: T1 plus ``roi_overlay.nii.gz``.

    ``roi_mask``/``affine``/``roi_values`` are the analysis's own, so the cursor
    is placed on the voxels the table was computed from and the window is read
    off the same numbers.
    """
    if not _enabled():
        return None
    try:
        import numpy as np

        from tit.figures.roi_plate import (
            _dataset,
            _volume_bounds,
            _volume_layer,
            anatomy_layer,
            assemble_scene,
            plan_framing,
        )

        mask = np.asarray(roi_mask, dtype=bool)
        plan = plan_framing(mask.astype(np.int16), affine, names={1: region_name})
        if plan.empty:
            logger.warning("analysis scene not written: %s", plan.reason)
            return None
        roi_values = np.asarray(roi_values, dtype=float)
        lo, hi = _window(roi_values)
        datasets = [
            _dataset(0, anatomy, out_dir, "volume"),
            _dataset(1, overlay, out_dir, "volume"),
        ]
        layers = [
            anatomy_layer(anatomy),
            _volume_layer(
                1,
                "ds1",
                os.path.basename(overlay),
                colormap=FIELD_COLORMAP,
                opacity=0.85,
                scale={"kind": "linear", "lo": lo, "hi": hi},
                threshold=_hide_below(ZERO_EPSILON),
                showColorbar=True,
            ),
        ]
        row = plan.rows[0]
        scene = assemble_scene(
            datasets=datasets,
            layers=layers,
            cursor=[float(v) for v in row.cursor_ras],
            mm_per_px=float(row.mm_per_px),
            bounds=_volume_bounds(anatomy),
            meta=_meta(meta, plan, field_name, roi_values, lo, hi, "voxels"),
            layout="2x2",
        )
        return _write(out_dir, scene, f"{field_name} in {region_name}")
    except Exception as exc:  # noqa: BLE001 - a scene never fails a job
        logger.warning("analysis scene could not be written: %s", exc)
        return None


def write_mesh_scene(
    *,
    out_dir: str,
    mesh: str,
    roi_coords,
    node_coords,
    roi_values,
    field_name: str,
    region_name: str,
    meta: dict,
    normal_max: float | None = None,
) -> str | None:
    """The scene for a mesh analysis: ``roi_overlay.msh`` twice over.

    ``roi_coords`` are the ROI's node coordinates (the cursor), ``node_coords``
    every node's (the camera fit), ``roi_values`` the field at the ROI's nodes.
    ``normal_max`` (the ROI's largest positive ``TI_normal``) adds a hidden
    third layer for the ``TI_normal_ROI`` node data the overlay carries.
    """
    if not _enabled():
        return None
    try:
        import numpy as np

        from tit.figures.roi_plate import _dataset, assemble_scene, plan_surface

        plan = plan_surface([np.asarray(roi_coords, dtype=float)], names=[region_name])
        if plan.empty:
            logger.warning("analysis scene not written: %s", plan.reason)
            return None
        roi_values = np.asarray(roi_values, dtype=float)
        # The mesh carries only the ROI, so its bar runs from 0 to the ROI's max.
        lo, hi = 0.0, round(float(np.max(roi_values)), 6)
        dataset = _dataset(0, mesh, out_dir, "mesh")
        opt = f"{mesh}.opt"
        if os.path.isfile(opt):
            dataset["sidecars"] = {"opt": {"path": os.path.basename(opt)}}
        name = os.path.basename(mesh)
        layers = [
            # The whole cortex, see-through and not in the way of a click.
            _mesh_layer(0, name, opacity=0.25, pickable=False, colorMode="solid"),
            # The ROI's field on top; every node outside the ROI is 0 and hidden.
            _mesh_layer(
                1,
                f"{field_name}_ROI",
                colorMode="field",
                field={
                    "source": "node",
                    "name": f"{field_name}_ROI",
                    "component": "mag",
                },
                scale={"kind": "linear", "lo": lo, "hi": hi},
                # Twice the max: any finite bound above every value, with the
                # peak node itself still inside the ramp.
                threshold=_hide_below(ZERO_EPSILON, round(2.0 * hi, 6)),
                showColorbar=True,
            ),
        ]
        if normal_max is not None and normal_max > 0:
            layers.append(
                _mesh_layer(
                    2,
                    "TI_normal_ROI",
                    visible=False,
                    colorMode="field",
                    field={
                        "source": "node",
                        "name": "TI_normal_ROI",
                        "component": "mag",
                    },
                    scale={
                        "kind": "linear",
                        "lo": 0.0,
                        "hi": round(float(normal_max), 6),
                    },
                    threshold=_hide_below(
                        ZERO_EPSILON, round(2.0 * float(normal_max), 6)
                    ),
                )
            )
        nodes = np.asarray(node_coords, dtype=float)
        row = plan.rows[0]
        scene = assemble_scene(
            datasets=[dataset],
            layers=layers,
            cursor=[float(v) for v in row.cursor_ras],
            mm_per_px=float(row.mm_per_px),
            bounds=(
                [float(v) for v in nodes.min(axis=0)],
                [float(v) for v in nodes.max(axis=0)],
            ),
            meta=_meta(meta, plan, field_name, roi_values, lo, hi, "vertices"),
            layout="1+3",
            transparency="peel",
        )
        return _write(out_dir, scene, f"{field_name} in {region_name}")
    except Exception as exc:  # noqa: BLE001 - a scene never fails a job
        logger.warning("analysis scene could not be written: %s", exc)
        return None


def _mesh_layer(index: int, name: str, **rest) -> dict:
    """A ``MeshLayer`` (Tetravox section 4.4) over ``ds0`` with *rest* on top.

    Two layers share the one dataset and are told apart by ``name``, which is
    how Tetravox matches a saved layer to a loaded file.
    """
    from tit.figures.roi_plate import _base_layer

    defaults = {
        "kind": "mesh",
        "colorMode": "solid",
        "solidColor": [0.78, 0.78, 0.8, 1.0],
        "colormap": FIELD_COLORMAP,
        "scale": {"kind": "linear", "lo": 0.0, "hi": 1.0},
        "threshold": {
            "lo": None,
            "hi": None,
            "symmetric": False,
            "mode": "clamp",
            "softEdge": 0.0,
        },
        "tagStyle": {},
        "edges": {"surface": False, "caps": False},
        "edgeColor": [0.0, 0.0, 0.0, 1.0],
        "edgeWidthPx": 1.0,
        "flatShading": False,
        # A central surface is open, so both faces are drawn.
        "faceMode": "both",
        "clip": {"planes": [], "caps": True, "capColorMode": "inherit"},
        "contoursIn2D": True,
        "contourWidthPx": 1.5,
        "fillIn2D": False,
    }
    defaults.update(rest)
    return _base_layer(index, "ds0", name, **defaults)


def _meta(
    meta: dict, plan, field_name: str, values, lo: float, hi: float, unit: str
) -> dict:
    import numpy as np

    values = np.asarray(values, dtype=float)
    positive = values[values > 0]
    out = dict(meta)
    out.update(
        {
            "voxels": int(positive.size),
            "unit": unit,
            "cursor_ras": [round(float(v), 2) for v in plan.cursor_ras],
            "rule": plan.rule,
            "framing": plan.as_dict(),
            "field": {
                "name": field_name,
                "unit": FIELD_UNIT,
                "max_in_roi": round(float(positive.max()), 6) if positive.size else 0.0,
                "scale": [lo, hi],
            },
        }
    )
    return out


def _enabled() -> bool:
    from tit.figures import roi_plate

    return roi_plate.enabled()


def _write(out_dir: str, scene: dict, title: str) -> str:
    from tit.figures.roi_plate import _announce

    path = Path(out_dir) / SCENE_NAME
    path.write_text(json.dumps(scene, indent=1) + "\n", encoding="utf-8")
    _announce(path, "json", f"Analysis scene — {title}")
    x, y, z = (round(v, 2) for v in scene["cursor"])
    print(
        f"Scene {title}: cursor ({x:g}, {y:g}, {z:g}) mm -- see {SCENE_NAME}",
        flush=True,
    )
    return str(path)
