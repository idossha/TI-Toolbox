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

# Initialize flex_montages early (will be populated after logger init)
flex_montages = []

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

# Check if we have any regular montages
if not montage_names:
    montages = {}  # No standard montages to process
    print("No regular montages provided, skipping montage validation")
else:
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
    derivatives_dir = os.path.join(project_dir, 'derivatives')
    log_dir = os.path.join(derivatives_dir, 'logs', f'sub-{subject_id}')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'Simulator_{time_stamp}.log')

# Initialize our main logger
logger = logging_util.get_logger('TI', log_file, overwrite=False)

# Configure SimNIBS related loggers to use our logging setup
logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct'], logger)

# Check if we have flex montages file (now after logger init)
flex_montages_file = os.environ.get('FLEX_MONTAGES_FILE')
if flex_montages_file and os.path.exists(flex_montages_file):
    logger.debug(f"Loading flex montage from: {flex_montages_file}")
    with open(flex_montages_file, 'r') as f:
        flex_config = json.load(f)
    
    # Handle new individual config format vs old array format
    if isinstance(flex_config, list):
        # Old format - array of montages
        flex_montages = flex_config
        logger.debug(f"Loaded {len(flex_montages)} flex montages (legacy format)")
    elif isinstance(flex_config, dict) and 'montage' in flex_config:
        # New format - single config with subject_id, eeg_net, and montage
        flex_montages = [flex_config['montage']]
        logger.debug(f"Loaded individual flex montage: {flex_config['montage']['name']} for subject {flex_config['subject_id']}")
        logger.debug(f"Using EEG net: {flex_config['eeg_net']}")
    else:
        logger.warning(f"Unrecognized flex montages file format: {type(flex_config)}")
        flex_montages = []
    
    # Note: Don't clean up the temporary file here - the CLI will handle cleanup
    logger.debug(f"Processing {len(flex_montages)} flex montage(s)")
else:
    logger.debug("No flex montages file provided")

# Base paths
derivatives_dir = os.path.join(project_dir, 'derivatives')
simnibs_dir = os.path.join(derivatives_dir, 'SimNIBS', f'sub-{subject_id}')
base_subpath = os.path.join(simnibs_dir, f'm2m_{subject_id}')
conductivity_path = base_subpath
tensor_file = os.path.join(conductivity_path, "DTI_coregT1_tensor.nii.gz")

# Create temporary directory for SimNIBS output
temp_dir = os.path.join(simulation_dir, "tmp")
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir, exist_ok=True)
    logger.debug(f"Created temporary directory at {temp_dir}")

