import os
import sys
import json
import subprocess
import shutil
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
#
# This script runs SimNIBS simulations for multipolar TI (mTI)
# It preserves the original mTI computation logic while using BIDS directory structure
###########################################

# Add logging utility import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils import logging_util

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

# Initialize logger
# Check if log file path is provided through environment variable
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    # If not provided, create a new log file (fallback behavior)
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    derivatives_dir = os.path.join(project_dir, 'derivatives')
    log_dir = os.path.join(derivatives_dir, 'logs', f'sub-{subject_id}')
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

# Function to run simulations
def run_simulation(montage_name, montage, output_dir):
    print(f"[DEBUG] Entering run_simulation for montage: {montage_name}")
    logger.info(f"Starting simulation for montage: {montage_name}")
    
    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    
    logger.info(f"Set up SimNIBS session with anisotropy type: {sim_type}")
    
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

    tdcs.currents = [intensity1_ch1, -intensity1_ch2]
    
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
    tdcs_2.currents = [intensity2_ch1, -intensity2_ch2]
    tdcs_2.electrode[0].centre = montage[1][0]
    tdcs_2.electrode[1].centre = montage[1][1]

    logger.info("Running SimNIBS simulation...")
    run_simnibs(S)
    logger.info("SimNIBS simulation completed")

    subject_identifier = base_subpath.split('_')[-1]
    anisotropy_type = S.anisotropy_type

    # Read the mesh files directly from where SimNIBS saves them
    m1_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_1_{anisotropy_type}.msh")
    m2_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_2_{anisotropy_type}.msh")

    m1 = mesh_io.read_msh(m1_file)
    m2 = mesh_io.read_msh(m2_file)

    # Create the directory structure for organizing files (multipolar structure)
    high_freq_a_dir = os.path.join(S.pathfem, "high_frequency_A")
    high_freq_b_dir = os.path.join(S.pathfem, "high_frequency_B")
    ti_mesh_a_dir = os.path.join(S.pathfem, "TI", "mesh_A")
    ti_mesh_b_dir = os.path.join(S.pathfem, "TI", "mesh_B")
    ti_nifti_dir = os.path.join(S.pathfem, "TI", "niftis")
    ti_montage_dir = os.path.join(S.pathfem, "TI", "montage_imgs")
    doc_dir = os.path.join(S.pathfem, "documentation")
    mti_dir = os.path.join(S.pathfem, "mTI")

    # Create directories
    for dir_path in [high_freq_a_dir, high_freq_b_dir, ti_mesh_a_dir, ti_mesh_b_dir,
                    ti_nifti_dir, ti_montage_dir, doc_dir, mti_dir]:
        os.makedirs(dir_path, exist_ok=True)

    # Move high frequency files to their directories
    for file in [f for f in os.listdir(S.pathfem) if "TDCS_1" in f]:
        src = os.path.join(S.pathfem, file)
        if file.endswith('.msh') or file.endswith('.geo') or file.endswith('.opt'):
            dst = os.path.join(high_freq_a_dir, file)
            os.rename(src, dst)
    
    for file in [f for f in os.listdir(S.pathfem) if "TDCS_2" in f]:
        src = os.path.join(S.pathfem, file)
        if file.endswith('.msh') or file.endswith('.geo') or file.endswith('.opt'):
            dst = os.path.join(high_freq_b_dir, file)
            os.rename(src, dst)

    # Move subject volumes to TI nifti directory
    subject_volumes_dir = os.path.join(S.pathfem, "subject_volumes")
    if os.path.exists(subject_volumes_dir):
        for file in os.listdir(subject_volumes_dir):
            src = os.path.join(subject_volumes_dir, file)
            dst = os.path.join(ti_nifti_dir, file)
            os.rename(src, dst)
        os.rmdir(subject_volumes_dir)

    # Move log and mat files to documentation
    for file in [f for f in os.listdir(S.pathfem) if f.endswith(('.log', '.mat'))]:
        src = os.path.join(S.pathfem, file)
        dst = os.path.join(doc_dir, file)
        os.rename(src, dst)

    # Move fields_summary.txt to documentation directory if it exists
    fields_summary = os.path.join(S.pathfem, "fields_summary.txt")
    if os.path.exists(fields_summary):
        dst = os.path.join(doc_dir, "fields_summary.txt")
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
    
    output_mesh_path = os.path.join(ti_mesh_a_dir, f"{montage_name}_TI.msh")
    mesh_io.write_msh(mout, output_mesh_path)

    v = mout.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"])
    v.write_opt(output_mesh_path)
    
    logger.info(f"Completed simulation for montage: {montage_name}")
    return output_mesh_path


