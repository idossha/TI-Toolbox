#!/usr/bin/env python3
"""
Voxel Analyzer Benchmark - Volumetric NIfTI-based field analysis

Benchmarks voxel-based field analysis performance for spherical ROI,
cortical region, and whole-head analysis.

Usage:
  python -m tit.benchmark.voxel_analyzer --config benchmark_config.yaml
  python -m tit.benchmark.voxel_analyzer --field-nifti /path/to/field.nii.gz
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import argparse
import json

from tit.benchmark.core import (
    BenchmarkTimer, print_hardware_info, print_benchmark_result, save_benchmark_result
)
from tit.benchmark.logger import BenchmarkLogger, create_benchmark_log_file
from tit.benchmark.config import BenchmarkConfig, merge_config_with_args


def run_voxel_analysis(field_nifti_path: Path, subject_dir: Path, output_dir: Path,
                      analysis_type: str, logger, roi_center=None, roi_radius=None,
                      atlas_file=None, target_region=None, visualize=False, 
                      debug_mode=True):
    """Run voxel-based field analysis and benchmark performance."""
    
    metadata = {
        "field_nifti_path": str(field_nifti_path),
        "subject_dir": str(subject_dir),
        "analysis_type": analysis_type,
        "visualize": visualize,
        "debug_mode": debug_mode
    }
    
    if analysis_type == "sphere":
        metadata.update({
            "roi_center": roi_center,
            "roi_radius": roi_radius
        })
    elif analysis_type == "cortex":
        metadata.update({
            "atlas_file": str(atlas_file),
            "target_region": target_region
        })
    elif analysis_type == "whole_head":
        metadata["atlas_file"] = str(atlas_file)
    
    timer = BenchmarkTimer(f"voxel_analysis_{analysis_type}", metadata=metadata)
    timer.start()
    
    try:
        # Import here to avoid loading heavy dependencies at module level
        from analyzer.voxel_analyzer import VoxelAnalyzer
        
        logger.info(f"Initializing VoxelAnalyzer...")
        # Pass the underlying Python logger to VoxelAnalyzer (it expects a standard logger)
        analyzer = VoxelAnalyzer(
            field_nifti=str(field_nifti_path),
            subject_dir=str(subject_dir),
            output_dir=str(output_dir),
            logger=logger.logger,  # Pass the underlying logger
            quiet=not debug_mode
        )
        
        # Sample periodically during analysis
        timer.sample()
        
        logger.info(f"Running {analysis_type} analysis...")
        
        if analysis_type == "sphere":
            results = analyzer.analyze_sphere(
                center_coordinates=roi_center,
                radius=roi_radius,
                visualize=visualize
            )
        elif analysis_type == "cortex":
            results = analyzer.analyze_cortex(
                atlas_file=str(atlas_file),
                target_region=target_region,
                visualize=visualize
            )
        elif analysis_type == "whole_head":
            results = analyzer.analyze_whole_head(
                atlas_file=str(atlas_file),
                visualize=visualize
            )
        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")
        
        timer.sample()
        
        if results is None:
            raise RuntimeError("Analysis returned no results")
        
        result = timer.stop(success=True)
        result.metadata['analysis_results'] = str(results) if isinstance(results, dict) else "multiple_regions"
        result.metadata['output_directory'] = str(output_dir)
        
        return result
        
    except Exception as e:
        logger.error(f"Voxel analysis failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return timer.stop(success=False, error_message=str(e))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark voxel-based field analyzer")
    parser.add_argument("--config", type=Path, help="Configuration file")
    parser.add_argument("--project-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--field-nifti", type=Path, help="Path to field NIfTI file (.nii.gz)")
    parser.add_argument("--subject-dir", type=Path, help="Path to subject directory")
    parser.add_argument("--subject-id", type=str)
    parser.add_argument("--analysis-type", type=str, choices=['sphere', 'cortex', 'whole_head'],
                       help="Type of analysis to run")
    parser.add_argument("--roi-center", type=str, help="ROI center coordinates (x,y,z)")
    parser.add_argument("--roi-radius", type=float, help="ROI radius in mm")
    parser.add_argument("--atlas-file", type=Path, help="Path to atlas file (.nii.gz or .mgz)")
    parser.add_argument("--target-region", type=str, help="Target region name for cortical analysis")
    parser.add_argument("--visualize", action="store_true", help="Generate visualizations")
    parser.add_argument("--no-debug", action="store_true")
    
    args = parser.parse_args()
    
    # Load and merge configuration
    config = BenchmarkConfig(args.config)
    merged = merge_config_with_args(config, args, 'voxel_analyzer')
    
    # Extract configuration
    project_dir = Path(merged.get('project_dir', '.'))
    output_dir = Path(merged['output_dir'])
    field_nifti_path = Path(merged['field_nifti'])
    subject_dir = Path(merged['subject_dir'])
    subject_id = str(merged.get('subject_id', 'unknown'))
    analysis_type = merged.get('analysis_type', 'sphere')
    debug_mode = merged.get('debug_mode', True)
    visualize = merged.get('visualize', False)
    
    # Analysis-specific parameters
    roi_center = None
    roi_radius = None
    atlas_file = None
    target_region = None
    
    if analysis_type == "sphere":
        roi_center_str = merged.get('roi_center', '0,0,0')
        if isinstance(roi_center_str, str):
            roi_center = [float(x.strip()) for x in roi_center_str.split(',')]
        else:
            roi_center = roi_center_str
        roi_radius = float(merged.get('roi_radius', 10.0))
    elif analysis_type == "cortex":
        atlas_file = Path(merged['atlas_file'])
        target_region = merged.get('target_region', 'Left-Hippocampus')
    elif analysis_type == "whole_head":
        atlas_file = Path(merged['atlas_file'])
    
    # Validate paths
    if not field_nifti_path.exists():
        print(f"Error: Field NIfTI file not found: {field_nifti_path}")
        sys.exit(1)
    if not subject_dir.exists():
        print(f"Error: Subject directory not found: {subject_dir}")
        sys.exit(1)
    if atlas_file and not atlas_file.exists():
        print(f"Error: Atlas file not found: {atlas_file}")
        sys.exit(1)
    
    # Setup logging
    log_file = create_benchmark_log_file("voxel_analyzer", output_dir, subject_id)
    logger = BenchmarkLogger("voxel_analyzer_benchmark", log_file, debug_mode, True)
    
    logger.header("VOXEL ANALYZER BENCHMARK")
    logger.info(f"Field NIfTI: {field_nifti_path}")
    logger.info(f"Subject directory: {subject_dir}")
    logger.info(f"Analysis type: {analysis_type}")
    logger.info(f"Subject ID: {subject_id}")

    try:
        print_hardware_info()
        
        logger.separator("=", 70)
        logger.info(f"Running: {analysis_type} analysis")
        logger.separator("=", 70)
        
        result = run_voxel_analysis(
            field_nifti_path=field_nifti_path,
            subject_dir=subject_dir,
            output_dir=output_dir,
            analysis_type=analysis_type,
            logger=logger,
            roi_center=roi_center,
            roi_radius=roi_radius,
            atlas_file=atlas_file,
            target_region=target_region,
            visualize=visualize,
            debug_mode=debug_mode
        )
        
        print_benchmark_result(result)
        
        # Save result
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_file = output_dir / f"voxel_analyzer_benchmark_{subject_id}_{analysis_type}_{timestamp}.json"
        save_benchmark_result(result, result_file)
        
        latest_file = output_dir / f"voxel_analyzer_benchmark_{subject_id}_{analysis_type}_latest.json"
        save_benchmark_result(result, latest_file)
        
        logger.separator("=", 70)
        logger.info("BENCHMARK COMPLETE")
        logger.separator("=", 70)
        status = "SUCCESS" if result.success else "FAILED"
        logger.info(f"{analysis_type.upper()}: {result.duration_formatted} - {status}")
        logger.info(f"Results: {result_file}")
        
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

