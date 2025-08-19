#!/usr/bin/env python3
"""
Skull Bone Analysis Tool for TI-toolbox
Analyzes skull bone (cortical + cancellous) from segmented tissue data.
Excludes jaw and vertebrae by spatial filtering around brain cortex.

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
from pathlib import Path

class BoneAnalyzer:
    def __init__(self, nifti_path, output_dir="bone_analysis_output"):
        """
        Initialize the bone analyzer.
        
        Args:
            nifti_path (str): Path to the segmented NIfTI file
            output_dir (str): Directory to save output files
        """
        self.nifti_path = nifti_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # Tissue labels from labeling_LUT.txt
        self.BONE_CORTICAL_LABEL = 515
        self.BONE_CANCELLOUS_LABEL = 516
        
        # Brain tissue labels for skull region definition
        self.LEFT_CEREBRAL_CORTEX_LABEL = 3
        self.RIGHT_CEREBRAL_CORTEX_LABEL = 42
        self.BRAIN_STEM_LABEL = 16
        
        # Load the NIfTI file
        print(f"Loading NIfTI file: {nifti_path}")
        self.nii = nib.load(nifti_path)
        self.data = self.nii.get_fdata()
        self.affine = self.nii.affine
        self.header = self.nii.header
        
        # Get voxel dimensions for volume calculations
        self.voxel_dims = self.nii.header.get_zooms()[:3]  # x, y, z dimensions in mm
        self.voxel_volume = np.prod(self.voxel_dims)  # mm³
        
        print(f"Data shape: {self.data.shape}")
        print(f"Voxel dimensions: {self.voxel_dims} mm")
        print(f"Voxel volume: {self.voxel_volume:.3f} mm³")
        
    def extract_skull_bone_mask(self):
        """Extract skull bone mask (cortical + cancellous) filtered to skull region only."""
        print("  Extracting skull bone mask...")
        
        # Combine both bone types
        cortical_mask = (self.data == self.BONE_CORTICAL_LABEL).astype(np.uint8)
        cancellous_mask = (self.data == self.BONE_CANCELLOUS_LABEL).astype(np.uint8)
        all_bone_mask = (cortical_mask + cancellous_mask > 0).astype(np.uint8)
        
        cortical_voxels = np.sum(cortical_mask)
        cancellous_voxels = np.sum(cancellous_mask)
        total_bone_voxels = np.sum(all_bone_mask)
        
        print(f"Bone-Cortical voxels: {cortical_voxels}")
        print(f"Bone-Cancellous voxels: {cancellous_voxels}")
        print(f"Total bone voxels: {total_bone_voxels}")
        
        if total_bone_voxels == 0:
            print("WARNING: No bone tissue found!")
            self.all_bone_mask = all_bone_mask
            self.brain_mask = np.zeros_like(all_bone_mask)
            self.bone_mask = all_bone_mask
            return all_bone_mask
        
        # Create brain mask for skull region definition
        print("Creating brain reference mask for skull filtering...")
        left_cortex = (self.data == self.LEFT_CEREBRAL_CORTEX_LABEL).astype(np.uint8)
        right_cortex = (self.data == self.RIGHT_CEREBRAL_CORTEX_LABEL).astype(np.uint8)
        brain_stem = (self.data == self.BRAIN_STEM_LABEL).astype(np.uint8)
        
        # Combine brain regions
        brain_mask = (left_cortex + right_cortex + brain_stem > 0).astype(np.uint8)
        brain_voxels = np.sum(brain_mask)
        
        print(f"Brain reference voxels: {brain_voxels}")
        
        if brain_voxels == 0:
            print("WARNING: No brain tissue found for skull filtering. Using all bone.")
            self.all_bone_mask = all_bone_mask
            self.brain_mask = np.zeros_like(all_bone_mask)
            self.bone_mask = all_bone_mask
            return all_bone_mask
        
        # Create skull region filter
        skull_bone_mask = self._filter_to_skull_region(all_bone_mask, brain_mask)
        
        skull_bone_voxels = np.sum(skull_bone_mask)
        filtered_ratio = skull_bone_voxels / total_bone_voxels * 100
        
        print(f"Skull bone voxels (after filtering): {skull_bone_voxels}")
        print(f"Filtered out {filtered_ratio:.1f}% of total bone (kept {100-filtered_ratio:.1f}%)")
        
        # Store masks for visualization
        self.all_bone_mask = all_bone_mask
        self.brain_mask = brain_mask
        self.bone_mask = skull_bone_mask
        
        return skull_bone_mask
    
    def _filter_to_skull_region(self, bone_mask, brain_mask):
        """Filter bone mask to include only skull region around brain."""
        print("Filtering bone to skull region...")
        
        # Get brain bounding box with some padding
        brain_coords = np.where(brain_mask > 0)
        if len(brain_coords[0]) == 0:
            return bone_mask
        
        # Brain bounding box
        min_x, max_x = brain_coords[0].min(), brain_coords[0].max()
        min_y, max_y = brain_coords[1].min(), brain_coords[1].max()
        min_z, max_z = brain_coords[2].min(), brain_coords[2].max()
        
        print(f"Brain bounding box: X({min_x}-{max_x}), Y({min_y}-{max_y}), Z({min_z}-{max_z})")
        
        # Create expanded bounding box for skull (add padding around brain)
        padding_voxels = 30  # approximately 15-30mm depending on voxel size
        skull_min_x = max(0, min_x - padding_voxels)
        skull_max_x = min(bone_mask.shape[0], max_x + padding_voxels)
        skull_min_y = max(0, min_y - padding_voxels)
        skull_max_y = min(bone_mask.shape[1], max_y + padding_voxels)
        skull_min_z = max(0, min_z - padding_voxels)
        skull_max_z = min(bone_mask.shape[2], max_z + padding_voxels)
        
        print(f"Skull region box: X({skull_min_x}-{skull_max_x}), Y({skull_min_y}-{skull_max_y}), Z({skull_min_z}-{skull_max_z})")
        
        # Create spatial filter
        skull_region_mask = np.zeros_like(bone_mask)
        skull_region_mask[skull_min_x:skull_max_x, 
                         skull_min_y:skull_max_y, 
                         skull_min_z:skull_max_z] = 1
        
        # Also exclude lower regions (jaw/vertebrae) by Z-coordinate filtering
        # Keep only upper portion relative to brain stem
        brain_center_z = (min_z + max_z) // 2
        z_threshold = brain_center_z - padding_voxels  # Cut below brain center
        skull_region_mask[:, :, :z_threshold] = 0
        
        print(f"Applied Z-coordinate filter: excluding regions below Z={z_threshold}")
        
        # Apply filters to bone mask
        skull_bone_mask = bone_mask * skull_region_mask
        
        return skull_bone_mask.astype(np.uint8)
    
    def calculate_volumes(self):
        """Calculate total skull bone volume."""
        # print("Calculating skull bone volume...")
        
        skull_bone_volume = np.sum(self.bone_mask) * self.voxel_volume  # mm³
        
        # Convert to cm³ for easier reading
        skull_bone_volume_cm3 = skull_bone_volume / 1000
        
        volume_results = {
            'skull_bone_volume_mm3': skull_bone_volume,
            'skull_bone_volume_cm3': skull_bone_volume_cm3
        }
        
        return volume_results
    
    def calculate_thickness_3d(self, mask, tissue_name):
        """
        Calculate thickness using 3D distance transform.
        Thickness is computed as twice the distance to the nearest edge.
        """
        # print(f"Calculating thickness for {tissue_name}...")
        
        if np.sum(mask) == 0:
            return {'max': 0, 'min': 0, 'mean': 0, 'std': 0, 'thickness_map': None}
        
        # Distance transform - distance to nearest zero (background)
        distance_map = ndimage.distance_transform_edt(mask, sampling=self.voxel_dims)
        
        # Get thickness only where mask is True
        thickness_values = distance_map[mask > 0]
        
        # Thickness is often considered as twice the distance to nearest boundary
        thickness_values = thickness_values * 2
        
        thickness_stats = {
            'max': np.max(thickness_values),
            'min': np.min(thickness_values),
            'mean': np.mean(thickness_values),
            'std': np.std(thickness_values),
            'thickness_map': distance_map * 2  # Full thickness map for visualization
        }
        
        return thickness_stats
    
    def create_thickness_visualization(self, thickness_map, mask, tissue_name, stats):
        """Create publication-quality visualization of thickness distribution."""
        # print(f"Creating thickness visualization for {tissue_name}...")
        
        if thickness_map is None or np.sum(mask) == 0:
            print(f"No data to visualize for {tissue_name}")
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
        fig.suptitle('Skull Bone Thickness Analysis', fontsize=18, fontweight='bold', y=0.95)
        
        # Calculate proper aspect ratios for medical imaging
        # Voxel dimensions: (x, y, z) in mm
        vx, vy, vz = self.voxel_dims
        
        # Get middle slices for visualization
        mid_x, mid_y, mid_z = [s // 2 for s in thickness_map.shape]
        
        # Find thickness range for consistent color scaling
        thickness_values = thickness_map[mask > 0]
        vmin, vmax = np.nanmin(thickness_values), np.nanmax(thickness_values)
        
                 # 1. Axial slice (X-Y plane) - top left
        ax1 = fig.add_subplot(gs[0, 0])
        masked_thickness = np.where(mask[:, :, mid_z] > 0, thickness_map[:, :, mid_z], np.nan)
        # Correct aspect ratio for X-Y plane
        aspect_ratio = vy / vx  # 0.5/0.8 = 0.625
        im1 = ax1.imshow(masked_thickness.T, cmap='hot', origin='lower', 
                        aspect=aspect_ratio, interpolation='bilinear', vmin=vmin, vmax=vmax)
        ax1.set_title('A. Axial View', fontsize=14, fontweight='bold', pad=15)
        ax1.set_xlabel('Anterior - Posterior', fontweight='bold', fontsize=12)
        ax1.set_ylabel('Left - Right', fontweight='bold', fontsize=12)
        ax1.grid(True, alpha=0.2, linestyle='--')
        
                 # 2. Coronal slice (X-Z plane) - top center
        ax2 = fig.add_subplot(gs[0, 1])
        masked_thickness = np.where(mask[:, mid_y, :] > 0, thickness_map[:, mid_y, :], np.nan)
        # Correct aspect ratio for X-Z plane
        aspect_ratio = vz / vx  # 0.5/0.8 = 0.625
        im2 = ax2.imshow(masked_thickness.T, cmap='hot', origin='lower',
                        aspect=aspect_ratio, interpolation='bilinear', vmin=vmin, vmax=vmax)
        ax2.set_title('B. Coronal View', fontsize=14, fontweight='bold', pad=15)
        ax2.set_xlabel('Anterior - Posterior', fontweight='bold', fontsize=12)
        ax2.set_ylabel('Inferior - Superior', fontweight='bold', fontsize=12)
        ax2.grid(True, alpha=0.2, linestyle='--')
        
        # 3. Sagittal slice (Y-Z plane) - top right  
        ax3 = fig.add_subplot(gs[0, 2])
        masked_thickness = np.where(mask[mid_x, :, :] > 0, thickness_map[mid_x, :, :], np.nan)
        # Correct aspect ratio for Y-Z plane
        aspect_ratio = vy / vz  # 0.5/0.5 = 1.0
        im3 = ax3.imshow(masked_thickness.T, cmap='hot', origin='lower',
                        aspect=aspect_ratio, interpolation='bilinear', vmin=vmin, vmax=vmax)
        ax3.set_title('C. Sagittal View', fontsize=14, fontweight='bold', pad=15)
        ax3.set_xlabel('Left - Right', fontweight='bold', fontsize=12)
        ax3.set_ylabel('Inferior - Superior', fontweight='bold', fontsize=12)
        ax3.grid(True, alpha=0.2, linestyle='--')
        
        # Add shared colorbar for the three views
        cbar_ax = fig.add_axes([0.92, 0.53, 0.02, 0.35])  # [left, bottom, width, height]
        sm = plt.cm.ScalarMappable(cmap='hot', norm=plt.Normalize(vmin=vmin, vmax=vmax))
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
        
        ax4.set_xlabel('Skull Bone Thickness (mm)', fontweight='bold', fontsize=12)
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
Volume: {np.sum(mask) * self.voxel_volume / 1000:.1f} cm³'''
        
        ax4.text(0.02, 0.98, stats_text, transform=ax4.transAxes, 
                fontsize=10, verticalalignment='top', horizontalalignment='left',
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9, edgecolor='gray'))
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(left=0.05, right=0.90, top=0.90, bottom=0.08, 
                          wspace=0.15, hspace=0.30)
        
        # Save the figure
        output_path = self.output_dir / f"skull_{tissue_name.lower()}_thickness_analysis.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"Thickness visualization saved to: {output_path}")
        return output_path
    
    def create_skull_extraction_illustration(self, all_bone_mask, brain_mask, skull_bone_mask):
        """Create publication-quality illustration of skull extraction methodology."""
        # print("Creating skull extraction methodology illustration...")
        
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
        fig.suptitle('Skull Extraction Methodology', fontsize=20, fontweight='bold', y=0.96)
        
        # Calculate proper aspect ratios for medical imaging
        vx, vy, vz = self.voxel_dims
        
        # Get middle slices for consistent visualization across all views
        mid_x, mid_y, mid_z = [s // 2 for s in all_bone_mask.shape]
        
        # Row labels for methodology steps
        step_labels = [
            'A. Brain Reference Regions\n(Anatomical Landmarks)', 
            'B. Final Skull Bone Mask\n(Analysis Target)'
        ]
        
        # Column labels for anatomical views  
        view_labels = ['Axial View', 'Coronal View', 'Sagittal View']
        
        # Add column headers
        for col, label in enumerate(view_labels):
            fig.text(0.18 + col * 0.27, 0.93, label, fontsize=14, fontweight='bold', 
                    ha='center', va='center')
        
        # Create separate mask for reference brain regions used for Z-filtering
        left_cortex = (self.data == self.LEFT_CEREBRAL_CORTEX_LABEL).astype(np.uint8)
        right_cortex = (self.data == self.RIGHT_CEREBRAL_CORTEX_LABEL).astype(np.uint8)
        brain_stem = (self.data == self.BRAIN_STEM_LABEL).astype(np.uint8)
        reference_brain_mask = (left_cortex + right_cortex + brain_stem > 0).astype(np.uint8)
        # New: separate masks for coloring
        hemisphere_mask = (left_cortex + right_cortex > 0).astype(np.uint8)
        # brainstem_mask is just brain_stem
        
        for row in range(2):
            # Add row labels
            fig.text(0.02, 0.75 - row * 0.40, step_labels[row], fontsize=12, fontweight='bold',
                    ha='left', va='center', rotation=90)
            
            for col in range(3):
                ax = fig.add_subplot(gs[row, col])
                
                # Get the appropriate slice and aspect ratio for each view
                if col == 0:  # Axial view (X-Y plane)
                    bone_slice = all_bone_mask[:, :, mid_z]
                    brain_slice = brain_mask[:, :, mid_z] if brain_mask is not None else np.zeros_like(bone_slice)
                    reference_slice = reference_brain_mask[:, :, mid_z]
                    skull_slice = skull_bone_mask[:, :, mid_z]
                    hemisphere_slice = hemisphere_mask[:, :, mid_z]
                    brainstem_slice = brain_stem[:, :, mid_z]
                    aspect_ratio = vy / vx  # 0.5/0.8 = 0.625
                    xlabel, ylabel = 'Anterior - Posterior', 'Left - Right'
                elif col == 1:  # Coronal view (X-Z plane)
                    bone_slice = all_bone_mask[:, mid_y, :]
                    brain_slice = brain_mask[:, mid_y, :] if brain_mask is not None else np.zeros_like(bone_slice)
                    reference_slice = reference_brain_mask[:, mid_y, :]
                    skull_slice = skull_bone_mask[:, mid_y, :]
                    hemisphere_slice = hemisphere_mask[:, mid_y, :]
                    brainstem_slice = brain_stem[:, mid_y, :]
                    aspect_ratio = vz / vx  # 0.5/0.8 = 0.625
                    xlabel, ylabel = 'Anterior - Posterior', 'Inferior - Superior'
                else:  # Sagittal view (Y-Z plane)
                    bone_slice = all_bone_mask[mid_x, :, :]
                    brain_slice = brain_mask[mid_x, :, :] if brain_mask is not None else np.zeros_like(bone_slice)
                    reference_slice = reference_brain_mask[mid_x, :, :]
                    skull_slice = skull_bone_mask[mid_x, :, :]
                    hemisphere_slice = hemisphere_mask[mid_x, :, :]
                    brainstem_slice = brain_stem[mid_x, :, :]
                    aspect_ratio = vy / vz  # 0.5/0.5 = 1.0
                    xlabel, ylabel = 'Left - Right', 'Inferior - Superior'
                
                # Create RGB overlay based on methodology step
                img = np.zeros((bone_slice.shape[1], bone_slice.shape[0], 3))  # (H, W, 3) for matplotlib
                
                if row == 0:  # Brain reference regions
                    img[bone_slice.T > 0] = [0.8, 0.8, 0.8]  # Light gray for bone context
                    # Color hemispheres blue, brainstem green
                    img[hemisphere_slice.T > 0] = [0, 0.5, 1]  # Blue for left/right hemispheres
                    img[brainstem_slice.T > 0] = [0, 1, 0]    # Green for brainstem
                    # Optionally, show other brain tissue (not reference) as lighter blue or skip
                    legend_text = 'Brain Regions Used:\n- Blue: Left/Right Cortex (hemispheres)\n- Green: Brain Stem\n- Gray: Bone (context)'
                    legend_color = 'lightblue'
                else:  # Final skull mask (row == 1)
                    img[bone_slice.T > 0] = [0.3, 0.3, 0.3]  # Dark gray for excluded bone
                    img[skull_slice.T > 0] = [1, 0, 0]  # Red for extracted skull bone
                    # Color hemispheres blue, brainstem green
                    img[hemisphere_slice.T > 0] = [0, 0.5, 1]  # Blue for left/right hemispheres
                    img[brainstem_slice.T > 0] = [0, 1, 0]    # Green for brainstem
                    # Add reference lines to show the filtering that was applied
                    brain_coords = np.where(reference_brain_mask > 0)
                    if len(brain_coords[0]) > 0:
                        min_z, max_z = brain_coords[2].min(), brain_coords[2].max()
                        brain_center_z = (min_z + max_z) // 2
                        padding_voxels = 30
                        z_threshold = brain_center_z - padding_voxels
                        # Show filtering reference lines for coronal and sagittal views
                        if col == 1:  # Coronal view
                            ax.axhline(y=z_threshold, color='yellow', linewidth=3, linestyle='--', alpha=0.9)
                            ax.axhline(y=brain_center_z, color='white', linewidth=2, linestyle=':', alpha=0.8)
                        elif col == 2:  # Sagittal view
                            ax.axhline(y=z_threshold, color='yellow', linewidth=3, linestyle='--', alpha=0.9)
                            ax.axhline(y=brain_center_z, color='white', linewidth=2, linestyle=':', alpha=0.8)
                    kept_percentage = np.sum(skull_bone_mask) / np.sum(all_bone_mask) * 100
                    legend_text = f'Final Skull Extraction:\n- Red: Extracted skull ({{kept_percentage:.1f}}%)\n- Dark gray: Excluded bone\n- Blue: Left/Right Cortex (hemispheres)\n- Green: Brain Stem\n- Yellow line: Z-cutoff applied'
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
        method_text = """
