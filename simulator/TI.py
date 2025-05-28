import os
import sys
import json
from copy import deepcopy
import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI
from datetime import datetime
import time

###########################################

# Ido Haber / ihaber@wisc.edu
# October 14, 2024
# optimized for TI-CSC analyzer

# This script runs SimNIBS simulations

# Arguments:
#   1. subject_id        : The ID of the subject.
#   2. sim_type          : The type of simulation anisotropy ('scalar', 'vn', 'dir', 'mc').
#   3. project_dir       : The directory where subject-specific data is stored.
#   4. simulation_dir    : The directory where simulation results will be saved.
#   5. sim_mode          : The mode of simulation ('scalar', 'vn', 'dir', 'mc').
#   6. intensity         : The stimulation intensity in A.
#   7. electrode_shape   : The shape of the electrodes ('rect' or 'ellipse').
#   8. dimensions        : The dimensions of the electrodes (x,y in mm).
#   9. thickness        : The thickness of the electrodes in mm.
#   10. eeg_net           : The filename of the selected EEG net.
#   11+ montage_names     : A list of montage names to use for the simulation.

# Functionality:
#   - Loads the selected montages from a JSON file located in the ../utils directory relative to the subject directory.
#   - Runs the simulation for each montage and saves the resulting mesh files.
#   - Calculates and stores the maximal amplitude of the temporal interference (TI) envelope for multi-polar montages.

###########################################

# Add logging utility import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util

# Get subject ID, simulation type, and montages from command-line arguments
subject_id = sys.argv[1]
sim_type = sys.argv[2]  # The anisotropy type
project_dir = sys.argv[3]  # Changed from subject_dir to project_dir
simulation_dir = sys.argv[4]
sim_mode = sys.argv[5]  # Now explicitly parsed

# Parse intensity - now supports either single value or comma-separated pair
intensity_str = sys.argv[6]
if ',' in intensity_str:
    # If comma-separated, parse as two different intensities
    intensity1, intensity2 = map(float, intensity_str.split(','))
else:
    # If single value, use same intensity for both channels
    intensity1 = intensity2 = float(intensity_str)

electrode_shape = sys.argv[7]
dimensions = [float(x) for x in sys.argv[8].split(',')]  # Convert dimensions to list of floats
thickness = float(sys.argv[9])
eeg_net = sys.argv[10]  # Get the EEG net filename
montage_names = sys.argv[11:]  # The list of montages starts from the 12th argument

# Define the correct path for the JSON file
ti_csc_dir = os.path.join(project_dir, 'ti-csc')
config_dir = os.path.join(ti_csc_dir, 'config')
montage_file = os.path.join(config_dir, 'montage_list.json')

# Create directories if they don't exist
os.makedirs(config_dir, exist_ok=True)
os.chmod(ti_csc_dir, 0o777)
os.chmod(config_dir, 0o777)

# Create montage file if it doesn't exist
if not os.path.exists(montage_file):
    initial_content = {
        "nets": {
            "EGI_template.csv": {
                "uni_polar_montages": {},
                "multi_polar_montages": {}
            }
        }
    }
    with open(montage_file, 'w') as f:
        json.dump(initial_content, f, indent=4)
    os.chmod(montage_file, 0o777)

# Load montages from JSON file
with open(montage_file) as f:
    all_montages = json.load(f)

# Check if the net exists in the JSON
if eeg_net not in all_montages.get('nets', {}):
    print(f"Error: EEG net '{eeg_net}' not found in montage list.")
    sys.exit(1)

# Get the montages for this net
net_montages = all_montages['nets'][eeg_net]

# Check and process montages based on simulation mode
montage_type = 'uni_polar_montages' if len(sys.argv[11:]) > 0 and sys.argv[11] in net_montages.get('uni_polar_montages', {}) else 'multi_polar_montages'
montages = {name: net_montages[montage_type].get(name) for name in montage_names}

# Validate montage structure
def validate_montage(montage, montage_name):
    if not montage or len(montage) < 2 or len(montage[0]) < 2:
        print(f"Invalid montage structure for {montage_name}. Skipping.")
        return False
    return True

# Initialize logger
# Check if log file path is provided through environment variable
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    # If not provided, create a new log file (fallback behavior)
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    log_dir = os.path.join(simulation_dir, montage_names[0], 'Documentation')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'Simulator_{time_stamp}.log')

# Initialize our main logger
logger = logging_util.get_logger('TI', log_file, overwrite=False)

# Configure SimNIBS related loggers to use our logging setup
logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct'], logger)

