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
        message_type: The type of message ('error', 'warning', 'success', 'info', 'command', 'default')
        tab_type: The type of tab ('general', 'simulator', 'analyzer', 'preprocess', 'flexsearch', 'exsearch')
    
    Returns:
        bool: True if the message should be shown in non-debug mode
    """
    # Always show critical message types (removed 'info' to be more selective)
    if message_type in ['error', 'warning', 'success']:
        return True
    
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
            'Generating surface mesh for specific field:'
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
            # Essential preprocessing step messages (user requested)
            'Starting processing for',
            'Starting DICOM to NIfTI conversion for subject:',
            'Starting SimNIBS charm for subject:',
            'Starting FreeSurfer recon-all for subject:',  # Only the specific one from recon-all.sh
            'Starting skull bone analysis',
            'Pre-processing for',
            'completed successfully',
            # Additional key step messages from scripts (keep only one of each type)
            'DICOM conversion completed for subject:',  # Only from structural.sh
            'SimNIBS charm completed for subject:',     # Only from structural.sh
            'FreeSurfer recon-all completed for subject:', # Only from structural.sh
            'Skull bone analysis completed',
            'All subjects processed successfully',
            # Simple report completion message (like simulator)
            'Report generation completed',
            # Critical error patterns that indicate real failures
            'segmentation fault',
            'bus error', 
            'illegal instruction',
            'permission denied',
            'command not found',
            'cannot execute',
            'bad interpreter',
            'fatal error',
            'critical error',
            'processing interrupted',
            'validation failed',
            'exited with errors',
            'script failed',
            # Specific preprocessing errors
            'No T1 image found',
            'failed for subject',
            'The following subjects had failures',
            'Please check the logs for more details'
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
    
    # Filter out verbose computational and detailed messages for preprocessing
    if tab_type == 'preprocess':
        # Filter out detailed FreeSurfer optimization and computational output
        if any(pattern in text.upper() for pattern in [
            'IFLAG=', 'LINE SEARCH', 'MCSRCH', 'QUASINEWTONEMA', 'BFGS', 'LBFGS',
            'CONVERGENCE:', 'ITERATION', 'GRADIENT', 'FUNCTION EVALUATION', 
            'ARMIJO', '-LOG(P)', 'TOL ', 'OUTOF QUASINEWTON',
            'DT:', 'RMS RADIAL ERROR=', 'AVGS=', 'FINAL DISTANCE ERROR',
            'DISTANCE ERROR %', '/300:', 'SURFACE RECONSTRUCTION'
        ]):
            return False
            
        # Filter out verbose atlas and report messages (keep only essential ones)
        # Also filter ANY message containing emojis or special characters
        emoji_patterns = ['✓', '📊', '📁', '💡', '❌', '✅', '🎯', '🔍', '📈', '🔄', '   •']
        verbose_shell_patterns = [
            'Non-recon processing completed successfully',  # structural.sh verbose
            'Sequential processing completed',  # structural.sh verbose
            'Completed processing subject:',  # structural.sh verbose
            'Processing subject:',  # structural.sh verbose with core info
            'System configuration:',  # structural.sh verbose
            'Each subject will use all',  # structural.sh verbose
            'Starting SEQUENTIAL processing',  # structural.sh verbose
            'Running SimNIBS charm for subject:',  # structural.sh - duplicate of essential message
            'Running FreeSurfer recon-all for subject:',  # structural.sh - duplicate of essential message
            'Preprocessing completed.',  # duplicate completion message
            # Additional DICOM conversion duplicates
            'DICOM to NIfTI conversion completed successfully for subject:',  # duplicate of "DICOM conversion completed"
            'Processing completed!',  # duplicate completion message from structural.sh
            # Duplicate completion messages from individual scripts
            'SimNIBS charm completed successfully for subject:',  # charm.sh - duplicate
            'FreeSurfer recon-all completed for subject:',  # recon-all.sh - duplicate
            # T2 image messages that don't need to be shown
            'No T2 image found',
            'proceeding with T1 only',
            # FreeSurfer verbose process output
            'lta_convert',
            'tessellation finished',
            'MRIScomputeBorderValues_new',
            'finished in',
            'min',
            'WARN: S lookup',
            'WARN: S explicit',
            'vertex =',
            'recon-all -s',
            'finished without error at',
        ]
        if any(pattern in text for pattern in [
            '[Atlas]',  # Individual atlas messages
            'Report generated:',  # Individual report files (without emoji)
            'Successfully generated',  # Detailed report summary
            'Reports location:',  # Reports directory info
            'Open the HTML files',  # Usage instructions
            'Failed to generate',  # Failed report details
            '=== Generating preprocessing reports ===',  # Verbose report start
            'Generating report for',  # Individual report generation
        ]) or any(emoji in text for emoji in emoji_patterns) or any(pattern in text for pattern in verbose_shell_patterns):
            return False
    

    
    # Default: don't show detailed/verbose messages
    return False


def is_verbose_message(text, tab_type='general'):
    """
    Legacy function for backward compatibility.
    Simplified until summary system is implemented.
    
    Args:
        text: The message text to check
        tab_type: The type of tab
        
    Returns:
        bool: True if the message should be filtered (is verbose)
    """
    # For backward compatibility, assume 'default' message type
    # and invert the result (verbose = not important)
    return not is_important_message(text, 'default', tab_type)