# Function to run simulations
def run_simulation(montage_name, montage, is_xyz=False, eeg_net=None):
    logger.info(f"Starting simulation for montage: {montage_name}")
    
    if not validate_montage(montage, montage_name):
        logger.error(f"Invalid montage structure for {montage_name}. Skipping.")
        return

    S = sim_struct.SESSION()
    S.subpath = base_subpath
    S.anisotropy_type = sim_type
    
    logger.debug(f"Set up SimNIBS session with anisotropy type: {sim_type}")
    
    # Use temporary directory for SimNIBS output
    S.pathfem = os.path.join(temp_dir, montage_name)
    
    # Use the selected EEG net (only if not using XYZ coordinates)
    if not is_xyz:
        # Use the passed eeg_net parameter if provided, otherwise use the global one
        net_to_use = eeg_net if eeg_net else globals()['eeg_net']
        S.eeg_cap = os.path.join(base_subpath, "eeg_positions", net_to_use)
    
    S.map_to_surf = True  # Enable cortical surface mapping for middle surface analysis
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
                logger.debug(f"Setting conductivity for tissue {tissue_num} to {tdcs.cond[i].value} S/m")
            except ValueError:
                logger.warning(f"Invalid conductivity value for tissue {tissue_num}")

    # Set currents for first pair using intensity1
    tdcs.currents = [intensity1, -intensity1]
    
    # First electrode
    electrode = tdcs.add_electrode()
    electrode.channelnr = 1
    if is_xyz:
        # For XYZ coordinates, montage[0][0] is already a list [x, y, z]
        electrode.centre = montage[0][0]
    else:
        # For electrode names, montage[0][0] is a string
        electrode.centre = montage[0][0]
    electrode.shape = electrode_shape
    electrode.dimensions = dimensions
    electrode.thickness = [thickness, 2]

    # Second electrode
    electrode = tdcs.add_electrode()
    electrode.channelnr = 2
    if is_xyz:
        electrode.centre = montage[0][1]
    else:
        electrode.centre = montage[0][1]
    electrode.shape = electrode_shape
    electrode.dimensions = dimensions
    electrode.thickness = [thickness, 2]

    # Second electrode pair
    tdcs_2 = S.add_tdcslist(deepcopy(tdcs))
    # Set currents for second pair using intensity2
    tdcs_2.currents = [intensity2, -intensity2]
    tdcs_2.electrode[0].centre = montage[1][0] if is_xyz else montage[1][0]
    tdcs_2.electrode[1].centre = montage[1][1] if is_xyz else montage[1][1]

    logger.info("Running SimNIBS simulation...")
    run_simnibs(S)
    logger.info("SimNIBS simulation completed")

    subject_identifier = base_subpath.split('_')[-1]
    anisotropy_type = S.anisotropy_type

    m1_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_1_{anisotropy_type}.msh")
    m2_file = os.path.join(S.pathfem, f"{subject_identifier}_TDCS_2_{anisotropy_type}.msh")

    logger.debug("Loading mesh files for TI calculation")
    m1 = mesh_io.read_msh(m1_file)
    m2 = mesh_io.read_msh(m2_file)

    tags_keep = np.hstack((np.arange(1, 100), np.arange(1001, 1100)))
    m1 = m1.crop_mesh(tags=tags_keep)
    m2 = m2.crop_mesh(tags=tags_keep)

    ef1 = m1.field["E"]
    ef2 = m2.field["E"]
    logger.debug("Calculating TI maximum values")
    TImax = TI.get_maxTI(ef1.value, ef2.value)

    # Calculate TI normal component using middle cortical surface
    logger.debug("Calculating TI normal component for middle cortical surface")
    try:
        # Look for central surface files (middle cortical layer)
        central_file_1 = os.path.join(S.pathfem, "subject_overlays", f"{subject_identifier}_TDCS_1_{anisotropy_type}_central.msh")
        central_file_2 = os.path.join(S.pathfem, "subject_overlays", f"{subject_identifier}_TDCS_2_{anisotropy_type}_central.msh")
        
        # Initialize TI_normal array with zeros for all elements
        TI_normal = np.zeros(len(ef1.value))
        TI_normal_central = None
        
        if os.path.exists(central_file_1) and os.path.exists(central_file_2):
            logger.debug("Using middle cortical surface (central.msh files) for normal calculation")
            
            # Load central surface meshes
            central_m1 = mesh_io.read_msh(central_file_1)
            central_m2 = mesh_io.read_msh(central_file_2)
            
            # Check what fields are available in the central mesh
            available_fields_1 = [field.field_name for field in central_m1.nodedata + central_m1.elmdata]
            available_fields_2 = [field.field_name for field in central_m2.nodedata + central_m2.elmdata]
            logger.debug(f"Available fields in central mesh 1: {available_fields_1}")
            logger.debug(f"Available fields in central mesh 2: {available_fields_2}")
            
            # Get 3D electric field vectors from central surface files
            # We need the full E field vectors (not just normal components) for proper TI calculation
            try:
                # Method 1: Try to get full E field vectors directly
                ef1_central = None
                ef2_central = None
                
                # Try different field access methods
                if hasattr(central_m1, 'field') and 'E' in central_m1.field:
                    ef1_central = central_m1.field["E"]
                    ef2_central = central_m2.field["E"]
                    logger.debug("Found full E field vectors using field['E'] accessor")
                else:
                    # Method 2: Reconstruct E field from components if available
                    try:
                        # Get individual components
                        ef1_normal = central_m1.field["E_normal"]
                        ef1_tangent = central_m1.field["E_tangent"] 
                        ef2_normal = central_m2.field["E_normal"]
                        ef2_tangent = central_m2.field["E_tangent"]
                        
                        # Calculate surface normals and tangent directions
                        surface_normals = central_m1.nodes_normals().value
                        
                        # Reconstruct 3D E field vectors (this is an approximation)
                        # E = E_normal * normal + E_tangent * tangent_direction
                        # For simplicity, we'll use a basic approach where tangent is in the xy-plane
                        n_nodes = len(ef1_normal.value)
                        
                        # Create approximate 3D vectors using normal and magnitude info
                        ef1_3d = np.zeros((n_nodes, 3))
                        ef2_3d = np.zeros((n_nodes, 3))
                        
                        # Use normal component along normal direction
                        ef1_3d = ef1_normal.value.reshape(-1, 1) * surface_normals
                        ef2_3d = ef2_normal.value.reshape(-1, 1) * surface_normals
                        
                        # Create field objects
                        ef1_central = type('', (), {'value': ef1_3d})()
                        ef2_central = type('', (), {'value': ef2_3d})()
                        
                        logger.debug("Reconstructed 3D E field vectors from normal components")
                        logger.warning("Using approximated 3D vectors - results may be less accurate")
                        
                    except Exception as reconstruct_error:
                        logger.error(f"Could not reconstruct E field vectors: {str(reconstruct_error)}")
                        raise ValueError("Could not access full E field vectors from central surface files")
                
                logger.debug(f"E field 1 has {len(ef1_central.value)} nodes with shape {ef1_central.value.shape}")
                logger.debug(f"E field 2 has {len(ef2_central.value)} nodes with shape {ef2_central.value.shape}")
                
            except Exception as e:
                logger.error(f"Could not access E field data: {str(e)}")
                logger.warning("Available node data fields: " + str([f.field_name for f in central_m1.nodedata]))
                logger.warning("Available element data fields: " + str([f.field_name for f in central_m1.elmdata]))
                raise ValueError("E field data not found in central surface files")
            
            # Calculate surface normals for directional calculation
            surface_normals = central_m1.nodes_normals().value
            
            # Calculate TI normal component using the proper SimNIBS method
            # This follows the exact approach used in tes_flex_optimization.py
            TI_normal_central = TI.get_dirTI(E1=ef1_central.value, E2=ef2_central.value, dirvec_org=surface_normals)
            
            logger.debug(f"Calculated TI normal component for {len(TI_normal_central)} nodes on middle cortical surface")
            logger.debug(f"TI_normal range: {np.min(TI_normal_central):.6f} to {np.max(TI_normal_central):.6f} V/m")
            
            # Save the central surface TI normal as a separate mesh file (TI_normal only)
            mout_central = deepcopy(central_m1)
            mout_central.nodedata = []
            mout_central.add_node_field(TI_normal_central, "TI_normal")
            
            # Write central surface mesh with TI fields
            central_ti_file = os.path.join(S.pathfem, "TI_central.msh")
            mesh_io.write_msh(mout_central, central_ti_file)
            
            # Create visualization for central surface (TI_normal only)
            v_central = mout_central.view(visible_fields=["TI_normal"])
            v_central.write_opt(central_ti_file)
            
            logger.debug(f"Saved middle cortical surface TI_normal analysis to: {central_ti_file}")
        
        else:
            logger.warning("Central surface files not found, falling back to superficial cortical surface")
            logger.debug("To use middle cortical surface, ensure map_to_surf=True in simulation settings")
            
            # Fallback to original method using superficial surface
            # Get indices of gray matter elements in the original mesh
            gm_indices = np.isin(m1.elm.tag1, [1002])
            
            if np.any(gm_indices):
                # Extract gray matter surface (tag 1002) for normal calculation
                gm_mesh = m1.crop_mesh(tags=[1002])
                
                if len(gm_mesh.elm.elm_number) > 0:
                    # Calculate surface normals for the gray matter surface
                    surface_normals = gm_mesh.triangle_normals()
                    
                    # Get electric fields for gray matter elements only
                    ef1_gm = ef1.value[gm_indices]
                    ef2_gm = ef2.value[gm_indices]
                    
                    # The surface normals from cropped mesh should match the gray matter elements
                    if len(surface_normals.value) == len(ef1_gm):
                        # Calculate directional TI along normal direction for gray matter
                        TI_normal_gm = TI.get_dirTI(ef1_gm, ef2_gm, surface_normals.value)
                        
                        # Assign calculated values to gray matter elements
                        TI_normal[gm_indices] = TI_normal_gm
                        
                        logger.debug(f"Calculated TI normal component for {len(TI_normal_gm)} superficial cortical elements")
                    else:
                        logger.warning(f"Dimension mismatch: normals {len(surface_normals.value)} vs fields {len(ef1_gm)}")
                else:
                    logger.warning("No gray matter surface found after cropping")
            else:
                logger.warning("No gray matter elements found for normal calculation")
            
    except Exception as e:
        logger.error(f"Error calculating TI normal component: {str(e)}")
        logger.debug("Setting TI_normal to zeros due to error")
        TI_normal = np.zeros(len(ef1.value))

    logger.debug("Writing output mesh files")
    mout = deepcopy(m1)
    mout.elmdata = []
    mout.add_element_field(TImax, "TI_max")
    # NOTE: TI_normal is NOT added to volume mesh - it's only in the central surface mesh
    mesh_io.write_msh(mout, os.path.join(S.pathfem, "TI.msh"))

    v = mout.view(visible_tags=[1002, 1006], visible_fields=["TI_max"])
    v.write_opt(os.path.join(S.pathfem, "TI.msh"))
    logger.info(f"Completed simulation for montage: {montage_name}")
    logger.info(f"Volume mesh (TI.msh) contains TI_max field only")
    logger.info(f"Central surface mesh (TI_central.msh) contains TI_normal field only")

