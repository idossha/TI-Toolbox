#!/usr/bin/env simnibs_python
"""
Unified TI/mTI simulation runner.

This module provides a single entry point for running both TI (2-pair) and mTI (4-pair)
simulations. The simulation type is automatically detected based on montage configuration.

This refactored module includes all features from the original pipeline:
- Montage visualization
- SimNIBS simulation
- Field extraction (GM/WM)
- NIfTI transformation
- T1 to MNI conversion
- File organization

Parallel execution support:
- Multiple montages can be simulated in parallel
- Worker count is configurable (default: half of CPU cores)
"""
from simnibs import run_simnibs

import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime
from typing import List, Optional, Callable, Any

# Use 'spawn' context for better compatibility with SimNIBS
mp_context = multiprocessing.get_context("spawn")

from tit.sim.config import (
    SimulationConfig,
    MontageConfig,
    SimulationMode,
    ElectrodeConfig,
    IntensityConfig,
    ConductivityType,
    ParallelConfig,
)
from tit.sim.montage_loader import load_montages
from tit.sim.session_builder import SessionBuilder
from tit.sim.post_processor import PostProcessor
from tit.core import get_path_manager
from tit import logger as logging_util


def setup_montage_directories(
    montage_dir: str, simulation_mode: SimulationMode
) -> dict:
    """
    Create the complete directory structure for a montage simulation.

    Args:
        montage_dir: Base montage directory
        simulation_mode: TI or MTI simulation mode

    Returns:
        Dictionary of created directory paths
    """
    dirs = {
        "montage_dir": montage_dir,
        "hf_dir": os.path.join(montage_dir, "high_Frequency"),
        "hf_mesh": os.path.join(montage_dir, "high_Frequency", "mesh"),
        "hf_niftis": os.path.join(montage_dir, "high_Frequency", "niftis"),
        "hf_analysis": os.path.join(montage_dir, "high_Frequency", "analysis"),
        "ti_mesh": os.path.join(montage_dir, "TI", "mesh"),
        "ti_niftis": os.path.join(montage_dir, "TI", "niftis"),
        "ti_surface_overlays": os.path.join(montage_dir, "TI", "surface_overlays"),
        "ti_montage_imgs": os.path.join(montage_dir, "TI", "montage_imgs"),
        "documentation": os.path.join(montage_dir, "documentation"),
    }

    # Add mTI directories for multipolar mode
    if simulation_mode == SimulationMode.MTI:
        dirs["mti_mesh"] = os.path.join(montage_dir, "mTI", "mesh")
        dirs["mti_niftis"] = os.path.join(montage_dir, "mTI", "niftis")
        dirs["mti_montage_imgs"] = os.path.join(montage_dir, "mTI", "montage_imgs")

    # Create all directories
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)

    return dirs


def create_simulation_config_file(
    config: SimulationConfig, montage: MontageConfig, documentation_dir: str, logger
) -> str:
    """
    Create a config.json file with all simulation parameters.

    This file is used by visualization tools to auto-populate parameters
    without requiring manual input.

    Args:
        config: Simulation configuration
        montage: Montage configuration
        documentation_dir: Documentation directory path
        logger: Logger instance

    Returns:
        Path to created config.json file
    """
    config_file = os.path.join(documentation_dir, "config.json")

    # Build configuration dictionary
    sim_config = {
        "subject_id": config.subject_id,
        "simulation_name": montage.name,
        "simulation_mode": montage.simulation_mode.value,
        "eeg_net": montage.eeg_net or config.eeg_net,
        "conductivity_type": config.conductivity_type.value,
        "electrode_pairs": montage.electrode_pairs,
        "is_xyz_montage": montage.is_xyz,
        "intensities": {
            "pair1": config.intensities.pair1,
            "pair2": config.intensities.pair2,
            "pair3": config.intensities.pair3,
            "pair4": config.intensities.pair4,
        },
        "electrode_geometry": {
            "shape": config.electrode.shape,
            "dimensions": config.electrode.dimensions,
            "gel_thickness": config.electrode.thickness,
            "sponge_thickness": config.electrode.sponge_thickness,
        },
        "mapping_options": {
            "map_to_surf": config.map_to_surf,
            "map_to_vol": config.map_to_vol,
            "map_to_mni": config.map_to_mni,
            "map_to_fsavg": config.map_to_fsavg,
        },
        "created_at": datetime.now().isoformat(),
        "ti_toolbox_version": "2.0.0",  # TODO: Get from version.py
    }

    # Write config file
    try:
        with open(config_file, "w") as f:
            json.dump(sim_config, f, indent=2)
        logger.info(f"Created simulation config: {config_file}")
    except Exception as e:
        logger.warning(f"Failed to create config file: {e}")

    return config_file


