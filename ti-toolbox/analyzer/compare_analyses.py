# This script compares two analysis outputs and returns the results

import os
import sys
import argparse
import pandas as pd
import nibabel as nib
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import logging
from pathlib import Path
import json
import re
from typing import List, Tuple

# Add the parent directory to the path to access utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools import logging_util
from tools.logging_util import get_logger

# Initialize centralized group analysis logger (will be configured in setup_group_logger)
group_logger = None

def setup_group_logger(project_name: str) -> logging.Logger:
    """
    Set up centralized group analysis logging with timestamped log files.
    
    Args:
        project_name (str): Project name to determine log file location
        
    Returns:
        logging.Logger: Configured group analysis logger
    """
    global group_logger
    
    if group_logger is not None:
        return group_logger
    
    # Create timestamped log directory
    log_dir = os.path.join("/mnt", project_name, "derivatives", "ti-toolbox", "logs", "group_analysis")
    os.makedirs(log_dir, exist_ok=True)
    
    # Create timestamped group analysis log file
    timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"group_analysis_{timestamp}.log")
    
    # Use logging_util to create the logger
    group_logger = logging_util.get_logger("group_analysis", log_file, overwrite=False)
    
    # Add a separator for new runs
    group_logger.info("=" * 80)
    group_logger.info(f"NEW GROUP ANALYSIS SESSION STARTED")
    group_logger.info(f"Timestamp: {timestamp}")
    group_logger.info("=" * 80)
    
    return group_logger

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

def _extract_montage_and_region_info(analysis_dirs: List[str]) -> Tuple[str, str]:
    """
    Extract montage name and region information from analysis directory paths.
    
    Expected path structure:
    .../derivatives/SimNIBS/sub-XXX/Simulations/{montage}/Analyses/{Mesh|Voxel}/{analysis_type}/
    
    Args:
        analysis_dirs (List[str]): List of analysis directory paths
        
    Returns:
        Tuple[str, str]: (montage_name, region_name)
    """
    if not analysis_dirs:
        return "unknown_montage", "unknown_region"
    
    # Use the first analysis directory to extract common montage and region info
    first_path = analysis_dirs[0]
    path_parts = first_path.replace('\\', '/').split('/')
    
    montage_name = "unknown_montage"
    region_name = "unknown_region"
    
    try:
        if group_logger:
            group_logger.debug(f"Extracting montage/region from path: {first_path}")
            group_logger.debug(f"Path parts: {path_parts}")
        
        # Find 'Simulations' in path and extract montage name
        if 'Simulations' in path_parts:
            sim_idx = path_parts.index('Simulations')
            if sim_idx + 1 < len(path_parts):
                montage_name = path_parts[sim_idx + 1]
                if group_logger:
                    group_logger.debug(f"Found montage: {montage_name}")
        
        # Extract region name from the analysis directory name (last part of path)
        analysis_dir_name = os.path.basename(first_path.rstrip('/\\'))
        if group_logger:
            group_logger.debug(f"Analysis directory name: {analysis_dir_name}")
        
        # Parse common analysis directory name patterns
        if analysis_dir_name.startswith('sphere_'):
            # For spherical analysis: sphere_x{X}_y{Y}_z{Z}_r{R}_{MNI|subject}
            # Extract coordinates, radius, and coordinate space for a complete name
            parts = analysis_dir_name.split('_')
            if len(parts) >= 4:
                # Extract x, y, z, r values and coordinate space
                coords = []
                radius = ""
                coord_space = ""
                for part in parts[1:]:
                    if part.startswith('x'):
                        coords.append(part)
                    elif part.startswith('y'):
                        coords.append(part)
                    elif part.startswith('z'):
                        coords.append(part)
                    elif part.startswith('r') and not radius:
                        radius = part
                    elif part in ['MNI', 'subject']:
                        coord_space = part
                        break
                # Build region name with coordinate space if available
                base_name = f"sphere_{'_'.join(coords)}_{radius}" if coords and radius else analysis_dir_name
                region_name = f"{base_name}_{coord_space}" if coord_space else base_name
            else:
                region_name = analysis_dir_name
        elif analysis_dir_name.startswith('region_'):
            # For cortical region analysis: region_{region_name}
            region_name = analysis_dir_name.replace('region_', '')
        elif analysis_dir_name.startswith('whole_head_'):
            # For whole head analysis: whole_head_{atlas_info}
            atlas_info = analysis_dir_name.replace('whole_head_', '')
            region_name = f"{atlas_info}_wholehead"
        else:
            # Fallback: use the analysis directory name as region
            region_name = analysis_dir_name
        
        # Clean up names - remove problematic characters
        region_name = region_name.replace('/', '_').replace('\\', '_').replace(' ', '_')
        montage_name = montage_name.replace('/', '_').replace('\\', '_').replace(' ', '_')
        
        # Keep full names as requested - no length limiting
        
        if group_logger:
            group_logger.debug(f"Final montage: {montage_name}, region: {region_name}")
        
    except Exception as e:
        if group_logger:
            group_logger.warning(f"Error extracting montage/region info from {first_path}: {e}")
            group_logger.warning(f"Using fallback names")
    
    return montage_name, region_name

def _get_run_specific_output_dir(input_paths: List[str]) -> str:
    """
    Create run-specific output directory using montage and region information.
    
    Args:
        input_paths (List[str]): List of input analysis paths
        
    Returns:
        str: Path to run-specific output directory
    """
    # Extract project name
    project_name = _extract_project_name(input_paths[0])
    
    # Extract montage and region information
    montage_name, region_name = _extract_montage_and_region_info(input_paths)
    
    # Create run-specific folder name
    run_folder_name = f"{montage_name}_{region_name}"
    
    # Create full output directory path under derivatives/SimNIBS/group_analysis
    output_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", "group_analysis", run_folder_name)
    os.makedirs(output_dir, exist_ok=True)
    
    if group_logger:
        group_logger.info(f"Created run-specific output directory: {output_dir}")
        group_logger.info(f"Montage: {montage_name}, Region: {region_name}")
    
    return output_dir

def _get_output_path(input_paths: List[str], method_name: str, 
                    filename: str, custom_suffix: str = "") -> str:
    """
    Construct output path for generated files in the run-specific directory.
    
    Args:
        input_paths (List[str]): List of input file paths
        method_name (str): Name of the method generating the output (e.g., 'averaging', 'intersection')
        filename (str): Base filename or custom filename
        custom_suffix (str): Optional suffix to add before file extension
        
    Returns:
        str: Full path for output file in run-specific directory
    """
    # Get run-specific output directory
    output_dir = _get_run_specific_output_dir(input_paths)
    
    # Get montage and region info for simpler naming
    montage_name, region_name = _extract_montage_and_region_info(input_paths)
    
    # Extract subject count for naming
    subject_count = len(input_paths)
    
    # Determine file extension
    extension = ""
    if filename.endswith('.nii.gz'):
        extension = '.nii.gz'
        base_filename = filename[:-7]  # Remove .nii.gz
    elif filename.endswith('.nii'):
        extension = '.nii'
        base_filename = filename[:-4]  # Remove .nii
    elif filename.endswith('.csv'):
        extension = '.csv'
        base_filename = filename[:-4]  # Remove .csv
    elif filename.endswith('.png'):
        extension = '.png'
        base_filename = filename[:-4]  # Remove .png
    else:
        # Try to extract extension
        name_parts = filename.split('.')
        if len(name_parts) > 1:
            extension = '.' + name_parts[-1]
            base_filename = '.'.join(name_parts[:-1])
        else:
            base_filename = filename
    
    # Create simplified descriptive name
    if not filename.startswith("group_"):
        # Build a cleaner, shorter filename
        if subject_count == 1:
            descriptive_name = f"group_{method_name}_{montage_name}_{region_name}"
        else:
            descriptive_name = f"group_{method_name}_{montage_name}_{region_name}_{subject_count}subj"
        
        if custom_suffix:
            descriptive_name += f"_{custom_suffix}"
            
        final_filename = descriptive_name + extension
    else:
        final_filename = filename
    
    # Clean up filename - remove problematic characters and limit length
    final_filename = final_filename.replace(' ', '_').replace('/', '_').replace('\\', '_')
    
    # Limit total filename length
    name_without_ext = final_filename
    if extension and final_filename.endswith(extension):
        name_without_ext = final_filename[:-len(extension)]
    
    if len(name_without_ext) > 100:  # Limit base name to 100 chars
        name_without_ext = name_without_ext[:97] + "..."
        final_filename = name_without_ext + extension
    
    output_path = os.path.join(output_dir, final_filename)
    
    if group_logger:
        group_logger.debug(f"Generated output path: {output_path}")
    
    return output_path

