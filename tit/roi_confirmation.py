"""Resolve a job's target to the files that describe it, and write its ROI scene.

Why this exists
---------------
A number about an ROI is only as good as the ROI.  An MNI ROI is not the ROI
that runs — every runner transforms it into the subject with the ``m2m_``
registration first (``mni2subject`` / :func:`tit.opt.masks.prepare_mask`), and a
transform that put the putamen in the wrong hemisphere, or 15 mm anterior, or
half outside the head, is the one error in this pipeline that no later number can
reveal: the optimisation converges, the focality ratio is finite, the analyzer's
table is full — and all of it is self-consistently about the wrong voxels.

A **subject-space** ROI has the same failure modes with none of the transform:
an atlas label with detached islands, a hand-drawn mask off by a slice, a sphere
whose centre was typed in guide coordinates.  So the check is for every target,
in every space, written *before* the expensive work starts.

This module is the thin place in the middle.  It turns a target — an atlas file
and a label, a hemisphere's ``.annot``, a mask, a sphere — into

* the **layers** a scene needs (which file, which label values, what colour),
* the **cursor and zoom** (:func:`tit.figures.roi_plate.plan_framing`), and
* the **numbers** (voxels, centroid, grey-matter overlap),

and hands them to :func:`tit.figures.roi_plate.write_roi_scene`, which writes one
small ``roi.tetravox.json`` that points at files that already exist.

Nothing is rasterised or duplicated to do it, with exactly one exception: an
**MNI** target's transformed mask is the ROI that runs and exists nowhere else,
so it is written once as a compressed ``uint8`` ``roi_mask.nii.gz`` on the
*atlas's* voxel grid — about 100 KB, not the 125 MB a 0.5 mm T1 grid costs.

Two rules, each with the failure it prevents:

* **An artefact never fails a job.**  Everything here is wrapped.  A failure is
  one log line.
* **It reports the mask that will actually be used**, not a second computation of
  it — the same :func:`tit.opt.masks.prepare_mask` call the runner makes, on the
  same label.  A confirmation derived independently could agree with the user and
  disagree with the run.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

#: Grey matter in charm's ``final_tissues.nii.gz`` (SimNIBS tissue numbering).
GM_TISSUE_LABEL = 2

from tit.figures.roi_plate import (  # noqa: E402  - re-exported for callers
    FIELD_SCENE_NAME,
    MNI_MASK_NAME,
    PALETTE,
    SCENE_NAME,
)

#: Set to ``1`` to skip the artefact entirely (a batch that wants no pictures).
#: The older name is still honoured so an existing batch script keeps working.
DISABLE_ENV = "TIT_NO_ROI_CONFIRMATION"


def enabled() -> bool:
    from tit.figures import roi_plate

    if os.environ.get(DISABLE_ENV, "").strip().lower() in ("1", "true", "yes"):
        return False
    return roi_plate.enabled()


def _hemisphere(annot_path: str) -> str:
    hemi = Path(annot_path).name.split(".")[0]
    if hemi not in ("lh", "rh"):
        raise ValueError(f"{annot_path}: hemisphere prefix must be lh or rh")
    return hemi


def _annot_vertices(annot_path: str, label, m2m: str):
    """The world coordinates of one region of a ``.annot``, and its surface.

    The cursor for a cortical target comes from the labelled vertices of the
    hemisphere's *central* surface — the same cortex the search evaluates — and
    **no file is written to get it**.  That is what lets the scene reference the
    ``.annot`` itself rather than a rasterisation of it.

    ``read_annot`` returns each vertex's index into the colortable, which is also
    what Tetravox's own reader remaps a packed FreeSurfer id to
    (``crates/tvx-mesh-io/src/freesurfer.rs``), so the integer written into the
    scene's ``visibleLabels`` is the integer this selects on.
    """
    import nibabel as nib
    import numpy as np
    from nibabel.freesurfer import read_annot

    surface = Path(m2m) / "surfaces" / f"{_hemisphere(annot_path)}.central.gii"
    if not surface.is_file():
        raise FileNotFoundError(f"{surface} is needed to place a cortical target")
    vertex_labels, _, _ = read_annot(annot_path)
    selected = vertex_labels >= 0 if label is None else vertex_labels == int(label)
    if not np.any(selected):
        raise ValueError(f"{annot_path} has no vertices with label {label}")
    coords = np.asarray(nib.load(str(surface)).darrays[0].data, dtype=float)[selected]
    return str(surface), coords


def _subject_volume(atlas_path: str, label, space: str, m2m: str, scratch: str):
    """The binary mask, in the subject's own voxels, that the job will use.

    A label is selected *before* the transform: ``prepare_mask`` resamples with
    nearest-neighbour interpolation, which preserves label values exactly, and
    binarising first means the confirmation cannot disagree with the run about
    which voxels the label owns.
    """
    import nibabel as nib
    import numpy as np

    from tit.opt.masks import prepare_mask

    source = atlas_path
    if label is not None:
        image = nib.load(atlas_path)
        data = np.asarray(image.dataobj)
        binary = (np.rint(data).astype(np.int64) == int(label)).astype(np.uint8)
        if not binary.any():
            raise ValueError(f"{atlas_path} has no voxels with label {label}")
        if space == "subject":
            return nib.Nifti1Image(binary, image.affine)
        Path(scratch).mkdir(parents=True, exist_ok=True)
        source = str(Path(scratch) / f"label-{int(label)}.nii")
        nib.save(nib.Nifti1Image(binary, image.affine), source)
    return nib.load(prepare_mask(source, space, m2m, scratch, binary=True))


def _label_values(atlas_path: str, label) -> list[int]:
    """The values the scene makes visible for one volume source."""
    import nibabel as nib
    import numpy as np

    if label is not None:
        return [int(label)]
    data = np.asarray(nib.load(atlas_path).dataobj)
    return sorted({int(v) for v in np.unique(np.rint(data)) if v > 0})[:64]


def _on_grid(image, shape, affine):
    """*image* resampled onto (*shape*, *affine*) with nearest neighbour."""
    import numpy as np
    from nibabel.processing import resample_from_to

    data = np.squeeze(np.asarray(image.dataobj))
    if data.shape == tuple(shape):
        return data > 0
    import nibabel as nib

    resampled = resample_from_to(
        nib.Nifti1Image(data.astype(np.uint8), image.affine), (shape, affine), order=0
    )
    return np.squeeze(np.asarray(resampled.dataobj)) > 0


def _coarsen(image, voxel_mm: float):
    """*image* resampled to isotropic *voxel_mm*, still in its own space.

    An MNI mask comes back from ``mni2subject`` on the subject's 0.5 mm conform
    grid: 125 MB of ``uint8`` for a structure a centimetre across.  The atlas it
    came from has 1 mm voxels and cannot say anything finer, so the file the
    scene points at is written at the atlas's own resolution — the same ROI, two
    orders of magnitude smaller, and honest about what it knows.
    """
    import nibabel as nib
    import numpy as np
    from nibabel.processing import resample_from_to

    zooms = np.asarray(image.header.get_zooms()[:3], dtype=float)
    factor = np.maximum(1.0, voxel_mm / np.where(zooms > 0, zooms, 1.0))
    if np.all(factor <= 1.0 + 1e-6):
        return image
    shape = np.maximum(1, np.floor(np.asarray(image.shape[:3]) / factor)).astype(int)
    affine = image.affine.copy()
    affine[:3, :3] = image.affine[:3, :3] * factor
    # Keep the corner of the first voxel where it was, so the coarse grid covers
    # exactly the volume the fine one did rather than sliding half a voxel.
    affine[:3, 3] = nib.affines.apply_affine(
        image.affine, (factor - 1.0) / 2.0
    )
    return resample_from_to(image, (tuple(shape), affine), order=0)


def _gm_overlap_volume(mask, affine, m2m: str) -> float | None:
    """Fraction of the mask's voxels that are grey matter, or ``None``."""
    import numpy as np

    world = _world_of(mask, affine)
    return _gm_overlap_points(world, m2m)