# Run the simulations for each selected montage
if montage_names:
    for name in montage_names:
        if name in montages and montages[name]:
            run_simulation(name, montages[name], is_xyz=False)
        else:
            logger.error(f"Montage {name} not found or invalid. Skipping.")
else:
    logger.debug("No regular montages to simulate")

# Run simulations for flex montages
for flex_montage in flex_montages:
    montage_name = flex_montage['name']
    montage_type = flex_montage['type']
    
    # Create directories for this flex montage
    montage_dir = os.path.join(simulation_dir, montage_name)
    os.makedirs(montage_dir, exist_ok=True)
    os.makedirs(os.path.join(montage_dir, "high_Frequency", "mesh"), exist_ok=True)
    os.makedirs(os.path.join(montage_dir, "high_Frequency", "niftis"), exist_ok=True)
    os.makedirs(os.path.join(montage_dir, "high_Frequency", "analysis"), exist_ok=True)
    os.makedirs(os.path.join(montage_dir, "TI", "mesh"), exist_ok=True)
    os.makedirs(os.path.join(montage_dir, "TI", "niftis"), exist_ok=True)
    os.makedirs(os.path.join(montage_dir, "TI", "montage_imgs"), exist_ok=True)
    os.makedirs(os.path.join(montage_dir, "documentation"), exist_ok=True)
    logger.debug(f"Created directory structure for flex montage: {montage_name}")
    
    if montage_type == 'flex_mapped':
        # For mapped electrodes, use electrode labels and EEG net from the JSON
        electrode_labels = flex_montage['electrode_labels']
        pairs = flex_montage['pairs']
        eeg_net_for_montage = flex_montage.get('eeg_net', eeg_net)  # Use from JSON, fallback to default
        
        # Convert to the expected format
        montage_data = [[pairs[0][0], pairs[0][1]], [pairs[1][0], pairs[1][1]]]
        logger.info(f"Running flex mapped simulation with electrodes: {electrode_labels}")
        logger.debug(f"Using EEG net from flex-search: {eeg_net_for_montage}")
        
        # Temporarily set the EEG net for this simulation
        original_eeg_net = eeg_net
        eeg_net = eeg_net_for_montage
        run_simulation(montage_name, montage_data, is_xyz=False, eeg_net=eeg_net_for_montage)
        eeg_net = original_eeg_net  # Restore original
    
    elif montage_type == 'flex_optimized':
        # For optimized electrodes, use XYZ coordinates (no EEG net needed)
        electrode_positions = flex_montage['electrode_positions']
        # Format: [[pos1, pos2], [pos3, pos4]] where each pos is [x, y, z]
        montage_data = [[electrode_positions[0], electrode_positions[1]], 
                        [electrode_positions[2], electrode_positions[3]]]
        logger.info(f"Running flex optimized simulation with XYZ coordinates")
        run_simulation(montage_name, montage_data, is_xyz=True)

