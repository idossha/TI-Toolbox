#!/usr/bin/env simnibs_python
"""Configuration and optimization setup for flex-search.

This module handles:
- Argument parsing
- Optimization object configuration
- Electrode setup
- Output directory structure
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TYPE_CHECKING

from simnibs import opt_struct

if TYPE_CHECKING:
    pass

# Import local roi module (flex-specific)
from . import roi


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments.
    
    Returns:
        Parsed arguments namespace
    """
    p = argparse.ArgumentParser(
        prog="flex-search",
        description="Optimise TI stimulation and (optionally) map final "
                    "electrodes to the nearest EEG-net nodes.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Core parameters
    p.add_argument("--subject", required=True, help="Subject ID")
    p.add_argument("--goal", choices=["mean", "max", "focality"], required=True,
                   help="Optimization goal")
    p.add_argument("--postproc", choices=["max_TI", "dir_TI_normal", "dir_TI_tangential"],
                   required=True, help="Post-processing method")
    p.add_argument("--eeg-net", required=True,
                   help="CSV filename in eeg_positions (without .csv)")
    p.add_argument("--radius", type=float, required=True,
                   help="Electrode radius in mm")
    p.add_argument("--current", type=float, required=True,
                   help="Electrode current in mA")
    p.add_argument("--roi-method", choices=["spherical", "atlas", "subcortical"],
                   required=True, help="ROI definition method")

    # Focality-specific arguments
    p.add_argument("--thresholds",
                   help="Single value or two comma-separated values for focality")
    p.add_argument("--non-roi-method", choices=["everything_else", "specific"],
                   help="Non-ROI definition method (required for focality goal)")

    # Mapping (disabled by default)
    p.add_argument("--enable-mapping", action="store_true",
                   help="Map optimal electrodes to nearest EEG-net nodes")
    p.add_argument("--disable-mapping-simulation", action="store_true",
                   help="Skip extra simulation with mapped electrodes")

    # Output control
    p.add_argument("--run-final-electrode-simulation", action="store_true", default=True,
                   help="Run final simulation with optimal electrodes (default: True)")
    p.add_argument("--skip-final-electrode-simulation", action="store_true",
                   help="Skip final simulation with optimal electrodes")

    # Stability and performance arguments
    p.add_argument("--n-multistart", type=int, default=1,
                   help="Number of optimization runs (multi-start). Best result will be kept.")
    p.add_argument("--max-iterations", type=int,
                   help="Maximum optimization iterations for differential_evolution")
    p.add_argument("--population-size", type=int,
                   help="Population size for differential_evolution")
    p.add_argument("--cpus", type=int,
                   help="Number of CPU cores to utilize")

    return p.parse_args()


def build_optimization(args: argparse.Namespace) -> opt_struct.TesFlexOptimization:
    """Set up optimization object with all parameters.
    
    Args:
        args: Parsed command line arguments
        
    Returns:
        Configured SimNIBS optimization object
        
    Raises:
        SystemExit: If required environment variables or files are missing
    """
    opt = opt_struct.TesFlexOptimization()

    # Get project directory
    proj_dir = os.getenv("PROJECT_DIR")
    if not proj_dir:
        raise SystemExit("[flex-search] PROJECT_DIR env-var is missing")

    # Set paths
    opt.subpath = os.path.join(
        proj_dir, "derivatives", "SimNIBS",
        f"sub-{args.subject}", f"m2m_{args.subject}"
    )
    opt.output_folder = os.path.join(
        proj_dir, "derivatives", "SimNIBS",
        f"sub-{args.subject}", "flex_search", roi.roi_dirname(args)
    )
    os.makedirs(opt.output_folder, exist_ok=True)

    # Configure goals and thresholds
    opt.goal = args.goal
    if args.goal == "focality":
        if not args.thresholds:
            raise SystemExit("--thresholds required for focality goal")
        vals = [float(v) for v in args.thresholds.split(",")]
        opt.threshold = vals if len(vals) > 1 else vals[0]
        if not args.non_roi_method:
            raise SystemExit("--non-roi-method required for focality goal")

    opt.e_postproc = args.postproc
    opt.open_in_gmsh = False  # Never auto-launch GUI
    
    # Final electrode simulation control
    opt.run_final_electrode_simulation = (
        args.run_final_electrode_simulation and 
        not args.skip_final_electrode_simulation
    )

    # Configure mapping
    if args.enable_mapping:
        opt.map_to_net_electrodes = True
        opt.net_electrode_file = os.path.join(
            opt.subpath, "eeg_positions", f"{args.eeg_net}.csv"
        )
        if not os.path.isfile(opt.net_electrode_file):
            raise SystemExit(f"EEG net file not found: {opt.net_electrode_file}")
        if hasattr(opt, "run_mapped_electrodes_simulation") and not args.disable_mapping_simulation:
            opt.run_mapped_electrodes_simulation = True
    else:
        # Initialize electrode_mapping to None when mapping is disabled
        # This prevents AttributeError in SimNIBS logging code
        opt.electrode_mapping = None

    # Configure electrodes
    r_m = args.radius
    c_A = args.current / 1000.0  # mA → A
    for _ in range(2):  # Two pairs for TI
        el = opt.add_electrode_layout("ElectrodeArrayPair")
        el.radius = [r_m]
        el.current = [c_A, -c_A]

    # Configure ROI
    roi.configure_roi(opt, args)

    return opt


def configure_optimizer_options(
    opt: opt_struct.TesFlexOptimization,
    args: argparse.Namespace,
    logger
) -> None:
    """Configure optimizer options for the optimization object.
    
    Args:
        opt: SimNIBS optimization object
        args: Parsed command line arguments
        logger: Logger instance
    """
    # Apply max_iterations if provided
    if args.max_iterations is not None:
        if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
            opt._optimizer_options_std["maxiter"] = args.max_iterations
            logger.debug(f"Set max iterations to {args.max_iterations}")
        else:
            logger.warning("opt._optimizer_options_std not found or not a dict, cannot set maxiter.")
    
    # Apply population_size if provided
    if args.population_size is not None:
        if hasattr(opt, '_optimizer_options_std') and isinstance(opt._optimizer_options_std, dict):
            opt._optimizer_options_std["popsize"] = args.population_size
            logger.debug(f"Set population size to {args.population_size}")
        else:
            logger.warning("opt._optimizer_options_std not found or not a dict, cannot set popsize.")
