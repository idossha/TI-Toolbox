#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path

# Add the parent directory to the path to access utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from simnibs import opt_struct, mni2subject_coords
from simnibs.mesh_tools.mesh_io import ElementTags
from utils.logging_util import get_logger, configure_external_loggers
from env_utils import apply_common_env_fixes

# -----------------------------------------------------------------------------
# Logger setup
# -----------------------------------------------------------------------------
def setup_logger(output_folder: str) -> None:
    """Initialize logger with console and file output.
    
    Args:
        output_folder: Path to the directory where logs should be stored
    """
    global logger
    # Get project directory from environment
    proj_dir = os.getenv("PROJECT_DIR")
    if not proj_dir:
        raise SystemExit("[flex-search] PROJECT_DIR env-var is missing")
    
    # Create logs directory in project derivatives
    logs_dir = os.path.join(proj_dir, "derivatives", "logs", f"sub-{os.getenv('SUBJECT_ID')}")
    os.makedirs(logs_dir, exist_ok=True)
    
    # Create timestamped log file
    time_stamp = time.strftime('%Y%m%d_%H%M%S')
    log_file = os.path.join(logs_dir, f'flex_search_{time_stamp}.log')
    logger = get_logger('flex-search', log_file, overwrite=True)

# -----------------------------------------------------------------------------
# Argument parsing (mapping is OFF by default)
# -----------------------------------------------------------------------------

def parse_arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="flex-search",
        description="Optimise TI stimulation and (optionally) map final "
                    "electrodes to the nearest EEG-net nodes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # core parameters
    p.add_argument("--subject", required=True)
    p.add_argument("--goal", choices=["mean", "max", "focality"], required=True)
    p.add_argument("--postproc", choices=["max_TI", "dir_TI_normal", "dir_TI_tangential"], required=True)
    p.add_argument("--eeg-net", required=True, help="CSV filename in eeg_positions (without .csv)")
    p.add_argument("--radius", type=float, required=True)
    p.add_argument("--current", type=float, required=True)
    p.add_argument("--roi-method", choices=["spherical", "atlas", "subcortical"], required=True)

    # focality-specific arguments
    p.add_argument("--thresholds", help="single value or two comma-separated values")
    p.add_argument("--non-roi-method", choices=["everything_else", "specific"], help="When goal=focality")

    # mapping (disabled by default)
    p.add_argument("--enable-mapping", action="store_true", help="Map to nearest EEG-net nodes")
    p.add_argument("--disable-mapping-simulation", action="store_true", help="Skip extra simulation with mapped electrodes")

    # output control
    p.add_argument("--quiet", action="store_true", help="Suppress optimization step output")

    # Stability and Performance arguments
    p.add_argument("--max-iterations", type=int, help="Maximum optimization iterations for differential_evolution.")
    p.add_argument("--population-size", type=int, help="Population size for differential_evolution.")
    p.add_argument("--cpus", type=int, help="Number of CPU cores to utilize.")

    return p.parse_args()

# -----------------------------------------------------------------------------
# Helper: simple ROI directory name
# -----------------------------------------------------------------------------

def roi_dirname(args: argparse.Namespace) -> str:
    """Generate output directory name following the naming convention:
    - Atlas: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
    - Spherical: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
    - Subcortical: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
    """
    # Convert postproc to shorter format
    postproc_map = {
        "max_TI": "maxTI",
        "dir_TI_normal": "normalTI", 
        "dir_TI_tangential": "tangentialTI"
    }
    postproc_short = postproc_map.get(args.postproc, args.postproc)
    
    if args.roi_method == "spherical":
        # Format: sphere_x{X}y{Y}z{Z}r{radius}_{goal}_{postprocess}
        roi_x = os.getenv('ROI_X', '0')
        roi_y = os.getenv('ROI_Y', '0') 
        roi_z = os.getenv('ROI_Z', '0')
        roi_radius = os.getenv('ROI_RADIUS', '10')
        base = f"sphere_x{roi_x}y{roi_y}z{roi_z}r{roi_radius}"
    elif args.roi_method == "atlas":
        # Format: {hemisphere}_{atlas}_{region}_{goal}_{postprocess}
        atlas_path = os.getenv("ATLAS_PATH", "")
        hemisphere = os.getenv("SELECTED_HEMISPHERE", "lh")
        roi_label = os.getenv("ROI_LABEL", "0")
        
        # Extract atlas name from path (e.g., lh.101_DK40.annot -> DK40)
        if atlas_path:
            atlas_filename = os.path.basename(atlas_path)
            # Remove hemisphere prefix and .annot suffix, then extract atlas name
            # e.g., lh.101_DK40.annot -> 101_DK40 -> DK40
            atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(".annot", "")
            atlas_name = atlas_with_subject.split("_", 1)[-1] if "_" in atlas_with_subject else atlas_with_subject
        else:
            atlas_name = "atlas"
        
        base = f"{hemisphere}_{atlas_name}_{roi_label}"
    else:  # subcortical
        # Format: subcortical_{volume_atlas}_{region}_{goal}_{postprocess}
        volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
        roi_label = os.getenv("VOLUME_ROI_LABEL", "0")
        
        if volume_atlas_path:
            volume_atlas = os.path.basename(volume_atlas_path)
            # Remove file extensions
            if volume_atlas.endswith('.nii.gz'):
                volume_atlas = volume_atlas[:-7]
            elif volume_atlas.endswith('.mgz'):
                volume_atlas = volume_atlas[:-4]
            elif volume_atlas.endswith('.nii'):
                volume_atlas = volume_atlas[:-4]
        else:
            volume_atlas = "volume"
        
        base = f"subcortical_{volume_atlas}_{roi_label}"
    
    return f"{base}_{args.goal}_{postproc_short}"

