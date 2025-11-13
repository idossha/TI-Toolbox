#!/usr/bin/env python3
"""
Benchmark script for flex-search optimization.
Tests TI optimization performance with different multi-start runs.

This benchmark is modular and can work with any existing m2m head model.
Simply point to an existing m2m directory (e.g., /path/to/m2m_101).

Default Parameters:
- Opt goal: mean
- Post-processing: max_TI  
- Spherical target: (0,0,0) with 10mm radius
- Electrode parameters: 4mm radius, 1mA current
- 500 iterations
- Population size: 13
- Number of CPUs: 1
- Multi-start: 1, 3, 5 runs

Usage:
  python -m benchmark.flex --config benchmark_config.yaml
  python -m benchmark.flex --m2m-dir /path/to/m2m_101 --project-dir /tmp/flex-test
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import argparse
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.core import (
    BenchmarkTimer,
    get_hardware_info,
    print_hardware_info,
    print_benchmark_result,
    save_benchmark_result
)
from benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from benchmark.config import BenchmarkConfig, merge_config_with_args


def setup_flex_test_project(
    project_dir: Path,
    m2m_dir: Path,
    logger: BenchmarkLogger
) -> tuple[Path, str]:
    """
    Set up test project for flex-search using existing m2m data.
    
    Args:
        project_dir: Path to the project directory for flex benchmark
        m2m_dir: Path to existing m2m directory (e.g., /path/to/m2m_subjectid)
        logger: Benchmark logger instance
        
    Returns:
        Tuple of (subject_dir, subject_id)
    """
    logger.info("Setting up flex-search test project...")
    
    # Validate m2m directory exists
    if not m2m_dir.exists():
        raise FileNotFoundError(f"m2m directory not found: {m2m_dir}")
    
    # Extract subject ID from m2m directory name (e.g., m2m_101 -> 101)
    m2m_name = m2m_dir.name
    if not m2m_name.startswith("m2m_"):
        raise ValueError(f"Invalid m2m directory name: {m2m_name}. Expected format: m2m_<subject_id>")
    
    subject_id = m2m_name.replace("m2m_", "")
    bids_subject_id = f"sub-{subject_id}"
    
    logger.info(f"Using m2m directory: {m2m_dir}")
    logger.info(f"Subject ID: {subject_id}")
    
    # Detect container environment and set up project structure
    if os.path.exists("/mnt"):
        project_name = project_dir.name
        mnt_project_dir = Path("/mnt") / project_name
        subject_dir = mnt_project_dir / bids_subject_id
        logger.info(f"Container detected - using /mnt path: {mnt_project_dir}")
        
        # Create derivatives structure in project directory
        simnibs_dir = mnt_project_dir / "derivatives" / "SimNIBS" / bids_subject_id
        simnibs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create symlink to m2m directory
        project_m2m_dir = simnibs_dir / f"m2m_{subject_id}"
        if not project_m2m_dir.exists():
            logger.info(f"Creating symlink: {project_m2m_dir} -> {m2m_dir}")
            project_m2m_dir.symlink_to(m2m_dir)
    else:
        subject_dir = project_dir / bids_subject_id
        
        # Create derivatives structure
        simnibs_dir = project_dir / "derivatives" / "SimNIBS" / bids_subject_id
        simnibs_dir.mkdir(parents=True, exist_ok=True)
        
        # Create symlink to m2m directory
        project_m2m_dir = simnibs_dir / f"m2m_{subject_id}"
        if not project_m2m_dir.exists():
            logger.info(f"Creating symlink: {project_m2m_dir} -> {m2m_dir}")
            project_m2m_dir.symlink_to(m2m_dir)
    
    logger.info(f"Subject directory: {subject_dir}")
    logger.info(f"m2m linked successfully")
    
    return subject_dir, subject_id


def create_spherical_roi(
    project_dir: Path,
    subject_id: str,
    center: tuple[float, float, float],
    radius: float,
    logger: BenchmarkLogger
) -> Path:
    """
    Create spherical ROI file for optimization.
    
    Args:
        project_dir: Path to the project directory
        subject_id: Subject ID
        center: ROI center coordinates (x, y, z)
        radius: ROI radius in mm
        logger: Benchmark logger instance
        
    Returns:
        Path to created ROI file
    """
    bids_subject_id = f"sub-{subject_id}"
    simnibs_dir = project_dir / "derivatives" / "SimNIBS" / bids_subject_id
    roi_dir = simnibs_dir / "roi"
    roi_dir.mkdir(parents=True, exist_ok=True)
    
    roi_file = roi_dir / f"spherical_r{int(radius)}.nii.gz"
    
    # Create ROI metadata
    roi_info = {
        "type": "spherical",
        "center": list(center),
        "radius": radius,
        "created_for": "benchmark"
    }
    
    roi_json = roi_dir / f"spherical_r{int(radius)}.json"
    with open(roi_json, 'w') as f:
        json.dump(roi_info, f, indent=2)
    
    logger.info(f"ROI metadata saved: {roi_json}")
    logger.info(f"ROI center: {center}, radius: {radius}mm")
    
    return roi_file


def run_flex_optimization(
    subject_id: str,
    project_dir: Path,
    n_multistart: int,
    logger: BenchmarkLogger,
    opt_goal: str = "mean",
    postproc: str = "max_TI",
    roi_method: str = "spherical",
    roi_center: tuple[float, float, float] = (0, 0, 0),
    roi_radius: float = 10.0,
    eeg_net: str = "10-10",
    electrode_radius: float = 4.0,
    electrode_current: float = 1.0,
    max_iterations: int = 500,
    population_size: int = 13,
    cpus: int = 1,
    thresholds: str = None,
    non_roi_method: str = None,
    enable_mapping: bool = False,
    disable_mapping_simulation: bool = False,
    run_final_electrode_simulation: bool = False,
    skip_final_electrode_simulation: bool = False,
    debug_mode: bool = True
) -> dict:
    """
    Run a single flex-search optimization.
    
    Returns:
        Dictionary with optimization results
    """
    logger.info(f"Running flex-search with {n_multistart} multi-start runs")
    logger.info(f"Parameters: goal={opt_goal}, postproc={postproc}")
    logger.info(f"ROI: center={roi_center}, radius={roi_radius}mm")
    logger.info(f"Electrode: radius={electrode_radius}mm, current={electrode_current}mA")
    logger.info(f"Optimizer: iter={max_iterations}, popsize={population_size}, cpus={cpus}")
    
    metadata = {
        "subject_id": subject_id,
        "n_multistart": n_multistart,
        "opt_goal": opt_goal,
        "postproc": postproc,
        "roi_center": list(roi_center),
        "roi_radius": roi_radius,
        "electrode_radius": electrode_radius,
        "electrode_current": electrode_current,
        "max_iterations": max_iterations,
        "population_size": population_size,
        "cpus": cpus,
        "debug_mode": debug_mode
    }
    
    timer = BenchmarkTimer(f"flex_search_multistart_{n_multistart}", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['PROJECT_DIR'] = str(project_dir)
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        # Add ti-toolbox to PYTHONPATH so simnibs_python can find opt.flex module
        # Detect if running in container (has /development mount)
        if os.path.exists("/development"):
            ti_toolbox_path = "/development/ti-toolbox"
        else:
            # Running locally - use parent directory of this script
            ti_toolbox_path = str(Path(__file__).parent.parent)
        
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{ti_toolbox_path}:{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = ti_toolbox_path
        
        # Set ROI parameters as environment variables (required by flex-search)
        env['ROI_X'] = str(roi_center[0])
        env['ROI_Y'] = str(roi_center[1])
        env['ROI_Z'] = str(roi_center[2])
        env['ROI_RADIUS'] = str(roi_radius)
        
        # Build command (note: ROI parameters are passed via env vars, not CLI args)
        cmd = [
            "simnibs_python", "-m", "opt.flex",
            "--subject", subject_id,
            "--goal", opt_goal,
            "--postproc", postproc,
            "--roi-method", roi_method,
            "--eeg-net", eeg_net,
            "--radius", str(electrode_radius),
            "--current", str(electrode_current),
            "--n-multistart", str(n_multistart),
            "--max-iterations", str(max_iterations),
            "--population-size", str(population_size),
            "--cpus", str(cpus)
        ]
        
        # Add optional focality parameters
        if thresholds:
            cmd.extend(["--thresholds", str(thresholds)])
        if non_roi_method:
            cmd.extend(["--non-roi-method", non_roi_method])
        
        # Add optional mapping parameters
        if enable_mapping:
            cmd.append("--enable-mapping")
        if disable_mapping_simulation:
            cmd.append("--disable-mapping-simulation")
        
        # Add optional simulation control parameters
        if run_final_electrode_simulation:
            cmd.append("--run-final-electrode-simulation")
        if skip_final_electrode_simulation:
            cmd.append("--skip-final-electrode-simulation")
        
        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"Environment: ROI_X={env['ROI_X']}, ROI_Y={env['ROI_Y']}, ROI_Z={env['ROI_Z']}, ROI_RADIUS={env['ROI_RADIUS']}")
        logger.separator("-", 70)
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
            cwd=str(project_dir.parent)
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
        
        return_code = process.wait()
        logger.separator("-", 70)
        logger.info(f"Process completed with exit code: {return_code}")
        
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, cmd)
        
        result = timer.stop(success=True)
        return {"success": True, "result": result}
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Optimization failed with exit code {e.returncode}")
        result = timer.stop(success=False, error_message=f"Exit code {e.returncode}")
        return {"success": False, "result": result}
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        result = timer.stop(success=False, error_message=str(e))
        return {"success": False, "result": result}


def run_flex_benchmark(
    subject_dir: Path,
    output_dir: Path,
    logger: BenchmarkLogger,
    multistart_values: list[int] = [1, 3, 5],
    **opt_params
) -> None:
    """
    Run flex-search benchmark with multiple multi-start values.
    
    Args:
        subject_dir: Path to the subject directory
        output_dir: Directory to save benchmark results
        logger: Benchmark logger instance
        multistart_values: List of multi-start values to test
        **opt_params: Additional optimization parameters
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    subject_id = subject_dir.name.replace("sub-", "")
    project_dir = subject_dir.parent
    
    print_hardware_info()
    
    logger.separator("=", 70)
    logger.info("FLEX-SEARCH MULTI-START BENCHMARK")
    logger.separator("=", 70)
    logger.info(f"Subject: {subject_id}")
    logger.info(f"Multi-start values to test: {multistart_values}")
    logger.separator("=", 70)
    
    all_results = []
    
    for n_multistart in multistart_values:
        logger.separator("=", 70)
        logger.info(f"BENCHMARK RUN: {n_multistart} multi-start")
        logger.separator("=", 70)
        
        result_data = run_flex_optimization(
            subject_id=subject_id,
            project_dir=project_dir,
            n_multistart=n_multistart,
            logger=logger,
            **opt_params
        )
        
        result = result_data["result"]
        all_results.append(result)
        
        # Print individual result
        print_benchmark_result(result)
        
        # Save individual result
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_dir / f"flex_benchmark_{subject_id}_ms{n_multistart}_{timestamp}.json"
        save_benchmark_result(result, result_file)
        
        logger.info(f"Result saved: {result_file}")
        logger.separator("=", 70)
    
    # Save summary
    summary_file = output_dir / f"flex_benchmark_{subject_id}_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary_data = {
        "subject_id": subject_id,
        "multistart_values": multistart_values,
        "optimization_parameters": opt_params,
        "results": [
            {
                "n_multistart": ms,
                "duration_seconds": result.duration_seconds,
                "duration_formatted": result.duration_formatted,
                "peak_memory_mb": result.peak_memory_mb,
                "avg_cpu_percent": result.avg_cpu_percent,
                "success": result.success
            }
            for ms, result in zip(multistart_values, all_results)
        ]
    }
    
    with open(summary_file, 'w') as f:
        json.dump(summary_data, f, indent=2)
    
    logger.info("")
    logger.info("="*70)
    logger.info("BENCHMARK SUMMARY")
    logger.info("="*70)
    for ms, result in zip(multistart_values, all_results):
        status = "SUCCESS" if result.success else "FAILED"
        logger.info(f"Multi-start {ms}: {result.duration_formatted} ({result.duration_seconds:.1f}s) - {status}")
    logger.info(f"Summary saved: {summary_file}")
    logger.info("="*70)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark flex-search optimization with multi-start",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration:
  This script can be configured using a YAML config file (benchmark_config.yaml).
  Command-line arguments override config file values.
  
  To generate an example config file:
    python -m benchmark.config
