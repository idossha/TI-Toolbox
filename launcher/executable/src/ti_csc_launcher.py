"""
Temporal Interference Toolbox - Cross-Platform Edition
A clean, robust launcher for the Temporal Interference Toolbox Docker environment with full Windows/macOS/Linux support.

Key Features:
- Cross-platform Docker detection and management
- Unified CLI approach for GUI launch (eliminates complex X11 debugging)
- No terminal flickering on Windows (silent subprocess execution)
- Auto-scrolling console with real-time progress tracking
- Comprehensive error handling with platform-specific guidance
- Qt compatibility layer supporting both PyQt6 and PySide6

Recent Improvements:
- Simplified GUI launch using proven CLI method across all platforms
- Removed 125+ lines of complex GUI debugging code
- Enhanced Windows compatibility with hidden terminal execution
- Unified subprocess handling preventing window flashing
"""

import os
import sys
import subprocess
import platform
import time
import shutil
import datetime
import tempfile
import threading
import re

# Ensure repo root is in sys.path for version.py import
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from qt_compat import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QMessageBox, QFrame, Qt, QTimer, QFont, QIcon
)

# Try to import yaml, with fallback if not available
try:
    import yaml
except ImportError:
    yaml = None

# Import our dialog classes
from dialogs import (
    SystemRequirementsDialog, ProjectHelpDialog, VersionInfoDialog, StyledMessageBox
)
from shortcuts_manager import ShortcutsManager
from docker_worker import DockerWorkerThread
from progress_widget import ProgressWidget, StoppableOperationWidget

# Add parent directory to path to import version module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    import version
except ImportError:
    # Fallback if version module not found
    class MockVersion:
        __version__ = "2.1.2"
        def get_version_info(self):
            return {"ti_toolbox": {"version": "2.1.0", "release_date": "Unknown", "build": "unknown"}}
    version = MockVersion()


def run_subprocess_silent(cmd, **kwargs):
    """
    Cross-platform subprocess runner that prevents window flashing on Windows
    """
    # Set up default kwargs
    default_kwargs = {
        'capture_output': True,
        'text': True,
        'timeout': 30
    }
    default_kwargs.update(kwargs)
    
    # On Windows, prevent window flashing
    if platform.system() == "Windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        default_kwargs['startupinfo'] = startupinfo
        default_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    
    return subprocess.run(cmd, **default_kwargs)


