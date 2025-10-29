#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-Toolbox Confirmation Dialog
This module provides a reusable confirmation dialog for the GUI.
"""

from PyQt5 import QtWidgets, QtCore

class ConfirmationDialog(QtWidgets.QMessageBox):
    """A reusable confirmation dialog that centers itself relative to the main window."""
    
    def __init__(self, parent=None, title="Confirm Action", message="Are you sure?", details=None):
        """Initialize the confirmation dialog.
        
        Args:
            parent: The parent widget
            title: The dialog title
            message: The main message
            details: Additional details to show (optional)
        """
        super().__init__(parent)
        
        # Set up the dialog
        self.setIcon(QtWidgets.QMessageBox.Question)
        self.setWindowTitle(title)
        self.setText(message)
        if details:
            self.setInformativeText(details)
        
        # Add buttons
        self.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        self.setDefaultButton(QtWidgets.QMessageBox.No)
        
        # Center the dialog relative to the main window
        if parent:
            main_window = parent.window()
            if main_window:
                # Get the main window's geometry
                main_rect = main_window.geometry()
                
                # Get the dialog's size
                dialog_size = self.sizeHint()
                
                # Calculate the center position
                x = main_rect.x() + (main_rect.width() - dialog_size.width()) // 2
                y = main_rect.y() + (main_rect.height() - dialog_size.height()) // 2
                
                # Move the dialog to the center
                self.move(x, y)
    
    @staticmethod
    def confirm(parent, title="Confirm Action", message="Are you sure?", details=None):
        """Show the confirmation dialog and return True if confirmed.
        
        Args:
            parent: The parent widget
            title: The dialog title
            message: The main message
            details: Additional details to show (optional)
            
        Returns:
            bool: True if the user confirmed, False otherwise
        """
        dialog = ConfirmationDialog(parent, title, message, details)
        return dialog.exec_() == QtWidgets.QMessageBox.Yes 