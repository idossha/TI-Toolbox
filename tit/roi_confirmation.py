"""Prove, at the start of a job, that an MNI ROI landed where the user meant.

Why this exists
---------------
An MNI-space ROI is not the ROI that runs.  Every runner transforms it into the
subject with the ``m2m_`` registration first (``mni2subject`` /
:func:`tit.opt.masks.prepare_mask`), and from that moment every number the job
produces is about the *transformed* mask.  A transform that put the putamen in
the wrong hemisphere, or 15 mm anterior, or half outside the head, is therefore
the one error in this pipeline that no later number can reveal: the optimisation
converges, the focality ratio is finite, the analyzer's table is full — and all
of it is self-consistently about the wrong voxels.

So the transform happens **first**, before any expensive work, and it leaves
behind an artefact a person can look at:

``roi_confirmation.png``
    Three orthogonal slices of the subject's own ``T1.nii.gz`` at the mask's
    centroid, with the subject-space mask drawn over them.
``roi_confirmation.json``
    ``centroid_ras`` (the subject's own millimetres), ``voxels``,
    ``gm_overlap`` (the fraction of the mask's voxels that are grey matter in
    ``final_tissues.nii.gz``), plus what it was made from.

and prints one line to the job's terminal.

Two rules, each with the failure it prevents:

* **A picture never fails a job.**  Everything here is wrapped: matplotlib may
  be absent, the T1 may be unreadable, the output directory may be read-only.
  None of that is a reason to refuse to run an optimisation.  A failure is one
  log line.
* **It reports the mask that will actually be used**, not a second computation
  of it — the same :func:`tit.opt.masks.prepare_mask` call the runner makes, on
  the same label, after the same island cleanup.  A confirmation image derived
  independently could agree with the user and disagree with the run.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Grey matter in charm's ``final_tissues.nii.gz`` (SimNIBS tissue numbering).
GM_TISSUE_LABEL = 2

PNG_NAME = "roi_confirmation.png"
JSON_NAME = "roi_confirmation.json"

#: Set to ``1`` to skip the artefact entirely (a batch that wants no pictures).
DISABLE_ENV = "TIT_NO_ROI_CONFIRMATION"


def enabled() -> bool:
    return os.environ.get(DISABLE_ENV, "").strip().lower() not in ("1", "true", "yes")


def _subject_mask(atlas_path: str, label: int | None, space: str, m2m: str, scratch: str):
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
        Path(scratch).mkdir(parents=True, exist_ok=True)
        source = str(Path(scratch) / f"label-{int(label)}.nii")
        nib.save(nib.Nifti1Image(binary, image.affine), source)
    prepared = prepare_mask(source, space, m2m, scratch, binary=True)
    return nib.load(prepared)


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


def _render(mask_image, m2m: str, centroid_voxel, destination: Path, title: str) -> None:
    """Three orthogonal T1 slices at the centroid with the mask drawn over them."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import nibabel as nib
    import numpy as np
    from nibabel.processing import resample_from_to

    t1_path = Path(m2m) / "T1.nii.gz"
    background_image = None
    if t1_path.is_file():
        # Resampled onto the MASK's grid, so one set of indices addresses both
        # and the slice a reader sees is the slice the numbers describe.
        background_image = resample_from_to(nib.load(str(t1_path)), mask_image, order=1)

    # Reoriented to RAS before slicing. charm's conformed space stores ernie's volume with its
    # axes permuted, so index 0 was an axial plane labelled "sagittal" and every panel was rotated
    # by an arbitrary amount. A picture that misinforms is worse than no picture, and
    # `as_closest_canonical` is the one line that makes axis 0/1/2 mean x/y/z everywhere.
    canonical = nib.as_closest_canonical(mask_image)
    mask = np.squeeze(np.asarray(canonical.dataobj)) > 0
    background = None
    if background_image is not None:
        background = np.squeeze(
            np.asarray(
                nib.as_closest_canonical(background_image).dataobj, dtype=np.float32
            )
        )
        if background.ndim != 3:
            background = None
    # The centroid in the canonical grid's own voxels (it is the same world point).
    index = [
        int(round(v))
        for v in nib.affines.apply_affine(
            np.linalg.inv(canonical.affine),
            nib.affines.apply_affine(mask_image.affine, np.asarray(centroid_voxel)),
        )
    ]
    planes = [(0, "sagittal"), (1, "coronal"), (2, "axial")]
    figure, axes = plt.subplots(1, 3, figsize=(9, 3.2), facecolor="black")
    for axis, (plane, name) in zip(axes, planes):
        cut = min(max(index[plane], 0), mask.shape[plane] - 1)
        slicer: list[Any] = [slice(None)] * 3
        slicer[plane] = cut
        layer = mask[tuple(slicer)].T
        axis.set_facecolor("black")
        if background is not None:
            grey = background[tuple(slicer)].T
            finite = grey[np.isfinite(grey)]
            top = float(np.percentile(finite, 99)) if finite.size else 1.0
            axis.imshow(grey, cmap="gray", origin="lower", vmin=0, vmax=max(top, 1e-6))
        axis.imshow(
            np.ma.masked_where(~layer, layer.astype(float)),
            cmap="autumn",
            origin="lower",
            alpha=0.55,
            vmin=0,
            vmax=1,
        )
        axis.set_title(name, color="white", fontsize=9)
        axis.set_xticks([])
        axis.set_yticks([])
    figure.suptitle(title, color="white", fontsize=10)
    figure.tight_layout()
    destination.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(str(destination), dpi=120, facecolor="black")
    plt.close(figure)


