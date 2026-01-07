#!/usr/bin/env simnibs_python
"""
Batch TI Simulation Script

This script allows running multiple TI simulations with flexible parallelization.
Simulations are executed at the individual simulation level, allowing maximum
parallelism regardless of subject grouping. Edit the BATCH_CONFIG section below
to customize your batch run.

Usage:
    simnibs_python batch_simulate.py [--verbose]

Options:
    --verbose, -v    Enable verbose logging to console

Configuration:
    Define simulations in the SIMULATIONS list with subject-specific entries.
    Each simulation specifies which subject, montages, and intensity to use.
    Simulations run in parallel when PARALLEL.enabled=True and multiple workers available.

Parallelization:
    - Simulation-level: Each individual simulation runs in parallel (recommended)
    - Montage-level: Multiple montages within a simulation run in parallel
    - Combined: Both levels of parallelism work together for maximum throughput

The script interfaces directly with the simulator module - no GUI required.
"""

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

from tit.core import get_path_manager
from tit import logger as logging_util

# =============================================================================
# INTERNAL FUNCTIONS
# =============================================================================

def _process_single_simulation(sim_idx, sim_config, project_dir, eeg_net,
                              conductivity, default_electrode, parallel_config):
    """Process a single simulation. Used for parallel execution."""
    try:
        # Lazy import: keep module importable for `--help` even without SimNIBS installed.
        from tit.sim import (
            run_simulation,
            SimulationConfig,
            ElectrodeConfig,
            IntensityConfig,
            ConductivityType,
            ParallelConfig,
        )
        from tit.sim.montage_loader import load_montages

        subject_id = sim_config["subject"]

        # Set up per-simulation logger (file-only to avoid console conflicts)
        log_dir = os.path.join(project_dir, 'derivatives', 'ti-toolbox', f'sub-{subject_id}')
        os.makedirs(log_dir, exist_ok=True)

        sim_logger = logging_util.get_file_only_logger(
            f'batch-simulate-sim{sim_idx + 1}',
            os.path.join(log_dir, f'simulation_{sim_idx + 1}.log'),
            level=logging.DEBUG
        )

        sim_logger.info(f"Processing simulation {sim_idx + 1} for subject {subject_id}")

        # Normalize configs (accept dicts to keep module import-light)
        intensity = sim_config.get("intensity")
        if isinstance(intensity, dict):
            intensity = IntensityConfig(**intensity)

        electrode = sim_config.get("electrode")
        if electrode is None:
            electrode = default_electrode
        if isinstance(electrode, dict):
            electrode = ElectrodeConfig(**electrode)

        cond = sim_config.get("conductivity", conductivity)
        if isinstance(cond, str):
            cond = getattr(ConductivityType, cond.strip().upper())

        par = parallel_config
        if isinstance(par, dict):
            par = ParallelConfig(**par)

        # Get montages
        montage_input = sim_config["montages"]
        if isinstance(montage_input[0], str):
            # Load montages from names
            montages = load_montages(
                montage_names=montage_input,
                project_dir=project_dir,
                eeg_net=eeg_net,
                include_flex=True
            )
        else:
            # Already MontageConfig objects
            montages = montage_input

        sim_logger.info(f"Running {len(montages)} montage(s) with intensity {sim_config['intensity'].pair1} mA")

        # Build config
        config = SimulationConfig(
            subject_id=subject_id,
            project_dir=project_dir,
            conductivity_type=cond,
            intensities=intensity,
            electrode=electrode,
            eeg_net=eeg_net,
            parallel=par
        )

        # Run simulation
        results = run_simulation(config, montages, logger=sim_logger)

        # Log results
        completed = sum(1 for r in results if r.get('status') == 'completed')
        failed = sum(1 for r in results if r.get('status') == 'failed')
        sim_logger.info(f"Simulation {sim_idx + 1} results: {completed} completed, {failed} failed")

        return results

    except Exception as e:
        # Re-raise with simulation context
        raise Exception(f"Simulation {sim_idx + 1} (subject {subject_id}) failed: {str(e)}")


# =============================================================================
# BATCH CONFIGURATION - EDIT THIS SECTION
# =============================================================================

# Project directory (BIDS root)
PROJECT_DIR = "/mnt/BIDS_new"

# EEG electrode cap file
EEG_NET = "GSN-HydroCel-185.csv"

# Default electrode configuration (can be overridden per simulation)
DEFAULT_ELECTRODE = {
    "shape": "ellipse",
    "dimensions": [8.0, 8.0],
    "thickness": 4.0,
    "sponge_thickness": 2.0,
}

# Parallel execution settings
PARALLEL = {
    "enabled": True,  # Enable parallel execution
    "max_workers": 2,  # Number of parallel workers (0 = auto)
}

