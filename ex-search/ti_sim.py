#!/usr/bin/env python3

import copy
import os
import re
import sys
import time
import numpy as np
import logging
from itertools import product
from simnibs import mesh_io
from simnibs.utils import TI_utils as TI
import csv

# Add logging utility import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util

'''
Ido Haber - ihaber@wisc.edu
TI Simulation Script - Optimized for ex-search pipeline

This script performs Temporal Interference (TI) simulations with:
1. Default 1mA current amplitude
2. Optimized sequential processing (SimNIBS has internal parallelization)
3. Better progress tracking and error handling

Key improvements:
- Default stimulation amplitude set to 1mA (0.001A)
- Progress tracking and time estimation
- Robust error handling
- Compatible with SimNIBS internal parallel processing
'''

# Define color variables
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
RESET = '\033[0m'
RED = '\033[0;31m'     # Red for errors
GREEN = '\033[0;32m'   # Green for success messages and prompts
CYAN = '\033[0;36m'    # Cyan for actions being performed
BOLD_CYAN = '\033[1;36m'
YELLOW = '\033[0;33m'  # Yellow for warnings

def get_roi_coordinates(roi_file):
    """Read coordinates from a ROI CSV file."""
    try:
        with open(roi_file, 'r') as f:
            reader = csv.reader(f)
            coords = next(reader)
            return [float(coord.strip()) for coord in coords]
    except Exception as e:
        # Use logger if available, otherwise print
        try:
            logger.error(f"Error reading coordinates from {roi_file}: {e}")
        except NameError:
            print(f"{RED}Error reading coordinates from {roi_file}: {e}{RESET}")
        return None

def generate_combinations(E1_plus, E1_minus, E2_plus, E2_minus):
    """Generate all electrode pair combinations."""
    logger.info("Generating all electrode pair combinations")
    combinations = []
    for e1p, e1m in product(E1_plus, E1_minus):
        for e2p, e2m in product(E2_plus, E2_minus):
            combinations.append(((e1p, e1m), (e2p, e2m)))
    logger.info(f"Generated {len(combinations)} total combinations")
    return combinations

def get_electrode_list(prompt):
    """Get user input for electrode lists with validation."""
    # Support various electrode naming conventions: E001, E1, Fp1, F3, C4, Cz, etc.
    pattern = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')
    while True:
        user_input = input(f"[INPUT] {prompt}").strip()
        # Replace commas with spaces and split into a list
        electrodes = user_input.replace(',', ' ').split()
        # Validate electrodes
        if all(pattern.match(e) for e in electrodes):
            logger.info(f"Electrode list accepted: {electrodes}")
            return electrodes
        else:
            logger.error("Invalid input. Please enter valid electrode names, e.g., E001, Fp1, F3, C4")

def get_intensity(prompt):
    """Get stimulation intensity with default 1mA option."""
    default_ma = 1.0  # Default 1mA
    default_a = default_ma / 1000.0  # Convert to Amperes (0.001A)
    
    logger.info("Stimulation intensity configuration:")
    logger.info(f"  Default: {default_ma} mA ({default_a} A)")
    
    while True:
        user_input = input(f"[INPUT] {prompt} [Press Enter for {default_ma} mA]: ").strip()
        
        if not user_input:  # Use default if empty
            logger.info(f"Using default intensity: {default_ma} mA ({default_a} A)")
            return default_a
            
        try:
            intensity_ma = float(user_input)
            intensity_a = intensity_ma / 1000.0  # Convert mA to A
            logger.info(f"Intensity set to {intensity_ma} mA ({intensity_a} A)")
            return intensity_a
        except ValueError:
            logger.error("Please enter a valid number for the intensity")

