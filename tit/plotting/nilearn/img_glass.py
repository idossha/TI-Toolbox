#!/usr/bin/env simnibs_python
"""
TI-Toolbox Glass Brain Visualizations
Creates glass brain visualizations using nilearn's plot_glass_brain.

Usage:
    python img_glass.py --subject 001 --simulation montage1
    python img_glass.py --subject 001 --simulation montage1 --cutoff 0.5 --cmap plasma
"""

import argparse
import sys

from .visualizer import NilearnVisualizer


def create_glass_brain_entry_point(subject_id: str, simulation_name: str,
                                 min_cutoff: float = 0.3, max_cutoff: float = None,
                                 cmap: str = 'hot', output_callback=None):
    """
    Entry point for glass brain visualization creation.

    Args:
        subject_id: Subject ID
        simulation_name: Simulation name
        min_cutoff: Minimum cutoff for visualization (V/m)
        max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
        cmap: Colormap name for visualization
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
            result = visualizer.create_glass_brain_visualization(subject_id, simulation_name, min_cutoff, max_cutoff, cmap)

        # Send captured output to callback line by line
        output_text = captured_output.getvalue()
        for line in output_text.split('\n'):
            if line.strip():
                output_callback(line)

        if result:
            output_callback(f"✓ Glass brain visualization completed: {result}")
            return result
        else:
            output_callback("✗ Glass brain visualization failed")
            return None
    else:
        # Normal operation - print to stdout
        visualizer = NilearnVisualizer()
        result = visualizer.create_glass_brain_visualization(subject_id, simulation_name, min_cutoff, max_cutoff, cmap)
        if result:
            print(f"\n✓ Glass brain visualization completed: {result}")
            return result
        else:
            print("\n✗ Glass brain visualization failed")
            return None


def create_glass_brain_entry_point_group(averaged_img, base_filename: str, output_dir: str,
                                       min_cutoff: float = 0.3, max_cutoff: float = None,
                                       cmap: str = 'hot', output_callback=None):
    """
    Entry point for glass brain visualization creation with pre-averaged nifti data.

    Args:
        averaged_img: Pre-averaged nibabel Nifti1Image
        base_filename: Base filename for output (without extension)
        output_dir: Output directory path
        min_cutoff: Minimum cutoff for visualization (V/m)
        max_cutoff: Maximum cutoff for visualization (V/m), if None uses 99.9th percentile
        cmap: Colormap name for visualization
        output_callback: Optional callback function for output (for GUI integration)
    """
    # Redirect stdout if callback provided (for GUI integration)
    import sys
    from contextlib import redirect_stdout
    import io
    import os
    import numpy as np
    import matplotlib.pyplot as plt
    from nilearn import plotting

    if output_callback:
        # Capture stdout and send to callback
        captured_output = io.StringIO()
        with redirect_stdout(captured_output):
            # Load and analyze data
            data = averaged_img.get_fdata()
            data_nonzero = data[data > 0]
            if len(data_nonzero) == 0:
                print("Warning: No non-zero field values found")
                return None

            max_value = np.max(data)
            percentile_999 = np.percentile(data_nonzero, 99.9)
            min_value = np.min(data_nonzero)

            # Use provided max_cutoff or default to 99.9th percentile
            if max_cutoff is None:
                max_cutoff = percentile_999

            print(f"Electric field statistics (averaged data):")
            print(f"  Absolute maximum: {max_value:.2f} V/m")
            print(f"  99.9th percentile: {percentile_999:.2f} V/m")
            print(f"  Minimum (non-zero): {min_value:.2f} V/m")
            print(f"  Visualization range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m")

            # Create output filename
            pdf_filename = f"{base_filename}_glass_brain.pdf"
            pdf_filepath = os.path.join(output_dir, pdf_filename)

            # Create glass brain visualization
            plotting.plot_glass_brain(
                stat_map_img=averaged_img,
                threshold=min_cutoff,
                vmax=max_cutoff,
                cmap=cmap,
                colorbar=True,
                plot_abs=False,
                symmetric_cbar=False,
                display_mode="lyrz",
                title=f"Electric Field - Group Average\n{min_cutoff:.2f}-{max_cutoff:.2f} V/m",
                output_file=pdf_filepath
            )

            print(f"✓ Saved glass brain visualization: {pdf_filepath}")
            result = pdf_filepath

        # Send captured output to callback line by line
        output_text = captured_output.getvalue()
        for line in output_text.split('\n'):
            if line.strip():
                output_callback(line)

        if result:
            output_callback(f"✓ Glass brain visualization completed: {result}")
            return result
        else:
            output_callback("✗ Glass brain visualization failed")
            return None
    else:
        # Normal operation - print to stdout
        # Load and analyze data
        data = averaged_img.get_fdata()
        data_nonzero = data[data > 0]
        if len(data_nonzero) == 0:
            print("Warning: No non-zero field values found")
            return None

        max_value = np.max(data)
        percentile_999 = np.percentile(data_nonzero, 99.9)
        min_value = np.min(data_nonzero)

        # Use provided max_cutoff or default to 99.9th percentile
        if max_cutoff is None:
            max_cutoff = percentile_999

        print(f"Electric field statistics (averaged data):")
        print(f"  Absolute maximum: {max_value:.2f} V/m")
        print(f"  99.9th percentile: {percentile_999:.2f} V/m")
        print(f"  Minimum (non-zero): {min_value:.2f} V/m")
        print(f"  Visualization range: {min_cutoff:.2f} - {max_cutoff:.2f} V/m")

        # Create output filename
        pdf_filename = f"{base_filename}_glass_brain.pdf"
        pdf_filepath = os.path.join(output_dir, pdf_filename)

        # Create glass brain visualization
        plotting.plot_glass_brain(
            stat_map_img=averaged_img,
            threshold=min_cutoff,
            vmax=max_cutoff,
            cmap=cmap,
            colorbar=True,
            plot_abs=False,
            symmetric_cbar=False,
            display_mode="lyrz",
            title=f"Electric Field - Group Average\n{min_cutoff:.2f}-{max_cutoff:.2f} V/m",
            output_file=pdf_filepath
        )

        print(f"✓ Saved glass brain visualization: {pdf_filepath}")
        result = pdf_filepath

        if result:
            print(f"\n✓ Glass brain visualization completed: {result}")
            return result
        else:
            print("\n✗ Glass brain visualization failed")
            return None


def main():
    """Main CLI entry point for glass brain visualizations."""
    parser = argparse.ArgumentParser(
        description="TI-Toolbox Glass Brain Visualizations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create glass brain visualization
  python img_glass.py --subject 001 --simulation montage1

  # Use custom cutoffs and colormap
  python img_glass.py --subject 001 --simulation montage1 --min-cutoff 0.5 --max-cutoff 10.0 --cmap plasma
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
    parser.add_argument('--cmap', default='hot',
                       choices=['hot', 'plasma', 'inferno', 'viridis', 'cividis', 'coolwarm'],
                       help='Colormap for visualization (default: hot)')

    args = parser.parse_args()

    # Run the glass brain visualization
    return create_glass_brain_entry_point(args.subject, args.simulation, args.min_cutoff, args.max_cutoff, args.cmap)


if __name__ == "__main__":
    sys.exit(main())
