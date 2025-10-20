# Standard library imports
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from copy import deepcopy
from datetime import datetime

# Third-party imports
import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Local imports
from tools import logging_util


# Get subject ID, simulation type, and montages from command-line arguments
print(f"[DEBUG] mTI.py called with {len(sys.argv)} arguments: {sys.argv}")
subject_id = sys.argv[1]
sim_type = sys.argv[2]  # The anisotropy type
project_dir = sys.argv[3]  # Changed from subject_dir to project_dir
simulation_dir = sys.argv[4]
print(f"[DEBUG] Parsed basic args: subject_id={subject_id}, sim_type={sim_type}, project_dir={project_dir}, simulation_dir={simulation_dir}")
# Handle multiple intensity values for multipolar mode
intensity_str = sys.argv[5]
print(f"[DEBUG] Intensity string: '{intensity_str}'")
if ',' in intensity_str:
    # Multiple current values for multipolar mode (4 channels)
    intensities = [float(x.strip()) for x in intensity_str.split(',')]
    print(f"[DEBUG] Parsed {len(intensities)} intensity values: {intensities}")
    if len(intensities) == 4:
        intensity1_ch1, intensity1_ch2, intensity2_ch1, intensity2_ch2 = intensities
    elif len(intensities) == 2:
        # Fallback: use first two values for both pairs
        intensity1_ch1, intensity1_ch2 = intensities
        intensity2_ch1, intensity2_ch2 = intensities
    else:
        # Use first value for all
        intensity1_ch1 = intensity1_ch2 = intensity2_ch1 = intensity2_ch2 = intensities[0]
else:
    # Single intensity value - use for all channels
    intensity = float(intensity_str)
    intensity1_ch1 = intensity1_ch2 = intensity2_ch1 = intensity2_ch2 = intensity
print(f"[DEBUG] Final current values: ch1={intensity1_ch1}, ch2={intensity1_ch2}, ch3={intensity2_ch1}, ch4={intensity2_ch2}")
electrode_shape = sys.argv[6]
dimensions = [float(x) for x in sys.argv[7].split(',')]  # Convert dimensions to list of floats
thickness = float(sys.argv[8])
eeg_net = sys.argv[9]  # Get the EEG net filename
montage_names = sys.argv[10:]
print(f"[DEBUG] Electrode params: shape={electrode_shape}, dimensions={dimensions}, thickness={thickness}")
print(f"[DEBUG] EEG net: {eeg_net}")
print(f"[DEBUG] Montage names: {montage_names}")

# Define the correct path for the JSON file
ti_csc_dir = os.path.join(project_dir, 'code', 'ti-toolbox')
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

# Initialize logger
# Check if log file path is provided through environment variable
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    # If not provided, create a new log file (fallback behavior)
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    derivatives_dir = os.path.join(project_dir, 'derivatives')
    log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'Simulator_{time_stamp}.log')

# Initialize our main logger
logger = logging_util.get_logger('mTI', log_file, overwrite=False)

# Configure SimNIBS related loggers to use our logging setup
logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct'], logger)

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

