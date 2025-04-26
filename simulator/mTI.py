
import os
import sys
import json
from copy import deepcopy
import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

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

# Create the montages dictionary based on the selected montages
montages = {name: all_montages['uni_polar_montages'].get(name, all_montages['multi_polar_montages'].get(name))
            for name in montage_names}

# Base paths
base_subpath = os.path.join(subject_dir, f"m2m_{subject_id}")
base_pathfem = os.path.join(simulation_dir, f"sim_{subject_id}", "FEM")
conductivity_path = base_subpath
tensor_file = os.path.join(conductivity_path, "DTI_coregT1_tensor.nii.gz")

# Ensure the base_pathfem directory exists
if not os.path.exists(base_pathfem):
    os.makedirs(base_pathfem)

def get_TI_vectors(E1_org, E2_org):
    """
    calculates the modulation amplitude vectors for the TI envelope

    Parameters
    ----------
    E1_org : np.ndarray
           field of electrode pair 1 (N x 3) where N is the number of
           positions at which the field was calculated
    E2_org : np.ndarray
        field of electrode pair 2 (N x 3)

    Returns
    -------
    TI_vectors : np.ndarray (N x 3)
        modulation amplitude vectors
    """
    assert E1_org.shape == E2_org.shape
    assert E1_org.shape[1] == 3
    E1 = E1_org.copy()
    E2 = E2_org.copy()

    # ensure E1>E2
    idx = np.linalg.norm(E2, axis=1) > np.linalg.norm(E1, axis=1)
    E1[idx] = E2[idx]
    E2[idx] = E1_org[idx]

    # ensure alpha < pi/2
    idx = np.sum(E1 * E2, axis=1) < 0
    E2[idx] = -E2[idx]

    # get maximal amplitude of envelope
    normE1 = np.linalg.norm(E1, axis=1)
    normE2 = np.linalg.norm(E2, axis=1)
    cosalpha = np.sum(E1 * E2, axis=1) / (normE1 * normE2)

    idx = normE2 <= normE1 * cosalpha
    
    TI_vectors = np.zeros_like(E1)
    TI_vectors[idx] = 2 * E2[idx]
    TI_vectors[~idx] = 2 * np.cross(E2[~idx], E1[~idx] - E2[~idx]) / np.linalg.norm(E1[~idx] - E2[~idx], axis=1)[:, None]

    return TI_vectors



# Function to run simulations
def run_simulation(montage_name, montage):
    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    S.pathfem = os.path.join(base_pathfem, f"TI_{montage_name}")
    S.eeg_cap = os.path.join(base_subpath, "eeg_positions", "EGI_template.csv")
    S.map_to_surf = False
    S.map_to_fsavg = False
    S.map_to_vol = False
    S.map_to_mni = False
    S.open_in_gmsh = False
    S.tissues_in_niftis = "all"

    # Load the conductivity tensors
    S.dti_nii = tensor_file

    # First electrode pair
    tdcs = S.add_tdcslist()
    tdcs.anisotropy_type = sim_type  # Set anisotropy_type to the input sim_type
    tdcs.currents = [0.0025, -0.0025]
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
    tdcs_2.currents = [0.0025, -0.0025]
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
    TImax_vectors = get_TI_vectors(ef1.value, ef2.value)

    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(TImax_vectors, "TI_vectors")
    output_mesh_path = os.path.join(S.pathfem, f"TI_{montage_name}.msh")
    mesh_io.write_msh(mout, output_mesh_path)

    v = mout.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"])
    v.write_opt(output_mesh_path)
    
    return output_mesh_path

# Run the simulations and collect the output paths
output_paths = {name: run_simulation(name, montage) for name, montage in montages.items()}

# Create pairs of montage names for mTI calculations
montage_pairs = [(montage_names[i], montage_names[i+1]) for i in range(0, len(montage_names) - 1, 2)]

# Iterate through the montage pairs for mTI calculation
for pair in montage_pairs:
    m1_name, m2_name = pair
    if m1_name in output_paths and m2_name in output_paths:
        m1_path = output_paths[m1_name]
        m2_path = output_paths[m2_name]

        m1 = mesh_io.read_msh(m1_path)
        m2 = mesh_io.read_msh(m2_path)

        # Calculate the maximal amplitude of the TI envelope
        ef1 = m1.field["TI_vectors"]
        ef2 = m2.field["TI_vectors"]

        # Use the get_maxTI function
        TI_MultiPolar = TI.get_maxTI(ef1.value, ef2.value)

        # Make a new mesh for visualization of the field strengths
        # and the amplitude of the TI envelope
        mout = deepcopy(m1)
        mout.elmdata = []

        mout.add_element_field(TI_MultiPolar, "TI_Max")

        mp_pathfem = base_pathfem
        output_mesh_path = os.path.join(mp_pathfem, f"mTI_{m1_name}_{m2_name}.msh")
        mesh_io.write_msh(mout, output_mesh_path)
    else:
        print(f"Montage names {m1_name} and {m2_name} are not in the output paths.")