# Helper function to run high-frequency simulation for electrode pair
def run_high_frequency_simulation(montage_name, electrode_pair, output_dir, current_ch1, current_ch2):
    """Run a high-frequency simulation for a single electrode pair"""
    print(f"[DEBUG] Running HF simulation: {montage_name}, electrodes: {electrode_pair}, current: {current_ch1}/{current_ch2}")
    
    # Access global variables
    global base_subpath, sim_type, project_dir, eeg_net, electrode_shape, dimensions, thickness, tensor_file
    
    # Create a SimNIBS session for high-frequency simulation (single electrode pair)
    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.pathfem = os.path.join(output_dir, montage_name)
    S.anisotropy_type = sim_type
    S.eeg_cap = os.path.join(base_subpath, "eeg_positions", eeg_net)
    S.map_to_surf = False
    S.map_to_fsavg = False
    S.map_to_vol = True
    S.map_to_mni = True
    S.open_in_gmsh = False
    S.tissues_in_niftis = "all"
    
    # Load the conductivity tensors
    S.dti_nii = tensor_file
    
    # Create the electrode montage for a single pair (TDCS simulation)
    tdcs = S.add_tdcslist()
    tdcs.anisotropy_type = sim_type
    
    # Set custom conductivities if provided in environment variables
    for i in range(len(tdcs.cond)):
        tissue_num = i + 1
        env_var = f"TISSUE_COND_{tissue_num}"
        if env_var in os.environ:
            try:
                tdcs.cond[i].value = float(os.environ[env_var])
                logger.info(f"Set tissue {tissue_num} conductivity to {tdcs.cond[i].value}")
            except ValueError:
                logger.warning(f"Invalid conductivity value in {env_var}: {os.environ[env_var]}")
    
    # Configure electrodes for the single pair
    electrode1, electrode2 = electrode_pair
    tdcs.currents = [current_ch1, -current_ch2]  # Current flows from electrode1 to electrode2
    
    # First electrode
    electrode = tdcs.add_electrode()
    electrode.channelnr = 1
    electrode.centre = electrode1
    if electrode_shape == "ellipse":
        electrode.shape = "ellipse"
    else:
        electrode.shape = "rect"
    electrode.dimensions = dimensions
    electrode.thickness = [thickness, thickness]
    
    # Second electrode
    electrode = tdcs.add_electrode()
    electrode.channelnr = 2
    electrode.centre = electrode2
    if electrode_shape == "ellipse":
        electrode.shape = "ellipse"
    else:
        electrode.shape = "rect"
    electrode.dimensions = dimensions
    electrode.thickness = [thickness, thickness]
    
    logger.info(f"Running SimNIBS simulation for high-frequency pair: {electrode1}, {electrode2}")
    run_simnibs(S)
    logger.info("High-frequency SimNIBS simulation completed")
    
    # Find the output mesh files (SimNIBS creates one file per TDCS list)
    subject_identifier = base_subpath.split('_')[-1]
    anisotropy_type = S.anisotropy_type
    
    mesh_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_1_{anisotropy_type}.msh")
    
    if os.path.exists(mesh_file):
        # Load and process the mesh
        m = mesh_io.read_msh(mesh_file)
        
        # Crop mesh to keep only relevant tissues (following reference pattern)
        tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
        m = m.crop_mesh(tags=tags_keep)
        
        # Save the processed mesh
        output_mesh_path = os.path.join(S.pathfem, f"HF_{montage_name}.msh")
        mesh_io.write_msh(m, output_mesh_path)
        
        print(f"[DEBUG] High-frequency mesh processed and saved to: {output_mesh_path}")
        return output_mesh_path
    else:
        print(f"[ERROR] Could not find expected mesh file: {mesh_file}")
        # Try to find any mesh file in the directory
        for file in os.listdir(S.pathfem):
            if file.endswith('.msh'):
                print(f"[DEBUG] Found alternative mesh file: {file}")
                return os.path.join(S.pathfem, file)
        return None


