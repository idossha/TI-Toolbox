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

# Standard library imports
import csv
import os
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path

# Third-party imports
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Local imports
from tools import logging_util
from analyzer.visualizer import VoxelVisualizer


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
    
    def __init__(self, field_nifti: str, subject_dir: str, output_dir: str, logger=None, quiet=False):
        """
        Initialize the VoxelAnalyzer with paths to required data.
        
        Args:
            field_nifti (str): Path to the NIfTI file containing field data
            subject_dir (str): Directory containing subject data
            output_dir (str): Directory where analysis results will be saved
            logger: Optional logger instance to use. If None, creates its own.
            quiet (bool): If True, suppress verbose logging messages
            
        Raises:
            FileNotFoundError: If field_nifti file does not exist
        """
        # Check for required dependencies
        if nib is None:
            raise ImportError("nibabel is required for voxel analysis but is not installed")
        
        self.field_nifti = field_nifti
        self.subject_dir = subject_dir
        self.output_dir = output_dir
        self.quiet = quiet
        
        # Set up logger - use provided logger or create a new one
        if logger is not None:
            # Create a child logger to distinguish voxel analyzer logs
            self.logger = logger.getChild('voxel_analyzer')
        else:
            # Create our own logger if none provided
            time_stamp = time.strftime('%Y%m%d_%H%M%S')
            
            # Extract subject ID from subject_dir (e.g., m2m_subject -> subject)
            subject_id = os.path.basename(self.subject_dir).split('_')[1] if '_' in os.path.basename(self.subject_dir) else os.path.basename(self.subject_dir)
            
            # Create derivatives/ti-toolbox/logs/sub-* directory structure
            log_dir = os.path.join('derivatives', 'ti-toolbox', 'logs', f'sub-{subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file in the new directory
            log_file = os.path.join(log_dir, f'voxel_analyzer_{time_stamp}.log')
            self.logger = logging_util.get_logger('voxel_analyzer', log_file, overwrite=True)
        
        # Initialize visualizer with logger
        self.visualizer = VoxelVisualizer(output_dir, self.logger)
        
        # Create output directory if it doesn't exist
        if not os.path.exists(output_dir):
            self.logger.debug(f"Creating output directory: {output_dir}")
            os.makedirs(output_dir)
        
        # Validate that field_nifti exists
        if not os.path.exists(field_nifti):
            self.logger.error(f"Field file not found: {field_nifti}")
            raise FileNotFoundError(f"Field file not found: {field_nifti}")
        
        self.logger.debug(f"Voxel analyzer initialized successfully")
        self.logger.debug(f"Field NIfTI path: {field_nifti}")
        self.logger.debug(f"Subject directory: {subject_dir}")
        self.logger.debug(f"Output directory: {output_dir}")

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
        if 'dkt' in atlas_file:
            return 'DKT'
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
        if not self.quiet:
            self.logger.info(f"Starting whole head analysis of atlas: {atlas_file}")
        
        # Extract atlas type from filename
        atlas_type = self._extract_atlas_type(atlas_file)
        self.logger.debug(f"Detected atlas type: {atlas_type}")
        
        try:
            # Load region information once
            region_info = self.get_atlas_regions(atlas_file)
            
            # Load atlas and field data once
            self.logger.debug(f"Loading atlas from {atlas_file}...")
            atlas_tuple = self.load_brain_image(atlas_file)
            atlas_img, atlas_arr = atlas_tuple
            
            self.logger.debug(f"Loading field from {self.field_nifti}...")
            field_tuple = self.load_brain_image(self.field_nifti)
            field_img, field_arr = field_tuple
            
            # Handle 4D field data (extract first volume if multiple volumes)
            if len(field_arr.shape) == 4:
                self.logger.debug(f"Detected 4D field data with shape {field_arr.shape}")
                field_shape_3d = field_arr.shape[:3]
                # If time dimension is 1, we can simply reshape to 3D
                if field_arr.shape[3] == 1:
                    self.logger.debug("Reshaping 4D field data to 3D")
                    field_arr = field_arr[:,:,:,0]
                else:
                    self.logger.warning(f"4D field has {field_arr.shape[3]} volumes. Using only the first volume.")
                    field_arr = field_arr[:,:,:,0]
            else:
                field_shape_3d = field_arr.shape
            
            # Check if resampling is needed and do it once if necessary
            if atlas_arr.shape != field_shape_3d:
                self.logger.debug("Atlas and field dimensions don't match, attempting to resample...")
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
            else:
                self.logger.debug("Atlas and field dimensions already match - skipping resampling")
            
            field_tuple = (field_img, field_arr)
            
            # Dictionary to store results for each region
            results = {}
            
            # Analyze each region in the atlas
            for region_id, info in region_info.items():
                region_name = info['name']
                try:
                    self.logger.debug(f"Processing region: {region_name}")
                    
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
                            'focality': None,
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
                            'focality': None,
                            'voxels_in_roi': 0
                        }
                        
                        # Store in the overall results
                        results[region_name] = region_results
                        
                        continue
                    
                    # Calculate statistics
                    mean_value = np.mean(field_values)
                    max_value = np.max(field_values)
                    min_value = np.min(field_values)

                    # Calculate focality (roi_average / whole_brain_average)
                    # Only include positive values in the whole brain average
                    whole_brain_positive_mask = field_arr > 0
                    whole_brain_average = np.mean(field_arr[whole_brain_positive_mask])
                    focality = mean_value / whole_brain_average
                    
                    # Log the whole brain average for debugging
                    if not self.quiet:
                        self.logger.info(f"Whole brain average (denominator for focality): {whole_brain_average:.6f}")
                    
                    # Create result dictionary for this region
                    region_results = {
                        'mean_value': mean_value,
                        'max_value': max_value,
                        'min_value': min_value,
                        'focality': focality,
                        'voxels_in_roi': filtered_count  # Store the number of voxels
                    }
                    
                    # Store in the overall results
                    results[region_name] = region_results
                    
                    # Generate visualizations if requested
                    if visualize:
                        # Create visualization NIfTI file directly in the region directory
                        viz_file = self.visualizer._generate_region_visualization(
                            atlas_img=atlas_img,
                            atlas_arr=atlas_arr,
                            field_arr=field_arr,
                            region_id=region_id,
                            region_name=region_name,
                            output_dir=region_dir
                        )
                        
                        # Generate focality histogram for this region
                        if len(field_values) > 0:
                            try:
                                if not self.quiet:
                                    self.logger.info(f"Generating focality histogram for region: {region_name}")
                                # Get voxel dimensions from the field image
                                field_img_tuple = self.load_brain_image(self.field_nifti)
                                voxel_dims = field_img_tuple[0].header.get_zooms()[:3]
                                
                                # Filter out zero values from whole head data for histogram
                                whole_head_positive_mask = field_arr > 0
                                whole_head_filtered = field_arr[whole_head_positive_mask]
                                
                                region_visualizer.generate_focality_histogram(
                                    whole_head_field_data=whole_head_filtered,
                                    roi_field_data=field_values,
                                    region_name=region_name,
                                    roi_field_value=mean_value,
                                    data_type='voxel',
                                    voxel_dims=voxel_dims
                                )
                            except Exception as e:
                                self.logger.warning(f"Could not generate focality histogram for {region_name}: {str(e)}")
                    
                except Exception as e:
                    self.logger.warning(f"Warning: Failed to analyze region {region_name}: {str(e)}")
                    results[region_name] = {
                        'mean_value': None,
                        'max_value': None,
                        'min_value': None,
                        'focality': None,
                        'voxels_in_roi': 0
                    }
            
            # Generate global visualization plots are disabled - only histograms are generated per region
                
                # Generate and save summary CSV
                self.visualizer.save_whole_head_results_to_csv(results, atlas_type, 'voxel')
            
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

    def analyze_sphere(self, center_coordinates, radius, visualize=False):
        """
        Analyze a spherical region of interest from voxel data.
        
        Returns:
            Dictionary containing analysis results or None if no valid voxels found
        """
        if not self.quiet:
            self.logger.info(f"Starting spherical ROI analysis (radius={radius}mm) at coordinates {center_coordinates}")
        
        # Load the NIfTI data
        if not self.quiet:
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
        if not self.quiet:
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
        
        if not self.quiet:
            self.logger.info("Calculating statistics...")
        # Get the field values within the ROI
        roi_values = field_data[combined_mask]
        
        # Calculate statistics
        min_value = np.min(roi_values)
        max_value = np.max(roi_values)
        mean_value = np.mean(roi_values)
        
        # Calculate focality (roi_average / whole_brain_average)
        # Only include positive values in the whole brain average
        whole_brain_positive_mask = field_data > 0
        whole_brain_average = np.mean(field_data[whole_brain_positive_mask])
        focality = mean_value / whole_brain_average
        
        # Log the whole brain average for debugging
        if not self.quiet:
            self.logger.info(f"Whole brain average (denominator for focality): {whole_brain_average:.6f}")
        
        # Create results dictionary
        results = {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'focality': focality,
            'voxels_in_roi': roi_voxels_count
        }
        
        # Generate visualization if requested
        if visualize:
            region_name = f"sphere_x{center_coordinates[0]:.2f}_y{center_coordinates[1]:.2f}_z{center_coordinates[2]:.2f}_r{radius}"
            
            # Create visualization overlay (showing field values only within the sphere)
            vis_arr = np.zeros_like(field_data)
            vis_arr[combined_mask] = field_data[combined_mask]
            
            # Save as NIfTI directly to the output directory
            vis_img = nib.Nifti1Image(vis_arr, affine)
            output_filename = os.path.join(self.output_dir, f"sphere_overlay_{region_name}.nii.gz")
            nib.save(vis_img, output_filename)
            if not self.quiet:
                self.logger.info(f"Created visualization overlay: {output_filename}")
            
            # Visualization requested but only histogram generation is supported
            
            # Generate focality histogram if visualizer is available
            if self.visualizer is not None:
                try:
                    if not self.quiet:
                        self.logger.info("Generating focality histogram for spherical ROI...")
                    # Get voxel dimensions from the loaded image
                    voxel_dims = img.header.get_zooms()[:3]
                    
                    # Filter out zero values from whole head data for histogram
                    whole_head_positive_mask = field_data > 0
                    whole_head_filtered = field_data[whole_head_positive_mask]
                    
                    self.visualizer.generate_focality_histogram(
                        whole_head_field_data=whole_head_filtered,
                        roi_field_data=roi_values,
                        region_name=region_name,
                        roi_field_value=mean_value,
                        data_type='voxel',
                        voxel_dims=voxel_dims
                    )
                except Exception as e:
                    self.logger.warning(f"Could not generate focality histogram for spherical ROI: {str(e)}")
        
        # Calculate and save extra focality information for entire volume
        if not self.quiet:
            self.logger.info("Calculating focality metrics for entire volume...")
        focality_info = self._calculate_focality_metrics(
            field_data,  # Use entire volume data
            np.prod(voxel_size),  # Voxel volume
            f"sphere_x{center_coordinates[0]:.2f}_y{center_coordinates[1]:.2f}_z{center_coordinates[2]:.2f}_r{radius}"
        )
        
        # Save results to CSV if visualizer is available
        if self.visualizer is not None:
            region_name = f"sphere_x{center_coordinates[0]:.2f}_y{center_coordinates[1]:.2f}_z{center_coordinates[2]:.2f}_r{radius}"
            self.visualizer.save_results_to_csv(results, 'spherical', region_name, 'voxel')
            
            # Save extra info CSV with focality data
            if focality_info:
                self.visualizer.save_extra_info_to_csv(focality_info, 'spherical', region_name, 'voxel')
        else:
            self.logger.warning("Cannot save results to CSV - VoxelVisualizer not available")
        
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
        if not self.quiet:
            self.logger.info(f"Resampling image from shape {source_img.shape} to {target_shape}")
        
        # If source_path is provided, try to find an existing resampled file
        if source_path:
            resampled_path = self._get_resampled_atlas_filename(source_path, target_shape)
            if os.path.exists(resampled_path):
                if not self.quiet:
                    self.logger.info(f"Found existing resampled atlas: {resampled_path}")
                try:
                    resampled_img = nib.load(resampled_path)
                    resampled_data = resampled_img.get_fdata()
                    
                    # Check if the resampled image has the correct shape
                    if resampled_data.shape[:3] == target_shape[:3]:
                        if not self.quiet:
                            self.logger.info("Loaded previously resampled atlas")
                        
                        # If target is 4D but resampled is 3D, reshape it to match
                        is_target_4d = len(target_shape) == 4
                        if is_target_4d and len(resampled_data.shape) == 3:
                            if not self.quiet:
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
                    if not self.quiet:
                        self.logger.info("Will generate a new one")
        
        if not self.quiet:
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
            
            if not self.quiet:
                self.logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True)
            
            # Load the resampled image
            resampled_img = nib.load(output_path)
            resampled_data = resampled_img.get_fdata()
            
            # If target is 4D but resampled is 3D, reshape it to match
            if is_target_4d and len(resampled_data.shape) == 3:
                if not self.quiet:
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
                if not self.quiet:
                    self.logger.info(f"Saving resampled atlas for future use: {resampled_save_path}")
                nib.save(resampled_img, resampled_save_path)
            
            if not self.quiet:
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
            self.logger.debug(f"Loading atlas from {atlas_file}...")
            atlas_tuple = self.load_brain_image(atlas_file)
            atlas_img, atlas_arr = atlas_tuple
        else:
            # Unpack the tuple
            atlas_img, atlas_arr = atlas_data
            
        if field_data is None:
            self.logger.debug(f"Loading field from {self.field_nifti}...")
            field_tuple = self.load_brain_image(self.field_nifti)
            field_img, field_arr = field_tuple
        else:
            # Unpack the tuple
            field_img, field_arr = field_data
        
        # Handle 4D field data (extract first volume if multiple volumes)
        if len(field_arr.shape) == 4:
            if not self.quiet:
                self.logger.info(f"Detected 4D field data with shape {field_arr.shape}")
            field_shape_3d = field_arr.shape[:3]
            # If time dimension is 1, we can simply reshape to 3D
            if field_arr.shape[3] == 1:
                if not self.quiet:
                    self.logger.info("Reshaping 4D field data to 3D")
                field_arr = field_arr[:,:,:,0]
            else:
                self.logger.warning(f"4D field has {field_arr.shape[3]} volumes. Using only the first volume.")
                field_arr = field_arr[:,:,:,0]
        else:
            field_shape_3d = field_arr.shape
                
        # Compare spatial dimensions for atlas and field
        if atlas_arr.shape != field_shape_3d:
            if not self.quiet:
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
        else:
            if not self.quiet:
                self.logger.info("Atlas and field dimensions already match - skipping resampling")
        
        # Load region information if not provided
        if region_info is None:
            region_info = self.get_atlas_regions(atlas_file)
        
        # Determine region ID based on target_region
        if not self.quiet:
            self.logger.info(f"Finding region information for {target_region}...")
        region_id, region_name = self.find_region(target_region, region_info)
        if not self.quiet:
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
                'min_value': None,
                'focality': None
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
                'min_value': None,
                'focality': None
            }
            
            # Save results to CSV even if empty
            self.visualizer.save_results_to_csv(results, 'cortical', region_name, 'voxel')
            
            return results
        
        if not self.quiet:
            self.logger.info("Calculating statistics...")
        # Calculate statistics
        mean_value = np.mean(field_values)
        max_value = np.max(field_values)
        min_value = np.min(field_values)

        # Calculate focality (roi_average / whole_brain_average)
        # Only include positive values in the whole brain average
        whole_brain_positive_mask = field_arr > 0
        whole_brain_average = np.mean(field_arr[whole_brain_positive_mask])
        focality = mean_value / whole_brain_average
        
        # Log the whole brain average for debugging
        if not self.quiet:
            self.logger.info(f"Whole brain average (denominator for focality): {whole_brain_average:.6f}")
        
        # Prepare results dictionary
        results = {
            'mean_value': mean_value,
            'max_value': max_value,
            'min_value': min_value,
            'focality': focality,
            'voxels_in_roi': filtered_count
        }
        
        # Generate visualization if requested
        if visualize:
            if not self.quiet:
                self.logger.info("Generating visualizations...")

            # Generate focality histogram
            try:
                if not self.quiet:
                    self.logger.info(f"Generating focality histogram for region: {region_name}")
                # Get voxel dimensions from the field image
                voxel_dims = field_img.header.get_zooms()[:3]
                
                # Filter out zero values from whole head data for histogram
                whole_head_positive_mask = field_arr > 0
                whole_head_filtered = field_arr[whole_head_positive_mask]
                
                self.visualizer.generate_focality_histogram(
                    whole_head_field_data=whole_head_filtered,
                    roi_field_data=field_values,
                    region_name=region_name,
                    roi_field_value=mean_value,
                    data_type='voxel',
                    voxel_dims=voxel_dims
                )
            except Exception as e:
                self.logger.warning(f"Could not generate focality histogram for {region_name}: {str(e)}")

            # Create visualization NIfTI file
            viz_file = self.visualizer.create_cortex_nifti(
                atlas_img=atlas_img,
                atlas_arr=atlas_arr,
                field_arr=field_arr,
                region_id=region_id,
                region_name=region_name
            )
            
        # Calculate and save extra focality information for entire field
        if not self.quiet:
            self.logger.info("Calculating focality metrics for entire field...")
        
        # Get voxel dimensions for volume calculations
        voxel_dims = field_img.header.get_zooms()[:3]
        voxel_volume = np.prod(voxel_dims)  # Volume of one voxel in mm³
        
        # Use entire field data (positive values only) for focality calculation
        entire_field_positive = field_arr[field_arr > 0]
        
        focality_info = self._calculate_focality_metrics(
            entire_field_positive,  # Use entire field, not just ROI
            voxel_volume, 
            region_name
        )
        
        # Save results to CSV
        self.visualizer.save_results_to_csv(results, 'cortical', region_name, 'voxel')
        
        # Save extra info CSV with focality data
        if focality_info:
            self.visualizer.save_extra_info_to_csv(focality_info, 'cortical', region_name, 'voxel')
        
        # Return analysis results
        return results

    def _calculate_focality_metrics(self, field_data, voxel_volume, region_name):
        """
        Calculate focality metrics similar to ex-search mesh_field_analyzer.
        
        Args:
            field_data: Field values for entire field volume (positive values only)
            voxel_volume: Volume of one voxel in mm³
            region_name: Name of the region being analyzed (for labeling purposes)
            
        Returns:
            dict: Dictionary containing focality metrics
        """
        try:
            # Standard parameters matching ex-search
            percentiles = [95, 99, 99.9]
            focality_cutoffs = [50, 75, 90, 95]
            
            if len(field_data) == 0:
                self.logger.warning(f"No field data available for focality calculation in {region_name}")
                return None
            
            # Remove NaN values
            valid_mask = ~np.isnan(field_data)
            data = field_data[valid_mask]
            
            if len(data) == 0:
                self.logger.warning(f"No valid field data after NaN removal for {region_name}")
                return None
            
            # For voxel data, each element has the same volume
            volumes = np.full(len(data), voxel_volume)
            
            # Sort data and corresponding volumes
            sort_idx = np.argsort(data)
            data_sorted = data[sort_idx]
            volumes_sorted = volumes[sort_idx]
            
            # Calculate cumulative volumes
            cumulative_volumes = np.cumsum(volumes_sorted)
            total_volume = cumulative_volumes[-1]
            normalized_cumulative = cumulative_volumes / total_volume
            
            # Calculate percentiles and their values
            percentile_values = []
            for percentile in percentiles:
                # Find index where cumulative volume exceeds percentile
                threshold_idx = np.searchsorted(normalized_cumulative, percentile/100.0)
                if threshold_idx >= len(data_sorted):
                    threshold_idx = len(data_sorted) - 1
                
                percentile_value = data_sorted[threshold_idx]
                percentile_values.append(float(percentile_value))
            
            # Calculate focality (volume above thresholds)
            # Use 99.9 percentile as reference (index 2)
            focality_values = []
            if len(percentile_values) > 2:
                reference_value = percentile_values[2]  # 99.9 percentile
                
                for cutoff in focality_cutoffs:
                    threshold = (cutoff / 100.0) * reference_value
                    above_threshold = data >= threshold
                    volume = np.sum(volumes[above_threshold]) if np.any(above_threshold) else 0.0
                    # Convert from mm³ to cm³ for consistency with ex-search
                    focality_values.append(float(volume / 1000.0))
            else:
                focality_values = [0.0] * len(focality_cutoffs)
            
            # Prepare results
            results = {
                'region_name': region_name,
                'field_name': 'field_value',  # Generic name for voxel data
                'max_value': float(np.max(data)),
                'min_value': float(np.min(data)),
                'percentile_95': percentile_values[0] if len(percentile_values) > 0 else 0.0,
                'percentile_99': percentile_values[1] if len(percentile_values) > 1 else 0.0,
                'percentile_99_9': percentile_values[2] if len(percentile_values) > 2 else 0.0,
                'focality_50': focality_values[0] if len(focality_values) > 0 else 0.0,
                'focality_75': focality_values[1] if len(focality_values) > 1 else 0.0,
                'focality_90': focality_values[2] if len(focality_values) > 2 else 0.0,
                'focality_95': focality_values[3] if len(focality_values) > 3 else 0.0,
                'total_volume_cm3': float(total_volume / 1000.0),  # Convert mm³ to cm³
                'num_voxels': len(data),
                'voxel_volume_mm3': float(voxel_volume)
            }
            
            if not self.quiet:
                self.logger.info(f"Focality metrics calculated for {region_name}: 99.9%={percentile_values[2]:.4f}, focality_95={focality_values[3]:.4f} cm³")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error calculating focality metrics for {region_name}: {str(e)}")
            return None

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
                if not self.quiet:
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
            if not self.quiet:
                self.logger.info(f"Found existing labels file: {output_file}")
            if parse_labels_file():
                if not self.quiet:
                    self.logger.info(f"Successfully parsed {len(region_info)} regions from existing file")
                return region_info
            else:
                if not self.quiet:
                    self.logger.info("Existing file is invalid or empty, regenerating...")
        
        # Generate new file if needed
        if generate_labels_file():
            if parse_labels_file():
                if not self.quiet:
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

    def get_grey_matter_statistics(self):
        """
        Calculate grey matter field statistics from the NIfTI data.
        
        Returns:
            dict: Dictionary containing grey matter statistics (mean, max, min)
        """
        if not self.quiet:
            self.logger.info("Calculating grey matter field statistics...")
        
        try:
            # Load the field data
            img = nib.load(self.field_nifti)
            field_data = img.get_fdata()
            
            # Handle 4D field data (extract first volume if multiple volumes)
            if len(field_data.shape) == 4:
                if field_data.shape[3] == 1:
                    field_data = field_data[:,:,:,0]
                else:
                    field_data = field_data[:,:,:,0]
            
            # For voxel analysis, we assume the entire field is grey matter
            # (since we're typically working with grey matter NIfTI files)
            # Filter for positive values only (matching ROI analysis behavior)
            positive_mask = field_data > 0
            field_data_positive = field_data[positive_mask]
            
            # Check if we have any positive values
            if len(field_data_positive) == 0:
                self.logger.warning("No positive values found in grey matter data")
                return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
            
            # Calculate statistics on positive values only
            grey_mean = np.mean(field_data_positive)
            grey_max = np.max(field_data_positive)
            grey_min = np.min(field_data_positive)
            
            if not self.quiet:
                self.logger.info(f"Grey matter statistics for field '{os.path.basename(self.field_nifti)}' (positive values only): "
                               f"mean={grey_mean:.6f}, max={grey_max:.6f}, min={grey_min:.6f}")
            
            return {
                'grey_mean': float(grey_mean),
                'grey_max': float(grey_max),
                'grey_min': float(grey_min)
            }
            
        except Exception as e:
            self.logger.error(f"Error calculating grey matter statistics: {str(e)}")
            return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}