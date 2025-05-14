import os
import json
from PyQt5 import QtWidgets, QtCore

def check_first_time_user(project_dir):
    """
    Check if this is the first time the user is running the GUI
    Returns True if it's the first time, False otherwise
    """
    info_dir = os.path.join(project_dir, '.ti-csc-info')
    status_file = os.path.join(info_dir, 'project_status.json')
    
    # Create info directory if it doesn't exist
    if not os.path.exists(info_dir):
        os.makedirs(info_dir)
    
    # Check the project status file
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status_data = json.load(f)
                return status_data.get('gui_explain', True)
        except (json.JSONDecodeError, KeyError):
            print("Warning: Could not read project status file")
            return True
    
    return True

def mark_user_as_experienced(project_dir):
    """
    Mark the user as experienced by updating the GUI flag in the status file
    """
    info_dir = os.path.join(project_dir, '.ti-csc-info')
    status_file = os.path.join(info_dir, 'project_status.json')
    
    # Read existing status if file exists
    status_data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status_data = json.load(f)
        except (json.JSONDecodeError, KeyError):
            print("Warning: Could not read project status file")
    
    # Update the GUI flag
    status_data['gui_explain'] = False
    status_data['last_updated'] = QtCore.QDateTime.currentDateTime().toString()
    
    # Write back to file
    with open(status_file, 'w') as f:
        json.dump(status_data, f, indent=2)

def show_welcome_message(parent=None):
    """
    Show a welcome message to first-time users using PyQt5
    """
    try:
        msg_box = QtWidgets.QMessageBox(parent)
        msg_box.setWindowTitle("Welcome to TI-CSC Toolbox")
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        
        message = """
Welcome to the TI-CSC Toolbox!

This toolbox provides a user-friendly interface for:
• Pre-processing structural MRI data
• Running TI simulations
• Optimizing electrode positions
• Analyzing results

The interface is organized into several tabs:
1. Pre-process: Prepare your structural data
2. Simulator: Run TI simulations
3. Optimizer: Find optimal electrode positions
4. Analyzer: View and analyze results

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
        print(f"Error showing welcome message: {e}")

def assess_user_status(parent=None):
    """
    Main function to assess user status and show welcome message if needed
    """
    try:
        project_dir = os.environ.get('PROJECT_DIR', '')
        if not project_dir:
            print("Warning: PROJECT_DIR environment variable not set")
            return
        
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
        print(f"Error in assess_user_status: {e}") 