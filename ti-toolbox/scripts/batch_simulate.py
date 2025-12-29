#!/usr/bin/env simnibs_python
"""
Batch TI Simulation Script

This script allows running multiple simulations across multiple subjects
with unique configurations per simulation. Edit the BATCH_CONFIG section
below to customize your batch run.

Usage:
    simnibs_python batch_simulate.py

The script interfaces directly with the simulator module - no GUI required.
"""

import os
import sys
import time

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sim import (
    run_simulation,
    SimulationConfig,
    ElectrodeConfig,
    IntensityConfig,
    MontageConfig,
    ConductivityType,
    ParallelConfig,
)
from sim.montage_loader import load_montages
from core import get_path_manager

# =============================================================================
# BATCH CONFIGURATION - EDIT THIS SECTION
# =============================================================================

# Project directory (BIDS root)
PROJECT_DIR = "/mnt/BIDS_new"

# Subjects to process
SUBJECTS = [
    "ernie",
    # "subject2",
    # "subject3",
]

# EEG electrode cap file
EEG_NET = "GSN-HydroCel-185.csv"

# Default electrode configuration (can be overridden per simulation)
DEFAULT_ELECTRODE = ElectrodeConfig(
    shape="ellipse",
    dimensions=[8.0, 8.0],
    thickness=4.0,
    sponge_thickness=2.0
)

# Parallel execution settings
PARALLEL = ParallelConfig(
    enabled=True,      # Enable parallel execution
    max_workers=2      # Number of parallel workers (0 = auto)
)

# Conductivity type: "scalar", "vn", "dir", or "mc"
CONDUCTIVITY = ConductivityType.SCALAR

# -----------------------------------------------------------------------------
# SIMULATIONS - Define your simulations here
# Each entry is a dict with:
#   - montages: list of montage names OR list of MontageConfig objects
#   - intensity: IntensityConfig (current in mA)
#   - electrode: (optional) ElectrodeConfig override
#   - conductivity: (optional) ConductivityType override
# -----------------------------------------------------------------------------

SIMULATIONS = [
    # Simulation 1: Standard intensity
    {
        "montages": ["test"],
        "intensity": IntensityConfig(
            pair1_ch1=1.0,  # mA
            pair1_ch2=1.0,
            pair2_ch1=1.0,
            pair2_ch2=1.0
        ),
    },
    
    # Simulation 2: Higher intensity
    {
        "montages": ["test2"],
        "intensity": IntensityConfig(
            pair1_ch1=2.0,  # mA
            pair1_ch2=2.0,
            pair2_ch1=2.0,
            pair2_ch2=2.0
        ),
    },
    
    # Simulation 3: Asymmetric intensity
    # {
    #     "montages": ["montage3"],
    #     "intensity": IntensityConfig(
    #         pair1_ch1=1.5,
    #         pair1_ch2=1.5,
    #         pair2_ch1=2.0,
    #         pair2_ch2=2.0
    #     ),
    #     # Optional: different electrode for this simulation
    #     "electrode": ElectrodeConfig(
    #         shape="ellipse",
    #         dimensions=[10.0, 10.0],
    #         thickness=5.0
    #     ),
    # },
    
    # Simulation 4: Multiple montages with same config
    # {
    #     "montages": ["montageA", "montageB", "montageC"],
    #     "intensity": IntensityConfig.from_string("1.0"),  # Shorthand
    # },
]

# =============================================================================
# END OF CONFIGURATION - DO NOT EDIT BELOW
# =============================================================================


def run_batch():
    """Run the batch simulation."""
    
    print("=" * 60)
    print("TI BATCH SIMULATION")
    print("=" * 60)
    print(f"Project: {PROJECT_DIR}")
    print(f"Subjects: {SUBJECTS}")
    print(f"Simulations: {len(SIMULATIONS)}")
    print(f"Parallel: {PARALLEL.enabled} ({PARALLEL.effective_workers} workers)")
    print("=" * 60)
    
    # Initialize path manager
    pm = get_path_manager()
    pm.project_dir = PROJECT_DIR
    
    all_results = []
    start_time = time.time()
    
    for subject_id in SUBJECTS:
        print(f"\n>>> Processing subject: {subject_id}")
        
        for sim_idx, sim_config in enumerate(SIMULATIONS):
            print(f"\n  Simulation {sim_idx + 1}/{len(SIMULATIONS)}")
            
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
            print(f"  Intensity: {sim_config['intensity'].pair1_ch1} mA")
            
            # Build config
            config = SimulationConfig(
                subject_id=subject_id,
                project_dir=PROJECT_DIR,
                conductivity_type=sim_config.get("conductivity", CONDUCTIVITY),
                intensities=sim_config["intensity"],
                electrode=sim_config.get("electrode", DEFAULT_ELECTRODE),
                eeg_net=EEG_NET,
                parallel=PARALLEL
            )
            
            # Run simulation
            results = run_simulation(config, montages)
            all_results.extend(results)
            
            # Report
            completed = sum(1 for r in results if r.get('status') == 'completed')
            failed = sum(1 for r in results if r.get('status') == 'failed')
            print(f"  Result: {completed} completed, {failed} failed")
    
    # Summary
    elapsed = time.time() - start_time
    total_completed = sum(1 for r in all_results if r.get('status') == 'completed')
    total_failed = sum(1 for r in all_results if r.get('status') == 'failed')
    
    print("\n" + "=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)
    print(f"Total simulations: {len(all_results)}")
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


if __name__ == "__main__":
    run_batch()