def process_leadfield(leadfield_type, E1_plus, E1_minus, E2_plus, E2_minus, 
                     intensity, project_dir, subject_name):
    """Process leadfield with sequential execution (SimNIBS-compatible)."""
    logger.info(f"Starting TI simulation for {leadfield_type} leadfield")
    
    # Get leadfield path from environment variable (set by CLI script)
    leadfield_hdf = os.getenv('LEADFIELD_HDF')
    selected_net = os.getenv('SELECTED_EEG_NET', 'Unknown')
    
    if not leadfield_hdf:
        logger.error("LEADFIELD_HDF environment variable not set")
        return
    
    if not os.path.exists(leadfield_hdf):
        logger.error(f"Leadfield file not found: {leadfield_hdf}")
        return
    
    logger.info(f"Using EEG net: {selected_net}")
    logger.info(f"Leadfield HDF5 path: {leadfield_hdf}")
    
    # Construct other paths according to BIDS structure
    simnibs_dir = os.path.join(project_dir, "derivatives", "SimNIBS")
    subject_dir = os.path.join(simnibs_dir, f"sub-{subject_name}")
    m2m_dir = os.path.join(subject_dir, f"m2m_{subject_name}")
    roi_dir = os.path.join(m2m_dir, "ROIs")
    
    # Get output directory from environment variables (set by GUI)
    roi_name = os.getenv('ROI_NAME')
    if roi_name:
        # Use GUI-provided ROI name and EEG net for directory naming
        output_dir_name = f"{roi_name}_{selected_net}"
        output_dir = os.path.join(subject_dir, "ex-search", output_dir_name)
        logger.info(f"Using GUI-selected ROI: {roi_name}")
    else:
        # CLI usage: fallback to coordinate-based naming
        roi_list_path = os.path.join(roi_dir, 'roi_list.txt')
        try:
            with open(roi_list_path, 'r') as file:
                first_roi_name = file.readline().strip()
                first_roi_name = os.path.basename(first_roi_name)
                first_roi = os.path.join(roi_dir, first_roi_name)
        except FileNotFoundError:
            logger.error(f"ROI list file not found: {roi_list_path}")
            sys.exit(1)
        
        coords = get_roi_coordinates(first_roi)
        if not coords:
            logger.error("Could not read coordinates from ROI file")
            sys.exit(1)
        
        # Create coordinate-based directory for CLI usage
        coord_dir = f"xyz_{int(coords[0])}_{int(coords[1])}_{int(coords[2])}"
        output_dir = os.path.join(subject_dir, "ex-search", coord_dir)
        logger.info(f"Using coordinate-based directory: {coord_dir}")
    logger.info(f"Output directory: {output_dir}")
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logger.info("Output directory created")
    
    # Load leadfield (SimNIBS handles internal optimization)
    try:
        logger.info(f"Loading leadfield matrix from: {leadfield_hdf}")
        logger.info("This may take several minutes for large leadfield matrices...")
        start_load_time = time.time()
        leadfield, mesh, idx_lf = TI.load_leadfield(leadfield_hdf)
        load_time = time.time() - start_load_time
        logger.info(f"Leadfield loaded successfully in {load_time:.1f} seconds")
    except Exception as e:
        logger.error(f"Failed to load leadfield: {e}")
        return
    
    # Generate combinations for sequential processing
    all_combinations = generate_combinations(E1_plus, E1_minus, E2_plus, E2_minus)
    total_combinations = len(all_combinations)
    
    logger.info(f"Starting sequential TI simulations for {total_combinations} combinations")
    logger.info("Note: Using sequential processing for SimNIBS compatibility")
    
    # Process combinations sequentially with progress tracking
    start_time = time.time()
    completed_count = 0
    failed_count = 0
    
    for i, ((e1p, e1m), (e2p, e2m)) in enumerate(all_combinations):
        try:
            logger.info(f"Processing combination {i+1}/{total_combinations}: {e1p}-{e1m} and {e2p}-{e2m}")
            
            # Create TI pairs
            TIpair1 = [e1p, e1m, intensity]
            TIpair2 = [e2p, e2m, intensity]
            
            # Calculate fields
            ef1 = TI.get_field(TIpair1, leadfield, idx_lf)
            ef2 = TI.get_field(TIpair2, leadfield, idx_lf)
            
            # Calculate TI_max
            TImax = TI.get_maxTI(ef1, ef2)
            
            # Create output mesh
            mout = copy.deepcopy(mesh)
            mout.add_element_field(TImax, "TImax")
            
            # Save mesh
            mesh_filename = os.path.join(output_dir, f"TI_field_{e1p}_{e1m}_and_{e2p}_{e2m}.msh")
            mesh_io.write_msh(mout, mesh_filename)
            
            # Create optimized view
            try:
                v = mout.view(
                    visible_tags=[1, 2, 1006],
                    visible_fields="TImax",
                )
                v.write_opt(mesh_filename)
            except Exception as view_error:
                # Non-critical error - continue without optimized view
                logger.warning(f"Could not create optimized view: {view_error}")
            
            completed_count += 1
            
            # Progress tracking with ETA
            elapsed_time = time.time() - start_time
            avg_time = elapsed_time / completed_count
            eta_seconds = avg_time * (total_combinations - completed_count)
            eta_str = f"{eta_seconds/60:.1f}m" if eta_seconds > 60 else f"{eta_seconds:.1f}s"
            
            progress_str = f"{completed_count:03}/{total_combinations}"
            logger.info(f"Completed {progress_str} - {e1p}_{e1m}_and_{e2p}_{e2m} - ETA: {eta_str}")
            
        except Exception as e:
            failed_count += 1
            logger.error(f"Failed: {e1p}_{e1m}_and_{e2p}_{e2m} - Error: {str(e)}")
            continue
    
    # Summary
    total_time = time.time() - start_time
    logger.info("========================================")
    logger.info("TI simulation completed")
    logger.info(f"  Successful: {completed_count}/{total_combinations}")
    if failed_count > 0:
        logger.warning(f"  Failed: {failed_count}/{total_combinations}")
    logger.info(f"  Total time: {total_time/60:.1f} minutes")
    if completed_count > 0:
        logger.info(f"  Average time per simulation: {total_time/completed_count:.1f} seconds")
    logger.info("========================================")

