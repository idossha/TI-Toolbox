#!/usr/bin/env simnibs_python

# Standard library imports
import csv
import json
import os
import re
import signal
import sys
import time
from itertools import product

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
BOLD_CYAN = '\033[1;36m'
CYAN = '\033[0;36m'
RED = '\033[0;31m'
RESET = '\033[0m'

def get_electrode_list(prompt):
    """Get user input for electrode lists with validation."""
    pattern = re.compile(r'^[A-Za-z][A-Za-z0-9]*$')
    while True:
        electrodes = input(f"[INPUT] {prompt}").strip().replace(',', ' ').split()
        if all(pattern.match(e) for e in electrodes):
            logger.info(f"Electrode list accepted: {electrodes}")
            return electrodes
        logger.error("Invalid input. Please enter valid electrode names, e.g., E001, Fp1, F3, C4")

def validate_environment():
    """Validate and return required environment variables."""
    selected_net = os.getenv('SELECTED_EEG_NET')
    leadfield_hdf = os.getenv('LEADFIELD_HDF')
    roi_name = os.getenv('ROI_NAME')
    
    if not selected_net:
        logger.error("SELECTED_EEG_NET environment variable not set")
        sys.exit(1)
    if not leadfield_hdf or not os.path.exists(leadfield_hdf):
        logger.error(f"Leadfield file not found: {leadfield_hdf}")
        sys.exit(1)
    if not roi_name:
        logger.error("ROI_NAME environment variable not set")
        sys.exit(1)
    
    return selected_net, leadfield_hdf, roi_name

def generate_current_ratios(total_current, current_step, channel_limit):
    """Generate valid current ratio combinations."""
    ratios = []
    epsilon = current_step * 0.01
    min_current = max(total_current - channel_limit, current_step)
    
    if min_current < current_step - epsilon:
        min_current = current_step
        logger.warning(f"Channel limit ({channel_limit} mA) exceeds total current ({total_current} mA).")
    
    current_ch1 = channel_limit
    while current_ch1 >= min_current - epsilon:
        current_ch2 = total_current - current_ch1
        if (current_ch1 <= channel_limit + epsilon and 
            current_ch2 <= channel_limit + epsilon and
            current_ch1 >= current_step - epsilon and 
            current_ch2 >= current_step - epsilon):
            ratios.append((current_ch1, current_ch2))
        current_ch1 -= current_step
    
    return ratios

