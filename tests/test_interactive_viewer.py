#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for the interactive visualization functionality.
This script demonstrates how to create an interactive visualization
using example T1 and TI field data.

Prerequisites:
-------------
1. Install Papaya:
   git clone https://github.com/rii-mango/Papaya.git
   Place it in one of these locations:
   - Project root directory (recommended)
   - utils directory
   - Current working directory
   - /development/Papaya (for Docker)

2. Ensure example data exists in tests/example_data:
   - T1.nii.gz
   - grey_101_L_insula_TI_TI_max.nii.gz
"""

import os
import sys
from pathlib import Path

# Add parent directory to path to import utils
sys.path.append(str(Path(__file__).parent.parent))

from utils.simulation_report_generator import SimulationReportGenerator
from utils.papaya_utils import add_papaya_viewer, get_papaya_dir

def check_prerequisites():
    """Check if all prerequisites are met."""
    # Check Papaya installation
    papaya_dir = get_papaya_dir()
    if not papaya_dir:
        print("\n❌ Papaya not found!")
        print("\nTo install Papaya:")
        print("1. Clone the repository:")
        print("   git clone https://github.com/rii-mango/Papaya.git")
        print("2. Place it in one of these locations:")
        print("   - Project root directory (recommended)")
        print("   - utils directory")
        print("   - Current working directory")
        print("   - /development/Papaya (for Docker)")
        return False
    
    print(f"\n✅ Found Papaya at: {papaya_dir}")
    
    # Check example data
    example_dir = Path(__file__).parent / "example_data"
    t1_file = example_dir / "T1.nii.gz"
    ti_file = example_dir / "grey_101_L_insula_TI_TI_max.nii.gz"
    
    if not t1_file.exists() or not ti_file.exists():
        print("\n❌ Example data not found!")
        print(f"Expected files in {example_dir}:")
        print("- T1.nii.gz")
        print("- grey_101_L_insula_TI_TI_max.nii.gz")
        return False
    
    print("✅ Found example data files")
    return True

def test_interactive_visualization():
    """Test the interactive visualization with example data."""
    
    # Get paths to example data
    example_dir = Path(__file__).parent / "example_data"
    t1_file = example_dir / "T1.nii.gz"
    ti_file = example_dir / "grey_101_L_insula_TI_TI_max.nii.gz"
    
    # Create output directory for the test
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    # Create a test report
    report_file = output_dir / "test_visualization.html"
    
    try:
        # Initialize report generator
        generator = SimulationReportGenerator(output_dir)
        
        # Add a test subject with our example data
        generator.add_subject(
            subject_id="test_subject",
            m2m_path=str(example_dir),
            status='completed'
        )
        
        # Add the T1 path to the subject data
        for subject in generator.report_data['subjects']:
            if subject['subject_id'] == "test_subject":
                subject['t1_path'] = str(t1_file)
                subject['simulation_outputs'] = [{
                    'montage_name': 'test_montage',
                    'nifti_visualizations': [str(ti_file)]
                }]
        
        # Generate the report
        report_path = generator.generate_report(str(report_file))
        
        print("\nTest Results:")
        print("-------------")
        print(f"✅ Report generated successfully at: {report_path}")
        print("\nInstructions:")
        print("1. Open the generated HTML file in your web browser")
        print("2. Navigate to the 'Interactive Brain Visualizations' section")
        print("3. You should see the T1 image with the TI field overlay")
        print("4. Use the Papaya viewer controls to:")
        print("   - Navigate through slices")
        print("   - Adjust overlay opacity")
        print("   - Change color maps")
        print("   - Switch between views")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error during test: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def create_standalone_viewer():
    """Create a standalone Papaya viewer HTML file with just the example data."""
    
    # Get paths to example data
    example_dir = Path(__file__).parent / "example_data"
    t1_file = example_dir / "T1.nii.gz"
    ti_file = example_dir / "grey_101_L_insula_TI_TI_max.nii.gz"
    
    # Create output directory
    output_dir = Path(__file__).parent / "test_output"
    output_dir.mkdir(exist_ok=True)
    
    # Create standalone viewer file
    viewer_file = output_dir / "standalone_viewer.html"
    
    try:
        # Create a minimal HTML file
        with open(viewer_file, 'w') as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <title>TI Field Visualization</title>
            </head>
            <body>
                <h1>TI Field Interactive Viewer</h1>
                <div id="papaya_viewer"></div>
            </body>
            </html>
            """)
        
        # Add Papaya viewer
        success = add_papaya_viewer(
            str(viewer_file),
            str(t1_file),
            str(ti_file)
        )
        
        if success:
            print("\nStandalone Viewer Results:")
            print("-------------------------")
            print(f"✅ Viewer created successfully at: {viewer_file}")
            print("\nInstructions:")
            print("1. Open the generated HTML file in your web browser")
            print("2. You should see the T1 image with the TI field overlay")
            print("3. Use the Papaya viewer controls to interact with the visualization")
        else:
            print("\n❌ Failed to create standalone viewer")
        
        return success
        
    except Exception as e:
        print(f"\n❌ Error creating standalone viewer: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Running Interactive Visualization Tests")
    print("=====================================")
    
    # Check prerequisites first
    if not check_prerequisites():
        print("\n❌ Prerequisites not met. Please fix the issues above and try again.")
        sys.exit(1)
    
    # Test full report generation
    print("\nTest 1: Generating Full Report...")
    test_interactive_visualization()
    
    # Test standalone viewer
    print("\nTest 2: Creating Standalone Viewer...")
    create_standalone_viewer() 