def _load_subject_data(analyses: List[str]) -> dict:
    """
    Load CSV data from each analysis directory and extract subject information.
    
    Args:
        analyses (List[str]): List of absolute paths to analysis directories
        
    Returns:
        dict: Dictionary with subject identifiers as keys and analysis data as values
              Each value contains: subject_id, montage_name, analysis_name, metrics dict
    """
    group_logger.info(f"Loading data from {len(analyses)} analysis directories...")
    analysis_results = {}
    
    for analysis_path in analyses:
        try:
            # Parse path to extract subject and montage info
            path_parts = analysis_path.split('/')
            
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
                group_logger.warning(f"No CSV file found in {analysis_path}")
                continue
            
            csv_path = os.path.join(analysis_path, csv_files[0])
            group_logger.debug(f"Reading CSV from: {csv_path}")
            
            # Read CSV with headers to handle both old and new formats
            df = pd.read_csv(csv_path)
            
            # Create a dictionary from the CSV for flexible field access
            csv_data = {}
            for _, row in df.iterrows():
                csv_data[row['Metric']] = row['Value']
            
            # Extract TI_max fields (always present)
            metrics = {
                'mean_value': float(csv_data.get('mean_value', 0)),
                'max_value': float(csv_data.get('max_value', 0)),
                'min_value': float(csv_data.get('min_value', 0)),
                'focality': float(csv_data.get('focality', 0)),
            }
            
            # Extract TI_normal fields (if available)
            if 'normal_mean_value' in csv_data:
                metrics.update({
                    'normal_mean_value': float(csv_data.get('normal_mean_value', 0)),
                    'normal_max_value': float(csv_data.get('normal_max_value', 0)),
                    'normal_min_value': float(csv_data.get('normal_min_value', 0)),
                    'normal_focality': float(csv_data.get('normal_focality', 0)),
                })
                group_logger.debug(f"TI_normal fields found for {unique_name}")
            else:
                group_logger.debug(f"TI_normal fields not available for {unique_name} (legacy format)")
            
            # Try to find the field file path used during analysis
            field_path = _find_field_path_from_analysis(analysis_path, subject_id, montage_name)
            
            # Get grey matter statistics by reconstructing the analyzer
            # Note: This is optional and will return 0.0 values if the analyzers can't be imported
            # due to module path issues. The CSV will still be generated with the basic ROI statistics.
            grey_stats = _get_grey_matter_statistics(analysis_path, subject_id, montage_name, field_path)
            metrics.update(grey_stats)
            
            analysis_results[unique_name] = {
                'subject_id': subject_id,
                'montage_name': montage_name,
                'analysis_name': analysis_name,
                'analysis_path': analysis_path,
                'csv_path': csv_path,
                'metrics': metrics
            }
            
            group_logger.debug(f"Loaded data for {unique_name}: mean={metrics['mean_value']:.6f}, "
                        f"max={metrics['max_value']:.6f}, min={metrics['min_value']:.6f}")
            
        except Exception as e:
            group_logger.error(f"Error loading data from {analysis_path}: {str(e)}")
            continue
    
    group_logger.debug(f"Successfully loaded data from {len(analysis_results)} analyses")
    return analysis_results

def _find_field_path_from_analysis(analysis_path: str, subject_id: str, montage_name: str) -> str:
    """
    Try to find the field file path used during analysis by looking for log files or configuration files.
    
    Args:
        analysis_path (str): Path to the analysis directory
        subject_id (str): Subject ID
        montage_name (str): Montage name
        
    Returns:
        str: Path to the field file if found, None otherwise
    """
    try:
        # Look for log files that might contain field path information
        log_files = [f for f in os.listdir(analysis_path) if f.endswith('.log')]
        
        for log_file in log_files:
            log_path = os.path.join(analysis_path, log_file)
            try:
                with open(log_path, 'r') as f:
                    content = f.read()
                    
                    # Look for field path patterns in the log
                    # Common patterns: --field_path, field_mesh_path, field_nifti
                    import re
                    
                    # Pattern for field path arguments - prioritize TI mesh files for TI_max field
                    field_patterns = [
                        r'--field_path\s+([^\s]+)',
                        r'field_mesh_path[=:]\s*([^\s\n]*_TI\.msh)',  # Prioritize TI mesh files
                        r'field_mesh_path[=:]\s*([^\s\n]+)',          # Fallback to any mesh file
                        r'field_nifti[=:]\s*([^\s\n]+)',
                        r'field_file[=:]\s*([^\s\n]+)'
                    ]
                    
                    for pattern in field_patterns:
                        match = re.search(pattern, content)
                        if match:
                            field_path = match.group(1).strip()
                            # Clean up the path (remove quotes, etc.)
                            field_path = field_path.strip('"\'')
                            
                            # Verify the file exists
                            if os.path.exists(field_path):
                                group_logger.debug(f"Found field path in {log_file}: {field_path}")
                                return field_path
                            
            except Exception as e:
                group_logger.debug(f"Error reading log file {log_file}: {str(e)}")
                continue
        
        # If no field path found in logs, try to construct it from the analysis path
        # This is a fallback method
        project_name = _extract_project_name(analysis_path)
        path_parts = analysis_path.split('/')
        space_type = "unknown"
        
        # Look for Mesh or Voxel in the path
        for part in path_parts:
            if part == 'Mesh':
                space_type = 'mesh'
                break
            elif part == 'Voxel':
                space_type = 'voxel'
                break
        
        if space_type == 'mesh':
            # For mesh analysis, construct the expected field path
            # Check for mTI simulation first
            mti_field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                         subject_id, "Simulations", montage_name, "mTI", "mesh")
            ti_field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                        subject_id, "Simulations", montage_name, "TI", "mesh")
            
            if os.path.exists(mti_field_dir):
                field_dir = mti_field_dir
                is_mti = True
            else:
                field_dir = ti_field_dir
                is_mti = False
            if os.path.exists(field_dir):
                msh_files = [f for f in os.listdir(field_dir) if f.endswith('.msh') and not f.endswith('.msh.opt')]
                
                # Look for TI/mTI mesh files first (contains TI_max field)
                if is_mti:
                    # For mTI simulations, look for _mTI.msh files
                    ti_files = [f for f in msh_files if '_mTI.msh' in f]
                else:
                    # For regular TI simulations, look for _TI.msh files
                    ti_files = [f for f in msh_files if '_TI.msh' in f]
                
                if ti_files:
                    field_path = os.path.join(field_dir, ti_files[0])
                    group_logger.debug(f"Constructed mesh field path (TI): {field_path}")
                    return field_path
                elif msh_files:
                    # Fallback to any .msh file
                    field_path = os.path.join(field_dir, msh_files[0])
                    group_logger.debug(f"Constructed mesh field path (fallback): {field_path}")
                    return field_path
        elif space_type == 'voxel':
            # For voxel analysis, construct the expected field path
            # Check for mTI simulation first
            mti_field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                         subject_id, "Simulations", montage_name, "mTI", "niftis")
            ti_field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                        subject_id, "Simulations", montage_name, "TI", "niftis")
            
            if os.path.exists(mti_field_dir):
                field_dir = mti_field_dir
                is_mti = True
            else:
                field_dir = ti_field_dir
                is_mti = False
            if os.path.exists(field_dir):
                grey_files = [f for f in os.listdir(field_dir) if f.startswith('grey_') and f.endswith(('.nii', '.nii.gz'))]
                if grey_files:
                    field_path = os.path.join(field_dir, grey_files[0])
                    group_logger.debug(f"Constructed voxel field path: {field_path}")
                    return field_path
        
        group_logger.warning(f"Could not find field path for {analysis_path}")
        return None
        
    except Exception as e:
        group_logger.warning(f"Error finding field path for {analysis_path}: {str(e)}")
        return None