def process_leadfield(E1_plus, E1_minus, E2_plus, E2_minus, subject_name, total_current, current_step, channel_limit=None):
    """Process leadfield and run TI simulations using fast in-memory approach."""
    
    # Validate environment and get parameters
    selected_net, leadfield_hdf, roi_name = validate_environment()
    
    # Set default channel limit
    if channel_limit is None:
        channel_limit = total_current / 2.0
        logger.info(f"No channel limit specified, using default: {channel_limit} mA (total_current/2)")
    
    # Log configuration
    logger.info(f"Using leadfield: {selected_net}")
    logger.info(f"Leadfield file: {leadfield_hdf}")
    logger.info(f"ROI: {roi_name}")
    logger.info(f"Total current: {total_current} mA ({total_current/1000} A)")
    logger.info(f"Current step: {current_step} mA")
    logger.info(f"Channel limit: {channel_limit} mA")
    
    # Setup output directory
    pm = get_path_manager()
    output_dir = os.path.join(pm.get_ex_search_dir(subject_name), f"{roi_name}_{selected_net}")
    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")
    
    # Load leadfield
    logger.info(f"Loading leadfield matrix from: {leadfield_hdf}")
    logger.info("This may take several minutes for large leadfield matrices...")
    start_load_time = time.time()
    leadfield, mesh, idx_lf = TI.load_leadfield(leadfield_hdf)
    logger.info(f"Leadfield loaded successfully in {time.time() - start_load_time:.1f} seconds")
    
    # Load ROI coordinates
    roi_file = os.path.join(pm.get_m2m_dir(subject_name), 'ROIs', f"{roi_name}.csv")
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
    
    # Find ROI and grey matter elements
    roi_radius = float(os.getenv('ROI_RADIUS', '3.0'))
    logger.info(f"Finding ROI elements in mesh (radius={roi_radius}mm)...")
    roi_indices, roi_volumes = find_roi_element_indices(mesh, roi_coords, radius=roi_radius)
    logger.info(f"Found {len(roi_indices)} elements within {roi_radius}mm ROI")
    
    logger.info("Finding grey matter elements for focality...")
    gm_indices, gm_volumes = find_grey_matter_indices(mesh, grey_matter_tags=[2])
    logger.info(f"Found {len(gm_indices)} grey matter elements")
    
    # Generate current ratios
    current_ratios = generate_current_ratios(total_current, current_step, channel_limit)
    logger.info(f"Generated {len(current_ratios)} current ratio combinations")
    logger.info(f"Current ratios (Ch1, Ch2) in mA: {current_ratios}")
    
    # Calculate total combinations
    total_combinations = len(E1_plus) * len(E1_minus) * len(E2_plus) * len(E2_minus) * len(current_ratios)
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Starting TI Calculations")
    logger.info(f"{'='*80}")
    logger.info(f"Total combinations: {total_combinations}")
    logger.info(f"E1+: {len(E1_plus)}, E1-: {len(E1_minus)}, E2+: {len(E2_plus)}, E2-: {len(E2_minus)}")
    logger.info(f"Current ratios: {len(current_ratios)}")
    logger.info(f"{'='*80}\n")
    
    # Setup signal handler for graceful termination
    stop_flag = {"value": False}
    signal.signal(signal.SIGINT, lambda s, f: stop_flag.update({"value": True}))
    signal.signal(signal.SIGTERM, lambda s, f: stop_flag.update({"value": True}))
    
    # Process all combinations using itertools.product
    all_results = {}
    start_time = time.time()
    
    for processed, (e1_plus, e1_minus, e2_plus, e2_minus, (current_ch1_mA, current_ch2_mA)) in \
            enumerate(product(E1_plus, E1_minus, E2_plus, E2_minus, current_ratios), 1):
        
        if stop_flag["value"]:
            logger.warning("Stopping calculation due to interrupt signal")
            break
        
        # Create montage name
        montage_name = f"{e1_plus}_{e1_minus}_and_{e2_plus}_{e2_minus}_I1-{current_ch1_mA:.1f}mA_I2-{current_ch2_mA:.1f}mA"
        mesh_key = f"TI_field_{montage_name}.msh"
        
        # Progress logging
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total_combinations - processed) / rate if rate > 0 else 0
        
        logger.info(f"[{processed}/{total_combinations}] Processing: {montage_name}")
        logger.info(f"  Progress: {100*processed/total_combinations:.1f}% | "
                  f"Rate: {rate:.2f} montages/sec | ETA: {eta/60:.1f} min")
        
        try:
            sim_start = time.time()
            
            # Calculate TI fields (convert mA to A)
            ef1 = TI.get_field([e1_plus, e1_minus, current_ch1_mA/1000], leadfield, idx_lf)
            ef2 = TI.get_field([e2_plus, e2_minus, current_ch2_mA/1000], leadfield, idx_lf)
            TImax_full = TI.get_maxTI(ef1, ef2)
            
            # Calculate ROI metrics
            roi_metrics = calculate_roi_metrics(
                TImax_full[roi_indices], roi_volumes,
                ti_field_gm=TImax_full[gm_indices], gm_volumes=gm_volumes
            )
            
            # Store results
            all_results[mesh_key] = {
                f'{roi_name}_TImax_ROI': roi_metrics['TImax_ROI'],
                f'{roi_name}_TImean_ROI': roi_metrics['TImean_ROI'],
                f'{roi_name}_TImean_GM': roi_metrics.get('TImean_GM', 0.0),
                f'{roi_name}_Focality': roi_metrics.get('Focality', 0.0),
                f'{roi_name}_n_elements': roi_metrics['n_elements'],
                'current_ch1_mA': current_ch1_mA,
                'current_ch2_mA': current_ch2_mA
            }
            
            logger.info(f"  Completed in {time.time()-sim_start:.2f}s | "
                      f"I1={current_ch1_mA:.1f}mA, I2={current_ch2_mA:.1f}mA | "
                      f"TImax={roi_metrics['TImax_ROI']:.4f} V/m, "
                      f"TImean={roi_metrics['TImean_ROI']:.4f} V/m, "
                      f"Focality={roi_metrics.get('Focality', 0.0):.4f}")
                
        except Exception as e:
            logger.error(f"  Error processing {montage_name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    # Save JSON results
    json_output_path = os.path.join(output_dir, 'analysis_results.json')
    with open(json_output_path, 'w') as f:
        json.dump(all_results, f, indent=4)
    logger.info(f"\nResults saved to: {json_output_path}")
    
    # Create CSV output (including composite intensity–focality index)
    csv_data = [['Montage', 'Current_Ch1_mA', 'Current_Ch2_mA',
                 'TImax_ROI', 'TImean_ROI', 'TImean_GM',
                 'Focality', 'Composite_Index', 'n_elements']]
    timax_values, timean_values, focality_values = [], [], []
    composite_values = []
    
    for mesh_name, data in all_results.items():
        formatted_name = re.sub(r"TI_field_(.*?)\.msh", r"\1", mesh_name).replace("_and_", " <> ")
        
        ti_max = data.get(f'{roi_name}_TImax_ROI')
        ti_mean = data.get(f'{roi_name}_TImean_ROI')
        ti_mean_gm = data.get(f'{roi_name}_TImean_GM')
        focality = data.get(f'{roi_name}_Focality')

        # Composite metric: focality-weighted intensity at target
        composite_index = None
        if ti_mean is not None and focality is not None:
            composite_index = ti_mean * focality
        
        csv_data.append([
            formatted_name,
            f"{data.get('current_ch1_mA', 0):.1f}",
            f"{data.get('current_ch2_mA', 0):.1f}",
            f"{ti_max:.4f}" if ti_max is not None else '',
            f"{ti_mean:.4f}" if ti_mean is not None else '',
            f"{ti_mean_gm:.4f}" if ti_mean_gm is not None else '',
            f"{focality:.4f}" if focality is not None else '',
            f"{composite_index:.4f}" if composite_index is not None else '',
            data.get(f'{roi_name}_n_elements', 0)
        ])
        
        # Collect histogram data
        if ti_max is not None:
            timax_values.append(ti_max)
        if ti_mean is not None:
            timean_values.append(ti_mean)
        if focality is not None:
            focality_values.append(focality)
        if composite_index is not None:
            composite_values.append(composite_index)
    
    # Write CSV
    csv_output_path = os.path.join(output_dir, 'final_output.csv')
    with open(csv_output_path, 'w', newline='') as f:
        csv.writer(f).writerows(csv_data)
    logger.info(f"CSV output created: {csv_output_path}")
    
    # Generate histogram and scatter visualizations
    if timax_values or timean_values or focality_values:
        logger.info("Generating histogram and scatter visualizations...")
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
            
            # Histograms: TImax, TImean, Focality
            fig, axes = plt.subplots(1, 3, figsize=(15, 4))
            hist_configs = [
                (timax_values, axes[0], 'TImax (V/m)', 'TImax Distribution', '#2196F3'),
                (timean_values, axes[1], 'TImean (V/m)', 'TImean Distribution', '#4CAF50'),
                (focality_values, axes[2], 'Focality (TImean_ROI/TImean_GM)', 'Focality Distribution', '#FF9800')
            ]
            
            for values, ax, xlabel, title, color in hist_configs:
                if values:
                    ax.hist(values, bins=20, color=color, edgecolor='black', alpha=0.7)
                    ax.set_xlabel(xlabel, fontsize=12)
                    ax.set_ylabel('Frequency', fontsize=12)
                    ax.set_title(title, fontsize=14, fontweight='bold')
                    ax.grid(axis='y', alpha=0.3)
            
            plt.tight_layout()
            histogram_path = os.path.join(output_dir, 'montage_distributions.png')
            plt.savefig(histogram_path, dpi=300, bbox_inches='tight')
            plt.close()
            logger.info(f"Histogram visualization saved: {histogram_path}")

            # Scatter plot: intensity vs focality, colored by composite index
            # Reconstruct aligned lists from all_results to avoid any length mismatch
            scatter_intensity, scatter_focality, scatter_composite = [], [], []
            for data in all_results.values():
                ti_mean = data.get(f'{roi_name}_TImean_ROI')
                focality = data.get(f'{roi_name}_Focality')
                comp = None
                if ti_mean is not None and focality is not None:
                    comp = ti_mean * focality
                if ti_mean is not None and focality is not None:
                    scatter_intensity.append(ti_mean)
                    scatter_focality.append(focality)
                    scatter_composite.append(comp)

            if scatter_intensity and scatter_focality:
                fig2, ax = plt.subplots(figsize=(6, 5))
                if any(c is not None for c in scatter_composite):
                    sc = ax.scatter(
                        scatter_intensity,
                        scatter_focality,
                        c=scatter_composite,
                        cmap='viridis',
                        s=40,
                        edgecolor='black',
                        alpha=0.7
                    )
                    cbar = plt.colorbar(sc, ax=ax)
                    cbar.set_label('Composite Index (TImean_ROI × Focality)', fontsize=12)
                else:
                    ax.scatter(
                        scatter_intensity,
                        scatter_focality,
                        s=40,
                        edgecolor='black',
                        alpha=0.7
                    )

                ax.set_xlabel('TImean_ROI (V/m)', fontsize=12)
                ax.set_ylabel('Focality (TImean_ROI/TImean_GM)', fontsize=12)
                ax.set_title('Intensity vs Focality', fontsize=14, fontweight='bold')
                ax.grid(alpha=0.3)

                scatter_path = os.path.join(output_dir, 'intensity_vs_focality_scatter.png')
                plt.tight_layout()
                plt.savefig(scatter_path, dpi=300, bbox_inches='tight')
                plt.close()
                logger.info(f"Scatter visualization saved: {scatter_path}")
        except Exception as e:
            logger.warning(f"Could not generate visualizations: {e}")
    
    # Final summary
    total_time = time.time() - start_time
    logger.info(f"\n{'='*80}")
    logger.info(f"Calculation Summary")
    logger.info(f"{'='*80}")
    logger.info(f"Processed: {processed}/{total_combinations} montages")
    logger.info(f"Total time: {total_time/60:.1f} minutes ({total_time/processed:.2f}s per montage)")
    logger.info(f"Output: {output_dir}")
    logger.info(f"{'='*80}")
    logger.info("Ex-search completed successfully!")

def get_current_parameter(name, default, validation_fn=None):
    """Get current parameter from stdin, environment, or use default."""
    # Try stdin first
    try:
        import select
        if select.select([sys.stdin], [], [], 0.0)[0]:
            value_str = input().strip()
            if value_str:
                value = float(value_str)
                if validation_fn is None or validation_fn(value):
                    logger.info(f"{name} set from stdin: {value}")
                    return value
    except:
        pass
    
    # Try environment variable
    env_value = os.getenv(name.upper().replace(' ', '_'))
    if env_value:
        try:
            value = float(env_value)
            if validation_fn is None or validation_fn(value):
                logger.info(f"{name} set from environment: {value}")
                return value
        except ValueError:
            logger.warning(f"Invalid {name} in environment: {env_value}")
    
    # Use default
    logger.info(f"{name} using default: {default}")
    return default

def main():
    """Main function."""
    global logger
    
    # Validate required environment variables
    project_dir = os.getenv('PROJECT_DIR')
    subject_name = os.getenv('SUBJECT_NAME')
    if not project_dir or not subject_name:
        print(f"{RED}Error: PROJECT_DIR and SUBJECT_NAME environment variables must be set{RESET}")
        sys.exit(1)
    
    # Initialize logger
    log_file = os.environ.get('TI_LOG_FILE') or f'ti_sim_{time.strftime("%Y%m%d_%H%M%S")}.log'
    logger = logging_util.get_logger('ti_sim', log_file, overwrite=False)
    logging_util.configure_external_loggers(['simnibs'], logger)
    
    logger.info("="*80)
    logger.info("TI Exhaustive Search - Simulation Module")
    logger.info("="*80)
    logger.info(f"Project: {project_dir}")
    logger.info(f"Subject: {subject_name}")
    logger.info("")
    
    # Get electrode lists
    print(f"\n{BOLD_CYAN}=== TI Electrode Configuration ==={RESET}")
    print(f"{CYAN}Please enter electrode lists for each channel{RESET}\n")

    E1_plus = get_electrode_list("E1+ electrodes (space or comma separated): ")
    E1_minus = get_electrode_list("E1- electrodes (space or comma separated): ")
    E2_plus = get_electrode_list("E2+ electrodes (space or comma separated): ")
    E2_minus = get_electrode_list("E2- electrodes (space or comma separated): ")

    # Get current parameters
    print(f"\n{BOLD_CYAN}=== Current Configuration ==={RESET}")
    print(f"{CYAN}The optimizer will test different current ratios for each electrode configuration{RESET}")
    print(f"{CYAN}Example: For total_current=2.0mA, step=0.2mA, channel_limit=1.6mA:{RESET}")
    print(f"{CYAN}  - Ch1: 1.6mA, Ch2: 0.4mA{RESET}")
    print(f"{CYAN}  - Ch1: 1.4mA, Ch2: 0.6mA{RESET}")
    print(f"{CYAN}  - Ch1: 1.2mA, Ch2: 0.8mA{RESET}")
    print(f"{CYAN}  - ... down to Ch1: 0.4mA, Ch2: 1.6mA{RESET}\n")
    
    total_current = get_current_parameter('total_current', 1.0, lambda x: x > 0)
    current_step = get_current_parameter('current_step', 0.1, lambda x: 0 < x < total_current)
    channel_limit_raw = get_current_parameter('channel_limit', None)
    channel_limit = channel_limit_raw if channel_limit_raw and 0 < channel_limit_raw <= total_current else None
    
    # Process leadfield and run simulations
    process_leadfield(
        E1_plus,
        E1_minus,
        E2_plus,
        E2_minus,
        subject_name,
        total_current,
        current_step,
        channel_limit
    )

if __name__ == "__main__":
    main()

