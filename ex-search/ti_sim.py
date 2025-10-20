#!/usr/bin/env python3

# Standard library imports
import copy
import csv
import logging
import os
import re
import signal
import sys
import time
from itertools import product

# Third-party imports
import numpy as np
from simnibs import mesh_io
from simnibs.utils import TI_utils as TI

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Local imports
from tools import logging_util

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

def get_memory_usage():
    """Get current memory usage in MB."""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        return memory_info.rss / 1024 / 1024  # Convert to MB
    except ImportError:
        # Fallback if psutil is not available
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Convert to MB

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

def signal_handler(signum, frame):
    """Handle termination signals gracefully."""
    logger.warning(f"Received signal {signum}. Attempting graceful shutdown...")
    sys.exit(1)

def process_leadfield(leadfield_type, E1_plus, E1_minus, E2_plus, E2_minus, 
                     intensity, project_dir, subject_name):
    """Process leadfield with sequential execution (SimNIBS-compatible)."""
    # Set up signal handlers for graceful termination
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
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
    
    # Create output directory (will be empty if GUI deleted it after user confirmation)
    os.makedirs(output_dir, exist_ok=True)
    logger.info("Output directory ready")
    
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
    
    # Calculate total combinations without generating all at once
    total_combinations = len(E1_plus) * len(E1_minus) * len(E2_plus) * len(E2_minus)
    
    logger.info(f"Starting sequential TI simulations for {total_combinations} combinations")
    logger.info("Note: Using sequential processing for SimNIBS compatibility")
    logger.info(f"Expected combinations: E1_plus({len(E1_plus)}) × E1_minus({len(E1_minus)}) × E2_plus({len(E2_plus)}) × E2_minus({len(E2_minus)}) = {total_combinations}")
    
    # Determine batch size based on available memory and combination count
    # Use smaller batches for large combination sets to manage memory
    if total_combinations <= 100:
        initial_batch_size = total_combinations  # Process all at once for small sets
    elif total_combinations <= 1000:
        initial_batch_size = 50  # Medium batches for moderate sets
    else:
        initial_batch_size = 25  # Small batches for large sets
    
    # Check available memory and adjust batch size accordingly
    try:
        initial_memory = get_memory_usage()
        logger.info(f"Initial memory usage: {initial_memory:.1f} MB")
        
        # If memory is already high, use smaller batches
        if initial_memory > 8000:  # 8GB
            initial_batch_size = max(10, initial_batch_size // 4)
            logger.info("High memory usage detected, reducing batch size")
        elif initial_memory > 4000:  # 4GB
            initial_batch_size = max(15, initial_batch_size // 2)
            logger.info("Moderate memory usage detected, reducing batch size")
    except Exception:
        logger.debug("Could not determine memory usage, using default batch size")
    
    batch_size = initial_batch_size
    logger.info(f"Using batch processing with batch size: {batch_size}")
    logger.info(f"Total batches needed: {(total_combinations + batch_size - 1) // batch_size}")
    
    # Process combinations in batches to manage memory
    start_time = time.time()
    completed_count = 0
    failed_count = 0
    current_batch = 0
    
    # Process combinations in batches using itertools.product directly
    combination_generator = product(
        product(E1_plus, E1_minus),
        product(E2_plus, E2_minus)
    )
    
    # Log first few combinations for verification
    logger.info("First 5 combinations to be processed:")
    temp_gen = product(product(E1_plus, E1_minus), product(E2_plus, E2_minus))
    for i, ((e1p, e1m), (e2p, e2m)) in enumerate(temp_gen):
        if i >= 5:
            break
        logger.info(f"  {i+1}: {e1p}-{e1m} and {e2p}-{e2m}")
    if total_combinations > 5:
        logger.info(f"  ... and {total_combinations - 5} more combinations")
    
    # Process combinations in memory-efficient batches
    batch_combinations = []
    global_index = 0
    
    for ((e1p, e1m), (e2p, e2m)) in combination_generator:
        batch_combinations.append(((e1p, e1m), (e2p, e2m)))
        global_index += 1
        
        # Process batch when it's full or we've reached the end
        if len(batch_combinations) >= batch_size or global_index >= total_combinations:
            current_batch += 1
            batch_start_time = time.time()
            
            logger.info(f"Processing batch {current_batch}: combinations {global_index - len(batch_combinations) + 1} to {global_index}")
            
            # Log memory usage at batch start
            try:
                memory_mb = get_memory_usage()
                logger.info(f"Batch {current_batch} starting memory usage: {memory_mb:.1f} MB")
            except Exception:
                pass
            
            # Process current batch
            for batch_index, ((e1p, e1m), (e2p, e2m)) in enumerate(batch_combinations):
                combination_index = global_index - len(batch_combinations) + batch_index + 1
                
                try:
                    logger.info(f"Processing combination {combination_index}/{total_combinations}: {e1p}-{e1m} and {e2p}-{e2m}")
                    
                    # Create TI pairs
                    TIpair1 = [e1p, e1m, intensity]
                    TIpair2 = [e2p, e2m, intensity]
                    
                    # Calculate fields with better error handling
                    try:
                        ef1 = TI.get_field(TIpair1, leadfield, idx_lf)
                        ef2 = TI.get_field(TIpair2, leadfield, idx_lf)
                    except Exception as field_error:
                        logger.error(f"Field calculation failed for {e1p}_{e1m}_and_{e2p}_{e2m}: {field_error}")
                        failed_count += 1
                        continue
                    
                    # Calculate TI_max
                    try:
                        TImax = TI.get_maxTI(ef1, ef2)
                    except Exception as ti_error:
                        logger.error(f"TI calculation failed for {e1p}_{e1m}_and_{e2p}_{e2m}: {ti_error}")
                        failed_count += 1
                        continue
                    
                    # Create output mesh
                    try:
                        mout = copy.deepcopy(mesh)
                        mout.add_element_field(TImax, "TImax")
                    except Exception as mesh_error:
                        logger.error(f"Mesh creation failed for {e1p}_{e1m}_and_{e2p}_{e2m}: {mesh_error}")
                        failed_count += 1
                        continue
                    
                    # Save mesh
                    try:
                        mesh_filename = os.path.join(output_dir, f"TI_field_{e1p}_{e1m}_and_{e2p}_{e2m}.msh")
                        mesh_io.write_msh(mout, mesh_filename)
                    except Exception as save_error:
                        logger.error(f"Mesh save failed for {e1p}_{e1m}_and_{e2p}_{e2m}: {save_error}")
                        failed_count += 1
                        continue
                    
                    # Create optimized view
                    try:
                        v = mout.view(
                            visible_tags=[1, 2, 1006],
                            visible_fields="TImax",
                        )
                        v.write_opt(mesh_filename)
                    except Exception as view_error:
                        # Non-critical error - continue without optimized view
                        logger.warning(f"Could not create optimized view for {e1p}_{e1m}_and_{e2p}_{e2m}: {view_error}")
                    
                    completed_count += 1
                    
                    # Progress tracking with ETA
                    elapsed_time = time.time() - start_time
                    avg_time = elapsed_time / completed_count
                    eta_seconds = avg_time * (total_combinations - completed_count)
                    eta_str = f"{eta_seconds/60:.1f}m" if eta_seconds > 60 else f"{eta_seconds:.1f}s"
                    
                    progress_str = f"{completed_count:03}/{total_combinations}"
                    logger.info(f"Completed {progress_str} - {e1p}_{e1m}_and_{e2p}_{e2m} - ETA: {eta_str}")
                    
                    # Force garbage collection every 10 iterations to prevent memory issues
                    if completed_count % 10 == 0:
                        import gc
                        gc.collect()
                        logger.debug(f"Memory cleanup performed at iteration {completed_count}")
                    
                    # Checkpoint logging every 25 iterations
                    if completed_count % 25 == 0:
                        logger.info(f"CHECKPOINT: Successfully completed {completed_count}/{total_combinations} combinations ({completed_count/total_combinations*100:.1f}%)")
                        logger.info(f"CHECKPOINT: Failed combinations so far: {failed_count}")
                        logger.info(f"CHECKPOINT: Average time per combination: {avg_time:.2f} seconds")
                    
                    # Clean up large objects immediately after use
                    del ef1, ef2, TImax, mout
                    
                except KeyboardInterrupt:
                    logger.warning(f"Process interrupted by user at combination {combination_index}/{total_combinations}")
                    break
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Unexpected error for {e1p}_{e1m}_and_{e2p}_{e2m}: {str(e)}")
                    logger.error(f"Exception type: {type(e).__name__}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    continue
            
            # Clean up batch and force garbage collection
            batch_time = time.time() - batch_start_time
            logger.info(f"Batch {current_batch} completed in {batch_time:.1f} seconds")
            logger.info(f"Batch {current_batch} stats: {len(batch_combinations)} combinations processed")
            
            # Log memory usage before cleanup
            try:
                memory_before = get_memory_usage()
                logger.debug(f"Batch {current_batch} memory before cleanup: {memory_before:.1f} MB")
            except Exception:
                pass
            
            # Clear batch memory and force garbage collection
            del batch_combinations
            import gc
            gc.collect()
            
            # Log memory usage after cleanup
            try:
                memory_after = get_memory_usage()
                logger.info(f"Batch {current_batch} memory after cleanup: {memory_after:.1f} MB")
            except Exception:
                pass
            
            # Reset batch for next iteration
            batch_combinations = []
    
    # Log completion of the processing loop
    logger.info(f"Processing loop completed. Processed {total_combinations} combinations in {current_batch} batches.")
    logger.info(f"Final counts: Completed={completed_count}, Failed={failed_count}")
    
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
        
        # Reconfigure as file-only logger when running from GUI
        logger = logging_util.get_file_only_logger('ti_sim', log_file)
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

