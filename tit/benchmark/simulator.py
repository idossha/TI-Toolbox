#!/usr/bin/env python3
"""
Simulator Benchmark - TI/mTI simulation execution

Benchmarks the TI/mTI simulator performance for electrode montage simulations.

Usage:
  python -m tit.benchmark.simulator --config benchmark_config.yaml
  python -m tit.benchmark.simulator --m2m-dir /path/to/m2m_101
"""

import sys
import os
import subprocess
import csv
import json
from pathlib import Path
from datetime import datetime
import argparse

from tit.benchmark.core import (
    BenchmarkTimer, print_benchmark_result, save_benchmark_result
)
from tit.benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from tit.benchmark.config import BenchmarkConfig, merge_config_with_args


def select_electrodes(m2m_dir: Path, eeg_net: str, sim_mode: str, logger):
    """
    Select electrodes from the EEG cap CSV file based on simulation mode.
    
    Args:
        m2m_dir: Path to m2m directory
        eeg_net: Name of the EEG cap CSV file
        sim_mode: Simulation mode ('U' for Unipolar, 'M' for Multipolar)
        logger: Logger instance
    
    Returns:
        Comma-separated string of electrode names
    """
    # Determine number of electrodes based on mode
    num_electrodes = 4 if sim_mode == 'U' else 8
    
    # Path to EEG positions file
    eeg_positions_dir = m2m_dir / "eeg_positions"
    eeg_csv_path = eeg_positions_dir / eeg_net
    
    if not eeg_csv_path.exists():
        logger.warning(f"EEG positions file not found: {eeg_csv_path}")
        logger.warning(f"Returning default electrode selection")
        # Return default electrodes if file not found
        if sim_mode == 'U':
            return "E1,E2,E3,E4"
        else:
            return "E1,E2,E3,E4,E5,E6,E7,E8"
    
    try:
        electrodes = []
        with open(eeg_csv_path, 'r') as csvfile:
            reader = csv.reader(csvfile)
            # Skip header if present
            header = next(reader, None)
            
            # Read electrodes from column index 4
            for row in reader:
                if len(row) > 4 and row[4].strip():
                    electrodes.append(row[4].strip())
                    if len(electrodes) >= num_electrodes:
                        break
        
        if len(electrodes) < num_electrodes:
            logger.warning(f"Only found {len(electrodes)} electrodes, needed {num_electrodes}")
        
        electrode_list = ','.join(electrodes[:num_electrodes])
        logger.info(f"Selected {num_electrodes} electrodes for mode '{sim_mode}': {electrode_list}")
        
        return electrode_list
        
    except Exception as e:
        logger.error(f"Error reading electrode file: {e}")
        logger.warning("Returning default electrode selection")
        if sim_mode == 'U':
            return "E1,E2,E3,E4"
        else:
            return "E1,E2,E3,E4,E5,E6,E7,E8"


def create_montage_config(project_dir: Path, montage_name: str, electrodes: list, 
                         eeg_net: str, sim_mode: str, logger):
    """
    Create or update montage configuration with electrode pairs.
    
    Args:
        project_dir: Project directory
        montage_name: Name of the montage to create
        electrodes: List of electrode names
        eeg_net: EEG cap filename
        sim_mode: Simulation mode ('U' or 'M')
        logger: Logger instance
    """
    # Determine montage file path
    montage_file = project_dir / "code" / "tit" / "config" / "montage_list.json"
    
    if not montage_file.exists():
        logger.warning(f"Montage file not found: {montage_file}")
        # Create default structure
        montage_data = {"nets": {}}
    else:
        try:
            with open(montage_file, 'r') as f:
                montage_data = json.load(f)
        except Exception as e:
            logger.error(f"Error reading montage file: {e}")
            montage_data = {"nets": {}}
    
    # Ensure net exists in structure
    if eeg_net not in montage_data["nets"]:
        montage_data["nets"][eeg_net] = {
            "uni_polar_montages": {},
            "multi_polar_montages": {}
        }
    
    # Create electrode pairs
    # For U mode: 2 pairs (4 electrodes)
    # For M mode: 4 pairs (8 electrodes)
    pairs = []
    for i in range(0, len(electrodes), 2):
        if i + 1 < len(electrodes):
            pairs.append([electrodes[i], electrodes[i + 1]])
    
    # Add montage to appropriate section
    if sim_mode == 'U':
        montage_data["nets"][eeg_net]["uni_polar_montages"][montage_name] = pairs
        logger.info(f"Created unipolar montage '{montage_name}' with {len(pairs)} pairs")
    else:  # M mode
        montage_data["nets"][eeg_net]["multi_polar_montages"][montage_name] = pairs
        logger.info(f"Created multipolar montage '{montage_name}' with {len(pairs)} pairs")
    
    # Log the pairs
    for i, pair in enumerate(pairs, 1):
        logger.info(f"  Pair {i}: {pair[0]} - {pair[1]}")
    
    # Write back to file
    try:
        montage_file.parent.mkdir(parents=True, exist_ok=True)
        with open(montage_file, 'w') as f:
            json.dump(montage_data, f, indent=4)
        logger.info(f"Updated montage configuration: {montage_file}")
    except Exception as e:
        logger.error(f"Error writing montage file: {e}")
        raise


