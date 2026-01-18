#!/usr/bin/env simnibs_python
"""
Subprocess runner for TI-Toolbox simulations.

This module is designed to be launched from the GUI via QProcess, so the GUI can
hard-terminate the entire simulation pipeline when the user clicks Stop.

Key properties:
- Runs the simulation pipeline in a separate OS process (simnibs_python).
- Puts itself in a dedicated process group (Unix) so the GUI can SIGKILL the group,
  ensuring parallel worker processes and child tools are also terminated.
- Streams logs to stdout (flushes) for real-time GUI display, and also logs to file.
- Writes a machine-readable results JSON file for the GUI to summarize outcomes.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _ensure_own_process_group() -> None:
    """
    Ensure the current process is the leader of its own process group.

    The GUI will SIGKILL the process group using the PID it gets from QProcess.
    For that to work reliably, we set pgid = pid here (Unix only).
    """
    try:
        if os.name != "nt":
            os.setpgid(0, 0)
    except Exception:
        # Process group setup may fail on some systems - continue anyway
        pass


def _build_logger(subject_id: str, project_dir: str, debug: bool):
    """Create a logger that logs to stdout (for GUI) and to a per-subject log file."""
    from tit.core import get_path_manager
    from tit import logger as logging_util

    pm = get_path_manager()
    log_dir = pm.path("ti_logs", subject_id=subject_id)
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"Simulator_{time.strftime('%Y%m%d_%H%M%S')}.log")

    logger = logging_util.get_logger(
        name=f"TI-Simulator-Subprocess-{subject_id}",
        log_file=log_file,
        overwrite=False,
        console=True,
    )

    # In debug mode, show DEBUG to stdout; otherwise INFO and above.
    try:
        import logging

        for handler in list(logger.handlers):
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.FileHandler
            ):
                handler.setLevel(logging.DEBUG if debug else logging.INFO)
    except Exception:
        # Logger configuration may fail - continue with default logging
        pass

    # Mirror external loggers (simnibs etc.) into the same handlers.
    try:
        logging_util.configure_external_loggers(
            ["simnibs", "mesh_io", "sim_struct", "TI"],
            parent_logger=logger,
        )
    except Exception:
        # External logger configuration may fail - continue without it
        pass

    return logger, log_file


def _load_payload(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def main(argv=None) -> int:
    _ensure_own_process_group()

    parser = argparse.ArgumentParser(
        description="TI-Toolbox simulation subprocess runner"
    )
    parser.add_argument("--config", required=True, help="Path to JSON config payload")
    parser.add_argument("--results", required=True, help="Path to write results JSON")
    args = parser.parse_args(argv)

    payload = _load_payload(args.config)

    cfg = payload.get("config") or {}
    montages_payload = payload.get("montages") or []
    debug = bool(payload.get("debug", False))

    subject_id = cfg.get("subject_id")
    project_dir = cfg.get("project_dir")
    if not subject_id or not project_dir:
        sys.stderr.write("Missing required config keys: subject_id, project_dir\n")
        return 2

    try:
        from tit.core import get_path_manager
        from tit.sim import run_simulation
        from tit.sim.config import (
            ConductivityType,
            ElectrodeConfig,
            IntensityConfig,
            MontageConfig,
            ParallelConfig,
            SimulationConfig,
        )

        # Ensure PathManager is configured for this subprocess.
        # Many parts of the pipeline rely on get_path_manager().project_dir.
        try:
            get_path_manager().project_dir = project_dir
        except Exception:
            # Path manager configuration may fail - continue with default paths
            pass

        logger, log_file = _build_logger(subject_id, project_dir, debug=debug)
        logger.info("=== Simulation Started (subprocess) ===")
        logger.info(f"Subject: {subject_id}")
        logger.info(f"Debug mode: {debug}")
        logger.info(f"Config payload: {Path(args.config).as_posix()}")
        logger.info(f"Log file: {log_file}")

        intensities = cfg.get("intensities") or {}
        electrode = cfg.get("electrode") or {}
        parallel = cfg.get("parallel") or {}

        sim_config = SimulationConfig(
            subject_id=subject_id,
            project_dir=project_dir,
            conductivity_type=ConductivityType(cfg.get("conductivity_type")),
            intensities=IntensityConfig(
                pair1=float(intensities.get("pair1", 1.0)),
                pair2=float(intensities.get("pair2", 1.0)),
                pair3=float(intensities.get("pair3", 1.0)),
                pair4=float(intensities.get("pair4", 1.0)),
            ),
            electrode=ElectrodeConfig(
                shape=str(electrode.get("shape", "ellipse")),
                dimensions=[float(x) for x in electrode.get("dimensions", [8.0, 8.0])],
                thickness=float(electrode.get("thickness", 4.0)),
                sponge_thickness=float(electrode.get("sponge_thickness", 2.0)),
            ),
            eeg_net=str(cfg.get("eeg_net") or "GSN-HydroCel-185.csv"),
            parallel=ParallelConfig(
                enabled=bool(parallel.get("enabled", False)),
                max_workers=int(parallel.get("max_workers", 0)),
            ),
        )

        montage_configs = []
        for m in montages_payload:
            montage_configs.append(
                MontageConfig(
                    name=str(m.get("name")),
                    electrode_pairs=[
                        tuple(p) for p in (m.get("electrode_pairs") or [])
                    ],
                    is_xyz=bool(m.get("is_xyz", False)),
                    eeg_net=m.get("eeg_net"),
                )
            )

        # Emit subject + simulation context in a stable, GUI-summary-friendly format.
        # The Simulator tab's "normal mode" filters by keywords like "Subject:" / "Simulation:".
        try:
            sim_names = [mc.name for mc in montage_configs if getattr(mc, "name", None)]
            if sim_names:
                logger.info(f"Simulation: {', '.join(sim_names)}")
        except Exception:
            # Simulation name logging may fail - continue with simulation
            pass

        # Make the parallel decision explicit in logs (helps users understand behavior).
        try:
            montage_count = len(montage_configs)
            workers = int(sim_config.parallel.effective_workers)
            logger.info(
                f"Parallel requested: {bool(sim_config.parallel.enabled)} (max_workers={sim_config.parallel.max_workers}, effective_workers={workers})"
            )
            logger.info(f"Montages to run: {montage_count}")
            if sim_config.parallel.enabled:
                if montage_count <= 1:
                    logger.warning(
                        "Parallel execution is enabled, but only 1 montage was provided; running sequentially."
                    )
                elif workers <= 1:
                    logger.warning(
                        "Parallel execution is enabled, but effective_workers<=1; running sequentially."
                    )
        except Exception:
            # Configuration logging may fail - continue with execution
            pass

        results = run_simulation(
            config=sim_config,
            montages=montage_configs,
            logger=logger,
        )

        # Write results for the GUI to read.
        out = {
            "status": "ok",
            "subject_id": subject_id,
            "log_file": log_file,
            "results": results,
        }
        with open(args.results, "w") as f:
            json.dump(out, f)

        logger.info("=== Simulation Finished (subprocess) ===")
        logger.info(f"Results JSON: {Path(args.results).as_posix()}")
        return 0

    except Exception as e:
        # Best effort: write results file describing failure so GUI can mark it.
        try:
            out = {
                "status": "failed",
                "subject_id": subject_id,
                "error": str(e),
            }
            with open(args.results, "w") as f:
                json.dump(out, f)
        except Exception:
            # Results file writing may fail - continue with error reporting
            pass

        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
