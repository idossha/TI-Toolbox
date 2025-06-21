#!/usr/bin/env python3
"""Test script to simulate the complete GUI simulation flow."""

import os
import sys
import json
import datetime
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from utils.simulation_report_generator import SimulationReportGenerator
from utils.report_util import get_simulation_report_generator

def test_gui_simulation_flow():
    """Test the complete GUI simulation flow including report generation."""
    
    print("\n" + "="*60)
    print("Testing Complete GUI Simulation Flow")
    print("="*60 + "\n")
    
    # Simulate GUI parameters
    project_dir = os.path.join(project_root, "example_data")
    subject_id = "101"
    montage_name = "L_Insula"
    
    # Simulation parameters (as collected by GUI)
    conductivity = "scalar"
    sim_mode = "U"
    eeg_net = "EGI_template.csv"
    current_ma_1 = 2.0
    current_ma_2 = 2.0
    electrode_shape = "rect"
    dimensions = "8,8"
    thickness = "8"
    
    print("1. Setting up simulation parameters...")
    print(f"   - Subject: {subject_id}")
    print(f"   - Montage: {montage_name}")
    print(f"   - Conductivity: {conductivity}")
    print(f"   - Mode: {'Unipolar' if sim_mode == 'U' else 'Multipolar'}")
    print(f"   - Current: {current_ma_1}/{current_ma_2} mA")
    print(f"   - Electrode: {electrode_shape} {dimensions}mm, {thickness}mm thick")
    
    # Create session ID (as GUI does)
    simulation_session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"\n2. Creating report generator with session ID: {simulation_session_id}")
    report_generator = get_simulation_report_generator(project_dir, simulation_session_id)
    
    # Add simulation parameters (as GUI does after fix)
    print("\n3. Adding simulation parameters...")
    report_generator.add_simulation_parameters(
        conductivity_type=conductivity,
        simulation_mode=sim_mode,
        eeg_net=eeg_net,
        intensity_ch1=current_ma_1,
        intensity_ch2=current_ma_2,
        quiet_mode=False
    )
    
    # Add electrode parameters (as GUI does after fix)
    print("4. Adding electrode parameters...")
    dim_parts = dimensions.split(',')
    report_generator.add_electrode_parameters(
        shape=electrode_shape,
        dimensions=[float(dim_parts[0]), float(dim_parts[1])],
        thickness=float(thickness)
    )
    
    # Add subject
    print("5. Adding subject...")
    m2m_path = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", f"m2m_{subject_id}")
    report_generator.add_subject(subject_id, m2m_path, 'processing')
    
    # Add montage (with actual electrode pairs from montage file)
    print("6. Adding montage...")
    electrode_pairs = [['E020', 'E034'], ['E070', 'E095']]
    report_generator.add_montage(
        name=montage_name,
        electrode_pairs=electrode_pairs,
        montage_type='unipolar'
    )
    
    print("\n7. Simulating individual report generation (as GUI does)...")
    
    # Create individual report generator
    sim_session_id = f"{simulation_session_id}_{subject_id}_{montage_name}"
    single_sim_generator = get_simulation_report_generator(project_dir, sim_session_id)
    
    # Get parameters from main generator
    params = report_generator.report_data['simulation_parameters']
    electrode_params = report_generator.report_data['electrode_parameters']
    
    print("\n   Debug: Simulation parameters keys:", list(params.keys()))
    print("   Debug: Electrode parameters keys:", list(electrode_params.keys()))
    
    # Add simulation parameters with proper handling (as GUI does after fix)
    filtered_params = {
        'conductivity_type': params.get('conductivity_type', 'scalar'),
        'simulation_mode': params.get('simulation_mode', 'U'),
        'eeg_net': params.get('eeg_net', 'EGI_template.csv'),
        'intensity_ch1': float(params.get('intensity_ch1_ma') or 2.0),  # Note: stored as intensity_ch1_ma
        'intensity_ch2': float(params.get('intensity_ch2_ma') or 2.0),  # Note: stored as intensity_ch2_ma
        'quiet_mode': params.get('quiet_mode', False)
    }
    if 'conductivities' in params and params['conductivities']:
        filtered_params['conductivities'] = params['conductivities']
    
    single_sim_generator.add_simulation_parameters(**filtered_params)
    
    # Add electrode parameters (only expected fields)
    single_sim_generator.add_electrode_parameters(
        shape=electrode_params['shape'],
        dimensions=electrode_params['dimensions'],
        thickness=electrode_params['thickness']
    )
    
    # Add subject
    subject = report_generator.report_data['subjects'][0]
    single_sim_generator.add_subject(
        subject_id=subject['subject_id'],
        m2m_path=subject['m2m_path'],
        status='completed'
    )
    
    # Add montage (only expected fields)
    montage = report_generator.report_data['montages'][0]
    single_sim_generator.add_montage(
        name=montage['name'],
        electrode_pairs=montage.get('electrode_pairs', []),
        montage_type=montage.get('type', 'unipolar')
    )
    
    # Get output files
    print("\n8. Checking for output files...")
    simulations_dir = os.path.join(project_dir, "derivatives", "SimNIBS", f"sub-{subject_id}", "Simulations", montage_name)
    ti_dir = os.path.join(simulations_dir, "TI")
    nifti_dir = os.path.join(ti_dir, "niftis")
    
    output_files = {'TI': [], 'niftis': []}
    if os.path.exists(nifti_dir):
        nifti_files = [f for f in os.listdir(nifti_dir) if f.endswith('.nii.gz')]
        output_files['niftis'] = [os.path.join(nifti_dir, f) for f in nifti_files]
        ti_files = [f for f in nifti_files if 'TI_max' in f]
        output_files['TI'] = [os.path.join(nifti_dir, f) for f in ti_files]
        print(f"   Found {len(nifti_files)} NIfTI files")
        print(f"   Found {len(ti_files)} TI max files")
    else:
        print("   No output files found (expected if simulation hasn't run)")
    
    # Add simulation result
    single_sim_generator.add_simulation_result(
        subject_id=subject_id,
        montage_name=montage_name,
        output_files=output_files,
        duration=None,
        status='completed'
    )
    
    # Generate report
    print("\n9. Generating report...")
    report_path = single_sim_generator.generate_report()
    
    if report_path and os.path.exists(report_path):
        print(f"\n✅ SUCCESS: Report generated at:\n   {report_path}")
        
        # Check report content
        with open(report_path, 'r') as f:
            content = f.read()
            
        print("\n10. Report validation:")
        print(f"    - File size: {len(content):,} bytes")
        print(f"    - Contains montage image: {'montage_imgs' in content}")
        print(f"    - Contains brain visualization: {'Brain Visualizations' in content}")
        print(f"    - Contains parameters: {'Simulation Parameters' in content}")
        
        return True
    else:
        print("\n❌ ERROR: Report file not found after generation")
        return False

if __name__ == "__main__":
    success = test_gui_simulation_flow()
    sys.exit(0 if success else 1) 