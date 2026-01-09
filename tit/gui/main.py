#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox GUI Main Entry Point
This module provides a GUI interface for the TI-Toolbox toolbox.
"""

import requests
from PyQt5 import QtWidgets, QtCore, QtGui

import atexit
import json
import os
import signal
import subprocess
import sys
import warnings
from pathlib import Path

# Suppress specific SIP deprecation warning originating from PyQt/SIP internals
warnings.filterwarnings(
    'ignore',
    message=r'.*sipPyTypeDict.*',
    category=DeprecationWarning,
)

# Ensure a valid XDG runtime directory for Qt on Linux (avoids QStandardPaths warning)
if sys.platform.startswith('linux') and 'XDG_RUNTIME_DIR' not in os.environ:
    try:
        runtime_dir = f"/tmp/runtime-{os.getuid()}" if hasattr(os, 'getuid') else f"/tmp/runtime-{os.getpid()}"
        os.makedirs(runtime_dir, exist_ok=True)
        os.chmod(runtime_dir, 0o700)
        os.environ['XDG_RUNTIME_DIR'] = runtime_dir
    except Exception:
        # Fallback: set the env var even if directory ops fail; Qt will still stop warning
        os.environ['XDG_RUNTIME_DIR'] = '/tmp'

from tit import __version__

# Import tool-specific modules
from tit.gui.simulator_tab import SimulatorTab
from tit.gui.pre_process_tab import PreProcessTab
from tit.gui.system_monitor_tab import SystemMonitorTab
from tit.gui.nifti_viewer_tab import NiftiViewerTab
from tit.gui.analyzer_tab import AnalyzerTab
from tit.gui.optimizer_tab import OptimizerTab
from tit.gui.settings_menu import SettingsMenuButton, ExtensionsButton
from tit.core import get_path_manager

class MainWindow(QtWidgets.QMainWindow):
    """Main window for the TI-Toolbox GUI."""
    
    def __init__(self):
        super(MainWindow, self).__init__()
        
        self.setWindowTitle("TI-Toolbox")
        
        # Set window icon if available
        icon_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'assets', 'imgs', 'icon.png')
        icon_path = os.path.abspath(icon_path)
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        
        # Set window flags to ensure proper window behavior
        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )
        # Allow all window states
        self.setWindowState(QtCore.Qt.WindowNoState)
        # Enable resizing
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        
        # Initialize path manager and extension config
        self.pm = get_path_manager()
        self.extensions_config_path = self.get_extensions_config_path()
        self.ensure_extensions_config()
        
        self.setup_ui()
        # Load saved extensions after UI is set up
        self.load_saved_extensions()
        # Always center on screen after setup
        self.center_on_screen()
        
    def setup_ui(self):
        """Set up the user interface."""
        # Central widget and layout
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)
        
        main_layout = QtWidgets.QVBoxLayout(self.central_widget)
        
        # Create the tab widget for different tools
        self.tab_widget = QtWidgets.QTabWidget()
        
        # Create a container widget for both buttons in the top right corner
        buttons_container = QtWidgets.QWidget()
        buttons_layout = QtWidgets.QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(0)
        
        # Add the extensions button
        self.extensions_button = ExtensionsButton(self)
        buttons_layout.addWidget(self.extensions_button)
        
        # Add the settings gear button
        self.settings_button = SettingsMenuButton(self)
        buttons_layout.addWidget(self.settings_button)
        
        # Add the container with both buttons to the right corner of the tab bar
        self.tab_widget.setCornerWidget(buttons_container, QtCore.Qt.TopRightCorner)
        
        # Create all tabs first
        self.pre_process_tab = PreProcessTab(self)
        self.optimizer_tab = OptimizerTab(self)
        self.simulator_tab = SimulatorTab(self)
        self.analyzer_tab = AnalyzerTab(self)
        self.nifti_viewer_tab = NiftiViewerTab(self)
        self.system_monitor_tab = SystemMonitorTab(self)

        # Create aliases for backward compatibility - access to individual optimization tabs
        self.flex_search_tab = self.optimizer_tab.flex_search_tab
        self.ex_search_tab = self.optimizer_tab.ex_search_tab

        # Connect analyzer tab signals
        self.analyzer_tab.analysis_completed.connect(self.on_analysis_completed)
        
        # Clear the tab widget in case we're reordering tabs
        self.tab_widget.clear()
        
        # Add all functional tabs
        self.tab_widget.addTab(self.pre_process_tab, "Pre-processing")
        self.tab_widget.addTab(self.optimizer_tab, "Optimizer")
        self.tab_widget.addTab(self.simulator_tab, "Simulator")
        self.tab_widget.addTab(self.analyzer_tab, "Analyzer")
        self.tab_widget.addTab(self.nifti_viewer_tab, "NIfTI Viewer")
        self.tab_widget.addTab(self.system_monitor_tab, "System Monitor")
        
        # Note: Help, Contact, and Acknowledgments are now accessible via the settings gear icon
        
        # Set the tab bar without close buttons
        self.tab_widget.setTabsClosable(False)
        
        # Track the core tabs (non-closable tabs)
        self.core_tab_count = self.tab_widget.count()
        
        main_layout.addWidget(self.tab_widget)
        
        # Set window properties and center on screen
        self.resize(1000, 800)
        self.setMinimumWidth(1050)  # 1000 * 1.05 = 1050
        self.center_on_screen()
        
    def center_on_screen(self):
        """Center the window on the screen where the window is (multi-monitor aware, modern approach)."""
        app = QtWidgets.QApplication.instance()
        # Use QGuiApplication for modern screen handling
        from PyQt5.QtGui import QGuiApplication
        window_rect = self.frameGeometry()
        center_point = window_rect.center()
        screen = None
        if hasattr(QGuiApplication, 'screenAt'):
            screen = QGuiApplication.screenAt(center_point)
        if screen is None:
            # Fallback: use primary screen
            screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
        else:
            screen_geometry = app.desktop().screenGeometry()
        qr = self.frameGeometry()
        qr.moveCenter(screen_geometry.center())
        self.move(qr.topLeft())
    
    def get_extensions_config_path(self):
        """Get the path to the extensions configuration file."""
        project_dir = self.pm.project_dir
        
        # Path: /mnt/project_dir/code/tit/config/extensions.json
        config_path = Path(project_dir) / 'code' / 'ti-toolbox' / 'config' / 'extensions.json'
        
        # Ensure the directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        return config_path
    
    def ensure_extensions_config(self):
        """Ensure the extensions config file exists with default values."""
        if not self.extensions_config_path.exists():
            # Create default config with all extensions disabled
            default_config = {
                "extensions": {}
            }
            try:
                with open(self.extensions_config_path, 'w') as f:
                    json.dump(default_config, f, indent=2)
            except Exception as e:
                print(f"Warning: Could not create extensions config: {e}")
    
    def load_extensions_config(self):
        """Load the extensions configuration from file."""
        try:
            if self.extensions_config_path.exists():
                with open(self.extensions_config_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load extensions config: {e}")
        
        return {"extensions": {}}
    
    def save_extension_state(self, extension_name, enabled):
        """Save the state of an extension (enabled/disabled as tab)."""
        try:
            config = self.load_extensions_config()
            config["extensions"][extension_name] = enabled
            
            with open(self.extensions_config_path, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save extension state: {e}")
    
    def load_saved_extensions(self):
        """Load extensions that were enabled in previous session."""
        try:
            config = self.load_extensions_config()
            extensions = config.get("extensions", {})
            
            # Find the extensions directory
            extensions_dir = Path(__file__).parent / "extensions"
            if not extensions_dir.exists():
                return
            
            # Import necessary modules
            import importlib.util
            
            # Load each enabled extension
            for extension_name, enabled in extensions.items():
                if not enabled:
                    continue
                
                # Find the extension file
                extension_files = list(extensions_dir.glob("*.py"))
                for extension_file in extension_files:
                    try:
                        # Import the module to get metadata
                        spec = importlib.util.spec_from_file_location(
                            extension_file.stem, 
                            extension_file
                        )
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        # Get extension metadata
                        name = getattr(module, 'EXTENSION_NAME', extension_file.stem.replace('_', ' ').title())
                        
                        if name == extension_name:
                            # Find the extension class (prefer QWidget over QDialog)
                            extension_class = None
                            for attr_name in dir(module):
                                attr = getattr(module, attr_name)
                                if isinstance(attr, type) and issubclass(attr, QtWidgets.QWidget):
                                    if attr not in (QtWidgets.QDialog, QtWidgets.QWidget):
                                        # Prefer widget classes over dialog classes
                                        if extension_class is None or not issubclass(extension_class, QtWidgets.QDialog):
                                            extension_class = attr
                            
                            if extension_class:
                                # Create the extension widget
                                extension_widget = extension_class(parent=self)

                                # Add it as a tab
                                self.tab_widget.addTab(extension_widget, name)
                            
                            break
                    except Exception as e:
                        print(f"Warning: Could not load extension {extension_name}: {e}")
        
        except Exception as e:
            print(f"Warning: Could not load saved extensions: {e}")

    def closeEvent(self, event):
        """Handle window close event."""
        # Allow programmatic forced shutdown without prompting
        if getattr(self, '_force_exit', False):
            if hasattr(self, 'system_monitor_tab'):
                self.system_monitor_tab.stop_monitoring()
            event.accept()
            return
        reply = QtWidgets.QMessageBox.question(
            self, 'Confirm Exit',
            "Are you sure you want to exit?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # Clean up system monitor thread before closing
            if hasattr(self, 'system_monitor_tab'):
                self.system_monitor_tab.stop_monitoring()
            event.accept()
        else:
            event.ignore()

    def set_tab_busy(self, tab_widget, busy=True, message="A process is running. Only the Stop button is available.", stop_btn=None, keep_enabled=None):
        """Disable all interactive widgets in the given tab except the provided stop button, and show a message at the top of the tab."""
        interactive_types = (
            QtWidgets.QPushButton, QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QCheckBox,
            QtWidgets.QListWidget, QtWidgets.QRadioButton, QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox,
            QtWidgets.QTextEdit
        )
        # Convert keep_enabled to list if it's a single widget
        if keep_enabled is not None and not isinstance(keep_enabled, (list, tuple)):
            keep_enabled = [keep_enabled]
        
        for widget in tab_widget.findChildren(QtWidgets.QWidget):
            if stop_btn is not None and widget is stop_btn:
                continue
            # Keep specified widgets enabled
            if keep_enabled and widget in keep_enabled:
                continue
            # Don't disable output consoles (QTextEdit widgets that are read-only)
            if isinstance(widget, QtWidgets.QTextEdit) and widget.isReadOnly():
                continue
            if isinstance(widget, interactive_types):
                widget.setEnabled(not busy)
        if stop_btn is not None:
            stop_btn.setEnabled(busy)
        # Show/hide message at the top
        if not hasattr(tab_widget, '_busy_message_label'):
            msg_label = QtWidgets.QLabel(tab_widget)
            msg_label.setStyleSheet("color: #d9534f; font-size: 14px; font-weight: bold; padding: 4px 0 4px 0;")
            msg_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
            msg_label.hide()
            tab_widget._busy_message_label = msg_label
            # Insert at the top of the main layout if possible
            layout = tab_widget.layout()
            if layout is not None:
                layout.insertWidget(0, msg_label)
        msg_label = tab_widget._busy_message_label
        msg_label.setText(message if busy else "")
        msg_label.setVisible(busy)

    def showEvent(self, event):
        super().showEvent(event)
        self.center_on_screen()

    def resizeEvent(self, event):
        # Ensure overlays resize with the window
        for tab in [self.pre_process_tab, self.simulator_tab, self.optimizer_tab]:
            if hasattr(tab, '_busy_overlay'):
                tab._busy_overlay.setGeometry(tab.rect())
        # Also check the sub-tabs within optimize_tab
        if hasattr(self, 'optimizer_tab'):
            for sub_tab in [self.optimizer_tab.flex_search_tab, self.optimizer_tab.ex_search_tab]:
                if hasattr(sub_tab, '_busy_overlay'):
                    sub_tab._busy_overlay.setGeometry(sub_tab.rect())
        super().resizeEvent(event)
        # Optionally, keep window centered after resize (uncomment if desired):
        # self.center_on_screen()

    def on_analysis_completed(self, subject_id, simulation_name, analysis_type):
        """Handle analysis completion by updating relevant tabs."""
        # Guard against recursive calls
        if hasattr(self, '_processing_analysis_completion') and self._processing_analysis_completion:
            return
        
        self._processing_analysis_completion = True
        try:
            # Update NIFTI viewer's analysis regions if it's a voxel analysis
            if analysis_type == 'Voxel':
                # Update the NIFTI viewer's subject and simulation selection
                self.nifti_viewer_tab.subject_combo.setCurrentText(subject_id)
                self.nifti_viewer_tab.sim_combo.setCurrentText(simulation_name)
                # Update available analyses for the current subject and simulation
                self.nifti_viewer_tab.update_available_analyses()
                
            # Update mesh files list if it's a mesh analysis
            if analysis_type == 'Mesh':
                # Update the mesh files list in the analyzer tab and refresh gmsh visualization
                self.analyzer_tab.update_field_files(subject_id, simulation_name)
        finally:
            self._processing_analysis_completion = False

def parse_version(version_str):
    """Parse a version string into a tuple of integers for comparison. Non-integer parts are ignored."""
    parts = version_str.strip().split('.')
    version_tuple = []
    for part in parts:
        try:
            version_tuple.append(int(part))
        except ValueError:
            # Ignore non-integer parts (e.g., 'rc', 'beta')
            break
    return tuple(version_tuple)

def check_for_update(current_version, parent_window=None):
    """Check for updates and show a notification dialog if a newer version is available.

    Args:
        current_version (str): The current version of the application
        parent_window (QWidget, optional): The parent window to center the dialog on
    """
    try:
        url = "https://api.github.com/repos/idossha/TI-Toolbox/releases/latest"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            release_data = response.json()
            latest_version = release_data.get('tag_name', '').lstrip('v')  # Remove 'v' prefix if present
            if latest_version:
                # Only prompt if remote version is strictly newer
                if parse_version(latest_version) > parse_version(current_version):
                    msg_box = QtWidgets.QMessageBox(parent_window)
                    msg_box.setIcon(QtWidgets.QMessageBox.Information)
                    msg_box.setWindowTitle("Update Available")
                    msg_box.setText(f"A new version of TI-Toolbox is available!")
                    msg_box.setInformativeText(
                        f"Current version: {current_version}\n"
                        f"Latest version: {latest_version}\n\n"
                        f"Visit:\nhttps://github.com/idossha/TI-Toolbox/releases"
                    )
                    msg_box.setWindowModality(QtCore.Qt.ApplicationModal)
                    # Center the dialog relative to the main window
                    if parent_window:
                        # Get the main window's geometry
                        main_rect = parent_window.geometry()
                        # Get the dialog's size
                        dialog_size = msg_box.sizeHint()
                        # Calculate the center position
                        x = main_rect.x() + (main_rect.width() - dialog_size.width()) // 2
                        y = main_rect.y() + (main_rect.height() - dialog_size.height()) // 2
                        # Move the dialog to the center
                        msg_box.move(x, y)
                    msg_box.exec_()
    except Exception as e:
        print(f"Error checking for updates: {e}")  # Print to console for debugging
        pass  # Continue execution

def main():
    """Main entry point for the application."""
    app = QtWidgets.QApplication(sys.argv)
    
    # Set application style
    app.setStyle("Fusion")
    
    # Set application icon if available
    icon_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'assets', 'imgs', 'icon.png')
    icon_path = os.path.abspath(icon_path)
    if os.path.exists(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))
    
    # Set up the main window
    window = MainWindow()
    window.show()
    # Inform the launcher that the GUI is now running (after event loop starts)
    QtCore.QTimer.singleShot(0, lambda: print("\033[0;32mRunning TI-Toolbox GUI...\033[0m"))

    # Ensure we close the window and quit cleanly on termination signals (e.g., Ctrl+C / Ctrl+Z / SIGTERM)
    def request_graceful_shutdown():
        def _quit():
            try:
                # Prevent confirmation dialog on forced shutdown
                setattr(window, '_force_exit', True)
                if window.isVisible():
                    window.close()
            except Exception:
                pass
            app.quit()
        QtCore.QTimer.singleShot(0, _quit)

    def _signal_handler(signum, frame):
        try:
            print("\033[0;31mClosing TI-Toolbox GUI...\033[0m")
        except Exception:
            pass
        request_graceful_shutdown()

    # Register common termination signals
    for sig in (
        getattr(signal, 'SIGINT', None),
        getattr(signal, 'SIGTERM', None),
        getattr(signal, 'SIGBREAK', None),  # Windows Ctrl+Break
    ):
        if sig is not None:
            try:
                signal.signal(sig, _signal_handler)
            except Exception:
                pass
    # Handle Ctrl+Z (SIGTSTP) when available to close instead of suspending the GUI
    sigtstp = getattr(signal, 'SIGTSTP', None)
    if sigtstp is not None:
        try:
            signal.signal(sigtstp, _signal_handler)
        except Exception:
            pass

    # Best-effort cleanup on normal interpreter exit
    def _atexit():
        try:
            setattr(window, '_force_exit', True)
            if hasattr(window, 'close'):
                window.close()
        except Exception:
            pass
    atexit.register(_atexit)

    # Heartbeat timer to ensure Python processes signals while Qt event loop is running
    sig_timer = QtCore.QTimer()
    sig_timer.setInterval(250)
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start()
    # Keep reference to avoid garbage collection
    app._signal_heartbeat_timer = sig_timer
    
    # Check if this is a first-time user after a short delay
    from tit.new_project.first_time_user import assess_user_status
    QtCore.QTimer.singleShot(500, lambda: assess_user_status(window))
    
    # Check for updates after a short delay to ensure window is fully shown
    QtCore.QTimer.singleShot(1000, lambda: check_for_update(__version__, window))
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 
