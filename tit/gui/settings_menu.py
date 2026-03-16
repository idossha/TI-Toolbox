from __future__ import annotations

"""Settings Menu - Gear icon menu for Help, Acknowledgments, and Contact."""

from PyQt5 import QtWidgets, QtCore
from tit.gui.style import ICON_SIZE_GEAR, ICON_SIZE_EXTENSIONS


class FloatingHelpWindow(QtWidgets.QDialog):
    """Floating window for Help content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TI-Toolbox - Help")
        self.setMinimumSize(800, 600)
        self.setup_ui()

    def setup_ui(self):
        from tit.gui.help_tab import HelpTab

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.help_content = HelpTab(self)
        layout.addWidget(self.help_content)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)


class FloatingContactWindow(QtWidgets.QDialog):
    """Floating window for Contact content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TI-Toolbox - Contact")
        self.setMinimumSize(700, 500)
        self.setup_ui()

    def setup_ui(self):
        from tit.gui.contact_tab import ContactTab

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.contact_content = ContactTab(self)
        layout.addWidget(self.contact_content)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)


class FloatingAcknowledgmentsWindow(QtWidgets.QDialog):
    """Floating window for Acknowledgments content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("TI-Toolbox - Acknowledgments")
        self.setMinimumSize(700, 500)
        self.setup_ui()

    def setup_ui(self):
        from tit.gui.acknowledgments_tab import AcknowledgmentsTab

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.acknowledgments_content = AcknowledgmentsTab(self)
        layout.addWidget(self.acknowledgments_content)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)


class SettingsMenuButton(QtWidgets.QPushButton):
    """Gear icon button with dropdown menu for settings/info."""

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

        self.setMenu(self.menu)

    def open_help(self):
        help_window = FloatingHelpWindow(self.parent)
        help_window.show()

    def open_extensions(self):
        from tit.gui.extensions import FloatingExtensionsWindow

        extensions_window = FloatingExtensionsWindow(
            self.parent, main_window=self.parent
        )
        extensions_window.show()

    def open_contact(self):
        contact_window = FloatingContactWindow(self.parent)
        contact_window.show()

    def open_acknowledgments(self):
        acknowledgments_window = FloatingAcknowledgmentsWindow(self.parent)
        acknowledgments_window.show()


class ExtensionsButton(QtWidgets.QPushButton):
    """Extensions icon button for opening extensions window."""

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
