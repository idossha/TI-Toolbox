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
#
# This script runs SimNIBS simulations for multipolar TI (mTI)
# It preserves the original mTI computation logic while using BIDS directory structure
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
montage_names = sys.argv[10:]

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
montage_type = 'multi_polar_montages'  # mTI only uses multi-polar montages
montages = {name: net_montages[montage_type].get(name) for name in montage_names}

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

# Base paths
derivatives_dir = os.path.join(project_dir, 'derivatives')
simnibs_dir = os.path.join(derivatives_dir, 'SimNIBS', f'sub-{subject_id}')
base_subpath = os.path.join(simnibs_dir, f'm2m_{subject_id}')
conductivity_path = base_subpath
tensor_file = os.path.join(conductivity_path, "DTI_coregT1_tensor.nii.gz")

# Function to run simulations
def run_simulation(montage_name, montage, output_dir):
    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    S.pathfem = os.path.join(output_dir, montage_name)
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

    # Read the mesh files directly from where SimNIBS saves them
    m1_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_1_{anisotropy_type}.msh")
    m2_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_2_{anisotropy_type}.msh")

    m1 = mesh_io.read_msh(m1_file)
    m2 = mesh_io.read_msh(m2_file)

    # Create the directory structure for organizing files
    high_freq_mesh_dir = os.path.join(S.pathfem, "high_Frequency", "mesh")
    high_freq_nifti_dir = os.path.join(S.pathfem, "high_Frequency", "niftis")
    high_freq_analysis_dir = os.path.join(S.pathfem, "high_Frequency", "analysis")
    ti_mesh_dir = os.path.join(S.pathfem, "TI", "mesh")
    ti_nifti_dir = os.path.join(S.pathfem, "TI", "niftis")
    ti_montage_dir = os.path.join(S.pathfem, "TI", "montage_imgs")
    doc_dir = os.path.join(S.pathfem, "documentation")

    # Create directories
    for dir_path in [high_freq_mesh_dir, high_freq_nifti_dir, high_freq_analysis_dir,
                    ti_mesh_dir, ti_nifti_dir, ti_montage_dir, doc_dir]:
        os.makedirs(dir_path, exist_ok=True)

    # Move high frequency files to their directories
    for pattern in ["TDCS_1", "TDCS_2"]:
        for file in [f for f in os.listdir(S.pathfem) if pattern in f]:
            src = os.path.join(S.pathfem, file)
            if file.endswith('.msh') or file.endswith('.geo') or file.endswith('.opt'):
                dst = os.path.join(high_freq_mesh_dir, file)
                os.rename(src, dst)

    # Move subject volumes to nifti directory
    subject_volumes_dir = os.path.join(S.pathfem, "subject_volumes")
    if os.path.exists(subject_volumes_dir):
        for file in os.listdir(subject_volumes_dir):
            src = os.path.join(subject_volumes_dir, file)
            dst = os.path.join(high_freq_nifti_dir, file)
            os.rename(src, dst)
        os.rmdir(subject_volumes_dir)

    # Move log and mat files to documentation
    for file in [f for f in os.listdir(S.pathfem) if f.endswith(('.log', '.mat'))]:
        src = os.path.join(S.pathfem, file)
        dst = os.path.join(doc_dir, file)
        os.rename(src, dst)

    # Move fields_summary.txt to analysis directory if it exists
    fields_summary = os.path.join(S.pathfem, "fields_summary.txt")
    if os.path.exists(fields_summary):
        dst = os.path.join(high_freq_analysis_dir, "fields_summary.txt")
        os.rename(fields_summary, dst)

    tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
    m1 = m1.crop_mesh(tags=tags_keep)
    m2 = m2.crop_mesh(tags=tags_keep)

    ef1 = m1.field["E"]
    ef2 = m2.field["E"]
    TImax_vectors = get_TI_vectors(ef1.value, ef2.value)

    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(TImax_vectors, "TI_vectors")
    
    output_mesh_path = os.path.join(ti_mesh_dir, f"{subject_identifier}_{montage_name}_TI.msh")
    mesh_io.write_msh(mout, output_mesh_path)

    v = mout.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"])
    v.write_opt(output_mesh_path)
    
    return output_mesh_path

# Create pairs of montage names for mTI calculations
montage_pairs = [(montage_names[i], montage_names[i+1]) for i in range(0, len(montage_names) - 1, 2)]

# Process each pair of montages
for pair in montage_pairs:
    m1_name, m2_name = pair
    pair_dir_name = f"{m1_name}_{m2_name}"
    pair_output_dir = os.path.join(simulation_dir, pair_dir_name)
    mti_output_dir = os.path.join(pair_output_dir, "mTI")
    
    # Create necessary directories
    os.makedirs(pair_output_dir, exist_ok=True)
    os.makedirs(mti_output_dir, exist_ok=True)
    
    # Run simulations for both montages
    if m1_name in montages and m2_name in montages:
        m1_path = run_simulation(m1_name, montages[m1_name], pair_output_dir)
        m2_path = run_simulation(m2_name, montages[m2_name], pair_output_dir)

        # Calculate mTI using the TI vectors from both montages
        m1 = mesh_io.read_msh(m1_path)
        m2 = mesh_io.read_msh(m2_path)

        # Calculate the maximal amplitude of the TI envelope
        ef1 = m1.field["TI_vectors"]
        ef2 = m2.field["TI_vectors"]

        # Calculate the multi-polar TI field
        TI_MultiPolar = TI.get_maxTI(ef1.value, ef2.value)

        # Create output mesh for the multi-polar TI field
        mout = deepcopy(m1)
        mout.elmdata = []
        mout.add_element_field(TI_MultiPolar, "TI_Max")

        # Save the multi-polar TI mesh
        output_mesh_path = os.path.join(mti_output_dir, f"{subject_id}_{pair_dir_name}_mTI.msh")
        mesh_io.write_msh(mout, output_mesh_path)

        # Create visualization
        v = mout.view(visible_tags=[1002, 1006], visible_fields="TI_Max")
        v.write_opt(output_mesh_path)
    else:
        print(f"Montage names {m1_name} and {m2_name} are not valid montages. Skipping.")

