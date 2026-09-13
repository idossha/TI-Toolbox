"""Declarative view specifications for the Freeview/Gmsh launchers.

``build_view(kind, ...)`` reproduces the layer-building logic of the former
PyQt NIfTI viewer tab (single-subject, group and overlay layer stacks) as a
pure function returning a JSON-able
``ViewSpec`` (``contracts/openapi.yaml`` ``#/components/schemas/ViewSpec``)
instead of driving Qt widgets and a subprocess directly. ``to_freeview_args``
reproduces the argv grammar of ``launch_freeview_with_files``
(``nifti_viewer_tab.py:1124-1140``).

Six audit bugs from TODO.md §2.6 are fixed here (each pinned by a test in
``tests/test_viewspec.py``):

1. **HF glob never matching.** The Qt tab globs
   ``high_Frequency/niftis/*_scalar_magnE.nii.gz`` for the high-frequency
   envelope overlay, but every real file is named
   ``..._scalar_subject_magnE.nii.gz`` or ``..._scalar_MNI_MNI_magnE.nii.gz``
   (verified against ``sub-ernie`` in Dataset 000) — the un-suffixed pattern
   matches nothing, ever. Fixed by globbing ``*_scalar_*magnE.nii.gz`` and
   filtering by the same ``_MNI`` substring rule used for TI_max niftis.
2. **``labeling_LUT.txt`` ignored.** The Qt tab sends the subject's
   ``labeling.nii.gz`` atlas overlay with ``colormap=lut`` and no LUT file at
   all, so regions render with Freeview's arbitrary default palette instead
   of the SimNIBS tissue colours. Fixed via
   ``VoxelAtlasManager.find_labeling_lut()``.
3. **``*_LUT.txt`` not found in group/MNI mode.** The bundled MNI atlases'
   sidecars are named ``<stem>_LUT.txt`` (e.g.
   ``CIT168_labeling_MNI152NLin2009cAsym_LUT.txt``,
   ``resources/atlas/``), but the Qt tab's candidate list only tries
   ``<stem>.txt`` / ``<stem>_labels.txt`` / a hyphen-split guess — never
   ``_LUT.txt``, and never the ``massp2021_labels.txt`` special case for the
   MASSP atlas (whose sidecar does not share its stem at all). Fixed by
   trying ``_LUT.txt`` first, matching ``roi_picker._find_volume_lut``.
4. **MNI paths hard-coded to the container.** ``MNI_ATLAS_DIR`` is the
   absolute container path ``/ti-toolbox/resources/atlas``; outside the
   container (host-run tests, ``--dump-openapi``) it silently finds nothing.
   Fixed with the same repo-relative fallback ``roi_picker._mni_atlas_dir()``
   uses.
5. **Absolute thresholds dropped when percentile mode is off.**
   ``launch_freeview_with_files`` only emits ``heatscale=...`` inside the
   ``if spec.get("percentile")`` branch, so a user-set *absolute* min/max
   threshold is silently ignored whenever percentile mode is unchecked.
   ``to_freeview_args`` here emits ``heatscale`` whenever a layer carries
   ``cal_min``/``cal_max``, independent of any percentile concept (which the
   ``ViewLayer`` schema does not even model).
6. **Single-subject MNI space has no usable atlas.** In single-subject mode
   the atlas dropdown only ever lists FreeSurfer *subject*-space atlases
   (``detect_freesurfer_atlases``), even after the space combo is switched to
   MNI — so the one dropdown atlas silently doesn't overlay the MNI template
   correctly. Fixed: ``kind="subject"`` with ``space="mni"`` lists the MNI
   atlases (with their own LUT) and the subject's ``T1_<id>_MNI.nii.gz``,
   exactly mirroring the subject-space branch.

Percentile thresholding (v1, ``pages/viewer/PARITY.md`` gap #3): a heat-colormap
layer built here (TI_max, magnE) carries a ``percentile`` window (``{"lo": 95,
"hi": 99.9}``, the Qt tab's own default) instead of a bare ``cal_min``/
``cal_max`` of ``None``. ``resolve_percentiles`` fills in the concrete
absolute values by reading the NIfTI and computing ``numpy.percentile`` over
its non-zero voxels — run once by ``build_view`` (``GET /api/view/{kind}``)
and again by ``POST /api/viewers/freeview`` on whatever ``ViewSpec`` the
client submits (a user-edited spec may still carry an unresolved percentile
window). A layer whose file cannot be read, or whose voxels are all zero,
simply keeps ``cal_min``/``cal_max`` as ``None`` — the resulting Freeview
layer just renders without a ``heatscale`` arg, exactly like today.

See Also
--------
tit.catalog : Discovery routines this module's helpers are shared with
    (``mni_resources_dir``).
"""

from __future__ import annotations

import copy
import glob
import hashlib
import json
import math
import os
import re
import secrets
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from tit.atlas import DEFAULT_MNI_ATLAS, MNI_ATLAS_DIR, MNI_TEMPLATE, VoxelAtlasManager
from tit.catalog import (
    VIEW_ATTACHMENT_KINDS,
    classify_view_file,
    surface_attachments,
)
from tit.atlas.constants import mni_resources_dir
from tit.paths import get_path_manager, is_within

_VIEW_KINDS = ("subject", "simulation", "analysis", "group", "custom")


def _mni_atlas_lut(atlas_path: str) -> str | None:
    """LUT sidecar for a bundled MNI atlas file (bug 3)."""
    directory = os.path.dirname(atlas_path)
    stem = os.path.basename(atlas_path)
    for ext in (".nii.gz", ".nii"):
        if stem.endswith(ext):
            stem = stem[: -len(ext)]
            break
    candidates = [
        os.path.join(directory, f"{stem}_LUT.txt"),
        os.path.join(directory, f"{stem}_labels.txt"),
        os.path.join(directory, f"{stem}.txt"),
    ]
    if stem.lower().startswith("massp"):
        candidates.append(os.path.join(directory, "massp2021_labels.txt"))
    return next((c for c in candidates if os.path.isfile(c)), None)


def _freesurfer_color_lut() -> str | None:
    candidate = os.path.join(mni_resources_dir(), "FreeSurferColorLUT.txt")
    return candidate if os.path.isfile(candidate) else None


def _default_mni_atlas_path(requested: str | None = None) -> str | None:
    """The bundled MNI atlas file to overlay.

    *requested* is the optional ``atlas`` query parameter (R5,
    ``docs/dev/HISTORY.md § 2026-09-05``): the **basename** of one of the
    bundled files, as ``GET /api/catalog/atlases?space=mni`` reports it. An
    id that matches nothing bundled falls through to the default rather
    than failing the whole view -- a stale bookmark or a project moved
    between images then still renders the anatomy, which is the useful
    half, instead of a 404 with no picture at all.
    """
    found = VoxelAtlasManager.detect_mni_atlases(mni_resources_dir())
    if not found:
        return None
    if requested:
        for path in found:
            if os.path.basename(path) == requested:
                return path
    for path in found:
        if os.path.basename(path) == DEFAULT_MNI_ATLAS:
            return path
    return found[0]


_DEFAULT_PERCENTILE = {"lo": 95.0, "hi": 99.9}


def _layer(
    path: str,
    *,
    kind: str = "volume",
    colormap: str = "grayscale",
    opacity: float = 1.0,
    visible: bool = True,
    cal_min: float | None = None,
    cal_max: float | None = None,
    lut: str | None = None,
    percentile: dict[str, float] | None = None,
) -> dict[str, Any]:
    layer: dict[str, Any] = {
        "path": path,
        "kind": kind,
        "colormap": colormap,
        "opacity": opacity,
        "visible": visible,
        "cal_min": cal_min,
        "cal_max": cal_max,
        "lut": lut,
    }
    if percentile is not None:
        layer["percentile"] = percentile
    return layer


def _subject_t1_layer(pm, sid: str, space: str) -> dict[str, Any] | None:
    name = f"T1_{sid}_MNI.nii.gz" if space == "mni" else "T1.nii.gz"
    path = os.path.join(pm.m2m(sid), name)
    return _layer(path) if os.path.isfile(path) else None


def _subject_atlas_layer(
    pm, sid: str, space: str, requested: str | None = None
) -> dict[str, Any] | None:
    """The atlas overlay for single-subject mode (bugs 2 and 6).

    *requested* is the optional ``atlas`` parameter. It names an id from
    ``GET /api/catalog/atlases`` for this subject and space -- a display
    name like ``"DK40"`` or ``"aparc.DKTatlas+aseg"`` in subject space, a
    bundled file's basename in MNI. ``None`` (the default, and every caller
    before R5) keeps the server's own choice exactly as it was:
    ``labeling.nii.gz`` when the head model has one, else the first atlas
    the voxel manager lists. An id that matches nothing available falls back
    to that same choice rather than dropping the overlay -- an atlas the
    subject does not have is a stale selection, not a reason to render a
    naked T1 with no explanation.
    """
    if space == "mni":
        atlas_path = _default_mni_atlas_path(requested)
        if not atlas_path:
            return None
        return _layer(
            atlas_path,
            colormap="lut",
            opacity=0.7,
            lut=_mni_atlas_lut(atlas_path),
        )

    seg_dir = os.path.join(pm.m2m(sid), "segmentation")
    mgr = VoxelAtlasManager(
        fastsurfer_mri_dir=pm.fastsurfer_mri(sid),
        freesurfer_mri_dir=pm.freesurfer_mri(sid),
        seg_dir=seg_dir,
        masks_dir=pm.masks(sid),
    )
    if requested:
        # The catalog's ids for subject space are the voxel manager's display
        # names; a basename is accepted too so one id grammar works for both
        # spaces from the client's point of view.
        for display_name, path in mgr.list_atlases():
            if requested in (display_name, os.path.basename(path)):
                return _layer(
                    path, colormap="lut", opacity=0.7, lut=_freesurfer_color_lut()
                )

    labeling = os.path.join(seg_dir, "labeling.nii.gz")
    if os.path.isfile(labeling):
        return _layer(
            labeling,
            colormap="lut",
            opacity=0.7,
            lut=VoxelAtlasManager(seg_dir=seg_dir).find_labeling_lut(),
        )

    atlases = mgr.list_atlases()
    if not atlases:
        return None
    _, path = atlases[0]
    return _layer(path, colormap="lut", opacity=0.7, lut=_freesurfer_color_lut())


_MODE_DIRS = ("mTI", "TI")


def _mode_niftis_dir(sim_dir: str) -> str | None:
    for mode in _MODE_DIRS:
        candidate = os.path.join(sim_dir, mode, "niftis")
        if os.path.isdir(candidate):
            return candidate
    return None


def _ti_max_layers(sim_dir: str, space: str) -> list[dict[str, Any]]:
    niftis_dir = _mode_niftis_dir(sim_dir)
    if niftis_dir is None:
        return []
    out = []
    for path in sorted(glob.glob(os.path.join(niftis_dir, "*.nii*"))):
        basename = os.path.basename(path)
        if "TI_max" not in basename or "TDCS" in basename:
            continue
        is_mni = "_MNI" in basename
        if is_mni != (space == "mni"):
            continue
        visible = basename.startswith("grey_")
        out.append(
            _layer(
                path,
                colormap="heat",
                opacity=0.85,
                visible=visible,
                percentile=dict(_DEFAULT_PERCENTILE),
            )
        )
    return out


def _hf_layers(sim_dir: str, space: str) -> list[dict[str, Any]]:
    """High-frequency envelope (magnE) overlays (bug 1)."""
    hf_dir = os.path.join(sim_dir, "high_Frequency", "niftis")
    if not os.path.isdir(hf_dir):
        return []
    out = []
    for path in sorted(glob.glob(os.path.join(hf_dir, "*_scalar_*magnE.nii.gz"))):
        basename = os.path.basename(path)
        is_mni = "_MNI" in basename
        if is_mni != (space == "mni"):
            continue
        out.append(
            _layer(
                path,
                colormap="heat",
                opacity=0.7,
                visible=False,
                percentile=dict(_DEFAULT_PERCENTILE),
            )
        )
    return out


def _grey_mesh_layer(sim_dir: str, sim: str) -> dict[str, Any] | None:
    """The grey-matter TI_max surface mesh, hidden by default (bugs of scale, W3a).

    Subject space only -- SimNIBS writes no MNI-space mesh at all -- and
    always the default ``TI_max`` field, never the high-frequency envelope
    (there is no ``grey_<sim>_magnE.msh``). ``kind="label"`` matches the
    ``ViewLayer`` contract's ``Literal["volume", "label"]`` (a mesh has no
    kind of its own there; ``build_view``'s ``custom`` branch uses the same
    convention). Hidden (``visible=False``) because these files run
    24-420 MB (``docs/dev/HISTORY.md § 2026-09-03 (native desktop research)``) --
    the dataset is declared lazy in the scene and fetched only if the user
    makes the layer visible.
    """
    for mode in _MODE_DIRS:
        mesh = os.path.join(sim_dir, mode, "mesh", f"grey_{sim}_TI.msh")
        if os.path.isfile(mesh):
            return _layer(
                mesh, kind="label", colormap="jet", opacity=1.0, visible=False
            )
    return None


def _electrode_overlay_layer(pm, sid: str, sim: str) -> dict[str, Any] | None:
    sim_dir = pm.simulation(sid, sim)
    for mode in _MODE_DIRS:
        overlay = os.path.join(
            sim_dir, mode, "montage_imgs", "electrode_overlay_subject.nii.gz"
        )
        if not os.path.isfile(overlay):
            continue
        lut = None
        try:
            from tit.tools.electrode_overlay import electrode_overlay_lut_path

            candidate = str(electrode_overlay_lut_path(overlay))
            lut = candidate if os.path.isfile(candidate) else None
        except ImportError:
            lut = None
        return _layer(overlay, colormap="lut", opacity=0.85, lut=lut)
    return None


def _analysis_layer(
    pm, sid: str, sim: str, analysis_name: str
) -> dict[str, Any] | None:
    for space_dir in ("Voxel", "Mesh"):
        candidate = os.path.join(
            pm.simulation(sid, sim), "Analyses", space_dir, analysis_name
        )
        if not os.path.isdir(candidate):
            continue
        nifti = os.path.join(candidate, "roi_overlay.nii.gz")
        if not os.path.isfile(nifti):
            matches = glob.glob(os.path.join(candidate, "*.nii*"))
            nifti = matches[0] if matches else None
        if nifti:
            return _layer(nifti, colormap="jet", opacity=0.6)
        return None
    return None


#: What the Viewer page's "Also open" checkboxes name, and the only extra
#: layers ``build_view`` will add on request.  Each one reuses the layer
#: builder the server already trusted for that file, so an extra is the same
#: layer it would have been had the view type produced it -- never a
#: second, differently-configured description of the same volume.
EXTRA_LAYERS = ("t1", "atlas", "electrodes", "gm_mesh")