# Helper function to create TI from two high-frequency simulations
def create_ti_from_hf_pair(hf_mesh1_path, hf_mesh2_path, ti_name, output_dir):
    """Create TI simulation from two high-frequency simulations"""
    print(f"[DEBUG] Creating TI '{ti_name}' from HF meshes: {hf_mesh1_path}, {hf_mesh2_path}")
    
    # Load the high-frequency meshes
    m1 = mesh_io.read_msh(hf_mesh1_path)
    m2 = mesh_io.read_msh(hf_mesh2_path)
    
    # Get the electric field data (high-frequency simulations produce "E" fields)
    ef1 = m1.field["E"]
    ef2 = m2.field["E"]
    
    # Calculate TI vectors using the same function as the reference script
    TI_vectors = get_TI_vectors(ef1.value, ef2.value)
    
    # Create output mesh with TI vectors
    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(TI_vectors, "TI_vectors")
    
    # Save TI mesh
    os.makedirs(output_dir, exist_ok=True)
    ti_mesh_path = os.path.join(output_dir, f"TI_{ti_name}.msh")
    mesh_io.write_msh(mout, ti_mesh_path)
    
    # Create visualization
    v = mout.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"])
    v.write_opt(ti_mesh_path)
    
    print(f"[DEBUG] TI mesh saved to: {ti_mesh_path}")
    
    # Extract grey matter and white matter fields
    gm_output = os.path.join(output_dir, f"grey_TI_{ti_name}.msh")
    wm_output = os.path.join(output_dir, f"white_TI_{ti_name}.msh")
    extract_fields(ti_mesh_path, gm_output, wm_output)
    
    return ti_mesh_path


# Helper function to create mTI from two TI simulations
def create_mti_from_ti_pair(ti_mesh1_path, ti_mesh2_path, mti_name, output_dir):
    """Create mTI simulation from two TI simulations"""
    print(f"[DEBUG] Creating mTI '{mti_name}' from TI meshes: {ti_mesh1_path}, {ti_mesh2_path}")
    
    # Load the TI meshes
    m1 = mesh_io.read_msh(ti_mesh1_path)
    m2 = mesh_io.read_msh(ti_mesh2_path)
    
    # Get the TI field data (from TI simulations)
    ef1 = m1.field["TI_vectors"]
    ef2 = m2.field["TI_vectors"]
    
    # Calculate multi-polar TI field using the get_maxTI function
    mTI_field = TI.get_maxTI(ef1.value, ef2.value)
    
    # Create output mesh
    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(mTI_field, "TI_Max")
    
    # Save mTI mesh
    os.makedirs(output_dir, exist_ok=True)
    mti_mesh_path = os.path.join(output_dir, f"mTI_{mti_name}.msh")
    mesh_io.write_msh(mout, mti_mesh_path)
    
    # Create visualization
    v = mout.view(visible_tags=[1002, 1006], visible_fields="TI_Max")
    v.write_opt(mti_mesh_path)
    
    print(f"[DEBUG] mTI mesh saved to: {mti_mesh_path}")
    
    # Extract grey matter and white matter fields
    gm_output = os.path.join(output_dir, f"grey_mTI_{mti_name}.msh")
    wm_output = os.path.join(output_dir, f"white_mTI_{mti_name}.msh")
    extract_fields(mti_mesh_path, gm_output, wm_output)
    
    return mti_mesh_path


# Function to extract fields (GM and WM meshes) - adapted from main-TI.sh
def extract_fields(input_file, gm_output_file, wm_output_file):
    """Extract grey matter and white matter fields from a mesh file"""
    print(f"[DEBUG] Extracting fields from: {os.path.basename(input_file)}")
    
    # Load the original mesh
    full_mesh = mesh_io.read_msh(input_file)
    
    # Extract grey matter mesh (tag #2) 
    gm_mesh = full_mesh.crop_mesh(tags=[2])
    
    # Extract white matter mesh (tag #1)
    wm_mesh = full_mesh.crop_mesh(tags=[1])
    
    # Save grey matter mesh
    mesh_io.write_msh(gm_mesh, gm_output_file)
    print(f"[DEBUG] Grey matter mesh saved to: {gm_output_file}")
    
    # Save white matter mesh  
    mesh_io.write_msh(wm_mesh, wm_output_file)
    print(f"[DEBUG] White matter mesh saved to: {wm_output_file}")
    
    return gm_output_file, wm_output_file


