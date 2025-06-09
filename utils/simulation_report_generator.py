#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Simulation Report Generator
This module generates comprehensive HTML reports for simulation pipelines,
similar to fMRIPrep reports, documenting all simulation parameters, montages,
subjects, and outputs with brain visualizations.
"""

import os
import json
import datetime
import subprocess
import glob
import base64
import tempfile
from pathlib import Path
import numpy as np

class SimulationReportGenerator:
    """Generate comprehensive HTML reports for simulation pipelines."""
    
    def __init__(self, project_dir, simulation_session_id=None):
        """Initialize the simulation report generator.
        
        Args:
            project_dir (str): Path to the project directory
            simulation_session_id (str): Unique identifier for this simulation session
        """
        self.project_dir = Path(project_dir)
        self.simulation_session_id = simulation_session_id or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Initialize report data structure
        self.report_data = {
            'simulation_session_id': self.simulation_session_id,
            'generation_time': datetime.datetime.now().isoformat(),
            'project_dir': str(project_dir),
            'subjects': [],
            'montages': [],
            'simulation_parameters': {},
            'electrode_parameters': {},
            'simulation_results': {},
            'errors': [],
            'warnings': [],
            'software_versions': {},
            'visualizations': []
        }
        
        # Collect software versions
        self._collect_software_versions()
    
    def _get_default_conductivities(self):
        """Get default tissue conductivity values.
        
        Returns:
            dict: Dictionary of tissue conductivity values {tissue_number: {name, conductivity, reference}}
        """
        return {
            1: {"name": "White Matter", "conductivity": 0.126, "reference": "Wagner et al., 2004"},
            2: {"name": "Gray Matter", "conductivity": 0.275, "reference": "Wagner et al., 2004"},
            3: {"name": "CSF", "conductivity": 1.654, "reference": "Wagner et al., 2004"},
            4: {"name": "Bone", "conductivity": 0.01, "reference": "Wagner et al., 2004"},
            5: {"name": "Scalp", "conductivity": 0.465, "reference": "Wagner et al., 2004"},
            6: {"name": "Eye balls", "conductivity": 0.5, "reference": "Opitz et al., 2015"},
            7: {"name": "Compact Bone", "conductivity": 0.008, "reference": "Opitz et al., 2015"},
            8: {"name": "Spongy Bone", "conductivity": 0.025, "reference": "Opitz et al., 2015"},
            9: {"name": "Blood", "conductivity": 0.6, "reference": "Gabriel et al., 2009"},
            10: {"name": "Muscle", "conductivity": 0.16, "reference": "Gabriel et al., 2009"},
            100: {"name": "Silicone Rubber", "conductivity": 29.4, "reference": "NeuroConn electrodes: Wacker Elastosil R 570/60 RUSS"},
            500: {"name": "Saline", "conductivity": 1.0, "reference": "Saturnino et al., 2015"}
        }
    
    def _collect_software_versions(self):
        """Collect versions of software used in the simulation pipeline."""
        try:
            # SimNIBS version
            result = subprocess.run(['simnibs_python', '-c', 'import simnibs; print(simnibs.__version__)'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.report_data['software_versions']['simnibs'] = result.stdout.strip()
        except:
            pass
        
        try:
            # Python version
            result = subprocess.run(['python', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.report_data['software_versions']['python'] = result.stdout.strip()
        except:
            pass
        
        try:
            # TI-CSC version (if available)
            version_file = self.project_dir / "ti-csc" / "VERSION"
            if version_file.exists():
                with open(version_file, 'r') as f:
                    self.report_data['software_versions']['ti_csc'] = f.read().strip()
        except:
            pass
    
    def add_simulation_parameters(self, conductivity_type, simulation_mode, eeg_net, 
                                intensity_ch1, intensity_ch2, quiet_mode=False, conductivities=None):
        """Add simulation parameters to the report.
        
        Args:
            conductivity_type (str): Type of conductivity ('scalar', 'tensor')
            simulation_mode (str): Simulation mode ('U' for unipolar, 'M' for multipolar)
            eeg_net (str): EEG net filename
            intensity_ch1 (float): Current intensity for channel 1 (mA)
            intensity_ch2 (float): Current intensity for channel 2 (mA)
            quiet_mode (bool): Whether simulation was run in quiet mode
            conductivities (dict): Dictionary of tissue conductivity values {tissue_number: conductivity_S/m}
        """
        self.report_data['simulation_parameters'] = {
            'conductivity_type': conductivity_type,
            'simulation_mode': simulation_mode,
            'simulation_mode_text': 'Unipolar' if simulation_mode == 'U' else 'Multipolar',
            'eeg_net': eeg_net,
            'intensity_ch1_ma': intensity_ch1,
            'intensity_ch2_ma': intensity_ch2,
            'intensity_ch1_a': intensity_ch1 / 1000.0,
            'intensity_ch2_a': intensity_ch2 / 1000.0,
            'quiet_mode': quiet_mode,
            'conductivities': conductivities or self._get_default_conductivities(),
            'timestamp': datetime.datetime.now().isoformat()
        }
    
    def add_electrode_parameters(self, shape, dimensions, thickness):
        """Add electrode parameters to the report.
        
        Args:
            shape (str): Electrode shape ('rect' or 'ellipse')
            dimensions (list): Electrode dimensions [width, height] in mm
            thickness (float): Electrode thickness in mm
        """
        self.report_data['electrode_parameters'] = {
            'shape': shape,
            'dimensions': dimensions,
            'thickness': thickness,
            'area_mm2': dimensions[0] * dimensions[1] if shape == 'rect' else np.pi * (dimensions[0]/2) * (dimensions[1]/2),
            'timestamp': datetime.datetime.now().isoformat()
        }
    
    def add_subject(self, subject_id, m2m_path=None, status='completed'):
        """Add a subject to the simulation report.
        
        Args:
            subject_id (str): Subject ID
            m2m_path (str): Path to the m2m directory
            status (str): Processing status ('completed', 'failed', 'skipped')
        """
        subject_data = {
            'subject_id': subject_id,
            'bids_subject_id': f"sub-{subject_id}",
            'm2m_path': m2m_path,
            'status': status,
            'simulation_outputs': [],
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        # simulation_outputs and t1_path will be populated by generate_report()
        self.report_data['subjects'].append(subject_data)
    
    def update_subject_status(self, subject_id, status):
        """Update the status of a subject.
        
        Args:
            subject_id (str): Subject ID
            status (str): New status ('completed', 'failed', 'processing')
        """
        for subject in self.report_data['subjects']:
            if subject['subject_id'] == subject_id:
                subject['status'] = status
                subject['timestamp'] = datetime.datetime.now().isoformat()
                break
    
    def add_montage(self, montage_name, electrode_pairs, montage_type='unipolar'):
        """Add a montage to the simulation report.
        
        Args:
            montage_name (str): Name of the montage
            electrode_pairs (list): List of electrode pairs
            montage_type (str): Type of montage ('unipolar' or 'multipolar')
        """
        montage_data = {
            'name': montage_name,
            'type': montage_type,
            'electrode_pairs': electrode_pairs,
            'num_pairs': len(electrode_pairs),
            'electrodes_used': list(set([e for pair in electrode_pairs for e in pair])),
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        self.report_data['montages'].append(montage_data)
    
    def add_simulation_result(self, subject_id, montage_name, output_files, 
                            duration=None, status='completed'):
        """Add simulation results for a specific subject-montage combination.
        
        Args:
            subject_id (str): Subject ID
            montage_name (str): Montage name
            output_files (dict): Dictionary of output file types and paths
            duration (float): Simulation duration in seconds
            status (str): Simulation status
        """
        result_key = f"{subject_id}_{montage_name}"
        self.report_data['simulation_results'][result_key] = {
            'subject_id': subject_id,
            'montage_name': montage_name,
            'output_files': output_files,
            'duration': duration,
            'status': status,
            'timestamp': datetime.datetime.now().isoformat()
        }
    
    def add_error(self, error_message, subject_id=None, montage_name=None):
        """Add an error to the report.
        
        Args:
            error_message (str): Error message
            subject_id (str): Subject ID where error occurred
            montage_name (str): Montage name where error occurred
        """
        self.report_data['errors'].append({
            'message': error_message,
            'subject_id': subject_id,
            'montage_name': montage_name,
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    def add_warning(self, warning_message, subject_id=None, montage_name=None):
        """Add a warning to the report.
        
        Args:
            warning_message (str): Warning message
            subject_id (str): Subject ID where warning occurred
            montage_name (str): Montage name where warning occurred
        """
        self.report_data['warnings'].append({
            'message': warning_message,
            'subject_id': subject_id,
            'montage_name': montage_name,
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    def _scan_simulation_outputs(self, subject_id, m2m_path):
        """Scan for simulation output files.
        
        Args:
            subject_id (str): Subject ID
            m2m_path (str): Path to m2m directory
            
        Returns:
            list: List of output file information
        """
        outputs = []
        
        # Look for simulation directories
        simulations_dir = Path(m2m_path).parent / "Simulations"
        if simulations_dir.exists():
            for montage_dir in simulations_dir.iterdir():
                if montage_dir.is_dir():
                    montage_outputs = {
                        'montage_name': montage_dir.name,
                        'files': {},
                        'montage_image': None,
                        'nifti_visualizations': []
                    }
                    
                    # Scan for different types of outputs
                    for output_type in ['TI', 'mTI', 'high_Frequency']:
                        type_dir = montage_dir / output_type
                        if type_dir.exists():
                            montage_outputs['files'][output_type] = []
                            
                            # Look for montage visualization image
                            montage_imgs_dir = type_dir / "montage_imgs"
                            if montage_imgs_dir.exists():
                                montage_img_pattern = f"{montage_dir.name}_highlighted_visualization.png"
                                montage_img_path = montage_imgs_dir / montage_img_pattern
                                if montage_img_path.exists():
                                    montage_outputs['montage_image'] = str(montage_img_path)
                            
                            # Scan for mesh files
                            mesh_dir = type_dir / "mesh"
                            if mesh_dir.exists():
                                mesh_files = list(mesh_dir.glob("*.msh"))
                                montage_outputs['files'][output_type].extend([str(f) for f in mesh_files])
                            
                            # Scan for NIfTI files and collect specific TI files
                            nifti_dir = type_dir / "niftis"
                            if nifti_dir.exists():
                                nifti_files = list(nifti_dir.glob("*.nii*"))
                                montage_outputs['files'][output_type].extend([str(f) for f in nifti_files])
                                
                                # Look for specific TI max files for visualization
                                ti_max_files = []
                                for pattern in [f"{subject_id}_{montage_dir.name}_TI_TI_max.nii.gz",
                                              f"grey_{subject_id}_{montage_dir.name}_TI_TI_max.nii.gz",
                                              f"white_{subject_id}_{montage_dir.name}_TI_TI_max.nii.gz"]:
                                    ti_file = nifti_dir / pattern
                                    if ti_file.exists():
                                        ti_max_files.append(str(ti_file))
                                
                                if ti_max_files:
                                    montage_outputs['nifti_visualizations'] = ti_max_files
                    
                    outputs.append(montage_outputs)
        
        return outputs
    
    def _find_t1_file(self, m2m_path):
        """Find T1 file in m2m directory.
        
        Args:
            m2m_path (str): Path to m2m directory
            
        Returns:
            str: Path to T1 file or None if not found
        """
        t1_candidates = ['T1.nii.gz', 'T1.nii', 'T1fs_conform.nii.gz']
        for candidate in t1_candidates:
            t1_path = os.path.join(m2m_path, candidate)
            if os.path.exists(t1_path):
                return t1_path
        return None
    
    def _generate_brain_visualization(self, subject_id, montage_name, mesh_file=None, nifti_file=None):
        """Generate brain visualization for the report.
        
        Args:
            subject_id (str): Subject ID
            montage_name (str): Montage name
            mesh_file (str): Path to mesh file (unused, kept for compatibility)
            nifti_file (str): Path to NIfTI file
            
        Returns:
            str: HTML for interactive visualization or placeholder
        """
        try:
            # Only handle NIfTI files with the interactive viewer
            if nifti_file and os.path.exists(nifti_file):
                viewer_name = f"{subject_id}_{montage_name}"
                return self._generate_nifti_visualization_html([nifti_file], viewer_name=viewer_name)
            else:
                return None
        except Exception as e:
            self.add_warning(f"Failed to generate visualization: {str(e)}", subject_id, montage_name)
            return None
    
    def _generate_nifti_visualization_html(self, nifti_files, t1_file=None, viewer_name=None):
        """Generate HTML for interactive NIfTI visualization using Papaya viewer.
        
        Args:
            nifti_files (list): List of NIfTI file paths to include
            t1_file (str): Optional path to T1 structural file
            viewer_name (str): Name for this viewer
            
        Returns:
            str: HTML content for the interactive visualization
        """
        try:
            # Import papaya utilities
            from .papaya_utils import create_papaya_viewer
            
            # Get the report directory (will be set during report generation)
            if hasattr(self, '_current_report_dir'):
                report_dir = self._current_report_dir
            else:
                # Fallback to a temporary directory for preview
                import tempfile
                report_dir = tempfile.gettempdir()
            
            # Ensure we have a list of files
            if isinstance(nifti_files, str):
                nifti_files = [nifti_files]
            
            # Filter to existing files
            existing_files = [f for f in nifti_files if f and os.path.exists(f)]
            if not existing_files:
                return f"""
                <div style="margin: 10px 0; padding: 15px; background-color: #fff3cd; border-radius: 8px; border: 1px solid #ffeaa7;">
                    <h6 style="color: #856404; margin-bottom: 10px;">⚠️ No NIfTI Files Found</h6>
                    <p style="color: #856404; margin: 0; font-size: 14px;">
                        No valid NIfTI files were found for visualization.
                    </p>
                </div>
                """
            
            # Use T1 file if available, otherwise create placeholder
            if t1_file and os.path.exists(t1_file):
                # Create labels for the files
                labels = []
                for nifti_file in existing_files:
                    basename = os.path.basename(nifti_file)
                    if 'ti_max' in basename.lower():
                        labels.append(f"TI Max ({basename})")
                    elif 'grey' in basename.lower():
                        labels.append(f"Grey Matter ({basename})")
                    elif 'white' in basename.lower():
                        labels.append(f"White Matter ({basename})")
                    else:
                        labels.append(f"Field ({basename})")
                
                # Create the viewer
                viewer_html = create_papaya_viewer(
                    report_dir=report_dir,
                    viewer_name=viewer_name or "brain_viewer",
                    t1_file=t1_file,
                    field_files=existing_files,
                    labels=labels
                )
                return viewer_html
            else:
                return f"""
                <div style="margin: 10px 0; padding: 15px; background-color: #e3f2fd; border-radius: 8px; border: 1px solid #2196f3;">
                    <h6 style="color: #1976d2; margin-bottom: 10px;">📊 NIfTI Files Available</h6>
                    <p style="color: #1976d2; margin: 0; font-size: 14px;">
                        <strong>Files:</strong> {', '.join([os.path.basename(f) for f in existing_files])}<br>
                        <strong>Note:</strong> T1 reference not available for interactive viewing.<br>
                        <em>The interactive viewer works best with both T1 structural and overlay data.</em>
                    </p>
                </div>
                """
                
        except ImportError:
            return self._generate_papaya_installation_guide(existing_files[0] if existing_files else "")
        except Exception as e:
            return f"""
            <div style="margin: 10px 0; padding: 15px; background-color: #fff3cd; border-radius: 8px; border: 1px solid #ffeaa7;">
                <h6 style="color: #856404; margin-bottom: 10px;">⚠️ Visualization Error</h6>
                <p style="color: #856404; margin: 0; font-size: 14px;">
                    <strong>Files:</strong> {', '.join([os.path.basename(f) for f in existing_files]) if existing_files else 'None'}<br>
                    <strong>Error:</strong> {str(e)}<br>
                    <em>Please check the console for more details.</em>
                </p>
            </div>
            """
    
    def _generate_papaya_installation_guide(self, nifti_file):
        """Generate HTML with Papaya installation instructions."""
        filename = os.path.basename(nifti_file)
        
        return f"""
        <div class="papaya-fallback" style="margin: 15px 0;">
            <div style="background-color: #f8f9fa; border: 2px dashed #6c757d; border-radius: 8px; padding: 20px; text-align: center;">
                <div style="font-size: 18px; margin-bottom: 10px;">🧠</div>
                <h6 style="color: #495057; margin-bottom: 10px;">Papaya Viewer</h6>
                <p style="color: #6c757d; margin-bottom: 15px;">
                    <strong>File:</strong> {filename}
                </p>
                
                <div style="background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
                    <p style="color: #856404; margin: 0; font-size: 14px;">
                        <strong>⚠️ Papaya viewer not available</strong><br>
                        Please install Papaya to enable interactive visualization.
                    </p>
                </div>
                
                <div style="background-color: #e8f5e8; padding: 12px; border-radius: 6px; margin-bottom: 15px;">
                    <p style="color: #2e7d32; margin: 0; font-size: 14px;">
                        💡 <strong>To enable Papaya viewer:</strong><br>
                        1. Clone the repository:<br>
                        <code style="background: #333; color: #0f0; padding: 2px 4px;">git clone https://github.com/rii-mango/Papaya.git</code><br>
                        2. Place it in project root directory<br>
                        3. Regenerate your report for full interactive features!
                    </p>
                </div>
                
                <div style="margin-top: 15px;">
                    <button onclick="window.open('https://github.com/rii-mango/Papaya', '_blank')" 
                            style="background-color: #2196f3; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-right: 10px; font-size: 12px;">
                        🌐 Learn About Papaya
                    </button>
                    <button onclick="copyToClipboard('{nifti_file}')" 
                            style="background-color: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 12px;">
                        📋 Copy File Path
                    </button>
                </div>
                
                <!-- File path for reference -->
                <div style="margin-top: 15px; padding: 8px; background-color: #f1f3f4; border-radius: 4px; font-family: monospace; font-size: 11px; color: #5f6368; word-break: break-all;">
                    <strong>File path:</strong> {nifti_file}
                </div>
            </div>
        </div>
        """
    
    def _generate_mesh_visualization(self, mesh_file):
        """Generate mesh visualization.
        
        Args:
            mesh_file (str): Path to mesh file
            
        Returns:
            str: Base64 encoded image or HTML
        """
        try:
            # This would use SimNIBS mesh visualization tools
            # For now, return a placeholder
            return self._create_placeholder_visualization("Mesh Visualization")
        except Exception:
            return None
    
    def _create_placeholder_visualization(self, title):
        """Create a placeholder visualization.
        
        Args:
            title (str): Title for the placeholder
            
        Returns:
            str: Base64 encoded placeholder image
        """
        # Create a simple SVG placeholder
        svg_content = f'''
        <svg width="400" height="300" xmlns="http://www.w3.org/2000/svg">
            <rect width="400" height="300" fill="#f0f0f0" stroke="#ccc" stroke-width="2"/>
            <text x="200" y="150" text-anchor="middle" font-family="Arial" font-size="16" fill="#666">
                {title}
            </text>
            <text x="200" y="180" text-anchor="middle" font-family="Arial" font-size="12" fill="#999">
                (Visualization placeholder)
            </text>
        </svg>
        '''
        return base64.b64encode(svg_content.encode()).decode()
    
    def generate_report(self, output_path=None):
        """Generate the HTML simulation report.
        
        Args:
            output_path (str): Path where to save the report. If None, saves to derivatives.
        
        Returns:
            str: Path to the generated report
        """
        # Scan for simulation outputs for all subjects before generating HTML
        for subject_data in self.report_data['subjects']:
            if subject_data.get('m2m_path') and os.path.exists(subject_data['m2m_path']):
                subject_data['simulation_outputs'] = self._scan_simulation_outputs(subject_data['subject_id'], subject_data['m2m_path'])
                subject_data['t1_path'] = self._find_t1_file(subject_data['m2m_path'])

        if output_path is None:
            # Use standardized path: project_dir/derivatives/reports/sub-subjectID/simulation_report_date_time.html
            # For single subject, or project_dir/derivatives/reports/simulation_session_ID.html for multi-subject
            if len(self.report_data['subjects']) == 1:
                # Single subject report
                subject_id = self.report_data['subjects'][0]['subject_id']
                bids_subject_id = f"sub-{subject_id}"
                reports_dir = self.project_dir / "derivatives" / "reports" / bids_subject_id
                reports_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = reports_dir / f"simulation_report_{timestamp}.html"
            else:
                # Multi-subject or session report
                reports_dir = self.project_dir / "derivatives" / "reports"
                reports_dir.mkdir(parents=True, exist_ok=True)
                output_path = reports_dir / f"simulation_session_{self.simulation_session_id}.html"
        
        # Set the report directory for Papaya resource management
        self._current_report_dir = str(Path(output_path).parent)
        
        # Generate HTML content
        html_content = self._generate_html_content()
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return str(output_path)
    
    def generate_html_report(self, output_path=None):
        """Alias for generate_report for backward compatibility."""
        return self.generate_report(output_path)
    
    def _generate_html_content(self):
        """Generate the HTML content for the simulation report."""
        
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TI-CSC Simulation Report - Session {simulation_session_id}</title>
    <style>
        {css_styles}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>TI-CSC Simulation Report</h1>
            <h2>Session: {simulation_session_id}</h2>
            <p class="timestamp">Generated on: {generation_time}</p>
        </header>
        
        <nav class="toc">
            <h3>Table of Contents</h3>
            <ul>
                <li><a href="#summary">Summary</a></li>
                <li><a href="#simulation-parameters">Simulation Parameters</a></li>
                <li><a href="#subjects">Subjects</a></li>
                <li><a href="#montages">Montages</a></li>
                <li><a href="#results">Simulation Results</a></li>
                <li><a href="#visualizations">Interactive Brain Visualizations</a></li>
                <li><a href="#server-setup">Local Server Setup</a></li>
                <li><a href="#software-info">Software Information</a></li>
                <li><a href="#methods">Methods</a></li>
                <li><a href="#errors-warnings">Errors and Warnings</a></li>
            </ul>
        </nav>
        
        <main>
            {summary_section}
            {simulation_parameters_section}
            {subjects_section}
            {montages_section}
            {results_section}
            {visualizations_section}
            {server_setup_section}
            {software_section}
            {methods_section}
            {errors_warnings_section}
        </main>
        
        <footer>
            <p>Report generated by TI-CSC 2.0 Simulation Pipeline</p>
            <p>For questions or issues, please refer to the TI-CSC documentation.</p>
        </footer>
    </div>
    
    <!-- Copy to clipboard functionality -->
    <script>
        function copyToClipboard(text) {{
            navigator.clipboard.writeText(text).then(function() {{
                // Create temporary success notification
                const notification = document.createElement('div');
                notification.textContent = '✅ Copied to clipboard!';
                notification.style.cssText = `
                    position: fixed; top: 20px; right: 20px; 
                    background: #28a745; color: white; 
                    padding: 10px 15px; border-radius: 6px; 
                    font-size: 14px; z-index: 1000;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                `;
                document.body.appendChild(notification);
                setTimeout(() => notification.remove(), 2000);
            }}).catch(function(err) {{
                console.error('Could not copy text: ', err);
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = text;
                document.body.appendChild(textArea);
                textArea.select();
                document.execCommand('copy');
                document.body.removeChild(textArea);
                alert('Copied to clipboard!');
            }});
        }}
    </script>
    
    <!-- Papaya Integration CSS -->
    <style>
        .papaya-container {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        
        .papaya-fallback {{
            transition: all 0.3s ease;
        }}
        
        .papaya-fallback:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        canvas {{
            image-rendering: -webkit-optimize-contrast;
            image-rendering: crisp-edges;
        }}
    </style>
    
    <script>
        {javascript_code}
    </script>
</body>
</html>
""".format(
            simulation_session_id=self.simulation_session_id,
            generation_time=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            css_styles=self._get_css_styles(),
            summary_section=self._generate_summary_section(),
            simulation_parameters_section=self._generate_simulation_parameters_section(),
            subjects_section=self._generate_subjects_section(),
            montages_section=self._generate_montages_section(),
            results_section=self._generate_results_section(),
            visualizations_section=self._generate_visualizations_section(),
            server_setup_section=self._generate_server_setup_section(),
            software_section=self._generate_software_section(),
            methods_section=self._generate_methods_section(),
            errors_warnings_section=self._generate_errors_warnings_section(),
            javascript_code=self._get_javascript()
        )
        return html.strip()
    
    def _get_css_styles(self):
        """Return CSS styles for the HTML report."""
        return """
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }
        
        header h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        
        header h2 {
            font-size: 1.5rem;
            font-weight: 300;
            margin-bottom: 1rem;
        }
        
        .timestamp {
            font-size: 0.9rem;
            opacity: 0.9;
        }
        
        .toc {
            background-color: #f8f9fa;
            padding: 1.5rem;
            border-bottom: 1px solid #dee2e6;
        }
        
        .toc h3 {
            margin-bottom: 1rem;
            color: #495057;
        }
        
        .toc ul {
            list-style: none;
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
        }
        
        .toc a {
            color: #007bff;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            transition: background-color 0.3s;
        }
        
        .toc a:hover {
            background-color: #e9ecef;
        }
        
        main {
            padding: 2rem;
        }
        
        .section {
            margin-bottom: 3rem;
        }
        
        .section h2 {
            color: #495057;
            border-bottom: 2px solid #007bff;
            padding-bottom: 0.5rem;
            margin-bottom: 1.5rem;
        }
        
        .section h3 {
            color: #6c757d;
            margin: 1.5rem 0 1rem 0;
        }
        
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        
        .info-card {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 1.5rem;
        }
        
        .info-card h4 {
            color: #495057;
            margin-bottom: 1rem;
        }
        
        .parameter-table {
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
        }
        
        .parameter-table th,
        .parameter-table td {
            border: 1px solid #dee2e6;
            padding: 0.75rem;
            text-align: left;
        }
        
        .parameter-table th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        
        .status-completed {
            color: #28a745;
            font-weight: bold;
        }
        
        .status-failed {
            color: #dc3545;
            font-weight: bold;
        }
        
        .status-skipped {
            color: #6c757d;
            font-weight: bold;
        }
        
        .montage-card {
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin-bottom: 1rem;
            overflow: hidden;
        }
        
        .montage-header {
            background-color: #e9ecef;
            padding: 1rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .montage-content {
            padding: 1rem;
            display: none;
        }
        
        .montage-content.active {
            display: block;
        }
        
        .electrode-pairs {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 0.5rem;
            margin: 1rem 0;
        }
        
        .electrode-pair {
            background-color: #f8f9fa;
            padding: 0.5rem;
            border-radius: 4px;
            text-align: center;
            font-family: monospace;
        }
        
        .visualization-container {
            text-align: center;
            margin: 1rem 0;
        }
        
        .visualization-placeholder {
            background-color: #f8f9fa;
            border: 2px dashed #dee2e6;
            padding: 2rem;
            border-radius: 8px;
            color: #6c757d;
        }
        
        .montage-visualization {
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin-bottom: 2rem;
            padding: 1.5rem;
            background-color: #fafafa;
        }
        
        .montage-visualization h4 {
            color: #495057;
            margin-bottom: 1rem;
            border-bottom: 1px solid #dee2e6;
            padding-bottom: 0.5rem;
        }
        
        .montage-visualization h5 {
            color: #6c757d;
            margin: 1rem 0 0.5rem 0;
        }
        
        .montage-visualization h6 {
            color: #6c757d;
            margin: 0.5rem 0 0.25rem 0;
            font-size: 0.9rem;
        }
        
        .error {
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            padding: 1rem;
            border-radius: 4px;
            margin: 0.5rem 0;
        }
        
        .warning {
            background-color: #fff3cd;
            border: 1px solid #ffeaa7;
            color: #856404;
            padding: 1rem;
            border-radius: 4px;
            margin: 0.5rem 0;
        }
        
        .file-list {
            background-color: #f8f9fa;
            border-radius: 4px;
            padding: 1rem;
            margin: 0.5rem 0;
            max-height: 200px;
            overflow-y: auto;
        }
        
        .file-list ul {
            list-style: none;
        }
        
        .file-list li {
            padding: 0.25rem 0;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
        }
        
        footer {
            background-color: #343a40;
            color: white;
            text-align: center;
            padding: 2rem;
        }
        
        .boilerplate {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 1.5rem;
            margin: 1rem 0;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            line-height: 1.4;
        }
        
        /* Enhanced setup section styles */
        .setup-container {
            max-width: 1000px;
            margin: 0 auto;
        }
        
        .quick-solution {
            background: linear-gradient(135deg, #e8f5e8 0%, #d4f1d4 100%);
            border: 2px solid #4caf50;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 30px;
            position: relative;
        }
        
        .quick-solution::before {
            content: "🚀";
            position: absolute;
            top: -15px;
            left: 20px;
            background: #4caf50;
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-size: 16px;
        }
        
        .command-box {
            background: #2d2d2d;
            color: #f8f8f2;
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            font-family: 'Courier New', monospace;
            position: relative;
            border-left: 4px solid #4caf50;
        }
        
        .command-box .command {
            display: block;
            color: #a6e22e;
            font-weight: bold;
            margin-bottom: 10px;
            font-size: 14px;
        }
        
        .command-box button {
            position: absolute;
            right: 10px;
            top: 10px;
            background: #4caf50;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .command-box button:hover {
            background: #45a049;
        }
        
        .note {
            background: #f0f9ff;
            border-left: 4px solid #0ea5e9;
            padding: 12px;
            margin: 15px 0;
            border-radius: 4px;
            color: #0c4a6e;
            font-size: 14px;
            line-height: 1.6;
        }
        
        .alternative-methods {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 30px;
        }
        
        .method {
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .method h4 {
            margin-top: 0;
            color: #2c3e50;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .command-group {
            display: flex;
            flex-direction: column;
            gap: 10px;
        }
        
        .command-option {
            display: flex;
            align-items: center;
            gap: 15px;
            background: #f8f9fa;
            padding: 10px;
            border-radius: 6px;
            border-left: 3px solid #6c757d;
        }
        
        .command-option .version {
            font-weight: bold;
            color: #495057;
            min-width: 80px;
            font-size: 12px;
        }
        
        .command-option code {
            flex: 1;
            background: #2d2d2d;
            color: #a6e22e;
            padding: 8px 12px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }
        
        .command-option button {
            background: #6c757d;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 11px;
            min-width: 35px;
        }
        
        .command-option button:hover {
            background: #5a6268;
        }
        
        .instructions {
            background: #fff;
            border: 2px solid #e9ecef;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 30px;
        }
        
        .instructions ol {
            counter-reset: step-counter;
            list-style: none;
            padding-left: 0;
        }
        
        .instructions ol li {
            counter-increment: step-counter;
            margin-bottom: 20px;
            padding-left: 40px;
            position: relative;
        }
        
        .instructions ol li::before {
            content: counter(step-counter);
            position: absolute;
            left: 0;
            top: 0;
            background: #007bff;
            color: white;
            width: 25px;
            height: 25px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 12px;
        }
        
        .instructions kbd {
            background: #f8f9fa;
            border: 1px solid #dee2e6;
            border-radius: 3px;
            padding: 2px 6px;
            font-family: monospace;
            font-size: 12px;
            color: #495057;
        }
        
        .url-box {
            background: #e3f2fd;
            border: 1px solid #2196f3;
            border-radius: 6px;
            padding: 12px;
            margin: 10px 0;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .url-box code {
            flex: 1;
            background: #1976d2;
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-weight: bold;
        }
        
        .url-box button {
            background: #2196f3;
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .url-box button:hover {
            background: #1976d2;
        }
        
        .troubleshooting {
            background: #fff9c4;
            border: 2px solid #ffeb3b;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 30px;
        }
        
        .trouble-item {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 15px;
            border-left: 4px solid #ff9800;
        }
        
        .trouble-item h4 {
            margin-top: 0;
            color: #e65100;
        }
        
        .trouble-item code {
            background: #2d2d2d;
            color: #a6e22e;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }
        
        .file-protocol-warning {
            background: #fef7f0;
            border: 2px solid #ff9800;
            border-radius: 12px;
            padding: 25px;
            margin-bottom: 30px;
        }
        
        .file-protocol-warning h3 {
            color: #e65100;
            margin-top: 0;
        }
        
        .file-protocol-warning ul {
            list-style-type: none;
            padding-left: 0;
        }
        
        .file-protocol-warning li {
            padding: 5px 0;
            padding-left: 25px;
            position: relative;
        }
        
        .file-protocol-warning li::before {
            content: "✓";
            position: absolute;
            left: 0;
            color: #4caf50;
            font-weight: bold;
        }
        
        /* Responsive design */
        @media (max-width: 768px) {
            .setup-container {
                padding: 0 15px;
            }
            
            .command-option {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
            
            .command-option .version {
                min-width: auto;
            }
            
            .url-box {
                flex-direction: column;
                align-items: stretch;
            }
            
            .command-box button {
                position: static;
                margin-top: 10px;
                align-self: flex-start;
            }
        }
        """
    
    def _generate_summary_section(self):
        """Generate the summary section."""
        # Count subjects and montages
        total_subjects = len(self.report_data['subjects'])
        completed_subjects = len([s for s in self.report_data['subjects'] if s['status'] == 'completed'])
        total_montages = len(self.report_data['montages'])
        
        # Count simulation results
        total_simulations = len(self.report_data['simulation_results'])
        completed_simulations = len([r for r in self.report_data['simulation_results'].values() if r['status'] == 'completed'])
        
        return f"""
        <section id="summary" class="section">
            <h2>Summary</h2>
            <div class="info-grid">
                <div class="info-card">
                    <h4>Simulation Session</h4>
                    <p><strong>Session ID:</strong> {self.simulation_session_id}</p>
                    <p><strong>Project Directory:</strong> {self.project_dir}</p>
                    <p><strong>Generation Time:</strong> {self.report_data['generation_time']}</p>
                </div>
                <div class="info-card">
                    <h4>Subjects</h4>
                    <p><strong>Total subjects:</strong> {total_subjects}</p>
                    <p><strong>Completed:</strong> {completed_subjects}</p>
                    <p><strong>Failed/Skipped:</strong> {total_subjects - completed_subjects}</p>
                </div>
                <div class="info-card">
                    <h4>Montages</h4>
                    <p><strong>Total montages:</strong> {total_montages}</p>
                    <p><strong>Unipolar:</strong> {len([m for m in self.report_data['montages'] if m['type'] == 'unipolar'])}</p>
                    <p><strong>Multipolar:</strong> {len([m for m in self.report_data['montages'] if m['type'] == 'multipolar'])}</p>
                </div>
                <div class="info-card">
                    <h4>Simulation Results</h4>
                    <p><strong>Total simulations:</strong> {total_simulations}</p>
                    <p><strong>Completed:</strong> {completed_simulations}</p>
                    <p><strong>Errors:</strong> {len(self.report_data['errors'])}</p>
                    <p><strong>Warnings:</strong> {len(self.report_data['warnings'])}</p>
                </div>
            </div>
        </section>
        """
    
    def _generate_simulation_parameters_section(self):
        """Generate the simulation parameters section."""
        params = self.report_data['simulation_parameters']
        electrode_params = self.report_data['electrode_parameters']
        
        if not params:
            return """
            <section id="simulation-parameters" class="section">
                <h2>Simulation Parameters</h2>
                <p>No simulation parameters recorded.</p>
            </section>
            """
        
        return f"""
        <section id="simulation-parameters" class="section">
            <h2>Simulation Parameters</h2>
            
            <h3>General Parameters</h3>
            <table class="parameter-table">
                <tr><th>Parameter</th><th>Value</th></tr>
                <tr><td>Conductivity Type</td><td>{params.get('conductivity_type', 'N/A')}</td></tr>
                <tr><td>Simulation Mode</td><td>{params.get('simulation_mode_text', 'N/A')} ({params.get('simulation_mode', 'N/A')})</td></tr>
                <tr><td>EEG Net</td><td>{params.get('eeg_net', 'N/A')}</td></tr>
                <tr><td>Current Channel 1</td><td>{params.get('intensity_ch1_ma', 'N/A')} mA ({params.get('intensity_ch1_a', 'N/A')} A)</td></tr>
                <tr><td>Current Channel 2</td><td>{params.get('intensity_ch2_ma', 'N/A')} mA ({params.get('intensity_ch2_a', 'N/A')} A)</td></tr>
                <tr><td>Quiet Mode</td><td>{'Yes' if params.get('quiet_mode', False) else 'No'}</td></tr>
            </table>
            
            {self._generate_electrode_parameters_table(electrode_params)}
            {self._generate_conductivity_parameters_table(params.get('conductivities', {}))}
        </section>
        """
    
    def _generate_electrode_parameters_table(self, electrode_params):
        """Generate electrode parameters table."""
        if not electrode_params:
            return "<h3>Electrode Parameters</h3><p>No electrode parameters recorded.</p>"
        
        return f"""
        <h3>Electrode Parameters</h3>
        <table class="parameter-table">
            <tr><th>Parameter</th><th>Value</th></tr>
            <tr><td>Shape</td><td>{electrode_params.get('shape', 'N/A')}</td></tr>
            <tr><td>Dimensions</td><td>{electrode_params.get('dimensions', 'N/A')} mm</td></tr>
            <tr><td>Thickness</td><td>{electrode_params.get('thickness', 'N/A')} mm</td></tr>
            <tr><td>Electrode Area</td><td>{electrode_params.get('area_mm2', 'N/A'):.2f} mm²</td></tr>
        </table>
        """
    
    def _generate_conductivity_parameters_table(self, conductivities):
        """Generate tissue conductivity parameters table."""
        if not conductivities:
            return "<h3>Tissue Conductivities</h3><p>No conductivity parameters recorded.</p>"
        
        html = """
        <h3>Tissue Conductivities</h3>
        <table class="parameter-table">
            <tr><th>Tissue #</th><th>Tissue Name</th><th>Conductivity (S/m)</th><th>Reference</th></tr>
        """
        
        # Sort by tissue number
        sorted_tissues = sorted(conductivities.items(), key=lambda x: int(x[0]))
        
        for tissue_num, tissue_info in sorted_tissues:
            if isinstance(tissue_info, dict):
                name = tissue_info.get('name', f'Tissue {tissue_num}')
                conductivity = tissue_info.get('conductivity', 'N/A')
                reference = tissue_info.get('reference', 'Default')
            else:
                # Handle case where conductivity is just a number (backward compatibility)
                name = f'Tissue {tissue_num}'
                conductivity = tissue_info
                reference = 'Custom'
            
            html += f"""
            <tr>
                <td>{tissue_num}</td>
                <td>{name}</td>
                <td>{conductivity}</td>
                <td style="font-size: 0.85em;">{reference}</td>
            </tr>
            """
        
        html += "</table>"
        return html
    
    def _generate_subjects_section(self):
        """Generate the subjects section."""
        html = """
        <section id="subjects" class="section">
            <h2>Subjects</h2>
        """
        
        if not self.report_data['subjects']:
            html += "<p>No subjects processed.</p>"
        else:
            for subject in self.report_data['subjects']:
                status_class = f"status-{subject['status']}"
                html += f"""
                <div class="info-card">
                    <h4>{subject['bids_subject_id']} <span class="{status_class}">{subject['status'].upper()}</span></h4>
                    <p><strong>Subject ID:</strong> {subject['subject_id']}</p>
                    <p><strong>m2m Path:</strong> {subject.get('m2m_path', 'N/A')}</p>
                    <p><strong>Simulation Outputs:</strong> {len(subject.get('simulation_outputs', []))} montage(s)</p>
                </div>
                """
        
        html += "</section>"
        return html
    
    def _generate_montages_section(self):
        """Generate the montages section."""
        html = """
        <section id="montages" class="section">
            <h2>Montages</h2>
        """
        
        if not self.report_data['montages']:
            html += "<p>No montages configured.</p>"
        else:
            for i, montage in enumerate(self.report_data['montages']):
                html += f"""
                <div class="montage-card">
                    <div class="montage-header" onclick="toggleMontage({i})">
                        <h4>{montage['name']} ({montage['type']})</h4>
                        <span>{montage['num_pairs']} pair(s)</span>
                    </div>
                    <div class="montage-content" id="montage-{i}">
                        <p><strong>Type:</strong> {montage['type'].title()}</p>
                        <p><strong>Number of electrode pairs:</strong> {montage['num_pairs']}</p>
                        <p><strong>Electrodes used:</strong> {', '.join(montage['electrodes_used'])}</p>
                        
                        <h5>Electrode Pairs:</h5>
                        <div class="electrode-pairs">
                """
                
                for j, pair in enumerate(montage['electrode_pairs']):
                    html += f"""
                    <div class="electrode-pair">
                        Pair {j+1}: {pair[0]} ↔ {pair[1]}
                    </div>
                    """
                
                html += """
                        </div>
                    </div>
                </div>
                """
        
        html += "</section>"
        return html
    
    def _generate_results_section(self):
        """Generate the simulation results section."""
        html = """
        <section id="results" class="section">
            <h2>Simulation Results</h2>
        """
        
        if not self.report_data['simulation_results']:
            html += "<p>No simulation results available.</p>"
        else:
            for result_key, result in self.report_data['simulation_results'].items():
                status_class = f"status-{result['status']}"
                duration_text = f"{result['duration']:.2f}s" if result['duration'] else "N/A"
                
                html += f"""
                <div class="info-card">
                    <h4>{result['subject_id']} - {result['montage_name']} <span class="{status_class}">{result['status'].upper()}</span></h4>
                    <p><strong>Duration:</strong> {duration_text}</p>
                    <p><strong>Output files:</strong></p>
                    <div class="file-list">
                        <ul>
                """
                
                for file_type, files in result.get('output_files', {}).items():
                    if isinstance(files, list):
                        for file_path in files:
                            html += f"<li>{file_type}: {os.path.basename(file_path)}</li>"
                    else:
                        html += f"<li>{file_type}: {files}</li>"
                
                html += """
                        </ul>
                    </div>
                </div>
                """
        
        html += "</section>"
        return html
    
    def _generate_visualizations_section(self):
        """Generate the interactive brain visualizations section."""
        html = """
        <section id="visualizations" class="section">
            <h2>Interactive Brain Visualizations</h2>
            <p>This section contains interactive 3D brain visualizations powered by Papaya viewer. 
               Each subject has one comprehensive viewer with all available field distributions.</p>
            
            <!-- Global Instructions -->
            <div style="background-color: #e3f2fd; padding: 20px; border-radius: 8px; margin-bottom: 30px; border: 1px solid #2196f3;">
                <h3 style="color: #1976d2; margin-top: 0;">🎯 How to Use the Viewers:</h3>
                <ol style="color: #1976d2; margin: 10px 0; padding-left: 20px; font-size: 15px;">
                    <li><strong>Right-click</strong> in any viewer area</li>
                    <li><strong>Select "Change Image"</strong> from the context menu</li>
                    <li><strong>Browse and select</strong> files from your file system</li>
                    <li><strong>Repeat</strong> to load additional images as overlays</li>
                </ol>
                <div style="background-color: #fff3cd; padding: 12px; border-radius: 6px; margin-top: 15px; border: 1px solid #ffeaa7;">
                    <p style="color: #856404; margin: 0; font-size: 14px;">
                        💡 <strong>Recommended workflow:</strong> Load T1 reference first, then add field overlays one by one to compare montages.
                    </p>
                </div>
            </div>
        """
        
        visualizations_found = False
        
        # Generate one viewer per subject with all their NIfTI files
        for subject in self.report_data['subjects']:
            subject_id = subject['subject_id']
            simulation_outputs = subject.get('simulation_outputs', [])
            t1_path = subject.get('t1_path')
            
            if simulation_outputs:
                # Collect all NIfTI files for this subject across all montages
                all_nifti_files = []
                all_labels = []
                montage_info = []
                
                for montage_output in simulation_outputs:
                    montage_name = montage_output['montage_name']
                    nifti_visualizations = montage_output.get('nifti_visualizations', [])
                    
                    if nifti_visualizations:
                        montage_info.append(montage_name)
                        for nifti_file in nifti_visualizations:
                            if os.path.exists(nifti_file):
                                all_nifti_files.append(nifti_file)
                                basename = os.path.basename(nifti_file)
                                if 'ti_max' in basename.lower():
                                    all_labels.append(f"{montage_name} - TI Max")
                                elif 'grey' in basename.lower():
                                    all_labels.append(f"{montage_name} - Grey Matter")
                                elif 'white' in basename.lower():
                                    all_labels.append(f"{montage_name} - White Matter")
                                else:
                                    all_labels.append(f"{montage_name} - Field")
                
                if all_nifti_files:
                    html += f"""
                    <h3>Subject {subject_id}</h3>
                    <div style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; margin-bottom: 30px;">
                        <p style="color: #6c757d; margin-bottom: 15px; font-size: 14px;">
                            <strong>Available montages:</strong> {', '.join(montage_info)} | 
                            <strong>Files ready:</strong> T1 + {len(all_nifti_files)} field distributions
                        </p>
                    """
                    
                    # Create one comprehensive viewer for all files from this subject
                    if t1_path and os.path.exists(t1_path):
                        try:
                            viewer_name = f"subject_{subject_id}"
                            viz_html = self._generate_subject_nifti_viewer(
                                subject_id=subject_id,
                                t1_file=t1_path,
                                nifti_files=all_nifti_files,
                                labels=all_labels,
                                viewer_name=viewer_name
                            )
                            if viz_html:
                                html += viz_html
                                visualizations_found = True
                        except Exception as e:
                            html += f"""
                            <div class="error">
                                <strong>Error generating viewer for subject {subject_id}:</strong> {str(e)}
                            </div>
                            """
                    else:
                        html += f"""
                        <div style="margin: 10px 0; padding: 15px; background-color: #e3f2fd; border-radius: 8px; border: 1px solid #2196f3;">
                            <h6 style="color: #1976d2; margin-bottom: 10px;">📊 NIfTI Files Available</h6>
                            <p style="color: #1976d2; margin: 0; font-size: 14px;">
                                <strong>Files:</strong> {len(all_nifti_files)} field distributions<br>
                                <strong>Note:</strong> T1 reference not available for interactive viewing.<br>
                                <em>The interactive viewer works best with both T1 structural and overlay data.</em>
                            </p>
                        </div>
                        """
                    
                    html += "</div>"  # Close subject container
        
        # Show placeholder if no visualizations found
        if not visualizations_found:
            html += """
            <div class="visualization-placeholder">
                <h3>Interactive Brain Visualizations</h3>
                <p>No simulation visualizations found. Visualizations will be generated automatically when simulation results are available.</p>
                <p>Expected visualizations include:</p>
                <ul>
                    <li><strong>Interactive electrode placement maps</strong> (montage_imgs/*.png)</li>
                    <li><strong>3D electric field distribution maps</strong> (niftis/*_TI_max.nii.gz) - <em>Interactive with Papaya viewer</em></li>
                    <li><strong>Temporal interference patterns</strong> - <em>One viewer per subject with all montages</em></li>
                    <li><strong>Cross-sectional views</strong> - <em>Load any combination of field files</em></li>
                </ul>
                <div style="background-color: #e3f2fd; padding: 15px; border-radius: 8px; margin-top: 15px;">
                    <p style="color: #1976d2; margin: 0; font-size: 14px;">
                        💡 <strong>Note:</strong> When visualizations are available, you'll have one comprehensive viewer per subject where you can:
                    </p>
                    <ul style="color: #1976d2; margin: 10px 0 0 20px; font-size: 14px;">
                        <li>Load images selectively from the File menu dropdown</li>
                        <li>Compare multiple montages side-by-side with overlays</li>
                        <li>Navigate through brain slices and adjust visualization parameters</li>
                        <li>Switch between different field distributions for the same subject</li>
                    </ul>
                </div>
            </div>
            """
        
        html += "</section>"
        return html
    
    def _generate_server_setup_section(self):
        """Generate setup section for local web server (for better file access)."""
        return """
        <section id="server-setup" class="section">
            <div class="server-setup-section" style="margin: 20px 0; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 12px; padding: 20px; color: white;">
                <div style="display: flex; align-items: center; margin-bottom: 15px;">
                    <div style="font-size: 28px; margin-right: 15px;">🧠</div>
                    <div>
                        <h4 style="margin: 0; color: white;">Interactive Brain Visualization</h4>
                        <p style="margin: 5px 0 0 0; opacity: 0.9; font-size: 14px;">
                            Powered by Papaya - Self-contained viewers ready to use
                        </p>
                    </div>
                </div>
            </div>
        </section>
        """
    
    def _generate_software_section(self):
        """Generate the software information section."""
        html = """
        <section id="software-info" class="section">
            <h2>Software Information</h2>
            <div class="info-card">
                <h4>Software Versions</h4>
        """
        
        if self.report_data['software_versions']:
            for software, version in self.report_data['software_versions'].items():
                html += f"<p><strong>{software.replace('_', ' ').title()}:</strong> {version}</p>"
        else:
            html += "<p>Software version information not available.</p>"
        
        html += """
            </div>
        </section>
        """
        return html
    
    def _generate_methods_section(self):
        """Generate the methods section with boilerplate text."""
        params = self.report_data['simulation_parameters']
        
        html = """
        <section id="methods" class="section">
            <h2>Methods</h2>
            <p>We kindly ask to report results from simulations performed with this tool using the following boilerplate.</p>
            
            <h3>Boilerplate Text</h3>
            <div class="boilerplate">
Electromagnetic field simulations were performed using the TI-CSC 2.0 
(Transcranial Stimulation Computational Suite), which integrates SimNIBS 
for finite element modeling of transcranial electrical stimulation.

"""
        
        # Add specific methods based on simulation parameters
        if params:
            conductivity_type = params.get('conductivity_type', 'scalar')
            sim_mode = params.get('simulation_mode_text', 'Unipolar')
            
            if conductivity_type == 'scalar':
                html += """Head models used isotropic conductivity values for different tissue types. """
            else:
                html += """Head models incorporated anisotropic conductivity based on diffusion tensor imaging (DTI) data. """
            
            if sim_mode == 'Unipolar':
                html += """Temporal interference (TI) stimulation was simulated using two pairs of electrodes 
in unipolar configuration. """
            else:
                html += """Multi-electrode temporal interference (mTI) stimulation was simulated using four pairs 
of electrodes in multipolar configuration. """
            
            html += f"""Electrode positions were defined using the {params.get('eeg_net', 'standard')} electrode 
positioning system. """
        
        html += """
The finite element method was used to solve Laplace's equation for the electric potential 
distribution in the head model. Electric field distributions and temporal interference 
patterns were calculated and analyzed using custom analysis pipelines.

All simulations were performed using SimNIBS (www.simnibs.org) with head models derived 
from individual anatomical MRI data processed through the TI-CSC preprocessing pipeline.
            </div>
        </section>
        """
        return html
    
    def _generate_errors_warnings_section(self):
        """Generate the errors and warnings section."""
        html = """
        <section id="errors-warnings" class="section">
            <h2>Errors and Warnings</h2>
        """
        
        if not self.report_data['errors'] and not self.report_data['warnings']:
            html += "<p>No errors or warnings to report!</p>"
        else:
            if self.report_data['errors']:
                html += "<h3>Errors</h3>"
                for error in self.report_data['errors']:
                    context = ""
                    if error.get('subject_id'):
                        context += f" (Subject: {error['subject_id']}"
                        if error.get('montage_name'):
                            context += f", Montage: {error['montage_name']}"
                        context += ")"
                    
                    html += f"""
                    <div class="error">
                        <strong>Error{context}:</strong> {error['message']}
                        <br><small>Time: {error['timestamp']}</small>
                    </div>
                    """
            
            if self.report_data['warnings']:
                html += "<h3>Warnings</h3>"
                for warning in self.report_data['warnings']:
                    context = ""
                    if warning.get('subject_id'):
                        context += f" (Subject: {warning['subject_id']}"
                        if warning.get('montage_name'):
                            context += f", Montage: {warning['montage_name']}"
                        context += ")"
                    
                    html += f"""
                    <div class="warning">
                        <strong>Warning{context}:</strong> {warning['message']}
                        <br><small>Time: {warning['timestamp']}</small>
                    </div>
                    """
        
        html += "</section>"
        return html
    
    def _get_javascript(self):
        """Return JavaScript for interactive elements."""
        return """
        function toggleMontage(index) {
            const content = document.getElementById('montage-' + index);
            content.classList.toggle('active');
        }
        
        function toggleSection(sectionId) {
            const section = document.getElementById(sectionId);
            if (section) {
                section.style.display = section.style.display === 'none' ? 'block' : 'none';
            }
        }
        """
    
    def _generate_subject_nifti_viewer(self, subject_id, t1_file, nifti_files, labels, viewer_name):
        """Generate HTML for a simple, empty Papaya viewer for a subject with all their files.
        
        Args:
            subject_id (str): Subject ID
            t1_file (str): Path to T1 structural file
            nifti_files (list): List of all NIfTI field files for this subject
            labels (list): Labels for each field file
            viewer_name (str): Name for this viewer
            
        Returns:
            str: HTML content for the empty interactive visualization
        """
        try:
            # Import papaya utilities
            from .papaya_utils import create_papaya_viewer
            
            # Get the report directory
            if hasattr(self, '_current_report_dir'):
                report_dir = self._current_report_dir
            else:
                import tempfile
                report_dir = tempfile.gettempdir()
            
            # Create the empty viewer with all files available in dropdown
            viewer_html = create_papaya_viewer(
                report_dir=report_dir,
                viewer_name=viewer_name,
                t1_file=t1_file,
                field_files=nifti_files,
                labels=labels
            )
            
            return viewer_html
                
        except ImportError:
            return self._generate_papaya_installation_guide(nifti_files[0] if nifti_files else "")
        except Exception as e:
            return f"""
            <div style="margin: 10px 0; padding: 15px; background-color: #fff3cd; border-radius: 8px; border: 1px solid #ffeaa7;">
                <h6 style="color: #856404; margin-bottom: 10px;">⚠️ Viewer Creation Error</h6>
                <p style="color: #856404; margin: 0; font-size: 14px;">
                    <strong>Subject:</strong> {subject_id}<br>
                    <strong>Error:</strong> {str(e)}<br>
                    <strong>Files available:</strong> {len(nifti_files)} field files + T1 reference
                </p>
            </div>
            """
    
    def _generate_file_instruction_list(self, labels):
        """Generate HTML list items for file loading instructions."""
        return "\n".join([f"<li>🧠 <strong>{label}</strong></li>" for label in labels])


