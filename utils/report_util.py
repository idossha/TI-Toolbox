#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC Report Utilities
This module provides a centralized interface for generating comprehensive HTML reports
for preprocessing and simulation pipelines, similar to fMRIPrep reports.
"""

import os
import datetime
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List

# Import the specific report generators - using absolute imports
try:
    from preprocessing_report_generator import PreprocessingReportGenerator
    from simulation_report_generator import SimulationReportGenerator
except ImportError:
    # Fallback: try importing from utils directory
    import sys
    utils_dir = os.path.dirname(os.path.abspath(__file__))
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    from preprocessing_report_generator import PreprocessingReportGenerator
    from simulation_report_generator import SimulationReportGenerator

# ----------------------------------------------------------------------------
# Configuration constants
# ----------------------------------------------------------------------------
REPORTS_BASE_DIR = "derivatives/ti-toolbox/reports"
PREPROCESSING_REPORT_PREFIX = "pre_processing_report"
SIMULATION_REPORT_PREFIX = "simulation_report"

# ----------------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------------
def _ensure_reports_directory(project_dir: str, subject_id: str) -> Path:
    """
    Ensure the reports directory structure exists.
    
    Args:
        project_dir: Path to the project directory
        subject_id: Subject ID (with or without 'sub-' prefix)
        
    Returns:
        Path to the subject's reports directory
    """
    # Ensure subject_id has 'sub-' prefix
    if not subject_id.startswith('sub-'):
        subject_id = f"sub-{subject_id}"
    
    # Ensure reports root exists and has dataset_description.json
    base_reports_dir = Path(project_dir) / REPORTS_BASE_DIR
    base_reports_dir.mkdir(parents=True, exist_ok=True)
    dd_path = base_reports_dir / "dataset_description.json"
    assets_template = Path(__file__).resolve().parent.parent / "assets" / "dataset_descriptions" / "reports.dataset_description.json"
    try:
        if not dd_path.exists() and assets_template.exists():
            shutil.copyfile(str(assets_template), str(dd_path))
    except Exception:
        # Non-fatal: continue even if we fail to copy the placeholder
        pass

    reports_dir = base_reports_dir / subject_id
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir

def _generate_timestamp() -> str:
    """Generate timestamp string for report filenames."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def _get_report_filename(report_type: str, subject_id: str, timestamp: str = None) -> str:
    """
    Generate standardized report filename.
    
    Args:
        report_type: Type of report ('preprocessing' or 'simulation')
        subject_id: Subject ID (with or without 'sub-' prefix)
        timestamp: Optional timestamp string
        
    Returns:
        Standardized filename
    """
    # Ensure subject_id has 'sub-' prefix
    if not subject_id.startswith('sub-'):
        subject_id = f"sub-{subject_id}"
    
    if timestamp is None:
        timestamp = _generate_timestamp()
    
    if report_type == 'preprocessing':
        return f"{PREPROCESSING_REPORT_PREFIX}_{timestamp}.html"
    elif report_type == 'simulation':
        return f"{SIMULATION_REPORT_PREFIX}_{timestamp}.html"
    else:
        return f"{report_type}_report_{timestamp}.html"

# ----------------------------------------------------------------------------
# Public API - Preprocessing Reports
# ----------------------------------------------------------------------------
def create_preprocessing_report(project_dir: str, 
                              subject_id: str, 
                              processing_log: Optional[Dict[str, Any]] = None,
                              output_path: Optional[str] = None) -> str:
    """
    Create a preprocessing report for a subject.
    
    Args:
        project_dir: Path to the project directory
        subject_id: Subject ID (without 'sub-' prefix)
        processing_log: Optional processing log with step information
        output_path: Optional custom output path for the report
        
    Returns:
        Path to the generated report
    """
    # Ensure subject_id doesn't have 'sub-' prefix for the generator
    clean_subject_id = subject_id.replace('sub-', '') if subject_id.startswith('sub-') else subject_id
    
    # Create the generator
    generator = PreprocessingReportGenerator(project_dir, clean_subject_id)
    
    # Add processing log data if provided
    if processing_log:
        for step in processing_log.get('steps', []):
            generator.add_processing_step(**step)
        
        for error in processing_log.get('errors', []):
            generator.add_error(**error)
        
        for warning in processing_log.get('warnings', []):
            generator.add_warning(**warning)
    
    # Determine output path if not provided
    if output_path is None:
        reports_dir = _ensure_reports_directory(project_dir, clean_subject_id)
        filename = _get_report_filename('preprocessing', clean_subject_id)
        output_path = reports_dir / filename
    
    return generator.generate_html_report(str(output_path))

def get_preprocessing_report_generator(project_dir: str, subject_id: str) -> PreprocessingReportGenerator:
    """
    Get a preprocessing report generator instance.
    
    Args:
        project_dir: Path to the project directory
        subject_id: Subject ID (without 'sub-' prefix)
        
    Returns:
        PreprocessingReportGenerator instance
    """
    clean_subject_id = subject_id.replace('sub-', '') if subject_id.startswith('sub-') else subject_id
    return PreprocessingReportGenerator(project_dir, clean_subject_id)

