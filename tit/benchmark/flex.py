#!/usr/bin/env python3
"""
Flex-Search Benchmark - TI optimization with differential evolution

Benchmarks flex-search optimization with multiple multi-start values.

Usage:
  python -m tit.benchmark.flex --config benchmark_config.yaml
  python -m tit.benchmark.flex --m2m-dir /path/to/m2m_101 --multistart 1,2,3
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
import argparse
import json

from tit.benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from tit.benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from tit.benchmark.config import BenchmarkConfig, merge_config_with_args


def setup_project(project_dir: Path, m2m_dir: Path, logger):
    """Set up flex-search project with m2m symlink."""
    m2m_name = m2m_dir.name
    if not m2m_name.startswith("m2m_"):
        raise ValueError(f"Invalid m2m directory: {m2m_name}")
    
    subject_id = m2m_name.replace("m2m_", "")
    bids_subject_id = f"sub-{subject_id}"
    
    # Use project_dir as-is (should already be the container path from config)
    subject_dir = project_dir / bids_subject_id
    simnibs_dir = project_dir / "derivatives" / "SimNIBS" / bids_subject_id
    
    simnibs_dir.mkdir(parents=True, exist_ok=True)

    # Verify m2m directory exists before creating symlink
    if not m2m_dir.exists():
        raise FileNotFoundError(
            f"m2m directory not found: {m2m_dir}\n"
            "This directory should be created by running the CHARM benchmark first.\n"
            "Make sure the CHARM step has completed successfully before running FLEX."
        )

    # Create symlink to m2m
    project_m2m_dir = simnibs_dir / f"m2m_{subject_id}"
    if not project_m2m_dir.exists():
        project_m2m_dir.symlink_to(m2m_dir)
        logger.info(f"Linked m2m: {m2m_dir} -> {project_m2m_dir}")

    return subject_dir, subject_id, project_dir


def run_flex_optimization(subject_id, project_dir, n_multistart, logger, **params):
    """Run a single flex-search optimization."""
    metadata = {
        "subject_id": subject_id,
        "n_multistart": n_multistart,
        **{k: v for k, v in params.items() if k not in ['debug_mode']}
    }
    
    timer = BenchmarkTimer(f"flex_search_multistart_{n_multistart}", metadata=metadata)
    timer.start()
    
    try:
        # Set environment variables
        env = os.environ.copy()
        env.update({
            'PROJECT_DIR': str(project_dir),
            'SIMNIBS_SUBJECTS_DIR': str(project_dir / 'derivatives' / 'SimNIBS'),
            'BIDS_ROOT': str(project_dir),
            'DEBUG_MODE': 'true' if params.get('debug_mode', True) else 'false',
            'ROI_X': str(params['roi_center'][0]),
            'ROI_Y': str(params['roi_center'][1]),
            'ROI_Z': str(params['roi_center'][2]),
            'ROI_RADIUS': str(params['roi_radius'])
        })
        
        # Add tit to PYTHONPATH
        if os.path.isdir("/development/ti-toolbox"):
            ti_toolbox_path = "/development/ti-toolbox"
        elif os.path.isdir("/development/tit"):
            # Backward compatibility (older mounts)
            ti_toolbox_path = "/development/tit"
        else:
            ti_toolbox_path = str(Path(__file__).parent.parent)
        env['PYTHONPATH'] = f"{ti_toolbox_path}:{env.get('PYTHONPATH', '')}"
        
        # Build command
        cmd = [
            "simnibs_python", "-m", "tit.opt.flex",
            "--subject", subject_id,
            "--goal", params['opt_goal'],
            "--postproc", params['postproc'],
            "--roi-method", params['roi_method'],
            "--eeg-net", params['eeg_net'],
            "--radius", str(params['electrode_radius']),
            "--current", str(params['electrode_current']),
            "--n-multistart", str(n_multistart),
            "--max-iterations", str(params['max_iterations']),
            "--population-size", str(params['population_size']),
            "--cpus", str(params['cpus'])
        ]
        
        # Add final simulation control
        # Default in SimNIBS is True, so we need to explicitly skip if we want False
        if not params.get('run_final_simulation', False):
            cmd.append("--skip-final-electrode-simulation")
        
        logger.info(f"Running flex-search: multistart={n_multistart}, goal={params['opt_goal']}")
        
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env, cwd=str(project_dir)
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
        return {"success": True, "result": result}
        
    except Exception as e:
        logger.error(f"Optimization failed: {e}")
        result = timer.stop(success=False, error_message=str(e))
        return {"success": False, "result": result}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark flex-search optimization")
    parser.add_argument("--config", type=Path, help="Configuration file")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--m2m-dir", type=Path)
    parser.add_argument("--multistart", type=str, help="Comma-separated multi-start values")
    parser.add_argument("--iterations", type=int)
    parser.add_argument("--popsize", type=int)
    parser.add_argument("--cpus", type=int)
    parser.add_argument("--no-debug", action="store_true")
    parser.add_argument("--run-final-simulation", action="store_true", 
                        help="Run final electrode simulation (default: False)")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'flex')
    
    # Extract configuration
    project_dir = Path(merged['project_dir'])
    output_dir = Path(merged['output_dir'])
    m2m_dir = Path(merged['m2m_dir'])
    debug_mode = merged.get('debug_mode', True)
    
    # Parse multi-start values
    if args.multistart:
        multistart_values = [int(x.strip()) for x in args.multistart.split(",")]
    else:
        multistart_values = merged.get('multistart', [1, 3, 5])
    
    if not m2m_dir.exists():
        print(f"Error: m2m directory not found: {m2m_dir}")
        sys.exit(1)
    
    # Setup logging
    subject_id = m2m_dir.name.replace("m2m_", "")
    log_file = create_benchmark_log_file("flex", output_dir, subject_id)
    logger = BenchmarkLogger("flex_benchmark", log_file, debug_mode, True)
    
    logger.header("FLEX-SEARCH BENCHMARK")
    logger.info(f"m2m: {m2m_dir}")
    logger.info(f"Multi-start values: {multistart_values}")
    
    try:
        # Setup project
        subject_dir, subject_id, resolved_project_dir = setup_project(project_dir, m2m_dir, logger)
        
        # Optimization parameters
        opt_params = {
            'opt_goal': merged.get('opt_goal', 'mean'),
            'postproc': merged.get('postproc', 'max_TI'),
            'roi_method': merged.get('roi_method', 'spherical'),
            'roi_center': tuple(merged.get('roi_center', [0, 0, 0])),
            'roi_radius': merged.get('roi_radius', 10.0),
            'eeg_net': merged.get('eeg_net', '10-10'),
            'electrode_radius': merged.get('electrode_radius', 4.0),
            'electrode_current': merged.get('electrode_current', 1.0),
            'max_iterations': merged.get('iterations', 500),
            'population_size': merged.get('popsize', 13),
            'cpus': merged.get('cpus', 1),
            'debug_mode': debug_mode,
            'run_final_simulation': merged.get('run_final_simulation', False) or args.run_final_simulation
        }
        
        print_hardware_info()
        logger.info(f"Testing multi-start values: {multistart_values}")
        
        all_results = []
        for n_multistart in multistart_values:
            logger.separator("=", 70)
            logger.info(f"Running: multi-start={n_multistart}")
            logger.separator("=", 70)
            
            result_data = run_flex_optimization(
                subject_id, resolved_project_dir,
                n_multistart, logger, **opt_params
            )
            
            result = result_data["result"]
            all_results.append(result)
            
            print_benchmark_result(result)
            
            # Save individual result
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = output_dir / f"flex_benchmark_{subject_id}_ms{n_multistart}_{timestamp}.json"
            save_benchmark_result(result, result_file)
        
        # Save summary
        summary = {
            "subject_id": subject_id,
            "multistart_values": multistart_values,
            "optimization_parameters": opt_params,
            "results": [
                {
                    "n_multistart": ms,
                    "duration_seconds": r.duration_seconds,
                    "duration_formatted": r.duration_formatted,
                    "success": r.success
                }
                for ms, r in zip(multistart_values, all_results)
            ]
        }
        
        summary_file = output_dir / f"flex_benchmark_{subject_id}_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.separator("=", 70)
        logger.info("BENCHMARK SUMMARY")
        logger.separator("=", 70)
        for ms, r in zip(multistart_values, all_results):
            status = "SUCCESS" if r.success else "FAILED"
            logger.info(f"Multi-start {ms}: {r.duration_formatted} - {status}")
        logger.info(f"Summary: {summary_file}")
        
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