# Function to run multipolar TI simulation
def run_simulation(montage_name, electrode_pairs, output_dir):
    """Run multipolar TI simulation with 4 electrode pairs"""
    print(f"[DEBUG] Entering run_simulation for montage: {montage_name}")
    logger.info(f"Starting multipolar simulation for montage: {montage_name}")
    
    if len(electrode_pairs) < 4:
        logger.error(f"Need at least 4 electrode pairs for mTI, got {len(electrode_pairs)}")
        return None
    
    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    S.pathfem = os.path.join(output_dir, montage_name)
    S.eeg_cap = os.path.join(base_subpath, "eeg_positions", eeg_net)
    S.map_to_surf = False
    S.map_to_fsavg = False
    S.map_to_vol = False
    S.map_to_mni = False
    S.open_in_gmsh = False
    S.tissues_in_niftis = "all"

    # Load the conductivity tensors
    S.dti_nii = tensor_file

    # Create 4 TDCS lists for the 4 electrode pairs (HF_A, HF_B, HF_C, HF_D)
    currents = [intensity1_ch1, intensity1_ch2, intensity2_ch1, intensity2_ch2]
    
    for i, pair in enumerate(electrode_pairs[:4]):
        tdcs = S.add_tdcslist()
        tdcs.anisotropy_type = sim_type
        
        # Set custom conductivities if provided in environment variables
        for j in range(len(tdcs.cond)):
            tissue_num = j + 1
            env_var = f"TISSUE_COND_{tissue_num}"
            if env_var in os.environ:
                try:
                    tdcs.cond[j].value = float(os.environ[env_var])
                    logger.debug(f"Setting conductivity for tissue {tissue_num} to {tdcs.cond[j].value} S/m")
                except ValueError:
                    logger.warning(f"Invalid conductivity value for tissue {tissue_num}")

        # Set current (positive and negative)
        tdcs.currents = [currents[i], -currents[i]]
        
        # Add electrodes for this pair
        electrode1 = tdcs.add_electrode()
        electrode1.channelnr = 1
        electrode1.centre = pair[0]
        electrode1.shape = electrode_shape
        electrode1.dimensions = dimensions
        electrode1.thickness = [thickness, 2]

        electrode2 = tdcs.add_electrode()
        electrode2.channelnr = 2
        electrode2.centre = pair[1]
        electrode2.shape = electrode_shape
        electrode2.dimensions = dimensions
        electrode2.thickness = [thickness, 2]

    logger.info("Running SimNIBS multipolar simulation...")
    run_simnibs(S)
    logger.info("SimNIBS multipolar simulation completed")

    # Use the provided subject_id directly to preserve underscores (e.g., 'ernie_extended')
    subject_identifier = subject_id
    anisotropy_type = S.anisotropy_type

    # Try both full and truncated subject IDs (SimNIBS truncation workaround)
    truncated_identifier = subject_id.split('_')[-1]  # Get last part after underscore

    # Helper to resolve the correct TDCS mesh file path and normalize filename
    def resolve_and_normalize_tdcs_file(tdcs_index: int) -> str:
        expected_full = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_{tdcs_index}_{anisotropy_type}.msh")
        if os.path.exists(expected_full):
            return expected_full
        # Try truncated identifier
        truncated = os.path.join(S.pathfem, f"{truncated_identifier}_TDCS_{tdcs_index}_{anisotropy_type}.msh")
        if os.path.exists(truncated):
            # Normalize filename to full subject id for downstream scripts
            try:
                os.rename(truncated, expected_full)
                opt_src = truncated + ".opt"
                opt_dst = expected_full + ".opt"
                if os.path.exists(opt_src):
                    os.rename(opt_src, opt_dst)
                logger.debug(f"Renamed truncated TDCS_{tdcs_index} file to full subject id: {os.path.basename(expected_full)}")
            except Exception as e:
                logger.warning(f"Could not rename truncated file {os.path.basename(truncated)}: {e}")
            return expected_full if os.path.exists(expected_full) else truncated
        # Fallback: glob any matching file
        pattern = os.path.join(S.pathfem, f"*TDCS_{tdcs_index}_{anisotropy_type}.msh")
        matches = glob.glob(pattern)
        if len(matches) >= 1:
            chosen = matches[0]
            # Normalize chosen to expected_full if needed
            if chosen != expected_full:
                try:
                    os.rename(chosen, expected_full)
                    opt_src = chosen + ".opt"
                    opt_dst = expected_full + ".opt"
                    if os.path.exists(opt_src):
                        os.rename(opt_src, opt_dst)
                    logger.debug(f"Normalized TDCS_{tdcs_index} via glob to: {os.path.basename(expected_full)}")
                    return expected_full
                except Exception as e:
                    logger.warning(f"Could not normalize globbed file {os.path.basename(chosen)}: {e}")
                    return chosen
            return chosen
        logger.error(f"Could not resolve TDCS_{tdcs_index} mesh. Looked for full, truncated, and pattern {pattern}")
        return expected_full

    # Load the 4 high-frequency mesh files
    hf_meshes = []
    for i in range(1, 5):  # TDCS_1, TDCS_2, TDCS_3, TDCS_4
        mesh_file = resolve_and_normalize_tdcs_file(i)
        if os.path.exists(mesh_file):
            m = mesh_io.read_msh(mesh_file)
            tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
            m = m.crop_mesh(tags=tags_keep)
            hf_meshes.append(m)
        else:
            logger.error(f"Could not find mesh file: {mesh_file}")
            return None

    if len(hf_meshes) != 4:
        logger.error(f"Expected 4 HF meshes, found {len(hf_meshes)}")
        return None

    # Calculate TI pairs: TI_AB (HF_A + HF_B), TI_CD (HF_C + HF_D)
    ef_a = hf_meshes[0].field["E"]
    ef_b = hf_meshes[1].field["E"]
    ef_c = hf_meshes[2].field["E"]
    ef_d = hf_meshes[3].field["E"]
    
    ti_ab_vectors = get_TI_vectors(ef_a.value, ef_b.value)
    ti_cd_vectors = get_TI_vectors(ef_c.value, ef_d.value)
    
    # Save intermediate TI meshes (TI_AB and TI_CD)
    # TI_AB mesh
    ti_ab_mesh = deepcopy(hf_meshes[0])
    ti_ab_mesh.elmdata = []
    ti_ab_mesh.add_element_field(ti_ab_vectors, "TI_vectors")
    ti_ab_path = os.path.join(S.pathfem, "TI_AB.msh")
    mesh_io.write_msh(ti_ab_mesh, ti_ab_path)
    v_ab = ti_ab_mesh.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"])
    v_ab.write_opt(ti_ab_path)
    
    # TI_CD mesh
    ti_cd_mesh = deepcopy(hf_meshes[0])
    ti_cd_mesh.elmdata = []
    ti_cd_mesh.add_element_field(ti_cd_vectors, "TI_vectors")
    ti_cd_path = os.path.join(S.pathfem, "TI_CD.msh")
    mesh_io.write_msh(ti_cd_mesh, ti_cd_path)
    v_cd = ti_cd_mesh.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"])
    v_cd.write_opt(ti_cd_path)
    
    # Calculate final mTI from TI_AB and TI_CD
    mti_field = TI.get_maxTI(ti_ab_vectors, ti_cd_vectors)
    
    # Create output mesh with mTI field
    mout = deepcopy(hf_meshes[0])
    mout.elmdata = []
    mout.add_element_field(mti_field, "TI_Max")
    
    # Save mTI mesh (file organization handled by main-mTI.sh)
    output_mesh_path = os.path.join(S.pathfem, "mTI.msh")
    mesh_io.write_msh(mout, output_mesh_path)

    v = mout.view(visible_tags=[1002, 1006], visible_fields="TI_Max")
    v.write_opt(output_mesh_path)
    
    logger.debug(f"Completed multipolar simulation for montage: {montage_name}")
    return output_mesh_path