if __name__ == "__main__":
    # Check for required environment variables
    project_dir = os.getenv('PROJECT_DIR_NAME')
    subject_name = os.getenv('SUBJECT_NAME')
    if not project_dir or not subject_name:
        print("Error: PROJECT_DIR_NAME and SUBJECT_NAME environment variables must be set")
        sys.exit(1)
    
    # Construct the full project path
    project_dir = f"/mnt/{project_dir}"
    
    # Initialize logger
    # Check if log file path is provided through environment variable (from GUI)
    shared_log_file = os.environ.get('TI_LOG_FILE')
    
    if shared_log_file:
        # Use shared log file and shared logger name for unified logging
        logger_name = 'Ex-Search'
        log_file = shared_log_file
        
        # When running from GUI, create a file-only logger to avoid console output
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.propagate = False
        
        # Remove any existing handlers
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
        
        # Add only file handler (no console handler) when running from GUI
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(file_handler)
    else:
        # CLI usage: create individual log file with both console and file output
        logger_name = 'TI-Sim'
        time_stamp = time.strftime('%Y%m%d_%H%M%S')
        log_file = f'ti_sim_{time_stamp}.log'
        logger = logging_util.get_logger(logger_name, log_file, overwrite=False)

    # Configure SimNIBS related loggers to use our logging setup
    logging_util.configure_external_loggers(['simnibs', 'mesh_io'], logger)
    
    logger.info("TI Simulation (SimNIBS Compatible)")
    logger.info(f"Subject: {subject_name}")
    logger.info(f"Project Directory: {project_dir}")
    
    # Get electrode lists from user input
    E1_plus = get_electrode_list("Enter electrodes for E1_plus separated by spaces or commas: ")
    E1_minus = get_electrode_list("Enter electrodes for E1_minus separated by spaces or commas: ")
    E2_plus = get_electrode_list("Enter electrodes for E2_plus separated by spaces or commas: ")
    E2_minus = get_electrode_list("Enter electrodes for E2_minus separated by spaces or commas: ")
    
    # Get intensity (keeping the 1mA default)
    intensity = get_intensity("Stimulation intensity in mA")
    
    logger.info("Configuration Summary:")
    logger.info(f"  E1_plus: {E1_plus}")
    logger.info(f"  E1_minus: {E1_minus}")
    logger.info(f"  E2_plus: {E2_plus}")
    logger.info(f"  E2_minus: {E2_minus}")
    logger.info(f"  Stimulation Current: {intensity*1000} mA ({intensity} A)")
    
    # Start sequential processing (SimNIBS compatible)
    process_leadfield("vol", E1_plus, E1_minus, E2_plus, E2_minus, 
                     intensity, project_dir, subject_name)