def _extra_layers(
    pm,
    existing: list[dict[str, Any]],
    *,
    subject: str | None,
    simulation: str | None,
    space: str,
    atlas: str | None,
    extras: list[str] | None,
) -> list[dict[str, Any]]:
    """The requested *extras* that resolve to a file this view does not already have.

    Additive and de-duplicated by path: asking for the T1 on a view that
    already opens the T1 changes nothing, which is what makes the checkbox
    safe to leave ticked.
    """
    if not extras:
        return []
    seen = {layer["path"] for layer in existing}
    out: list[dict[str, Any]] = []
    for name in extras:
        if name not in EXTRA_LAYERS:
            continue
        layer: dict[str, Any] | None = None
        if name == "t1" and subject:
            layer = _subject_t1_layer(pm, subject, space)
        elif name == "atlas" and subject:
            layer = _subject_atlas_layer(pm, subject, space, atlas)
        elif name == "electrodes" and subject and simulation:
            layer = _electrode_overlay_layer(pm, subject, simulation)
        elif name == "gm_mesh" and subject and simulation and space == "subject":
            layer = _grey_mesh_layer(pm.simulation(subject, simulation), simulation)
        if layer is None or layer["path"] in seen:
            continue
        seen.add(layer["path"])
        out.append(layer)
    return out


def _scene_title(
    subject: str | None, simulation: str | None, field: str | None
) -> str | None:
    """``"ernie · Thalamus · TI_max"`` -- what the viewer's source bar reads."""
    parts = [part for part in (subject, simulation, field) if part]
    return " · ".join(parts) if parts else None


def _analysis_cursor(pm, sid: str, sim: str, analysis_name: str) -> list[float] | None:
    """The centre of a *spherical* analysis, as a starting cursor.

    ``analysis.json`` is the only place the server can source an initial
    cursor from, and only for ``analysis_type: "spherical"`` -- a cortical or
    atlas-region analysis has ``center: null``
    (``tit/analyzer/config.py``), so those keep the volume's own centre.
    """
    import json

    for space_dir in ("Voxel", "Mesh"):
        config = os.path.join(
            pm.simulation(sid, sim),
            "Analyses",
            space_dir,
            analysis_name,
            "analysis.json",
        )
        if not is_within(pm.project_dir, config) or not os.path.isfile(config):
            continue
        try:
            with open(config, encoding="utf-8") as f:
                data = json.load(f)
            center = data.get("center")
            if isinstance(center, (list, tuple)) and len(center) == 3:
                return [float(v) for v in center]
        except (OSError, ValueError, TypeError):
            return None
        return None
    return None


# ---------------------------------------------------------------------------
# Scene overrides (VM) -- the Viewer page's composition panel, on the wire.
#
# Everything the page exposes has to land in the scene file, or the control is
# a lie.  So the knobs below are exactly the ones this server can *write*: the
# per-layer fields ``to_tetravox_viewspec`` already emits, the four layouts the
# schema's ``Layout.kind`` enum offers that make sense without a per-file
# camera fit, six anatomical camera presets, the radiological flag and the
# background.  Nothing here invents a field the engine does not have -- there
# is no points layer in ViewSpec v2, for instance, so the page offers no
# electrode-points checkbox and offers the electrode *overlay volume* instead.
#
# Applied to the finished ``scene`` rather than to ``spec["layers"]`` because
# that is where these words exist: opacity on a layer spec is the *input* to a
# scale/threshold decision, opacity on a scene layer is the number the engine
# reads.
# ---------------------------------------------------------------------------

#: ``kind`` -> the cells that kind's panes are, in order.  A subset of the
#: schema's ``Layout.kind`` enum: the ones a person can ask for without the
#: server knowing anything about the data's own extent.
SCENE_LAYOUTS: dict[str, list[str]] = {
    "1x1": ["axial"],
    "1+3": ["view3d", "axial", "coronal", "sagittal"],
    "2x2": ["axial", "coronal", "sagittal", "view3d"],
    "3d-only": ["view3d"],
}

#: Six anatomical camera presets, as ``view3d.camera.rotation`` quaternions
#: ``[x, y, z, w]``.  ``A`` is the engine's own identity framing, and the other
#: five are quarter- and half-turns from it about the up and right axes; this
#: is a rotation of the default view, not a claim about the engine's world
#: axes, which the server cannot see.
CAMERA_PRESETS: dict[str, list[float]] = {
    "A": [0.0, 0.0, 0.0, 1.0],
    "P": [0.0, 1.0, 0.0, 0.0],
    "L": [0.0, -0.7071067811865476, 0.0, 0.7071067811865476],
    "R": [0.0, 0.7071067811865476, 0.0, 0.7071067811865476],
    "S": [-0.7071067811865476, 0.0, 0.0, 0.7071067811865476],
    "I": [0.7071067811865476, 0.0, 0.0, 0.7071067811865476],
}

#: The scene ground every scene has always had.  Defined here rather than
#: beside the other ``_DEFAULT_*`` rig constants only because
#: :data:`SCENE_BACKGROUNDS` needs it and that block comes later in the file.
_DEFAULT_BACKGROUND = [
    0.058823529411764705,
    0.06666666666666667,
    0.08627450980392157,
    1.0,
]

#: Named backgrounds.  ``dark`` is the default every scene has always had.
SCENE_BACKGROUNDS: dict[str, list[float]] = {
    "dark": list(_DEFAULT_BACKGROUND),
    "black": [0.0, 0.0, 0.0, 1.0],
    "light": [0.94, 0.95, 0.96, 1.0],
}

#: The per-layer keys a client may set, and the type each is coerced to.
_LAYER_NUMBER_KEYS = ("opacity",)
_LAYER_BOOL_KEYS = ("visible", "showIn3D", "showColorbar", "contoursIn2D")


