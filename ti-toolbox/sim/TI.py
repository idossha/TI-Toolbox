import numpy as np
from simnibs import mesh_io, run_simnibs, sim_struct
from simnibs.utils import TI_utils as TI

import json
import os
import sys
import time
from copy import deepcopy
from datetime import datetime

# Local imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools import logging_util
from core import get_path_manager

# Parse command-line arguments
subject_id = sys.argv[1]
sim_type = sys.argv[2]
project_dir = sys.argv[3]
simulation_dir = sys.argv[4]
sim_mode = sys.argv[5]

intensity_str = sys.argv[6]
if ',' in intensity_str:
    intensity1, intensity2 = map(float, intensity_str.split(','))
else:
    intensity1 = intensity2 = float(intensity_str)

electrode_shape = sys.argv[7]
dimensions = [float(x) for x in sys.argv[8].split(',')]
thickness = float(sys.argv[9])
eeg_net = sys.argv[10]

remaining_args = sys.argv[11:]
montage_names = [arg for arg in remaining_args if arg != '--quiet']
quiet_mode = '--quiet' in remaining_args

# Setup paths using PathManager
pm = get_path_manager()
derivatives_dir = pm.get_derivatives_dir()
config_dir = os.path.join(project_dir, 'code', 'ti-toolbox', 'config')
montage_file = os.path.join(config_dir, 'montage_list.json')
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

montages = {}
if montage_names and eeg_net in all_montages.get('nets', {}):
    net_montages = all_montages['nets'][eeg_net]
    montage_type = 'uni_polar_montages' if sys.argv[11] in net_montages.get('uni_polar_montages', {}) else 'multi_polar_montages'
    montages = {name: net_montages[montage_type].get(name) for name in montage_names}

