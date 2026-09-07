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
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

from tit.atlas import DEFAULT_MNI_ATLAS, MNI_ATLAS_DIR, MNI_TEMPLATE, VoxelAtlasManager
from tit.atlas.constants import mni_resources_dir
from tit.paths import get_path_manager

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
        if not os.path.isfile(config):
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
        layers.append(
            copy.deepcopy(by_path[path]) if path in by_path else _layer_for_path(path)
        )
    return layers


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
        "kind": "mesh" if _scene_is_mesh(path) else "volume",
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
    """Forget every memoised window. For tests; nothing in the server calls it."""
    with _PERCENTILE_LOCK:
        _PERCENTILE_CACHE.clear()


def _resolve_layer_percentile(layer: dict[str, Any]) -> None:
    """Fill *layer*'s ``cal_min``/``cal_max`` from its ``percentile`` window, in place.

    Any failure (missing/unreadable file, an all-zero volume, no ``nibabel``
    in this environment) leaves ``cal_min``/``cal_max`` exactly as they were
    -- a layer with an unresolved threshold still renders, just without a
    ``heatscale`` arg (see :func:`to_freeview_args`).

    Memoised on the file's identity (see :data:`_PERCENTILE_CACHE`). A miss reads the volume
    exactly as before; a hit costs one ``os.stat``.
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
# `DatasetRef.path`/`.absPath` are both set to the *same* origin-relative
# `/api/files/raw/...` URL string (never a container filesystem path): the
# embed is served from this same server at `/tetravox/`, so from inside its
# iframe an absolute-path URL (leading `/`, no scheme/host) is directly
# fetchable -- no client-side rewriting is needed, and
# `scene/serialize.ts`'s own path-joining (`joinPath`/`relativePath`) treats
# any string starting with `/` as already-absolute and passes it through
# unchanged regardless of which of `path`/`absPath` a host's `resolve`
# callback happens to prefer. `fingerprint` is always ``''`` (§4.6: computing
# one needs the file bytes, which only the loader's WASM worker ever reads).

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
    lowered = name.lower()
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

        if role == "mesh":
            region_label = region or "Mesh"
            return (
                f"{region_label} mesh · {field_name}"
                if field_name
                else f"{region_label} mesh (tags)"
            )
        if field_name:
            return (
                f"{region} · {field_name} (volume)"
                if region
                else f"{field_name} (volume)"
            )

    return stem


# path -> (mtime, size, stats). Process-lifetime cache: a NIfTI is re-read
# only when it changes on disk, so building several views of the same
# simulation in a row (subject -> simulation -> analysis) costs one read.
_stats_cache: dict[str, tuple[float, int, dict[str, float]]] = {}


def _volume_stats(path: str) -> dict[str, float] | None:
    """min/max and a few percentiles of *path*'s non-zero voxels, or ``None``.

    The one place this module reads voxel data -- deliberately: a real
    ``Scale`` needs concrete numbers (see the module note above), and reading
    one NIfTI is cheap. Any failure (missing file, unreadable, no numpy/
    nibabel in this environment, an all-zero/all-NaN volume) yields ``None``
    rather than raising; callers fall back to a documented generic range.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    cached = _stats_cache.get(path)
    if cached is not None and cached[0] == st.st_mtime and cached[1] == st.st_size:
        return cached[2]
    try:
        import nibabel as nib
        import numpy as np

        data = np.asarray(nib.load(path).dataobj)
    except Exception:  # noqa: BLE001 - never let an unreadable volume break the scene
        return None
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return None
    nonzero = finite[finite != 0]
    sample = nonzero if nonzero.size else finite
    p0, p50, p95, p999, p100 = np.percentile(sample, [0, 50, 95, 99.9, 100])
    stats = {
        "min": float(finite.min()),
        "max": float(finite.max()),
        "nz_lo": float(p0),
        "p50": float(p50),
        "p95": float(p95),
        "p999": float(p999),
        "nz_hi": float(p100),
    }
    _stats_cache[path] = (st.st_mtime, st.st_size, stats)
    return stats


