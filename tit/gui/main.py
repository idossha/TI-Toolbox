#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Main window and application entry point for the TI-Toolbox GUI.

Creates the ``QApplication``, assembles all tabs, loads saved extensions,
registers signal handlers for graceful shutdown, and starts the Qt event
loop.  The ``MainWindow`` class owns the tab widget and provides cross-tab
event bridging (e.g. analysis completion refreshing the NIfTI viewer).

See Also
--------
tit.gui.style : Shared design tokens and stylesheet.
tit.gui.extensions : Extension discovery and tab integration.
"""

from PyQt5 import QtWidgets, QtCore, QtGui

import atexit
import os
import signal
import sys
import warnings
from pathlib import Path

from tit.paths import get_path_manager
from tit.gui.style import APP_STYLESHEET
from tit.logger import setup_logging

# Suppress specific SIP deprecation warning originating from PyQt/SIP internals
warnings.filterwarnings(
    "ignore",
    message=r".*sipPyTypeDict.*",
    category=DeprecationWarning,
)


# Ensure a valid XDG runtime directory for Qt on Linux (avoids QStandardPaths warning)
if sys.platform.startswith("linux") and "XDG_RUNTIME_DIR" not in os.environ:
    try:
        runtime_dir = (
            f"/tmp/runtime-{os.getuid()}"
            if hasattr(os, "getuid")
            else f"/tmp/runtime-{os.getpid()}"
        )
        os.makedirs(runtime_dir, exist_ok=True)
        os.chmod(runtime_dir, 0o700)
        os.environ["XDG_RUNTIME_DIR"] = runtime_dir
    except OSError:
        # Fallback: set the env var even if directory ops fail; Qt will still stop warning
        os.environ["XDG_RUNTIME_DIR"] = "/tmp"

from tit import __version__
from tit.gui.simulator_tab import SimulatorTab
from tit.gui.pre_process_tab import PreProcessTab
from tit.gui.system_monitor_tab import SystemMonitorTab
from tit.gui.nifti_viewer_tab import NiftiViewerTab
from tit.gui.analyzer_tab import AnalyzerTab
from tit.gui.optimizer_tab import OptimizerTab
from tit.gui.settings_menu import SettingsMenuButton, ExtensionsButton


class MainWindow(QtWidgets.QMainWindow):
    """Top-level window that hosts all TI-Toolbox tabs.

    Assembles the core tabs (Pre-processing, Optimizer, Simulator,
    Analyzer, NIfTI Viewer, System Monitor), loads user-enabled
    extensions as additional tabs, and wires cross-tab signals such as
    the ``analysis_completed`` bridge between the Analyzer and NIfTI
    Viewer.

    Parameters
    ----------
    None

    Attributes
    ----------
    tab_widget : QTabWidget
        Central tab container.
    pm : PathManager
        Project path resolver singleton.
    core_tab_count : int
        Number of built-in tabs (extensions start after this index).

    See Also
    --------
    tit.gui.settings_menu.SettingsMenuButton : Gear-icon menu (Help / Contact / Ack).
    tit.gui.extensions.ExtensionsTab : Extension discovery panel.
    """

    def __init__(self):
        super(MainWindow, self).__init__()

        self.setWindowTitle(f"TI-Toolbox {__version__}")

        icon_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "docs", "assets", "imgs", "icon.png"
        )
        icon_path = os.path.abspath(icon_path)
        self.setWindowIcon(QtGui.QIcon(icon_path))

        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowMaximizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
        )
        # Allow all window states
        self.setWindowState(QtCore.Qt.WindowNoState)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self.pm = get_path_manager()
        self.extensions_config_path = self.get_extensions_config_path()
        self.ensure_extensions_config()

        self.setup_ui()
        self.load_saved_extensions()
        self.center_on_screen()

        # First-run telemetry consent (non-blocking dialog),
        # then record a gui_launch event.
        from tit.telemetry import consent_prompt_gui, track_event
        from tit import constants as const

        consent_prompt_gui(self)
        track_event(const.TELEMETRY_OP_GUI_LAUNCH)

    def setup_ui(self):
        """Set up the user interface."""
        self.central_widget = QtWidgets.QWidget()
        self.setCentralWidget(self.central_widget)

        main_layout = QtWidgets.QVBoxLayout(self.central_widget)

        self.tab_widget = QtWidgets.QTabWidget()

        buttons_container = QtWidgets.QWidget()
        buttons_layout = QtWidgets.QHBoxLayout(buttons_container)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(0)

        self.extensions_button = ExtensionsButton(self)
        buttons_layout.addWidget(self.extensions_button)

        self.settings_button = SettingsMenuButton(self)
        buttons_layout.addWidget(self.settings_button)

        self.tab_widget.setCornerWidget(buttons_container, QtCore.Qt.TopRightCorner)

        self.pre_process_tab = PreProcessTab(self)
        self.optimizer_tab = OptimizerTab(self)
        self.simulator_tab = SimulatorTab(self)
        self.analyzer_tab = AnalyzerTab(self)
        self.nifti_viewer_tab = NiftiViewerTab(self)
        self.system_monitor_tab = SystemMonitorTab(self)

        self.flex_search_tab = self.optimizer_tab.flex_search_tab
        self.ex_search_tab = self.optimizer_tab.ex_search_tab

        # Analyzer -> Main Window event bridge: when analysis completes,
        # refresh NIfTI viewer and mesh visualization in dependent tabs.
        self.analyzer_tab.analysis_completed.connect(self.on_analysis_completed)
        self._processing_analysis_completion = False

        self.tab_widget.clear()

        self.tab_widget.addTab(self.pre_process_tab, "Pre-processing")
        self.tab_widget.addTab(self.optimizer_tab, "Optimizer")
        self.tab_widget.addTab(self.simulator_tab, "Simulator")
        self.tab_widget.addTab(self.analyzer_tab, "Analyzer")
        self.tab_widget.addTab(self.nifti_viewer_tab, "NIfTI Viewer")
        self.tab_widget.addTab(self.system_monitor_tab, "System Monitor")

        self.tab_widget.setTabsClosable(False)
        self.tab_widget.tabBar().setUsesScrollButtons(True)

        self.core_tab_count = self.tab_widget.count()

        main_layout.addWidget(self.tab_widget)

        from tit.gui.style import WINDOW_WIDTH, WINDOW_HEIGHT

        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumWidth(max(643, int(WINDOW_WIDTH * 0.85)))
        self.center_on_screen()

    def center_on_screen(self):
        """Center the window on the screen where it is currently located (multi-monitor aware)."""
        from PyQt5.QtGui import QGuiApplication

        window_rect = self.frameGeometry()
        center_point = window_rect.center()

        # Try to find the screen containing the window center, fall back to primary.
        screen = QGuiApplication.screenAt(center_point)
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return  # No screen available; nothing we can do.

        screen_geometry = screen.availableGeometry()
        qr = self.frameGeometry()
        qr.moveCenter(screen_geometry.center())
        self.move(qr.topLeft())

    def get_extensions_config_path(self):
        """Get the path to the extensions configuration file."""
        from tit.gui.extensions_config import get_extensions_config_path

        config_dir = Path(self.pm.ensure(self.pm.config_dir()))
        return get_extensions_config_path(config_dir)

    def ensure_extensions_config(self):
        """Ensure the extensions config file exists with default values."""
        from tit.gui.extensions_config import ensure_extensions_config

        ensure_extensions_config(self.extensions_config_path)

    def load_extensions_config(self):
        """Load the extensions configuration from file."""
        from tit.gui.extensions_config import load_extensions_config

        return load_extensions_config(self.extensions_config_path)

    def save_extension_state(self, extension_name, enabled):
        """Save the state of an extension (enabled/disabled as tab)."""
        from tit.gui.extensions_config import save_extension_state

        save_extension_state(self.extensions_config_path, extension_name, enabled)

    def load_saved_extensions(self):
        """Load extensions that were enabled in previous session."""
        config = self.load_extensions_config()
        extensions = config.get("extensions", {})

        extensions_dir = Path(__file__).parent / "extensions"

        import importlib.util

        for extension_name, enabled in extensions.items():
            if not enabled:
                continue

            # Find the extension file
            extension_files = list(extensions_dir.glob("*.py"))
            for extension_file in extension_files:
                # Import the module to get metadata
                spec = importlib.util.spec_from_file_location(
                    extension_file.stem, extension_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Get extension metadata
                name = getattr(
                    module,
                    "EXTENSION_NAME",
                    extension_file.stem.replace("_", " ").title(),
                )

                if name == extension_name:
                    # Find the extension class (prefer QWidget over QDialog)
                    extension_class = None
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if isinstance(attr, type) and issubclass(
                            attr, QtWidgets.QWidget
                        ):
                            if attr not in (
                                QtWidgets.QDialog,
                                QtWidgets.QWidget,
                            ):
                                # Prefer widget classes over dialog classes
                                if extension_class is None or not issubclass(
                                    extension_class, QtWidgets.QDialog
                                ):
                                    extension_class = attr

                    if extension_class:
                        # Create the extension widget
                        extension_widget = extension_class(parent=self)

                        # Add it as a tab
                        self.tab_widget.addTab(extension_widget, name)

    def closeEvent(self, event):
        """Handle window close event."""
        # Allow programmatic forced shutdown without prompting
        if getattr(self, "_force_exit", False):
            self.system_monitor_tab.stop_monitoring()
            event.accept()
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Exit",
            "Are you sure you want to exit?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            # Clean up system monitor thread before closing
            self.system_monitor_tab.stop_monitoring()
            event.accept()
        else:
            event.ignore()

    def set_tab_busy(
        self,
        tab_widget,
        busy=True,
        message="A process is running. Only the Stop button is available.",
        stop_btn=None,
        keep_enabled=None,
    ):
        """Toggle the busy state of a tab, disabling interactive widgets.

        When *busy* is ``True``, all interactive controls inside
        *tab_widget* are disabled except for *stop_btn* and any widgets
        in *keep_enabled*.  A warning label is shown at the top of the
        tab layout.

        Parameters
        ----------
        tab_widget : QWidget
            The tab whose controls should be toggled.
        busy : bool, optional
            ``True`` to enter busy state, ``False`` to restore.
        message : str, optional
            Text shown in the busy-state warning label.
        stop_btn : QPushButton or None, optional
            Button that remains enabled during busy state.
        keep_enabled : QWidget or list[QWidget] or None, optional
            Additional widgets to keep enabled.
        """
        interactive_types = (
            QtWidgets.QPushButton,
            QtWidgets.QLineEdit,
            QtWidgets.QComboBox,
            QtWidgets.QCheckBox,
            QtWidgets.QListWidget,
            QtWidgets.QRadioButton,
            QtWidgets.QSpinBox,
            QtWidgets.QDoubleSpinBox,
            QtWidgets.QTextEdit,
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
        if not hasattr(tab_widget, "_busy_message_label"):
            msg_label = QtWidgets.QLabel(tab_widget)
            msg_label.setStyleSheet(
                "color: #d9534f; font-size: 10pt; font-weight: bold; padding: 4px 0 4px 0;"
            )
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
            if hasattr(tab, "_busy_overlay"):
                tab._busy_overlay.setGeometry(tab.rect())
        # Also check the sub-tabs within optimize_tab
        for sub_tab in [
            self.optimizer_tab.flex_search_tab,
            self.optimizer_tab.ex_search_tab,
        ]:
            if hasattr(sub_tab, "_busy_overlay"):
                sub_tab._busy_overlay.setGeometry(sub_tab.rect())
        super().resizeEvent(event)
        # Optionally, keep window centered after resize (uncomment if desired):
        # self.center_on_screen()

    def on_analysis_completed(self, subject_id, simulation_name, analysis_type):
        """Refresh dependent tabs after an analysis run completes.

        Parameters
        ----------
        subject_id : str
            Subject identifier (without ``sub-`` prefix).
        simulation_name : str
            Name of the simulation whose analysis just finished.
        analysis_type : str
            ``"Voxel"`` or ``"Mesh"`` -- determines which viewer to refresh.
        """
        # Guard against recursive calls
        if self._processing_analysis_completion:
            return

        self._processing_analysis_completion = True
        try:
            # Update NIFTI viewer's analysis regions if it's a voxel analysis
            if analysis_type == "Voxel":
                # Update the NIFTI viewer's subject and simulation selection
                self.nifti_viewer_tab.subject_combo.setCurrentText(subject_id)
                self.nifti_viewer_tab.sim_combo.setCurrentText(simulation_name)
                # Update available analyses for the current subject and simulation
                self.nifti_viewer_tab.update_available_analyses()

            # Update mesh files list if it's a mesh analysis
            if analysis_type == "Mesh":
                # Update the mesh files list in the analyzer tab and refresh gmsh visualization
                self.analyzer_tab.update_field_files(subject_id, simulation_name)
        finally:
            self._processing_analysis_completion = False


def check_for_update(current_version, parent_window=None):
    """Check GitHub for a newer release and show a notification dialog.

    Parameters
    ----------
    current_version : str
        The running version string (e.g. ``"2.2.3"``).
    parent_window : QWidget, optional
        Parent for the notification dialog (centered relative to it).
    """
    from tit.tools.check_for_update import check_for_new_version

    try:
        latest_version = check_for_new_version(current_version)
        if not latest_version:
            return
    except Exception:
        return

    # Show update notification dialog
    msg_box = QtWidgets.QMessageBox(parent_window)
    msg_box.setIcon(QtWidgets.QMessageBox.Information)
    msg_box.setWindowTitle("Update Available")
    msg_box.setText("A new version of TI-Toolbox is available!")
    msg_box.setInformativeText(
        f"Current version: {current_version}\n"
        f"Latest version: {latest_version}\n\n"
        f"Visit:\nhttps://github.com/idossha/TI-Toolbox/releases"
    )
    msg_box.setWindowModality(QtCore.Qt.ApplicationModal)
    # Center the dialog relative to the main window
    if parent_window:
        main_rect = parent_window.geometry()
        dialog_size = msg_box.sizeHint()
        x = main_rect.x() + (main_rect.width() - dialog_size.width()) // 2
        y = main_rect.y() + (main_rect.height() - dialog_size.height()) // 2
        msg_box.move(x, y)
    msg_box.exec_()


def main():
    """Main entry point for the application."""
    setup_logging(level=os.environ.get("TI_LOG_LEVEL", "INFO"))

    # Enable HiDPI scaling BEFORE creating QApplication (Qt5 hard requirement).
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication(sys.argv)

    # Set application style and apply shared design tokens.
    # _NarrowSpinStyle wraps Fusion and narrows spinbox button columns without
    # breaking native arrow rendering (CSS ::up-button overrides suppress glyphs).
    from tit.gui.style import build_stylesheet, _NarrowSpinStyle

    app.setStyle(_NarrowSpinStyle("fusion"))
    app.setStyleSheet(build_stylesheet())

    # Set application icon if available
    icon_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "docs", "assets", "imgs", "icon.png"
    )
    icon_path = os.path.abspath(icon_path)
    if os.path.exists(icon_path):
        app.setWindowIcon(QtGui.QIcon(icon_path))

    # Set up the main window
    window = MainWindow()
    window.show()
    # Inform the launcher that the GUI is now running (after event loop starts)
    QtCore.QTimer.singleShot(
        0, lambda: print("\033[0;32mRunning TI-Toolbox GUI...\033[0m")
    )

    # Ensure we close the window and quit cleanly on termination signals (e.g., Ctrl+C / Ctrl+Z / SIGTERM)
    def request_graceful_shutdown():
        def _quit():
            try:
                # Prevent confirmation dialog on forced shutdown
                setattr(window, "_force_exit", True)
                if window.isVisible():
                    window.close()
            except RuntimeError:
                pass  # Qt objects may already be destroyed
            app.quit()

        QtCore.QTimer.singleShot(0, _quit)

    def _signal_handler(signum, frame):
        print("\033[0;31mClosing TI-Toolbox GUI...\033[0m")
        request_graceful_shutdown()

    # Register common termination signals
    for sig in (
        getattr(signal, "SIGINT", None),
        getattr(signal, "SIGTERM", None),
        getattr(signal, "SIGBREAK", None),  # Windows Ctrl+Break
    ):
        if sig is not None:
            signal.signal(sig, _signal_handler)
    # Handle Ctrl+Z (SIGTSTP) when available to close instead of suspending the GUI
    sigtstp = getattr(signal, "SIGTSTP", None)
    if sigtstp is not None:
        signal.signal(sigtstp, _signal_handler)

    # Best-effort cleanup on normal interpreter exit
    def _atexit():
        setattr(window, "_force_exit", True)
        window.close()

    atexit.register(_atexit)

    # Heartbeat timer to ensure Python processes signals while Qt event loop is running
    sig_timer = QtCore.QTimer()
    sig_timer.setInterval(250)
    sig_timer.timeout.connect(lambda: None)
    sig_timer.start()
    # Keep reference to avoid garbage collection
    app._signal_heartbeat_timer = sig_timer

    # Check if this is a first-time user after a short delay
    from tit.project_init.first_time_user import assess_user_status

    QtCore.QTimer.singleShot(500, lambda: assess_user_status(window))

    # Check for updates after a short delay to ensure window is fully shown
    QtCore.QTimer.singleShot(1000, lambda: check_for_update(__version__, window))

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
