#!/usr/bin/env simnibs_python

"""
Group Analyzer Script

Each subject's analysis will be saved under:
    derivatives/SimNIBS/<subject_id>/Simulations/<montage_name>/Analyses/<Mesh-or-Voxel>/

Within each subject's Analyses folder, we also capture:
  - overlays & plots (via --visualize)
  - CSV summary  (handled by main_analyzer.py)
  - centralized group analysis log file (all subjects logged together)
"""

import os
import sys
import argparse
import subprocess
import logging
import time
from pathlib import Path
from typing import List, Tuple, Optional

# Global variables for summary mode and timing
SUMMARY_MODE = False
_group_start_time = None

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

def log_group_analysis_start(num_subjects, analysis_description):
    """Log the start of group analysis."""
    global _group_start_time, SUMMARY_MODE
    _group_start_time = time.time()
    
    if SUMMARY_MODE:
        print(f"\nBeginning group analysis for {num_subjects} subjects ({analysis_description})")

def log_group_analysis_complete(num_successful, num_total, output_path=""):
    """Log the completion of group analysis."""
    global _group_start_time, SUMMARY_MODE
    
    if _group_start_time is not None:
        total_duration = time.time() - _group_start_time
        duration_str = format_duration(total_duration)
        
        if SUMMARY_MODE:
            if num_successful == num_total:
                print(f"└─ Group analysis completed ({num_successful}/{num_total} subjects successful, Total: {duration_str})")
            else:
                print(f"└─ Group analysis completed with failures ({num_successful}/{num_total} subjects successful, Total: {duration_str})")
            if output_path:
                # Show relative path from /mnt/ for cleaner display
                display_path = output_path.replace('/mnt/', '') if output_path.startswith('/mnt/') else output_path
                print(f"   Group results saved to: {display_path}")

def log_group_subject_status(subject_id, status, duration_str, error_msg=""):
    """Log the status of a subject in group analysis."""
    global SUMMARY_MODE
    
    if SUMMARY_MODE:
        if status == "complete":
            print(f"├─ Subject {subject_id}: ✓ Complete ({duration_str})")
        else:
            print(f"├─ Subject {subject_id}: ✗ Failed ({duration_str}) - {error_msg}")

# Import SimNIBS for MNI coordinate transformation
try:
    from simnibs import mni2subject_coords
except ImportError:
    mni2subject_coords = None

# Import our comparison functions
try:
    # Try absolute import first (for testing)
    from compare_analyses import run_all_group_comparisons, _extract_project_name, setup_group_logger
except ImportError:
    try:
        # Fallback for relative import (for package usage)
        from .compare_analyses import run_all_group_comparisons, _extract_project_name, setup_group_logger
    except ImportError:
        # If compare_analyses is not available, create dummy functions
        print("Warning: compare_analyses not available. Group comparison functionality will be limited.")
        
        def run_all_group_comparisons(analysis_paths, project_name=None):
            """Dummy function when compare_analyses is not available."""
            return ""
        
        def _extract_project_name(path):
            """Dummy function when compare_analyses is not available."""
            return "unknown_project"
        
        def setup_group_logger(output_dir, project_name):
            """Dummy function when compare_analyses is not available."""
            return None

# Global group logger for centralized logging
group_logger = None

def create_group_output_directory(first_subject_path: str) -> str:
    """
    Create centralized group analysis output directory.
    
    Args:
        first_subject_path (str): Path from the first subject to extract project name
        
    Returns:
        str: Path to the created group analysis directory
    """
    global group_logger
    
    # Extract project name from the first subject's path
    project_name = _extract_project_name(first_subject_path)
    
    # No longer create centralized group analysis directory under SimNIBS
    # Individual subject analyses are stored in their respective subject directories
    # Group comparisons will be stored in the user-specified output directory
    
    if group_logger:
        group_logger.debug(f"Using project: {project_name}")
    
    # Return a placeholder path - not actually used since we don't create central directories
    return f"/mnt/{project_name}/derivatives/SimNIBS"

