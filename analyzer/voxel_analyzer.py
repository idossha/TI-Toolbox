"""
VoxelAnalyzer: A tool for analyzing voxel-based neuroimaging data

This module provides functionality for analyzing voxel-based data from medical imaging,
particularly focusing on field analysis in specific regions of interest (ROIs).

Inputs:
    - NIfTI files containing field data
    - Atlas files (NIfTI/MGZ) for cortical parcellation
    - ROI specifications (coordinates, regions)

Outputs:
    - Statistical measures (mean, min, max)
    - ROI masks
    - Visualization files (optional)

Example Usage:
    ```python
    # Initialize analyzer
    analyzer = VoxelAnalyzer(
        field_nifti="/path/to/field.nii.gz",
        subject_dir="/path/to/subject",
        output_dir="/path/to/output"
    )

    # Analyze a spherical ROI
    sphere_results = analyzer.analyze_sphere(
        center_coordinates=[0, 0, 0],
        radius=10,
        visualize=True
    )

    # Analyze a cortical region
    cortex_results = analyzer.analyze_cortex(
        atlas_file="/path/to/atlas.mgz",
        target_region="Left-Hippocampus"
    )

    # Analyze whole head
    whole_head_results = analyzer.analyze_whole_head(
        atlas_file="/path/to/atlas.mgz",
        visualize=True
    )
    ```

Dependencies:
    - numpy
    - nibabel
    - subprocess (for FreeSurfer operations)
"""

import os
import numpy as np
import nibabel as nib
import subprocess
import tempfile
from pathlib import Path
import time
from visualizer import VoxelVisualizer
import csv
from datetime import datetime
import sys
import traceback

# Configure matplotlib for non-interactive backend before importing
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt

# Add the parent directory to the path to access utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util


