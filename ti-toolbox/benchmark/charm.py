#!/usr/bin/env python3
"""
Benchmark script for SimNIBS charm (m2m) creation.
Tests the preprocessing pipeline performance with any T1/T2 anatomical images.

This benchmark is modular and can work with any T1 (and optionally T2) images.
Simply provide paths to the T1 and T2 NIfTI files.

Usage:
  python -m benchmark.charm --config benchmark_config.yaml
  python -m benchmark.charm --t1-image /path/to/T1.nii.gz --t2-image /path/to/T2.nii.gz
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


def setup_test_project(
    project_dir: Path,
    t1_image: Path,
    t2_image: Path,
    subject_id: str,
    logger: BenchmarkLogger
) -> tuple[Path, str]:
    """
    Set up a test project directory with provided T1/T2 images.
    
    Args:
        project_dir: Path to the project directory
        t1_image: Path to T1 NIfTI image
        t2_image: Path to T2 NIfTI image (optional, can be None)
        subject_id: Subject identifier (extracted from filename or provided)
        logger: Benchmark logger instance
        
    Returns:
        Tuple of (subject_dir, subject_id)
    """
    logger.info("Setting up test project...")
    
    bids_subject_id = f"sub-{subject_id}"
    
    # Detect if running in container and adjust paths accordingly
    # The charm.sh script expects /mnt/<project_name> structure
    if os.path.exists("/mnt"):
        # Running in container - use /mnt prefix
        project_name = project_dir.name
        mnt_project_dir = Path("/mnt") / project_name
        
        # Create BIDS structure in /mnt
        subject_dir = mnt_project_dir / bids_subject_id
        anat_dir = subject_dir / "anat"
        anat_dir.mkdir(parents=True, exist_ok=True)
        
        # Create derivatives directories in /mnt
        simnibs_dir = mnt_project_dir / "derivatives" / "SimNIBS" / bids_subject_id
        simnibs_dir.mkdir(parents=True, exist_ok=True)
        
        ti_toolbox_dir = mnt_project_dir / "derivatives" / "ti-toolbox"
        ti_toolbox_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Container detected - using /mnt path: {mnt_project_dir}")
    else:
        # Not in container - use provided path
        subject_dir = project_dir / bids_subject_id
        anat_dir = subject_dir / "anat"
        anat_dir.mkdir(parents=True, exist_ok=True)
        
        # Create derivatives directories
        simnibs_dir = project_dir / "derivatives" / "SimNIBS" / bids_subject_id
        simnibs_dir.mkdir(parents=True, exist_ok=True)
        
        ti_toolbox_dir = project_dir / "derivatives" / "ti-toolbox"
        ti_toolbox_dir.mkdir(parents=True, exist_ok=True)
    
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
    
    # Create dataset_description.json files
    # Use the actual project directory (mnt_project_dir if in container)
    actual_project_dir = subject_dir.parent
    root_dataset_desc = actual_project_dir / "dataset_description.json"
    if not root_dataset_desc.exists():
        root_dataset_desc.write_text("""{
  "Name": "TI-Toolbox Charm Benchmark",
  "BIDSVersion": "1.6.0",
  "DatasetType": "raw",
  "Authors": ["TI-Toolbox Benchmark"]
}
""")
    
    logger.info(f"Test project ready at: {actual_project_dir}")
    logger.info(f"Subject directory: {subject_dir}")
    
    return subject_dir, subject_id


def check_charm_available() -> bool:
    """Check if SimNIBS charm is available."""
    try:
        result = subprocess.run(
            ["charm", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_charm_benchmark(
    subject_dir: Path,
    charm_script: Path,
    output_dir: Path,
    logger: BenchmarkLogger,
    clean: bool = False,
    debug_mode: bool = True
) -> None:
    """
    Run the charm benchmark.
    
    Args:
        subject_dir: Path to the subject directory
        charm_script: Path to the charm.sh script
        output_dir: Directory to save benchmark results
        logger: Benchmark logger instance
        clean: Whether to clean existing m2m directory before running
        debug_mode: Whether to run charm in debug mode
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    subject_id = subject_dir.name.replace("sub-", "")
    project_dir = subject_dir.parent
    
    # Check if m2m already exists
    simnibs_dir = project_dir / "derivatives" / "SimNIBS" / subject_dir.name
    m2m_dir = simnibs_dir / f"m2m_{subject_id}"
    
    if m2m_dir.exists() and clean:
        logger.info(f"Cleaning existing m2m directory: {m2m_dir}")
        shutil.rmtree(m2m_dir)
    elif m2m_dir.exists():
        logger.warning(f"m2m directory already exists: {m2m_dir}")
        logger.warning("charm will run with --forcerun flag")
    
    # Prepare metadata
    metadata = {
        "subject_id": subject_id,
        "subject_dir": str(subject_dir),
        "project_dir": str(project_dir),
        "charm_script": str(charm_script),
        "m2m_exists": m2m_dir.exists(),
        "clean_run": clean,
        "debug_mode": debug_mode
    }
    
    # Print hardware info before running
    print_hardware_info()
    
    # Run benchmark
    logger.separator()
    logger.info(f"Starting charm benchmark for subject: {subject_id}")
    logger.info(f"Using script: {charm_script}")
    logger.info(f"Subject directory: {subject_dir}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.separator()
    
    timer = BenchmarkTimer("charm_m2m_creation", metadata=metadata)
    timer.start()
    
    try:
        # Set DEBUG_MODE environment variable for the charm script
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        # Run the charm script
        cmd = [str(charm_script), str(subject_dir)]
        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"Environment: DEBUG_MODE={env['DEBUG_MODE']}")
        logger.separator("-", 70)
        
        # Use subprocess to run the script with real-time output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        
        # Stream output and sample resources periodically
        output_lines = []
        line_count = 0
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                # Log to both console and file
                line_stripped = line.rstrip()
                logger.debug(line_stripped)
                output_lines.append(line_stripped)
                line_count += 1
                
                # Sample resources every 10 lines
                if line_count % 10 == 0:
                    timer.sample()
        
        # Get return code
        return_code = process.wait()
        
        logger.separator("-", 70)
        logger.info(f"charm process completed with exit code: {return_code}")
        
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, cmd)
        
        # Success!
        result = timer.stop(success=True)
        
    except subprocess.CalledProcessError as e:
        logger.error(f"charm process failed with exit code {e.returncode}")
        result = timer.stop(
            success=False,
            error_message=f"charm process failed with exit code {e.returncode}"
        )
    except KeyboardInterrupt:
        logger.warning("Benchmark interrupted by user")
        result = timer.stop(
            success=False,
            error_message="Benchmark interrupted by user"
        )
        raise
    except Exception as e:
        logger.error(f"Benchmark failed with error: {e}")
        result = timer.stop(
            success=False,
            error_message=str(e)
        )
        raise
    
    # Print results
    print_benchmark_result(result)
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = output_dir / f"charm_benchmark_{subject_id}_{timestamp}.json"
    save_benchmark_result(result, result_file)
    
    # Also save a "latest" file for easy access
    latest_file = output_dir / f"charm_benchmark_{subject_id}_latest.json"
    save_benchmark_result(result, latest_file)


