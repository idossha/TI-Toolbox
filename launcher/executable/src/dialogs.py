"""
TI-CSC Dialog Classes
Handles all popup dialogs and styled message boxes for the TI-CSC launcher.
"""

import os
import sys
from qt_compat import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QScrollArea, QWidget, QMessageBox, QFrame, Qt, QFont, QPixmap
)

# Add parent directory to path to import version module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
try:
    import version
except ImportError as e:
    # Fallback if version module not found
    class MockVersion:
        __version__ = "2.1.2"
        def get_version_info(self):
            return {"ti_csc": {"version": "2.0.0", "release_date": "Unknown", "build": "unknown"}}
    version = MockVersion()


class StyledDialog:
    """Base class for creating styled dialogs with consistent design"""
    
    @staticmethod
    def create_header(parent, title, subtitle, icon="🧠"):
        """Create a styled header for dialogs"""
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #f8f8f8;")
        
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 15, 20, 12)
        header_layout.setSpacing(4)
        
        # Title with icon
        title_text = f"{icon} {title}"
        title_label = QLabel(title_text)
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333333; background: transparent;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title_label)
        
        # Subtitle
        subtitle_label = QLabel(subtitle)
        subtitle_label.setFont(QFont("Arial", 11))
        subtitle_label.setStyleSheet("color: #666666; background: transparent;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(subtitle_label)
        
        return header_widget
    
    @staticmethod
    def create_scroll_area():
        """Create a consistent scroll area"""
        scroll_area = QScrollArea()
        scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: white;
            }
            QScrollBar:vertical {
                background-color: #f0f0f0;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background-color: #cccccc;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #999999;
            }
        """)
        return scroll_area
    
    @staticmethod
    def create_info_card(title, content, bg_color="#ffffff"):
        """Create a styled information card"""
        # Create outer container for the card
        card_container = QFrame()
        card_container.setFrameShape(QFrame.Shape.NoFrame)
        card_container.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                margin: 8px 0px;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }}
        """)
        
        card_layout = QVBoxLayout(card_container)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)
        
        # Title
        title_label = QLabel(title)
        title_label.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333333; background: transparent; border: none;")
        card_layout.addWidget(title_label)
        
        # Content
        content_label = QLabel(content)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.RichText)
        content_label.setStyleSheet("color: #444444; background: transparent; border: none;")
        card_layout.addWidget(content_label)
        
        return card_container
    
    @staticmethod
    def create_footer_with_button(parent, button_text="Got it!", callback=None):
        """Create a styled footer with close button"""
        footer_widget = QWidget()
        footer_widget.setStyleSheet("background-color: #f8f8f8;")
        
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(20, 8, 20, 12)
        
        # Spacer
        footer_layout.addStretch()
        
        # Close button
        close_btn = QPushButton(button_text)
        close_btn.setFont(QFont("Arial", 11))
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                padding: 8px 20px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2968a3;
            }
        """)
        
        if callback:
            close_btn.clicked.connect(callback)
        
        footer_layout.addWidget(close_btn)
        
        return footer_widget, close_btn


class SystemRequirementsDialog(StyledDialog):
    """Dialog for showing system requirements"""
    
    def __init__(self, parent):
        self.parent = parent
    
    def show(self):
        """Display the system requirements dialog"""
        dialog = QDialog(self.parent)
        dialog.setWindowTitle("System Requirements")
        dialog.setFixedSize(750, 600)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = self.create_header(dialog, "System Requirements", "Hardware & Software Prerequisites", "💻")
        layout.addWidget(header)
        
        # Content
        scroll_area = self.create_scroll_area()
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: white;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(16, 10, 16, 10)
        scroll_layout.setSpacing(8)
        
        # Add content cards
        self._add_content_cards(scroll_layout)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        layout.addWidget(scroll_area)
        
        # Footer
        footer, close_btn = self.create_footer_with_button(dialog, callback=dialog.accept)
        layout.addWidget(footer)
        
        dialog.exec()
    
    def _add_content_cards(self, layout):
        """Add all content cards to the layout"""
        # Hardware Requirements Card
        hw_content = """
        <div style='font-size: 13px; line-height: 1.4; background: transparent;'>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Operating System:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>macOS 10.14+, Windows 10+, or modern Linux</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Memory (RAM):</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>32GB+ minimum</span><span style='background: transparent;'> for full functionality</span><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>64GB+ recommended</span><span style='background: transparent;'> for optimal performance</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Docker:</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>Docker Desktop v4.0+</span><span style='background: transparent;'> or Docker Engine</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>Must be running and accessible</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Disk Space:</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>~30GB</span><span style='background: transparent;'> for all Docker images</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>Additional space needed for project data</span>
        </div>
        <div style='background: transparent;'>
            <b style='color: #333333; background: transparent;'>CPU:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>Multi-core processor recommended</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>8+ cores for optimal FreeSurfer performance</span>
        </div>
        </div>
        """
        hw_card = self.create_info_card("💻 Hardware Requirements", hw_content)
        layout.addWidget(hw_card)
        
        # First-Time Setup Card
        setup_content = """
        <div style='font-size: 13px; line-height: 1.4; background: transparent;'>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Initial Download Size:</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>~30GB total</span><span style='background: transparent;'> for all images</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• SimNIBS Core: ~8GB</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• FreeSurfer: ~12GB</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• FSL: ~4GB</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Python Environment: ~3GB</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Download Time:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>15-30 minutes</span><span style='background: transparent;'> with good internet connection</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>Varies based on internet speed and Docker cache</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Internet Connection:</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>Stable, high-speed connection required</span><span style='background: transparent;'> for initial setup</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>Broadband recommended (25+ Mbps)</span>
        </div>
        <div style='background: transparent;'>
            <b style='color: #333333; background: transparent;'>Subsequent Launches:</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>Fast startup</span><span style='background: transparent;'> (30-60 seconds) - images cached locally</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>No internet required after initial setup</span>
        </div>
        </div>
        """
        setup_card = self.create_info_card("⏱️ First-Time Setup", setup_content)
        layout.addWidget(setup_card)

        # Docker Setup Instructions Card
        docker_setup_content = """
        <div style='font-size: 13px; line-height: 1.4; background: transparent;'>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>macOS Setup:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>1. Download Docker Desktop from docker.com</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>2. Install and start Docker Desktop</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>3. Wait for whale icon in menu bar</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>4. Allocate at least 16GB RAM in Docker settings</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Windows Setup:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>1. Enable WSL2 (Windows Subsystem for Linux)</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>2. Download Docker Desktop for Windows</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>3. Use WSL2 backend (recommended)</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>4. Allocate sufficient resources</span>
        </div>
        <div style='background: transparent;'>
            <b style='color: #333333; background: transparent;'>Linux Setup:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>1. Install Docker Engine via package manager</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>2. Add user to docker group</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>3. Start Docker service</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>4. Test with: docker run hello-world</span>
        </div>
        </div>
        """
        docker_card = self.create_info_card("🐋 Docker Setup Instructions", docker_setup_content)
        layout.addWidget(docker_card)

        # XQuartz Setup Card (macOS specific)
        xquartz_content = """
        <div style='font-size: 13px; line-height: 1.4; background: transparent;'>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>XQuartz Requirements (macOS):</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>XQuartz 2.7.7 - 2.8.0</span><span style='background: transparent;'> (newer versions may have issues)</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>Download from: xquartz.macosforge.org</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Installation Steps:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>1. Download and install XQuartz</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>2. Log out and log back in (required!)</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>3. Launch XQuartz from Applications > Utilities</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>4. Check X11 forwarding is enabled in Terminal</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Automatic Configuration:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• TI-CSC launcher automatically configures XQuartz</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Enables network client connections</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Sets up proper X11 permissions</span>
        </div>
        <div style='background: transparent;'>
            <b style='color: #333333; background: transparent;'>Troubleshooting:</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>GUI not appearing?</span><span style='background: transparent;'> Check XQuartz is running</span><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>Permission denied?</span><span style='background: transparent;'> Restart XQuartz and try again</span><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>Version issues?</span><span style='background: transparent;'> Downgrade to XQuartz 2.7.7</span>
        </div>
        </div>
        """
        xquartz_card = self.create_info_card("🖼️ XQuartz Setup (macOS GUI)", xquartz_content, "#f0f8ff")
        layout.addWidget(xquartz_card)

        # Performance & Memory Card
        performance_content = """
        <div style='font-size: 13px; line-height: 1.4; background: transparent;'>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Memory Allocation:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Docker: Allocate 16-24GB to Docker</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Host System: Reserve 8-16GB for OS</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Total: 32GB+ system memory required</span>
        </div>
        <div style='margin-bottom: 8px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Performance Tips:</b><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Close other memory-intensive applications</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Use SSD storage for better I/O performance</span><br style='background: transparent;'>
            <span style='color: #666666; background: transparent;'>• Monitor system resources during processing</span>
        </div>
        <div style='background: transparent;'>
            <b style='color: #333333; background: transparent;'>Common Issues:</b><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>• Out of memory errors:</span><span style='background: transparent;'> Increase Docker memory</span><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>• Slow performance:</span><span style='background: transparent;'> Check available RAM</span><br style='background: transparent;'>
            <span style='color: #333333; background: transparent;'>• Docker not found:</span><span style='background: transparent;'> Ensure Docker is running</span>
        </div>
        </div>
        """
        performance_card = self.create_info_card("⚡ Performance & Troubleshooting", performance_content)
        layout.addWidget(performance_card)


class ProjectHelpDialog(StyledDialog):
    """Dialog for showing project directory help"""
    
    def __init__(self, parent):
        self.parent = parent
    
    def show(self):
        dialog = QDialog(self.parent)
        dialog.setWindowTitle("Project Directory Structure Guide")
        dialog.setFixedSize(800, 600)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = self.create_header(dialog, "BIDS Directory Guide", "Project Structure & Data Organization", "📁")
        layout.addWidget(header)
        
        # Content
        scroll_area = self.create_scroll_area()
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("background-color: white;")
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(16, 10, 16, 10)
        scroll_layout.setSpacing(8)
        
        # Add content cards
        self._add_content_cards(scroll_layout)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        layout.addWidget(scroll_area)
        
        # Footer
        footer, close_btn = self.create_footer_with_button(dialog, callback=dialog.accept)
        layout.addWidget(footer)
        
        dialog.exec()
    
    def _add_content_cards(self, layout):
        """Add all content cards to the layout"""
        # Quick Setup Guide Card
        setup_content = """
        <div style='background: #f5f5f5; border: 2px solid #999999; border-radius: 6px; padding: 12px; margin: 8px 0;'>
        <div style='font-size: 13px; line-height: 1.4; background: transparent;'>
        <ol style='margin: 0; padding-left: 16px; background: transparent;'>
        <li style='margin-bottom: 8px; background: transparent;'>
            <b style='background: transparent;'>Create your project directory</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>e.g., <code style='background: transparent; font-family: monospace; color: #333;'>"my_TI_project"</code></span>
        </li>
        <li style='margin-bottom: 8px; background: transparent;'>
            <b style='background: transparent;'>Create the sourcedata directory structure</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>This is where you'll place your DICOM files</span>
        </li>
        <li style='margin-bottom: 8px; background: transparent;'>
            <b style='background: transparent;'>Create subject folders</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>e.g., <code style='background: transparent; font-family: monospace; color: #333;'>"sub-101"</code>, <code style='background: transparent; font-family: monospace; color: #333;'>"sub-102"</code></span>
        </li>
        <li style='margin-bottom: 8px; background: transparent;'>
            <b style='background: transparent;'>Place DICOM files in correct subdirectories</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>Unzipped DICOMs are okay</span>
        </li>
        <li style='background: transparent;'>
            <b style='background: transparent;'>Run preprocessing to generate full BIDS structure</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>All other directories created automatically</span>
        </li>
        </ol>
        </div>
        </div>
        """
        setup_card = self.create_info_card("🎯 Quick Setup Guide", setup_content)
        layout.addWidget(setup_card)

        # BIDS Directory Structure Card
        bids_structure_content = """
        <div style='font-size: 12px; line-height: 1.3; background: transparent;'>
        <div style='margin-bottom: 10px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Complete BIDS Structure:</b>
        </div>
        <div style='background: #f5f5f5; border: 2px solid #999999; border-radius: 6px; padding: 12px; margin: 8px 0;'>
            <pre style='background: transparent; font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", "Source Code Pro", Consolas, "Ubuntu Mono", monospace; font-size: 12px; color: #2d3748; margin: 0; padding: 0; border: none; line-height: 1.4; white-space: pre;'>my_project/