def _world_of(mask, affine):
    import nibabel as nib
    import numpy as np

    voxels = np.argwhere(mask)
    if not len(voxels):
        return None
    return nib.affines.apply_affine(affine, voxels)


def _gm_overlap_points(world, m2m: str) -> float | None:
    """Fraction of *world* points (mm) that land on grey matter, or ``None``."""
    import nibabel as nib
    import numpy as np
    from scipy.ndimage import map_coordinates

    if world is None or not len(world):
        return None
    tissues_path = Path(m2m) / "final_tissues.nii.gz"
    if not tissues_path.is_file():
        return None
    tissues = nib.load(str(tissues_path))
    # charm writes final_tissues.nii.gz with a trailing singleton axis
    # (256,256,208,1); map_coordinates wants coordinates.shape[0] == input.ndim,
    # so the volume is squeezed to the three axes the affine actually describes.
    volume = np.squeeze(np.asarray(tissues.dataobj))
    if volume.ndim != 3:
        return None
    ijk = nib.affines.apply_affine(np.linalg.inv(tissues.affine), np.asarray(world))
    sampled = map_coordinates(
        volume.astype(np.float32), ijk.T, order=0, mode="constant", cval=0
    )
    return float(np.mean(np.rint(sampled) == GM_TISSUE_LABEL))


