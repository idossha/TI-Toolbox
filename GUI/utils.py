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
        message_type: The message type ('error', 'warning', 'info', 'success', 'command', 'debug', 'default')
        tab_type: The type of tab
        
    Returns:
        bool: True if the message should be shown in non-debug mode
    """
    # Never show debug messages in non-debug mode
    if message_type == 'debug':
        return False
    
    # For preprocessing tab, use summary-based filtering
    if tab_type == 'preprocess':
        # Show summary messages (our new clean format)
        summary_patterns = [
            'Beginning pre-processing for subject:',
            '├─ ',  # Process status lines
            '└─ ',  # Final completion line
        ]
        
        if any(pattern in text for pattern in summary_patterns):
            return True
        
        # Filter out atlas segmentation warnings - these should be handled by summary system
        atlas_warning_patterns = [
            'm2m folder not found, skipping atlas segmentation',
            'Atlas segmentation completed but some files missing',
            'Atlas segmentation failed'
        ]
        
        if any(pattern in text for pattern in atlas_warning_patterns):
            return False
        
        # Show critical errors that aren't captured by summary system
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
            'cores available'
        ]
        
        if any(pattern in text for pattern in filtered_patterns):
            return False
        
        # Filter out all other verbose messages
        return False
    
    # Always show critical message types for non-preprocessing tabs, except for calibration errors in specific tabs
    if message_type in ['error', 'warning', 'success']:
        # Special case: filter out calibration errors in ex-search and flex-search tabs even if marked as 'error'
        if (tab_type == 'exsearch' or tab_type == 'flexsearch') and 'Estimated current calibration error:' in text:
            return False
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
    
    # For flex search tab, use summary-based filtering similar to other tabs
    if tab_type == 'flexsearch':
        # Show flex search summary messages (our new clean format)
        flexsearch_summary_patterns = [
            'Beginning flex-search optimization for subject:',
            '├─ ',  # Process status lines
            '└─ ',  # Final completion line
            'Optimization run 1/3: ✓ Complete',
            'Optimization run 2/3: ✓ Complete',
            'Optimization run 3/3: ✓ Complete',
            'Optimization run 4/3: ✓ Complete',
            'Optimization run 5/3: ✓ Complete',
            'Optimization run 6/3: ✓ Complete',
            'Optimization run 7/3: ✓ Complete',
            'Optimization run 8/3: ✓ Complete',
            'Optimization run 9/3: ✓ Complete',
            'Optimization run 10/3: ✓ Complete',
        ]
        
        if any(pattern in text for pattern in flexsearch_summary_patterns):
            return True
        
        # Filter out verbose flex search messages that should be handled by summary system
        flexsearch_filtered_patterns = [
            'Starting optimization',
            'OPTIMIZATION RUN',
            'SINGLE OPTIMIZATION RUN',
            'OPTIMIZATION CONFIGURATION:',
            'Subject:',
            'Goal:',
            'Post-processing:',
            'ROI Method:',
            'EEG Net:',
            'Electrode Radius:',
            'Electrode Current:',
            'Volume Atlas:',
            'ROI Label:',
            'Hemisphere:',
            'ROI Center',
            'ROI Radius:',
            'Non-ROI Method:',
            'Threshold Values:',
            'Electrode Mapping:',
            'Run Mapped Simulation:',
            'OPTIMIZATION ALGORITHM SETTINGS:',
            'Max Iterations:',
            'Population Size:',
            'CPU Cores:',
            'Multi-start Runs:',
            'MULTI-START OPTIMIZATION',
            'OPTIMIZATION RUN COMPLETED:',
            'Function Value:',
            'Optimization Duration:',
            'Total Run Duration:',
            'Function Evaluations:',
            'Optimization Success:',
            'MULTI-START OPTIMIZATION POST-PROCESSING',
            'OPTIMIZATION RESULTS SUMMARY:',
            'Valid runs:',
            'Failed runs:',
            'BEST SOLUTION SELECTION:',
            'Best run:',
            'Best function value:',
            'Improvement over worst:',
            'Function value range:',
            'FINALIZING RESULTS:',
            'Copying best solution',
            'Best solution successfully copied',
            'Failed to copy best solution',
            'Best solution folder not found',
            'CLEANING UP TEMPORARY DIRECTORIES:',
            'Removed temporary directory',
            'Failed to remove temporary directory',
            'All temporary directories cleaned up',
            'Some temporary directories could not be removed',
            'MULTI-START OPTIMIZATION COMPLETED SUCCESSFULLY',
            'SINGLE OPTIMIZATION COMPLETED SUCCESSFULLY',
            'Final function value:',
            'Results available in:',
            'Optimization summary saved to:',
            'Failed to create optimization summary file',
            'FLEX-SEARCH SESSION COMPLETED',
            'Total session duration:',
            'Optimization runs:',
            'Base output directory:',
            'Command:',
            'Running multi-start optimization',
            'Running single optimization',
            'Run output folder:',
            'Set max iterations to',
            'Set population size to',
            'opt._optimizer_options_std not found',
            'cannot set disp for quiet mode',
            'cannot set maxiter',
            'cannot set popsize',
            'Transforming MNI coordinates',
            'Transformed coordinates:',
            'Transforming non-ROI MNI coordinates',
            'Transformed non-ROI coordinates:',
            'MNI coordinate transformation failed',
            'Non-ROI coordinate transformation failed',
            'Volume atlas file not found',
            'Non-ROI volume atlas file not found',
            'EEG net file not found',
            '--thresholds required for focality goal',
            '--non-roi-method required for focality goal',
            'PROJECT_DIR env-var is missing',
            'IndexError in run',
            'This error may occur during final analysis',
            'Setting penalty value for run',
            'ERROR in optimization run',
            'Error type:',
            'Error message:',
            'Full traceback:',
            'Setting penalty value for run',
            'No valid optimization results found',
            'Check individual run logs above',
            'No valid optimization results found - all runs failed',
            'Estimated current calibration error:',
            'OPTIMIZATION RUN COMPLETED:',
            'SINGLE OPTIMIZATION COMPLETED SUCCESSFULLY',
            'Optimization process completed.',
            # Additional patterns to suppress command and environment output
            'Running optimization for subject',
            'this may take a while',
            'Environment for subprocess will include:',
            'PROJECT_DIR:',
            'SUBJECT_ID:',
            'ROI_X:',
            'ROI_Y:',
            'ROI_Z:',
            'ROI_RADIUS:',
            'ATLAS_PATH:',
            'SELECTED_HEMISPHERE:',
            'ROI_LABEL:',
            'VOLUME_ATLAS_PATH:',
            'VOLUME_ROI_LABEL:',
            'NON_ROI_X:',
            'NON_ROI_Y:',
            'NON_ROI_Z:',
            'NON_ROI_RADIUS:',
            'NON_ROI_ATLAS_PATH:',
            'NON_ROI_HEMISPHERE:',
            'NON_ROI_LABEL:',
            'VOLUME_NON_ROI_ATLAS_PATH:',
            'VOLUME_NON_ROI_LABEL:',
            'USE_MNI_COORDS:',
            'USE_MNI_COORDS_NON_ROI:',
        ]
        
        if any(pattern in text for pattern in flexsearch_filtered_patterns):
            return False
        
        # Filter out all other verbose flex search messages
        return False
    
    # For ex-search tab, use summary-based filtering similar to other tabs
    if tab_type == 'exsearch':
        # Show ex-search summary messages (our new clean format)
        exsearch_summary_patterns = [
            'Beginning ex-search optimization for subject:',
            '├─ ',  # Process status lines
            '└─ ',  # Final completion line
            'Processing ROI',
            'Step 1: Running TI simulation...',
            'Step 2: Running ROI analysis...',
            'Step 3: Running mesh processing...',
            'TI simulation completed',
            'ROI analysis completed',
            'Mesh processing completed',
            'ROI processing completed',
            'Ex-search optimization completed successfully',
        ]
        
        if any(pattern in text for pattern in exsearch_summary_patterns):
            return True
        
        # Filter out verbose ex-search messages that should be handled by summary system
        exsearch_filtered_patterns = [
                    'Looking for subjects in:',
                    '=== Subjects Found ===',
                    'Found ',
                    'EEG net templates for subject',
                    'unique atlases for subject',
                    'subcortical segmentation for subject',
                    'Running optimization for subject',
                    'Command: ',
                    'Environment for subprocess will include:',
                    'PROJECT_DIR:',
                    'SUBJECT_ID:',
                    'ROI_X:',
                    'ROI_Y:',
                    'ROI_Z:',
                    'ROI_RADIUS:',
                    'labeling.nii.gz with LUT file',
                    'with LUT file',
                    'atlases for subject',
                    'segmentation for subject',
                    'Ex-search log file:',
                    'Using leadfield:',
                    'HDF5 file:',
                    'ROI coordinates:',
                    'Output directory: ex-search/',
                    'Welcome to Ex-Search Optimization!',
                    'Checking available subjects and leadfields...',
                    'Found ',
                    'subject(s):',
                    'Total leadfield matrices:',
                    'Subjects with leadfields:',
                    'Subjects without leadfields:',
                    'To start optimization:',
                    'Selected ROI(s):',
                    'Running optimization for subject',
                    '=== Processing ROI',
                    '--- Processing ROI',
                    'Optimization process completed!',
                    'Estimated current calibration error:',
                    'OPTIMIZATION RUN COMPLETED:',
                    'SINGLE OPTIMIZATION COMPLETED SUCCESSFULLY',
                    'Optimization process completed.',
                    'function value:',
                    'completed during optimization',
                    'Running optimization for subject',
                    'this may take a while',
                    'simnibs_python',
                    '--subject',
                    '--goal',
                    '--postproc',
                    '--eeg-net',
                    '--radius',
                    '--current',
                    '--roi-method',
                    '--enable-mapping',
                    '--disable-mapping-simulation',
                    '--quiet',
                    '--n-multistart',
                    '--max-iterations',
                    '--population-size',
                    '--cpus',
                    'Stopping optimization...',
                    'Optimization stopped.',
                ]
        
        if any(pattern in text for pattern in exsearch_filtered_patterns):
            return False
        
        # Filter out all other verbose ex-search messages
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
    # For now, don't filter any messages (show everything)
    # TODO: Remove this function when summary system is implemented
    return False