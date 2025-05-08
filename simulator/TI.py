import os
import sys
import json
from copy import deepcopy
import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

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
#   5. intensity         : The stimulation intensity in A.
#   6. electrode_shape   : The shape of the electrodes ('rect' or 'ellipse').
#   7. dimensions        : The dimensions of the electrodes (x,y in mm).
#   8. thickness        : The thickness of the electrodes in mm.
#   9. eeg_net           : The filename of the selected EEG net.
#   10+ montage_names     : A list of montage names to use for the simulation.

# Functionality:
#   - Loads the selected montages from a JSON file located in the ../utils directory relative to the subject directory.
#   - Runs the simulation for each montage and saves the resulting mesh files.
#   - Calculates and stores the maximal amplitude of the temporal interference (TI) envelope for multi-polar montages.

###########################################


# Get subject ID, simulation type, and montages from command-line arguments
subject_id = sys.argv[1]
sim_type = sys.argv[2]  # The anisotropy type
project_dir = sys.argv[3]  # Changed from subject_dir to project_dir
simulation_dir = sys.argv[4]
intensity = float(sys.argv[5])  # Convert intensity to float
electrode_shape = sys.argv[6]
dimensions = [float(x) for x in sys.argv[7].split(',')]  # Convert dimensions to list of floats
thickness = float(sys.argv[8])
eeg_net = sys.argv[9]  # Get the EEG net filename
montage_names = sys.argv[10:]  # The list of montages starts from the 10th argument

# Define the correct path for the JSON file
utils_dir = os.path.join(project_dir, 'utils')
montage_file = os.path.join(utils_dir, 'montage_list.json')

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
montage_type = 'uni_polar_montages' if len(sys.argv[10:]) > 0 and sys.argv[10] in net_montages.get('uni_polar_montages', {}) else 'multi_polar_montages'
montages = {name: net_montages[montage_type].get(name) for name in montage_names}

# Validate montage structure
def validate_montage(montage, montage_name):
    if not montage or len(montage) < 2 or len(montage[0]) < 2:
        print(f"Invalid montage structure for {montage_name}. Skipping.")
        return False
    return True

# Base paths
subject_dir = os.path.join(project_dir, subject_id)
base_subpath = os.path.join(subject_dir, 'SimNIBS', f"m2m_{subject_id}")
conductivity_path = base_subpath
tensor_file = os.path.join(conductivity_path, "DTI_coregT1_tensor.nii.gz")

# Create temporary directory for SimNIBS output
temp_dir = os.path.join(simulation_dir, "tmp")
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)

# Function to run simulations
def run_simulation(montage_name, montage):
    if not validate_montage(montage, montage_name):
        return

    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    
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
    tdcs.currents = [intensity, -intensity]
    
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
    tdcs_2.currents = [intensity, -intensity]
    tdcs_2.electrode[0].centre = montage[1][0]
    tdcs_2.electrode[1].centre = montage[1][1]

    run_simnibs(S)

    subject_identifier = base_subpath.split('_')[-1]
    anisotropy_type = S.anisotropy_type

    m1_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_1_{anisotropy_type}.msh")
    m2_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_2_{anisotropy_type}.msh")

    m1 = mesh_io.read_msh(m1_file)
    m2 = mesh_io.read_msh(m2_file)

    tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
    m1 = m1.crop_mesh(tags=tags_keep)
    m2 = m2.crop_mesh(tags=tags_keep)

    ef1 = m1.field["E"]
    ef2 = m2.field["E"]
    TImax = TI.get_maxTI(ef1.value, ef2.value)

    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(TImax, "TI_max")
    mesh_io.write_msh(mout, os.path.join(S.pathfem, "TI.msh"))

    v = mout.view(visible_tags=[1002, 1006], visible_fields="TI_max")
    v.write_opt(os.path.join(S.pathfem, "TI.msh"))

# Run the simulations for each selected montage
for name in montage_names:
    if name in montages and montages[name]:
        run_simulation(name, montages[name])
    else:
        print(f"Montage {name} not found or invalid. Skipping.")

