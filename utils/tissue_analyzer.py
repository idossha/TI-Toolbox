#!/usr/bin/env python3
"""
Unified Tissue Analysis Tool for TI-toolbox
Analyzes different tissue types (CSF, bone, etc.) from segmented tissue data.
Supports multiple tissue labels and configurable analysis parameters.

Author: TI-toolbox
Date: 2025
"""

import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from scipy import ndimage
from scipy.spatial.distance import cdist
import os
import argparse
import logging
from pathlib import Path
from abc import ABC, abstractmethod

# Logging setup: integrate with shared logging utility if available
try:
    from logging_util import get_logger
    # Only create a file logger if TI_LOG_FILE environment variable is set
    # This prevents duplicate logging when called from the bash script
    log_file = os.environ.get('TI_LOG_FILE')
    if log_file:
        LOGGER = get_logger('tissue_analyzer', log_file=log_file, overwrite=False)
    else:
        # Just use console logging when no file is specified
        LOGGER = get_logger('tissue_analyzer')
    # Set to DEBUG level to capture all detailed information
    LOGGER.setLevel(logging.DEBUG)
except Exception:
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    LOGGER = logging.getLogger('tissue_analyzer')
    LOGGER.setLevel(logging.DEBUG)

class TissueAnalyzer(ABC):
    """Base class for tissue analysis with common functionality."""
    
    def __init__(self, nifti_path, output_dir, tissue_config):
        """
        Initialize the tissue analyzer.
        
        Args:
            nifti_path (str): Path to the segmented NIfTI file
            output_dir (str): Directory to save output files
            tissue_config (dict): Tissue-specific configuration
        """
        self.nifti_path = nifti_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Load configuration
        self.tissue_name = tissue_config['name']
        self.tissue_labels = tissue_config['labels']
        self.padding_voxels = tissue_config['padding']
        self.color_scheme = tissue_config['color_scheme']
        self.brain_labels = tissue_config['brain_labels']
        
        # Load the NIfTI file
        LOGGER.info(f"Loading NIfTI file: {nifti_path}")
        self.nii = nib.load(nifti_path)
        self.data = self.nii.get_fdata()
        self.affine = self.nii.affine
        self.header = self.nii.header
        
        # Get voxel dimensions for volume calculations
        self.voxel_dims = self.nii.header.get_zooms()[:3]
        self.voxel_volume = np.prod(self.voxel_dims)
        
        # Load label-to-name mapping from labeling_LUT.txt
        self.label_names = self._load_label_names()
        
        LOGGER.debug(f"Data shape: {self.data.shape}")
        LOGGER.debug(f"Total image voxels: {np.prod(self.data.shape):,}")
        LOGGER.debug(f"Voxel dimensions: {self.voxel_dims} mm")
        LOGGER.debug(f"Voxel volume: {self.voxel_volume:.3f} mm³")
        LOGGER.debug(f"Tissue: {self.tissue_name}")
        LOGGER.debug(f"Labels: {self.tissue_labels}")
        LOGGER.debug(f"Label names loaded: {len(self.label_names)} mappings")
        
        # Log the specific labels being analyzed with their names
        LOGGER.debug(f"Tissue labels with names:")
        for label in self.tissue_labels:
            label_name = self.get_label_name(label)
            LOGGER.debug(f"  Label {label:2d}: {label_name}")
    
    def set_tissue_labels(self, labels):
        """Set custom tissue labels for analysis."""
        if not isinstance(labels, list):
            raise ValueError("Labels must be a list of integers")
        if not all(isinstance(label, int) for label in labels):
            raise ValueError("All labels must be integers")
        
        self.tissue_labels = labels
        LOGGER.info(f"{self.tissue_name} labels updated to: {self.tissue_labels}")
        
        # Re-extract masks if data is already loaded
        if hasattr(self, 'all_tissue_mask') and hasattr(self, 'data'):
            LOGGER.debug(f"Re-extracting masks with new labels: {self.tissue_labels}")
            self.extract_tissue_mask()
    
    def _load_label_names(self):
        """
        Load label-to-name mapping from labeling_LUT.txt file.
        Returns a dictionary mapping numeric labels to tissue names.
        """
        label_names = {}
        
        # Try to find labeling_LUT.txt in common locations
        possible_lut_paths = []
        
        # 1. Check if nifti_path is in a derivatives/SimNIBS structure
        nifti_path = Path(self.nifti_path)
        if 'derivatives' in nifti_path.parts and 'SimNIBS' in nifti_path.parts:
            # Try to find the segmentation directory
            for i, part in enumerate(nifti_path.parts):
                if part == 'SimNIBS':
                    if i + 1 < len(nifti_path.parts):
                        subject_dir = nifti_path.parts[i + 1]
                        if subject_dir.startswith('sub-'):
                            # Look for m2m directory
                            simnibs_dir = Path(*nifti_path.parts[:i + 2])
                            for subdir in simnibs_dir.iterdir():
                                if subdir.name.startswith('m2m_'):
                                    seg_dir = subdir / 'segmentation'
                                    lut_path = seg_dir / 'labeling_LUT.txt'
                                    if lut_path.exists():
                                        possible_lut_paths.append(lut_path)
        
        # 2. Check in the same directory as the NIfTI file
        nifti_dir = nifti_path.parent
        lut_path = nifti_dir / 'labeling_LUT.txt'
        if lut_path.exists():
            possible_lut_paths.append(lut_path)
        
        # 3. Check in parent directories (up to 3 levels)
        for i in range(1, 4):
            parent_dir = nifti_path.parents[i] if i < len(nifti_path.parents) else None
            if parent_dir:
                lut_path = parent_dir / 'labeling_LUT.txt'
                if lut_path.exists():
                    possible_lut_paths.append(lut_path)
        
        # Try to load from the first available path
        for lut_path in possible_lut_paths:
            try:
                LOGGER.debug(f"Attempting to load label names from: {lut_path}")
                with open(lut_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if line and not line.startswith('#'):
                            # Split by tab to handle the specific format: #No. | Label Name: | R | G | B | A
                            parts = line.split('\t')
                            if len(parts) >= 2:  # At least ID and Name
                                try:
                                    # First part should be the label number
                                    label_id = int(parts[0].strip())
                                    # Second part should be the label name (remove trailing colon if present)
                                    label_name = parts[1].strip().rstrip(':')
                                    label_names[label_id] = label_name
                                except (ValueError, IndexError):
                                    LOGGER.debug(f"Skipping malformed line {line_num}: {line}")
                                    continue
                
                LOGGER.info(f"Successfully loaded {len(label_names)} label names from: {lut_path}")
                return label_names
                
            except Exception as e:
                LOGGER.debug(f"Failed to load from {lut_path}: {e}")
                continue
        
        LOGGER.warning("Could not find or load labeling_LUT.txt file. Labels will be shown as numbers only.")
        LOGGER.info("Expected locations for labeling_LUT.txt:")
        LOGGER.info("  - derivatives/SimNIBS/sub-*/m2m_*/segmentation/labeling_LUT.txt")
        LOGGER.info("  - Same directory as input NIfTI file")
        LOGGER.info("  - Parent directories of input NIfTI file")
        return label_names
    
    def get_label_name(self, label_id):
        """
        Get the human-readable name for a numeric label.
        Returns the name if available, otherwise returns the numeric label as string.
        """
        return self.label_names.get(label_id, str(label_id))
    
    def print_available_labels(self):
        """
        Print all available label names for debugging purposes.
        """
        if not self.label_names:
            LOGGER.info("No label names loaded from labeling_LUT.txt")
            return
        
        LOGGER.info(f"Available label names ({len(self.label_names)} total):")
        LOGGER.info("-" * 50)
        for label_id in sorted(self.label_names.keys()):
            label_name = self.label_names[label_id]
            LOGGER.info(f"  {label_id:3d}: {label_name}")
        
        # Show which labels are being analyzed
        LOGGER.info("-" * 50)
        LOGGER.info(f"Labels being analyzed for {self.tissue_name}:")
        for label in self.tissue_labels:
            label_name = self.get_label_name(label)
            LOGGER.info(f"  {label:3d}: {label_name}")
    
    def set_label_names(self, label_names_dict):
        """
        Manually set label names mapping.
        Useful when labeling_LUT.txt is not available or needs to be overridden.
        
        Args:
            label_names_dict (dict): Dictionary mapping numeric labels to tissue names
        """
        if not isinstance(label_names_dict, dict):
            raise ValueError("label_names_dict must be a dictionary")
        
        self.label_names.update(label_names_dict)
        LOGGER.info(f"Updated label names mapping with {len(label_names_dict)} entries")
        
        # Show updated mapping
        self.print_available_labels()
    
    def extract_tissue_mask(self):
        """Extract tissue mask filtered to brain region only."""
        LOGGER.info(f"Extracting {self.tissue_name} mask...")
        
        # Extract tissue from multiple labels
        tissue_mask = np.zeros_like(self.data, dtype=np.uint8)
        for label in self.tissue_labels:
            label_mask = (self.data == label).astype(np.uint8)
            tissue_mask = np.logical_or(tissue_mask, label_mask).astype(np.uint8)
        
        total_tissue_voxels = np.sum(tissue_mask)
        
        LOGGER.debug(f"{self.tissue_name} labels used: {self.tissue_labels}")
        LOGGER.debug(f"{self.tissue_name} voxels: {total_tissue_voxels:,}")
        
        if total_tissue_voxels == 0:
            LOGGER.warning(f"No {self.tissue_name} tissue found!")
            self.all_tissue_mask = tissue_mask
            self.brain_mask = np.zeros_like(tissue_mask)
            self.tissue_mask = tissue_mask
            return tissue_mask
        
        # Create brain mask for region definition
        LOGGER.debug("Creating brain reference mask for filtering...")
        brain_mask = np.zeros_like(tissue_mask)
        for label in self.brain_labels:
            brain_label_mask = (self.data == label).astype(np.uint8)
            brain_mask = np.logical_or(brain_mask, brain_label_mask).astype(np.uint8)
        
        brain_voxels = np.sum(brain_mask)
        LOGGER.debug(f"Brain reference voxels: {brain_voxels:,}")
        
        if brain_voxels == 0:
            LOGGER.warning(f"No brain tissue found for filtering. Using all {self.tissue_name}.")
            self.all_tissue_mask = tissue_mask
            self.brain_mask = np.zeros_like(tissue_mask)
            self.tissue_mask = tissue_mask
            return tissue_mask
        
        # Create filtered region
        filtered_tissue_mask = self._filter_to_brain_region(tissue_mask, brain_mask)
        
        filtered_tissue_voxels = np.sum(filtered_tissue_mask)
        filtered_ratio = filtered_tissue_voxels / total_tissue_voxels * 100
        
        LOGGER.debug(f"Filtered {self.tissue_name} voxels: {filtered_tissue_voxels:,}")
        LOGGER.debug(f"Filtered out {filtered_ratio:.1f}% of total {self.tissue_name} (kept {100-filtered_ratio:.1f}%)")
        LOGGER.debug(f"Voxel counts - Total {self.tissue_name}: {total_tissue_voxels:,}, Filtered: {filtered_tissue_voxels:,}, Excluded: {total_tissue_voxels - filtered_tissue_voxels:,}")
        
        # Store masks for visualization
        self.all_tissue_mask = tissue_mask
        self.brain_mask = brain_mask
        self.tissue_mask = filtered_tissue_mask
        
        return filtered_tissue_mask
    
    def _filter_to_brain_region(self, tissue_mask, brain_mask):
        """Filter tissue mask to include only region around brain."""
        LOGGER.debug(f"Filtering {self.tissue_name} to brain region...")
        
        # Get brain bounding box with padding
        brain_coords = np.where(brain_mask > 0)
        if len(brain_coords[0]) == 0:
            return tissue_mask
        
        # Brain bounding box
        min_x, max_x = brain_coords[0].min(), brain_coords[0].max()
        min_y, max_y = brain_coords[1].min(), brain_coords[1].max()
        min_z, max_z = brain_coords[2].min(), brain_coords[2].max()
        
        LOGGER.debug(f"Brain bounding box: X({min_x}-{max_x}), Y({min_y}-{max_y}), Z({min_z}-{max_z})")
        
        # Create expanded bounding box with padding
        region_min_x = max(0, min_x - self.padding_voxels)
        region_max_x = min(tissue_mask.shape[0], max_x + self.padding_voxels)
        region_min_y = max(0, min_y - self.padding_voxels)
        region_max_y = min(tissue_mask.shape[1], max_y + self.padding_voxels)
        region_min_z = max(0, min_z - self.padding_voxels)
        region_max_z = min(tissue_mask.shape[2], max_z + self.padding_voxels)
        
        LOGGER.debug(f"Filtered region box: X({region_min_x}-{region_max_x}), Y({region_min_y}-{region_max_y}), Z({region_min_z}-{region_max_z})")
        
        # Create spatial filter
        region_mask = np.zeros_like(tissue_mask)
        region_mask[region_min_x:region_max_x, 
                   region_min_y:region_max_y, 
                   region_min_z:region_max_z] = 1
        
        # Z-coordinate filtering to exclude lower regions
        brain_center_z = (min_z + max_z) // 2
        z_threshold = brain_center_z - self.padding_voxels
        region_mask[:, :, :z_threshold] = 0
        
        LOGGER.debug(f"Applied Z-coordinate filter: excluding regions below Z={z_threshold}")
        
        # Apply filters to tissue mask
        filtered_tissue_mask = tissue_mask * region_mask
        
        return filtered_tissue_mask.astype(np.uint8)
    
    def _print_voxel_summary(self):
        """Print comprehensive voxel summary information."""
        LOGGER.debug("\n" + "="*60)
        LOGGER.debug("VOXEL SUMMARY")
        LOGGER.debug("="*60)
        LOGGER.debug(f"Total image dimensions:        {self.data.shape}")
        LOGGER.debug(f"Total image voxels:            {np.prod(self.data.shape):,}")
        LOGGER.debug(f"Voxel dimensions:              {self.voxel_dims} mm")
        LOGGER.debug(f"Voxel volume:                  {self.voxel_volume:.3f} mm³")
        LOGGER.debug("-" * 60)
        LOGGER.debug(f"{self.tissue_name} labels analyzed:           {self.tissue_labels}")
        LOGGER.debug(f"Total {self.tissue_name} voxels:              {np.sum(self.all_tissue_mask):,}")
        LOGGER.debug(f"Filtered {self.tissue_name} voxels:           {np.sum(self.tissue_mask):,}")
        LOGGER.debug(f"Excluded {self.tissue_name} voxels:           {np.sum(self.all_tissue_mask) - np.sum(self.tissue_mask):,}")
        LOGGER.debug(f"Brain reference voxels:        {np.sum(self.brain_mask):,}")
        
        # Show breakdown by individual labels
        LOGGER.debug("-" * 60)
        LOGGER.debug("BREAKDOWN BY LABEL:")
        for label in self.tissue_labels:
            label_voxels = np.sum(self.data == label)
            filtered_label_voxels = np.sum((self.data == label) & (self.tissue_mask > 0))
            label_name = self.get_label_name(label)
            LOGGER.debug(f"  Label {label:2d} ({label_name}): {label_voxels:8,} total, {filtered_label_voxels:8,} filtered")
        
        LOGGER.debug("-" * 60)
        LOGGER.debug(f"{self.tissue_name} filtering efficiency:      {np.sum(self.tissue_mask) / np.sum(self.all_tissue_mask) * 100:.1f}%")
        LOGGER.debug(f"Filtered {self.tissue_name} volume:           {np.sum(self.tissue_mask) * self.voxel_volume / 1000:.3f} cm³")
        LOGGER.debug("="*60)
    
    def calculate_volumes(self):
        """Calculate total filtered tissue volume."""
        tissue_volume = np.sum(self.tissue_mask) * self.voxel_volume  # mm³
        tissue_volume_cm3 = tissue_volume / 1000
        
        LOGGER.debug(f"[{self.tissue_name} Analysis] Volume calculation:")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Tissue mask voxels: {np.sum(self.tissue_mask):,}")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Voxel volume: {self.voxel_volume:.3f} mm³")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Total volume: {tissue_volume:.1f} mm³ ({tissue_volume_cm3:.3f} cm³)")
        
        volume_results = {
            f'{self.tissue_name.lower()}_volume_mm3': tissue_volume,
            f'{self.tissue_name.lower()}_volume_cm3': tissue_volume_cm3
        }
        
        return volume_results
    
    def calculate_thickness_3d(self, mask, tissue_name):
        """Calculate thickness using 3D distance transform."""
        if np.sum(mask) == 0:
            LOGGER.debug(f"[{self.tissue_name} Analysis] No tissue mask data for thickness calculation")
            return {'max': 0, 'min': 0, 'mean': 0, 'std': 0, 'thickness_map': None}
        
        LOGGER.debug(f"[{self.tissue_name} Analysis] Calculating thickness using 3D distance transform...")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Input mask voxels: {np.sum(mask):,}")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Voxel dimensions: {self.voxel_dims} mm")
        
        # Distance transform - distance to nearest zero (background)
        distance_map = ndimage.distance_transform_edt(mask, sampling=self.voxel_dims)
        
        # Get thickness only where mask is True
        thickness_values = distance_map[mask > 0]
        
        # Thickness is often considered as twice the distance to nearest boundary
        thickness_values = thickness_values * 2
        
        LOGGER.debug(f"[{self.tissue_name} Analysis] Thickness calculation results:")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Raw distance values: {len(thickness_values):,} points")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Distance range: {np.min(distance_map[mask > 0]):.3f} - {np.max(distance_map[mask > 0]):.3f} mm")
        LOGGER.debug(f"[{self.tissue_name} Analysis]   - Thickness range: {np.min(thickness_values):.3f} - {np.max(thickness_values):.3f} mm")
        
        thickness_stats = {
            'max': np.max(thickness_values),
            'min': np.min(thickness_values),
            'mean': np.mean(thickness_values),
            'std': np.std(thickness_values),
            'thickness_map': distance_map * 2
        }
        
        return thickness_stats
    
    def create_thickness_visualization(self, thickness_map, mask, tissue_name, stats):
        """Create publication-quality visualization of thickness distribution."""
        if thickness_map is None or np.sum(mask) == 0:
            LOGGER.debug(f"No data to visualize for {tissue_name}")
            return None
        
        # Set publication style
        plt.style.use('default')
        plt.rcParams.update({
            'font.size': 11,
            'font.family': 'DejaVu Sans',
            'axes.linewidth': 1.2,
            'axes.labelweight': 'bold',
            'figure.dpi': 300
        })
        
        # Create figure with 2 rows: 3 views on top, distribution below
        fig = plt.figure(figsize=(16, 10))
        gs = fig.add_gridspec(2, 3, height_ratios=[2, 1], width_ratios=[1, 1, 1])
        
        # Main title
        fig.suptitle(f'{self.tissue_name} Thickness Analysis', fontsize=18, fontweight='bold', y=0.95)
        
        # Calculate proper aspect ratios for medical imaging
        vx, vy, vz = self.voxel_dims
        
        # Get middle slices for visualization
        mid_x, mid_y, mid_z = [s // 2 for s in thickness_map.shape]
        
        # Find thickness range for consistent color scaling
        thickness_values = thickness_map[mask > 0]
        vmin, vmax = np.nanmin(thickness_values), np.nanmax(thickness_values)
        
        # 1. Axial slice (X-Y plane) - top left
        ax1 = fig.add_subplot(gs[0, 0])
        masked_thickness = np.where(mask[:, :, mid_z] > 0, thickness_map[:, :, mid_z], np.nan)
        aspect_ratio = vy / vx
        im1 = ax1.imshow(masked_thickness.T, cmap=self.color_scheme, origin='lower', 
                        aspect=aspect_ratio, interpolation='bilinear', vmin=vmin, vmax=vmax)
        ax1.set_title('A. Axial View', fontsize=14, fontweight='bold', pad=15)
        ax1.set_xlabel('Anterior - Posterior', fontweight='bold', fontsize=12)
        ax1.set_ylabel('Left - Right', fontweight='bold', fontsize=12)
        ax1.grid(True, alpha=0.2, linestyle='--')
        
        # 2. Coronal slice (X-Z plane) - top center
        ax2 = fig.add_subplot(gs[0, 1])
        masked_thickness = np.where(mask[:, mid_y, :] > 0, thickness_map[:, mid_y, :], np.nan)
        aspect_ratio = vz / vx
        im2 = ax2.imshow(masked_thickness.T, cmap=self.color_scheme, origin='lower',
                        aspect=aspect_ratio, interpolation='bilinear', vmin=vmin, vmax=vmax)
        ax2.set_title('B. Coronal View', fontsize=14, fontweight='bold', pad=15)
        ax2.set_xlabel('Anterior - Posterior', fontweight='bold', fontsize=12)
        ax2.set_ylabel('Inferior - Superior', fontweight='bold', fontsize=12)
        ax2.grid(True, alpha=0.2, linestyle='--')
        
        # 3. Sagittal slice (Y-Z plane) - top right  
        ax3 = fig.add_subplot(gs[0, 2])
        masked_thickness = np.where(mask[mid_x, :, :] > 0, thickness_map[mid_x, :, :], np.nan)
        aspect_ratio = vy / vz
        im3 = ax3.imshow(masked_thickness.T, cmap=self.color_scheme, origin='lower',
                        aspect=aspect_ratio, interpolation='bilinear', vmin=vmin, vmax=vmax)
        ax3.set_title('C. Sagittal View', fontsize=14, fontweight='bold', pad=15)
        ax3.set_xlabel('Left - Right', fontweight='bold', fontsize=12)
        ax3.set_ylabel('Inferior - Superior', fontweight='bold', fontsize=12)
        ax3.grid(True, alpha=0.2, linestyle='--')
        
        # Add shared colorbar for the three views
        cbar_ax = fig.add_axes([0.92, 0.53, 0.02, 0.35])
        sm = plt.cm.ScalarMappable(cmap=self.color_scheme, norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cbar = fig.colorbar(sm, cax=cbar_ax)
        cbar.set_label('Thickness (mm)', rotation=90, fontweight='bold', labelpad=15, fontsize=12)
        
        # 4. Thickness distribution - bottom spanning all columns
        ax4 = fig.add_subplot(gs[1, :])
        
        # Create histogram with better styling
        n, bins, patches = ax4.hist(thickness_values, bins=50, alpha=0.7, 
                                   color='lightblue', edgecolor='navy', linewidth=1.2, density=True)
        
        # Add statistical lines
        ax4.axvline(stats['mean'], color='red', linestyle='-', linewidth=3, 
                   label=f"Mean: {stats['mean']:.2f} mm")
        ax4.axvline(stats['mean'] + stats['std'], color='red', linestyle='--', linewidth=2, 
                   label=f"+1 SD: {stats['mean'] + stats['std']:.2f} mm")
        ax4.axvline(stats['mean'] - stats['std'], color='red', linestyle='--', linewidth=2,
                   label=f"-1 SD: {stats['mean'] - stats['std']:.2f} mm")
        
        # Add percentile lines
        p25, p75 = np.percentile(thickness_values, [25, 75])
        ax4.axvline(p25, color='orange', linestyle=':', linewidth=2, alpha=0.8,
                   label=f"25th percentile: {p25:.2f} mm")
        ax4.axvline(p75, color='orange', linestyle=':', linewidth=2, alpha=0.8,
                   label=f"75th percentile: {p75:.2f} mm")
        
        ax4.set_xlabel(f'{self.tissue_name} Thickness (mm)', fontweight='bold', fontsize=12)
        ax4.set_ylabel('Probability Density', fontweight='bold', fontsize=12)
        ax4.set_title('D. Thickness Distribution', fontsize=14, fontweight='bold', pad=15)
        ax4.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=10)
        ax4.grid(True, alpha=0.3, axis='y')
        
        # Add comprehensive statistics text box
        stats_text = f'''Statistics Summary:
Range: {stats['min']:.2f} - {stats['max']:.2f} mm
Mean ± SD: {stats['mean']:.2f} ± {stats['std']:.2f} mm
Median: {np.median(thickness_values):.2f} mm
IQR: {p25:.2f} - {p75:.2f} mm
Voxels: {np.sum(mask):,}
Volume: {np.sum(mask) * self.voxel_volume / 1000:.1f} cm³
Voxel dimensions: {self.voxel_dims} mm'''
        
        ax4.text(0.02, 0.98, stats_text, transform=ax4.transAxes, 
                fontsize=10, verticalalignment='top', horizontalalignment='left',
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9, edgecolor='gray'))
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(left=0.05, right=0.90, top=0.90, bottom=0.08, 
                          wspace=0.15, hspace=0.30)
        
        # Save the figure in both PNG and PDF formats
        output_path_png = self.output_dir / f"{self.tissue_name.lower()}_thickness_analysis.png"
        output_path_pdf = self.output_dir / f"{self.tissue_name.lower()}_thickness_analysis.pdf"
        
        plt.savefig(output_path_png, dpi=300, bbox_inches='tight', facecolor='white')
        plt.savefig(output_path_pdf, bbox_inches='tight', facecolor='white')
        plt.close()
        
        LOGGER.debug(f"Thickness visualization saved to: {output_path_png} and {output_path_pdf}")
        return output_path_png

    def create_methodology_illustration(self, all_tissue_mask, brain_mask, filtered_tissue_mask):
        """Create publication-quality illustration of tissue extraction methodology."""
        # Set publication style
        plt.style.use('default')
        plt.rcParams.update({
            'font.size': 10,
            'font.family': 'DejaVu Sans',
            'axes.linewidth': 1.2,
            'axes.labelweight': 'bold',
            'figure.dpi': 300
        })
        
        # Create figure with 2 rows (methodology steps) x 3 columns (anatomical views)
        fig = plt.figure(figsize=(18, 12))
        gs = fig.add_gridspec(2, 3, height_ratios=[1, 1], width_ratios=[1, 1, 1])
        
        # Main title
        fig.suptitle(f'{self.tissue_name} Extraction Methodology', fontsize=20, fontweight='bold', y=0.96)
        
        # Calculate proper aspect ratios for medical imaging
        vx, vy, vz = self.voxel_dims
        
        # Get middle slices for consistent visualization across all views
        mid_x, mid_y, mid_z = [s // 2 for s in all_tissue_mask.shape]
        
        # Row labels for methodology steps
        step_labels = [
            f'A. Brain Reference Regions\n(Anatomical Landmarks)', 
            f'B. Final {self.tissue_name} Mask\n(Analysis Target)'
        ]
        
        # Column labels for anatomical views  
        view_labels = ['Axial View', 'Coronal View', 'Sagittal View']
        
        # Add column headers
        for col, label in enumerate(view_labels):
            fig.text(0.18 + col * 0.27, 0.93, label, fontsize=14, fontweight='bold', 
                    ha='center', va='center')
        
        # Create separate masks for reference brain regions
        hemisphere_mask = np.zeros_like(brain_mask)
        brainstem_mask = np.zeros_like(brain_mask)
        
        # Separate hemispheres and brainstem for coloring
        for label in self.brain_labels:
            if label in [3, 42]:  # Left/Right cerebral cortex
                hemisphere_mask = np.logical_or(hemisphere_mask, (self.data == label).astype(np.uint8))
            elif label == 16:  # Brain stem
                brainstem_mask = (self.data == label).astype(np.uint8)
        
        for row in range(2):
            # Add row labels
            fig.text(0.02, 0.75 - row * 0.40, step_labels[row], fontsize=12, fontweight='bold',
                    ha='left', va='center', rotation=90)
            
            for col in range(3):
                ax = fig.add_subplot(gs[row, col])
                
                # Get the appropriate slice and aspect ratio for each view
                if col == 0:  # Axial view (X-Y plane)
                    tissue_slice = all_tissue_mask[:, :, mid_z]
                    brain_slice = brain_mask[:, :, mid_z] if brain_mask is not None else np.zeros_like(tissue_slice)
                    filtered_slice = filtered_tissue_mask[:, :, mid_z]
                    hemisphere_slice = hemisphere_mask[:, :, mid_z]
                    brainstem_slice = brainstem_mask[:, :, mid_z]
                    aspect_ratio = vy / vx
                    xlabel, ylabel = 'Anterior - Posterior', 'Left - Right'
                elif col == 1:  # Coronal view (X-Z plane)
                    tissue_slice = all_tissue_mask[:, mid_y, :]
                    brain_slice = brain_mask[:, mid_y, :] if brain_mask is not None else np.zeros_like(tissue_slice)
                    filtered_slice = filtered_tissue_mask[:, mid_y, :]
                    hemisphere_slice = hemisphere_mask[:, mid_y, :]
                    brainstem_slice = brainstem_mask[:, mid_y, :]
                    aspect_ratio = vz / vx
                    xlabel, ylabel = 'Anterior - Posterior', 'Inferior - Superior'
                else:  # Sagittal view (Y-Z plane)
                    tissue_slice = all_tissue_mask[mid_x, :, :]
                    brain_slice = brain_mask[mid_x, :, :] if brain_mask is not None else np.zeros_like(tissue_slice)
                    filtered_slice = filtered_tissue_mask[mid_x, :, :]
                    hemisphere_slice = hemisphere_mask[mid_x, :, :]
                    brainstem_slice = brainstem_mask[mid_x, :, :]
                    aspect_ratio = vy / vz
                    xlabel, ylabel = 'Left - Right', 'Inferior - Superior'
                
                # Create RGB overlay based on methodology step
                img = np.zeros((tissue_slice.shape[1], tissue_slice.shape[0], 3))
                
                if row == 0:  # Brain reference regions
                    img[tissue_slice.T > 0] = [0.8, 0.9, 1.0] if self.tissue_name == 'CSF' else [0.8, 0.8, 0.8]
                    img[hemisphere_slice.T > 0] = [0, 0.5, 1]  # Blue for left/right hemispheres
                    img[brainstem_slice.T > 0] = [0, 1, 0]    # Green for brainstem
                    legend_text = f'Brain Regions Used:\n- Blue: Left/Right Cortex (hemispheres)\n- Green: Brain Stem\n- Light color: {self.tissue_name} (context)'
                    legend_color = 'lightblue'
                else:  # Final filtered mask (row == 1)
                    img[tissue_slice.T > 0] = [0.3, 0.3, 0.3]  # Dark gray for excluded tissue
                    img[filtered_slice.T > 0] = [0, 0, 1] if self.tissue_name == 'CSF' else [1, 0, 0]  # Blue for CSF, Red for bone
                    img[hemisphere_slice.T > 0] = [0, 0.5, 1]  # Blue for left/right hemispheres
                    img[brainstem_slice.T > 0] = [0, 1, 0]    # Green for brainstem
                    
                    # Add reference lines to show the filtering that was applied
                    brain_coords = np.where(brain_mask > 0)
                    if len(brain_coords[0]) > 0:
                        min_z, max_z = brain_coords[2].min(), brain_coords[2].max()
                        brain_center_z = (min_z + max_z) // 2
                        z_threshold = brain_center_z - self.padding_voxels
                        # Show filtering reference lines for coronal and sagittal views
                        if col in [1, 2]:  # Coronal and sagittal views
                            ax.axhline(y=z_threshold, color='yellow', linewidth=3, linestyle='--', alpha=0.9)
                            ax.axhline(y=brain_center_z, color='white', linewidth=2, linestyle=':', alpha=0.8)
                    
                    kept_percentage = np.sum(filtered_tissue_mask) / np.sum(all_tissue_mask) * 100
                    legend_text = f'Final {self.tissue_name} Extraction:\n- Colored: Extracted {self.tissue_name} ({kept_percentage:.1f}%)\n- Dark gray: Excluded {self.tissue_name}\n- Blue: Left/Right Cortex (hemispheres)\n- Green: Brain Stem\n- Yellow line: Z-cutoff applied'
                    legend_color = 'lightcoral'
                
                # Display the image with correct aspect ratio
                ax.imshow(img, origin='lower', aspect=aspect_ratio)
                # Set labels and formatting
                ax.set_xlabel(xlabel, fontweight='bold', fontsize=9)
                ax.set_ylabel(ylabel, fontweight='bold', fontsize=9)
                ax.grid(True, alpha=0.2, linestyle='--')
                # Add legend for first column only to avoid repetition
                if col == 0:
                    ax.text(0.02, 0.98, legend_text, transform=ax.transAxes, 
                           fontsize=8, verticalalignment='top', horizontalalignment='left',
                           bbox=dict(boxstyle="round,pad=0.3", facecolor=legend_color, alpha=0.7))
                # Remove tick labels to clean up the display
                ax.set_xticks([])
                ax.set_yticks([])
        
        # Add comprehensive methodology explanation at the bottom
        method_text = f"""
{self.tissue_name} Extraction Methodology:
A. Brain Reference Identification: Left/Right Cerebral Cortex (blue) + Brain Stem (green) define Z-coordinate reference
B. {self.tissue_name} Extraction Result: Apply 3D bounding box (±{self.padding_voxels}mm) + Z-cutoff below brain center to exclude lower anatomy
        """.strip()
        fig.text(0.02, 0.02, method_text, fontsize=11, verticalalignment='bottom',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.9, edgecolor='gray'))
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(left=0.05, right=0.98, top=0.91, bottom=0.15, 
                          wspace=0.08, hspace=0.25)
        
        # Save the figure in both PNG and PDF formats
        output_path_png = self.output_dir / f"{self.tissue_name.lower()}_extraction_methodology.png"
        output_path_pdf = self.output_dir / f"{self.tissue_name.lower()}_extraction_methodology.pdf"
        
        plt.savefig(output_path_png, dpi=300, bbox_inches='tight', facecolor='white')
        plt.savefig(output_path_pdf, bbox_inches='tight', facecolor='white')
        plt.close()
        
        LOGGER.debug(f"{self.tissue_name} extraction methodology illustration saved to: {output_path_png} and {output_path_pdf}")
        return output_path_png
    
    def create_combined_publication_figure(self, all_tissue_mask, brain_mask, filtered_tissue_mask, thickness_map, thickness_mask, thickness_stats):
        """Create a single publication-ready figure with identification, extraction, and thickness analysis."""
        plt.style.use('default')
        plt.rcParams.update({
            'font.size': 11,
            'font.family': 'DejaVu Sans',
            'axes.linewidth': 1.2,
            'axes.labelweight': 'bold',
            'figure.dpi': 300
        })
        
        # 3 rows (identification, extraction, thickness), 4 columns (3 views + 1 colorbar)
        fig = plt.figure(figsize=(15, 12))
        gs = fig.add_gridspec(3, 4, width_ratios=[1, 1, 1, 0.1], height_ratios=[1, 1, 1], wspace=0.15, hspace=0.3)
        
        # Main title
        fig.suptitle(f'{self.tissue_name} Analysis Pipeline', fontsize=16, fontweight='bold', y=0.95)
        
        vx, vy, vz = self.voxel_dims
        mid_x, mid_y, mid_z = [s // 2 for s in all_tissue_mask.shape]
        
        # Create separate masks for reference brain regions
        hemisphere_mask = np.zeros_like(brain_mask)
        brainstem_mask = np.zeros_like(brain_mask)
        for label in self.brain_labels:
            if label in [3, 42]:  # Left/Right cerebral cortex
                hemisphere_mask = np.logical_or(hemisphere_mask, (self.data == label).astype(np.uint8))
            elif label == 16:  # Brain stem
                brainstem_mask = (self.data == label).astype(np.uint8)
        
        view_labels = ['Axial View', 'Coronal View', 'Sagittal View']
        
        # Define distinct color schemes for CSF and Bone thickness
        thickness_cmap = 'hot' if self.tissue_name == 'Bone' else 'Blues'
        
        # Process each row (identification, extraction, thickness)
        for row in range(3):
            # Create colorbar for thickness row
            if row == 2:
                thickness_values = thickness_map[thickness_mask > 0]
                vmin, vmax = np.nanmin(thickness_values), np.nanmax(thickness_values)
                cbar_ax = fig.add_subplot(gs[row, 3])
                sm = plt.cm.ScalarMappable(cmap=thickness_cmap, norm=plt.Normalize(vmin=vmin, vmax=vmax))
                sm.set_array([])
                cbar = fig.colorbar(sm, cax=cbar_ax)
                cbar.set_label('Thickness (mm)', rotation=90, fontweight='bold', labelpad=12, fontsize=11)
            
            # Process each view (axial, coronal, sagittal)
            for col in range(3):
                ax = fig.add_subplot(gs[row, col])
                
                # Get appropriate slice and aspect ratio for each view
                if col == 0:  # Axial
                    tissue_slice = all_tissue_mask[:, :, mid_z]
                    filtered_slice = filtered_tissue_mask[:, :, mid_z]
                    hemisphere_slice = hemisphere_mask[:, :, mid_z]
                    brainstem_slice = brainstem_mask[:, :, mid_z]
                    if row == 2:
                        thickness_slice = np.where(thickness_mask[:, :, mid_z] > 0, thickness_map[:, :, mid_z], np.nan)
                    aspect_ratio = vy / vx
                    xlabel, ylabel = 'Anterior - Posterior', 'Left - Right'
                elif col == 1:  # Coronal
                    tissue_slice = all_tissue_mask[:, mid_y, :]
                    filtered_slice = filtered_tissue_mask[:, mid_y, :]
                    hemisphere_slice = hemisphere_mask[:, mid_y, :]
                    brainstem_slice = brainstem_mask[:, mid_y, :]
                    if row == 2:
                        thickness_slice = np.where(thickness_mask[:, mid_y, :] > 0, thickness_map[:, mid_y, :], np.nan)
                    aspect_ratio = vz / vx
                    xlabel, ylabel = 'Anterior - Posterior', 'Inferior - Superior'
                else:  # Sagittal
                    tissue_slice = all_tissue_mask[mid_x, :, :]
                    filtered_slice = filtered_tissue_mask[mid_x, :, :]
                    hemisphere_slice = hemisphere_mask[mid_x, :, :]
                    brainstem_slice = brainstem_mask[mid_x, :, :]
                    if row == 2:
                        thickness_slice = np.where(thickness_mask[mid_x, :, :] > 0, thickness_map[mid_x, :, :], np.nan)
                    aspect_ratio = vy / vz
                    xlabel, ylabel = 'Left - Right', 'Inferior - Superior'
                
                # Create visualization based on row type
                if row == 0:  # Identification
                    img = np.zeros((tissue_slice.shape[1], tissue_slice.shape[0], 3))
                    img[tissue_slice.T > 0] = [0.8, 0.9, 1.0] if self.tissue_name == 'CSF' else [0.8, 0.8, 0.8]
                    img[hemisphere_slice.T > 0] = [0, 0.5, 1]
                    img[brainstem_slice.T > 0] = [0, 1, 0]
                    ax.imshow(img, origin='lower', aspect=aspect_ratio)
                    row_title = 'Identification'
                    
                    if col == 0:
                        ax.text(0.02, 0.98, f'Brain Regions Used:\n- Blue: Left/Right Cortex\n- Green: Brain Stem\n- Light color: {self.tissue_name}',
                               transform=ax.transAxes, fontsize=8, verticalalignment='top', horizontalalignment='left',
                               bbox=dict(boxstyle="round,pad=0.3", facecolor='lightblue', alpha=0.7))
                
                elif row == 1:  # Extraction
                    img = np.zeros((tissue_slice.shape[1], tissue_slice.shape[0], 3))
                    img[tissue_slice.T > 0] = [0.3, 0.3, 0.3]
                    img[filtered_slice.T > 0] = [0, 0, 1] if self.tissue_name == 'CSF' else [1, 0, 0]
                    img[hemisphere_slice.T > 0] = [0, 0.5, 1]
                    img[brainstem_slice.T > 0] = [0, 1, 0]
                    
                    # Add Z-cutoff lines for coronal and sagittal views
                    brain_coords = np.where(brain_mask > 0)
                    if len(brain_coords[0]) > 0 and col in [1, 2]:
                        min_z, max_z = brain_coords[2].min(), brain_coords[2].max()
                        brain_center_z = (min_z + max_z) // 2
                        z_threshold = brain_center_z - self.padding_voxels
                        ax.axhline(y=z_threshold, color='yellow', linewidth=2, linestyle='--', alpha=0.9)
                        ax.axhline(y=brain_center_z, color='white', linewidth=1, linestyle=':', alpha=0.8)
                    
                    ax.imshow(img, origin='lower', aspect=aspect_ratio)
                    row_title = 'Extraction'
                    
                    if col == 0:
                        kept_percentage = np.sum(filtered_tissue_mask) / np.sum(all_tissue_mask) * 100
                        ax.text(0.02, 0.98, f'Extracted {self.tissue_name}:\n- Colored: {kept_percentage:.1f}% kept\n- Dark gray: excluded\n- Yellow line: Z-cutoff',
                               transform=ax.transAxes, fontsize=8, verticalalignment='top', horizontalalignment='left',
                               bbox=dict(boxstyle="round,pad=0.3", facecolor='lightcoral', alpha=0.7))
                
                else:  # Thickness
                    # For thickness plots, use high resolution and disable interpolation for PDF export
                    im = ax.imshow(thickness_slice.T, cmap=thickness_cmap, origin='lower',
                                 aspect=aspect_ratio, interpolation='nearest', vmin=vmin, vmax=vmax,
                                 rasterized=False)
                    row_title = 'Thickness'
                    
                    if col == 0:
                        stats_text = f'Thickness Stats:\nMean: {thickness_stats["mean"]:.2f} ± {thickness_stats["std"]:.2f} mm\nRange: {thickness_stats["min"]:.2f} - {thickness_stats["max"]:.2f} mm'
                        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes, fontsize=8,
                               verticalalignment='top', horizontalalignment='left',
                               bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.9))
                
                # Set common properties
                ax.set_title(f'{chr(65+row)}{col+1}. {view_labels[col]} ({row_title})',
                           fontsize=11, fontweight='bold', pad=8)
                ax.set_xlabel(xlabel, fontweight='bold', fontsize=9)
                ax.set_ylabel(ylabel, fontweight='bold', fontsize=9)
                ax.grid(True, alpha=0.2, linestyle='--')
                ax.set_xticks([])
                ax.set_yticks([])
        
        # Add methodology summary
        method_text = f"""Analysis Pipeline:
A. Identification: Brain reference regions (cortex in blue, stem in green) with {self.tissue_name} context
B. Extraction: Apply 3D bounding box (±{self.padding_voxels}mm) + Z-cutoff to isolate relevant {self.tissue_name}
C. Thickness: Calculate using 3D distance transform (color scheme: {'hot for bone' if self.tissue_name == 'Bone' else 'blue for CSF'})"""
        
        fig.text(0.02, 0.02, method_text, fontsize=9, verticalalignment='bottom',
                bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.9, edgecolor='gray'))
        
        # Adjust layout
        fig.subplots_adjust(left=0.05, right=0.95, top=0.92, bottom=0.08, wspace=0.15, hspace=0.25)
        # Save the figure in both PNG and PDF formats
        output_path_png = self.output_dir / f"{self.tissue_name.lower()}_combined_publication_figure.png"
        output_path_pdf = self.output_dir / f"{self.tissue_name.lower()}_combined_publication_figure.pdf"
        
        # Save PNG with high DPI
        plt.savefig(output_path_png, dpi=300, bbox_inches='tight', facecolor='white')
        
        # Save PDF with vector graphics and high quality settings
        plt.savefig(output_path_pdf, dpi=1200, bbox_inches='tight', facecolor='white',
                   format='pdf', transparent=False, metadata={'Creator': 'TI-toolbox'})
        plt.close()
        
        LOGGER.debug(f"Combined publication figure saved to: {output_path_png} and {output_path_pdf}")
        return output_path_png
    
    def generate_summary_report(self, volume_results, thickness_stats):
        """Generate a summary report of the analysis."""
        report_path = self.output_dir / f"{self.tissue_name.lower()}_analysis_summary.txt"
        
        with open(report_path, 'w') as f:
            f.write(f"{self.tissue_name.upper()} ANALYSIS SUMMARY REPORT\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"Input file: {self.nifti_path}\n")
            f.write(f"Data shape: {self.data.shape}\n")
            f.write(f"Total image voxels: {np.prod(self.data.shape):,}\n")
            f.write(f"Voxel dimensions: {self.voxel_dims} mm\n")
            f.write(f"Voxel volume: {self.voxel_volume:.3f} mm³\n\n")
            
            f.write("VOLUME ANALYSIS:\n")
            f.write("-" * 20 + "\n")
            f.write(f"{self.tissue_name} volume:       {volume_results[f'{self.tissue_name.lower()}_volume_cm3']:.3f} cm³ ({volume_results[f'{self.tissue_name.lower()}_volume_mm3']:.1f} mm³)\n")
            f.write(f"{self.tissue_name} voxels:       {np.sum(self.tissue_mask):,}\n\n")
            
            f.write("THICKNESS ANALYSIS:\n")
            f.write("-" * 20 + "\n")
            f.write(f"{self.tissue_name}:\n")
            f.write(f"  Maximum thickness:     {thickness_stats['max']:.3f} mm\n")
            f.write(f"  Minimum thickness:     {thickness_stats['min']:.3f} mm\n")
            f.write(f"  Mean thickness:        {thickness_stats['mean']:.3f} mm\n")
            f.write(f"  Standard deviation:    {thickness_stats['std']:.3f} mm\n\n")
            
            f.write("SPATIAL FILTERING:\n")
            f.write("-" * 18 + "\n")
            f.write(f"- Analysis focused on {self.tissue_name} only (lower anatomy excluded)\n")
            f.write("- Spatial filtering based on brain cortex and brain stem locations\n")
            f.write("- Bounding box extended around brain regions with padding\n")
            f.write("- Z-coordinate filtering applied to exclude lower anatomy\n\n")
            
            f.write("VOXEL COUNTS:\n")
            f.write("-" * 12 + "\n")
            f.write(f"{self.tissue_name} labels analyzed:           {self.tissue_labels}\n")
            f.write(f"Total {self.tissue_name} voxels:              {np.sum(self.all_tissue_mask):,}\n")
            f.write(f"Filtered {self.tissue_name} voxels:           {np.sum(self.tissue_mask):,}\n")
            f.write(f"Excluded {self.tissue_name} voxels:           {np.sum(self.all_tissue_mask) - np.sum(self.tissue_mask):,}\n")
            f.write(f"Brain reference voxels:        {np.sum(self.brain_mask):,}\n\n")
            
            # Add breakdown by individual labels
            f.write("BREAKDOWN BY LABEL:\n")
            f.write("-" * 18 + "\n")
            for label in self.tissue_labels:
                label_voxels = np.sum(self.data == label)
                filtered_label_voxels = np.sum((self.data == label) & (self.tissue_mask > 0))
                label_name = self.get_label_name(label)
                f.write(f"Label {label:2d} ({label_name}): {label_voxels:8,} total, {filtered_label_voxels:8,} filtered\n")
            f.write("\n")
            
            f.write("ANALYSIS NOTES:\n")
            f.write("-" * 15 + "\n")
            f.write(f"- Analyzed {self.tissue_name} tissue with labels {self.tissue_labels}\n")
            f.write("- Thickness calculated using 3D distance transform\n")
            f.write("- Thickness represents twice the distance to nearest tissue boundary\n")
            f.write("- Volume calculations based on voxel dimensions from NIfTI header\n")
            f.write("- Visualizations show middle slices and thickness distributions\n")
            f.write("- Output designed for derivatives/ti-toolbox/{self.tissue_name.lower()}_analysis/sub-*/ structure\n")
        
        LOGGER.debug(f"Summary report saved to: {report_path}")
        return report_path
    
    def run_full_analysis(self):
        """Run the complete tissue analysis pipeline."""
        LOGGER.info(f"[{self.tissue_name} Analysis] Starting...")
        
        # Log detailed analysis parameters at DEBUG level
        LOGGER.debug(f"[{self.tissue_name} Analysis] Input file: {self.nifti_path}")
        LOGGER.debug(f"[{self.tissue_name} Analysis] Output directory: {self.output_dir}")
        LOGGER.debug(f"[{self.tissue_name} Analysis] Tissue labels: {self.tissue_labels}")
        LOGGER.debug(f"[{self.tissue_name} Analysis] Brain reference labels: {self.brain_labels}")
        LOGGER.debug(f"[{self.tissue_name} Analysis] Padding voxels: {self.padding_voxels}")
        LOGGER.debug(f"[{self.tissue_name} Analysis] Color scheme: {self.color_scheme}")
        
        # Show available label names
        self.print_available_labels()
        
        filtered_tissue_mask = self.extract_tissue_mask()
        volume_results = self.calculate_volumes()
        thickness_stats = self.calculate_thickness_3d(filtered_tissue_mask, self.tissue_name)
        
        # Log analysis results at DEBUG level
        LOGGER.debug(f"[{self.tissue_name} Analysis] Volume results: {volume_results}")
        LOGGER.debug(f"[{self.tissue_name} Analysis] Thickness statistics: {thickness_stats}")
        
        # Create publication figure
        LOGGER.debug(f"[{self.tissue_name} Analysis] Creating publication figure...")
        self.create_combined_publication_figure(
            self.all_tissue_mask,
            self.brain_mask,
            filtered_tissue_mask,
            thickness_stats['thickness_map'],
            filtered_tissue_mask,
            thickness_stats
        )
        
        # Generate report
        LOGGER.debug(f"[{self.tissue_name} Analysis] Generating summary report...")
        self.generate_summary_report(volume_results, thickness_stats)
        self._print_voxel_summary()
        
        LOGGER.info(f"[{self.tissue_name} Analysis] Complete. Volume: {volume_results[f'{self.tissue_name.lower()}_volume_cm3']:.2f} cm³ | Thickness: {thickness_stats['mean']:.2f}±{thickness_stats['std']:.2f} mm (range: {thickness_stats['min']:.2f}-{thickness_stats['max']:.2f} mm)")
        LOGGER.info(f"[{self.tissue_name} Analysis] Voxel summary - Total {self.tissue_name}: {np.sum(self.all_tissue_mask):,}, Filtered: {np.sum(self.tissue_mask):,}, Brain reference: {np.sum(self.brain_mask):,}")
        
        # Log label breakdown with names
        LOGGER.info(f"[{self.tissue_name} Analysis] Label breakdown:")
        for label in self.tissue_labels:
            label_voxels = np.sum(self.data == label)
            filtered_label_voxels = np.sum((self.data == label) & (self.tissue_mask > 0))
            label_name = self.get_label_name(label)
            LOGGER.info(f"[{self.tissue_name} Analysis]   Label {label:2d} ({label_name}): {label_voxels:,} total, {filtered_label_voxels:,} filtered")
        
        LOGGER.info(f"[{self.tissue_name} Analysis] Results saved to: {self.output_dir}")
        LOGGER.info(f"[{self.tissue_name} Analysis] Note: Output is now organized under derivatives/ti-toolbox/{self.tissue_name.lower()}_analysis/sub-*/ structure")
        
        return {
            'volumes': volume_results,
            'thickness_stats': thickness_stats
        }


# Tissue configurations
TISSUE_CONFIGS = {
    'csf': {
        'name': 'CSF',
        'labels': [4, 5, 14, 15, 43, 44, 72, 24, 520],
        'padding': 40,
        'color_scheme': 'hot',
        'brain_labels': [3, 42, 16]  # Left cortex, right cortex, brain stem
    },
    'bone': {
        'name': 'Bone',
        'labels': [515, 516],  # Cortical + cancellous
        'padding': 30,
        'color_scheme': 'hot',
        'brain_labels': [3, 42, 16]  # Left cortex, right cortex, brain stem
    },
    'skin': {
        'name': 'Skin',
        'labels': [511],  # Skin tissue tag number 5
        'padding': 35,
        'color_scheme': 'viridis',
        'brain_labels': [3, 42, 16]  # Left cortex, right cortex, brain stem
    }
}


def main():
    parser = argparse.ArgumentParser(description="Unified tissue analysis tool for segmented NIfTI data.")
    parser.add_argument("nifti_path", help="Path to the segmented NIfTI file")
    parser.add_argument("-t", "--tissue", choices=['csf', 'bone', 'skin'], default='csf',
                       help="Tissue type to analyze (default: csf)")
    parser.add_argument("-o", "--output", default=None,
                       help="Output directory for results (default: {tissue}_analysis)")
    parser.add_argument("-l", "--labels", nargs='+', type=int, default=None,
                       help="Custom tissue labels to analyze (overrides default)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.nifti_path):
        print(f"Error: NIfTI file not found: {args.nifti_path}")
        return 1
    
    # Set output directory if not specified
    if args.output is None:
        args.output = f"{args.tissue}_analysis"
    
    try:
        # Get tissue configuration
        tissue_config = TISSUE_CONFIGS[args.tissue].copy()
        
        # Override labels if custom ones provided
        if args.labels is not None:
            tissue_config['labels'] = args.labels
        
        # Create analyzer
        analyzer = TissueAnalyzer(args.nifti_path, args.output, tissue_config)
        
        # Example of manually setting label names if labeling_LUT.txt is not available
        # Uncomment the following lines if you need to override or add label names:
        # custom_labels = {
        #     4: "Left-Lateral-Ventricle",
        #     5: "Left-Inf-Lat-Vent", 
        #     14: "3rd-Ventricle",
        #     15: "4th-Ventricle",
        #     43: "Right-Lateral-Ventricle",
        #     44: "Right-Inf-Lat-Vent",
        #     72: "5th-Ventricle",
        #     24: "CSF",
        #     520: "Cortical-CSF"
        # }
        # analyzer.set_label_names(custom_labels)
        
        # Run analysis
        results = analyzer.run_full_analysis()
        return 0
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