def confirm_roi(
    *,
    atlas_path: str,
    space: str,
    m2m: str,
    out_dir: str,
    label: int | None = None,
    name: str = "",
) -> dict | None:
    """Write the confirmation artefacts for one ROI and return their summary.

    Returns ``None`` when there is nothing to confirm (a subject-space ROI, the
    artefact switched off) or when the artefact could not be produced — never
    raises, because a job must not fail because a picture did.
    """
    if not enabled() or str(space).lower() != "mni":
        return None
    import tempfile

    try:
        import nibabel as nib
        import numpy as np

        with tempfile.TemporaryDirectory(prefix="roi-confirm-") as scratch:
            mask_image = _subject_mask(atlas_path, label, "mni", m2m, scratch)
            mask = np.squeeze(np.asarray(mask_image.dataobj)) > 0
            voxels = np.argwhere(mask)
            if not len(voxels):
                raise ValueError("the transformed mask is empty")
            centroid_voxel = voxels.mean(axis=0)
            centroid = nib.affines.apply_affine(mask_image.affine, centroid_voxel)
            spacing = np.abs(np.linalg.det(mask_image.affine[:3, :3]))
            overlap = _gm_overlap(mask_image, m2m)
            label_name = name or (f"label {label}" if label is not None else Path(atlas_path).name)
            summary = {
                "roi": label_name,
                "space": "mni",
                "source": atlas_path,
                "label": label,
                "voxels": int(len(voxels)),
                "volume_mm3": round(float(len(voxels) * spacing), 1),
                "centroid_ras": [round(float(v), 1) for v in centroid],
                "gm_overlap": None if overlap is None else round(overlap, 3),
                "image": PNG_NAME,
            }
            destination = Path(out_dir)
            try:
                _render(
                    mask_image,
                    m2m,
                    centroid_voxel,
                    destination / PNG_NAME,
                    f"{label_name} (MNI to subject)",
                )
            except Exception as exc:  # noqa: BLE001 - a picture never fails a job
                logger.warning("ROI confirmation image could not be drawn: %s", exc)
                summary["image"] = None
            destination.mkdir(parents=True, exist_ok=True)
            (destination / JSON_NAME).write_text(
                json.dumps(summary, indent=1) + "\n", encoding="utf-8"
            )
            # The desktop's job Artifacts tab previews a PNG inline, so announcing
            # the file is the whole of "show it in the job's results".
            _announce(destination, summary)
        x, y, z = summary["centroid_ras"]
        overlap_text = (
            "GM overlap unknown"
            if summary["gm_overlap"] is None
            else f"GM overlap {summary['gm_overlap'] * 100:.0f} %"
        )
        # print(), not logger: the desktop captures the runner's stdout as the
        # job's terminal, and this line is for the person watching it.
        print(
            f"ROI {label_name} (MNI->subject): {summary['voxels']} voxels, "
            f"centroid ({x:g}, {y:g}, {z:g}) mm, {overlap_text} "
            f"-- see {PNG_NAME}",
            flush=True,
        )
        return summary
    except Exception as exc:  # noqa: BLE001 - never fail a job over a check
        logger.warning("ROI confirmation could not be written: %s", exc)
        return None


def _announce(destination: Path, summary: dict) -> None:
    """Report the artefacts as job artifacts, when a job is what is running."""
    try:
        from tit.jobs.events import emit_artifact

        if summary.get("image"):
            emit_artifact(
                str(destination / PNG_NAME), "png", f"ROI confirmation — {summary['roi']}"
            )
        emit_artifact(str(destination / JSON_NAME), "json", "ROI confirmation (values)")
    except Exception as exc:  # noqa: BLE001 - outside a job there is no sink
        logger.debug("ROI confirmation artifacts not announced: %s", exc)


def confirm_rois(entries, *, m2m: str, out_dir: str) -> list[dict]:
    """:func:`confirm_roi` over several targets; the first one keeps the plain
    file names, the rest are suffixed so a union of regions leaves one artefact
    per region rather than overwriting each other."""
    out: list[dict] = []
    for index, entry in enumerate(entries):
        directory = out_dir if index == 0 else os.path.join(out_dir, f"roi_{index + 1}")
        summary = confirm_roi(m2m=m2m, out_dir=directory, **entry)
        if summary:
            out.append(summary)
    return out