def run_montage_visualization(
    montage_name: str,
    simulation_mode: SimulationMode,
    eeg_net: str,
    output_dir: str,
    project_dir: str,
    logger,
    electrode_pairs: Optional[List] = None,
) -> bool:
    """
    Run montage visualization using visualize-montage.sh.

    Args:
        montage_name: Name of the montage
        simulation_mode: TI or MTI mode
        eeg_net: EEG net name
        output_dir: Output directory for montage images
        project_dir: Project directory path
        logger: Logger instance
        electrode_pairs: Optional list of electrode pairs for direct visualization

    Returns:
        True if successful, False otherwise
    """
    # Skip visualization for freehand/flex modes with XYZ coordinates (no electrode_pairs provided)
    if eeg_net in ["freehand", "flex_mode"] and not electrode_pairs:
        logger.info(f"Skipping montage visualization for {eeg_net} mode")
        return True

    # Determine sim_mode string for visualize-montage.sh
    sim_mode_str = "U" if simulation_mode == SimulationMode.TI else "M"

    # Path to visualize-montage.sh
    script_dir = os.path.dirname(__file__)
    visualize_script = os.path.join(script_dir, "visualize-montage.sh")

    if not os.path.exists(visualize_script):
        logger.warning(f"Visualize montage script not found: {visualize_script}")
        return True  # Non-fatal, continue without visualization

    logger.info(f"Visualizing montage: {montage_name}")

    try:
        # Set PROJECT_DIR_NAME environment variable for the script
        env = os.environ.copy()
        project_dir_name = os.path.basename(project_dir)
        env["PROJECT_DIR_NAME"] = project_dir_name

        # Build command
        cmd = ["bash", visualize_script, sim_mode_str, eeg_net, output_dir]

        if electrode_pairs:
            # For flex montages with known electrode pairs, pass --pairs
            pairs_str = ",".join([f"{pair[0]}-{pair[1]}" for pair in electrode_pairs])
            pairs_arg = f"{montage_name}:{pairs_str}"
            cmd.extend(["--pairs", pairs_arg])
        else:
            # For standard montages, pass montage name
            cmd.insert(2, montage_name)  # Insert after script path and sim_mode

        result = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=120
        )

        if result.returncode != 0:
            logger.warning(f"Montage visualization returned non-zero: {result.stderr}")

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        logger.warning(f"Montage visualization timed out for {montage_name}")
        return False
    except Exception as e:
        logger.warning(f"Montage visualization failed: {e}")
        return False


