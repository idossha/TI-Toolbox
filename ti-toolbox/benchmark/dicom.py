#!/usr/bin/env python3
"""
Benchmark script for DICOM to NIfTI conversion.
Tests dcm2niix conversion performance with example data.
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


def setup_dicom_test_project(
    project_dir: Path,
    source_dicom_dir: Path,
    subject_id: str,
    logger: BenchmarkLogger
) -> tuple[Path, str]:
    """
    Set up test project with DICOM data.
    
    Args:
        project_dir: Path to the project directory
        source_dicom_dir: Path to source DICOM files
        subject_id: Subject identifier
        logger: Benchmark logger instance
        
    Returns:
        Tuple of (subject_dir, subject_id)
    """
    logger.info("Setting up DICOM test project...")
    
    bids_subject_id = f"sub-{subject_id}"
    
    # Use the project directory as specified in config
    subject_dir = project_dir / bids_subject_id
    sourcedata_dir = project_dir / "sourcedata" / bids_subject_id
    
    logger.info(f"Using project directory: {project_dir}")
    
    # Create directories
    subject_dir.mkdir(parents=True, exist_ok=True)
    t1_dicom_dir = sourcedata_dir / "T1w" / "dicom"
    t2_dicom_dir = sourcedata_dir / "T2w" / "dicom"
    t1_dicom_dir.mkdir(parents=True, exist_ok=True)
    t2_dicom_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy DICOM files if provided
    if source_dicom_dir and source_dicom_dir.exists():
        logger.info(f"Copying DICOM files from: {source_dicom_dir}")
        for file in source_dicom_dir.glob("*"):
            if file.is_file():
                shutil.copy2(file, t1_dicom_dir)
        logger.info(f"DICOM files copied to: {t1_dicom_dir}")
    else:
        logger.warning("No source DICOM directory provided - will test with empty dirs")
    
    # Create dataset_description.json
    actual_project_dir = subject_dir.parent
    root_dataset_desc = actual_project_dir / "dataset_description.json"
    if not root_dataset_desc.exists():
        root_dataset_desc.write_text("""{
  "Name": "DICOM Conversion Benchmark",
  "BIDSVersion": "1.6.0",
  "DatasetType": "raw"
}
""")
    
    logger.info(f"Test project ready at: {actual_project_dir}")
    logger.info(f"Subject directory: {subject_dir}")
    
    return subject_dir, subject_id


def run_dicom_benchmark(
    subject_dir: Path,
    dicom_script: Path,
    output_dir: Path,
    logger: BenchmarkLogger,
    debug_mode: bool = True
) -> None:
    """
    Run the DICOM conversion benchmark.
    
    Args:
        subject_dir: Path to the subject directory
        dicom_script: Path to the dicom2nifti.sh script
        output_dir: Directory to save benchmark results
        logger: Benchmark logger instance
        debug_mode: Whether to run in debug mode
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    subject_id = subject_dir.name.replace("sub-", "")
    project_dir = subject_dir.parent
    
    metadata = {
        "subject_id": subject_id,
        "subject_dir": str(subject_dir),
        "project_dir": str(project_dir),
        "dicom_script": str(dicom_script),
        "debug_mode": debug_mode
    }
    
    print_hardware_info()
    
    logger.separator()
    logger.info(f"Starting DICOM conversion benchmark for subject: {subject_id}")
    logger.info(f"Using script: {dicom_script}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.separator()
    
    timer = BenchmarkTimer("dicom_to_nifti_conversion", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        cmd = [str(dicom_script), str(subject_dir)]
        logger.info(f"Running command: {' '.join(cmd)}")
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
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        result = timer.stop(success=False, error_message=str(e))
        raise
    
    print_benchmark_result(result)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_file = output_dir / f"dicom_benchmark_{subject_id}_{timestamp}.json"
    save_benchmark_result(result, result_file)
    
    latest_file = output_dir / f"dicom_benchmark_{subject_id}_latest.json"
    save_benchmark_result(result, latest_file)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Benchmark DICOM to NIfTI conversion",
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
    parser.add_argument("--keep-project", action="store_true")
    parser.add_argument("--dicom-source", type=Path, help="Source DICOM directory (overrides config)")
    parser.add_argument("--subject-id", type=str, help="Subject identifier (overrides config, default: dicom)")
    parser.add_argument("--dicom-script", type=Path, help="Path to dicom2nifti.sh (overrides config)")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load configuration
    config = BenchmarkConfig(args.config)
    
    # Merge config with command-line arguments
    merged_config = merge_config_with_args(config, args, 'dicom')
    
    # Extract values from merged config
    project_dir = Path(merged_config.get('project_dir'))
    output_dir = Path(merged_config.get('output_dir'))
    dicom_script = Path(merged_config.get('dicom_script'))
    dicom_source = merged_config.get('dicom_source')
    if dicom_source:
        dicom_source = Path(dicom_source)
    subject_id = merged_config.get('subject_id', 'dicom')
    keep_project = merged_config.get('keep_project', False)
    debug_mode = merged_config.get('debug_mode', True)
    
    if not dicom_script.exists():
        print(f"Error: dicom2nifti.sh not found: {dicom_script}")
        sys.exit(1)
    
    log_file = create_benchmark_log_file("dicom", output_dir, subject_id)
    logger = BenchmarkLogger("dicom_benchmark", log_file, debug_mode, True)
    
    logger.header("DICOM TO NIFTI BENCHMARK")
    if args.config:
        logger.info(f"Config File: {args.config}")
    logger.info(f"Project Directory: {project_dir}")
    logger.info(f"Output Directory: {output_dir}")
    logger.info(f"DICOM Source: {dicom_source}")
    logger.info(f"Subject ID: {subject_id}")
    logger.info(f"Keep Project: {keep_project}")
    logger.info(f"Debug Mode: {debug_mode}")
    
    try:
        subject_dir, subject_id = setup_dicom_test_project(
            project_dir, dicom_source, subject_id, logger
        )
        
        run_dicom_benchmark(
            subject_dir, dicom_script, output_dir, logger, debug_mode
        )
        
        logger.info("Benchmark completed successfully!")
        
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)
    finally:
        if not keep_project:
            if project_dir.exists():
                logger.info(f"Removing test project: {project_dir}")
                try:
                    shutil.rmtree(project_dir)
                except Exception as e:
                    logger.warning(f"Failed to remove: {e}")
        else:
            logger.info(f"Keeping project files at: {project_dir}")


if __name__ == "__main__":
    main()

