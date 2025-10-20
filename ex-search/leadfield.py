# Standard library imports
import logging
import os
import sys
import time

from simnibs import run_simnibs, sim_struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Local imports
from tools import logging_util

# Ensure the correct number of arguments are provided
if len(sys.argv) != 4:
    print("Usage: leadfield.py <m2m_directory> <eeg_cap_path> <net_name>")
    print("Example: leadfield.py /path/to/m2m_101 /path/to/GSN-HydroCel-185.csv GSN-HydroCel-185")
    sys.exit(1)

# Get arguments from command line
m2m_dir = sys.argv[1]
eeg_cap_path = sys.argv[2]
net_name = sys.argv[3]

# Initialize logger
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    # If not provided, create a new log file (fallback behavior)
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    subject_number = os.path.basename(m2m_dir).replace('m2m_', '')
    # Navigate to derivatives directory for log placement
    subject_dir = os.path.dirname(m2m_dir)
    derivatives_dir = os.path.join(os.path.dirname(subject_dir), 'derivatives')
    log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_number}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'leadfield_{time_stamp}.log')

# Initialize our main logger
if log_file and os.environ.get('TI_LOG_FILE'):
    # When running from GUI, create a file-only logger to avoid console output
    logger = logging.getLogger('Leadfield')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    
    # Reconfigure as file-only logger when running from GUI
    logger = logging_util.get_file_only_logger('leadfield', log_file)
else:
    # CLI usage: use standard logging utility with both console and file output
    logger = logging_util.get_logger('Leadfield', log_file, overwrite=False)

# Configure SimNIBS related loggers to use our logging setup
logging_util.configure_external_loggers(['simnibs', 'mesh_io'], logger)

logger.info("Leadfield Generation")
logger.info(f"M2M Directory: {m2m_dir}")
logger.info(f"EEG Cap: {eeg_cap_path}")
logger.info(f"Net Name: {net_name}")

# Extract subject information
subject_number = os.path.basename(m2m_dir).replace('m2m_', '')
subject_dir = os.path.dirname(m2m_dir)  # This is the subject BIDS directory (e.g., sub-101)

# Verify input files exist
if not os.path.exists(m2m_dir):
    logger.error(f"M2M directory not found: {m2m_dir}")
    sys.exit(1)

if not os.path.exists(eeg_cap_path):
    logger.error(f"EEG cap file not found: {eeg_cap_path}")
    sys.exit(1)

# Function to create the leadfield matrix
def create_leadfield(m2m_dir, eeg_cap_path, net_name, suffix='vol'):
    """Create leadfield matrix with new naming scheme."""
    logger.info(f"Creating {suffix} leadfield for {net_name}")
    
    tdcs_lf = sim_struct.TDCSLEADFIELD()

    # Extract the subject number from the m2m directory
    subject_number = os.path.basename(m2m_dir).replace('m2m_', '')
    
    # Get the subject BIDS directory (parent of m2m directory)
    subject_bids_dir = os.path.dirname(m2m_dir)
    
    # Create output directory with new naming scheme: leadfield_vol_{net_name}
    output_dir = os.path.join(subject_bids_dir, f"leadfield_{suffix}_{net_name}")
    
    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        logger.info(f"Created output directory: {output_dir}")
    
    # Set up simulation parameters
    tdcs_lf.subpath = m2m_dir  # m2m directory path
    tdcs_lf.pathfem = output_dir  # output directory
    tdcs_lf.eeg_cap = eeg_cap_path  # full path to EEG cap file

    # Electrode configuration
    electrode = tdcs_lf.electrode
    electrode.dimensions = [8, 8]  # in mm
    electrode.shape = "ellipse"  # shape
    electrode.thickness = [4, 4]  # arg1=gel_thickness , arg2=electrode_thickness

    # Set leadfield-specific parameters
    tdcs_lf.interpolation = None  # No interpolation for volumetric data
    tdcs_lf.tissues = list(range(1, 16))  # All tissues

    # Optionally enable the faster pardiso solver if memory allows
    # tdcs_lf.solver_options = "pardiso"

    logger.info("Starting SimNIBS leadfield calculation...")
    start_time = time.time()
    
    # Run the simulation
    run_simnibs(tdcs_lf)
    
    calculation_time = time.time() - start_time
    logger.info(f"Leadfield calculation completed in {calculation_time/60:.1f} minutes")

    # Check if the leadfield was created and rename to standard name
    # SimNIBS creates: {subject_number}_leadfield_{net_name_without_extension}.hdf5
    # We want: leadfield.hdf5
    
    # Remove extension from EEG cap filename
    eeg_cap_basename = os.path.splitext(os.path.basename(eeg_cap_path))[0]
    original_name = f"{subject_number}_leadfield_{eeg_cap_basename}.hdf5"
    original_hdf5 = os.path.join(output_dir, original_name)
    target_hdf5 = os.path.join(output_dir, "leadfield.hdf5")
    
    if os.path.exists(original_hdf5):
        # Rename to standard name
        os.rename(original_hdf5, target_hdf5)
        logger.info(f"Renamed leadfield file to: leadfield.hdf5")
    else:
        logger.error(f"Expected leadfield file not found: {original_hdf5}")
        return False
    
    # Verify final file exists
    if os.path.exists(target_hdf5):
        file_size = os.path.getsize(target_hdf5) / (1024**3)  # Size in GB
        logger.info(f"Leadfield file created successfully: {target_hdf5}")
        logger.info(f"File size: {file_size:.2f} GB")
        return True
    else:
        logger.error(f"Final leadfield file not found: {target_hdf5}")
        return False

# Create the volumetric leadfield
logger.info("Starting leadfield matrix creation")
if create_leadfield(m2m_dir, eeg_cap_path, net_name, suffix='vol'):
    logger.info("Leadfield matrix creation completed successfully")
else:
    logger.error("Leadfield matrix creation failed")
    sys.exit(1)