def _run_montage_worker(args: dict) -> dict:
    """
    Worker function for parallel montage execution.

    This function runs in a separate process and handles its own logging.
    IMPORTANT: This function is called in a spawned process, so all imports
    must happen inside the function.

    Logging behavior:
    - All output goes to a per-worker log file
    - No output to terminal/stdout (prevents console flooding)
    - Errors are captured and returned in the result dict

    Args:
        args: Dictionary containing:
            - config_dict: Serialized SimulationConfig
            - montage_dict: Serialized MontageConfig
            - simulation_dir: Base simulation directory
            - worker_id: Worker identifier for logging

    Returns:
        Dictionary with simulation result
    """
    import os
    import sys
    import time
    import traceback
    import logging

    # Extract args first (before imports that might fail)
    config_dict = args["config_dict"]
    montage_dict = args["montage_dict"]
    simulation_dir = args["simulation_dir"]
    worker_id = args.get("worker_id", 0)
    montage_name = montage_dict.get("name", "unknown")

    # Suppress stdout/stderr to prevent terminal flooding
    # Redirect to devnull for cleaner execution
    class NullWriter:
        def write(self, *args, **kwargs):
            pass

        def flush(self, *args, **kwargs):
            pass

    # Save original streams
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    try:
        # Import dependencies inside the worker (required for spawn context)
        from tit.sim.config import (
            SimulationConfig,
            MontageConfig,
            ConductivityType,
            ElectrodeConfig,
            IntensityConfig,
            ParallelConfig,
        )
        from tit.sim.session_builder import SessionBuilder
        from tit.sim.post_processor import PostProcessor
        from tit.core import get_path_manager
        from tit import logger as logging_util

        # Reconstruct MontageConfig
        montage = MontageConfig(
            name=montage_dict["name"],
            electrode_pairs=[tuple(p) for p in montage_dict["electrode_pairs"]],
            is_xyz=montage_dict.get("is_xyz", False),
            eeg_net=montage_dict.get("eeg_net"),
        )

        # Reconstruct config
        config = SimulationConfig(
            subject_id=config_dict["subject_id"],
            project_dir=config_dict["project_dir"],
            conductivity_type=ConductivityType(config_dict["conductivity_type"]),
            intensities=IntensityConfig(**config_dict["intensities"]),
            electrode=ElectrodeConfig(**config_dict["electrode"]),
            eeg_net=config_dict["eeg_net"],
            parallel=ParallelConfig(**config_dict.get("parallel", {})),
        )

        # Set up per-worker file-only logger (no console output)
        pm = get_path_manager()
        log_dir = pm.path("ti_logs", subject_id=config.subject_id)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir,
            f'Simulator_worker{worker_id}_{montage.name}_{time.strftime("%Y%m%d_%H%M%S")}.log',
        )

        # Use file-only logger to prevent terminal output
        logger = logging_util.get_file_only_logger(
            name=f"TI-Simulator-W{worker_id}", log_file=log_file, level=logging.DEBUG
        )

        # Configure external loggers to also use file-only logging
        for ext_name in ["simnibs", "mesh_io", "sim_struct", "TI"]:
            ext_logger = logging.getLogger(ext_name)
            ext_logger.setLevel(logging.DEBUG)
            ext_logger.propagate = False
            # Clear existing handlers
            for handler in list(ext_logger.handlers):
                ext_logger.removeHandler(handler)
            # Add file handler
            file_handler = logging.FileHandler(log_file, mode="a")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
                )
            )
            ext_logger.addHandler(file_handler)

        # Now suppress stdout/stderr after logging is set up
        sys.stdout = NullWriter()
        sys.stderr = NullWriter()

        logger.info(
            f"Worker {worker_id}: Starting {montage.simulation_mode.value} simulation: {montage.name}"
        )
        logger.info(f"Log file: {log_file}")

        # Initialize components
        session_builder = SessionBuilder(config)
        m2m_dir = pm.path("m2m", subject_id=config.subject_id)

        post_processor = PostProcessor(
            subject_id=config.subject_id,
            conductivity_type=config.conductivity_type.value,
            m2m_dir=m2m_dir,
            logger=logger,
        )

        # Import _run_single_montage here to ensure all its dependencies are loaded
        from tit.sim.simulator import _run_single_montage

        result = _run_single_montage(
            config=config,
            montage=montage,
            simulation_dir=simulation_dir,
            session_builder=session_builder,
            post_processor=post_processor,
            logger=logger,
        )

        logger.info(f"Worker {worker_id}: Completed {montage.name}")
        result["log_file"] = log_file
        return result

    except Exception as e:
        error_tb = traceback.format_exc()

        # Try to log the error if logger is available
        try:
            if "logger" in dir() and logger:
                logger.error(f"Worker {worker_id}: Failed - {str(e)}")
                logger.error(error_tb)
        except:
            pass

        return {
            "montage_name": montage_name,
            "montage_type": "unknown",
            "status": "failed",
            "error": str(e),
        }
    finally:
        # Restore original streams
        sys.stdout = original_stdout
        sys.stderr = original_stderr


