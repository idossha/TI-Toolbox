#!/usr/bin/env python3

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from utils.simulation_report_generator import SimulationReportGenerator

def test_report_from_example():
    """Generate a simulation report using example data."""
    try:
        # Set up paths
        project_dir = os.path.join(project_root, "example_data")
        subject_id = "101"
        montage_name = "L_Insula"  # Test with a single montage
        session_id = f"example_test_{subject_id}_{montage_name}"
        
        print("\nGenerating simulation report from example data...")
        print(f"Project directory: {project_dir}")
        print(f"Subject ID: {subject_id}")
        print(f"Montage: {montage_name}")
        
        # Create report generator
        generator = SimulationReportGenerator(project_dir, session_id)
        
        # Add simulation parameters
        generator.add_simulation_parameters(
            conductivity_type='scalar',
            simulation_mode='U',  # Unipolar
            eeg_net='EGI_template.csv',
            intensity_ch1=2.0,  # mA
            intensity_ch2=2.0,  # mA
            quiet_mode=False
        )
        
        # Add electrode parameters
        generator.add_electrode_parameters(
            shape='ellipse',
            dimensions=[8.0, 8.0],  # mm
            thickness=8.0  # mm
        )
        
        # Add subject
        m2m_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", f"m2m_{subject_id}")
        generator.add_subject(
            subject_id=subject_id,
            m2m_path=m2m_path,
            status='completed'
        )
        
        # Add montage
        generator.add_montage(
            name=montage_name,
            electrode_pairs=[['E020', 'E034'], ['E070', 'E095']],  # Example pairs from montage_list.json
            montage_type='unipolar'
        )
        
        # Add simulation result
        simulations_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "Simulations", montage_name)
        ti_dir = os.path.join(simulations_dir, "TI")
        nifti_dir = os.path.join(ti_dir, "niftis")
        
        output_files = {'TI': [], 'niftis': []}
        if os.path.exists(nifti_dir):
            # Add all NIfTI files
            nifti_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii.gz')]
            output_files['niftis'] = [os.path.join(nifti_dir, f) for f in nifti_files]
            # Add TI files specifically
            ti_files = [f for f in nifti_files if 'TI_max' in f]
            output_files['TI'] = [os.path.join(nifti_dir, f) for f in ti_files]
        
        generator.add_simulation_result(
            subject_id=subject_id,
            montage_name=montage_name,
            output_files=output_files,
            duration=120.0,  # Example duration
            status='completed'
        )
        
        # Generate the report
        report_path = generator.generate_report()
        
        if report_path and os.path.exists(report_path):
            print("\n✅ Test Results:")
            print("-------------")
            print(f"Report generated successfully at: {report_path}")
            print("\nReport contains:")
            print(f"- Subject: {subject_id}")
            print(f"- Montage: {montage_name}")
            print("- Simulation parameters and electrode settings")
            print("- Brain visualizations (if example data contains the files)")
            print("\nInstructions:")
            print("1. Open the generated HTML file in your web browser")
            print("2. Verify that all sections are populated correctly")
            print("3. Check that visualizations are displayed if example data contains the files")
            return True
        else:
            print("\n❌ Error: Report file not found after generation")
            return False
            
    except Exception as e:
        print(f"\n❌ Error generating report: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_report_from_example() 