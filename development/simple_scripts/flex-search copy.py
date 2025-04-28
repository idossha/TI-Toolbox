
from simnibs import opt_struct
import os

# Initialize optimization structure
# TesFlexOptimization allows for flexible electrode positioning and current optimization
opt = opt_struct.TesFlexOptimization()
# Set path to the subject's head model 
opt.subpath = '/path/to/subject/headmodel'
# Define output directory for results
opt.output_folder = "/path/to/output/folder"

# Set up goal function parameters: could be either mean, 
opt.goal = {user_input}

# either max_TI or dir_TI_normal or dir_TI_tangential
opt.e_postproc = {user_input}

# Setup electrode mapping to standardized positions
opt.net_electrode_file = os.path.join(opt.subpath, "eeg_positions", "{EGI_template}.csv")
# Enable mapping of optimized electrode positions to nearest standard positions
opt.map_to_net_electrodes = True
# Run additional simulation with the mapped electrode positions
opt.run_mapped_electrodes_simulation = True


# Configure electrodes
''' Define first electrode pair '''
electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair") # Pair of TES electrode arrays (here: 1 electrode per array)
electrode_layout.radius = [{user_input}]                                    # radii of electrodes
electrode_layout.current = [{user_input}, -{user_input}]                        # electrode currents

''' Define second electrode pair '''
electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair")
electrode_layout.radius = [{user_input}]                                    # radii of electrodes
electrode_layout.current = [{user_input}, -{user_input}]                        # electrode currents



# if the user goal is mean only target ROI is needed:
########################################################
# Define Region of Interest (ROI)
''' Define ROI '''
roi = opt.add_roi()
roi.method = "surface"
roi.surface_type = "central"                        # define ROI on central GM surfaces
roi.roi_sphere_center_space = "subject"
roi.roi_sphere_center = [x, y, z]       # center of spherical ROI in subject space (in mm)
roi.roi_sphere_radius = X                          # radius of spherical ROI (in mm)

# if the user goal is focality: target ROI and non-target ROI are needed:
#############################################################################
''' Define ROI '''
roi = opt.add_roi()
roi.method = "surface"
roi.surface_type = "central"                            # define ROI on central GM surfaces
roi.roi_sphere_center_space = "subject"
roi.roi_sphere_center = [X, Y, Z]           # center of spherical ROI in subject space (in mm)
roi.roi_sphere_radius = x                              # radius of spherical ROI (in mm)
# uncomment for visual control of ROI:
#roi.subpath = opt.subpath
#roi.write_visualization('','roi.msh')

''' Define non-ROI '''
# all of GM surface except a spherical region with 25 mm around roi center
non_roi = opt.add_roi()
non_roi.method = "surface"
non_roi.surface_type = "central"
non_roi.roi_sphere_center_space = "subject"
non_roi.roi_sphere_center = [X, Y, Z]
non_roi.roi_sphere_radius = x
non_roi.roi_sphere_operator = ["difference"]                             # take difference between GM surface and the sphere region


# the user can also define an ROI based on an atlas:
########################################################

# Define Region of Interest (ROI)
roi = opt.add_roi()

# For surface-based targeting
roi.method = "surface"
roi.surface_type = "central"  # Use the central GM surface
roi.mask_space = "subject_lh"
roi.mask_path = "/{subpath}/label/lh.aparc_DKTatlas.annot"  # Path to FreeSurfer annotation file based on the atlas the user wants to use
roi.mask_value = X  # label value for your target region

# same for non-ROI as with the sphere roi from before.


# Execute the optimization
print("Starting optimization...")
opt.run()
