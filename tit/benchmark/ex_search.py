#!/usr/bin/env python3
"""
Ex-Search Benchmark - Exhaustive TI electrode optimization

Benchmarks the complete ex-search pipeline including ROI setup, TI simulation,
and analysis using pre-existing leadfield matrices.

Usage:
  python -m tit.benchmark.ex_search --config benchmark_config.yaml
  python -m tit.benchmark.ex_search --m2m-dir /path/to/m2m_101 --leadfield /path/to/leadfield.hdf5
  python -m tit.benchmark.ex_search --config benchmark_config.yaml --n-electrodes 2,4,6
  python -m tit.benchmark.ex_search --config benchmark_config.yaml --total-current 2.0 --step-size 0.2 --channel-limit 1.6
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import argparse
import json

from tit.benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from tit.benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from tit.benchmark.config import BenchmarkConfig, merge_config_with_args


def setup_project(project_dir: Path, m2m_dir: Path, leadfield_path: Path, logger):
    """Set up benchmark project structure and copy leadfield."""
    m2m_name = m2m_dir.name
    if not m2m_name.startswith("m2m_"):
        raise ValueError(f"Invalid m2m directory name: {m2m_name}")

    subject_id = m2m_name.replace("m2m_", "")
    bids_subject_id = f"sub-{subject_id}"

    # Detect container and set paths
    if os.path.exists("/mnt"):
        mnt_project_dir = Path("/mnt") / project_dir.name
        subject_dir = mnt_project_dir / bids_subject_id
        simnibs_dir = mnt_project_dir / "derivatives" / "SimNIBS" / bids_subject_id
    else:
        subject_dir = project_dir / bids_subject_id
        simnibs_dir = project_dir / "derivatives" / "SimNIBS" / bids_subject_id

    # Verify m2m directory exists
    if not m2m_dir.exists():
        raise FileNotFoundError(
            f"m2m directory not found: {m2m_dir}\n"
            "This directory should be created by running the CHARM benchmark first.\n"
            "Make sure the CHARM step has completed successfully before running EX_SEARCH."
        )

    # Verify leadfield exists
    if not leadfield_path.exists():
        raise FileNotFoundError(f"Leadfield not found: {leadfield_path}")

    # Create output directories
    ex_search_dir = simnibs_dir / "ex_search"
    ex_search_dir.mkdir(parents=True, exist_ok=True)

    # Copy leadfield to expected SimNIBS location
    leadfield_dir = simnibs_dir / "leadfields"
    leadfield_dir.mkdir(parents=True, exist_ok=True)
    expected_leadfield_path = leadfield_dir / leadfield_path.name

    if not expected_leadfield_path.exists():
        shutil.copy2(leadfield_path, expected_leadfield_path)
        logger.info(f"Copied leadfield: {leadfield_path} -> {expected_leadfield_path}")

    logger.info(f"Using existing leadfield: {leadfield_path}")
    return subject_dir, subject_id, expected_leadfield_path


def create_roi_files(m2m_dir: Path, roi_center: tuple, roi_radius: float, logger):
    """Create ROI files for ex-search."""
    roi_dir = m2m_dir / "ROIs"
    roi_dir.mkdir(parents=True, exist_ok=True)
    
    x, y, z = int(round(roi_center[0])), int(round(roi_center[1])), int(round(roi_center[2]))
    
    # Create ROI CSV file (required by TI simulation)
    roi_csv = roi_dir / f"xyz_{x}_{y}_{z}.csv"
    roi_csv.write_text(f"{roi_center[0]},{roi_center[1]},{roi_center[2]}\n")
    
    # Create ROI list file (required by ex_analyzer)
    roi_list = roi_dir / "roi_list.txt"
    roi_list.write_text(f"{roi_csv.name}\n")
    
    logger.info(f"Created ROI files: {roi_csv.name}")
    return roi_dir


def select_electrodes(electrode_cap_path: Path, n_per_channel: int, logger):
    """Select electrodes from cap file for TI simulation."""
    electrodes = []
    with open(electrode_cap_path, 'r') as f:
        for line in f.readlines()[1:]:  # Skip header
            parts = line.strip().split(',')
            # Handle both 5-column (type,X,Y,Z,Name) and 3-column (name,x,y) formats
            if len(parts) >= 5:
                name = parts[4].strip()
                if name and name.lower() not in ['electrode', 'referenceelectrode', 'fiducial']:
                    electrodes.append(name)
            elif len(parts) >= 1:
                name = parts[0].strip()
                if name:
                    electrodes.append(name)
    
    # Select exactly n_per_channel * 4 electrodes
    total_needed = n_per_channel * 4
    if len(electrodes) < total_needed:
        logger.warning(f"Only {len(electrodes)} electrodes available, need {total_needed}")
        n_per_channel = len(electrodes) // 4
    
    electrodes = electrodes[:total_needed]
    e1_plus = electrodes[:n_per_channel]
    e1_minus = electrodes[n_per_channel:2*n_per_channel]
    e2_plus = electrodes[2*n_per_channel:3*n_per_channel]
    e2_minus = electrodes[3*n_per_channel:4*n_per_channel]
    
    logger.info(f"Selected {n_per_channel} electrodes per channel from {electrode_cap_path.name}")
    return e1_plus, e1_minus, e2_plus, e2_minus


def run_ti_simulation(subject_id, project_dir, leadfield_path, electrode_cap_path, 
                      n_electrodes, total_current, step_size, roi_center, channel_limit, logger):
    """Run TI simulation with automatic electrode selection."""
    # Select electrodes
    e1_plus, e1_minus, e2_plus, e2_minus = select_electrodes(
        electrode_cap_path, n_electrodes, logger
    )
    
    # Extract net name for environment variable
    net_name = leadfield_path.stem.replace('_leadfield', '')
    
    # Set environment variables
    env = os.environ.copy()
    env.update({
        'PROJECT_DIR': str(project_dir),
        'SUBJECT_NAME': subject_id,
        'LEADFIELD_HDF': str(leadfield_path),
        'SELECTED_EEG_NET': net_name,
        'ROI_NAME': f"xyz_{int(round(roi_center[0]))}_{int(round(roi_center[1]))}_{int(round(roi_center[2]))}",
        'TOTAL_CURRENT': str(total_current),
        'CURRENT_STEP': str(step_size),
        'TI_LOG_FILE': str(logger.log_file) if hasattr(logger, 'log_file') else '/tmp/ti_log.txt',
        'DEBUG_MODE': 'true' if logger.debug_mode else 'false'
    })
    
    # Prepare input data
    input_lines = [
        " ".join(e1_plus), " ".join(e1_minus), " ".join(e2_plus), " ".join(e2_minus),
        str(total_current), str(step_size)
    ]
    
    # Add channel_limit if specified
    if channel_limit is not None:
        input_lines.append(str(channel_limit))
    else:
        input_lines.append("")  # Empty line for default behavior
    
    input_data = "\n".join(input_lines) + "\n"
    
    # Run TI simulation
    ti_sim_script = Path(__file__).parent.parent / "opt" / "ex" / "ti_sim.py"
    cmd = ["simnibs_python", str(ti_sim_script)]
    
    limit_str = f", limit={channel_limit}mA" if channel_limit is not None else ""
    logger.info(f"Running TI simulation: {n_electrodes} electrodes/channel, {total_current}mA, {step_size}mA step{limit_str}")
    
    process = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, text=True, env=env, cwd=str(project_dir)
    )
    
    stdout, _ = process.communicate(input=input_data)
    
    if logger.debug_mode:
        for line in stdout.split('\n'):
            if line.strip():
                logger.debug(line)
    
    if process.returncode != 0:
        logger.error(f"TI simulation failed with exit code {process.returncode}")
        return False
    
    logger.info("TI simulation completed successfully")
    return True


def verify_results(subject_id, project_dir, roi_dir, roi_center, leadfield_path, logger):
    """Verify pre-calculated results exist (runs ex_analyzer in verification mode)."""
    net_name = leadfield_path.stem.replace('_leadfield', '')
    
    env = os.environ.copy()
    env.update({
        'PROJECT_DIR': str(project_dir),
        'SUBJECT_NAME': subject_id,
        'ROI_NAME': f"xyz_{int(round(roi_center[0]))}_{int(round(roi_center[1]))}_{int(round(roi_center[2]))}",
        'SELECTED_EEG_NET': net_name,
        'ROI_LIST_FILE': str(roi_dir / "roi_list.txt"),
        'TI_LOG_FILE': str(logger.log_file) if hasattr(logger, 'log_file') else '/tmp/ti_log.txt'
    })
    
    analyzer_script = Path(__file__).parent.parent / "opt" / "ex" / "ex_analyzer.py"
    cmd = ["simnibs_python", str(analyzer_script), str(roi_dir)]
    
    logger.info("Verifying pre-calculated results...")
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(roi_dir.parent.parent.parent))
    
    if result.returncode != 0:
        logger.error("Results verification failed")
        return False
    
    logger.info("Results verified successfully")
    return True


def run_single_benchmark(subject_dir, project_dir, m2m_dir, leadfield_path, output_dir,
                         n_electrodes, total_current, step_size, roi_center, roi_radius, 
                         channel_limit, logger):
    """Run ex-search benchmark pipeline for a single electrode configuration."""
    subject_id = subject_dir.name.replace("sub-", "")
    
    logger.separator("=", 70)
    logger.info(f"EX-SEARCH: {n_electrodes} electrodes/channel")
    logger.separator("=", 70)
    logger.info(f"Subject: {subject_id}")
    limit_str = f", Channel limit: {channel_limit}mA" if channel_limit is not None else ""
    logger.info(f"Electrodes/channel: {n_electrodes}, Current: {total_current}mA, Step: {step_size}mA{limit_str}")
    logger.info(f"ROI: center={roi_center}, radius={roi_radius}mm")
    logger.separator("=", 70)
    
    # Start benchmark timer
    metadata = {
        "subject_id": subject_id,
        "leadfield_path": str(leadfield_path),
        "electrodes_per_channel": n_electrodes,
        "total_current": total_current,
        "step_size": step_size,
        "channel_limit": channel_limit,
        "roi_center": list(roi_center),
        "roi_radius": roi_radius
    }
    
    timer = BenchmarkTimer(f"ex_search_n{n_electrodes}", metadata=metadata)
    timer.start()
    
    try:
        # Step 1: Create ROI files
        logger.info("Step 1: Creating ROI files...")
        roi_dir = create_roi_files(m2m_dir, roi_center, roi_radius, logger)
        
        # Step 2: Find electrode cap
        logger.info("Step 2: Locating electrode cap...")
        leadfield_name = leadfield_path.stem
        if leadfield_name.startswith(f"{subject_id}_leadfield_"):
            net_name = leadfield_name.replace(f"{subject_id}_leadfield_", "", 1)
        elif leadfield_name.startswith("leadfield_"):
            net_name = leadfield_name.replace("leadfield_", "", 1)
        elif leadfield_name.startswith(f"{subject_id}_"):
            net_name = leadfield_name.replace(f"{subject_id}_", "", 1)
        else:
            net_name = leadfield_name
        
        electrode_cap_path = m2m_dir / "eeg_positions" / f"{net_name}.csv"
        if not electrode_cap_path.exists():
            raise FileNotFoundError(f"Electrode cap not found: {electrode_cap_path}")
        logger.info(f"Found electrode cap: {electrode_cap_path}")
        
        # Step 3: Run TI simulation
        logger.info("Step 3: Running TI simulation...")
        # Get the copied leadfield path in the project structure
        project_root_dir = subject_dir.parent
        simnibs_dir = project_root_dir / "derivatives" / "SimNIBS" / subject_dir.name
        copied_leadfield = simnibs_dir / "leadfields" / leadfield_path.name
        
        # Determine actual project directory for container compatibility
        if os.path.exists("/mnt") and str(subject_dir).startswith("/mnt/"):
            actual_project_dir = subject_dir.parent
        else:
            actual_project_dir = project_dir
        
        if not run_ti_simulation(
            subject_id, actual_project_dir, copied_leadfield, electrode_cap_path,
            n_electrodes, total_current, step_size, roi_center, channel_limit, logger
        ):
            raise RuntimeError("TI simulation failed")
        
        # Step 4: Verify results
        logger.info("Step 4: Verifying pre-calculated results...")
        if not verify_results(subject_id, actual_project_dir, roi_dir, roi_center, copied_leadfield, logger):
            raise RuntimeError("Results verification failed")
        
        # Success - log results location
        net_name_full = copied_leadfield.stem.replace('_leadfield', '')
        roi_name = f"xyz_{int(round(roi_center[0]))}_{int(round(roi_center[1]))}_{int(round(roi_center[2]))}"
        results_path = f"/mnt/BIDS_new/derivatives/SimNIBS/sub-{subject_id}/ex-search/{roi_name}_{net_name_full}"
        
        logger.separator("=", 70)
        logger.info("EX-SEARCH RESULTS")
        logger.separator("=", 70)
        logger.info(f"Directory: {results_path}")
        logger.info(f"  - analysis_results.json (all montage results)")
        logger.info(f"  - final_output.csv (spreadsheet format)")
        logger.info(f"  - montage_distributions.png (visualizations)")
        logger.separator("=", 70)
        
        result = timer.stop(success=True)
        
        # Calculate number of current ratios (accounting for channel_limit)
        effective_channel_limit = channel_limit if channel_limit is not None else total_current / 2.0
        min_current = max(total_current - effective_channel_limit, step_size)
        num_ratios = int((effective_channel_limit - min_current) / step_size) + 1
        
        # Calculate total iterations and throughput
        total_iterations = (n_electrodes ** 4) * num_ratios
        iterations_per_second = total_iterations / result.duration_seconds if result.duration_seconds > 0 else 0
        
        # Enhanced metadata
        result.metadata.update({
            'results_directory': results_path,
            'output_files': {
                'analysis_results': f"{results_path}/analysis_results.json",
                'csv_output': f"{results_path}/final_output.csv",
                'histogram': f"{results_path}/montage_distributions.png"
            },
            'electrode_configuration': {
                'electrodes_per_channel': n_electrodes,
                'total_electrode_combinations': n_electrodes ** 4,
                'current_ratios': num_ratios,
                'total_montages_tested': total_iterations,
                'channel_limit': channel_limit
            },
            'performance': {
                'total_iterations': total_iterations,
                'iterations_per_second': round(iterations_per_second, 2),
                'duration_seconds': result.duration_seconds
            }
        })
        
        return {"success": True, "result": result}
        
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        result = timer.stop(success=False, error_message=str(e))
        return {"success": False, "result": result}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark ex-search optimization pipeline")
    parser.add_argument("--config", type=Path, help="Path to configuration file (YAML)")
    parser.add_argument("--project-dir", type=Path, help="Project directory")
    parser.add_argument("--output-dir", type=Path, help="Output directory for results")
    parser.add_argument("--m2m-dir", type=Path, help="Path to m2m directory")
    parser.add_argument("--leadfield", type=Path, help="Path to leadfield HDF5 file")
    parser.add_argument("--n-electrodes", type=str, help="Comma-separated electrode counts per channel")
    parser.add_argument("--total-current", type=float, help="Total current in mA")
    parser.add_argument("--step-size", type=float, help="Current step size in mA")
    parser.add_argument("--channel-limit", type=float, help="Channel current limit in mA (default: total_current/2)")
    parser.add_argument("--roi-center", type=str, help="ROI center as 'x,y,z'")
    parser.add_argument("--roi-radius", type=float, help="ROI radius in mm")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'ex_search')
    
    # Extract configuration
    project_dir = Path(merged['project_dir'])
    output_dir = Path(merged['output_dir'])
    m2m_dir = Path(merged['m2m_dir'])
    leadfield_path = Path(merged['leadfield'])
    debug_mode = merged.get('debug_mode', True)
    
    # Parse n_electrodes - can be single value or list
    if args.n_electrodes:
        n_electrodes_list = [int(x.strip()) for x in args.n_electrodes.split(",")]
    else:
        n_electrodes_config = merged.get('n_electrodes', 4)
        if isinstance(n_electrodes_config, list):
            n_electrodes_list = n_electrodes_config
        else:
            n_electrodes_list = [n_electrodes_config]
    
    # Parse current parameters
    total_current = args.total_current if args.total_current is not None else merged.get('total_current', 1.0)
    step_size = args.step_size if args.step_size is not None else merged.get('step_size', 0.1)
    channel_limit = args.channel_limit if args.channel_limit is not None else merged.get('channel_limit', None)
    
    # Parse ROI parameters
    roi_center_config = merged.get('roi_center', [0, 0, 0])
    roi_center = tuple(float(x) for x in roi_center_config) if isinstance(roi_center_config, list) else \
                 tuple(float(x.strip()) for x in roi_center_config.split(","))
    roi_radius = merged.get('roi_radius', 10.0)
    
    # Validate paths
    if not m2m_dir.exists():
        print(f"Error: m2m directory not found: {m2m_dir}")
        sys.exit(1)
    if not leadfield_path.exists():
        print(f"Error: Leadfield not found: {leadfield_path}")
        sys.exit(1)
    
    # Setup logging
    subject_id = m2m_dir.name.replace("m2m_", "")
    log_file = create_benchmark_log_file("ex_search", output_dir, subject_id)
    logger = BenchmarkLogger("ex_search_benchmark", log_file, debug_mode, True)
    
    logger.header("EX-SEARCH BENCHMARK")
    logger.info(f"m2m: {m2m_dir}")
    logger.info(f"Leadfield: {leadfield_path}")
    logger.info(f"Electrode counts to test: {n_electrodes_list}")
    logger.info(f"Current parameters: {total_current}mA total, {step_size}mA step, {channel_limit}mA limit" if channel_limit else f"Current parameters: {total_current}mA total, {step_size}mA step")
    
    try:
        # Setup project
        subject_dir, subject_id, expected_leadfield_path = setup_project(project_dir, m2m_dir, leadfield_path, logger)
        
        print_hardware_info()
        logger.info(f"Testing electrode counts: {n_electrodes_list}")
        
        all_results = []
        for n_electrodes in n_electrodes_list:
            logger.separator("=", 70)
            logger.info(f"Running: n_electrodes={n_electrodes}")
            logger.separator("=", 70)
            
            result_data = run_single_benchmark(
                subject_dir, project_dir, m2m_dir, expected_leadfield_path, output_dir,
                n_electrodes, total_current, step_size, roi_center, roi_radius, 
                channel_limit, logger
            )
            
            result = result_data["result"]
            all_results.append(result)
            
            print_benchmark_result(result)
            
            # Save individual result
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            leadfield_name = leadfield_path.stem.replace('_leadfield', '')
            result_file = output_dir / f"ex_search_benchmark_{subject_id}_n{n_electrodes}_{timestamp}.json"
            save_benchmark_result(result, result_file)
        
        # Save summary
        summary = {
            "subject_id": subject_id,
            "electrode_counts": n_electrodes_list,
            "parameters": {
                "total_current": total_current,
                "step_size": step_size,
                "channel_limit": channel_limit,
                "roi_center": list(roi_center),
                "roi_radius": roi_radius
            },
            "results": [
                {
                    "n_electrodes": n,
                    "duration_seconds": r.duration_seconds,
                    "duration_formatted": r.duration_formatted,
                    "success": r.success,
                    "total_iterations": r.metadata.get('performance', {}).get('total_iterations') if r.success else None,
                    "iterations_per_second": r.metadata.get('performance', {}).get('iterations_per_second') if r.success else None,
                    "total_montages_tested": r.metadata.get('electrode_configuration', {}).get('total_montages_tested') if r.success else None
                }
                for n, r in zip(n_electrodes_list, all_results)
            ]
        }
        
        summary_file = output_dir / f"ex_search_benchmark_{subject_id}_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.separator("=", 70)
        logger.info("BENCHMARK SUMMARY")
        logger.separator("=", 70)
        for n, r in zip(n_electrodes_list, all_results):
            status = "SUCCESS" if r.success else "FAILED"
            if r.success:
                iterations = r.metadata.get('performance', {}).get('total_iterations', 'N/A')
                iter_per_sec = r.metadata.get('performance', {}).get('iterations_per_second', 'N/A')
                logger.info(f"n_electrodes={n}: {r.duration_formatted} - {status}")
                logger.info(f"  Total iterations: {iterations} | Throughput: {iter_per_sec} iter/sec")
            else:
                logger.info(f"n_electrodes={n}: {r.duration_formatted} - {status}")
        logger.info(f"Summary: {summary_file}")
        
    except KeyboardInterrupt:
        logger.warning("Benchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