def main():
    """Main entry point for the benchmark script."""
    parser = argparse.ArgumentParser(
        description="Benchmark SimNIBS charm (m2m) creation with any T1/T2 images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration:
  This script can be configured using a YAML config file (benchmark_config.yaml).
  The config file will be searched in:
    1. Current directory
    2. ~/.ti-toolbox/
    3. TI-Toolbox root directory
  
  Command-line arguments override config file values.
  
  To generate an example config file:
    python -m benchmark.config
"""
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (YAML format)"
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        help="Project directory for the benchmark (overrides config)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to save benchmark results (overrides config)"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Clean existing m2m directory before running"
    )
    parser.add_argument(
        "--keep-project",
        action="store_true",
        help="Keep the test project directory after benchmarking"
    )
    parser.add_argument(
        "--t1-image",
        type=Path,
        help="Path to T1 NIfTI image (overrides config)"
    )
    parser.add_argument(
        "--t2-image",
        type=Path,
        help="Path to T2 NIfTI image (optional, overrides config)"
    )
    parser.add_argument(
        "--subject-id",
        type=str,
        help="Subject identifier (overrides config, default: extracted from filename)"
    )
    parser.add_argument(
        "--charm-script",
        type=Path,
        help="Path to charm.sh script (overrides config)"
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Run in summary mode instead of debug mode (less verbose)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = BenchmarkConfig(args.config)
    
    # Merge config with command-line arguments
    merged_config = merge_config_with_args(config, args, 'charm')
    
    # Extract values from merged config
    project_dir = Path(merged_config.get('project_dir'))
    output_dir = Path(merged_config.get('output_dir'))
    t1_image = Path(merged_config.get('t1_image'))
    t2_image_str = merged_config.get('t2_image')
    t2_image = Path(t2_image_str) if t2_image_str else None
    charm_script = Path(merged_config.get('charm_script'))
    clean = merged_config.get('clean', False)
    keep_project = merged_config.get('keep_project', False)
    debug_mode = merged_config.get('debug_mode', True)
    
    # Get or extract subject ID
    subject_id = merged_config.get('subject_id')
    if not subject_id:
        # Try to extract from T1 filename (e.g., sub-101_T1w.nii.gz -> 101)
        t1_name = t1_image.stem.replace('.nii', '')  # Remove .nii from .nii.gz
        if 'sub-' in t1_name:
            subject_id = t1_name.split('sub-')[1].split('_')[0]
        else:
            subject_id = "subject"
    
    # Validate paths
    if not t1_image.exists():
        print(f"Error: T1 image not found: {t1_image}")
        print(f"Please provide a valid path to a T1 NIfTI image")
        sys.exit(1)
    
    if not charm_script.exists():
        print(f"Error: charm.sh script not found: {charm_script}")
        sys.exit(1)
    
    # Check if charm is available
    if not check_charm_available():
        print("Error: SimNIBS charm is not installed or not in PATH")
        print("Please install SimNIBS before running this benchmark")
        sys.exit(1)
    
    # Create log file
    log_file = create_benchmark_log_file(
        benchmark_name="charm",
        output_dir=output_dir,
        subject_id=subject_id
    )
    
    # Create logger
    logger = BenchmarkLogger(
        name="charm_benchmark",
        log_file=log_file,
        debug_mode=debug_mode,
        console_output=True
    )
    
    logger.header("TI-TOOLBOX CHARM BENCHMARK")
    logger.info("")
    logger.info("Configuration:")
    if args.config:
        logger.info(f"  Config File: {args.config}")
    logger.info(f"  Project Directory: {project_dir}")
    logger.info(f"  Output Directory: {output_dir}")
    logger.info(f"  Log File: {log_file}")
    logger.info(f"  T1 Image: {t1_image}")
    logger.info(f"  T2 Image: {t2_image if t2_image else 'Not provided'}")
    logger.info(f"  Subject ID: {subject_id}")
    logger.info(f"  Charm Script: {charm_script}")
    logger.info(f"  Clean Run: {clean}")
    logger.info(f"  Keep Project: {keep_project}")
    logger.info(f"  Debug Mode: {debug_mode}")
    logger.info("")
    
    try:
        # Setup test project
        subject_dir, subject_id = setup_test_project(
            project_dir,
            t1_image,
            t2_image,
            subject_id,
            logger
        )
        
        # Run benchmark
        run_charm_benchmark(
            subject_dir=subject_dir,
            charm_script=charm_script,
            output_dir=output_dir,
            logger=logger,
            clean=clean,
            debug_mode=debug_mode
        )
        
        logger.info("")
        logger.info("Benchmark completed successfully!")
        logger.info(f"Results saved to: {output_dir}")
        logger.info(f"Log file: {log_file}")
        
    except KeyboardInterrupt:
        logger.warning("")
        logger.warning("Benchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("")
        logger.error(f"Benchmark failed: {e}")
        import traceback
        for line in traceback.format_exc().split('\n'):
            if line:
                logger.error(line)
        sys.exit(1)
    finally:
        # Cleanup
        if not keep_project:
            # In container, we need to clean both /mnt path and potentially the original path
            cleanup_paths = []
            if os.path.exists("/mnt"):
                mnt_path = Path("/mnt") / project_dir.name
                if mnt_path.exists():
                    cleanup_paths.append(mnt_path)
            if project_dir.exists():
                cleanup_paths.append(project_dir)
            
            for cleanup_path in cleanup_paths:
                logger.info(f"Removing test project directory: {cleanup_path}")
                try:
                    shutil.rmtree(cleanup_path)
                except Exception as e:
                    logger.warning(f"Failed to remove project directory: {e}")


if __name__ == "__main__":
    main()

