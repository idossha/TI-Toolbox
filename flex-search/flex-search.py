#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Add the parent directory to the path to access utils
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from simnibs import opt_struct
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
    p.add_argument("--roi-method", choices=["spherical", "atlas"], required=True)

    # focality-specific arguments
    p.add_argument("--thresholds", help="single value or two comma-separated values")
    p.add_argument("--non-roi-method", choices=["everything_else", "specific"], help="When goal=focality")

    # mapping (disabled by default)
    p.add_argument("--enable-mapping", action="store_true", help="Map to nearest EEG-net nodes")
    p.add_argument("--disable-mapping-simulation", action="store_true", help="Skip extra simulation with mapped electrodes")
    p.add_argument("--run-optimized-simulation", action="store_true", help="Run simulation with optimized electrodes before mapping")

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
    if args.roi_method == "spherical":
        base = f"{os.getenv('ROI_X')}x{os.getenv('ROI_Y')}y{os.getenv('ROI_Z')}z_{os.getenv('ROI_RADIUS')}mm"
    else:
        atlas = os.path.splitext(os.path.basename(os.path.basename(os.getenv("ATLAS_PATH", "atlas"))))[0]
        base = f"{atlas}_{os.getenv('ROI_LABEL', '0')}"
    return f"{base}_{args.goal}"

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
    # else: leave mapping attributes untouched

    # simulation options ---------------------------------------------------
    if args.run_optimized_simulation:
        opt.run_optimized_simulation = True

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
    else:
        _roi_atlas(opt, args)

    return opt

# -----------------------------------------------------------------------------
# ROI helpers
# -----------------------------------------------------------------------------

def _roi_spherical(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    roi.roi_sphere_center_space = "subject"
    roi.roi_sphere_center = [float(os.getenv(k)) for k in ("ROI_X", "ROI_Y", "ROI_Z")]
    radius = float(os.getenv("ROI_RADIUS"))
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
            nx = float(os.getenv("NON_ROI_X"))
            ny = float(os.getenv("NON_ROI_Y"))
            nz = float(os.getenv("NON_ROI_Z"))
            nr = float(os.getenv("NON_ROI_RADIUS"))
            non_roi.roi_sphere_center_space = "subject"
            non_roi.roi_sphere_center = [nx, ny, nz]
            non_roi.roi_sphere_radius = nr
            non_roi.weight = -1

def _roi_atlas(opt: opt_struct.TesFlexOptimization, args: argparse.Namespace) -> None:
    roi = opt.add_roi()
    roi.method = "surface"
    roi.surface_type = "central"
    hemi = os.getenv("SELECTED_HEMISPHERE")
    roi.mask_space = [f"subject_{hemi}"]
    roi.mask_path = [os.getenv("ATLAS_PATH")]
    label_val = int(os.getenv("ROI_LABEL"))
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
            non_roi_label = int(os.getenv("NON_ROI_LABEL"))
            non_roi_atlas_path = os.getenv("NON_ROI_ATLAS_PATH")
            non_roi.mask_space = roi.mask_space
            non_roi.mask_path = [non_roi_atlas_path]
            non_roi.mask_value = [non_roi_label]
            non_roi.weight = -1

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
        logger.info(f"  Mapping: {args.enable_mapping}")
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
    except Exception as exc:  # noqa: BLE001
        logger.error(f"ERROR during optimization: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
