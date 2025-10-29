#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Extensions Tab for TI-Toolbox GUI
This module provides an interface for managing and launching extensions.
"""

import os
import sys
import importlib.util
from pathlib import Path

from PyQt5 import QtWidgets, QtCore, QtGui


class ExtensionCard(QtWidgets.QGroupBox):
    """Card widget for displaying a single extension."""
    
    def __init__(self, name, description, module_path, parent=None, main_window=None):
        super(ExtensionCard, self).__init__(parent)
        self.name = name
        self.description = description
        self.module_path = module_path
        self.parent = parent
        self.main_window = main_window
        self.extension_widget = None  # Store the extension widget when added as tab
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the extension card UI."""
        self.setTitle(self.name)
        layout = QtWidgets.QHBoxLayout(self)
        
        # Description label
        desc_label = QtWidgets.QLabel(self.description)
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        layout.addWidget(desc_label)
        
        # Launch button
        self.launch_btn = QtWidgets.QPushButton("Launch")
        self.launch_btn.setFixedWidth(100)
        self.launch_btn.clicked.connect(self.launch_extension)
        layout.addWidget(self.launch_btn)
        
        # Add/Remove Tab button (only if main_window is available)
        if self.main_window:
            self.tab_btn = QtWidgets.QPushButton("Add Tab")
            self.tab_btn.setFixedWidth(100)
            self.tab_btn.clicked.connect(self.toggle_tab)
            layout.addWidget(self.tab_btn)
            
            # Update button text based on current state
            self.update_tab_button_state()
    
    def launch_extension(self):
        """Launch the extension by importing and executing its main function."""
        try:
            # Import the extension module dynamically
            spec = importlib.util.spec_from_file_location(
                f"extension_{self.name.replace(' ', '_').lower()}", 
                self.module_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Check if the module has a main() or run() function
            if hasattr(module, 'main'):
                module.main(parent=self.parent)
            elif hasattr(module, 'run'):
                module.run(parent=self.parent)
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Extension Error",
                    f"Extension '{self.name}' does not have a main() or run() function."
                )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Extension Launch Error",
                f"Failed to launch extension '{self.name}':\n\n{str(e)}"
            )
    
    def update_tab_button_state(self):
        """Update the tab button text based on whether extension is in tabs."""
        if not self.main_window or not hasattr(self, 'tab_btn'):
            return
        
        # Check if this extension is currently a tab
        if self.is_extension_in_tabs():
            self.tab_btn.setText("Remove Tab")
        else:
            self.tab_btn.setText("Add Tab")
    
    def is_extension_in_tabs(self):
        """Check if this extension is currently shown as a tab."""
        if not self.main_window:
            return False
        
        # Check all tabs beyond core tabs
        for i in range(self.main_window.core_tab_count, self.main_window.tab_widget.count()):
            if self.main_window.tab_widget.tabText(i) == self.name:
                return True
        return False
    
    def toggle_tab(self):
        """Toggle the extension as a tab in the main window."""
        if self.is_extension_in_tabs():
            self.remove_from_tab()
        else:
            self.add_as_tab()
    
    def add_as_tab(self):
        """Add the extension as a tab in the main window."""
        if not self.main_window:
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot Add Tab",
                "Main window reference not available."
            )
            return
        
        try:
            # Import the extension module dynamically
            spec = importlib.util.spec_from_file_location(
                f"extension_{self.name.replace(' ', '_').lower()}", 
                self.module_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Check if the extension window class exists
            # Look for a class that inherits from QDialog or QWidget
            extension_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, (QtWidgets.QDialog, QtWidgets.QWidget)):
                    # Skip base classes
                    if attr not in (QtWidgets.QDialog, QtWidgets.QWidget):
                        extension_class = attr
                        break
            
            if extension_class:
                # Create the extension widget
                self.extension_widget = extension_class(parent=self.main_window)
                
                # If it's a QDialog, we need to convert it to work as a tab
                # Remove window flags if it's a dialog
                if isinstance(self.extension_widget, QtWidgets.QDialog):
                    self.extension_widget.setWindowFlags(QtCore.Qt.Widget)
                
                # Add it as a tab
                tab_index = self.main_window.tab_widget.addTab(self.extension_widget, self.name)
                
                # Switch to the new tab
                self.main_window.tab_widget.setCurrentIndex(tab_index)
                
                # Save extension state
                self.main_window.save_extension_state(self.name, True)
                
                # Update button state
                self.update_tab_button_state()
            else:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Cannot Add Tab",
                    f"Extension '{self.name}' does not have a compatible window class."
                )
                
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Add Tab Error",
                f"Failed to add extension '{self.name}' as tab:\n\n{str(e)}"
            )
    
    def remove_from_tab(self):
        """Remove the extension from tabs."""
        if not self.main_window:
            return
        
        # Find and remove the tab
        for i in range(self.main_window.core_tab_count, self.main_window.tab_widget.count()):
            if self.main_window.tab_widget.tabText(i) == self.name:
                widget = self.main_window.tab_widget.widget(i)
                self.main_window.tab_widget.removeTab(i)
                if widget:
                    widget.deleteLater()
                
                # Save extension state
                self.main_window.save_extension_state(self.name, False)
                
                # Update button state
                self.update_tab_button_state()
                break


