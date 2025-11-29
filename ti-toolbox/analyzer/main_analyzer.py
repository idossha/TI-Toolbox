#!/usr/bin/env simnibs_python

"""
Main Analyzer Script

This script provides a unified interface for analyzing both mesh and voxel-based
neuroimaging data. It supports both spherical ROI analysis and cortical analysis
using different atlas types.

Example Usage:
    # For mesh-based spherical analysis:
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --montage_name montage_name \
        --space mesh \
        --analysis_type spherical \
        --coordinates 10 20 30 \
        --radius 5

    # For mesh-based cortical analysis (single region):
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --montage_name montage_name \
        --space mesh \
        --analysis_type cortical \
        --atlas_name DK40 \
        --region superiorfrontal

    # For mesh-based cortical analysis (whole head):
    python main_analyzer.py \
        --m2m_subject_path /path/to/m2m_folder \
        --montage_name montage_name \
        --space mesh \
        --analysis_type cortical \
        --atlas_name DK40 \
        --whole_head

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

# Standard library imports
import argparse
import functools
import logging
import math
import os
import sys
import time
from pathlib import Path

# SIMNIBS imports (with fallback for MNI coordinate transformation)
try:
    from simnibs import mni2subject_coords
except ImportError:
    mni2subject_coords = None

# Local imports
from mesh_analyzer import MeshAnalyzer
from voxel_analyzer import VoxelAnalyzer

# Global variables for summary mode and timing
SUMMARY_MODE = False
_start_times = {}
_analysis_start_time = None

# Initialize a default logger for module-level functions
logger = logging.getLogger('analyzer')
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    # Add a console handler if no handlers exist
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Force unbuffered output for real-time GUI updates
try:
    # Try to reconfigure for line buffering if available (Python 3.7+)
    stdout_reconfigure = getattr(sys.stdout, 'reconfigure', None)
    stderr_reconfigure = getattr(sys.stderr, 'reconfigure', None)
    if stdout_reconfigure and stderr_reconfigure:
        stdout_reconfigure(line_buffering=True)
        stderr_reconfigure(line_buffering=True)
    else:
        raise AttributeError("reconfigure not available")
except (AttributeError, OSError):
    # For Python < 3.7 or when reconfigure is not available, use this approach
    original_stdout_write = sys.stdout.write
    original_stderr_write = sys.stderr.write
    
    def flushing_stdout_write(text):
        result = original_stdout_write(text)
        sys.stdout.flush()
        return result
    
    def flushing_stderr_write(text):
        result = original_stderr_write(text)
        sys.stderr.flush()
        return result
    
    sys.stdout.write = flushing_stdout_write
    sys.stderr.write = flushing_stderr_write

# Add the parent directory to the path to access tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from tools import logging_util

def flush_output():
    """Force flush stdout and stderr for real-time GUI updates."""
    try:
        sys.stdout.flush()
    except:
        pass
    
    try:
        sys.stderr.flush()
    except:
        pass

def format_duration(total_seconds):
    """Format duration in human-readable format."""
    total_seconds = int(total_seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"

def log_analysis_start(analysis_type, subject_id, roi_description):
    """Log the start of analysis for a subject."""
    global _analysis_start_time, SUMMARY_MODE
    _analysis_start_time = time.time()
    
    if SUMMARY_MODE:
        print(f"Beginning analysis for subject: {subject_id} ({roi_description})")
    else:
        logger.info(f"Beginning analysis for subject: {subject_id} ({roi_description})")

def log_analysis_complete(analysis_type, subject_id, results_summary="", output_path=""):
    """Log the completion of analysis for a subject."""
    global _analysis_start_time, SUMMARY_MODE
    
    if _analysis_start_time is not None:
        total_duration = time.time() - _analysis_start_time
        duration_str = format_duration(total_duration)
        
        if SUMMARY_MODE:
            if results_summary:
                print(f"└─ Analysis completed successfully for subject: {subject_id} ({results_summary}, Total: {duration_str})")
            else:
                print(f"└─ Analysis completed successfully for subject: {subject_id} (Total: {duration_str})")
            if output_path:
                # Show relative path from /mnt/ for cleaner display
                display_path = output_path.replace('/mnt/', '') if output_path.startswith('/mnt/') else output_path
                print(f"   Results saved to: {display_path}")
        else:
            logger.info(f"Analysis completed successfully for subject: {subject_id} (Total: {duration_str})")

def log_analysis_failed(analysis_type, subject_id, error_msg):
    """Log the failure of analysis for a subject."""
    global _analysis_start_time, SUMMARY_MODE
    
    if _analysis_start_time is not None:
        total_duration = time.time() - _analysis_start_time
        duration_str = format_duration(total_duration)
        
        if SUMMARY_MODE:
            print(f"└─ Analysis failed for subject: {subject_id} ({duration_str}) - {error_msg}")
        else:
            logger.error(f"Analysis failed for subject: {subject_id} ({duration_str}) - {error_msg}")

def log_analysis_step_start(step_name, subject_id):
    """Log the start of an analysis step."""
    global _start_times, SUMMARY_MODE
    
    step_key = f"{subject_id}_{step_name}"
    _start_times[step_key] = time.time()
    
    if SUMMARY_MODE:
        print(f"├─ {step_name}: Started")
    else:
        logger.info(f"{step_name}: Started")

def log_analysis_step_complete(step_name, subject_id, step_details=""):
    """Log the completion of an analysis step."""
    global _start_times, SUMMARY_MODE
    
    step_key = f"{subject_id}_{step_name}"
    if step_key in _start_times:
        duration = time.time() - _start_times[step_key]
        duration_str = format_duration(duration)
        
        if SUMMARY_MODE:
            if step_details:
                print(f"├─ {step_name}: ✓ Complete ({duration_str}) - {step_details}")
            else:
                print(f"├─ {step_name}: ✓ Complete ({duration_str})")
        else:
            logger.info(f"{step_name}: Complete ({duration_str})")
        
        # Clean up timing
        del _start_times[step_key]

def log_analysis_step_failed(step_name, subject_id, error_msg):
    """Log the failure of an analysis step."""
    global _start_times, SUMMARY_MODE
    
    step_key = f"{subject_id}_{step_name}"
    if step_key in _start_times:
        duration = time.time() - _start_times[step_key]
        duration_str = format_duration(duration)
        
        if SUMMARY_MODE:
            print(f"├─ {step_name}: ✗ Failed ({duration_str}) - {error_msg}")
        else:
            logger.error(f"{step_name}: Failed ({duration_str}) - {error_msg}")
        
        # Clean up timing
        del _start_times[step_key]

def create_roi_description(args):
    """Create a human-readable ROI description for summary logging."""
    if args.analysis_type == 'spherical':
        coords = args.coordinates
        formatted_coords = [f"{c:.2f}" for c in coords]
        return f"Spherical: ({formatted_coords[0]},{formatted_coords[1]},{formatted_coords[2]}) r{args.radius}mm"
    elif args.analysis_type == 'cortical':
        if args.whole_head:
            if args.space == 'mesh':
                return f"Cortical: {args.atlas_name} (whole head)"
            else:
                atlas_name = os.path.basename(args.atlas_path) if args.atlas_path else "atlas"
                return f"Cortical: {atlas_name} (whole head)"
        else:
            if args.space == 'mesh':
                return f"Cortical: {args.atlas_name}.{args.region}"
            else:
                atlas_name = os.path.basename(args.atlas_path) if args.atlas_path else "atlas"
                return f"Cortical: {atlas_name}.{args.region}"
    return "Analysis"

def validate_file_extension(file_path, valid_extensions):
    """Validate file extension against a list of valid extensions."""
    # Handle double extensions like .nii.gz
    path = Path(file_path)
    if path.name.lower().endswith('.nii.gz'):
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
    except (ValueError, TypeError):
        raise ValueError("Coordinates must be numeric values")

def validate_radius(radius):
    """Validate that radius is a positive number."""
    try:
        radius_float = float(radius)
        if radius_float <= 0:
            raise ValueError
        return radius_float
    except (ValueError, TypeError):
        raise ValueError("Radius must be a positive number")

def construct_mesh_field_path(m2m_subject_path, montage_name):
    """Construct the mesh field path using the exact montage directory name provided."""
    # Extract subject ID from m2m_subject_path, preserving underscores (e.g., m2m_ernie_extended -> ernie_extended)
    base_name = os.path.basename(m2m_subject_path)
    subject_id = base_name[4:] if base_name.startswith('m2m_') else base_name
    
    # Navigate up to find the project directory
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(m2m_subject_path))))
    if not project_dir.startswith('/mnt/'):
        project_dir = f"/mnt/{os.path.basename(project_dir)}"
    
    # Check if mTI directory exists - if yes, this is an mTI simulation
    mti_mesh_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                                'Simulations', montage_name, 'mTI', 'mesh')
    ti_mesh_dir = os.path.join(project_dir, 'derivatives', 'SimNIBS', f'sub-{subject_id}', 
                               'Simulations', montage_name, 'TI', 'mesh')
    
    # Determine if this is an mTI or TI simulation
    is_mti = os.path.exists(mti_mesh_dir)
    
    if is_mti:
        # For mTI simulations, look in mTI/mesh directory for _mTI.msh files
        mesh_dir = mti_mesh_dir
        possible_filenames = []
        
        # Pattern 1: Use montage directory name + _mTI.msh
        possible_filenames.append(f'{montage_name}_mTI.msh')
        
        # Pattern 2: Check for variations with _mTI suffix
        if '_mTINormal' in montage_name:
            possible_filenames.append(f'{montage_name}_mTI.msh')
        
        # Pattern 3: Standard pattern where we remove any _mTI-related suffix from montage name
        if montage_name.endswith('_mTINormal'):
            base_name = montage_name.replace('_mTINormal', '')
            possible_filenames.append(f'{base_name}_mTI.msh')
        elif montage_name.endswith('Normal'):
            base_name = montage_name.replace('Normal', '')
            possible_filenames.append(f'{base_name}_mTI.msh')
    else:
        # For regular TI simulations, use the original logic
        mesh_dir = ti_mesh_dir
        possible_filenames = []
        
        # Pattern 1: Use montage directory name + _TI.msh
        possible_filenames.append(f'{montage_name}_TI.msh')
        
        # Pattern 2: If montage dir has _TINormal, the file might be montage_dir + _TI.msh
        # (This handles the case where directory is ernie_sphere_5mm_max_TINormal and file is ernie_sphere_5mm_max_TINormal_TI.msh)
        if '_TINormal' in montage_name:
            possible_filenames.append(f'{montage_name}_TI.msh')  # Already added above, but keep for clarity
        
        # Pattern 3: Standard pattern where we remove any _TI-related suffix from montage name
        if montage_name.endswith('_TINormal'):
            base_name = montage_name.replace('_TINormal', '')
            possible_filenames.append(f'{base_name}_TI.msh')
        elif montage_name.endswith('Normal'):
            base_name = montage_name.replace('Normal', '')
            possible_filenames.append(f'{base_name}_TI.msh')

        # Pattern 4: Some exports use *_normal.msh rather than *_TI.msh
        possible_filenames.append(f'{montage_name}_normal.msh')
        if montage_name.endswith('_Normal'):
            base_name = montage_name[:-7]
            possible_filenames.append(f'{base_name}_normal.msh')
    
    # Remove duplicates while preserving order
    seen = set()
    unique_filenames = []
    for filename in possible_filenames:
        if filename not in seen:
            seen.add(filename)
            unique_filenames.append(filename)
    
    # Check which file actually exists
    for filename in unique_filenames:
        field_path = os.path.join(mesh_dir, filename)
        if os.path.exists(field_path):
            return field_path
    
    # Fallback: pick the first .msh file in the directory if available
    try:
        for fname in sorted(os.listdir(mesh_dir)):
            if fname.lower().endswith('.msh'):
                return os.path.join(mesh_dir, fname)
    except Exception:
        pass

    # If no file found, return the first pattern for error reporting
    suffix = '_mTI.msh' if is_mti else '_TI.msh'
    return os.path.join(mesh_dir, unique_filenames[0] if unique_filenames else f'{montage_name}{suffix}')

def setup_parser():
    """Set up command line argument parser."""
    parser = argparse.ArgumentParser(description="Analyze neuroimaging data in mesh or voxel space")
    
    # Required arguments
    parser.add_argument("--m2m_subject_path", required=True,
                      help="Path to the m2m subject folder")
    parser.add_argument("--space", required=True, choices=['mesh', 'voxel'],
                      help="Analysis space: mesh or voxel")
    parser.add_argument("--analysis_type", required=True, choices=['spherical', 'cortical'],
                      help="Type of analysis to perform")
    
    # Field/montage specification - different for mesh vs voxel
    parser.add_argument("--montage_name",
                      help="Montage name for mesh analysis (field path will be auto-constructed)")
    parser.add_argument("--field_path",
                      help="Path to the field file (.nii, .nii.gz, .mgz) for voxel analysis")
    
    # Optional arguments based on analysis type
    parser.add_argument("--atlas_name",
                      help="Atlas name for mesh-based cortical analysis (e.g., DK40)")
    parser.add_argument("--atlas_path",
                      help="Path to atlas file for voxel-based cortical analysis")
    parser.add_argument("--coordinates", nargs=3,
                      help="x y z coordinates for spherical analysis")
    parser.add_argument("--use-mni-coords", action="store_true",
                      help="Treat coordinates as MNI space and transform to subject's native space")
    parser.add_argument("--radius", type=float,
                      help="Radius for spherical analysis")
    parser.add_argument("--region",
                      help="Region name for cortical analysis (required if not doing whole head analysis)")
    parser.add_argument("--whole_head", action="store_true",
                      help="Analyze the whole head instead of a specific region")
    
    # Additional options
    parser.add_argument("--output_dir", default="analysis_output",
                      help="Directory for output files (default: analysis_output)")
    parser.add_argument("--visualize", action="store_true",
                      help="Generate visualization outputs")
    parser.add_argument("--log_file",
                      help="Path to centralized log file (for group analysis integration)")
    parser.add_argument("--quiet", action="store_true",
                      help="Enable summary mode for clean output (non-debug mode)")
    
    return parser

def validate_args(args):
    """Validate command line arguments based on analysis type and space."""
    # Validate m2m_subject_path exists
    if not os.path.isdir(args.m2m_subject_path):
        logger.error(f"m2m subject directory not found: {args.m2m_subject_path}")
        raise ValueError(f"m2m subject directory not found: {args.m2m_subject_path}")
    
    # Validate space-specific requirements
    if args.space == 'mesh':
        # Prefer explicitly provided field_path if valid, otherwise construct from montage_name
        if args.field_path and os.path.exists(args.field_path):
            validate_file_extension(args.field_path, ['.msh'])
        else:
            if not args.montage_name:
                logger.error("--montage_name is required for mesh analysis when --field_path is not provided")
                raise ValueError("--montage_name is required for mesh analysis when --field_path is not provided")
            # Construct and validate mesh field path
            args.field_path = construct_mesh_field_path(args.m2m_subject_path, args.montage_name)
            if not os.path.exists(args.field_path):
                logger.error(f"Constructed mesh field file not found: {args.field_path}")
                raise ValueError(f"Constructed mesh field file not found: {args.field_path}")
            validate_file_extension(args.field_path, ['.msh'])
        
    else:  # voxel
        if not args.field_path:
            logger.error("--field_path is required for voxel analysis")
            raise ValueError("--field_path is required for voxel analysis")
        
        if not os.path.exists(args.field_path):
            logger.error(f"Field file not found: {args.field_path}")
            raise ValueError(f"Field file not found: {args.field_path}")
        
        validate_file_extension(args.field_path, ['.nii', '.nii.gz', '.mgz'])
    
    # Validate analysis-specific arguments
    if args.analysis_type == 'spherical':
        if not args.coordinates:
            logger.error("Coordinates are required for spherical analysis")
            raise ValueError("Coordinates are required for spherical analysis")
        if args.radius is None:
            logger.error("Radius is required for spherical analysis")
            raise ValueError("Radius is required for spherical analysis")
        
        args.coordinates = validate_coordinates(args.coordinates)
        args.radius = validate_radius(args.radius)
        
    else:  # cortical
        if args.space == 'mesh':
            if not args.atlas_name:
                logger.error("Atlas name is required for mesh-based cortical analysis")
                raise ValueError("Atlas name is required for mesh-based cortical analysis")
        else:  # voxel
            if not args.atlas_path:
                logger.error("Atlas path is required for voxel-based cortical analysis")
                raise ValueError("Atlas path is required for voxel-based cortical analysis")
            if not os.path.exists(args.atlas_path):
                logger.error(f"Atlas file not found: {args.atlas_path}")
                raise ValueError(f"Atlas file not found: {args.atlas_path}")
            validate_file_extension(args.atlas_path, ['.nii', '.nii.gz', '.mgz'])
            
        # Validate region specification for cortical analysis
        if not args.whole_head and not args.region:
            logger.error("Either --whole_head flag or --region must be specified for cortical analysis")
            raise ValueError("Either --whole_head flag or --region must be specified for cortical analysis")
        if args.whole_head and args.region:
            logger.warning("Warning: --region is ignored when --whole_head is specified")
        
    logger.debug(f"  Atlas name: {getattr(args, 'atlas_name', None)}")
    logger.debug(f"  Atlas path: {getattr(args, 'atlas_path', None)}")
    logger.debug(f"  Coordinates: {getattr(args, 'coordinates', None)}")
    logger.debug(f"  Radius: {getattr(args, 'radius', None)}")
    logger.debug(f"  Region: {getattr(args, 'region', None)}")
    logger.debug(f"  Whole head: {getattr(args, 'whole_head', None)}")

def main():
    """Main function to run the analysis."""
    # Set up and parse arguments
    parser = setup_parser()
    args = parser.parse_args()
    
    try:
        # Initialize logger after creating output directory
        time_stamp = time.strftime('%Y%m%d_%H%M%S')
        
        # Extract subject ID from m2m_subject_path (e.g., m2m_subject -> subject)
        subject_id = os.path.basename(args.m2m_subject_path).split('_')[1] if '_' in os.path.basename(args.m2m_subject_path) else os.path.basename(args.m2m_subject_path)
        
        # Set up summary mode if requested
        if args.quiet:
            global SUMMARY_MODE
            SUMMARY_MODE = True
        
        # Set up logging - use centralized log file if provided, otherwise use subject-specific
        global logger
        if args.log_file:
            # Use centralized log file for group analysis
            logger = logging_util.get_logger('analyzer', args.log_file, overwrite=False)
            logger.info(f"=== Subject {subject_id} Analysis Started ===")
            flush_output()
        else:
            # Use default subject-specific logging
            # Get project directory from m2m_subject_path
            project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(args.m2m_subject_path))))  # Go up four levels from m2m_subject
            if not project_dir.startswith('/mnt/'):
                project_dir = f"/mnt/{os.path.basename(project_dir)}"
            
            # Create derivatives/ti-toolbox/logs/sub-* directory structure
            log_dir = os.path.join(project_dir, 'derivatives', 'ti-toolbox', 'logs', f'sub-{subject_id}')
            os.makedirs(log_dir, exist_ok=True)
            
            # Create log file in the new directory
            log_file = os.path.join(log_dir, f'analyzer_{time_stamp}.log')
            logger = logging_util.get_logger('analyzer', log_file, overwrite=True)
        
        logger.debug(f"Output directory created: {args.output_dir}")
        flush_output()
        
        # Validate arguments
        validate_args(args)
        logger.debug("Arguments validated successfully")
        flush_output()

        # Transform MNI coordinates to subject space if requested
        if hasattr(args, 'use_mni_coords') and args.use_mni_coords and args.analysis_type == 'spherical':
            if mni2subject_coords is None:
                raise RuntimeError("MNI coordinate transformation requested but simnibs.mni2subject_coords is not available. Please install simnibs.")

            formatted_orig_coords = [f"{float(c):.2f}" for c in args.coordinates]
            logger.info(f"Transforming MNI coordinates [{', '.join(formatted_orig_coords)}] to subject {subject_id} space")
            flush_output()

            try:
                mni_coords = [float(c) for c in args.coordinates]
                subject_coords = mni2subject_coords(mni_coords, args.m2m_subject_path)

                # Validate transformation result
                if subject_coords is None or len(subject_coords) != 3:
                    raise ValueError(f"MNI transformation failed: returned {subject_coords}")

                # Ensure all coordinates are valid finite numbers
                for i, c in enumerate(subject_coords):
                    if c is None or not math.isfinite(float(c)):
                        raise ValueError(f"Invalid coordinate {i}: {c}")

                args.coordinates = subject_coords
                formatted_coords = [f"{c:.2f}" for c in subject_coords]
                logger.info(f"Transformed MNI coordinates for {subject_id}: [{', '.join(formatted_coords)}]")
                flush_output()
            except Exception as e:
                logger.error(f"MNI transformation failed for {subject_id}: {e}")
                raise RuntimeError(f"Failed to transform MNI coordinates: {e}")
        
        # Start summary logging if in quiet mode
        roi_description = create_roi_description(args)
        if args.quiet:
            log_analysis_start(args.analysis_type, subject_id, roi_description)
        
        # Hardcode field name to TI_max
        field_name = "TI_max"
        # Determine field name based on simulation type
        # mTI uses "TI_Max" while regular TI uses "TI_max"
        if args.space == 'mesh' and 'mTI' in args.field_path:
            field_name = "TI_Max"  # mTI simulations use capital M
        else:
            field_name = "TI_max"  # Regular TI simulations use lowercase m
        
        # Initialize appropriate analyzer
        if args.quiet:
            log_analysis_step_start("Field data loading", subject_id)
        
        if args.space == 'mesh':
            logger.debug("Initializing mesh analyzer...")
            flush_output()
            analyzer = MeshAnalyzer(
                field_mesh_path=args.field_path,
                field_name=field_name,
                subject_dir=args.m2m_subject_path,
                output_dir=args.output_dir,
                logger=logger
            )
            if analyzer is None:
                if args.quiet:
                    log_analysis_step_failed("Field data loading", subject_id, "Failed to initialize mesh analyzer")
                logger.error("Failed to initialize mesh analyzer")
                flush_output()
                raise ValueError("Failed to initialize mesh analyzer")

        else:  # voxel
            logger.debug("Initializing voxel analyzer...")
            flush_output()
            analyzer = VoxelAnalyzer(
                field_nifti=args.field_path,
                subject_dir=args.m2m_subject_path,
                output_dir=args.output_dir,
                logger=logger,
                quiet=args.quiet
            )
            if analyzer is None:
                if args.quiet:
                    log_analysis_step_failed("Field data loading", subject_id, "Failed to initialize voxel analyzer")
                logger.error("Failed to initialize voxel analyzer")
                flush_output()
                raise ValueError("Failed to initialize voxel analyzer")
        
        if args.quiet:
            log_analysis_step_complete("Field data loading", subject_id)

        # Perform analysis based on type
        if args.quiet:
            if args.analysis_type == 'spherical':
                log_analysis_step_start("Spherical Analysis", subject_id)
            else:
                log_analysis_step_start("Cortical Analysis", subject_id)
        
        if args.analysis_type == 'spherical':
            if args.space == 'mesh':
                if not args.quiet:
                    logger.info("Performing spherical analysis on mesh")
                    flush_output()
                # Mesh analyzer 
                results = analyzer.analyze_sphere(
                    center_coordinates=args.coordinates,
                    radius=args.radius,
                    visualize=args.visualize
                )
            else:  # voxel
                # Voxel analyzer 
                if not args.quiet:
                    logger.info("Performing spherical analysis on voxel")
                    flush_output()
                results = analyzer.analyze_sphere(
                    center_coordinates=args.coordinates,
                    radius=args.radius,
                    visualize=args.visualize
                )
        else:  # cortical
            if args.whole_head:
                if args.space == 'mesh':
                    if not args.quiet:
                        logger.info("Performing whole head analysis on mesh")
                        flush_output()
                    results = analyzer.analyze_whole_head(
                        atlas_type=args.atlas_name,
                        visualize=args.visualize
                    )
                else:  # voxel
                    if not args.quiet:
                        logger.info("Performing whole head analysis on voxel")
                        flush_output()
                    results = analyzer.analyze_whole_head(
                        atlas_file=args.atlas_path,
                        visualize=args.visualize
                    )
            else:  # specific region
                if args.space == 'mesh':
                    if not args.quiet:
                        logger.info("Performing region analysis on mesh")
                        flush_output()
                    results = analyzer.analyze_cortex(
                        atlas_type=args.atlas_name,
                        target_region=args.region,
                        visualize=args.visualize
                    )
                else:  # voxel
                    if not args.quiet:
                        logger.info("Performing region analysis on voxel")
                        flush_output()
                    results = analyzer.analyze_cortex(
                        atlas_file=args.atlas_path,
                        target_region=args.region,
                        visualize=args.visualize
                    )
        
        # Complete the analysis step
        if args.quiet:
            if args.analysis_type == 'spherical':
                if isinstance(results, dict) and results.get('voxel_count'):
                    step_details = f"{results['voxel_count']} voxels analyzed"
                    log_analysis_step_complete("Spherical Analysis", subject_id, step_details)
                else:
                    log_analysis_step_complete("Spherical Analysis", subject_id)
            else:
                if isinstance(results, dict):
                    if any(k in results for k in ['mean_value', 'max_value', 'min_value']):
                        # Single region results
                        log_analysis_step_complete("Cortical Analysis", subject_id, "1 region analyzed")
                    else:
                        # Multiple region results
                        valid_regions = len([r for r in results.values() if isinstance(r, dict) and r.get('mean_value') is not None])
                        total_regions = len(results)
                        log_analysis_step_complete("Cortical Analysis", subject_id, f"{valid_regions}/{total_regions} regions processed")
                else:
                    log_analysis_step_complete("Cortical Analysis", subject_id)
        
        # Add results saving step
        if args.quiet:
            log_analysis_step_start("Results saving", subject_id)
        
        # Log completion with summary instead of full results (only in debug mode)
        if not args.quiet:
            if isinstance(results, dict):
                if any(k in results for k in ['mean_value', 'max_value', 'min_value']):
                    # Single region results
                    logger.info("Analysis completed successfully: Single region analysis")
                    flush_output()
                else:
                    # Multiple region results - log count instead of full data
                    valid_regions = len([r for r in results.values() if isinstance(r, dict) and r.get('mean_value') is not None])
                    total_regions = len(results)
                    logger.info(f"Analysis completed successfully: {valid_regions}/{total_regions} regions processed")
                    flush_output()
            else:
                logger.info(f"Analysis completed successfully")
                flush_output()
        
        # Add completion marker for group analysis
        if args.log_file:
            logger.info(f"=== Subject {subject_id} Analysis Completed ===")
            flush_output()
        
        # Handle both single region results and whole-head multi-region results
        if isinstance(results, dict) and any(k in results for k in ['mean_value', 'max_value', 'min_value']):
            # Single region results
            print("\nTI_max Values:")
            print_stat_if_exists(results, 'mean_value', 'Mean Value')
            print_stat_if_exists(results, 'max_value', 'Max Value')
            print_stat_if_exists(results, 'min_value', 'Min Value')
            print_stat_if_exists(results, 'focality', 'Focality')
            
            # Print TI_normal values if available
            if any(k in results for k in ['normal_mean_value', 'normal_max_value', 'normal_min_value']):
                print("\nTI_normal Values:")
                print_stat_if_exists(results, 'normal_mean_value', 'Normal Mean Value')
                print_stat_if_exists(results, 'normal_max_value', 'Normal Max Value')
                print_stat_if_exists(results, 'normal_min_value', 'Normal Min Value')
                print_stat_if_exists(results, 'normal_focality', 'Normal Focality')
            
        elif isinstance(results, dict):
            # Whole head results with multiple regions
            print("Multiple region analysis results:")
            for region_name, region_data in results.items():
                if isinstance(region_data, dict) and region_data.get('mean_value') is not None:
                    print(f"\n{region_name}:")
                    print("  TI_max Values:")
                    print_stat_if_exists(region_data, 'mean_value', 'Mean Value')
                    print_stat_if_exists(region_data, 'max_value', 'Max Value')
                    print_stat_if_exists(region_data, 'min_value', 'Min Value')
                    print_stat_if_exists(region_data, 'focality', 'Focality')
                    
                    # Print TI_normal values if available
                    if any(k in region_data for k in ['normal_mean_value', 'normal_max_value', 'normal_min_value']):
                        print("  TI_normal Values:")
                        print_stat_if_exists(region_data, 'normal_mean_value', '  Normal Mean Value')
                        print_stat_if_exists(region_data, 'normal_max_value', '  Normal Max Value')
                        print_stat_if_exists(region_data, 'normal_min_value', '  Normal Min Value')
                        print_stat_if_exists(region_data, 'normal_focality', '  Normal Focality')
        
        # Complete results saving step and overall analysis
        if args.quiet:
            # Show where results were saved
            display_path = args.output_dir.replace('/mnt/', '') if args.output_dir.startswith('/mnt/') else args.output_dir
            step_details = f"saved to {display_path}"
            log_analysis_step_complete("Results saving", subject_id, step_details)
            
            # Create results summary for final completion message
            results_summary = ""
            if isinstance(results, dict):
                if any(k in results for k in ['mean_value', 'max_value', 'min_value']):
                    # Single region results
                    results_summary = "1 region analyzed"
                else:
                    # Multiple region results
                    valid_regions = len([r for r in results.values() if isinstance(r, dict) and r.get('mean_value') is not None])
                    total_regions = len(results)
                    results_summary = f"{valid_regions}/{total_regions} regions processed"
            
            log_analysis_complete(args.analysis_type, subject_id, results_summary, args.output_dir)
    
    except Exception as e:
        # Handle analysis failure
        if args.quiet:
            log_analysis_failed(args.analysis_type, subject_id, str(e))
        
        logger.error(f"Error: {str(e)}")
        if args.log_file:
            logger.error(f"=== Subject {subject_id} Analysis Failed ===")
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