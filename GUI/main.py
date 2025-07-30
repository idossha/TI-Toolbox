#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 GUI Main Entry Point
This module provides a GUI interface for the TI-CSC-2.0 toolbox.
"""

import sys
import os
import subprocess
import requests
from PyQt5 import QtWidgets, QtCore, QtGui

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from version import __version__

# Import tool-specific modules
from simulator_tab import SimulatorTab
from flex_search_tab import FlexSearchTab
from ex_search_tab import ExSearchTab
from pre_process_tab import PreProcessTab
from system_monitor_tab import SystemMonitorTab
from help_tab import HelpTab
from contact_tab import ContactTab
from acknowledgments_tab import AcknowledgmentsTab
from nifti_viewer_tab import NiftiViewerTab
from analyzer_tab import AnalyzerTab

class MainWindow(QtWidgets.QMainWindow):
    """Main window for the TI-CSC GUI."""
    
    def __init__(self):
        super(MainWindow, self).__init__()
        
        self.setWindowTitle("TI-Toolbox")
        # Set window flags to ensure proper window behavior
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        # Allow all window states
        self.setWindowState(QtCore.Qt.WindowNoState)
        # Enable resizing
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        
        self.setup_ui()
        # Always center on screen after setup
        self.center_on_screen()
        
    def setup_ui(self):
        """Set up the user interface."""
        # Central widget and layout
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        
        main_layout = QtWidgets.QVBoxLayout(self.central_widget)
        
        # Create the tab widget for different tools
        self.tab_widget = QtWidgets.QTabWidget()
        
        # Create all tabs first
        self.pre_process_tab = PreProcessTab(self)
        self.flex_search_tab = FlexSearchTab(self)
        self.ex_search_tab = ExSearchTab(self)
        self.simulator_tab = SimulatorTab(self)
        self.analyzer_tab = AnalyzerTab(self)
        self.nifti_viewer_tab = NiftiViewerTab(self)
        self.system_monitor_tab = SystemMonitorTab(self)
        self.help_tab = HelpTab(self)
        self.contact_tab = ContactTab(self)
        self.acknowledgments_tab = AcknowledgmentsTab(self)

        # Connect analyzer tab signals
        self.analyzer_tab.analysis_completed.connect(self.on_analysis_completed)

        # Clear the tab widget in case we're reordering tabs
        self.tab_widget.clear()
        
        # Step 1: Add functional tabs on the left side
        self.tab_widget.addTab(self.pre_process_tab, "Pre-processing")
        self.tab_widget.addTab(self.flex_search_tab, "Flex-Search")
        self.tab_widget.addTab(self.ex_search_tab, "Ex-Search")
        self.tab_widget.addTab(self.simulator_tab, "Simulator")
        self.tab_widget.addTab(self.analyzer_tab, "Analyzer")
        self.tab_widget.addTab(self.nifti_viewer_tab, "NIfTI Viewer")
        self.tab_widget.addTab(self.system_monitor_tab, "System Monitor")

        # Step 2: Count how many tabs we have to calculate positions from the right
        total_tabs = self.tab_widget.count() + 3  # +3 for Help, Contact, and Acknowledgments
        
        # Step 3: Add the utility tabs at the end (right side)
        self.tab_widget.insertTab(total_tabs - 3, self.help_tab, "Help")
        self.tab_widget.insertTab(total_tabs - 2, self.contact_tab, "Contact")
        self.tab_widget.insertTab(total_tabs - 1, self.acknowledgments_tab, "Acknowledgments")
        
        # Set the tab bar with close buttons only for certain tabs
        self.tab_widget.setTabsClosable(False)
        
        main_layout.addWidget(self.tab_widget)
        
        # Set window properties and center on screen
        self.resize(1000, 800)
        self.center_on_screen()
        
    def center_on_screen(self):
        """Center the window on the screen where the window is (multi-monitor aware, modern approach)."""
        app = QtWidgets.QApplication.instance()
        # Use QGuiApplication for modern screen handling
        from PyQt5.QtGui import QGuiApplication
        window_rect = self.frameGeometry()
        center_point = window_rect.center()
        screen = None
        if hasattr(QGuiApplication, 'screenAt'):
            screen = QGuiApplication.screenAt(center_point)
        if screen is None:
            # Fallback: use primary screen
            screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
        else:
            screen_geometry = app.desktop().screenGeometry()
        qr = self.frameGeometry()
        qr.moveCenter(screen_geometry.center())
        self.move(qr.topLeft())

    def closeEvent(self, event):
        """Handle window close event."""
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm Exit',
            "Are you sure you want to exit?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # Clean up system monitor thread before closing
            if hasattr(self, 'system_monitor_tab'):
                self.system_monitor_tab.stop_monitoring()
            event.accept()
        else:
            event.ignore()

    def set_tab_busy(self, tab_widget, busy=True, message="A process is running. Only the Stop button is available.", stop_btn=None):
        """Disable all interactive widgets in the given tab except the provided stop button, and show a message at the top of the tab."""
        interactive_types = (
            QtWidgets.QPushButton, QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QCheckBox,
            QtWidgets.QListWidget, QtWidgets.QRadioButton, QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox,
            QtWidgets.QTextEdit
        )
        for widget in tab_widget.findChildren(QtWidgets.QWidget):
            if stop_btn is not None and widget is stop_btn:
                continue
            # Don't disable output consoles (QTextEdit widgets that are read-only)
            if isinstance(widget, QtWidgets.QTextEdit) and widget.isReadOnly():
                continue
            if isinstance(widget, interactive_types):
                widget.setEnabled(not busy)
        if stop_btn is not None:
            stop_btn.setEnabled(busy)
        # Show/hide message at the top
        if not hasattr(tab_widget, '_busy_message_label'):
            msg_label = QtWidgets.QLabel(tab_widget)
            msg_label.setStyleSheet("color: #d9534f; font-size: 14px; font-weight: bold; padding: 4px 0 4px 0;")
            msg_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            msg_label.hide()
            tab_widget._busy_message_label = msg_label
            # Insert at the top of the main layout if possible
            layout = tab_widget.layout()
            if layout is not None:
                layout.insertWidget(0, msg_label)
        msg_label = tab_widget._busy_message_label
        msg_label.setText(message if busy else "")
        msg_label.setVisible(busy)

    def showEvent(self, event):
        super().showEvent(event)
        self.center_on_screen()

    def resizeEvent(self, event):
        # Ensure overlays resize with the window
        for tab in [self.pre_process_tab, self.simulator_tab, self.flex_search_tab]:
            if hasattr(tab, '_busy_overlay'):
                tab._busy_overlay.setGeometry(tab.rect())
        super().resizeEvent(event)
        # Optionally, keep window centered after resize (uncomment if desired):
        # self.center_on_screen()

    def on_analysis_completed(self, subject_id, simulation_name, analysis_type):
        """Handle analysis completion by updating relevant tabs."""
        # Guard against recursive calls
        if hasattr(self, '_processing_analysis_completion') and self._processing_analysis_completion:
            return
        
        self._processing_analysis_completion = True
        try:
            # Update NIFTI viewer's analysis regions if it's a voxel analysis
            if analysis_type == 'Voxel':
                # Update the NIFTI viewer's subject and simulation selection
                self.nifti_viewer_tab.subject_combo.setCurrentText(subject_id)
                self.nifti_viewer_tab.sim_combo.setCurrentText(simulation_name)
                # Update available analyses for the current subject and simulation
                self.nifti_viewer_tab.update_available_analyses()
                
            # Update mesh files list if it's a mesh analysis
            if analysis_type == 'Mesh':
                # Update the mesh files list in the analyzer tab
                self.analyzer_tab.update_mesh_files()
                self.analyzer_tab.update_field_files()
        finally:
            self._processing_analysis_completion = False

def parse_version(version_str):
    """Parse a version string into a tuple of integers for comparison. Non-integer parts are ignored."""
    parts = version_str.strip().split('.')
    version_tuple = []
    for part in parts:
        try:
            version_tuple.append(int(part))
        except ValueError:
            # Ignore non-integer parts (e.g., 'rc', 'beta')
            break
    return tuple(version_tuple)

def check_for_update(current_version, parent_window=None):
    """Check for updates and show a notification dialog if a newer version is available.
    
    Args:
        current_version (str): The current version of the application
        parent_window (QWidget, optional): The parent window to center the dialog on
    """
    try:
        url = "https://raw.githubusercontent.com/idossha/TI-CSC-2.0/main/docs/latest_version.txt"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            latest_version = response.text.strip()
            if latest_version:
                # Only prompt if remote version is strictly newer
                if parse_version(latest_version) > parse_version(current_version):
                    msg_box = QtWidgets.QMessageBox(parent_window)
                    msg_box.setIcon(QtWidgets.QMessageBox.Information)
                    msg_box.setWindowTitle("Update Available")
                    msg_box.setText(f"A new version of TI-CSC-2.0 is available!")
                    msg_box.setInformativeText(
                        f"Current version: {current_version}\n"
                        f"Latest version: {latest_version}\n\n"
                        f"Visit:\nhttps://github.com/idossha/TI-CSC-2.0/releases"
                    )
                    msg_box.setWindowModality(QtCore.Qt.ApplicationModal)
                    # Center the dialog relative to the main window
                    if parent_window:
                        # Get the main window's geometry
                        main_rect = parent_window.geometry()
                        # Get the dialog's size
                        dialog_size = msg_box.sizeHint()
                        # Calculate the center position
                        x = main_rect.x() + (main_rect.width() - dialog_size.width()) // 2
                        y = main_rect.y() + (main_rect.height() - dialog_size.height()) // 2
                        # Move the dialog to the center
                        msg_box.move(x, y)
                    msg_box.exec_()
    except Exception as e:
        print(f"Error checking for updates: {e}")  # Print to console for debugging
        pass  # Continue execution

def main():
    """Main entry point for the application."""
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Set up the main window
    window = MainWindow()
    window.show()
    
    # Check if this is a first-time user after a short delay
    from new_project.first_time_user import assess_user_status
    QtCore.QTimer.singleShot(500, lambda: assess_user_status(window))
    
    # Check for updates after a short delay to ensure window is fully shown
    QtCore.QTimer.singleShot(1000, lambda: check_for_update(__version__, window))
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 