def create_simulation_report(project_dir, simulation_session_id=None, simulation_log=None):
    """Convenience function to create a simulation report.
    
    Args:
        project_dir (str): Path to the project directory
        simulation_session_id (str): Unique identifier for this simulation session
        simulation_log (dict): Optional simulation log with detailed information
    
    Returns:
        str: Path to the generated report
    """
    generator = SimulationReportGenerator(project_dir, simulation_session_id)
    
    # If simulation log is provided, add the information
    if simulation_log:
        # Add simulation parameters
        if 'parameters' in simulation_log:
            params = simulation_log['parameters']
            generator.add_simulation_parameters(
                params.get('conductivity_type', 'scalar'),
                params.get('simulation_mode', 'U'),
                params.get('eeg_net', 'EGI_template.csv'),
                params.get('intensity_ch1_ma', 0),
                params.get('intensity_ch2_ma', 0),
                params.get('quiet_mode', False)
            )
        
        # Add electrode parameters
        if 'electrode_parameters' in simulation_log:
            electrode_params = simulation_log['electrode_parameters']
            generator.add_electrode_parameters(
                electrode_params.get('shape', 'rect'),
                electrode_params.get('dimensions', [50, 50]),
                electrode_params.get('thickness', 4)
            )
        
        # Add subjects
        for subject in simulation_log.get('subjects', []):
            generator.add_subject(**subject)
        
        # Add montages
        for montage in simulation_log.get('montages', []):
            generator.add_montage(**montage)
        
        # Add results
        for result_key, result in simulation_log.get('results', {}).items():
            generator.add_simulation_result(**result)
        
        # Add errors and warnings
        for error in simulation_log.get('errors', []):
            generator.add_error(**error)
        
        for warning in simulation_log.get('warnings', []):
            generator.add_warning(**warning)
    
    return generator.generate_report() 