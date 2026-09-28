"""SimNIBS object construction for flex-search.

All SimNIBS imports are isolated here so that ``flex.py`` remains a
pure-Python orchestrator with zero SimNIBS coupling.

Public API
----------
build_optimization
    Construct a SimNIBS ``TesFlexOptimization`` from a
    :class:`~tit.opt.config.FlexConfig`.
configure_optimizer_options
    Apply DE hyperparameters to a SimNIBS optimization object.

See Also
--------
tit.opt.flex.flex.run_flex_search : Calls these functions internally.
tit.opt.config.FlexConfig : Configuration dataclass consumed here.
"""

import os
import warnings
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
    from .runtime import optimization_class
    from simnibs.optimization.tes_flex_optimization.electrode_layout import (
        ElectrodeArrayPair,
    )
    from tit.paths import get_path_manager

    opt = optimization_class()()
    if not hasattr(opt, "optim_parameters"):
        raise RuntimeError(
            "The installed SimNIBS Flex integration predates candidate recording. "
            "Update the TI-Toolbox runtime before starting this optimization."
        )

    pm = get_path_manager()
    opt.subpath = pm.m2m(config.subject_id)

    opt.output_folder = config.output_folder or pm.flex_search(config.subject_id)
    os.makedirs(opt.output_folder, exist_ok=True)

    # Configure goals and thresholds
    # Use .value to pass plain strings — SimNIBS does substring checks
    # (e.g. "dir_TI" in self.e_postproc) that fail on StrEnum instances.
    if config.goal is FlexConfig.OptGoal.FOCALITY_TF:
        # Threshold-free focality is not a SimNIBS built-in goal; inject it as a
        # callable objective. SimNIBS's callable-goal path skips the threshold
        # requirement, and requires a plain types.FunctionType.
        from .objectives import make_objective

        score = make_objective(config.goal, config.intensity_weight)

        def _threshold_free_goal(e_pp):
            # e_pp[channel][roi_index]; index 0 = ROI, 1 = non-ROI. TI envelopes
            # collapse to a single effective channel, but average defensively.
            return float(np.mean([score(ch[0], ch[1]) for ch in e_pp]))

        opt.goal = [_threshold_free_goal]
    else:
        opt.goal = config.goal.value
        if config.goal == "focality":
            thr_raw = (config.thresholds or "").strip()
            if thr_raw and thr_raw.lower() not in {"dynamic", "auto"}:
                vals = [float(v) for v in thr_raw.split(",")]
                opt.threshold = vals if len(vals) > 1 else vals[0]

    if config.postproc == FlexConfig.FieldPostproc.DIR_TI_TANGENTIAL:
        warnings.warn(
            "FieldPostproc.DIR_TI_TANGENTIAL ('dir_TI_tangential') computes "
            "tangential TI as sqrt(max(0, maxTI**2 - dirTI_normal**2)) -- a "
            "non-Pythagorean projection of already-modulated TI envelope "
            "amplitudes, not a vector decomposition of the underlying "
            "carrier fields. For a correct tangential/normal decomposition, "
            "use get_dirTI(E1, E2, n) applied to the raw carrier fields "
            "(as tit.sim's TI_normal does), not this postproc option. This "
            "option is kept for backward compatibility with existing "
            "configs and is not removed by this warning.",
            DeprecationWarning,
            stacklevel=2,
        )
    opt.e_postproc = config.postproc.value
    opt.anisotropy_type = config.anisotropy_type
    opt.aniso_maxratio = config.aniso_maxratio
    opt.aniso_maxcond = config.aniso_maxcond
    opt.open_in_gmsh = False  # Never auto-launch GUI

    # Minimum distance between electrodes of different arrays (mm)
    opt.min_electrode_distance = config.min_electrode_distance

    # Final electrode simulation control
    opt.run_final_electrode_simulation = config.run_final_electrode_simulation
    # Match Simulator's gel/rubber model; never silently use SimNIBS's 1 mm gel.
    opt.electrode_thickness = [float(config.electrode.gel_thickness), 2.0]

    # Detailed results control
    if config.detailed_results:
        opt.detailed_results = True

    # Skin visualization is always generated for flex-search reports.
    opt.visualize_valid_skin_region = True
    opt.skin_region_margin_mm = config.skin_region_margin_mm
    opt.avoid_landmark_regions = config.avoid_landmark_regions
    opt.skin_visualization_net_file = config.skin_visualization_net

    # Configure mapping
    if config.enable_mapping:
        if not config.eeg_net:
            raise ValueError("enable_mapping requires an EEG net name.")
        opt.map_to_net_electrodes = True
        eeg_dir = pm.eeg_positions(config.subject_id)
        opt.net_electrode_file = str(utils.eeg_net_csv_path(eeg_dir, config.eeg_net))
        if (
            hasattr(opt, "run_mapped_electrodes_simulation")
            and not config.disable_mapping_simulation
        ):
            opt.run_mapped_electrodes_simulation = True
    else:
        opt.electrode_mapping = None

    # Configure electrodes
    c_A = config.current_mA / 1000.0  # mA -> A
    electrode_shape = config.electrode.shape
    dimensions = config.electrode.dimensions

    # SimNIBS supports circles here, not unequal-axis ellipses.
    if electrode_shape == "ellipse":
        if dimensions[0] != dimensions[1]:
            raise ValueError(
                "Flex optimization supports circular electrodes only: ellipse "
                "dimensions must be equal. Unequal axes were previously "
                "approximated as a circle; select equal axes or a rectangle."
            )
        effective_radius = dimensions[0] / 2.0
    else:  # rectangle
        effective_radius = max(dimensions) / 2.0

    # Create electrode pairs for TI stimulation (2 pairs)
    electrode_pairs = []
    for _ in range(2):
        electrode_pair = ElectrodeArrayPair()

        if electrode_shape == "ellipse":
            electrode_pair.radius = [effective_radius]
        else:  # rectangle
            electrode_pair.radius = [0]
            electrode_pair.length_x = [dimensions[0]]
            electrode_pair.length_y = [dimensions[1]]

        electrode_pair.current = [c_A, -c_A]
        electrode_pairs.append(electrode_pair)

    opt.electrode = electrode_pairs

    # Configure ROI
    utils.configure_roi(opt, config)

    # Optionally search the channel current split alongside the placement. The
    # goal above stays configured so SimNIBS's own preparation/validation still
    # runs; the wrapper then takes over scoring from opt.goal_fun.
    if config.optimize_current_ratio:
        from .objectives import install_ratio_search, make_objective, ratio_levels

        # Explicit None test: `or` would swallow a deliberate 0.0 and silently
        # substitute the default (FlexConfig rejects 0.0, so it never gets here).
        total_mA = (
            2.0 * config.current_mA
            if config.ratio_total_mA is None
            else config.ratio_total_mA
        )
        install_ratio_search(
            opt,
            make_objective(
                config.goal,
                intensity_weight=config.intensity_weight,
                thresholds=config.thresholds,
            ),
            base_mA=config.current_mA,
            ratios=ratio_levels(total_mA, config.ratio_levels),
        )

    from .candidates import install_candidate_recorder

    install_candidate_recorder(opt, config)
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
