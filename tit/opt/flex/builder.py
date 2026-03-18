"""SimNIBS object construction and reporting for flex-search.

All SimNIBS imports are isolated here so that ``flex.py`` remains a
pure-Python orchestrator with zero SimNIBS coupling.

Public API:
    - ``build_optimization(config) -> TesFlexOptimization``
    - ``configure_optimizer_options(opt, config, logger)``
    - ``generate_report(config, n_multistart, funvalue_list, best_idx, base_folder, logger)``
"""

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING
import logging

import numpy as np

from tit.opt.config import FlexConfig

from . import utils

# ---------------------------------------------------------------------------
# SimNIBS optimization object construction
# ---------------------------------------------------------------------------


def build_optimization(config: FlexConfig):
    """Build a SimNIBS TesFlexOptimization object from a FlexConfig.

    Args:
        config: Fully-populated FlexConfig.

    Returns:
        A configured ``TesFlexOptimization`` object.
    """
    from simnibs import opt_struct
    from simnibs.optimization.tes_flex_optimization.electrode_layout import (
        ElectrodeArrayPair,
    )
    from tit.paths import get_path_manager

    opt = opt_struct.TesFlexOptimization()

    pm = get_path_manager()
    opt.subpath = pm.m2m(config.subject_id)

    opt.output_folder = config.output_folder or pm.flex_search(config.subject_id)
    os.makedirs(opt.output_folder, exist_ok=True)

    # Configure goals and thresholds
    opt.goal = config.goal
    if config.goal == "focality":
        thr_raw = (config.thresholds or "").strip()
        if thr_raw and thr_raw.lower() not in {"dynamic", "auto"}:
            vals = [float(v) for v in thr_raw.split(",")]
            opt.threshold = vals if len(vals) > 1 else vals[0]

    opt.e_postproc = config.postproc
    opt.anisotropy_type = config.anisotropy_type
    opt.aniso_maxratio = config.aniso_maxratio
    opt.aniso_maxcond = config.aniso_maxcond
    opt.open_in_gmsh = False  # Never auto-launch GUI

    # Final electrode simulation control
    opt.run_final_electrode_simulation = config.run_final_electrode_simulation

    # Detailed results control
    if config.detailed_results:
        opt.detailed_results = True

    # Skin visualization control
    if config.visualize_valid_skin_region:
        opt.visualize_valid_skin_region = True

    # Configure mapping
    if config.enable_mapping:
        opt.map_to_net_electrodes = True
        eeg_dir = pm.eeg_positions(config.subject_id)
        opt.net_electrode_file = os.path.join(eeg_dir, f"{config.eeg_net}.csv")
        if (
            hasattr(opt, "run_mapped_electrodes_simulation")
            and not config.disable_mapping_simulation
        ):
            opt.run_mapped_electrodes_simulation = True
    else:
        opt.electrode_mapping = None

    # Configure skin visualization net file (separate from mapping)
    if config.skin_visualization_net:
        opt.net_electrode_file = config.skin_visualization_net

    # Configure electrodes
    c_A = config.current_mA / 1000.0  # mA -> A
    electrode_shape = config.electrode.shape
    dimensions = config.electrode.dimensions

    # Calculate effective radius from dimensions for ElectrodeArrayPair layout
    if electrode_shape == "ellipse":
        effective_radius = (dimensions[0] + dimensions[1]) / 4.0
    else:  # rectangle
        effective_radius = max(dimensions) / 2.0

    # Create electrode pairs for TI stimulation (2 pairs)
    electrode_pairs = []
    for _ in range(2):
        electrode_pair = ElectrodeArrayPair()

        if electrode_shape == "ellipse":
            electrode_pair.radius = [effective_radius]
            electrode_pair.dimensions = [dimensions[0], dimensions[1]]
        else:  # rectangle
            electrode_pair.radius = [0]
            electrode_pair.length_x = [dimensions[0]]
            electrode_pair.length_y = [dimensions[1]]

        electrode_pair.current = [c_A, -c_A]
        electrode_pairs.append(electrode_pair)

    opt.electrode = electrode_pairs

    # Configure ROI
    utils.configure_roi(opt, config)

    return opt