def setup_parser():
    """Set up command line argument parser."""
    parser = argparse.ArgumentParser(description="Run analysis across multiple subjects and compare results")

    # Analysis parameters (same as main_analyzer.py)
    parser.add_argument("--space", required=True, choices=['mesh', 'voxel'],
                        help="Analysis space: mesh or voxel")
    parser.add_argument("--analysis_type", required=True, choices=['spherical', 'cortical'],
                        help="Type of analysis to perform")

    # Analysis‐specific parameters
    parser.add_argument("--atlas_name",
                        help="Atlas name for mesh-based cortical analysis (e.g., DK40)")
    parser.add_argument("--coordinates", nargs=3,
                        help="x y z coordinates for spherical analysis")
    parser.add_argument("--coordinate-space", choices=['MNI', 'subject'], required=True,
                        help="Coordinate space of the input coordinates (MNI or subject)")
    parser.add_argument("--radius", type=float,
                        help="Radius for spherical analysis")
    parser.add_argument("--region",
                        help="Region name for cortical analysis")
    parser.add_argument("--whole_head", action="store_true",
                        help="Analyze the whole head instead of a specific region")

    # Subject specification; for voxel‐cortical we expect an extra atlas_path
    parser.add_argument("--subject", action="append", nargs='+', metavar="ARG",
                        help="Subject specification: subject_id m2m_path field_path [atlas_path] "
                             "(atlas_path required for voxel-based cortical analysis)")

    # Output and comparison options
    parser.add_argument("--output_dir", required=True,
                        help="Directory for legacy group analysis outputs (comprehensive results go to centralized location)")
    parser.add_argument("--quiet", action="store_true",
                        help="Enable summary mode for clean output (non-debug mode)")
    parser.add_argument("--no-compare", action="store_true",
                        help="Skip comparison analysis after all subjects are processed (comparison runs by default)")
    parser.add_argument("--visualize", action="store_true",
                        help="Generate visualization outputs for each analysis")

    return parser


def validate_args(args):
    """Validate command line arguments."""
    if not args.subject or len(args.subject) == 0:
        raise ValueError("At least one --subject must be specified")

    # Validate analysis‐specific arguments
    if args.analysis_type == 'spherical':
        if not args.coordinates:
            raise ValueError("Coordinates are required for spherical analysis")
        if args.radius is None:
            raise ValueError("Radius is required for spherical analysis")

        # Spherical: each subject must supply exactly (id, m2m_path, field_path)
        for i, subject_args in enumerate(args.subject):
            if len(subject_args) != 3:
                raise ValueError(
                    f"Subject {i+1}: Spherical analysis requires exactly 3 arguments: "
                    "subject_id m2m_path field_path"
                )

    else:  # cortical
        if args.space == 'mesh':
            if not args.atlas_name:
                raise ValueError("Atlas name is required for mesh-based cortical analysis")
            # Mesh‐cortical: each subject still has (id, m2m_path, field_path)
            for i, subject_args in enumerate(args.subject):
                if len(subject_args) != 3:
                    raise ValueError(
                        f"Subject {i+1}: Mesh cortical analysis requires exactly 3 arguments: "
                        "subject_id m2m_path field_path"
                    )
        else:
            # Voxel‐cortical: each subject must supply (id, m2m_path, field_path, atlas_path)
            for i, subject_args in enumerate(args.subject):
                if len(subject_args) != 4:
                    raise ValueError(
                        f"Subject {i+1}: Voxel cortical analysis requires exactly 4 arguments: "
                        "subject_id m2m_path field_path atlas_path"
                    )

        if not args.whole_head and not args.region:
            raise ValueError("Either --whole_head flag or --region must be specified for cortical analysis")

    # Validate space‐specific: mesh needs a field_name (now hardcoded)
    # Field name is now hardcoded to "TI_max", no validation needed

    # Validate existence of provided paths
    for subject_args in args.subject:
        subject_id = subject_args[0]
        m2m_path = subject_args[1]
        field_path = subject_args[2]

        if not os.path.isdir(m2m_path):
            raise ValueError(f"Subject {subject_id} m2m directory not found: {m2m_path}")
        # For mesh analysis, field_path is actually a montage name, not a file path
        # Skip file existence check for mesh analysis
        if args.space != 'mesh' and not os.path.exists(field_path):
            raise ValueError(f"Subject {subject_id} field file not found: {field_path}")

        if args.space == 'voxel' and args.analysis_type == 'cortical':
            atlas_path = subject_args[3]
            if not os.path.exists(atlas_path):
                raise ValueError(f"Subject {subject_id} atlas file not found: {atlas_path}")


