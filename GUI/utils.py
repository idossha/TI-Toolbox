#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-CSC-2.0 GUI Utilities
This module provides utility functions for the GUI.
"""

import os
from PyQt5 import QtWidgets

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
    if os.path.exists(path):
        msg = QtWidgets.QMessageBox(parent)
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setWindowTitle("Confirm Overwrite")
        msg.setText(f"The {item_type} already exists:\n{path}\n\nDo you want to overwrite it?")
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        msg.setDefaultButton(QtWidgets.QMessageBox.No)
        return msg.exec_() == QtWidgets.QMessageBox.Yes
    return True  # No existing file/directory, so no confirmation needed 

def is_important_message(text, message_type, tab_type='general'):
    """
    Check if a message is important and should be shown in non-debug mode.
    
    Args:
        text: The message text to check
        message_type: The message type ('error', 'warning', 'info', 'success', 'command', 'debug', 'default')
        tab_type: The type of tab ('general', 'simulator', 'analyzer', 'preprocess', 'flexsearch', 'exsearch')
        
    Returns:
        bool: True if the message should be shown in non-debug mode
    """
    # Always show critical message types (removed 'info' to be more selective)
    if message_type in ['error', 'warning', 'success']:
        return True
    
    # Never show debug messages in non-debug mode
    if message_type == 'debug':
        return False
    
    # Important operational messages that should always be shown
    important_patterns = {
        'general': [
        ],
        'simulator': [
            # Only show these key messages in non-debug mode
            'Starting simulation for montage',
            'Processing pair:',
            'Pipeline completed successfully',
            # Result output locations
            'Simulation completion report written to',
            'results saved to:',
            'saved to:'
        ],
        'analyzer': [
            'ROI contains',
            'TI_max Values:',
            'TI_normal Values:',
            'Focality:',
            'Mean Value:',
            'Max Value:',
            'Min Value:',
            # Result output locations
            'saved to:',
            'written to:',
            'results saved to:',
            'output saved to:',
            'Analysis completed successfully',
            'All results saved to:',
            'Visualization settings saved to:',
            'Average NIfTI saved to:',
            'Group analysis complete'
        ],
        'preprocess': [
        ],
        'flexsearch': [
        ],
        'exsearch': [
        ]
    }
    
    text_lower = text.lower()
    
    # Check general important patterns
    general_patterns = important_patterns.get('general', [])
    if any(pattern.lower() in text_lower for pattern in general_patterns):
        return True
    
    # Check tab-specific important patterns
    tab_patterns = important_patterns.get(tab_type, [])
    if any(pattern.lower() in text_lower for pattern in tab_patterns):
        return True
    
    # For command type messages, be very selective
    if message_type == 'command':
        # Only show specific command patterns that match our whitelist
        tab_patterns = important_patterns.get(tab_type, [])
        return any(pattern.lower() in text_lower for pattern in tab_patterns)
    
    # For info type messages, be selective based on tab-specific patterns
    if message_type == 'info':
        tab_patterns = important_patterns.get(tab_type, [])
        return any(pattern.lower() in text_lower for pattern in tab_patterns)
    
    # Default: don't show detailed/verbose messages
    return False


def is_verbose_message(text, tab_type='general'):
    """
    Legacy function for backward compatibility.
    Now uses the new is_important_message logic.
    
    Args:
        text: The message text to check
        tab_type: The type of tab
        
    Returns:
        bool: True if the message should be filtered (is verbose)
    """
    # For backward compatibility, assume 'default' message type
    # and invert the result (verbose = not important)
    return not is_important_message(text, 'default', tab_type)