# Base paths
derivatives_dir = os.path.join(project_dir, 'derivatives')
simnibs_dir = os.path.join(derivatives_dir, 'SimNIBS', f'sub-{subject_id}')
base_subpath = os.path.join(simnibs_dir, f'm2m_{subject_id}')
conductivity_path = base_subpath
tensor_file = os.path.join(conductivity_path, "DTI_coregT1_tensor.nii.gz")

# Create temporary directory for SimNIBS output
temp_dir = os.path.join(simulation_dir, "tmp")
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)
    logger.info(f"Created temporary directory at {temp_dir}")

# Function to run simulations
def run_simulation(montage_name, montage):
    logger.info(f"Starting simulation for montage: {montage_name}")
    
    if not validate_montage(montage, montage_name):
        logger.error(f"Invalid montage structure for {montage_name}. Skipping.")
        return

    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    
    logger.info(f"Set up SimNIBS session with anisotropy type: {sim_type}")
    
    # Use temporary directory for SimNIBS output
    S.pathfem = os.path.join(temp_dir, montage_name)
    
    # Use the selected EEG net
    S.eeg_cap = os.path.join(base_subpath, "eeg_positions", eeg_net)
    S.map_to_surf = False
    S.map_to_fsavg = False
    S.map_to_vol = True
    S.map_to_mni = True
    S.open_in_gmsh = False
    S.tissues_in_niftis = "all"

    # Load the conductivity tensors
    S.dti_nii = tensor_file

    # First electrode pair
    tdcs = S.add_tdcslist()
    tdcs.anisotropy_type = sim_type  # Set anisotropy_type to the input sim_type
    
    # Set custom conductivities if provided in environment variables
    for i in range(len(tdcs.cond)):
        tissue_num = i + 1
        env_var = f"TISSUE_COND_{tissue_num}"
        if env_var in os.environ:
            try:
                tdcs.cond[i].value = float(os.environ[env_var])
                logger.info(f"Setting conductivity for tissue {tissue_num} to {tdcs.cond[i].value} S/m")
            except ValueError:
                logger.warning(f"Invalid conductivity value for tissue {tissue_num}")

    # Set currents for first pair using intensity1
    tdcs.currents = [intensity1, -intensity1]
    
    electrode = tdcs.add_electrode()
    electrode.channelnr = 1
    electrode.centre = montage[0][0]
    electrode.shape = electrode_shape
    electrode.dimensions = dimensions
    electrode.thickness = [thickness, 2]

    electrode = tdcs.add_electrode()
    electrode.channelnr = 2
    electrode.centre = montage[0][1]
    electrode.shape = electrode_shape
    electrode.dimensions = dimensions
    electrode.thickness = [thickness, 2]

    # Second electrode pair
    tdcs_2 = S.add_tdcslist(deepcopy(tdcs))
    # Set currents for second pair using intensity2
    tdcs_2.currents = [intensity2, -intensity2]
    tdcs_2.electrode[0].centre = montage[1][0]
    tdcs_2.electrode[1].centre = montage[1][1]

    logger.info("Running SimNIBS simulation...")
    run_simnibs(S)
    logger.info("SimNIBS simulation completed")

    subject_identifier = base_subpath.split('_')[-1]
    anisotropy_type = S.anisotropy_type

    m1_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_1_{anisotropy_type}.msh")
    m2_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_2_{anisotropy_type}.msh")

    logger.info("Loading mesh files for TI calculation")
    m1 = mesh_io.read_msh(m1_file)
    m2 = mesh_io.read_msh(m2_file)

    tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
    m1 = m1.crop_mesh(tags=tags_keep)
    m2 = m2.crop_mesh(tags=tags_keep)

    ef1 = m1.field["E"]
    ef2 = m2.field["E"]
    logger.info("Calculating TI maximum values")
    TImax = TI.get_maxTI(ef1.value, ef2.value)

    logger.info("Writing output mesh files")
    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(TImax, "TI_max")
    mesh_io.write_msh(mout, os.path.join(S.pathfem, "TI.msh"))

    v = mout.view(visible_tags=[1002, 1006], visible_fields="TI_max")
    v.write_opt(os.path.join(S.pathfem, "TI.msh"))
    logger.info(f"Completed simulation for montage: {montage_name}")

# Run the simulations for each selected montage
for name in montage_names:
    if name in montages and montages[name]:
        run_simulation(name, montages[name])
    else:
        logger.error(f"Montage {name} not found or invalid. Skipping.")

logger.info("All simulations completed successfully")
        