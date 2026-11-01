"""Exhaustive search optimization for TI stimulation.

Public API: ``run_ex_search(config) -> ExResult``
"""

import logging
import os
import time


from tit.opt.masks import validate_mask_paths
from tit.opt.config import ExConfig, ExResult
from tit.paths import get_path_manager
from tit.logger import add_file_handler

from .engine import ExSearchEngine
from .logic import (
    count_combinations,
    explain_zero_combinations,
    generate_current_ratios,
)
from .results import process_and_save
from .roi import (
    atlas_roi_entries,
    confirm_atlas_targets,
    mni_roi_files_to_subject_space,
)
from .symmetry import build_symmetry_mirror_map, net_name_from_leadfield


def run_ex_search(config: ExConfig) -> ExResult:
    """Run an exhaustive two-pair TI search over a precomputed leadfield.

    Enumerates every electrode-pair combination allowed by
    ``config.electrodes`` and every current split allowed by
    ``total_current``/``current_step``/``channel_limit``, scores each
    against the ROI, and writes a ranked CSV plus a config JSON to the
    run directory under the subject's ``ex-search/`` folder.

    Parameters
    ----------
    config : ExConfig
        Fully specified search configuration (subject, leadfield file,
        ROI, electrode pool or buckets, current sweep).

    Returns
    -------
    ExResult
        ``success``, ``output_dir``, ``n_combinations`` evaluated, and the
        ``results_csv`` / ``config_json`` paths.

    Raises
    ------
    ValueError
        If no candidate montage can be enumerated (empty pool/buckets or
        an over-restrictive symmetry rule), an electrode is not in the
        leadfield (raised before it is loaded), a referenced ROI CSV or atlas
        file does not exist, or the ROI selects no leadfield mesh element
        (raised before the search; no results are written).
    FileNotFoundError
        If ``config.leadfield_hdf`` cannot be found under the subject's
        ``leadfields/`` directory.

    Examples
    --------
    >>> from tit.opt import ExConfig, run_ex_search
    >>> cfg = ExConfig(
    ...     subject_id="ernie",
    ...     leadfield_hdf="ernie_leadfield_EEG10-10_UI_Jurak_2007.hdf5",
    ...     roi_name="L-Insula",
    ...     electrodes=ExConfig.PoolElectrodes(electrodes=["Fp1", "Fp2", "C3", "C4"]),
    ...     total_current=2.0, current_step=0.5, channel_limit=1.2,
    ...     run_name="insula_pool",
    ... )
    >>> res = run_ex_search(cfg)  # doctest: +SKIP
    >>> res.success, res.n_combinations, res.results_csv  # doctest: +SKIP
    (True, 18, '.../ex-search/insula_pool/final_output.csv')

    See Also
    --------
    ExConfig : Configuration dataclass for this search.
    ExResult : Returned container.
    tit.opt.mex.mex.run_m_ex_search : Four-pair (mTI) variant.
    """
    from tit.telemetry import track_operation
    from tit import constants as const

    with track_operation(const.TELEMETRY_OP_EX_SEARCH):
        return _run_ex_search_inner(config)


def _run_ex_search_inner(config: ExConfig) -> ExResult:
    """Inner implementation of :func:`run_ex_search` (unwrapped)."""
    validate_mask_paths(config)
    pm = get_path_manager()

    logs_dir = pm.logs(config.subject_id)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, f'ex_search_{time.strftime("%Y%m%d_%H%M%S")}.log')
    logger_name = f"tit.opt.ex_search.{config.subject_id}"
    handlers = [
        (name, add_file_handler(log_file, logger_name=name))
        for name in (logger_name, "simnibs")
    ]
    try:
        return _ex_search(config, pm, logging.getLogger(logger_name))
    finally:
        # One process may run many searches (a notebook): close this run's log file.
        for name, handler in handlers:
            logging.getLogger(name).removeHandler(handler)
            handler.close()


