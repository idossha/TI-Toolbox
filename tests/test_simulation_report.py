#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Test script for generating a comprehensive simulation report.
This script creates a full simulation report with multiple subjects,
montages, and results, similar to what would be generated in a
real simulation scenario.

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
import shutil
import datetime
from pathlib import Path

# Add parent directory to path to import utils
sys.path.append(str(Path(__file__).parent.parent))

from utils.simulation_report_generator import SimulationReportGenerator
from utils.papaya_utils import get_papaya_dir

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

def setup_test_data(base_dir):
    """Set up test data structure simulating multiple subjects and montages."""
    # Create directory structure
    subjects = ['101', '102']
    montages = ['L_insula', 'R_insula', 'M1']
    
    # Get path to example data
    example_dir = Path(__file__).parent / "example_data"
    
    for subject in subjects:
        # Create subject m2m directory
        m2m_dir = base_dir / f"sub-{subject}" / "m2m"
        m2m_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy T1 to m2m directory
        shutil.copy2(
            example_dir / "T1.nii.gz",
            m2m_dir / "T1.nii.gz"
        )
        
        # Create simulations directory
        sim_dir = base_dir / f"sub-{subject}" / "Simulations"
        sim_dir.mkdir(parents=True, exist_ok=True)
        
        for montage in montages:
            # Create montage directories
            montage_dir = sim_dir / montage
            for subdir in ['TI', 'mTI']:
                # Create type directories
                type_dir = montage_dir / subdir
                type_dir.mkdir(parents=True, exist_ok=True)
                
                # Create subdirectories
                (type_dir / "mesh").mkdir(exist_ok=True)
                (type_dir / "niftis").mkdir(exist_ok=True)
                (type_dir / "montage_imgs").mkdir(exist_ok=True)
                
                # Copy example TI field
                if subdir == 'TI':
                    shutil.copy2(
                        example_dir / "grey_101_L_insula_TI_TI_max.nii.gz",
                        type_dir / "niftis" / f"grey_{subject}_{montage}_TI_TI_max.nii.gz"
                    )

def test_full_simulation_report():
    """Generate a comprehensive simulation report with multiple subjects and montages."""
    
    # Create test output directory
    output_dir = Path(__file__).parent / "test_output" / "full_report"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Set up test data structure
    setup_test_data(output_dir)
    
    try:
        # Initialize report generator
        generator = SimulationReportGenerator(
            output_dir,
            simulation_session_id=datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        )
        
        # Add simulation parameters
        generator.add_simulation_parameters(
            conductivity_type='tensor',
            simulation_mode='M',
            eeg_net='EGI_128.csv',
            intensity_ch1=1.0,
            intensity_ch2=1.0,
            quiet_mode=False
        )
        
        # Add electrode parameters
        generator.add_electrode_parameters(
            shape='rect',
            dimensions=[50, 70],
            thickness=4.0
        )
        
        # Add subjects
        subjects = ['101', '102']
        for subject in subjects:
            m2m_path = output_dir / f"sub-{subject}" / "m2m"
            generator.add_subject(
                subject_id=subject,
                m2m_path=str(m2m_path),
                status='completed'
            )
            
            # Add T1 path to subject data
            for subj in generator.report_data['subjects']:
                if subj['subject_id'] == subject:
                    subj['t1_path'] = str(m2m_path / "T1.nii.gz")
        
        # Add montages
        montages = {
            'L_insula': [('F3', 'Cz'), ('C3', 'T7')],
            'R_insula': [('F4', 'Cz'), ('C4', 'T8')],
            'M1': [('C3', 'Fp1'), ('C4', 'Fp2')]
        }
        
        for name, pairs in montages.items():
            generator.add_montage(
                montage_name=name,
                electrode_pairs=pairs,
                montage_type='multipolar'
            )
        
        # Add simulation results
        for subject in subjects:
            for montage in montages:
                # Get paths to simulation outputs
                sim_dir = output_dir / f"sub-{subject}" / "Simulations" / montage
                ti_dir = sim_dir / "TI"
                
                # Add simulation result
                generator.add_simulation_result(
                    subject_id=subject,
                    montage_name=montage,
                    output_files={
                        'TI': [
                            str(ti_dir / "niftis" / f"grey_{subject}_{montage}_TI_TI_max.nii.gz")
                        ]
                    },
                    duration=120.5,
                    status='completed'
                )
                
                # Add visualization data to subject
                for subj in generator.report_data['subjects']:
                    if subj['subject_id'] == subject:
                        if 'simulation_outputs' not in subj:
                            subj['simulation_outputs'] = []
                        
                        subj['simulation_outputs'].append({
                            'montage_name': montage,
                            'nifti_visualizations': [
                                str(ti_dir / "niftis" / f"grey_{subject}_{montage}_TI_TI_max.nii.gz")
                            ]
                        })
        
        # Add some test errors and warnings
        generator.add_error(
            "Failed to compute field in white matter",
            subject_id='101',
            montage_name='L_insula'
        )
        
        generator.add_warning(
            "High conductivity value detected in CSF",
            subject_id='102',
            montage_name='M1'
        )
        
        # Generate the report
        report_path = generator.generate_report()
        
        print("\nTest Results:")
        print("-------------")
        print(f"✅ Full simulation report generated successfully at: {report_path}")
        print("\nReport contains:")
        print("- Multiple subjects (101, 102)")
        print("- Multiple montages (L_insula, R_insula, M1)")
        print("- Simulation parameters and electrode settings")
        print("- Interactive brain visualizations for each subject/montage")
        print("- Example errors and warnings")
        print("\nInstructions:")
        print("1. Open the generated HTML file in your web browser")
        print("2. Navigate through the different sections")
        print("3. Test the interactive visualizations")
        print("4. Verify all data is displayed correctly")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Error generating full report: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("Running Full Simulation Report Test")
    print("==================================")
    
    # Check prerequisites first
    if not check_prerequisites():
        print("\n❌ Prerequisites not met. Please fix the issues above and try again.")
        sys.exit(1)
    
    # Generate full simulation report
    test_full_simulation_report() 