class TIToolboxLoaderApp(QWidget):
    """Main Temporal Interference Toolbox Application"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Temporal Interference Toolbox")
        
        # Set minimum size constraints to prevent design problems
        self.setMinimumSize(900, 500)
        
        # Set initial size and position (not fullscreen)
        self.resize(800, 650)
        self.move(100, 100)

        # Initialize state variables
        self.project_dir = ""
        self.containers_running = False
        self.containers_ever_started = False  # Track if containers have ever been started
        self.cli_launching = False
        self.containers_started_by_launcher = False  # Track if we started the containers
        self.worker_thread = None  # For background Docker operations
        self.operation_cancelled = False  # Track if user cancelled operation
        
        # Setup paths and managers
        self._setup_paths()
        self._initialize_managers()
        
        # Initialize UI
        self.init_ui()

    def _setup_paths(self):
        """Setup Docker and file paths"""
        # Get the directory containing the script/executable
        if getattr(sys, 'frozen', False):
            # If we're running as a PyInstaller bundle
            self.script_dir = sys._MEIPASS
        else:
            # If we're running from source, the docker-compose.yml is in the same directory as this script
            self.script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # The docker-compose.yml will be in the script directory (for source) or bundle root (for executable)
        self.docker_compose_file = os.path.join(self.script_dir, "docker-compose.yml")
        
        if not os.path.exists(self.docker_compose_file):
            # Debug prints (remove for production)
            # print(f"Warning: docker-compose.yml not found at {self.docker_compose_file}")
            # print(f"Current directory contents: {os.listdir(self.script_dir)}")
            pass
        
        self._setup_docker_path()

    def _initialize_managers(self):
        """Initialize manager classes"""
        self.shortcuts_manager = ShortcutsManager(logger=self.log_message)
        self.message_box = StyledMessageBox(self)

    def _setup_docker_path(self):
        """Set up PATH to include common Docker locations"""
        system = platform.system()
        
        if system == "Windows":
            # Windows Docker Desktop locations
            docker_paths = [
                r'C:\Program Files\Docker\Docker\resources\bin',
                r'C:\ProgramData\DockerDesktop\version-bin',
                r'C:\Users\Public\Documents\Hyper-V\Virtual Hard Disks',
                os.path.expanduser(r'~\AppData\Local\Docker\wsl\distro\bin'),
            ]
            path_separator = ';'
            current_path = os.environ.get('PATH', '')
            path_parts = current_path.split(path_separator) if current_path else []
        else:
            # macOS and Linux Docker locations
            docker_paths = [
                '/usr/local/bin',
                '/opt/homebrew/bin',
                '/Applications/Docker.app/Contents/Resources/bin',
                '/usr/bin',
                '/bin'
            ]
            path_separator = ':'
            current_path = os.environ.get('PATH', '')
            path_parts = current_path.split(path_separator) if current_path else []
        
        # Add Docker paths to PATH if they exist
        for docker_path in docker_paths:
            if docker_path not in path_parts and os.path.exists(docker_path):
                path_parts.insert(0, docker_path)
        
        os.environ['PATH'] = path_separator.join(path_parts)

    def _find_docker_executable(self):
        """Find the Docker executable using cross-platform methods"""
        # Try shutil.which first (most reliable)
        docker_path = shutil.which('docker')
        if docker_path and os.path.exists(docker_path):
            return docker_path
        
        # Platform-specific fallback locations
        system = platform.system()
        
        if system == "Windows":
            locations = [
                r'C:\Program Files\Docker\Docker\resources\bin\docker.exe',
                r'C:\ProgramData\DockerDesktop\version-bin\docker.exe'
            ]
        elif system == "Darwin":  # macOS
            locations = [
                '/usr/local/bin/docker',
                '/opt/homebrew/bin/docker',
                '/Applications/Docker.app/Contents/Resources/bin/docker'
            ]
        else:  # Linux
            locations = [
                '/usr/local/bin/docker',
                '/usr/bin/docker',
                '/bin/docker',
                '/snap/bin/docker',
                os.path.expanduser('~/.local/bin/docker')
            ]
        
        # Check fallback locations
        for location in locations:
            if os.path.exists(location) and (system == "Windows" or os.access(location, os.X_OK)):
                return location
        
        # Final test: try running docker --version
        for cmd in ['docker', 'docker.exe']:
            try:
                result = run_subprocess_silent([cmd, '--version'], timeout=5)
                if result.returncode == 0:
                    return cmd
            except Exception:
                continue
        
        self.log_message("Docker executable not found", "ERROR")
        return None

    # Dialog Methods (using new classes)
    def show_requirements_help(self):
        """Show system requirements dialog"""
        dialog = SystemRequirementsDialog(self)
        dialog.show()

    def show_project_help(self):
        """Show project directory help dialog"""
        dialog = ProjectHelpDialog(self)
        dialog.show()

    def show_version_info(self):
        """Show version information dialog"""
        dialog = VersionInfoDialog(self, logger=self.log_message)
        dialog.show()

    def show_shortcuts_menu(self):
        """Create desktop shortcut"""
        success = self.shortcuts_manager.create_desktop_shortcut()
        if success:
            self.log_message("Desktop shortcut created successfully", "SUCCESS")
            self.message_box.show_message(
                "Shortcut Created",
                "Desktop shortcut created successfully!\n\nYou can now double-click the TI-toolbox icon on your desktop to launch the application.",
                "success",
                ""
            )
        else:
            self.log_message("Failed to create desktop shortcut", "ERROR")
            self.message_box.show_message(
                "Shortcut Error",
                "Failed to create desktop shortcut.\n\nCheck the console output for details.",
                "error",
                ""
            )

    def init_ui(self):
        """Initialize the user interface"""
        main_layout = QVBoxLayout()

        # Header Section
        self._create_header_section(main_layout)
        
        # Project Directory Selection
        self._create_directory_section(main_layout)
        
        # Docker Control
        self._create_docker_control_section(main_layout)
        
        # Console Output
        self._create_console_section(main_layout)
        
        # Progress widgets
        self.progress_widget = ProgressWidget(self)
        main_layout.addWidget(self.progress_widget)
        
        self.stop_widget = StoppableOperationWidget(self)
        self.stop_widget.stop_button.clicked.connect(self.stop_current_operation)
        main_layout.addWidget(self.stop_widget)

        self.setLayout(main_layout)
        
        # Initial message
        self.log_user_message("Welcome to TI-Toolbox!")
        self.log_user_message("Steps to get started:")
        self.log_user_message("  1. Select your project directory")
        self.log_user_message("  2. Click 'Start Docker Containers'")
        self.log_user_message("  3. Launch CLI or GUI once containers are ready")
        self.log_user_message("")
        self.log_user_message("Note: First-time setup may take 15-30 minutes (downloading ~30GB)")

    def _create_header_section(self, main_layout):
        """Create the header section with title, description, and utility buttons"""
        synthesis_frame = QFrame()
        synthesis_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        synthesis_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: none;
                border-radius: 6px;
                padding: 8px;
                margin: 5px;
            }
        """)
        
        synthesis_layout = QVBoxLayout(synthesis_frame)
        synthesis_layout.setContentsMargins(15, 10, 15, 10)
        synthesis_layout.setSpacing(8)
        
        title_label = QLabel("Temporal Interference Toolbox")
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2c3e50;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        desc_label = QLabel(
            "Comprehensive toolbox for Temporal Interference (TI) stimulation research providing end-to-end "
            "neuroimaging and simulation capabilities:\n"
            "• Pre-processing: DICOM→NIfTI conversion, FreeSurfer cortical reconstruction, SimNIBS head modeling\n"
            "• Simulation: FEM-based TI field calculations with enhanced control over simulation parameters\n"
            "• Optimization: evolution and exhaustive search algorithms for optimal electrode placement\n"
            "• Analysis: atlas-based and arbitrary ROI analysis\n"
            "• Visualization: Interactive NIfTI and mesh viewers with overlay capabilities and 3D rendering"
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #6c757d; font-size: 12px; line-height: 1.3;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        synthesis_layout.addWidget(title_label)
        synthesis_layout.addWidget(desc_label)
        
        # Add utility buttons within the intro container - smaller, grey, and centered
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 8, 0, 0)
        
        # Add stretch to center the buttons
        buttons_layout.addStretch()
        
        # Requirements Button
        self.requirements_button = QPushButton("System Requirements")
        self.requirements_button.clicked.connect(self.show_requirements_help)
        self.requirements_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 9px;
                font-weight: bold;
                padding: 4px 8px;
                border: none;
                border-radius: 3px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        # Create Shortcuts Button
        self.shortcuts_button = QPushButton("Desktop Shortcut")
        self.shortcuts_button.clicked.connect(self.show_shortcuts_menu)
        self.shortcuts_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 9px;
                font-weight: bold;
                padding: 4px 8px;
                border: none;
                border-radius: 3px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        # Version Info Button
        self.version_button = QPushButton("Version Info")
        self.version_button.clicked.connect(self.show_version_info)
        self.version_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 9px;
                font-weight: bold;
                padding: 4px 8px;
                border: none;
                border-radius: 3px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        # Help Button
        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.show_project_help)
        self.help_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 9px;
                font-weight: bold;
                padding: 4px 8px;
                border: none;
                border-radius: 3px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        buttons_layout.addWidget(self.requirements_button)
        buttons_layout.addWidget(self.shortcuts_button)
        buttons_layout.addWidget(self.version_button)
        buttons_layout.addWidget(self.help_button)
        
        # Add stretch to center the buttons
        buttons_layout.addStretch()
        
        synthesis_layout.addLayout(buttons_layout)
        main_layout.addWidget(synthesis_frame)

    def _create_directory_section(self, main_layout):
        """Create the project directory selection section"""
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel("Project Directory:")
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select your BIDS-compliant project directory")
        self.dir_input.textChanged.connect(self.on_dir_text_changed)
        
        # Path validation indicator
        self.path_indicator = QLabel("")
        self.path_indicator.setFixedWidth(20)
        self.path_indicator.setStyleSheet("font-size: 16px; font-weight: bold;")
        
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_project_dir)

        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(self.path_indicator)
        dir_layout.addWidget(self.browse_button)
        main_layout.addLayout(dir_layout)

    def _create_docker_control_section(self, main_layout):
        """Create the Docker control section with launch buttons"""
        # Docker controls and launch buttons in same row
        controls_layout = QHBoxLayout()
        
        # Docker Toggle button
        self.docker_toggle = QPushButton("Start Docker Containers")
        self.docker_toggle.setCheckable(True)
        self.docker_toggle.clicked.connect(self.toggle_docker_containers)
        self.docker_toggle.setStyleSheet("""
            QPushButton {
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                background-color: #28a745;
                color: white;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:checked {
                background-color: #dc3545;
                color: white;
            }
            QPushButton:checked:hover {
                background-color: #c82333;
            }
        """)
        
        # Docker Status indicator
        self.status_label = QLabel("Docker Status: Not Started")
        self.status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 4px;
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
                font-size: 11px;
                min-width: 120px;
            }
        """)
        
        # Launch CLI button
        self.cli_button = QPushButton(" Launch CLI")
        self.cli_button.clicked.connect(self.launch_cli)
        self.cli_button.setEnabled(False)
        self.cli_button.setStyleSheet("""
            QPushButton {
                background-color: #2E86AB;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #1B6B93;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        
        # Launch GUI button
        self.gui_button = QPushButton(" Launch GUI")
        self.gui_button.clicked.connect(self.launch_gui)
        self.gui_button.setEnabled(False)
        self.gui_button.setStyleSheet("""
            QPushButton {
                background-color: #A23B72;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #8B2C5A;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        
        # Clear console button
        self.clear_console_button = QPushButton("Clear Console")
        self.clear_console_button.clicked.connect(self.clear_console)
        self.clear_console_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                font-size: 12px;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                min-width: 120px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        controls_layout.addWidget(self.docker_toggle)
        controls_layout.addWidget(self.status_label)
        controls_layout.addStretch()
        controls_layout.addWidget(self.cli_button)
        controls_layout.addWidget(self.gui_button)
        controls_layout.addWidget(self.clear_console_button)
        
        main_layout.addLayout(controls_layout)

    def _create_console_section(self, main_layout):
        """Create the console output section"""
        # Console output widget (no header text)
        self.console_output = QTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.setPlaceholderText("Status messages and command output will appear here...")
        self.console_output.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #555;
                padding: 5px;
            }
        """)
        main_layout.addWidget(self.console_output)



    # Core functionality methods
    def update_status_display(self):
        """Update the status display based on container state"""
        if self.containers_running:
            self.status_label.setText("Docker Status: Running")
            self.status_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    padding: 6px 10px;
                    border-radius: 4px;
                    background-color: #d4edda;
                    color: #155724;
                    border: 1px solid #c3e6cb;
                    font-size: 11px;
                }
            """)
            self.docker_toggle.setText("Stop Docker Containers")
            self.docker_toggle.setChecked(True)
            self.cli_button.setEnabled(True)
            self.gui_button.setEnabled(True)
        else:
            # Show different status based on whether containers were ever started
            if self.containers_ever_started:
                self.status_label.setText("Docker Status: Stopped")
            else:
                self.status_label.setText("Docker Status: Not Started")
            
            self.status_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    padding: 6px 10px;
                    border-radius: 4px;
                    background-color: #f8d7da;
                    color: #721c24;
                    border: 1px solid #f5c6cb;
                    font-size: 11px;
                }
            """)
            self.docker_toggle.setText("Start Docker Containers")
            self.docker_toggle.setChecked(False)
            self.cli_button.setEnabled(False)
            self.gui_button.setEnabled(False)

    def toggle_docker_containers(self):
        """Handle the toggle for starting/stopping Docker containers"""
        if self.docker_toggle.isChecked() and not self.containers_running:
            self.start_docker()
        elif not self.docker_toggle.isChecked() and self.containers_running:
            self.stop_docker()

    def log_message(self, message, level="INFO"):
        """Add message to console output with auto-scroll"""
        if level == "ERROR":
            color_start = '<span style="color: #ff6b6b;">'  # Red for errors
        elif level == "SUCCESS":
            color_start = '<span style="color: #51cf66;">'  # Green for success
        elif level == "WARNING":
            color_start = '<span style="color: #ffd43b;">'  # Yellow for warnings
        else:  # INFO - default white
            color_start = '<span style="color: #ffffff;">'  # White for normal info
        
        color_end = '</span>'
        formatted_message = f"{color_start}{message}{color_end}"
        
        # Add message to console
        self.console_output.append(formatted_message)
        
        # Auto-scroll to bottom to show latest messages
        scrollbar = self.console_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Process events to ensure UI updates immediately
        QApplication.processEvents()
    
    def log_user_message(self, message, level="INFO"):
        """Alias for log_message for backwards compatibility"""
        self.log_message(message, level)

    def clear_console(self):
        """Clear the console output"""
        self.console_output.clear()
        self.log_user_message("Console cleared")

    def stop_current_operation(self):
        """Stop the current Docker operation"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.log_message("Stopping operation...", "WARNING")
            self.operation_cancelled = True
            self.worker_thread.stop()
            self.stop_widget.hide_operation()
            self.progress_widget.clear_all()
        
        # Re-enable docker button
        self.docker_toggle.setEnabled(True)
        self.docker_toggle.setChecked(False)

    def on_dir_text_changed(self):
        """Handle manual text entry in project directory field"""
        entered_path = self.dir_input.text().strip()
        
        # Only validate if the path seems complete (not while user is still typing)
        if entered_path and (entered_path.endswith('/') or entered_path.endswith('\\') or len(entered_path) > 10):
            # Check if path exists
            if os.path.exists(entered_path):
                if os.path.isdir(entered_path):
                    self.project_dir = entered_path
                    # Show green checkmark for valid path
                    self.path_indicator.setText("✓")
                    self.path_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #28a745;")
                else:
                    # Path exists but is not a directory - show red X
                    self.path_indicator.setText("✗")
                    self.path_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #dc3545;")
            else:
                # Path doesn't exist - show red X
                self.path_indicator.setText("✗")
                self.path_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #dc3545;")
        else:
            # Reset to empty while typing
            self.project_dir = entered_path
            self.path_indicator.setText("")

    def browse_project_dir(self):
        """Browse for project directory"""
        directory = QFileDialog.getExistingDirectory(self, "Select Project Directory")
        if directory:
            self.project_dir = directory
            self.dir_input.setText(directory)
            # Show green checkmark for valid path
            self.path_indicator.setText("✓")
            self.path_indicator.setStyleSheet("font-size: 16px; font-weight: bold; color: #28a745;")
            self.log_user_message(f"Project directory selected: {os.path.basename(self.project_dir)}")

    def validate_requirements(self):
        """Validate that all requirements are met before starting Docker"""
        if not self.project_dir or not self.project_dir.strip():
            self.message_box.show_message("Error", "Please select a project directory first", "warning", "")
            self.log_user_message("  No project directory selected", "ERROR")
            return False
        
        # Check if project directory is accessible
        if not os.path.exists(self.project_dir):
            self.message_box.show_message("Error", f"Project directory does not exist:\n{self.project_dir}", "error", "")
            self.log_user_message(f"  Directory not found: {self.project_dir}", "ERROR")
            return False
        
        if not os.access(self.project_dir, os.W_OK):
            self.message_box.show_message("Warning", 
                f"No write permissions in project directory:\n{self.project_dir}\n\nDocker containers may not function properly.",
                "warning", "")
            # Continue anyway - user might have set up specific permissions
        
        # Enhanced Docker validation with Windows-specific handling
        docker_executable = self._find_docker_executable()
        if not docker_executable:
            self.log_message("Docker executable not found", "ERROR")
            self._show_docker_install_instructions()
            return False
        
        # Test Docker connectivity with better error handling
        try:
            self.log_message("Testing Docker connectivity...", "INFO")
            result = run_subprocess_silent([docker_executable, '--version'], timeout=10)
            if result.returncode != 0:
                self.log_message(f"Docker version check failed: {result.stderr}", "ERROR")
                self._show_docker_start_instructions()
                return False
            else:
                self.log_message(f"Docker version: {result.stdout.strip()}", "SUCCESS")
        except subprocess.TimeoutExpired:
            self.log_message("Docker version check timed out", "ERROR")
            self._show_docker_start_instructions()
            return False
        except Exception as e:
            self.log_message(f"Docker test error: {str(e)}", "ERROR")
            self._show_docker_start_instructions()
            return False
        
        # Test Docker daemon connectivity
        try:
            self.log_message("Testing Docker daemon connectivity...", "INFO")
            result = run_subprocess_silent([docker_executable, 'info'], timeout=15)
            if result.returncode != 0:
                self.log_message("Docker daemon is not running or accessible", "ERROR")
                if "permission denied" in result.stderr.lower():
                    self.log_message("Permission issue detected - try running as administrator", "INFO")
                self._show_docker_start_instructions()
                return False
            else:
                self.log_message("Docker daemon is accessible", "SUCCESS")
        except subprocess.TimeoutExpired:
            self.log_message("Docker daemon check timed out", "ERROR")
            self._show_docker_start_instructions()
            return False
        except Exception as e:
            self.log_message(f"Docker daemon test error: {str(e)}", "ERROR")
            self._show_docker_start_instructions()
            return False
        
        # Test Docker Compose
        try:
            self.log_message("Testing Docker Compose...", "INFO")
            result = run_subprocess_silent([docker_executable, 'compose', 'version'], timeout=10)
            if result.returncode != 0:
                self.log_message(" Docker Compose test failed, but continuing...", "WARNING")
                self.log_message(f"Compose error: {result.stderr}", "WARNING")
            else:
                self.log_message(f"Docker Compose: {result.stdout.strip()}", "SUCCESS")
        except Exception as e:
            self.log_message(f" Docker Compose test error: {str(e)}", "WARNING")
        
        self.log_message("All requirements validated", "SUCCESS")
        return True

    def _show_docker_install_instructions(self):
        """Show platform-specific Docker installation instructions"""
        system = platform.system()
        
        if system == "Windows":
            message = (
                "Docker Desktop not found.\n\n"
                "Please:\n"
                "1. Install Docker Desktop for Windows\n"
                "2. Ensure Docker Desktop is running\n"
                "3. Restart this application"
            )
        elif system == "Darwin":
            message = (
                "Docker Desktop not found.\n\n"
                "Please:\n"
                "1. Install Docker Desktop for Mac\n"
                "2. Ensure Docker Desktop is running (whale icon in menu bar)\n"
                "3. Try running 'docker --version' in Terminal"
            )
        else:  # Linux
            message = (
                "Docker not found.\n\n"
                "Please:\n"
                "1. Install Docker using your package manager\n"
                "2. Add user to docker group: sudo usermod -aG docker $USER\n"
                "3. Start Docker service: sudo systemctl start docker\n"
                "4. Try running 'docker --version' in terminal"
            )
        
        self.message_box.show_message("Docker Error", message, "error", "")

    def _show_docker_start_instructions(self):
        """Show platform-specific Docker startup instructions"""
        system = platform.system()
        
        if system == "Windows":
            message = (
                "Docker Desktop is not running.\n\n"
                "Please:\n"
                "1. Start Docker Desktop\n"
                "2. Wait for it to fully start (system tray icon should be stable)\n"
                "3. Try again"
            )
        elif system == "Darwin":
            message = (
                "Docker Desktop is not running.\n\n"
                "Please:\n"
                "1. Start Docker Desktop\n"
                "2. Wait for it to fully start (whale icon in menu bar)\n"
                "3. Try again"
            )
        else:  # Linux
            message = (
                "Docker service is not running.\n\n"
                "Please:\n"
                "1. Start Docker service: sudo systemctl start docker\n"
                "2. Check service status: sudo systemctl status docker\n"
                "3. Ensure user is in docker group\n"
                "4. Try again"
            )
        
        self.message_box.show_message("Docker Error", message, "error", "")

    def setup_display_env(self):
        """Set up DISPLAY environment variable - simplified to match working bash script"""
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # For Docker Desktop on macOS, try to get the host IP
            try:
                result = run_subprocess_silent(['ifconfig', 'en0'], timeout=5)
                if result.returncode == 0:
                    match = re.search(r'inet (\d+\.\d+\.\d+\.\d+)', result.stdout)
                    if match:
                        host_ip = match.group(1)
                        self.log_message(f"Using host IP for DISPLAY: {host_ip}:0", "INFO")
                        return f"{host_ip}:0"
            except:
                pass
            
            # Fallback to localhost
            self.log_message("Using localhost:0 for DISPLAY", "INFO")
            return "localhost:0"
            
        elif system == "Linux":
            return os.environ.get("DISPLAY", ":0")
            
        else:  # Windows
            # Docker Desktop on Windows X11 forwarding
            # Need to find the right host reference for Docker to reach Windows X11
            existing_display = os.environ.get("DISPLAY")
            if existing_display:
                self.log_message(f"Using existing DISPLAY: {existing_display}", "INFO")
                return existing_display
            else:
                # Try different Docker Desktop Windows approaches
                system_info = platform.platform().lower()
                
                # For Docker Desktop on Windows, try host.docker.internal
                if "windows" in system_info:
                    # Try the Docker Desktop internal hostname first
                    self.log_message("Using host.docker.internal:0.0 for Docker Desktop on Windows", "INFO")
                    return "host.docker.internal:0.0"
                else:
                    # Fallback to :0 for other cases
                    self.log_message("Using :0 for DISPLAY", "INFO")
                    return ":0"

    def run_docker_command(self, cmd, description, show_progress=True, timeout=None):
        """Run a Docker command with progress tracking and stop capability"""
        if show_progress:
            self.log_message(f"Running: {description}")
        
        try:
            # Use the full path to docker executable
            if cmd[0] == 'docker':
                docker_executable = self._find_docker_executable()
                if docker_executable:
                    cmd[0] = docker_executable
                else:
                    raise FileNotFoundError("Docker executable not found")
            
            env = os.environ.copy()
            
            # Normalize Windows paths for Docker volume mounting
            if platform.system() == "Windows":
                # Convert Windows path to Docker-compatible format
                # C:\Users\name\project -> C:/Users/name/project
                normalized_path = self.project_dir.replace('\\', '/')
                # Handle potential UNC paths or paths with spaces
                if ' ' in normalized_path and not (normalized_path.startswith('"') and normalized_path.endswith('"')):
                    normalized_path = f'"{normalized_path}"'
                env["LOCAL_PROJECT_DIR"] = normalized_path
                self.log_message(f"Windows path normalized for Docker: {normalized_path}", "INFO")
            else:
                env["LOCAL_PROJECT_DIR"] = self.project_dir
                
            env["PROJECT_DIR_NAME"] = os.path.basename(self.project_dir)
            env["DISPLAY"] = self.setup_display_env()
            
            # For long-running operations, use threaded approach
            if timeout is None or timeout > 300:
                return self._run_docker_command_threaded(cmd, env, description)
            else:
                # For quick operations, use the original method
                result = subprocess.run(cmd, cwd=self.script_dir, env=env, 
                                      capture_output=True, text=True, timeout=timeout)
                
                if result.stdout.strip():
                    self.log_message(result.stdout.strip())
                if result.stderr.strip():
                    self.log_message(result.stderr.strip(), "WARNING")
                
                if result.returncode != 0:
                    self.log_message(f"Command failed with exit code {result.returncode}", "ERROR")
                    return False
                return True
            
        except subprocess.TimeoutExpired:
            self.log_message("Command timed out", "ERROR")
            return False
        except Exception as e:
            self.log_message(f"Command error: {str(e)}", "ERROR")
            return False

    def _run_docker_command_threaded(self, cmd, env, description):
        """Run Docker command using background thread with stop capability"""
        # Reset cancellation flag
        self.operation_cancelled = False
        
        # Only show stop widget for long operations that actually need it
        # Don't show for quick validation operations
        show_progress_widgets = "pull" in " ".join(cmd).lower() or "build" in " ".join(cmd).lower() or "up" in " ".join(cmd).lower()
        
        if show_progress_widgets:
            # Show stop widget only for operations that might take time
            self.stop_widget.show_operation(f"Running: {description}")
        
        # Create and start worker thread
        self.worker_thread = DockerWorkerThread(cmd, env, self.script_dir)
        
        # Connect signals
        self.worker_thread.log_signal.connect(self.log_message)
        if show_progress_widgets:
            self.worker_thread.progress_signal.connect(self.progress_widget.add_layer_progress)
        self.worker_thread.finished_signal.connect(self._on_docker_finished)
        
        # Start the thread
        self.worker_thread.start()
        
        # Wait for completion while keeping UI responsive
        while self.worker_thread.isRunning() and not self.operation_cancelled:
            QApplication.processEvents()
            time.sleep(0.05)  # Small delay to prevent excessive CPU usage
        
        # Hide progress widgets only if we showed them
        if show_progress_widgets:
            self.stop_widget.hide_operation()
            self.progress_widget.clear_all()
        
        # Return success status
        if self.operation_cancelled:
            return False
        return hasattr(self, '_last_command_success') and self._last_command_success

    def _on_docker_finished(self, success, error_message):
        """Handle completion of Docker command"""
        self._last_command_success = success
        self._last_command_error = error_message
        if not success and error_message and not self.operation_cancelled:
            self.log_message(error_message, "ERROR")
            # Also show to user in normal mode
            self.log_user_message(f"  {error_message}", "ERROR")



    def start_docker(self):
        """Start Docker containers with robust volume and image handling"""
        if not self.validate_requirements():
            self.docker_toggle.setChecked(False)
            return
        
        # Check if containers are already running before starting
        running_containers = self._check_existing_containers()
        if running_containers:
            container_list = "\n".join([f"  - {name}" for name in running_containers])
            self.log_message("=" * 60)
            self.log_message("Existing containers detected:")
            self.log_message(container_list)
            self.log_message("")
            self.log_message("Please stop and remove them first using:")
            self.log_message(f"  docker stop {' '.join(running_containers)}")
            self.log_message(f"  docker rm {' '.join(running_containers)}")
            self.log_message("=" * 60)
            self.docker_toggle.setChecked(False)
            return
        
        self.docker_toggle.setEnabled(False)
        self.log_user_message("")
        self.log_user_message("=" * 60)
        self.log_user_message("Starting Docker Environment...")
        self.log_user_message("=" * 60)
        
        try:
            # Step 1: Check Docker connectivity
            self.log_user_message("▶ Step 1/4: Checking Docker")
            self.log_message("Verifying Docker is running...", "INFO")
            # Docker validation already done in validate_requirements
            self.log_user_message("  Docker is running")
            
            # Step 2: Check volumes
            self.log_user_message("▶ Step 2/4: Preparing volumes")
            if not self._ensure_docker_volumes():
                raise Exception("Failed to create required Docker volumes")
            self.log_user_message("  Volumes ready")
            
            # Step 2.5: Setup example data for new projects
            self.log_user_message("▶ Checking for example data...")
            self._setup_example_data()  # This is optional, so we don't fail if it doesn't work
            
            # Step 3: Check images and internet
            self.log_user_message("▶ Step 3/4: Checking Docker images")
            images_exist = self._check_docker_images_exist()
            has_internet = self._check_internet_connectivity()
            
            if not images_exist and not has_internet:
                raise Exception(
                    "Docker images not found locally and no internet connection available.\n\n"
                    "Please connect to the internet to download required images (~30GB)."
                )
            
            if not images_exist and has_internet:
                self.log_user_message("  Downloading Docker images (this may take 15-30 minutes)...")
                self.log_message("Pulling Docker images from registry...", "INFO")
                if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'pull'], 
                                             "Pulling Docker images", show_progress=True, timeout=None):
                    self.log_message(" Image pull failed, attempting to build locally...", "WARNING")
                    if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'build'], 
                                                 "Building Docker images", show_progress=True, timeout=None):
                        raise Exception("Failed to pull or build Docker images")
                self.log_user_message("  Docker images ready")
            else:
                self.log_user_message("  Docker images already available locally")
            
            # Step 4: Start containers
            self.log_user_message("▶ Step 4/4: Starting containers")
            self.log_message("Creating and starting containers...", "INFO")
            start_result = self.run_docker_command(
                ['docker', 'compose', '-f', self.docker_compose_file, 'up', '-d', '--remove-orphans'], 
                "Starting containers", show_progress=True, timeout=None
            )
            
            if not start_result:
                error_detail = getattr(self, '_last_command_error', 'Unknown error')
                # Check if containers actually started despite the error
                if self._check_containers_already_running():
                    # Docker compose can return error codes even when successful
                    self.log_message("Docker compose exit code was non-zero but containers are running (this is normal)", "INFO")
                else:
                    raise Exception(f"Docker compose failed: {error_detail}")
            
            # Verify containers are running and healthy
            self.log_message("Verifying container health...", "INFO")
            if not self._verify_containers_running():
                raise Exception("Containers did not start properly. Try stopping and starting again.")
            
            self.containers_running = True
            self.containers_ever_started = True
            self.containers_started_by_launcher = True
            self.update_status_display()
            
            self.log_user_message("  Containers running")
            self.log_user_message("")
            self.log_user_message("=" * 60, "SUCCESS")
            self.log_user_message("TI-Toolbox is ready!", "SUCCESS")
            self.log_user_message("=" * 60, "SUCCESS")
            self.log_user_message("You can now launch CLI or GUI applications", "SUCCESS")
            self.log_user_message("")
            
        except Exception as e:
            self.log_user_message("")
            self.log_user_message("=" * 60, "ERROR")
            self.log_user_message(f"Startup Failed: {str(e)}", "ERROR")
            self.log_user_message("=" * 60, "ERROR")
            
            self.message_box.show_message(
                "Startup Failed", 
                f"Docker startup failed:\n\n{str(e)}\n\nCheck the console for details or enable Debug Mode for more information.",
                "error", ""
            )
            self.containers_running = False
            self.docker_toggle.setChecked(False)
        
        finally:
            self.docker_toggle.setEnabled(True)

    def _check_internet_connectivity(self):
        """Check if internet connection is available"""
        try:
            self.log_message("Checking internet connectivity...", "INFO")
            # Try to reach a common DNS server
            import socket
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            self.log_message("Internet connection available", "SUCCESS")
            return True
        except OSError:
            self.log_message(" No internet connection detected", "WARNING")
            return False
    
    def _setup_example_data(self):
        """Setup example data (ernie and MNI152) for new projects"""
        try:
            self.log_message("Checking if example data should be copied...", "INFO")
            
            # Find the actual TI-toolbox root directory
            # When frozen, we need to find it relative to the executable location
            if getattr(sys, 'frozen', False):
                # Running as PyInstaller bundle
                # The .app is typically in: TI-toolbox/launcher/executable/dist/TI-Toolbox.app
                # We need to go up several levels to find TI-toolbox root
                executable_path = sys.executable
                
                # Navigate up from the executable to find TI-toolbox root
                # From: /path/to/TI-toolbox/launcher/executable/dist/TI-Toolbox.app/Contents/MacOS/TI-Toolbox
                # To: /path/to/TI-toolbox
                current_path = os.path.dirname(executable_path)  # MacOS
                current_path = os.path.dirname(current_path)  # Contents
                current_path = os.path.dirname(current_path)  # TI-Toolbox.app
                current_path = os.path.dirname(current_path)  # dist
                current_path = os.path.dirname(current_path)  # executable
                current_path = os.path.dirname(current_path)  # launcher
                toolbox_root = os.path.dirname(current_path)  # TI-toolbox
                
                # Verify we found a valid TI-toolbox directory
                # It should have key directories like 'new_project', 'assets', etc.
                if not os.path.exists(os.path.join(toolbox_root, 'new_project')):
                    # Fallback: look for TI-toolbox in common locations
                    home = os.path.expanduser('~')
                    possible_locations = [
                        os.path.join(home, 'TI-toolbox'),
                        os.path.join(home, 'Documents', 'TI-toolbox'),
                        os.path.join(home, 'Desktop', 'TI-toolbox'),
                        '/opt/TI-toolbox',
                        '/usr/local/TI-toolbox'
                    ]
                    
                    for location in possible_locations:
                        if os.path.exists(os.path.join(location, 'new_project')):
                            toolbox_root = location
                            self.log_message(f"Found TI-toolbox at: {toolbox_root}", "INFO")
                            break
            else:
                # Running from source
                toolbox_root = repo_root
            
            # Get path to example_data_manager.py
            example_data_manager_path = os.path.join(toolbox_root, 'new_project', 'example_data_manager.py')
            
            if not os.path.exists(example_data_manager_path):
                self.log_message(f"Example data manager not found at {example_data_manager_path}", "WARNING")
                # Try to provide helpful debug info
                self.log_message(f"Looked in toolbox root: {toolbox_root}", "INFO")
                return False
            
            # Run the example data manager
            # When frozen, sys.executable is the app bundle, so use python3
            python_executable = 'python3' if getattr(sys, 'frozen', False) else sys.executable
            
            try:
                result = run_subprocess_silent([
                    python_executable, example_data_manager_path, toolbox_root, self.project_dir
                ], timeout=120)
                
                if result.returncode == 0:
                    # Parse output to see if data was copied
                    if "Successfully set up example data" in result.stdout:
                        self.log_message("Example data (ernie & MNI152) copied to project", "SUCCESS")
                        return True
                    elif "not new" in result.stdout or "already copied" in result.stdout or "existing" in result.stdout:
                        self.log_message("Project already has data, skipping example data copy", "INFO")
                        return True
                    else:
                        self.log_message("Example data setup completed", "SUCCESS")
                        return True
                else:
                    # Non-zero exit but check stderr
                    if result.stderr.strip():
                        self.log_message(f"Example data setup warning: {result.stderr.strip()}", "WARNING")
                    return False
                    
            except subprocess.TimeoutExpired:
                self.log_message("Example data setup timed out", "WARNING")
                return False
            except Exception as e:
                self.log_message(f"Example data setup error: {str(e)}", "WARNING")
                return False
                
        except Exception as e:
            self.log_message(f"Failed to setup example data: {str(e)}", "WARNING")
            return False
    
    def _check_docker_images_exist(self):
        """Check if required Docker images exist locally"""
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                return False
            
            self.log_message("Checking for local Docker images...", "INFO")
            
            # Get list of images
            result = run_subprocess_silent([docker_executable, 'images', '--format', '{{.Repository}}:{{.Tag}}'], timeout=30)
            
            if result.returncode != 0:
                self.log_message("Failed to check Docker images", "ERROR")
                return False
            
            available_images = result.stdout.strip().split('\n')
            self.log_message(f"Found {len(available_images)} local Docker images", "INFO")
            
            # Check if simnibs image exists (the main required image)
            # Look for images containing 'simnibs' or 'ti-toolbox'
            for image in available_images:
                if 'simnibs' in image.lower() or 'ti-toolbox' in image.lower():
                    self.log_message(f"Found local image: {image}", "SUCCESS")
                    return True
            
            self.log_message(" Required Docker images not found locally", "WARNING")
            return False
            
        except Exception as e:
            self.log_message(f"Error checking Docker images: {str(e)}", "ERROR")
            return False
    
    def _ensure_docker_volumes(self):
        """Ensure all required Docker volumes exist"""
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                return False
                
            self.log_message("Checking Docker volumes...", "INFO")
            
            # Create required volumes - FSL removed for future release
            required_volumes = ['ti-toolbox_freesurfer_data']
            
            for volume in required_volumes:
                self.log_message(f"Ensuring volume exists: {volume}", "INFO")
                result = run_subprocess_silent([docker_executable, 'volume', 'create', volume], timeout=60)
                
                if result.returncode == 0:
                    self.log_message(f"Volume ready: {volume}", "SUCCESS")
                elif "already exists" in result.stderr:
                    self.log_message(f" Volume {volume} already exists", "INFO")
                else:
                    self.log_message(f" Warning creating {volume}: {result.stderr}", "WARNING")
            
            self.log_message("All volumes are ready", "SUCCESS")
            return True
                
        except Exception as e:
            self.log_message(f"Volume creation error: {str(e)}", "ERROR")
            return False

    def _check_existing_containers(self):
        """Check if any of our containers are already running and return their names"""
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                return []
            
            # Check for all our containers
            container_names = ['simnibs_container', 'freesurfer_container']
            running_containers = []
            
            result = run_subprocess_silent([
                docker_executable, 'ps', '-a', '--format', '{{.Names}}'
            ], timeout=5)
            
            if result.returncode == 0:
                existing = result.stdout.strip().split('\n')
                for container in container_names:
                    if container in existing:
                        running_containers.append(container)
            
            return running_containers
        except Exception:
            return []
    
    def _check_containers_already_running(self):
        """Quick check if containers are already running (no retry, immediate check)"""
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                return False
            
            # Quick check without retry
            result = run_subprocess_silent([
                docker_executable, 'ps', '--filter', 'name=simnibs_container', 
                '--format', '{{.Names}}\t{{.Status}}'
            ], timeout=5)
            
            if result.returncode == 0 and 'simnibs_container' in result.stdout:
                # Check if status contains "Up" (actually running)
                if 'Up' in result.stdout:
                    return True
            
            return False
        except Exception:
            return False
    
    def _verify_containers_running(self):
        """Verify that the main simnibs container is running with retry logic"""
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                self.log_user_message("Docker executable not found during verification", "ERROR")
                return False
            
            # Wait for containers to start with retry logic
            max_retries = 6  # 30 seconds total (6 * 5 seconds)
            retry_delay = 5
            
            self.log_user_message("  Waiting for containers to initialize...")
            
            for attempt in range(1, max_retries + 1):
                self.log_message(f"Verification attempt {attempt}/{max_retries}...", "INFO")
                time.sleep(retry_delay)
                
                # Check simnibs_container status
                result = run_subprocess_silent([
                    docker_executable, 'ps', '--filter', 'name=simnibs_container', 
                    '--format', '{{.Names}}\t{{.Status}}'
                ], timeout=10)
                
                if result.returncode == 0 and 'simnibs_container' in result.stdout:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if 'simnibs_container' in line:
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                status = parts[1]
                                # Check if container is actually running (not just created)
                                if 'Up' in status:
                                    self.log_message(f"simnibs_container: {status}", "SUCCESS")
                                    return True
                                else:
                                    self.log_message(f"Container status: {status} (waiting...)", "INFO")
                            else:
                                # If no status but container exists, assume it's running
                                self.log_message("simnibs_container is running", "SUCCESS")
                                return True
                
                if attempt < max_retries:
                    self.log_message(f"Container not ready yet, waiting {retry_delay} more seconds...", "INFO")
            
            # If we get here, all retries failed
            error_msg = "simnibs_container did not start within 30 seconds"
            self.log_user_message(f"  {error_msg}", "ERROR")
            self.log_message(f"Last check output: {result.stdout if result else 'No output'}", "ERROR")
            return False
                    
        except Exception as e:
            error_msg = f"Container verification error: {str(e)}"
            self.log_user_message(f"  {error_msg}", "ERROR")
            self.log_message(f"Full error: {str(e)}", "ERROR")
            return False

    def launch_cli(self):
        """Launch CLI interface"""
        if not self.containers_running:
            self.message_box.show_message("Error", "Please start Docker containers first", "warning", "")
            return
        
        if self.cli_launching:
            self.log_user_message("CLI already launching, please wait...", "WARNING")
            return
        
        self.cli_launching = True
        self.cli_button.setEnabled(False)
        
        try:
            system = platform.system()
            display_env = self.setup_display_env()
            
            if system == "Darwin":  # macOS
                docker_cmd = f'docker exec -it --workdir /ti-toolbox simnibs_container bash'
                
                # Use the most reliable approach: open Terminal with a specific command file
                # This avoids the double window issue entirely
                try:
                    # Create a temporary script file
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.command', delete=False) as f:
                        f.write(f'#!/bin/bash\ncd "{self.script_dir}"\n{docker_cmd}\n')
                        script_path = f.name
                    
                    # Make it executable
                    os.chmod(script_path, 0o755)
                    
                    # Open it with Terminal - this creates exactly one window
                    subprocess.Popen(['open', '-a', 'Terminal', script_path])
                    
                    # Clean up the temp file after a delay
                    def cleanup():
                        time.sleep(5)  # Give Terminal time to read the file
                        try:
                            os.unlink(script_path)
                        except:
                            pass
                    
                    threading.Thread(target=cleanup, daemon=True).start()
                    
                except Exception as e:
                    # Fallback to the simple AppleScript method
                    self.log_message(f"Temp file method failed, using fallback: {e}", "WARNING")
                    terminal_script = f'''
                    tell application "Terminal"
                        do script "cd '{self.script_dir}' && {docker_cmd}"
                        activate
                    end tell
                    '''
                    subprocess.Popen(['osascript', '-e', terminal_script])
                
            elif system == "Linux":
                # Try different terminal emulators
                terminals = ['gnome-terminal', 'konsole', 'xterm', 'x-terminal-emulator']
                docker_cmd = f'docker exec -it --workdir /ti-toolbox simnibs_container bash'
                
                for terminal in terminals:
                    try:
                        if terminal == 'gnome-terminal':
                            subprocess.Popen([terminal, '--', 'bash', '-c', f'cd "{self.script_dir}" && {docker_cmd}; exec bash'])
                        elif terminal == 'konsole':
                            subprocess.Popen([terminal, '-e', 'bash', '-c', f'cd "{self.script_dir}" && {docker_cmd}; exec bash'])
                        else:
                            subprocess.Popen([terminal, '-e', f'bash -c "cd \\"{self.script_dir}\\" && {docker_cmd}; exec bash"'])
                        break
                    except FileNotFoundError:
                        continue
                else:
                    raise Exception("No suitable terminal emulator found")
                    
            elif system == "Windows":
                # Use Command Prompt
                docker_cmd = f'docker exec -it --workdir /ti-toolbox simnibs_container bash'
                subprocess.Popen(f'start cmd /k "cd /d "{self.script_dir}" && {docker_cmd}"', shell=True)
            
            self.log_user_message("CLI launched successfully", "SUCCESS")
            
        except Exception as e:
            self.log_user_message(f"Failed to launch CLI: {e}", "ERROR")
            self.message_box.show_message("CLI Launch Error", f"Failed to launch CLI terminal: {e}", "error", "")
        finally:
            self.cli_launching = False
            self.cli_button.setEnabled(True)

    def launch_gui(self):
        """Launch GUI interface using hidden terminal approach"""
        if not self.containers_running:
            self.message_box.show_message("Error", "Please start Docker containers first", "warning", "")
            return
        
        try:
            system = platform.system()
            
            # Set up XQuartz on macOS first
            if system == "Darwin":
                self.log_message("Setting up XQuartz for GUI launch...", "INFO")
                if not self.setup_xquartz_macos():
                    self.message_box.show_message(
                        "XQuartz Setup Failed", 
                        "Could not properly set up XQuartz. GUI may not work correctly.\n\n" +
                        "Please ensure:\n" +
                        "1. XQuartz is installed\n" +
                        "2. XQuartz version is 2.8.0 or lower (preferably 2.7.7)\n" +
                        "3. You have proper permissions",
                        "warning", ""
                    )
                    # Continue anyway, but warn the user
            
            # Windows X11 server guidance
            elif system == "Windows":
                self.log_message("=" * 60, "INFO")
                self.log_message("Windows GUI Launch Requirement", "INFO") 
                self.log_message("=" * 60, "INFO")
                self.log_message("If GUI fails, you need VcXsrv X11 server:", "INFO")
                self.log_message("1. Download: https://sourceforge.net/projects/vcxsrv/", "INFO")
                self.log_message("2. Launch 'XLaunch' → Multiple windows → Start no client → Disable access control", "INFO")
                self.log_message("3. Keep VcXsrv running while using GUI", "INFO")
                self.log_message("=" * 60, "INFO")
            
            self.log_message("Launching GUI (hidden terminal)...", "INFO")
            
            # Get docker executable
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                self.log_message("Docker executable not found", "ERROR")
                return
            
            # Set up environment - same as CLI but run GUI command
            env = os.environ.copy()
            env["LOCAL_PROJECT_DIR"] = self.project_dir
            env["PROJECT_DIR_NAME"] = os.path.basename(self.project_dir)
            env["DISPLAY"] = self.setup_display_env()
            
            # The docker command - same as CLI but runs GUI script
            docker_cmd = [
                docker_executable, 'exec', '-it',
                'simnibs_container', 'bash', '-lc', '/ti-toolbox/CLI/GUI.sh'
            ]
            
            if system == "Darwin":  # macOS
                # Create invisible Terminal window with proper TTY for docker exec -it
                docker_cmd_str = ' '.join(docker_cmd)
                
                # AppleScript that creates a Terminal window but keeps it completely hidden
                applescript_cmd = f'''
                tell application "Terminal"
                    -- Create new window without bringing Terminal to front
                    set newWindow to do script "cd '{self.script_dir}' && {docker_cmd_str}"
                    
                    -- Make window invisible immediately
                    set visible of newWindow to false
                    
                    -- Optional: close the terminal after command completes
                    delay 2
                    do script "exit" in newWindow
                end tell
                '''
                
                # Run AppleScript in background
                subprocess.Popen(['osascript', '-e', applescript_cmd],
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
                
            elif system == "Linux":
                # Run docker command directly in background with nohup to detach from terminal
                subprocess.Popen(['nohup'] + docker_cmd, 
                               cwd=self.script_dir, env=env,
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL,
                               stdin=subprocess.DEVNULL)
                    
            elif system == "Windows":
                # Keep Windows behavior - use hidden terminal window
                docker_cmd_str = ' '.join(docker_cmd)
                cmd_line = f'cmd /c "cd /d "{self.script_dir}" && {docker_cmd_str}"'
                
                # Use hidden window creation
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                subprocess.Popen(cmd_line, shell=True, 
                               startupinfo=startupinfo, 
                               creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.log_user_message("GUI launched successfully", "SUCCESS")
            self.log_message("GUI application should appear shortly", "INFO")
            
        except Exception as e:
            self.log_user_message(f"Failed to launch GUI: {e}", "ERROR")
            self.message_box.show_message("GUI Launch Error", f"Failed to launch GUI: {e}", "error", "")

    def stop_docker(self):
        """Stop Docker containers"""
        self.docker_toggle.setEnabled(False)
        self.log_user_message("Stopping Docker containers...")
        self.log_message("Stopping Docker containers...", "INFO")
        
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                self.log_user_message("Docker executable not found for stop operation", "ERROR")
                return
            
            # Set up environment
            env = os.environ.copy()
            
            # Normalize Windows paths for Docker volume mounting
            if platform.system() == "Windows":
                normalized_path = self.project_dir.replace('\\', '/')
                if ' ' in normalized_path and not (normalized_path.startswith('"') and normalized_path.endswith('"')):
                    normalized_path = f'"{normalized_path}"'
                env["LOCAL_PROJECT_DIR"] = normalized_path
            else:
                env["LOCAL_PROJECT_DIR"] = self.project_dir
                
            env["PROJECT_DIR_NAME"] = os.path.basename(self.project_dir)
            
            # Stop containers
            result = run_subprocess_silent([
                docker_executable, 'compose', '-f', self.docker_compose_file, 'down'
            ], env=env, cwd=self.script_dir, timeout=120)
            
            if result.returncode == 0:
                self.containers_running = False
                self.update_status_display()
                self.log_user_message("Docker containers stopped successfully", "SUCCESS")
            else:
                self.log_message(" Some containers may still be running", "WARNING")
                if result.stderr.strip():
                    self.log_message(f"Stop error: {result.stderr.strip()}", "WARNING")
                # Update status anyway
                self.containers_running = False
                self.update_status_display()
                
        except subprocess.TimeoutExpired:
            self.log_user_message("Stop operation timed out", "ERROR")
            self.containers_running = False
            self.update_status_display()
        except Exception as e:
            self.log_user_message(f"Error stopping containers: {str(e)}", "ERROR")
            self.containers_running = False
            self.update_status_display()
        finally:
            self.docker_toggle.setEnabled(True)

    def closeEvent(self, event):
        """Handle window close"""
        # Stop any running worker threads
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait(3000)  # Wait up to 3 seconds
        
        if self.containers_running:
            reply = QMessageBox.question(self, 'Confirm Exit',
                                       "Docker containers are running. Stop them before exiting?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_docker()
        
        # Ensure cursor is restored
        QApplication.restoreOverrideCursor()
        event.accept()

    def setup_xquartz_macos(self):
        """Set up XQuartz for macOS GUI applications"""
        try:
            # Check if XQuartz is installed
            xquartz_app = "/Applications/Utilities/XQuartz.app"
            if not os.path.exists(xquartz_app):
                self.log_message("XQuartz not found. Please install XQuartz to use GUI applications.", "WARNING")
                return False
            
            # Check XQuartz version
            try:
                result = subprocess.run(['mdls', '-name', 'kMDItemVersion', xquartz_app], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    version_line = result.stdout.strip()
                    # Extract version from output like: kMDItemVersion = "2.7.11"
                    if '"' in version_line:
                        version = version_line.split('"')[1]
                        self.log_message(f"XQuartz version detected: {version}", "INFO")
                        
                        # Warn about versions > 2.8.0
                        try:
                            version_parts = version.split('.')
                            if len(version_parts) >= 2:
                                major, minor = int(version_parts[0]), int(version_parts[1])
                                if major > 2 or (major == 2 and minor > 8):
                                    self.log_message("Warning: XQuartz version > 2.8.0 may have compatibility issues", "WARNING")
                        except:
                            pass
            except:
                self.log_message("Could not check XQuartz version", "WARNING")
            
            # Enable network clients in XQuartz
            self.log_message("Configuring XQuartz for network clients...", "INFO")
            try:
                subprocess.run(['defaults', 'write', 'org.macosforge.xquartz.X11', 'nolisten_tcp', '-bool', 'false'], 
                             timeout=5)
            except:
                self.log_message("Could not configure XQuartz network settings", "WARNING")
            
            # Check if XQuartz is running
            try:
                result = subprocess.run(['pgrep', '-f', 'XQuartz'], capture_output=True, timeout=5)
                xquartz_running = result.returncode == 0
            except:
                xquartz_running = False
            
            if not xquartz_running:
                self.log_message("Starting XQuartz...", "INFO")
                try:
                    subprocess.Popen(['open', '-a', 'XQuartz'])
                    # Give XQuartz time to start
                    time.sleep(5)  # Increased wait time
                except:
                    self.log_message("Could not start XQuartz", "ERROR")
                    return False
                
                # Wait a bit more for XQuartz to fully initialize
                self.log_message("Waiting for XQuartz to initialize...", "INFO")
                time.sleep(3)
            
            # Find xhost executable more robustly
            def find_xhost():
                """Find xhost executable in common locations"""
                common_paths = [
                    '/usr/X11/bin/xhost',
                    '/opt/X11/bin/xhost', 
                    '/usr/local/bin/xhost',
                    '/opt/homebrew/bin/xhost',
                    '/usr/bin/xhost'
                ]
                
                # First try shutil.which
                xhost_path = shutil.which('xhost')
                if xhost_path and os.path.exists(xhost_path):
                    return xhost_path
                
                # Then try common paths
                for path in common_paths:
                    if os.path.exists(path) and os.access(path, os.X_OK):
                        return path
                
                return None
            
            # Set up X11 permissions with robust xhost finding
            self.log_message("Setting up X11 permissions...", "INFO")
            
            # Set DISPLAY environment variable first
            os.environ['DISPLAY'] = ':0'
            
            # Find xhost executable
            xhost_executable = find_xhost()
            
            if xhost_executable:
                self.log_message(f"Found xhost at: {xhost_executable}", "INFO")
                try:
                    # Allow connections from localhost
                    result = subprocess.run([xhost_executable, '+localhost'], 
                                          capture_output=True, text=True, timeout=10,
                                          env=dict(os.environ, DISPLAY=':0'))
                    if result.returncode != 0:
                        self.log_message(f"xhost +localhost failed: {result.stderr}", "WARNING")
                    else:
                        self.log_message("X11 permissions set for localhost", "SUCCESS")
                    
                    # Allow connections from hostname
                    try:
                        hostname_result = subprocess.run(['hostname'], capture_output=True, text=True, timeout=5)
                        if hostname_result.returncode == 0:
                            hostname = hostname_result.stdout.strip()
                            result = subprocess.run([xhost_executable, f'+{hostname}'], 
                                                  capture_output=True, text=True, timeout=10,
                                                  env=dict(os.environ, DISPLAY=':0'))
                            if result.returncode != 0:
                                self.log_message(f"xhost +{hostname} failed: {result.stderr}", "WARNING")
                            else:
                                self.log_message(f"X11 permissions set for {hostname}", "SUCCESS")
                    except Exception as e:
                        self.log_message(f"Could not set hostname xhost permission: {e}", "WARNING")
                    
                    # Also allow Docker's internal IP access
                    try:
                        # Add common Docker internal IPs
                        docker_ips = ['172.17.0.1', '192.168.65.2', '172.16.0.1']
                        for ip in docker_ips:
                            subprocess.run([xhost_executable, f'+{ip}'], 
                                         capture_output=True, text=True, timeout=5,
                                         env=dict(os.environ, DISPLAY=':0'))
                    except:
                        pass  # These are optional
                    
                except Exception as e:
                    self.log_message(f"Warning: Could not set X11 permissions: {e}", "WARNING")
            else:
                self.log_message("xhost not found - X11 permissions may not be set properly", "WARNING")
                self.log_message("GUI may still work if XQuartz is already configured", "INFO")
            
            # Verify X11 is accessible (optional, don't fail if this doesn't work)
            if xhost_executable:
                try:
                    # Try to find xset as well
                    xset_executable = shutil.which('xset') or '/usr/X11/bin/xset' or '/opt/X11/bin/xset'
                    if xset_executable and os.path.exists(xset_executable):
                        result = subprocess.run([xset_executable, 'q'], 
                                              capture_output=True, text=True, timeout=5,
                                              env=dict(os.environ, DISPLAY=':0'))
                        if result.returncode == 0:
                            self.log_message("X11 server is accessible", "SUCCESS")
                        else:
                            self.log_message("X11 server test failed, but continuing", "WARNING")
                    else:
                        self.log_message("xset not found, skipping X11 server test", "INFO")
                except:
                    self.log_message("Could not test X11 server access, but continuing", "INFO")
            
            self.log_message("XQuartz setup completed", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_message(f"XQuartz setup failed: {e}", "ERROR")
            return False


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("Temporal Interference Toolbox")
    app.setApplicationDisplayName("Temporal Interference Toolbox")
    
    # Set application icon if available
    icon_path = os.path.join(os.path.dirname(__file__), "icon.icns")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = TIToolboxLoaderApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main() 
