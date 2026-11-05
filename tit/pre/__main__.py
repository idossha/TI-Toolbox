"""
CLI entry point for the preprocessing package.

Usage::

    simnibs_python -m tit.pre config.json

Reads a JSON configuration file and delegates to ``run_pipeline``.

See Also
--------
tit.pre.structural.run_pipeline : Pipeline function invoked by this entry point.
"""

import dataclasses
import json
import logging
import sys

from tit.jobs import locks
from tit.paths import get_path_manager
from tit.pre.config import PreprocessConfig, migrate_legacy_keys
from tit.pre.structural import run_pipeline
from tit.pre.utils import PreprocessError


def _build_config(data: dict) -> PreprocessConfig:
    """Build a :class:`PreprocessConfig` from config.json, after migrating legacy keys.

    There is no lenient fallback: a value ``deserialize_config`` refuses (a string where the
    dataclass declares a list or a number) would otherwise run as something the user never
    sent, e.g. ``subject_ids: "001"`` as subjects ``0``, ``0`` and ``1``.

    Raises
    ------
    ValueError
        If *data* is not a valid ``PreprocessConfig``.
    """
    from tit.config_io import deserialize_config

    return deserialize_config(PreprocessConfig, migrate_legacy_keys(data))


def main() -> None:
    """Parse a JSON config and run the preprocessing pipeline."""
    if len(sys.argv) < 2:
        sys.exit("Usage: simnibs_python -m tit.pre <config.json>")

    config_path = sys.argv[1]
    try:
        with open(config_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"Could not read config file {config_path}: {exc}")

    for key in ("project_dir", "subject_ids"):
        if key not in data:
            sys.exit(f"Config file {config_path} is missing required key: {key}")

    from tit.logger import setup_logging, add_stream_handler
    from tit.jobs import events

    setup_logging()
    add_stream_handler("tit.pre")
    logger = logging.getLogger("tit.pre")

    get_path_manager(data.pop("project_dir"))

    try:
        config = _build_config(data)
    except (TypeError, ValueError) as exc:
        sys.exit(f"Invalid preprocessing config: {exc}")

    lock_cm = locks.hold_for_job("pre", config.subject_ids, data)

    exit_code = 1
    try:
        with lock_cm:
            events.emit_stage("preprocessing")

            qsiprep_settings = (
                dataclasses.asdict(config.qsiprep_config)
                if config.qsiprep_config
                else None
            )
            qsirecon_settings = (
                dataclasses.asdict(config.qsi_recon_config)
                if config.qsi_recon_config
                else None
            )

            exit_code = run_pipeline(
                subject_ids=config.subject_ids,
                convert_dicom=config.convert_dicom,
                run_fastsurfer=config.run_fastsurfer,
                charm_threads=config.charm_threads,
                charm_options=config.charm_options,
                fastsurfer_threads=config.fastsurfer_threads,
                run_freesurfer=config.run_freesurfer,
                freesurfer_recon_all=config.freesurfer_recon_all,
                freesurfer_subregions=config.freesurfer_subregions,
                freesurfer_threads=config.freesurfer_threads,
                create_m2m=config.create_m2m,
                run_tissue_analysis=config.run_tissue_analysis,
                run_qsiprep=config.run_qsiprep,
                run_qsirecon=config.run_qsirecon,
                qsiprep_config=qsiprep_settings,
                qsi_recon_config=qsirecon_settings,
                extract_dti=config.extract_dti,
                skip_existing_outputs=config.skip_existing_outputs,
                replace_existing_outputs=config.replace_existing_outputs,
            )
            if exit_code == 0 and config.run_tractography:
                # Run from a script: the job route plans this as its own `tract` stage (G7).
                _run_tractography(config)
            events.emit_result({"exit_code": exit_code})
    except PreprocessError as exc:
        logger.error(str(exc))
        print(f"Preprocessing failed: {exc}", file=sys.stderr)
        exit_code = 2
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


def _run_tractography(config) -> None:
    from tit.jobs.plans import _tractography_config
    from tit.tract import run_network, run_track
    from tit.tract.config import NetworkConfig, TrackConfig

    for sid in config.subject_ids:
        built = _tractography_config(config, sid)
        built["track"].pop("_type", None)
        built["network"].pop("_type", None)
        run_track(sid, TrackConfig(**built["track"]))
        run_network(sid, NetworkConfig(**built["network"]))


if __name__ == "__main__":
    main()