def confirm_roi(
    *,
    atlas_path: str | list[str],
    space: str | list[str],
    m2m: str,
    out_dir: str,
    label: int | None | list[int | None] = None,
    name: str | list[str] = "",
    sphere: tuple | None = None,
    field_path: str | None = None,
    field_name: str | None = None,
) -> dict | None:
    """Write the ROI scene for one target and return its ``meta`` block.

    Args:
        atlas_path: the ROI's source — an atlas, a mask, or a ``.annot``.
        space: ``"mni"`` or ``"subject"``; only MNI is transformed on the way.
        m2m: the subject's ``m2m_`` directory.
        out_dir: where the scene goes.
        label: one label of *atlas_path*, or ``None`` for the whole mask.
        name: what to call this ROI.
        sphere: ``(centre_ras, radius_mm)`` when the ROI is a sphere, so the
            framing uses the sphere the user typed rather than its rasterisation.
        field_path: when given, the **field** scene is written instead — the
            analysis's own field volume with the ROI over it and a threshold.
        field_name: the file the field scene is titled after.

    Returns:
        The ``meta`` block as written, or ``None`` when the scene was switched off
        or could not be written — never raises, because a job must not fail
        because an artefact did.
    """
    if not enabled():
        return None
    entries = [
        {
            "atlas_path": p,
            "label": lb,
            "space": sp,
            "name": nm,
            "sphere": sphere,
            "field_path": field_path,
            "field_name": field_name,
        }
        for p, lb, sp, nm in zip(*_broadcast(atlas_path, label, space, name))
    ]
    written = confirm_rois(entries, m2m=m2m, out_dir=out_dir)
    return written[0] if written else None


def _broadcast(atlas_path, label, space, name):
    sources = atlas_path if isinstance(atlas_path, list) else [atlas_path]
    labels = label if isinstance(label, list) else [label] * len(sources)
    spaces = space if isinstance(space, list) else [space] * len(sources)
    names = name if isinstance(name, list) else [name] * len(sources)
    return sources, labels, spaces, names


def confirm_rois(entries, *, m2m: str, out_dir: str) -> list[dict]:
    """Write **one** scene for a search's targets, however many regions it has.

    A search treats several regions as one union target, so the confirmation is
    one scene too — never a directory per region.  Each region keeps its own
    colour in the scene and its own voxel count in ``meta``.
    """
    if not enabled():
        return []
    entries = [dict(e) for e in entries]
    if not entries:
        return []
    try:
        meta = _write(entries, m2m=m2m, out_dir=out_dir)
    except Exception as exc:  # noqa: BLE001 - never fail a job over a check
        logger.warning("ROI confirmation could not be written: %s", exc)
        return []
    return [meta] if meta else []