def _clamp01(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return 0.0 if number < 0.0 else 1.0 if number > 1.0 else number


def _apply_layer_override(layer: dict[str, Any], patch: dict[str, Any]) -> None:
    for key in _LAYER_BOOL_KEYS:
        if key in patch and key in layer:
            layer[key] = bool(patch[key])
    for key in _LAYER_NUMBER_KEYS:
        if key in patch:
            layer[key] = _clamp01(patch[key], layer.get(key, 1.0))
    if isinstance(patch.get("colormap"), str) and patch["colormap"]:
        layer["colormap"] = patch["colormap"]
    threshold = patch.get("threshold")
    if isinstance(threshold, dict):
        for bound in ("lo", "hi"):
            if bound not in threshold:
                continue
            value = threshold[bound]
            if value is None:
                layer["threshold"][bound] = None
            else:
                try:
                    layer["threshold"][bound] = float(value)
                except (TypeError, ValueError):
                    pass
    if layer["kind"] != "mesh":
        return
    if isinstance(patch.get("colorMode"), str) and patch["colorMode"] in (
        "tag",
        "field",
        "solid",
        "label",
    ):
        layer["colorMode"] = patch["colorMode"]
    if "clip" in patch:
        enabled = bool(patch["clip"])
        for plane in layer["clip"]["planes"]:
            plane["enabled"] = enabled


def apply_scene_overrides(
    scene: dict[str, Any], overrides: dict[str, Any] | None
) -> dict[str, Any]:
    """*scene*, edited in place by *overrides*; unknown keys are ignored.

    The accepted document::

        {
          "layers": {"<layerId>": {"visible": bool, "opacity": 0..1,
                                   "colormap": str, "showIn3D": bool,
                                   "showColorbar": bool, "contoursIn2D": bool,
                                   "threshold": {"lo": num|null, "hi": num|null},
                                   "colorMode": "tag|field|solid|label",
                                   "clip": bool}},
          "layout": "1x1|1+3|2x2|3d-only",
          "camera": "A|P|L|R|S|I",
          "radiological": bool,
          "background": "dark|black|light" | [r, g, b, a]
        }

    Every value is validated against what the engine's own type accepts and
    silently dropped otherwise: a stale preset from a saved selection must
    not turn into a scene the app refuses to open.  ``None`` returns *scene*
    untouched, which is the whole compatibility guarantee -- absent
    overrides means byte-identical output.
    """
    if not overrides:
        return scene
    by_id = {layer["id"]: layer for layer in scene.get("layers", [])}
    layers = overrides.get("layers")
    if isinstance(layers, dict):
        for layer_id, patch in layers.items():
            layer = by_id.get(str(layer_id))
            if layer is not None and isinstance(patch, dict):
                _apply_layer_override(layer, patch)
    layout = overrides.get("layout")
    if isinstance(layout, str) and layout in SCENE_LAYOUTS:
        scene["layout"] = {"kind": layout, "cells": list(SCENE_LAYOUTS[layout])}
    camera = overrides.get("camera")
    if isinstance(camera, str) and camera.upper() in CAMERA_PRESETS:
        scene["view3d"]["camera"]["rotation"] = list(CAMERA_PRESETS[camera.upper()])
    if "radiological" in overrides:
        scene["radiological"] = bool(overrides["radiological"])
    background = overrides.get("background")
    if isinstance(background, str) and background in SCENE_BACKGROUNDS:
        scene["background"] = list(SCENE_BACKGROUNDS[background])
    elif isinstance(background, (list, tuple)) and len(background) == 4:
        try:
            scene["background"] = [float(c) for c in background]
        except (TypeError, ValueError):
            pass
    # The active layer must still be one that exists and is visible, or the
    # app opens with its inspector pointed at a layer nobody can see.
    visible = [la["id"] for la in scene.get("layers", []) if la["visible"]]
    if visible and scene.get("activeLayerId") not in visible:
        scene["activeLayerId"] = visible[0]
    return scene


def _apply(
    spec: dict[str, Any] | None, overrides: dict[str, Any] | None
) -> dict[str, Any] | None:
    """:func:`apply_scene_overrides` on a finished spec's ``scene``, or a no-op."""
    if spec is not None and overrides:
        apply_scene_overrides(spec["scene"], overrides)
    return spec


# ---------------------------------------------------------------------------
# VM2 -- the file list is the scene.
#
# The Viewer page is one "what will open" list a person edits directly: remove
# a row, add a file, drag to reorder.  When the client sends that list, it is
# **authoritative** -- these are the datasets, in this order, and nothing the
# view type would otherwise have contributed is added back.
#
# What the client does *not* send is how each file should look.  That stays
# here, because it is a judgement about the data (a percentile window on a TI
# field, `nearest` interpolation and a LUT on a label volume, a hidden mesh
# because the file is 64 MB) and a client that mirrored it would drift from it.
# So a path that the view type already produced keeps **exactly** the layer
# settings that view type gave it, and only a path that was *added* is
# described from scratch by :func:`_layer_for_path`.
# ---------------------------------------------------------------------------

#: Basenames that read as anatomy rather than as a field: grayscale, opaque.
_ANATOMY_HINTS = ("t1", "t2", "mni152", "template", "brain", "orig", "conform")

#: Basenames that read as a labelled volume: a LUT, `nearest`, half-opaque.
_LABEL_HINTS = (
    "labeling",
    "aseg",
    "aparc",
    "atlas",
    "label",
    "seg",
    "dk40",
    "hcp_mmp1",
    "a2009s",
    "schaefer",
    "final_tissues",
)


def _lut_for(path: str) -> str | None:
    """The colour table beside *path*, if this server can name one.

    Three chances, in the order they are likely to be right: a
    ``<stem>_LUT.txt`` sibling (SimNIBS writes ``labeling_LUT.txt`` and
    ``final_tissues_LUT.txt`` exactly like this), the segmentation
    directory's own answer, then FreeSurfer's global table.  ``None`` is a
    perfectly good result -- the engine renders a label volume without one,
    it just picks its own colours.
    """
    directory = os.path.dirname(path)
    stem = os.path.basename(path)
    for suffix in _STRIPPED_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    sibling = os.path.join(directory, f"{stem}_LUT.txt")
    if os.path.isfile(sibling):
        return sibling
    if os.path.basename(directory) == "segmentation":
        found = VoxelAtlasManager(seg_dir=directory).find_labeling_lut()
        if found:
            return found
    return _freesurfer_color_lut()


def _layer_for_path(path: str) -> dict[str, Any]:
    """The default layer for a file that no view type produced.

    Only reached for a file the *user* added, so the rules are the same ones
    the view builders apply, re-derived from the name alone: a mesh is a
    hidden ``jet`` surface (they run 24-420 MB), a labelled volume gets a LUT
    at 0.7, anything anatomical is opaque grayscale, and everything else is
    treated as a field -- ``heat`` at 0.85 with the same percentile window
    ``_ti_max_layers`` uses, because a field rendered on its raw min/max is a
    picture of its outliers.
    """
    name = os.path.basename(path).lower()
    if classify_view_file(path) == "surface":
        # **Visible**, unlike the mesh case below. A `.msh` starts hidden because it is 24-420 MB
        # and loading one nobody asked to see is a minute of somebody's time; a cortical sheet is
        # ~8 MB. A surface that arrived hidden would mean ticking `lh.central` and its
        # parcellation and getting a picture with neither in it, which reads as a bug in the
        # ticking rather than a deliberate saving.
        return _layer(path, kind="label", colormap="jet", opacity=1.0, visible=True)
    if _scene_is_mesh(path):
        return _layer(path, kind="label", colormap="jet", opacity=1.0, visible=False)
    if any(hint in name for hint in _LABEL_HINTS):
        return _layer(path, colormap="lut", opacity=0.7, lut=_lut_for(path))
    if any(hint in name for hint in _ANATOMY_HINTS):
        return _layer(path)
    return _layer(
        path, colormap="heat", opacity=0.85, percentile=dict(_DEFAULT_PERCENTILE)
    )


def _layers_from_files(
    files: list[str], defaults: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """*files*, in order, as layers -- default settings kept where they exist.

    Every path is re-resolved through :func:`resolve_jailed` before it is
    used, exactly like ``kind=custom``'s own path: this list arrives from a
    client and is not trustworthy just because the client got most of it from
    us.  A path that does not resolve is dropped rather than refused, so one
    stale row in a restored preset does not cost a person the whole scene.
    """
    by_path = {
        layer["path"]: layer for layer in (defaults or {}).get("layers", [])
    }
    layers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in files:
        if not isinstance(raw, str):
            continue
        resolved = resolve_jailed(raw)
        if resolved is None:
            continue
        path = str(resolved)
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        kind = classify_view_file(path)
        if kind in VIEW_ATTACHMENT_KINDS:
            # An attachment is **not a layer**. A `.annot` is a colour table and a `lh.thickness`
            # is a column of numbers; neither has geometry, and Tetravox models both the same way
            # -- as a node field on the surface's own dataset (`sidecars.fields`), referenced by
            # the surface layer's `annotation.name` / `overlay.name`. Folding it here rather than
            # in `to_tetravox_viewspec` keeps `spec["layers"]` and `scene["datasets"]` the same
            # length, which the file list in `tit/server/routes/viewers.py` zips together.
            #
            # Hemisphere decides which surface it lands on, because that is the only
            # correspondence FreeSurfer promises. With no matching surface ticked it is dropped,
            # like any other unusable row: an attachment alone would draw nothing.
            host = _surface_for_attachment(layers, path)
            if host is not None:
                host.setdefault("attachments", []).append(path)
            continue
        layers.append(
            copy.deepcopy(by_path[path]) if path in by_path else _layer_for_path(path)
        )
    return layers


def _surface_for_attachment(
    layers: list[dict[str, Any]], attachment: str
) -> dict[str, Any] | None:
    """The last ticked surface of the attachment's hemisphere, or ``None``.

    *Last*, so a person who ticks `lh.pial` then `lh.central` then an annotation gets it on the
    surface they just chose. A hemisphere-less attachment (rare, but a `.func.gii` need not be
    named `lh.*`) goes on the last surface of any hemisphere.
    """
    hemi = os.path.basename(attachment)[:3]
    hemi = hemi if hemi in ("lh.", "rh.") else ""
    for layer in reversed(layers):
        if classify_view_file(layer["path"]) != "surface":
            continue
        if hemi and not os.path.basename(layer["path"]).startswith(hemi):
            continue
        return layer
    return None


def build_view(
    kind: str,
    *,
    subject: str | None = None,
    simulation: str | None = None,
    space: str | None = None,
    field: str | None = None,
    analysis: str | None = None,
    atlas: str | None = None,
    roi: str | None = None,
    path: str | None = None,
    extras: list[str] | None = None,
    overrides: dict[str, Any] | None = None,
    files: list[str] | None = None,
) -> dict[str, Any] | None:
    """Build a ``ViewSpec`` dict, or ``None`` when the request cannot resolve.

    ``None`` means "unknown subject/simulation/analysis" (the route turns
    that into a 404); an unrecognised *kind* also returns ``None``.

    *extras* and *overrides* are **additive and optional** (VM,
    ``docs/dev/HISTORY.md § 2026-09-06 (native panes, external viewer)``).  With neither
    given -- which is every caller that existed before them -- this function
    returns exactly the document it returned before: *extras* adds no layer
    and :func:`apply_scene_overrides` is not called at all.  *extras* names
    files to add to the layer list (:data:`EXTRA_LAYERS`); *overrides*
    edits the finished ``scene`` (per-layer appearance, layout, camera,
    convention, background) and is documented on
    :func:`apply_scene_overrides`.
    """
    if kind not in _VIEW_KINDS:
        return None
    # The contract declares exactly two spaces; anything else is the subject's
    # own, which is also what every layer helper falls back to.
    space = "mni" if (space or "").lower() == "mni" else "subject"
    pm = get_path_manager()

    if files is not None:
        # VM2: the client edited the list, so the list *is* the scene. The view
        # type is still built once -- not to contribute layers, but to be the
        # source of each kept file's settings and of the scene's cursor.
        defaults = build_view(
            kind,
            subject=subject,
            simulation=simulation,
            space=space,
            field=field,
            analysis=analysis,
            atlas=atlas,
            roi=roi,
            path=path,
            extras=extras,
        )
        layers = _layers_from_files(files, defaults)
        if not layers:
            return None
        return _apply(
            _finish(
                space,
                layers,
                title=_scene_title(subject, simulation, analysis or field),
                cursor=(defaults or {}).get("cursor"),
            ),
            overrides,
        )

    if kind == "custom":
        if not path:
            return None
        resolved = resolve_jailed(path)
        if resolved is None:
            return None
        resolved_str = str(resolved)
        layer_kind = "label" if resolved_str.endswith(".msh") else "volume"
        return _apply(
            _finish(
                space,
                [_layer(resolved_str, kind=layer_kind)],
                title=os.path.basename(resolved_str),
            ),
            overrides,
        )

    if kind == "subject":
        if not subject or subject not in pm.list_simnibs_subjects():
            return None
        layers = []
        t1 = _subject_t1_layer(pm, subject, space)
        if t1:
            layers.append(t1)
        atlas_layer = _subject_atlas_layer(pm, subject, space, atlas)
        if atlas_layer:
            layers.append(atlas_layer)
        layers.extend(
            _extra_layers(
                pm,
                layers,
                subject=subject,
                simulation=None,
                space=space,
                atlas=atlas,
                extras=extras,
            )
        )
        return _apply(
            _finish(space, layers, title=_scene_title(subject, None, None)), overrides
        )

    if kind == "simulation":
        if not subject or not simulation:
            return None
        if simulation not in pm.list_simulations(subject):
            return None
        sim_dir = pm.simulation(subject, simulation)
        layers = []
        t1 = _subject_t1_layer(pm, subject, space)
        if t1:
            layers.append(t1)
        overlay = _electrode_overlay_layer(pm, subject, simulation)
        if overlay:
            layers.append(overlay)
        if field == "magnE":
            layers.extend(_hf_layers(sim_dir, space))
        else:
            layers.extend(_ti_max_layers(sim_dir, space))
            if space == "subject":
                mesh_layer = _grey_mesh_layer(sim_dir, simulation)
                if mesh_layer:
                    layers.append(mesh_layer)
        cursor = None
        if analysis:
            analysis_layer = _analysis_layer(pm, subject, simulation, analysis)
            if analysis_layer:
                layers.append(analysis_layer)
                cursor = _analysis_cursor(pm, subject, simulation, analysis)
        layers.extend(
            _extra_layers(
                pm,
                layers,
                subject=subject,
                simulation=simulation,
                space=space,
                atlas=atlas,
                extras=extras,
            )
        )
        return _apply(
            _finish(
                space,
                layers,
                title=_scene_title(subject, simulation, analysis or field or "TI_max"),
                cursor=cursor,
            ),
            overrides,
        )

    if kind == "analysis":
        if not subject or not simulation or not analysis:
            return None
        if simulation not in pm.list_simulations(subject):
            return None
        layer = _analysis_layer(pm, subject, simulation, analysis)
        if layer is None:
            return None
        layers = []
        t1 = _subject_t1_layer(pm, subject, "subject")
        if t1:
            layers.append(t1)
        layers.append(layer)
        layers.extend(
            _extra_layers(
                pm,
                layers,
                subject=subject,
                simulation=simulation,
                space="subject",
                atlas=atlas,
                extras=extras,
            )
        )
        return _apply(
            _finish(
                "subject",
                layers,
                title=_scene_title(subject, simulation, analysis),
                cursor=_analysis_cursor(pm, subject, simulation, analysis),
            ),
            overrides,
        )

    if kind == "group":
        layers = []
        template = os.path.join(mni_resources_dir(), MNI_TEMPLATE)
        if os.path.isfile(template):
            layers.append(_layer(template))
        atlas_path = _default_mni_atlas_path(atlas)
        if atlas_path:
            layers.append(
                _layer(
                    atlas_path,
                    colormap="lut",
                    opacity=0.5,
                    lut=_mni_atlas_lut(atlas_path),
                )
            )
        if (
            subject
            and simulation
            and subject in pm.list_simnibs_subjects()
            and simulation in pm.list_simulations(subject)
        ):
            layers.extend(_ti_max_layers(pm.simulation(subject, simulation), "mni"))
        return _apply(
            _finish("mni", layers, title=_scene_title(subject, simulation, "group")),
            overrides,
        )

    return None  # pragma: no cover - _VIEW_KINDS guards this


def _candidate(path: str, group: str) -> dict[str, Any]:
    try:
        size: int | None = os.path.getsize(path)
    except OSError:
        size = None
    return {
        "name": os.path.basename(path),
        "path": path,
        # The same classifier the composition tree reads (`tit.catalog.classify_view_file`), so
        # the "+ Add…" picker and the tree cannot disagree about what a file is.
        "kind": classify_view_file(path) or "volume",
        "group": group,
        "bytes": size,
    }


def viewer_candidates(
    subject: str | None = None,
    simulation: str | None = None,
    space: str | None = None,
) -> list[dict[str, Any]]:
    """Everything this subject (and simulation) offers the Viewer's "+ Add…".

    Grouped the way a person looks for a file -- the head model, the atlases,
    the simulation's own outputs, its analyses -- and every entry is a real
    file that exists right now, with its size, because the point of the list
    is to choose without guessing.  Files that a scene *cannot* use are not
    listed at all: FreeSurfer ``.annot`` parcellations, ``.mat`` matrices,
    logs and reports are not volumes or meshes.

    This is a read: it opens nothing and writes nothing.
    """
    pm = get_path_manager()
    space = "mni" if (space or "").lower() == "mni" else "subject"
    out: list[dict[str, Any]] = []
    if not subject or subject not in pm.list_simnibs_subjects():
        return out

    m2m = pm.m2m(subject)
    for name in sorted(os.listdir(m2m)) if os.path.isdir(m2m) else []:
        candidate = os.path.join(m2m, name)
        if os.path.isfile(candidate) and (
            name.endswith((".nii", ".nii.gz", ".mgz")) or name.endswith(".msh")
        ):
            out.append(_candidate(candidate, "Head model"))

    surfaces = os.path.join(m2m, "surfaces")
    for path in sorted(glob.glob(os.path.join(surfaces, "*.gii"))):
        # The reconstruction surfaces: central/pial/white per hemisphere. The
        # sphere and sphere.reg files are registration targets, not anatomy --
        # offering them would be offering a ball.
        if os.path.basename(path).split(".")[1] in ("central", "pial", "white"):
            out.append(_candidate(path, "Surfaces"))

    seg_dir = os.path.join(m2m, "segmentation")
    manager = VoxelAtlasManager(
        fastsurfer_mri_dir=pm.fastsurfer_mri(subject),
        freesurfer_mri_dir=pm.freesurfer_mri(subject),
        seg_dir=seg_dir,
        masks_dir=pm.masks(subject),
    )
    for _display, path in manager.list_atlases():
        if os.path.isfile(path):
            out.append(_candidate(path, "Atlases"))
    if space == "mni":
        for path in VoxelAtlasManager.detect_mni_atlases(mni_resources_dir()):
            out.append(_candidate(path, "Atlases (MNI)"))
        template = os.path.join(mni_resources_dir(), MNI_TEMPLATE)
        if os.path.isfile(template):
            out.append(_candidate(template, "Head model"))

    if simulation and simulation in pm.list_simulations(subject):
        sim_dir = pm.simulation(subject, simulation)
        for mode in _MODE_DIRS + ("high_Frequency",):
            for sub, group in (
                ("niftis", "Simulation volumes"),
                ("mesh", "Simulation meshes"),
                ("montage_imgs", "Electrodes"),
            ):
                directory = os.path.join(sim_dir, mode, sub)
                for path in sorted(glob.glob(os.path.join(directory, "*"))):
                    if os.path.isfile(path) and path.endswith(
                        (".nii", ".nii.gz", ".mgz", ".msh", ".gii")
                    ):
                        out.append(_candidate(path, group))
        for space_dir in ("Voxel", "Mesh"):
            root = os.path.join(sim_dir, "Analyses", space_dir)
            for path in sorted(glob.glob(os.path.join(root, "*", "*.nii*"))):
                out.append(_candidate(path, "Analyses"))

    seen: set[str] = set()
    unique = []
    for entry in out:
        if entry["path"] in seen:
            continue
        seen.add(entry["path"])
        unique.append(entry)
    return unique


# ── the composition tree (2026-09-07) ────────────────────────────────────────
#
# Maintainer: *"please change the menu such that there is subject and then it kind of like shows
# two little branches with the anatomy and then there is a simulation section where they can
# choose the different simulations -- they can potentially choose multiple -- and then they choose
# analysis output; and in each one the user should be able to choose what input they want for each
# stage ... It depends on what is available and what is selected, but it should be a continuous
# integrated thing instead of what we have right now."*
#
# `viewer_candidates` above already knows every file a scene can use; what it does not do is say
# what *stage* a file belongs to, whether it is available, or why not. That is the difference
# between a flat "+ Add..." picker and a tree a person can read their whole composition off.
#
# Two rules this shares with the rest of the module, and they are what keep the tree honest:
#
#  1. **Every node is a real file that exists right now**, with its size -- or it is marked
#     unavailable with the reason. A tree that offers something which is not there moves the
#     failure to Open, which is a worse moment to learn it.
#  2. **No voxel is read.** The tree is drawn on every keystroke in the Menu; it is `os.listdir`
#     and `os.stat`, nothing more. Windows are decided later, by `build_view`, from the sidecar.

#: Stable id for a node: the container path. Not an index and not a display name -- a composition
#: saved today has to resolve against a project that has since gained or lost files, and the only
#: thing that survives that is what the file is called.
def _size_or_none(path: str) -> int | None:
    try:
        return os.path.getsize(path)
    except OSError:
        return None


def _tree_node(
    path: str,
    *,
    label: str | None = None,
    default_on: bool = False,
    attachment_dirs: tuple[str, ...] = (),
) -> dict[str, Any]:
    """One row of the tree, with the *kind* every menu now reads rather than re-derives.

    ``kind`` is :func:`tit.catalog.classify_view_file`'s answer, so this row says ``surface``
    where it used to say ``mesh`` for a ``.gii`` sheet -- the maintainer's note of 2026-09-07 (a
    mesh is the tetrahedral FEM domain; a surface is a triangulated sheet). A file the classifier
    refuses still shows as a ``volume``, because reaching here means some branch already decided
    it was offerable and silently dropping it would be worse than a blunt chip.

    A **surface** carries its ``attachments``: the ``.annot`` parcellations, morphometry curves
    and data GIfTIs that share its hemisphere. They are sub-rows, not siblings, because that is
    what they are -- a ``.annot`` on its own is a colour table with nowhere to go.

    """
    try:
        size: int | None = os.path.getsize(path)
        available = True
        reason = None
    except OSError:
        size, available, reason = None, False, "file is missing"
    kind = classify_view_file(path) or "volume"
    node = {
        "id": path,
        "name": os.path.basename(path),
        "label": label or _scene_display_name(
            os.path.basename(path),
            role=_scene_role(path, "heat" if _scene_field_name(os.path.basename(path)) else "grayscale"),
            field_name=_scene_field_name(os.path.basename(path)),
        ),
        "path": path,
        "kind": kind,
        "bytes": size,
        "default_on": default_on,
        "available": available,
        "reason": reason,
    }
    if kind == "surface":
        node["attachments"] = [
            {
                "id": attachment,
                "name": os.path.basename(attachment),
                "label": _scene_stem(os.path.basename(attachment)),
                "path": attachment,
                "kind": classify_view_file(attachment) or "surface-data",
                "bytes": _size_or_none(attachment),
                "default_on": False,
                "available": available,
                "reason": reason,
            }
            for attachment in surface_attachments(
                path, extra_dirs=attachment_dirs,
                project_root=get_path_manager().project_dir,
            )
        ]
    return node


def _anatomy_branch(
    pm, subject: str, space: str
) -> list[dict[str, Any]]:
    """T1, T2, the head mesh, the reconstruction surfaces and the atlases.

    ``default_on`` marks the T1 (in subject space) or the MNI template (in MNI space): a scene
    with no anatomy under it is a field floating in black, so exactly one base layer starts ticked
    and everything else starts off.
    """
    out: list[dict[str, Any]] = []
    m2m = pm.m2m(subject)
    sid_stem = str(subject)
    names = sorted(os.listdir(m2m)) if os.path.isdir(m2m) else []
    for name in names:
        candidate = os.path.join(m2m, name)
        if not os.path.isfile(candidate):
            continue
        if not name.endswith((".nii", ".nii.gz", ".mgz", ".msh")):
            continue
        # `<subject>.msh` is the head model itself, and its stem is the subject id -- a row
        # labelled "101" says nothing about what it is. Everything else reads fine as its stem.
        stem = _scene_stem(name)
        label = f"Head mesh ({stem})" if _scene_is_mesh(name) and stem == sid_stem else stem
        out.append(
            _tree_node(
                candidate,
                label=label,
                default_on=(space == "subject" and name in ("T1.nii.gz", "T1.nii")),
            )
        )

    surfaces = os.path.join(m2m, "surfaces")
    # SimNIBS keeps the geometry in `surfaces/` and writes the parcellations it made two
    # directories away, into `segmentation/` -- which is exactly why nothing had ever offered
    # them. `surface_attachments` is told to look in both.
    segmentation = os.path.join(m2m, "segmentation")
    for path in sorted(glob.glob(os.path.join(surfaces, "*.gii"))):
        # central/pial/white only: `sphere` and `sphere.reg` are registration targets, and
        # offering them would be offering a ball.
        parts = os.path.basename(path).split(".")
        if len(parts) > 1 and parts[1] in ("central", "pial", "white"):
            out.append(
                _tree_node(
                    path,
                    label=_scene_stem(os.path.basename(path)),
                    attachment_dirs=(segmentation,),
                )
            )

    manager = VoxelAtlasManager(
        fastsurfer_mri_dir=pm.fastsurfer_mri(subject),
        freesurfer_mri_dir=pm.freesurfer_mri(subject),
        seg_dir=os.path.join(m2m, "segmentation"),
        masks_dir=pm.masks(subject),
    )
    for display, path in manager.list_atlases():
        if os.path.isfile(path):
            out.append(_tree_node(path, label=display))

    if space == "mni":
        for path in VoxelAtlasManager.detect_mni_atlases(mni_resources_dir()):
            out.append(_tree_node(path, label=_scene_stem(os.path.basename(path))))
        template = os.path.join(mni_resources_dir(), MNI_TEMPLATE)
        if os.path.isfile(template):
            out.append(_tree_node(template, label="MNI152 template", default_on=True))
    return out


def _simulation_branch(
    pm, subject: str, simulation: str, space: str
) -> dict[str, Any]:
    """One simulation's own outputs, split into what a person picks between.

    ``fields`` are the NIfTI volumes, ``meshes`` the tetrahedral ``.msh`` outputs, ``surfaces``
    the GIfTI/fsaverage sheets with their per-vertex data, ``electrodes`` the montage overlay.

    ``surfaces`` is its own bucket rather than a corner of ``meshes``, for the reason this whole
    change exists: the fsaverage projection writes ``lh.*.gii`` sheets a few MB each, and filing
    them under "Meshes" beside a 64 MB ``.msh`` told a reader they were the same sort of thing and
    the same sort of wait.

    Space matters: a subject-space scene must not offer the MNI copies, because two volumes in
    different spaces in one scene is a misregistration nobody asked for.
    """
    sim_dir = pm.simulation(subject, simulation)
    fields: list[dict[str, Any]] = []
    meshes: list[dict[str, Any]] = []
    surfaces: list[dict[str, Any]] = []
    electrodes: list[dict[str, Any]] = []
    for mode in _MODE_DIRS + ("high_Frequency",):
        for sub, bucket in (
            ("niftis", fields),
            ("mesh", meshes),
            ("montage_imgs", electrodes),
        ):
            for path in sorted(glob.glob(os.path.join(sim_dir, mode, sub, "*"))):
                if not os.path.isfile(path):
                    continue
                if not path.endswith((".nii", ".nii.gz", ".mgz", ".msh", ".gii")):
                    continue
                if not _in_space(os.path.basename(path), space, is_mesh=_scene_is_mesh(path)):
                    continue
                node = _tree_node(
                    path,
                    attachment_dirs=(os.path.dirname(path),),
                )
                # A `.gii` written into `mesh/` is still a sheet; the directory it landed in is
                # SimNIBS's filing, not a claim about the geometry.
                (surfaces if node["kind"] == "surface" else bucket).append(node)

    # The grey-matter-masked field is the one a reader wants first: the whole-head copy is mostly
    # skull and CSF, where the number is not the thing being reported.
    for node in fields:
        if node["name"].lower().startswith("grey_"):
            node["default_on"] = True
            break
    else:
        if fields:
            fields[0]["default_on"] = True

    return {
        "name": simulation,
        "fields": fields,
        "meshes": meshes,
        "surfaces": surfaces,
        "electrodes": electrodes,
    }


def _in_space(name: str, space: str, *, is_mesh: bool) -> bool:
    """Whether *name* belongs in a *space* scene.

    SimNIBS marks the MNI copies in the filename (``..._MNI_MNI_TI_max.nii.gz`` against
    ``..._subject_TI_max.nii.gz``). Meshes are always subject space -- there is no MNI mesh -- so
    they are offered in both, which is the honest answer rather than hiding them in MNI mode.
    """
    if is_mesh:
        return True
    lowered = name.lower()
    if "_mni_" in lowered or lowered.endswith("_mni.nii.gz"):
        return space == "mni"
    if "_subject_" in lowered:
        return space == "subject"
    return True


def _analysis_branch(
    pm, subject: str, simulation: str
) -> list[dict[str, Any]]:
    """The analyzer outputs under one simulation: ROI masks, spheres, group and statistic maps."""
    sim_dir = pm.simulation(subject, simulation)
    out: list[dict[str, Any]] = []
    for space_dir in ("Voxel", "Mesh"):
        root = os.path.join(sim_dir, "Analyses", space_dir)
        for run in sorted(glob.glob(os.path.join(root, "*"))):
            if not os.path.isdir(run):
                continue
            nodes = [
                _tree_node(
                    path, attachment_dirs=(run,)
                )
                for path in sorted(glob.glob(os.path.join(run, "*")))
                if os.path.isfile(path)
                and path.endswith((".nii", ".nii.gz", ".mgz", ".msh", ".gii"))
            ]
            if nodes:
                out.append(
                    {
                        "name": os.path.basename(run),
                        "simulation": simulation,
                        "space": space_dir.lower(),
                        "outputs": nodes,
                    }
                )
    return out


def viewer_tree(
    subject: str | None = None,
    space: str | None = None,
    simulations: list[str] | None = None,
) -> dict[str, Any]:
    """What the Menu's composition tree draws, for one subject.

    *simulations* is what the person has expanded/selected: analyses are listed only for those,
    because a subject with a dozen simulations has a dozen Analyses directories and listing all of
    them turns a menu into a file browser. Anatomy is always listed; it is what a scene starts from.

    A read. It opens nothing, writes nothing and reads no voxels.
    """
    pm = get_path_manager()
    space = "mni" if (space or "").lower() == "mni" else "subject"
    empty = {
        "subject": subject,
        "space": space,
        "anatomy": [],
        "simulations": [],
        "analyses": [],
        "available": False,
        "reason": None,
    }
    if not subject:
        return {**empty, "reason": "no subject chosen"}
    if subject not in pm.list_simnibs_subjects():
        # Named rather than silently empty: "this subject has no head model" is a different
        # problem from "this subject has no simulations", and the Menu should be able to say which.
        return {**empty, "reason": f"{subject} has no head model (m2m directory)"}

    chosen = set(simulations or [])
    all_sims = pm.list_simulations(subject) or []
    sims = [
        _simulation_branch(pm, subject, name, space)
        for name in sorted(all_sims)
    ]
    analyses: list[dict[str, Any]] = []
    for name in sorted(all_sims):
        if chosen and name not in chosen:
            continue
        analyses.extend(
            _analysis_branch(pm, subject, name)
        )

    return {
        "subject": subject,
        "space": space,
        "anatomy": _anatomy_branch(
            pm, subject, space
        ),
        "simulations": sims,
        "analyses": analyses,
        "available": True,
        "reason": None,
    }


def _percentiles_from_array(
    data: Any, lo: float, hi: float
) -> tuple[float, float] | None:
    """``(cal_min, cal_max)`` at the *lo*/*hi* percentiles of *data*'s non-zero
    voxels, or ``None`` if there are none (e.g. an all-zero volume)."""
    import numpy as np

    nonzero = data[data != 0]
    if nonzero.size == 0:
        return None
    lo_val, hi_val = np.percentile(nonzero, [lo, hi])
    return float(lo_val), float(hi_val)


#: Resolved percentile windows, keyed by the file's identity and the window asked for.
#:
#: Reading a volume to find its percentiles is by far the most expensive thing this module does:
#: ``nibabel`` decompresses the whole gzip stream and ``get_fdata`` materialises it as float64, so
#: one 17 MB ``.nii.gz`` costs ~100 ms and a five-layer scene ~150 ms. That was paid **on every
#: call**, and the Viewer's file list re-resolves through this code on every edit -- so adding a row
#: re-read every volume already in the scene, which is what "the menu acts way too slow" was
#: (maintainer, 2026-09-06).
#:
#: The answer is not to read less of the file -- a percentile taken from a subsample is a different
#: number, and the window it produces is what the reader actually sees. It is to notice that **a
#: file that has not changed has the same percentiles**. The key is (path, size, mtime_ns, lo, hi),
#: so a rewritten or replaced volume misses and is re-read; `mtime_ns` rather than `mtime` because
#: a simulation can rewrite a file inside one filesystem-clock tick.
#:
#: Bounded and process-local on purpose. It is a memoisation of a pure function of file bytes, not
#: a cache of anything a user can see, so it needs no invalidation hook and no persistence; a
#: restart simply pays the first read again.
_PERCENTILE_CACHE: "OrderedDict[tuple[str, int, int, float, float], tuple[float, float] | None]" = (
    OrderedDict()
)
_PERCENTILE_CACHE_MAX = 256
_PERCENTILE_LOCK = threading.Lock()


def _percentile_cache_key(
    path: str, lo: float, hi: float
) -> tuple[str, int, int, float, float] | None:
    """The file's identity plus the window, or ``None`` if it cannot be stat'ed."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (path, st.st_size, st.st_mtime_ns, float(lo), float(hi))


def clear_percentile_cache() -> None:
    """Forget every memoised window. For tests; nothing in the server calls it.

    Both in-process caches, because since the two percentile paths were joined
    (:func:`_resolve_layer_percentile`) a window can be memoised in either: clearing only one
    would leave a test asserting "this file is read again" passing for the wrong reason. The
    on-disk sidecars are *not* removed -- they live in the project under test's own tmp directory
    and are keyed by ``(size, mtime_ns)``, so they cannot leak between tests.
    """
    with _PERCENTILE_LOCK:
        _PERCENTILE_CACHE.clear()
    _stats_cache.clear()
    _bounds_cache.clear()


#: Which :func:`_volume_stats` key answers which percentile, for the windows this module actually
#: asks for. A window outside this table falls back to reading the volume -- correctness first: a
#: p90 answered with p95 would be wrong, and wrong is worse than slow.
_STATS_PERCENTILE_KEYS: dict[float, str] = {
    0.0: "nz_lo",
    2.0: "p2",
    50.0: "p50",
    95.0: "p95",
    98.0: "p98",
    99.0: "p99",
    99.9: "p999",
    100.0: "nz_hi",
}


def _stats_can_answer(lo: float, hi: float) -> bool:
    """Whether :func:`_volume_stats` computes both ends of this window."""
    return (
        float(lo) in _STATS_PERCENTILE_KEYS and float(hi) in _STATS_PERCENTILE_KEYS
    )


def _percentiles_from_stats(
    path: str, lo: float, hi: float
) -> tuple[float, float] | None:
    """``(lo, hi)`` from the cached/sidecar statistics, or ``None`` if they cannot answer.

    ``None`` means either the file has no statistics (unreadable, all-zero) or the window asked
    for is not one :func:`_volume_stats` computes -- the caller then reads the volume itself.
    """
    lo_key = _STATS_PERCENTILE_KEYS.get(float(lo))
    hi_key = _STATS_PERCENTILE_KEYS.get(float(hi))
    if lo_key is None or hi_key is None:
        return None
    stats = _volume_stats(path)
    if stats is None or lo_key not in stats or hi_key not in stats:
        return None
    if not stats.get("has_nonzero", 1.0):
        # Matches `_percentiles_from_array`, which answers `None` for a volume with no non-zero
        # voxels rather than the degenerate window [0, 0]. A layer with no window still renders;
        # one windowed [0, 0] shows nothing at all.
        return None
    return float(stats[lo_key]), float(stats[hi_key])


def _resolve_layer_percentile(layer: dict[str, Any]) -> None:
    """Fill *layer*'s ``cal_min``/``cal_max`` from its ``percentile`` window, in place.

    Any failure (missing/unreadable file, an all-zero volume, no ``nibabel``
    in this environment) leaves ``cal_min``/``cal_max`` exactly as they were
    -- a layer with an unresolved threshold still renders, just without a
    ``heatscale`` arg (see :func:`to_freeview_args`).

    Memoised on the file's identity (see :data:`_PERCENTILE_CACHE`). A miss reads the volume
    exactly as before; a hit costs one ``os.stat``.

    **It usually does not read anything at all.** :func:`_volume_stats` computes a fixed set of
    percentiles over the same non-zero voxels of the same file, and persists them to a sidecar --
    so whenever the window asked for here is one of those (and 95/99.9, the Viewer's default, is),
    the answer is already on disk and this function is a lookup. That matters because the two used
    to be *independent* full reads of the same volumes: one resolve of a simulation scene inflated
    every field volume twice, once with ``get_fdata`` (float64) here and once with ``dataobj``
    there, which is most of what "a lot of loading time" was (maintainer, 2026-09-07).
    """
    pct = layer.get("percentile")
    if not pct or (
        layer.get("cal_min") is not None and layer.get("cal_max") is not None
    ):
        return

    key = _percentile_cache_key(layer["path"], pct["lo"], pct["hi"])
    if key is not None:
        with _PERCENTILE_LOCK:
            if key in _PERCENTILE_CACHE:
                _PERCENTILE_CACHE.move_to_end(key)
                cached = _PERCENTILE_CACHE[key]
                if cached is not None:
                    layer["cal_min"], layer["cal_max"] = cached
                return

    # `key is not None` means the file could be stat'ed, which is also what `_volume_stats`
    # needs before it will read anything: a path it cannot stat is one it answers `None` for
    # without trying, so treating that as the authoritative answer would window nothing at all.
    if key is not None and _stats_can_answer(pct["lo"], pct["hi"]):
        # `_volume_stats` computes these exact percentiles over these exact voxels, so it is not a
        # first attempt to be retried on failure -- it is *the* answer. Falling through to a second
        # read here would read the same file twice to fail the same way, which is what the
        # unreadable-volume case would otherwise do.
        from_stats = _percentiles_from_stats(layer["path"], pct["lo"], pct["hi"])
        if from_stats is not None:
            layer["cal_min"], layer["cal_max"] = from_stats
            if key is not None:
                with _PERCENTILE_LOCK:
                    _PERCENTILE_CACHE[key] = from_stats
                    _PERCENTILE_CACHE.move_to_end(key)
                    while len(_PERCENTILE_CACHE) > _PERCENTILE_CACHE_MAX:
                        _PERCENTILE_CACHE.popitem(last=False)
        return

    try:
        import nibabel as nib

        data = nib.load(layer["path"]).get_fdata()
        resolved = _percentiles_from_array(data, pct["lo"], pct["hi"])
    except Exception:  # noqa: BLE001 - never let a bad volume break the viewer
        # Deliberately NOT cached: an unreadable file is usually a transient state (a simulation
        # still writing it), and remembering "this one has no window" would outlive the cause.
        return

    if key is not None:
        with _PERCENTILE_LOCK:
            # An all-zero volume caches as `None`: it is a real, stable answer about the file, and
            # re-reading 17 MB to learn it again on every list edit is the whole defect.
            _PERCENTILE_CACHE[key] = resolved
            _PERCENTILE_CACHE.move_to_end(key)
            while len(_PERCENTILE_CACHE) > _PERCENTILE_CACHE_MAX:
                _PERCENTILE_CACHE.popitem(last=False)

    if resolved is not None:
        layer["cal_min"], layer["cal_max"] = resolved


def resolve_percentiles(spec: dict[str, Any]) -> dict[str, Any]:
    """Resolve every layer's ``percentile`` window to concrete ``cal_min``/
    ``cal_max``, in place, and return *spec*.

    Layers are resolved concurrently on a small thread pool -- reading a
    NIfTI and computing ``numpy.percentile`` both release the GIL for most
    of their time, so a multi-layer ``ViewSpec`` (e.g. TI_max + a high-
    frequency envelope) stays well under the ~2s budget for a 256^3 volume
    even when several layers need a percentile scan at once.
    """
    import concurrent.futures

    pending = [layer for layer in spec.get("layers", []) if layer.get("percentile")]
    if not pending:
        return spec
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(pending))) as ex:
        list(ex.map(_resolve_layer_percentile, pending))
    return spec


# ── Tetravox ViewSpec v2 (docs/dev/HISTORY.md § 2026-09-03 (Docker streamline) §1) ─────────
#
# The scene the in-app viewer loads: a real Tetravox `ViewSpec` (v2, the
# frozen `@tetravox/engine` `scene/types.ts`/`scene/serialize.ts` shape), not
# an approximation of it. `Engine.load(spec, resolve)` hands `spec.datasets`
# to the *caller's* `resolve` function (the embed's own host code, which the
# TI server does not control) and, for every other §4.6 field, restores it
# **verbatim** onto the live scene (`serialize.ts::applyViewSpec`) -- so a
# document this module emits must already carry concrete, engine-shaped
# values for every one of those fields, not a placeholder the client is
# expected to fill in.
#
# Two consequences that shaped this module:
#
# 1. **No percentile-window escape hatch.** A real `Scale` is exactly
#    ``{kind:'linear', lo, hi}`` or ``{kind:'heat', min, mid, max, ...}`` --
#    concrete numbers, not a `{percentile:{lo,hi}}` object the client is
#    supposed to resolve after load (that shape does not exist on this type
#    at all; it was a Stage-0 TI-only invention). So a base/field volume
#    layer's window is resolved **here**, server-side, from
#    :func:`_volume_stats` -- one ``numpy``/``nibabel`` read per file, cached
#    by ``(mtime, size)``, cheap for a single 13-17 MB head volume.
# 2. **No per-file camera fit.** `slices`/`view3d`/`annotations`/
#    `background`/`lighting`/`transparency` are restored exactly as this
#    module writes them (`ROUND_TRIP_FIELDS` in `scene/serialize.ts`), and
#    this server never reads a NIfTI's affine/bounds to compute a "fit to
#    this head" camera. A single fixed, documented default rig
#    (``_DEFAULT_SLICES``/``_DEFAULT_VIEW3D``/…) is used for every scene;
#    the client MAY re-fit after ``loaded`` if it wants to. This is a known
#    v1 limitation, not an oversight.
#
# Intermediate dataset paths use the raw-file API format. Native export validates and
# rewrites them to host filesystem paths, staging bundled reference assets when needed.

RAW_ROUTE_PREFIX = "/api/files/raw/"

VIEWSPEC_VERSION = 2

_MESH_EXTS = (".msh", ".gii")
_STRIPPED_SUFFIXES = (".nii.gz", ".nii", ".msh", ".gii", ".mgz")

# One fixed slice/3D/annotation/background/lighting/transparency rig, reused
# by every scene (see the module note above: this server has no per-file
# camera fit). Values match a normal head-sized framing at the origin, in
# the same units/ranges the real app's own saved scenes use
# (`packages/app/src/shared/scenes/*.tetravox.json` in the tetravox repo).
_DEFAULT_SLICES: list[dict[str, Any]] = [
    {
        "id": "axial",
        "mode": "axial",
        "normal": [0.0, 0.0, 1.0],
        "up": [0.0, 1.0, 0.0],
        "camera": {"center": [0.0, 0.0], "mmPerPx": 0.6},
    },
    {
        "id": "coronal",
        "mode": "coronal",
        "normal": [0.0, -1.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "camera": {"center": [0.0, 0.0], "mmPerPx": 0.6},
    },
    {
        "id": "sagittal",
        "mode": "sagittal",
        "normal": [-1.0, 0.0, 0.0],
        "up": [0.0, 0.0, 1.0],
        "camera": {"center": [0.0, 0.0], "mmPerPx": 0.6},
    },
]
_DEFAULT_VIEW3D: dict[str, Any] = {
    "id": "view3d",
    "camera": {
        "target": [0.0, 0.0, 0.0],
        "distance": 350.0,
        "rotation": [0.0, 0.0, 0.0, 1.0],
        "fovYDeg": 35.0,
        "orthographic": False,
        "near": 1.0,
        "far": 1400.0,
    },
    "showSlicePlanes": False,
}
_DEFAULT_ANNOTATIONS: dict[str, Any] = {
    "orientationLabels": True,
    "cornerInfo": True,
    "conventionBadge": True,
    "scaleBar": True,
    "colorbars": True,
    "crosshair": True,
    "orientationCube": True,
}
_DEFAULT_LIGHTING = {"ambient": 0.25, "headlight": True}
_DEFAULT_TRANSPARENCY = {"mode": "twoPhase"}
_ZERO_THRESHOLD = {
    "lo": None,
    "hi": None,
    "symmetric": False,
    "mode": "clamp",
    "softEdge": 0.0,
}


def _scene_raw_url(path: str) -> str:
    """``/api/files/raw/<absolute path without its leading slash>``.

    Path-shaped, not ``?path=``, so the URL's last segment is the real file
    name: the engine's worker keys both gzip inflation and its volume-vs-mesh
    routing off that basename (r1 §3.4).
    """
    from urllib.parse import quote

    return RAW_ROUTE_PREFIX + quote(str(path).lstrip("/"))


def _scene_stem(name: str) -> str:
    for suffix in _STRIPPED_SUFFIXES:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name


def _scene_slug(name: str) -> str:
    slug = "".join(c if c.isalnum() else "_" for c in _scene_stem(name).lower())
    return slug.strip("_") or "layer"


def _scene_is_mesh(path: str) -> bool:
    return path.lower().endswith(_MESH_EXTS)


def _scene_role(path: str, colormap: str) -> str:
    """``base | field | atlas | electrodes | mesh``, this module's own routing key.

    Not a field of the real ``ViewSpec`` (``LayerBase`` has no ``role``) --
    used only internally to pick a layer's colormap/interpolation/showIn3D.
    """
    name = os.path.basename(path).lower()
    if _scene_is_mesh(path):
        return "mesh"
    if colormap == "lut":
        return "electrodes" if name.startswith("electrode_overlay") else "atlas"
    if colormap in ("heat", "jet"):
        return "field"
    return "base"


#: The field tokens SimNIBS puts at the **end** of a volume's basename. Longest-first, so
#: `TI_normal` is not shadowed by a shorter token that is also a suffix of it.
_VOLUME_FIELD_TOKENS = (
    "mTI_normal",
    "mTI_max",
    "TI_normal",
    "TI_max",
    "hf_peak",
    "hf_sar",
    "magnE",
    "normE",
)


def _scene_field_name(name: str) -> str | None:
    """The physical field a layer represents, guessed from its basename.

    Used both for a ``.msh`` layer's colour-by field (the real field names
    live inside the mesh, which the server deliberately never reads -- a
    field ``.msh`` here is 24-420 MB) and, since QA researcher finding #4
    (``qa-neuro-researcher-notes.md``), a NIfTI field volume's curated
    display name (:func:`_scene_display_name`). The basenames SimNIBS writes
    are unambiguous enough for the default -- ``*_TI.msh`` /
    ``*_TI_subject_TI_max.nii.gz`` carry ``TI_max``, ``*_normal.msh`` carries
    ``TI_normal``, an mTI simulation's outputs carry ``mTI_max``, and the
    high-frequency ``*_TDCS_*_scalar*.msh``/``*_scalar_*magnE.nii.gz`` carry
    ``magnE`` -- and the client can always re-pick from the engine's own
    ``MeshDataset.fields`` after load. ``None`` means "colour by tag/solid"
    for a mesh, or "no recognised field" for a volume (e.g. an analysis ROI
    overlay).
    """
    stem = _scene_stem(name)
    lowered = stem.lower()

    # A **volume** says which field it is in its last token, and that is what to read. The loose
    # substring chain below is wrong for one: `L_Insula_TI_subject_hf_peak.nii.gz` contains "ti"
    # (twice) and was answered `TI_max`, so a simulation's TI_max, hf_peak and hf_sar volumes all
    # came out named "TI_max (volume)" -- three identical rows in the Layers list and, once the
    # composition tree existed, three identical checkboxes (screenshot, 2026-09-07). Matching the
    # trailing token instead is both correct and narrower.
    for field in _VOLUME_FIELD_TOKENS:
        if lowered.endswith(f"_{field.lower()}") or lowered == field.lower():
            return field

    # A **mesh** genuinely carries no trailing field token -- `grey_L_Insula_TI.msh`,
    # `..._normal.msh`, `..._TDCS_1_scalar.msh` -- so the hint chain stays, but *only* for meshes.
    # Letting a volume reach it is what made `final_tissues.nii.gz` a "TI_max" layer: "tissues"
    # contains "ti". A volume whose last token names no field simply has none, which is what this
    # function's docstring has always said `None` means for a volume.
    if not _scene_is_mesh(name):
        return None
    if "magne" in lowered or "tdcs" in lowered:
        return "magnE"
    if "normal" in lowered:
        return "TI_normal"
    if "mti" in lowered:
        return "mTI_max"
    if "ti" in lowered:
        return "TI_max"
    return None


def _scene_display_name(name: str, *, role: str, field_name: str | None) -> str:
    """A curated layer name for the inspector's Layers list.

    Replaces the raw pipeline basename (``grey_Thalamus_TI_subject_TI_max``,
    ``grey_Thalamus_TI``) that used to be the entire explanation a viewer got
    for what a layer was (QA researcher finding #4,
    ``qa-neuro-researcher-notes.md``: "raw layer names" -- two visually
    near-identical rows, a mesh and a NIfTI carrying the same field under
    different colormaps, un-glossed). Built from the role
    :func:`_scene_role` already computed plus SimNIBS's own basename grammar:
    a ``grey_``/``white_`` prefix means the field was masked to the grey- or
    white-matter surface, and :func:`_scene_field_name` names the physical
    quantity. ``T1``, ``Electrodes`` and ``Atlas`` are fixed (each occurs at
    most once per scene, so the role alone is unambiguous). Anything that
    matches none of these known shapes (e.g. an analysis ROI overlay, or a
    ``custom``-view file outside the pipeline's own naming) keeps today's
    plain basename stem -- this only replaces names once understood, never
    invents one for a shape it does not recognise. The dataset's own
    ``name`` field is untouched (:func:`_dataset_ref`): it always keeps the
    real basename, which the raw-URL route and gzip/mesh sniffing depend on.
    """
    stem = _scene_stem(name)
    lowered = stem.lower()

    if role == "electrodes":
        return "Electrodes"
    if role == "atlas":
        return "Atlas"
    if role == "base" and (lowered == "t1" or lowered.startswith("t1_")):
        return "T1"

    if role in ("mesh", "field"):
        if lowered.startswith("grey_"):
            region = "GM"
        elif lowered.startswith("white_"):
            region = "WM"
        else:
            region = None

        # A high-frequency simulation writes one output *per electrode pair*
        # (`101_TDCS_1_scalar_subject_magnE`, `..._TDCS_2_...`), so without the pair number two
        # rows come out identically named -- "magnE (volume)" twice, and "Mesh mesh · magnE" twice
        # at 412 MB each, with nothing to choose between them (screenshot, 2026-09-07).
        pair = re.search(r"_tdcs_(\d+)_", lowered)
        suffix = f" · pair {pair.group(1)}" if pair else ""

        if role == "mesh":
            # "Head", not "Mesh": `region_label` is already followed by the word "mesh", and
            # "Mesh mesh · TI_max" is a stutter that reads as a bug.
            region_label = region or "Head"
            return (
                f"{region_label} mesh · {field_name}{suffix}"
                if field_name
                else f"{region_label} mesh (tags){suffix}"
            )
        if field_name:
            return (
                f"{region} · {field_name}{suffix} (volume)"
                if region
                else f"{field_name}{suffix} (volume)"
            )

    return stem


# path -> (mtime, size, stats). Process-lifetime cache: a NIfTI is re-read
# only when it changes on disk, so building several views of the same
# simulation in a row (subject -> simulation -> analysis) costs one read.
_stats_cache: dict[str, tuple[float, int, dict[str, float]]] = {}

#: Version of the :func:`_volume_stats` payload. Bump when a key is added or its meaning changes:
#: an on-disk sidecar written by an older toolbox is then ignored and recomputed rather than
#: silently answering a question it was never asked (e.g. a sidecar from before ``p2``/``p98``
#: existed would otherwise window every T1 at ``None``).
_STATS_VERSION = 2

#: Statistics keys every current sidecar must carry to be usable.
_STATS_KEYS = (
    "min",
    "max",
    "nz_lo",
    "p2",
    "p50",
    "p95",
    "p98",
    "p99",
    "p999",
    "nz_hi",
    "abs_p99",
    "has_nonzero",
)


def stats_cache_dir() -> str | None:
    """Where the on-disk statistics sidecars live, or ``None`` with no project open.

    ``<project>/code/ti-toolbox/viewer/cache``. Beside the scene documents the Viewer already
    writes, for the same reason they live there: the project is the unit people copy and archive,
    and a window computed from a file belongs with that file's project rather than in a home
    directory that does not travel with it.
    """
    try:
        project = get_path_manager().project_dir
    except Exception:  # noqa: BLE001 - a statistics cache must never break a view
        return None
    if not project:
        return None
    directory = os.path.join(str(project), "code", "ti-toolbox", "viewer", "cache")
    if not is_within(str(project), directory):
        return None
    return os.path.realpath(directory)


def _stats_sidecar_path(path: str) -> str | None:
    """The sidecar file for *path*, or ``None`` with no project open.

    Named by a hash of the absolute path rather than mirroring the tree: two projects can mount
    the same derivatives directory at different absolute paths, and the sidecar has to be keyed by
    the path the reader actually opened.
    """
    directory = stats_cache_dir()
    if directory is None:
        return None
    digest = hashlib.sha256(os.path.abspath(path).encode("utf-8")).hexdigest()[:32]
    target = os.path.join(directory, f"{digest}.stats.json")
    project = get_path_manager().project_dir
    if not project or not is_within(project, target):
        return None
    # Keep a checked leaf alias: replacement must replace the alias, not its target.
    return os.path.join(
        os.path.realpath(os.path.dirname(target)), os.path.basename(target)
    )


def _read_stats_sidecar(path: str, st: os.stat_result) -> dict[str, float] | None:
    """The sidecar's statistics for *path* if it describes *this* version of the file.

    Invalidated by ``(size, mtime_ns)`` -- ``mtime_ns`` rather than ``mtime`` because a simulation
    can rewrite a volume inside one filesystem-clock tick -- and by ``_STATS_VERSION``. Any
    unreadable, truncated or hand-edited sidecar is a miss, never an error: the cost of a miss is
    one volume read, and the cost of trusting a bad one is a wrong window on screen.
    """
    target = _stats_sidecar_path(path)
    if target is None:
        return None
    try:
        with open(target, encoding="utf-8") as handle:
            body = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    if body.get("version") != _STATS_VERSION:
        return None
    if body.get("size") != st.st_size or body.get("mtime_ns") != st.st_mtime_ns:
        return None
    stats = body.get("stats")
    if not isinstance(stats, dict) or not all(k in stats for k in _STATS_KEYS):
        return None
    try:
        return {k: float(v) for k, v in stats.items()}
    except (TypeError, ValueError):
        return None


def _write_stats_sidecar(
    path: str, st: os.stat_result, stats: dict[str, float]
) -> None:
    """Persist *stats* beside the project, best-effort.

    Best-effort on purpose: a read-only project, a full disk or a race with another process are
    all reasons to have no sidecar, and none of them is a reason to fail a view. Written whole and
    renamed so a concurrent reader never parses half a document.
    """
    target = _stats_sidecar_path(path)
    if target is None:
        return
    document = {
        "version": _STATS_VERSION,
        "path": os.path.abspath(path),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "stats": stats,
    }
    temporary = None
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        candidate = os.path.join(
            os.path.dirname(target), f".stats-{secrets.token_hex(16)}.partial"
        )
        with open(candidate, "x", encoding="utf-8") as handle:
            temporary = candidate
            json.dump(document, handle)
        os.replace(temporary, target)
    except OSError:
        return
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _volume_stats(path: str) -> dict[str, float] | None:
    """min/max and a few percentiles of *path*'s non-zero voxels, or ``None``.

    The one place this module reads voxel data -- deliberately: a real
    ``Scale`` needs concrete numbers (see the module note above). Any failure (missing file,
    unreadable, no numpy/nibabel in this environment, an all-zero/all-NaN volume) yields ``None``
    rather than raising; callers fall back to a documented generic range.

    **Two caches, because one was not enough** (maintainer, 2026-09-07: "there is still a lot of
    loading time once the user starts manipulating the input data"). Reading a simulation's five
    volumes costs ~16 s -- ``nibabel`` inflates the whole gzip stream and ``numpy`` sorts it for
    each percentile -- and the in-process ``_stats_cache`` made that cost *once per server
    process*. Under ``--reload``, and on every app start, that is once per sitting: exactly the
    wait a person notices. So the same answer is also written to an on-disk sidecar
    (:func:`stats_cache_dir`), which survives the process. A file that has not changed has the
    same statistics, so the sidecar is keyed by ``(size, mtime_ns)`` and needs no invalidation
    hook.

    Nothing here is sampled. A percentile taken from a subsample is a different number, and the
    window it produces is what the reader actually sees.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    cached = _stats_cache.get(path)
    if cached is not None and cached[0] == st.st_mtime and cached[1] == st.st_size:
        return cached[2]

    from_disk = _read_stats_sidecar(path, st)
    if from_disk is not None:
        _stats_cache[path] = (st.st_mtime, st.st_size, from_disk)
        return from_disk

    try:
        import nibabel as nib
        import numpy as np

        image = nib.load(path)
        data = np.asarray(image.dataobj)
        affine = np.asarray(image.affine, dtype=float)
    except Exception:  # noqa: BLE001 - never let an unreadable volume break the scene
        return None
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return None
    nonzero = finite[finite != 0]
    sample = nonzero if nonzero.size else finite
    p0, p2, p50, p95, p98, p99, p999, p100 = np.percentile(
        sample, [0, 2, 50, 95, 98, 99, 99.9, 100]
    )
    stats = {
        "min": float(finite.min()),
        "max": float(finite.max()),
        "nz_lo": float(p0),
        "p2": float(p2),
        "p50": float(p50),
        "p95": float(p95),
        "p98": float(p98),
        "p99": float(p99),
        "p999": float(p999),
        "nz_hi": float(p100),
        # Whether the percentiles above describe *non-zero* voxels or a volume that has none.
        # An all-zero volume is a real, stable answer about a file -- a simulation that produced
        # nothing in this tissue, say -- but its window is [0, 0], which is not a window. Callers
        # need to tell that apart from a genuinely constant non-zero volume, and only this read
        # knows which it was.
        "has_nonzero": 1.0 if nonzero.size else 0.0,
    }
    # A signed statistic map is windowed symmetrically about zero, so its window needs the 99th
    # percentile of |value| -- not of the signed values, whose 99th percentile says nothing about
    # how far the negative tail runs.
    stats["abs_p99"] = float(np.percentile(np.abs(sample), 99))
    # Where the volume peaks, in world RAS mm. Free here (the array is already in memory and the
    # affine is the header's) and it is what puts the crosshair on the hotspot instead of on the
    # scanner origin, which for a subject-space head volume is a corner of the field of view.
    # Computed on a NaN-safe copy: `argmax` on an array with a NaN answers the NaN.
    try:
        safe = np.nan_to_num(data, nan=-np.inf, posinf=-np.inf, neginf=-np.inf)
        ijk = np.unravel_index(int(np.argmax(safe)), safe.shape[:3])
        world = affine @ np.array(
            [float(ijk[0]), float(ijk[1]), float(ijk[2]), 1.0], dtype=float
        )
        if np.all(np.isfinite(world[:3])):
            stats["max_x"] = float(world[0])
            stats["max_y"] = float(world[1])
            stats["max_z"] = float(world[2])
    except Exception:  # noqa: BLE001 - a missing hotspot is a default cursor, not a failure
        pass
    _stats_cache[path] = (st.st_mtime, st.st_size, stats)
    _write_stats_sidecar(path, st, stats)
    return stats


# path -> (mtime, size, bounds). Same shape and lifetime as `_stats_cache`, and cleared with it.
# A header read is milliseconds rather than seconds, but it is milliseconds on *every* resolve of
# *every* layer, and the warm resolve this whole change exists to produce is ~14 ms in total.
_bounds_cache: dict[str, tuple[float, int, tuple[list[float], list[float]] | None]] = {}


def _volume_bounds(path: str) -> tuple[list[float], list[float]] | None:
    """*path*'s world-RAS bounding box as ``(min_xyz, max_xyz)``, from the **header alone**.

    No voxel is read: the eight corners of the voxel grid are pushed through the affine and the
    extremes taken. That matters because this is on the resolve path -- inflating a 240x512x512
    float volume to learn how big it is would cost about a second per file for an answer the
    header already gives exactly.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    cached = _bounds_cache.get(path)
    if cached is not None and cached[0] == st.st_mtime and cached[1] == st.st_size:
        return cached[2]
    bounds = _read_volume_bounds(path)
    _bounds_cache[path] = (st.st_mtime, st.st_size, bounds)
    return bounds


def _read_volume_bounds(path: str) -> tuple[list[float], list[float]] | None:
    """:func:`_volume_bounds` without the cache."""
    try:
        import nibabel as nib
        import numpy as np

        image = nib.load(path)
        shape = tuple(int(n) for n in image.shape[:3])
        affine = np.asarray(image.affine, dtype=float)
    except Exception:  # noqa: BLE001 - an unmeasurable volume just does not vote on the fit
        return None
    if len(shape) < 3 or any(n <= 0 for n in shape):
        return None
    # Voxel *centres* run 0..n-1; the grid's outer face is half a voxel beyond each end.
    lo = [-0.5, -0.5, -0.5]
    hi = [shape[0] - 0.5, shape[1] - 0.5, shape[2] - 0.5]
    corners = []
    for i in (lo[0], hi[0]):
        for j in (lo[1], hi[1]):
            for k in (lo[2], hi[2]):
                corners.append([i, j, k, 1.0])
    world = (affine @ np.asarray(corners, dtype=float).T).T[:, :3]
    if not bool(np.all(np.isfinite(world))):
        return None
    return ([float(v) for v in world.min(axis=0)], [float(v) for v in world.max(axis=0)])


def _scene_bounds(paths: list[str]) -> tuple[list[float], list[float]] | None:
    """The union of every readable volume's world bounding box, or ``None``."""
    lo: list[float] | None = None
    hi: list[float] | None = None
    for path in paths:
        if _scene_is_mesh(path):
            # A .msh's extent lives in its 24-420 MB body; the sibling volumes cover the same head.
            continue
        box = _volume_bounds(path)
        if box is None:
            continue
        if lo is None or hi is None:
            lo, hi = list(box[0]), list(box[1])
        else:
            lo = [min(a, b) for a, b in zip(lo, box[0])]
            hi = [max(a, b) for a, b in zip(hi, box[1])]
    if lo is None or hi is None:
        return None
    return lo, hi


#: The 2D pane size the server fits for, in pixels (the short edge).
#:
#: The server cannot know the real pane size -- the window has not been laid out when the scene is
#: written, and the same scene file is opened later at whatever size the app happens to be. 512 is
#: the engine's *own* fallback for exactly this situation (``engine.ts#onFirstDataset``, when no
#: rect has been measured yet), so fitting for it puts the scene at the zoom the engine would have
#: chosen itself, and the reader's first wheel notch moves from there rather than from a default
#: that ignores the data entirely.
_FIT_PANE_PX = 512


def _fit_mm_per_px(bounds: tuple[list[float], list[float]], px: int) -> float:
    """The engine's own 2D fit, recomputed server-side.

    Deliberately identical to ``@tetravox/engine``'s ``fitMmPerPx``
    (``packages/engine/src/view/geometry.ts``): ``max(0.05, diag * 0.62 / px)``. It is duplicated
    rather than approximated because the number this returns is the one the engine treats as the
    pane's *fit reference* -- the zero point its corner ``ZOOM`` readout and its ``r`` reset both
    measure from (``engine.ts::setView``). A close-but-different number would make a freshly
    opened scene read as already zoomed.

    **Why the server has to send this at all.** The engine fits a pane only in
    ``#onFirstDataset``, and only when ``datasets.size === 1``. Every scene this module writes
    carries four or five datasets, so that branch never runs and every pane kept the default
    0.5 mm/px -- which is what "the head is a small square in each pane" was (maintainer,
    2026-09-07).
    """
    lo, hi = bounds
    diag = math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])
    return max(0.05, (diag * 0.62) / max(1, px))


def _fit_camera(
    camera: dict[str, Any], bounds: tuple[list[float], list[float]]
) -> dict[str, Any]:
    """The engine's ``fitCamera`` for the 3D pane: target the box, back off to contain it.

    Mirrors ``packages/engine/src/view/geometry.ts::fitCamera`` --
    ``distance = radius / sin(fovY/2)``, ``near = max(1, fitRadius/1000)``, ``far = radius * 8``.
    """
    lo, hi = bounds
    center = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    radius = max(1.0, 0.5 * math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]))
    fov = float(camera.get("fovYDeg", 35.0))
    distance = radius / max(1e-3, math.sin(math.radians(fov) * 0.5))
    return {
        **camera,
        "target": center,
        "distance": distance,
        "near": max(1.0, radius / 1000.0),
        "far": radius * 8.0,
    }


