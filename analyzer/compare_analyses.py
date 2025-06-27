# This script compares two analysis outputs and returns the results

import os
import sys
import argparse
import pandas as pd
import nibabel as nib
import numpy as np

# Add the parent directory to the path to access utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util
from utils.logging_util import get_logger

# Initialize logger
logger = get_logger(__name__)

def _extract_project_name(file_path: str) -> str:
    """
    Extract project directory name from a file path.
    
    Looks for patterns like '/mnt/{project_name}/derivatives/...' or similar.
    
    Args:
        file_path (str): Full path to a file
        
    Returns:
        str: Project directory name, or 'unknown_project' if not found
    """
    # Normalize path separators
    normalized_path = file_path.replace('\\', '/')
    
    # Look for /mnt/{project_name}/ pattern
    mnt_separator = '/mnt/'
    if mnt_separator in normalized_path:
        parts = normalized_path.split(mnt_separator)
        if len(parts) > 1:
            remaining = parts[1].split('/')
            if len(remaining) > 0:
                return remaining[0]
    
    # Fallback: look for any directory that might be a project root
    # (e.g., contains 'derivatives' as a subdirectory)
    parts = normalized_path.split('/')
    for i, part in enumerate(parts):
        if part == 'derivatives' and i > 0:
            return parts[i-1]
    
    # Final fallback
    return 'unknown_project'

def _get_output_path(input_paths: list[str], method_name: str, 
                    filename: str, custom_suffix: str = "") -> str:
    """
    Construct centralized output path for generated files.
    
    Args:
        input_paths (list[str]): List of input file paths
        method_name (str): Name of the method generating the output (e.g., 'averaging', 'intersection')
        filename (str): Base filename or custom filename
        custom_suffix (str): Optional suffix to add before file extension
        
    Returns:
        str: Full path for output file in centralized directory
    """
    # Extract project name from first input path
    project_name = _extract_project_name(input_paths[0])
    
    # Create centralized output directory
    output_dir = os.path.join("/mnt", project_name, "derivatives", "group_analysis")
    
    # Extract subject IDs or base names from input paths for descriptive naming
    input_identifiers = []
    for path in input_paths[:5]:  # Limit to first 5 to avoid overly long names
        # Extract meaningful identifier from path
        basename = os.path.basename(path)
        # Remove common extensions
        for ext in ['.nii.gz', '.nii', '.csv']:
            if basename.endswith(ext):
                basename = basename[:-len(ext)]
                break
        
        # Extract subject ID if present (patterns like sub-XXX)
        if 'sub-' in basename:
            parts = basename.split('sub-')
            if len(parts) > 1:
                subject_part = parts[1].split('_')[0]  # Get part after sub- until next underscore
                input_identifiers.append(f"sub-{subject_part}")
            else:
                input_identifiers.append(basename[:20])  # Truncate long names
        else:
            input_identifiers.append(basename[:20])  # Truncate long names
    
    # If more than 5 inputs, add count
    if len(input_paths) > 5:
        input_identifiers.append(f"plus{len(input_paths)-5}more")
    
    # Construct descriptive filename
    if filename and not filename.startswith("group_"):
        # Parse the original filename to extract extension
        name_parts = filename.split('.')
        if len(name_parts) > 1:
            base_name = '.'.join(name_parts[:-1])
            extension = name_parts[-1]
        else:
            base_name = filename
            extension = ""
        
        # Create new descriptive name
        identifier_str = "_".join(input_identifiers)
        descriptive_name = f"group_{method_name}_{identifier_str}"
        
        if custom_suffix:
            descriptive_name += f"_{custom_suffix}"
            
        if extension:
            descriptive_name += f".{extension}"
        else:
            # Try to preserve original extension pattern
            if filename.endswith('.nii.gz'):
                descriptive_name += '.nii.gz'
            elif '.' in filename:
                descriptive_name += '.' + filename.split('.')[-1]
                
        final_filename = descriptive_name
    else:
        final_filename = filename
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    return os.path.join(output_dir, final_filename)

