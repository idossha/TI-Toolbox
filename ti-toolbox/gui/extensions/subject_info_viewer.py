#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: Subject Info Viewer
View detailed information about processed subjects in your TI-Toolbox project.
"""

import sys
import os
import json
from pathlib import Path
from PyQt5 import QtWidgets, QtCore, QtGui

# Extension metadata (required)
EXTENSION_NAME = "Subject Info Viewer"
EXTENSION_DESCRIPTION = "View details for subjects in your project directory."

# Add TI-Toolbox to path
ti_toolbox_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ti_toolbox_path))

from core import get_path_manager
from core import constants as const

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
        layout = QtWidgets.QVBoxLayout(self)

        # Header
        header = QtWidgets.QLabel("<h2>Subject Information Viewer</h2>")
        header.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(header)

        # Project directory section
        dir_group = QtWidgets.QGroupBox("Project Directory")
        dir_layout = QtWidgets.QHBoxLayout(dir_group)

        self.dir_label = QtWidgets.QLabel(str(self.project_dir) if self.project_dir else "No project directory detected")
        self.dir_label.setStyleSheet("color: #000; font-weight: bold;" if self.project_dir else "color: #ff0000;")
        dir_layout.addWidget(self.dir_label, 1)

        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.scan_subjects)
        refresh_btn.setToolTip("Refresh subject information")
        dir_layout.addWidget(refresh_btn)
        layout.addWidget(dir_group)

        # Results table
        results_group = QtWidgets.QGroupBox("Subject Status")
        results_layout = QtWidgets.QVBoxLayout(results_group)

        self.results_table = QtWidgets.QTableWidget()
        self.results_table.setColumnCount(7)
        self.results_table.setHorizontalHeaderLabels(["Subject ID", "Raw Data", "FreeSurfer", "SimNIBS", "Simulations", "Flex-Search", "Analysis"])
        self.results_table.horizontalHeader().setStretchLastSection(True)
        self.results_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.results_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.itemSelectionChanged.connect(self.on_selection_changed)
        results_layout.addWidget(self.results_table)

        # Export button
        export_layout = QtWidgets.QHBoxLayout()
        export_layout.addStretch()
        self.export_btn = QtWidgets.QPushButton("Export Selected Subjects")
        self.export_btn.clicked.connect(self.export_selected_subjects)
        self.export_btn.setToolTip("Export JSON snapshot of selected subjects' information")
        self.export_btn.setEnabled(False)
        export_layout.addWidget(self.export_btn)
        export_layout.addStretch()
        results_layout.addLayout(export_layout)
        layout.addWidget(results_group)

        # Status label
        self.info_label = QtWidgets.QLabel("Scanning subjects automatically..." if self.project_dir else "No project directory detected.")
        self.info_label.setWordWrap(True)
        self.info_label.setAlignment(QtCore.Qt.AlignCenter)
        self.info_label.setStyleSheet("color: #666; padding: 10px;")
        layout.addWidget(self.info_label)
    
    def scan_subjects(self):
        if not self.project_dir or not self.project_dir.exists():
            self.info_label.setText("No valid project directory found.")
            self.info_label.setStyleSheet("color: #ff0000; padding: 10px;")
            return

        self.results_table.setRowCount(0)

        # Find subject directories
        subjects = []
        try:
            subjects = [item.name for item in self.project_dir.iterdir()
                       if not item.name.startswith('.') and item.is_dir() and item.name.startswith('sub-')]
        except (PermissionError, OSError) as e:
            self.info_label.setText(f"Error accessing project directory: {str(e)}")
            self.info_label.setStyleSheet("color: #ff0000; padding: 10px;")
            return

        if not subjects:
            self.info_label.setText("No subjects found. Subject folders should start with 'sub-'.")
            return

        subjects.sort()
        
        # Analyze each subject
        for subject_id in subjects:
            row_position = self.results_table.rowCount()
            self.results_table.insertRow(row_position)

            # Subject ID
            self.results_table.setItem(row_position, 0, QtWidgets.QTableWidgetItem(subject_id))

            # Set up paths
            simnibs_dir = self.project_dir / 'derivatives' / 'SimNIBS' / subject_id

            # Raw data, FreeSurfer, SimNIBS
            has_raw = (self.project_dir / 'sourcedata' / subject_id).exists() or (self.project_dir / subject_id / 'anat').exists()
            has_fs = (self.project_dir / 'derivatives' / 'freesurfer' / subject_id / 'mri').exists()
            has_simnibs = simnibs_dir.exists() and len(list(simnibs_dir.glob(f"m2m_{subject_id.replace('sub-', '')}*"))) > 0

            self.results_table.setItem(row_position, 1, self.create_status_item(has_raw))
            self.results_table.setItem(row_position, 2, self.create_status_item(has_fs))
            self.results_table.setItem(row_position, 3, self.create_status_item(has_simnibs))

            # Simulations count
            sim_count = 0
            if simnibs_dir.exists():
                sim_count = len([d for d in (simnibs_dir / 'Simulations').iterdir() if d.is_dir()]) if (simnibs_dir / 'Simulations').exists() else 0

            sim_item = QtWidgets.QTableWidgetItem(f"{sim_count} simulation(s)" if sim_count > 0 else "None")
            sim_item.setForeground(QtGui.QColor("#4CAF50") if sim_count > 0 else QtGui.QColor("#999"))
            self.results_table.setItem(row_position, 4, sim_item)

            # Flex-search count
            flex_count = 0
            if simnibs_dir.exists():
                flex_count = len([d for d in (simnibs_dir / const.DIR_FLEX_SEARCH).iterdir() if d.is_dir()]) if (simnibs_dir / const.DIR_FLEX_SEARCH).exists() else 0

            flex_item = QtWidgets.QTableWidgetItem(f"{flex_count} search(es)" if flex_count > 0 else "None")
            flex_item.setForeground(QtGui.QColor("#2196F3") if flex_count > 0 else QtGui.QColor("#999"))
            self.results_table.setItem(row_position, 5, flex_item)

            # Analysis count
            analysis_count = 0
            if simnibs_dir.exists() and (simnibs_dir / 'Simulations').exists():
                for sim_dir in (simnibs_dir / 'Simulations').iterdir():
                    if sim_dir.is_dir():
                        analyses_dir = sim_dir / const.DIR_ANALYSIS
                        if analyses_dir.exists():
                            analysis_count += len([d for d in analyses_dir.iterdir() if d.is_dir()])

            analysis_item = QtWidgets.QTableWidgetItem(f"{analysis_count} analysis(es)" if analysis_count > 0 else "None")
            analysis_item.setForeground(QtGui.QColor("#FF9800") if analysis_count > 0 else QtGui.QColor("#999"))
            self.results_table.setItem(row_position, 6, analysis_item)
        
        self.results_table.resizeColumnsToContents()
        self.info_label.setText(f"Found {len(subjects)} subject(s).")
        self.on_selection_changed()

    def on_selection_changed(self):
        """Enable/disable export button based on selection."""
        selected_rows = set()
        for item in self.results_table.selectedItems():
            selected_rows.add(item.row())
        self.export_btn.setEnabled(len(selected_rows) > 0)

    def export_selected_subjects(self):
        """Export JSON snapshot of selected subjects' information."""
        if not self.project_dir:
            return QtWidgets.QMessageBox.warning(self, "No Project Directory",
                                               "No project directory available for export.")

        # Get selected subject IDs
        selected_subjects = set(self.results_table.item(item.row(), 0).text()
                              for item in self.results_table.selectedItems())

        if not selected_subjects:
            return QtWidgets.QMessageBox.information(self, "No Selection",
                                                   "Please select one or more subjects to export.")

        try:
            # Create export directory and file
            export_dir = self.project_dir / 'derivatives' / 'ti-toolbox' / 'subjects-viewer'
            export_dir.mkdir(parents=True, exist_ok=True)

            timestamp = QtCore.QDateTime.currentDateTime().toString("yyyyMMdd_HHmmss")
            file_path = export_dir / f"subject_info_export_{timestamp}_{len(selected_subjects)}_subjects.json"

            # Create export data
            export_data = {
                "export_timestamp": QtCore.QDateTime.currentDateTime().toString(QtCore.Qt.ISODate),
                "project_directory": str(self.project_dir),
                "subjects": {sid: self.get_detailed_subject_info(sid) for sid in selected_subjects}
            }

            # Write JSON file
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)

            QtWidgets.QMessageBox.information(self, "Export Complete",
                                            f"Subject information exported to:\n{file_path}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Export Error",
                                         f"Failed to export subject information:\n{str(e)}")

    def get_detailed_subject_info(self, subject_id):
        """Get detailed information for a specific subject."""
        info = {"subject_id": subject_id}

        # Raw data
        sourcedata_dir = self.project_dir / 'sourcedata' / subject_id
        anat_dir = self.project_dir / subject_id / 'anat'

        if sourcedata_dir.exists():
            try:
                info["sourcedata_files"] = [f.name for f in sourcedata_dir.iterdir() if f.is_file()]
            except (PermissionError, OSError):
                info["sourcedata_files"] = ["Permission denied"]

        if anat_dir.exists():
            try:
                info["anat_files"] = [f.name for f in anat_dir.iterdir() if f.is_file()]
            except (PermissionError, OSError):
                info["anat_files"] = ["Permission denied"]

        # FreeSurfer
        freesurfer_dir = self.project_dir / 'derivatives' / 'freesurfer' / subject_id
        if freesurfer_dir.exists():
            info["freesurfer_complete"] = (freesurfer_dir / 'mri').exists()

        # SimNIBS data
        simnibs_dir = self.project_dir / 'derivatives' / 'SimNIBS' / subject_id
        if not simnibs_dir.exists():
            return info

        # m2m directories
        try:
            m2m_dirs = list(simnibs_dir.glob(f"m2m_{subject_id.replace('sub-', '')}*"))
            info["m2m_dirs"] = [d.name for d in m2m_dirs]
        except (PermissionError, OSError):
            info["m2m_dirs"] = ["Permission denied"]

        # Simulations
        simulations_dir = simnibs_dir / 'Simulations'
        if simulations_dir.exists():
            try:
                info["simulation_dirs"] = [d.name for d in simulations_dir.iterdir() if d.is_dir()]
            except (PermissionError, OSError):
                info["simulation_dirs"] = ["Permission denied"]

        # Flex-search
        flex_search_dir = simnibs_dir / const.DIR_FLEX_SEARCH
        if flex_search_dir.exists():
            try:
                flex_dirs = [d.name for d in flex_search_dir.iterdir() if d.is_dir()]
                info["flex_search"] = {"count": len(flex_dirs), "dirs": flex_dirs}
            except (PermissionError, OSError):
                info["flex_search"] = {"error": "Permission denied"}
        else:
            info["flex_search"] = {"count": 0, "dirs": []}

        # Analysis
        analysis_count = 0
        analysis_by_simulation = {}

        if simulations_dir.exists():
            try:
                for sim_dir in simulations_dir.iterdir():
                    if sim_dir.is_dir():
                        analyses_dir = sim_dir / const.DIR_ANALYSIS
                        if analyses_dir.exists():
                            try:
                                sim_analysis_subdirs = [d.name for d in analyses_dir.iterdir() if d.is_dir()]
                                if sim_analysis_subdirs:
                                    analysis_by_simulation[sim_dir.name] = sim_analysis_subdirs
                                    analysis_count += len(sim_analysis_subdirs)
                            except (PermissionError, OSError):
                                pass
            except (PermissionError, OSError):
                pass

        info["analysis"] = {"count": analysis_count, "by_simulation": analysis_by_simulation}
        return info

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