def _get_grey_matter_statistics(analysis_path: str, subject_id: str, montage_name: str, field_path: str = None) -> dict:
    """
    Get grey matter statistics by reconstructing the analyzer and calling the appropriate method.
    
    Args:
        analysis_path (str): Path to the analysis directory
        subject_id (str): Subject ID
        montage_name (str): Montage name
        field_path (str, optional): Path to the field file used during analysis
        
    Returns:
        dict: Dictionary with grey matter statistics
    """
    try:
        # Extract project name from analysis path
        project_name = _extract_project_name(analysis_path)
        
        # Determine if this is mesh or voxel analysis based on the analysis path
        path_parts = analysis_path.split('/')
        space_type = "unknown"
        
        # Look for Mesh or Voxel in the path
        for part in path_parts:
            if part == 'Mesh':
                space_type = 'mesh'
                break
            elif part == 'Voxel':
                space_type = 'voxel'
                break
        
        if space_type == 'unknown':
            group_logger.warning(f"Could not determine space type for {analysis_path}")
            return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
        
        # Construct paths to find the field file and subject directory
        subject_short = subject_id.replace('sub-', '')
        
        if space_type == 'mesh':
            # For mesh analysis, use the provided field path or look for .msh files
            if field_path and os.path.exists(field_path):
                # Use the provided field path
                subject_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                         subject_id, f"m2m_{subject_short}")
                
                # Try to import and create mesh analyzer
                try:
                    # Add the analyzer directory to the path
                    analyzer_dir = os.path.dirname(os.path.abspath(__file__))
                    if analyzer_dir not in sys.path:
                        sys.path.insert(0, analyzer_dir)
                    
                    from mesh_analyzer import MeshAnalyzer
                    analyzer = MeshAnalyzer(
                        field_mesh_path=field_path,
                        field_name='TI_max',  # Default field name
                        subject_dir=subject_dir,
                        output_dir=analysis_path,
                        logger=group_logger
                    )
                    
                    return analyzer.get_grey_matter_statistics()
                except ImportError as e:
                    group_logger.warning(f"Could not import mesh_analyzer for {analysis_path}: {str(e)}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
            else:
                # Fallback: look for .msh files in the directory
                field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                       subject_id, "Simulations", montage_name, "TI", "mesh")
                if not os.path.exists(field_dir):
                    group_logger.warning(f"Mesh field directory not found: {field_dir}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
                
                # Find .msh files
                msh_files = [f for f in os.listdir(field_dir) if f.endswith('.msh') and not f.endswith('.msh.opt')]
                if not msh_files:
                    group_logger.warning(f"No .msh files found in {field_dir}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
                
                field_path = os.path.join(field_dir, msh_files[0])
                subject_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                         subject_id, f"m2m_{subject_short}")
                
                # Try to import and create mesh analyzer
                try:
                    # Add the analyzer directory to the path
                    analyzer_dir = os.path.dirname(os.path.abspath(__file__))
                    if analyzer_dir not in sys.path:
                        sys.path.insert(0, analyzer_dir)
                    
                    from mesh_analyzer import MeshAnalyzer
                    analyzer = MeshAnalyzer(
                        field_mesh_path=field_path,
                        field_name='TI_max',  # Default field name
                        subject_dir=subject_dir,
                        output_dir=analysis_path,
                        logger=group_logger
                    )
                    
                    return analyzer.get_grey_matter_statistics()
                except ImportError as e:
                    group_logger.warning(f"Could not import mesh_analyzer for {analysis_path}: {str(e)}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
            
        else:  # voxel
            # For voxel analysis, use the provided field path or look for grey matter NIfTI files
            if field_path and os.path.exists(field_path):
                # Use the provided field path
                subject_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                         subject_id, f"m2m_{subject_short}")
                
                # Try to import and create voxel analyzer
                try:
                    # Add the analyzer directory to the path
                    analyzer_dir = os.path.dirname(os.path.abspath(__file__))
                    if analyzer_dir not in sys.path:
                        sys.path.insert(0, analyzer_dir)
                    
                    from voxel_analyzer import VoxelAnalyzer
                    analyzer = VoxelAnalyzer(
                        field_nifti=field_path,
                        subject_dir=subject_dir,
                        output_dir=analysis_path,
                        logger=group_logger
                    )
                    
                    return analyzer.get_grey_matter_statistics()
                except ImportError as e:
                    group_logger.warning(f"Could not import voxel_analyzer for {analysis_path}: {str(e)}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
            else:
                # Fallback: look for grey matter NIfTI files in the directory
                field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                       subject_id, "Simulations", montage_name, "TI", "niftis")
                if not os.path.exists(field_dir):
                    group_logger.warning(f"Voxel field directory not found: {field_dir}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
                
                # Find grey matter NIfTI files
                grey_files = [f for f in os.listdir(field_dir) if f.startswith('grey_') and f.endswith(('.nii', '.nii.gz'))]
                if not grey_files:
                    group_logger.warning(f"No grey matter NIfTI files found in {field_dir}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
                
                field_path = os.path.join(field_dir, grey_files[0])
                subject_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                         subject_id, f"m2m_{subject_short}")
                
                # Try to import and create voxel analyzer
                try:
                    # Add the analyzer directory to the path
                    analyzer_dir = os.path.dirname(os.path.abspath(__file__))
                    if analyzer_dir not in sys.path:
                        sys.path.insert(0, analyzer_dir)
                    
                    from voxel_analyzer import VoxelAnalyzer
                    analyzer = VoxelAnalyzer(
                        field_nifti=field_path,
                        subject_dir=subject_dir,
                        output_dir=analysis_path,
                        logger=group_logger
                    )
                    
                    return analyzer.get_grey_matter_statistics()
                except ImportError as e:
                    group_logger.warning(f"Could not import voxel_analyzer for {analysis_path}: {str(e)}")
                    return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}
        
    except Exception as e:
        group_logger.error(f"Error getting grey matter statistics for {analysis_path}: {str(e)}")
        return {'grey_mean': 0.0, 'grey_max': 0.0, 'grey_min': 0.0}

def _compute_subject_stats(analysis_results: dict, region_name: str = None) -> pd.DataFrame:
    """
    Compute statistics including focality for each subject and aggregate statistics.

    Args:
        analysis_results (dict): Dictionary with analysis data from _load_subject_data
        region_name (str, optional): Region name for ROI-specific column headers

    Returns:
        pd.DataFrame: DataFrame with ROI-specific columns: Subject_ID, ROI_Mean, ROI_Max, ROI_Min, ROI_Focality,
                     Grey_Mean, Grey_Max, Grey_Min, plus row for averages
    """
    group_logger.info("Computing subject statistics and focality metrics...")
    
    # Determine region name for headers if not provided
    if region_name is None:
        region_name = "ROI"
    
    # Create list to store individual subject data
    subject_data = []
    
    # Check if any subject has TI_normal data
    has_normal_data = any('normal_mean_value' in data['metrics'] for data in analysis_results.values())
    
    for unique_name, data in analysis_results.items():
        metrics = data['metrics']
        
        # Use focality value from the CSV (not recalculated)
        focality = metrics.get('focality', 0.0)
        
        # Basic subject data with TI_max fields
        subject_row = {
            'Subject_ID': data['subject_id'],
            'Montage': data['montage_name'],
            'Analysis': data['analysis_name'],
            f'ROI_Mean': metrics['mean_value'],
            f'ROI_Max': metrics['max_value'],
            f'ROI_Min': metrics['min_value'],
            f'ROI_Focality': focality,
            f'Grey_Mean': metrics.get('grey_mean', 0.0),
            f'Grey_Max': metrics.get('grey_max', 0.0),
            f'Grey_Min': metrics.get('grey_min', 0.0)
        }
        
        # Add TI_normal fields if available
        if has_normal_data:
            subject_row.update({
                f'Normal_Mean': metrics.get('normal_mean_value', 0.0),
                f'Normal_Max': metrics.get('normal_max_value', 0.0),
                f'Normal_Min': metrics.get('normal_min_value', 0.0),
                f'Normal_Focality': metrics.get('normal_focality', 0.0)
            })
        
        subject_data.append(subject_row)
    
    # Create DataFrame
    df = pd.DataFrame(subject_data)
    
    if len(df) == 0:
        group_logger.warning("No valid subject data found")
        return df
    
    # Calculate averages and standard deviations across all subjects
    numeric_cols = [f'ROI_Mean', f'ROI_Max', f'ROI_Min', f'ROI_Focality',
                   f'Grey_Mean', f'Grey_Max', f'Grey_Min']
    
    # Add normal columns if present
    if has_normal_data:
        numeric_cols.extend([f'Normal_Mean', f'Normal_Max', f'Normal_Min', f'Normal_Focality'])
    
    averages = df[numeric_cols].mean()
    std_devs = df[numeric_cols].std(ddof=1)  # Sample standard deviation
    
    # STD columns removed - no longer calculating z-scores
    
    # Create average row
    avg_row = {
        'Subject_ID': 'AVERAGE',
        'Montage': 'ALL',
        'Analysis': 'SUMMARY',
        **averages.to_dict()
    }
    
    # Combine all data: subjects + average (no difference percentage rows)
    all_data = df.to_dict('records') + [avg_row]
    final_df = pd.DataFrame(all_data)
    
    group_logger.info(f"Computed statistics for {len(subject_data)} subjects")
    group_logger.info(f"TI_max averages - ROI_Mean: {averages[f'ROI_Mean']:.6f}, ROI_Max: {averages[f'ROI_Max']:.6f}, "
               f"ROI_Min: {averages[f'ROI_Min']:.6f}, ROI_Focality: {averages[f'ROI_Focality']:.6f}")
    group_logger.info(f"TI_max std devs - ROI_Mean: {std_devs[f'ROI_Mean']:.6f}, ROI_Max: {std_devs[f'ROI_Max']:.6f}, "
               f"ROI_Min: {std_devs[f'ROI_Min']:.6f}, ROI_Focality: {std_devs[f'ROI_Focality']:.6f}")
    
    # Log TI_normal statistics if available
    if has_normal_data:
        group_logger.info(f"TI_normal averages - Normal_Mean: {averages[f'Normal_Mean']:.6f}, Normal_Max: {averages[f'Normal_Max']:.6f}, "
                   f"Normal_Min: {averages[f'Normal_Min']:.6f}, Normal_Focality: {averages[f'Normal_Focality']:.6f}")
        group_logger.info(f"TI_normal std devs - Normal_Mean: {std_devs[f'Normal_Mean']:.6f}, Normal_Max: {std_devs[f'Normal_Max']:.6f}, "
                   f"Normal_Min: {std_devs[f'Normal_Min']:.6f}, Normal_Focality: {std_devs[f'Normal_Focality']:.6f}")
    
    return final_df

def _write_summary_csv(stats_df: pd.DataFrame, output_path: str, region_name: str = None) -> str:
    """
    Write main summary CSV with individual and aggregate statistics.

    Args:
        stats_df (pd.DataFrame): DataFrame with computed statistics
        output_path (str): Base output path for file naming
        region_name (str, optional): Region name for filename

    Returns:
        str: Path to the saved CSV file
    """
    # Construct CSV output path with region information
    if region_name:
        # For spherical regions, simplify the naming
        if region_name.startswith('sphere_'):
            # Extract just the coordinates and radius part (remove 'sphere_' prefix)
            coords_part = region_name.replace('sphere_', '')
            csv_filename = f"main_summary_{coords_part}.csv"
        else:
            csv_filename = f"main_summary_{region_name}.csv"
    else:
        csv_filename = "main_summary.csv"
    
    csv_path = os.path.join(output_path, csv_filename)
    
    group_logger.info(f"Writing main summary CSV to: {csv_path}")
    
    # Ensure output directory exists
    os.makedirs(output_path, exist_ok=True)
    
    # Write CSV with proper formatting
    stats_df.to_csv(csv_path, index=False, float_format='%.6f')
    
    group_logger.debug(f"Enhanced ROI-specific summary CSV successfully written with {len(stats_df)} rows")
    return csv_path

def _generate_comparison_plot(stats_df: pd.DataFrame, output_path: str, region_name: str = None) -> str:
    """
    Generate ROI-specific comparison visualization showing each subject's actual values with standard deviation reference lines.
    
    Args:
        stats_df (pd.DataFrame): DataFrame with computed statistics
        output_path (str): Base output path for file naming
        region_name (str, optional): Region name for plot title and filename
        
    Returns:
        str: Path to the saved plot file
    """
    group_logger.info("Generating ROI-specific field value comparison visualization...")
    
    # Filter to only subject rows (exclude AVERAGE and DIFF% rows)
    subject_df = stats_df[~stats_df['Subject_ID'].str.contains('AVERAGE|DIFF%', na=False)].copy()
    
    if len(subject_df) == 0:
        group_logger.warning("No subject data available for plotting")
        return ""
    
    if len(subject_df) < 2:
        group_logger.warning("At least 2 subjects required for standard deviation analysis")
        return ""
    
    # Calculate means and standard deviations for each metric
    metrics = ['ROI_Mean', 'ROI_Max', 'ROI_Min', 'ROI_Focality']
    metric_labels = ['Mean', 'Max', 'Min', 'Focality']
    
    std_devs = {}
    means = {}
    actual_values = {}
    
    for metric in metrics:
        values = subject_df[metric].values
        means[metric] = np.mean(values)
        std_devs[metric] = np.std(values, ddof=1)  # Sample standard deviation
        actual_values[metric] = values
    
    # Create figure with subplots
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
    axes = [ax1, ax2, ax3, ax4]
    
    # Set main title with region information
    if region_name:
        main_title = f'Field Value Comparison for {region_name}'
    else:
        main_title = 'Field Value Comparison'
    
    fig.suptitle(main_title, fontsize=16, fontweight='bold')
    
    # Prepare data for plotting
    subjects = subject_df['Subject_ID'].tolist()
    x_pos = np.arange(len(subjects))
    
    # Colors for each metric - use positive/negative coloring relative to mean
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728']  # blue, orange, green, red
    
    for i, (metric, label, color, ax) in enumerate(zip(metrics, metric_labels, colors, axes)):
        values = actual_values[metric]
        mean_val = means[metric]
        std_val = std_devs[metric]
        
        # Color bars based on whether above or below mean
        bar_colors = []
        for val in values:
            if val >= mean_val:
                bar_colors.append(color)  # Above mean
            else:
                bar_colors.append(color)  # Below mean - same color but different alpha
        
        # Create bars with actual values
        bars = ax.bar(x_pos, values, color=bar_colors, alpha=0.7)
        
        # Color bars differently for above vs below mean
        for bar, val in zip(bars, values):
            if val >= mean_val:
                bar.set_color(color)
                bar.set_alpha(0.8)
            else:
                bar.set_color(color)
                bar.set_alpha(0.4)
        
        # Add horizontal line at actual mean
        ax.axhline(y=mean_val, color='black', linestyle='-', linewidth=2, alpha=0.8, label=f'Mean ({mean_val:.3f})')
        
        # Add ±1 and ±2 standard deviation lines using actual values
        if std_val > 0:
            ax.axhline(y=mean_val + std_val, color='gray', linestyle='--', linewidth=1, alpha=0.6, label=f'+1σ ({mean_val + std_val:.3f})')
            ax.axhline(y=mean_val - std_val, color='gray', linestyle='--', linewidth=1, alpha=0.6, label=f'-1σ ({mean_val - std_val:.3f})')
            ax.axhline(y=mean_val + 2*std_val, color='red', linestyle='--', linewidth=1, alpha=0.6, label=f'+2σ ({mean_val + 2*std_val:.3f})')
            ax.axhline(y=mean_val - 2*std_val, color='red', linestyle='--', linewidth=1, alpha=0.6, label=f'-2σ ({mean_val - 2*std_val:.3f})')
        
        # Determine appropriate units for labeling
        if 'Focality' in metric:
            unit_label = 'Field Strength Units'
            value_format = '.3f'
        else:
            unit_label = 'V/m'  # Common unit for electric field
            value_format = '.4f'
        
        # Formatting
        ax.set_title(f'ROI {label} ({unit_label})', fontweight='bold')
        ax.set_ylabel(f'{label} {unit_label}')
        ax.tick_params(axis='x', rotation=45)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(subjects, ha='right')
        ax.grid(True, alpha=0.3)
        
        # Set y-axis limits to show all data with some padding
        if std_val > 0:
            y_min = min(np.min(values), mean_val - 2.5*std_val)
            y_max = max(np.max(values), mean_val + 2.5*std_val)
        else:
            y_range = np.max(values) - np.min(values)
            padding = max(0.1 * y_range, 0.01 * np.abs(mean_val))
            y_min = np.min(values) - padding
            y_max = np.max(values) + padding
        
        ax.set_ylim(y_min, y_max)
        
        # Add text annotations for extreme values (>2 std devs from mean)
        for j, (subject, val) in enumerate(zip(subjects, values)):
            if std_val > 0:
                z_score = abs(val - mean_val) / std_val
                if z_score > 2:
                    ax.annotate(f'{val:{value_format}}\n({z_score:.1f}σ)', (j, val), 
                               xytext=(0, 15 if val > mean_val else -25), 
                               textcoords='offset points',
                               ha='center', va='bottom' if val > mean_val else 'top',
                               fontweight='bold', fontsize=8,
                               color='darkred',
                               bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
    
    # Create legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color='black', linestyle='-', linewidth=2, label='Group Mean'),
        Line2D([0], [0], color='gray', linestyle='--', label='±1 Std Dev'),
        Line2D([0], [0], color='red', linestyle='--', label='±2 Std Dev'),
        mpatches.Patch(color='gray', alpha=0.8, label='Above Mean'),
        mpatches.Patch(color='gray', alpha=0.4, label='Below Mean')
    ]
    fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.95))
        
    # Adjust layout to prevent overlap
    plt.tight_layout()
    plt.subplots_adjust(top=0.93)
    
    # Save plot
    if region_name:
        plot_filename = f"roi_field_comparison_plot_{region_name}.png"
    else:
        plot_filename = "roi_field_comparison_plot.png"
    
    plot_path = os.path.join(output_path, plot_filename)
    
    # Ensure output directory exists
    os.makedirs(output_path, exist_ok=True)
    
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    group_logger.info(f"ROI-specific field value comparison plot saved to: {plot_path}")
    return plot_path