# ---------------------------------------------------------------------------
# Optimizer option configuration
# ---------------------------------------------------------------------------


def configure_optimizer_options(
    opt, config: FlexConfig, logger: logging.Logger
) -> None:
    """Configure differential-evolution optimizer options on the SimNIBS object.

    Args:
        opt: SimNIBS optimization object.
        config: FlexConfig with solver parameters.
        logger: Logger instance.
    """

    if config.max_iterations is not None:
        opt._optimizer_options_std["maxiter"] = config.max_iterations
        logger.debug(f"Set max iterations to {config.max_iterations}")

    if config.population_size is not None:
        opt._optimizer_options_std["popsize"] = config.population_size
        logger.debug(f"Set population size to {config.population_size}")

    if config.tolerance is not None:
        opt._optimizer_options_std["tol"] = config.tolerance
        logger.debug(f"Set tolerance to {config.tolerance}")

    if config.mutation is not None:
        mutation_str = config.mutation.strip()
        if "," in mutation_str:
            parts = [float(x.strip()) for x in mutation_str.split(",")]
            opt._optimizer_options_std["mutation"] = parts
        else:
            opt._optimizer_options_std["mutation"] = float(mutation_str)

    if config.recombination is not None:
        opt._optimizer_options_std["recombination"] = config.recombination
        logger.debug(f"Set recombination to {config.recombination}")


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------


