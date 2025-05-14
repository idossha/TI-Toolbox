#!/usr/bin/env python3

"""
Main Analyzer Script

This script provides a unified interface for analyzing both mesh and voxel-based
neuroimaging data. It supports both spherical ROI analysis and cortical analysis
using different atlas types.

Example Usage:
    # For mesh-based spherical analysis:
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --field_path field.msh \
        --space mesh \
        --analysis_type spherical \
        --coordinates 10 20 30 \
        --radius 5 \
        --field_name normE

    # For mesh-based cortical analysis (single region):
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --field_path field.msh \
        --space mesh \
        --analysis_type cortical \
        --atlas_name DK40 \
        --region superiorfrontal \
        --field_name normE

    # For mesh-based cortical analysis (whole head):
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --field_path field.msh \
        --space mesh \
        --analysis_type cortical \
        --atlas_name DK40 \
        --whole_head \
        --field_name normE

    # For voxel-based spherical analysis:
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --field_path field.nii.gz \
        --space voxel \
        --analysis_type spherical \
        --coordinates 10 20 30 \
        --radius 5

    # For voxel-based cortical analysis (single region):
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --field_path field.nii.gz \
        --space voxel \
        --analysis_type cortical \
        --atlas_path atlas.nii.gz \
        --region Left-Hippocampus

    # For voxel-based cortical analysis (whole head):
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --field_path field.nii.gz \
        --space voxel \
        --analysis_type cortical \
        --atlas_path atlas.nii.gz \
        --whole_head
"""

import os
import sys
import argparse
from pathlib import Path
from mesh_analyzer import MeshAnalyzer
from voxel_analyzer import VoxelAnalyzer

def validate_file_extension(file_path, valid_extensions):
    """Validate file extension against a list of valid extensions."""
    # Handle double extensions like .nii.gz
    path = Path(file_path)
    if path.name.endswith('.nii.gz'):
        ext = '.nii.gz'
    else:
        ext = path.suffix.lower()
    
    if ext not in valid_extensions:
        raise ValueError(f"Invalid file extension {ext}. Must be one of: {', '.join(valid_extensions)}")

def validate_coordinates(coords):
    """Validate that coordinates are three numeric values."""
    if len(coords) != 3:
        raise ValueError("Coordinates must be exactly three values (x, y, z)")
    try:
        return [float(c) for c in coords]
    except ValueError:
        raise ValueError("Coordinates must be numeric values")

def validate_radius(radius):
    """Validate that radius is a positive number."""
    try:
        radius_float = float(radius)
        if radius_float <= 0:
            raise ValueError
        return radius_float
    except ValueError:
        raise ValueError("Radius must be a positive number")

def setup_parser():
    """Set up command line argument parser."""
    parser = argparse.ArgumentParser(description="Analyze neuroimaging data in mesh or voxel space")
    
    # Required arguments
    parser.add_argument("--m2m_subject_path", required=True,
                      help="Path to the m2m subject folder")
    parser.add_argument("--field_path", required=True,
                      help="Path to the field file (.msh, .nii, or .nii.gz)")
    parser.add_argument("--space", required=True, choices=['mesh', 'voxel'],
                      help="Analysis space: mesh or voxel")
    parser.add_argument("--analysis_type", required=True, choices=['spherical', 'cortical'],
                      help="Type of analysis to perform")
    
    # Optional arguments based on analysis type
    parser.add_argument("--atlas_name",
                      help="Atlas name for mesh-based cortical analysis (e.g., DK40)")
    parser.add_argument("--atlas_path",
                      help="Path to atlas file for voxel-based cortical analysis")
    parser.add_argument("--coordinates", nargs=3,
                      help="x y z coordinates for spherical analysis")
    parser.add_argument("--radius", type=float,
                      help="Radius for spherical analysis")
    parser.add_argument("--region",
                      help="Region name for cortical analysis (required if not doing whole head analysis)")
    parser.add_argument("--whole_head", action="store_true",
                      help="Analyze the whole head instead of a specific region")
    parser.add_argument("--field_name",
                      help="Field name for mesh analysis (e.g., normE)")
    
    # Additional options
    parser.add_argument("--output_dir", default="analysis_output",
                      help="Directory for output files (default: analysis_output)")
    parser.add_argument("--visualize", action="store_true",
                      help="Generate visualization outputs")
    
    return parser

