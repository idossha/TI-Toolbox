import sys
import os
import subprocess
import platform
import shutil
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QTextEdit, QMessageBox, QFrame, QScrollArea,
    QCheckBox, QDialog
)
from PyQt6.QtCore import Qt, QProcess, QProcessEnvironment
from PyQt6.QtGui import QFont

# Add parent directory to path to import version module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    import version
    print(f"Version module loaded successfully: {version.__version__}")
except ImportError as e:
    print(f"Failed to import version module: {e}")
    # Fallback if version module not found
    class MockVersion:
        __version__ = "2.0.0"
        def get_version_info(self):
            return {"ti_csc": {"version": "2.0.0", "release_date": "Unknown", "build": "unknown"}}
    version = MockVersion()

class TICSCLoaderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TI-Toolbox Docker Loader")
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
        req_dialog.setFixedSize(900, 700)
        req_dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8f9fa, stop:1 #e9ecef);
            }
        """)
        
        layout = QVBoxLayout(req_dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header section
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 0px;
            }
        """)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(30, 20, 30, 20)
        
        # Header title and icon
        main_title = QLabel("🐋 System Requirements")
        main_title.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        main_title.setStyleSheet("color: white; margin: 0px;")
        main_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle = QLabel("Hardware & Software Prerequisites")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.9); margin: 5px 0px 0px 0px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(main_title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header_widget)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #f1f3f4;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c1c8cd;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a8b2b8;
            }
        """)
        
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(30, 20, 30, 20)
        scroll_layout.setSpacing(20)
        
        # System Requirements Card
        sys_req_content = """
        <div style='font-size: 14px; line-height: 1.8;'>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>Operating System:</b><br>
            <span style='color: #495057;'>macOS 10.14+, Windows 10+, or modern Linux</span>
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>Memory (RAM):</b><br>
            <span style='color: #d32f2f;'>32GB+ minimum</span> for full functionality
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>Docker:</b><br>
            <span style='color: #1976d2;'>Docker Desktop v4.0+</span> or Docker Engine
        </div>
        <div>
            <b style='color: #2c3e50;'>Disk Space:</b><br>
            <span style='color: #f57c00;'>~30GB</span> for all Docker images
        </div>
        </div>
        """
        sys_req_card = self._create_info_card("💻 Hardware Requirements", sys_req_content, "#e3f2fd")
        scroll_layout.addWidget(sys_req_card)
        
        # First-Time Setup Card
        setup_content = """
        <div style='font-size: 14px; line-height: 1.8;'>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>Download Size:</b><br>
            <span style='color: #f57c00;'>~8GB</span> (SimNIBS, FreeSurfer, Python environment)
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>Download Time:</b><br>
            <span style='color: #495057;'>10-15 minutes</span> with good internet connection
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>Internet:</b><br>
            <span style='color: #d32f2f;'>Stable connection required</span> for initial setup
        </div>
        <div>
            <b style='color: #2c3e50;'>Subsequent Launches:</b><br>
            <span style='color: #388e3c;'>Fast startup</span> (seconds) - images cached locally
        </div>
        </div>
        """
        setup_card = self._create_info_card("⏱️ First-Time Setup", setup_content, "#fff3e0")
        scroll_layout.addWidget(setup_card)
        
        # Performance Notes Card
        perf_content = """
        <div style='font-size: 14px; line-height: 1.8;'>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>FreeSurfer Processing:</b><br>
            <span style='color: #495057;'>2-8 hours</span> per subject (hardware dependent)
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>SimNIBS Mesh Generation:</b><br>
            <span style='color: #495057;'>~60 minutes</span> per subject
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>TI Simulations:</b><br>
            <span style='color: #495057;'>~10 minutes</span> per montage
        </div>
        <div>
            <b style='color: #2c3e50;'>Optimization Algorithms:</b><br>
            <span style='color: #495057;'>Variable</span> (minutes to hours)
        </div>
        </div>
        """
        perf_card = self._create_info_card("🚀 Performance Expectations", perf_content, "#e8f5e8")
        scroll_layout.addWidget(perf_card)
        
        # Prerequisites Card
        prereq_content = """
        <div style='font-size: 14px; line-height: 1.8;'>
        <div style='margin-bottom: 15px;'>
            <b style='color: #d32f2f;'>Docker Desktop must be running</b><br>
            <span style='color: #495057;'>Before starting containers</span>
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #d32f2f;'>BIDS-compliant data structure</b><br>
            <span style='color: #495057;'>Required (see Project Help button)</span>
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #d32f2f;'>T1w MRI scans mandatory</b><br>
            <span style='color: #495057;'>T2w optional but recommended</span>
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>X11 Forwarding (GUI only):</b><br>
            <div style='margin-left: 20px; margin-top: 10px;'>
                <div style='margin-bottom: 8px;'><b>macOS:</b> Install <a href='https://www.xquartz.org/' style='color: #1976d2;'>XQuartz</a></div>
                <div style='margin-bottom: 8px;'><b>Linux:</b> X11 usually pre-installed</div>
                <div style='margin-bottom: 8px;'><b>Windows:</b> Install VcXsrv or similar X server</div>
                <div style='color: #666; font-style: italic;'>Note: CLI functionality works without X forwarding</div>
            </div>
        </div>
        </div>
        """
        prereq_card = self._create_info_card("⚠️ Important Prerequisites", prereq_content, "#fce4ec")
        scroll_layout.addWidget(prereq_card)
        
        # Set up scroll area
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        layout.addWidget(scroll_area)
        
        # Footer with close button
        footer_widget = QWidget()
        footer_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #e0e0e0;
            }
        """)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(30, 15, 30, 15)
        footer_layout.addStretch()
        
        close_button = QPushButton("Got it!")
        close_button.clicked.connect(req_dialog.accept)
        close_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 30px;
                border: none;
                border-radius: 25px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5a67d8, stop:1 #6b46c1);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4c51bf, stop:1 #553c9a);
            }
        """)
        
        footer_layout.addWidget(close_button)
        layout.addWidget(footer_widget)
        
        req_dialog.exec()

    def show_project_help(self):
        """Show help dialog for project directory requirements"""
        help_dialog = QDialog(self)
        help_dialog.setWindowTitle("Project Directory Structure Guide")
        help_dialog.setFixedSize(950, 700)
        help_dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8f9fa, stop:1 #e9ecef);
            }
        """)
        
        layout = QVBoxLayout(help_dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header section
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 0px;
            }
        """)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(30, 20, 30, 20)
        
        # Header title and icon
        main_title = QLabel("📁 BIDS Directory Guide")
        main_title.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        main_title.setStyleSheet("color: white; margin: 0px;")
        main_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle = QLabel("Project Structure & Data Organization")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.9); margin: 5px 0px 0px 0px;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(main_title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header_widget)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar:vertical {
                background-color: #f1f3f4;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #c1c8cd;
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #a8b2b8;
            }
        """)
        
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(30, 20, 30, 20)
        scroll_layout.setSpacing(20)
        
        # Quick Setup Guide Card
        setup_content = """
        <div style='font-size: 14px; line-height: 1.8;'>
        <ol style='margin: 0; padding-left: 20px;'>
        <li style='margin-bottom: 12px;'>
            <b>Create your project directory</b><br>
            <span style='color: #666;'>e.g., <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px;'>"my_TI_project"</code></span>
        </li>
        <li style='margin-bottom: 12px;'>
            <b>Create the sourcedata directory structure</b><br>
            <span style='color: #666;'>This is where you'll place your DICOM files</span>
        </li>
        <li style='margin-bottom: 12px;'>
            <b>Create subject folders</b><br>
            <span style='color: #666;'>e.g., <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px;'>"sub-101"</code>, <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px;'>"sub-102"</code></span>
        </li>
        <li style='margin-bottom: 12px;'>
            <b>Place DICOM files in correct subdirectories</b><br>
            <span style='color: #666;'>Unzipped DICOMs are okay</span>
        </li>
        <li>
            <b>Run preprocessing to generate full BIDS structure</b><br>
            <span style='color: #666;'>All other directories created automatically</span>
        </li>
        </ol>
        </div>
        """
        setup_card = self._create_info_card("🎯 Quick Setup Guide", setup_content, "#e3f2fd")
        scroll_layout.addWidget(setup_card)
        
        # Directory Structure Card
        structure_content = """
        <div style='font-family: "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace; font-size: 13px; line-height: 1.6; background-color: #f8f9fa; padding: 20px; border-radius: 8px; border: 1px solid #e9ecef;'>
        <div style='color: #1976d2; font-weight: bold; margin-bottom: 5px;'>📂 Project Directory/</div>
        <div style='margin-left: 0px;'>├── <span style='color: #d32f2f; font-weight: bold;'>sourcedata/</span> <span style='color: #666; font-style: italic;'>(👤 Manual setup)</span></div>
        <div style='margin-left: 0px;'>│&nbsp;&nbsp;&nbsp;└── sub-{subject}/</div>
        <div style='margin-left: 0px;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├── <span style='color: #d32f2f;'>T1w/</span></div>
        <div style='margin-left: 0px;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;└── <span style='color: #d32f2f; font-weight: bold;'>dicom/</span> <span style='color: #f57c00; font-style: italic;'>(📄 T1w DICOM files)</span></div>
        <div style='margin-left: 0px;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── T2w/ <span style='color: #666; font-style: italic;'>(optional)</span></div>
        <div style='margin-left: 0px;'>│&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── dicom/ <span style='color: #f57c00; font-style: italic;'>(📄 T2w DICOM files)</span></div>
        <div style='margin-left: 0px;'>├── <span style='color: #388e3c;'>sub-{subject}/</span> <span style='color: #666; font-style: italic;'>(🤖 Auto-created)</span></div>
        <div style='margin-left: 0px;'>├── <span style='color: #388e3c;'>derivatives/</span> <span style='color: #666; font-style: italic;'>(🤖 Auto-created)</span></div>
        <div style='margin-left: 0px;'>│&nbsp;&nbsp;&nbsp;├── freesurfer/</div>
        <div style='margin-left: 0px;'>│&nbsp;&nbsp;&nbsp;└── SimNIBS/</div>
                        <div style='margin-left: 0px;'>└── <span style='color: #388e3c;'>ti-toolbox/</span> <span style='color: #666; font-style: italic;'>(🤖 Auto-created)</span></div>
        </div>
        """
        structure_card = self._create_info_card("🗂️ Directory Structure", structure_content, "#f3e5f5")
        scroll_layout.addWidget(structure_card)
        
        # Key Points Card
        points_content = """
        <div style='font-size: 14px; line-height: 1.8;'>
        <div style='margin-bottom: 15px;'>
            <b style='color: #d32f2f;'>Only sourcedata needs manual setup</b><br>
            <span style='color: #495057;'>All other directories are created automatically</span>
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>DICOM file location:</b><br>
            <span style='color: #495057;'><code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px;'>sourcedata/sub-{subject}/T1w/dicom/</code></span>
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>T2w images improve quality</b><br>
            <span style='color: #495057;'>Optional but recommended for better head models</span>
        </div>
        <div style='margin-bottom: 15px;'>
            <b style='color: #2c3e50;'>Subject ID format:</b><br>
            <span style='color: #495057;'>Must follow BIDS: <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px;'>sub-101</code>, <code style='background: #f5f5f5; padding: 2px 6px; border-radius: 3px;'>sub-102</code>, etc.</span>
        </div>
        <div>
            <b style='color: #388e3c;'>Processing directories</b><br>
            <span style='color: #495057;'>Created automatically during first run</span>
        </div>
        </div>
        """
        points_card = self._create_info_card("✅ Key Points", points_content, "#e8f5e8")
        scroll_layout.addWidget(points_card)
        
        # Example Card
        example_content = """
        <div style='font-size: 13px; line-height: 1.6;'>
        <div style='background-color: #fff3cd; padding: 15px; border-radius: 8px; margin-bottom: 15px;'>
            <b style='color: #856404;'>Example: Single Subject Setup</b><br>
            <div style='margin-top: 10px; font-family: monospace; font-size: 12px;'>
            my_study/<br>
            └── sourcedata/<br>
            &nbsp;&nbsp;&nbsp;&nbsp;└── sub-001/<br>
            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;├── T1w/<br>
            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;└── dicom/ (place T1 DICOM files here)<br>
            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── T2w/<br>
            &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── dicom/ (place T2 DICOM files here)
            </div>
        </div>
        <div style='text-align: center; color: #666; font-style: italic;'>
            💡 After preprocessing, full BIDS structure with derivatives will be generated
        </div>
        </div>
        """
        example_card = self._create_info_card("📝 Example Setup", example_content, "#fff3e0")
        scroll_layout.addWidget(example_card)
        
        # Set up scroll area
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        layout.addWidget(scroll_area)
        
        # Footer with close button
        footer_widget = QWidget()
        footer_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #e0e0e0;
            }
        """)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(30, 15, 30, 15)
        footer_layout.addStretch()
        
        close_button = QPushButton("Got it!")
        close_button.clicked.connect(help_dialog.accept)
        close_button.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 30px;
                border: none;
                border-radius: 25px;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #5a67d8, stop:1 #6b46c1);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #4c51bf, stop:1 #553c9a);
            }
        """)
        
        footer_layout.addWidget(close_button)
        layout.addWidget(footer_widget)
        
        help_dialog.exec()

    def init_ui(self):
        main_layout = QVBoxLayout()

        # TI-Toolbox Toolbox Synthesis Section (More Compact)
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
        title_label = QLabel("TI-Toolbox: Temporal Interference Computational Stimulation Consortium")
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
        
        # Create Shortcuts Button
        self.shortcuts_button = QPushButton("🔗 Create Desktop Shortcut")
        self.shortcuts_button.clicked.connect(self.show_shortcuts_menu)
        self.shortcuts_button.setStyleSheet("""
            QPushButton {
                background-color: #6f42c1;
                color: white;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #5936a3;
            }
        """)
        
        # Version Info Button
        self.version_button = QPushButton("ℹ️ Version Info")
        self.version_button.clicked.connect(self.show_version_info)
        self.version_button.setStyleSheet("""
            QPushButton {
                background-color: #17a2b8;
                color: white;
                font-size: 11px;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #138496;
            }
        """)
        
        req_button_layout.addWidget(self.requirements_button)
        req_button_layout.addWidget(self.shortcuts_button)
        req_button_layout.addWidget(self.version_button)
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
        self.log_message("TI-Toolbox Docker Launcher ready")
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
            if self.send_background_command("/ti-toolbox/CLI/GUI.sh"):
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

    def create_desktop_shortcut(self):
        """Create a desktop shortcut"""
        try:
            system = platform.system()
            
            if system == "Darwin":  # macOS
                return self._create_macos_desktop_shortcut()
            elif system == "Windows":
                return self._create_windows_desktop_shortcut()
            elif system == "Linux":
                return self._create_linux_desktop_shortcut()
            else:
                self.log_message(f"❌ Desktop shortcuts not supported on {system}", "ERROR")
                return False
                
        except Exception as e:
            self.log_message(f"❌ Error creating desktop shortcut: {str(e)}", "ERROR")
            return False

    def _create_macos_desktop_shortcut(self):
        """Create desktop shortcut on macOS"""
        try:
            # Get the path to the current executable with better detection
            app_path = None
            
            if getattr(sys, 'frozen', False):
                # Running as compiled executable
                executable_path = sys.executable
                self.log_message(f"Frozen executable path: {executable_path}", "INFO")
                
                if executable_path.endswith('MacOS/TI-Toolbox'):
                    # We're inside the .app bundle - go up to get the .app bundle
                    app_path = os.path.dirname(os.path.dirname(os.path.dirname(executable_path)))
                    self.log_message(f"Detected app bundle path: {app_path}", "INFO")
                else:
                    # Fallback - try to find .app bundle
                    current_dir = os.path.dirname(executable_path)
                    while current_dir and current_dir != '/':
                        if current_dir.endswith('.app'):
                            app_path = current_dir
                            break
                        current_dir = os.path.dirname(current_dir)
            
            if not app_path:
                # Running as script or couldn't detect - search for .app bundle
                base_dir = os.path.dirname(os.path.abspath(__file__))
                self.log_message(f"Searching for .app bundle from: {base_dir}", "INFO")
                
                app_name = "TI-Toolbox.app"
                possible_paths = [
                    os.path.join(base_dir, "dist", app_name),
                    os.path.join(base_dir, app_name),
                    os.path.join(os.path.dirname(base_dir), app_name),
                    os.path.join(os.path.dirname(base_dir), "dist", app_name)
                ]
                
                for path in possible_paths:
                    self.log_message(f"Checking path: {path}", "INFO")
                    if os.path.exists(path) and os.path.isdir(path):
                        app_path = path
                        self.log_message(f"Found app bundle: {path}", "SUCCESS")
                        break
                
                if not app_path:
                    self.log_message("❌ Could not find TI-Toolbox.app bundle in any expected location", "ERROR")
                    self.log_message(f"Searched in: {possible_paths}", "ERROR")
                    return False

            # Verify the app bundle exists and is a directory
            if not os.path.exists(app_path):
                self.log_message(f"❌ App bundle does not exist: {app_path}", "ERROR")
                return False
                
            if not os.path.isdir(app_path):
                self.log_message(f"❌ App bundle is not a directory: {app_path}", "ERROR")
                return False

            # Get user's Desktop directory
            desktop_path = os.path.expanduser("~/Desktop")
            if not os.path.exists(desktop_path):
                self.log_message("❌ Desktop directory not found", "ERROR")
                return False

                        # Extract the app name with extension for the alias
            app_name = os.path.basename(app_path)  # This will be "TI-Toolbox.app"
            desktop_shortcut_path = os.path.join(desktop_path, app_name)
            
            self.log_message(f"Creating alias from {app_path} to {desktop_shortcut_path}", "INFO")
            
            # Remove existing shortcut if it exists
            if os.path.exists(desktop_shortcut_path):
                try:
                    if os.path.islink(desktop_shortcut_path) or os.path.isfile(desktop_shortcut_path):
                        os.remove(desktop_shortcut_path)
                    elif os.path.isdir(desktop_shortcut_path):
                        shutil.rmtree(desktop_shortcut_path)
                    self.log_message(f"Removed existing shortcut: {desktop_shortcut_path}", "INFO")
                except Exception as e:
                    self.log_message(f"Warning: Could not remove existing shortcut: {e}", "WARNING")
            
            # Create alias using AppleScript - preserve the .app extension
            applescript = f'''
            tell application "Finder"
                set the source_file to POSIX file "{app_path}" as alias
                set the dest_folder to POSIX file "{desktop_path}" as alias
                try
                    make alias file to source_file at dest_folder with properties {{name:"{app_name}"}}
                    return "success"
                on error error_message
                    return "error: " & error_message
                end try
            end tell
            '''
            
            result = subprocess.run(['osascript', '-e', applescript], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                if "success" in result.stdout:
                    self.log_message(f"✅ Created desktop alias: {app_name}", "SUCCESS")
                    return True
                else:
                    self.log_message(f"AppleScript returned: {result.stdout}", "WARNING")
                    self.log_message(f"AppleScript stderr: {result.stderr}", "WARNING")
                    return False
            else:
                self.log_message(f"❌ AppleScript failed with return code {result.returncode}", "ERROR")
                self.log_message(f"AppleScript error: {result.stderr}", "ERROR")
                return False
            
        except Exception as e:
            self.log_message(f"❌ macOS desktop shortcut error: {str(e)}", "ERROR")
            return False

    def _create_windows_desktop_shortcut(self):
        """Create desktop shortcut on Windows"""
        try:
            try:
                import winshell
                from win32com.client import Dispatch
            except ImportError as e:
                self.log_message("⚠️ Windows shortcut creation requires pywin32 and winshell packages", "WARNING")
                self.log_message("  Install with: pip install pywin32 winshell", "INFO")
                return False
            
            # Get the path to the current executable
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TI-Toolbox.exe")
                if not os.path.exists(exe_path):
                    self.log_message("❌ Could not find TI-Toolbox.exe", "ERROR")
                    return False

            desktop = winshell.desktop()
                        # Use the proper executable name for the shortcut
            exe_name = os.path.basename(exe_path)  # This will be "TI-Toolbox.exe"
            shortcut_name = exe_name.replace('.exe', '.lnk')  # This will be "TI-Toolbox.lnk"
            shortcut_path = os.path.join(desktop, shortcut_name)
            
                        shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = exe_path
            shortcut.WorkingDirectory = os.path.dirname(exe_path)
            shortcut.Description = "TI-Toolbox Docker Launcher"
            # Try to set icon if available
            icon_path = os.path.join(os.path.dirname(exe_path), "icon.ico")
            if os.path.exists(icon_path):
                shortcut.IconLocation = icon_path
            shortcut.save()
            
            self.log_message(f"Created desktop shortcut: {shortcut_name}", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Windows desktop shortcut error: {str(e)}", "ERROR")
            return False

    def _create_linux_desktop_shortcut(self):
        """Create desktop shortcut on Linux"""
        try:
            # Get the path to the current executable
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "TI-Toolbox")
                if not os.path.exists(exe_path):
                    self.log_message("❌ Could not find TI-CSC executable", "ERROR")
                    return False

            desktop_path = os.path.expanduser("~/Desktop")
            if not os.path.exists(desktop_path):
                desktop_path = os.path.expanduser("~/.local/share/applications")

            # Use proper executable name for the desktop file
            exe_name = os.path.basename(exe_path)  # This will be "TI-CSC"
            desktop_file_name = f"{exe_name}.desktop"  # This will be "TI-CSC.desktop"

            shortcut_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=TI-CSC
Comment=TI-CSC Docker Launcher
Exec={exe_path}
Icon={os.path.join(os.path.dirname(exe_path), "icon.png")}
Terminal=false
Categories=Science;
"""
            
            shortcut_path = os.path.join(desktop_path, desktop_file_name)
            with open(shortcut_path, 'w') as f:
                f.write(shortcut_content)
            
            # Make executable
            os.chmod(shortcut_path, 0o755)
            
            self.log_message(f"Created desktop shortcut: {desktop_file_name}", "SUCCESS")
            return True
            
        except Exception as e:
            self.log_message(f"❌ Linux desktop shortcut error: {str(e)}", "ERROR")
            return False

    def _create_info_card(self, title, content, bg_color):
        """Create a styled information card"""
        card_widget = QWidget()
        card_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border-radius: 12px;
                border: 1px solid rgba(0,0,0,0.1);
            }}
        """)
        
        card_layout = QVBoxLayout(card_widget)
        card_layout.setContentsMargins(20, 15, 20, 15)
        card_layout.setSpacing(10)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #2c3e50; margin: 0px;")
        card_layout.addWidget(title_label)
        
        # Content
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.RichText)
        content_label.setStyleSheet("color: #34495e; margin: 0px;")
        card_layout.addWidget(content_label)
        
        return card_widget

    def _show_styled_message(self, title, message, msg_type="info", icon_emoji="ℹ️"):
        """Show a styled message dialog consistent with other dialogs"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(500, 300)
        dialog.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #f8f9fa, stop:1 #e9ecef);
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header section
        header_widget = QWidget()
        if msg_type == "success":
            gradient = "stop:0 #28a745, stop:1 #20c997"
        elif msg_type == "warning":
            gradient = "stop:0 #ffc107, stop:1 #fd7e14"
        elif msg_type == "error":
            gradient = "stop:0 #dc3545, stop:1 #e83e8c"
        else:  # info
            gradient = "stop:0 #667eea, stop:1 #764ba2"
            
        header_widget.setStyleSheet(f"""
            QWidget {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    {gradient});
                border-radius: 0px;
            }}
        """)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(30, 20, 30, 20)
        
        # Header title with icon
        header_title = QLabel(f"{icon_emoji} {title}")
        header_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        header_title.setStyleSheet("color: white; margin: 0px;")
        header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(header_title)
        layout.addWidget(header_widget)
        
        # Content area
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: transparent;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(30, 30, 30, 20)
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setFont(QFont("Arial", 12))
        message_label.setStyleSheet("color: #2c3e50; line-height: 1.6;")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        content_layout.addWidget(message_label)
        layout.addWidget(content_widget)
        
        # Footer with close button
        footer_widget = QWidget()
        footer_widget.setStyleSheet("""
            QWidget {
                background-color: white;
                border-top: 1px solid #e0e0e0;
            }
        """)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(30, 15, 30, 15)
        footer_layout.addStretch()
        
        close_button = QPushButton("OK")
        close_button.clicked.connect(dialog.accept)
        close_button.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    {gradient});
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px 30px;
                border: none;
                border-radius: 25px;
                min-width: 80px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
            QPushButton:pressed {{
                opacity: 0.8;
            }}
        """)
        
        footer_layout.addWidget(close_button)
        layout.addWidget(footer_widget)
        
        dialog.exec()

    def show_shortcuts_menu(self):
        """Create desktop shortcut directly"""
        success = self.create_desktop_shortcut()
        if success:
            self.log_message("✅ Desktop shortcut created successfully", "SUCCESS")
            self._show_styled_message(
                "Shortcut Created",
                "Desktop shortcut created successfully!\n\nYou can now double-click the TI-CSC icon on your desktop to launch the application.",
                "success",
                "✅"
            )
        else:
            self.log_message("❌ Failed to create desktop shortcut", "ERROR")
            self._show_styled_message(
                "Shortcut Error",
                "Failed to create desktop shortcut.\n\nCheck the console output for details.",
                "error",
                "❌"
            )

    def show_version_info(self):
        """Show comprehensive version information in a dialog"""
        try:
            version_info = version.get_version_info()
            print(f"Version info loaded: {version_info}")  # Debug print
            
            # Create a dialog window
            dialog = QDialog(self)
            dialog.setWindowTitle("TI-CSC Version Information")
            dialog.setFixedSize(900, 700)
            dialog.setStyleSheet("""
                QDialog {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #f8f9fa, stop:1 #e9ecef);
                }
            """)
            
            layout = QVBoxLayout(dialog)
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            
            # Header section
            header_widget = QWidget()
            header_widget.setStyleSheet("""
                QWidget {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 #667eea, stop:1 #764ba2);
                    border-radius: 0px;
                }
            """)
            header_layout = QVBoxLayout(header_widget)
            header_layout.setContentsMargins(30, 20, 30, 20)
            
            # Main title
            main_title = QLabel("🧠 TI-CSC")
            main_title.setFont(QFont("Arial", 24, QFont.Weight.Bold))
            main_title.setStyleSheet("color: white; margin: 0px;")
            main_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            subtitle = QLabel("Temporal Interference - Computational Stimulation Core")
            subtitle.setFont(QFont("Arial", 12))
            subtitle.setStyleSheet("color: rgba(255, 255, 255, 0.9); margin: 5px 0px 0px 0px;")
            subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            header_layout.addWidget(main_title)
            header_layout.addWidget(subtitle)
            
            layout.addWidget(header_widget)
            
            # Create a scroll area for the content
            scroll_area = QScrollArea()
            scroll_area.setStyleSheet("""
                QScrollArea {
                    border: none;
                    background-color: transparent;
                }
                QScrollBar:vertical {
                    background-color: #f1f3f4;
                    width: 12px;
                    border-radius: 6px;
                }
                QScrollBar::handle:vertical {
                    background-color: #c1c8cd;
                    border-radius: 6px;
                    min-height: 20px;
                }
                QScrollBar::handle:vertical:hover {
                    background-color: #a8b2b8;
                }
            """)
            
            scroll_widget = QWidget()
            scroll_widget.setStyleSheet("background-color: transparent;")
            scroll_layout = QVBoxLayout(scroll_widget)
            scroll_layout.setContentsMargins(30, 20, 30, 20)
            scroll_layout.setSpacing(20)
            
            # Version info card
            ti_csc_info = version_info.get('ti_csc', {})
            version_card = self._create_info_card(
                "📋 Version Information",
                f"""
                <div style='font-size: 14px; line-height: 1.6;'>
                <b>Version:</b> {ti_csc_info.get('version', 'Unknown')}<br>
                <b>Release Date:</b> {ti_csc_info.get('release_date', 'Unknown')}<br>
                <b>Build:</b> {ti_csc_info.get('build', 'Unknown')}
                </div>
                """,
                "#e3f2fd"
            )
            scroll_layout.addWidget(version_card)
            
            # Docker Images card
            docker_images = version_info.get('docker_images', {})
            docker_content = "<div style='font-size: 13px; line-height: 1.8;'>"
            for name, info in docker_images.items():
                docker_content += f"""
                <div style='margin-bottom: 15px; padding: 10px; background-color: rgba(255,255,255,0.7); border-radius: 8px;'>
                <b style='color: #1976d2;'>{info.get('description', name.title())}</b><br>
                <span style='color: #424242;'>Version: {info.get('version', 'Unknown')}</span><br>
                <span style='color: #666;'>Tag: <code style='background:#f5f5f5; padding:2px 4px; border-radius:3px;'>{info.get('tag', 'Unknown')}</code></span><br>
                <span style='color: #666;'>Size: {info.get('size', 'Unknown')}</span>
                </div>
                """
            docker_content += "</div>"
            
            docker_card = self._create_info_card("🐋 Docker Images", docker_content, "#f3e5f5")
            scroll_layout.addWidget(docker_card)
            
            # Key Tools card
            tools = version_info.get('tools', {})
            key_tools = ['freesurfer', 'simnibs', 'fsl', 'dcm2niix']
            tools_content = "<div style='font-size: 13px; line-height: 1.8;'>"
            
            for tool_name in key_tools:
                if tool_name in tools:
                    tool_info = tools[tool_name]
                    tools_content += f"""
                    <div style='margin-bottom: 15px; padding: 10px; background-color: rgba(255,255,255,0.7); border-radius: 8px;'>
                    <b style='color: #388e3c;'>{tool_info.get('description', tool_name.title())}</b><br>
                    <span style='color: #424242;'>Version: {tool_info.get('version', 'Unknown')}</span><br>
                    <span style='color: #666;'>License: {tool_info.get('license', 'Unknown')}</span><br>
                    <span style='color: #1976d2;'><a href='{tool_info.get('website', '#')}' style='color: #1976d2; text-decoration: none;'>Website ↗</a></span>
                    </div>
                    """
            tools_content += "</div>"
            
            tools_card = self._create_info_card("🛠️ Neuroimaging Tools", tools_content, "#e8f5e8")
            scroll_layout.addWidget(tools_card)
            
            # Python Libraries card
            python_libs = ['numpy', 'scipy', 'matplotlib', 'pandas', 'nibabel', 'vtk', 'gmsh']
            libs_content = "<div style='font-size: 12px; line-height: 1.6;'>"
            
            for lib_name in python_libs:
                if lib_name in tools:
                    lib_info = tools[lib_name]
                    libs_content += f"""
                    <div style='display: inline-block; margin: 5px; padding: 8px 12px; background-color: rgba(255,255,255,0.8); border-radius: 20px; border: 1px solid #ddd;'>
                    <b>{lib_name}</b> v{lib_info.get('version', 'Unknown')}
                    </div>
                    """
            libs_content += "</div>"
            
            libs_card = self._create_info_card("🐍 Python Libraries", libs_content, "#fff3e0")
            scroll_layout.addWidget(libs_card)
            
            # System Requirements card
            sys_req = version_info.get('system_requirements', {})
            sys_content = f"""
            <div style='font-size: 13px; line-height: 1.8;'>
            <div style='display: grid; grid-template-columns: 1fr 1fr; gap: 15px;'>
                <div><b>Minimum RAM:</b><br><span style='color: #d32f2f;'>{sys_req.get('min_ram', 'Unknown')}</span></div>
                <div><b>Recommended RAM:</b><br><span style='color: #388e3c;'>{sys_req.get('recommended_ram', 'Unknown')}</span></div>
                <div><b>Disk Space:</b><br><span style='color: #f57c00;'>{sys_req.get('disk_space', 'Unknown')}</span></div>
                <div><b>Docker Version:</b><br><span style='color: #1976d2;'>{sys_req.get('docker_version', 'Unknown')}</span></div>
            </div>
            <div style='margin-top: 15px;'>
                <b>Supported OS:</b><br>
                <span style='color: #666;'>{', '.join(sys_req.get('supported_os', ['Unknown']))}</span>
            </div>
            </div>
            """
            
            sys_card = self._create_info_card("💻 System Requirements", sys_content, "#fce4ec")
            scroll_layout.addWidget(sys_card)
            
            # Set up scroll area
            scroll_widget.setLayout(scroll_layout)
            scroll_area.setWidget(scroll_widget)
            scroll_area.setWidgetResizable(True)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
            layout.addWidget(scroll_area)
            
            # Footer with close button
            footer_widget = QWidget()
            footer_widget.setStyleSheet("""
                QWidget {
                    background-color: white;
                    border-top: 1px solid #e0e0e0;
                }
            """)
            footer_layout = QHBoxLayout(footer_widget)
            footer_layout.setContentsMargins(30, 15, 30, 15)
            
            footer_layout.addStretch()
            
            close_button = QPushButton("Close")
            close_button.clicked.connect(dialog.accept)
            close_button.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #667eea, stop:1 #764ba2);
                    color: white;
                    font-weight: bold;
                    font-size: 14px;
                    padding: 12px 30px;
                    border: none;
                    border-radius: 25px;
                    min-width: 100px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #5a67d8, stop:1 #6b46c1);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #4c51bf, stop:1 #553c9a);
                }
            """)
            
            footer_layout.addWidget(close_button)
            layout.addWidget(footer_widget)
            
            dialog.setLayout(layout)
            dialog.exec()
            
        except Exception as e:
            # Fallback to simple message if dialog fails
            self.log_message(f"Version info error: {e}", "ERROR")
            QMessageBox.information(self, "Version Info", f"TI-CSC Version: {version.__version__}")
        
        # Also log to console
        self.log_message(f"Displayed version information for TI-CSC v{version.__version__}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = TICSCLoaderApp()
    main_window.show()
    sys.exit(app.exec()) 