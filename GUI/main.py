#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 GUI Main Entry Point
This module provides a GUI interface for the TI-CSC-2.0 toolbox.
"""

import sys
import os
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui

# Import tool-specific modules
from simulator_tab import SimulatorTab
from flex_search_tab import FlexSearchTab
from pre_process_tab import PreProcessTab

# Try to import visualization modules
MESH_VIEWER_AVAILABLE = False
NIFTI_VIEWER_AVAILABLE = False

try:
    from mesh_viewer_tab import MeshViewerTab, OPENGL_AVAILABLE
    MESH_VIEWER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Mesh viewer not available: {str(e)}")
    MESH_VIEWER_AVAILABLE = False

try:
    from nifti_viewer_tab import NiftiViewerTab, NIBABEL_AVAILABLE
    NIFTI_VIEWER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: NIfTI viewer not available: {str(e)}")
    NIFTI_VIEWER_AVAILABLE = False

class MainWindow(QtWidgets.QMainWindow):
    """Main window for the TI-CSC-2.0 GUI."""
    
    def __init__(self):
        super(MainWindow, self).__init__()
        
        self.setWindowTitle("TI-CSC-2.0 Toolbox")
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the user interface."""
        # Central widget and layout
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        
        main_layout = QtWidgets.QVBoxLayout(self.central_widget)
        
        # Create the tab widget for different tools
        self.tab_widget = QtWidgets.QTabWidget()
        
        # Add pre-process tab
        self.pre_process_tab = PreProcessTab(self)
        self.tab_widget.addTab(self.pre_process_tab, "Pre-processing")
        
        # Add simulator tab
        self.simulator_tab = SimulatorTab(self)
        self.tab_widget.addTab(self.simulator_tab, "Simulator")
        
        # Add flex-search tab
        self.flex_search_tab = FlexSearchTab(self)
        self.tab_widget.addTab(self.flex_search_tab, "Flex-Search")
        
        # Add visualization tabs if available
        if MESH_VIEWER_AVAILABLE:
            # Add mesh viewer tab
            self.mesh_viewer_tab = MeshViewerTab(self)
            self.tab_widget.addTab(self.mesh_viewer_tab, "Mesh Viewer")
            print("Mesh Viewer tab added")
        
        if NIFTI_VIEWER_AVAILABLE:
            # Add NIfTI viewer tab
            self.nifti_viewer_tab = NiftiViewerTab(self)
            self.tab_widget.addTab(self.nifti_viewer_tab, "NIfTI Viewer")
            print("NIfTI Viewer tab added")
        
        main_layout.addWidget(self.tab_widget)
        
        # If visualization modules are not available, add a help text
        if not (MESH_VIEWER_AVAILABLE or NIFTI_VIEWER_AVAILABLE):
            help_text = QtWidgets.QLabel(
                "Visualization tabs are not available. Install PyOpenGL and nibabel packages to enable them."
            )
            help_text.setStyleSheet("color: orange; padding: 5px;")
            help_text.setAlignment(QtCore.Qt.AlignCenter)
            main_layout.addWidget(help_text)
        
        # Set window properties
        self.resize(1000, 800)
        
    def closeEvent(self, event):
        """Handle window close event."""
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm Exit',
            "Are you sure you want to exit?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

def main():
    """Main entry point for the application."""
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Set up the main window
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 