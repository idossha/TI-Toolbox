#!/usr/bin/env python3
"""
Charm Benchmark - SimNIBS head mesh (m2m) creation

Benchmarks the charm preprocessing pipeline with T1/T2 anatomical images.

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

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from benchmark.config import BenchmarkConfig, merge_config_with_args


def setup_project(project_dir: Path, t1_image: Path, t2_image: Path, subject_id: str, logger):
    """Set up BIDS project with T1/T2 images."""
    bids_subject_id = f"sub-{subject_id}"
    
    # Detect container and set paths
    if os.path.exists("/mnt"):
        mnt_project_dir = Path("/mnt") / project_dir.name
        subject_dir = mnt_project_dir / bids_subject_id
    else:
        subject_dir = project_dir / bids_subject_id
    
    # Create BIDS structure
    anat_dir = subject_dir / "anat"
    anat_dir.mkdir(parents=True, exist_ok=True)
    
    (subject_dir.parent / "derivatives" / "SimNIBS" / bids_subject_id).mkdir(parents=True, exist_ok=True)
    
    # Copy images
    shutil.copy2(t1_image, anat_dir / f"{bids_subject_id}_T1w.nii.gz")
    if t2_image and t2_image.exists():
        shutil.copy2(t2_image, anat_dir / f"{bids_subject_id}_T2w.nii.gz")
    
    # Create dataset_description.json
    dataset_desc = subject_dir.parent / "dataset_description.json"
    if not dataset_desc.exists():
        dataset_desc.write_text('{"Name": "TI-Toolbox Benchmark", "BIDSVersion": "1.6.0"}')
    
    logger.info(f"Project ready: {subject_dir.parent}")
    return subject_dir, subject_id


def run_charm(subject_dir: Path, charm_script: Path, logger, debug_mode=True):
    """Run charm and benchmark performance."""
    subject_id = subject_dir.name.replace("sub-", "")
    
    metadata = {
        "subject_id": subject_id,
        "charm_script": str(charm_script),
        "debug_mode": debug_mode
    }
    
    timer = BenchmarkTimer("charm_m2m_creation", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        cmd = [str(charm_script), str(subject_dir)]
        logger.info(f"Running charm for subject: {subject_id}")
        
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
        
        # Add m2m output location to metadata
        m2m_dir = subject_dir.parent / "derivatives" / "SimNIBS" / subject_dir.name / f"m2m_{subject_id}"
        result.metadata['m2m_output'] = str(m2m_dir)
        
        return result
        
    except Exception as e:
        logger.error(f"Charm failed: {e}")
        return timer.stop(success=False, error_message=str(e))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark SimNIBS charm")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--t1-image", type=Path)
    parser.add_argument("--t2-image", type=Path)
    parser.add_argument("--subject-id", type=str)
    parser.add_argument("--charm-script", type=Path)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'charm')
    
    # Extract configuration
    project_dir = Path(merged['project_dir'])
    output_dir = Path(merged['output_dir'])
    t1_image = Path(merged['t1_image'])
    t2_image_str = merged.get('t2_image')
    t2_image = Path(t2_image_str) if t2_image_str else None
    charm_script = Path(merged['charm_script'])
    subject_id = merged.get('subject_id', 'subject')
    debug_mode = merged.get('debug_mode', True)
    
    if not t1_image.exists():
        print(f"Error: T1 image not found: {t1_image}")
        sys.exit(1)
    if not charm_script.exists():
        print(f"Error: charm.sh not found: {charm_script}")
        sys.exit(1)
    
    # Setup logging
    log_file = create_benchmark_log_file("charm", output_dir, subject_id)
    logger = BenchmarkLogger("charm_benchmark", log_file, debug_mode, True)
    
    logger.header("CHARM BENCHMARK")
    logger.info(f"T1: {t1_image}")
    logger.info(f"T2: {t2_image if t2_image else 'Not provided'}")
    
    try:
        subject_dir, subject_id = setup_project(project_dir, t1_image, t2_image, subject_id, logger)
        
        result = run_charm(subject_dir, charm_script, logger, debug_mode)
        
        print_benchmark_result(result)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_dir / f"charm_benchmark_{subject_id}_{timestamp}.json"
        save_benchmark_result(result, result_file)
        
        latest_file = output_dir / f"charm_benchmark_{subject_id}_latest.json"
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
