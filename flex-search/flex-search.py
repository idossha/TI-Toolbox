#!/usr/bin/env python3

from simnibs import opt_struct
import os
import argparse
import sys

def parse_arguments():
    parser = argparse.ArgumentParser(description='Flexible electrode position optimization for TI stimulation')
    
    parser.add_argument('--subject', required=True,
                      help='Subject ID')
    parser.add_argument('--goal', required=True, choices=['mean', 'focality'],
                      help='Optimization goal: mean or focality')
    parser.add_argument('--postproc', required=True, 
                      choices=['max_TI', 'dir_TI_normal', 'dir_TI_tangential'],
                      help='Post-processing method')
    parser.add_argument('--eeg-net', required=True,
                      help='EEG net template name (must match a .csv file in the subject\'s eeg_positions directory)')
    parser.add_argument('--radius', required=True, type=float,
                      help='Electrode radius in mm')
    parser.add_argument('--current', required=True, type=float,
                      help='Electrode current in mA')
    parser.add_argument('--roi-method', required=True,
                      choices=['spherical', 'cortical'],
                      help='ROI definition method')
    parser.add_argument('--output-dir', required=True,
                      help='Output directory for results')
    
    args = parser.parse_args()
    
    # Validate that the EEG net template exists
    project_dir = os.getenv('PROJECT_DIR')
    if not project_dir:
        raise ValueError("PROJECT_DIR environment variable not set")
    
    eeg_net_path = os.path.join(project_dir, 'Subjects', f'm2m_{args.subject}', 
                               'eeg_positions', f'{args.eeg_net}.csv')
    if not os.path.exists(eeg_net_path):
        raise ValueError(f"EEG net template file not found: {eeg_net_path}")
    
    return args

def setup_optimization(args):
    # Initialize optimization structure
    opt = opt_struct.TesFlexOptimization()
    
    # Set paths
    project_dir = os.getenv('PROJECT_DIR')
    if not project_dir:
        raise ValueError("PROJECT_DIR environment variable not set")
    
    # Set subject path
    opt.subpath = os.path.join(project_dir, 'Subjects', f'm2m_{args.subject}')
    if not os.path.exists(opt.subpath):
        raise ValueError(f"Subject directory not found: {opt.subpath}")
    
    # Set output directory
    opt.output_folder = args.output_dir
    os.makedirs(opt.output_folder, exist_ok=True)
    
    # Set optimization goal
    opt.goal = args.goal
    
    # Set post-processing method
    opt.e_postproc = args.postproc
    
    # Setup electrode mapping
    opt.net_electrode_file = os.path.join(opt.subpath, "eeg_positions", f"{args.eeg_net}.csv")
    opt.map_to_net_electrodes = True
    opt.run_mapped_electrodes_simulation = True
    
    # Configure electrode pairs
    # First pair
    electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair")
    electrode_layout.radius = [args.radius]
    electrode_layout.current = [args.current/1000.0, -args.current/1000.0]  # Convert mA to A
    
    # Second pair
    electrode_layout = opt.add_electrode_layout("ElectrodeArrayPair")
    electrode_layout.radius = [args.radius]
    electrode_layout.current = [args.current/1000.0, -args.current/1000.0]  # Convert mA to A
    
    # Setup ROI based on method
    if args.roi_method == 'spherical':
        setup_spherical_roi(opt, args.goal)
    else:  # cortical
        setup_cortical_roi(opt, args.goal)
    
    return opt

def setup_spherical_roi(opt, goal):
    # Define target ROI
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.roi_sphere_center_space = "subject"
    
    # Get ROI coordinates from environment variables
    try:
        x = float(os.getenv('ROI_X'))
        y = float(os.getenv('ROI_Y'))
        z = float(os.getenv('ROI_Z'))
        radius = float(os.getenv('ROI_RADIUS'))
    except (TypeError, ValueError) as e:
        raise ValueError("Missing or invalid ROI coordinates or radius in environment variables") from e
    
    roi.roi_sphere_center = [x, y, z]
    roi.roi_sphere_radius = radius
    
    # If goal is focality, add non-ROI
    if goal == 'focality':
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"
        non_roi.roi_sphere_center_space = "subject"
        non_roi.roi_sphere_center = [x, y, z]
        non_roi.roi_sphere_radius = radius + 25  # 25mm larger than target ROI
        non_roi.roi_sphere_operator = ["difference"]

def setup_cortical_roi(opt, goal):
    # Define target ROI
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.mask_space = "subject_lh"
    
    # Get atlas information from environment variables
    try:
        label_value = int(os.getenv('ROI_LABEL'))
        atlas_path = os.getenv('ATLAS_PATH')
        if not atlas_path:
            raise ValueError("ATLAS_PATH environment variable not set")
    except (TypeError, ValueError) as e:
        raise ValueError("Missing or invalid ROI label or atlas path in environment variables") from e
    
    roi.mask_path = os.path.join(opt.subpath, "label", atlas_path)
    roi.mask_value = label_value
    
    # If goal is focality, add non-ROI with same setup but different operator
    if goal == 'focality':
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"
        non_roi.mask_space = "subject_lh"
        non_roi.mask_path = roi.mask_path
        non_roi.mask_value = label_value
        non_roi.roi_sphere_operator = ["difference"]

def main():
    try:
        # Parse command-line arguments
        args = parse_arguments()
        
        # Setup optimization
        opt = setup_optimization(args)
        
        # Run optimization
        print("Starting optimization...")
        opt.run()
        
        print("Optimization completed successfully.")
        return 0
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
