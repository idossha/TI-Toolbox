#!/usr/bin/env python3

from simnibs import opt_struct
import os
import argparse
import sys

def get_roi_dirname(args):
    """Generate directory name based on ROI type and parameters."""
    base_name = ""
    if args.roi_method == 'spherical':
        try:
            x = float(os.getenv('ROI_X'))
            y = float(os.getenv('ROI_Y'))
            z = float(os.getenv('ROI_Z'))
            radius = float(os.getenv('ROI_RADIUS'))
            base_name = f"{x}x{y}y{z}z_{radius}mm"
        except (TypeError, ValueError) as e:
            raise ValueError("Missing or invalid ROI coordinates or radius in environment variables") from e
    else:  # atlas
        try:
            atlas_name = os.path.splitext(os.path.basename(os.getenv('ATLAS_PATH')))[0]
            label_value = int(os.getenv('ROI_LABEL'))
            base_name = f"{atlas_name}_{label_value}"
        except (TypeError, ValueError) as e:
            raise ValueError("Missing or invalid atlas information in environment variables") from e
    
    # Add goal to directory name
    dirname = f"{base_name}_{args.goal}"
    
    # Add non-ROI method for focality
    if args.goal == 'focality' and args.non_roi_method == 'specific':
        dirname += "_specific"
    
    return dirname

def parse_arguments():
    parser = argparse.ArgumentParser(description='Flexible electrode position optimization for TI stimulation')
    
    parser.add_argument('--subject', required=True,
                      help='Subject ID')
    parser.add_argument('--goal', required=True, choices=['mean', 'focality', 'max'],
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
                      choices=['spherical', 'atlas'],
                      help='ROI definition method')
    parser.add_argument('--non-roi-method', choices=['everything_else', 'specific'],
                      help='Method for defining non-ROI when goal is focality')
    parser.add_argument('--thresholds',
                      help='Threshold values for focality optimization. Either a single value or two comma-separated values.')
    
    args = parser.parse_args()
    
    # Validate thresholds for focality optimization
    if args.goal == 'focality':
        if not args.thresholds:
            raise ValueError("--thresholds is required when goal is focality")
        
        # Parse threshold values
        threshold_values = args.thresholds.split(',')
        if len(threshold_values) not in [1, 2]:
            raise ValueError("--thresholds must be either a single value or two comma-separated values")
        
        try:
            args.threshold_values = [float(v) for v in threshold_values]
        except ValueError:
            raise ValueError("Invalid threshold values. Must be numeric.")
    
    # Validate that the EEG net template exists
    project_dir = os.getenv('PROJECT_DIR')
    if not project_dir:
        raise ValueError("PROJECT_DIR environment variable not set")
    
    # Generate output directory path based on ROI type
    roi_dirname = get_roi_dirname(args)
    args.output_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{args.subject}', 'flex-search', roi_dirname)
    
    eeg_net_path = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{args.subject}', 
                               f"m2m_{args.subject}", 'eeg_positions', f'{args.eeg_net}.csv')
    if not os.path.exists(eeg_net_path):
        raise ValueError(f"EEG net template file not found: {eeg_net_path}")
    
    # Validate non-ROI method if goal is focality
    if args.goal == 'focality':
        if not args.non_roi_method:
            raise ValueError("--non-roi-method is required when goal is focality")
        if args.non_roi_method not in ['everything_else', 'specific']:
            raise ValueError("Invalid non-ROI method. Must be 'everything_else' or 'specific'")
    
    return args

