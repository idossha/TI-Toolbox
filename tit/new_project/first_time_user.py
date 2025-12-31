from PyQt5 import QtWidgets, QtCore

import json
import logging
import os
import os.path
from datetime import datetime

from tit import __version__

# Set up logging
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())
logger.setLevel(logging.INFO)
logger.propagate = False  # Prevent propagation to root logger


def get_status_file_path():
    """
    Get the path to the status file in the project directory.
    The file will be stored in /mnt/PROJECT_DIR_NAME/derivatives/ti-toolbox/.ti-toolbox-info/project_status.json
    """
    # Get project directory from environment
    project_dir = os.environ.get('PROJECT_DIR', '')
    if not project_dir:
        project_dir = f"/mnt/{os.environ.get('PROJECT_DIR_NAME', 'BIDS_new')}"
    
    info_dir = os.path.join(project_dir, 'derivatives', 'ti-toolbox', '.ti-toolbox-info')
    return os.path.join(info_dir, 'project_status.json')

def initialize_project_status(project_dir):
    """
    Initialize the project status file with default values.
    This is called when a new project is created or when the status file is missing.
    Creates the BIDS-compliant directory structure and initializes project tracking.
    """
    status_file = get_status_file_path()
    info_dir = os.path.dirname(status_file)
    
    # Create info directory if it doesn't exist
    if not os.path.exists(info_dir):
        os.makedirs(info_dir, exist_ok=True)
        logger.info(f"Created info directory: {info_dir}")
    
    # Ensure core BIDS directories exist
    core_dirs = [
        os.path.join(project_dir, 'sourcedata'),
        os.path.join(project_dir, 'derivatives', 'tit'),
        os.path.join(project_dir, 'derivatives', 'SimNIBS'),
        os.path.join(project_dir, 'derivatives', 'freesurfer'),
        os.path.join(project_dir, 'code', 'tit', 'config')
    ]
    
    for dir_path in core_dirs:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path, exist_ok=True)
            logger.info(f"Created BIDS directory: {dir_path}")
    
    # Default status data
    status_data = {
        'project_created': datetime.now().isoformat(),
        'last_updated': datetime.now().isoformat(),
        'config_created': False,
        'example_data_copied': False,
        'user_preferences': {
            'show_welcome': True
        },
        'project_metadata': {
            'name': os.path.basename(project_dir),
            'path': project_dir,
            'version': __version__
        }
    }
    
    # Write initial status file
    try:
        with open(status_file, 'w') as f:
            json.dump(status_data, f, indent=2)
        logger.info(f"Initialized project status file at {status_file}")
        return status_data
    except Exception as e:
        logger.error(f"Failed to initialize project status file: {e}")
        return None

