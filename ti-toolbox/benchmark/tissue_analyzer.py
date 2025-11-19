#!/usr/bin/env python3
"""
Tissue Analyzer Benchmark - Tissue volume and thickness analysis

Benchmarks tissue analysis performance for CSF, bone, and skin tissues.

Usage:
  python -m benchmark.tissue_analyzer --config benchmark_config.yaml
  python -m benchmark.tissue_analyzer --nifti-path /path/to/Labeling.nii.gz
"""

import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime
import argparse
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from benchmark.config import BenchmarkConfig, merge_config_with_args


def run_tissue_analysis(nifti_path: Path, tissue_type: str, output_dir: Path, 
                       tissue_script: Path, logger, debug_mode=True):
    """Run tissue analysis and benchmark performance."""
    
    metadata = {
        "nifti_path": str(nifti_path),
        "tissue_type": tissue_type,
        "output_dir": str(output_dir),
        "debug_mode": debug_mode
    }
    
    timer = BenchmarkTimer(f"tissue_analysis_{tissue_type}", metadata=metadata)
    timer.start()
    
    try:
        env = os.environ.copy()
        env['DEBUG_MODE'] = 'true' if debug_mode else 'false'
        
        # Build command - use simnibs_python to run tissue_analyzer.py
        cmd = [
            "simnibs_python",
            str(tissue_script),
            str(nifti_path),
            "--tissue", tissue_type,
            "--output", str(output_dir / f"{tissue_type}_analysis")
        ]
        
        logger.info(f"Running tissue analysis for: {tissue_type}")
        logger.info(f"Input: {nifti_path}")
        logger.info(f"Output: {output_dir / f'{tissue_type}_analysis'}")
        
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
        result.metadata['output_directory'] = str(output_dir / f"{tissue_type}_analysis")
        
        return result
        
    except Exception as e:
        logger.error(f"Tissue analysis failed: {e}")
        return timer.stop(success=False, error_message=str(e))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark tissue analyzer")
    parser.add_argument("--config", type=Path, help="Configuration file")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--nifti-path", type=Path, help="Path to segmented NIfTI file (Labeling.nii.gz)")
    parser.add_argument("--subject-id", type=str)
    parser.add_argument("--tissue-script", type=Path, help="Path to tissue_analyzer.py")
    parser.add_argument("--tissues", type=str, help="Comma-separated tissue types (csf,bone,skin)")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'tissue_analyzer')
    
    # Extract configuration
    project_dir = Path(merged.get('project_dir', '.'))
    output_dir = Path(merged['output_dir'])
    nifti_path = Path(merged['nifti_path'])
    subject_id = str(merged.get('subject_id', 'unknown'))
    tissue_script = Path(merged.get('tissue_script', 
                                    '/development/ti-toolbox/ti-toolbox/tools/tissue_analyzer.py'))
    debug_mode = merged.get('debug_mode', True)
    
    # Parse tissue types
    if args.tissues:
        tissue_types = [t.strip() for t in args.tissues.split(",")]
    else:
        tissue_types = merged.get('tissues', ['csf', 'bone', 'skin'])
    
    # Validate paths
    if not nifti_path.exists():
        print(f"Error: NIfTI file not found: {nifti_path}")
        sys.exit(1)
    if not tissue_script.exists():
        print(f"Error: tissue_analyzer.py script not found: {tissue_script}")
        sys.exit(1)
    
    # Setup logging
    log_file = create_benchmark_log_file("tissue_analyzer", output_dir, subject_id)
    logger = BenchmarkLogger("tissue_analyzer_benchmark", log_file, debug_mode, True)
    
    logger.header("TISSUE ANALYZER BENCHMARK")
    logger.info(f"NIfTI file: {nifti_path}")
    logger.info(f"Tissue types: {tissue_types}")
    logger.info(f"Subject ID: {subject_id}")

    try:
        print_hardware_info()
        
        all_results = []
        for tissue_type in tissue_types:
            logger.separator("=", 70)
            logger.info(f"Running: tissue type = {tissue_type}")
            logger.separator("=", 70)
            
            result = run_tissue_analysis(
                nifti_path, tissue_type, output_dir, tissue_script, logger, debug_mode
            )
            
            all_results.append(result)
            print_benchmark_result(result)
            
            # Save individual result
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            result_file = output_dir / f"tissue_analyzer_benchmark_{subject_id}_{tissue_type}_{timestamp}.json"
            save_benchmark_result(result, result_file)
        
        # Save summary
        summary = {
            "subject_id": subject_id,
            "nifti_path": str(nifti_path),
            "tissue_types": tissue_types,
            "results": [
                {
                    "tissue_type": tt,
                    "duration_seconds": r.duration_seconds,
                    "duration_formatted": r.duration_formatted,
                    "success": r.success
                }
                for tt, r in zip(tissue_types, all_results)
            ]
        }
        
        summary_file = output_dir / f"tissue_analyzer_benchmark_{subject_id}_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)
        
        logger.separator("=", 70)
        logger.info("BENCHMARK SUMMARY")
        logger.separator("=", 70)
        for tt, r in zip(tissue_types, all_results):
            status = "SUCCESS" if r.success else "FAILED"
            logger.info(f"{tt.upper()}: {r.duration_formatted} - {status}")
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

