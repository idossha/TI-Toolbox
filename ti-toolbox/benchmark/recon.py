#!/usr/bin/env python3
"""
Recon-All Benchmark - FreeSurfer cortical reconstruction

Benchmarks FreeSurfer recon-all performance with T1/T2 anatomical images.
Supports multiple subjects running in parallel or sequentially using recon-all.sh's native capabilities.

Usage:
  python -m benchmark.recon --config benchmark_config.yaml
  python -m benchmark.recon --config benchmark_config.yaml --parallel
  python -m benchmark.recon --subjects 101,102,103 --parallel
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
import argparse
import json
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from benchmark.config import BenchmarkConfig, merge_config_with_args


def setup_project(project_dir: Path, t1_image: Path, t2_image: Path, subject_id: str, logger):
    """Set up BIDS project structure (no file copying needed)."""
    bids_subject_id = f"sub-{subject_id}"
    
    # Detect container and set paths
    if os.path.exists("/mnt"):
        mnt_project_dir = Path("/mnt") / project_dir.name
        subject_dir = mnt_project_dir / bids_subject_id
    else:
        subject_dir = project_dir / bids_subject_id
    
    # Verify input files exist
    if not t1_image.exists():
        raise FileNotFoundError(f"T1 image not found: {t1_image}")
    if t2_image and not t2_image.exists():
        raise FileNotFoundError(f"T2 image not found: {t2_image}")
    
    # Create output directory for FreeSurfer
    freesurfer_dir = subject_dir.parent / "derivatives" / "freesurfer" / bids_subject_id
    freesurfer_dir.mkdir(parents=True, exist_ok=True)
    
    # Create dataset_description.json
    dataset_desc = subject_dir.parent / "dataset_description.json"
    if not dataset_desc.exists():
        dataset_desc.write_text('{"Name": "FreeSurfer Benchmark", "BIDSVersion": "1.6.0"}')
    
    logger.info(f"Using existing files - T1: {t1_image}")
    if t2_image:
        logger.info(f"Using existing files - T2: {t2_image}")
    logger.info(f"Project ready: {subject_dir.parent}")
    return subject_dir, subject_id


def run_recon_subject(subject_dir: Path, recon_script: Path, logger, use_openmp=False, debug_mode=True):
    """Run FreeSurfer recon-all for a single subject using the script's native capabilities."""
    subject_id = subject_dir.name.replace("sub-", "")
    
    metadata = {
        "subject_id": subject_id,
        "recon_script": str(recon_script),
        "openmp_enabled": use_openmp,
        "debug_mode": debug_mode
    }
    
    timer = BenchmarkTimer(f"recon_all_{subject_id}", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        # Build command - let recon-all.sh handle threading
        cmd = [str(recon_script), str(subject_dir)]
        if use_openmp:
            cmd.append("--parallel")
        
        logger.info(f"Running recon-all: subject={subject_id}, openmp={'enabled' if use_openmp else 'disabled'}")
        logger.info(f"Command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, env=env
        )
        
        line_count = 0
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                logger.debug(line.rstrip())
                line_count += 1
                if line_count % 50 == 0:
                    timer.sample()
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
        
        result = timer.stop(success=True)
        
        # Add FreeSurfer output location to metadata
        fs_dir = subject_dir.parent / "derivatives" / "freesurfer" / subject_dir.name
        result.metadata['freesurfer_output'] = str(fs_dir)
        
        return {"success": True, "result": result, "subject_id": subject_id}
        
    except Exception as e:
        logger.error(f"Recon-all failed for {subject_id}: {e}")
        result = timer.stop(success=False, error_message=str(e))
        return {"success": False, "result": result, "subject_id": subject_id}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark FreeSurfer recon-all")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--subjects", type=str, help="Comma-separated subject IDs")
    parser.add_argument("--recon-script", type=Path)
    parser.add_argument("--parallel", action="store_true", dest="parallel_override", help="Run multiple subjects in parallel (bash background jobs)")
    parser.add_argument("--use-openmp", action="store_true", dest="openmp_override", help="Use OpenMP threading (--parallel flag to recon-all.sh)")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'recon')
    
    # Extract configuration
    project_dir = Path(merged['project_dir'])
    output_dir = Path(merged['output_dir'])
    recon_script = Path(merged['recon_script'])
    debug_mode = merged.get('debug_mode', True)
    # Use command line arg if provided, otherwise use config value
    run_parallel = merged.get('parallel', False) if not args.parallel_override else True
    use_openmp = merged.get('use_openmp', False) if not args.openmp_override else True
    
    # Parse subjects - can be list or single subject
    if args.subjects:
        subject_ids = [str(s).strip() for s in args.subjects.split(",")]
    else:
        subjects_config = merged.get('subjects') or merged.get('subject_id', '101')
        if isinstance(subjects_config, list):
            subject_ids = [str(s) for s in subjects_config]
        else:
            subject_ids = [str(subjects_config)]
    
    if not recon_script.exists():
        print(f"Error: recon-all.sh not found: {recon_script}")
        sys.exit(1)
    
    # Verify subject data exists
    for subject_id in subject_ids:
        t1_path = project_dir / f"sub-{subject_id}" / "anat" / f"sub-{subject_id}_T1w.nii.gz"
        if not t1_path.exists():
            print(f"Error: T1 image not found for subject {subject_id}: {t1_path}")
            sys.exit(1)
    
    # Setup logging
    log_file = create_benchmark_log_file("recon", output_dir, f"multi_{len(subject_ids)}")
    logger = BenchmarkLogger("recon_benchmark", log_file, debug_mode, True)
    
    print_hardware_info()
    logger.header("FREESURFER RECON-ALL BENCHMARK")
    logger.info(f"Subjects to process: {subject_ids}")
    logger.info(f"Parallel execution: {run_parallel}")
    logger.info(f"OpenMP per subject: {use_openmp}")
    
    try:
        # Setup projects for all subjects
        subject_dirs = []
        for subject_id in subject_ids:
            t1_path = project_dir / f"sub-{subject_id}" / "anat" / f"sub-{subject_id}_T1w.nii.gz"
            t2_path = project_dir / f"sub-{subject_id}" / "anat" / f"sub-{subject_id}_T2w.nii.gz"
            subject_dir, _ = setup_project(
                project_dir, t1_path, t2_path if t2_path.exists() else None, 
                subject_id, logger
            )
            subject_dirs.append(subject_dir)
        
        # Start overall timer
        overall_timer = BenchmarkTimer("recon_all_batch", metadata={
            "num_subjects": len(subject_ids),
            "subject_ids": subject_ids,
            "parallel_execution": run_parallel,
            "use_openmp": use_openmp
        })
        overall_timer.start()
        
        all_results = []
        processes = []
        
        if run_parallel:
            # Launch all subjects in parallel using subprocess
            logger.info(f"Launching {len(subject_dirs)} subjects in parallel...")
            
            for subject_dir in subject_dirs:
                subject_id = subject_dir.name.replace("sub-", "")
                logger.info(f"Starting subject: {subject_id}")
                
                # Start timing for this subject
                start_time = time.time()
                
                # Launch subprocess (non-blocking)
                cmd = [str(recon_script), str(subject_dir)]
                if use_openmp:
                    cmd.append("--parallel")
                
                env = os.environ.copy()
                env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
                
                process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                processes.append((process, subject_id, start_time))
            
            # Wait for all to complete
            logger.info(f"Waiting for {len(processes)} subjects to complete...")
            for process, subject_id, start_time in processes:
                process.wait()
                end_time = time.time()
                duration = end_time - start_time
                
                success = process.returncode == 0
                logger.info(f"Subject {subject_id} {'completed' if success else 'failed'}: {duration:.2f}s")
                
                # Create result
                timer = BenchmarkTimer(f"recon_all_{subject_id}")
                timer.start_time = start_time
                result = timer.stop(success=success)
                
                all_results.append({
                    "success": success,
                    "result": result,
                    "subject_id": subject_id
                })
        else:
            # Run subjects sequentially
            logger.info(f"Running {len(subject_dirs)} subjects sequentially...")
            
            for subject_dir in subject_dirs:
                subject_id = subject_dir.name.replace("sub-", "")
                logger.separator("=", 70)
                logger.info(f"Processing subject: {subject_id}")
                logger.separator("=", 70)
                
                result_data = run_recon_subject(subject_dir, recon_script, logger, use_openmp, debug_mode)
                all_results.append(result_data)
        
        overall_result = overall_timer.stop(success=True)
        
        # Calculate metrics
        total_processing_time = sum(r['result'].duration_seconds for r in all_results if r['success'])
        num_successful = sum(1 for r in all_results if r['success'])
        
        # Save individual results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for result_data in all_results:
            result = result_data['result']
            subject_id = result_data['subject_id']
            
            print_benchmark_result(result)
            
            result_file = output_dir / f"recon_benchmark_{subject_id}_{timestamp}.json"
            save_benchmark_result(result, result_file)
        
        # Save summary
        summary = {
            "num_subjects": len(subject_ids),
            "subject_ids": subject_ids,
            "execution_mode": {
                "parallel_subjects": run_parallel,
                "use_openmp": use_openmp
            },
            "total_wallclock_time_seconds": overall_result.duration_seconds,
            "total_wallclock_time_formatted": overall_result.duration_formatted,
            "total_processing_time_seconds": total_processing_time,
            "average_time_per_subject": total_processing_time / num_successful if num_successful > 0 else 0,
            "parallel_efficiency": (total_processing_time / overall_result.duration_seconds) if run_parallel and overall_result.duration_seconds > 0 else 1.0,
            "results": [
                {
                    "subject_id": r['subject_id'],
                    "success": r['success'],
                    "duration_seconds": r['result'].duration_seconds,
                    "duration_formatted": r['result'].duration_formatted
                }
                for r in all_results
            ]
        }
        
        summary_file = output_dir / f"recon_benchmark_summary_{timestamp}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        # Print summary
        logger.separator("=", 70)
        logger.info("BENCHMARK SUMMARY")
        logger.separator("=", 70)
        logger.info(f"Total subjects: {len(subject_ids)}")
        logger.info(f"Successful: {num_successful}")
        logger.info(f"Wallclock time: {overall_result.duration_formatted}")
        logger.info(f"Total processing time: {total_processing_time:.2f}s")
        if run_parallel:
            logger.info(f"Parallel efficiency: {summary['parallel_efficiency']:.2f}x")
        logger.info(f"Average time per subject: {summary['average_time_per_subject']:.2f}s")
        logger.separator("=", 70)
        for r in all_results:
            status = "SUCCESS" if r['success'] else "FAILED"
            logger.info(f"  {r['subject_id']}: {r['result'].duration_formatted} - {status}")
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