def compare_analyses(analyses: List[str], output_dir: str, 
                    generate_plot: bool = True, generate_csv: bool = True):
    """
    Compare multiple analyses using structured sub-methods and generate comprehensive reports.
    
    This refactored function breaks down the comparison process into logical steps:
    1. Load subject data from CSV files
    2. Compute ROI-specific statistics
    3. Generate CSV summary with averages and differences
    4. Create analysis information JSON file
    5. Generate visualization plots (optional)
    
    Args:
        analyses (List[str]): List of absolute paths to analysis directories
        output_dir (str): Path to the output directory (legacy parameter for compatibility)
        generate_plot (bool, optional): Whether to generate comparison plots. Defaults to True.
        generate_csv (bool, optional): Whether to generate CSV summary. Defaults to True.
        
    Returns:
        dict: Dictionary containing paths to generated files and summary statistics
    """
    # Set up centralized logging
    project_name = _extract_project_name(analyses[0])
    global group_logger
    group_logger = setup_group_logger(project_name)
    
    group_logger.info(f"Starting comprehensive analysis comparison for {len(analyses)} analyses")
    group_logger.info(f"Options - Generate CSV: {generate_csv}, Generate Plot: {generate_plot}")
    
    if len(analyses) == 0:
        group_logger.error("No analysis directories provided")
        return {}
    
    # Extract montage and region information for this run
    montage_name, region_name = _extract_montage_and_region_info(analyses)
    
    # Create run-specific output directory
    run_output_dir = _get_run_specific_output_dir(analyses)
    
    group_logger.info(f"Using run-specific output directory: {run_output_dir}")
    group_logger.info(f"Analysis focus: {montage_name} montage, {region_name} region")
    
    try:
        # Step 1: Load subject data
        analysis_results = _load_subject_data(analyses)
        
        if len(analysis_results) == 0:
            group_logger.error("No valid analysis data could be loaded")
            return {}
        
        # Step 2: Compute ROI-specific statistics
        stats_df = _compute_subject_stats(analysis_results, region_name)
        
        if len(stats_df) == 0:
            group_logger.error("No statistics could be computed")
            return {}
        
        generated_files = {}
        
        # Step 3: Generate ROI-specific CSV summary (if requested)
        if generate_csv:
            csv_path = _write_summary_csv(stats_df, run_output_dir, region_name)
            generated_files['csv_summary'] = csv_path
        
        # Step 4: Create analysis information JSON file
        json_path = _create_analysis_info_json(analysis_results, run_output_dir, region_name)
        generated_files['analysis_info'] = json_path
        
        # Step 5: Generate ROI-specific field value visualization (if requested and sufficient data)
        if generate_plot:
            # Only generate plot if we have subject data (not just averages)
            subject_count = len(stats_df[~stats_df['Subject_ID'].str.contains('AVERAGE|DIFF%', na=False)])
            if subject_count > 0:
                plot_path = _generate_comparison_plot(stats_df, run_output_dir, region_name)
                if plot_path:
                    generated_files['field_comparison_plot'] = plot_path
            else:
                group_logger.warning("Insufficient subject data for plot generation")
        
        # Generate summary information
        summary_info = {
            'total_subjects': len(analysis_results),
            'output_directory': run_output_dir,
            'montage_name': montage_name,
            'region_name': region_name,
            'generated_files': generated_files
        }
        
        # Add average statistics to summary
        avg_row = stats_df[stats_df['Subject_ID'] == 'AVERAGE']
        if len(avg_row) > 0:
            summary_info['average_statistics'] = {
                'mean': avg_row['ROI_Mean'].iloc[0],
                'max': avg_row['ROI_Max'].iloc[0],
                'min': avg_row['ROI_Min'].iloc[0],
                'focality': avg_row['ROI_Focality'].iloc[0]
            }
        
        group_logger.debug("Analysis comparison completed successfully")
        group_logger.info(f"Generated files: {list(generated_files.keys())}")
        
        return summary_info
        
    except Exception as e:
        group_logger.error(f"Error during analysis comparison: {str(e)}")
        raise

