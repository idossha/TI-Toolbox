#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TI-Toolbox GUI Utilities
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
        msg.setText(
            f"The {item_type} already exists:\n{path}\n\nDo you want to overwrite it?"
        )
        msg.setStandardButtons(
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        msg.setDefaultButton(QtWidgets.QMessageBox.No)
        return msg.exec_() == QtWidgets.QMessageBox.Yes
    return True  # No existing file/directory, so no confirmation needed

def is_important_message(text, message_type, tab_type='general'):
    """
    Summary-based message filtering for clean user experience.

    Args:
        text: The message text to check
        message_type: The type of message ('error', 'warning', 'success', 'info',
                                        'command', 'default')
        tab_type: The type of tab ('general', 'simulator', 'analyzer', 'preprocess',
                                 'flexsearch', 'exsearch')

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
            # Summary headings and starts
            'beginning simulation for subject:',
            # Major step starts/completions
            'montage visualization:',
            'simnibs simulation:',
            'field extraction:',
            'nifti transformation:',
            'results processing:',
            # Completion summaries
            'simulation completed successfully for subject:',
            'pipeline completed successfully',
            # Result output locations
            'simulation completion report written to',
            'results available in:',
            'results saved to:',
            'saved to:'
        ],
        'analyzer': [
            # Summary headline and steps
            'beginning analysis for subject:',
            'field data loading:',
            'cortical analysis:',
            'spherical analysis:',
            'results saving:',
            # Completion summaries
            'analysis completed successfully for subject:',
            'group analysis complete'
        ],
        'flexsearch': [
            # Summary headings and starts
            'beginning flex-search optimization for subject:',
            'single optimization run',
            # Major step starts/completions
            'optimization: starting',
            'optimization: ✓ complete',
            'final electrode simulation: starting',
            'final electrode simulation: ✓ complete',
            # Completion summaries and locations
            'flex-search optimization completed successfully for subject:',
            'results available in:'
        ],
        'exsearch': [
            # Summary headings and starts
            'beginning ex-search optimization for subject:',
            # Major step starts/completions
            'processing roi',
            'ti simulation:',
            'roi analysis:',
            'mesh processing:',
            # Completion summaries and locations
            'ex-search optimization completed successfully for subject:',
            'results available in:'
        ],
        'preprocess': [
            # Summary-mode lines emitted by bash_logging.sh (pass-through)
            'beginning pre-processing for subject:',
            'beginning pre-processing for subject:',  # Exact match for the actual output
            '├─ dicom conversion:',
            '├─ simnibs charm:',
            '├─ freesurfer recon-all:',
            '├─ tissue analysis:',
            '├─ bone analysis:',
            '├─ csf analysis:',
            '├─ skull bone analysis:',
            '└─ pre-processing completed',
            '└─ pre-processing completed successfully for subject:',  # Exact match for completion
            '└─ pre-processing failed for subject:',  # Exact match for failure
            # Backward-compatible allowance for direct script messages (if any leak through)
            'starting dicom to nifti conversion for subject:',
            'simnibs charm completed for subject:',
            'freesurfer recon-all completed for subject:',
            'skull bone analysis completed',
            'tissue analysis completed successfully',
            'all subjects processed successfully',
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
    }

    # Check if text matches any important patterns for the given tab type
    if tab_type in important_patterns:
        text_lower = text.lower()
        if any(pattern.lower() in text_lower for pattern in important_patterns[tab_type]):
            return True

    # Critical error patterns that should always be shown
    error_patterns = [
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
        'cores available',
        'Estimated current calibration error'  # Normal calibration message that shouldn't alert users
    ]

    if any(pattern in text for pattern in filtered_patterns):
        return False

    # Filter out all other verbose messages
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
