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
    Summary-based message filtering for clean user experience.
    
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
            'critical error'
        ]
        
        text_lower = text.lower()
        if any(pattern in text_lower for pattern in error_patterns):
            return True
        
        # Explicitly filter out messages that should not appear in summary mode
        filtered_patterns = [
            'Pre-processing completed for all subjects',
            'Report generation completed',
            'Processing completed!',
            'All subjects processed successfully!',
            'Sequential processing completed',
            'Parallel processing completed',
            'Starting SEQUENTIAL processing',
            'Starting PARALLEL processing',
            'System configuration:',
            'Processing plan:',
            'Each subject will',
            'Will run',
            'cores available'
        ]
        
        if any(pattern in text for pattern in filtered_patterns):
            return False
        
        # Filter out all other verbose messages
        return False
    
    # Always show critical message types for non-preprocessing tabs
    if message_type in ['error', 'warning', 'success']:
        return True
    
    # For analyzer tab, use summary-based filtering similar to preprocessing
    if tab_type == 'analyzer':
        # Show analyzer summary messages (our new clean format)
        analyzer_summary_patterns = [
            'Beginning analysis for subject:',
            'Beginning group analysis for',
            '├─ ',  # Process status lines
            '└─ ',  # Final completion line
        ]
        
        if any(pattern in text for pattern in analyzer_summary_patterns):
            return True
        
        # Filter out verbose analyzer messages that should be handled by summary system
        analyzer_filtered_patterns = [
            'ROI contains',
            'TI_max Values:',
            'TI_normal Values:',
            'Analysis completed successfully',
            'results saved to:',
            'saved to:',
            'Starting analysis for subject:',
            'Subject analysis completed',
            'Group analysis complete',
            'Comprehensive group results',
            'Multiple region analysis results',
            'Performing',
            'analysis on',
            'Initializing',
            'analyzer',
            'Mesh analyzer initialized',
            'Voxel analyzer initialized',
            'initialized successfully',
            'Single region analysis',
            'Multiple region analysis',
            'Arguments validated successfully',
            'Output directory created',
        ]
        
        if any(pattern in text for pattern in analyzer_filtered_patterns):
            return False
        
        # Filter out all other verbose analyzer messages
        return False
    
    # For simulator tab, use summary-based filtering similar to preprocessing and analyzer
    if tab_type == 'simulator':
        # Show simulator summary messages (our new clean format)
        simulator_summary_patterns = [
            'Beginning simulation for subject:',
            '├─ ',  # Process status lines
            '└─ ',  # Final completion line
        ]
        
        if any(pattern in text for pattern in simulator_summary_patterns):
            return True
        
        # Filter out verbose simulator messages that should be handled by summary system
        simulator_filtered_patterns = [
            'Starting simulation for montage',
            'Processing pair:',
            'Pipeline completed successfully',
            'results saved to:',
            'saved to:',
            'Simulation parameters:',
            'Subject ID:',
            'Conductivity:',
            'Simulation Mode:',
            'Intensity:',
            'Electrode Shape:',
            'Electrode Dimensions:',
            'Electrode Thickness:',
            'Visualizing montage:',
            'Running SimNIBS simulation',
            'Processing simulation results',
            'Extracting fields from:',
            'Field extraction completed',
            'Converting meshes to NIfTI',
            'Mesh to NIfTI conversion',
            'Processing TI mesh',
            'Moved and renamed',
            'Verifying files for montage',
        ]
        
        if any(pattern in text for pattern in simulator_filtered_patterns):
            return False
        
        # Filter out all other verbose simulator messages
        return False
    
    # Default: don't show verbose messages
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
