#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-Toolbox Path Management
Centralized path management for the entire TI-Toolbox codebase.

This module provides a professional path management system for BIDS-compliant
directory structures, handling project directories, subject paths, and common
path patterns consistently across all tools.

Usage:
    # Use the singleton instance
    from ti_toolbox.core import get_path_manager
    
    pm = get_path_manager()
    subjects = pm.list_subjects()
    m2m_dir = pm.get_m2m_dir("001")
    
    # Or use convenience functions
    from ti_toolbox.core import get_project_dir, list_subjects
    
    project_dir = get_project_dir()
    subjects = list_subjects()
"""

import os
import re
from pathlib import Path
from typing import Optional, List, Dict

from . import constants as const


class PathManager:
    """
    Centralized path management for TI-Toolbox.
    
    This class provides consistent path resolution across all components:
    - Project directory detection
    - Subject listing and validation
    - Common path patterns (derivatives, SimNIBS, m2m, etc.)
    - BIDS-compliant directory structure handling
    """
    
    def __init__(self):
        """Initialize the path manager."""
        self._project_dir: Optional[str] = None
        self._project_dir_name: Optional[str] = None
        self._refresh()
    
    def _refresh(self):
        """Refresh project directory information."""
        self._project_dir = self.detect_project_dir()
        if self._project_dir:
            self._project_dir_name = os.path.basename(self._project_dir)
        else:
            self._project_dir_name = os.environ.get(const.ENV_PROJECT_DIR_NAME)
    
    def detect_project_dir(self) -> Optional[str]:
        """
        Detect the project directory using multiple strategies.
        
        Check PROJECT_DIR_NAME with /mnt prefix (Docker)
        
        Returns:
            Path to project directory or None if not found
        """
        
        # Check PROJECT_DIR_NAME with /mnt prefix (Docker)
        project_dir_name = os.environ.get(const.ENV_PROJECT_DIR_NAME)
        if project_dir_name:
            mnt_path = os.path.join(const.DOCKER_MOUNT_PREFIX, project_dir_name)
            if os.path.isdir(mnt_path):
                return mnt_path
        
        return None
    
    def get_project_dir(self) -> Optional[str]:
        """
        Get the project directory path.
        
        Returns:
            Path to project directory or None if not found
        """
        if not self._project_dir:
            self._refresh()
        return self._project_dir
    
    def get_project_dir_name(self) -> Optional[str]:
        """
        Get the project directory name.
        
        Returns:
            Project directory name or None if not found
        """
        if not self._project_dir_name:
            self._refresh()
        return self._project_dir_name
    
    def get_derivatives_dir(self) -> Optional[str]:
        """
        Get the derivatives directory path.
        
        Returns:
            Path to derivatives directory or None if project not found
        """
        project_dir = self.get_project_dir()
        if project_dir:
            return os.path.join(project_dir, const.DIR_DERIVATIVES)
        return None
    
    def get_simnibs_dir(self) -> Optional[str]:
        """
        Get the SimNIBS derivatives directory path.
        
        Returns:
            Path to SimNIBS directory or None if not found
        """
        derivatives_dir = self.get_derivatives_dir()
        if derivatives_dir:
            return os.path.join(derivatives_dir, const.DIR_SIMNIBS)
        return None
    
    def get_subject_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the subject directory path in SimNIBS derivatives.
        
        Args:
            subject_id: Subject ID (e.g., "001" or "101")
            
        Returns:
            Path to subject directory (e.g., .../sub-001/) or None
        """
        simnibs_dir = self.get_simnibs_dir()
        if simnibs_dir:
            return os.path.join(simnibs_dir, f"{const.PREFIX_SUBJECT}{subject_id}")
        return None
    
    def get_m2m_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the m2m directory for a subject.
        
        Args:
            subject_id: Subject ID (e.g., "001" or "101")
            
        Returns:
            Path to m2m directory (e.g., .../sub-001/m2m_001/) or None
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            m2m_path = os.path.join(subject_dir, f"{const.DIR_M2M_PREFIX}{subject_id}")
            if os.path.isdir(m2m_path):
                return m2m_path
        return None
    
    def get_sourcedata_dir(self, subject_id: Optional[str] = None) -> Optional[str]:
        """
        Get the sourcedata directory path.
        
        Args:
            subject_id: Optional subject ID to get subject-specific sourcedata
            
        Returns:
            Path to sourcedata directory or None
        """
        project_dir = self.get_project_dir()
        if not project_dir:
            return None
        
        if subject_id:
            return os.path.join(project_dir, const.DIR_SOURCEDATA, 
                              f"{const.PREFIX_SUBJECT}{subject_id}")
        return os.path.join(project_dir, const.DIR_SOURCEDATA)
    
    def list_subjects(self) -> List[str]:
        """
        List all available subjects in the project.
        
        Returns:
            List of subject IDs (without 'sub-' prefix), sorted naturally
        """
        simnibs_dir = self.get_simnibs_dir()
        if not simnibs_dir or not os.path.exists(simnibs_dir):
            return []
        
        subjects = []
        for item in os.listdir(simnibs_dir):
            if item.startswith(const.PREFIX_SUBJECT):
                subject_path = os.path.join(simnibs_dir, item)
                if os.path.isdir(subject_path):
                    # Check if it has an m2m directory
                    subject_id = item.replace(const.PREFIX_SUBJECT, "")
                    m2m_dir = os.path.join(subject_path, f"{const.DIR_M2M_PREFIX}{subject_id}")
                    if os.path.isdir(m2m_dir):
                        subjects.append(subject_id)
        
        # Sort subjects naturally (001, 002, 010, 100)
        subjects.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() 
                                     for c in re.split('([0-9]+)', x)])
        return subjects
    
    def list_simulations(self, subject_id: str) -> List[str]:
        """
        List all simulations for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            List of simulation names, sorted alphabetically
        """
        subject_dir = self.get_subject_dir(subject_id)
        if not subject_dir or not os.path.exists(subject_dir):
            return []
        
        simulations = []
        for item in os.listdir(subject_dir):
            item_path = os.path.join(subject_dir, item)
            if os.path.isdir(item_path) and not item.startswith(const.DIR_M2M_PREFIX):
                simulations.append(item)
        
        simulations.sort()
        return simulations
    
    def get_simulation_dir(self, subject_id: str, simulation_name: str) -> Optional[str]:
        """
        Get the simulation directory path.
        
        Args:
            subject_id: Subject ID
            simulation_name: Simulation name
            
        Returns:
            Path to simulation directory or None
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, simulation_name)
        return None
    
    def get_eeg_positions_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the EEG positions directory for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to eeg_positions directory or None
        """
        m2m_dir = self.get_m2m_dir(subject_id)
        if m2m_dir:
            return os.path.join(m2m_dir, const.DIR_EEG_POSITIONS)
        return None
    
    def get_flex_search_dir(self, subject_id: str, search_name: str) -> Optional[str]:
        """
        Get the flex-search directory for a specific search.
        
        Args:
            subject_id: Subject ID
            search_name: Name of the flex-search
            
        Returns:
            Path to flex-search directory or None
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, const.DIR_FLEX_SEARCH, search_name)
        return None
    
    def get_reports_dir(self) -> Optional[str]:
        """
        Get the reports directory.
        
        Returns:
            Path to reports directory or None
        """
        derivatives_dir = self.get_derivatives_dir()
        if derivatives_dir:
            return os.path.join(derivatives_dir, const.DIR_REPORTS)
        return None
    
    def get_logs_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the logs directory for a specific subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to subject's logs directory or None
        """
        derivatives_dir = self.get_derivatives_dir()
        if derivatives_dir:
            return os.path.join(derivatives_dir, const.DIR_TI_TOOLBOX, 
                              const.DIR_LOGS, f"{const.PREFIX_SUBJECT}{subject_id}")
        return None
    
    def get_ex_search_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the ex-search directory for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to ex-search directory or None
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, const.DIR_EX_SEARCH)
        return None
    
    def get_roi_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the ROI directory for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to ROI directory or None
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            return os.path.join(subject_dir, const.DIR_ROIS)
        return None
    
    def get_mesh_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the mesh directory (m2m) for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to m2m directory or None (alias for get_m2m_dir)
        """
        return self.get_m2m_dir(subject_id)
    
    def get_t1_path(self, subject_id: str) -> Optional[str]:
        """
        Get the T1 NIfTI file path for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to T1.nii.gz file or None
        """
        m2m_dir = self.get_m2m_dir(subject_id)
        if m2m_dir:
            return os.path.join(m2m_dir, const.FILE_T1)
        return None
    
    def list_eeg_caps(self, subject_id: str) -> List[str]:
        """
        List available EEG cap files for a subject.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            List of EEG cap CSV filenames, sorted alphabetically
        """
        eeg_pos_dir = self.get_eeg_positions_dir(subject_id)
        if not eeg_pos_dir or not os.path.exists(eeg_pos_dir):
            return []
        
        caps = []
        for file in os.listdir(eeg_pos_dir):
            if file.endswith(const.EXT_CSV) and not file.startswith('.'):
                caps.append(file)
        
        caps.sort()
        return caps
    
    def get_movea_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the MOVEA directory for a subject.
        Creates the directory if it doesn't exist.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to MOVEA directory or None
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            movea_dir = os.path.join(subject_dir, const.DIR_MOVEA)
            os.makedirs(movea_dir, exist_ok=True)
            return movea_dir
        return None
    
    def get_leadfield_dir(self, subject_id: str) -> Optional[str]:
        """
        Get the leadfield directory for a subject (under MOVEA).
        Creates the directory if it doesn't exist.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Path to leadfield directory or None
        """
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            leadfield_dir = os.path.join(subject_dir, const.DIR_LEADFIELDS)
            os.makedirs(leadfield_dir, exist_ok=True)
            return leadfield_dir
        return None
    
    def create_output_dir(self, subject_id: str, tool_name: str, 
                         timestamp: Optional[str] = None) -> Optional[str]:
        """
        Create a timestamped output directory for a tool.
        
        Args:
            subject_id: Subject ID
            tool_name: Name of the tool (e.g., "MOVEA", "Analyzer")
            timestamp: Optional timestamp string (generated if None)
            
        Returns:
            Path to created output directory or None
        """
        import time
        if timestamp is None:
            timestamp = time.strftime(const.TIMESTAMP_FORMAT_DEFAULT)
        
        subject_dir = self.get_subject_dir(subject_id)
        if subject_dir:
            output_dir = os.path.join(subject_dir, tool_name, timestamp)
            os.makedirs(output_dir, exist_ok=True)
            return output_dir
        return None
    
    def validate_subject_structure(self, subject_id: str) -> Dict[str, any]:
        """
        Validate that a subject has the required directory structure.
        
        Args:
            subject_id: Subject ID
            
        Returns:
            Dictionary with validation results:
            - 'valid': bool indicating if structure is valid
            - 'missing': list of missing required components
            - 'warnings': list of optional missing components
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
            results['missing'].append(f"Subject directory: {const.PREFIX_SUBJECT}{subject_id}")
            return results
        
        # Check m2m directory
        m2m_dir = self.get_m2m_dir(subject_id)
        if not m2m_dir:
            results['valid'] = False
            results['missing'].append(f"m2m directory: {const.DIR_M2M_PREFIX}{subject_id}")
        
        # Check for EEG positions (optional warning)
        eeg_pos_dir = self.get_eeg_positions_dir(subject_id)
        if not eeg_pos_dir or not os.path.exists(eeg_pos_dir):
            results['warnings'].append(const.WARNING_NO_EEG_POSITIONS)
        
        return results


# ============================================================================
# SINGLETON PATTERN
# ============================================================================

_path_manager_instance: Optional[PathManager] = None


def get_path_manager() -> PathManager:
    """
    Get the global PathManager singleton instance.
    
    Returns:
        The global path manager instance
    """
    global _path_manager_instance
    if _path_manager_instance is None:
        _path_manager_instance = PathManager()
    return _path_manager_instance


def reset_path_manager():
    """
    Reset the global PathManager singleton instance.
    Useful for testing or when project directory changes.
    """
    global _path_manager_instance
    _path_manager_instance = None


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_project_dir() -> Optional[str]:
    """Get the project directory path."""
    return get_path_manager().get_project_dir()


def get_subject_dir(subject_id: str) -> Optional[str]:
    """Get the subject directory path."""
    return get_path_manager().get_subject_dir(subject_id)


def get_m2m_dir(subject_id: str) -> Optional[str]:
    """Get the m2m directory for a subject."""
    return get_path_manager().get_m2m_dir(subject_id)


def list_subjects() -> List[str]:
    """List all available subjects."""
    return get_path_manager().list_subjects()


def validate_subject(subject_id: str) -> Dict[str, any]:
    """Validate subject directory structure."""
    return get_path_manager().validate_subject_structure(subject_id)