def collect_arguments() -> Tuple[List[str], str]:
    """
    Collect absolute paths to analysis directories and output directory using command line arguments.
    
    Returns:
        Tuple[List[str], str]: List of absolute paths to analysis directories and output directory path
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

def average_nifti_images(nifti_paths: List[str], output_filename: str = "average_output.nii.gz", output_dir: str = None) -> str:
    """
    Loads multiple NIfTI images, computes their element-wise average, and saves the result.
    
    Args:
        nifti_paths (List[str]): List of file paths to NIfTI images (.nii or .nii.gz)
        output_filename (str, optional): Name of the output file. Defaults to "average_output.nii.gz"
        output_dir (str, optional): Output directory. If None, uses old path generation logic.
    
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
    
    if group_logger:
        group_logger.info(f"Loading and averaging {len(nifti_paths)} NIfTI images...")
    
    try:
        # Load the first image to get reference shape and affine
        first_img = nib.load(nifti_paths[0])
        reference_shape = first_img.shape
        reference_affine = first_img.affine
        reference_header = first_img.header
        
        if group_logger:
            group_logger.info(f"Reference image shape: {reference_shape}")
        
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
        if group_logger:
            group_logger.info("Computing element-wise average...")
        averaged_data = np.mean(all_data, axis=0)
        
        # Create new NIfTI image with averaged data
        averaged_img = nib.Nifti1Image(averaged_data, reference_affine, reference_header)
        
        # Determine output path
        if output_dir:
            # Use provided output directory
            output_path = os.path.join(output_dir, output_filename)
            os.makedirs(output_dir, exist_ok=True)
        else:
            # Use old path generation logic for backward compatibility
            output_path = _get_output_path(nifti_paths, 'averaging', output_filename, 'avg')
        
        if group_logger:
            group_logger.info(f"Saving averaged NIfTI to: {output_path}")
        
        # Save the averaged image
        nib.save(averaged_img, output_path)
        
        if group_logger:
            group_logger.debug(f"Successfully created averaged NIfTI image: {output_path}")
            group_logger.info(f"Output shape: {averaged_data.shape}, Mean value: {np.mean(averaged_data):.6f}")
        
        return output_path
        
    except Exception as e:
        raise Exception(f"Error processing NIfTI images: {str(e)}")