def _ex_search(config, pm, logger):
    logger.info(f"{'=' * 60}\nTI Exhaustive Search\n{'=' * 60}")
    logger.info(f"Project: {pm.project_dir}")
    logger.info(f"Subject: {config.subject_id}")

    run_name = config.run_name or time.strftime("%Y%m%d_%H%M%S")
    output_dir = pm.ex_search_run(config.subject_id, run_name)

    if isinstance(config.electrodes, ExConfig.PoolElectrodes):
        pool = config.electrodes.electrodes
        e1_plus = e1_minus = e2_plus = e2_minus = pool
        all_combinations = True
        symmetry_mirror_map = None
    else:
        e1_plus = config.electrodes.e1_plus
        e1_minus = config.electrodes.e1_minus
        e2_plus = config.electrodes.e2_plus
        e2_minus = config.electrodes.e2_minus
        all_combinations = False
        symmetry_mirror_map = build_symmetry_mirror_map(config, pm, logger)

    ratios = generate_current_ratios(
        config.total_current,
        config.current_step,
        config.channel_limit,
    )
    logger.info(f"Generated {len(ratios)} current ratio combinations")

    # Enumeration is cheap and independent of the leadfield: fail before
    # loading it (and before creating the run directory) when there is
    # nothing to evaluate.
    enumeration = (
        e1_plus,
        e1_minus,
        e2_plus,
        e2_minus,
        ratios,
        all_combinations,
        symmetry_mirror_map,
        config.symmetry_pairing,
    )
    n_candidates = count_combinations(*enumeration)
    if n_candidates == 0:
        raise ValueError(
            "ex-search has no candidate montages to evaluate: "
            f"{explain_zero_combinations(*enumeration)}"
        )
    logger.info(f"Candidate montage x ratio combinations: {n_candidates}")

    leadfield_path = os.path.join(
        pm.leadfields(config.subject_id), config.leadfield_hdf
    )
    refuse_electrodes_off_leadfield(
        "ex-search", [*e1_plus, *e1_minus, *e2_plus, *e2_minus], leadfield_path
    )

    os.makedirs(output_dir, exist_ok=True)
    logger.info(f"Output: {output_dir}")

    roi_names = config.roi_names if config.roi_names is not None else [config.roi_name]
    roi_dir = pm.rois(config.subject_id)
    if roi_names and config.roi_coordinate_space == "mni":
        roi_files = mni_roi_files_to_subject_space(
            roi_names, roi_dir, pm.m2m(config.subject_id), output_dir, logger
        )
    else:
        roi_files = [os.path.join(roi_dir, name) for name in roi_names]
    if len(roi_files) > 1:
        logger.info(f"Combining {len(roi_files)} ROIs into one target: {roi_names}")

    # Every atlas target is resolved into the subject first, and leaves an ROI
    # plate and a JSON in the run folder (tit/roi_confirmation.py): a misplaced
    # ROI is invisible in every number this search produces.
    confirm_atlas_targets(config, pm.m2m(config.subject_id), output_dir)

    atlas_entries = atlas_roi_entries(
        config, pm.m2m(config.subject_id), os.path.join(output_dir, "masks")
    )
    if atlas_entries:
        logger.info(f"Adding {len(atlas_entries)} atlas ROI target(s)")
        roi_files = roi_files + atlas_entries

    engine = ExSearchEngine(leadfield_path, roi_files, config.roi_name, logger)
    engine.initialize(roi_radius=config.roi_radius)

    results = engine.run(
        e1_plus,
        e1_minus,
        e2_plus,
        e2_minus,
        ratios,
        all_combinations,
        output_dir,
        n_jobs=config.n_jobs,
        symmetry_mirror_map=symmetry_mirror_map,
        symmetry_pairing=config.symmetry_pairing,
    )

    output_info = process_and_save(
        results, config, output_dir, logger, leadfield_path=leadfield_path
    )
    logger.info(f"Config: {output_info['config_json_path']}")
    logger.info(f"CSV: {output_info['csv_path']}")
    _write_report(config.subject_id, output_dir, logger)

    return ExResult(
        success=True,
        output_dir=output_dir,
        n_combinations=len(results),
        results_csv=output_info.get("csv_path"),
        config_json=output_info.get("config_json_path"),
    )


def leadfield_electrode_names(leadfield_path: str) -> list[str]:
    """The electrode names a leadfield HDF5 holds, read from its attributes only.

    The ``electrode_names`` attribute :func:`simnibs.utils.TI_utils.load_leadfield` builds
    its electrode index from (the reference electrode included), read without loading the
    multi-GB field.
    """
    import h5py

    with h5py.File(leadfield_path, "r") as handle:
        attrs = handle["mesh_leadfield"]["leadfields"]["tdcs_leadfield"].attrs
        return [
            name.decode() if isinstance(name, bytes) else str(name)
            for name in attrs["electrode_names"]
        ]


def refuse_electrodes_off_leadfield(
    search: str, labels: list[str], leadfield_path: str
) -> None:
    """Raise before the leadfield is loaded when an electrode label is not in it.

    Without this the engine loads the whole leadfield and the first unknown label then
    dies as a bare ``KeyError`` inside SimNIBS's ``TI.get_field`` (on a worker process
    when ``n_jobs > 1``). A missing file is left to the engine, whose load names it; so is
    a file whose name list reads empty (no real leadfield has one and SimNIBS's load
    refuses it; it is what the host suite's h5py stand-in reads).

    Raises:
        ValueError: Naming the leadfield's net and every label it does not hold.
    """
    if not os.path.isfile(leadfield_path):
        return
    names = set(leadfield_electrode_names(leadfield_path))
    missing = [label for label in dict.fromkeys(labels) if label not in names]
    if names and missing:
        net = net_name_from_leadfield(leadfield_path)
        raise ValueError(
            f"{search} electrodes not in the leadfield of {net}: "
            f"{', '.join(missing)}. Pick electrodes from {net}, or the leadfield of "
            "the net these came from."
        )


def _write_report(subject_id: str, run_dir: str, logger) -> None:
    """Write the ex-search report from the run folder; a report never fails the search."""
    from tit.reporting.generators.ex_search import create_ex_search_report

    try:
        path = create_ex_search_report(
            get_path_manager().project_dir, subject_id, run_dir
        )
        logger.info(f"Ex-search report: {path}")
    except Exception as exc:  # the search results stand without their report
        logger.warning(f"Ex-search report could not be written: {exc}")
