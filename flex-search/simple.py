from simnibs import opt_struct
import os
import numpy as np

# Initialize optimization structure
# TesFlexOptimization allows for flexible electrode positioning and current optimization
opt = opt_struct.TesFlexOptimization()

# Set path to the subject's head model 
opt.subpath = '/Users/idohaber/Git-Projects/4.5_learn/sample_data/m2m_101'

# Define output directory for results
opt.output_folder = "Left_INSULA_focal"

# Set up goal function parameters
# "mean" optimizes for the mean electric field in the ROI
opt.goal = "focality"

opt.e_postproc = "max_TI"

# Configure electrodes

''' Define first electrode pair '''
electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair") # Pair of TES electrode arrays (here: 1 electrode per array)
electrode_layout.radius = [4]                                    # radii of electrodes
electrode_layout.current = [0.008, -0.008]                        # electrode currents

''' Define second electrode pair '''
electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair")
electrode_layout.radius = [4]
electrode_layout.current = [0.008, -0.008]



# Define Region of Interest (ROI)
roi = opt.add_roi()

# For surface-based targeting
roi.method = "surface"
roi.surface_type = "central"  # Use the central GM surface
roi.mask_path = ["/Users/idohaber/Git-Projects/4.5_learn/sample_data/m2m_101/label_prep/lh.101_DK40.annot"]
roi.mask_value = [35]  # label value for target region
roi.mask_space = ["subject_lh"]
roi.mask_operator = ["intersection"]  # Default operator for the ROI

# Define everything else as non-ROI for focality
non_roi = opt.add_roi()
non_roi.method = "surface"
non_roi.surface_type = "central"
non_roi.mask_path = ["/Users/idohaber/Git-Projects/4.5_learn/sample_data/m2m_101/label_prep/lh.101_DK40.annot"]
non_roi.mask_space = ["subject_lh"]
non_roi.mask_value = [35]
non_roi.mask_operator = ["difference"]  # This will select everything except the ROI
non_roi.weight = -1  # Negative weight to minimize field in non-ROI regions

# Setup electrode mapping to standardized positions
opt.net_electrode_file = os.path.join(opt.subpath, "eeg_positions", "EGI_template.csv")
opt.map_to_net_electrodes = True
opt.run_mapped_electrodes_simulation = True

# Execute the optimization
print("Starting optimization...")
opt.run()