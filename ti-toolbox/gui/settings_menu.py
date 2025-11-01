#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Settings Menu - Gear icon menu for Help, Acknowledgments, and Contact
"""

from PyQt5 import QtWidgets, QtCore, QtGui


class FloatingHelpWindow(QtWidgets.QDialog):
    """Floating window for Help content."""
    
    def __init__(self, parent=None):
        super(FloatingHelpWindow, self).__init__(parent)
        self.setWindowTitle("TI-Toolbox - Help")
        self.setMinimumSize(800, 600)
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the help window UI."""
        from help_tab import HelpTab
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create the help tab content
        self.help_content = HelpTab(self)
        layout.addWidget(self.help_content)
        
        # Add a close button at the bottom
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
        super(FloatingContactWindow, self).__init__(parent)
        self.setWindowTitle("TI-Toolbox - Contact")
        self.setMinimumSize(700, 500)
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the contact window UI."""
        from contact_tab import ContactTab
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create the contact tab content
        self.contact_content = ContactTab(self)
        layout.addWidget(self.contact_content)
        
        # Add a close button at the bottom
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
        super(FloatingAcknowledgmentsWindow, self).__init__(parent)
        self.setWindowTitle("TI-Toolbox - Acknowledgments")
        self.setMinimumSize(700, 500)
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the acknowledgments window UI."""
        from acknowledgments_tab import AcknowledgmentsTab
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create the acknowledgments tab content
        self.acknowledgments_content = AcknowledgmentsTab(self)
        layout.addWidget(self.acknowledgments_content)
        
        # Add a close button at the bottom
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
        super(SettingsMenuButton, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the gear button and menu."""
        # Set gear icon (using Unicode gear symbol)
        self.setText("⚙")  # Gear emoji/symbol
        self.setStyleSheet("""
            QPushButton {
                font-size: 24px;
                border: none;
                background: transparent;
                padding: 5px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }
            QPushButton::menu-indicator {
                width: 0px;
            }
        """)
        self.setToolTip("Settings and Information")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        
        # Create the dropdown menu
        self.menu = QtWidgets.QMenu(self)
        
        # Add menu actions
        help_action = self.menu.addAction("Help")
        help_action.triggered.connect(self.open_help)
        
        contact_action = self.menu.addAction("Contact")
        contact_action.triggered.connect(self.open_contact)
        
        acknowledgments_action = self.menu.addAction("Acknowledgments")
        acknowledgments_action.triggered.connect(self.open_acknowledgments)
        
        # Set the menu to the button
        self.setMenu(self.menu)
        
    def open_help(self):
        """Open the Help window."""
        help_window = FloatingHelpWindow(self.parent)
        help_window.show()
    
    def open_extensions(self):
        """Open the Extensions window."""
        from extensions import FloatingExtensionsWindow
        extensions_window = FloatingExtensionsWindow(self.parent, main_window=self.parent)
        extensions_window.show()
        
    def open_contact(self):
        """Open the Contact window."""
        contact_window = FloatingContactWindow(self.parent)
        contact_window.show()
        
    def open_acknowledgments(self):
        """Open the Acknowledgments window."""
        acknowledgments_window = FloatingAcknowledgmentsWindow(self.parent)
        acknowledgments_window.show()


class ExtensionsButton(QtWidgets.QPushButton):
    """Extensions icon button for opening extensions window."""
    
    def __init__(self, parent=None):
        super(ExtensionsButton, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
        
    def setup_ui(self):
        """Set up the extensions button."""
        # Set extensions icon (using Unicode symbol compatible with Ubuntu containers)
        self.setText("◳")  # Square with top right quadrant - represents extensions/modules
        self.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: bold;
                border: none;
                background: transparent;
                padding: 5px;
            }
            QPushButton:hover {
                background: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }
        """)
        self.setToolTip("Extensions")
        self.setCursor(QtCore.Qt.PointingHandCursor)
        
        # Connect click to open extensions
        self.clicked.connect(self.open_extensions)
    
    def open_extensions(self):
        """Open the Extensions window."""
        from extensions import FloatingExtensionsWindow
        extensions_window = FloatingExtensionsWindow(self.parent, main_window=self.parent)
        extensions_window.show()