Skull Extraction Methodology:
A. Brain Reference Identification: Left/Right Cerebral Cortex (blue) + Brain Stem (green) define Z-coordinate reference
B. Skull Extraction Result: Apply 3D bounding box (±30mm) + Z-cutoff below brain center to exclude jaw/vertebrae
        """.strip()
        fig.text(0.02, 0.02, method_text, fontsize=11, verticalalignment='bottom',
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.9, edgecolor='gray'))
        
        # Adjust layout
        plt.tight_layout()
        plt.subplots_adjust(left=0.05, right=0.98, top=0.91, bottom=0.15, 
                          wspace=0.08, hspace=0.25)
        
        # Save the figure
        output_path = self.output_dir / "skull_extraction_methodology.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"Skull extraction methodology illustration saved to: {output_path}")
        return output_path
    
    def create_combined_publication_figure(self, all_bone_mask, brain_mask, skull_bone_mask, thickness_map, thickness_mask, thickness_stats):
        """Create a single publication-ready figure with both extraction steps, thickness analysis, and aligned colorbar."""
        import matplotlib.pyplot as plt
        import numpy as np
        plt.style.use('default')
        plt.rcParams.update({
            'font.size': 11,
            'font.family': 'DejaVu Sans',
            'axes.linewidth': 1.2,
            'axes.labelweight': 'bold',
            'figure.dpi': 300
        })
        # 4 rows (step A, step B, thickness, histogram), 4 columns (3 views + 1 colorbar)
        fig = plt.figure(figsize=(15, 16))
        gs = fig.add_gridspec(4, 4, width_ratios=[1, 1, 1, 0.07], height_ratios=[1, 1, 1, 0.7], wspace=0.08, hspace=0.18)
        vx, vy, vz = self.voxel_dims
        mid_x, mid_y, mid_z = [s // 2 for s in all_bone_mask.shape]
        left_cortex = (self.data == self.LEFT_CEREBRAL_CORTEX_LABEL).astype(np.uint8)
        right_cortex = (self.data == self.RIGHT_CEREBRAL_CORTEX_LABEL).astype(np.uint8)
        brain_stem = (self.data == self.BRAIN_STEM_LABEL).astype(np.uint8)
        reference_brain_mask = (left_cortex + right_cortex + brain_stem > 0).astype(np.uint8)
        hemisphere_mask = (left_cortex + right_cortex > 0).astype(np.uint8)
        view_labels = ['Axial View', 'Coronal View', 'Sagittal View']
        # --- Row 0: Extraction Step A (reference regions) ---
        for col in range(3):
            ax = fig.add_subplot(gs[0, col])
            if col == 0:
                bone_slice = all_bone_mask[:, :, mid_z]
                hemisphere_slice = hemisphere_mask[:, :, mid_z]
                brainstem_slice = brain_stem[:, :, mid_z]
                aspect_ratio = vy / vx
                xlabel, ylabel = 'Anterior - Posterior', 'Left - Right'
            elif col == 1:
                bone_slice = all_bone_mask[:, mid_y, :]
                hemisphere_slice = hemisphere_mask[:, mid_y, :]
                brainstem_slice = brain_stem[:, mid_y, :]
                aspect_ratio = vz / vx
                xlabel, ylabel = 'Anterior - Posterior', 'Inferior - Superior'
            else:
                bone_slice = all_bone_mask[mid_x, :, :]
                hemisphere_slice = hemisphere_mask[mid_x, :, :]
                brainstem_slice = brain_stem[mid_x, :, :]
                aspect_ratio = vy / vz
                xlabel, ylabel = 'Left - Right', 'Inferior - Superior'
            img = np.zeros((bone_slice.shape[1], bone_slice.shape[0], 3))
            img[bone_slice.T > 0] = [0.8, 0.8, 0.8]
            img[hemisphere_slice.T > 0] = [0, 0.5, 1]
            img[brainstem_slice.T > 0] = [0, 1, 0]
            ax.imshow(img, origin='lower', aspect=aspect_ratio)
            ax.set_title(f'A{chr(65+col)}. {view_labels[col]} (Reference)', fontsize=13, fontweight='bold', pad=10)
            ax.set_xlabel(xlabel, fontweight='bold', fontsize=10)
            ax.set_ylabel(ylabel, fontweight='bold', fontsize=10)
            ax.grid(True, alpha=0.2, linestyle='--')
            ax.set_xticks([])
            ax.set_yticks([])
            if col == 0:
                ax.text(0.02, 0.98, 'Brain Regions Used:\n- Blue: Left/Right Cortex (hemispheres)\n- Green: Brain Stem\n- Gray: Bone (context)',
                        transform=ax.transAxes, fontsize=8, verticalalignment='top', horizontalalignment='left',
                        bbox=dict(boxstyle="round,pad=0.3", facecolor='lightblue', alpha=0.7))
        # --- Row 1: Extraction Step B (final skull mask) ---
        for col in range(3):
            ax = fig.add_subplot(gs[1, col])
            if col == 0:
                bone_slice = all_bone_mask[:, :, mid_z]
                skull_slice = skull_bone_mask[:, :, mid_z]
                hemisphere_slice = hemisphere_mask[:, :, mid_z]
                brainstem_slice = brain_stem[:, :, mid_z]
                aspect_ratio = vy / vx
                xlabel, ylabel = 'Anterior - Posterior', 'Left - Right'
            elif col == 1:
                bone_slice = all_bone_mask[:, mid_y, :]
                skull_slice = skull_bone_mask[:, mid_y, :]
                hemisphere_slice = hemisphere_mask[:, mid_y, :]
                brainstem_slice = brain_stem[:, mid_y, :]
                aspect_ratio = vz / vx
                xlabel, ylabel = 'Anterior - Posterior', 'Inferior - Superior'
            else:
                bone_slice = all_bone_mask[mid_x, :, :]
                skull_slice = skull_bone_mask[mid_x, :, :]
                hemisphere_slice = hemisphere_mask[mid_x, :, :]
                brainstem_slice = brain_stem[mid_x, :, :]
                aspect_ratio = vy / vz
                xlabel, ylabel = 'Left - Right', 'Inferior - Superior'
            img = np.zeros((bone_slice.shape[1], bone_slice.shape[0], 3))
            img[bone_slice.T > 0] = [0.3, 0.3, 0.3]
            img[skull_slice.T > 0] = [1, 0, 0]
            img[hemisphere_slice.T > 0] = [0, 0.5, 1]
            img[brainstem_slice.T > 0] = [0, 1, 0]
            ax.imshow(img, origin='lower', aspect=aspect_ratio)
            # Add Z-cutoff and brain center lines for coronal and sagittal views
            brain_coords = np.where(reference_brain_mask > 0)
            if len(brain_coords[0]) > 0 and col in [1, 2]:
                min_z, max_z = brain_coords[2].min(), brain_coords[2].max()
                brain_center_z = (min_z + max_z) // 2
                padding_voxels = 30
                z_threshold = brain_center_z - padding_voxels
                # In coronal and sagittal, y axis is z
                ax.axhline(y=z_threshold, color='yellow', linewidth=3, linestyle='--', alpha=0.9)
                ax.axhline(y=brain_center_z, color='white', linewidth=2, linestyle=':', alpha=0.8)
            ax.set_title(f'B{chr(65+col)}. {view_labels[col]} (Skull Mask)', fontsize=13, fontweight='bold', pad=10)
            ax.set_xlabel(xlabel, fontweight='bold', fontsize=10)
            ax.set_ylabel(ylabel, fontweight='bold', fontsize=10)
            ax.grid(True, alpha=0.2, linestyle='--')
            ax.set_xticks([])
            ax.set_yticks([])
            if col == 0:
                kept_percentage = np.sum(skull_bone_mask) / np.sum(all_bone_mask) * 100
                ax.text(0.02, 0.98, f'Final Skull Extraction:\n- Red: Extracted skull ({{kept_percentage:.1f}}%)\n- Dark gray: Excluded bone\n- Blue: Left/Right Cortex (hemispheres)\n- Green: Brain Stem',
                        transform=ax.transAxes, fontsize=8, verticalalignment='top', horizontalalignment='left',
                        bbox=dict(boxstyle="round,pad=0.3", facecolor='lightcoral', alpha=0.7))
        # --- Row 2: Thickness Analysis (3 views + colorbar) ---
        thickness_values = thickness_map[thickness_mask > 0]
        vmin, vmax = np.nanmin(thickness_values), np.nanmax(thickness_values)
        for col in range(3):
            ax = fig.add_subplot(gs[2, col])
            if col == 0:
                masked_thickness = np.where(thickness_mask[:, :, mid_z] > 0, thickness_map[:, :, mid_z], np.nan)
                aspect_ratio = vy / vx
                xlabel, ylabel = 'Anterior - Posterior', 'Left - Right'
            elif col == 1:
                masked_thickness = np.where(thickness_mask[:, mid_y, :] > 0, thickness_map[:, mid_y, :], np.nan)
                aspect_ratio = vz / vx
                xlabel, ylabel = 'Anterior - Posterior', 'Inferior - Superior'
            else:
                masked_thickness = np.where(thickness_mask[mid_x, :, :] > 0, thickness_map[mid_x, :, :], np.nan)
                aspect_ratio = vy / vz
                xlabel, ylabel = 'Left - Right', 'Inferior - Superior'
            im = ax.imshow(masked_thickness.T, cmap='hot', origin='lower', aspect=aspect_ratio, interpolation='bilinear', vmin=vmin, vmax=vmax)
            ax.set_title(f'C{chr(65+col)}. {view_labels[col]} Thickness', fontsize=13, fontweight='bold', pad=10)
            ax.set_xlabel(xlabel, fontweight='bold', fontsize=10)
            ax.set_ylabel(ylabel, fontweight='bold', fontsize=10)
            ax.grid(True, alpha=0.2, linestyle='--')
            ax.set_xticks([])
            ax.set_yticks([])
        # Colorbar in its own column, only for thickness row
        cbar_ax = fig.add_subplot(gs[2, 3])
        sm = plt.cm.ScalarMappable(cmap='hot', norm=plt.Normalize(vmin=vmin, vmax=vmax))
        sm.set_array([])
        cbar = fig.colorbar(sm, cax=cbar_ax)
        cbar.set_label('Thickness (mm)', rotation=90, fontweight='bold', labelpad=12, fontsize=11)
        # --- Row 3: Histogram (spanning first 3 columns) ---
        ax4 = fig.add_subplot(gs[3, :3])
        n, bins, patches = ax4.hist(thickness_values, bins=50, alpha=0.7, color='lightblue', edgecolor='navy', linewidth=1.2, density=True)
        ax4.axvline(thickness_stats['mean'], color='red', linestyle='-', linewidth=3, label=f"Mean: {thickness_stats['mean']:.2f} mm")
        ax4.axvline(thickness_stats['mean'] + thickness_stats['std'], color='red', linestyle='--', linewidth=2, label=f"+1 SD: {thickness_stats['mean'] + thickness_stats['std']:.2f} mm")
        ax4.axvline(thickness_stats['mean'] - thickness_stats['std'], color='red', linestyle='--', linewidth=2, label=f"-1 SD: {thickness_stats['mean'] - thickness_stats['std']:.2f} mm")
        p25, p75 = np.percentile(thickness_values, [25, 75])
        ax4.axvline(p25, color='orange', linestyle=':', linewidth=2, alpha=0.8, label=f"25th percentile: {p25:.2f} mm")
        ax4.axvline(p75, color='orange', linestyle=':', linewidth=2, alpha=0.8, label=f"75th percentile: {p75:.2f} mm")
        ax4.set_xlabel('Skull Bone Thickness (mm)', fontweight='bold', fontsize=11)
        ax4.set_ylabel('Probability Density', fontweight='bold', fontsize=11)
        ax4.set_title('D. Thickness Distribution', fontsize=13, fontweight='bold', pad=10)
        ax4.legend(loc='upper right', frameon=True, fancybox=True, shadow=True, fontsize=9)
        ax4.grid(True, alpha=0.3, axis='y')
        stats_text = f'''Statistics Summary:\nRange: {thickness_stats['min']:.2f} - {thickness_stats['max']:.2f} mm\nMean ± SD: {thickness_stats['mean']:.2f} ± {thickness_stats['std']:.2f} mm\nMedian: {np.median(thickness_values):.2f} mm\nIQR: {p25:.2f} - {p75:.2f} mm\nVoxels: {np.sum(thickness_mask):,}\nVolume: {np.sum(thickness_mask) * self.voxel_volume / 1000:.1f} cm³'''
        ax4.text(0.02, 0.98, stats_text, transform=ax4.transAxes, fontsize=9, verticalalignment='top', horizontalalignment='left', bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.9, edgecolor='gray'))
        # Methodology explanation at the bottom left
        fig.text(0.01, 0.01, "Skull Extraction Methodology:\nA. Brain Reference Identification: Left/Right Cerebral Cortex (blue) + Brain Stem (green) define Z-coordinate reference\nB. Skull Extraction Result: Apply 3D bounding box (±30mm) + Z-cutoff below brain center to exclude jaw/vertebrae", fontsize=10, verticalalignment='bottom', bbox=dict(boxstyle="round,pad=0.4", facecolor="lightyellow", alpha=0.9, edgecolor='gray'))
        fig.subplots_adjust(left=0.05, right=0.97, top=0.94, bottom=0.07, wspace=0.08, hspace=0.18)
        output_path = self.output_dir / "skull_combined_publication_figure.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"Combined publication figure saved to: {output_path}")
        return output_path
    
    def generate_summary_report(self, volume_results, skull_bone_thickness):
        """Generate a summary report of the analysis."""
        # print("Generating summary report...")
        
        report_path = self.output_dir / "skull_bone_analysis_summary.txt"
        
        with open(report_path, 'w') as f:
            f.write("SKULL BONE ANALYSIS SUMMARY REPORT\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"Input file: {self.nifti_path}\n")
            f.write(f"Data shape: {self.data.shape}\n")
            f.write(f"Voxel dimensions: {self.voxel_dims} mm\n")
            f.write(f"Voxel volume: {self.voxel_volume:.3f} mm³\n\n")
            
            f.write("VOLUME ANALYSIS:\n")
            f.write("-" * 20 + "\n")
            f.write(f"Skull bone volume:       {volume_results['skull_bone_volume_cm3']:.3f} cm³ ({volume_results['skull_bone_volume_mm3']:.1f} mm³)\n\n")
            
            f.write("THICKNESS ANALYSIS:\n")
            f.write("-" * 20 + "\n")
            f.write("Skull Bone (cortical + cancellous):\n")
            f.write(f"  Maximum thickness:     {skull_bone_thickness['max']:.3f} mm\n")
            f.write(f"  Minimum thickness:     {skull_bone_thickness['min']:.3f} mm\n")
            f.write(f"  Mean thickness:        {skull_bone_thickness['mean']:.3f} mm\n")
            f.write(f"  Standard deviation:    {skull_bone_thickness['std']:.3f} mm\n\n")
            
            f.write("SPATIAL FILTERING:\n")
            f.write("-" * 18 + "\n")
            f.write("- Analysis focused on skull bone only (jaw and vertebrae excluded)\n")
            f.write("- Spatial filtering based on brain cortex and brain stem locations\n")
            f.write("- Bounding box extended around brain regions with padding\n")
            f.write("- Z-coordinate filtering applied to exclude lower anatomy\n\n")
            
            f.write("ANALYSIS NOTES:\n")
            f.write("-" * 15 + "\n")
            f.write("- Combined cortical and cancellous bone as single 'Bone' tissue\n")
            f.write("- Thickness calculated using 3D distance transform\n")
            f.write("- Thickness represents twice the distance to nearest tissue boundary\n")
            f.write("- Volume calculations based on voxel dimensions from NIfTI header\n")
            f.write("- Visualizations show middle slices and thickness distributions\n")
        
        print(f"Summary report saved to: {report_path}")
        return report_path
    
    def run_full_analysis(self):
        """Run the complete skull bone analysis pipeline."""
        print("\n[Skull Bone Analysis] Starting...")
        skull_bone_mask = self.extract_skull_bone_mask()
        volume_results = self.calculate_volumes()
        skull_bone_thickness = self.calculate_thickness_3d(skull_bone_mask, "Bone")
        self.create_combined_publication_figure(
            self.all_bone_mask,
            self.brain_mask,
            skull_bone_mask,
            skull_bone_thickness['thickness_map'],
            skull_bone_mask,
            skull_bone_thickness
        )
        self.generate_summary_report(volume_results, skull_bone_thickness)
        print(f"[Skull Bone Analysis] Complete. Volume: {volume_results['skull_bone_volume_cm3']:.2f} cm³ | Thickness: {skull_bone_thickness['mean']:.2f}±{skull_bone_thickness['std']:.2f} mm (range: {skull_bone_thickness['min']:.2f}-{skull_bone_thickness['max']:.2f} mm)")
        print(f"[Skull Bone Analysis] Results saved to: {self.output_dir}")
        return {
            'volumes': volume_results,
            'skull_bone_thickness': skull_bone_thickness
        }


def main():
    parser = argparse.ArgumentParser(description="Analyze skull bone structures from segmented tissue data (excludes jaw/vertebrae)")
    parser.add_argument("nifti_path", help="Path to the segmented NIfTI file")
    parser.add_argument("-o", "--output", default="bone_analysis_output", 
                       help="Output directory for results (default: bone_analysis_output)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.nifti_path):
        print(f"Error: NIfTI file not found: {args.nifti_path}")
        return 1
    
    try:
        analyzer = BoneAnalyzer(args.nifti_path, args.output)
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