def _write(entries, *, m2m: str, out_dir: str) -> dict | None:
    import tempfile

    import nibabel as nib
    import numpy as np

    from tit.figures.roi_plate import (
        FIELD_FLOOR_FRACTION,
        plan_framing,
        plan_spheres,
        plan_surface,
        write_mask_nii_gz,
        write_roi_scene,
    )

    destination = Path(out_dir)
    destination.mkdir(parents=True, exist_ok=True)
    anatomy = str(Path(m2m) / "T1.nii.gz")
    if not Path(anatomy).is_file():
        raise FileNotFoundError(f"{anatomy} is needed to draw the ROI on")

    spheres = [e["sphere"] for e in entries if e.get("sphere") and not e.get("atlas_path")]
    if spheres and len(spheres) == len(entries):
        return _sphere_scene(entries, spheres, m2m=m2m, destination=destination, anatomy=anatomy)

    names = [
        entry.get("name")
        or (
            f"label {entry.get('label')}"
            if entry.get("label") is not None
            else Path(entry["atlas_path"]).name
        )
        for entry in entries
    ]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(entries))]
    sphere = entries[0].get("sphere") if len(entries) == 1 else None

    roi_layers: list[dict] = []
    surface_groups: list = []
    surface_names: list[str] = []

    with tempfile.TemporaryDirectory(prefix="roi-confirm-") as scratch:
        # --- cortical targets: the .annot is referenced, never rasterised -----
        annots: dict[tuple[str, str], dict] = {}
        volume_parts: list[tuple[int, object]] = []
        mni_indices: list[int] = []
        for index, entry in enumerate(entries):
            source = str(entry["atlas_path"])
            space = str(entry.get("space", "subject")).lower()
            label = entry.get("label")
            if source.endswith(".annot"):
                surface, coords = _annot_vertices(source, label, m2m)
                surface_groups.append(coords)
                surface_names.append(names[index])
                key = (surface, source)
                layer = annots.get(key)
                if layer is None:
                    layer = {
                        "kind": "surface",
                        "path": surface,
                        "annot": source,
                        "labels": {},
                    }
                    annots[key] = layer
                    roi_layers.append(layer)
                for value in _label_values_annot(source, label):
                    layer["labels"][value] = colors[index]
                continue
            image = _subject_volume(source, label, space, m2m, scratch)
            volume_parts.append((index, image))
            if space == "mni":
                mni_indices.append(index)

        # --- volume targets: one array for the numbers, one file for the scene -
        mask = None
        affine = None
        if volume_parts:
            first = volume_parts[0][1]
            affine = first.affine
            shape = np.squeeze(np.asarray(first.dataobj)).shape
            mask = np.zeros(shape, dtype=np.int16)
            for index, image in volume_parts:
                part = _on_grid(image, shape, affine)
                mask[part & (mask == 0)] = index + 1
            if mni_indices:
                # The one legitimate intermediate: the transformed mask is the
                # ROI that runs and exists in no file the user already has.
                voxel_mm = max(
                    float(
                        np.max(
                            nib.load(str(entries[i]["atlas_path"])).header.get_zooms()[:3]
                        )
                    )
                    for i in mni_indices
                )
                coarse = _coarsen(
                    nib.Nifti1Image(mask.astype(np.uint8), affine), voxel_mm
                )
                mask_path = destination / MNI_MASK_NAME
                write_mask_nii_gz(coarse, mask_path)
                roi_layers.append(
                    {
                        "kind": "volume",
                        "path": str(mask_path),
                        "labels": {
                            index + 1: colors[index] for index, _ in volume_parts
                        },
                    }
                )
            else:
                # Subject space: the atlas the user named is already on disk, so
                # the scene points at it and selects the labels it is about.
                for index, _ in volume_parts:
                    entry = entries[index]
                    source = str(entry["atlas_path"])
                    layer = next(
                        (
                            la
                            for la in roi_layers
                            if la["kind"] == "volume" and la["path"] == source
                        ),
                        None,
                    )
                    if layer is None:
                        layer = {"kind": "volume", "path": source, "labels": {}}
                        roi_layers.append(layer)
                    for value in _label_values(source, entry.get("label")):
                        layer["labels"][value] = colors[index]

    if mask is not None:
        plan = plan_framing(
            mask,
            affine,
            names={index + 1: names[index] for index in range(len(entries))},
            spheres=[sphere] if sphere else None,
        )
        world = _world_of(mask > 0, affine)
        voxels = 0 if world is None else len(world)
        spacing = float(abs(np.linalg.det(np.asarray(affine)[:3, :3])))
        overlap = _gm_overlap_volume(mask > 0, affine, m2m)
        volume_mm3 = round(voxels * spacing, 1)
    elif surface_groups:
        plan = plan_surface(surface_groups, names=surface_names)
        world = np.concatenate([np.asarray(g) for g in surface_groups])
        voxels = len(world)
        overlap = _gm_overlap_points(world, m2m)
        volume_mm3 = None
    else:
        raise ValueError("the target named no volume and no surface")

    centroid = (
        [0.0, 0.0, 0.0] if world is None else [float(v) for v in np.mean(world, axis=0)]
    )
    title = " + ".join(names)
    spaces = [str(e.get("space", "subject")).lower() for e in entries]
    meta = {
        "roi": title,
        "space": spaces if len(spaces) > 1 else spaces[0],
        "source": [str(e["atlas_path"]) for e in entries],
        "label": [e.get("label") for e in entries],
        # A cortical target is counted in vertices, a volume one in voxels; the
        # key is shared because it is "how many members does this ROI have" and
        # `unit` says which, rather than two keys one of which is always null.
        "voxels": int(voxels),
        "unit": "vertices" if mask is None else "voxels",
        "volume_mm3": volume_mm3,
        "centroid_ras": [round(v, 1) for v in centroid],
        "cursor_ras": [round(v, 2) for v in plan.cursor_ras],
        "gm_overlap": None if overlap is None else round(overlap, 3),
        "rule": plan.rule,
        "island_voxels": plan.island_voxels,
        "regions": {r.name: r.voxels for r in plan.regions},
        "framing": plan.as_dict(),
    }

    scene = write_roi_scene(
        out_dir=str(destination),
        anatomy=anatomy,
        roi_layers=roi_layers,
        plan=plan,
        meta=meta,
        title=title,
    )

    # The field scene is written in the **same pass**, not after the analysis
    # finishes: the field it shows is the analyzer's input file, which exists
    # before a single number is computed, and writing it here means the ROI is
    # resolved once rather than twice (an MNI target's transform is not cheap).
    field_path = entries[0].get("field_path")
    if scene is not None and field_path:
        field = _field_window(field_path, world, FIELD_FLOOR_FRACTION)
        if field is not None:
            field_meta = dict(meta)
            field_meta["field"] = {
                "file": str(field_path),
                "unit": "V/m",
                "max_in_roi": field.pop("max_in_roi"),
                "p99_9_in_roi": field["hi"],
                "threshold_floor": field["lo"],
            }
            write_roi_scene(
                out_dir=str(destination),
                anatomy=anatomy,
                roi_layers=roi_layers,
                plan=plan,
                meta=field_meta,
                title=f"{Path(field_path).name} in {title}",
                field=field,
            )
            meta["field"] = field_meta["field"]
    return scene