def collect_arguments() -> tuple[list[str], str]:
    """
    Collect absolute paths to analysis directories and output directory using command line arguments.
    
    Returns:
        tuple[list[str], str]: List of absolute paths to analysis directories and output directory path
    """
    parser = argparse.ArgumentParser(description='Compare multiple SimNIBS analysis outputs')
    parser.add_argument('-analyses', nargs='+', required=True, help='Absolute paths to analysis directories (minimum 2)')
    parser.add_argument('--output', required=True, help='Path to output directory')
    
    args = parser.parse_args()
    
    if len(args.analyses) < 2:
        parser.error("At least 2 analysis paths must be provided")
    
    # Verify all analysis paths exist
    for path in args.analyses:
        if not os.path.isdir(path):
            parser.error(f"Analysis path does not exist or is not a directory: {path}")
    
    return args.analyses, args.output

def setup_output_dir(output_path: str) -> str:
    """
    Create and setup the output directory if it doesn't exist.
    
    Args:
        output_path (str): Path to desired output directory
    
    Returns:
        str: Path to the created/existing output directory
    """
    # Create the output directory if it doesn't exist
    os.makedirs(output_path, exist_ok=True)
    return output_path

def compare_analyses(analyses: list[str], output_dir: str):
    """
    Compare multiple analyses and write their names to a file.
    Extracts mean, max, and min values from each analysis CSV and computes percent differences.
    
    Args:
        analyses (list[str]): List of absolute paths to analysis directories
        output_dir (str): Path to the output directory
    """
    # Dictionary to store results for each analysis
    analysis_results = {}
    
    # Process each analysis directory
    for analysis_path in analyses:
        # Create a unique identifier that includes more path info to avoid collisions
        # Instead of just using the last directory name, use a more descriptive identifier
        path_parts = analysis_path.split('/')
        
        # Try to find subject and montage info in the path
        subject_id = "unknown"
        montage_name = "unknown"
        analysis_name = os.path.basename(os.path.normpath(analysis_path))
        
        for i, part in enumerate(path_parts):
            if part.startswith('sub-'):
                subject_id = part
            elif 'Simulations' in path_parts and i < len(path_parts) - 1:
                # Look for the directory after 'Simulations'
                sim_idx = path_parts.index('Simulations')
                if i == sim_idx + 1:
                    montage_name = part
        
        # Create unique identifier: subject_montage_analysis
        unique_name = f"{subject_id}_{montage_name}_{analysis_name}"
        
        # Find the CSV file in the analysis directory
        csv_files = [f for f in os.listdir(analysis_path) if f.endswith('.csv')]
        if not csv_files:
            print(f"Warning: No CSV file found in {analysis_path}")
            continue
        
        csv_path = os.path.join(analysis_path, csv_files[0])
        logger.info(f"Reading CSV from: {csv_path}")
        
        # Read specific rows from the CSV
        try:
            df = pd.read_csv(csv_path, header=None)
            metrics = {
                'mean_value': float(df.iloc[1, 1]),  # Row 2, Column 2
                'max_value': float(df.iloc[2, 1]),   # Row 3, Column 2
                'min_value': float(df.iloc[3, 1]),   # Row 4, Column 2
            }
            analysis_results[unique_name] = metrics
            logger.info(f"Extracted metrics from {unique_name}: mean={metrics['mean_value']:.6f}, max={metrics['max_value']:.6f}, min={metrics['min_value']:.6f}")
        except Exception as e:
            logger.error(f"Error reading CSV for {unique_name}: {str(e)}")
            continue
    
    logger.info(f"Found {len(analysis_results)} valid analyses for comparison")
    
    # Calculate and write percent differences
    if len(analysis_results) < 2:
        logger.error("Need at least 2 valid analyses to compare")
        return
    
    # Construct centralized output path
    output_file_path = _get_output_path(analyses, 'comparison', 'comparison_results.txt')
    logger.info(f"Saving comparison results to: {output_file_path}")
    
    # Write results to file
    with open(output_file_path, 'w') as f:
        f.write("Analysis Comparison Results\n")
        f.write("=========================\n\n")
        
        # Write the analysis names
        f.write("Analyses compared:\n")
        for i, name in enumerate(analysis_results.keys(), 1):
            f.write(f"{i}. {name}\n")
        f.write("\n")
        
        # Calculate percent differences between each pair
        analysis_names = list(analysis_results.keys())
        for i in range(len(analysis_names)):
            for j in range(i + 1, len(analysis_names)):
                name1, name2 = analysis_names[i], analysis_names[j]
                results1, results2 = analysis_results[name1], analysis_results[name2]
                
                f.write(f"\nComparison between {name1} and {name2}:\n")
                f.write("-" * 40 + "\n")
                
                for metric in ['mean_value', 'max_value', 'min_value']:
                    val1, val2 = results1[metric], results2[metric]
                    # Calculate percent difference
                    avg = (val1 + val2) / 2
                    if avg != 0:
                        pct_diff = abs(val1 - val2) / avg * 100
                        f.write(f"{metric}:\n")
                        f.write(f"  {name1}: {val1:.6f}\n")
                        f.write(f"  {name2}: {val2:.6f}\n")
                        f.write(f"  Percent difference: {pct_diff:.2f}%\n\n")
                    else:
                        f.write(f"{metric}: Both values are 0\n\n")
        
        logger.info(f"Comparison results successfully written to {output_file_path}")

