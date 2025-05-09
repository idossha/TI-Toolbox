#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 GUI Main Entry Point
This module provides a GUI interface for the TI-CSC-2.0 toolbox.
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import subprocess
from PyQt5 import QtWidgets, QtCore, QtGui

# Import tool-specific modules
from simulator_tab import SimulatorTab
from flex_search_tab import FlexSearchTab
from pre_process_tab import PreProcessTab
from help_tab import HelpTab
from contact_tab import ContactTab
from acknowledgments_tab import AcknowledgmentsTab
from nifti_viewer_tab import NiftiViewerTab

class MainWindow(QtWidgets.QMainWindow):
    """Main window for the TI-CSC-2.0 GUI."""
    
    def __init__(self):
        super(MainWindow, self).__init__()
        
        self.setWindowTitle("TI-CSC-2.0 Toolbox")
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
        self.simulator_tab = SimulatorTab(self)
        self.flex_search_tab = FlexSearchTab(self)
        self.help_tab = HelpTab(self)
        self.contact_tab = ContactTab(self)
        self.acknowledgments_tab = AcknowledgmentsTab(self)
        self.nifti_viewer_tab = NiftiViewerTab(self)
        
        # Clear the tab widget in case we're reordering tabs
        self.tab_widget.clear()
        
        # Step 1: Add functional tabs on the left side
        self.tab_widget.addTab(self.pre_process_tab, "Pre-processing")
        self.tab_widget.addTab(self.simulator_tab, "Simulator")
        self.tab_widget.addTab(self.flex_search_tab, "Flex-Search")
        self.tab_widget.addTab(self.nifti_viewer_tab, "NIfTI Viewer")
        
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
        """Center the window on the screen."""
        # Get the screen geometry
        screen = QtWidgets.QApplication.desktop().screenGeometry()
        # Get the window geometry
        window = self.geometry()
        # Calculate the center point
        x = (screen.width() - window.width()) // 2
        y = (screen.height() - window.height()) // 2
        # Move the window
        self.move(x, y)

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

    def resizeEvent(self, event):
        # Ensure overlays resize with the window
        for tab in [self.pre_process_tab, self.simulator_tab, self.flex_search_tab]:
            if hasattr(tab, '_busy_overlay'):
                tab._busy_overlay.setGeometry(tab.rect())
        super().resizeEvent(event)

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