# Create a simulation completion report for the GUI
completion_report = {
    'session_id': os.environ.get('SIMULATION_SESSION_ID', 'unknown'),
    'subject_id': subject_id,
    'project_dir': project_dir,
    'simulation_dir': simulation_dir,
    'completed_simulations': [],
    'timestamp': datetime.now().isoformat(),
    'total_simulations': 0,
    'success_count': 0,
    'error_count': 0
}

# Track completed regular montages
successful_montages = []
if montage_names:
    for name in montage_names:
        if name in montages and montages[name]:
            # Check if simulation files were created
            temp_montage_dir = os.path.join(temp_dir, name)
            if os.path.exists(temp_montage_dir):
                ti_mesh_file = os.path.join(temp_montage_dir, "TI.msh")
                if os.path.exists(ti_mesh_file):
                    successful_montages.append(name)
                    completion_report['completed_simulations'].append({
                        'montage_name': name,
                        'montage_type': 'regular',
                        'status': 'completed',
                        'temp_path': temp_montage_dir,
                        'output_files': {
                            'TI': [ti_mesh_file]
                        }
                    })
                    completion_report['success_count'] += 1
                else:
                    logger.error(f"TI mesh file not found for {name}")
                    completion_report['error_count'] += 1
            else:
                logger.error(f"Simulation directory not found for {name}")
                completion_report['error_count'] += 1
        else:
            logger.error(f"Montage {name} not found or invalid")
            completion_report['error_count'] += 1

