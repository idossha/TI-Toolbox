#!/usr/bin/env simnibs_python

# Standard library imports
import csv
import json
import os
import re
import signal
import sys
import time

# Third-party imports
from simnibs.utils import TI_utils as TI

# Add project root to path (ti-toolbox directory)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Local imports
from tools import logging_util
from core import get_path_manager
from opt.roi import ROICoordinateHelper
from opt.ti_calculations import (
    find_roi_element_indices,
    find_grey_matter_indices,
    calculate_roi_metrics
)

# Define color variables
BOLD = '\033[1m'
UNDERLINE = '\033[4m'
RESET = '\033[0m'
RED = '\033[0;31m'     # Red for errors
GREEN = '\033[0;32m'   # Green for success messages and prompts
CYAN = '\033[0;36m'    # Cyan for actions being performed
BOLD_CYAN = '\033[1;36m'
YELLOW = '\033[0;33m'  # Yellow for warnings

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

def process_leadfield(E1_plus, E1_minus, E2_plus, E2_minus, subject_name):
    """Process leadfield and run TI simulations using fast in-memory approach."""
    # Hardcoded intensity: 1mA = 0.001A
    intensity = 0.001  # 1mA in Amperes
    
    # Get environment variables
    selected_net = os.getenv('SELECTED_EEG_NET')
    leadfield_hdf = os.getenv('LEADFIELD_HDF')
    roi_name = os.getenv('ROI_NAME')
    
    # Validate required environment variables
    if not selected_net:
        logger.error("SELECTED_EEG_NET environment variable not set")
        sys.exit(1)
    if not leadfield_hdf or not os.path.exists(leadfield_hdf):
        logger.error(f"Leadfield file not found: {leadfield_hdf}")
        sys.exit(1)
    if not roi_name:
        logger.error("ROI_NAME environment variable not set")
        sys.exit(1)
    
    logger.info(f"Using leadfield: {selected_net}")
    logger.info(f"Leadfield file: {leadfield_hdf}")
    logger.info(f"ROI: {roi_name}")
    logger.info(f"Intensity: 1.0 mA (0.001 A)")
    
    # Setup output directory
    pm = get_path_manager()
    subject_dir = pm.get_subject_dir(subject_name)
    output_dir_name = f"{roi_name}_{selected_net}"
    ex_search_dir = pm.get_ex_search_dir(subject_name)
    output_dir = os.path.join(ex_search_dir, output_dir_name)
    logger.info(f"Output directory: {output_dir}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Load leadfield

    logger.info(f"Loading leadfield matrix from: {leadfield_hdf}")
    logger.info("This may take several minutes for large leadfield matrices...")
    start_load_time = time.time()
    leadfield, mesh, idx_lf = TI.load_leadfield(leadfield_hdf)
    load_time = time.time() - start_load_time
    logger.info(f"Leadfield loaded successfully in {load_time:.1f} seconds")
 
    
    # Load ROI coordinates
    m2m_dir = pm.get_m2m_dir(subject_name)
    roi_dir = os.path.join(m2m_dir, 'ROIs')
    roi_file = os.path.join(roi_dir, f"{roi_name}.csv")
    
    if not os.path.exists(roi_file):
        logger.error(f"ROI file not found: {roi_file}")
        return
    
    roi_coords = ROICoordinateHelper.load_roi_from_csv(roi_file)
    if roi_coords is None:
        logger.error(f"Could not load ROI coordinates from {roi_file}")
        return
    
    if hasattr(roi_coords, 'tolist'):
        roi_coords = roi_coords.tolist()
    
    logger.info(f"ROI coordinates: {roi_coords}")
    
    # Get ROI radius from environment variable (default 3.0mm)
    roi_radius = float(os.getenv('ROI_RADIUS', '3.0'))
    
    # Find ROI element indices for fast extraction
    logger.info(f"Finding ROI elements in mesh (radius={roi_radius}mm)...")
    roi_indices, roi_volumes = find_roi_element_indices(mesh, roi_coords, radius=roi_radius)
    logger.info(f"Found {len(roi_indices)} elements within {roi_radius}mm ROI")
    
    # Find grey matter indices for focality calculation
    logger.info("Finding grey matter elements for focality...")
    gm_indices, gm_volumes = find_grey_matter_indices(mesh, grey_matter_tags=[2])
    logger.info(f"Found {len(gm_indices)} grey matter elements")
    
    # Calculate total combinations
    total_combinations = len(E1_plus) * len(E1_minus) * len(E2_plus) * len(E2_minus)
    logger.info(f"\n{'='*80}")
    logger.info(f"Starting TI Calculations")
    logger.info(f"{'='*80}")
    logger.info(f"Total montage combinations: {total_combinations}")
    logger.info(f"E1+ electrodes: {len(E1_plus)}")
    logger.info(f"E1- electrodes: {len(E1_minus)}")
    logger.info(f"E2+ electrodes: {len(E2_plus)}")
    logger.info(f"E2- electrodes: {len(E2_minus)}")
    logger.info(f"Intensity: {intensity*1000} mA")
    logger.info(f"{'='*80}\n")
    
    # Setup signal handler for graceful termination
    stop_flag = {"value": False}
    
    def signal_handler(signum, frame):
        logger.warning("\nReceived interrupt signal. Finishing current simulation...")
        stop_flag["value"] = True
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Track progress
    processed = 0
    start_time = time.time()
    
    # Store results for all montages
    all_results = {}
    
    # Process combinations using generator to save memory
    for e1_plus in E1_plus:
        if stop_flag["value"]:
            break
        for e1_minus in E1_minus:
            if stop_flag["value"]:
                break
            for e2_plus in E2_plus:
                if stop_flag["value"]:
                    break
                for e2_minus in E2_minus:
                    if stop_flag["value"]:
                        logger.warning("Stopping calculation due to interrupt signal")
                        break
                    
                    processed += 1
                    
                    # Create montage name
                    montage_name = f"{e1_plus}_{e1_minus}_and_{e2_plus}_{e2_minus}"
                    mesh_key = f"TI_field_{montage_name}.msh"
                    
                    # Progress logging
                    elapsed = time.time() - start_time
                    rate = processed / elapsed if elapsed > 0 else 0
                    remaining = (total_combinations - processed) / rate if rate > 0 else 0
                    
                    logger.info(f"[{processed}/{total_combinations}] Processing: {montage_name}")
                    logger.info(f"  Progress: {100*processed/total_combinations:.1f}% | "
                              f"Rate: {rate:.2f} montages/sec | "
                              f"ETA: {remaining/60:.1f} min")
                    
                    try:
                        # Run TI calculation using SimNIBS API (in-memory)
                        sim_start = time.time()
                        
                        # Create TI pairs
                        TIpair1 = [e1_plus, e1_minus, intensity]
                        TIpair2 = [e2_plus, e2_minus, intensity]
                        
                        # Calculate fields for entire mesh
                        ef1 = TI.get_field(TIpair1, leadfield, idx_lf)
                        ef2 = TI.get_field(TIpair2, leadfield, idx_lf)
                        
                        # Calculate TI_max for entire mesh
                        TImax_full = TI.get_maxTI(ef1, ef2)
                        
                        # Extract ROI values directly (no mesh file needed!)
                        ti_field_roi = TImax_full[roi_indices]
                        
                        # Extract grey matter values for focality
                        ti_field_gm = TImax_full[gm_indices]
                        
                        # Calculate ROI metrics including focality
                        roi_metrics = calculate_roi_metrics(
                            ti_field_roi, roi_volumes,
                            ti_field_gm=ti_field_gm, gm_volumes=gm_volumes
                        )
                        
                        sim_time = time.time() - sim_start
                        
                        # Store results
                        all_results[mesh_key] = {
                            f'{roi_name}_TImax_ROI': roi_metrics['TImax_ROI'],
                            f'{roi_name}_TImean_ROI': roi_metrics['TImean_ROI'],
                            f'{roi_name}_TImean_GM': roi_metrics.get('TImean_GM', 0.0),
                            f'{roi_name}_Focality': roi_metrics.get('Focality', 0.0),
                            f'{roi_name}_n_elements': roi_metrics['n_elements']
                        }
                        
                        logger.info(f"  Completed in {sim_time:.2f}s | "
                                  f"TImax={roi_metrics['TImax_ROI']:.4f} V/m, "
                                  f"TImean={roi_metrics['TImean_ROI']:.4f} V/m, "
                                  f"Focality={roi_metrics.get('Focality', 0.0):.4f}")
                            
                    except Exception as e:
                        logger.error(f"  Error processing {montage_name}: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                        continue
    
    # Save results directly to output directory (not in analysis/ subdirectory)
    os.makedirs(output_dir, exist_ok=True)
    
    # Save JSON results
    json_output_path = os.path.join(output_dir, 'analysis_results.json')
    with open(json_output_path, 'w') as json_file:
        json.dump(all_results, json_file, indent=4)
    logger.info(f"\nResults saved to: {json_output_path}")
    
    # Create CSV output with focality
    header = ['Montage', 'TImax_ROI', 'TImean_ROI', 'TImean_GM', 'Focality', 'n_elements']
    csv_data = [header]
    
    # Lists for histogram data
    timax_values = []
    timean_values = []
    focality_values = []
    
    for mesh_name, data in all_results.items():
        # Format montage name
        formatted_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")
        
        # Get ROI results
        ti_max_roi = data.get(f'{roi_name}_TImax_ROI', None)
        ti_mean_roi = data.get(f'{roi_name}_TImean_ROI', None)
        ti_mean_gm = data.get(f'{roi_name}_TImean_GM', None)
        focality = data.get(f'{roi_name}_Focality', None)
        n_elements = data.get(f'{roi_name}_n_elements', 0)
        
        # Format values
        ti_max_str = f"{float(ti_max_roi):.4f}" if ti_max_roi is not None else ''
        ti_mean_str = f"{float(ti_mean_roi):.4f}" if ti_mean_roi is not None else ''
        ti_mean_gm_str = f"{float(ti_mean_gm):.4f}" if ti_mean_gm is not None else ''
        focality_str = f"{float(focality):.4f}" if focality is not None else ''
        
        csv_data.append([formatted_name, ti_max_str, ti_mean_str, ti_mean_gm_str, focality_str, n_elements])
        
        # Collect for histogram
        if ti_max_roi is not None:
            timax_values.append(ti_max_roi)
        if ti_mean_roi is not None:
            timean_values.append(ti_mean_roi)
        if focality is not None:
            focality_values.append(focality)
    
    # Write CSV
    csv_output_path = os.path.join(output_dir, 'final_output.csv')
    with open(csv_output_path, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(csv_data)
    
    logger.info(f"CSV output created: {csv_output_path}")
    
    # Generate histogram visualizations
    if timax_values or timean_values or focality_values:
        logger.info("Generating histogram visualizations...")
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            # Create figure with 3 subplots
            fig, axes = plt.subplots(1, 3, figsize=(15, 4))
            
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
            
            # Focality histogram
            if focality_values:
                axes[2].hist(focality_values, bins=20, color='#FF9800', edgecolor='black', alpha=0.7)
                axes[2].set_xlabel('Focality (TImean_ROI/TImean_GM)', fontsize=12)
                axes[2].set_ylabel('Frequency', fontsize=12)
                axes[2].set_title('Focality Distribution', fontsize=14, fontweight='bold')
                axes[2].grid(axis='y', alpha=0.3)
            
            plt.tight_layout()
            
            # Save histogram
            histogram_path = os.path.join(output_dir, 'montage_distributions.png')
            plt.savefig(histogram_path, dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"Histogram visualization saved: {histogram_path}")
            
        except Exception as e:
            logger.warning(f"Could not generate histogram: {e}")
    
    # Final summary
    total_time = time.time() - start_time
    logger.info(f"\n{'='*80}")
    logger.info(f"Calculation Summary")
    logger.info(f"{'='*80}")
    logger.info(f"Processed: {processed}/{total_combinations} montages")
    logger.info(f"Total time: {total_time/60:.1f} minutes")
    logger.info(f"Average time: {total_time/processed:.2f} seconds per montage")
    logger.info(f"Output: {output_dir}")
    logger.info(f"{'='*80}")
    logger.info("Ex-search completed successfully!")

def main():
    """Main function."""
    global logger
    
    # Get environment variables
    project_dir = os.getenv('PROJECT_DIR')
    subject_name = os.getenv('SUBJECT_NAME')
    
    if not project_dir or not subject_name:
        print(f"{RED}Error: PROJECT_DIR and SUBJECT_NAME environment variables must be set{RESET}")
        sys.exit(1)
    
    # Initialize logger
    shared_log_file = os.environ.get('TI_LOG_FILE')
    if shared_log_file:
        log_file = shared_log_file
        logger = logging_util.get_logger('ti_sim', log_file, overwrite=False)
    else:
        logger_name = 'TI-Sim'
        time_stamp = time.strftime('%Y%m%d_%H%M%S')
        log_file = f'ti_sim_{time_stamp}.log'
        logger = logging_util.get_logger(logger_name, log_file, overwrite=False)
    
    # Configure external loggers
    logging_util.configure_external_loggers(['simnibs'], logger)
    
    logger.info("="*80)
    logger.info("TI Exhaustive Search - Simulation Module")
    logger.info("="*80)
    logger.info(f"Project: {project_dir}")
    logger.info(f"Subject: {subject_name}")
    logger.info("")
    
    # Get electrode lists from stdin
    print(f"\n{BOLD_CYAN}=== TI Electrode Configuration ==={RESET}")
    print(f"{CYAN}Please enter electrode lists for each channel{RESET}")
    print(f"{CYAN}Intensity: 1.0 mA (fixed){RESET}\n")
    
    E1_plus = get_electrode_list("E1+ electrodes (space or comma separated): ")
    E1_minus = get_electrode_list("E1- electrodes (space or comma separated): ")
    E2_plus = get_electrode_list("E2+ electrodes (space or comma separated): ")
    E2_minus = get_electrode_list("E2- electrodes (space or comma separated): ")
    
    # Process leadfield and run simulations
    process_leadfield(
        E1_plus,
        E1_minus,
        E2_plus,
        E2_minus,
        subject_name
    )

if __name__ == "__main__":
    main()