# Initialize logger
log_file = os.environ.get('TI_LOG_FILE')
if not log_file:
    log_dir = os.path.join(derivatives_dir, 'ti-toolbox', 'logs', f'sub-{subject_id}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'Simulator_{time.strftime("%Y%m%d_%H%M%S")}.log')

logger = logging_util.get_logger('TI', log_file, overwrite=False)
logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct'], logger)

# Load flex montages
flex_montages = []
flex_file = os.environ.get('FLEX_MONTAGES_FILE')
if flex_file and os.path.exists(flex_file):
    with open(flex_file, 'r') as f:
        flex_config = json.load(f)
    flex_montages = flex_config if isinstance(flex_config, list) else ([flex_config['montage']] if 'montage' in flex_config else [])
    logger.debug(f"Loaded {len(flex_montages)} flex montage(s)")

def run_simulation(montage_name, montage, is_xyz=False, net=None):
    logger.info(f"Starting simulation: {montage_name}")
    
    # Setup paths
    montage_dir = os.path.join(simulation_dir, montage_name)
    hf_dir = os.path.join(montage_dir, "high_Frequency")
    ti_mesh_dir = os.path.join(montage_dir, "TI", "mesh")
    os.makedirs(montage_dir, exist_ok=True)
    
    # Setup SimNIBS session
    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.fnamehead = os.path.join(base_subpath, f"{subject_id}.msh")  # Full path to head mesh
    S.anisotropy_type = sim_type
    S.pathfem = hf_dir
    if not is_xyz:
        S.eeg_cap = os.path.join(base_subpath, "eeg_positions", net or eeg_net)
    S.map_to_surf = True
    S.map_to_fsavg = False
    S.map_to_vol = True
    S.map_to_mni = True
    S.open_in_gmsh = False
    S.tissues_in_niftis = "all"
    S.dti_nii = tensor_file
    
    # First electrode pair
    tdcs = S.add_tdcslist()
    tdcs.anisotropy_type = sim_type
    tdcs.currents = [intensity1, -intensity1]
    
    for i in range(len(tdcs.cond)):
        env_var = f"TISSUE_COND_{i+1}"
        if env_var in os.environ:
            try:
                tdcs.cond[i].value = float(os.environ[env_var])
            except ValueError:
                pass
    
    for idx, pos in enumerate(montage[0]):
        electrode = tdcs.add_electrode()
        electrode.channelnr = idx + 1
        electrode.centre = pos
        electrode.shape = electrode_shape
        electrode.dimensions = dimensions
        electrode.thickness = [thickness, 2]
    
    # Second electrode pair
    tdcs_2 = S.add_tdcslist(deepcopy(tdcs))
    tdcs_2.currents = [intensity2, -intensity2]
    tdcs_2.electrode[0].centre = montage[1][0]
    tdcs_2.electrode[1].centre = montage[1][1]
    
    # Run simulation
    logger.info("Running SimNIBS...")
    run_simnibs(S)
    logger.info("SimNIBS completed")
    
    # Find output files with explicit subject prefix
    m1_file = os.path.join(S.pathfem, f"{subject_id}_TDCS_1_{sim_type}.msh")
    m2_file = os.path.join(S.pathfem, f"{subject_id}_TDCS_2_{sim_type}.msh")
    
    # Load and process meshes
    m1 = mesh_io.read_msh(m1_file)
    m2 = mesh_io.read_msh(m2_file)
    
    tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
    m1 = m1.crop_mesh(tags=tags_keep)
    m2 = m2.crop_mesh(tags=tags_keep)
    
    # Calculate TI max
    TImax = TI.get_maxTI(m1.field["E"].value, m2.field["E"].value)
    
    # Calculate TI normal (central surface if available)
    overlays_dir = os.path.join(S.pathfem, "subject_overlays")
    central_1 = os.path.join(overlays_dir, f"{subject_id}_TDCS_1_{sim_type}_central.msh")
    central_2 = os.path.join(overlays_dir, f"{subject_id}_TDCS_2_{sim_type}_central.msh")
    
    if os.path.exists(central_1) and os.path.exists(central_2):
        cm1 = mesh_io.read_msh(central_1)
        cm2 = mesh_io.read_msh(central_2)
        
        if hasattr(cm1, 'field') and 'E' in cm1.field:
            ef1_c, ef2_c = cm1.field["E"], cm2.field["E"]
        else:
            normals = cm1.nodes_normals().value
            ef1_c = type('', (), {'value': cm1.field["E_normal"].value.reshape(-1, 1) * normals})()
            ef2_c = type('', (), {'value': cm2.field["E_normal"].value.reshape(-1, 1) * normals})()
        
        TI_normal = TI.get_dirTI(ef1_c.value, ef2_c.value, cm1.nodes_normals().value)
        
        mout_c = deepcopy(cm1)
        mout_c.nodedata = []
        mout_c.add_node_field(TI_normal, "TI_normal")
        normal_path = os.path.join(ti_mesh_dir, f"{montage_name}_normal.msh")
        mesh_io.write_msh(mout_c, normal_path)
        mout_c.view(visible_fields=["TI_normal"]).write_opt(normal_path)
        logger.debug(f"Saved {montage_name}_normal.msh")
    
    # Save TI max mesh
    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(TImax, "TI_max")
    ti_path = os.path.join(ti_mesh_dir, f"{montage_name}_TI.msh")
    mesh_io.write_msh(mout, ti_path)
    mout.view(visible_tags=[1002, 1006], visible_fields=["TI_max"]).write_opt(ti_path)
    
    logger.info(f"Completed: {montage_name}")

# Run regular montages
for name in montage_names:
    if name in montages and montages[name]:
        # For freehand mode, electrode positions are XYZ coordinates, not electrode names
        is_xyz_mode = eeg_net in ["freehand", "flex_mode"]
        try:
            run_simulation(name, montages[name], is_xyz=is_xyz_mode)
        except Exception as e:
            logger.error(f"Failed to run regular montage {name}: {e}")
            import traceback
            traceback.print_exc()

# Run flex montages
for flex in flex_montages:
    montage_name = flex['name']
    montage_type = flex['type']

    try:
        if montage_type == 'flex_mapped':
            pairs = flex['pairs']
            montage_data = [[pairs[0][0], pairs[0][1]], [pairs[1][0], pairs[1][1]]]
            run_simulation(montage_name, montage_data, is_xyz=False, net=flex.get('eeg_net', eeg_net))
        elif montage_type == 'flex_optimized':
            ep = flex['electrode_positions']
            montage_data = [[ep[0], ep[1]], [ep[2], ep[3]]]
            run_simulation(montage_name, montage_data, is_xyz=True)
        elif montage_type == 'freehand_xyz':
            # Freehand mode: electrode positions are XYZ coordinates
            ep = flex['electrode_positions']
            montage_data = [[ep[0], ep[1]], [ep[2], ep[3]]]
            run_simulation(montage_name, montage_data, is_xyz=True)
        else:
            logger.warning(f"Unknown flex montage type: {montage_type}")
    except Exception as e:
        logger.error(f"Failed to run flex montage {montage_name} ({montage_type}): {e}")
        import traceback
        traceback.print_exc()

# Create completion report
completed = []
actual_regular_montages = 0
for name in montage_names:
    if name in montages and montages[name]:  # Only count montages that will actually be processed
        actual_regular_montages += 1
        ti_mesh = os.path.join(simulation_dir, name, "TI", "mesh", f"{name}_TI.msh")
        if os.path.exists(ti_mesh):
            completed.append({'montage_name': name, 'montage_type': 'regular', 'status': 'completed'})

for flex in flex_montages:
    ti_mesh = os.path.join(simulation_dir, flex['name'], "TI", "mesh", f"{flex['name']}_TI.msh")
    if os.path.exists(ti_mesh):
        completed.append({'montage_name': flex['name'], 'montage_type': flex['type'], 'status': 'completed'})

report = {
    'session_id': os.environ.get('SIMULATION_SESSION_ID', 'unknown'),
    'subject_id': subject_id,
    'project_dir': project_dir,
    'simulation_dir': simulation_dir,
    'completed_simulations': completed,
    'timestamp': datetime.now().isoformat(),
    'total_simulations': actual_regular_montages + len(flex_montages),
    'success_count': len(completed),
    'error_count': actual_regular_montages + len(flex_montages) - len(completed)
}

report_file = os.path.join(project_dir, 'derivatives', 'temp', f'simulation_completion_{subject_id}_{int(time.time())}.json')
os.makedirs(os.path.dirname(report_file), exist_ok=True)
with open(report_file, 'w') as f:
    json.dump(report, f, indent=2)

logger.info(f"Completed {report['success_count']}/{report['total_simulations']} simulations")