# Function to transform parcellated meshes to NIfTI - adapted from main-TI.sh
def transform_parcellated_meshes_to_nifti(input_mesh_dir, output_dir):
    """Convert all .msh files in input directory to NIfTI format"""
    print(f"[DEBUG] Converting meshes to NIfTI format from: {input_mesh_dir} to: {output_dir}")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Get mesh files
    mesh_files = [f for f in os.listdir(input_mesh_dir) if f.endswith('.msh')]
    
    if not mesh_files:
        print(f"[WARNING] No .msh files found in {input_mesh_dir}")
        return
        
    for mesh_file in mesh_files:
        mesh_path = os.path.join(input_mesh_dir, mesh_file)
        base_name = os.path.splitext(mesh_file)[0]
        
        # MNI space conversion
        mni_output = os.path.join(output_dir, f"{base_name}_MNI.nii.gz")
        subject_output = os.path.join(output_dir, f"{base_name}_subject.nii.gz")
        
        print(f"[DEBUG] Converting {mesh_file} to NIfTI format")
        
        # Run subject2mni for MNI space
        try:
            subprocess.run(["subject2mni", "-i", mesh_path, "-m", base_subpath, "-o", mni_output], 
                         check=True, capture_output=True, text=True)
            print(f"[DEBUG] MNI conversion completed: {mni_output}")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] subject2mni failed for {mesh_file}: {e}")
            continue
            
        # Run msh2nii for subject space
        try:
            subprocess.run(["msh2nii", mesh_path, base_subpath, subject_output], 
                         check=True, capture_output=True, text=True)
            print(f"[DEBUG] Subject space conversion completed: {subject_output}")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] msh2nii failed for {mesh_file}: {e}")
            continue
    
    print(f"[DEBUG] All mesh-to-NIfTI conversions completed")


# For multipolar mode, we need to process a single montage and get its electrode pairs
print(f"[DEBUG] Processing single montage for multipolar simulation: {montage_names}")

