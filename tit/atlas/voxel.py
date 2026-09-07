"""Voxel (volumetric) atlas discovery and region listing."""

import os
import re

from tit.atlas.constants import (
    FASTSURFER_ATLAS_FILES,
    LEGACY_FREESURFER_ATLAS_FILES,
    MNI_ATLAS_FILES,
    MASK_EXTENSIONS,
)
from tit.atlas.segstats import (
    compute_segstats,
    resolve_lut_for_atlas,
    write_segstats_sum,
)


def parse_region_label(region_display: str) -> int:
    """Extract the integer label from a :meth:`VoxelAtlasManager.list_regions`
    entry, e.g. ``"Hippocampus (ID: 17)"`` -> ``17``.

    Args:
        region_display: A ``"RegionName (ID: N)"`` string.

    Returns:
        The integer label.

    Raises:
        ValueError: If *region_display* does not end in ``"(ID: <int>)"``.
    """
    match = re.search(r"\(ID:\s*(-?\d+)\)\s*$", region_display)
    if not match:
        raise ValueError(
            f"Could not parse an atlas region label from {region_display!r}"
        )
    return int(match.group(1))


class VoxelAtlasManager:
    """Discovers and queries volumetric atlas files.

    All discovery methods use the same canonical atlas-name lists from
    :mod:`tit.atlas.constants` so that the analyzer, flex-search and NIfTI
    viewer show identical atlases.

    Search order for a name present in both trees: ``fastsurfer_mri_dir``
    first, then ``freesurfer_mri_dir``. The two never collide in practice --
    FastSurfer writes ``aparc.DKTatlas+aseg.deep.*`` and recon-all writes
    ``aparc.DKTatlas+aseg.mgz`` -- but the order is fixed so a project that
    holds both offers the current pipeline's output first.

    Args:
        freesurfer_mri_dir: Path to a legacy FreeSurfer ``mri/`` directory
            (``derivatives/freesurfer/sub-<id>/mri``). Read-only: nothing in
            the toolbox writes there any more.
        fastsurfer_mri_dir: Path to the FastSurfer ``mri/`` directory
            (``derivatives/fastsurfer/sub-<id>/mri``).
        seg_dir: Path to m2m_{subject}/segmentation/ directory.
        masks_dir: Path to m2m_{subject}/masks/, holding user-supplied custom
            label volumes.  Optional; most subjects have no such directory.
    """

    def __init__(
        self,
        freesurfer_mri_dir: str = "",
        seg_dir: str = "",
        masks_dir: str = "",
        fastsurfer_mri_dir: str = "",
    ) -> None:
        self.freesurfer_mri_dir = freesurfer_mri_dir
        self.fastsurfer_mri_dir = fastsurfer_mri_dir
        self.seg_dir = seg_dir
        self.masks_dir = masks_dir

    def list_atlases(self) -> list[tuple[str, str]]:
        """Discover available voxel atlas files for a subject.

        Checks FastSurfer ``mri/`` first, then a legacy FreeSurfer ``mri/``,
        then ``segmentation/`` for charm's own ``labeling.nii.gz``, then
        ``masks/`` for any user-supplied label volume. Used by the analyzer
        tab, the flex subcortical tab and the NIfTI viewer.

        Returns:
            List of (display_name, full_path) tuples, first match per name.
        """
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        for mri_dir, names in (
            (self.fastsurfer_mri_dir, FASTSURFER_ATLAS_FILES),
            (self.freesurfer_mri_dir, LEGACY_FREESURFER_ATLAS_FILES),
        ):
            if not mri_dir or not os.path.isdir(mri_dir):
                continue
            for name in names:
                if name in seen:
                    continue
                path = os.path.join(mri_dir, name)
                if os.path.isfile(path):
                    results.append((name, path))
                    seen.add(name)

        if self.seg_dir:
            labeling = os.path.join(self.seg_dir, "labeling.nii.gz")
            if os.path.isfile(labeling):
                results.append(("labeling.nii.gz", labeling))

        results.extend(self.list_custom_masks())

        return results

    def list_custom_masks(self) -> list[tuple[str, str]]:
        """Discover user-supplied label volumes in the subject's masks/ dir.

        Any ``*.nii.gz``/``*.nii``/``*.mgz`` file dropped into
        ``m2m_{subject}/masks/`` is offered for targeting.  Display names are
        prefixed with ``masks/`` so custom entries are distinguishable from
        the curated atlases.  A missing directory yields no entries.

        Returns:
            Sorted list of (display_name, full_path) tuples.
        """
        if not self.masks_dir or not os.path.isdir(self.masks_dir):
            return []

        found: list[tuple[str, str]] = []
        for name in sorted(os.listdir(self.masks_dir)):
            if not name.lower().endswith(MASK_EXTENSIONS):
                continue
            path = os.path.join(self.masks_dir, name)
            if os.path.isfile(path):
                found.append((f"masks/{name}", path))
        return found

    def list_regions(self, atlas_path: str) -> list[str]:
        """List regions in a voxel atlas.

        Pure-Python replacement for shelling out to FreeSurfer's
        ``mri_segstats``: labels present in the volume come from
        :func:`~tit.atlas.segstats.compute_segstats` (nibabel + numpy),
        named via :func:`~tit.atlas.segstats.resolve_lut_for_atlas` (a
        sidecar colour table next to the atlas, else the bundled standard
        FreeSurfer colour table). Validated voxel-for-voxel against live
        ``mri_segstats`` output on real recon-all data -- see
        ``docs/dev/SPIKES.md``.

        Caches the label file next to the atlas, in ``mri_segstats
        --sum``'s own text layout (other modules parse this exact sidecar
        filename), so subsequent calls skip recomputation.

        Returns:
            Sorted list of "RegionName (ID: N)" strings.
        """
        atlas_bname = os.path.splitext(os.path.basename(atlas_path))[0]
        if atlas_bname.endswith(".nii"):
            atlas_bname = os.path.splitext(atlas_bname)[0]
        labels_file = os.path.join(
            os.path.dirname(atlas_path), f"{atlas_bname}_labels.txt"
        )

        if os.path.isfile(labels_file):
            return self._parse_labels_file(labels_file)

        lut = resolve_lut_for_atlas(atlas_path)
        stats = compute_segstats(atlas_path, lut)
        write_segstats_sum(stats, labels_file)
        return sorted({f"{s.name} (ID: {s.seg_id})" for s in stats})

    @staticmethod
    def _parse_labels_file(labels_file: str) -> list[str]:
        """Parse a cached ``mri_segstats --sum``-format labels file.

        Reads a pre-existing cache -- whether written by this module's own
        :func:`~tit.atlas.segstats.write_segstats_sum` or (for a project
        whose cache predates this change) by a real ``mri_segstats`` run --
        both share the same ``Index SegId NVoxels Volume_mm3 StructName``
        column layout.
        """
        regions: list[str] = []
        in_header = True
        with open(labels_file) as fh:
            for line in fh:
                if in_header and not line.startswith("#"):
                    in_header = False
                if not in_header and line.strip():
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        name = " ".join(parts[4:])
                        seg_id = parts[1]
                        regions.append(f"{name} (ID: {seg_id})")

        return sorted(set(regions))

    @staticmethod
    def detect_mni_atlases(atlas_dir: str) -> list[str]:
        """Detect available MNI atlases in an assets directory.

        Args:
            atlas_dir: Path to the atlas resources directory.

        Returns:
            List of full paths to found MNI atlas files.
        """
        if not os.path.isdir(atlas_dir):
            return []
        return [
            os.path.join(atlas_dir, p)
            for p in MNI_ATLAS_FILES
            if os.path.isfile(os.path.join(atlas_dir, p))
        ]

    def find_labeling_lut(self) -> str | None:
        """Find the LUT file for the SimNIBS labeling atlas.

        Returns:
            Path to labeling_LUT.txt if it exists, else None.
        """
        lut_path = os.path.join(self.seg_dir, "labeling_LUT.txt")
        return lut_path if os.path.isfile(lut_path) else None