# Conductivity type: "scalar", "vn", "dir", or "mc"
CONDUCTIVITY = "SCALAR"

# -----------------------------------------------------------------------------
# SIMULATIONS - Define your simulations here
# Each entry is a dict with:
#   - subject: subject ID (required) - which subject to run this simulation on
#   - montages: list of montage names OR list of MontageConfig objects
#   - intensity: IntensityConfig (current in mA)
#   - electrode: (optional) ElectrodeConfig override
#   - conductivity: (optional) ConductivityType override
# -----------------------------------------------------------------------------

SIMULATIONS = [
    # Simulation 1: Ernie - Standard intensity
    {
        "subject": "ernie",
        "montages": ["test"],
        "intensity": {"pair1": 1.0, "pair2": 1.0, "pair3": 1.0, "pair4": 1.0},
    },

    # # Simulation 2: Ernie - Higher intensity
    # {
    #     "subject": "ernie",
    #     "montages": ["test"],
    #     "intensity": IntensityConfig(
    #         pair1=2.0,  # mA for electrode pair 1
    #         pair2=2.0,  # mA for electrode pair 2
    #         pair3=2.0,  # mA for electrode pair 3 (mTI mode)
    #         pair4=2.0   # mA for electrode pair 4 (mTI mode)
    #     ),
    # },

    #     # Simulation 2: Ernie - Higher intensity (different montage)
    {
        "subject": "ernie",
        "montages": ["test"],
        "intensity": {"pair1": 2.0, "pair2": 2.0, "pair3": 2.0, "pair4": 2.0},
    },

    # Simulation 3: Subject2 - Different montage and intensity
    {
        "subject": "subject2",
        "montages": ["test"],
        "intensity": {"pair1": 1.5, "pair2": 2.5, "pair3": 1.0, "pair4": 1.0},
    },

    # Simulation 4: Ernie - Another configuration
    {
        "subject": "ernie",
        "montages": ["test"],
        "intensity": {"pair1": 0.5, "pair2": 1.0, "pair3": 0.5, "pair4": 1.0},
    },
    
    # # Simulation 2: Ernie - Higher intensity
    # {
    #     "subject": "ernie",
    #     "montages": ["test2"],
    #     "intensity": IntensityConfig(
    #         pair1=2.0,  # mA for electrode pair 1
    #         pair2=2.0,  # mA for electrode pair 2
    #         pair3=2.0,  # mA for electrode pair 3 (mTI mode)
    #         pair4=2.0   # mA for electrode pair 4 (mTI mode)
    #     ),
    # },
    
    # Simulation 3: Subject2 - Asymmetric intensity
    # {
    #     "subject": "subject2",
    #     "montages": ["montage3"],
    #     "intensity": IntensityConfig(
    #         pair1=1.5,  # mA for electrode pair 1
    #         pair2=2.0,  # mA for electrode pair 2
    #         pair3=1.0,  # mA for electrode pair 3 (mTI mode)
    #         pair4=1.0   # mA for electrode pair 4 (mTI mode)
    #     ),
    #     # Optional: different electrode for this simulation
    #     "electrode": ElectrodeConfig(
    #         shape="ellipse",
    #         dimensions=[10.0, 10.0],
    #         thickness=5.0
    #     ),
    # },
    
    # Simulation 4: Ernie - Multiple montages with same config
    # {
    #     "subject": "ernie",
    #     "montages": ["montageA", "montageB", "montageC"],
    #     "intensity": IntensityConfig.from_string("1.0"),  # Shorthand
    # },
]

# Subjects to process (automatically determined from SIMULATIONS below)
# SUBJECTS list is now optional - if not provided, subjects will be extracted from SIMULATIONS
SUBJECTS = [
    # "ernie",  # Uncomment to override automatic subject detection
    # "subject2",
    # "subject3",
]

# =============================================================================
# END OF CONFIGURATION - DO NOT EDIT BELOW
# =============================================================================


