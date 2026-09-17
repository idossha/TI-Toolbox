"""Prove, at the start of a job, that the ROI it is about is the ROI you meant.

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
whose centre was typed in guide coordinates.  So the check is no longer for MNI
ROIs only.  Every optimizer and every analyzer run writes it, for every target,
in every space, *before* the expensive work starts.

What it leaves behind is the ROI plate (:mod:`tit.figures.roi_plate`):

``roi_plate.png``
    Three orthogonal slices of the subject's own ``T1.nii.gz``, with the ROI
    centred and filling the view, drawn in a 40 % fill under an opaque outline.
``roi_plate.json``
    ``centroid_ras`` (the subject's own millimetres), ``voxels``, ``gm_overlap``
    (the fraction of the ROI's voxels that are grey matter in
    ``final_tissues.nii.gz``), the framing rule that was chosen, and what it was
    all made from.
``roi_mask.nii``
    The subject-space mask itself, kept rather than thrown away with a scratch
    directory, because the host-side renderer needs a file it can open.

and prints one line to the job's terminal.

Two rules, each with the failure it prevents:

* **A picture never fails a job.**  Everything here is wrapped: matplotlib may be
  absent, the T1 may be unreadable, the output directory may be read-only.  None
  of that is a reason to refuse to run an optimisation.  A failure is one log
  line.
* **It reports the mask that will actually be used**, not a second computation of
  it — the same :func:`tit.opt.masks.prepare_mask` call the runner makes, on the
  same label, after the same island cleanup.  A confirmation derived
  independently could agree with the user and disagree with the run.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

#: Grey matter in charm's ``final_tissues.nii.gz`` (SimNIBS tissue numbering).
GM_TISSUE_LABEL = 2

#: The mask the plate is drawn from, kept beside it.
MASK_NAME = "roi_mask.nii"

from tit.figures.roi_plate import (  # noqa: E402  - re-exported for callers
    FIELD_PLATE_JSON,
    FIELD_PLATE_PNG,
    PLATE_JSON as JSON_NAME,
    PLATE_PNG as PNG_NAME,
)

#: Set to ``1`` to skip the artefact entirely (a batch that wants no pictures).
#: The older name is still honoured so an existing batch script keeps working.
DISABLE_ENV = "TIT_NO_ROI_CONFIRMATION"


def enabled() -> bool:
    from tit.figures import roi_plate

    if os.environ.get(DISABLE_ENV, "").strip().lower() in ("1", "true", "yes"):
        return False
    return roi_plate.enabled()


def _subject_mask(
    atlas_path: str, label: int | None, space: str, m2m: str, scratch: str
):
    """The binary mask, in the subject's own voxels, that the job will use.

    A label is selected *before* the transform: ``prepare_mask`` resamples with
    nearest-neighbour interpolation, which preserves label values exactly, and
    binarising first means the confirmation cannot disagree with the run about
    which voxels the label owns.
    """
    import nibabel as nib
    import numpy as np

    from tit.opt.masks import prepare_mask

    if str(atlas_path).endswith(".annot"):
        # A cortical target lives on a surface; the plate needs voxels.
        return _annot_mask(atlas_path, label, m2m, scratch)
    source = atlas_path
    if label is not None:
        image = nib.load(atlas_path)
        data = np.asarray(image.dataobj)
        binary = (np.rint(data).astype(np.int64) == int(label)).astype(np.uint8)
        if not binary.any():
            raise ValueError(f"{atlas_path} has no voxels with label {label}")
        Path(scratch).mkdir(parents=True, exist_ok=True)
        source = str(Path(scratch) / f"label-{int(label)}.nii")
        nib.save(nib.Nifti1Image(binary, image.affine), source)
    prepared = prepare_mask(source, space, m2m, scratch, binary=True)
    return nib.load(prepared)


def _annot_mask(annot_path: str, label: int | None, m2m: str, scratch: str):
    """Rasterise one region of a FreeSurfer ``.annot`` onto the subject's T1 grid.

    The labelled vertices of the hemisphere's *central* surface are marked on
    the grid, grown by one voxel so a 1 mm sheet does not fall between voxel
    centres, and kept only where ``final_tissues`` says grey matter (2). It is
    the same cortex the search evaluates, drawn as voxels for the plate; the
    voxel count is therefore indicative, not the search's own vertex count.
    """
    import nibabel as nib
    import numpy as np
    from nibabel.freesurfer import read_annot
    from scipy import ndimage

    name = Path(annot_path).name
    hemi = name.split(".")[0]
    if hemi not in ("lh", "rh"):
        raise ValueError(f"{annot_path}: hemisphere prefix must be lh or rh")
    surface = Path(m2m) / "surfaces" / f"{hemi}.central.gii"
    if not surface.is_file():
        raise FileNotFoundError(f"{surface} is needed to draw a cortical target")
    vertex_labels, _, names = read_annot(annot_path)
    if label is None:
        selected = vertex_labels >= 0
    else:
        selected = vertex_labels == int(label)
    if not selected.any():
        raise ValueError(f"{annot_path} has no vertices with label {label}")
    coords = np.asarray(nib.load(str(surface)).darrays[0].data, dtype=float)[selected]
    tissues = nib.load(str(Path(m2m) / "final_tissues.nii.gz"))
    gm = np.squeeze(np.asarray(tissues.dataobj)) == 2
    ijk = np.rint(nib.affines.apply_affine(np.linalg.inv(tissues.affine), coords)).astype(int)
    inside = np.all((ijk >= 0) & (ijk < np.array(gm.shape)), axis=1)
    mask = np.zeros(gm.shape, dtype=bool)
    mask[tuple(ijk[inside].T)] = True
    mask = ndimage.binary_dilation(mask, iterations=1) & gm
    if not mask.any():
        raise ValueError(f"{annot_path} label {label} touches no grey-matter voxel")
    Path(scratch).mkdir(parents=True, exist_ok=True)
    out = Path(scratch) / f"annot-{hemi}-{label}.nii"
    nib.save(nib.Nifti1Image(mask.astype(np.uint8), tissues.affine), str(out))
    return nib.load(str(out))


def _gm_overlap(mask_image, m2m: str) -> float | None:
    """Fraction of the mask's voxels that are grey matter, or ``None``."""
    import nibabel as nib
    import numpy as np
    from scipy.ndimage import map_coordinates

    tissues_path = Path(m2m) / "final_tissues.nii.gz"
    if not tissues_path.is_file():
        return None
    tissues = nib.load(str(tissues_path))
    # charm writes final_tissues.nii.gz with a trailing singleton axis (256,256,208,1);
    # scipy's map_coordinates wants coordinates.shape[0] == input.ndim, so the volume
    # is squeezed to the three axes the affine actually describes.
    volume = np.squeeze(np.asarray(tissues.dataobj))
    if volume.ndim != 3:
        return None
    mask = np.asarray(mask_image.dataobj) > 0
    voxels = np.argwhere(mask)
    if not len(voxels):
        return None
    world = nib.affines.apply_affine(mask_image.affine, voxels)
    in_tissue = nib.affines.apply_affine(np.linalg.inv(tissues.affine), world)
    sampled = map_coordinates(
        volume.astype(np.float32),
        in_tissue.T,
        order=0,
        mode="constant",
        cval=0,
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
) -> dict | None:
    """Write the ROI plate for one target and return its summary.

    Args:
        atlas_path: the ROI's source volume (an atlas, or a mask).
        space: ``"mni"`` or ``"subject"`` — both get a plate; only MNI is
            transformed on the way.
        m2m: the subject's ``m2m_`` directory.
        out_dir: where the plate goes.
        label: one label of *atlas_path*, or ``None`` for the whole mask.
        name: what to call this ROI.
        sphere: ``(centre_ras, radius_mm)`` when the ROI is a sphere, so the
            plate frames the sphere the user typed rather than its rasterisation.
        field_path: when given, the **field** plate is written instead — the
            field masked to the ROI, in inferno, with a colour bar.

    Returns:
        The summary dict, or ``None`` when the plate was switched off or could
        not be written — never raises, because a job must not fail because a
        picture did.
    """
    if not enabled():
        return None
    import tempfile

    from tit.figures.roi_plate import write_roi_plate

    try:
        import nibabel as nib
        import numpy as np

        destination = Path(out_dir)
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="roi-confirm-") as scratch:
            sources = atlas_path if isinstance(atlas_path, list) else [atlas_path]
            labels = label if isinstance(label, list) else [label] * len(sources)
            spaces = space if isinstance(space, list) else [space] * len(sources)
            region_names = name if isinstance(name, list) else [name] * len(sources)
            mask_image = None
            mask = None
            # A union of regions is ONE target for the search, so it is one
            # mask and one plate; each region keeps its own value so the plate
            # can colour it, and the framing decides one row or several.
            for index, (src, lab, spc) in enumerate(zip(sources, labels, spaces), start=1):
                part = _subject_mask(src, lab, str(spc).lower(), m2m, scratch)
                data = np.squeeze(np.asarray(part.dataobj)) > 0
                if mask is None:
                    mask_image = part
                    mask = np.zeros(data.shape, dtype=np.int16)
                elif data.shape != mask.shape:
                    raise ValueError(f"{src}: grid differs from the first region's")
                mask[data & (mask == 0)] = index
            # Kept, not thrown away with the scratch directory: the host-side
            # Tetravox pass needs a file it can open long after the job ended.
            mask_path = destination / MASK_NAME
            nib.save(nib.Nifti1Image(mask, mask_image.affine), str(mask_path))
            voxels = np.argwhere(mask > 0)
            spacing = np.abs(np.linalg.det(mask_image.affine[:3, :3]))
            overlap = _gm_overlap(mask_image, m2m) if len(voxels) else None
            centroid = (
                nib.affines.apply_affine(mask_image.affine, voxels.mean(axis=0))
                if len(voxels)
                else np.zeros(3)
            )
            names = [
                nm or (f"label {lab}" if lab is not None else Path(src).name)
                for nm, lab, src in zip(region_names, labels, sources)
            ]
            label_name = " + ".join(names)
            extra = {
                "roi": label_name,
                "space": [str(x).lower() for x in spaces] if len(sources) > 1 else str(spaces[0]).lower(),
                "source": atlas_path,
                "label": label,
                "volume_mm3": round(float(len(voxels) * spacing), 1),
                "centroid_ras": [round(float(v), 1) for v in centroid],
                "gm_overlap": None if overlap is None else round(overlap, 3),
            }
            summary = write_roi_plate(
                mask_path=str(mask_path),
                m2m=m2m,
                out_dir=str(destination),
                field_path=field_path,
                names=names,
                spheres=[sphere] if sphere else None,
                title=label_name,
                extra=extra,
            )
        return summary
    except Exception as exc:  # noqa: BLE001 - never fail a job over a check
        logger.warning("ROI confirmation could not be written: %s", exc)
        return None


def confirm_rois(entries, *, m2m: str, out_dir: str) -> list[dict]:
    """:func:`confirm_roi` over a search's targets, as **one** plate.

    A search treats several regions as one union target, so the confirmation
    is one mask and one plate too — never a directory per region. Each region
    keeps its own colour in the plate and its own voxel count in the sidecar.
    """
    entries = list(entries)
    if not entries:
        return []
    summary = confirm_roi(
        m2m=m2m,
        out_dir=out_dir,
        atlas_path=[e["atlas_path"] for e in entries],
        label=[e.get("label") for e in entries],
        space=[e.get("space", "subject") for e in entries],
        name=[e.get("name", "") for e in entries],
        sphere=entries[0].get("sphere") if len(entries) == 1 else None,
        field_path=entries[0].get("field_path"),
    )
    return [summary] if summary else []
