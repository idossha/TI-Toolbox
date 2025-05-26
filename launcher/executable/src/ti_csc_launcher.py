"""
TI-CSC Docker Launcher - Refactored Version
A clean, modular launcher for the TI-CSC Docker environment.
"""

import sys
import os
import subprocess
import platform
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QMessageBox, QFrame, 
    QCheckBox
)
from PyQt6.QtCore import Qt, QProcess, QProcessEnvironment
from PyQt6.QtGui import QFont, QIcon, QPixmap

# Import our dialog classes
from dialogs import (
    SystemRequirementsDialog, ProjectHelpDialog, VersionInfoDialog, StyledMessageBox
)
from shortcuts_manager import ShortcutsManager

# Add parent directory to path to import version module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    import version
except ImportError:
    # Fallback if version module not found
    class MockVersion:
        __version__ = "2.0.0"
        def get_version_info(self):
            return {"ti_csc": {"version": "2.0.0", "release_date": "Unknown", "build": "unknown"}}
    version = MockVersion()


class TICSCLoaderApp(QWidget):
    """Main TI-CSC Docker Launcher Application"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TI-CSC Docker Loader")
        self.setGeometry(100, 100, 800, 650)

        # Initialize state variables
        self.project_dir = ""
        self.containers_running = False
        self.background_process = None
        self.cli_launching = False
        
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
        docker_paths = [
            '/usr/local/bin',
            '/opt/homebrew/bin',
            '/Applications/Docker.app/Contents/Resources/bin',
            '/usr/bin',
            '/bin'
        ]
        
        current_path = os.environ.get('PATH', '')
        path_parts = current_path.split(':') if current_path else []
        
        for docker_path in docker_paths:
            if docker_path not in path_parts and os.path.exists(docker_path):
                path_parts.insert(0, docker_path)
        
        os.environ['PATH'] = ':'.join(path_parts)

    def _find_docker_executable(self):
        """Find the Docker executable in common locations"""
        docker_locations = [
            '/usr/local/bin/docker',
            '/opt/homebrew/bin/docker',
            '/Applications/Docker.app/Contents/Resources/bin/docker',
            '/usr/bin/docker',
            '/bin/docker'
        ]
        
        # Try the standard 'docker' command first
        try:
            result = subprocess.run(['which', 'docker'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                docker_path = result.stdout.strip()
                if os.path.exists(docker_path):
                    return docker_path
        except Exception:
            pass
        
        # Fallback: check common locations directly
        for location in docker_locations:
            if os.path.exists(location) and os.access(location, os.X_OK):
                return location
        
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
                "Desktop shortcut created successfully!\n\nYou can now double-click the TI-CSC icon on your desktop to launch the application.",
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

        self.setLayout(main_layout)
        
        # Initial message
        self.log_message("TI-CSC Docker Launcher ready")
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
        
        title_label = QLabel("TI-CSC (Temporal Interference - Computational Stimulation Core)")
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
        self.status_label = QLabel("Docker Status: Stopped")
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

    def _create_button_section(self, main_layout):
        """Create the requirements and utility buttons section - removed since buttons moved to header"""
        pass

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
            self.status_label.setText("Docker Status: Stopped")
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
        """Add message to console output"""
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
        
        self.console_output.append(formatted_message)
        QApplication.processEvents()

    def clear_console(self):
        """Clear the console output"""
        self.console_output.clear()
        self.log_message("Console cleared")

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
        
        # Enhanced Docker detection
        docker_executable = self._find_docker_executable()
        if not docker_executable:
            self.log_message("Docker executable not found in common locations", "ERROR")
            self.message_box.show_message(
                "Docker Error", 
                "Docker executable not found. Please ensure Docker Desktop is installed.\n\n" +
                "Expected locations:\n" +
                "• /usr/local/bin/docker\n" +
                "• /opt/homebrew/bin/docker\n" +
                "• /Applications/Docker.app/Contents/Resources/bin/docker",
                "error", "❌"
            )
            return False
        
        self.log_message(f"Found Docker at: {docker_executable}", "SUCCESS")
        
        # Check if Docker is running
        try:
            result = subprocess.run([docker_executable, 'info'], 
                                  capture_output=True, check=True, timeout=10)
            self.log_message("Docker is running and accessible", "SUCCESS")
            return True
        except subprocess.CalledProcessError as e:
            self.log_message(f"Docker command failed: {e}", "ERROR")
            self.message_box.show_message(
                "Docker Error",
                "Docker is installed but not running or not accessible.\n\n" +
                "Please:\n" +
                "1. Start Docker Desktop\n" +
                "2. Wait for it to fully start (whale icon in menu bar)\n" +
                "3. Try again",
                "error", "❌"
            )
            return False
        except subprocess.TimeoutExpired:
            self.log_message("Docker info command timed out", "ERROR")
            self.message_box.show_message(
                "Docker Error",
                "Docker is not responding. Please restart Docker Desktop and try again.",
                "error", "❌"
            )
            return False
        except FileNotFoundError:
            self.log_message("Docker executable not found in PATH", "ERROR")
            self.message_box.show_message(
                "Docker Error",
                "Docker executable not found. Please ensure Docker Desktop is installed and running.",
                "error", "❌"
            )
            return False

    def setup_display_env(self):
        """Set up DISPLAY environment variable"""
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # For Docker Desktop on macOS, we need the host IP
            try:
                # Get the host IP that Docker can reach
                result = subprocess.run(
                    ['ifconfig', 'en0'],
                    capture_output=True, text=True, timeout=5
                )
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
            return "host.docker.internal:0.0"

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

    def test_x11_connection(self, display_env):
        """Test X11 connection from Docker container"""
        try:
            docker_executable = self._find_docker_executable()
            
            # Test if we can connect to X11 from container
            test_cmd = [
                docker_executable, 'exec', '-e', f'DISPLAY={display_env}',
                'simnibs_container', 'xset', 'q'
            ]
            
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                self.log_message("✓ X11 connection test successful", "SUCCESS")
                return True
            else:
                self.log_message(f"✗ X11 connection test failed: {result.stderr}", "ERROR")
                return False
                
        except subprocess.TimeoutExpired:
            self.log_message("✗ X11 connection test timed out", "ERROR")
            return False
        except Exception as e:
            self.log_message(f"✗ X11 connection test error: {e}", "ERROR")
            return False

    def run_docker_command(self, cmd, description, show_progress=True):
        """Run a Docker command and log output"""
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
            
            result = subprocess.run(cmd, cwd=self.script_dir, env=env, 
                                  capture_output=True, text=True, timeout=120)
            
            # Filter and log command output for cleaner display
            if result.stdout.strip():
                self._log_filtered_output(result.stdout, show_progress)
            
            if result.stderr.strip():
                self._log_filtered_output(result.stderr, show_progress)
            
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

    def _log_filtered_output(self, output, show_progress=True):
        """Filter Docker output to show only important messages"""
        lines = output.strip().split('\n')
        
        # Track what we've already shown to avoid duplicates
        shown_images = set()
        shown_containers = set()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Filter out verbose container status messages during startup
            if any(phrase in line for phrase in [
                "Creating", "Created", "Starting", "Started"
            ]) and "Container" in line:
                # Extract container name and show simplified message
                if "Creating" in line and "Container" in line:
                    container_name = line.split("Container ")[1].split(" ")[0]
                    if container_name not in shown_containers:
                        self.log_message(f"📦 Starting {container_name}...")
                        shown_containers.add(container_name)
                continue
                
            # Filter out network creation messages
            if "Network" in line and ("Creating" in line or "Created" in line):
                if "Creating" in line:
                    self.log_message("🌐 Setting up Docker network...")
                continue
                
            # Show image pulling progress in a cleaner way
            if "Pulling" in line and show_progress:
                if " Pulling " in line:
                    image_name = line.split(" ")[0]
                    if image_name not in shown_images:
                        self.log_message(f"⬇️  Pulling {image_name} image...")
                        shown_images.add(image_name)
                elif " Pulled" in line:
                    image_name = line.split(" ")[0]
                    self.log_message(f"✅ {image_name} image ready")
                continue
                
            # Show other important messages
            if any(keyword in line.lower() for keyword in [
                "error", "warning", "failed", "timeout", "denied"
            ]):
                self.log_message(line, "WARNING")
            elif show_progress:
                # Show other non-filtered messages
                self.log_message(line)

    def start_docker(self):
        """Start Docker containers"""
        if not self.validate_requirements():
            self.docker_toggle.setChecked(False)
            return
        
        self.docker_toggle.setEnabled(False)
        self.log_message("🐋 Initializing Docker environment...")
        self.log_message("--------------------------------")
        
        try:
            # Pull images first (important for first-time setup)
            self.log_message("📥 Checking for image updates (may take 10-15 minutes on first run)...")
            if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'pull'], 
                                         "Pulling Docker images", show_progress=True):
                raise Exception("Failed to pull Docker images")
            
            self.log_message("--------------------------------")
            self.log_message("🚀 Launching containers...")
            # Start containers
            if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'up', '-d'], 
                                         "Starting containers", show_progress=True):
                raise Exception("Failed to start Docker containers")
            
            # Wait for containers to initialize
            self.log_message("--------------------------------")
            self.log_message("⏳ Waiting for containers to initialize...")
            import time
            time.sleep(3)
            
            # Verify main container is running
            docker_executable = self._find_docker_executable()
            result = subprocess.run([docker_executable, 'ps', '--filter', 'name=simnibs_container', '--format', '{{.Names}}'], 
                                  capture_output=True, text=True)
            if 'simnibs_container' not in result.stdout:
                raise Exception("simnibs_container is not running")
            
            self.containers_running = True
            self.update_status_display()
            self.log_message("--------------------------------")
            self.log_message("🎉 All containers are ready! You can now launch CLI or GUI.", "SUCCESS")
            
        except Exception as e:
            self.log_message(f"❌ Startup failed: {str(e)}", "ERROR")
            self.message_box.show_message("Startup Failed", str(e), "error", "❌")
            self.containers_running = False
            self.docker_toggle.setChecked(False)
        
        finally:
            self.docker_toggle.setEnabled(True)

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
                            subprocess.Popen([terminal, '-e', f'bash -c "cd \\"{self.script_dir}\\" && {docker_cmd}; exec bash"'])
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
        """Launch GUI interface"""
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
            
            display_env = self.setup_display_env()
            
            # Set up environment
            env = os.environ.copy()
            env["DISPLAY"] = display_env
            env["LOCAL_PROJECT_DIR"] = self.project_dir
            env["PROJECT_DIR_NAME"] = os.path.basename(self.project_dir)
            
            # Additional X11 environment variables for better compatibility
            if system == "Darwin":
                env["LIBGL_ALWAYS_SOFTWARE"] = "1"
                env["XDG_RUNTIME_DIR"] = "/tmp"
                
                # Start socat to bridge X11 connection if needed
                if "localhost" in display_env or any(char.isdigit() for char in display_env.split(':')[0]):
                    self.log_message("Setting up X11 forwarding bridge...", "INFO")
                    try:
                        # Check if socat is available in the container
                        docker_executable = self._find_docker_executable()
                        check_socat = subprocess.run([
                            docker_executable, 'exec', 'simnibs_container', 
                            'which', 'socat'
                        ], capture_output=True, timeout=5)
                        
                        if check_socat.returncode == 0:
                            # Kill any existing socat processes
                            subprocess.run([
                                docker_executable, 'exec', 'simnibs_container',
                                'pkill', '-f', 'socat.*X11'
                            ], capture_output=True)
                            
                            # Start socat bridge
                            host_ip = display_env.split(':')[0]
                            if host_ip in ['localhost', '127.0.0.1']:
                                # For localhost, use the host gateway
                                socat_cmd = [
                                    docker_executable, 'exec', '-d', 'simnibs_container',
                                    'socat', 'TCP-LISTEN:6000,reuseaddr,fork',
                                    'TCP:host.docker.internal:6000'
                                ]
                            else:
                                # For specific IP
                                socat_cmd = [
                                    docker_executable, 'exec', '-d', 'simnibs_container',
                                    'socat', 'TCP-LISTEN:6000,reuseaddr,fork',
                                    f'TCP:{host_ip}:6000'
                                ]
                            
                            subprocess.run(socat_cmd, timeout=5)
                            
                            # Update display to use local X11 server in container
                            display_env = ":0"
                            env["DISPLAY"] = display_env
                            
                            self.log_message("X11 bridge established", "SUCCESS")
                        else:
                            self.log_message("socat not available in container, using direct connection", "WARNING")
                    except Exception as e:
                        self.log_message(f"Could not set up X11 bridge: {e}", "WARNING")
            
            # Test X11 connection before launching GUI
            self.log_message("Testing X11 connection...", "INFO")
            if not self.test_x11_connection(display_env):
                self.log_message("X11 connection test failed, GUI may not work properly", "WARNING")
                if system == "Darwin":
                    self.message_box.show_message(
                        "X11 Connection Failed",
                        "Cannot connect to X11 server. Please:\n\n" +
                        "1. Ensure XQuartz is running\n" +
                        "2. Try restarting XQuartz\n" +
                        "3. Check that X11 forwarding is enabled\n" +
                        "4. Verify your network connection\n\n" +
                        "Continuing anyway, but GUI may not appear.",
                        "warning", "⚠️"
                    )
            
            self.log_message(f"Launching GUI with DISPLAY={display_env}...", "INFO")
            
            # Launch GUI using the same command as the old script
            cmd = ['docker', 'exec', '-e', f'DISPLAY={display_env}', 
                   '-e', 'LIBGL_ALWAYS_SOFTWARE=1',
                   '-e', 'QT_X11_NO_MITSHM=1',  # Additional Qt fix for X11
                   'simnibs_container', '/ti-csc/CLI/GUI.sh']
            
            docker_executable = self._find_docker_executable()
            if docker_executable:
                cmd[0] = docker_executable
            
            # Launch in background to avoid blocking
            process = subprocess.Popen(cmd, cwd=self.script_dir, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.log_message("✓ GUI launch command executed", "SUCCESS")
            
            # Show helpful message for macOS users
            if system == "Darwin":
                self.log_message("Note: GUI should appear in a few seconds. If not, check XQuartz is running.", "INFO")
                self.log_message("Troubleshooting: Try restarting XQuartz if GUI doesn't appear", "INFO")
            
        except Exception as e:
            self.log_message(f"Failed to launch GUI: {e}", "ERROR")
            self.message_box.show_message("GUI Launch Error", f"Failed to launch GUI: {e}", "error", "❌")

    def stop_docker(self):
        """Stop Docker containers"""
        self.docker_toggle.setEnabled(False)
        
        if self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'down'], 
                                 "Stopping containers"):
            self.containers_running = False
            self.update_status_display()
            self.log_message("✓ Docker containers stopped", "SUCCESS")
        
        self.docker_toggle.setEnabled(True)

    def closeEvent(self, event):
        """Handle window close"""
        if self.containers_running:
            reply = QMessageBox.question(self, 'Confirm Exit',
                                       "Docker containers are running. Stop them before exiting?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_docker()
        event.accept()


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("TI-CSC Docker Launcher")
    app.setApplicationDisplayName("TI-CSC Docker Launcher")
    
    # Set application icon if available
    icon_path = os.path.join(os.path.dirname(__file__), "icon.icns")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    window = TICSCLoaderApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main() 