def run_batch(logger=None):
    """Run the batch simulation."""
    # Lazy import: keep module importable for `--help` even without SimNIBS installed.
    from tit.sim import ParallelConfig

    parallel_cfg = ParallelConfig(**PARALLEL) if isinstance(PARALLEL, dict) else PARALLEL
    parallel_enabled = bool(getattr(parallel_cfg, "enabled", False))
    workers = int(getattr(parallel_cfg, "effective_workers", 1))

    # Group simulations by subject
    simulations_by_subject = {}
    for sim_config in SIMULATIONS:
        subject = sim_config.get("subject")
        if not subject:
            raise ValueError(f"Simulation configuration missing required 'subject' field: {sim_config}")
        if subject not in simulations_by_subject:
            simulations_by_subject[subject] = []
        simulations_by_subject[subject].append(sim_config)

    # Determine subjects to process
    if SUBJECTS:
        # Use explicitly specified subjects
        subjects_to_process = SUBJECTS
    else:
        # Auto-detect subjects from simulations
        subjects_to_process = sorted(list(simulations_by_subject.keys()))

    # Check if we should run simulations in parallel
    run_simulations_parallel = (
        parallel_enabled and
        len(SIMULATIONS) > 1 and
        workers > 1
    )

    if logger:
        logger.info("Starting TI Batch Simulation")
        logger.debug(f"Project directory: {PROJECT_DIR}")
        logger.debug(f"SUBJECTS config: {SUBJECTS}")
        logger.debug(f"Available subjects from simulations: {list(simulations_by_subject.keys())}")
        logger.debug(f"Subjects to process: {subjects_to_process}")
        logger.debug(f"Total simulations: {len(SIMULATIONS)}")
        logger.debug(f"Simulations by subject: {dict((k, len(v)) for k, v in simulations_by_subject.items())}")
        logger.debug(f"Parallel enabled: {parallel_enabled} ({workers} workers)")
        if run_simulations_parallel:
            logger.info(f"Will run simulations in parallel with {workers} workers")
        else:
            logger.info("Will run simulations sequentially")

    print("=" * 60)
    print("TI BATCH SIMULATION")
    print("=" * 60)
    print(f"Project: {PROJECT_DIR}")
    print(f"Subjects: {subjects_to_process}")
    print(f"Simulations: {len(SIMULATIONS)}")
    if run_simulations_parallel:
        print(f"Parallel: Simulation-level ({workers} workers)")
    else:
        print(f"Parallel: {parallel_enabled} ({workers} workers)")
    print("=" * 60)

    # Initialize path manager
    pm = get_path_manager()
    pm.project_dir = PROJECT_DIR

    all_results = []
    start_time = time.time()

    if run_simulations_parallel:
        if logger:
            logger.info(f"Running {len(SIMULATIONS)} simulations in parallel with {workers} workers")

        # Run simulations in parallel
        with ProcessPoolExecutor(max_workers=workers) as executor:
            # Submit all simulation tasks
            future_to_sim = {}
            for sim_idx, sim_config in enumerate(SIMULATIONS):
                subject_id = sim_config["subject"]

                future = executor.submit(
                    _process_single_simulation,
                    sim_idx,
                    sim_config,
                    PROJECT_DIR,
                    EEG_NET,
                    CONDUCTIVITY,
                    DEFAULT_ELECTRODE,
                    PARALLEL
                )
                future_to_sim[future] = (sim_idx, subject_id)

            # Collect results as they complete
            for future in as_completed(future_to_sim):
                sim_idx, subject_id = future_to_sim[future]
                try:
                    sim_results = future.result()

                    # Add global simulation index to results for reporting
                    for result in sim_results:
                        result['_global_sim_idx'] = sim_idx + 1

                    all_results.extend(sim_results)

                    # Report simulation completion
                    completed = sum(1 for r in sim_results if r.get('status') == 'completed')
                    failed = sum(1 for r in sim_results if r.get('status') == 'failed')
                    total = len(sim_results)
                    montage_names = [r.get('montage_name', 'unknown') for r in sim_results]
                    print(f"\n>>> Simulation {sim_idx + 1}/{len(SIMULATIONS)} (subject {subject_id}) complete: {completed}/{total} montages successful")
                    if montage_names:
                        print(f"    Montages: {', '.join(montage_names[:3])}{'...' if len(montage_names) > 3 else ''}")

                except Exception as exc:
                    print(f"\n>>> Simulation {sim_idx + 1} (subject {subject_id}) generated an exception: {exc}")
                    if logger:
                        logger.error(f"Simulation {sim_idx + 1} (subject {subject_id}) failed with exception: {exc}")

    else:
        # Run simulations sequentially
        # Lazy import: keep module importable for `--help` even without SimNIBS installed.
        from tit.sim import (
            run_simulation,
            SimulationConfig,
            ElectrodeConfig,
            IntensityConfig,
            ConductivityType,
            ParallelConfig,
        )
        from tit.sim.montage_loader import load_montages

        par = ParallelConfig(**PARALLEL) if isinstance(PARALLEL, dict) else PARALLEL

        if logger and len(SIMULATIONS) > 1:
            logger.info(f"Running {len(SIMULATIONS)} simulations sequentially")

        for sim_idx, sim_config in enumerate(SIMULATIONS):
            subject_id = sim_config["subject"]

            print(f"\n>>> Simulation {sim_idx + 1}/{len(SIMULATIONS)} (subject {subject_id})")

            # Get montages
            montage_input = sim_config["montages"]
            if isinstance(montage_input[0], str):
                # Load montages from names
                montages = load_montages(
                    montage_names=montage_input,
                    project_dir=PROJECT_DIR,
                    eeg_net=EEG_NET,
                    include_flex=True
                )
            else:
                # Already MontageConfig objects
                montages = montage_input

            print(f"  Montages: {[m.name for m in montages]}")

            intensity = sim_config.get("intensity")
            if isinstance(intensity, dict):
                intensity = IntensityConfig(**intensity)
            print(f"  Intensity: {getattr(intensity, 'pair1', '?')} mA")

            electrode = sim_config.get("electrode")
            if electrode is None:
                electrode = DEFAULT_ELECTRODE
            if isinstance(electrode, dict):
                electrode = ElectrodeConfig(**electrode)

            cond = sim_config.get("conductivity", CONDUCTIVITY)
            if isinstance(cond, str):
                cond = getattr(ConductivityType, cond.strip().upper())

            # Build config
            config = SimulationConfig(
                subject_id=subject_id,
                project_dir=PROJECT_DIR,
                conductivity_type=cond,
                intensities=intensity,
                electrode=electrode,
                eeg_net=EEG_NET,
                parallel=par
            )

            # Run simulation
            results = run_simulation(config, montages, logger=logger)

            # Add global simulation index to results for reporting
            for result in results:
                result['_global_sim_idx'] = sim_idx + 1

            all_results.extend(results)

            # Report
            completed = sum(1 for r in results if r.get('status') == 'completed')
            failed = sum(1 for r in results if r.get('status') == 'failed')
            print(f"  Result: {completed} completed, {failed} failed")
    
    # Summary
    elapsed = time.time() - start_time
    total_completed = sum(1 for r in all_results if r.get('status') == 'completed')
    total_failed = sum(1 for r in all_results if r.get('status') == 'failed')

    # Group results by simulation for better reporting
    sim_results = {}
    for result in all_results:
        sim_idx = result.get('_global_sim_idx', 0)
        if sim_idx not in sim_results:
            sim_results[sim_idx] = []
        sim_results[sim_idx].append(result)

    print("\n" + "=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)
    print(f"Total simulations: {len(SIMULATIONS)}")
    print(f"Total montages: {len(all_results)}")
    print(f"Completed: {total_completed}")
    print(f"Failed: {total_failed}")
    print(f"Time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print("=" * 60)
    
    # List any failures
    if total_failed > 0:
        print("\nFailed simulations:")
        for r in all_results:
            if r.get('status') == 'failed':
                print(f"  - {r['montage_name']}: {r.get('error', 'Unknown error')}")
    
    return all_results


def main():
    """Main entry point with command line argument parsing."""
    parser = argparse.ArgumentParser(
        description="Batch TI Simulation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s                           # Run with default settings
    %(prog)s --verbose                 # Run with verbose logging
    %(prog)s -v                        # Same as --verbose

Configuration Example:
    SIMULATIONS = [
        # Different subjects, same montage
        {"subject": "ernie", "montages": ["montage1"], "intensity": IntensityConfig(pair1=1.0, pair2=1.0)},
        {"subject": "subject2", "montages": ["montage1"], "intensity": IntensityConfig(pair1=1.0, pair2=1.0)},

        # Same subject, different intensities
        {"subject": "ernie", "montages": ["montage1"], "intensity": IntensityConfig(pair1=2.0, pair2=2.0)},
        {"subject": "ernie", "montages": ["montage2"], "intensity": IntensityConfig(pair1=1.5, pair2=1.5)},

        # Same subject, different montages
        {"subject": "ernie", "montages": ["montage2"], "intensity": IntensityConfig(pair1=1.0, pair2=1.0)},
        {"subject": "ernie", "montages": ["montage3"], "intensity": IntensityConfig(pair1=1.0, pair2=1.0)}
    ]
        """
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging to console'
    )

    args = parser.parse_args()

    # Set up logging based on verbose flag
    if args.verbose:
        # Verbose mode: show DEBUG level logs on console
        logger = logging_util.get_logger('batch-simulate', console=True)
        logger.setLevel(logging.DEBUG)
        console_level = logging.DEBUG
    else:
        # Normal mode: show INFO level logs on console
        logger = logging_util.get_logger('batch-simulate', console=True)
        logger.setLevel(logging.INFO)
        console_level = logging.INFO

    # Update console handler level
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(console_level)

    # Configure external loggers (simnibs, etc.) to use our logger's handlers
    logging_util.configure_external_loggers(['simnibs', 'mesh_io', 'sim_struct', 'TI'], logger)

    run_batch(logger)


if __name__ == "__main__":
    main()

