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
import os
import sys
from contextlib import nullcontext

from tit.paths import get_path_manager
from tit.pre.config import PreprocessConfig, migrate_legacy_keys
from tit.pre.structural import run_pipeline
from tit.pre.utils import PreprocessError


def _hold_locks(kind: str, subject_ids: list[str], config_dict: dict):
    """Best-effort lock scaffold: a no-op unless running as a ``tit.jobs`` job."""
    try:
        from tit.jobs import locks
        from tit.jobs.runner import ENV_JOB_ID
    except ImportError:
        return nullcontext()
    job_id = os.environ.get(ENV_JOB_ID)
    if not job_id:
        return nullcontext()
    requests = locks.keys_for(kind, subject_ids, config_dict)
    return locks.hold(get_path_manager().project_dir, job_id, requests)


def _build_config_legacy(data: dict) -> PreprocessConfig:
    """Old, pre-``PreprocessConfig`` dict layout -- read verbatim.

    Kept for one release so a caller sending the flat dict this entry point
    accepted before :class:`~tit.pre.config.PreprocessConfig` existed still
    works. In practice its shape already matches the dataclass field for
    field, so this only differs from ``deserialize_config`` in skipping
    ``__post_init__`` validation errors that aren't about ``subject_ids``.
    Pre-FastSurfer keys are already translated by
    :func:`~tit.pre.config.migrate_legacy_keys` before this runs.
    """
    from tit.pre.config import QSIPrepSettings, QSIReconSettings

    qsiprep_config = data.get("qsiprep_config")
    qsi_recon_config = data.get("qsi_recon_config")
    return PreprocessConfig(
        subject_ids=data["subject_ids"],
        convert_dicom=data.get("convert_dicom", False),
        run_fastsurfer=data.get("run_fastsurfer", False),
        charm_threads=data.get("charm_threads"),
        fastsurfer_threads=data.get("fastsurfer_threads"),
        run_freesurfer=data.get("run_freesurfer", False),
        freesurfer_recon_all=data.get("freesurfer_recon_all", True),
        freesurfer_subregions=data.get("freesurfer_subregions", []),
        freesurfer_threads=data.get("freesurfer_threads"),
        create_m2m=data.get("create_m2m", False),
        run_tissue_analysis=data.get("run_tissue_analysis", False),
        run_qsiprep=data.get("run_qsiprep", False),
        run_qsirecon=data.get("run_qsirecon", False),
        qsiprep_config=(QSIPrepSettings(**qsiprep_config) if qsiprep_config else None),
        qsi_recon_config=(
            QSIReconSettings(**qsi_recon_config) if qsi_recon_config else None
        ),
        extract_dti=data.get("extract_dti", False),
        skip_existing_outputs=data.get("skip_existing_outputs", False),
        replace_existing_outputs=data.get("replace_existing_outputs", False),
    )


def _build_config(data: dict) -> PreprocessConfig:
    """Build a :class:`PreprocessConfig`, preferring ``deserialize_config``.

    Falls back to :func:`_build_config_legacy` when *data* does not
    round-trip through the typed path (e.g. a caller still sending the
    pre-dataclass flat-dict shape with extra/renamed keys) -- see the
    module-level "old dict layout for one release" note.
    """
    from tit.config_io import deserialize_config

    data = migrate_legacy_keys(data)
    try:
        return deserialize_config(PreprocessConfig, data)
    except (TypeError, ValueError, KeyError) as exc:
        logging.getLogger("tit.pre").debug(
            f"deserialize_config(PreprocessConfig, ...) failed ({exc}); "
            "falling back to the legacy dict layout"
        )
        return _build_config_legacy(data)


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

    lock_cm = _hold_locks("pre", config.subject_ids, data)

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

            def _logger_callback(msg: str, level: str) -> None:
                logger.log(getattr(logging, level.upper(), logging.INFO), msg)
                if msg.startswith("Report generated: "):
                    events.emit_artifact(
                        msg[len("Report generated: ") :], kind="report"
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
                logger_callback=_logger_callback,
            )
            events.emit_result({"exit_code": exit_code})
    except PreprocessError as exc:
        logger.error(str(exc))
        print(f"Preprocessing failed: {exc}", file=sys.stderr)
        exit_code = 2
    finally:
        events.emit_exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
