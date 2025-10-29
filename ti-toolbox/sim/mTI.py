# Standard library imports
import json
import os
import sys
import time
from copy import deepcopy

# Third-party imports
import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

# Local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools import logging_util
from core import get_path_manager
from core.calc import get_TI_vectors

# Parse command-line arguments
subject_id = sys.argv[1]
sim_type = sys.argv[2]
project_dir = sys.argv[3]
simulation_dir = sys.argv[4]
intensity_str = sys.argv[5]

if ',' in intensity_str:
    intensities = [float(x.strip()) for x in intensity_str.split(',')]
    if len(intensities) == 4:
        intensity1_ch1, intensity1_ch2, intensity2_ch1, intensity2_ch2 = intensities
    elif len(intensities) == 2:
        intensity1_ch1, intensity1_ch2 = intensities
        intensity2_ch1, intensity2_ch2 = intensities
    else:
        intensity1_ch1 = intensity1_ch2 = intensity2_ch1 = intensity2_ch2 = intensities[0]
else:
    intensity = float(intensity_str)
    intensity1_ch1 = intensity1_ch2 = intensity2_ch1 = intensity2_ch2 = intensity

electrode_shape = sys.argv[6]
dimensions = [float(x) for x in sys.argv[7].split(',')]
thickness = float(sys.argv[8])
eeg_net = sys.argv[9]
montage_names = sys.argv[10:]

# Setup paths using PathManager
pm = get_path_manager()
config_dir = os.path.join(project_dir, 'code', 'ti-toolbox', 'config')
montage_file = os.path.join(config_dir, 'montage_list.json')
derivatives_dir = pm.get_derivatives_dir()
simnibs_dir = pm.get_simnibs_dir()
base_subpath = pm.get_m2m_dir(subject_id)
tensor_file = os.path.join(base_subpath, "DTI_coregT1_tensor.nii.gz")

# Create config directory
os.makedirs(config_dir, exist_ok=True)
os.chmod(os.path.join(project_dir, 'code', 'ti-toolbox'), 0o777)
os.chmod(config_dir, 0o777)

# Initialize montage file
if not os.path.exists(montage_file):
    with open(montage_file, 'w') as f:
        json.dump({"nets": {"EGI_template.csv": {"uni_polar_montages": {}, "multi_polar_montages": {}}}}, f, indent=4)
    os.chmod(montage_file, 0o777)

# Load montages
with open(montage_file) as f:
    all_montages = json.load(f)

if eeg_net not in all_montages.get('nets', {}):
    print(f"Error: EEG net '{eeg_net}' not found in montage list.")
    sys.exit(1)

montages = {name: all_montages['nets'][eeg_net]['multi_polar_montages'].get(name) for name in montage_names}

# Initialize logger
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'Simulator_{time.strftime("%Y%m%d_%H%M%S")}.log')

logger = logging_util.get_logger('mTI', log_file, overwrite=False)
logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct'], logger)


