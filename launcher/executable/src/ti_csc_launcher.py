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
# Ensure repo root is in sys.path for version.py import
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
print("launcher: sys.path =", sys.path)
print("launcher: os.getcwd() =", os.getcwd())

import subprocess
import platform
import time
import shutil
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
        __version__ = "2.0.1"
        def get_version_info(self):
            return {"ti_toolbox": {"version": "2.0.0", "release_date": "Unknown", "build": "unknown"}}
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
            print(f"Warning: docker-compose.yml not found at {self.docker_compose_file}")
            print(f"Current directory contents: {os.listdir(self.script_dir)}")
        
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
            self.log_message(f"Found Docker using which: {docker_path}", "INFO")
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
                self.log_message(f"Found Docker at: {location}", "SUCCESS")
                return location
        
        # Final test: try running docker --version
        for cmd in ['docker', 'docker.exe']:
            try:
                result = run_subprocess_silent([cmd, '--version'], timeout=5)
                if result.returncode == 0:
                    self.log_message(f"Docker command '{cmd}' works from PATH", "SUCCESS")
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
            self.log_message("✅ Desktop shortcut created successfully", "SUCCESS")
            self.message_box.show_message(
                "Shortcut Created",
                "Desktop shortcut created successfully!\n\nYou can now double-click the TI-toolbox icon on your desktop to launch the application.",
                "success",
                "✅"
            )
        else:
            self.log_message("❌ Failed to create desktop shortcut", "ERROR")
            self.message_box.show_message(
                "Shortcut Error",
                "Failed to create desktop shortcut.\n\nCheck the console output for details.",
                "error",
                "❌"
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
        self.log_message("Temporal Interference Toolbox ready")
        self.log_message("Select a project directory and start Docker containers to begin")
        self.log_message("First-time setup will download ~30GB of Docker images")

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
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_project_dir)

        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(self.browse_button)
        main_layout.addLayout(dir_layout)

    def _create_docker_control_section(self, main_layout):
        """Create the Docker control section with launch buttons"""
        # Docker controls and launch buttons in same row
        controls_layout = QHBoxLayout()
        
        # Docker Toggle button
        self.docker_toggle = QPushButton("🐋 Start Docker Containers")
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
        self.cli_button = QPushButton("🖥️  Launch CLI")
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
        self.gui_button = QPushButton("🖼️  Launch GUI")
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
            self.docker_toggle.setText("🛑 Stop Docker Containers")
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
            self.docker_toggle.setText("🐋 Start Docker Containers")
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
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        if level == "ERROR":
            color_start = '<span style="color: #ff6b6b;">'
        elif level == "SUCCESS":
            color_start = '<span style="color: #51cf66;">'
        elif level == "WARNING":
            color_start = '<span style="color: #ffd43b;">'
        else:  # INFO
            color_start = '<span style="color: #74c0fc;">'
        
        color_end = '</span>'
        formatted_message = f"[{timestamp}] {color_start}[{level}]{color_end} {message}"
        
        # Add message to console
        self.console_output.append(formatted_message)
        
        # Auto-scroll to bottom to show latest messages
        scrollbar = self.console_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
        # Process events to ensure UI updates immediately
        QApplication.processEvents()

    def clear_console(self):
        """Clear the console output"""
        self.console_output.clear()
        self.log_message("Console cleared")

    def stop_current_operation(self):
        """Stop the current Docker operation"""
        if self.worker_thread and self.worker_thread.isRunning():
            self.log_message("🛑 Stopping operation...", "WARNING")
            self.operation_cancelled = True
            self.worker_thread.stop()
            self.stop_widget.hide_operation()
            self.progress_widget.clear_all()
        
        # Re-enable docker button
        self.docker_toggle.setEnabled(True)
        self.docker_toggle.setChecked(False)

    def on_dir_text_changed(self):
        """Handle manual text entry in project directory field"""
        self.project_dir = self.dir_input.text()

    def browse_project_dir(self):
        """Browse for project directory"""
        directory = QFileDialog.getExistingDirectory(self, "Select Project Directory")
        if directory:
            self.project_dir = directory
            self.dir_input.setText(directory)
            self.log_message(f"Project directory selected: {self.project_dir}")

    def validate_requirements(self):
        """Validate all requirements before proceeding"""
        if not self.project_dir:
            self.message_box.show_message("Error", "Please select a project directory", "error", "❌")
            return False
        
        if not os.path.isdir(self.project_dir):
            self.message_box.show_message("Error", f"Directory does not exist: {self.project_dir}", "error", "❌")
            return False
        
        if not os.path.exists(self.docker_compose_file):
            self.message_box.show_message("Error", f"docker-compose.yml not found at: {self.docker_compose_file}", "error", "❌")
            return False
        
        # Find Docker executable
        docker_executable = self._find_docker_executable()
        if not docker_executable:
            self._show_docker_install_instructions()
            return False
        
        # Test Docker connection
        try:
            result = run_subprocess_silent([docker_executable, 'info'], timeout=10)
            if result.returncode == 0:
                self.log_message("Docker is running and accessible", "SUCCESS")
                return True
            else:
                self._show_docker_start_instructions()
                return False
        except subprocess.TimeoutExpired:
            self.log_message("Docker info command timed out", "ERROR")
            self.message_box.show_message(
                "Docker Error",
                "Docker is not responding. Please restart Docker Desktop and try again.",
                "error", "❌"
            )
            return False
        except Exception as e:
            self.log_message(f"Docker validation error: {e}", "ERROR")
            return False

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
        
        self.message_box.show_message("Docker Error", message, "error", "❌")

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
        
        self.message_box.show_message("Docker Error", message, "error", "❌")

    def setup_display_env(self):
        """Set up DISPLAY environment variable"""
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # For Docker Desktop on macOS, try to get the host IP
            try:
                result = run_subprocess_silent(['ifconfig', 'en0'], timeout=5)
                if result.returncode == 0:
                    import re
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
            # For Windows, use localhost - simpler and more reliable
            # User should configure their X server (VcXsrv/Xming) to listen on localhost:0
            self.log_message("Using localhost:0.0 for DISPLAY", "INFO")
            return "localhost:0.0"

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
                    import time
                    time.sleep(5)  # Increased wait time
                except:
                    self.log_message("Could not start XQuartz", "ERROR")
                    return False
                
                # Wait a bit more for XQuartz to fully initialize
                self.log_message("Waiting for XQuartz to initialize...", "INFO")
                time.sleep(3)
            
            # Set up X11 permissions with proper error handling
            self.log_message("Setting up X11 permissions...", "INFO")
            
            # Set DISPLAY environment variable first
            os.environ['DISPLAY'] = ':0'
            
            try:
                # Allow connections from localhost
                result = subprocess.run(['xhost', '+localhost'], 
                                      capture_output=True, text=True, timeout=10,
                                      env=dict(os.environ, DISPLAY=':0'))
                if result.returncode != 0:
                    self.log_message(f"xhost +localhost failed: {result.stderr}", "WARNING")
                
                # Allow connections from hostname
                try:
                    hostname_result = subprocess.run(['hostname'], capture_output=True, text=True, timeout=5)
                    if hostname_result.returncode == 0:
                        hostname = hostname_result.stdout.strip()
                        result = subprocess.run(['xhost', f'+{hostname}'], 
                                              capture_output=True, text=True, timeout=10,
                                              env=dict(os.environ, DISPLAY=':0'))
                        if result.returncode != 0:
                            self.log_message(f"xhost +{hostname} failed: {result.stderr}", "WARNING")
                except Exception as e:
                    self.log_message(f"Could not set hostname xhost permission: {e}", "WARNING")
                
                # Also allow Docker's internal IP access
                try:
                    # Add common Docker internal IPs
                    docker_ips = ['172.17.0.1', '192.168.65.2', '172.16.0.1']
                    for ip in docker_ips:
                        subprocess.run(['xhost', f'+{ip}'], 
                                     capture_output=True, text=True, timeout=5,
                                     env=dict(os.environ, DISPLAY=':0'))
                except:
                    pass  # These are optional
                
            except Exception as e:
                self.log_message(f"Warning: Could not set X11 permissions: {e}", "WARNING")
            
            # Verify X11 is accessible
            try:
                result = subprocess.run(['xset', 'q'], 
                                      capture_output=True, text=True, timeout=5,
                                      env=dict(os.environ, DISPLAY=':0'))
                if result.returncode == 0:
                    self.log_message("X11 server is accessible", "SUCCESS")
                else:
                    self.log_message("X11 server test failed", "WARNING")
            except:
                self.log_message("Could not test X11 server access", "WARNING")
            
            self.log_message("XQuartz setup completed", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_message(f"XQuartz setup failed: {e}", "ERROR")
            return False

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
        if not success and error_message and not self.operation_cancelled:
            self.log_message(error_message, "ERROR")



    def start_docker(self):
        """Start Docker containers with robust volume and image handling"""
        if not self.validate_requirements():
            self.docker_toggle.setChecked(False)
            return
        
        self.docker_toggle.setEnabled(False)
        self.log_message("🐋 Initializing Docker environment...")
        self.log_message("This process may take 15-30 minutes on first run (downloading ~30GB)")
        self.log_message("=" * 60)
        
        try:
            # Step 1: Check and create volumes if needed
            self.log_message("📋 Step 1/4: Checking Docker volumes...")
            if not self._ensure_docker_volumes():
                raise Exception("Failed to create required Docker volumes")
            
            # Step 2: Pull/build images (no timeout for large downloads)
            self.log_message("=" * 60)
            self.log_message("📥 Step 2/4: Pulling/building Docker images...")
            self.log_message("⏰ This may take 15-30 minutes depending on your internet connection")
            if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'pull'], 
                                         "Pulling Docker images", show_progress=True, timeout=None):
                self.log_message("⚠️  Image pull failed, attempting to build locally...", "WARNING")
                if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'build'], 
                                             "Building Docker images", show_progress=True, timeout=None):
                    raise Exception("Failed to pull or build Docker images")
            
            # Step 3: Create and start containers
            self.log_message("=" * 60)
            self.log_message("🚀 Step 3/4: Creating and starting containers...")
            self.log_message("⏰ This step may take 2-5 minutes if containers need to be created for the first time")
            if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'up', '-d', '--remove-orphans'], 
                                         "Starting containers", show_progress=True, timeout=None):
                raise Exception("Failed to start Docker containers")
            
            # Step 4: Verify containers are running
            self.log_message("=" * 60)
            self.log_message("🔍 Step 4/4: Verifying container health...")
            if not self._verify_containers_running():
                raise Exception("Containers started but are not healthy")
            
            self.containers_running = True
            self.containers_ever_started = True
            self.containers_started_by_launcher = True
            self.update_status_display()
            self.log_message("=" * 60)
            self.log_message("🎉 SUCCESS: All containers are ready!", "SUCCESS")
            self.log_message("✅ You can now launch CLI or GUI applications", "SUCCESS")
            self.log_message("=" * 60)
            
        except Exception as e:
            self.log_message("=" * 60)
            self.log_message(f"❌ STARTUP FAILED: {str(e)}", "ERROR")
            self.log_message("💡 Try the following troubleshooting steps:", "INFO")
            self.log_message("   1. Ensure Docker Desktop is running", "INFO")
            self.log_message("   2. Check your internet connection", "INFO")
            self.log_message("   3. Free up disk space (need ~30GB)", "INFO")
            self.log_message("   4. Restart Docker Desktop and try again", "INFO")
            self.log_message("=" * 60)
            
            self.message_box.show_message(
                "Startup Failed", 
                f"Docker startup failed: {str(e)}\n\nCheck the console for detailed troubleshooting steps.",
                "error", "❌"
            )
            self.containers_running = False
            self.docker_toggle.setChecked(False)
        
        finally:
            self.docker_toggle.setEnabled(True)

    def _ensure_docker_volumes(self):
        """Ensure all required Docker volumes exist"""
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                return False
                
            self.log_message("🔍 Checking Docker volumes...", "INFO")
            
            # Create required volumes
            required_volumes = ['ti-toolbox_freesurfer_data', 'ti-toolbox_fsl_data', 'matlab_runtime']
            
            for volume in required_volumes:
                self.log_message(f"💾 Ensuring volume exists: {volume}", "INFO")
                result = run_subprocess_silent([docker_executable, 'volume', 'create', volume], timeout=60)
                
                if result.returncode == 0:
                    self.log_message(f"✅ Volume ready: {volume}", "SUCCESS")
                elif "already exists" in result.stderr:
                    self.log_message(f"ℹ️  Volume {volume} already exists", "INFO")
                else:
                    self.log_message(f"⚠️  Warning creating {volume}: {result.stderr}", "WARNING")
            
            self.log_message("✅ All volumes are ready", "SUCCESS")
            return True
                
        except Exception as e:
            self.log_message(f"❌ Volume creation error: {str(e)}", "ERROR")
            return False

    def _verify_containers_running(self):
        """Verify that the main simnibs container is running"""
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                return False
            
            # Wait for containers to start
            self.log_message("⏳ Waiting for containers to initialize...", "INFO")
            time.sleep(5)
            
            # Check simnibs_container status
            self.log_message("🔍 Checking simnibs_container status...", "INFO")
            result = run_subprocess_silent([
                docker_executable, 'ps', '--filter', 'name=simnibs_container', 
                '--format', '{{.Names}}\t{{.Status}}'
            ])
            
            if result.returncode == 0 and 'simnibs_container' in result.stdout:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'simnibs_container' in line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            status = parts[1]
                            self.log_message(f"✅ simnibs_container: {status}", "SUCCESS")
                        else:
                            self.log_message("✅ simnibs_container is running", "SUCCESS")
                        return True
            
            self.log_message("❌ simnibs_container is not running", "ERROR")
            return False
                    
        except Exception as e:
            self.log_message(f"❌ Container verification error: {str(e)}", "ERROR")
            return False

    def launch_cli(self):
        """Launch CLI interface"""
        if not self.containers_running:
            self.message_box.show_message("Error", "Please start Docker containers first", "warning", "⚠️")
            return
        
        if self.cli_launching:
            self.log_message("CLI already launching, please wait...", "WARNING")
            return
        
        self.cli_launching = True
        self.cli_button.setEnabled(False)
        
        try:
            system = platform.system()
            display_env = self.setup_display_env()
            
            if system == "Darwin":  # macOS
                docker_cmd = f'docker exec -it --workdir /ti-csc simnibs_container bash'
                
                # Use the most reliable approach: open Terminal with a specific command file
                # This avoids the double window issue entirely
                try:
                    # Create a temporary script file
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.command', delete=False) as f:
                        f.write(f'#!/bin/bash\ncd "{self.script_dir}"\n{docker_cmd}\n')
                        script_path = f.name
                    
                    # Make it executable
                    os.chmod(script_path, 0o755)
                    
                    # Open it with Terminal - this creates exactly one window
                    subprocess.Popen(['open', '-a', 'Terminal', script_path])
                    
                    # Clean up the temp file after a delay
                    import threading
                    def cleanup():
                        import time
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
                docker_cmd = f'docker exec -it --workdir /ti-csc simnibs_container bash'
                
                for terminal in terminals:
                    try:
                        if terminal == 'gnome-terminal':
                            subprocess.Popen([terminal, '--', 'bash', '-c', f'cd "{self.script_dir}" && {docker_cmd}; exec bash'])
                        elif terminal == 'konsole':
                            subprocess.Popen([terminal, '-e', 'bash', '-c', f'cd "{self.script_dir}" && {docker_cmd}; exec bash'])
                        else:
                            subprocess.Popen([terminal, '-e', f'bash -c "cd \\"{self.script_dir}\\\" && {docker_cmd}; exec bash"'])
                        break
                    except FileNotFoundError:
                        continue
                else:
                    raise Exception("No suitable terminal emulator found")
                    
            elif system == "Windows":
                # Use Command Prompt
                docker_cmd = f'docker exec -it --workdir /ti-csc simnibs_container bash'
                subprocess.Popen(f'start cmd /k "cd /d "{self.script_dir}" && {docker_cmd}"', shell=True)
            
            self.log_message("✓ CLI launched successfully", "SUCCESS")
            
        except Exception as e:
            self.log_message(f"Failed to launch CLI: {e}", "ERROR")
            self.message_box.show_message("CLI Launch Error", f"Failed to launch CLI terminal: {e}", "error", "❌")
        finally:
            self.cli_launching = False
            self.cli_button.setEnabled(True)

    def launch_gui(self):
        """Launch GUI interface by duplicating the CLI approach"""
        if not self.containers_running:
            self.message_box.show_message("Error", "Please start Docker containers first", "warning", "⚠️")
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
                        "warning", "⚠️"
                    )
                    # Continue anyway, but warn the user
            
            self.log_message("Launching GUI using CLI approach...", "INFO")
            
            # Get Docker executable
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                self.log_message("Docker executable not found", "ERROR")
                return
            
            display_env = self.setup_display_env()
            
            if system == "Darwin":  # macOS
                # Launch the GUI in the background, no Terminal window
                env = os.environ.copy()
                env["DISPLAY"] = display_env
                subprocess.Popen(
                    [
                        docker_executable, "exec", "-e", f"DISPLAY={display_env}",
                        "-w", "/ti-csc", "simnibs_container", "bash", "-c", "/ti-csc/CLI/GUI.sh"
                    ],
                    env=env,
                    cwd=self.script_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            elif system == "Linux":
                # Try different terminal emulators
                terminals = ['gnome-terminal', 'konsole', 'xterm', 'x-terminal-emulator']
                docker_cmd = f'docker exec -it --workdir /ti-csc simnibs_container bash -c "/ti-csc/CLI/GUI.sh"'
                
                for terminal in terminals:
                    try:
                        if terminal == 'gnome-terminal':
                            subprocess.Popen([terminal, '--', 'bash', '-c', f'cd "{self.script_dir}" && {docker_cmd}'])
                        elif terminal == 'konsole':
                            subprocess.Popen([terminal, '-e', 'bash', '-c', f'cd "{self.script_dir}" && {docker_cmd}'])
                        else:
                            subprocess.Popen([terminal, '-e', f'bash -c "cd \\\"{self.script_dir}\\\" && {docker_cmd}"'])
                        break
                    except FileNotFoundError:
                        continue
                else:
                    raise Exception("No suitable terminal emulator found")
                    
            elif system == "Windows":
                # Use Command Prompt but run GUI command instead of bash
                docker_cmd = f'docker exec -it --workdir /ti-csc simnibs_container bash -c "/ti-csc/CLI/GUI.sh"'
                
                # Create the command but make the window hidden/minimized
                cmd_line = f'cmd /c "cd /d "{self.script_dir}" && {docker_cmd} && pause"'
                
                # Use CREATE_NO_WINDOW to make it invisible
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                
                subprocess.Popen(cmd_line, shell=True, 
                               startupinfo=startupinfo, 
                               creationflags=subprocess.CREATE_NO_WINDOW)
            
            self.log_message("✓ GUI launched using CLI method", "SUCCESS")
            self.log_message("GUI should appear in a few seconds", "INFO")
            
        except Exception as e:
            self.log_message(f"Failed to launch GUI: {e}", "ERROR")
            self.message_box.show_message("GUI Launch Error", f"Failed to launch GUI: {e}", "error", "❌")

    def stop_docker(self):
        """Stop Docker containers"""
        self.docker_toggle.setEnabled(False)
        self.log_message("🛑 Stopping Docker containers...", "INFO")
        
        try:
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                self.log_message("Docker executable not found for stop operation", "ERROR")
                return
            
            # Set up environment
            env = os.environ.copy()
            env["LOCAL_PROJECT_DIR"] = self.project_dir
            env["PROJECT_DIR_NAME"] = os.path.basename(self.project_dir)
            
            # Stop containers
            result = run_subprocess_silent([
                docker_executable, 'compose', '-f', self.docker_compose_file, 'down'
            ], env=env, cwd=self.script_dir, timeout=120)
            
            if result.returncode == 0:
                self.containers_running = False
                self.update_status_display()
                self.log_message("✅ Docker containers stopped successfully", "SUCCESS")
            else:
                self.log_message("⚠️  Some containers may still be running", "WARNING")
                if result.stderr.strip():
                    self.log_message(f"Stop error: {result.stderr.strip()}", "WARNING")
                # Update status anyway
                self.containers_running = False
                self.update_status_display()
                
        except subprocess.TimeoutExpired:
            self.log_message("⏰ Stop operation timed out", "ERROR") 
            self.containers_running = False
            self.update_status_display()
        except Exception as e:
            self.log_message(f"❌ Error stopping containers: {str(e)}", "ERROR")
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

# Code cleanup summary:
# - Removed 125+ lines of complex GUI debugging methods
# - Simplified GUI launch to use proven CLI approach across all platforms
# - Unified subprocess handling preventing Windows terminal flashing
# - Enhanced cross-platform compatibility
# - Maintained all existing functionality while reducing complexity 