def compute_subject_output_dir(args, subject_args: List[str]) -> str:
    """
    Create a consistent output directory structure for analysis results.
    Structure: output_dir/sub-{subject_id}/Simulations/{montage_name}/Analyses/{Mesh|Voxel}/{analysis_name}
    """
    subject_id = subject_args[0]

    # For mesh analysis, field_path is the montage name
    # For voxel analysis, we need to extract montage name from field path
    if args.space == 'mesh':
        montage_name = subject_args[2]  # field_path is montage name for mesh
    else:
        # For voxel analysis, extract montage name from path structure
        field_path = subject_args[2]
        try:
            path_parts = Path(field_path).parts
            sim_idx = path_parts.index('Simulations')
            montage_name = path_parts[sim_idx + 1]
        except (ValueError, IndexError):
            # If we can't parse the path, use a default montage name
            montage_name = 'unknown_montage'

    # Build consistent directory structure
    space_dir = 'Mesh' if args.space == 'mesh' else 'Voxel'
    base_dir = os.path.join(args.output_dir, f'sub-{subject_id}', 'Simulations', montage_name, 'Analyses', space_dir)

    # Create analysis-specific directory name
    if args.analysis_type == 'spherical':
        coord_space_suffix = f"_{args.coordinate_space}"
        coords = [float(c) for c in args.coordinates]
        analysis_name = f"sphere_x{coords[0]:.2f}_y{coords[1]:.2f}_z{coords[2]:.2f}_r{args.radius}{coord_space_suffix}"
    else:  # cortical
        if args.whole_head:
            if args.space == 'mesh':
                analysis_name = f"whole_head_{args.atlas_name}"
            else:
                atlas_path = subject_args[3]
                atlas_name = os.path.basename(atlas_path).split('.')[0]
                analysis_name = f"whole_head_{atlas_name}"
        else:
            analysis_name = f"region_{args.region}"

    output_dir = os.path.join(base_dir, analysis_name)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def build_main_analyzer_command(
    args,
    subject_args: List[str],
    subject_output_dir: str
) -> List[str]:
    """
    Build the command to run main_analyzer.py for a single subject,
    matching the exact structure used in analyzer_tab.py.
    """
    global group_logger
    
    subject_id = subject_args[0]
    m2m_path = subject_args[1]
    field_path = subject_args[2]

    # Locate main_analyzer.py (assume it sits next to this script)
    script_dir = Path(__file__).parent
    main_analyzer_path = script_dir / "main_analyzer.py"

    # Use `simnibs_python` as the interpreter (matching analyzer_tab.py)
    cmd = ["simnibs_python", str(main_analyzer_path)]

    # Add arguments in the same order as analyzer_tab.py
    cmd += ["--m2m_subject_path", m2m_path]
    
    # For mesh analysis, field_path is the montage name directly
    # For voxel analysis, field_path is the actual file path
    if args.space == 'mesh':
        # field_path is already the montage name
        cmd += ["--montage_name", field_path]
    else:
        cmd += ["--field_path", field_path]
    
    cmd += ["--space", args.space]
    cmd += ["--analysis_type", args.analysis_type]

    # Analysis-type-specific flags
    if args.analysis_type == 'spherical':
        # Pass coordinates and coordinate space - let main_analyzer.py handle transformation
        cmd += ["--coordinates"] + [str(c) for c in args.coordinates]
        cmd += ["--coordinate-space", args.coordinate_space]
        cmd += ["--radius", str(args.radius)]

    else:  # cortical
        # For cortical, add atlas info first
        if args.space == 'mesh':
            cmd += ["--atlas_name", args.atlas_name]
        else:  # voxel
            atlas_path = subject_args[3]
            cmd += ["--atlas_path", atlas_path]

        # Then add region or whole_head flag
        if args.whole_head:
            cmd += ["--whole_head"]
        else:
            cmd += ["--region", args.region]

    # Field name is now hardcoded in main_analyzer.py, no need to pass it
    
    # Add output directory
    cmd += ["--output_dir", subject_output_dir]
    
    # Always enable visualizations (matching the request)
    cmd += ["--visualize"]
    
    # Add group analysis log file path if available
    if group_logger and hasattr(group_logger, 'handlers') and group_logger.handlers:
        # Get the log file path from the first handler
        for handler in group_logger.handlers:
            if hasattr(handler, 'baseFilename'):
                log_file_path = getattr(handler, 'baseFilename')
                cmd += ["--log_file", log_file_path]
                break
    
    # Add quiet flag if requested
    if args.quiet:
        cmd += ["--quiet"]

    return cmd