def intersection_high_values_nifti(nifti_paths: List[str], 
                                 min_overlap: int = None,
                                 output_filename: str = "intersection_high_values.nii.gz",
                                 fill_value: float = 0.0,
                                 percentile_low: float = 95.0,
                                 percentile_high: float = 99.9,
                                 output_dir: str = None) -> str:
    """
    Computes intersection of high-value voxels across multiple NIfTI images.
    
    For each NIfTI, identifies voxels within the top percentile range (default: 95th to 99.9th percentiles).
    Creates an intersection mask where a minimum number of NIfTIs have high values, then computes
    the weighted average of those voxels across all contributing NIfTIs.
    
    Args:
        nifti_paths (List[str]): List of file paths to NIfTI images (.nii or .nii.gz)
        min_overlap (int, optional): Minimum number of NIfTIs that must have high values in a voxel
                                   for it to be included. Defaults to total number of input NIfTIs.
        output_filename (str, optional): Name of the output file. Defaults to "intersection_high_values.nii.gz"
        fill_value (float, optional): Value to fill non-intersecting voxels. Defaults to 0.0. 
                                    Use np.nan for NaN fill.
        percentile_low (float, optional): Lower percentile threshold (default: 95.0)
        percentile_high (float, optional): Upper percentile threshold (default: 99.9)
        output_dir (str, optional): Output directory. If None, uses old path generation logic.
    
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
    
    if group_logger:
        group_logger.info(f"Processing {len(nifti_paths)} NIfTI images for high-value intersection")
        group_logger.info(f"Percentile range: {percentile_low}%-{percentile_high}%, Min overlap: {min_overlap}/{len(nifti_paths)}")
    
    try:
        # Load the first image to get reference shape and affine
        first_img = nib.load(nifti_paths[0])
        reference_shape = first_img.shape
        reference_affine = first_img.affine
        reference_header = first_img.header
        
        if group_logger:
            group_logger.info(f"Reference image shape: {reference_shape}")
        
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
                if group_logger:
                    group_logger.debug(f"Image {i+1}: percentiles {p_low:.6f}-{p_high:.6f}, high-value voxels: {num_high_voxels}")
            else:
                if group_logger:
                    group_logger.warning(f"No finite non-zero values found in {os.path.basename(path)}")
                high_value_masks[i] = np.zeros(reference_shape, dtype=bool)
        
        # Compute intersection mask based on min_overlap
        if group_logger:
            group_logger.info("Computing intersection mask...")
        overlap_count = np.sum(high_value_masks, axis=0)  # Count how many images have high values at each voxel
        intersection_mask = overlap_count >= min_overlap
        
        num_intersection_voxels = np.sum(intersection_mask)
        intersection_percent = num_intersection_voxels/np.prod(reference_shape)*100
        if group_logger:
            group_logger.info(f"Intersection voxels: {num_intersection_voxels} ({intersection_percent:.2f}%)")
        
        if num_intersection_voxels == 0:
            if group_logger:
                group_logger.warning("No voxels meet intersection criteria - output will be filled with fill_value")
        
        # Create output array
        output_data = np.full(reference_shape, fill_value, dtype=np.float64)
        
        if num_intersection_voxels > 0:
            # For intersection voxels, compute weighted average across contributing images
            if group_logger:
                group_logger.info("Computing weighted averages for intersection voxels...")
            
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
        
        # Determine output path
        if output_dir:
            # Use provided output directory
            output_path = os.path.join(output_dir, output_filename)
            os.makedirs(output_dir, exist_ok=True)
        else:
            # Use old path generation logic for backward compatibility
            suffix = f"overlap{percentile_low}-{percentile_high}pct_min{min_overlap}"
            output_path = _get_output_path(nifti_paths, 'intersection', output_filename, suffix)
        
        if group_logger:
            group_logger.info(f"Saving intersection NIfTI to: {output_path}")
        
        # Save the intersection image
        nib.save(intersection_img, output_path)
        
        # Summary statistics
        if num_intersection_voxels > 0:
            valid_values = output_data[intersection_mask]
            value_range = f"{np.min(valid_values):.6f} to {np.max(valid_values):.6f}"
            mean_value = np.mean(valid_values)
            if group_logger:
                group_logger.debug(f"Successfully created intersection NIfTI: {output_path}")
                group_logger.info(f"Intersection statistics - voxels: {num_intersection_voxels}, range: {value_range}, mean: {mean_value:.6f}")
        else:
            if group_logger:
                group_logger.info(f"Created intersection NIfTI filled with {fill_value}: {output_path}")
        
        return output_path
        
    except Exception as e:
        raise Exception(f"Error processing NIfTI intersection: {str(e)}")

def _generate_focality_summary(analysis_dirs: List[str], output_dir: str, region_name: str) -> str:
    """
    Generate a focality summary CSV across all subjects.
    
    Args:
        analysis_dirs: List of analysis directories (one per subject)
        output_dir: Output directory for the summary
        region_name: Name of the region being analyzed
        
    Returns:
        str: Path to the generated focality summary CSV file
    """
    try:
        group_logger.info(f"Loading focality data from {len(analysis_dirs)} subjects")
        
        # Collect focality data from all subjects
        focality_data = []
        
        for analysis_dir in analysis_dirs:
            # Extract subject ID from path
            subject_id = _extract_subject_id_from_path(analysis_dir)
            
            # Find extra_info CSV files in the analysis directory
            extra_info_files = []
            for root, dirs, files in os.walk(analysis_dir):
                for file in files:
                    if file.endswith('_extra_info.csv'):
                        extra_info_files.append(os.path.join(root, file))
            
            if not extra_info_files:
                group_logger.warning(f"No extra_info CSV files found for subject {subject_id}")
                continue
            
            # Process each extra_info file (there should typically be one per region)
            for csv_file in extra_info_files:
                try:
                    # Load the focality data
                    df = pd.read_csv(csv_file)
                    
                    # Convert to dictionary format
                    data_dict = {}
                    for _, row in df.iterrows():
                        data_dict[row['Metric']] = row['Value']
                    
                    # Add subject identifier
                    data_dict['Subject_ID'] = subject_id
                    data_dict['CSV_File'] = os.path.basename(csv_file)
                    
                    focality_data.append(data_dict)
                    
                except Exception as e:
                    group_logger.warning(f"Failed to process {csv_file}: {e}")
                    continue
        
        if not focality_data:
            group_logger.warning("No focality data found across all subjects")
            return None
        
        # Create DataFrame from collected data
        df = pd.DataFrame(focality_data)
        
        # Ensure we have the required columns
        required_cols = ['Subject_ID', 'region_name', 'percentile_95', 'percentile_99', 'percentile_99_9', 
                        'focality_50', 'focality_75', 'focality_90', 'focality_95']
        
        # Check which columns exist
        existing_cols = [col for col in required_cols if col in df.columns]
        if not existing_cols:
            group_logger.warning("No required focality columns found in data")
            return None
        
        # Select and reorder columns
        columns_to_include = ['Subject_ID'] + [col for col in existing_cols if col != 'Subject_ID']
        df_summary = df[columns_to_include].copy()
        
        # Generate output filename
        if region_name:
            filename = f"focality_summary_{region_name}.csv"
        else:
            filename = "focality_summary.csv"
        
        output_path = os.path.join(output_dir, filename)
        
        # Save the summary
        df_summary.to_csv(output_path, index=False, float_format='%.6f')
        
        group_logger.info(f"Focality summary saved with {len(df_summary)} entries to: {output_path}")
        group_logger.info(f"Summary columns: {list(df_summary.columns)}")
        
        return output_path
        
    except Exception as e:
        group_logger.error(f"Error generating focality summary: {e}")
        return None

def _extract_subject_id_from_path(analysis_path: str) -> str:
    """Extract subject ID from analysis directory path."""
    path_parts = analysis_path.split(os.sep)
    for part in path_parts:
        if part.startswith('sub-'):
            return part
    return "unknown_subject"

def run_all_group_comparisons(analysis_dirs: List[str], project_name: str = None) -> str:
    """
    Run all available comparison methods on a list of analysis directories.
    
    This is the main orchestration function called by group_analyzer.py to perform
    comprehensive group-level comparisons using all available methods.
    
    Args:
        analysis_dirs (List[str]): List of paths to individual subject analysis directories
        project_name (str, optional): Project name for output directory. If None, extracted from first path.
        
    Returns:
        str: Path to the run-specific group analysis output directory containing all results
    """
    # Set up centralized logging
    if project_name is None:
        project_name = _extract_project_name(analysis_dirs[0])
    
    global group_logger
    group_logger = setup_group_logger(project_name)
    
    if not analysis_dirs:
        group_logger.error("No analysis directories provided for group comparison")
        return ""
    
    if len(analysis_dirs) < 2:
        group_logger.warning(f"Only {len(analysis_dirs)} analysis directory provided. Some comparisons require multiple subjects.")
    
    # Extract montage and region information for this run
    montage_name, region_name = _extract_montage_and_region_info(analysis_dirs)
    
    # Create run-specific output directory
    run_output_dir = _get_run_specific_output_dir(analysis_dirs)
    
    group_logger.info(f"Starting comprehensive group analysis for {len(analysis_dirs)} subjects")
    group_logger.info(f"Analysis focus: {montage_name} montage, {region_name} region")
    group_logger.info(f"Run-specific output directory: {run_output_dir}")
    
    # 1. Run ROI-specific statistical comparison analysis
    comparison_results = None
    if len(analysis_dirs) >= 1:  # Allow single subject for basic statistics
        group_logger.info("Running ROI-specific statistical comparison...")
        try:
            comparison_results = compare_analyses(analysis_dirs, run_output_dir, 
                                                generate_plot=True, generate_csv=True)
            if comparison_results:
                group_logger.info(f"Statistical comparison completed for {comparison_results.get('total_subjects', 0)} subjects")
                generated_files = comparison_results.get('generated_files', {})
                for file_type, file_path in generated_files.items():
                    group_logger.info(f"Generated {file_type}: {file_path}")
        except Exception as e:
            group_logger.error(f"Statistical comparison failed: {e}")

    # 1.5. Generate focality summary across subjects  
    if len(analysis_dirs) >= 1:
        group_logger.info("Generating focality summary...")
        try:
            focality_summary_path = _generate_focality_summary(analysis_dirs, run_output_dir, region_name)
            if focality_summary_path:
                group_logger.info(f"Focality summary generated: {focality_summary_path}")
        except Exception as e:
            group_logger.error(f"Focality summary generation failed: {e}")
    
    # 2. Collect standardized grey matter MNI NIfTI files for image-based comparisons
    nifti_files = []
    subject_ids = []
    
    for analysis_dir in analysis_dirs:
        # Extract subject ID and montage from analysis directory path
        # Expected path pattern: .../sub-{subject_id}/Simulations/{montage_name}/Analyses/...
        path_parts = analysis_dir.split(os.sep)
        
        subject_id = None
        extracted_montage = None
        
        # Find subject ID (sub-XXX pattern)
        for i, part in enumerate(path_parts):
            if part.startswith('sub-'):
                subject_id = part
                # Look for Simulations directory and get montage name
                if i + 2 < len(path_parts) and path_parts[i + 1] == 'Simulations':
                    extracted_montage = path_parts[i + 2]
                break
        
        if not subject_id or not extracted_montage:
            group_logger.warning(f"Could not extract subject ID or montage from path: {analysis_dir}")
            continue
        
        # Construct path to the standardized grey matter MNI NIfTI file
        # Format: projectdir/derivatives/SimNIBS/sub-{subject_id}/Simulations/{montage_name}/TI/niftis/grey_{subject_short}_TI_MNI_MNI_TI_max.nii.gz
        subject_short = subject_id.replace('sub-', '')  # Remove 'sub-' prefix
        nifti_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                subject_id, "Simulations", extracted_montage, "TI", "niftis")
        
        if not os.path.exists(nifti_dir):
            group_logger.warning(f"NIfTI directory not found: {nifti_dir}")
            continue
        
        # Look for the standardized grey matter MNI file with flexible pattern matching
        # Try multiple common patterns for grey matter NIfTI files
        # First try patterns without subject ID (common in newer file structures)
        potential_patterns = [
            f"grey_{extracted_montage}_TI_MNI_MNI_TI_max",
            f"grey_{extracted_montage}_TI_MNI_TI_max",
            f"grey_{extracted_montage}_TI_max",
            f"grey_{extracted_montage}_MNI_TI_max",
            # Then try patterns with subject ID (legacy file structures)
            f"grey_{subject_short}_{extracted_montage}_TI_MNI_MNI_TI_max",
            f"grey_{subject_short}_{extracted_montage}_TI_MNI_TI_max", 
            f"grey_{subject_short}_{extracted_montage}_TI_max",
            f"grey_{subject_short}_{extracted_montage}_MNI_TI_max",
            f"grey_{subject_short}_TI_MNI_MNI_TI_max",
            f"grey_{subject_short}_TI_MNI_TI_max"
        ]
        
        # List all files in the directory for debugging
        all_files = os.listdir(nifti_dir)
        grey_files = [f for f in all_files if f.startswith('grey_') and f.endswith(('.nii', '.nii.gz'))]
        
        group_logger.info(f"Found {len(grey_files)} grey matter NIfTI files in {nifti_dir}")
        group_logger.debug(f"Grey matter files: {grey_files}")
        
        matching_files = []
        used_pattern = None
        
        # Try each pattern until we find a match
        for pattern in potential_patterns:
            for file in grey_files:
                if file.startswith(pattern):
                    matching_files.append(file)
                    used_pattern = pattern
                    break
            if matching_files:
                break
        
        # If no exact pattern match, try more flexible matching
        if not matching_files:
            group_logger.info(f"No exact pattern match found, trying flexible matching for {subject_id}")
            for file in grey_files:
                # Check if file contains the subject and montage info in any order
                if (subject_short in file and 
                    extracted_montage in file and 
                    'TI' in file and 
                    'max' in file):
                    matching_files.append(file)
                    used_pattern = "flexible_match"
                    group_logger.info(f"Found flexible match: {file}")
                    break
        
        if matching_files:
            # Use the first matching file (they should be equivalent)
            nifti_filename = matching_files[0]
            nifti_path = os.path.join(nifti_dir, nifti_filename)
            nifti_files.append(nifti_path)
            subject_ids.append(subject_id)
            group_logger.info(f"Found standardized NIfTI for {subject_id}: {nifti_filename} (pattern: {used_pattern})")
        else:
            group_logger.warning(f"No standardized grey matter MNI NIfTI found for {subject_id} in {nifti_dir}")
            group_logger.warning(f"Tried patterns: {potential_patterns}")
            group_logger.warning(f"Available grey matter files: {grey_files}")
    
    group_logger.info(f"Found {len(nifti_files)} standardized grey matter MNI NIfTI files for image-based analysis")
    
    # Track generated NIfTI files
    nifti_results = {}
    
    # 3. Run NIfTI averaging if multiple files found
    if len(nifti_files) >= 2:
        group_logger.info("Running NIfTI averaging analysis...")
        try:
            avg_output = average_nifti_images(
                nifti_files, 
                f"averaged_field_{region_name}.nii.gz",
                output_dir=run_output_dir
            )
            group_logger.info(f"Average NIfTI saved to: {avg_output}")
            nifti_results['averaged_nifti'] = avg_output
        except Exception as e:
            group_logger.error(f"NIfTI averaging failed: {e}")
    elif len(nifti_files) == 1:
        group_logger.info("Only 1 NIfTI file found - skipping averaging (requires at least 2 files)")
    else:
        group_logger.info("No NIfTI files found - skipping averaging")
    
    # 4. Run high-value intersection analysis if multiple files found
    if len(nifti_files) >= 2:
        group_logger.info("Running high-value intersection analysis...")
        try:
            # Run intersection with all subjects required (strictest)
            intersection_all = intersection_high_values_nifti(
                nifti_files, 
                min_overlap=len(nifti_files),
                output_filename=f"intersection_all_subjects_{region_name}.nii.gz",
                percentile_low=95.0,
                percentile_high=99.9,
                output_dir=run_output_dir
            )
            group_logger.info(f"Strict intersection (all subjects) saved to: {intersection_all}")
            nifti_results['intersection_all'] = intersection_all
            
            # Note: Partial intersection method is available but not currently produced
            # To enable partial intersection, uncomment the following code:
            # if len(nifti_files) > 2:
            #     min_overlap = max(2, len(nifti_files) // 2)
            #     intersection_partial = intersection_high_values_nifti(
            #         nifti_files,
            #         min_overlap=min_overlap,
            #         output_filename=f"intersection_partial_overlap_{region_name}.nii.gz",
            #         percentile_low=95.0,
            #         percentile_high=99.9,
            #         output_dir=run_output_dir
            #     )
            #     group_logger.info(f"Partial intersection ({min_overlap}/{len(nifti_files)} subjects) saved to: {intersection_partial}")
            #     nifti_results['intersection_partial'] = intersection_partial
            
        except Exception as e:
            group_logger.error(f"Intersection analysis failed: {e}")
    elif len(nifti_files) == 1:
        group_logger.info("Only 1 NIfTI file found - skipping intersection (requires at least 2 files)")
    else:
        group_logger.info("No NIfTI files found - skipping intersection")
    
    # Summary information is already logged, no need for separate summary file
    
    group_logger.info(f"Group analysis complete. All results saved to: {run_output_dir}")
    if nifti_results:
        group_logger.info(f"Generated NIfTI files: {list(nifti_results.keys())}")
        for analysis_type, file_path in nifti_results.items():
            group_logger.info(f"  • {analysis_type}: {os.path.basename(file_path)}")
    
    return run_output_dir

def _create_analysis_info_json(analysis_results: dict, output_path: str, region_name: str = None) -> str:
    """
    Create a JSON file with information about each analysis.
    
    Args:
        analysis_results (dict): Dictionary with analysis data from _load_subject_data
        output_path (str): Base output path for file naming
        region_name (str, optional): Region name for filename
        
    Returns:
        str: Path to the saved JSON file
    """
    # Construct JSON output path with region information
    if region_name:
        json_filename = f"analysis_info_{region_name}.json"
    else:
        json_filename = "analysis_info.json"
    
    json_path = os.path.join(output_path, json_filename)
    
    group_logger.info(f"Creating analysis information JSON file: {json_path}")
    
    # Ensure output directory exists
    os.makedirs(output_path, exist_ok=True)
    
    # Create analysis information dictionary
    analysis_info = {
        "metadata": {
            "total_analyses": len(analysis_results),
            "region_name": region_name,
            "created_at": __import__('datetime').datetime.now().isoformat()
        },
        "analyses": []
    }
    
    for unique_name, data in analysis_results.items():
        # Extract field file information
        field_file_name = "unknown"
        space_type = "unknown"
        
        # Determine space type and field file from analysis path
        analysis_path = data['analysis_path']
        path_parts = analysis_path.split('/')
        
        # Look for Mesh or Voxel in the path
        for part in path_parts:
            if part == 'Mesh':
                space_type = 'mesh'
                break
            elif part == 'Voxel':
                space_type = 'voxel'
                break
        
        # Try to find the field file name
        try:
            project_name = _extract_project_name(analysis_path)
            subject_id = data['subject_id']
            montage_name = data['montage_name']
            subject_short = subject_id.replace('sub-', '')
            
            if space_type == 'mesh':
                # Look for .msh files in the mesh directory
                field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                       subject_id, "Simulations", montage_name, "TI", "mesh")
                if os.path.exists(field_dir):
                    msh_files = [f for f in os.listdir(field_dir) if f.endswith('.msh') and not f.endswith('.msh.opt')]
                    if msh_files:
                        field_file_name = msh_files[0]
            else:  # voxel
                # Look for grey matter NIfTI files
                field_dir = os.path.join("/mnt", project_name, "derivatives", "SimNIBS", 
                                       subject_id, "Simulations", montage_name, "TI", "niftis")
                if os.path.exists(field_dir):
                    grey_files = [f for f in os.listdir(field_dir) if f.startswith('grey_') and f.endswith(('.nii', '.nii.gz'))]
                    if grey_files:
                        field_file_name = grey_files[0]
        except Exception as e:
            group_logger.warning(f"Could not determine field file for {unique_name}: {str(e)}")
        
        # Create analysis entry
        analysis_entry = {
            "subject_id": data['subject_id'],
            "montage": data['montage_name'],
            "roi": data['analysis_name'],
            "space": space_type,
            "folder_path": data['analysis_path'],
            "field_file_name": field_file_name,
            "csv_file": os.path.basename(data['csv_path']) if 'csv_path' in data else "unknown"
        }
        
        analysis_info["analyses"].append(analysis_entry)
    
    # Write JSON file
    with open(json_path, 'w') as f:
        json.dump(analysis_info, f, indent=2)
    
    group_logger.info(f"Analysis information JSON file created with {len(analysis_info['analyses'])} entries")
    return json_path

if __name__ == "__main__":
    analyses, output_path = collect_arguments()
    output_dir = setup_output_dir(output_path)
    
    # Run the refactored comparison analysis
    try:
        results = compare_analyses(analyses, output_dir, generate_plot=True, generate_csv=True)
        
        if results:
            if group_logger:
                group_logger.info("\n" + "="*60)
                group_logger.debug("ROI-SPECIFIC ANALYSIS COMPARISON COMPLETED SUCCESSFULLY")
                group_logger.info("="*60)
                group_logger.info(f"Total subjects analyzed: {results.get('total_subjects', 0)}")
                group_logger.info(f"Montage: {results.get('montage_name', 'N/A')}")
                group_logger.info(f"Region/ROI: {results.get('region_name', 'N/A')}")
                group_logger.info(f"Output directory: {results.get('output_directory', 'N/A')}")
                
                generated_files = results.get('generated_files', {})
                if generated_files:
                    group_logger.info("\nGenerated files:")
                    for file_type, file_path in generated_files.items():
                        group_logger.info(f"  • {file_type}: {file_path}")
                
                avg_stats = results.get('average_statistics', {})
                if avg_stats:
                    group_logger.info(f"\nGroup average ROI statistics:")
                    group_logger.info(f"  • ROI Mean: {avg_stats.get('mean', 0):.6f}")
                    group_logger.info(f"  • ROI Max: {avg_stats.get('max', 0):.6f}")
                    group_logger.info(f"  • ROI Min: {avg_stats.get('min', 0):.6f}")
                    group_logger.info(f"  • ROI Focality: {avg_stats.get('focality', 0):.6f}")
                
                group_logger.info("\n" + "="*60)
        else:
            if group_logger:
                group_logger.warning("Analysis comparison completed but no results were generated.")
            
    except Exception as e:
        if group_logger:
            group_logger.error(f"Error during analysis comparison: {e}")
        sys.exit(1)