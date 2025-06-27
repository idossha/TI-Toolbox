#!/usr/bin/env python3

"""
Group Analyzer Script

Each subject's analysis will be saved under:
    derivatives/SimNIBS/<subject_id>/Simulations/<montage_name>/Analyses/<Mesh-or-Voxel>/

Within each subject's Analyses folder, we also capture:
  - overlays & plots (via --visualize)
  - CSV summary  (handled by main_analyzer.py)
  - a per‐subject log file (stdout/stderr)
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Tuple

# Import our comparison functions
try:
    from .compare_analyses import run_all_group_comparisons, _extract_project_name
except ImportError:
    # Fallback for direct execution
    sys.path.insert(0, os.path.dirname(__file__))
    from compare_analyses import run_all_group_comparisons, _extract_project_name


def create_group_output_directory(first_subject_path: str) -> str:
    """
    Create centralized group analysis output directory.
    
    Args:
        first_subject_path (str): Path from the first subject to extract project name
        
    Returns:
        str: Path to the created group analysis directory
    """
    # Extract project name from the first subject's path
    project_name = _extract_project_name(first_subject_path)
    
    # Create centralized group analysis directory
    group_output_dir = os.path.join("/mnt", project_name, "derivatives", "group_analysis")
    os.makedirs(group_output_dir, exist_ok=True)
    
    print(f"Created group analysis directory: {group_output_dir}")
    return group_output_dir

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
    parser.add_argument("--radius", type=float,
                        help="Radius for spherical analysis")
    parser.add_argument("--region",
                        help="Region name for cortical analysis")
    parser.add_argument("--whole_head", action="store_true",
                        help="Analyze the whole head instead of a specific region")
    parser.add_argument("--field_name",
                        help="Field name for mesh analysis (e.g., normE)")

    # Subject specification; for voxel‐cortical we expect an extra atlas_path
    parser.add_argument("--subject", action="append", nargs='+', metavar="ARG",
                        help="Subject specification: subject_id m2m_path field_path [atlas_path] "
                             "(atlas_path required for voxel-based cortical analysis)")

    # Output and comparison options
    parser.add_argument("--output_dir", required=True,
                        help="Directory for legacy group analysis outputs (comprehensive results go to centralized location)")
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

    # Validate space‐specific: mesh needs a field_name
    if args.space == 'mesh' and not args.field_name:
        raise ValueError("--field_name is required for mesh analysis")

    # Validate existence of provided paths
    for subject_args in args.subject:
        subject_id = subject_args[0]
        m2m_path = subject_args[1]
        field_path = subject_args[2]

        if not os.path.isdir(m2m_path):
            raise ValueError(f"Subject {subject_id} m2m directory not found: {m2m_path}")
        if not os.path.exists(field_path):
            raise ValueError(f"Subject {subject_id} field file not found: {field_path}")

        if args.space == 'voxel' and args.analysis_type == 'cortical':
            atlas_path = subject_args[3]
            if not os.path.exists(atlas_path):
                raise ValueError(f"Subject {subject_id} atlas file not found: {atlas_path}")


def compute_subject_output_dir(args, subject_args: List[str]) -> str:
    """
    Create a descriptive output directory name based on analysis parameters,
    matching the structure used in analyzer_tab.py:
    derivatives/SimNIBS/<subject_id>/Simulations/<montage_name>/Analyses/<Mesh-or-Voxel>/<analysis_description>/
    """
    field_path = subject_args[2]
    path_parts = Path(field_path).parts

    try:
        # Locate "Simulations" in the file path
        sim_idx = path_parts.index('Simulations')
        # Montage name is the folder immediately after "Simulations"
        montage_name = path_parts[sim_idx + 1]
        # Build base up through: .../Simulations/<montage_name>
        base_montage_dir = os.path.join(*path_parts[: sim_idx + 2])

        # Decide if this is a Mesh or Voxel subfolder
        space_dir = 'Mesh' if args.space == 'mesh' else 'Voxel'
        analyses_base = os.path.join(base_montage_dir, 'Analyses', space_dir)
        
        # Create descriptive analysis folder name based on parameters
        if args.analysis_type == 'spherical':
            coords_str = '_'.join([str(c) for c in args.coordinates])
            analysis_name = f"sphere_x{args.coordinates[0]}_y{args.coordinates[1]}_z{args.coordinates[2]}_r{args.radius}"
        else:  # cortical
            if args.whole_head:
                if args.space == 'mesh':
                    atlas_info = args.atlas_name
                    analysis_name = f"whole_head_{atlas_info}"
                else:  # voxel
                    atlas_path = subject_args[3]
                    atlas_name = os.path.basename(atlas_path).split('.')[0]
                    analysis_name = f"whole_head_{atlas_name}"
            else:
                analysis_name = f"region_{args.region}"
        
        output_dir = os.path.join(analyses_base, analysis_name)
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    except (ValueError, IndexError):
        # If "Simulations" isn't found, fall back to placing outputs next to the field file:
        fallback = os.path.join(os.path.dirname(field_path), f"fallback_{subject_args[0]}")
        os.makedirs(fallback, exist_ok=True)
        return fallback


def build_main_analyzer_command(
    args,
    subject_args: List[str],
    subject_output_dir: str
) -> List[str]:
    """
    Build the command to run main_analyzer.py for a single subject,
    matching the exact structure used in analyzer_tab.py.
    """
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
    cmd += ["--field_path", field_path]
    cmd += ["--space", args.space]
    cmd += ["--analysis_type", args.analysis_type]

    # Analysis-type-specific flags (matching analyzer_tab.py order):
    if args.analysis_type == 'spherical':
        # Spherical: coordinates then radius
        cmd += ["--coordinates"] + [str(c) for c in args.coordinates]
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

    # Add field name for mesh analysis
    if args.space == 'mesh':
        cmd += ["--field_name", args.field_name]

    # Add output directory
    cmd += ["--output_dir", subject_output_dir]
    
    # Always enable visualizations (matching the request)
    cmd += ["--visualize"]

    return cmd


def run_subject_analysis(args, subject_args: List[str]) -> Tuple[bool, str]:
    """
    Run analysis for a single subject and return (success, output_dir).
    """
    subject_id = subject_args[0]
    m2m_path = subject_args[1]
    field_path = subject_args[2]

    # Compute the target output folder for this subject
    subject_output_dir = compute_subject_output_dir(args, subject_args)

    # Build the command
    cmd = build_main_analyzer_command(args, subject_args, subject_output_dir)

    print(f"\n=== Processing subject: {subject_id} ===")
    print(f"  M2M path:    {m2m_path}")
    print(f"  Field path:  {field_path}")
    print(f"  Output dir:  {subject_output_dir}")
    if len(subject_args) == 4:
        print(f"  Atlas path:  {subject_args[3]}")
    print(f"  Command:\n    {' '.join(cmd)}\n")

    # Run main_analyzer.py
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode == 0:
        print(f"✔ Subject {subject_id} completed successfully")
        print(proc.stdout)
        return True, subject_output_dir
    else:
        print(f"✖ Subject {subject_id} FAILED.")
        print("STDOUT:", proc.stdout)
        print("STDERR:", proc.stderr)
        return False, ""


def collect_analysis_paths(successful_dirs: List[str]) -> List[str]:
    """
    Each entry in successful_dirs is exactly the folder we passed to --output_dir
    for main_analyzer.py. We check that it contains at least one .csv before returning it.
    """
    analysis_paths = []
    for d in successful_dirs:
        if os.path.isdir(d):
            csv_list = [f for f in os.listdir(d) if f.lower().endswith(".csv")]
            if csv_list:
                analysis_paths.append(d)
            else:
                print(f"Warning: no CSV found under {d}")
        else:
            print(f"Warning: expected analysis directory not found: {d}")
    return analysis_paths


def run_comprehensive_group_analysis(analysis_paths: List[str], project_name: str = None) -> str:
    """
    Run comprehensive group analysis using all available comparison methods.
    
    Args:
        analysis_paths (List[str]): List of paths to individual subject analysis directories
        project_name (str, optional): Project name. If None, extracted from first path.
        
    Returns:
        str: Path to the group analysis output directory
    """
    if len(analysis_paths) == 0:
        print("Warning: No analysis paths provided for group comparison.")
        return ""
    
    print(f"\n=== Running comprehensive group analysis on {len(analysis_paths)} analyses ===")
    
    try:
        # Use the comprehensive comparison function from compare_analyses.py
        group_output_dir = run_all_group_comparisons(analysis_paths, project_name)
        print(f"✔ Comprehensive group analysis completed successfully.")
        print(f"  All results saved to: {group_output_dir}")
        return group_output_dir
    except Exception as e:
        print(f"✖ Group analysis failed with error: {e}")
        return ""


def main():
    parser = setup_parser()
    args = parser.parse_args()

    try:
        validate_args(args)
        
        # Create centralized group output directory based on first subject's path
        first_subject_path = args.subject[0][1]  # m2m_path from first subject
        centralized_group_dir = create_group_output_directory(first_subject_path)
        
        # Extract project name for later use
        project_name = _extract_project_name(first_subject_path)

        print(f"\n>>> Starting group analysis with {len(args.subject)} subject(s).")
        print(f"    Project: {project_name}")
        print(f"    Analysis = {args.analysis_type} (space={args.space})")
        print(f"    Centralized group results will go to: {centralized_group_dir}")
        
        # Still create the user-specified output directory for legacy compatibility
        os.makedirs(args.output_dir, exist_ok=True)
        print(f"    Legacy output directory: {args.output_dir}\n")

        successful_dirs = []
        failed_subjects = []

        for subj_args in args.subject:
            subj_id = subj_args[0]
            ok, outdir = run_subject_analysis(args, subj_args)
            if ok:
                successful_dirs.append(outdir)
            else:
                failed_subjects.append(subj_id)

        print("\n=== GROUP ANALYSIS SUMMARY ===")
        print(f"Total subjects : {len(args.subject)}")
        print(f"Succeeded      : {len(successful_dirs)}")
        print(f"Failed         : {len(failed_subjects)}")
        if failed_subjects:
            print(f"Failed subjects: {', '.join(failed_subjects)}")

        # Always run comprehensive group analysis if we have successful analyses (unless --no-compare is specified)
        if len(successful_dirs) >= 1 and not args.no_compare:
            analysis_dirs = collect_analysis_paths(successful_dirs)
            if analysis_dirs:
                final_group_dir = run_comprehensive_group_analysis(analysis_dirs, project_name)
                
                # Also create a simple summary in the legacy output directory
                legacy_summary = os.path.join(args.output_dir, "group_analysis_summary.txt")
                with open(legacy_summary, 'w') as f:
                    f.write(f"Group Analysis Completed\n")
                    f.write(f"========================\n\n")
                    f.write(f"Comprehensive results are available in:\n")
                    f.write(f"{final_group_dir}\n\n")
                    f.write(f"This includes:\n")
                    f.write(f"- Statistical comparisons\n")
                    f.write(f"- Averaged NIfTI images\n")
                    f.write(f"- High-value intersection analysis\n")
                    f.write(f"- Organized output structure\n")
                print(f"Legacy summary created: {legacy_summary}")
            else:
                print("Warning: No valid analysis directories found for group comparison.")
        elif args.no_compare:
            print("Group comparison skipped (--no-compare flag specified).")
        else:
            print("Warning: No successful analyses to compare.\n")

        print("\n>>> Group analysis complete.")
        if len(successful_dirs) >= 1 and not args.no_compare:
            print(f"Comprehensive group results are in: {centralized_group_dir}")
            print(f"Legacy comparison summary is in: {args.output_dir}\n")
        elif args.no_compare:
            print(f"Group comparison was skipped. Individual subject results are in their respective directories.\n")
        else:
            print("No successful analyses completed.\n")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