def get_project_status():
    """
    Get the current project status, initializing if necessary.
    Returns the status data dictionary or None if initialization fails.
    """
    status_file = get_status_file_path()
    project_dir = os.environ.get('PROJECT_DIR', '')
    
    if not os.path.exists(status_file):
        return initialize_project_status(project_dir)
    
    try:
        with open(status_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read project status file: {e}")
        return initialize_project_status(project_dir)

def update_project_status(updates):
    """
    Update specific fields in the project status file.
    Args:
        updates (dict): Dictionary containing the fields to update
    Returns:
        bool: True if update was successful, False otherwise
    """
    status_file = get_status_file_path()
    current_status = get_project_status()
    
    if not current_status:
        logger.error("Failed to get current project status")
        return False
    
    # Update the status data
    current_status.update(updates)
    current_status['last_updated'] = datetime.now().isoformat()
    
    try:
        with open(status_file, 'w') as f:
            json.dump(current_status, f, indent=2)
        logger.info(f"Updated project status file at {status_file}")
        return True
    except Exception as e:
        logger.error(f"Failed to update project status file: {e}")
        return False

def check_first_time_user(project_dir):
    """
    Check if this is the first time the user is running the GUI.
    Returns True if it's the first time, False otherwise.
    """
    status_data = get_project_status()
    if not status_data:
        return True
    
    return status_data.get('user_preferences', {}).get('show_welcome', True)

def mark_user_as_experienced(project_dir):
    """
    Mark the user as experienced by updating the show_welcome preference.
    This is called when the user checks "Don't show this message again".
    """
    updates = {
        'user_preferences': {
            'show_welcome': False
        }
    }
    return update_project_status(updates)

def show_welcome_message(parent=None):
    """
    Show a welcome message to first-time users using PyQt5.
    The message includes a checkbox to prevent showing it again.
    """
    try:
        msg_box = QtWidgets.QMessageBox(parent)
        msg_box.setWindowTitle("Welcome to TI-Toolbox")
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        
        message = """
Welcome to the TI-Toolbox!

This toolbox provides a user-friendly interface for:
• Pre-processing structural MRI data and analyze anatomical structures
• Optimizing electrode positions for ROI targeting
• Running flexible uTI & mTI simulations
• Analyzing and visualizing results

The interface is organized into several tabs:
1. Pre-process: Prepare your structural data
3. ex/flex-search: Find optimal electrode positions
2. Simulator: Run TI simulations
4. Analyzer: Analyze results & view in mesh/voxel spaces
5. Nifti-viewer: View simulations and analyses in voxel space

Each tab has its own configuration options and help buttons.
Feel free to explore the interface and check the documentation for more details.
        """
        
        msg_box.setText(message)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)
        
        # Create and set the checkbox
        checkbox = QtWidgets.QCheckBox("Don't show this message again")
        msg_box.setCheckBox(checkbox)
        
        # Center the dialog relative to the parent window
        if parent and parent.isVisible():
            main_rect = parent.geometry()
            dialog_size = msg_box.sizeHint()
            x = main_rect.x() + (main_rect.width() - dialog_size.width()) // 2
            y = main_rect.y() + (main_rect.height() - dialog_size.height()) // 2
            msg_box.move(x, y)
        
        # Show the message box
        msg_box.exec_()
        
        # If checkbox is checked, mark user as experienced
        if checkbox.isChecked():
            project_dir = os.environ.get('PROJECT_DIR', '')
            if project_dir:
                mark_user_as_experienced(project_dir)
                
    except Exception as e:
        logger.error(f"Error showing welcome message: {e}")

def setup_project_example_data():
    """
    Set up example data for a new project if applicable.
    This function integrates with the example_data_manager module.
    """
    try:
        project_dir = os.environ.get('PROJECT_DIR', '')
        if not project_dir:
            logger.warning("PROJECT_DIR environment variable not set, skipping example data setup")
            return False
        
        # Get the toolbox root directory
        toolbox_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        
        # Import and use the example data manager
        try:
            from . import example_data_manager
            success, subjects = example_data_manager.setup_example_data(toolbox_root, project_dir)
            
            if success and subjects:
                logger.info(f"Successfully set up example data with subjects: {', '.join(subjects)}")
                return True
            else:
                logger.info("Example data setup skipped or failed")
                return False
                
        except ImportError as e:
            logger.warning(f"Could not import example_data_manager: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error setting up example data: {e}")
        return False


def assess_user_status(parent=None):
    """
    Main function to assess user status and show welcome message if needed.
    This is called when the GUI starts up.
    Also handles example data setup for new projects.
    """
    try:
        project_dir = os.environ.get('PROJECT_DIR', '')
        if not project_dir:
            logger.warning("PROJECT_DIR environment variable not set")
            return
        
        # Get or initialize project status
        status = get_project_status()
        
        # Check if this is a completely new project (no example data copied yet)
        if status and not status.get('example_data_copied', False):
            logger.info("New project detected, attempting to set up example data...")
            setup_project_example_data()
        
        # Show welcome message if this is the first time
        if check_first_time_user(project_dir):
            # Ensure we're in the main thread
            if QtCore.QThread.currentThread() == QtWidgets.QApplication.instance().thread():
                show_welcome_message(parent)
            else:
                # If we're not in the main thread, use invokeMethod to show the message
                QtCore.QMetaObject.invokeMethod(
                    QtWidgets.QApplication.instance(),
                    "show_welcome_message",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(QtWidgets.QWidget, parent)
                )
    except Exception as e:
        logger.error(f"Error in assess_user_status: {e}") 
