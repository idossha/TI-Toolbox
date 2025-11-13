#!/usr/bin/env python3
"""
DICOM Benchmark - DICOM to NIfTI conversion

Benchmarks dcm2niix conversion performance.

Usage:
  python -m benchmark.dicom --config benchmark_config.yaml
  python -m benchmark.dicom --dicom-source /path/to/dicom/files
"""

import sys
import os
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
import argparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from benchmark.config import BenchmarkConfig, merge_config_with_args


def setup_project(project_dir: Path, dicom_source: Path, subject_id: str, logger):
    """Set up BIDS project with DICOM data."""
    bids_subject_id = f"sub-{subject_id}"
    
    # Detect container and set paths (dicom2nifti.sh expects /mnt paths)
    if os.path.exists("/mnt"):
        mnt_project_dir = Path("/mnt") / project_dir.name
        subject_dir = mnt_project_dir / bids_subject_id
        sourcedata_dir = mnt_project_dir / "sourcedata" / bids_subject_id
        logger.info(f"Container detected - using /mnt path: {mnt_project_dir}")
    else:
        subject_dir = project_dir / bids_subject_id
        sourcedata_dir = project_dir / "sourcedata" / bids_subject_id
    
    # Create directories (subject_dir must exist for dicom2nifti.sh validation)
    subject_dir.mkdir(parents=True, exist_ok=True)
    t1_dicom_dir = sourcedata_dir / "T1w" / "dicom"
    t1_dicom_dir.mkdir(parents=True, exist_ok=True)
    
    # Create dataset_description.json
    dataset_desc = subject_dir.parent / "dataset_description.json"
    if not dataset_desc.exists():
        dataset_desc.write_text('{"Name": "TI-Toolbox DICOM Benchmark", "BIDSVersion": "1.6.0"}')
    
    # Copy DICOM files
    if dicom_source.is_dir():
        dcm_count = 0
        for dcm_file in dicom_source.glob("*"):
            if dcm_file.is_file():
                shutil.copy2(dcm_file, t1_dicom_dir / dcm_file.name)
                dcm_count += 1
        logger.info(f"Copied {dcm_count} DICOM files to {t1_dicom_dir}")
    
    logger.info(f"Project ready: {subject_dir.parent}")
    return subject_dir, subject_id


def run_dicom_conversion(subject_dir: Path, dicom_script: Path, logger, debug_mode=True):
    """Run DICOM to NIfTI conversion."""
    subject_id = subject_dir.name.replace("sub-", "")
    
    metadata = {
        "subject_id": subject_id,
        "dicom_script": str(dicom_script),
        "debug_mode": debug_mode
    }
    
    timer = BenchmarkTimer("dicom_conversion", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        cmd = [str(dicom_script), str(subject_dir)]
        logger.info(f"Running DICOM conversion for: {subject_id}")
        
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
                if line_count % 10 == 0:
                    timer.sample()
        
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, cmd)
        
        result = timer.stop(success=True)
        
        # Add output location to metadata
        anat_dir = subject_dir / "anat"
        result.metadata['nifti_output'] = str(anat_dir)
        
        return result
        
    except Exception as e:
        logger.error(f"DICOM conversion failed: {e}")
        return timer.stop(success=False, error_message=str(e))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark DICOM to NIfTI conversion")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dicom-source", type=Path)
    parser.add_argument("--subject-id", type=str)
    parser.add_argument("--dicom-script", type=Path)
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'dicom')
    
    # Extract configuration
    project_dir = Path(merged['project_dir'])
    output_dir = Path(merged['output_dir'])
    dicom_source = Path(merged['dicom_source'])
    dicom_script = Path(merged['dicom_script'])
    subject_id = merged.get('subject_id', 'benchmark_dicom')
    debug_mode = merged.get('debug_mode', True)
    
    if not dicom_source.exists():
        print(f"Error: DICOM source not found: {dicom_source}")
        sys.exit(1)
    if not dicom_script.exists():
        print(f"Error: dicom2nifti.sh not found: {dicom_script}")
        sys.exit(1)
    
    # Setup logging
    log_file = create_benchmark_log_file("dicom", output_dir, subject_id)
    logger = BenchmarkLogger("dicom_benchmark", log_file, debug_mode, True)
    
    logger.header("DICOM CONVERSION BENCHMARK")
    logger.info(f"DICOM source: {dicom_source}")
    
    try:
        subject_dir, subject_id = setup_project(project_dir, dicom_source, subject_id, logger)
        
        result = run_dicom_conversion(subject_dir, dicom_script, logger, debug_mode)
        
        print_benchmark_result(result)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_dir / f"dicom_benchmark_{subject_id}_{timestamp}.json"
        save_benchmark_result(result, result_file)
        
        latest_file = output_dir / f"dicom_benchmark_{subject_id}_latest.json"
        save_benchmark_result(result, latest_file)
        
        logger.info(f"Results saved: {result_file}")
        
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
