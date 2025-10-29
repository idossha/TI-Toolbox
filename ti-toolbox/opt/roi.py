#!/usr/bin/env python3
"""Shared ROI (Region of Interest) module for ex-search and movea.

This module provides a unified interface for ROI operations using SimNIBS's
RegionOfInterest class. It supports:
- Spherical ROIs with MNI/subject space coordinates
- Atlas-based cortical ROIs (surface)
- Volume-based subcortical ROIs
- ROI visualization and mesh extraction

Note: flex-search has its own specialized ROI module (flex/roi.py) that
integrates directly with SimNIBS optimization structures.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Optional, Union, List, Tuple
import numpy as np
import numpy.typing as npt

# SimNIBS imports - these are available in the docker container
try:
    from simnibs.utils.region_of_interest import RegionOfInterest
    from simnibs.mesh_tools.mesh_io import Msh, read_msh, ElementTags
    from simnibs.utils.transformations import mni2subject_coords
    SIMNIBS_AVAILABLE = True
except ImportError:
    SIMNIBS_AVAILABLE = False
    print("Warning: SimNIBS not available. ROI functionality will be limited.")

if TYPE_CHECKING:
    from typing import Dict, Any


class ROIManager:
    """High-level interface for creating and managing ROIs using SimNIBS RegionOfInterest.
    
    This class simplifies ROI creation for common use cases in ex-search and movea.
    """
    
    def __init__(self, m2m_path: str, mesh_path: Optional[str] = None):
        """Initialize ROI manager.
        
        Args:
            m2m_path: Path to the m2m folder (e.g., /path/to/m2m_subject)
            mesh_path: Optional path to the head mesh. If not provided, will be
                      loaded from m2m folder when needed.
        """
        if not SIMNIBS_AVAILABLE:
            raise ImportError("SimNIBS is required for ROI functionality")
        
        self.m2m_path = m2m_path
        self.mesh_path = mesh_path
        self._mesh = None
        
        # Validate paths
        if not os.path.isdir(m2m_path):
            raise ValueError(f"m2m folder not found: {m2m_path}")
    
    @property
    def mesh(self) -> Msh:
        """Lazy load the head mesh."""
        if self._mesh is None:
            if self.mesh_path is not None:
                self._mesh = read_msh(self.mesh_path)
            else:
                # Load from m2m folder
                default_mesh = os.path.join(self.m2m_path, f"{os.path.basename(self.m2m_path)}.msh")
                if os.path.exists(default_mesh):
                    self._mesh = read_msh(default_mesh)
                else:
                    raise ValueError(f"Could not find mesh in m2m folder: {self.m2m_path}")
        return self._mesh
    
    def create_spherical_roi(
        self,
        center: Union[List[float], npt.NDArray],
        radius: float,
        coordinate_space: str = "subject",
        roi_type: str = "surface",
        tissues: Optional[List[int]] = None
    ) -> RegionOfInterest:
        """Create a spherical ROI.
        
        Args:
            center: Center coordinates [x, y, z] in mm
            radius: Radius in mm
            coordinate_space: "subject" or "mni" coordinate space
            roi_type: "surface" for cortical or "volume" for subcortical
            tissues: List of tissue tags for volume ROIs (default: [ElementTags.GM])
        
        Returns:
            Configured RegionOfInterest object
        """
        roi = RegionOfInterest()
        roi.subpath = self.m2m_path
        
        if roi_type == "surface":
            roi.method = "surface"
            roi.surface_type = "central"
            roi.roi_sphere_center_space = coordinate_space
            roi.roi_sphere_center = list(center)
            roi.roi_sphere_radius = radius
        elif roi_type == "volume":
            roi.method = "volume"
            roi.mesh = self.mesh
            roi.roi_sphere_center_space = coordinate_space
            roi.roi_sphere_center = list(center)
            roi.roi_sphere_radius = radius
            roi.tissues = tissues if tissues is not None else [ElementTags.GM]
        else:
            raise ValueError(f"Invalid roi_type: {roi_type}. Must be 'surface' or 'volume'")
        
        return roi
    
    def create_atlas_roi(
        self,
        atlas_path: str,
        label_value: int,
        hemisphere: str = "lh"
    ) -> RegionOfInterest:
        """Create a cortical atlas-based ROI.
        
        Args:
            atlas_path: Path to atlas file (.annot, .label, or surface mask file)
            label_value: Label value in the atlas to use as ROI
            hemisphere: "lh" or "rh" for left/right hemisphere
        
        Returns:
            Configured RegionOfInterest object
        """
        if not os.path.exists(atlas_path):
            raise ValueError(f"Atlas file not found: {atlas_path}")
        
        roi = RegionOfInterest()
        roi.subpath = self.m2m_path
        roi.method = "surface"
        roi.surface_type = "central"
        roi.mask_space = [f"subject_{hemisphere}"]
        roi.mask_path = [atlas_path]
        roi.mask_value = [label_value]
        
        return roi
    
    def create_volume_roi(
        self,
        mask_path: str,
        mask_value: int = 1,
        coordinate_space: str = "subject",
        tissues: Optional[List[int]] = None
    ) -> RegionOfInterest:
        """Create a volume-based ROI from a NIfTI mask.
        
        Args:
            mask_path: Path to NIfTI volume mask (.nii or .nii.gz)
            mask_value: Value in the mask representing the ROI
            coordinate_space: "subject" or "mni" coordinate space
            tissues: List of tissue tags to restrict ROI to (default: [ElementTags.GM])
        
        Returns:
            Configured RegionOfInterest object
        """
        if not os.path.exists(mask_path):
            raise ValueError(f"Mask file not found: {mask_path}")
        
        roi = RegionOfInterest()
        roi.subpath = self.m2m_path
        roi.method = "volume"
        roi.mesh = self.mesh
        roi.mask_space = [coordinate_space]
        roi.mask_path = [mask_path]
        roi.mask_value = [mask_value]
        roi.tissues = tissues if tissues is not None else [ElementTags.GM]
        
        return roi
    
    def get_roi_coordinates(
        self,
        roi: RegionOfInterest,
        node_type: Optional[str] = None
    ) -> npt.NDArray[np.float_]:
        """Extract coordinates from an ROI.
        
        Args:
            roi: RegionOfInterest object
            node_type: "node" for node coordinates, "elm_center" for element centers,
                      None for automatic based on ROI type
        
        Returns:
            Array of coordinates [N, 3]
        """
        return roi.get_nodes(node_type=node_type)
    
    def get_roi_mesh(self, roi: RegionOfInterest) -> Msh:
        """Extract the ROI as a mesh.
        
        Args:
            roi: RegionOfInterest object
        
        Returns:
            Mesh containing only the ROI
        """
        return roi.get_roi_mesh()
    
    def visualize_roi(
        self,
        roi: RegionOfInterest,
        output_dir: str,
        base_name: str = "roi_visualization"
    ) -> str:
        """Create visualization files for the ROI.
        
        Args:
            roi: RegionOfInterest object
            output_dir: Directory to save visualization files
            base_name: Base name for output files
        
        Returns:
            Path to the main visualization file (.msh)
        """
        os.makedirs(output_dir, exist_ok=True)
        roi.write_visualization(output_dir, base_name)
        return os.path.join(output_dir, f"{base_name}.msh")


class ROICoordinateHelper:
    """Helper functions for coordinate transformation and ROI specification.
    
    These utilities are useful for both ex-search and movea workflows.
    """
    
    @staticmethod
    def transform_mni_to_subject(
        mni_coords: Union[List[float], npt.NDArray],
        m2m_path: str
    ) -> npt.NDArray:
        """Transform MNI coordinates to subject space.
        
        Args:
            mni_coords: MNI coordinates [x, y, z]
            m2m_path: Path to m2m folder
        
        Returns:
            Subject space coordinates [x, y, z]
        """
        if not SIMNIBS_AVAILABLE:
            raise ImportError("SimNIBS is required for coordinate transformation")
        
        return mni2subject_coords(list(mni_coords), m2m_path)
    
    @staticmethod
    def find_voxels_in_sphere(
        voxel_positions: npt.NDArray,
        center: Union[List[float], npt.NDArray],
        radius: float
    ) -> npt.NDArray[np.int_]:
        """Find voxel indices within a spherical ROI.
        
        Useful for MOVEA-style optimization where you need to identify
        target voxels in a leadfield matrix.
        
        Args:
            voxel_positions: Array of voxel positions [N, 3]
            center: Center coordinate [x, y, z]
            radius: Radius in mm
        
        Returns:
            Array of voxel indices within the sphere
        """
        center = np.array(center)
        distances = np.linalg.norm(voxel_positions - center, axis=1)
        return np.where(distances <= radius)[0]
    
    @staticmethod
    def compute_roi_centroid(coordinates: npt.NDArray) -> npt.NDArray:
        """Compute the centroid of an ROI.
        
        Args:
            coordinates: Array of coordinates [N, 3]
        
        Returns:
            Centroid coordinate [x, y, z]
        """
        return np.mean(coordinates, axis=0)
    
    @staticmethod
    def compute_roi_bounds(
        coordinates: npt.NDArray
    ) -> Tuple[npt.NDArray, npt.NDArray]:
        """Compute bounding box of an ROI.
        
        Args:
            coordinates: Array of coordinates [N, 3]
        
        Returns:
            Tuple of (min_coords, max_coords) each [x, y, z]
        """
        return np.min(coordinates, axis=0), np.max(coordinates, axis=0)
    
    @staticmethod
    def load_roi_from_csv(csv_path: str) -> npt.NDArray:
        """Load ROI coordinates from CSV file.
        
        Supports the ex-search CSV format with single coordinate [x, y, z].
        
        Args:
            csv_path: Path to CSV file
        
        Returns:
            Coordinate array [x, y, z]
        """
        import csv
        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            coords = next(reader)
            return np.array([float(c) for c in coords])
    
    @staticmethod
    def save_roi_to_csv(coordinates: Union[List[float], npt.NDArray], csv_path: str):
        """Save ROI coordinates to CSV file.
        
        Uses ex-search compatible format.
        
        Args:
            coordinates: Coordinate [x, y, z]
            csv_path: Path to save CSV file
        """
        import csv
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(coordinates)


def create_roi_from_preset(
    preset_name: str,
    m2m_path: str,
    radius: float = 10.0,
    roi_type: str = "surface"
) -> RegionOfInterest:
    """Create an ROI from a preset target (for MOVEA compatibility).
    
    Args:
        preset_name: Name of preset region (e.g., "motor", "dlpfc", "hippocampus")
        m2m_path: Path to m2m folder
        radius: Radius in mm (default: 10)
        roi_type: "surface" or "volume"
    
    Returns:
        Configured RegionOfInterest object
    """
    # Load presets from movea
    import json
    preset_path = os.path.join(
        os.path.dirname(__file__),
        "movea",
        "presets.json"
    )
    
    if not os.path.exists(preset_path):
        raise ValueError(f"Presets file not found: {preset_path}")
    
    with open(preset_path, 'r') as f:
        presets = json.load(f)
    
    if preset_name not in presets.get("regions", {}):
        available = ", ".join(presets.get("regions", {}).keys())
        raise ValueError(
            f"Unknown preset: {preset_name}. Available presets: {available}"
        )
    
    mni_coords = presets["regions"][preset_name]["mni"]
    
    # Create ROI manager and build spherical ROI
    manager = ROIManager(m2m_path)
    roi = manager.create_spherical_roi(
        center=mni_coords,
        radius=radius,
        coordinate_space="mni",
        roi_type=roi_type
    )
    
    return roi


def roi_to_dict(roi: RegionOfInterest) -> Dict[str, Any]:
    """Convert RegionOfInterest to dictionary for serialization.
    
    Args:
        roi: RegionOfInterest object
    
    Returns:
        Dictionary representation
    """
    return roi.to_dict()


def roi_from_dict(roi_dict: Dict[str, Any]) -> RegionOfInterest:
    """Create RegionOfInterest from dictionary.
    
    Args:
        roi_dict: Dictionary representation
    
    Returns:
        RegionOfInterest object
    """
    roi = RegionOfInterest()
    roi.from_dict(roi_dict)
    return roi


# Convenience functions for backward compatibility with existing code

def create_spherical_roi_simple(
    center: List[float],
    radius: float,
    m2m_path: str,
    coordinate_space: str = "subject"
) -> Tuple[RegionOfInterest, ROIManager]:
    """Simple interface for creating a spherical cortical ROI.
    
    Args:
        center: Center coordinates [x, y, z]
        radius: Radius in mm
        m2m_path: Path to m2m folder
        coordinate_space: "subject" or "mni"
    
    Returns:
        Tuple of (roi, manager)
    """
    manager = ROIManager(m2m_path)
    roi = manager.create_spherical_roi(
        center=center,
        radius=radius,
        coordinate_space=coordinate_space,
        roi_type="surface"
    )
    return roi, manager


def get_roi_voxel_indices(
    roi: RegionOfInterest,
    voxel_positions: npt.NDArray
) -> npt.NDArray[np.int_]:
    """Get indices of voxels that fall within an ROI.
    
    Useful for MOVEA leadfield-based optimization.
    
    Args:
        roi: RegionOfInterest object
        voxel_positions: Array of all voxel positions [N, 3]
    
    Returns:
        Array of indices of voxels within the ROI
    """
    roi_coords = roi.get_nodes()
    
    # For each ROI coordinate, find closest voxels
    from scipy.spatial import cKDTree
    tree = cKDTree(voxel_positions)
    
    # Find voxels within 1mm of any ROI coordinate
    indices_list = tree.query_ball_point(roi_coords, r=1.0)
    
    # Flatten and get unique indices
    indices = np.unique(np.concatenate([np.array(idx_list) for idx_list in indices_list if len(idx_list) > 0]))
    
    return indices


# Example usage and documentation
if __name__ == "__main__":
    print("ROI Module for ex-search and movea")
    print("=" * 50)
    print("\nThis module provides a unified interface for ROI operations")
    print("using SimNIBS's RegionOfInterest class.\n")
    
    print("Example 1: Create a spherical cortical ROI")
    print("-" * 50)
    print("""
    from opt.roi import ROIManager
    
    manager = ROIManager("/path/to/m2m_subject")
    roi = manager.create_spherical_roi(
        center=[47, -13, 52],  # Motor cortex in MNI
        radius=10.0,
        coordinate_space="mni",
        roi_type="surface"
    )
    
    # Get ROI coordinates
    coords = manager.get_roi_coordinates(roi)
    print(f"ROI contains {len(coords)} nodes")
    """)
    
    print("\nExample 2: Create an atlas-based ROI")
    print("-" * 50)
    print("""
    roi = manager.create_atlas_roi(
        atlas_path="/path/to/lh.aparc.a2009s.annot",
        label_value=1,  # Specific region label
        hemisphere="lh"
    )
    """)
    
    print("\nExample 3: Create a volume ROI for subcortical structures")
    print("-" * 50)
    print("""
    roi = manager.create_volume_roi(
        mask_path="/path/to/hippocampus_mask.nii.gz",
        mask_value=1,
        coordinate_space="subject"
    )
    """)
    
    print("\nExample 4: Use preset ROIs (MOVEA compatibility)")
    print("-" * 50)
    print("""
    from opt.roi import create_roi_from_preset
    
    roi = create_roi_from_preset(
        preset_name="motor",
        m2m_path="/path/to/m2m_subject",
        radius=10.0
    )
    """)
    
    print("\nExample 5: Coordinate transformation")
    print("-" * 50)
    print("""
    from opt.roi import ROICoordinateHelper
    
    # Transform MNI to subject space
    subject_coords = ROICoordinateHelper.transform_mni_to_subject(
        mni_coords=[47, -13, 52],
        m2m_path="/path/to/m2m_subject"
    )
    """)