# Process each montage for multipolar simulation
for montage_name in montage_names:
    print(f"[DEBUG] Processing montage: {montage_name}")
    logger.info(f"Starting multipolar simulation for montage: {montage_name}")
    
    # Get montage configuration from JSON file
    montage_config_path = os.path.join(project_dir, "code", "ti-toolbox", "config", "montage_list.json")
    
    try:
        with open(montage_config_path, 'r') as f:
            montage_config = json.load(f)
        
        # Get the electrode pairs for this montage
        electrode_pairs = montage_config.get("nets", {}).get(eeg_net, {}).get("multi_polar_montages", {}).get(montage_name, [])
        
        if not electrode_pairs or len(electrode_pairs) < 4:
            logger.error(f"Need at least 4 electrode pairs for mTI, found {len(electrode_pairs)} for montage '{montage_name}'")
            continue
            
    except Exception as e:
        logger.error(f"Failed to load montage config: {e}")
        continue
    
    # Run the basic multipolar simulation (4 electrode pairs -> 1 mTI result)
    # File organization and post-processing will be handled by main-mTI.sh
    output_path = run_simulation(montage_name, electrode_pairs, simulation_dir)
    logger.debug(f"Multipolar simulation completed for {montage_name}: {output_path}")

print("[DEBUG] mTI.py script completed")
        