├── sourcedata/           <span style='color: #718096; background: transparent; font-style: italic;'># Your DICOM files go here</span>
│   ├── sub-101/
│   │   └── anat/         <span style='color: #718096; background: transparent; font-style: italic;'># Anatomical DICOMs</span>
│   │       └── *.dcm
│   └── sub-102/
├── sub-101/              <span style='color: #718096; background: transparent; font-style: italic;'># Generated by preprocessing</span>
│   ├── anat/
│   │   └── sub-101_T1w.nii.gz
│   └── derivatives/
│       ├── freesurfer/
│       └── simnibs/
├── derivatives/
└── README.md</pre>
        </div>
        <div style='background: transparent;'>
            <span style='color: #666666; background: transparent;'><b style='background: transparent;'>Note:</b> Only create the <code style='background: #f5f5f5; padding: 2px 4px; border-radius: 3px; font-family: monospace; color: #d73a49; border: 1px solid #e1e4e8;'>sourcedata/</code> directory manually. All other directories are generated automatically during preprocessing.</span>
        </div>
        </div>
        """
        bids_card = self.create_info_card("📂 BIDS Directory Structure", bids_structure_content)
        layout.addWidget(bids_card)

        # DICOM Organization Card
        dicom_org_content = """
        <div style='background: #f5f5f5; border: 2px solid #999999; border-radius: 6px; padding: 12px; margin: 8px 0;'>
        <div style='font-size: 13px; line-height: 1.5; background: transparent;'>
        <div style='margin-bottom: 10px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>DICOM File Organization:</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Extract all DICOM files from ZIP/TAR archives</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Place in subject-specific folders under sourcedata/</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Anatomical scans should be in anat/ subdirectory</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Multiple sessions can be organized as ses-01/, ses-02/, etc.</span>
        </div>
        <div style='margin-bottom: 10px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Supported Formats:</b><br style='background: transparent;'>
            <span style='color: #388e3c; background: transparent;'>✓ DICOM files (.dcm, .ima, no extension)</span><br style='background: transparent;'>
            <span style='color: #388e3c; background: transparent;'>✓ Compressed DICOM (.dcm.gz)</span><br style='background: transparent;'>
            <span style='color: #388e3c; background: transparent;'>✓ DICOM directories (multiple files)</span><br style='background: transparent;'>
            <span style='color: #d32f2f; background: transparent;'>✗ NIfTI files (use dcm2niix first)</span>
        </div>
        <div style='margin-bottom: 6px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Example DICOM Structure:</b>
        </div>
        </div>
        <div style='background: #f5f5f5; border: 2px solid #999999; border-radius: 6px; padding: 12px; margin: 8px 0;'>
            <pre style='background: transparent; font-family: "SF Mono", "Monaco", "Inconsolata", "Fira Code", "Source Code Pro", Consolas, "Ubuntu Mono", monospace; font-size: 12px; color: #2d3748; margin: 0; padding: 0; border: none; line-height: 1.4; white-space: pre;'>sourcedata/
