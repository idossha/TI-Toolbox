#!/usr/bin/env simnibs_python
"""
TI-Toolbox HTML Report Generator
Creates interactive HTML visualizations of electric field distributions.

Usage:
    python html_report.py --subject 001 --simulation montage1
    python html_report.py --subject 001 --simulation montage1 --cutoff 0.5
"""

import argparse
import sys

from .visualizer import NilearnVisualizer


def create_html_entry_point(subject_id: str, simulation_name: str, min_cutoff: float = 0.3):
    """
    Entry point for HTML visualization creation.

    Args:
        subject_id: Subject ID
        simulation_name: Simulation name
        min_cutoff: Minimum cutoff for visualization (V/m)
    """
    visualizer = NilearnVisualizer()
    result = visualizer.create_html_visualization(subject_id, simulation_name, min_cutoff)
    if result:
        print(f"\n✓ HTML visualization completed: {result}")
        return 0
    else:
        print("\n✗ HTML visualization failed")
        return 1


def main():
    """Main CLI entry point for HTML reports."""
    parser = argparse.ArgumentParser(
        description="TI-Toolbox HTML Report Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create interactive HTML visualization
  python html_report.py --subject 001 --simulation montage1

  # Use custom cutoff
  python html_report.py --subject 001 --simulation montage1 --cutoff 0.5
        """
    )

    parser.add_argument('--subject', '-s', required=True,
                       help='Subject ID (e.g., 001, 101)')
    parser.add_argument('--simulation', '-sim', required=True,
                       help='Simulation name')
    parser.add_argument('--cutoff', '-c', type=float, default=0.3,
                       help='Minimum cutoff for visualization (V/m, default: 0.3)')

    args = parser.parse_args()

    # Run the HTML visualization
    return create_html_entry_point(args.subject, args.simulation, args.cutoff)


if __name__ == "__main__":
    sys.exit(main())