def _sphere_scene(entries, spheres, *, m2m, destination, anatomy) -> dict | None:
    """The scene for a target that is only a sphere: the T1 and the crosshair.

    A sphere names no file, so there is nothing to reference and nothing worth
    writing: the artefact is the anatomy with the cursor on the centre the user
    typed and the zoom set by the radius.  ``meta`` carries the centres and radii,
    and the one Tetravox addition that would make this scene draw the extent is a
    marker/sphere layer in ``ViewSpec`` -- today ``sphere`` exists only inside a
    mesh ``IsolateSpec`` and cannot be drawn on its own.
    """
    import numpy as np

    from tit.figures.roi_plate import FIELD_FLOOR_FRACTION, plan_spheres, write_roi_scene

    names = [e.get("name") or f"sphere {i + 1}" for i, e in enumerate(entries)]
    plan = plan_spheres(spheres, names=names)
    title = " + ".join(names)
    world = np.asarray([[float(v) for v in centre] for centre, _ in spheres])
    meta = {
        "roi": title,
        "space": "subject",
        "source": None,
        "label": None,
        "voxels": len(spheres),
        "unit": "sphere" if len(spheres) == 1 else "spheres",
        "volume_mm3": round(
            float(sum(4.0 / 3.0 * np.pi * float(r) ** 3 for _, r in spheres)), 1
        ),
        "centroid_ras": [round(float(v), 1) for v in world.mean(axis=0)],
        "cursor_ras": [round(v, 2) for v in plan.cursor_ras],
        "gm_overlap": _gm_overlap_points(world, m2m),
        "rule": plan.rule,
        "island_voxels": 0,
        "spheres": [
            {"centre_ras": [round(float(v), 2) for v in centre], "radius_mm": float(r)}
            for centre, r in spheres
        ],
        "framing": plan.as_dict(),
    }
    scene = write_roi_scene(
        out_dir=str(destination),
        anatomy=anatomy,
        roi_layers=[],
        plan=plan,
        meta=meta,
        title=title,
    )
    field_path = entries[0].get("field_path")
    if scene is not None and field_path:
        field = _field_window(field_path, world, FIELD_FLOOR_FRACTION)
        if field is not None:
            field_meta = dict(meta)
            field_meta["field"] = {
                "file": str(field_path),
                "unit": "V/m",
                "max_in_roi": field.pop("max_in_roi"),
                "p99_9_in_roi": field["hi"],
                "threshold_floor": field["lo"],
            }
            write_roi_scene(
                out_dir=str(destination),
                anatomy=anatomy,
                roi_layers=[],
                plan=plan,
                meta=field_meta,
                title=f"{Path(field_path).name} in {title}",
                field=field,
            )
            meta["field"] = field_meta["field"]
    return scene