├── sub-101/
│   └── anat/
│       ├── IM_0001.dcm
│       ├── IM_0002.dcm
│       └── <span style='color: #718096; background: transparent; font-style: italic;'>... (all T1w DICOM slices)</span>
└── sub-102/</pre>
        </div>
        </div>
        """
        dicom_card = self.create_info_card("💾 DICOM Organization", dicom_org_content)
        layout.addWidget(dicom_card)

        # Processing Workflow Card
        workflow_content = """
        <div style='background: #f5f5f5; border: 2px solid #999999; border-radius: 6px; padding: 12px; margin: 8px 0;'>
        <div style='font-size: 13px; line-height: 1.5; background: transparent;'>
        <div style='margin-bottom: 6px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>TI-CSC Processing Workflow:</b>
            <ol style='margin: 8px 0; padding-left: 16px; background: transparent;'>
            <li style='margin-bottom: 6px; background: transparent;'>
                <b style='background: transparent;'>DICOM to NIfTI Conversion</b><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'>Converts DICOM files to BIDS-compliant NIfTI format</span>
            </li>
            <li style='margin-bottom: 6px; background: transparent;'>
                <b style='background: transparent;'>FreeSurfer Reconstruction</b><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'>Cortical surface reconstruction and segmentation</span>
            </li>
            <li style='margin-bottom: 6px; background: transparent;'>
                <b style='background: transparent;'>SimNIBS Head Modeling</b><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'>Finite element head model generation</span>
            </li>
            <li style='background: transparent;'>
                <b style='background: transparent;'>TI Field Simulation</b><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'>Temporal interference field calculations</span>
            </li>
            </ol>
        </div>
        <div style='background: transparent;'>
            <b style='color: #333333; background: transparent;'>Processing Time Estimates:</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• DICOM Conversion: 2-5 minutes</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• FreeSurfer: 4-8 hours</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• SimNIBS: 1-3 hours</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• TI Simulation: 10-30 minutes</span>
        </div>
        </div>
        </div>
        """
        workflow_card = self.create_info_card("⚙️ Processing Workflow", workflow_content)
        layout.addWidget(workflow_card)

        # Troubleshooting Card
        troubleshooting_content = """
        <div style='background: #f5f5f5; border: 2px solid #999999; border-radius: 6px; padding: 12px; margin: 8px 0;'>
        <div style='font-size: 13px; line-height: 1.5; background: transparent;'>
        <div style='margin-bottom: 6px; background: transparent;'>
            <b style='color: #333333; background: transparent;'>Common Issues & Solutions:</b>
            <div style='margin: 6px 0; background: transparent;'>
                <span style='color: #d32f2f; background: transparent;'><b style='background: transparent;'>Error:</b> "No DICOM files found"</span><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'><b style='background: transparent;'>Solution:</b> Ensure DICOMs are in sourcedata/sub-XXX/anat/ folder</span>
            </div>
            <div style='margin: 6px 0; background: transparent;'>
                <span style='color: #d32f2f; background: transparent;'><b style='background: transparent;'>Error:</b> "Invalid BIDS structure"</span><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'><b style='background: transparent;'>Solution:</b> Follow exact naming: sub-001, sub-002, etc.</span>
            </div>
            <div style='margin: 6px 0; background: transparent;'>
                <span style='color: #d32f2f; background: transparent;'><b style='background: transparent;'>Error:</b> "Permission denied"</span><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'><b style='background: transparent;'>Solution:</b> Check folder permissions, avoid system directories</span>
            </div>
        </div>
        <div style='background: transparent;'>
            <b style='color: #333333; background: transparent;'>Best Practices:</b><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Use descriptive project names without spaces</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Keep project directory on local disk (not network)</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Backup important data before processing</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>• Monitor disk space during processing</span>
        </div>
        </div>
        </div>
        """
        troubleshooting_card = self.create_info_card("🔧 Troubleshooting & Best Practices", troubleshooting_content)
        layout.addWidget(troubleshooting_card)


class VersionInfoDialog(StyledDialog):
    """Dialog for showing version information"""
    
    def __init__(self, parent, logger=None):
        self.parent = parent
        self.logger = logger
    
    def show(self):
        """Display the version information dialog"""
        try:
            version_info = version.get_version_info()
            
            dialog = QDialog(self.parent)
            dialog.setWindowTitle("Version Information")
            dialog.setFixedSize(700, 550)
            dialog.setStyleSheet("""
                QDialog {
                    background-color: white;
                }
            """)
            
            layout = QVBoxLayout(dialog)
            layout.setSpacing(0)
            layout.setContentsMargins(0, 0, 0, 0)
            
            # Custom header with actual icon
            header = self._create_header_with_icon(dialog)
            layout.addWidget(header)
            
            # Content
            scroll_area = self.create_scroll_area()
            scroll_widget = QWidget()
            scroll_widget.setStyleSheet("background-color: white;")
            scroll_layout = QVBoxLayout(scroll_widget)
            scroll_layout.setContentsMargins(16, 10, 16, 10)
            scroll_layout.setSpacing(8)
            
            # Add version cards
            self._add_version_cards(scroll_layout, version_info)
            
            scroll_widget.setLayout(scroll_layout)
            scroll_area.setWidget(scroll_widget)
            scroll_area.setWidgetResizable(True)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            
            layout.addWidget(scroll_area)
            
            # Footer
            footer, close_btn = self.create_footer_with_button(dialog, callback=dialog.accept)
            layout.addWidget(footer)
            
            dialog.exec()
            
            if self.logger:
                self.logger(f"Displayed version information for TI-CSC v{version.__version__}")
                
        except Exception as e:
            if self.logger:
                self.logger(f"Version info error: {e}", "ERROR")
            # Fallback dialog
            msg = QMessageBox(self.parent)
            msg.setWindowTitle("Version Information")
            msg.setText("Unable to load version information")
            msg.setInformativeText(f"Error: {str(e)}")
            msg.exec()
    
    def _create_header_with_icon(self, parent):
        """Create header with actual TI-CSC icon"""
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f8f8;
            }
        """)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        # Title with icon layout
        title_layout = QHBoxLayout()
        title_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Load and add icon
        icon_path = os.path.join(os.path.dirname(__file__), "icon.icns")
        if os.path.exists(icon_path):
            icon_label = QLabel()
            pixmap = QPixmap(icon_path)
            # Scale icon to appropriate size (20x20 pixels for dialog header)
            scaled_pixmap = pixmap.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            icon_label.setPixmap(scaled_pixmap)
            title_layout.addWidget(icon_label)
        
        main_title = QLabel("TI-CSC")
        main_title.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        main_title.setStyleSheet("color: #333333; background: transparent; margin-left: 8px;")
        title_layout.addWidget(main_title)
        
        # Create widget for title layout
        title_widget = QWidget()
        title_widget.setLayout(title_layout)
        
        subtitle_label = QLabel("Temporal Interference Toolbox")
        subtitle_label.setFont(QFont("Arial", 11))
        subtitle_label.setStyleSheet("color: #666666; background: transparent; margin-top: 4px;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(title_widget)
        header_layout.addWidget(subtitle_label)
        
        return header_widget
    
    def _add_version_cards(self, layout, version_info):
        """Add version information cards"""
        # Version info card
        ti_csc_info = version_info.get('ti_csc', {})
        version_content = f"""
        <div style='font-size: 14px; line-height: 1.6; background: transparent;'>
        <b style='background: transparent;'>Version:</b><span style='background: transparent;'> {ti_csc_info.get('version', 'Unknown')}</span><br style='background: transparent;'>
        <b style='background: transparent;'>Release Date:</b><span style='background: transparent;'> {ti_csc_info.get('release_date', 'Unknown')}</span><br style='background: transparent;'>
        <b style='background: transparent;'>Build:</b><span style='background: transparent;'> {ti_csc_info.get('build', 'Unknown')}</span>
        </div>
        """
        version_card = self.create_info_card("📋 Version Information", version_content)
        layout.addWidget(version_card)
        
        # Docker Images card
        docker_images = version_info.get('docker_images', {})
        docker_content = "<div style='font-size: 13px; line-height: 1.8; background: transparent;'>"
        for name, info in docker_images.items():
            docker_content += f"""
            <div style='margin-bottom: 15px; padding: 10px; background-color: rgba(255,255,255,0.7); border-radius: 8px;'>
            <b style='color: #1976d2; background: transparent;'>{info.get('description', name.title())}</b><br style='background: transparent;'>
            <span style='color: #424242; background: transparent;'>Version: {info.get('version', 'Unknown')}</span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>Tag: <code style='background:#f5f5f5; padding:2px 4px; border-radius:3px;'>{info.get('tag', 'Unknown')}</code></span><br style='background: transparent;'>
            <span style='color: #666; background: transparent;'>Size: {info.get('size', 'Unknown')}</span>
            </div>
            """
        docker_content += "</div>"
        
        docker_card = self.create_info_card("🐋 Docker Images", docker_content)
        layout.addWidget(docker_card)
        
        # Tools card
        tools = version_info.get('tools', {})
        key_tools = ['freesurfer', 'simnibs', 'fsl', 'dcm2niix']
        tools_content = "<div style='font-size: 13px; line-height: 1.8; background: transparent;'>"
        
        for tool_name in key_tools:
            if tool_name in tools:
                tool_info = tools[tool_name]
                # Use tool name as title, description as content
                display_name = tool_name.upper() if tool_name in ['fsl'] else tool_name.title()
                website_url = tool_info.get('website', '#')
                tools_content += f"""
                <div style='margin-bottom: 15px; padding: 10px; background-color: rgba(255,255,255,0.7); border-radius: 8px;'>
                <b style='color: #388e3c; background: transparent;'>{display_name}</b><br style='background: transparent;'>
                <span style='color: #424242; background: transparent;'>{tool_info.get('description', 'No description available')}</span><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'>Version: {tool_info.get('version', 'Unknown')}</span><br style='background: transparent;'>
                <span style='color: #666; background: transparent;'>License: {tool_info.get('license', 'Unknown')}</span><br style='background: transparent;'>
                <a href="{website_url}" style='color: #1976d2; text-decoration: underline; background: transparent;'>Visit Website ↗</a>
                </div>
                """
        tools_content += "</div>"
        
        tools_card = self.create_info_card("🛠️ Neuroimaging Tools", tools_content)
        layout.addWidget(tools_card)


class StyledMessageBox(StyledDialog):
    """Styled message box for consistent notifications"""
    
    def __init__(self, parent):
        self.parent = parent
    
    def show_custom_message(self, title, message, buttons=["OK", "Cancel"]):
        """Show a styled message dialog with custom buttons"""
        dialog = QDialog(self.parent)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(480, 350)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header section
        header_widget = QWidget()
        header_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
            }
        """)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        # Header title with icon
        header_title = QLabel(f"🖥️ {title}")
        header_title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        header_title.setStyleSheet("color: #4a90e2; background: transparent;")
        header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(header_title)
        layout.addWidget(header_widget)
        
        # Content area
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 15)
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setFont(QFont("Arial", 11))
        message_label.setStyleSheet("color: #444444; line-height: 1.4; background: transparent;")
        message_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        content_layout.addWidget(message_label)
        layout.addWidget(content_widget)
        
        # Footer with custom buttons
        footer_widget = QWidget()
        footer_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
            }
        """)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(20, 12, 20, 12)
        footer_layout.addStretch()
        
        result = None
        
        # Create buttons
        for i, button_text in enumerate(buttons):
            button = QPushButton(button_text)
            
            if i == 0:  # First button (primary action)
                button.setStyleSheet("""
                    QPushButton {
                        background-color: #4a90e2;
                        color: white;
                        font-weight: bold;
                        font-size: 13px;
                        padding: 10px 20px;
                        min-width: 80px;
                        margin-left: 5px;
                    }
                    QPushButton:hover {
                        background-color: #357abd;
                    }
                    QPushButton:pressed {
                        background-color: #2968a3;
                    }
                """)
            else:  # Secondary buttons
                button.setStyleSheet("""
                    QPushButton {
                        background-color: #6c757d;
                        color: white;
                        font-weight: bold;
                        font-size: 13px;
                        padding: 10px 20px;
                        min-width: 80px;
                        margin-left: 5px;
                    }
                    QPushButton:hover {
                        background-color: #5a6268;
                    }
                    QPushButton:pressed {
                        background-color: #484e53;
                    }
                """)
            
            # Capture the button text in the lambda closure
            button.clicked.connect(lambda checked, text=button_text: (
                setattr(dialog, 'result_text', text),
                dialog.accept()
            ))
            
            footer_layout.addWidget(button)
        
        layout.addWidget(footer_widget)
        
        # Show dialog and return the result
        dialog.result_text = buttons[-1] if buttons else "Cancel"  # Default to last button
        dialog.exec()
        
        return getattr(dialog, 'result_text', buttons[-1] if buttons else "Cancel")

    def show_message(self, title, message, msg_type="info", icon_emoji="ℹ️"):
        """Show a styled message dialog"""
        dialog = QDialog(self.parent)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(400, 220)
        dialog.setStyleSheet("""
            QDialog {
                background-color: white;
            }
        """)
        
        layout = QVBoxLayout(dialog)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header section
        header_widget = QWidget()
        if msg_type == "success":
            bg_color = "#f8f9fa"
            text_color = "#28a745"
        elif msg_type == "warning":
            bg_color = "#f8f9fa"
            text_color = "#ffc107"
        elif msg_type == "error":
            bg_color = "#f8f9fa"
            text_color = "#dc3545"
        else:  # info
            bg_color = "#f8f9fa"
            text_color = "#4a90e2"
            
        header_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
            }}
        """)
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(20, 15, 20, 15)
        
        # Header title with icon
        header_title = QLabel(f"{icon_emoji} {title}")
        header_title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        header_title.setStyleSheet(f"color: {text_color}; background: transparent;")
        header_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(header_title)
        layout.addWidget(header_widget)
        
        # Content area
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 15)
        
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        message_label.setFont(QFont("Arial", 11))
        message_label.setStyleSheet("color: #444444; line-height: 1.4; background: transparent;")
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        content_layout.addWidget(message_label)
        layout.addWidget(content_widget)
        
        # Footer with close button
        footer_widget = QWidget()
        footer_widget.setStyleSheet("""
            QWidget {
                background-color: #f8f9fa;
            }
        """)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(20, 12, 20, 12)
        footer_layout.addStretch()
        
        close_button = QPushButton("OK")
        close_button.clicked.connect(dialog.accept)
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 20px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2968a3;
            }
        """)
        
        footer_layout.addWidget(close_button)
        layout.addWidget(footer_widget)
        
        dialog.exec() 