def run_simulation(montage_name, electrode_pairs):
    """Run multipolar TI simulation with 4 electrode pairs"""
    logger.info(f"Starting multipolar simulation: {montage_name}")
    
    if len(electrode_pairs) < 4:
        logger.error(f"Need 4 electrode pairs for mTI, got {len(electrode_pairs)}")
        return None
    
    # Setup paths
    montage_dir = os.path.join(simulation_dir, montage_name)
    hf_dir = os.path.join(montage_dir, "high_Frequency")
    ti_mesh_dir = os.path.join(montage_dir, "TI", "mesh")
    mti_mesh_dir = os.path.join(montage_dir, "mTI", "mesh")
    os.makedirs(hf_dir, exist_ok=True)
    os.makedirs(ti_mesh_dir, exist_ok=True)
    os.makedirs(mti_mesh_dir, exist_ok=True)
    
    # Setup SimNIBS session
    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.fnamehead = os.path.join(base_subpath, f"{subject_id}.msh")  # Full path to head mesh
    S.anisotropy_type = sim_type
    S.pathfem = hf_dir
    S.eeg_cap = os.path.join(base_subpath, "eeg_positions", eeg_net)
    S.map_to_surf = False
    S.map_to_fsavg = False
    S.map_to_vol = False
    S.map_to_mni = False
    S.open_in_gmsh = False
    S.tissues_in_niftis = "all"
    S.dti_nii = tensor_file
    
    currents = [intensity1_ch1, intensity1_ch2, intensity2_ch1, intensity2_ch2]
    
    # Create 4 electrode pairs
    for i, pair in enumerate(electrode_pairs[:4]):
        tdcs = S.add_tdcslist()
        tdcs.anisotropy_type = sim_type
        tdcs.currents = [currents[i], -currents[i]]
        
        for j in range(len(tdcs.cond)):
            env_var = f"TISSUE_COND_{j+1}"
            if env_var in os.environ:
                try:
                    tdcs.cond[j].value = float(os.environ[env_var])
                except ValueError:
                    pass
        
        for idx, pos in enumerate(pair):
            electrode = tdcs.add_electrode()
            electrode.channelnr = idx + 1
            electrode.centre = pos
            electrode.shape = electrode_shape
            electrode.dimensions = dimensions
            electrode.thickness = [thickness, 2]
    
    # Run simulation
    logger.info("Running SimNIBS multipolar simulation...")
    run_simnibs(S)
    logger.info("SimNIBS completed")
    
    # Load HF meshes (fnamehead is set to subject_id, so filenames are predictable)
    hf_meshes = []
    
    for i in range(1, 5):
        mesh_file = os.path.join(hf_dir, f"{subject_id}_TDCS_{i}_{sim_type}.msh")
            
        if not os.path.exists(mesh_file):
            logger.error(f"Could not find mesh file: {mesh_file}")
            return None
            
        m = mesh_io.read_msh(mesh_file)
        m = m.crop_mesh(tags=np.hstack((np.arange(1, 100), np.arange(1001, 1100))))
        hf_meshes.append(m)
    
    if len(hf_meshes) != 4:
        logger.error(f"Expected 4 meshes, found {len(hf_meshes)}")
        return None
    
    # Calculate TI pairs
    ti_ab_vectors = get_TI_vectors(hf_meshes[0].field["E"].value, hf_meshes[1].field["E"].value)
    ti_cd_vectors = get_TI_vectors(hf_meshes[2].field["E"].value, hf_meshes[3].field["E"].value)
    
    # Save intermediate TI meshes
    ti_ab_mesh = deepcopy(hf_meshes[0])
    ti_ab_mesh.elmdata = []
    ti_ab_mesh.add_element_field(ti_ab_vectors, "TI_vectors")
    ti_ab_path = os.path.join(ti_mesh_dir, f"{montage_name}_TI_AB.msh")
    mesh_io.write_msh(ti_ab_mesh, ti_ab_path)
    ti_ab_mesh.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"]).write_opt(ti_ab_path)
    
    ti_cd_mesh = deepcopy(hf_meshes[0])
    ti_cd_mesh.elmdata = []
    ti_cd_mesh.add_element_field(ti_cd_vectors, "TI_vectors")
    ti_cd_path = os.path.join(ti_mesh_dir, f"{montage_name}_TI_CD.msh")
    mesh_io.write_msh(ti_cd_mesh, ti_cd_path)
    ti_cd_mesh.view(visible_tags=[1002, 1006], visible_fields=["TI_vectors"]).write_opt(ti_cd_path)
    
    # Calculate and save final mTI
    mti_field = TI.get_maxTI(ti_ab_vectors, ti_cd_vectors)
    mout = deepcopy(hf_meshes[0])
    mout.elmdata = []
    mout.add_element_field(mti_field, "TI_Max")
    
    mti_path = os.path.join(mti_mesh_dir, f"{montage_name}_mTI.msh")
    mesh_io.write_msh(mout, mti_path)
    mout.view(visible_tags=[1002, 1006], visible_fields="TI_Max").write_opt(mti_path)
    
    logger.info(f"Completed: {montage_name}")
    return mti_path

# Run simulations
for montage_name in montage_names:
    if montage_name in montages and montages[montage_name]:
        electrode_pairs = montages[montage_name]
        if not electrode_pairs or len(electrode_pairs) < 4:
            logger.error(f"Need 4 electrode pairs for mTI, found {len(electrode_pairs)} for '{montage_name}'")
            continue
        run_simulation(montage_name, electrode_pairs)
    else:
        logger.error(f"Montage {montage_name} not found")