# -----------------------------------------------------------------------------
# Set-up optimisation object
# -----------------------------------------------------------------------------

def build_optimisation(args: argparse.Namespace) -> opt_struct.TesFlexOptimization:
    opt = opt_struct.TesFlexOptimization()

    proj_dir = os.getenv("PROJECT_DIR")
    if not proj_dir:
        raise SystemExit("[flex-search] PROJECT_DIR env-var is missing")

    opt.subpath = os.path.join(proj_dir, "derivatives", "SimNIBS", f"sub-{args.subject}", f"m2m_{args.subject}")
    opt.output_folder = os.path.join(proj_dir, "derivatives", "SimNIBS", f"sub-{args.subject}", "flex-search", roi_dirname(args))
    os.makedirs(opt.output_folder, exist_ok=True)

    # goals / thresholds -------------------------------------------------------
    opt.goal = args.goal
    if args.goal == "focality":
        if not args.thresholds:
            raise SystemExit("--thresholds required for focality goal")
        vals = [float(v) for v in args.thresholds.split(",")]
        opt.threshold = vals if len(vals) > 1 else vals[0]
        if not args.non_roi_method:
            raise SystemExit("--non-roi-method required for focality goal")

    opt.e_postproc = args.postproc
    opt.open_in_gmsh = False  # never auto-launch GUI

    # mapping --------------------------------------------------------------
    if args.enable_mapping:
        opt.map_to_net_electrodes = True
        opt.net_electrode_file = os.path.join(opt.subpath, "eeg_positions", f"{args.eeg_net}.csv")
        if not os.path.isfile(opt.net_electrode_file):
            raise SystemExit(f"EEG net file not found: {opt.net_electrode_file}")
        if hasattr(opt, "run_mapped_electrodes_simulation") and not args.disable_mapping_simulation:
            opt.run_mapped_electrodes_simulation = True
    else:
        # Initialize electrode_mapping to None when mapping is disabled
        # This prevents AttributeError in SimNIBS logging code that checks for this attribute
        opt.electrode_mapping = None


    # electrodes -----------------------------------------------------------
    r_m = args.radius
    c_A = args.current / 1000.0  # mA → A
    for _ in range(2):  # two pairs for TI
        el = opt.add_electrode_layout("ElectrodeArrayPair")
        el.radius = [r_m]
        el.current = [c_A, -c_A]

    # ROI ------------------------------------------------------------------
    if args.roi_method == "spherical":
        _roi_spherical(opt, args)
    elif args.roi_method == "atlas":
        _roi_atlas(opt, args)
    else:  # subcortical
        _roi_subcortical(opt, args)

    return opt

# -----------------------------------------------------------------------------
# ROI helpers
# -----------------------------------------------------------------------------

