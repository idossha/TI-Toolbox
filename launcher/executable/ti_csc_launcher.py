import sys
import os
import subprocess
import platform
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QMessageBox, QFrame, QScrollArea,
    QCheckBox, QDialog
)
from PyQt6.QtCore import Qt, QProcess, QProcessEnvironment
from PyQt6.QtGui import QFont

class TICSCLoaderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TI-CSC Docker Loader")
        self.setGeometry(100, 100, 800, 650)

        self.project_dir = ""
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.docker_compose_file = os.path.join(self.script_dir, "docker-compose.yml")
        
        # Background terminal process for sending commands
        self.background_process = None
        
        # Docker container state
        self.containers_running = False
        
        # Prevent double-launching
        self.cli_launching = False
        
        # Set up proper PATH for Docker detection
        self._setup_docker_path()
        
        self.init_ui()

    def _setup_docker_path(self):
        """Set up PATH to include common Docker locations"""
        # Common Docker installation paths on macOS
        docker_paths = [
            '/usr/local/bin',
            '/opt/homebrew/bin',  # Homebrew on Apple Silicon
            '/Applications/Docker.app/Contents/Resources/bin',
            '/usr/bin',
            '/bin'
        ]
        
        current_path = os.environ.get('PATH', '')
        path_parts = current_path.split(':') if current_path else []
        
        # Add Docker paths if they're not already in PATH
        for docker_path in docker_paths:
            if docker_path not in path_parts and os.path.exists(docker_path):
                path_parts.insert(0, docker_path)
        
        # Update the PATH
        os.environ['PATH'] = ':'.join(path_parts)

    def _find_docker_executable(self):
        """Find the Docker executable in common locations"""
        docker_locations = [
            '/usr/local/bin/docker',
            '/opt/homebrew/bin/docker',  # Homebrew on Apple Silicon
            '/Applications/Docker.app/Contents/Resources/bin/docker',
            '/usr/bin/docker',
            '/bin/docker'
        ]
        
        # First try the standard 'docker' command (should work if PATH is set correctly)
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

    def show_requirements_help(self):
        """Show system requirements popup"""
        req_dialog = QDialog(self)
        req_dialog.setWindowTitle("System Requirements & Setup Information")
        req_dialog.setModal(True)
        req_dialog.resize(900, 650)
        
        layout = QVBoxLayout(req_dialog)
        
        # Create text display
        text_display = QTextEdit()
        text_display.setReadOnly(True)
        text_display.setStyleSheet("QTextEdit { background-color: white; border: none; }")
        
        req_text = """
<div style='font-family: system-ui, -apple-system, sans-serif; background-color: white; color: black; padding: 20px; margin: 0;'>

<h2 style='color: #2c3e50; text-align: center; margin-bottom: 20px; background-color: transparent;'>
🐋 TI-CSC System Requirements
</h2>

<div style='background-color: #e8f4fd; padding: 15px; border-radius: 8px; border-left: 4px solid #2196F3; margin-bottom: 15px; color: black;'>
<h3 style='color: #1976D2; margin-top: 0; background-color: transparent;'>💻 System Requirements</h3>
<ul style='margin: 10px 0; padding-left: 20px; color: black;'>
<li><b>Operating System:</b> macOS 10.14+, Windows 10+, or modern Linux</li>
<li><b>RAM:</b> 32GB+ minimum for full functionality</li>
<li><b>Docker Desktop or Docker engine:</b> Version 4.0 or higher</li>
</ul>
</div>

<div style='background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #FF9800; margin-bottom: 15px; color: black;'>
<h3 style='color: #F57C00; margin-top: 0; background-color: transparent;'>⏱️ First-Time Setup</h3>
<ul style='margin: 10px 0; padding-left: 20px; color: black;'>
<li><b>Download Size:</b> ~8GB (SimNIBS, FreeSurfer, Python environment)</li>
<li><b>Download Time:</b> 10-15 minutes with good internet connection</li>
<li><b>Internet:</b> Stable connection required for initial setup</li>
<li><b>Subsequent Launches:</b> Fast (seconds) startup as images and volumes are cached locally</li>
</ul>
</div>

<div style='background-color: #d4edda; padding: 15px; border-radius: 8px; border-left: 4px solid #4CAF50; margin-bottom: 15px; color: black;'>
<h3 style='color: #388E3C; margin-top: 0; background-color: transparent;'>🚀 Performance Notes</h3>
<ul style='margin: 10px 0; padding-left: 20px; color: black;'>
<li><b>FreeSurfer Processing:</b> 2-8 hours per subject (depending on hardware)</li>
<li><b>SimNIBS Mesh Generation:</b> ~60 minutes per subject</li>
<li><b>TI Simulations:</b> ~10 minutes per montage</li>
<li><b>Optimization Algorithms:</b> Variable (minutes to hours)</li>
</ul>
</div>

<div style='background-color: #f8d7da; padding: 15px; border-radius: 8px; border-left: 4px solid #f44336; color: black;'>
<h3 style='color: #D32F2F; margin-top: 0; background-color: transparent;'>⚠️ Important Prerequisites</h3>
<ul style='margin: 10px 0; padding-left: 20px; color: black;'>
<li><b>Docker Desktop must be running</b> before starting containers</li>
<li><b>BIDS-compliant data structure</b> is required (see Help button)</li>
<li><b>T1w MRI scans</b> are mandatory (T2w optional but recommended)</li>
<li><b>Administrative privileges</b> may be required for Docker installation</li>
<li><b>X11 forwarding (GUI only):</b> Required for GUI applications
<ul style='margin: 5px 0; padding-left: 15px;'>
<li><b>macOS:</b> Install XQuartz (https://www.xquartz.org/)</li>
<li><b>Linux:</b> X11 usually pre-installed (may need xhost +local:docker)</li>
<li><b>Windows:</b> Install VcXsrv or similar X server</li>
<li><b>Note:</b> CLI functionality works without X forwarding</li>
</ul>
</li>
</ul>
</div>

</div>
        """
        
        text_display.setHtml(req_text)
        layout.addWidget(text_display)
        
        # Add OK button
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(req_dialog.accept)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        layout.addWidget(ok_button)
        
        req_dialog.exec()

    def show_project_help(self):
        """Show help dialog for project directory requirements"""
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("Project Directory Structure Guide")
        help_dialog.setModal(True)
        help_dialog.resize(950, 700)
        
        layout = QVBoxLayout(help_dialog)
        
        # Create text display
        text_display = QTextEdit()
        text_display.setReadOnly(True)
        text_display.setStyleSheet("QTextEdit { background-color: white; border: none; }")
        
        help_text = """
<div style='font-family: system-ui, -apple-system, sans-serif; background-color: white; color: black; padding: 20px; margin: 0;'>

<h2 style='color: #2c3e50; text-align: center; margin-bottom: 20px; background-color: transparent;'>
📁 BIDS Project Directory Structure
</h2>

<div style='background-color: #e3f2fd; padding: 15px; border-radius: 8px; border-left: 4px solid #2196F3; margin-bottom: 15px; color: black;'>
<h3 style='color: #1976D2; margin-top: 0; background-color: transparent;'>🎯 Quick Setup Guide</h3>
<ol style='margin: 10px 0; padding-left: 20px; line-height: 1.6; color: black;'>
<li>Create your project directory (e.g., <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px; color: black;'>"my_TI_project"</code>)</li>
<li>Create the <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px; color: black;'>sourcedata</code> directory structure</li>
<li>Create subject folders (e.g., <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px; color: black;'>"sub-101"</code>)</li>
<li>Place DICOM files in the correct subdirectories (unzipped is okay)</li>
<li>Run preprocessing to generate the full BIDS structure</li>
</ol>
</div>

<div style='background-color: #f3e5f5; padding: 15px; border-radius: 8px; border-left: 4px solid #9C27B0; margin-bottom: 15px; color: black;'>
<h3 style='color: #7B1FA2; margin-top: 0; background-color: transparent;'>🗂️ Directory Structure</h3>
<div style='background-color: #fafafa; padding: 12px; border: 1px solid #e0e0e0; border-radius: 6px; font-family: "SF Mono", Monaco, monospace; font-size: 12px; line-height: 1.4; overflow-x: auto; color: black;'>
<div style='color: #1976D2; font-weight: bold; background-color: transparent;'>Project Directory/</div>
<div style='color: black; background-color: transparent;'>├── <span style='color: #D32F2F; font-weight: bold;'>sourcedata/</span> <span style='color: #666; font-style: italic;'>(👤 Set up by user)</span></div>
<div style='color: black; background-color: transparent;'>│&nbsp;&nbsp;&nbsp;└── sub-{subject}/</div>
<div style='color: black; background-color: transparent;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├── <span style='color: #D32F2F;'>T1w/</span></div>
<div style='color: black; background-color: transparent;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;└── <span style='color: #D32F2F; font-weight: bold;'>dicom/</span> <span style='color: #F57C00; font-style: italic;'>(📄 T1w DICOM files here)</span></div>
<div style='color: black; background-color: transparent;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── T2w/ <span style='color: #666; font-style: italic;'>(optional)</span></div>
<div style='color: black; background-color: transparent;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── dicom/ <span style='color: #F57C00; font-style: italic;'>(📄 T2w DICOM files here)</span></div>
<div style='color: black; background-color: transparent;'>├── <span style='color: #388E3C;'>sub-{subject}/</span> <span style='color: #666; font-style: italic;'>(🤖 Auto-created)</span></div>
<div style='color: black; background-color: transparent;'>├── <span style='color: #388E3C;'>derivatives/</span> <span style='color: #666; font-style: italic;'>(🤖 Auto-created)</span></div>
<div style='color: black; background-color: transparent;'>│&nbsp;&nbsp;&nbsp;├── freesurfer/</div>
<div style='color: black; background-color: transparent;'>│&nbsp;&nbsp;&nbsp;└── SimNIBS/</div>
<div style='color: black; background-color: transparent;'>└── <span style='color: #388E3C;'>ti-csc/</span> <span style='color: #666; font-style: italic;'>(🤖 Auto-created)</span></div>
</div>
</div>

<div style='background-color: #e8f5e8; padding: 15px; border-radius: 8px; border-left: 4px solid #4CAF50; margin-bottom: 15px; color: black;'>
<h3 style='color: #2E7D32; margin-top: 0; background-color: transparent;'>✅ Key Points</h3>
<ul style='margin: 10px 0; padding-left: 20px; line-height: 1.6; color: black;'>
<li>Only the <span style='color: #D32F2F; font-weight: bold;'>sourcedata</span> directory needs manual setup</li>
<li>DICOM files go in <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px; color: black;'>sourcedata/sub-{subject}/T1w/dicom/</code></li>
<li>T2w images improve head model quality but are optional</li>
<li>Subject IDs must follow BIDS: <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px; color: black;'>sub-101</code>, <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px; color: black;'>sub-102</code>, etc.</li>
<li>All processing directories are created automatically</li>
</ul>
</div>

<div style='text-align: center; padding: 10px; background-color: #f5f5f5; border-radius: 6px; color: #666;'>
<small>💡 Need help? Check the TI-CSC documentation or contact your system administrator</small>
</div>

</div>
        """
        
        text_display.setHtml(help_text)
        layout.addWidget(text_display)
        
        # Add OK button
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(help_dialog.accept)
        ok_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-weight: bold;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        layout.addWidget(ok_button)
        
        help_dialog.exec()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # TI-CSC Toolbox Synthesis Section (More Compact)
        synthesis_frame = QFrame()
        synthesis_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        synthesis_frame.setStyleSheet("""
            QFrame {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 6px;
                padding: 8px;
                margin: 2px;
            }
        """)
        synthesis_layout = QVBoxLayout(synthesis_frame)
        synthesis_layout.setSpacing(5)
        
        # Title
        title_label = QLabel("TI-CSC: Temporal Interference Computational Stimulation Consortium")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 3px;")
        synthesis_layout.addWidget(title_label)
        
        # Description (More Compact but Expanded)
        description_text = (
            "Comprehensive toolbox for Temporal Interference (TI) stimulation research providing end-to-end "
            "neuroimaging and simulation capabilities:\n"
            "• Pre-processing: DICOM→NIfTI conversion, FreeSurfer cortical reconstruction, SimNIBS head modeling\n"
            "• Simulation: FEM-based TI field calculations with enhanced control over simulation parameters\n"
            "• Optimization: evolution and exhastive search algorithms for optimal electrode placement\n"
            "• Analysis: atlas-based and arbitrary ROI analysis\n"
            "• Visualization: Interactive NIfTI and mesh viewers with overlay capabilities and 3D rendering"
        )
        description_label = QLabel(description_text)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("color: #34495e; font-size: 10px; line-height: 1.3;")
        synthesis_layout.addWidget(description_label)
        
        main_layout.addWidget(synthesis_frame)

        # System Requirements Button (instead of always showing)
        req_button_layout = QHBoxLayout()
        req_button_layout.addStretch()
        
        self.requirements_button = QPushButton("📋 System Requirements")
        self.requirements_button.clicked.connect(self.show_requirements_help)
        self.requirements_button.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #e67e22;
            }
        """)
        
        req_button_layout.addWidget(self.requirements_button)
        req_button_layout.addStretch()
        main_layout.addLayout(req_button_layout)

        # Project Directory Selection with Help
        dir_layout = QHBoxLayout()
        self.dir_label = QLabel("Project Directory:")
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Select your BIDS-compliant project directory")
        self.dir_input.textChanged.connect(self.on_dir_text_changed)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse_project_dir)
        
        # Help button for project directory (Greyed out)
        self.help_button = QPushButton("❓ Help")
        self.help_button.clicked.connect(self.show_project_help)
        self.help_button.setStyleSheet("""
            QPushButton {
                background-color: #9e9e9e;
                color: white;
                font-size: 10px;
                padding: 4px 8px;
                border: none;
                border-radius: 3px;
                opacity: 0.8;
            }
            QPushButton:hover {
                background-color: #757575;
            }
        """)

        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(self.browse_button)
        dir_layout.addWidget(self.help_button)
        main_layout.addLayout(dir_layout)

        # Docker Control Toggle (Button Left, Status Right)
        docker_control_layout = QHBoxLayout()
        
        # Toggle button first (left side)
        self.docker_toggle = QPushButton("🐋 Start Docker Containers")
        self.docker_toggle.setCheckable(True)
        self.docker_toggle.clicked.connect(self.toggle_docker_containers)
        self.docker_toggle.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                font-weight: bold;
                padding: 8px 16px;
                border: 2px solid #28a745;
                border-radius: 6px;
                background-color: #28a745;
                color: white;
                min-width: 200px;
            }
            QPushButton:hover {
                background-color: #218838;
                border-color: #218838;
            }
            QPushButton:checked {
                background-color: #dc3545;
                border-color: #dc3545;
                color: white;
            }
            QPushButton:checked:hover {
                background-color: #c82333;
                border-color: #c82333;
            }
        """)
        
        # Container status indicator (right side)
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
                margin-left: 10px;
            }
        """)
        
        docker_control_layout.addWidget(self.docker_toggle)
        docker_control_layout.addWidget(self.status_label)
        docker_control_layout.addStretch()
        main_layout.addLayout(docker_control_layout)

        # Console Output Area with Controls at Top Right
        console_header_layout = QHBoxLayout()
        console_label = QLabel("Console Output:")
        console_header_layout.addWidget(console_label)
        console_header_layout.addStretch()
        
        # Launch and Control buttons at top right of console
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
                margin-left: 5px;
            }
            QPushButton:hover {
                background-color: #1B6B93;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        
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
                margin-left: 5px;
            }
            QPushButton:hover {
                background-color: #8B2C5A;
            }
            QPushButton:disabled {
                background-color: #CCCCCC;
                color: #666666;
            }
        """)
        
        self.clear_console_button = QPushButton("🗑️ Clear")
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
                margin-left: 5px;
            }
            QPushButton:hover {
                background-color: #5a6268;
            }
        """)
        
        console_header_layout.addWidget(self.cli_button)
        console_header_layout.addWidget(self.gui_button)
        console_header_layout.addWidget(self.clear_console_button)
        main_layout.addLayout(console_header_layout)
        
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

        self.setLayout(main_layout)
        
        # Initial message
        self.log_message("TI-CSC Docker Launcher ready")
        self.log_message("Select a project directory and start Docker containers to begin")
        self.log_message("First-time setup will download ~30GB of Docker images")

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
            QMessageBox.warning(self, "Error", "Please select a project directory")
            return False
        
        if not os.path.isdir(self.project_dir):
            QMessageBox.warning(self, "Error", f"Directory does not exist: {self.project_dir}")
            return False
        
        if not os.path.exists(self.docker_compose_file):
            QMessageBox.critical(self, "Error", f"docker-compose.yml not found at: {self.docker_compose_file}")
            return False
        
        # Enhanced Docker detection
        docker_executable = self._find_docker_executable()
        if not docker_executable:
            self.log_message("Docker executable not found in common locations", "ERROR")
            QMessageBox.critical(self, "Docker Error", 
                               "Docker executable not found. Please ensure Docker Desktop is installed.\n\n" +
                               "Expected locations:\n" +
                               "• /usr/local/bin/docker\n" +
                               "• /opt/homebrew/bin/docker\n" +
                               "• /Applications/Docker.app/Contents/Resources/bin/docker")
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
            QMessageBox.critical(self, "Docker Error", 
                               "Docker is installed but not running or not accessible.\n\n" +
                               "Please:\n" +
                               "1. Start Docker Desktop\n" +
                               "2. Wait for it to fully start (whale icon in menu bar)\n" +
                               "3. Try again")
            return False
        except subprocess.TimeoutExpired:
            self.log_message("Docker info command timed out", "ERROR")
            QMessageBox.critical(self, "Docker Error", 
                               "Docker is not responding. Please restart Docker Desktop and try again.")
            return False
        except FileNotFoundError:
            self.log_message("Docker executable not found in PATH", "ERROR")
            QMessageBox.critical(self, "Docker Error", 
                               "Docker executable not found. Please ensure Docker Desktop is installed and running.")
            return False

    def setup_display_env(self):
        """Set up DISPLAY environment variable"""
        system = platform.system()
        
        if system == "Darwin":  # macOS
            try:
                result = subprocess.run(
                    'ifconfig en0 | grep inet | awk \'$1=="inet" {print $2}\'',
                    shell=True, capture_output=True, text=True
                )
                host_ip = result.stdout.strip()
                if host_ip:
                    return f"{host_ip}:0"
            except Exception:
                pass
            return "127.0.0.1:0"
            
        elif system == "Linux":
            return os.environ.get("DISPLAY", ":0")
        else:  # Windows
            return "host.docker.internal:0.0"

    def run_docker_command(self, cmd, description):
        """Run a Docker command and log output"""
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
            
            # Log command output
            if result.stdout.strip():
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        self.log_message(line)
            
            if result.stderr.strip():
                for line in result.stderr.strip().split('\n'):
                    if line.strip():
                        self.log_message(line)
            
            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, cmd)
            
            self.log_message(f"✓ {description} completed successfully", "SUCCESS")
            return True
            
        except subprocess.TimeoutExpired:
            self.log_message(f"✗ {description} timed out", "ERROR")
            return False
        except subprocess.CalledProcessError as e:
            self.log_message(f"✗ {description} failed (exit code {e.returncode})", "ERROR")
            return False
        except Exception as e:
            self.log_message(f"✗ {description} failed: {str(e)}", "ERROR")
            return False

    def setup_background_terminal(self):
        """Set up a persistent background terminal connection to the container"""
        if self.background_process and self.background_process.state() == QProcess.ProcessState.Running:
            return True
            
        try:
            # Create background process for persistent container connection
            self.background_process = QProcess(self)
            
            # Connect output handlers
            self.background_process.readyReadStandardOutput.connect(self.handle_background_output)
            self.background_process.readyReadStandardError.connect(self.handle_background_error)
            self.background_process.finished.connect(self.handle_background_finished)
            
            # Set up environment
            env = QProcessEnvironment.systemEnvironment()
            env.insert("DISPLAY", self.setup_display_env())
            env.insert("TERM", "xterm-256color")
            self.background_process.setProcessEnvironment(env)
            
            # Use full path to docker executable
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                raise Exception("Docker executable not found")
            
            # Connect to container
            self.background_process.start(docker_executable, ['exec', '-i', 'simnibs_container', 'bash'])
            
            # Source .bashrc
            self.send_background_command("source ~/.bashrc 2>/dev/null || true")
            
            return True
                
        except Exception as e:
            self.log_message(f"✗ Background terminal setup failed: {e}", "ERROR")
            return False

    def handle_background_output(self):
        """Handle output from background terminal"""
        if self.background_process:
            data = self.background_process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
            if data.strip():
                # Log output from background terminal
                for line in data.strip().split('\n'):
                    if line.strip() and not line.strip().startswith('container$'):
                        self.log_message(f"[CONTAINER] {line.strip()}", "INFO")
    
    def handle_background_error(self):
        """Handle error output from background terminal"""
        if self.background_process:
            data = self.background_process.readAllStandardError().data().decode('utf-8', errors='ignore')
            if data.strip():
                # Log error output from background terminal
                for line in data.strip().split('\n'):
                    if line.strip():
                        self.log_message(f"[CONTAINER ERROR] {line.strip()}", "ERROR")
    
    def handle_background_finished(self):
        """Handle background terminal process termination"""
        self.log_message("Background terminal connection lost", "WARNING")
        self.background_process = None
    
    def send_background_command(self, command):
        """Send a command to the background terminal"""
        if self.background_process and self.background_process.state() == QProcess.ProcessState.Running:
            self.log_message(f"[SENDING] {command}")
            self.background_process.write(f"{command}\n".encode())
            # Give some time for command to execute and produce output
            QApplication.processEvents()
            return True
        return False

    def cleanup_background_terminal(self):
        """Clean up the background terminal process"""
        if self.background_process and self.background_process.state() == QProcess.ProcessState.Running:
            self.send_background_command("exit")
            self.background_process.waitForFinished(3000)
            self.background_process = None

    def start_docker(self):
        """Start Docker containers"""
        if not self.validate_requirements():
            # Reset toggle if validation fails
            self.docker_toggle.setChecked(False)
            self.containers_running = False
            self.update_status_display()
            return

        self.docker_toggle.setEnabled(False)  # Disable during startup
        self.log_message("Starting Docker containers - this may take several minutes on first run...")
        
        try:
            # Pull images
            if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'pull'], 
                                         "Pulling Docker images (this may take 10-15 minutes on first run)"):
                raise Exception("Failed to pull Docker images")
            
            # Start containers
            if not self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'up', '-d'], 
                                         "Starting Docker containers"):
                raise Exception("Failed to start Docker containers")
            
            # Wait for containers to initialize
            import time
            time.sleep(3)
            
            # Verify container is running
            result = subprocess.run(['docker', 'ps', '--filter', 'name=simnibs_container', '--format', '{{.Names}}'], 
                                  capture_output=True, text=True)
            if 'simnibs_container' not in result.stdout:
                raise Exception("simnibs_container is not running")
            
            # Set up background terminal connection
            if self.setup_background_terminal():
                self.log_message("✓ Background terminal ready", "SUCCESS")
            else:
                self.log_message("⚠️ Background terminal setup failed", "WARNING")
            
            # Update state and UI
            self.containers_running = True
            self.update_status_display()
            
            # Enable launch buttons
            self.cli_button.setEnabled(True)
            self.gui_button.setEnabled(True)
            
            self.log_message("✓ Docker containers started successfully!", "SUCCESS")
            
        except Exception as e:
            self.log_message(f"Startup failed: {str(e)}", "ERROR")
            QMessageBox.critical(self, "Startup Failed", str(e))
            self.containers_running = False
            self.docker_toggle.setChecked(False)
            self.update_status_display()
        
        finally:
            self.docker_toggle.setEnabled(True)

    def launch_cli(self):
        """Launch CLI in external terminal"""
        # Prevent double-launching
        if self.cli_launching:
            self.log_message("CLI launch already in progress...", "WARNING")
            return
            
        self.cli_launching = True
        self.cli_button.setEnabled(False)
        
        self.log_message("Launching CLI in external terminal...")
        
        try:
            # Get the docker executable path
            docker_executable = self._find_docker_executable()
            if not docker_executable:
                self.log_message("Docker executable not found", "ERROR")
                return
            
            # Set up environment
            env = os.environ.copy()
            env["DISPLAY"] = self.setup_display_env()
            
            # Docker exec command for CLI
            docker_cmd = [docker_executable, 'exec', '-ti', 'simnibs_container', 'bash']
            
            system = platform.system()
            
            if system == "Darwin":  # macOS
                # Use AppleScript to open a NEW Terminal window (not tab)
                # Escape the command properly to avoid issues
                escaped_cmd = ' '.join([f'"{arg}"' if ' ' in arg else arg for arg in docker_cmd])
                terminal_script = f'''
                tell application "Terminal"
                    do script "{escaped_cmd}"
                    activate
                end tell
                '''
                
                # Run the AppleScript and capture any errors
                result = subprocess.run(['osascript', '-e', terminal_script], 
                                      env=env, capture_output=True, text=True, timeout=10)
                
                if result.returncode == 0:
                    self.log_message("✓ CLI terminal opened successfully", "SUCCESS")
                else:
                    self.log_message(f"AppleScript error: {result.stderr}", "ERROR")
                    # Fallback: try direct terminal command
                    subprocess.Popen(['open', '-a', 'Terminal'] + docker_cmd, env=env)
                    self.log_message("✓ CLI terminal opened with fallback method", "SUCCESS")
                
            elif system == "Linux":
                # Try common Linux terminals
                terminals = ['gnome-terminal', 'konsole', 'xterm', 'terminator']
                launched = False
                
                for terminal in terminals:
                    try:
                        if terminal == 'gnome-terminal':
                            subprocess.Popen([terminal, '--', 'bash', '-c', f"{' '.join(docker_cmd)}; exec bash"], env=env)
                        elif terminal == 'konsole':
                            subprocess.Popen([terminal, '-e', 'bash', '-c', f"{' '.join(docker_cmd)}; exec bash"], env=env)
                        else:  # xterm, terminator
                            subprocess.Popen([terminal, '-e', f"{' '.join(docker_cmd)}"], env=env)
                        
                        self.log_message(f"✓ CLI terminal opened with {terminal}", "SUCCESS")
                        launched = True
                        break
                    except FileNotFoundError:
                        continue
                
                if not launched:
                    self.log_message("No suitable terminal found. Please run manually:", "WARNING")
                    self.log_message(' '.join(docker_cmd))
                    
            elif system == "Windows":
                # Windows Command Prompt
                subprocess.Popen(['cmd', '/c', 'start', 'cmd', '/k'] + docker_cmd, env=env)
                self.log_message("✓ CLI terminal opened in Command Prompt", "SUCCESS")
            
        except Exception as e:
            self.log_message(f"Failed to launch CLI: {e}", "ERROR")
            QMessageBox.critical(self, "CLI Launch Error", f"Failed to launch CLI terminal: {e}")
        
        finally:
            # Re-enable the button after a short delay
            import time
            time.sleep(1)  # Give the terminal time to launch
            self.cli_launching = False
            if self.containers_running:
                self.cli_button.setEnabled(True)

    def launch_gui(self):
        """Launch GUI application using background terminal"""
        self.log_message("Launching GUI application...")
        
        try:
            # Check if background terminal is available
            if not self.background_process or self.background_process.state() != QProcess.ProcessState.Running:
                self.log_message("Background terminal not available, attempting to reconnect...", "WARNING")
                if not self.setup_background_terminal():
                    self.log_message("✗ Cannot launch GUI without background terminal connection", "ERROR")
                    return
                # Give reconnection time to settle
                import time
                time.sleep(2)
            
            # Send GUI command to background terminal
            self.log_message("Sending GUI command to background terminal...")
            if self.send_background_command("/ti-csc/CLI/GUI.sh"):
                self.log_message("✓ GUI command sent successfully!", "SUCCESS")
                self.log_message("Waiting for GUI to start...", "INFO")
                
                # Wait a bit to see if we get any output/errors from the GUI command
                import time
                time.sleep(3)
                QApplication.processEvents()  # Process any pending output
                
                self.log_message("If no error messages appeared above, the GUI should be starting", "INFO")
                self.log_message("Check your screen for the application window", "SUCCESS")
                
                # Also send a test command to verify the terminal is still responsive
                self.send_background_command("echo 'GUI command completed'")
                
            else:
                self.log_message("✗ Failed to send GUI command", "ERROR")
                    
        except Exception as e:
            self.log_message(f"Failed to launch GUI: {e}", "ERROR")
            QMessageBox.critical(self, "GUI Launch Error", f"Failed to launch GUI: {e}")

    def stop_docker(self):
        """Stop Docker containers"""
        # Clean up background terminal first
        self.cleanup_background_terminal()
        
        self.docker_toggle.setEnabled(False)  # Disable during shutdown
        
        if self.run_docker_command(['docker', 'compose', '-f', self.docker_compose_file, 'down'], 
                                 "Stopping containers"):
            self.containers_running = False
            self.update_status_display()
            self.cli_button.setEnabled(False)
            self.gui_button.setEnabled(False)
            self.log_message("✓ Docker containers stopped", "SUCCESS")
        
        self.docker_toggle.setEnabled(True)

    def closeEvent(self, event):
        """Handle window close"""
        # Clean up background terminal
        self.cleanup_background_terminal()
        
        if self.containers_running:
            reply = QMessageBox.question(self, 'Confirm Exit',
                                       "Docker containers are running. Stop them before exiting?",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_docker()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = TICSCLoaderApp()
    main_window.show()
    sys.exit(app.exec()) 