def average_nifti_images(nifti_paths: list[str], output_filename: str = "average_output.nii.gz") -> str:
    """
    Loads multiple NIfTI images, computes their element-wise average, and saves the result.
    
    Args:
        nifti_paths (list[str]): List of file paths to NIfTI images (.nii or .nii.gz)
        output_filename (str, optional): Name of the output file. Defaults to "average_output.nii.gz"
    
    Returns:
        str: Path to the saved averaged NIfTI file
        
    Raises:
        ValueError: If input list is empty, files don't exist, or images have mismatched shapes/affines
        FileNotFoundError: If any of the input NIfTI files don't exist
        Exception: If there are issues loading or saving NIfTI files
    """
    if not nifti_paths:
        raise ValueError("Input list of NIfTI paths cannot be empty")
    
    if len(nifti_paths) < 2:
        raise ValueError("At least 2 NIfTI files are required for averaging")
    
    # Verify all files exist
    for path in nifti_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"NIfTI file not found: {path}")
        if not (path.endswith('.nii') or path.endswith('.nii.gz')):
            raise ValueError(f"File does not appear to be a NIfTI file: {path}")
    
    logger.info(f"Loading and averaging {len(nifti_paths)} NIfTI images...")
    
    try:
        # Load the first image to get reference shape and affine
        first_img = nib.load(nifti_paths[0])
        reference_shape = first_img.shape
        reference_affine = first_img.affine
        reference_header = first_img.header
        
        logger.info(f"Reference image shape: {reference_shape}")
        
        # Initialize array to store all image data
        all_data = np.zeros((len(nifti_paths),) + reference_shape, dtype=np.float64)
        all_data[0] = first_img.get_fdata().astype(np.float64)
        
        # Load remaining images and verify compatibility
        for i, path in enumerate(nifti_paths[1:], start=1):
            img = nib.load(path)
            current_shape = img.shape
            current_affine = img.affine
            
            # Check shape compatibility
            if current_shape != reference_shape:
                raise ValueError(
                    f"Shape mismatch: {path} has shape {current_shape}, "
                    f"but reference has shape {reference_shape}"
                )
            
            # Check affine compatibility (with small tolerance for floating point differences)
            if not np.allclose(current_affine, reference_affine, atol=1e-6):
                raise ValueError(
                    f"Affine mismatch: {path} has different affine transformation than reference image"
                )
            
            # Store the image data
            all_data[i] = img.get_fdata().astype(np.float64)
        
        # Compute element-wise average
        logger.info("Computing element-wise average...")
        averaged_data = np.mean(all_data, axis=0)
        
        # Create new NIfTI image with averaged data
        averaged_img = nib.Nifti1Image(averaged_data, reference_affine, reference_header)
        
        # Construct centralized output path
        output_path = _get_output_path(nifti_paths, 'averaging', output_filename, 'avg')
        logger.info(f"Saving averaged NIfTI to: {output_path}")
        
        # Save the averaged image
        nib.save(averaged_img, output_path)
        
        logger.info(f"Successfully created averaged NIfTI image: {output_path}")
        logger.info(f"Output shape: {averaged_data.shape}, Mean value: {np.mean(averaged_data):.6f}")
        
        return output_path
        
    except Exception as e:
        raise Exception(f"Error processing NIfTI images: {str(e)}")

