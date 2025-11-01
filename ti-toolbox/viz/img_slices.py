#!/usr/bin/env simnibs_python
"""
TI-Toolbox Publication-Ready Visualizations
Creates PDF visualizations with multiple views and atlas contours for publication.

Usage:
    python img_slices.py --subject 001 --simulation montage1
    python img_slices.py --subject 001 --simulation montage1 --cutoff 0.5 --atlas aal
"""

import argparse
import sys
from pathlib import Path

# Add the ti_toolbox package to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.viz import NilearnVisualizer


def create_pdf_entry_point(subject_id: str, simulation_name: str,
                          min_cutoff: float = 0.3, max_cutoff: float = None,
                          atlas_name: str = "harvard_oxford_sub", selected_regions: list = None,
                          output_callback=None):
    """
    Entry point for PDF visualization creation.

    Args:
        subject_id: Subject ID
        simulation_name: Simulation name
        min_cutoff: Minimum cutoff for visualization (V/m)
        max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
        atlas_name: Atlas name for contours
        selected_regions: List of region indices to include (0-indexed), if None includes all
        output_callback: Optional callback function for output (for GUI integration)
    """
    # Redirect stdout if callback provided (for GUI integration)
    import sys
    from contextlib import redirect_stdout
    import io

    if output_callback:
        # Capture stdout and send to callback
        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            visualizer = NilearnVisualizer()
            result = visualizer.create_pdf_visualization(subject_id, simulation_name, min_cutoff, max_cutoff, atlas_name, selected_regions)

        # Send captured output to callback line by line
        output_text = captured_output.getvalue()
        for line in output_text.split('\n'):
            if line.strip():
                output_callback(line)

        if result:
            output_callback(f"✓ PDF visualization completed: {result}")
            return result
        else:
            output_callback("✗ PDF visualization failed")
            return None
    else:
        # Normal operation - print to stdout
        visualizer = NilearnVisualizer()
        result = visualizer.create_pdf_visualization(subject_id, simulation_name, min_cutoff, max_cutoff, atlas_name, selected_regions)
        if result:
            print(f"\n✓ PDF visualization completed: {result}")
            return result
        else:
            print("\n✗ PDF visualization failed")
            return None


def create_pdf_entry_point_group(averaged_img, base_filename: str, output_dir: str,
                                min_cutoff: float = 0.3, max_cutoff: float = None,
                                atlas_name: str = "harvard_oxford_sub", selected_regions: list = None,
                                output_callback=None):
    """
    Entry point for PDF visualization creation with pre-averaged nifti data.

    Args:
        averaged_img: Pre-averaged nibabel Nifti1Image
        base_filename: Base filename for output (without extension)
        output_dir: Output directory path
        min_cutoff: Minimum cutoff for visualization (V/m)
        max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
        atlas_name: Atlas name for contours
        selected_regions: List of region indices to include (0-indexed), if None includes all
        output_callback: Optional callback function for output (for GUI integration)
    """
    # Redirect stdout if callback provided (for GUI integration)
    import sys
    from contextlib import redirect_stdout
    import io

    if output_callback:
        # Capture stdout and send to callback
        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            visualizer = NilearnVisualizer()
            result = visualizer.create_pdf_visualization_group(averaged_img, base_filename, output_dir, min_cutoff, max_cutoff, atlas_name, selected_regions)

        # Send captured output to callback line by line
        output_text = captured_output.getvalue()
        for line in output_text.split('\n'):
            if line.strip():
                output_callback(line)

        if result:
            output_callback(f"✓ PDF visualization completed: {result}")
            return result
        else:
            output_callback("✗ PDF visualization failed")
            return None
    else:
        # Normal operation - print to stdout
        visualizer = NilearnVisualizer()
        result = visualizer.create_pdf_visualization_group(averaged_img, base_filename, output_dir, min_cutoff, max_cutoff, atlas_name, selected_regions)
        if result:
            print(f"\n✓ PDF visualization completed: {result}")
            return result
        else:
            print("\n✗ PDF visualization failed")
            return None


def main():
    """Main CLI entry point for publication-ready visualizations."""
    parser = argparse.ArgumentParser(
        description="TI-Toolbox Publication-Ready Visualizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create PDF visualization with atlas contours
  python img_slices.py --subject 001 --simulation montage1

  # Use custom cutoffs and atlas
  python img_slices.py --subject 001 --simulation montage1 --min-cutoff 0.5 --max-cutoff 10.0 --atlas aal

  # Use specific regions from atlas
  python img_slices.py --subject 001 --simulation montage1 --atlas harvard_oxford_sub --regions 1 2 3
        """
    )

    parser.add_argument('--subject', '-s', required=True,
                       help='Subject ID (e.g., 001, 101)')
    parser.add_argument('--simulation', '-sim', required=True,
                       help='Simulation name')
    parser.add_argument('--min-cutoff', '-c', type=float, default=0.3,
                       help='Minimum cutoff for visualization (V/m, default: 0.3)')
    parser.add_argument('--max-cutoff', '-mc', type=float, default=None,
                       help='Maximum cutoff for visualization (V/m, default: 99.9th percentile)')
    parser.add_argument('--atlas', '-a', default='harvard_oxford_sub',
                       choices=['harvard_oxford', 'harvard_oxford_sub', 'aal', 'schaefer_2018'],
                       help='Atlas for contour overlay (default: harvard_oxford_sub)')
    parser.add_argument('--regions', '-r', nargs='*', type=int,
                       help='Region indices to include (0-indexed, space-separated). If not specified, all regions are included.')

    args = parser.parse_args()

    # Run the PDF visualization
    return create_pdf_entry_point(args.subject, args.simulation, args.min_cutoff, args.max_cutoff, args.atlas, args.regions)


if __name__ == "__main__":
    sys.exit(main())
