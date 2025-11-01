#!/usr/bin/env simnibs_python
"""
Ex-Search Field Analyzer
Simplified analyzer specifically for ex-search that extracts all field values within ROI.
"""

import csv
import json
import os
import re
import sys
import time

# Third-party imports
import numpy as np
from simnibs import mesh_io

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Local imports
from tools import logging_util
from core import get_path_manager
from opt.roi import ROICoordinateHelper
from opt.ti_calculations import find_roi_element_indices


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
    logger.info("Using ROI-based field extraction (all elements within 3mm sphere)")
    
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
    
    # If no pre-calculated results, check for mesh files (legacy mode)
    logger.info("="*60)
    logger.info("Ex-Search Analysis - Legacy Mode")
    logger.info("="*60)
    logger.info("No pre-calculated results found, checking for mesh files...")
    
    # Read ROI list
    custom_roi_list = os.getenv('ROI_LIST_FILE')
    if custom_roi_list and os.path.exists(custom_roi_list):
        roi_list_path = custom_roi_list
        # For custom ROI list, use the directory where the list file is located
        custom_roi_dir = os.path.dirname(roi_list_path)
        logger.info(f"Using custom ROI list: {roi_list_path}")
        logger.info(f"Custom ROI directory: {custom_roi_dir}")
        roi_directory = custom_roi_dir
    else:
        roi_list_path = os.path.join(roi_directory, 'roi_list.txt')
        logger.info(f"Using default ROI list: {roi_list_path}")
    
    try:
        with open(roi_list_path, 'r') as file:
            position_files = [os.path.join(roi_directory, line.strip()) for line in file]
    except FileNotFoundError:
        logger.error(f"ROI list file not found at {roi_list_path}")
        sys.exit(1)
    
    # Verify ROI files exist
    missing_files = [f for f in position_files if not os.path.exists(f)]
    if missing_files:
        logger.error("The following ROI files are missing:")
        for f in missing_files:
            logger.error(f"  - {f}")
        sys.exit(1)
    
    # Run analysis (opt_directory already determined above)
    logger.info("="*60)
    logger.info("Ex-Search Field Analysis")
    logger.info("="*60)
    
    mesh_data, analysis_dir = analyze_ex_search(opt_directory, roi_directory, position_files, m2m_dir, logger)
    
    # Save JSON results
    json_output_path = os.path.join(analysis_dir, 'analysis_results.json')
    with open(json_output_path, 'w') as json_file:
        json.dump(mesh_data, json_file, indent=4)
    logger.info(f"Results saved to: {json_output_path}")
    
    # Create CSV output
    header = ['Montage', 'TImax_ROI', 'TImean_ROI']
    csv_data = [header]
    
    # Lists for histogram data
    timax_values = []
    timean_values = []
    
    for mesh_name, data in mesh_data.items():
        # Format montage name
        formatted_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")
        
        # Get ROI results
        ti_max_roi = None
        ti_mean_roi = None
        
        for key, value in data.items():
            if 'TImax_ROI' in key:
                ti_max_roi = value
            elif 'TImean_ROI' in key:
                ti_mean_roi = value
        
        # Format values
        ti_max_str = f"{float(ti_max_roi):.4f}" if ti_max_roi is not None else ''
        ti_mean_str = f"{float(ti_mean_roi):.4f}" if ti_mean_roi is not None else ''
        
        csv_data.append([formatted_name, ti_max_str, ti_mean_str])
        
        # Collect for histogram
        if ti_max_roi is not None:
            timax_values.append(ti_max_roi)
        if ti_mean_roi is not None:
            timean_values.append(ti_mean_roi)
    
    # Write CSV
    csv_output_path = os.path.join(analysis_dir, 'final_output.csv')
    with open(csv_output_path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(csv_data)
    
    logger.info(f"CSV output created: {csv_output_path}")
    
    # Generate histogram visualizations
    if timax_values or timean_values:
        logger.info("Generating histogram visualizations...")
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            # Create figure with 2 subplots
            fig, axes = plt.subplots(1, 2, figsize=(12, 4))
            
            # TImax histogram
            if timax_values:
                axes[0].hist(timax_values, bins=20, color='#2196F3', edgecolor='black', alpha=0.7)
                axes[0].set_xlabel('TImax (V/m)', fontsize=12)
                axes[0].set_ylabel('Frequency', fontsize=12)
                axes[0].set_title('TImax Distribution', fontsize=14, fontweight='bold')
                axes[0].grid(axis='y', alpha=0.3)
            
            # TImean histogram
            if timean_values:
                axes[1].hist(timean_values, bins=20, color='#4CAF50', edgecolor='black', alpha=0.7)
                axes[1].set_xlabel('TImean (V/m)', fontsize=12)
                axes[1].set_ylabel('Frequency', fontsize=12)
                axes[1].set_title('TImean Distribution', fontsize=14, fontweight='bold')
                axes[1].grid(axis='y', alpha=0.3)
            
            plt.tight_layout()
            
            # Save histogram
            histogram_path = os.path.join(analysis_dir, 'montage_distributions.png')
            plt.savefig(histogram_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"Histogram visualization saved: {histogram_path}")
            
        except Exception as e:
            logger.warning(f"Could not generate histogram: {e}")
    
    logger.info("="*60)
    logger.info(f"Analysis completed for {len(mesh_data)} montages")
    logger.info("ROI extraction: All mesh elements within 3mm sphere (volume-weighted averaging)")
    logger.info("="*60)


if __name__ == "__main__":
    main()

