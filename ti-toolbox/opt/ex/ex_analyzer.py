#!/usr/bin/env simnibs_python
"""
Ex-Search Field Analyzer
Simplified analyzer specifically for ex-search that extracts all field values within ROI.
"""

# Third-party imports
import numpy as np
from simnibs import mesh_io

# Standard library imports
import csv
import json
import os
import re
import sys
import time

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Local imports
from tools import logging_util
from core import get_path_manager
from core.roi import ROICoordinateHelper
from core.roi import find_roi_element_indices


def analyze_ex_search(opt_directory, roi_directory, position_files, m2m_dir, logger):
    """
    Analyze ex-search results by extracting all field values within ROI.
    
    Args:
        opt_directory: Directory containing mesh files
        roi_directory: Directory containing ROI files
        position_files: List of ROI file paths
        m2m_dir: Path to m2m directory (for ROI manager)
        logger: Logger instance
    
    Returns:
        Dictionary of analysis results
    """
    # Create analysis directory
    analysis_dir = os.path.join(opt_directory, "analysis")
    os.makedirs(analysis_dir, exist_ok=True)
    
    # Dictionary to hold results
    mesh_data = {}
    
    # Get list of mesh files
    msh_files = [f for f in os.listdir(opt_directory) if f.endswith('.msh')]
    total_files = len(msh_files)
    
    logger.info(f"Found {total_files} mesh files to process")
    
    # Process each mesh file
    for i, msh_file in enumerate(msh_files):
        msh_file_path = os.path.join(opt_directory, msh_file)
        
        progress_str = f"{i+1:03}/{total_files}"
        logger.info(f"{progress_str} Analyzing {msh_file}")
        
        mesh_key = os.path.basename(msh_file_path)
        mesh_data[mesh_key] = {}
        
        # Load mesh once per file
        try:
            mesh = mesh_io.read_msh(msh_file_path)
        except Exception as e:
            logger.error(f"Error loading mesh {msh_file}: {e}")
            continue
        
        # Process each ROI
        for pos_file in position_files:
            pos_base = os.path.splitext(os.path.basename(pos_file))[0]
            
            # Get ROI center coordinates
            roi_coords = ROICoordinateHelper.load_roi_from_csv(pos_file)
            if roi_coords is None:
                logger.error(f"Could not read ROI coordinates from {pos_file}")
                continue
            
            # Convert to list if numpy array
            if hasattr(roi_coords, 'tolist'):
                roi_coords = roi_coords.tolist()
            
            # Find ROI elements using shared utility
            roi_indices, element_volumes = find_roi_element_indices(mesh, roi_coords, radius=3.0)
            
            if len(roi_indices) == 0:
                logger.warning(f"No elements found within ROI for {pos_base}")
                mesh_data[mesh_key][f'{pos_base}_TImax_ROI'] = None
                mesh_data[mesh_key][f'{pos_base}_TImean_ROI'] = None
                mesh_data[mesh_key][f'{pos_base}_n_elements'] = 0
                continue
            
            # Get field data
            if 'TImax' not in mesh.field:
                available_fields = list(mesh.field.keys())
                logger.error(f"Field 'TImax' not found. Available: {available_fields}")
                continue
            
            # Extract field values within ROI
            field_values = mesh.field['TImax'].value[roi_indices]
            
            # Calculate ROI metrics
            roi_max = float(np.max(field_values))
            roi_mean = float(np.average(field_values, weights=element_volumes))
            
            # Store results
            mesh_data[mesh_key][f'{pos_base}_TImax_ROI'] = roi_max
            mesh_data[mesh_key][f'{pos_base}_TImean_ROI'] = roi_mean
            mesh_data[mesh_key][f'{pos_base}_n_elements'] = int(len(roi_indices))
            
            logger.debug(f"  {pos_base}: TImax={roi_max:.4f}, TImean={roi_mean:.4f}, n_elements={len(roi_indices)}")
    
    return mesh_data, analysis_dir


def main():
    """Main function for ex-search field analysis."""
    # Get environment variables
    project_dir = os.getenv('PROJECT_DIR')
    subject_name = os.getenv('SUBJECT_NAME')
    
    if not project_dir or not subject_name:
        print("Error: PROJECT_DIR and SUBJECT_NAME environment variables must be set")
        sys.exit(1)
    
    # Initialize logger
    shared_log_file = os.environ.get('TI_LOG_FILE')
    if shared_log_file:
        log_file = shared_log_file
        logger = logging_util.get_logger('ex_analyzer', log_file, overwrite=False)
    else:
        logger_name = 'Ex-Analyzer'
        time_stamp = time.strftime('%Y%m%d_%H%M%S')
        log_file = f'ex_analyzer_{time_stamp}.log'
        logger = logging_util.get_logger(logger_name, log_file, overwrite=False)
    
    # Configure external loggers
    logging_util.configure_external_loggers(['simnibs'], logger)
    
    # Use PathManager for consistent paths
    pm = get_path_manager()
    m2m_dir = pm.get_m2m_dir(subject_name)
    ex_search_dir = pm.get_ex_search_dir(subject_name)
    roi_directory = pm.get_roi_dir(subject_name)
    
    # Determine output directory from environment variables
    roi_name = os.getenv('ROI_NAME')
    selected_eeg_net = os.getenv('SELECTED_EEG_NET')
    
    if not roi_name or not selected_eeg_net:
        logger.error("ROI_NAME and SELECTED_EEG_NET environment variables must be set")
        sys.exit(1)
    
    output_dir_name = f"{roi_name}_{selected_eeg_net}"
    opt_directory = os.path.join(ex_search_dir, output_dir_name)
    
    # Check if results already exist from fast mode
    results_file = os.path.join(opt_directory, 'analysis_results.json')
    
    if os.path.exists(results_file):
        logger.info("="*60)
        logger.info("Ex-Search Analysis - Fast Mode Results")
        logger.info("="*60)
        logger.info(f"Results already calculated by ti_sim.py (fast mode)")
        logger.info(f"Results file: {results_file}")
        logger.info("No additional analysis needed - results ready!")
        logger.info("="*60)
        sys.exit(0)
    
    # If no pre-calculated results, exit with error
    logger.warning("="*60)
    logger.warning("No Pre-Calculated Results Found")
    logger.warning("="*60)
    logger.warning("Ex-search should be run with fast mode enabled (default).")
    logger.warning("Fast mode calculates results during TI simulation.")
    logger.warning(f"Expected results file: {results_file}")
    logger.warning("="*60)
    logger.error("No results found - analysis cannot proceed without pre-calculated data.")
    logger.error("Legacy mode has been disabled. TI simulation must use fast mode.")
    sys.exit(1)


if __name__ == "__main__":
    main()