def run_simulation(
    config: SimulationConfig,
    montages: List[MontageConfig],
    logger=None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[dict]:
    """
    Run TI/mTI simulations for given montages.

    Supports both sequential and parallel execution based on config.parallel settings.

    Args:
        config: Simulation configuration
        montages: List of montage configurations
        logger: Optional logger instance
        progress_callback: Optional callback for progress updates (current, total, montage_name)

    Returns:
        List of dictionaries with simulation results
    """
    # Initialize logger if not provided
    if logger is None:
        import logging

        pm = get_path_manager()
        log_dir = pm.path("ti_logs", subject_id=config.subject_id)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(
            log_dir, f'Simulator_{time.strftime("%Y%m%d_%H%M%S")}.log'
        )

        # Use file-only logger by default (no console output)
        # Console output should be controlled by the caller (GUI or CLI)
        logger = logging_util.get_file_only_logger(
            "TI-Simulator", log_file, level=logging.DEBUG
        )

        # Configure external loggers to also use file-only logging
        for ext_name in ["simnibs", "mesh_io", "sim_struct", "TI"]:
            ext_logger = logging.getLogger(ext_name)
            ext_logger.setLevel(logging.DEBUG)
            ext_logger.propagate = False
            for handler in list(ext_logger.handlers):
                ext_logger.removeHandler(handler)
            file_handler = logging.FileHandler(log_file, mode="a")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter(
                    "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
                )
            )
            ext_logger.addHandler(file_handler)

    # Get simulation directory
    pm = get_path_manager()
    simulation_dir = pm.path("simulations", subject_id=config.subject_id)

    # Check if parallel execution is enabled and we have multiple montages
    use_parallel = (
        config.parallel.enabled
        and len(montages) > 1
        and config.parallel.effective_workers > 1
    )

    if use_parallel:
        return _run_parallel(
            config, montages, simulation_dir, logger, progress_callback
        )
    else:
        return _run_sequential(
            config, montages, simulation_dir, logger, progress_callback
        )