def run_subject_analysis(args, subject_args: List[str]) -> Tuple[bool, str]:
    """
    Run analysis for a single subject and return (success, output_dir).
    All output is logged to the centralized group analysis log file.
    """
    global group_logger
    
    subject_id = subject_args[0]
    m2m_path = subject_args[1]
    field_path = subject_args[2]

    # Compute the target output folder for this subject
    subject_output_dir = compute_subject_output_dir(args, subject_args)

    # Build the command
    cmd = build_main_analyzer_command(args, subject_args, subject_output_dir)

    if group_logger:
        group_logger.debug(f"Starting analysis for subject: {subject_id}")

    # Track timing for subject analysis
    import time
    start_time = time.time()

    # Run main_analyzer.py with real-time output streaming
    if args.quiet:
        # In summary mode, stream output in real-time to show task steps as they happen
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                               text=True, bufsize=1, universal_newlines=True)
        
        # Stream output in real-time
        output_lines = []
        while True:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            if line:
                line = line.strip()
                if line:
                    output_lines.append(line)
                    # Display task steps in real-time
                    if line.startswith('Beginning analysis for subject:'):
                        # This is the subject start message, display it with proper indentation
                        print(f"  {line}")
                    elif line.startswith('├─ ') or line.startswith('└─ '):
                        # This is a task step, display it with proper indentation
                        clean_line = line[2:]  # Remove the tree symbols
                        print(f"  ├─ {clean_line}")
                    elif 'Starting...' in line and 'Subject' in line:
                        # Skip the "Subject X: Starting..." line as it's already shown
                        continue
                    elif '✓ Complete' in line or '✗ Failed' in line:
                        # Skip completion lines as they're handled separately
                        continue
                    elif 'Analysis completed successfully' in line:
                        # Skip the final completion message as it's handled separately
                        continue
        
        # Wait for process to complete
        return_code = proc.wait()
        stdout_output = '\n'.join(output_lines)
    else:
        # In debug mode, capture output as before
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return_code = proc.returncode
        stdout_output = proc.stdout

    end_time = time.time()
    duration = int(end_time - start_time)
    duration_str = format_duration(duration)

    if return_code == 0:
        if group_logger:
            group_logger.debug(f"Subject {subject_id} analysis completed successfully")
        
        # Log subject status for summary
        if args.quiet:
            log_group_subject_status(subject_id, "complete", duration_str)
        
        return True, subject_output_dir
    else:
        if group_logger:
            group_logger.error(f"Subject {subject_id} analysis failed")
            # Log any additional error output that might not have been captured by main_analyzer.py
            if stdout_output.strip():
                group_logger.error(f"stdout: {stdout_output.strip()}")
            # For streaming mode, stderr is redirected to stdout, so no separate stderr handling needed

        # Extract meaningful error message for summary
        error_msg = ""
        if stdout_output.strip():
            # Look for error patterns in stdout
            stdout_lines = stdout_output.strip().split('\n')
            for line in stdout_lines:
                if any(keyword in line.lower() for keyword in ['error:', 'failed', 'exception', 'critical']):
                    error_msg = line.strip()
                    break
        
        # Log subject status for summary
        if args.quiet:
            log_group_subject_status(subject_id, "failed", duration_str, error_msg)
        
        return False, ""


def collect_analysis_paths(successful_dirs: List[str]) -> List[str]:
    """
    Each entry in successful_dirs is exactly the folder we passed to --output_dir
    for main_analyzer.py. We check that it contains at least one .csv before returning it.
    """
    global group_logger
    
    analysis_paths = []
    for d in successful_dirs:
        if os.path.isdir(d):
            csv_list = [f for f in os.listdir(d) if f.lower().endswith(".csv")]
            if csv_list:
                analysis_paths.append(d)
            else:
                if group_logger:
                    group_logger.debug(f"No CSV found under {d}")
        else:
            if group_logger:
                group_logger.debug(f"Expected analysis directory not found: {d}")

    return analysis_paths


