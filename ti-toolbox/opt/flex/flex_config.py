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
from simnibs.optimization.tes_flex_optimization.electrode_layout import ElectrodeArrayPair

if TYPE_CHECKING:
    pass

# Add project root to path for core imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core import constants as const

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
    p.add_argument("--eeg-net",
                   help="CSV filename in eeg_positions (without .csv). Required when --enable-mapping is used.")
    p.add_argument("--current", type=float, required=True,
                   help="Electrode current in mA")
    p.add_argument("--electrode-shape", choices=["rect", "ellipse"], required=True,
                   help="Electrode shape (rect or ellipse)")
    p.add_argument("--dimensions", type=str, required=True,
                   help="Electrode dimensions in mm (x,y format, e.g., '8,8')")
    p.add_argument("--thickness", type=float, required=True,
                   help="Electrode thickness in mm")
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

    # Differential evolution optimizer parameters
    p.add_argument("--tolerance", type=float,
                   help="Tolerance for differential_evolution convergence (tol parameter)")
    p.add_argument("--mutation", type=str,
                   help="Mutation parameter for differential_evolution (single value or 'min,max' range)")
    p.add_argument("--recombination", type=float,
                   help="Recombination parameter for differential_evolution")

    # Output control
    p.add_argument("--detailed-results", action="store_true",
                   help="Enable detailed results output (creates additional visualization and debug files)")
    p.add_argument("--visualize-valid-skin-region", action="store_true",
                   help="Create visualizations of valid skin region for electrode placement (requires --detailed-results)")
    p.add_argument("--skin-visualization-net",
                   help="EEG net CSV file to use for skin visualization (shows electrode positions on valid/invalid skin regions)")

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
        f"sub-{args.subject}", const.DIR_FLEX_SEARCH, roi.roi_dirname(args)
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

    # Detailed results control
    if hasattr(args, 'detailed_results') and args.detailed_results:
        opt.detailed_results = True

    # Skin visualization control
    if hasattr(args, 'visualize_valid_skin_region') and args.visualize_valid_skin_region:
        opt.visualize_valid_skin_region = True

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

    # Configure skin visualization net file (separate from mapping)
    if hasattr(args, 'skin_visualization_net') and args.skin_visualization_net:
        opt.net_electrode_file = args.skin_visualization_net
        if not os.path.isfile(opt.net_electrode_file):
            raise SystemExit(f"Skin visualization EEG net file not found: {opt.net_electrode_file}")

    # Configure electrodes
    c_A = args.current / 1000.0  # mA → A
    electrode_shape = args.electrode_shape
    dimensions = [float(x) for x in args.dimensions.split(',')]
    thickness = args.thickness

    # Calculate effective radius from dimensions for ElectrodeArrayPair layout
    # For circular electrodes, use average of dimensions; for rectangular, use max dimension
    if electrode_shape == "ellipse":
        effective_radius = (dimensions[0] + dimensions[1]) / 4.0  # Average dimension / 2
    else:  # rectangle
        effective_radius = max(dimensions) / 2.0  # Max dimension / 2

    # Create electrode pairs for TI stimulation (2 pairs)
    electrode_pairs = []
    for _ in range(2):  # Two pairs for TI
        electrode_pair = ElectrodeArrayPair()

        # Set electrode shape and dimensions for plotting
        if electrode_shape == "ellipse":
            electrode_pair.radius = [effective_radius]
            electrode_pair.dimensions = [dimensions[0], dimensions[1]]
        else:  # rectangle
            electrode_pair.radius = [0]  # No radius for rectangular
            electrode_pair.length_x = [dimensions[0]]
            electrode_pair.length_y = [dimensions[1]]

        electrode_pair.current = [c_A, -c_A]
        electrode_pairs.append(electrode_pair)

    # Add to optimization
    opt.electrode = electrode_pairs

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
    # Check if optimizer options exist
    if not hasattr(opt, '_optimizer_options_std') or not isinstance(opt._optimizer_options_std, dict):
        logger.warning("opt._optimizer_options_std not found or not a dict, cannot configure optimizer options.")
        return

    # Apply max_iterations if provided
    if args.max_iterations is not None:
        opt._optimizer_options_std["maxiter"] = args.max_iterations
        logger.debug(f"Set max iterations to {args.max_iterations}")

    # Apply population_size if provided
    if args.population_size is not None:
        opt._optimizer_options_std["popsize"] = args.population_size
        logger.debug(f"Set population size to {args.population_size}")

    # Apply tolerance if provided
    if hasattr(args, 'tolerance') and args.tolerance is not None:
        opt._optimizer_options_std["tol"] = args.tolerance
        logger.debug(f"Set tolerance to {args.tolerance}")

    # Apply mutation if provided
    if hasattr(args, 'mutation') and args.mutation is not None:
        # Parse mutation parameter - can be single value or min,max range
        mutation_str = args.mutation.strip()
        if ',' in mutation_str:
            # Parse as [min, max] range
            try:
                mutation_parts = [float(x.strip()) for x in mutation_str.split(',')]
                if len(mutation_parts) == 2:
                    opt._optimizer_options_std["mutation"] = mutation_parts
                    logger.debug(f"Set mutation to {mutation_parts}")
                else:
                    logger.warning(f"Invalid mutation format: {mutation_str}. Expected single value or 'min,max'")
            except ValueError as e:
                logger.warning(f"Failed to parse mutation parameter '{mutation_str}': {e}")
        else:
            # Parse as single value
            try:
                mutation_val = float(mutation_str)
                opt._optimizer_options_std["mutation"] = mutation_val
                logger.debug(f"Set mutation to {mutation_val}")
            except ValueError as e:
                logger.warning(f"Failed to parse mutation parameter '{mutation_str}': {e}")

    # Apply recombination if provided
    if hasattr(args, 'recombination') and args.recombination is not None:
        opt._optimizer_options_std["recombination"] = args.recombination
        logger.debug(f"Set recombination to {args.recombination}")
