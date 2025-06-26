#!/usr/bin/env python3

import os
import sys
import json
from pathlib import Path
import datetime

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from utils.simulation_report_generator import SimulationReportGenerator
from utils.report_util import get_simulation_report_generator

def test_gui_simulation_report():
    """Test report generation as it happens in the GUI."""
    try:
        # Set up paths
        project_dir = os.path.join(project_root, "example_data")
        subject_id = "101"
        montage_name = "L_Insula"
        
        # Simulate GUI behavior
        simulation_session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("\nTesting GUI-style simulation report generation...")
        print(f"Project directory: {project_dir}")
        print(f"Session ID: {simulation_session_id}")
        
        # Create main report generator (like GUI does)
        main_generator = get_simulation_report_generator(project_dir, simulation_session_id)
        
        # Add simulation parameters (like GUI does)
        main_generator.add_simulation_parameters(
            conductivity_type='scalar',  # Correct parameter name
            simulation_mode='U',  # Correct parameter name
            eeg_net='EGI_template.csv',
            intensity_ch1=1.0,  # Correct parameter name
            intensity_ch2=1.0,  # Correct parameter name
            quiet_mode=False
        )
        
        # Add electrode parameters
        main_generator.add_electrode_parameters(
            shape='ellipse',  # Correct parameter name
            dimensions=[8.0, 8.0],
            thickness=8.0
        )
        
        # Add subject
        m2m_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", f"m2m_{subject_id}")
        main_generator.add_subject(subject_id, m2m_path, 'processing')
        
        # Add montage
        main_generator.add_montage(
            name=montage_name,
            electrode_pairs=[['E020', 'E034'], ['E070', 'E095']],
            montage_type='unipolar'
        )
        
        # Now simulate the report generation for individual simulation
        print("\nGenerating individual report...")
        
        # Create individual report generator
        sim_session_id = f"{simulation_session_id}_{subject_id}_{montage_name}"
        single_sim_generator = get_simulation_report_generator(project_dir, sim_session_id)
        
        # Get parameters from main generator
        params = main_generator.report_data['simulation_parameters']
        electrode_params = main_generator.report_data['electrode_parameters']
        
        print(f"Debug: Simulation parameters: {params}")
        print(f"Debug: Electrode parameters: {electrode_params}")
        
        # Add simulation parameters with proper handling
        filtered_params = {
            'conductivity_type': params.get('conductivity_type', 'scalar'),
            'simulation_mode': params.get('simulation_mode', 'U'),
            'eeg_net': params.get('eeg_net', 'EGI_template.csv'),
            'intensity_ch1': float(params.get('intensity_ch1') or 2.0),
            'intensity_ch2': float(params.get('intensity_ch2') or 2.0),
            'quiet_mode': params.get('quiet_mode', False)
        }
        if 'conductivities' in params and params['conductivities']:
            filtered_params['conductivities'] = params['conductivities']
        
        single_sim_generator.add_simulation_parameters(**filtered_params)
        
        # Add electrode parameters
        single_sim_generator.add_electrode_parameters(
            shape=electrode_params['shape'],
            dimensions=electrode_params['dimensions'],
            thickness=electrode_params['thickness']
        )
        
        # Add subject
        subject = main_generator.report_data['subjects'][0]
        single_sim_generator.add_subject(
            subject_id=subject['subject_id'],
            m2m_path=subject['m2m_path'],
            status='completed'
        )
        
        # Add montage
        montage = main_generator.report_data['montages'][0]
        single_sim_generator.add_montage(
            name=montage['name'],
            electrode_pairs=montage.get('electrode_pairs', []),
            montage_type=montage.get('type', 'unipolar')
        )
        
        # Get output files
        simulations_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "Simulations", montage_name)
        ti_dir = os.path.join(simulations_dir, "TI")
        nifti_dir = os.path.join(ti_dir, "niftis")
        
        output_files = {'TI': [], 'niftis': []}
        if os.path.exists(nifti_dir):
            nifti_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii.gz')]
            output_files['niftis'] = [os.path.join(nifti_dir, f) for f in nifti_files]
            ti_files = [f for f in nifti_files if 'TI_max' in f]
            output_files['TI'] = [os.path.join(nifti_dir, f) for f in ti_files]
        
        # Add simulation result
        single_sim_generator.add_simulation_result(
            subject_id=subject_id,
            montage_name=montage_name,
            output_files=output_files,
            duration=None,
            status='completed'
        )
        
        # Generate report
        report_path = single_sim_generator.generate_report()
        
        if report_path and os.path.exists(report_path):
            print("\n✅ Test Results:")
            print("-------------")
            print(f"Report generated successfully at: {report_path}")
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
    test_gui_simulation_report() 