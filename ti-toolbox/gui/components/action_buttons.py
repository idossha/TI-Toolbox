#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Action Buttons Component
Reusable styled buttons for TI-Toolbox GUI (Run, Stop, etc.)
"""

from PyQt5 import QtWidgets


class RunStopButtons(QtWidgets.QWidget):
    """
    Reusable Run/Stop button pair with consistent styling.
    
    Features:
    - Green "Run" button with hover effects
    - Red "Stop" button with hover effects
    - Stop button starts disabled
    - Consistent styling across all tabs
    """
    
    def __init__(self, parent=None, run_text="Run", stop_text="Stop"):
        """
        Initialize the Run/Stop button pair.
        
        Args:
            parent: Parent widget
            run_text: Text for the run button (default: "Run")
            stop_text: Text for the stop button (default: "Stop")
        """
        super(RunStopButtons, self).__init__(parent)
        self.parent = parent
        self.run_text = run_text
        self.stop_text = stop_text
        
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the button UI components."""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        # Run button (Green)
        self.run_btn = QtWidgets.QPushButton(self.run_text)
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        layout.addWidget(self.run_btn)
        
        # Stop button (Red)
        self.stop_btn = QtWidgets.QPushButton(self.stop_text)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                padding: 5px 15px;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #888888;
            }
        """)
        self.stop_btn.setEnabled(False)  # Initially disabled
        layout.addWidget(self.stop_btn)
    
    def connect_run(self, callback):
        """Connect the run button clicked signal."""
        self.run_btn.clicked.connect(callback)
    
    def connect_stop(self, callback):
        """Connect the stop button clicked signal."""
        self.stop_btn.clicked.connect(callback)
    
    def set_running(self, is_running):
        """
        Update button states for running/stopped.
        
        Args:
            is_running: True if process is running, False if stopped
        """
        self.run_btn.setEnabled(not is_running)
        self.stop_btn.setEnabled(is_running)
    
    def enable_run(self):
        """Enable run button, disable stop button."""
        self.set_running(False)
    
    def enable_stop(self):
        """Disable run button, enable stop button."""
        self.set_running(True)
    
    def get_run_button(self):
        """Return the run button widget."""
        return self.run_btn
    
    def get_stop_button(self):
        """Return the stop button widget."""
        return self.stop_btn

