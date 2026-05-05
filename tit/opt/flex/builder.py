"""SimNIBS object construction and reporting for flex-search.

All SimNIBS imports are isolated here so that ``flex.py`` remains a
pure-Python orchestrator with zero SimNIBS coupling.

Public API
----------
build_optimization
    Construct a SimNIBS ``TesFlexOptimization`` from a
    :class:`~tit.opt.config.FlexConfig`.
configure_optimizer_options
    Apply DE hyperparameters to a SimNIBS optimization object.
generate_report
    Create an HTML report summarising the flex-search run.

See Also
--------
tit.opt.flex.flex.run_flex_search : Calls these functions internally.
tit.opt.config.FlexConfig : Configuration dataclass consumed here.
"""

import base64
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
    """Build a SimNIBS ``TesFlexOptimization`` object from a FlexConfig.

    Translates every field from *config* into the corresponding SimNIBS
    attribute, including electrode geometry, ROI specification, and
    mapping settings.

    Parameters
    ----------
    config : FlexConfig
        Fully-populated flex-search configuration.

    Returns
    -------
    TesFlexOptimization
        A configured SimNIBS optimization object ready for
        ``opt.run()``.

    See Also
    --------
    configure_optimizer_options : Apply DE solver parameters after build.
    tit.opt.flex.utils.configure_roi : Delegates ROI setup.
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
    # Use .value to pass plain strings — SimNIBS does substring checks
    # (e.g. "dir_TI" in self.e_postproc) that fail on StrEnum instances.
    opt.goal = config.goal.value
    if config.goal == "focality":
        thr_raw = (config.thresholds or "").strip()
        if thr_raw and thr_raw.lower() not in {"dynamic", "auto"}:
            vals = [float(v) for v in thr_raw.split(",")]
            opt.threshold = vals if len(vals) > 1 else vals[0]

    opt.e_postproc = config.postproc.value
    opt.anisotropy_type = config.anisotropy_type
    opt.aniso_maxratio = config.aniso_maxratio
    opt.aniso_maxcond = config.aniso_maxcond
    opt.open_in_gmsh = False  # Never auto-launch GUI

    # Minimum distance between electrodes of different arrays (mm)
    opt.min_electrode_distance = config.min_electrode_distance

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
    """Apply differential-evolution solver parameters to a SimNIBS object.

    Reads optional DE hyperparameters from *config* and writes them
    into ``opt._optimizer_options_std``.  Parameters that are ``None``
    in the config are left at their SimNIBS defaults.

    Parameters
    ----------
    opt : TesFlexOptimization
        SimNIBS optimization object (mutated in-place).
    config : FlexConfig
        Configuration carrying optional DE parameters.
    logger : logging.Logger
        Logger for debug-level messages.

    See Also
    --------
    build_optimization : Creates the *opt* object that this function configures.
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
    """Generate an HTML report summarising the flex-search run.

    Delegates to :class:`~tit.reporting.FlexSearchReportGenerator` to
    produce a self-contained HTML file in the project's reports
    directory.

    Parameters
    ----------
    config : FlexConfig
        Configuration with all run parameters.
    n_multistart : int
        Number of multi-start DE runs executed.
    optim_funvalue_list : numpy.ndarray
        Array of objective function values, one per restart.
    best_opt_idx : int
        Zero-based index of the best run (``-1`` if all failed).
    base_output_folder : str
        Absolute path to the output directory (used to locate
        ``electrode_positions.json``).
    logger : logging.Logger
        Logger for info-level progress messages.
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
        intensity_ch1=config.current_mA,
        intensity_ch2=config.current_mA,
        electrode_shape=config.electrode.shape,
        electrode_dimensions_mm=dims_str,
        electrode_thickness_mm=config.electrode.gel_thickness,
        electrode_current_mA=config.current_mA,
        min_electrode_distance_mm=config.min_electrode_distance,
        anisotropy_type=config.anisotropy_type,
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
        atlas_name = _atlas_name_from_path(roi.atlas_path, roi.hemisphere)
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

    # Load electrode positions and optional mapping data
    output_path = Path(base_output_folder)
    electrode_positions = None
    channel_array_indices = None
    mapped_labels = None
    mapped_positions = None

    positions_file = output_path / "electrode_positions.json"
    if positions_file.exists():
        with open(positions_file) as f:
            pos_data = json.load(f)
        electrode_positions = pos_data.get("optimized_positions")
        channel_array_indices = pos_data.get("channel_array_indices")

    mapping_file = output_path / "electrode_mapping.json"
    if mapping_file.exists():
        with open(mapping_file) as f:
            map_data = json.load(f)
        mapped_labels = map_data.get("mapped_labels")
        mapped_positions = map_data.get("mapped_positions")

    best_score_idx = best_opt_idx if n_multistart > 1 else 0

    # Add search results. Per-run rows only include mapped EEG labels for the
    # selected solution because electrode_mapping.json records the final mapping.
    for i, score in enumerate(optim_funvalue_list):
        if score != float("inf"):
            result_metrics = {}
            if mapped_labels and best_score_idx >= 0 and i == best_score_idx:
                result_metrics["mapped_labels"] = mapped_labels
            report_gen.add_search_result(
                rank=i + 1,
                electrode_1a="",
                electrode_1b="",
                electrode_2a="",
                electrode_2b="",
                score=float(score),
                **result_metrics,
            )

    # Build electrode pairs from mapped labels when available
    electrode_pairs: list[dict[str, str]] = []
    if mapped_labels and len(mapped_labels) >= 4:
        electrode_pairs = [
            {"electrode1": mapped_labels[0], "electrode2": mapped_labels[1]},
            {"electrode1": mapped_labels[2], "electrode2": mapped_labels[3]},
        ]

    # Build metrics dict
    if best_score_idx == -1 or optim_funvalue_list[best_score_idx] == float("inf"):
        report_path = report_gen.generate()
        logger.info(f"Report generated: {report_path}")
        return

    best_metrics: dict = {}
    if n_multistart > 1:
        best_metrics["run"] = best_opt_idx + 1

    # Discover electrode placement images from output directory
    montage_b64 = _build_electrode_montage_base64(output_path)

    report_gen.set_best_solution(
        electrode_pairs=electrode_pairs,
        score=float(optim_funvalue_list[best_score_idx]),
        metrics=best_metrics,
        electrode_coordinates=electrode_positions,
        channel_array_indices=channel_array_indices,
        mapped_labels=mapped_labels,
        mapped_positions=mapped_positions,
        montage_image_base64=montage_b64,
    )

    report_path = report_gen.generate()
    logger.info(f"Report generated: {report_path}")


def _build_electrode_montage_base64(output_dir: Path) -> str | None:
    """Combine electrode placement PNGs into a single base64-encoded montage.

    SimNIBS writes one PNG per electrode (e.g.
    ``electrode_channel_0_array_0.png``).  This helper stitches them into
    a 2x2 grid and returns the result as a base64 string for embedding
    in HTML reports.

    Parameters
    ----------
    output_dir : Path
        Flex-search output directory containing ``electrode_*.png`` files.

    Returns
    -------
    str or None
        Base64-encoded PNG, or *None* if no images were found.
    """
    import io

    electrode_pngs = sorted(output_dir.glob("electrode_channel_*.png"))
    if not electrode_pngs:
        return None

    try:
        from PIL import Image
    except ImportError:
        # Fall back: embed the first image only
        with open(electrode_pngs[0], "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")

    images = [Image.open(p) for p in electrode_pngs]
    n = len(images)
    cols = min(n, 2)
    rows = (n + cols - 1) // cols
    w = max(img.width for img in images)
    h = max(img.height for img in images)

    montage = Image.new("RGBA", (cols * w, rows * h), (255, 255, 255, 255))
    for idx, img in enumerate(images):
        r, c = divmod(idx, cols)
        montage.paste(img, (c * w, r * h))

    buf = io.BytesIO()
    montage.save(buf, format="PNG")
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _atlas_name_from_path(path_value: str, hemisphere: str) -> str:
    """Extract a human-readable atlas name from an annotation file path."""
    atlas_filename = os.path.basename(path_value)
    atlas_with_subject = atlas_filename.replace(f"{hemisphere}.", "").replace(
        ".annot", ""
    )

    if "_" in atlas_with_subject:
        return atlas_with_subject.split("_", 1)[-1]
    return atlas_with_subject