def setup_optimization(args):
    # Initialize optimization structure
    opt = opt_struct.TesFlexOptimization()
    
    # Set paths
    project_dir = os.getenv('PROJECT_DIR')
    if not project_dir:
        raise ValueError("PROJECT_DIR environment variable not set")
    
    # Set subject path using new directory structure
    opt.subpath = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{args.subject}', f"m2m_{args.subject}")
    if not os.path.exists(opt.subpath):
        raise ValueError(f"Subject directory not found: {opt.subpath}")
    
    # Set output directory
    opt.output_folder = args.output_dir
    
    # Create output directory (overwrite handled by GUI)
    os.makedirs(opt.output_folder, exist_ok=True)
    
    # Set optimization goal
    opt.goal = args.goal
    
    # Set thresholds for focality optimization
    if args.goal == 'focality':
        if len(args.threshold_values) == 1:
            opt.threshold = args.threshold_values[0]  # Same threshold for both ROI and non-ROI
        else:
            opt.threshold = args.threshold_values  # Different thresholds for ROI and non-ROI
    
    # Set post-processing method
    opt.e_postproc = args.postproc
    
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
        setup_spherical_roi(opt, args)
    else:  # atlas
        setup_atlas_roi(opt, args)
    
    return opt

def setup_spherical_roi(opt, args):
    # Define target ROI
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"                            # define ROI on central GM surfaces
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
    
    # If goal is focality, add non-ROI based on method
    if args.goal == 'focality':
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"
        
        if args.non_roi_method == 'everything_else':
            # Use the same center but with a slightly larger radius to cover surrounding area
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = [x, y, z]
            non_roi.roi_sphere_radius = radius + 5  # Make the non-ROI sphere 5mm larger than the target ROI
            non_roi.roi_sphere_operator = ["difference"]  # Must be a list with "difference" as element
        else:  # specific non-ROI
            # Get non-ROI coordinates from environment variables
            try:
                nx = float(os.getenv('NON_ROI_X'))
                ny = float(os.getenv('NON_ROI_Y'))
                nz = float(os.getenv('NON_ROI_Z'))
                nradius = float(os.getenv('NON_ROI_RADIUS'))
            except (TypeError, ValueError) as e:
                raise ValueError("Missing or invalid non-ROI coordinates or radius in environment variables") from e
            
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = [nx, ny, nz]
            non_roi.roi_sphere_radius = nradius

def setup_atlas_roi(opt, args):
    # Define target ROI
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    
    # Get atlas information from environment variables
    try:
        label_value = int(os.getenv('ROI_LABEL'))
        atlas_path = os.getenv('ATLAS_PATH')
        hemisphere = os.getenv('SELECTED_HEMISPHERE')
        
        if not atlas_path:
            raise ValueError("ATLAS_PATH environment variable not set")
        if not os.path.exists(atlas_path):
            raise ValueError(f"Atlas file not found: {atlas_path}")
        if hemisphere not in ['lh', 'rh']:
            raise ValueError(f"Invalid hemisphere: {hemisphere}. Must be 'lh' or 'rh'")
            
    except (TypeError, ValueError) as e:
        raise ValueError("Missing or invalid ROI label or atlas path in environment variables") from e
    
    # Set the mask space based on the hemisphere
    roi.mask_space = f"subject_{hemisphere}"
    roi.mask_path = atlas_path
    roi.mask_value = label_value
    
    # If goal is focality, add non-ROI based on method
    if args.goal == 'focality':
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"
        
        if args.non_roi_method == 'everything_else':
            # Use the same atlas but invert the selection
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]  # Exclude the target ROI
        else:  # specific non-ROI
            try:
                non_roi_label = int(os.getenv('NON_ROI_LABEL'))
                non_roi_atlas_path = os.getenv('NON_ROI_ATLAS_PATH')
                if not non_roi_atlas_path:
                    raise ValueError("NON_ROI_ATLAS_PATH environment variable not set")
                if not os.path.exists(non_roi_atlas_path):
                    raise ValueError(f"Non-ROI atlas file not found: {non_roi_atlas_path}")
            except (TypeError, ValueError) as e:
                raise ValueError("Missing or invalid non-ROI label or atlas path in environment variables") from e
            
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = non_roi_atlas_path
            non_roi.mask_value = non_roi_label

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
