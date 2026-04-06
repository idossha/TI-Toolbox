"""Settings and extensions menu buttons for the TI-Toolbox GUI title bar.

Provides the gear icon (``SettingsMenuButton``) for Help/Contact/Acknowledgments
and the extensions icon (``ExtensionsButton``) that opens the extensions panel.
"""

from PyQt5 import QtWidgets, QtCore
from tit.gui.style import ICON_SIZE_GEAR, ICON_SIZE_EXTENSIONS


class FloatingContentWindow(QtWidgets.QDialog):
    """Generic floating dialog that hosts a content widget with a Close button.

    Parameters
    ----------
    parent : QWidget
        Parent widget.
    title : str
        Window title.
    min_size : tuple[int, int]
        Minimum (width, height) in pixels.
    content_class : type
        Widget class to instantiate as the dialog body.
    **content_kwargs
        Extra keyword arguments forwarded to *content_class*.
    """

    def __init__(self, parent, title, min_size, content_class, **content_kwargs):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(*min_size)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.content = content_class(self, **content_kwargs)
        layout.addWidget(self.content)
        # Close button
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)


class SettingsMenuButton(QtWidgets.QPushButton):
    """Gear icon button with a dropdown menu for Help, Contact, and Acknowledgments."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        self.setText("\u2699")
        self.setStyleSheet(f"""
            QPushButton {{
                font-size: {ICON_SIZE_GEAR}px;
                border: none;
                background: transparent;
                padding: 5px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }}
            QPushButton::menu-indicator {{
                width: 0px;
            }}
        """)
        self.setToolTip("Settings and Information")
        self.setCursor(QtCore.Qt.PointingHandCursor)

        self.menu = QtWidgets.QMenu(self)

        help_action = self.menu.addAction("Help")
        help_action.triggered.connect(self.open_help)

        contact_action = self.menu.addAction("Contact")
        contact_action.triggered.connect(self.open_contact)

        acknowledgments_action = self.menu.addAction("Acknowledgments")
        acknowledgments_action.triggered.connect(self.open_acknowledgments)

        self.menu.addSeparator()

        self.privacy_action = self.menu.addAction(self._privacy_label())
        self.privacy_action.triggered.connect(self.toggle_privacy)

        self.setMenu(self.menu)

    # ── Privacy / telemetry toggle ──────────────────────────────────

    @staticmethod
    def _privacy_label() -> str:
        """Return the menu label reflecting the current telemetry state."""
        from tit.telemetry import is_enabled

        state = "✓ Enabled" if is_enabled() else "✗ Disabled"
        return f"Usage Statistics: {state}"

    def toggle_privacy(self):
        """Flip telemetry on/off and update the menu label."""
        from tit.telemetry import is_enabled, set_enabled

        set_enabled(not is_enabled())
        self.privacy_action.setText(self._privacy_label())

    def open_help(self):
        from tit.gui.help_tab import HelpTab

        help_window = FloatingContentWindow(
            self.parent, "TI-Toolbox - Help", (800, 600), HelpTab
        )
        help_window.show()

    def open_extensions(self):
        from tit.gui.extensions import FloatingExtensionsWindow

        extensions_window = FloatingExtensionsWindow(
            self.parent, main_window=self.parent
        )
        extensions_window.show()

    def open_contact(self):
        from tit.gui.contact_tab import ContactTab

        contact_window = FloatingContentWindow(
            self.parent, "TI-Toolbox - Contact", (700, 500), ContactTab
        )
        contact_window.show()

    def open_acknowledgments(self):
        from tit.gui.acknowledgments_tab import AcknowledgmentsTab

        acknowledgments_window = FloatingContentWindow(
            self.parent, "TI-Toolbox - Acknowledgments", (700, 500), AcknowledgmentsTab
        )
        acknowledgments_window.show()


class ExtensionsButton(QtWidgets.QPushButton):
    """Icon button that opens the floating extensions window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        self.setText("\u25f3")
        self.setStyleSheet(f"""
            QPushButton {{
                font-size: {ICON_SIZE_EXTENSIONS}px;
                font-weight: bold;
                border: none;
                background: transparent;
                padding: 5px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }}
        """)
        self.setToolTip("Extensions")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.clicked.connect(self.open_extensions)

    def open_extensions(self):
        from tit.gui.extensions import FloatingExtensionsWindow

        extensions_window = FloatingExtensionsWindow(
            self.parent, main_window=self.parent
        )
        extensions_window.show()