def generate_report(
    config: FlexConfig,
    n_multistart: int,
    optim_funvalue_list: np.ndarray,
    best_opt_idx: int,
    base_output_folder: str,
    logger: logging.Logger,
) -> None:
    """Generate an HTML report from config fields (no env vars).

    Args:
        config: FlexConfig with all parameters.
        n_multistart: Number of multi-start runs.
        optim_funvalue_list: Array of function values.
        best_opt_idx: Index of best run (-1 if all failed).
        base_output_folder: Path to the output directory.
        logger: Logger instance.
    """
    from tit.reporting import FlexSearchReportGenerator
    from tit.paths import get_path_manager

    pm = get_path_manager()
    report_gen = FlexSearchReportGenerator(
        project_dir=pm.project_dir,
        subject_id=config.subject_id,
    )

    postproc_map = {
        "max_TI": "TImax",
        "dir_TI_normal": "normal",
        "dir_TI_tangential": "tangential",
    }
    dims_str = ",".join(str(d) for d in config.electrode.dimensions)

    report_gen.set_configuration(
        electrode_net=config.eeg_net,
        optimization_goal=config.goal,
        post_processing=postproc_map.get(config.postproc, config.postproc),
        n_candidates=n_multistart,
        n_starts=n_multistart,
        selection_method="best" if n_multistart > 1 else "single",
        electrode_shape=config.electrode.shape,
        electrode_dimensions_mm=dims_str,
        electrode_thickness_mm=config.electrode.gel_thickness,
        electrode_current_mA=config.current_mA,
        mapping_enabled=config.enable_mapping,
        disable_mapping_simulation=config.disable_mapping_simulation,
        run_final_electrode_simulation=config.run_final_electrode_simulation,
        max_iterations=config.max_iterations,
        population_size=config.population_size,
        tolerance=config.tolerance,
        mutation=config.mutation,
        recombination=config.recombination,
        thresholds=config.thresholds,
        non_roi_method=config.non_roi_method,
        cpu_cores=config.cpus,
        detailed_results=config.detailed_results,
        visualize_valid_skin_region=config.visualize_valid_skin_region,
        skin_visualization_net=config.skin_visualization_net,
    )

    # Build ROI info from config
    roi = config.roi
    roi_data: dict = {}

    if isinstance(roi, FlexConfig.SphericalROI):
        roi_data = {
            "roi_name": "Target ROI",
            "roi_type": "spherical",
            "coordinates": [roi.x, roi.y, roi.z],
            "radius": roi.radius,
            "coordinate_space": "MNI" if roi.use_mni else "subject",
        }
        if (
            config.goal == "focality"
            and config.non_roi_method == "specific"
            and isinstance(config.non_roi, FlexConfig.SphericalROI)
        ):
            nr = config.non_roi
            roi_data.update(
                {
                    "non_roi_method": config.non_roi_method,
                    "non_roi_coordinates": [nr.x, nr.y, nr.z],
                    "non_roi_radius": nr.radius,
                    "non_roi_coordinate_space": ("MNI" if nr.use_mni else "subject"),
                }
            )
    elif isinstance(roi, FlexConfig.AtlasROI):
        atlas_name = atlas_name_from_path(roi.atlas_path, roi.hemisphere)
        roi_data = {
            "roi_name": "Target ROI",
            "roi_type": "atlas",
            "hemisphere": roi.hemisphere,
            "atlas": atlas_name or roi.atlas_path,
            "atlas_label": roi.label,
        }
        if (
            config.goal == "focality"
            and config.non_roi_method == "specific"
            and isinstance(config.non_roi, FlexConfig.AtlasROI)
        ):
            nr = config.non_roi
            roi_data.update(
                {
                    "non_roi_atlas": (
                        os.path.basename(nr.atlas_path) if nr.atlas_path else None
                    ),
                    "non_roi_label": nr.label,
                }
            )
    elif isinstance(roi, FlexConfig.SubcorticalROI):
        roi_data = {
            "roi_name": "Target ROI",
            "roi_type": "subcortical",
            "volume_atlas": (
                os.path.basename(roi.atlas_path) if roi.atlas_path else None
            ),
            "volume_label": roi.label,
        }
        if (
            config.goal == "focality"
            and config.non_roi_method == "specific"
            and isinstance(config.non_roi, FlexConfig.SubcorticalROI)
        ):
            nr = config.non_roi
            roi_data.update(
                {
                    "non_roi_atlas": (
                        os.path.basename(nr.atlas_path) if nr.atlas_path else None
                    ),
                    "non_roi_label": nr.label,
                }
            )

    if config.goal == "focality" and config.non_roi_method:
        roi_data.setdefault("non_roi_method", config.non_roi_method)

    report_gen.set_roi_info(**roi_data)

    # Add search results
    for i, score in enumerate(optim_funvalue_list):
        if score != float("inf"):
            report_gen.add_search_result(
                rank=i + 1,
                electrode_1a="",
                electrode_1b="",
                electrode_2a="",
                electrode_2b="",
                score=float(score),
            )

    # Set best solution if available
    electrode_positions_path = Path(base_output_folder) / "electrode_positions.json"
    electrode_positions = None
    channel_array_indices = None
    if electrode_positions_path.exists():
        with open(electrode_positions_path) as f:
            pos_data = json.load(f)
        electrode_positions = pos_data.get("optimized_positions")
        channel_array_indices = pos_data.get("channel_array_indices")

    if n_multistart > 1 and best_opt_idx != -1:
        report_gen.set_best_solution(
            electrode_pairs=[],
            score=float(optim_funvalue_list[best_opt_idx]),
            metrics={"run": best_opt_idx + 1},
            electrode_coordinates=electrode_positions,
            channel_array_indices=channel_array_indices,
        )
    elif n_multistart == 1 and optim_funvalue_list[0] != float("inf"):
        report_gen.set_best_solution(
            electrode_pairs=[],
            score=float(optim_funvalue_list[0]),
            metrics={},
            electrode_coordinates=electrode_positions,
            channel_array_indices=channel_array_indices,
        )

    report_path = report_gen.generate()
    logger.info(f"Report generated: {report_path}")


def atlas_name_from_path(path_value: str, hemisphere: str) -> str:
    """Extract a human-readable atlas name from an annotation file path.

    Args:
        path_value: Full path to the .annot file.
        hemisphere: Hemisphere string (e.g. "lh").

    Returns:
        Clean atlas name, or empty string if extraction fails.
    """
    atlas_filename = os.path.basename(path_value)
    atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(
        ".annot", ""
    )

    if "_" in atlas_with_subject:
        return atlas_with_subject.split("_", 1)[-1]
    return atlas_with_subject