def prefetch_volume_stats(paths: list[str]) -> None:
    """Warm :func:`_volume_stats` for *paths* concurrently.

    Reading a NIfTI and computing a percentile both release the GIL for nearly all of their time,
    so the four volumes of a typical simulation scene cost about as long as the slowest one rather
    than the sum of all four. This is the *cold* half of the fix; the sidecar is the warm half.
    """
    import concurrent.futures

    pending = [p for p in dict.fromkeys(paths) if not _scene_is_mesh(p)]
    if len(pending) < 2:
        for path in pending:
            _volume_stats(path)
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(pending))) as ex:
        list(ex.map(_volume_stats, pending))


#: Basename markers of a **signed statistic** map -- a t-map, a z-map, a Cohen's d, a paired
#: difference. Such a volume is not a field magnitude: its sign carries the finding, so a heat
#: window anchored at a positive percentile with ``negative: 'hide'`` would delete exactly half
#: the result. These get a symmetric window about zero instead (see :func:`_volume_window`).
_STAT_MAP_MARKERS = (
    "_tstat",
    "_tmap",
    "_t_map",
    "tstat_",
    "_zstat",
    "_zmap",
    "_z_map",
    "cohens_d",
    "cohen_d",
    "_diff",
    "_difference",
)


def _is_stat_map(path: str) -> bool:
    """Whether *path*'s basename marks it a signed statistic map."""
    name = os.path.basename(path).lower()
    return any(marker in name for marker in _STAT_MAP_MARKERS)