# Process each montage (typically just one in multipolar mode)
for montage_name in montage_names:
    print(f"[DEBUG] Processing montage: {montage_name}")
    
    # Set up directories for this montage (using the new multipolar structure)
    montage_output_dir = os.path.join(simulation_dir, montage_name)
    high_freq_a_dir = os.path.join(montage_output_dir, "high_frequency_A")
    high_freq_b_dir = os.path.join(montage_output_dir, "high_frequency_B") 
    ti_mesh_a_dir = os.path.join(montage_output_dir, "TI", "mesh_A")
    ti_mesh_b_dir = os.path.join(montage_output_dir, "TI", "mesh_B")
    ti_nifti_dir = os.path.join(montage_output_dir, "TI", "niftis")
    ti_montage_dir = os.path.join(montage_output_dir, "TI", "montage_imgs")
    mti_output_dir = os.path.join(montage_output_dir, "mTI")
    doc_dir = os.path.join(montage_output_dir, "documentation")
    
    # Create directories
    for dir_path in [high_freq_a_dir, high_freq_b_dir, ti_mesh_a_dir, ti_mesh_b_dir, 
                     ti_nifti_dir, ti_montage_dir, mti_output_dir, doc_dir]:
        os.makedirs(dir_path, exist_ok=True)
    
    # Get electrode pairs for this montage from the JSON file
    montage_config_path = os.path.join(project_dir, "ti-csc", "config", "montage_list.json")
    print(f"[DEBUG] Loading montage config from: {montage_config_path}")
    
    try:
        with open(montage_config_path, 'r') as f:
            montage_config = json.load(f)
        
        # Get the electrode pairs for this montage
        net_key = eeg_net  # Keep the full filename with .csv
        electrode_pairs = montage_config.get("nets", {}).get(net_key, {}).get("multi_polar_montages", {}).get(montage_name, [])
        print(f"[DEBUG] Found {len(electrode_pairs)} electrode pairs for montage '{montage_name}': {electrode_pairs}")
        
        if not electrode_pairs:
            print(f"[ERROR] No electrode pairs found for montage '{montage_name}' in net '{net_key}'")
            continue
            
    except Exception as e:
        print(f"[ERROR] Failed to load montage config: {e}")
        continue
    
    # Process electrode pairs to run high-frequency simulations
    high_freq_meshes = []
    ti_meshes = []
    
    # Create pairs of electrode pairs for TI (takes 2 pairs to make 1 TI)
    for i in range(0, len(electrode_pairs), 2):
        if i + 1 < len(electrode_pairs):
            pair_a = electrode_pairs[i]
            pair_b = electrode_pairs[i + 1] if i + 1 < len(electrode_pairs) else electrode_pairs[i]
            
            print(f"[DEBUG] Processing TI pair {i//2 + 1}: {pair_a} -> {pair_b}")
            
            # Run high frequency simulations for each electrode in both pairs
            for j, electrode_pair in enumerate([pair_a, pair_b]):
                electrode1, electrode2 = electrode_pair
                print(f"[DEBUG] Running high-frequency simulation for electrodes: {electrode1}, {electrode2}")
                
                # Create temporary montage name for this electrode pair
                temp_montage_name = f"{montage_name}_HF_{i//2 + 1}_{chr(65 + j)}"  # e.g., test_HF_1_A, test_HF_1_B
                
                # Set up directory for this high-frequency simulation
                hf_output_dir = high_freq_a_dir if j == 0 else high_freq_b_dir
                
                # Run the simulation
                current_ch1 = intensity1_ch1 if j == 0 else intensity2_ch1
                current_ch2 = intensity1_ch2 if j == 0 else intensity2_ch2
                
                mesh_path = run_high_frequency_simulation(temp_montage_name, electrode_pair, hf_output_dir, current_ch1, current_ch2)
                high_freq_meshes.append(mesh_path)
            
            # Now create TI simulation from the two high-frequency simulations
            if len(high_freq_meshes) >= 2:
                ti_mesh_path = create_ti_from_hf_pair(high_freq_meshes[-2], high_freq_meshes[-1], 
                                                    f"{montage_name}_TI_{i//2 + 1}", ti_mesh_a_dir if i == 0 else ti_mesh_b_dir)
                ti_meshes.append(ti_mesh_path)
    
    # Finally, create mTI simulation from the TI simulations
    if len(ti_meshes) >= 2:
        print(f"[DEBUG] Creating mTI from {len(ti_meshes)} TI meshes")
        mti_mesh_path = create_mti_from_ti_pair(ti_meshes[0], ti_meshes[1], f"{montage_name}_mTI", mti_output_dir)
        print(f"[DEBUG] mTI simulation completed: {mti_mesh_path}")
        
        # Convert all grey matter meshes to NIfTI format
        print(f"[DEBUG] Converting all grey matter meshes to NIfTI format")
        
        # Create temporary directory with only grey matter meshes for NIfTI conversion
        temp_nifti_dir = os.path.join(simulation_dir, f"{montage_name}_nifti_conversion")
        os.makedirs(temp_nifti_dir, exist_ok=True)
        
        # Copy grey matter meshes from TI mesh_A, mesh_B, and mTI
        grey_meshes_to_convert = []
        
        # From TI mesh_A
        gm_a_source = os.path.join(ti_mesh_a_dir, f"grey_TI_{montage_name}_TI_1.msh")
        if os.path.exists(gm_a_source):
            gm_a_dest = os.path.join(temp_nifti_dir, f"grey_TI_{montage_name}_A.msh")
            shutil.copy2(gm_a_source, gm_a_dest)
            grey_meshes_to_convert.append(gm_a_dest)
        
        # From TI mesh_B  
        gm_b_source = os.path.join(ti_mesh_b_dir, f"grey_TI_{montage_name}_TI_2.msh")
        if os.path.exists(gm_b_source):
            gm_b_dest = os.path.join(temp_nifti_dir, f"grey_TI_{montage_name}_B.msh")
            shutil.copy2(gm_b_source, gm_b_dest)
            grey_meshes_to_convert.append(gm_b_dest)
        
        # From mTI
        gm_mti_source = os.path.join(mti_output_dir, f"grey_mTI_{montage_name}_mTI.msh")
        if os.path.exists(gm_mti_source):
            gm_mti_dest = os.path.join(temp_nifti_dir, f"grey_mTI_{montage_name}.msh")
            shutil.copy2(gm_mti_source, gm_mti_dest)
            grey_meshes_to_convert.append(gm_mti_dest)
        
        print(f"[DEBUG] Found {len(grey_meshes_to_convert)} grey matter meshes to convert")
        
        # Convert to NIfTI format
        if grey_meshes_to_convert:
            transform_parcellated_meshes_to_nifti(temp_nifti_dir, ti_nifti_dir)
        
        # Clean up temporary directory
        shutil.rmtree(temp_nifti_dir)
        
    else:
        print(f"[ERROR] Need at least 2 TI meshes to create mTI, but only have {len(ti_meshes)}")

print("[DEBUG] mTI.py script completed")
        