def setup_project(project_dir: Path, m2m_dir: Path, subject_id: str, logger):
    """Set up project structure for simulation (no file copying needed)."""
    bids_subject_id = f"sub-{subject_id}"
    
    # Detect container and set paths
    if os.path.exists("/mnt"):
        mnt_project_dir = Path("/mnt") / project_dir.name
        subject_dir = mnt_project_dir / bids_subject_id
    else:
        subject_dir = project_dir / bids_subject_id
    
    # Verify m2m directory exists
    if not m2m_dir.exists():
        raise FileNotFoundError(f"m2m directory not found: {m2m_dir}")
    
    # Create output directory structure
    simnibs_dir = subject_dir.parent / "derivatives" / "SimNIBS" / bids_subject_id
    simulation_dir = simnibs_dir / "Simulations"
    simulation_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Using existing m2m: {m2m_dir}")
    logger.info(f"Simulation output: {simulation_dir}")
    
    return subject_dir, simulation_dir


def run_simulator(subject_id: str, project_dir: Path, simulation_dir: Path, 
                  simulator_script: Path, m2m_dir: Path, montage: str, sim_mode: str,
                  conductivity: str, current: str, eeg_net: str,
                  electrode_shape: str, dimensions: str, thickness: str,
                  logger, debug_mode=True):
    """Run TI/mTI simulator and benchmark performance."""
    
    # Select electrodes based on simulation mode and EEG cap
    electrode_string = select_electrodes(m2m_dir, eeg_net, sim_mode, logger)
    electrode_list = electrode_string.split(',')
    
    # Create montage configuration dynamically
    create_montage_config(project_dir, montage, electrode_list, eeg_net, sim_mode, logger)
    
    metadata = {
        "subject_id": subject_id,
        "simulator_script": str(simulator_script),
        "montage": montage,
        "sim_mode": sim_mode,
        "conductivity": conductivity,
        "current": current,
        "eeg_net": eeg_net,
        "electrodes": electrode_string,
        "electrode_shape": electrode_shape,
        "dimensions": dimensions,
        "thickness": thickness,
        "debug_mode": debug_mode
    }
    
    timer = BenchmarkTimer("ti_simulation", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        env['DIRECT_MODE'] = 'true'
        env['SUBJECT_CHOICES'] = str(subject_id)
        env['CONDUCTIVITY'] = conductivity
        env['SIM_MODE'] = sim_mode
        env['CURRENT'] = current
        env['ELECTRODE_SHAPE'] = electrode_shape
        env['DIMENSIONS'] = dimensions
        env['THICKNESS'] = thickness
        env['SELECTED_MONTAGES'] = montage
        env['EEG_NETS'] = eeg_net
        env['ELECTRODES'] = electrode_string  # Selected electrodes based on sim_mode
        env['SIMULATION_FRAMEWORK'] = 'montage'
        env['PROJECT_DIR_NAME'] = project_dir.name
        
        # Determine main script based on mode
        simulator_dir = simulator_script.parent.parent / "sim"
        if sim_mode == "U":
            main_script = simulator_dir / "main-TI.sh"
        elif sim_mode == "M":
            main_script = simulator_dir / "main-mTI.sh"
        else:
            main_script = simulator_dir / "main-TI.sh"
        
        # Build command - call simulator.sh with direct mode
        cmd = [str(simulator_script), "--run-direct"]
        
        logger.info(f"Running TI simulation for subject: {subject_id}")
        logger.info(f"Montage: {montage}, Mode: {sim_mode}, Conductivity: {conductivity}")
        logger.info(f"Electrodes: {electrode_string}")
        
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env
        )
        
        line_count = 0
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                logger.debug(line.rstrip())
                line_count += 1
                if line_count % 10 == 0:
                    timer.sample()
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
        
        result = timer.stop(success=True)
        result.metadata['simulation_output'] = str(simulation_dir)
        
        return result
        
    except Exception as e:
        logger.error(f"Simulation failed: {e}")
        return timer.stop(success=False, error_message=str(e))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark TI/mTI simulator")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--m2m-dir", type=Path)
    parser.add_argument("--subject-id", type=str)
    parser.add_argument("--simulator-script", type=Path)
    parser.add_argument("--montage", type=str)
    parser.add_argument("--sim-mode", type=str, choices=['U', 'M'])
    parser.add_argument("--conductivity", type=str)
    parser.add_argument("--current", type=str)
    parser.add_argument("--eeg-net", type=str)
    parser.add_argument("--electrode-shape", type=str)
    parser.add_argument("--dimensions", type=str)
    parser.add_argument("--thickness", type=str)
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'simulator')
    
    # Extract configuration
    project_dir = Path(merged['project_dir'])
    output_dir = Path(merged['output_dir'])
    m2m_dir = Path(merged['m2m_dir'])
    simulator_script = Path(merged['simulator_script'])
    subject_id = str(merged.get('subject_id', '101'))
    debug_mode = merged.get('debug_mode', True)
    
    # Simulation parameters (convert all to strings)
    montage = str(merged.get('montage', 'default_montage'))
    sim_mode = str(merged.get('sim_mode', 'U'))
    conductivity = str(merged.get('conductivity', 'scalar'))
    current = str(merged.get('current', '0.002,0.002'))
    eeg_net = str(merged.get('eeg_net', 'GSN-HydroCel-185.csv'))
    electrode_shape = str(merged.get('electrode_shape', 'rect'))
    dimensions = str(merged.get('dimensions', '50,50'))
    thickness = str(merged.get('thickness', '5'))
    
    # Validate paths
    if not m2m_dir.exists():
        print(f"Error: m2m directory not found: {m2m_dir}")
        sys.exit(1)
    if not simulator_script.exists():
        print(f"Error: simulator script not found: {simulator_script}")
        sys.exit(1)
    
    # Setup logging
    log_file = create_benchmark_log_file("simulator", output_dir, subject_id)
    logger = BenchmarkLogger("simulator_benchmark", log_file, debug_mode, True)
    
    logger.header("TI/MTI SIMULATOR BENCHMARK")
    logger.info(f"m2m directory: {m2m_dir}")
    logger.info(f"Montage: {montage}")
    logger.info(f"Subject ID (type: {type(subject_id).__name__}): {subject_id}")

    try:
        # Setup project
        subject_dir, simulation_dir = setup_project(project_dir, m2m_dir, subject_id, logger)
        
        # Run simulation
        result = run_simulator(
            subject_id, project_dir, simulation_dir, simulator_script, m2m_dir,
            montage, sim_mode, conductivity, current, eeg_net,
            electrode_shape, dimensions, thickness, logger, debug_mode
        )
        
        # Save and display results
        print_benchmark_result(result)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_dir / f"simulator_benchmark_{subject_id}_{timestamp}.json"
        save_benchmark_result(result, result_file)
        
        latest_file = output_dir / f"simulator_benchmark_{subject_id}_latest.json"
        save_benchmark_result(result, latest_file)
        
        logger.info(f"Results saved to {output_dir}")
        
    except KeyboardInterrupt:
        logger.warning("Benchmark interrupted")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

