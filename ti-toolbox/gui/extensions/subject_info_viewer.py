#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: Subject Info Viewer
View detailed information about processed subjects in your TI-Toolbox project.
"""

import sys
import os
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui

# Extension metadata (required)
EXTENSION_NAME = "Subject Info Viewer"
EXTENSION_DESCRIPTION = "View details for subjects in your project directory."

# Add TI-Toolbox to path
ti_toolbox_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ti_toolbox_path))

from core import get_path_manager

class SubjectInfoWindow(QtWidgets.QDialog):
    """Subject information viewer window."""
    
    def __init__(self, parent=None):
        super(SubjectInfoWindow, self).__init__(parent)
        self.setWindowTitle("Subject Info Viewer")
        self.setMinimumSize(700, 500)
        self.setWindowFlag(QtCore.Qt.Window)  # Make it a proper window, not modal
        self.parent_window = parent
        
        # Get path manager and auto-detect project directory
        self.pm = get_path_manager() if get_path_manager else None
        self.project_dir = None
        if self.pm:
            project_path = self.pm.get_project_dir()
            if project_path and os.path.exists(project_path):
                self.project_dir = Path(project_path)
        
        self.setup_ui()
        
        # Auto-scan on startup if project directory is available
        if self.project_dir:
            # Use QTimer to scan after UI is fully set up
            QtCore.QTimer.singleShot(100, self.scan_subjects)
    
    def setup_ui(self):
        """Set up the subject info viewer UI."""
        layout = QtWidgets.QVBoxLayout(self)
        
        # Header
        header_label = QtWidgets.QLabel("<h2>Subject Information Viewer</h2>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header_label)
        
        # Project directory display
        dir_group = QtWidgets.QGroupBox("Project Directory")
        dir_layout = QtWidgets.QHBoxLayout(dir_group)
        
        # Auto-detected directory label
        if self.project_dir:
            self.dir_label = QtWidgets.QLabel(str(self.project_dir))
            self.dir_label.setStyleSheet("color: #000; font-weight: bold;")
        else:
            self.dir_label = QtWidgets.QLabel("No project directory detected")
            self.dir_label.setStyleSheet("color: #ff0000;")
        
        dir_layout.addWidget(self.dir_label, 1)
        
        # Refresh button
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.scan_subjects)
        refresh_btn.setToolTip("Refresh subject information")
        dir_layout.addWidget(refresh_btn)
        
        layout.addWidget(dir_group)
        
        # Results area
        results_group = QtWidgets.QGroupBox("Subject Status")
        results_layout = QtWidgets.QVBoxLayout(results_group)
        
        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels([
            "Subject ID", 
            "Raw Data", 
            "FreeSurfer", 
            "SimNIBS", 
            "Simulations"
        ])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        
        results_layout.addWidget(self.results_table)
        layout.addWidget(results_group)
        
        # Info label
        if self.project_dir:
            self.info_label = QtWidgets.QLabel("Scanning subjects automatically...")
        else:
            self.info_label = QtWidgets.QLabel("No project directory detected. Please ensure the project environment is set up correctly.")
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(self.info_label)
    
    def scan_subjects(self):
        """Scan project directory for subjects and their processing status."""
        if not self.project_dir or not self.project_dir.exists():
            self.info_label.setText("No valid project directory found. Cannot scan subjects.")
            self.info_label.setStyleSheet("color: #ff0000; padding: 10px;")
            return
        
        # Clear existing table
        self.results_table.setRowCount(0)
        
        # Find all subject directories
        subjects = []
        try:
            for item in self.project_dir.iterdir():
                # Skip hidden files and handle permission errors
                if item.name.startswith('.'):
                    continue
                try:
                    if item.is_dir() and item.name.startswith('sub-'):
                        subjects.append(item.name)
                except (PermissionError, OSError):
                    # Skip files/directories we can't access
                    continue
        except (PermissionError, OSError) as e:
            self.info_label.setText(f"Error accessing project directory: {str(e)}")
            self.info_label.setStyleSheet("color: #ff0000; padding: 10px;")
            return
        
        if not subjects:
            self.info_label.setText("No subjects found in this directory. Subject folders should start with 'sub-'.")
            return
        
        subjects.sort()
        
        # Analyze each subject
        for subject_id in subjects:
            row_position = self.results_table.rowCount()
            self.results_table.insertRow(row_position)
            
            # Subject ID
            self.results_table.setItem(row_position, 0, QtWidgets.QTableWidgetItem(subject_id))
            
            # Check for raw data (sourcedata or anat directory)
            has_sourcedata = (self.project_dir / 'sourcedata' / subject_id).exists()
            has_anat = (self.project_dir / subject_id / 'anat').exists()
            raw_data_status = self.create_status_item(has_sourcedata or has_anat)
            self.results_table.setItem(row_position, 1, raw_data_status)
            
            # Check for FreeSurfer
            freesurfer_dir = self.project_dir / 'derivatives' / 'freesurfer' / subject_id
            has_freesurfer = freesurfer_dir.exists() and (freesurfer_dir / 'mri').exists()
            freesurfer_status = self.create_status_item(has_freesurfer)
            self.results_table.setItem(row_position, 2, freesurfer_status)
            
            # Check for SimNIBS
            simnibs_dir = self.project_dir / 'derivatives' / 'SimNIBS' / subject_id
            m2m_pattern = f"m2m_{subject_id.replace('sub-', '')}"
            has_simnibs = False
            if simnibs_dir.exists():
                m2m_dirs = list(simnibs_dir.glob(m2m_pattern + '*'))
                has_simnibs = len(m2m_dirs) > 0
            simnibs_status = self.create_status_item(has_simnibs)
            self.results_table.setItem(row_position, 3, simnibs_status)
            
            # Check for simulations
            simulations_dir = simnibs_dir / 'Simulations' if simnibs_dir.exists() else None
            simulation_count = 0
            if simulations_dir and simulations_dir.exists():
                simulation_count = len([d for d in simulations_dir.iterdir() if d.is_dir()])
            
            sim_text = f"{simulation_count} simulation(s)" if simulation_count > 0 else "None"
            sim_item = QtWidgets.QTableWidgetItem(sim_text)
            if simulation_count > 0:
                sim_item.setForeground(QtGui.QColor("#4CAF50"))
            else:
                sim_item.setForeground(QtGui.QColor("#999"))
            self.results_table.setItem(row_position, 4, sim_item)
        
        # Resize columns to content
        self.results_table.resizeColumnsToContents()
        
        # Update info label
        self.info_label.setText(f"Found {len(subjects)} subject(s) in the project directory.")
    
    def create_status_item(self, exists):
        """Create a table item with status indicator."""
        if exists:
            item = QtWidgets.QTableWidgetItem("✓ Present")
            item.setForeground(QtGui.QColor("#4CAF50"))
        else:
            item = QtWidgets.QTableWidgetItem("✗ Missing")
            item.setForeground(QtGui.QColor("#f44336"))
        return item


def main(parent=None):
    """
    Main entry point for the extension.
    This function is called when the extension is launched.
    """
    window = SubjectInfoWindow(parent)
    window.show()
    return window


# Alternative entry point (for flexibility)
def run(parent=None):
    """Alternative entry point."""
    main(parent)