class ExtensionsTab(QtWidgets.QWidget):
    """Extensions tab for TI-Toolbox GUI."""
    
    def __init__(self, parent=None, main_window=None):
        super(ExtensionsTab, self).__init__(parent)
        self.parent = parent
        self.main_window = main_window or parent  # Use parent as main_window if not provided
        self.extensions_dir = Path(__file__).parent / "extentions"
        self.setup_ui()
        self.load_extensions()
    
    def setup_ui(self):
        """Set up the user interface for the extensions tab."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Header
        header_label = QtWidgets.QLabel("<h1>TI-Toolbox Extensions</h1>")
        header_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(header_label)
        
        # Description
        description_label = QtWidgets.QLabel(
            "<p>Extensions are additional tools and utilities that extend the functionality of TI-Toolbox. "
            "Browse the available extensions below and click 'Launch' to run them.</p>"
        )
        description_label.setWordWrap(True)
        description_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(description_label)
        
        # Separator
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        main_layout.addWidget(separator)
        
        # Create scroll area for extensions
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        
        # Container widget for extensions
        self.extensions_container = QtWidgets.QWidget()
        self.extensions_layout = QtWidgets.QVBoxLayout(self.extensions_container)
        self.extensions_layout.setAlignment(QtCore.Qt.AlignTop)
        self.extensions_layout.setSpacing(10)
        
        scroll_area.setWidget(self.extensions_container)
        main_layout.addWidget(scroll_area)
        
        # Refresh button
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        refresh_btn = QtWidgets.QPushButton("Refresh Extensions")
        refresh_btn.clicked.connect(self.refresh_extensions)
        refresh_btn.setMinimumWidth(150)
        button_layout.addWidget(refresh_btn)
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
    
    def load_extensions(self):
        """Load all extensions from the extensions directory."""
        # Clear existing extensions
        while self.extensions_layout.count():
            child = self.extensions_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Check if extensions directory exists
        if not self.extensions_dir.exists():
            no_dir_label = QtWidgets.QLabel(
                "<p style='color: #666; font-style: italic;'>Extensions directory not found.</p>"
            )
            no_dir_label.setAlignment(QtCore.Qt.AlignCenter)
            self.extensions_layout.addWidget(no_dir_label)
            return
        
        # Find all Python files in extensions directory
        extension_files = list(self.extensions_dir.glob("*.py"))
        
        if not extension_files:
            no_extensions_label = QtWidgets.QLabel(
                "<p style='color: #666; font-style: italic;'>No extensions found. "
                "Add Python scripts to the 'gui/extentions/' directory to create extensions.</p>"
            )
            no_extensions_label.setAlignment(QtCore.Qt.AlignCenter)
            self.extensions_layout.addWidget(no_extensions_label)
            return
        
        # Load each extension
        for extension_file in sorted(extension_files):
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
                description = getattr(module, 'EXTENSION_DESCRIPTION', 'No description available.')
                
                # Create extension card with main_window reference
                card = ExtensionCard(name, description, str(extension_file), self.parent, self.main_window)
                self.extensions_layout.addWidget(card)
                
            except Exception as e:
                # Show error card for failed extensions
                error_card = QtWidgets.QGroupBox(f"Error: {extension_file.name}")
                error_layout = QtWidgets.QVBoxLayout(error_card)
                error_label = QtWidgets.QLabel(f"Failed to load extension: {str(e)}")
                error_label.setStyleSheet("color: red;")
                error_layout.addWidget(error_label)
                self.extensions_layout.addWidget(error_card)
    
    def refresh_extensions(self):
        """Refresh the list of available extensions."""
        self.load_extensions()


class FloatingExtensionsWindow(QtWidgets.QDialog):
    """Floating window for Extensions content."""
    
    def __init__(self, parent=None, main_window=None):
        super(FloatingExtensionsWindow, self).__init__(parent)
        self.setWindowTitle("TI-Toolbox - Extensions")
        self.setMinimumSize(800, 600)
        self.setWindowFlag(QtCore.Qt.Window)  # Make it a proper window, not modal
        self.main_window = main_window or parent
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the extensions window UI."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create the extensions tab content with main_window reference
        self.extensions_content = ExtensionsTab(self, main_window=self.main_window)
        layout.addWidget(self.extensions_content)
        
        # Add a close button at the bottom
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)