def _volume_window(path: str, *, role: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """A concrete engine ``(Scale, Threshold)`` pair for one volume layer.

    The defaults a scene opens at, and the reason this function exists at all (maintainer,
    2026-09-07: "for some reason it provides it with some very strange defaults ... it would be
    much more reasonable to set more logical thresholds, for example 95 to 99.9 of the electric
    field"). One rule per kind of thing a layer can be:

    **field** -- TI_max, TI_normal, mTI_max, an E-field magnitude. ``{kind:'heat'}`` windowed
    ``[p95, p99.9]`` of the non-zero voxels, with ``threshold.lo = p95`` and ``mode: 'hide'`` so
    everything below the 95th percentile is transparent rather than a wash of low colour over the
    whole head. This is the change: the window used to open at ``min = nz_lo``, the smallest
    non-zero voxel in the file -- ``5.08e-09`` V/m for ``sub-101/L_Insula`` -- which is not a
    threshold at all, it is "show every voxel that is not exactly zero", and it is why the
    overlay covered the brain uniformly. ``mid`` sits at the midpoint of the visible window, which
    is what makes the colour ramp span it rather than saturate at one end.

    **stat** -- a signed t/z/d map (:func:`_is_stat_map`). Symmetric ``[-|v|p99, +|v|p99]``, linear,
    ``negative`` kept: the sign is the finding.

    **base** -- the T1. ``[p2, p98]`` rather than the file's own ``[min, max]``. A T1's max is a
    handful of bright scalp-fat or artefact voxels (3238 for ``sub-101``, against a p98 near 900),
    so windowing to the full range makes the brain read as uniform dark grey -- the "very strange
    defaults" complaint applies to the anatomy as much as to the overlay.

    **atlas / electrodes** -- a label volume, windowed at its exact ``[min, max]``. Deliberately
    *not* percentile-windowed: these are integer region indices addressed through a LUT, and a
    window that clips them makes two different regions the same colour.

    A file :func:`_volume_stats` could not read falls back to a generic, documented placeholder
    range rather than failing the whole scene.
    """
    stats = _volume_stats(path)
    if stats is not None and not stats.get("has_nonzero", 1.0):
        # Every voxel is zero, so every percentile is zero and every window derived from them has
        # zero width -- which renders nothing at all. Treat it exactly like a file that could not
        # be read: fall back to the documented generic range, so the layer is still there to be
        # windowed by hand.
        stats = None

    if role == "field" and _is_stat_map(path):
        role = "stat"

    if role == "field":
        if stats is None:
            return (
                {
                    "kind": "heat",
                    "min": 0.0,
                    "mid": 0.5,
                    "max": 1.0,
                    "truncate": False,
                    "inverse": False,
                    "negative": "hide",
                },
                dict(_ZERO_THRESHOLD),
            )
        lo = stats["p95"]
        hi = stats["p999"] if stats["p999"] > lo else stats["max"]
        if not hi > lo:
            # A near-constant field (or a mask): fall back to the file's own range so the layer
            # still renders instead of collapsing to a zero-width window that shows nothing.
            lo, hi = stats["nz_lo"], stats["max"]
        return (
            {
                "kind": "heat",
                "min": lo,
                "mid": (lo + hi) / 2.0,
                "max": hi,
                "truncate": False,
                "inverse": False,
                "negative": "hide",
            },
            {
                "lo": lo,
                "hi": None,
                "symmetric": False,
                # `hide`, not `clamp`: clamping paints every sub-threshold voxel at the bottom
                # colour, which is the wash. `hide` makes them transparent. EMBED.md §(a) uses
                # exactly this pair for a heat field layer.
                "mode": "hide",
                "softEdge": 0.0,
            },
        )

    if role == "stat":
        extent = 1.0
        if stats is not None:
            extent = stats.get("abs_p99") or max(abs(stats["min"]), abs(stats["max"]))
        if not extent > 0:
            extent = 1.0
        return (
            {"kind": "linear", "lo": -extent, "hi": extent},
            dict(_ZERO_THRESHOLD),
        )

    if stats is None:
        return ({"kind": "linear", "lo": 0.0, "hi": 1.0}, dict(_ZERO_THRESHOLD))

    if role == "base":
        lo, hi = stats["p2"], stats["p98"]
        if not hi > lo:
            lo, hi = stats["min"], stats["max"]
        return ({"kind": "linear", "lo": lo, "hi": hi}, dict(_ZERO_THRESHOLD))

    return (
        {"kind": "linear", "lo": stats["min"], "hi": stats["max"]},
        dict(_ZERO_THRESHOLD),
    )


#: Tissue prefixes SimNIBS puts on both a masked field volume and the matching surface mesh.
_TISSUE_PREFIXES = ("grey_", "gray_", "white_")


def _tissue_prefix(name: str) -> str | None:
    """``grey_`` for ``grey_L_Insula_TI.msh``, ``None`` for a whole-head file."""
    lowered = name.lower()
    for prefix in _TISSUE_PREFIXES:
        if lowered.startswith(prefix):
            # `gray_`/`grey_` are the same tissue spelled two ways; normalise so a `gray_` mesh
            # still finds its `grey_` volume.
            return "grey_" if prefix in ("grey_", "gray_") else prefix
    return None


def _bounds_for_mesh(
    mesh_name: str, field_volumes: list[dict[str, Any]]
) -> tuple[float, float] | None:
    """The window for a mesh layer: **its own tissue's** volume, not just the first field found.

    A field ``.msh`` is 24-420 MB, so its element values are never read (see
    :func:`_mesh_scale_and_threshold`) and the window is borrowed from the sibling NIfTI carrying
    the same physical field. *Which* sibling matters more than it looks. A simulation scene holds
    the whole-head field **and** its grey- and white-matter masked copies, whose ranges differ by
    an order of magnitude -- ``sub-101/L_Insula`` is ``[0.254, 3.34]`` whole-head against
    ``[0.087, 0.139]`` in grey matter. Borrowing the first one found put the GM surface's entire
    value range below the bottom of its own colour ramp, and the mesh rendered a uniform blue with
    every element under its threshold (screenshot, 2026-09-07).

    So: match the tissue prefix first (``grey_L_Insula_TI.msh`` -> ``grey_..._TI_max.nii.gz``),
    fall back to the visible field layer, then to any field layer at all.
    """
    if not field_volumes:
        return None

    def window(layer: dict[str, Any]) -> tuple[float, float]:
        scale, _ = _volume_window(layer["path"], role="field")
        if scale["kind"] == "heat":
            return float(scale["min"]), float(scale["max"])
        return float(scale["lo"]), float(scale["hi"])

    prefix = _tissue_prefix(mesh_name)
    if prefix is not None:
        for layer in field_volumes:
            if _tissue_prefix(os.path.basename(layer["path"])) == prefix:
                return window(layer)

    for layer in field_volumes:
        if layer.get("visible", True):
            return window(layer)
    return window(field_volumes[0])


def _mesh_scale_and_threshold(
    field_bounds: tuple[float, float] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """A ``MeshLayer``'s ``scale``/``threshold``, approximated from *field_bounds*.

    *field_bounds* is the sibling NIfTI field layer's own resolved
    ``(nz_lo, p999-or-max)`` (:func:`_volume_scale`'s heat window) -- the mesh
    carries the *same physical field*, voxelised, so its element-wise value
    range is not read separately (a field ``.msh`` is 24-420 MB; see
    :func:`_scene_field_name`'s docstring for the same trade). ``None`` when
    no such sibling was found (e.g. the ``custom`` view kind opened a bare
    mesh) falls back to a generic ``[0, 1]``. The 1.5x threshold headroom
    mirrors the ratio the tetravox app's own saved ``ernie-ti.tetravox.json``
    fixture carries (scale max 0.13, threshold hi 0.2).
    """
    if field_bounds is None:
        lo, hi = 0.0, 1.0
    else:
        lo, hi = field_bounds
    return (
        {"kind": "linear", "lo": lo, "hi": hi},
        {
            # The same p95 floor the sibling volume layer gets, for the same reason: the mesh
            # carries the same field, and a surface coloured from zero is a surface where the
            # hotspot is one shade among many. `hi` stays open (`null` reads back as +Infinity)
            # so nothing above the window is deleted, only compressed to the top colour.
            "lo": lo,
            "hi": None,
            "symmetric": False,
            "mode": "clamp",
            "softEdge": 0.0,
        },
    )


#: Tetravox's own `SURFACE_CONTOUR_PALETTE` first entry (`scene/defaults.ts`) -- Freeview yellow.
#: Used for both `solidColor` and `contourColor`, which is what `defaultSurfaceLayer` does, so a
#: scene the server built and a surface a person dropped on the app look the same.
_SURFACE_COLOR = [1.0, 0.9, 0.15, 1.0]


def _attachment_field_name(path: str) -> str:
    """The node-field name an attached file becomes on its surface's dataset.

    **The file name, extension and all** -- ``lh.ernie_DK40.annot``, not ``lh.ernie_DK40`` and
    never a role word like ``annotation``. The embed names the field after the file it attached,
    and this is the embed lane's stated contract (2026-09-07), so it is a fact about the far end
    rather than a choice made here.

    Worth stating because getting it wrong is invisible from this side: the sidecar loads, the
    ``loaded`` event is a success, and the surface comes back solid-coloured with the parcellation
    attached but unselected. Only ``colorMode`` on the embed's own ``layers`` event says so, which
    is what the real spec asserts on.
    """
    return os.path.basename(path)


def _surface_layer(
    name: str, attachments: list[str], index: int
) -> dict[str, Any]:
    """The ``kind: "surface"`` half of a layer — Tetravox 0.4.0's own schema (§4.4, §7.4).

    **One colour source at a time**, which is the engine's rule and not ours: ``solid`` for a bare
    sheet, ``annotation`` when a ``.annot`` is attached, ``overlay`` when a scalar is. An
    annotation wins over a scalar when both are ticked, because a parcellation is what a person
    ticks a surface *for*; the other stays attached and one click away in the app's own panel.

    ``annotation.name`` / ``overlay.name`` are **node-field names, not paths**: the worker names
    the field after the file it attached, so the stem is the name. This is the one thing in this
    function that is a convention rather than a schema, and it is the thing to re-check against
    the embed lane's `attachField` reply -- a wrong name leaves the surface solid-coloured with
    the data attached but unselected, which is recoverable in the app, rather than broken.

    Deliberately **not** emitted: ``tagStyle``, ``fillIn2D`` and clip ``caps``, all of which a
    mesh layer carries and a surface must not (§7.4: a sheet has no interior to cap). Its
    2-D presence is an outline, which is why ``contoursIn2D`` is on.
    """
    annotation = next(
        (a for a in attachments if classify_view_file(a) == "annotation"), None
    )
    scalar = next(
        (a for a in attachments if classify_view_file(a) in ("morph", "surface-data")),
        None,
    )
    if annotation is not None:
        color_mode = "annotation"
    elif scalar is not None:
        color_mode = "overlay"
    else:
        color_mode = "solid"

    layer: dict[str, Any] = {
        "kind": "surface",
        "colorMode": color_mode,
        "solidColor": list(_SURFACE_COLOR),
        "colormap": "viridis",
        # A sheet's own values (curvature, thickness) have no pipeline-wide range the way a field
        # volume does, and this server reads no vertex data -- so the engine's own default window
        # is left in place rather than a number invented here.
        "scale": {"kind": "linear", "lo": 0.0, "hi": 1.0},
        "threshold": {
            "lo": 0.0,
            "hi": None,
            "symmetric": False,
            "mode": "clamp",
            "softEdge": 0.0,
        },
        "flatShading": False,
        "faceMode": "cull",
        "edges": False,
        "edgeColor": [0.0, 0.0, 0.0, 1.0],
        "edgeWidthPx": 1.0,
        "clip": {"planes": []},
        "contoursIn2D": True,
        "contourWidthPx": 1.5,
        "contourColor": list(_SURFACE_COLOR),
    }
    if annotation is not None:
        layer["annotation"] = {
            "name": _attachment_field_name(annotation),
            # Outline, not fill: the surface is usually shown *under* a field, and a filled
            # parcellation would be the only thing anybody saw.
            "mode": "outline",
            "outlineWidthPx": 1.5,
        }
        # A parcellation has no continuous scale, so a colorbar for it would be a ramp with no
        # meaning (Tetravox's own `showAttached` clears it for the same reason).
        layer["showColorbar"] = False
    elif scalar is not None:
        layer["overlay"] = {
            "name": _attachment_field_name(scalar),
            "component": "mag",
        }
    return layer


def _dataset_ref(path: str, index: int) -> dict[str, Any]:
    url = _scene_raw_url(path)
    # `surface` is an alias of `mesh` on the engine side -- a surface *is* a mesh dataset, one
    # with no tetrahedra -- so either loads. It is written because a scene is also a document
    # someone reads, and `kind: "mesh"` on a row called `lh.central.gii` is the exact confusion
    # this whole change is about.
    if classify_view_file(path) == "surface":
        kind = "surface"
    elif _scene_is_mesh(path):
        kind = "mesh"
    else:
        kind = "volume"
    return {
        "id": f"ds{index}",
        "kind": kind,
        "name": os.path.basename(path),
        "path": url,
        "absPath": url,
        "fingerprint": "",
    }


def _relative_sidecar_path(surface_path: str, attachment: str) -> str:
    """*attachment* as the embed addresses it: relative to the **surface's** directory.

    Both addressings of a scene (`/api/files/raw/...` URLs for the embed, host paths for the
    desktop app) re-root every absolute path they carry. A relative path needs neither and is
    correct in both, which is why the embed lane asks for one -- it is the only field in a scene
    that survives the re-rooting untouched.
    """
    return os.path.relpath(attachment, os.path.dirname(surface_path))


def _sidecar_ref(path: str) -> dict[str, str]:
    url = _scene_raw_url(path)
    return {"path": url, "absPath": url}


def to_tetravox_viewspec(spec: dict[str, Any]) -> dict[str, Any]:
    """The real Tetravox ``ViewSpec`` (v2) for an already-resolved *spec* (pure I/O-wise).

    Every file, LUT, colormap, opacity and visibility comes from
    ``spec["layers"]``, which :func:`build_view` already decided -- this
    function only reshapes that decision into the engine's vocabulary (plus
    the read-only voxel-statistics lookups documented on
    :func:`_volume_stats`/:func:`_volume_scale`). A hidden layer's dataset
    carries no special "lazy" marker (unlike the retired ``TitScene``): a
    real ``DatasetRef`` has no such field, and the embed's own host code
    decides when to fetch each dataset from ``ViewSpec.layers[].visible``.

    Validated against ``contracts/tetravox-viewspec-v2.schema.json`` (the
    hand-written subset this function emits) by
    ``tests/test_viewspec_scene.py``.
    """
    layer_specs = spec.get("layers", [])

    # Read every volume's statistics **at once** rather than one at a time down the layer loop.
    # Each read is an inflate-plus-sort that releases the GIL, so four of them cost about as long
    # as the slowest rather than the sum -- and after the first time they cost a sidecar read.
    prefetch_volume_stats([layer["path"] for layer in layer_specs])

    # A sibling NIfTI field layer's resolved window, reused as the mesh's own
    # approximate scale/threshold (see _mesh_scale_and_threshold), and the volume whose peak the
    # crosshair is placed on.
    field_volumes: list[dict[str, Any]] = [
        layer
        for layer in layer_specs
        if not _scene_is_mesh(layer["path"])
        and _scene_role(layer["path"], layer.get("colormap", "grayscale")) == "field"
        and _volume_stats(layer["path"]) is not None
    ]

    field_peak: list[float] | None = None
    for layer in field_volumes:
        stats = _volume_stats(layer["path"])
        if stats is not None and all(k in stats for k in ("max_x", "max_y", "max_z")):
            field_peak = [stats["max_x"], stats["max_y"], stats["max_z"]]
            break

    datasets: list[dict[str, Any]] = []
    layers: list[dict[str, Any]] = []

    for index, layer in enumerate(layer_specs):
        path = layer["path"]
        name = os.path.basename(path)
        colormap = layer.get("colormap", "grayscale")
        role = _scene_role(path, colormap)
        # A `.gii` sheet used to reach the mesh branch, because `_scene_role` calls anything with
        # a mesh extension a mesh. It is a `surface` now (Tetravox 0.4.0, protocol 3) and never
        # emitted as a mesh: `build_view` refuses the scene rather than lie about the file.
        is_surface = classify_view_file(path) == "surface"
        is_mesh = role == "mesh" and not is_surface
        is_label = colormap == "lut" and not is_mesh and not is_surface
        visible = bool(layer.get("visible", True))
        field_name = _scene_field_name(name) if role in ("mesh", "field") else None

        dataset = _dataset_ref(path, index)
        sidecars: dict[str, Any] = {}
        lut = layer.get("lut")
        if lut and os.path.isabs(str(lut)):
            sidecars["lut"] = _sidecar_ref(str(lut))
        if is_mesh:
            # A SimNIBS .msh carries no $PhysicalNames, so its <mesh>.msh.opt
            # is the only source of tissue names and colours.
            opt = f"{path}.opt"
            if os.path.isfile(opt):
                sidecars["opt"] = _sidecar_ref(opt)
        attachments = [
            attachment
            for attachment in layer.get("attachments", [])
            if os.path.isfile(attachment)
        ]
        if is_surface and attachments:
            # Tetravox §4.6: a surface's `.annot`, morph and data-GIfTI files are re-attached from
            # `sidecars.fields`, in order, before the layers are restored. Each becomes a node
            # field on this dataset, named after the file -- which is what `annotation.name` /
            # `overlay.name` below refer to. There is no attachment *layer*.
            #
            # Relative to the surface's own directory, and `{path}` alone -- the embed lane's
            # contract, and the one place in a scene where a path is not absolute. SimNIBS keeps
            # the parcellations a directory across from the geometry, so these really do come out
            # as `../segmentation/lh.ernie_DK40.annot`.
            sidecars["fields"] = [
                {"path": _relative_sidecar_path(path, a)} for a in attachments
            ]
        if sidecars:
            dataset["sidecars"] = sidecars
        datasets.append(dataset)

        layer_id = f"L{index}"
        base_fields = {
            "id": layer_id,
            "datasetId": dataset["id"],
            # **The file's own basename, exactly as it is on disk.** Maintainer, 2026-09-07:
            # *"Please do not change the name of the files that we load into the viewer. For
            # example, `labeling.nii.gz` should be `labeling.nii.gz` and not [Atlas]."*
            #
            # This used to be a curated label (`Atlas`, `GM · TI_max (volume)`,
            # `Head mesh · magnE · pair 2`). The intent was to explain a layer, and the cost was
            # that the Layers panel no longer named anything a person could find on disk, grep a
            # log for, or match against the "what will open" list they had just composed. A name
            # that cannot be looked up is worse than a name that needs one thing explained.
            #
            # The context has nowhere else to go -- the engine's `LayerBase` (§4.4) has `id`,
            # `datasetId`, `name`, `visible`, `opacity`, `pickable`, `showColorbar` and no
            # description or subtitle field -- so it is dropped rather than smuggled back into the
            # name. `_scene_display_name` is still used, but only where a *human label for
            # choosing* is wanted and the filename is beside it anyway: the Menu's composition
            # tree (`viewer_tree`).
            "name": name,
            "visible": visible,
            "opacity": float(layer.get("opacity", 1.0)),
            "pickable": True,
            "showColorbar": True,
        }

        if is_surface:
            layers.append({**base_fields, **_surface_layer(name, attachments, index)})
        elif is_mesh:
            scale, threshold = _mesh_scale_and_threshold(
                _bounds_for_mesh(name, field_volumes)
            )
            layers.append(
                {
                    **base_fields,
                    "kind": "mesh",
                    "colorMode": "field" if field_name else "solid",
                    "solidColor": [0.78, 0.78, 0.8, 1.0],
                    **(
                        {"field": {"source": "elm", "name": field_name, "component": "mag"}}
                        if field_name
                        else {}
                    ),
                    "colormap": "jet",
                    "scale": scale,
                    "threshold": threshold,
                    "tagStyle": {},
                    "edges": {"surface": False, "caps": False},
                    "edgeColor": [0.0, 0.0, 0.0, 1.0],
                    "edgeWidthPx": 1.0,
                    "flatShading": False,
                    "faceMode": "cull",
                    "clip": {
                        "planes": [
                            {
                                "plane": {"normal": [1.0, 0.0, 0.0], "offset": 0.0},
                                "enabled": True,
                                # The plane's offset tracks the live cursor
                                # (Scene.cursor), not a value baked in here --
                                # this is what "cursor clip" means for a mesh
                                # layer the server never re-derives per cursor
                                # move.
                                "followCursor": True,
                            }
                        ],
                        "caps": True,
                        "capColorMode": "inherit",
                    },
                    # Grey-matter surfaces read best as an outline over the slices.
                    "contoursIn2D": name.lower().startswith("grey_"),
                    "contourWidthPx": 1.0,
                    "fillIn2D": True,
                }
            )
        else:
            volume_scale, volume_threshold = _volume_window(path, role=role)
            if role == "field":
                # A signed statistic map is windowed symmetrically about zero, so it needs a
                # diverging ramp: `turbo` would give its most saturated colour to the most
                # negative voxel and read as a strong positive finding.
                volume_colormap = "coolwarm" if _is_stat_map(path) else "turbo"
            else:
                volume_colormap = "gray"
            layers.append(
                {
                    **base_fields,
                    "kind": "volume",
                    "volumeIndex": 0,
                    "colormap": volume_colormap,
                    "scale": volume_scale,
                    "threshold": volume_threshold,
                    "interpolation": "nearest" if is_label else "linear",
                    "labelMode": "fill",
                    "outlineWidthPx": 2.0 if is_label else 1.0,
                    "showIn3D": is_label,
                    "precision": "auto",
                }
            )

    # A layout that reserves a 3D pane and a mesh nobody can see is an empty 3D pane -- which is
    # what the maintainer got (2026-09-07: "the 3-D pane empty"). The layout below gives the mesh
    # a pane precisely *because* the scene has one, so the two decisions have to agree: if a mesh
    # is the reason for the 3D pane, the mesh is visible.
    mesh_layers = [la for la in layers if la["kind"] == "mesh"]
    if mesh_layers and not any(la["visible"] for la in mesh_layers):
        mesh_layers[0]["visible"] = True

    visible_ids = [la["id"] for la in layers if la["visible"]]
    active_layer_id = (
        visible_ids[0] if visible_ids else (layers[0]["id"] if layers else None)
    )

    has_mesh = any(la["kind"] == "mesh" for la in layers)
    layout_kind = "3d+1" if has_mesh else "2x2"
    layout_cells = (
        ["view3d", "axial"] if has_mesh else ["axial", "coronal", "sagittal", "view3d"]
    )

    # Where the crosshair lands, in order of how much it knows about what the reader came to see:
    #
    # 1. the spec's own cursor -- an analysis or an optimisation carries its ROI centre, and that
    #    is the exact place the result is *about*;
    # 2. the field's peak voxel -- for a plain simulation there is no ROI, and the hotspot is the
    #    one place a reader always wants first;
    # 3. the scene's bounding-box centre -- no field, so at least land in the middle of the head.
    #
    # What it must not be is the old unconditional `[0, 0, 0]`: world RAS zero is the scanner
    # origin, which for a subject-space head volume is off in a corner of the field of view.
    cursor_raw = spec.get("cursor")
    bounds = _scene_bounds([layer["path"] for layer in layer_specs])
    if cursor_raw:
        cursor = [float(c) for c in cursor_raw]
    elif field_peak is not None:
        cursor = [float(c) for c in field_peak]
    elif bounds is not None:
        cursor = [(bounds[0][i] + bounds[1][i]) / 2.0 for i in range(3)]
    else:
        cursor = [0.0, 0.0, 0.0]
    # The mesh clip plane's offset tracks the scene cursor at load time (the
    # engine keeps it in sync afterwards via followCursor); a scene with no
    # cursor clips through the origin, matching cursor's own [0,0,0] default.
    for layer in layers:
        if layer["kind"] == "mesh":
            layer["clip"]["planes"][0]["plane"]["offset"] = cursor[0]

    return {
        "version": VIEWSPEC_VERSION,
        "datasets": datasets,
        "layers": layers,
        "activeLayerId": active_layer_id,
        # Fitted to the data, not left at the engine's 0.5 mm/px default -- see _fit_mm_per_px for
        # why the engine's own fit never runs for a scene this module writes.
        "slices": [
            dict(
                s,
                camera=(
                    {"center": [0.0, 0.0], "mmPerPx": _fit_mm_per_px(bounds, _FIT_PANE_PX)}
                    if bounds is not None
                    else dict(s["camera"])
                ),
            )
            for s in _DEFAULT_SLICES
        ],
        "view3d": {
            **_DEFAULT_VIEW3D,
            "camera": (
                _fit_camera(dict(_DEFAULT_VIEW3D["camera"]), bounds)
                if bounds is not None
                else dict(_DEFAULT_VIEW3D["camera"])
            ),
        },
        "layout": {"kind": layout_kind, "cells": layout_cells},
        "cursor": cursor,
        "radiological": False,
        "background": list(_DEFAULT_BACKGROUND),
        "lighting": dict(_DEFAULT_LIGHTING),
        "annotations": dict(_DEFAULT_ANNOTATIONS),
        "transparency": dict(_DEFAULT_TRANSPARENCY),
    }


def _finish(
    space: str,
    layers: list[dict[str, Any]],
    *,
    title: str | None = None,
    cursor: list[float] | None = None,
) -> dict[str, Any]:
    # Named subject/simulation layers also come from untrusted project symlinks.
    # Check them before percentiles or bounds touch the file, not after scene creation.
    checked = []
    for layer in layers:
        path = resolve_jailed(layer["path"])
        if path is None:
            continue
        layer = dict(layer, path=str(path))
        if "attachments" in layer:
            layer["attachments"] = [
                str(resolved)
                for raw in layer["attachments"]
                if (resolved := resolve_jailed(raw)) is not None
            ]
        lut = layer.get("lut")
        if lut and os.path.isabs(str(lut)):
            resolved = resolve_jailed(str(lut))
            layer["lut"] = str(resolved) if resolved is not None else None
        checked.append(layer)
    spec: dict[str, Any] = {"space": space, "layers": checked}
    resolve_percentiles(spec)
    return finish_spec(spec, title=title, cursor=cursor)


def finish_spec(
    spec: dict[str, Any],
    *,
    title: str | None = None,
    cursor: list[float] | None = None,
) -> dict[str, Any]:
    """Attach the two derived views of *spec* -- ``freeview_args`` (deprecated,
    kept for one release) and ``scene`` -- in place.

    The single place both derivations happen, so ``GET /api/view/{kind}``
    (via :func:`_finish`) and ``POST /api/view/args`` (on a client-edited
    spec) can never hand out an argv and a scene built from different rules.

    *title* has nowhere to go in a real ``ViewSpec`` (unlike the retired
    ``TitScene``, it carries no title field) and is accepted only for call-
    site compatibility with :func:`build_view`'s existing ``_scene_title``
    plumbing; it is not part of the returned document.
    """
    if cursor is not None:
        spec["cursor"] = list(cursor)
    spec["freeview_args"] = to_freeview_args(spec)
    spec["scene"] = to_tetravox_viewspec(spec)
    return spec


def to_freeview_args(spec: dict[str, Any]) -> list[str]:
    """The argv tail Freeview should be launched with for *spec*.

    Reproduces ``launch_freeview_with_files``'s per-layer grammar
    (``path:colormap=...:opacity=...:visible=...[:lut=...][:heatscale=lo,hi]``),
    with bug 5 fixed: ``heatscale`` is emitted whenever a layer carries both
    ``cal_min`` and ``cal_max``, not only in some percentile-mode branch.
    """
    args = []
    for layer in spec.get("layers", []):
        arg = layer["path"]
        arg += f":colormap={layer.get('colormap', 'grayscale')}"
        opacity = layer.get("opacity")
        if opacity is not None:
            arg += f":opacity={opacity}"
        arg += f":visible={1 if layer.get('visible', True) else 0}"
        lut = layer.get("lut")
        if lut:
            arg += f":lut={lut}"
        cal_min, cal_max = layer.get("cal_min"), layer.get("cal_max")
        if cal_min is not None and cal_max is not None:
            arg += f":heatscale={cal_min},{cal_max}"
        args.append(arg)
    return args


def freeview_command(spec: dict[str, Any]) -> list[str]:
    """Full ``["freeview", ...]`` argv for *spec*."""
    return ["freeview"] + to_freeview_args(spec)


# ── path jail (ra_14 finding 11) ─────────────────────────────────────────────
#
# A ``ViewSpec`` (custom-kind ``path=``, or a layer inside a client-submitted
# spec at launch time) can carry an arbitrary client-supplied path. This is
# the single place that decides what "safe to open" means for a viewer path
# -- the project directory plus the bundled ``resources/`` tree, nothing
# else -- so :mod:`tit.server.routes.files` (HTTP jail, raises on violation)
# and :mod:`tit.server.routes.viewers` (job-launch jail) both check against
# exactly the same roots instead of each re-deriving them.


def jail_roots() -> list[Path]:
    """Directories a viewer/file path is allowed to resolve into."""
    pm = get_path_manager()
    roots = []
    if pm.project_dir:
        roots.append(Path(pm.project_dir).resolve())
    roots.append(Path(mni_resources_dir()).resolve().parent)  # resources/
    return roots


def raw_jail_roots() -> list[Path]:
    """Directories ``GET /api/files/raw`` may stream bytes out of.

    The viewer jail, narrowed: the project plus the bundled *atlas* directory
    only, not the whole ``resources/`` tree :func:`jail_roots` allows. The
    wider root exists so a launcher can hand Freeview any bundled reference
    file; the raw route hands *the browser* bytes from the app's own origin,
    and ``resources/`` also holds patches and scripts that have no business
    being fetchable there.
    """
    pm = get_path_manager()
    roots = []
    if pm.project_dir:
        roots.append(Path(pm.project_dir).resolve())
    roots.append(Path(mni_resources_dir()).resolve())  # resources/atlas
    return roots


def resolve_jailed(raw_path: str) -> Path | None:
    """*raw_path* resolved to an existing file inside :func:`jail_roots`, or ``None``.

    Pure and exception-free by design (domain layer, no HTTP concerns): a
    caller that needs a 403/404 distinction wraps this; :func:`build_view`
    just treats ``None`` the same as any other "can't resolve this" case.
    """
    try:
        resolved = os.path.realpath(raw_path)
    except OSError:
        return None
    for root in jail_roots():
        canonical_root = os.path.realpath(root)
        # Include the separator so a sibling such as project-copy cannot match.
        if resolved == canonical_root:
            return Path(canonical_root) if os.path.isfile(canonical_root) else None
        if resolved.startswith(canonical_root.rstrip(os.sep) + os.sep):
            return Path(resolved) if os.path.isfile(resolved) else None
    return None
