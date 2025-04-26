import os
import sys
import json
from copy import deepcopy
import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

# To do:
#   - Add option to run simulations for multiple current intensities and electrode dimensions
#   - look into what options we should allow: map_to_mni, map_to_fsavg, map_to_vol


###########################################

# Ido Haber / ihaber@wisc.edu
# Month, day, year

# This script runs SimNIBS simulations

# Arguments:
#   1. subject_id           : The ID of the subject.
#   2. sim_type             : The type of simulation anisotropy ('scalar', 'vn', 'dir', 'mc').
#   3. subject_dir          : The directory where subject-specific data is stored.
#   4. simulation_dir       : The directory where simulation results will be saved.
#   5. montage_names        : A list of montage names to use for the simulation.
#   6. current intensity    : The current intensity to use for the simulation.
#   7. electrode dimention  : The electrode dimension to use for the simulation.

# Functionality:
#   - Loads the selected montages from a JSON file located in the ../utils directory relative to the subject directory.
#   - Runs the simulation for each montage and saves the resulting mesh files.
#   - Calculates and stores the maximal amplitude of the temporal interference (TI) envelope for multi-polar montages.

###########################################


# Get subject ID, simulation type, and montages from command-line arguments
subject_id = sys.argv[1]
sim_type = sys.argv[2]  # The anisotropy type
subject_dir = sys.argv[3]
simulation_dir = sys.argv[4]
montage_names = sys.argv[5:]  # The list of montages

# Define the correct path for the JSON file
utils_dir = os.path.join(subject_dir, '..', 'utils')
montage_file = os.path.join(utils_dir, 'montage_list.json')

# Load montages from JSON file
with open(montage_file) as f:
    all_montages = json.load(f)

# Check and process montages for unipolar montages
montages = {name: all_montages['uni_polar_montages'].get(name) for name in montage_names}

# Validate montage structure
def validate_montage(montage, montage_name):
    if not montage or len(montage) < 2 or len(montage[0]) < 2:
        print(f"Invalid montage structure for {montage_name}. Skipping.")
        return False
    return True

# Base paths
base_subpath = os.path.join(subject_dir, f"m2m_{subject_id}")
base_pathfem = os.path.join(simulation_dir, f"sim_{subject_id}", "FEM")
conductivity_path = base_subpath
tensor_file = os.path.join(conductivity_path, "DTI_coregT1_tensor.nii.gz")

# Ensure the base_pathfem directory exists
if not os.path.exists(base_pathfem):
    os.makedirs(base_pathfem)

# Function to run simulations
def run_simulation(montage_name, montage):
    if not validate_montage(montage, montage_name):
        return

    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    S.pathfem = os.path.join(base_pathfem, f"TI_{montage_name}")
    S.eeg_cap = os.path.join(base_subpath, "eeg_positions", "EGI_template.csv")
    S.map_to_surf = True    #  Map to subject's middle gray matter surface
    S.map_to_fsavg = True   #  Map to FreeSurfer's FSAverage group template
    S.map_to_vol = True     #  Save as nifti volume
    S.map_to_MNI = True     #  Save in MNI space
    S.tissues_in_niftis = [1,2,3]  # Results in the niftis will be masked 
                                   # to only show WM (1), GM (2), CSF(3)
                                   # (standard: only GM)
                                   # To get fields everywhere: 
                                   #    S.tissues_in_niftis = 'all'
    S.open_in_gmsh = False
    S.tissues_in_niftis = "all"

    # Load the conductivity tensors
    S.dti_nii = tensor_file

    # First electrode pair
    tdcs = S.add_tdcslist()
    tdcs.anisotropy_type = sim_type  # Set anisotropy_type to the input sim_type
    tdcs.currents = [0.005, -0.005]
    
    electrode = tdcs.add_electrode()
    electrode.channelnr = 1
    electrode.centre = montage[0][0]
    electrode.shape = "ellipse"
    electrode.dimensions = [8, 8]
    electrode.thickness = [4, 4]

    electrode = tdcs.add_electrode()
    electrode.channelnr = 2
    electrode.centre = montage[0][1]
    electrode.shape = "ellipse"
    electrode.dimensions = [8, 8]
    electrode.thickness = [4, 4]

    # Second electrode pair
    tdcs_2 = S.add_tdcslist(deepcopy(tdcs))
    tdcs_2.currents = [0.005, -0.005]
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

