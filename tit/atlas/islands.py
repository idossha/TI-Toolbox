"""Remove the detached islands charm's ``labeling.nii.gz`` leaves in a region.

Why this exists
---------------
``m2m_<id>/segmentation/labeling.nii.gz`` is an atlas warped into the subject and
intersected with tissue labels, so a region is not guaranteed to be one connected
body.  Measured on the packaged Ernie head model (2026-09-17, 26-connectivity,
``scipy.ndimage.label``):

===========================  ==========  ======  =====  =========  ==========
region                       components   total  minor  minor (%)  farthest
===========================  ==========  ======  =====  =========  ==========
Left-Putamen                         10    6109     77      1.26      38.2 mm
Right-Thalamus-Proper                13    7346     70      0.95      44.3 mm
Right-Putamen                         3    5727      3      0.05      13.2 mm
Left-Hippocampus                      2    4298      2      0.05      19.4 mm
===========================  ==========  ======  =====  =========  ==========

Left-Putamen's main body is 6032 voxels; the rest is one 67-voxel blob 36.9 mm
away plus seven specks of one or two voxels 22–38 mm away.  That is exactly the
"second blob inferior-anterior plus grey debris" a user reported seeing in the
scene pane, and the left/right asymmetry (10 components against 3 for the same
structure in the same subject) is what says it is a segmentation artefact rather
than anatomy or a defect in our surface extraction.

So the islands are upstream data, and they were never only cosmetic: 77 voxels
sitting 37 mm outside the putamen are averaged into the ROI field and into a
focality denominator exactly like the other 6032.  This module is therefore
applied to the mask used for search and analysis *and* to the display surface,
so the pane shows what will be optimised.

Threshold
---------
A component is kept when it has at least ``max(5% of the largest component, 50
voxels)`` voxels.  The 5% term is what separates a genuine bilateral or bipartite
structure from debris; the 50-voxel floor stops a tiny region (Optic-Chiasm is 90
voxels in Ernie) from being reduced to a single component by the ratio alone.  On
the table above it removes the 67-voxel blob and every speck from Left-Putamen
and keeps every region whose components are real.

Escape hatch
------------
``TIT_ROI_KEEP_ISLANDS=1`` disables the cleanup everywhere, for a subject whose
segmentation genuinely is multi-component.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: A component survives if it has at least this fraction of the largest one's voxels.
MIN_FRACTION_OF_LARGEST = 0.05
#: ...and never fewer than this many voxels, so small regions keep their real parts.
MIN_VOXELS = 50


def cleanup_enabled() -> bool:
    """False when ``TIT_ROI_KEEP_ISLANDS`` asks for the raw segmentation."""
    return os.environ.get("TIT_ROI_KEEP_ISLANDS", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    )


def keep_main_components(mask, *, what: str = "region"):
    """Return *mask* without its detached islands, plus the number of voxels dropped.

    *mask* is a boolean 3-D array.  Connectivity is 26-neighbour (the most
    generous, so nothing is split on a diagonal touch).  Returns
    ``(cleaned_mask, removed_voxels, removed_components)``; an empty mask, a
    single-component mask, or a disabled cleanup returns the input unchanged with
    ``(mask, 0, 0)``.  *what* only names the region in the log line.
    """
    import numpy as np

    mask = np.asarray(mask, dtype=bool)
    if not cleanup_enabled() or not mask.any():
        return mask, 0, 0
    from scipy import ndimage

    labelled, count = ndimage.label(
        mask, structure=ndimage.generate_binary_structure(3, 3)
    )
    if count < 2:
        return mask, 0, 0
    sizes = np.bincount(labelled.ravel())
    sizes[0] = 0
    largest = int(sizes.max())
    threshold = max(MIN_VOXELS, largest * MIN_FRACTION_OF_LARGEST)
    keep = sizes >= threshold
    cleaned = keep[labelled]
    removed = int(mask.sum() - cleaned.sum())
    dropped = int(count - keep[1:].sum())
    if removed:
        logger.info(
            "%s: removed %d detached voxel(s) in %d island(s) from the "
            "segmentation; the largest component has %d voxels "
            "(set TIT_ROI_KEEP_ISLANDS=1 to keep them)",
            what,
            removed,
            dropped,
            largest,
        )
    return cleaned, removed, dropped


def cleaned_label_mask(atlas_path: str, label: int, output_dir: str) -> str | None:
    """Write a binary mask of *label* with its islands removed; ``None`` if there are none.

    ``None`` is the common answer and means "use the atlas and the label directly":
    the optimizers pass ``(atlas_path, label)`` straight to SimNIBS, and there is no
    reason to materialise a file, or to change what they do, for a region that is
    already one connected body.  When there *are* islands the caller uses the
    returned path with mask value ``1`` instead.

    The file is named from the atlas's path, size and modification time plus the
    label, so a second search on the same subject reuses it rather than rewriting it.
    """
    import hashlib
    from pathlib import Path

    import nibabel as nib
    import numpy as np

    if not cleanup_enabled():
        return None
    source = Path(atlas_path)
    stat = source.stat()
    key = hashlib.sha256(
        f"{source.resolve()}|{stat.st_size}|{int(stat.st_mtime)}|{label}|"
        f"{MIN_FRACTION_OF_LARGEST}|{MIN_VOXELS}".encode()
    ).hexdigest()[:16]
    destination = Path(output_dir) / f"roi-{source.stem.split('.')[0]}-{label}-{key}.nii"
    if destination.is_file():
        return str(destination)
    image = nib.load(str(source))
    mask = np.asanyarray(image.dataobj) == label
    if not mask.any():
        return None
    cleaned, removed, _ = keep_main_components(mask, what=f"{source.name} label {label}")
    if not removed:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    # The source header is deliberately not reused: it carries the atlas's own
    # datatype and scaling, and this file is a plain 0/1 mask.
    nib.save(nib.Nifti1Image(cleaned.astype(np.uint8), image.affine), str(destination))
    return str(destination)