def intersection_high_values_nifti(nifti_paths: list[str], 
                                 min_overlap: int = None,
                                 output_filename: str = "intersection_high_values.nii.gz",
                                 fill_value: float = 0.0,
                                 percentile_low: float = 95.0,
                                 percentile_high: float = 99.9) -> str:
    """
    Computes intersection of high-value voxels across multiple NIfTI images.
    
    For each NIfTI, identifies voxels within the top percentile range (default: 95th to 99.9th percentiles).
    Creates an intersection mask where a minimum number of NIfTIs have high values, then computes
    the weighted average of those voxels across all contributing NIfTIs.
    
    Args:
        nifti_paths (list[str]): List of file paths to NIfTI images (.nii or .nii.gz)
        min_overlap (int, optional): Minimum number of NIfTIs that must have high values in a voxel
                                   for it to be included. Defaults to total number of input NIfTIs.
        output_filename (str, optional): Name of the output file. Defaults to "intersection_high_values.nii.gz"
        fill_value (float, optional): Value to fill non-intersecting voxels. Defaults to 0.0. 
                                    Use np.nan for NaN fill.
        percentile_low (float, optional): Lower percentile threshold (default: 95.0)
        percentile_high (float, optional): Upper percentile threshold (default: 99.9)
    
    Returns:
        str: Path to the saved intersection NIfTI file
        
    Raises:
        ValueError: If input list is empty, files don't exist, or images have mismatched shapes/affines
        FileNotFoundError: If any of the input NIfTI files don't exist
        Exception: If there are issues loading or saving NIfTI files
    """
    if not nifti_paths:
        raise ValueError("Input list of NIfTI paths cannot be empty")
    
    if len(nifti_paths) < 1:
        raise ValueError("At least 1 NIfTI file is required")
    
    # Set default min_overlap to require all NIfTIs
    if min_overlap is None:
        min_overlap = len(nifti_paths)
    
    if min_overlap < 1 or min_overlap > len(nifti_paths):
        raise ValueError(f"min_overlap must be between 1 and {len(nifti_paths)}, got {min_overlap}")
    
    if percentile_low >= percentile_high:
        raise ValueError(f"percentile_low ({percentile_low}) must be less than percentile_high ({percentile_high})")
    
    # Verify all files exist
    for path in nifti_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"NIfTI file not found: {path}")
        if not (path.endswith('.nii') or path.endswith('.nii.gz')):
            raise ValueError(f"File does not appear to be a NIfTI file: {path}")
    
    logger.info(f"Processing {len(nifti_paths)} NIfTI images for high-value intersection")
    logger.info(f"Percentile range: {percentile_low}%-{percentile_high}%, Min overlap: {min_overlap}/{len(nifti_paths)}")
    
    try:
        # Load the first image to get reference shape and affine
        first_img = nib.load(nifti_paths[0])
        reference_shape = first_img.shape
        reference_affine = first_img.affine
        reference_header = first_img.header
        
        logger.info(f"Reference image shape: {reference_shape}")
        
        # Initialize arrays for processing
        high_value_masks = np.zeros((len(nifti_paths),) + reference_shape, dtype=bool)
        all_data = np.zeros((len(nifti_paths),) + reference_shape, dtype=np.float64)
        
        # Process each NIfTI image
        for i, path in enumerate(nifti_paths):
            img = nib.load(path)
            current_shape = img.shape
            current_affine = img.affine
            
            # Check shape compatibility
            if current_shape != reference_shape:
                raise ValueError(
                    f"Shape mismatch: {path} has shape {current_shape}, "
                    f"but reference has shape {reference_shape}"
                )
            
            # Check affine compatibility (with small tolerance for floating point differences)
            if not np.allclose(current_affine, reference_affine, atol=1e-6):
                raise ValueError(
                    f"Affine mismatch: {path} has different affine transformation than reference image"
                )
            
            # Get image data
            data = img.get_fdata().astype(np.float64)
            all_data[i] = data
            
            # Compute percentiles for this image
            # Only compute percentiles on non-zero, finite values
            finite_nonzero_mask = np.isfinite(data) & (data != 0)
            if np.any(finite_nonzero_mask):
                finite_nonzero_values = data[finite_nonzero_mask]
                p_low = np.percentile(finite_nonzero_values, percentile_low)
                p_high = np.percentile(finite_nonzero_values, percentile_high)
                
                # Create mask for high-value voxels (between percentile_low and percentile_high)
                high_value_masks[i] = (data >= p_low) & (data <= p_high) & finite_nonzero_mask
                num_high_voxels = np.sum(high_value_masks[i])
                logger.debug(f"Image {i+1}: percentiles {p_low:.6f}-{p_high:.6f}, high-value voxels: {num_high_voxels}")
            else:
                logger.warning(f"No finite non-zero values found in {os.path.basename(path)}")
                high_value_masks[i] = np.zeros(reference_shape, dtype=bool)
        
        # Compute intersection mask based on min_overlap
        logger.info("Computing intersection mask...")
        overlap_count = np.sum(high_value_masks, axis=0)  # Count how many images have high values at each voxel
        intersection_mask = overlap_count >= min_overlap
        
        num_intersection_voxels = np.sum(intersection_mask)
        intersection_percent = num_intersection_voxels/np.prod(reference_shape)*100
        logger.info(f"Intersection voxels: {num_intersection_voxels} ({intersection_percent:.2f}%)")
        
        if num_intersection_voxels == 0:
            logger.warning("No voxels meet intersection criteria - output will be filled with fill_value")
        
        # Create output array
        output_data = np.full(reference_shape, fill_value, dtype=np.float64)
        
        if num_intersection_voxels > 0:
            # For intersection voxels, compute weighted average across contributing images
            logger.info("Computing weighted averages for intersection voxels...")
            
            # Create a mask for where we need to compute averages
            intersection_indices = np.where(intersection_mask)
            
            # For each intersection voxel, compute the average
            for i in range(len(intersection_indices[0])):
                # Get the spatial coordinates for this intersection voxel
                if len(reference_shape) == 3:
                    spatial_idx = (intersection_indices[0][i], intersection_indices[1][i], intersection_indices[2][i])
                elif len(reference_shape) == 4:
                    spatial_idx = (intersection_indices[0][i], intersection_indices[1][i], intersection_indices[2][i], intersection_indices[3][i])
                else:
                    raise ValueError(f"Unsupported image dimensionality: {len(reference_shape)}D. Only 3D and 4D images are supported.")
                
                # Get which images have high values at this voxel
                contributing_mask = high_value_masks[(slice(None),) + spatial_idx]
                
                if np.any(contributing_mask):
                    # Get the values from contributing images at this voxel
                    contributing_values = all_data[(contributing_mask,) + spatial_idx]
                    # Compute the average and store it
                    output_data[spatial_idx] = np.mean(contributing_values)
        
        # Create new NIfTI image with intersection data
        intersection_img = nib.Nifti1Image(output_data, reference_affine, reference_header)
        
        # Construct centralized output path with descriptive suffix
        suffix = f"overlap{percentile_low}-{percentile_high}pct_min{min_overlap}"
        output_path = _get_output_path(nifti_paths, 'intersection', output_filename, suffix)
        logger.info(f"Saving intersection NIfTI to: {output_path}")
        
        # Save the intersection image
        nib.save(intersection_img, output_path)
        
        # Summary statistics
        if num_intersection_voxels > 0:
            valid_values = output_data[intersection_mask]
            value_range = f"{np.min(valid_values):.6f} to {np.max(valid_values):.6f}"
            mean_value = np.mean(valid_values)
            logger.info(f"Successfully created intersection NIfTI: {output_path}")
            logger.info(f"Intersection statistics - voxels: {num_intersection_voxels}, range: {value_range}, mean: {mean_value:.6f}")
        else:
            logger.info(f"Created intersection NIfTI filled with {fill_value}: {output_path}")
        
        return output_path
        
    except Exception as e:
        raise Exception(f"Error processing NIfTI intersection: {str(e)}")