def validate_args(args):
    """Validate command line arguments based on analysis type and space."""
    # Validate m2m_subject_path exists
    if not os.path.isdir(args.m2m_subject_path):
        raise ValueError(f"m2m subject directory not found: {args.m2m_subject_path}")
    
    # Validate field_path exists and has correct extension
    if not os.path.exists(args.field_path):
        raise ValueError(f"Field file not found: {args.field_path}")
    
    # Validate space-specific requirements
    if args.space == 'mesh':
        validate_file_extension(args.field_path, ['.msh'])
        if not args.field_name:
            raise ValueError("--field_name is required for mesh analysis")
    else:  # voxel
        validate_file_extension(args.field_path, ['.nii', '.nii.gz', '.mgz'])
    
    # Validate analysis-specific arguments
    if args.analysis_type == 'spherical':
        if not args.coordinates:
            raise ValueError("Coordinates are required for spherical analysis")
        if args.radius is None:
            raise ValueError("Radius is required for spherical analysis")
        
        args.coordinates = validate_coordinates(args.coordinates)
        args.radius = validate_radius(args.radius)
        
    else:  # cortical
        if args.space == 'mesh':
            if not args.atlas_name:
                raise ValueError("Atlas name is required for mesh-based cortical analysis")
        else:  # voxel
            if not args.atlas_path:
                raise ValueError("Atlas path is required for voxel-based cortical analysis")
            if not os.path.exists(args.atlas_path):
                raise ValueError(f"Atlas file not found: {args.atlas_path}")
            validate_file_extension(args.atlas_path, ['.nii', '.nii.gz', '.mgz'])
            
        # Validate region specification for cortical analysis
        if not args.whole_head and not args.region:
            raise ValueError("Either --whole_head flag or --region must be specified for cortical analysis")
        if args.whole_head and args.region:
            print("Warning: --region is ignored when --whole_head is specified")

def main():
    """Main function to run the analysis."""
    # Set up and parse arguments
    parser = setup_parser()
    args = parser.parse_args()
    
    try:
        # Validate arguments
        validate_args(args)
        
        # Create output directory
        os.makedirs(args.output_dir, exist_ok=True)
        
        # Initialize appropriate analyzer
        if args.space == 'mesh':
            analyzer = MeshAnalyzer(
                field_mesh_path=args.field_path,
                field_name=args.field_name,
                subject_dir=args.m2m_subject_path,
                output_dir=args.output_dir
            )
        else:  # voxel
            analyzer = VoxelAnalyzer(
                field_nifti=args.field_path,
                subject_dir=args.m2m_subject_path,
                output_dir=args.output_dir
            )
        
        # Perform analysis based on type
        if args.analysis_type == 'spherical':
            results = analyzer.analyze_sphere(
                center_coordinates=args.coordinates,
                radius=args.radius
            )
        else:  # cortical
            if args.whole_head:
                if args.space == 'mesh':
                    results = analyzer.analyze_whole_head(
                        atlas_type=args.atlas_name,
                        visualize=args.visualize
                    )
                else:  # voxel
                    results = analyzer.analyze_whole_head(
                        atlas_file=args.atlas_path,
                        visualize=args.visualize
                    )
            else:  # specific region
                if args.space == 'mesh':
                    results = analyzer.analyze_cortex(
                        atlas_type=args.atlas_name,
                        target_region=args.region,
                        visualize=args.visualize
                    )
                else:  # voxel
                    results = analyzer.analyze_cortex(
                        atlas_file=args.atlas_path,
                        target_region=args.region,
                        visualize=args.visualize
                    )
        
        # Print results summary - standardized to only show mean, max, min values
        print("\nAnalysis Results Summary:")
        print("-" * 50)
        
        # Handle both single region results and whole-head multi-region results
        if isinstance(results, dict) and any(k in results for k in ['mean_value', 'max_value', 'min_value']):
            # Single region results
            print_stat_if_exists(results, 'mean_value', 'Mean Value')
            print_stat_if_exists(results, 'max_value', 'Max Value')
            print_stat_if_exists(results, 'min_value', 'Min Value')
        elif isinstance(results, dict):
            # Whole head results with multiple regions
            print("Multiple region analysis results:")
            for region_name, region_data in results.items():
                if isinstance(region_data, dict) and region_data.get('mean_value') is not None:
                    print(f"\n{region_name}:")
                    print_stat_if_exists(region_data, 'mean_value', 'Mean Value')
                    print_stat_if_exists(region_data, 'max_value', 'Max Value')
                    print_stat_if_exists(region_data, 'min_value', 'Min Value')
    
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)

def print_stat_if_exists(results_dict, key, label):
    """Helper function to print a statistic if it exists in the results."""
    if key in results_dict and results_dict[key] is not None:
        if isinstance(results_dict[key], (int, float)):
            print(f"{label}: {results_dict[key]:.6f}")
        else:
            print(f"{label}: {results_dict[key]}")

if __name__ == "__main__":
    main() 