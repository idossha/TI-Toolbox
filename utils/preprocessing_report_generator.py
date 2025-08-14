#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 Report Generator
This module generates comprehensive HTML reports for preprocessing pipelines,
similar to fMRIPrep reports, documenting all steps, parameters, and outputs.
"""

import os
import json
import shutil
import datetime
import subprocess
import glob
from pathlib import Path
import base64

class PreprocessingReportGenerator:
    """Generate comprehensive HTML reports for preprocessing pipelines."""
    
    def __init__(self, project_dir, subject_id):
        """Initialize the report generator.
        
        Args:
            project_dir (str): Path to the project directory
            subject_id (str): Subject ID (without 'sub-' prefix)
        """
        self.project_dir = Path(project_dir)
        self.subject_id = subject_id
        self.bids_subject_id = f"sub-{subject_id}"
        
        # Initialize report data structure
        self.report_data = {
            'subject_id': subject_id,
            'bids_subject_id': self.bids_subject_id,
            'generation_time': datetime.datetime.now().isoformat(),
            'project_dir': str(project_dir),
            'processing_steps': [],
            'input_data': {},
            'output_data': {},
            'parameters': {},
            'errors': [],
            'warnings': [],
            'software_versions': {},
            'figures': []
        }
        
        # Collect software versions
        self._collect_software_versions()
    
    def _collect_software_versions(self):
        """Collect versions of software used in the pipeline."""
        try:
            # FreeSurfer version
            result = subprocess.run(['freesurfer', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.report_data['software_versions']['freesurfer'] = result.stdout.strip()
        except:
            pass
        
        try:
            # SimNIBS version
            result = subprocess.run(['simnibs_python', '-c', 'import simnibs; print(simnibs.__version__)'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                self.report_data['software_versions']['simnibs'] = result.stdout.strip()
        except:
            pass
        
        try:
            # dcm2niix version
            result = subprocess.run(['dcm2niix', '-h'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                # Extract version from help output
                for line in result.stdout.split('\n'):
                    if 'version' in line.lower():
                        self.report_data['software_versions']['dcm2niix'] = line.strip()
                        break
        except:
            pass
    
    def add_processing_step(self, step_name, description, parameters=None, status='completed', 
                          duration=None, output_files=None, figures=None):
        """Add a processing step to the report.
        
        Args:
            step_name (str): Name of the processing step
            description (str): Description of what the step does
            parameters (dict): Parameters used for this step
            status (str): Status of the step ('completed', 'failed', 'skipped')
            duration (float): Duration in seconds
            output_files (list): List of output files created
            figures (list): List of figure files for visualization
        """
        step = {
            'name': step_name,
            'description': description,
            'parameters': parameters or {},
            'status': status,
            'duration': duration,
            'output_files': output_files or [],
            'figures': figures or [],
            'timestamp': datetime.datetime.now().isoformat()
        }
        self.report_data['processing_steps'].append(step)
    
    def add_input_data(self, data_type, file_paths, metadata=None):
        """Add input data information to the report.
        
        Args:
            data_type (str): Type of input data (e.g., 'T1w', 'T2w', 'DICOM')
            file_paths (list): List of input file paths
            metadata (dict): Additional metadata about the input
        """
        self.report_data['input_data'][data_type] = {
            'files': file_paths,
            'count': len(file_paths),
            'metadata': metadata or {}
        }
    
    def add_output_data(self, data_type, file_paths, metadata=None):
        """Add output data information to the report.
        
        Args:
            data_type (str): Type of output data
            file_paths (list): List of output file paths
            metadata (dict): Additional metadata about the output
        """
        self.report_data['output_data'][data_type] = {
            'files': file_paths,
            'count': len(file_paths),
            'metadata': metadata or {}
        }
    
    def add_error(self, error_message, step=None):
        """Add an error to the report.
        
        Args:
            error_message (str): Error message
            step (str): Processing step where error occurred
        """
        self.report_data['errors'].append({
            'message': error_message,
            'step': step,
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    def add_warning(self, warning_message, step=None):
        """Add a warning to the report.
        
        Args:
            warning_message (str): Warning message
            step (str): Processing step where warning occurred
        """
        self.report_data['warnings'].append({
            'message': warning_message,
            'step': step,
            'timestamp': datetime.datetime.now().isoformat()
        })
    
    def scan_for_data(self):
        """Automatically scan project directory for input and output data."""
        # Scan for input data
        self._scan_input_data()
        
        # Scan for output data
        self._scan_output_data()
    
    def _scan_input_data(self):
        """Scan for input data in sourcedata directory."""
        sourcedata_dir = self.project_dir / "sourcedata" / self.bids_subject_id
        
        if sourcedata_dir.exists():
            # Check for T1w data
            t1w_dir = sourcedata_dir / "T1w"
            if t1w_dir.exists():
                t1w_files = list(t1w_dir.rglob("*"))
                t1w_files = [f for f in t1w_files if f.is_file()]
                if t1w_files:
                    self.add_input_data('T1w', [str(f) for f in t1w_files])
            
            # Check for T2w data
            t2w_dir = sourcedata_dir / "T2w"
            if t2w_dir.exists():
                t2w_files = list(t2w_dir.rglob("*"))
                t2w_files = [f for f in t2w_files if f.is_file()]
                if t2w_files:
                    self.add_input_data('T2w', [str(f) for f in t2w_files])
            
            # Check for compressed DICOM files
            dicom_files = list(sourcedata_dir.glob("*.tgz"))
            if dicom_files:
                self.add_input_data('DICOM_compressed', [str(f) for f in dicom_files])
    
    def _scan_output_data(self):
        """Scan for output data in various directories."""
        # NIfTI outputs
        nifti_dir = self.project_dir / self.bids_subject_id / "anat"
        if nifti_dir.exists():
            nifti_files = list(nifti_dir.glob("*.nii*"))
            if nifti_files:
                self.add_output_data('NIfTI', [str(f) for f in nifti_files])
        
        # FreeSurfer outputs
        fs_dir = self.project_dir / "derivatives" / "freesurfer" / self.bids_subject_id
        if fs_dir.exists():
            # Key FreeSurfer files
            key_files = []
            for pattern in ["mri/T1.mgz", "mri/brain.mgz", "surf/lh.pial", "surf/rh.pial", 
                           "surf/lh.white", "surf/rh.white", "scripts/recon-all.log"]:
                files = list(fs_dir.glob(pattern))
                key_files.extend([str(f) for f in files])
            if key_files:
                self.add_output_data('FreeSurfer', key_files)
        
        # SimNIBS m2m outputs
        simnibs_dir = self.project_dir / "derivatives" / "SimNIBS" / self.bids_subject_id / f"m2m_{self.subject_id}"
        if simnibs_dir.exists():
            # Key SimNIBS files
            key_files = []
            for pattern in ["*.msh", "eeg_positions/*.csv", "segmentation/*.annot", "charm_report.html"]:
                files = list(simnibs_dir.rglob(pattern))
                key_files.extend([str(f) for f in files])
            if key_files:
                self.add_output_data('SimNIBS_m2m', key_files)
        
        # Atlas segmentation outputs
        if simnibs_dir.exists():
            seg_dir = simnibs_dir / "segmentation"
            if seg_dir.exists():
                annot_files = list(seg_dir.glob("*.annot"))
                if annot_files:
                    self.add_output_data('Atlas_segmentation', [str(f) for f in annot_files])
    
    def generate_html_report(self, output_path=None):
        """Generate the HTML report.
        
        Args:
            output_path (str): Path where to save the report. If None, saves to derivatives.
        
        Returns:
            str: Path to the generated report
        """
        if output_path is None:
            # Use standardized path: project_dir/derivatives/ti-toolbox/reports/sub-subjectID/pre_processing_report_date_time.html
            base_reports_dir = self.project_dir / "derivatives" / "ti-toolbox" / "reports"
            base_reports_dir.mkdir(parents=True, exist_ok=True)
            # Ensure dataset_description.json exists at reports root
            try:
                dd_path = base_reports_dir / "dataset_description.json"
                assets_template = Path(__file__).resolve().parent.parent / "assets" / "dataset_descriptions" / "reports.dataset_description.json"
                if not dd_path.exists() and assets_template.exists():
                    shutil.copyfile(str(assets_template), str(dd_path))
            except Exception:
                pass
            reports_dir = base_reports_dir / self.bids_subject_id
            reports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = reports_dir / f"pre_processing_report_{timestamp}.html"
        
        # Scan for data before generating report
        self.scan_for_data()
        
        # Generate HTML content
        html_content = self._generate_html_content()
        
        # Write to file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return str(output_path)
    
    def _generate_html_content(self):
        """Generate the HTML content for the report."""
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TI-CSC Preprocessing Report - {self.bids_subject_id}</title>
    <style>
        {self._get_css_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>TI-CSC Preprocessing Report</h1>
            <h2>Subject: {self.bids_subject_id}</h2>
            <p class="timestamp">Generated on: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </header>
        
        <nav class="toc">
            <h3>Table of Contents</h3>
            <ul>
                <li><a href="#summary">Summary</a></li>
                <li><a href="#input-data">Input Data</a></li>
                <li><a href="#processing-steps">Processing Steps</a></li>
                <li><a href="#output-data">Output Data</a></li>
                <li><a href="#software-info">Software Information</a></li>
                <li><a href="#methods">Methods</a></li>
                <li><a href="#errors-warnings">Errors and Warnings</a></li>
            </ul>
        </nav>
        
        <main>
            {self._generate_summary_section()}
            {self._generate_input_data_section()}
            {self._generate_processing_steps_section()}
            {self._generate_output_data_section()}
            {self._generate_software_section()}
            {self._generate_methods_section()}
            {self._generate_errors_warnings_section()}
        </main>
        
        <footer>
            <p>Report generated by TI-CSC 2.0 Preprocessing Pipeline</p>
            <p>For questions or issues, please refer to the TI-CSC documentation.</p>
        </footer>
    </div>
</body>
</html>
"""
        return html
    
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
        
        .processing-step {
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin-bottom: 1rem;
            overflow: hidden;
        }
        
        .step-header {
            background-color: #e9ecef;
            padding: 1rem;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .step-content {
            padding: 1rem;
            display: none;
        }
        
        .step-content.active {
            display: block;
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
        """
    
    def _generate_summary_section(self):
        """Generate the summary section."""
        # Count input files
        t1w_count = len(self.report_data['input_data'].get('T1w', {}).get('files', []))
        t2w_count = len(self.report_data['input_data'].get('T2w', {}).get('files', []))
        
        # Count processing steps
        completed_steps = len([s for s in self.report_data['processing_steps'] if s['status'] == 'completed'])
        total_steps = len(self.report_data['processing_steps'])
        
        return f"""
        <section id="summary" class="section">
            <h2>Summary</h2>
            <div class="info-grid">
                <div class="info-card">
                    <h4>Subject Information</h4>
                    <p><strong>Subject ID:</strong> {self.subject_id}</p>
                    <p><strong>BIDS Subject ID:</strong> {self.bids_subject_id}</p>
                    <p><strong>Project Directory:</strong> {self.project_dir}</p>
                </div>
                <div class="info-card">
                    <h4>Input Data</h4>
                    <p><strong>T1-weighted images:</strong> {t1w_count}</p>
                    <p><strong>T2-weighted images:</strong> {t2w_count}</p>
                    <p><strong>Total input files:</strong> {sum(len(data.get('files', [])) for data in self.report_data['input_data'].values())}</p>
                </div>
                <div class="info-card">
                    <h4>Processing Status</h4>
                    <p><strong>Completed steps:</strong> {completed_steps}/{total_steps}</p>
                    <p><strong>Errors:</strong> {len(self.report_data['errors'])}</p>
                    <p><strong>Warnings:</strong> {len(self.report_data['warnings'])}</p>
                </div>
            </div>
        </section>
        """
    
    def _generate_input_data_section(self):
        """Generate the input data section."""
        html = """
        <section id="input-data" class="section">
            <h2>Input Data</h2>
        """
        
        for data_type, data_info in self.report_data['input_data'].items():
            html += f"""
            <div class="info-card">
                <h4>{data_type.replace('_', ' ').title()}</h4>
                <p><strong>Number of files:</strong> {data_info['count']}</p>
                <div class="file-list">
                    <ul>
            """
            for file_path in data_info['files'][:10]:  # Show first 10 files
                html += f"<li>{os.path.basename(file_path)}</li>"
            
            if data_info['count'] > 10:
                html += f"<li>... and {data_info['count'] - 10} more files</li>"
            
            html += """
                    </ul>
                </div>
            </div>
            """
        
        html += "</section>"
        return html
    
    def _generate_processing_steps_section(self):
        """Generate the processing steps section."""
        html = """
        <section id="processing-steps" class="section">
            <h2>Processing Steps</h2>
        """
        
        for i, step in enumerate(self.report_data['processing_steps']):
            status_class = f"status-{step['status']}"
            html += f"""
            <div class="processing-step">
                <div class="step-header" onclick="toggleStep({i})">
                    <h4>{step['name']}</h4>
                    <span class="{status_class}">{step['status'].upper()}</span>
                </div>
                <div class="step-content" id="step-{i}">
                    <p>{step['description']}</p>
            """
            
            if step['duration']:
                html += f"<p><strong>Duration:</strong> {step['duration']:.2f} seconds</p>"
            
            if step['parameters']:
                html += """
                <h5>Parameters:</h5>
                <table class="parameter-table">
                    <tr><th>Parameter</th><th>Value</th></tr>
                """
                for param, value in step['parameters'].items():
                    html += f"<tr><td>{param}</td><td>{value}</td></tr>"
                html += "</table>"
            
            if step['output_files']:
                html += """
                <h5>Output Files:</h5>
                <div class="file-list">
                    <ul>
                """
                for file_path in step['output_files']:
                    html += f"<li>{os.path.basename(file_path)}</li>"
                html += """
                    </ul>
                </div>
                """
            
            html += """
                </div>
            </div>
            """
        
        html += """
        </section>
        <script>
        function toggleStep(stepIndex) {
            const content = document.getElementById('step-' + stepIndex);
            content.classList.toggle('active');
        }
        </script>
        """
        return html
    
    def _generate_output_data_section(self):
        """Generate the output data section."""
        html = """
        <section id="output-data" class="section">
            <h2>Output Data</h2>
        """
        
        for data_type, data_info in self.report_data['output_data'].items():
            html += f"""
            <div class="info-card">
                <h4>{data_type.replace('_', ' ').title()}</h4>
                <p><strong>Number of files:</strong> {data_info['count']}</p>
                <div class="file-list">
                    <ul>
            """
            for file_path in data_info['files'][:10]:  # Show first 10 files
                html += f"<li>{os.path.basename(file_path)}</li>"
            
            if data_info['count'] > 10:
                html += f"<li>... and {data_info['count'] - 10} more files</li>"
            
            html += """
                    </ul>
                </div>
            </div>
            """
        
        html += "</section>"
        return html
    
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
                html += f"<p><strong>{software.title()}:</strong> {version}</p>"
        else:
            html += "<p>Software version information not available.</p>"
        
        html += """
            </div>
        </section>
        """
        return html
    
    def _generate_methods_section(self):
        """Generate the methods section with boilerplate text."""
        html = """
        <section id="methods" class="section">
            <h2>Methods</h2>
            <p>We kindly ask to report results preprocessed with this tool using the following boilerplate.</p>
            
            <h3>Boilerplate Text</h3>
            <div class="boilerplate">
Results included in this manuscript come from preprocessing performed using TI-CSC 2.0 
(Transcranial Stimulation Computational Suite), which integrates multiple neuroimaging tools 
for comprehensive head modeling and analysis.

Anatomical data preprocessing was performed using the TI-CSC preprocessing pipeline. 
"""
        
        # Add specific methods based on processing steps
        steps = [step['name'] for step in self.report_data['processing_steps']]
        
        if 'DICOM Conversion' in steps:
            html += """
DICOM files were converted to NIfTI format using dcm2niix, with automatic detection 
of T1-weighted and T2-weighted sequences. """
        
        if 'FreeSurfer Reconstruction' in steps:
            html += """
Structural preprocessing was performed using FreeSurfer's recon-all pipeline, which includes 
skull stripping, tissue segmentation, and cortical surface reconstruction. """
        
        if 'SimNIBS m2m Creation' in steps:
            html += """
Head models for electromagnetic field simulations were created using SimNIBS's charm 
segmentation algorithm, which provides accurate tissue segmentation for transcranial 
stimulation modeling. """
        
        if 'Atlas Segmentation' in steps:
            html += """
Cortical parcellation was performed using multiple atlases including the Destrieux 
(a2009s), Desikan-Killiany (DK40), and Human Connectome Project Multi-Modal 
Parcellation (HCP_MMP1) atlases. """
        
        html += """
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
                    html += f"""
                    <div class="error">
                        <strong>Error{f" in {error['step']}" if error['step'] else ""}:</strong> {error['message']}
                        <br><small>Time: {error['timestamp']}</small>
                    </div>
                    """
            
            if self.report_data['warnings']:
                html += "<h3>Warnings</h3>"
                for warning in self.report_data['warnings']:
                    html += f"""
                    <div class="warning">
                        <strong>Warning{f" in {warning['step']}" if warning['step'] else ""}:</strong> {warning['message']}
                        <br><small>Time: {warning['timestamp']}</small>
                    </div>
                    """
        
        html += "</section>"
        return html


def create_preprocessing_report(project_dir, subject_id, processing_log=None):
    """Convenience function to create a preprocessing report.
    
    Args:
        project_dir (str): Path to the project directory
        subject_id (str): Subject ID (without 'sub-' prefix)
        processing_log (dict): Optional processing log with step information
    
    Returns:
        str: Path to the generated report
    """
    generator = PreprocessingReportGenerator(project_dir, subject_id)
    
    # If processing log is provided, add the steps
    if processing_log:
        for step in processing_log.get('steps', []):
            generator.add_processing_step(**step)
        
        for error in processing_log.get('errors', []):
            generator.add_error(**error)
        
        for warning in processing_log.get('warnings', []):
            generator.add_warning(**warning)
    
    return generator.generate_html_report() 