class VoxelAnalyzer:
    """
    A class for analyzing voxel-based data from medical imaging.
    
    This class provides methods for analyzing field data in specific regions of interest,
    including spherical ROIs and cortical regions defined by an atlas.
    
    Attributes:
        field_nifti (str): Path to the NIfTI file containing field data
        subject_dir (str): Directory containing subject data
        output_dir (str): Directory where analysis results will be saved
        visualizer (VoxelVisualizer): Instance of visualizer for generating plots
    """
    
    def __init__(self, field_nifti: str, subject_dir: str, output_dir: str, logger=None):
        """
        Initialize the VoxelAnalyzer with paths to required data.
        
        Args:
            field_nifti (str): Path to the NIfTI file containing field data
            subject_dir (str): Directory containing subject data
            output_dir (str): Directory where analysis results will be saved
            logger: Optional logger instance to use. If None, creates its own.
            
        Raises:
            FileNotFoundError: If field_nifti file does not exist
        """
        self.field_nifti = field_nifti
        self.subject_dir = subject_dir
        self.output_dir = output_dir
        
        # Set up logger - use provided logger or create a new one
        if logger is not None:
            # Create a child logger to distinguish voxel analyzer logs
            self.logger = logger.getChild('voxel_analyzer')
        else:
            # Create our own logger if none provided
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            self.logger = logging_util.get_logger('voxel_analyzer', f'output/Documentation/voxel_analyzer_{time_stamp}.log', overwrite=True)
        
        # Initialize visualizer with logger
        self.visualizer = VoxelVisualizer(output_dir, self.logger)
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            self.logger.info(f"Creating output directory: {output_dir}")
            os.makedirs(output_dir)
        
        # Validate that field_nifti exists
        if not os.path.exists(field_nifti):
            self.logger.error(f"Field file not found: {field_nifti}")
            raise FileNotFoundError(f"Field file not found: {field_nifti}")
        
        self.logger.info(f"Voxel analyzer initialized successfully")
        self.logger.info(f"Field NIfTI path: {field_nifti}")
        self.logger.info(f"Subject directory: {subject_dir}")
        self.logger.info(f"Output directory: {output_dir}")

    def _extract_atlas_type(self, atlas_file):
        """
        Extract atlas type from filename by looking for common atlas names.
        
        Args:
            atlas_file (str): Path to the atlas file
            
        Returns:
            str: Atlas type if found, otherwise 'custom'
            
        Example:
            >>> analyzer._extract_atlas_type("/path/to/subject_dk40.mgz")
            'DK40'
        """
        atlas_file = os.path.basename(atlas_file).lower()
        
        # Check for common atlas types in filename
        if 'dk40' in atlas_file:
            return 'DK40'
        elif 'hcp_mmp1' in atlas_file:
            return 'HCP_MMP1'
        elif 'a2009s' in atlas_file:
            return 'a2009s'
        else:
            return 'custom'

    def analyze_whole_head(self, atlas_file, visualize=False):
        """
        Analyze all regions in the specified atlas.
        """
        start_time = time.time()
        self.logger.info(f"Starting whole head analysis of atlas: {atlas_file}")
        
        # Extract atlas type from filename
        atlas_type = self._extract_atlas_type(atlas_file)
        self.logger.info(f"Detected atlas type: {atlas_type}")
        
        try:
            # Load region information once
            region_info = self.get_atlas_regions(atlas_file)
            
            # Load atlas and field data once
            self.logger.info(f"Loading atlas from {atlas_file}...")
            atlas_tuple = self.load_brain_image(atlas_file)
            atlas_img, atlas_arr = atlas_tuple
            
            self.logger.info(f"Loading field from {self.field_nifti}...")
            field_tuple = self.load_brain_image(self.field_nifti)
            field_img, field_arr = field_tuple
            
            # Handle 4D field data (extract first volume if multiple volumes)
            if len(field_arr.shape) == 4:
                self.logger.info(f"Detected 4D field data with shape {field_arr.shape}")
                field_shape_3d = field_arr.shape[:3]
                # If time dimension is 1, we can simply reshape to 3D
                if field_arr.shape[3] == 1:
                    self.logger.info("Reshaping 4D field data to 3D")
                    field_arr = field_arr[:,:,:,0]
                else:
                    self.logger.warning(f"4D field has {field_arr.shape[3]} volumes. Using only the first volume.")
                    field_arr = field_arr[:,:,:,0]
            else:
                field_shape_3d = field_arr.shape
            
            # Check if resampling is needed and do it once if necessary
            if atlas_arr.shape != field_shape_3d:
                self.logger.info("Atlas and field dimensions don't match, attempting to resample...")
                self.logger.debug(f"Atlas shape: {atlas_arr.shape}")
                self.logger.debug(f"Field shape: {field_arr.shape}")

                # Resample the atlas to match the field data, passing atlas_file
                atlas_img, atlas_arr = self.resample_to_match(
                    atlas_img,
                    field_shape_3d,  # Use only the spatial dimensions
                    field_img.affine,
                    source_path=atlas_file  # Pass the atlas file path
                )
                
                # Verify the resampling worked
                if atlas_arr.shape != field_shape_3d:
                    raise ValueError(f"Failed to resample atlas to match field dimensions: {atlas_arr.shape} vs {field_shape_3d}")
            
            field_tuple = (field_img, field_arr)
            
            # Dictionary to store results for each region
            results = {}
            
            # Analyze each region in the atlas
            for region_id, info in region_info.items():
                region_name = info['name']
                try:
                    self.logger.info(f"Processing region: {region_name}")
                    
                    # Create a directory for this region in the main output directory
                    region_dir = os.path.join(self.output_dir, region_name)
                    os.makedirs(region_dir, exist_ok=True)
                    
                    # Create mask for this region
                    region_mask = (atlas_arr == region_id)
                    
                    # Check if the mask contains any voxels
                    mask_count = np.sum(region_mask)
                    if mask_count == 0:
                        self.logger.warning(f"Warning: Region {region_name} (ID: {region_id}) contains 0 voxels in the atlas")
                        region_results = {
                            'mean_value': None,
                            'max_value': None,
                            'min_value': None,
                            'voxels_in_roi': 0
                        }
                        
                        # Store in the overall results
                        results[region_name] = region_results
                        
                        continue
                    
                    # Filter for voxels with positive values
                    value_mask = (field_arr > 0)
                    combined_mask = region_mask & value_mask
                    
                    # Extract field values after filtering
                    field_values = field_arr[combined_mask]
                    
                    # Check if any voxels remain after filtering
                    filtered_count = len(field_values)
                    if filtered_count == 0:
                        self.logger.warning(f"Warning: Region {region_name} (ID: {region_id}) has no voxels with positive values")
                        region_results = {
                            'mean_value': None,
                            'max_value': None,
                            'min_value': None,
                            'voxels_in_roi': 0
                        }
                        
                        # Store in the overall results
                        results[region_name] = region_results
                        
                        continue
                    
                    # Calculate statistics
                    mean_value = np.mean(field_values)
                    max_value = np.max(field_values)
                    min_value = np.min(field_values)
                    
                    # Create result dictionary for this region
                    region_results = {
                        'mean_value': mean_value,
                        'max_value': max_value,
                        'min_value': min_value,
                        'voxels_in_roi': filtered_count  # Store the number of voxels
                    }
                    
                    # Store in the overall results
                    results[region_name] = region_results
                    
                    # Generate visualizations if requested
                    if visualize:
                        # Create visualization NIfTI file directly in the region directory
                        viz_file = self._generate_region_visualization(
                            atlas_img=atlas_img,
                            atlas_arr=atlas_arr,
                            field_arr=field_arr,
                            region_id=region_id,
                            region_name=region_name,
                            output_dir=region_dir
                        )
                        
                        # Generate region-specific value distribution plot
                        if len(field_values) > 0:
                            # Create a custom visualizer just for this region with the region directory as output
                            region_visualizer = VoxelVisualizer(region_dir, self.logger)
                            
                            # Generate value distribution plot for this region
                            region_visualizer.generate_value_distribution_plot(
                                field_values,
                                region_name,
                                atlas_type,
                                mean_value,
                                max_value,
                                min_value,
                                data_type='voxel'
                            )
                    
                except Exception as e:
                    self.logger.warning(f"Warning: Failed to analyze region {region_name}: {str(e)}")
                    results[region_name] = {
                        'mean_value': None,
                        'max_value': None,
                        'min_value': None,
                        'voxels_in_roi': 0
                    }
            
            # Generate global scatter plot and save whole-head results to CSV directly in the main output directory
            if visualize and results:
                self.logger.info("Generating global visualization plots...")
                # Generate scatter plots in the main output directory
                self._generate_whole_head_plots(results, atlas_type, 'voxel')
                
                # Generate and save summary CSV
                self._save_whole_head_summary_csv(results, atlas_type, 'voxel')
            
            return results
            
        finally:
            # Clean up all temporary data
            try:
                del atlas_arr
                del field_arr
                del region_info
                if 'atlas_tuple' in locals():
                    del atlas_tuple
                if 'field_tuple' in locals():
                    del field_tuple
            except:
                pass
    
    def _generate_region_visualization(self, atlas_img, atlas_arr, field_arr, region_id, region_name, output_dir):
        """Generate a NIfTI file visualization for a specific cortical region and save it directly to the specified directory."""
        # Create mask for this region
        region_mask = (atlas_arr == region_id)
        
        # Ensure field_arr is 3D for visualization
        if len(field_arr.shape) == 4:
            viz_field_arr = field_arr[:,:,:,0]  # Use the first volume
        else:
            viz_field_arr = field_arr
        
        # Create visualization array (zeros everywhere except the region)
        vis_arr = np.zeros_like(atlas_arr)
        vis_arr[region_mask] = viz_field_arr[region_mask]
        
        # Create output filename directly in the region directory
        output_filename = os.path.join(output_dir, f"{region_name}_ROI.nii.gz")
        
        # Save as NIfTI
        import nibabel as nib
        vis_img = nib.Nifti1Image(vis_arr, atlas_img.affine)
        nib.save(vis_img, output_filename)
        
        self.logger.info(f"Created visualization: {output_filename}")
        return output_filename
                
    def _generate_whole_head_plots(self, results, atlas_type, data_type='voxel'):
        """Generate a sorted scatter plot for whole head analysis directly in the main output directory."""
        # Filter out regions with None values
        valid_results = {name: res for name, res in results.items() if res['mean_value'] is not None}
        
        if not valid_results:
            self.logger.warning("Warning: No valid results to plot")
            return
        
        try:
            # Prepare data for plotting
            regions = list(valid_results.keys())
            mean_values = [res['mean_value'] for res in valid_results.values()]
            
            # Check if voxel count data is available, and use it if possible
            try:
                # Attempt to get voxel counts if they're in the data
                counts = [res.get(f'{data_type}s_in_roi', 1) for res in valid_results.values()]
                use_counts_for_color = True
            except (KeyError, AttributeError):
                # If not available, use a default color
                self.logger.note(f"Note: '{data_type}s_in_roi' not found in results, using default coloring")
                counts = [1 for _ in valid_results.values()]
                use_counts_for_color = False
            
            # Create output directory if it doesn't exist
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Create figure with larger size for all regions
            fig, ax = plt.subplots(figsize=(15, 10))
            
            # Sort regions by mean value
            sorted_indices = np.argsort(mean_values)
            sorted_regions = [regions[i] for i in sorted_indices]
            sorted_values = [mean_values[i] for i in sorted_indices]
            
            # Use the coloring approach based on availability of count data
            if use_counts_for_color:
                sorted_counts = [counts[i] for i in sorted_indices]
                scatter = ax.scatter(range(len(sorted_regions)), sorted_values,
                                c=sorted_counts,
                                cmap='viridis',
                                s=100,
                                alpha=0.6,
                                edgecolors='black',
                                linewidths=1)
                
                # Add colorbar with enhanced styling
                cbar = plt.colorbar(scatter, ax=ax)
                cbar.set_label(f'Number of {data_type.capitalize()}s', fontsize=12, fontweight='bold')
            else:
                scatter = ax.scatter(range(len(sorted_regions)), sorted_values,
                                c='royalblue',
                                s=100,
                                alpha=0.6,
                                edgecolors='black',
                                linewidths=1)
            
            # Customize plot
            ax.set_title(f'Cortical Region Analysis - {atlas_type}', 
                    pad=20, 
                    fontsize=14, 
                    fontweight='bold')
            ax.set_xlabel('Region Index (sorted by mean value)', 
                        fontsize=12, 
                        fontweight='bold')
            ax.set_ylabel('Mean Field Value', 
                        fontsize=12, 
                        fontweight='bold')
            
            # Add grid
            ax.grid(True, linestyle='--', alpha=0.3)
            
            # Set x-ticks to show region names at the bottom
            ax.set_xticks(range(len(sorted_regions)))
            ax.set_xticklabels(sorted_regions, rotation=45, ha='right', fontsize=8)
            
            # Adjust layout to prevent label cutoff
            plt.tight_layout()
            
            # Save plot directly in the main output directory
            output_file = os.path.join(self.output_dir, f'cortex_analysis_{atlas_type}.png')
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            self.logger.info(f"Generated sorted scatter plot: {output_file}")
        except Exception as e:
            # If there's any error during plotting, log it but don't stop the overall analysis
            self.logger.warning(f"Warning: Failed to generate plots: {str(e)}")
            self.logger.error(f"Error details: {traceback.format_exc()}")
            self.logger.info("Continuing with analysis without visualizations.")

    def _save_whole_head_summary_csv(self, results, atlas_type, data_type='voxel'):
        """Save a summary CSV of whole-head analysis results directly in the output directory."""
        # Create the CSV
        filename = f"whole_head_{atlas_type}_summary.csv"
        output_path = os.path.join(self.output_dir, filename)
        
        # Write results to CSV
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header row
            header = ['Region', 'Mean Value', 'Max Value', 'Min Value', f'{data_type.capitalize()}s in ROI']
            writer.writerow(header)
            
            # Write data for each region
            for region_name, region_data in results.items():
                row = [
                    region_name,
                    region_data.get('mean_value', 'N/A'),
                    region_data.get('max_value', 'N/A'),
                    region_data.get('min_value', 'N/A'),
                    region_data.get(f'{data_type}s_in_roi', 0)
                ]
                writer.writerow(row)
        
        self.logger.info(f"Saved whole-head analysis summary to: {output_path}")
        return output_path

    def analyze_sphere(self, center_coordinates, radius, visualize=False):
        """
        Analyze a spherical region of interest from voxel data.
        
        Returns:
            Dictionary containing analysis results or None if no valid voxels found
        """
        self.logger.info(f"Starting spherical ROI analysis (radius={radius}mm) at coordinates {center_coordinates}")
        
        # Load the NIfTI data
        self.logger.info("Loading field data...")
        img = nib.load(self.field_nifti)
        field_data = img.get_fdata()
        
        # Handle 4D field data (extract first volume if multiple volumes)
        if len(field_data.shape) == 4:
            if field_data.shape[3] == 1:
                field_data = field_data[:,:,:,0]
            else:
                field_data = field_data[:,:,:,0]
        
        # Get voxel dimensions (for proper distance calculation)
        voxel_size = np.array(img.header.get_zooms()[:3])
        
        # Get affine transformation matrix
        affine = img.affine
        
        # Convert world coordinates to voxel coordinates if needed
        self.logger.info("Converting coordinates and creating ROI mask...")
        inv_affine = np.linalg.inv(affine)
        voxel_coords = np.dot(inv_affine, np.append(center_coordinates, 1))[:3]
        
        # Create coordinate grids for the entire volume
        x_size, y_size, z_size = field_data.shape
        x, y, z = np.ogrid[:x_size, :y_size, :z_size]
        
        # Calculate distance from center voxel (using voxel dimensions to account for anisotropy)
        dist_from_center = np.sqrt(
            ((x - voxel_coords[0])**2 * voxel_size[0]**2) +
            ((y - voxel_coords[1])**2 * voxel_size[1]**2) +
            ((z - voxel_coords[2])**2 * voxel_size[2]**2)
        )
        
        # Create the spherical mask
        roi_mask = dist_from_center <= radius
        
        # Create mask for non-zero values
        nonzero_mask = field_data > 0
        
        # Combine masks to get only non-zero values within ROI
        combined_mask = roi_mask & nonzero_mask
        
        # Count voxels in ROI
        roi_voxels_count = np.sum(combined_mask)
        total_roi_voxels = np.sum(roi_mask)
        
        # Check if we have any voxels in the ROI
        if roi_voxels_count == 0:
            # Determine the tissue type from the field NIfTI name
            field_name = os.path.basename(self.field_nifti).lower()
            tissue_type = "grey matter" if "grey" in field_name else "white matter" if "white" in field_name else "brain tissue"
            
            warning_msg = f"""
\033[93m⚠️  WARNING: Analysis Failed ⚠️
• No valid voxels found in ROI at [{center_coordinates[0]}, {center_coordinates[1]}, {center_coordinates[2]}], r={radius}mm
• {"ROI not intersecting " + tissue_type if total_roi_voxels == 0 else "ROI contains only zero/invalid values"}
• {"Adjust coordinates/radius" if total_roi_voxels == 0 else "Check field data"} or verify using freeview\033[0m"""
            self.logger.warning(warning_msg)
            
            return None
        
        self.logger.info("Calculating statistics...")
        # Get the field values within the ROI
        roi_values = field_data[combined_mask]
        
        # Calculate statistics
        min_value = np.min(roi_values)
        max_value = np.max(roi_values)
        mean_value = np.mean(roi_values)
        
        # Create results dictionary
        results = {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'voxels_in_roi': roi_voxels_count
        }
        
        # Generate visualization if requested
        if visualize:
            region_name = f"sphere_x{center_coordinates[0]}_y{center_coordinates[1]}_z{center_coordinates[2]}_r{radius}"
            
            # Create visualization overlay (showing field values only within the sphere)
            vis_arr = np.zeros_like(field_data)
            vis_arr[combined_mask] = field_data[combined_mask]
            
            # Save as NIfTI directly to the output directory
            vis_img = nib.Nifti1Image(vis_arr, affine)
            output_filename = os.path.join(self.output_dir, f"sphere_overlay_{region_name}.nii.gz")
            nib.save(vis_img, output_filename)
            self.logger.info(f"Created visualization overlay: {output_filename}")
            
            # Generate value distribution plot
            self.visualizer.generate_value_distribution_plot(
                roi_values,
                region_name,
                "Spherical ROI",
                mean_value,
                max_value,
                min_value,
                data_type='voxel'
            )
        
        # Save results to CSV
        region_name = f"sphere_x{center_coordinates[0]}_y{center_coordinates[1]}_z{center_coordinates[2]}_r{radius}"
        self.visualizer.save_results_to_csv(results, 'spherical', region_name, 'voxel')
        
        return results
    
    def _get_resampled_atlas_filename(self, atlas_file, target_shape):
        """Generate a filename for the resampled atlas.
        
        Args:
            atlas_file (str): Path to the original atlas file
            target_shape (tuple): Target shape for resampling
            
        Returns:
            str: Path to the resampled atlas file
        """
        # Extract base filename and extension
        atlas_dir = os.path.dirname(atlas_file)
        atlas_basename = os.path.basename(atlas_file)
        atlas_name, ext = os.path.splitext(atlas_basename)
        
        # Handle double extensions like .nii.gz
        if ext == '.gz' and atlas_name.endswith('.nii'):
            atlas_name = os.path.splitext(atlas_name)[0]
            ext = '.nii.gz'
        
        # Generate a shape string (e.g., "256x256x256")
        shape_str = 'x'.join(map(str, target_shape[:3]))  # Only use spatial dimensions
        
        # Create new filename
        resampled_filename = f"{atlas_name}_resampled_{shape_str}{ext}"
        resampled_path = os.path.join(atlas_dir, resampled_filename)
        
        return resampled_path

    def resample_to_match(self, source_img, target_shape, target_affine, source_path=None):
        """Resample source image to match target dimensions and affine using FreeSurfer's mri_convert.
        
        If a resampled version already exists, it will be loaded instead of generating a new one.
        
        Parameters
        ----------
        source_img : nibabel.Nifti1Image
            Source image to resample
        target_shape : tuple
            Target shape (x, y, z) or (x, y, z, t)
        target_affine : numpy.ndarray
            Target affine transformation matrix
        source_path : str, optional
            Path to the source file. If provided, will be used to generate a resampled file name.
            
        Returns
        -------
        tuple
            (resampled nibabel image, resampled data array)
        """
        self.logger.info(f"Resampling image from shape {source_img.shape} to {target_shape}")
        
        # If source_path is provided, try to find an existing resampled file
        if source_path:
            resampled_path = self._get_resampled_atlas_filename(source_path, target_shape)
            if os.path.exists(resampled_path):
                self.logger.info(f"Found existing resampled atlas: {resampled_path}")
                try:
                    resampled_img = nib.load(resampled_path)
                    resampled_data = resampled_img.get_fdata()
                    
                    # Check if the resampled image has the correct shape
                    if resampled_data.shape[:3] == target_shape[:3]:
                        self.logger.info("Loaded previously resampled atlas")
                        
                        # If target is 4D but resampled is 3D, reshape it to match
                        is_target_4d = len(target_shape) == 4
                        if is_target_4d and len(resampled_data.shape) == 3:
                            self.logger.info(f"Reshaping 3D data {resampled_data.shape} to match 4D target {target_shape}")
                            # Add a dimension to match the 4D target shape
                            resampled_data = np.expand_dims(resampled_data, axis=3)
                            
                            # Create a new 4D NIfTI image
                            new_header = resampled_img.header.copy()
                            new_header.set_data_shape(resampled_data.shape)
                            resampled_img = nib.Nifti1Image(resampled_data, resampled_img.affine, header=new_header)
                        
                        return resampled_img, resampled_data
                    else:
                        self.logger.warning(f"Existing resampled atlas has wrong shape: {resampled_data.shape[:3]} vs expected {target_shape[:3]}")
                except Exception as e:
                    self.logger.error(f"Error loading existing resampled atlas: {str(e)}")
                    self.logger.info("Will generate a new one")
        
        self.logger.info("Generating new resampled atlas...")
        
        # If target shape is 4D but source is 3D, we need to handle this specially
        is_target_4d = len(target_shape) == 4
        spatial_shape = target_shape[:3]  # Extract just the spatial dimensions
        
        # Create a temporary file for the target template
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_template:
            template_path = temp_template.name
        
        # Create a temporary file for the resampled output
        with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_output:
            output_path = temp_output.name
            
        try:
            # Save the source image to a temporary file if not provided
            if source_path and os.path.exists(source_path):
                # Use the provided source path
                temp_source_created = False
            else:
                # Save the source image to a temporary file
                with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp_source:
                    source_path = temp_source.name
                    nib.save(source_img, source_path)
                    temp_source_created = True
            
            # Create a template image with target dimensions (3D only)
            template_img = nib.Nifti1Image(np.zeros(spatial_shape), target_affine)
            nib.save(template_img, template_path)
            
            # Run mri_convert to resample the image
            cmd = [
                'mri_convert',
                '--reslice_like', template_path,  # Use template for resampling
                source_path,                      # Source image
                output_path                       # Output image
            ]
            
            self.logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True)
            
            # Load the resampled image
            resampled_img = nib.load(output_path)
            resampled_data = resampled_img.get_fdata()
            
            # If target is 4D but resampled is 3D, reshape it to match
            if is_target_4d and len(resampled_data.shape) == 3:
                self.logger.info(f"Reshaping 3D data {resampled_data.shape} to match 4D target {target_shape}")
                # Add a dimension to match the 4D target shape
                resampled_data = np.expand_dims(resampled_data, axis=3)
                
                # Create a new 4D NIfTI image
                new_header = resampled_img.header.copy()
                new_header.set_data_shape(resampled_data.shape)
                resampled_img = nib.Nifti1Image(resampled_data, resampled_img.affine, header=new_header)
            
            # Save the resampled atlas for future use if source_path was provided and not temporary
            if source_path and not temp_source_created:
                resampled_save_path = self._get_resampled_atlas_filename(source_path, target_shape)
                self.logger.info(f"Saving resampled atlas for future use: {resampled_save_path}")
                nib.save(resampled_img, resampled_save_path)
            
            self.logger.info("Resampling complete")
            return resampled_img, resampled_data
            
        finally:
            # Clean up temporary files
            for temp_file in [template_path, output_path]:
                try:
                    os.unlink(temp_file)
                except:
                    pass
            
            # Also remove temporary source file if we created it
            if 'temp_source_created' in locals() and temp_source_created and 'source_path' in locals():
                try:
                    os.unlink(source_path)
                except:
                    pass

    def analyze_cortex(self, atlas_file, target_region, region_info=None, atlas_data=None, field_data=None, visualize=False):
        """
        Analyze a field scan within a specific cortical region defined in an atlas.
        """
        # Extract atlas type from filename
        atlas_type = self._extract_atlas_type(atlas_file)
        
        # Load the atlas and field data if not provided
        if atlas_data is None:
            self.logger.info(f"Loading atlas from {atlas_file}...")
            atlas_tuple = self.load_brain_image(atlas_file)
            atlas_img, atlas_arr = atlas_tuple
        else:
            # Unpack the tuple
            atlas_img, atlas_arr = atlas_data
            
        if field_data is None:
            self.logger.info(f"Loading field from {self.field_nifti}...")
            field_tuple = self.load_brain_image(self.field_nifti)
            field_img, field_arr = field_tuple
        else:
            # Unpack the tuple
            field_img, field_arr = field_data
        
        # Handle 4D field data (extract first volume if multiple volumes)
        if len(field_arr.shape) == 4:
            self.logger.info(f"Detected 4D field data with shape {field_arr.shape}")
            field_shape_3d = field_arr.shape[:3]
            # If time dimension is 1, we can simply reshape to 3D
            if field_arr.shape[3] == 1:
                self.logger.info("Reshaping 4D field data to 3D")
                field_arr = field_arr[:,:,:,0]
            else:
                self.logger.warning(f"4D field has {field_arr.shape[3]} volumes. Using only the first volume.")
                field_arr = field_arr[:,:,:,0]
        else:
            field_shape_3d = field_arr.shape
                
        # Compare spatial dimensions for atlas and field
        if atlas_arr.shape != field_shape_3d:
            self.logger.info("Atlas and field dimensions don't match, attempting to resample...")
            self.logger.debug(f"Atlas shape: {atlas_arr.shape}")
            self.logger.debug(f"Field shape: {field_arr.shape}")

            # Resample the atlas to match the field data, passing atlas_file
            atlas_img, atlas_arr = self.resample_to_match(
                atlas_img,
                field_shape_3d,  # Use only the spatial dimensions
                field_img.affine,
                source_path=atlas_file  # Pass the atlas file path
            )
            
            # Verify the resampling worked
            if atlas_arr.shape != field_shape_3d:
                raise ValueError(f"Failed to resample atlas to match field dimensions: {atlas_arr.shape} vs {field_shape_3d}")
        
        # Load region information if not provided
        if region_info is None:
            region_info = self.get_atlas_regions(atlas_file)
        
        # Determine region ID based on target_region
        self.logger.info(f"Finding region information for {target_region}...")
        region_id, region_name = self.find_region(target_region, region_info)
        self.logger.info(f"Processing region: {region_name} (ID: {region_id})")
        
        # Create mask for this region
        region_mask = (atlas_arr == region_id)
        
        # Check if the mask contains any voxels
        mask_count = np.sum(region_mask)
        if mask_count == 0:
            self.logger.warning(f"Warning: Region {region_name} (ID: {region_id}) contains 0 voxels in the atlas")
            results = {
                'mean_value': None,
                'max_value': None,
                'min_value': None
            }
            
            # Save results to CSV even if empty
            self.visualizer.save_results_to_csv(results, 'cortical', region_name, 'voxel')
            
            return results
        
        # Filter for voxels with positive values
        value_mask = (field_arr > 0)
        combined_mask = region_mask & value_mask
        
        # Extract field values after filtering
        field_values = field_arr[combined_mask]
        
        # Check if any voxels remain after filtering
        filtered_count = len(field_values)
        if filtered_count == 0:
            self.logger.warning(f"Warning: Region {region_name} (ID: {region_id}) has no voxels with positive values")
            results = {
                'mean_value': None,
                'max_value': None,
                'min_value': None
            }
            
            # Save results to CSV even if empty
            self.visualizer.save_results_to_csv(results, 'cortical', region_name, 'voxel')
            
            return results
        
        self.logger.info("Calculating statistics...")
        # Calculate statistics
        mean_value = np.mean(field_values)
        max_value = np.max(field_values)
        min_value = np.min(field_values)
        
        # Prepare results dictionary
        results = {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value
        }
        
        # Generate visualization if requested
        if visualize:
            self.logger.info("Generating visualizations...")
            self.visualizer.generate_value_distribution_plot(
                field_values,
                region_name,
                atlas_type,
                mean_value,
                max_value,
                min_value,
                data_type='voxel'
            )

            # Create visualization NIfTI file
            viz_file = self.visualizer.create_cortex_nifti(
                atlas_img=atlas_img,
                atlas_arr=atlas_arr,
                field_arr=field_arr,
                region_id=region_id,
                region_name=region_name
            )
            
        # Save results to CSV
        self.visualizer.save_results_to_csv(results, 'cortical', region_name, 'voxel')
        
        # Return analysis results
        return results

    def get_atlas_regions(self, atlas_file):
        """Extract region information from atlas file using FreeSurfer's mri_segstats.
        
        Parameters
        ----------
        atlas_file : str
            Path to the atlas file (.nii or .mgz)
            
        Returns
        -------
        dict
            Dictionary mapping region IDs to region information
        """
        region_info = {}
        
        # Get the atlas name from the file path
        atlas_name = os.path.basename(atlas_file)
        atlas_name = os.path.splitext(atlas_name)[0]  # Remove extension
        if atlas_name.endswith('.nii'):  # Handle .nii.gz case
            atlas_name = os.path.splitext(atlas_name)[0]
            
        # Get the FreeSurfer subject directory (parent of mri directory)
        mri_dir = os.path.dirname(atlas_file)
        freesurfer_dir = os.path.dirname(mri_dir)
        
        # Define the output file path in the mri directory
        output_file = os.path.join(mri_dir, f"{atlas_name}_labels.txt")
        
        # Create mri directory if it doesn't exist
        os.makedirs(mri_dir, exist_ok=True)
        
        # Function to generate the labels file
        def generate_labels_file():
            cmd = [
                'mri_segstats',
                '--seg', atlas_file,
                '--excludeid', '0',  # Exclude background
                '--ctab-default',    # Use default color table
                '--sum', output_file
            ]
            
            try:
                self.logger.info(f"Running: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, capture_output=True)
                return True
            except subprocess.CalledProcessError as e:
                self.logger.warning(f"Warning: Could not extract region information using mri_segstats: {str(e)}")
                self.logger.debug(f"Command output: {e.stdout.decode() if e.stdout else ''}")
                self.logger.debug(f"Command error: {e.stderr.decode() if e.stderr else ''}")
                return False
        
        # Function to parse the labels file
        def parse_labels_file():
            try:
                with open(output_file, 'r') as f:
                    # Skip header lines (all lines starting with #)
                    in_header = True
                    for line in f:
                        # Check if we've reached the end of the header
                        if in_header and not line.startswith('#'):
                            in_header = False
                            
                        # Process data lines (non-header)
                        if not in_header and line.strip():
                            parts = line.strip().split()
                            
                            # The format is:
                            # Index SegId NVoxels Volume_mm3 StructName
                            # We need at least 5 columns
                            if len(parts) >= 5:
                                try:
                                    region_id = int(parts[1])  # SegId is the second column
                                    n_voxels = int(parts[2])   # NVoxels is the third column
                                    
                                    # Structure name can contain spaces, so join the remaining parts
                                    region_name = ' '.join(parts[4:])
                                    
                                    # Generate a random color based on region_id for visualization
                                    # This creates a consistent color for each region
                                    import random
                                    random.seed(region_id)
                                    r = random.uniform(0.2, 0.8)
                                    g = random.uniform(0.2, 0.8)
                                    b = random.uniform(0.2, 0.8)
                                    
                                    region_info[region_id] = {
                                        'name': region_name,
                                        'voxel_count': n_voxels,
                                        'color': (r, g, b)
                                    }
                                except (ValueError, IndexError) as e:
                                    self.logger.warning(f"Warning: Could not parse line: {line.strip()}")
                                    self.logger.debug(f"Error: {str(e)}")
                
                return len(region_info) > 0
            except Exception as e:
                self.logger.error(f"Error reading labels file: {str(e)}")
                return False
        
        # Try to use existing file first
        if os.path.exists(output_file):
            self.logger.info(f"Found existing labels file: {output_file}")
            if parse_labels_file():
                self.logger.info(f"Successfully parsed {len(region_info)} regions from existing file")
                return region_info
            else:
                self.logger.info("Existing file is invalid or empty, regenerating...")
        
        # Generate new file if needed
        if generate_labels_file():
            if parse_labels_file():
                self.logger.info(f"Successfully generated and parsed {len(region_info)} regions")
                return region_info
        
        self.logger.warning("Warning: Could not get region information from atlas file")
        return region_info

    def load_brain_image(self, file_path):
        """Load brain image data from file, handling different formats.
        
        Parameters
        ----------
        file_path : str
            Path to the image file
            
        Returns
        -------
        tuple
            (nibabel image object, numpy array of data)
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext == '.mgz':
            # Try to use nibabel directly first
            try:
                img = nib.load(file_path)
                data = img.get_fdata()
                return img, data
            except Exception as e:
                self.logger.warning(f"Could not load MGZ file directly: {str(e)}")
                
                # Try to convert MGZ to NIfTI using mri_convert
                try:
                    # Create a temporary file for the converted image
                    with tempfile.NamedTemporaryFile(suffix='.nii.gz', delete=False) as temp:
                        temp_path = temp.name
                    
                    # Run mri_convert to convert MGZ to NIfTI
                    cmd = ['mri_convert', file_path, temp_path]
                    subprocess.run(cmd, check=True)
                    
                    # Load the converted file
                    img = nib.load(temp_path)
                    data = img.get_fdata()
                    
                    # Clean up
                    os.unlink(temp_path)
                    
                    return img, data
                except Exception as e2:
                    raise RuntimeError(f"Failed to convert MGZ file: {str(e2)}")
        else:
            # For NIfTI and other formats, use nibabel directly
            img = nib.load(file_path)
            data = img.get_fdata()
            return img, data
        
    def find_region(self, target_region, region_info):
        """Find region ID and name based on input.
        
        Parameters
        ----------
        target_region : str or int
            Target region name or ID
        region_info : dict
            Dictionary with region information
            
        Returns
        -------
        tuple
            (region_id, region_name)
        """
        # Check if target_region is an ID (int) or can be converted to one
        try:
            region_id = int(target_region)
            # If it's an ID, get the name from region_info if available
            if region_info and region_id in region_info:
                region_name = region_info[region_id]['name']
            else:
                region_name = f"Region {region_id}"
            return region_id, region_name
        except ValueError:
            # target_region is a string name, need to find the corresponding ID
            if not region_info:
                raise ValueError("Region labels are required to look up regions by name")
            
            # Search for the region name (case-insensitive)
            target_lower = target_region.lower()
            for region_id, info in region_info.items():
                if target_lower in info['name'].lower():
                    return region_id, info['name']
            
            # If we get here, region name was not found
            raise ValueError(f"Region name '{target_region}' not found in region labels")