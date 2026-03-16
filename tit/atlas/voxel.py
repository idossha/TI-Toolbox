"""Voxel (volumetric) atlas discovery and region listing."""

from __future__ import annotations

import os
import subprocess
from typing import Dict, List, Optional, Tuple

from tit.atlas.constants import VOXEL_ATLAS_FILES, MNI_ATLAS_FILES


class VoxelAtlasManager:
    """Discovers and queries volumetric atlas files.

    All discovery methods use the same canonical ``VOXEL_ATLAS_FILES`` list
    so that the analyzer, flex-search, and NIfTI viewer show identical atlases.

    Args:
        freesurfer_mri_dir: Path to FreeSurfer mri/ directory.
        seg_dir: Path to m2m_{subject}/segmentation/ directory.
    """

    def __init__(self, freesurfer_mri_dir: str = "", seg_dir: str = "") -> None:
        self.freesurfer_mri_dir = freesurfer_mri_dir
        self.seg_dir = seg_dir

    def list_atlases(self) -> List[Tuple[str, str]]:
        """Discover available voxel atlas files for a subject.

        Checks FreeSurfer mri/ for VOXEL_ATLAS_FILES and segmentation/
        for labeling.nii.gz.  Used by analyzer tab, flex subcortical tab,
        and NIfTI viewer.

        Returns:
            List of (display_name, full_path) tuples.
        """
        results: List[Tuple[str, str]] = []

        if self.freesurfer_mri_dir and os.path.isdir(self.freesurfer_mri_dir):
            for name in VOXEL_ATLAS_FILES:
                path = os.path.join(self.freesurfer_mri_dir, name)
                if os.path.isfile(path):
                    results.append((name, path))

        if self.seg_dir:
            labeling = os.path.join(self.seg_dir, "labeling.nii.gz")
            if os.path.isfile(labeling):
                results.append(("labeling.nii.gz", labeling))

        return results

    def list_regions(self, atlas_path: str) -> List[str]:
        """List regions in a voxel atlas using mri_segstats.

        Caches the label file next to the atlas so subsequent calls are fast.

        Returns:
            Sorted list of "RegionName (ID: N)" strings.
        """
        atlas_bname = os.path.splitext(os.path.basename(atlas_path))[0]
        if atlas_bname.endswith(".nii"):
            atlas_bname = os.path.splitext(atlas_bname)[0]
        labels_file = os.path.join(
            os.path.dirname(atlas_path), f"{atlas_bname}_labels.txt"
        )

        if not os.path.isfile(labels_file):
            cmd = [
                "mri_segstats",
                "--seg",
                atlas_path,
                "--excludeid",
                "0",
                "--ctab-default",
                "--sum",
                labels_file,
            ]
            subprocess.run(cmd, check=True, capture_output=True)

        regions: List[str] = []
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
    def detect_mni_atlases(atlas_dir: str) -> List[str]:
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

    def find_labeling_lut(self) -> Optional[str]:
        """Find the LUT file for the SimNIBS labeling atlas.

        Returns:
            Path to labeling_LUT.txt if it exists, else None.
        """
        lut_path = os.path.join(self.seg_dir, "labeling_LUT.txt")
        return lut_path if os.path.isfile(lut_path) else None
