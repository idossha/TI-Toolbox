#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Path Manager Component
Centralized path management for TI-Toolbox GUI
Handles project directories, subject paths, and common path patterns
"""

import os
import glob
from pathlib import Path


class PathManager:
    """
    Centralized path management for TI-Toolbox.
    
    This class provides consistent path resolution across all tabs:
    - Project directory detection
    - Subject listing
    - Common path patterns (derivatives, SimNIBS, m2m, etc.)
    """
    
    def __init__(self):
        """Initialize the path manager."""
        self._project_dir = None
        self._project_dir_name = None
        self._refresh()
    
    def _refresh(self):
        """Refresh project directory information."""
        self._project_dir = self.detect_project_dir()
        if self._project_dir:
            self._project_dir_name = os.path.basename(self._project_dir)
        else:
            self._project_dir_name = os.environ.get('PROJECT_DIR_NAME')
    
    def detect_project_dir(self):
        """
        Detect the project directory using multiple strategies.
        
        Returns:
            str: Path to project directory or None if not found
        """
        # Strategy 1: Check PROJECT_DIR environment variable
        project_dir = os.environ.get('PROJECT_DIR')
        if project_dir and os.path.isdir(project_dir):
            return project_dir
        
        # Strategy 2: Check PROJECT_DIR_NAME with /mnt prefix (Docker)
        project_dir_name = os.environ.get('PROJECT_DIR_NAME')
        if project_dir_name:
            mnt_path = f"/mnt/{project_dir_name}"
            if os.path.isdir(mnt_path):
                return mnt_path
        
        # Strategy 3: If in Docker, scan /mnt for BIDS-like directories
        if os.path.isdir("/mnt"):
            for dir_name in os.listdir("/mnt"):
                dir_path = os.path.join("/mnt", dir_name)
                if os.path.isdir(dir_path):
                    # Check if it looks like a valid project directory
                    if (os.path.isdir(os.path.join(dir_path, "sourcedata")) or 
                        os.path.isdir(os.path.join(dir_path, "derivatives"))):
                        return dir_path
        
        return None
    
    def get_project_dir(self):
        """Get the project directory path."""
        if not self._project_dir:
            self._refresh()
        return self._project_dir
    
    def get_project_dir_name(self):
        """Get the project directory name."""
        if not self._project_dir_name:
            self._refresh()
        return self._project_dir_name
    
    def get_derivatives_dir(self):
        """Get the derivatives directory path."""
        project_dir = self.get_project_dir()
        if project_dir:
            return os.path.join(project_dir, "derivatives")
        return None
    
    def get_simnibs_dir(self):
        """Get the SimNIBS derivatives directory path."""
        derivatives_dir = self.get_derivatives_dir()
        if derivatives_dir:
            return os.path.join(derivatives_dir, "SimNIBS")
        return None
    
    def get_subject_dir(self, subject_id):
        """
        Get the subject directory path in SimNIBS derivatives.
        
        Args:
            subject_id: Subject ID (e.g., "001" or "101")
            
        Returns:
            str: Path to subject directory (e.g., .../sub-001/)
        """
        simnibs_dir = self.get_simnibs_dir()
        if simnibs_dir:
            return os.path.join(simnibs_dir, f"sub-{subject_id}")
        return None
    
    def get_m2m_dir(self, subject_id):
        """
        Get the m2m directory for a subject.
        
        Args:
            subject_id: Subject ID (e.g., "001" or "101")
            
        Returns:
            str: Path to m2m directory (e.g., .../sub-001/m2m_001/)
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            m2m_path = os.path.join(subject_dir, f"m2m_{subject_id}")
            if os.path.isdir(m2m_path):
                return m2m_path
        return None
    
    def get_sourcedata_dir(self, subject_id=None):
        """
        Get the sourcedata directory path.
        
        Args:
            subject_id: Optional subject ID to get subject-specific sourcedata
            
        Returns:
            str: Path to sourcedata directory
        """
        project_dir = self.get_project_dir()
        if not project_dir:
            return None
        
        if subject_id:
            return os.path.join(project_dir, "sourcedata", f"sub-{subject_id}")
        return os.path.join(project_dir, "sourcedata")
    
    def list_subjects(self):
        """
        List all available subjects in the project.
        
        Returns:
            list: List of subject IDs (without 'sub-' prefix)
        """
        simnibs_dir = self.get_simnibs_dir()
        if not simnibs_dir or not os.path.exists(simnibs_dir):
            return []
        
        subjects = []
        for item in os.listdir(simnibs_dir):
            if item.startswith("sub-"):
                subject_path = os.path.join(simnibs_dir, item)
                if os.path.isdir(subject_path):
                    # Check if it has an m2m directory
                    subject_id = item.replace("sub-", "")
                    m2m_dir = os.path.join(subject_path, f"m2m_{subject_id}")
                    if os.path.isdir(m2m_dir):
                        subjects.append(subject_id)
        
        # Sort subjects naturally (001, 002, 010, 100)
        subjects.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() 
                                     for c in __import__('re').split('([0-9]+)', x)])
        return subjects
    
    def list_simulations(self, subject_id):
        """
        List all simulations for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            list: List of simulation names
        """
        subject_dir = self.get_subject_dir(subject_id)
        if not subject_dir or not os.path.exists(subject_dir):
            return []
        
        simulations = []
        for item in os.listdir(subject_dir):
            item_path = os.path.join(subject_dir, item)
            if os.path.isdir(item_path) and not item.startswith("m2m_"):
                simulations.append(item)
        
        simulations.sort()
        return simulations
    
    def get_simulation_dir(self, subject_id, simulation_name):
        """
        Get the simulation directory path.
        
        Args:
            subject_id: Subject ID
            simulation_name: Simulation name
            
        Returns:
            str: Path to simulation directory
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, simulation_name)
        return None
    
    def get_eeg_positions_dir(self, subject_id):
        """
        Get the EEG positions directory for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to eeg_positions directory
        """
        m2m_dir = self.get_m2m_dir(subject_id)
        if m2m_dir:
            return os.path.join(m2m_dir, "eeg_positions")
        return None
    
    def get_flex_search_dir(self, subject_id, search_name):
        """
        Get the flex-search directory for a specific search.
        
        Args:
            subject_id: Subject ID
            search_name: Name of the flex-search
            
        Returns:
            str: Path to flex-search directory
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, "flex-search", search_name)
        return None
    
    def get_reports_dir(self):
        """
        Get the reports directory.
        
        Returns:
            str: Path to reports directory
        """
        derivatives_dir = self.get_derivatives_dir()
        if derivatives_dir:
            return os.path.join(derivatives_dir, "reports")
        return None
    
    def get_logs_dir(self, subject_id):
        """
        Get the logs directory for a specific subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to subject's logs directory
        """
        derivatives_dir = self.get_derivatives_dir()
        if derivatives_dir:
            return os.path.join(derivatives_dir, "ti-toolbox", "logs", f"sub-{subject_id}")
        return None
    
    def get_ex_search_dir(self, subject_id):
        """
        Get the ex-search directory for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to ex-search directory
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, "ex-search")
        return None
    
    def get_roi_dir(self, subject_id):
        """
        Get the ROI directory for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to ROI directory
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, "ROIs")
        return None
    
    def get_mesh_dir(self, subject_id):
        """
        Get the mesh directory (m2m) for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to m2m directory (same as get_m2m_dir)
        """
        return self.get_m2m_dir(subject_id)
    
    def get_t1_path(self, subject_id):
        """
        Get the T1 NIfTI file path for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to T1.nii.gz file
        """
        m2m_dir = self.get_m2m_dir(subject_id)
        if m2m_dir:
            return os.path.join(m2m_dir, "T1.nii.gz")
        return None
    
    def list_eeg_caps(self, subject_id):
        """
        List available EEG cap files for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            list: List of EEG cap CSV filenames
        """
        eeg_pos_dir = self.get_eeg_positions_dir(subject_id)
        if not eeg_pos_dir or not os.path.exists(eeg_pos_dir):
            return []
        
        caps = []
        for file in os.listdir(eeg_pos_dir):
            if file.endswith('.csv') and not file.startswith('.'):
                caps.append(file)
        
        caps.sort()
        return caps
    
    def get_movea_dir(self, subject_id):
        """
        Get the MOVEA directory for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to MOVEA directory
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            movea_dir = os.path.join(subject_dir, "MOVEA")
            os.makedirs(movea_dir, exist_ok=True)
            return movea_dir
        return None
    
    def get_leadfield_dir(self, subject_id):
        """
        Get the leadfield directory for a subject (under MOVEA).
        
        Args:
            subject_id: Subject ID
            
        Returns:
            str: Path to leadfield directory
        """
        movea_dir = self.get_movea_dir(subject_id)
        if movea_dir:
            leadfield_dir = os.path.join(movea_dir, "leadfields")
            os.makedirs(leadfield_dir, exist_ok=True)
            return leadfield_dir
        return None
    
    def create_output_dir(self, subject_id, tool_name, timestamp=None):
        """
        Create a timestamped output directory for a tool.
        
        Args:
            subject_id: Subject ID
            tool_name: Name of the tool (e.g., "MOVEA", "Analyzer")
            timestamp: Optional timestamp string (generated if None)
            
        Returns:
            str: Path to created output directory
        """
        import time
        if timestamp is None:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
        
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            output_dir = os.path.join(subject_dir, tool_name, timestamp)
            os.makedirs(output_dir, exist_ok=True)
            return output_dir
        return None
    
    def validate_subject_structure(self, subject_id):
        """
        Validate that a subject has the required directory structure.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            dict: Validation results with 'valid' bool and 'missing' list
        """
        results = {
            'valid': True,
            'missing': [],
            'warnings': []
        }
        
        # Check subject directory
        subject_dir = self.get_subject_dir(subject_id)
        if not subject_dir or not os.path.exists(subject_dir):
            results['valid'] = False
            results['missing'].append(f"Subject directory: sub-{subject_id}")
            return results
        
        # Check m2m directory
        m2m_dir = self.get_m2m_dir(subject_id)
        if not m2m_dir:
            results['valid'] = False
            results['missing'].append(f"m2m directory: m2m_{subject_id}")
        
        # Check for EEG positions (optional warning)
        eeg_pos_dir = self.get_eeg_positions_dir(subject_id)
        if not eeg_pos_dir or not os.path.exists(eeg_pos_dir):
            results['warnings'].append("No eeg_positions directory found")
        
        return results


# Global singleton instance
_path_manager_instance = None

def get_path_manager():
    """
    Get the global PathManager singleton instance.
    
    Returns:
        PathManager: The global path manager instance
    """
    global _path_manager_instance
    if _path_manager_instance is None:
        _path_manager_instance = PathManager()
    return _path_manager_instance