def _volume_scale(path: str, *, role: str) -> dict[str, Any]:
    """A concrete engine ``Scale`` for one volume layer.

    ``role == "field"`` (a heat overlay, e.g. TI_max/magnE) gets the engine's
    own ``{kind:'heat', min, mid, max, ...}``, windowed at the 0th/95th/99.9th
    percentile of the file's non-zero voxels -- the same 95/99.9 window
    ``to_freeview_args``'s ``heatscale`` resolves to
    (``_DEFAULT_PERCENTILE``), expressed the way ``VolumeLayer.scale``
    requires it (an absolute triple, not a percentile pair the client
    resolves). Everything else (base T1, an atlas/label volume, the
    electrode overlay) gets a plain ``{kind:'linear', lo, hi}`` over the
    file's own min/max, which is what every real base-layer scene in the
    tetravox app's own fixtures carries. A file :func:`_volume_stats` could
    not read falls back to a generic, documented placeholder range rather
    than failing the whole scene.
    """
    stats = _volume_stats(path)
    if role == "field":
        if stats is None:
            return {
                "kind": "heat",
                "min": 0.0,
                "mid": 0.5,
                "max": 1.0,
                "truncate": False,
                "inverse": False,
                "negative": "hide",
            }
        top = stats["p999"] if stats["p999"] > stats["p95"] else stats["max"]
        return {
            "kind": "heat",
            "min": stats["nz_lo"],
            "mid": stats["p95"],
            "max": top,
            "truncate": False,
            "inverse": False,
            "negative": "hide",
        }
    if stats is None:
        return {"kind": "linear", "lo": 0.0, "hi": 1.0}
    return {"kind": "linear", "lo": stats["min"], "hi": stats["max"]}


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
            "lo": 0.0,
            "hi": hi * 1.5,
            "symmetric": False,
            "mode": "clamp",
            "softEdge": 0.0,
        },
    )


def _dataset_ref(path: str, index: int) -> dict[str, Any]:
    url = _scene_raw_url(path)
    return {
        "id": f"ds{index}",
        "kind": "mesh" if _scene_is_mesh(path) else "volume",
        "name": os.path.basename(path),
        "path": url,
        "absPath": url,
        "fingerprint": "",
    }


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

    # A sibling NIfTI field layer's resolved window, reused as the mesh's own
    # approximate scale/threshold (see _mesh_scale_and_threshold).
    field_bounds: tuple[float, float] | None = None
    for layer in layer_specs:
        path = layer["path"]
        if _scene_is_mesh(path):
            continue
        if _scene_role(path, layer.get("colormap", "grayscale")) != "field":
            continue
        stats = _volume_stats(path)
        if stats is not None:
            top = stats["p999"] if stats["p999"] > stats["p95"] else stats["max"]
            field_bounds = (stats["nz_lo"], top)
            break

    datasets: list[dict[str, Any]] = []
    layers: list[dict[str, Any]] = []

    for index, layer in enumerate(layer_specs):
        path = layer["path"]
        name = os.path.basename(path)
        colormap = layer.get("colormap", "grayscale")
        role = _scene_role(path, colormap)
        is_mesh = role == "mesh"
        is_label = colormap == "lut" and not is_mesh
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
        if sidecars:
            dataset["sidecars"] = sidecars
        datasets.append(dataset)

        layer_id = f"L{index}"
        base_fields = {
            "id": layer_id,
            "datasetId": dataset["id"],
            "name": _scene_display_name(name, role=role, field_name=field_name),
            "visible": visible,
            "opacity": float(layer.get("opacity", 1.0)),
            "pickable": True,
            "showColorbar": True,
        }

        if is_mesh:
            scale, threshold = _mesh_scale_and_threshold(field_bounds)
            layers.append(
                {
                    **base_fields,
                    "kind": "mesh",
                    "colorMode": "field" if field_name else "solid",
                    "solidColor": [0.78, 0.78, 0.8, 1.0],
                    "field": (
                        {"source": "elm", "name": field_name, "component": "mag"}
                        if field_name
                        else None
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
            layers.append(
                {
                    **base_fields,
                    "kind": "volume",
                    "volumeIndex": 0,
                    "colormap": "turbo" if role == "field" else "gray",
                    "scale": _volume_scale(path, role=role),
                    "threshold": dict(_ZERO_THRESHOLD),
                    "interpolation": "nearest" if is_label else "linear",
                    "labelMode": "fill",
                    "outlineWidthPx": 2.0 if is_label else 1.0,
                    "showIn3D": is_label,
                    "precision": "auto",
                }
            )

    visible_ids = [la["id"] for la in layers if la["visible"]]
    active_layer_id = (
        visible_ids[0] if visible_ids else (layers[0]["id"] if layers else None)
    )

    has_mesh = any(la["kind"] == "mesh" for la in layers)
    layout_kind = "3d+1" if has_mesh else "2x2"
    layout_cells = (
        ["view3d", "axial"] if has_mesh else ["axial", "coronal", "sagittal", "view3d"]
    )

    cursor_raw = spec.get("cursor")
    cursor = [float(c) for c in cursor_raw] if cursor_raw else [0.0, 0.0, 0.0]
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
        "slices": [dict(s, camera=dict(s["camera"])) for s in _DEFAULT_SLICES],
        "view3d": {**_DEFAULT_VIEW3D, "camera": dict(_DEFAULT_VIEW3D["camera"])},
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
    spec: dict[str, Any] = {"space": space, "layers": layers}
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
        resolved = Path(raw_path).resolve()
    except OSError:
        return None
    if not any(resolved.is_relative_to(root) for root in jail_roots()):
        return None
    if not resolved.is_file():
        return None
    return resolved
