"""Mesh (surface) atlas discovery and region listing."""

from __future__ import annotations

import glob
import os
from typing import Dict, List, Optional, Tuple

from tit.atlas.constants import BUILTIN_ATLASES


class MeshAtlasManager:
    """Discovers and queries FreeSurfer .annot mesh atlases.

    Args:
        seg_dir: Path to m2m_{subject}/segmentation/ directory.
    """

    def __init__(self, seg_dir: str) -> None:
        self.seg_dir = seg_dir

    def list_atlases(self) -> List[str]:
        """List available mesh atlas names.

        Returns:
            Sorted list of atlas names (always includes builtins).
        """
        discovered: List[str] = []
        if os.path.isdir(self.seg_dir):
            for fname in os.listdir(self.seg_dir):
                if fname.startswith("lh.") and fname.endswith(".annot"):
                    stem = fname[3:-6]
                    atlas_name = stem.split("_", 1)[-1] if "_" in stem else stem
                    if (
                        atlas_name not in discovered
                        and atlas_name not in BUILTIN_ATLASES
                    ):
                        discovered.append(atlas_name)
        return sorted(set(BUILTIN_ATLASES + discovered))

    def list_regions(self, atlas_name: str) -> List[str]:
        """List regions for a mesh atlas from .annot files.

        Returns:
            Sorted list of region names with hemisphere suffix (e.g. "precentral-lh").
        """
        if os.path.isdir(self.seg_dir):
            import nibabel.freesurfer as nfs

            regions: List[str] = []
            for hemi in ("lh", "rh"):
                matches = glob.glob(
                    os.path.join(self.seg_dir, f"{hemi}.*{atlas_name}.annot")
                )
                if not matches:
                    continue
                _, _, names = nfs.read_annot(matches[0])
                for n in names:
                    name = n.decode("utf-8") if isinstance(n, bytes) else str(n)
                    if name != "unknown":
                        regions.append(f"{name}-{hemi}")
            if regions:
                return sorted(regions)

        return []

    def find_atlas_file(self, atlas_name: str, hemisphere: str) -> Optional[str]:
        """Find the .annot file path for a given atlas and hemisphere.

        Returns:
            Path to the .annot file, or None if not found.
        """
        if not os.path.isdir(self.seg_dir):
            return None
        matches = glob.glob(
            os.path.join(self.seg_dir, f"{hemisphere}.*{atlas_name}.annot")
        )
        return matches[0] if matches else None

    def find_all_atlases(self, hemisphere: str) -> Dict[str, str]:
        """Find all available atlas files for a hemisphere.

        Returns:
            Dict mapping atlas display name to file path.
        """
        atlas_map: Dict[str, str] = {}
        if not os.path.isdir(self.seg_dir):
            return atlas_map
        pattern = f"{hemisphere}.*.annot"
        for atlas_file in sorted(glob.glob(os.path.join(self.seg_dir, pattern))):
            fname = os.path.basename(atlas_file)
            parts = fname.split(".")
            if len(parts) == 3 and parts[2] == "annot":
                atlas_full = parts[1]
                atlas_display = (
                    atlas_full.split("_", 1)[-1] if "_" in atlas_full else atlas_full
                )
                atlas_map[atlas_display] = atlas_file
        return atlas_map

    def list_annot_regions(self, annot_path: str) -> List[Tuple[int, str]]:
        """List all regions in a .annot file.

        Returns:
            List of (region_index, region_name) tuples.
        """
        import nibabel.freesurfer.io as fsio

        labels, ctab, names = fsio.read_annot(annot_path)
        regions = []
        for i, name in enumerate(names):
            region_name = name.decode("utf-8") if isinstance(name, bytes) else str(name)
            regions.append((i, region_name))
        return regions