# ----------------------------------------------------------------------------
# Public API - Simulation Reports
# ----------------------------------------------------------------------------
def create_simulation_report(project_dir: str,
                           simulation_session_id: Optional[str] = None,
                           simulation_log: Optional[Dict[str, Any]] = None,
                           output_path: Optional[str] = None,
                           subject_id: Optional[str] = None) -> str:
    """
    Create a simulation report for a session.
    
    Args:
        project_dir: Path to the project directory
        simulation_session_id: Optional simulation session ID
        simulation_log: Optional simulation log with step information
        output_path: Optional custom output path for the report
        subject_id: Optional subject ID for single-subject reports
        
    Returns:
        Path to the generated report
    """
    # Create the generator
    generator = SimulationReportGenerator(project_dir, simulation_session_id)
    
    # Add simulation log data if provided
    if simulation_log:
        # Add simulation parameters
        if 'simulation_parameters' in simulation_log:
            params = simulation_log['simulation_parameters']
            generator.add_simulation_parameters(**params)
        
        # Add electrode parameters
        if 'electrode_parameters' in simulation_log:
            electrode_params = simulation_log['electrode_parameters']
            generator.add_electrode_parameters(**electrode_params)
        
        # Add subjects
        for subject in simulation_log.get('subjects', []):
            generator.add_subject(**subject)
        
        # Add montages
        for montage in simulation_log.get('montages', []):
            generator.add_montage(**montage)
        
        # Add errors and warnings
        for error in simulation_log.get('errors', []):
            generator.add_error(**error)
        
        for warning in simulation_log.get('warnings', []):
            generator.add_warning(**warning)
    
    # Determine output path if not provided
    if output_path is None:
        if subject_id:
            # Single subject report
            reports_dir = _ensure_reports_directory(project_dir, subject_id)
            filename = _get_report_filename('simulation', subject_id)
            output_path = reports_dir / filename
        else:
            # Multi-subject or session report
            base_reports_dir = Path(project_dir) / REPORTS_BASE_DIR
            base_reports_dir.mkdir(parents=True, exist_ok=True)
            session_id = simulation_session_id or _generate_timestamp()
            filename = f"simulation_session_{session_id}.html"
            output_path = base_reports_dir / filename
    
    return generator.generate_report(str(output_path))

def get_simulation_report_generator(project_dir: str, 
                                  simulation_session_id: Optional[str] = None) -> SimulationReportGenerator:
    """
    Get a simulation report generator instance.
    
    Args:
        project_dir: Path to the project directory
        simulation_session_id: Optional simulation session ID
        
    Returns:
        SimulationReportGenerator instance
    """
    return SimulationReportGenerator(project_dir, simulation_session_id)

# ----------------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------------
def list_reports(project_dir: str, subject_id: Optional[str] = None, report_type: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List existing reports in the project.
    
    Args:
        project_dir: Path to the project directory
        subject_id: Optional subject ID to filter reports
        report_type: Optional report type ('preprocessing' or 'simulation')
        
    Returns:
        List of report information dictionaries
    """
    reports = []
    reports_base = Path(project_dir) / REPORTS_BASE_DIR
    
    if not reports_base.exists():
        return reports
    
    if subject_id:
        # Ensure subject_id has 'sub-' prefix
        if not subject_id.startswith('sub-'):
            subject_id = f"sub-{subject_id}"
        
        subject_dirs = [reports_base / subject_id] if (reports_base / subject_id).exists() else []
    else:
        subject_dirs = [d for d in reports_base.iterdir() if d.is_dir() and d.name.startswith('sub-')]
    
    for subject_dir in subject_dirs:
        for report_file in subject_dir.glob("*.html"):
            report_info = {
                'path': str(report_file),
                'filename': report_file.name,
                'subject_id': subject_dir.name,
                'modified': datetime.datetime.fromtimestamp(report_file.stat().st_mtime),
                'size': report_file.stat().st_size
            }
            
            # Determine report type from filename
            if PREPROCESSING_REPORT_PREFIX in report_file.name:
                report_info['type'] = 'preprocessing'
            elif SIMULATION_REPORT_PREFIX in report_file.name:
                report_info['type'] = 'simulation'
            else:
                report_info['type'] = 'unknown'
            
            # Filter by report type if specified
            if report_type is None or report_info['type'] == report_type:
                reports.append(report_info)
    
    # Also check for session-level simulation reports
    if report_type is None or report_type == 'simulation':
        for report_file in reports_base.glob("simulation_session_*.html"):
            report_info = {
                'path': str(report_file),
                'filename': report_file.name,
                'subject_id': 'session',
                'type': 'simulation',
                'modified': datetime.datetime.fromtimestamp(report_file.stat().st_mtime),
                'size': report_file.stat().st_size
            }
            reports.append(report_info)
    
    # Sort by modification time (newest first)
    reports.sort(key=lambda x: x['modified'], reverse=True)
    return reports

def get_latest_report(project_dir: str, subject_id: str, report_type: str) -> Optional[str]:
    """
    Get the path to the latest report for a subject.
    
    Args:
        project_dir: Path to the project directory
        subject_id: Subject ID
        report_type: Type of report ('preprocessing' or 'simulation')
        
    Returns:
        Path to the latest report or None if not found
    """
    reports = list_reports(project_dir, subject_id, report_type)
    return reports[0]['path'] if reports else None 