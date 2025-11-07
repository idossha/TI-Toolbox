"""
TI-Toolbox Utils Package
This package contains utility functions and modules used across the project.
"""

import os

def confirm_overwrite(parent, path, item_type="file"):
    """
    Show a confirmation dialog when attempting to overwrite an existing file/directory.
    
    Args:
        parent: The parent widget for the dialog
        path: The path to the file/directory that would be overwritten
        item_type: String describing the type of item ("file" or "directory")
        
    Returns:
        bool: True if the user confirms overwrite, False otherwise
    """
    try:
        from PyQt5 import QtWidgets
        if os.path.exists(path):
            msg = QtWidgets.QMessageBox(parent)
            msg.setIcon(QtWidgets.QMessageBox.Warning)
            msg.setWindowTitle("Confirm Overwrite")
            msg.setText(f"The {item_type} already exists:\n{path}\n\nDo you want to overwrite it?")
            msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
            msg.setDefaultButton(QtWidgets.QMessageBox.No)
            return msg.exec_() == QtWidgets.QMessageBox.Yes
        return True  # No existing file/directory, so no confirmation needed
    except ImportError:
        # Fallback if PyQt5 is not available (e.g., in CLI mode)
        if os.path.exists(path):
            response = input(f"The {item_type} already exists: {path}\nDo you want to overwrite it? (y/N): ")
            return response.lower() in ['y', 'yes']
        return True 