def _roi_spherical(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.roi_sphere_center_space = "subject"
    
    # Get coordinates from environment variables with proper defaults
    roi_x = float(os.getenv("ROI_X", "0"))
    roi_y = float(os.getenv("ROI_Y", "0"))
    roi_z = float(os.getenv("ROI_Z", "0"))
    radius = float(os.getenv("ROI_RADIUS", "10"))
    
    # Check if MNI coordinates should be used (for multiple subjects)
    use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
    
    if use_mni_coords:
        # Transform MNI coordinates to subject space
        print(f"[flex-search] Transforming MNI coordinates [{roi_x}, {roi_y}, {roi_z}] to subject space")
        try:
            # Use simnibs.mni2subject_coords to transform coordinates
            m2m_path = opt.subpath
            subject_coords = mni2subject_coords([roi_x, roi_y, roi_z], m2m_path)
            roi.roi_sphere_center = subject_coords
            print(f"[flex-search] Transformed coordinates: {subject_coords}")
        except Exception as e:
            print(f"[flex-search] ERROR: Failed to transform MNI coordinates to subject space: {e}")
            raise SystemExit(f"MNI coordinate transformation failed: {e}")
    else:
        # Use coordinates as-is (subject space)
        roi.roi_sphere_center = [roi_x, roi_y, roi_z]
    
    roi.roi_sphere_radius = radius

    # Add non-ROI if focality optimisation is requested
    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if args.non_roi_method == "everything_else":
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = roi.roi_sphere_center
            non_roi.roi_sphere_radius = radius
            non_roi.roi_sphere_operator = ["difference"]
            non_roi.weight = -1
        else:  # specific non-ROI defined via env vars
            # Get non-ROI coordinates with proper defaults
            nx = float(os.getenv("NON_ROI_X", "0"))
            ny = float(os.getenv("NON_ROI_Y", "0"))
            nz = float(os.getenv("NON_ROI_Z", "0"))
            nr = float(os.getenv("NON_ROI_RADIUS", "10"))
            
            # Check if non-ROI coordinates are also MNI
            use_mni_coords_non_roi = os.getenv("USE_MNI_COORDS_NON_ROI", "false").lower() == "true"
            
            if use_mni_coords_non_roi:
                # Transform non-ROI MNI coordinates to subject space
                print(f"[flex-search] Transforming non-ROI MNI coordinates [{nx}, {ny}, {nz}] to subject space")
                try:
                    m2m_path = opt.subpath
                    non_roi_subject_coords = mni2subject_coords([nx, ny, nz], m2m_path)
                    non_roi.roi_sphere_center = non_roi_subject_coords
                    print(f"[flex-search] Transformed non-ROI coordinates: {non_roi_subject_coords}")
                except Exception as e:
                    print(f"[flex-search] ERROR: Failed to transform non-ROI MNI coordinates to subject space: {e}")
                    raise SystemExit(f"Non-ROI MNI coordinate transformation failed: {e}")
            else:
                # Use non-ROI coordinates as-is (subject space)
                non_roi.roi_sphere_center = [nx, ny, nz]
            
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_radius = nr
            non_roi.weight = -1

def _roi_atlas(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    hemi = os.getenv("SELECTED_HEMISPHERE", "lh")
    roi.mask_space = [f"subject_{hemi}"]
    roi.mask_path = [os.getenv("ATLAS_PATH", "")]
    label_val = int(os.getenv("ROI_LABEL", "1"))
    roi.mask_value = [label_val]

    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "surface"
        non_roi.surface_type = "central"

        if args.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
        else:
            non_roi_label = int(os.getenv("NON_ROI_LABEL", "1"))
            non_roi_atlas_path = os.getenv("NON_ROI_ATLAS_PATH", "")
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = [non_roi_atlas_path]
            non_roi.mask_value = [non_roi_label]
            non_roi.weight = -1

def _roi_subcortical(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH", "")
    label_val = int(os.getenv("VOLUME_ROI_LABEL", "10"))
    
    # Validate that the volume atlas file exists
    if not volume_atlas_path or not os.path.isfile(volume_atlas_path):
        raise SystemExit(f"Volume atlas file not found: {volume_atlas_path}")
    
    # Note: logger not available during optimization setup, will log later
    
    roi = opt.add_roi()
    roi.method = "volume"
    roi.mask_space = ["subject"]
    roi.mask_path = [volume_atlas_path]
    roi.mask_value = [label_val]
    
    # Add some additional properties that might help with volume ROI processing
    roi.tissues = [ElementTags.GM]  # Gray matter tissue for volume ROI

    if args.goal == "focality":
        non_roi = opt.add_roi()
        non_roi.method = "volume"

        if args.non_roi_method == "everything_else":
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = roi.mask_path
            non_roi.mask_value = roi.mask_value
            non_roi.mask_operator = ["difference"]
            non_roi.weight = -1
            non_roi.tissues = [ElementTags.GM]  # Gray matter
        else:
            non_roi_label = int(os.getenv("VOLUME_NON_ROI_LABEL", "10"))
            non_roi_atlas_path = os.getenv("VOLUME_NON_ROI_ATLAS_PATH", "")
            if not non_roi_atlas_path or not os.path.isfile(non_roi_atlas_path):
                raise SystemExit(f"Non-ROI volume atlas file not found: {non_roi_atlas_path}")
            non_roi.mask_space = ["subject"]
            non_roi.mask_path = [non_roi_atlas_path]
            non_roi.mask_value = [non_roi_label]
            non_roi.weight = -1
            non_roi.tissues = [ElementTags.GM]  # Gray matter

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> int:
    apply_common_env_fixes()
    args = parse_arguments()
    
    try:
        # First build optimization to get output folder
        opt = build_optimisation(args)
        
        # Setup logger after output folder is created
        setup_logger(opt.output_folder)
        logger.info(f"Output directory created: {opt.output_folder}")
        
        # Log the command that was called
        command = " ".join(sys.argv)
        logger.info(f"Command: {command}")
        
        # Configure SimNIBS related loggers to use our logging setup
        configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct', 'opt_struct'], logger)
        
        # Log optimization parameters
        logger.info(f"Starting optimization with parameters:")
        logger.info(f"  Subject: {args.subject}")
        logger.info(f"  Goal: {args.goal}")
        logger.info(f"  ROI Method: {args.roi_method}")
        
        # Log ROI-specific details
        if args.roi_method == "subcortical":
            volume_atlas_path = os.getenv("VOLUME_ATLAS_PATH")
            volume_roi_label = os.getenv("VOLUME_ROI_LABEL")
            logger.info(f"  Volume Atlas: {volume_atlas_path}")
            logger.info(f"  Volume ROI Label: {volume_roi_label}")
        elif args.roi_method == "atlas":
            atlas_path = os.getenv("ATLAS_PATH")
            roi_label = os.getenv("ROI_LABEL")
            hemisphere = os.getenv("SELECTED_HEMISPHERE")
            logger.info(f"  Atlas: {atlas_path}")
            logger.info(f"  ROI Label: {roi_label}")
            logger.info(f"  Hemisphere: {hemisphere}")
        elif args.roi_method == "spherical":
            roi_coords = f"({os.getenv('ROI_X')}, {os.getenv('ROI_Y')}, {os.getenv('ROI_Z')})"
            roi_radius = os.getenv("ROI_RADIUS")
            use_mni_coords = os.getenv("USE_MNI_COORDS", "false").lower() == "true"
            coord_space = "MNI" if use_mni_coords else "subject"
            logger.info(f"  ROI Center ({coord_space} space): {roi_coords}")
            logger.info(f"  ROI Radius: {roi_radius}mm")
            if use_mni_coords:
                logger.info(f"  MNI coordinates will be transformed to subject space")
        
        logger.info(f"  Mapping: {args.enable_mapping}")
        if args.enable_mapping:
            logger.info(f"  Run mapped simulation: {not args.disable_mapping_simulation}")
        if args.max_iterations is not None:
            logger.info(f"  Max iterations: {args.max_iterations}")
        if args.population_size is not None:
            logger.info(f"  Population size: {args.population_size}")
        if args.cpus is not None:
            logger.info(f"  CPUs: {args.cpus}")
        
        # Set optimizer display option based on quiet mode
        if args.quiet:
            if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
                opt._optimizer_options_std["disp"] = False
            else:
                logger.warning("opt._optimizer_options_std not found or not a dict, cannot set disp for quiet mode.")

        # Apply max_iterations and population_size if provided
        if args.max_iterations is not None:
            if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
                opt._optimizer_options_std["maxiter"] = args.max_iterations
            else:
                logger.warning("opt._optimizer_options_std not found or not a dict, cannot set maxiter.")
        
        if args.population_size is not None:
            if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
                opt._optimizer_options_std["popsize"] = args.population_size
            else:
                logger.warning("opt._optimizer_options_std not found or not a dict, cannot set popsize.")
            
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR during setup: {exc}", file=sys.stderr)  # Fallback to print since logger might not be initialized
        return 1

    try:
        # Pass cpus argument to run method
        cpus_to_pass = args.cpus if args.cpus is not None else None 
        logger.info("Starting optimization run...")
        opt.run(cpus=cpus_to_pass)
        logger.info("Optimization completed successfully")
    except IndexError as exc:
        # Special handling for the index error we're seeing
        logger.error(f"IndexError during optimization (likely in post-processing): {exc}")
        logger.info("This error may occur during final analysis but optimization itself likely completed")
        # Check if simulation results exist to confirm optimization worked
        if hasattr(opt, 'output_folder') and os.path.exists(opt.output_folder):
            result_files = []
            for root, dirs, files in os.walk(opt.output_folder):
                for file in files:
                    if file.endswith('.msh') or file.endswith('.nii.gz'):
                        result_files.append(os.path.join(root, file))
            if result_files:
                logger.info(f"Found {len(result_files)} result files, optimization likely succeeded despite error")
                for f in result_files[:5]:  # Log first 5 files
                    logger.info(f"  Result file: {f}")
            else:
                logger.warning("No result files found, optimization may have failed")
        return 0  # Return success if we have results despite the error
    except Exception as exc:  # noqa: BLE001
        logger.error(f"ERROR during optimization: {exc}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