# Track completed flex montages
successful_flex_montages = []
for flex_montage in flex_montages:
    montage_name = flex_montage['name']
    temp_montage_dir = os.path.join(temp_dir, montage_name)
    
    if os.path.exists(temp_montage_dir):
        ti_mesh_file = os.path.join(temp_montage_dir, "TI.msh")
        if os.path.exists(ti_mesh_file):
            successful_flex_montages.append(montage_name)
            completion_report['completed_simulations'].append({
                'montage_name': montage_name,
                'montage_type': flex_montage['type'],
                'status': 'completed',
                'temp_path': temp_montage_dir,
                'output_files': {
                    'TI': [ti_mesh_file]
                }
            })
            completion_report['success_count'] += 1
        else:
            logger.error(f"TI mesh file not found for flex montage {montage_name}")
            completion_report['error_count'] += 1
    else:
        logger.error(f"Simulation directory not found for flex montage {montage_name}")
        completion_report['error_count'] += 1

completion_report['total_simulations'] = len(montage_names) + len(flex_montages)

# Write completion report to a file the GUI can read
completion_file = os.path.join(project_dir, 'derivatives', 'temp', f'simulation_completion_{subject_id}_{int(time.time())}.json')
os.makedirs(os.path.dirname(completion_file), exist_ok=True)
with open(completion_file, 'w') as f:
    json.dump(completion_report, f, indent=2)

logger.info(f"Simulation completion report written to: {completion_file}")
logger.info(f"Successfully completed {completion_report['success_count']}/{completion_report['total_simulations']} simulations")

logger.info("All simulations completed successfully")
        