def _run_sequential(
    config: SimulationConfig,
    montages: List[MontageConfig],
    simulation_dir: str,
    logger,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[dict]:
    """
    Run montages sequentially in a single process.

    Processes each montage one at a time in the current process. This is the
    default execution mode and is more memory-efficient than parallel execution.

    Parameters
    ----------
    config : SimulationConfig
        Simulation configuration
    montages : list of MontageConfig
        List of montages to simulate
    simulation_dir : str
        Base simulation directory path
    logger : logging.Logger
        Logger instance for progress tracking
    progress_callback : callable, optional
        Callback function(current, total, montage_name) for progress updates

    Returns
    -------
    list of dict
        List of simulation results, one per montage. Each dict contains:
        - montage_name : str
        - montage_type : str ('TI' or 'mTI')
        - status : str ('completed' or 'failed')
        - output_mesh : str (path to output mesh file, if successful)
        - error : str (error message, if failed)
    """
    # Initialize components
    session_builder = SessionBuilder(config)
    pm = get_path_manager()
    m2m_dir = pm.path("m2m", subject_id=config.subject_id)

    post_processor = PostProcessor(
        subject_id=config.subject_id,
        conductivity_type=config.conductivity_type.value,
        m2m_dir=m2m_dir,
        logger=logger,
    )

    results = []
    total = len(montages)

    # Run simulations for each montage
    for idx, montage in enumerate(montages):
        try:
            logger.info(
                f"Starting {montage.simulation_mode.value} simulation: {montage.name} ({idx+1}/{total})"
            )

            if progress_callback:
                progress_callback(idx, total, montage.name)

            result = _run_single_montage(
                config=config,
                montage=montage,
                simulation_dir=simulation_dir,
                session_builder=session_builder,
                post_processor=post_processor,
                logger=logger,
            )

            results.append(result)

        except Exception as e:
            logger.error(f"Failed to run montage {montage.name}: {e}")
            import traceback

            traceback.print_exc()

            results.append(
                {
                    "montage_name": montage.name,
                    "montage_type": montage.simulation_mode.value,
                    "status": "failed",
                    "error": str(e),
                }
            )

    if progress_callback:
        progress_callback(total, total, "Complete")

    return results


def _run_parallel(
    config: SimulationConfig,
    montages: List[MontageConfig],
    simulation_dir: str,
    logger,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[dict]:
    """
    Run montages in parallel using multiple worker processes.

    Uses ProcessPoolExecutor with 'spawn' context for SimNIBS compatibility.
    Each montage runs in a separate worker process with its own file-based logging.
    Memory intensive - each worker requires ~4-8 GB RAM.

    Parameters
    ----------
    config : SimulationConfig
        Simulation configuration
    montages : list of MontageConfig
        List of montages to simulate
    simulation_dir : str
        Base simulation directory path
    logger : logging.Logger
        Main logger instance (each worker gets its own file logger)
    progress_callback : callable, optional
        Callback function(current, total, montage_name) for progress updates

    Returns
    -------
    list of dict
        List of simulation results in completion order. Each dict contains:
        - montage_name : str
        - montage_type : str ('TI' or 'mTI')
        - status : str ('completed' or 'failed')
        - output_mesh : str (path to output mesh file, if successful)
        - log_file : str (path to worker log file)
        - error : str (error message, if failed)

    Notes
    -----
    - Uses 'spawn' multiprocessing context to avoid fork-related issues with SimNIBS
    - Each worker suppresses stdout/stderr and logs only to files
    - Worker count determined by config.parallel.effective_workers
    - 2-hour timeout per simulation
    """
    max_workers = min(config.parallel.effective_workers, len(montages))

    logger.info(
        f"Starting parallel execution with {max_workers} workers for {len(montages)} montages"
    )

    # Serialize config for passing to worker processes
    config_dict = {
        "subject_id": config.subject_id,
        "project_dir": config.project_dir,
        "conductivity_type": config.conductivity_type.value,
        "intensities": {
            "pair1": config.intensities.pair1,
            "pair2": config.intensities.pair2,
            "pair3": config.intensities.pair3,
            "pair4": config.intensities.pair4,
        },
        "electrode": {
            "shape": config.electrode.shape,
            "dimensions": config.electrode.dimensions,
            "thickness": config.electrode.thickness,
            "sponge_thickness": config.electrode.sponge_thickness,
        },
        "eeg_net": config.eeg_net,
        "parallel": {
            "enabled": config.parallel.enabled,
            "max_workers": config.parallel.max_workers,
        },
    }

    # Prepare worker arguments
    worker_args = []
    for idx, montage in enumerate(montages):
        montage_dict = {
            "name": montage.name,
            "electrode_pairs": [list(p) for p in montage.electrode_pairs],
            "is_xyz": montage.is_xyz,
            "eeg_net": montage.eeg_net,
        }
        worker_args.append(
            {
                "config_dict": config_dict,
                "montage_dict": montage_dict,
                "simulation_dir": simulation_dir,
                "worker_id": idx,
            }
        )

    results = []
    completed = 0
    total = len(montages)

    # Use ProcessPoolExecutor with 'spawn' context for SimNIBS compatibility
    # 'spawn' creates fresh Python interpreters, avoiding fork-related issues
    with ProcessPoolExecutor(
        max_workers=max_workers, mp_context=mp_context
    ) as executor:
        # Submit all tasks
        future_to_montage = {
            executor.submit(_run_montage_worker, args): args["montage_dict"]["name"]
            for args in worker_args
        }

        # Collect results as they complete
        for future in as_completed(future_to_montage):
            montage_name = future_to_montage[future]
            try:
                result = future.result(timeout=7200)  # 2 hour timeout per simulation
                results.append(result)
                completed += 1

                status = (
                    "completed" if result.get("status") == "completed" else "failed"
                )
                logger.info(f"Montage {montage_name} {status} ({completed}/{total})")

                if progress_callback:
                    progress_callback(completed, total, montage_name)

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Worker exception for {montage_name}: {error_msg}")
                results.append(
                    {
                        "montage_name": montage_name,
                        "status": "failed",
                        "error": error_msg,
                    }
                )
                completed += 1

                if progress_callback:
                    progress_callback(completed, total, montage_name)

    logger.info(f"Parallel execution complete: {completed}/{total} montages processed")
    return results


def _run_single_montage(
    config: SimulationConfig,
    montage: MontageConfig,
    simulation_dir: str,
    session_builder: SessionBuilder,
    post_processor: PostProcessor,
    logger,
) -> dict:
    """
    Run simulation for a single montage.

    Args:
        config: Simulation configuration
        montage: Montage configuration
        simulation_dir: Base simulation directory
        session_builder: Session builder instance
        post_processor: Post-processor instance
        logger: Logger instance

    Returns:
        Dictionary with simulation result
    """
    pm = get_path_manager()
    montage_dir = pm.path(
        "simulation", subject_id=config.subject_id, simulation_name=montage.name
    )

    # Step 1: Create complete directory structure
    logger.info(f"Creating directory structure for {montage.name}")
    dirs = setup_montage_directories(montage_dir, montage.simulation_mode)

    # Step 1.5: Create simulation config file for downstream tools
    logger.info(f"Creating simulation configuration file")
    create_simulation_config_file(config, montage, dirs["documentation"], logger)

    # Step 2: Run montage visualization immediately after directory setup
    montage_img_dir = (
        dirs.get("mti_montage_imgs")
        if montage.simulation_mode == SimulationMode.MTI
        else dirs["ti_montage_imgs"]
    )
    logger.info("Montage visualization: Started")
    logger.info(
        f"Running montage visualization for {montage.name} (output dir: {montage_img_dir})"
    )
    # Only pass electrode_pairs if they contain electrode names (not coordinates)
    electrode_pairs = None
    if montage.electrode_pairs and not montage.is_xyz:
        # Check if pairs contain strings (electrode names) not numbers (coordinates)
        if any(isinstance(e, str) for pair in montage.electrode_pairs for e in pair):
            electrode_pairs = montage.electrode_pairs

    viz_success = run_montage_visualization(
        montage_name=montage.name,
        simulation_mode=montage.simulation_mode,
        eeg_net=montage.eeg_net or config.eeg_net,
        output_dir=montage_img_dir,
        project_dir=config.project_dir,
        logger=logger,
        electrode_pairs=electrode_pairs,
    )
    if viz_success:
        logger.info("Montage visualization: ✓ Complete")
        logger.info(f"Montage visualization completed for {montage.name}")
    else:
        logger.warning(
            f"Montage visualization failed or was skipped for {montage.name}, continuing with simulation"
        )

    # Step 3: Build and run SimNIBS session
    S = session_builder.build_session(montage, dirs["hf_dir"])

    logger.info("SimNIBS simulation: Started")
    logger.info(f"Running SimNIBS for {montage.name}...")
    run_simnibs(S)
    logger.info("SimNIBS simulation: ✓ Complete")
    logger.info("SimNIBS completed")

    # Step 4: Post-process results (TI calculation, field extraction, NIfTI, file organization)
    logger.info("Results processing: Started")
    if montage.simulation_mode == SimulationMode.TI:
        output_mesh = post_processor.process_ti_results(
            hf_dir=dirs["hf_dir"],
            output_dir=dirs["ti_mesh"],
            nifti_dir=dirs["ti_niftis"],
            surface_overlays_dir=dirs["ti_surface_overlays"],
            hf_mesh_dir=dirs["hf_mesh"],
            hf_nifti_dir=dirs["hf_niftis"],
            hf_analysis_dir=dirs["hf_analysis"],
            documentation_dir=dirs["documentation"],
            montage_name=montage.name,
        )
    elif montage.simulation_mode == SimulationMode.MTI:
        output_mesh = post_processor.process_mti_results(
            hf_dir=dirs["hf_dir"],
            ti_dir=dirs["ti_mesh"],
            mti_dir=dirs["mti_mesh"],
            mti_nifti_dir=dirs["mti_niftis"],
            hf_mesh_dir=dirs["hf_mesh"],
            hf_analysis_dir=dirs["hf_analysis"],
            documentation_dir=dirs["documentation"],
            montage_name=montage.name,
        )
    else:
        raise ValueError(f"Unknown simulation mode: {montage.simulation_mode}")

    logger.info("Results processing: ✓ Complete")
    logger.info(f"✓ Completed: {montage.name}")

    return {
        "montage_name": montage.name,
        "montage_type": montage.simulation_mode.value,
        "status": "completed",
        "output_mesh": output_mesh,
    }


def main():
    """
    Command-line entry point for the simulator.

    Parses command-line arguments, loads montages, runs simulations, and generates
    a completion report. This function is called when the module is executed directly
    or via the CLI wrapper script.

    Command-line Arguments
    ----------------------
    1. subject_id : str
        Subject identifier (e.g., '001')
    2. conductivity_str : str
        Conductivity type ('scalar', 'vn', 'dir', 'mc')
    3. project_dir : str
        Project directory path
    4. simulation_dir : str
        Simulation output directory (legacy, not used)
    5. mode : str
        Simulation mode (legacy, not used - auto-detected)
    6. intensity_str : str
        Current intensity string (e.g., '2.0' or '2.0,1.5' or '2.0,1.5,1.0,0.5')
    7. electrode_shape : str
        Electrode shape ('ellipse' or 'rect')
    8. dimensions : str
        Electrode dimensions as 'x,y' in mm (e.g., '8.0,8.0')
    9. thickness : float
        Gel thickness in mm
    10. eeg_net : str
        EEG cap name (e.g., 'GSN-HydroCel-185.csv')
    11+. montage_names : str
        One or more montage names to simulate

    Exit Codes
    ----------
    0 : All simulations completed successfully
    1 : One or more simulations failed

    Output
    ------
    Creates simulation_completion_<subject_id>_<timestamp>.json in derivatives/temp/
    with detailed results of all simulations.

    Examples
    --------
    >>> python simulator.py 001 scalar /path/to/project /tmp TI 2.0 ellipse 8.0,8.0 4.0 GSN-HydroCel-185.csv montage1 montage2
    """
    if len(sys.argv) < 11:
        print(
            "Usage: simulator.py SUBJECT_ID CONDUCTIVITY PROJECT_DIR SIMULATION_DIR MODE "
            "INTENSITY ELECTRODE_SHAPE DIMENSIONS THICKNESS EEG_NET MONTAGE_NAMES..."
        )
        sys.exit(1)

    # Parse command-line arguments
    subject_id = sys.argv[1]
    conductivity_str = sys.argv[2]
    project_dir = sys.argv[3]
    simulation_dir = sys.argv[4]
    mode = sys.argv[5]  # Kept for backward compatibility but not used
    intensity_str = sys.argv[6]
    electrode_shape = sys.argv[7]
    dimensions = [float(x) for x in sys.argv[8].split(",")]
    thickness = float(sys.argv[9])
    eeg_net = sys.argv[10]
    montage_names = sys.argv[11:]

    # Filter out flags
    montage_names = [name for name in montage_names if not name.startswith("--")]

    # Build configuration
    config = SimulationConfig(
        subject_id=subject_id,
        project_dir=project_dir,
        conductivity_type=ConductivityType(conductivity_str),
        intensities=IntensityConfig.from_string(intensity_str),
        electrode=ElectrodeConfig(
            shape=electrode_shape, dimensions=dimensions, thickness=thickness
        ),
        eeg_net=eeg_net,
    )

    # Load montages
    montages = load_montages(
        montage_names=montage_names,
        project_dir=project_dir,
        eeg_net=eeg_net,
        include_flex=True,
    )

    # Run simulations
    results = run_simulation(config, montages)

    # Generate completion report
    pm = get_path_manager()
    derivatives_dir = pm.path("derivatives")

    report = {
        "session_id": os.environ.get("SIMULATION_SESSION_ID", "unknown"),
        "subject_id": subject_id,
        "project_dir": project_dir,
        "simulation_dir": simulation_dir,
        "completed_simulations": [r for r in results if r["status"] == "completed"],
        "failed_simulations": [r for r in results if r["status"] == "failed"],
        "timestamp": datetime.now().isoformat(),
        "total_simulations": len(results),
        "success_count": len([r for r in results if r["status"] == "completed"]),
        "error_count": len([r for r in results if r["status"] == "failed"]),
    }

    report_file = os.path.join(
        derivatives_dir,
        "temp",
        f"simulation_completion_{subject_id}_{int(time.time())}.json",
    )
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, "w") as f:
        json.dump(report, f, indent=2)

    print(
        f"Completed {report['success_count']}/{report['total_simulations']} simulations"
    )

    # Generate HTML report
    try:
        from tit.reporting import SimulationReportGenerator

        report_gen = SimulationReportGenerator(
            project_dir=project_dir,
            simulation_session_id=report["session_id"],
            subject_id=subject_id,
        )

        # Add simulation parameters
        report_gen.add_simulation_parameters(
            conductivity_type=conductivity_str,
            simulation_mode=mode,
            eeg_net=eeg_net,
            intensity_ch1=config.intensities.pair1,
            intensity_ch2=config.intensities.pair2,
            intensity_ch3=config.intensities.pair3,
            intensity_ch4=config.intensities.pair4,
        )

        # Add electrode parameters
        report_gen.add_electrode_parameters(
            shape=electrode_shape,
            dimensions=f"{dimensions[0]}x{dimensions[1]} mm",
            thickness=thickness,
        )

        # Add subject
        report_gen.add_subject(
            subject_id=subject_id,
            m2m_path=pm.path("m2m", subject_id=subject_id),
            status="completed" if report["error_count"] == 0 else "partial",
        )

        # Add montages and results
        for montage in montages:
            report_gen.add_montage(
                montage_name=montage.name,
                electrode_pairs=[
                    {"electrode1": p[0], "electrode2": p[1]}
                    for p in montage.electrode_pairs
                ],
                montage_type=montage.simulation_mode.value,
            )

        for result in results:
            report_gen.add_simulation_result(
                subject_id=subject_id,
                montage_name=result["montage_name"],
                output_files=result.get("output_files", []),
                status=result["status"],
            )
            if result["status"] == "failed":
                report_gen.add_error(
                    result.get("error", "Unknown error"),
                    context=result["montage_name"],
                )

        report_path = report_gen.generate()
        print(f"Report generated: {report_path}")

    except Exception as e:
        print(f"Warning: Could not generate HTML report: {e}")

    # Exit with error if any simulations failed
    if report["error_count"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