"""
    )
    parser.add_argument("--config", type=Path, help="Path to configuration file (YAML)")
    parser.add_argument("--project-dir", type=Path, help="Project directory (overrides config)")
    parser.add_argument("--output-dir", type=Path, help="Output directory (overrides config)")
    parser.add_argument("--keep-project", action="store_true")
    parser.add_argument("--m2m-dir", type=Path, help="Path to m2m directory (e.g., /path/to/m2m_101) (overrides config)")
    parser.add_argument("--multistart", type=str, 
                       help="Comma-separated multi-start values (overrides config)")
    parser.add_argument("--iterations", type=int, help="Max iterations (overrides config)")
    parser.add_argument("--popsize", type=int, help="Population size (overrides config)")
    parser.add_argument("--cpus", type=int, help="Number of CPUs (overrides config)")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load configuration
    config = BenchmarkConfig(args.config)
    
    # Merge config with command-line arguments
    merged_config = merge_config_with_args(config, args, 'flex')
    
    # Extract values from merged config
    project_dir = Path(merged_config.get('project_dir'))
    output_dir = Path(merged_config.get('output_dir'))
    m2m_dir = Path(merged_config.get('m2m_dir'))
    keep_project = merged_config.get('keep_project', False)
    debug_mode = merged_config.get('debug_mode', True)
    iterations = merged_config.get('iterations', 500)
    popsize = merged_config.get('popsize', 13)
    cpus = merged_config.get('cpus', 1)
    
    # Parse multi-start values
    if args.multistart:
        multistart_values = [int(x.strip()) for x in args.multistart.split(",")]
    else:
        multistart_values = merged_config.get('multistart', [1, 3, 5])
    
    if not m2m_dir.exists():
        print(f"Error: m2m directory not found: {m2m_dir}")
        print(f"Please provide a valid path to an existing m2m directory")
        sys.exit(1)
    
    # Extract subject ID from m2m directory for logging
    m2m_name = m2m_dir.name
    if m2m_name.startswith("m2m_"):
        log_subject_id = m2m_name.replace("m2m_", "")
    else:
        log_subject_id = "subject"
    
    log_file = create_benchmark_log_file("flex", output_dir, log_subject_id)
    logger = BenchmarkLogger("flex_benchmark", log_file, debug_mode, True)
    
    logger.header("FLEX-SEARCH OPTIMIZATION BENCHMARK")
    if args.config:
        logger.info(f"Config File: {args.config}")
    logger.info(f"Project Directory: {project_dir}")
    logger.info(f"Output Directory: {output_dir}")
    logger.info(f"m2m Directory: {m2m_dir}")
    logger.info(f"Multi-start values: {multistart_values}")
    logger.info(f"Max iterations: {iterations}")
    logger.info(f"Population size: {popsize}")
    logger.info(f"CPUs: {cpus}")
    logger.info(f"Debug Mode: {debug_mode}")
    
    try:
        subject_dir, subject_id = setup_flex_test_project(
            project_dir, m2m_dir, logger
        )
        
        # Optimization parameters from config
        opt_params = {
            "opt_goal": merged_config.get('opt_goal', 'mean'),
            "postproc": merged_config.get('postproc', 'max_TI'),
            "roi_method": merged_config.get('roi_method', 'spherical'),
            "roi_center": tuple(merged_config.get('roi_center', [0, 0, 0])),
            "roi_radius": merged_config.get('roi_radius', 10.0),
            "eeg_net": merged_config.get('eeg_net', '10-10'),
            "electrode_radius": merged_config.get('electrode_radius', 4.0),
            "electrode_current": merged_config.get('electrode_current', 1.0),
            "max_iterations": iterations,
            "population_size": popsize,
            "cpus": cpus,
            "thresholds": merged_config.get('thresholds'),
            "non_roi_method": merged_config.get('non_roi_method'),
            "enable_mapping": merged_config.get('enable_mapping', False),
            "disable_mapping_simulation": merged_config.get('disable_mapping_simulation', False),
            "run_final_electrode_simulation": merged_config.get('run_final_electrode_simulation', False),
            "skip_final_electrode_simulation": merged_config.get('skip_final_electrode_simulation', False),
            "debug_mode": debug_mode
        }
        
        run_flex_benchmark(
            subject_dir, output_dir, logger, 
            multistart_values, **opt_params
        )
        
        logger.info("All benchmarks completed successfully!")
        
    except KeyboardInterrupt:
        logger.warning("Benchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        import traceback
        for line in traceback.format_exc().split('\n'):
            if line:
                logger.error(line)
        sys.exit(1)


if __name__ == "__main__":
    main()

