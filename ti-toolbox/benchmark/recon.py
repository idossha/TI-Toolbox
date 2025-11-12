#!/usr/bin/env python3
"""
Benchmark script for FreeSurfer recon-all.
Tests cortical reconstruction performance with any T1/T2 anatomical images.

This benchmark is modular and can work with any T1 (and optionally T2) images.
Simply provide paths to the T1 and T2 NIfTI files.

Usage:
  python -m benchmark.recon --config benchmark_config.yaml
  python -m benchmark.recon --t1-image /path/to/T1.nii.gz --t2-image /path/to/T2.nii.gz
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import argparse

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


def setup_recon_test_project(
    project_dir: Path,
    t1_image: Path,
    t2_image: Path,
    subject_id: str,
    logger: BenchmarkLogger
) -> tuple[Path, str]:
    """
    Set up test project with provided T1/T2 images for recon-all.
    
    Args:
        project_dir: Path to the project directory
        t1_image: Path to T1 NIfTI image
        t2_image: Path to T2 NIfTI image (optional, can be None)
        subject_id: Subject identifier
        logger: Benchmark logger instance
        
    Returns:
        Tuple of (subject_dir, subject_id)
    """
    logger.info("Setting up recon-all test project...")
    
    bids_subject_id = f"sub-{subject_id}"
    
    # Detect container environment
    if os.path.exists("/mnt"):
        project_name = project_dir.name
        mnt_project_dir = Path("/mnt") / project_name
        subject_dir = mnt_project_dir / bids_subject_id
        anat_dir = subject_dir / "anat"
        logger.info(f"Container detected - using /mnt path: {mnt_project_dir}")
    else:
        subject_dir = project_dir / bids_subject_id
        anat_dir = subject_dir / "anat"
    
    anat_dir.mkdir(parents=True, exist_ok=True)
    
    # Validate and copy T1 image
    if not t1_image.exists():
        raise FileNotFoundError(f"T1 image not found: {t1_image}")
    
    t1_dst = anat_dir / f"{bids_subject_id}_T1w.nii.gz"
    logger.info(f"Copying T1 image: {t1_image} -> {t1_dst}")
    shutil.copy2(t1_image, t1_dst)
    
    # Copy T2 image if provided
    if t2_image and t2_image.exists():
        t2_dst = anat_dir / f"{bids_subject_id}_T2w.nii.gz"
        logger.info(f"Copying T2 image: {t2_image} -> {t2_dst}")
        shutil.copy2(t2_image, t2_dst)
    else:
        logger.warning("T2 image not provided or not found, proceeding with T1 only")
    
    # Create dataset_description.json
    actual_project_dir = subject_dir.parent
    root_dataset_desc = actual_project_dir / "dataset_description.json"
    if not root_dataset_desc.exists():
        root_dataset_desc.write_text("""{
  "Name": "FreeSurfer Recon-all Benchmark",
  "BIDSVersion": "1.6.0",
  "DatasetType": "raw"
}
""")
    
    logger.info(f"Test project ready at: {actual_project_dir}")
    logger.info(f"Subject directory: {subject_dir}")
    
    return subject_dir, subject_id


def check_recon_available() -> bool:
    """Check if FreeSurfer recon-all is available."""
    try:
        result = subprocess.run(
            ["recon-all", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_recon_benchmark(
    subject_dir: Path,
    recon_script: Path,
    output_dir: Path,
    logger: BenchmarkLogger,
    parallel: bool = False,
    debug_mode: bool = True,
    clean: bool = False
) -> None:
    """
    Run the recon-all benchmark.
    
    Args:
        subject_dir: Path to the subject directory
        recon_script: Path to the recon-all.sh script
        output_dir: Directory to save benchmark results
        logger: Benchmark logger instance
        parallel: Whether to use parallel processing
        debug_mode: Whether to run in debug mode
        clean: Whether to clean existing FreeSurfer directory
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    subject_id = subject_dir.name.replace("sub-", "")
    project_dir = subject_dir.parent
    
    # Check if FreeSurfer output exists
    fs_dir = project_dir / "derivatives" / "freesurfer" / subject_dir.name
    if fs_dir.exists() and clean:
        logger.info(f"Cleaning existing FreeSurfer directory: {fs_dir}")
        shutil.rmtree(fs_dir)
    elif fs_dir.exists():
        logger.warning(f"FreeSurfer directory exists: {fs_dir}")
    
    metadata = {
        "subject_id": subject_id,
        "subject_dir": str(subject_dir),
        "project_dir": str(project_dir),
        "recon_script": str(recon_script),
        "parallel": parallel,
        "debug_mode": debug_mode,
        "clean_run": clean
    }
    
    print_hardware_info()
    
    logger.separator()
    logger.info(f"Starting recon-all benchmark for subject: {subject_id}")
    logger.info(f"Using script: {recon_script}")
    logger.info(f"Parallel mode: {parallel}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.separator()
    
    timer = BenchmarkTimer("recon_all", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        cmd = [str(recon_script), str(subject_dir)]
        if parallel:
            cmd.append("--parallel")
        
        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"Environment: DEBUG_MODE={env['DEBUG_MODE']}")
        logger.separator("-", 70)
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
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
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Process failed with exit code {e.returncode}")
        result = timer.stop(success=False, error_message=f"Exit code {e.returncode}")
    except KeyboardInterrupt:
        logger.warning("Benchmark interrupted by user")
        result = timer.stop(success=False, error_message="Interrupted")
        raise
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        result = timer.stop(success=False, error_message=str(e))
        raise
    
    print_benchmark_result(result)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = output_dir / f"recon_benchmark_{subject_id}_{timestamp}.json"
    save_benchmark_result(result, result_file)
    
    latest_file = output_dir / f"recon_benchmark_{subject_id}_latest.json"
    save_benchmark_result(result, latest_file)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark FreeSurfer recon-all with any T1/T2 images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration:
  This script can be configured using a YAML config file (benchmark_config.yaml).
  Command-line arguments override config file values.
"""
    )
    parser.add_argument("--config", type=Path, help="Path to configuration file (YAML)")
    parser.add_argument("--project-dir", type=Path, help="Project directory (overrides config)")
    parser.add_argument("--output-dir", type=Path, help="Output directory (overrides config)")
    parser.add_argument("--clean", action="store_true", help="Clean existing FreeSurfer output")
    parser.add_argument("--keep-project", action="store_true")
    parser.add_argument("--t1-image", type=Path, help="Path to T1 NIfTI image (overrides config)")
    parser.add_argument("--t2-image", type=Path, help="Path to T2 NIfTI image (optional, overrides config)")
    parser.add_argument("--subject-id", type=str, help="Subject identifier (overrides config)")
    parser.add_argument("--recon-script", type=Path, help="Path to recon-all.sh (overrides config)")
    parser.add_argument("--parallel", action="store_true", help="Use parallel processing")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load configuration
    config = BenchmarkConfig(args.config)
    
    # Merge config with command-line arguments
    merged_config = merge_config_with_args(config, args, 'recon')
    
    # Extract values from merged config
    project_dir = Path(merged_config.get('project_dir'))
    output_dir = Path(merged_config.get('output_dir'))
    t1_image = Path(merged_config.get('t1_image'))
    t2_image_str = merged_config.get('t2_image')
    t2_image = Path(t2_image_str) if t2_image_str else None
    recon_script = Path(merged_config.get('recon_script'))
    clean = merged_config.get('clean', False)
    keep_project = merged_config.get('keep_project', False)
    parallel = merged_config.get('parallel', False)
    debug_mode = merged_config.get('debug_mode', True)
    
    # Get or extract subject ID
    subject_id = merged_config.get('subject_id')
    if not subject_id:
        # Try to extract from T1 filename
        t1_name = t1_image.stem.replace('.nii', '')
        if 'sub-' in t1_name:
            subject_id = t1_name.split('sub-')[1].split('_')[0]
        else:
            subject_id = "subject"
    
    if not t1_image.exists():
        print(f"Error: T1 image not found: {t1_image}")
        print(f"Please provide a valid path to a T1 NIfTI image")
        sys.exit(1)
    
    if not recon_script.exists():
        print(f"Error: recon-all.sh not found: {recon_script}")
        sys.exit(1)
    
    if not check_recon_available():
        print("Error: FreeSurfer recon-all is not installed or not in PATH")
        sys.exit(1)
    
    log_file = create_benchmark_log_file("recon", output_dir, subject_id)
    logger = BenchmarkLogger("recon_benchmark", log_file, debug_mode, True)
    
    logger.header("FREESURFER RECON-ALL BENCHMARK")
    if args.config:
        logger.info(f"Config File: {args.config}")
    logger.info(f"Project Directory: {project_dir}")
    logger.info(f"Output Directory: {output_dir}")
    logger.info(f"T1 Image: {t1_image}")
    logger.info(f"T2 Image: {t2_image if t2_image else 'Not provided'}")
    logger.info(f"Subject ID: {subject_id}")
    logger.info(f"Parallel: {parallel}")
    logger.info(f"Debug Mode: {debug_mode}")
    
    try:
        subject_dir, subject_id = setup_recon_test_project(
            project_dir, t1_image, t2_image, subject_id, logger
        )
        
        run_recon_benchmark(
            subject_dir, recon_script, output_dir, 
            logger, parallel, debug_mode, clean
        )
        
        logger.info("Benchmark completed successfully!")
        
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
    finally:
        if not keep_project:
            cleanup_paths = []
            if os.path.exists("/mnt"):
                mnt_path = Path("/mnt") / project_dir.name
                if mnt_path.exists():
                    cleanup_paths.append(mnt_path)
            if project_dir.exists():
                cleanup_paths.append(project_dir)
            
            for cleanup_path in cleanup_paths:
                logger.info(f"Removing test project: {cleanup_path}")
                try:
                    shutil.rmtree(cleanup_path)
                except Exception as e:
                    logger.warning(f"Failed to remove: {e}")


if __name__ == "__main__":
    main()