def run_comprehensive_group_analysis(analysis_paths: List[str], project_name: Optional[str] = None) -> str:
    """
    Run comprehensive group analysis using all available comparison methods.
    
    Args:
        analysis_paths (List[str]): List of paths to individual subject analysis directories
        project_name (str, optional): Project name. If None, extracted from first path.
        
    Returns:
        str: Path to the group analysis output directory
    """
    global group_logger
    
    if len(analysis_paths) == 0:
        if group_logger:
            group_logger.debug("No analysis paths provided for group comparison.")
        return ""
    
    if group_logger:
        group_logger.debug(f"\n=== Running comprehensive group analysis on {len(analysis_paths)} analyses ===")
    
    try:
        # Use the comprehensive comparison function from compare_analyses.py
        group_output_dir = run_all_group_comparisons(analysis_paths, project_name)
        if group_logger:
            group_logger.debug(f"✔ Comprehensive group analysis completed successfully.")
            group_logger.debug(f"  All results saved to: {group_output_dir}")
        return group_output_dir
    except Exception as e:
        if group_logger:
            group_logger.error(f"✖ Group analysis failed with error: {e}")
        return ""


def determine_group_subfolder_name(args, first_subject_args: List[str]) -> str:
    """
    Determine the group subfolder name in format: {montage}_{roi}
    
    Args:
        args: Command line arguments
        first_subject_args: First subject's arguments to extract montage info
        
    Returns:
        str: Subfolder name like "montage_roi"
    """
    # Extract montage name from field path
    field_path = first_subject_args[2]
    path_parts = Path(field_path).parts
    
    try:
        # Locate "Simulations" in the file path
        sim_idx = path_parts.index('Simulations')
        # Montage name is the folder immediately after "Simulations"
        montage_name = path_parts[sim_idx + 1]
    except (ValueError, IndexError):
        # If "Simulations" not found in path, try to extract from filename
        field_filename = Path(field_path).stem
        if field_filename.endswith('_TINormal'):
            montage_name = field_filename.replace('_TINormal', 'Normal')
        elif field_filename.endswith('_TI_Normal'):
            montage_name = field_filename.replace('_TI_Normal', '_Normal')
        elif field_filename.endswith('_TI'):
            montage_name = field_filename.replace('_TI', '')
        else:
            montage_name = field_filename
    
    # Determine ROI description
    if args.analysis_type == 'spherical':
        roi_desc = f"sphere_r{args.radius}"
    else:  # cortical
        if args.whole_head:
            if args.space == 'mesh':
                roi_desc = f"whole_head_{args.atlas_name}"
            else:  # voxel
                atlas_path = first_subject_args[3] if len(first_subject_args) > 3 else "unknown_atlas"
                atlas_name = os.path.basename(atlas_path).split('.')[0] if atlas_path != "unknown_atlas" else "unknown_atlas"
                roi_desc = f"whole_head_{atlas_name}"
        else:
            roi_desc = args.region
    
    return f"{montage_name}_{roi_desc}"