def cortical_entries(m2m: str, atlas: str, regions) -> list[dict]:
    """``.annot`` path and label index for each named cortical region.

    The analyzer names a cortical target by atlas and region (``DK40`` /
    ``lh.superiorfrontal``); the scene needs the file and the integer.  Discovery
    goes through :class:`tit.atlas.MeshAtlasManager`, the same one
    ``GET /api/catalog/atlases`` uses, so the scene sees exactly the atlases the
    subject has.  A name that resolves to neither hemisphere is skipped with one
    log line -- an artefact never fails a job.
    """
    from nibabel.freesurfer import read_annot

    from tit.atlas import MeshAtlasManager

    manager = MeshAtlasManager(str(Path(m2m) / "segmentation"))
    tables: dict[str, tuple[str, dict[str, int]]] = {}
    for hemi in ("lh", "rh"):
        path = manager.find_atlas_file(atlas, hemi)
        if not path or not Path(path).is_file():
            continue
        _, _, labels = read_annot(str(path))
        tables[hemi] = (
            str(path),
            {
                (name.decode() if isinstance(name, bytes) else str(name)).lower(): index
                for index, name in enumerate(labels)
            },
        )
    entries: list[dict] = []
    for raw in regions:
        text = str(raw)
        stem = text
        hemis = ("lh", "rh")
        for prefix in ("lh.", "rh."):
            if text.lower().startswith(prefix):
                hemis, stem = (prefix[:2],), text[3:]
        for suffix in ("-lh", "-rh", "_lh", "_rh"):
            if text.lower().endswith(suffix):
                hemis, stem = (suffix[1:],), text[: -len(suffix)]
        for hemi in hemis:
            table = tables.get(hemi)
            if table is None:
                continue
            index = table[1].get(stem.lower())
            if index is None:
                continue
            entries.append(
                {
                    "atlas_path": table[0],
                    "label": int(index),
                    "space": "subject",
                    "name": f"{hemi}.{stem}",
                }
            )
    if not entries:
        logger.warning("no .annot region of %s matched %s", atlas, list(regions))
    return entries


def _label_values_annot(annot_path: str, label) -> list[int]:
    """The ids the **scene** makes visible for one ``.annot`` region.

    Not the same integer the rest of this module selects on.  ``read_annot``
    returns a *dense index* into the colortable, and that is what picks the
    vertices; Tetravox's ``visibleLabels`` names the colortable entry's own
    **packed FreeSurfer id** (``r | g << 8 | b << 16`` --
    ``crates/tvx-mesh-io/src/freesurfer.rs`` builds ``LabelEntry.id`` that way and
    ``layers/mesh.ts::buildLabelPalette`` matches on it).  Sending the dense index
    matches no entry, every label's alpha goes to zero, and the parcellation
    renders as nothing at all -- which is exactly what it did.
    """
    import numpy as np
    from nibabel.freesurfer import read_annot

    vertex_labels, ctab, _ = read_annot(annot_path)
    ctab = np.asarray(ctab)

    def packed(index: int) -> int:
        row = ctab[int(index)]
        return int(row[0]) | (int(row[1]) << 8) | (int(row[2]) << 16)

    if label is not None:
        return [packed(label)]
    indices = sorted({int(v) for v in np.unique(vertex_labels) if v > 0})[:64]
    return [packed(i) for i in indices]


def _field_window(field_path, world, floor_fraction) -> dict | None:
    """The field's display window **inside** the ROI, read at the ROI's own points.

    Sampled from the analysis's own volume, never from a copy of it masked to the
    ROI: the scene points at the file the table came from, so a reader can check
    the picture against the numbers and know it is the same data.  Sampling at
    points rather than intersecting grids is what lets a cortical target -- whose
    ROI is a set of surface vertices and no volume at all -- have a field scene.
    """
    import nibabel as nib
    import numpy as np
    from scipy.ndimage import map_coordinates

    if world is None or not len(world):
        return None
    image = nib.load(str(field_path))
    volume = np.squeeze(np.asarray(image.dataobj, dtype=np.float32))
    if volume.ndim != 3:
        return None
    ijk = nib.affines.apply_affine(np.linalg.inv(image.affine), np.asarray(world))
    inside = map_coordinates(volume, ijk.T, order=1, mode="constant", cval=0.0)
    inside = inside[np.isfinite(inside)]
    if not inside.size:
        return None
    hi = float(np.percentile(inside, 99.9))
    return {
        "path": str(field_path),
        "lo": round(floor_fraction * hi, 6),
        "hi": round(hi, 6),
        "max_in_roi": round(float(np.nanmax(inside)), 6),
    }