def run_all_group_comparisons(analysis_dirs: list[str], project_name: str = None) -> str:
    """
    Run all available comparison methods on a list of analysis directories.
    
    This is the main orchestration function called by group_analyzer.py to perform
    comprehensive group-level comparisons using all available methods.
    
    Args:
        analysis_dirs (list[str]): List of paths to individual subject analysis directories
        project_name (str, optional): Project name for output directory. If None, extracted from first path.
        
    Returns:
        str: Path to the group analysis output directory containing all results
    """
    if not analysis_dirs:
        logger.error("No analysis directories provided for group comparison")
        return ""
    
    if len(analysis_dirs) < 2:
        logger.warning(f"Only {len(analysis_dirs)} analysis directory provided. Some comparisons require multiple subjects.")
    
    # Extract project name if not provided
    if project_name is None:
        project_name = _extract_project_name(analysis_dirs[0])
    
    # Create centralized group analysis directory
    group_output_dir = os.path.join("/mnt", project_name, "derivatives", "group_analysis")
    os.makedirs(group_output_dir, exist_ok=True)
    
    logger.info(f"Starting comprehensive group analysis for {len(analysis_dirs)} subjects")
    logger.info(f"Group output directory: {group_output_dir}")
    
    # 1. Run traditional CSV-based comparison analysis
    if len(analysis_dirs) >= 2:
        logger.info("Running CSV-based statistical comparison...")
        try:
            csv_output_dir = os.path.join(group_output_dir, "statistical_comparison")
            os.makedirs(csv_output_dir, exist_ok=True)
            compare_analyses(analysis_dirs, csv_output_dir)
        except Exception as e:
            logger.error(f"CSV comparison failed: {e}")
    
    # 2. Collect standardized grey matter MNI NIfTI files for image-based comparisons
    nifti_files = []
    subject_ids = []
    
    for analysis_dir in analysis_dirs:
        # Extract subject ID and montage from analysis directory path
        # Expected path pattern: .../sub-{subject_id}/Simulations/{montage_name}/Analyses/...
        path_parts = analysis_dir.split(os.sep)
        
        subject_id = None
        montage_name = None
        
        # Find subject ID (sub-XXX pattern)
        for i, part in enumerate(path_parts):
            if part.startswith('sub-'):
                subject_id = part
                # Look for Simulations directory and get montage name
                if i + 2 < len(path_parts) and path_parts[i + 1] == 'Simulations':
                    montage_name = path_parts[i + 2]
                break
        
        if not subject_id or not montage_name:
            logger.warning(f"Could not extract subject ID or montage from path: {analysis_dir}")
            continue
        
        # Construct path to the standardized grey matter MNI NIfTI file
        # Format: projectdir/derivatives/SimNIBS/sub-{subject_id}/Simulations/{montage_name}/TI/niftis/grey_{subject_short}_TI_MNI_MNI_TI_max.nii.gz
        subject_short = subject_id.replace('sub-', '')  # Remove 'sub-' prefix
        nifti_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                subject_id, "Simulations", montage_name, "TI", "niftis")
        
        if not os.path.exists(nifti_dir):
            logger.warning(f"NIfTI directory not found: {nifti_dir}")
            continue
        
        # Look for the standardized grey matter MNI file
        # Actual pattern: grey_{subject_short}_{montage_name}_TI_MNI_MNI_TI_max.nii.gz
        # Note: The montage name in the file is the actual montage name, and MNI appears twice
        target_pattern = f"grey_{subject_short}_{montage_name}_TI_MNI_MNI_TI_max"
        matching_files = []
        
        for file in os.listdir(nifti_dir):
            if file.startswith(target_pattern) and file.endswith(('.nii', '.nii.gz')):
                matching_files.append(file)
        
        if matching_files:
            # Use the first matching file (they should be equivalent)
            nifti_filename = matching_files[0]
            nifti_path = os.path.join(nifti_dir, nifti_filename)
            nifti_files.append(nifti_path)
            subject_ids.append(subject_id)
            logger.info(f"Found standardized NIfTI for {subject_id}: {nifti_filename}")
        else:
            logger.warning(f"No standardized grey matter MNI NIfTI found for {subject_id} in {nifti_dir}")
            logger.warning(f"Expected pattern: {target_pattern}*.nii*")
    
    logger.info(f"Found {len(nifti_files)} standardized grey matter MNI NIfTI files for image-based analysis")
    
    # 3. Run NIfTI averaging if multiple files found
    if len(nifti_files) >= 2:
        logger.info("Running NIfTI averaging analysis...")
        try:
            avg_output_dir = os.path.join(group_output_dir, "averaged_images")
            os.makedirs(avg_output_dir, exist_ok=True)
            
            # Temporarily override the output path logic for organized output
            original_get_output_path = globals()['_get_output_path']
            
            def _organized_output_path(input_paths, method_name, filename, custom_suffix=""):
                # Create filename in the avg_output_dir
                subject_str = "_".join(subject_ids[:5])  # Use collected subject IDs
                if len(subject_ids) > 5:
                    subject_str += f"_plus{len(subject_ids)-5}more"
                
                final_filename = f"group_{method_name}_{subject_str}"
                if custom_suffix:
                    final_filename += f"_{custom_suffix}"
                
                # Preserve original extension
                if filename.endswith('.nii.gz'):
                    final_filename += '.nii.gz'
                elif filename.endswith('.nii'):
                    final_filename += '.nii'
                elif '.' in filename:
                    final_filename += '.' + filename.split('.')[-1]
                
                return os.path.join(avg_output_dir, final_filename)
            
            # Temporarily replace the function
            globals()['_get_output_path'] = _organized_output_path
            
            avg_output = average_nifti_images(nifti_files, "averaged_field.nii.gz")
            logger.info(f"Average NIfTI saved to: {avg_output}")
            
            # Restore original function
            globals()['_get_output_path'] = original_get_output_path
            
        except Exception as e:
            logger.error(f"NIfTI averaging failed: {e}")
    
    # 4. Run high-value intersection analysis if multiple files found
    if len(nifti_files) >= 2:
        logger.info("Running high-value intersection analysis...")
        try:
            intersection_output_dir = os.path.join(group_output_dir, "intersection_analysis")
            os.makedirs(intersection_output_dir, exist_ok=True)
            
            # Temporarily override the output path logic for organized output
            def _organized_intersection_path(input_paths, method_name, filename, custom_suffix=""):
                # Create filename in the intersection_output_dir
                subject_str = "_".join(subject_ids[:5])  # Use collected subject IDs
                if len(subject_ids) > 5:
                    subject_str += f"_plus{len(subject_ids)-5}more"
                
                final_filename = f"group_{method_name}_{subject_str}"
                if custom_suffix:
                    final_filename += f"_{custom_suffix}"
                
                # Preserve original extension
                if filename.endswith('.nii.gz'):
                    final_filename += '.nii.gz'
                elif filename.endswith('.nii'):
                    final_filename += '.nii'
                elif '.' in filename:
                    final_filename += '.' + filename.split('.')[-1]
                
                return os.path.join(intersection_output_dir, final_filename)
            
            # Temporarily replace the function
            original_get_output_path = globals()['_get_output_path']
            globals()['_get_output_path'] = _organized_intersection_path
            
            # Run intersection with all subjects required (strictest)
            intersection_all = intersection_high_values_nifti(
                nifti_files, 
                min_overlap=len(nifti_files),
                output_filename="intersection_all_subjects.nii.gz",
                percentile_low=95.0,
                percentile_high=99.9
            )
            logger.info(f"Strict intersection (all subjects) saved to: {intersection_all}")
            
            # Run intersection with 50% overlap requirement if more than 2 subjects
            if len(nifti_files) > 2:
                min_overlap = max(2, len(nifti_files) // 2)
                intersection_partial = intersection_high_values_nifti(
                    nifti_files,
                    min_overlap=min_overlap,
                    output_filename="intersection_partial_overlap.nii.gz",
                    percentile_low=95.0,
                    percentile_high=99.9
                )
                logger.info(f"Partial intersection ({min_overlap}/{len(nifti_files)} subjects) saved to: {intersection_partial}")
            
            # Restore original function
            globals()['_get_output_path'] = original_get_output_path
            
        except Exception as e:
            logger.error(f"Intersection analysis failed: {e}")
    
    # 5. Create summary report
    summary_file = os.path.join(group_output_dir, "group_analysis_summary.txt")
    logger.info(f"Creating group analysis summary: {summary_file}")
    
    with open(summary_file, 'w') as f:
        f.write("Group Analysis Summary\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Analysis Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Project: {project_name}\n")
        f.write(f"Total Subjects: {len(analysis_dirs)}\n")
        f.write(f"Standardized NIfTI Files Found: {len(nifti_files)}\n\n")
        
        f.write("Subject Analysis Directories:\n")
        for i, analysis_dir in enumerate(analysis_dirs, 1):
            f.write(f"  {i}. {analysis_dir}\n")
        f.write("\n")
        
        f.write("Standardized Grey Matter MNI NIfTI Files Used:\n")
        for i, nifti_path in enumerate(nifti_files, 1):
            f.write(f"  {i}. {nifti_path}\n")
        f.write("\n")
        
        f.write("Analyses Performed:\n")
        if len(analysis_dirs) >= 2:
            f.write("  ✓ Statistical comparison (CSV-based)\n")
        if len(nifti_files) >= 2:
            f.write("  ✓ NIfTI averaging (using standardized grey matter MNI files)\n")
            f.write("  ✓ High-value intersection analysis (using standardized grey matter MNI files)\n")
        
        f.write("\nOutput Organization:\n")
        f.write(f"  Main directory: {group_output_dir}\n")
        f.write("  ├── statistical_comparison/     # CSV-based statistical analysis\n")
        f.write("  ├── averaged_images/           # Group-averaged NIfTI images\n")
        f.write("  ├── intersection_analysis/     # High-value intersection maps\n")
        f.write("  └── group_analysis_summary.txt # This summary file\n")
    
    logger.info(f"Group analysis complete. All results saved to: {group_output_dir}")
    return group_output_dir

if __name__ == "__main__":
    analyses, output_path = collect_arguments()
    output_dir = setup_output_dir(output_path)
    compare_analyses(analyses, output_dir)