def main():
    global group_logger
    
    parser = setup_parser()
    args = parser.parse_args()

    try:
        validate_args(args)

        # Set up summary mode if requested
        if args.quiet:
            global SUMMARY_MODE
            SUMMARY_MODE = True

        # Create centralized group output directory based on first subject's path
        first_subject_path = args.subject[0][1]  # m2m_path from first subject
        centralized_group_dir = create_group_output_directory(first_subject_path)
        
        # Extract project name for later use
        project_name = _extract_project_name(first_subject_path)
        
        # Set up centralized logging for group analysis
        group_logger = setup_group_logger(project_name)
        
        # Create analysis description for summary
        analysis_description = f"{args.analysis_type} ({args.space})"
        if args.analysis_type == 'spherical' and args.coordinates:
            coords_str = ', '.join(f"{float(c):.1f}" for c in args.coordinates)
            analysis_description += f" - x={coords_str}, r={args.radius}mm"
        elif args.analysis_type == 'cortical':
            if args.whole_head:
                if args.space == 'mesh':
                    analysis_description += f" - {args.atlas_name} (whole head)"
                else:
                    analysis_description += " - whole head"
            else:
                if args.space == 'mesh':
                    analysis_description += f" - {args.atlas_name}.{args.region}"
                else:
                    analysis_description += f" - {args.region}"
        
        # Start group analysis summary logging
        if args.quiet:
            log_group_analysis_start(len(args.subject), analysis_description)

        if group_logger:
            group_logger.debug(f"\n>>> Starting group analysis with {len(args.subject)} subject(s).")
            group_logger.debug(f"    Project: {project_name}")
            group_logger.debug(f"    Analysis = {args.analysis_type} (space={args.space})")
            group_logger.debug(f"    Centralized group results will go to: {centralized_group_dir}")
        
        # Still create the user-specified output directory for legacy compatibility
        os.makedirs(args.output_dir, exist_ok=True)
        if group_logger:
            group_logger.debug(f"    Legacy output directory: {args.output_dir}\n")

        successful_dirs = []
        successful_subjects_info = []  # Store (subject_args, output_dir) pairs
        failed_subjects = []

        for subj_args in args.subject:
            subj_id = subj_args[0]
            
            # Log subject start for summary
            if args.quiet:
                print(f"├─ Subject {subj_id}: Starting...")
            
            ok, outdir = run_subject_analysis(args, subj_args)
            if ok:
                successful_dirs.append(outdir)
                successful_subjects_info.append((subj_args, outdir))
            else:
                failed_subjects.append(subj_id)
            
            # Add a small visual separator between subjects for clarity
            if args.quiet and len(args.subject) > 1:
                print("")  # Empty line for visual separation

        if group_logger:
            group_logger.debug("\n=== GROUP ANALYSIS SUMMARY ===")
            group_logger.debug(f"Total subjects : {len(args.subject)}")
            group_logger.debug(f"Succeeded      : {len(successful_dirs)}")
            group_logger.debug(f"Failed         : {len(failed_subjects)}")
            if failed_subjects:
                group_logger.debug(f"Failed subjects: {', '.join(failed_subjects)}")

        # Always run comprehensive group analysis if we have successful analyses (unless --no-compare is specified)
        if len(successful_dirs) >= 1 and not args.no_compare:
            # Log group comparison start for summary
            if args.quiet:
                print("├─ Group comparison: Starting...")
            
            # Track timing for group comparison
            group_start_time = time.time()
            
            analysis_dirs = collect_analysis_paths(successful_dirs)
            if analysis_dirs:
                final_group_dir = run_comprehensive_group_analysis(analysis_dirs, project_name)
                
                # Calculate group comparison duration
                group_duration = int(time.time() - group_start_time)
                group_duration_str = format_duration(group_duration)
                
                # Log group comparison completion for summary
                if args.quiet:
                    print(f"├─ Group comparison: ✓ Complete ({len(analysis_dirs)} subjects processed, {group_duration_str})")
                
                if group_logger:
                    group_logger.debug(f"Group comparison completed. Output directory: {final_group_dir}")
                
                # Results are comprehensively logged, no need for separate summary files
            else:
                if group_logger:
                    group_logger.debug("No valid analysis directories found for group comparison.")
        elif args.no_compare:
            if group_logger:
                group_logger.debug("Group comparison skipped (--no-compare flag specified).")
        else:
            if group_logger:
                group_logger.debug("No successful analyses to compare.")

        # Complete group analysis summary logging
        if args.quiet:
            output_path = ""
            if len(successful_dirs) >= 1 and not args.no_compare and 'analysis_dirs' in locals():
                output_path = final_group_dir if 'final_group_dir' in locals() else ""
            log_group_analysis_complete(len(successful_dirs), len(args.subject), output_path)

        if group_logger:
            group_logger.debug("\n>>> Group analysis complete.")
            if len(successful_dirs) >= 1 and not args.no_compare:
                group_logger.debug(f"Comprehensive group results are available in the centralized location.")
                group_logger.debug("")  # Empty line for spacing
            elif args.no_compare:
                group_logger.debug(f"Group comparison was skipped. Individual subject results are in their respective directories.\n")
            else:
                group_logger.debug("No successful analyses completed.\n")

    except Exception as e:
        if group_logger:
            group_logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
