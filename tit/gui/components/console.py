#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Console Widget Component
Reusable console output widget with associated controls for TI-Toolbox GUI
"""

import re
from PyQt5 import QtWidgets, QtCore

# Utility: strip ANSI/VT100 escape sequences from text (e.g., "\x1b[0;32m")
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color/control sequences from a string."""
    if not text:
        return text
    # Remove standard CSI sequences
    cleaned = ANSI_ESCAPE_PATTERN.sub("", text)
    # Remove any stray ESC characters that might remain
    cleaned = cleaned.replace("\x1b", "")
    return cleaned


class ConsoleWidget(QtWidgets.QWidget):
    """
    Reusable console widget with output display and optional controls.

    Features:
    - Dark-themed console output (QTextEdit)
    - Optional Clear Console button
    - Optional Debug Mode checkbox
    - Auto-scrolling when user is at bottom
    - Colored output based on message type
    - ANSI escape sequence handling
    """

    def __init__(
        self,
        parent=None,
        show_clear_button=True,
        show_debug_checkbox=True,
        console_label="Output:",
        min_height=200,
        max_height=None,
        custom_buttons=None,
    ):
        """
        Initialize the console widget.

        Args:
            parent: Parent widget
            show_clear_button: Whether to show the Clear Console button
            show_debug_checkbox: Whether to show the Debug Mode checkbox
            console_label: Label text for the console (None to hide)
            min_height: Minimum height of the console in pixels
            max_height: Maximum height of the console in pixels (None for unlimited)
            custom_buttons: List of custom QPushButton widgets to add before Clear button (optional)
        """
        super(ConsoleWidget, self).__init__(parent)
        self.parent = parent
        self.debug_mode = False

        # Use GraphicsConfig minimum height when the caller leaves min_height
        # at its default sentinel value of 200.
        from tit.gui.graphics_config import get_graphics_config as _get_gfx
        _gfx = _get_gfx()
        if min_height == 200:   # default sentinel
            min_height = _gfx.console_min_height

        # Store configuration
        self.show_clear_button = show_clear_button
        self.show_debug_checkbox = show_debug_checkbox
        self.console_label = console_label
        self.min_height = min_height
        self.max_height = max_height
        self.custom_buttons = custom_buttons or []

        self.setup_ui()

        # Apply a minimum height so the console is always usable.
        # No maximum height is set — the console grows freely with the window.
        if self.min_height:
            self.setMinimumHeight(self.min_height)

    def setup_ui(self):
        """Set up the console UI components."""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header layout for label and controls
        header_layout = QtWidgets.QHBoxLayout()

        # Console label
        if self.console_label:
            label = QtWidgets.QLabel(self.console_label)
            label.setStyleSheet("font-weight: bold; margin-top: 8px;")
            header_layout.addWidget(label)

        # Add stretch to push buttons to the right
        header_layout.addStretch()

        # Add custom buttons first (e.g., Run, Stop buttons)
        for button in self.custom_buttons:
            header_layout.addWidget(button)

        # Clear button
        if self.show_clear_button:
            self.clear_btn = QtWidgets.QPushButton("Clear Console")
            self.clear_btn.clicked.connect(self.clear_console)
            # Subtle dark style so it visually belongs to the console area.
            self.clear_btn.setStyleSheet(
                "QPushButton { background-color: #555; color: white; border-color: #444; }"
                " QPushButton:hover { background-color: #666; }"
            )
            header_layout.addWidget(self.clear_btn)

        # Debug mode checkbox
        if self.show_debug_checkbox:
            self.debug_checkbox = QtWidgets.QCheckBox("Debug Mode")
            self.debug_checkbox.setChecked(self.debug_mode)
            self.debug_checkbox.setToolTip(
                "Toggle debug mode:\n"
                "• ON: Show all detailed logging information\n"
                "• OFF: Show only key operational steps"
            )
            self.debug_checkbox.toggled.connect(self.toggle_debug_mode)
            self.debug_checkbox.setStyleSheet(
                "QCheckBox { font-weight: bold; margin-left: 8px; }"
                " QCheckBox::indicator:unchecked { border: 2px solid #cccccc;"
                "  background-color: white; border-radius: 3px; }"
                " QCheckBox::indicator:checked  { border: 2px solid #4CAF50;"
                "  background-color: #4CAF50; border-radius: 3px; }"
            )
            header_layout.addWidget(self.debug_checkbox)

        layout.addLayout(header_layout)

        # Console output with dark theme.
        # Height constraints are applied to the outer ConsoleWidget (self),
        # not to this QTextEdit, so the dark area always fills the wrapper.
        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)
        self.console.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.console.setStyleSheet(
            """
            QTextEdit {
                background-color: #1e1e1e;
                color: #f0f0f0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 5pt;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                padding: 8px;
            }
        """
        )
        self.console.setAcceptRichText(True)
        # stretch=1 ensures the QTextEdit fills all remaining vertical space
        # within whatever height the outer ConsoleWidget is given.
        layout.addWidget(self.console, 1)

    def toggle_debug_mode(self):
        """Toggle debug mode for verbose output."""
        self.debug_mode = self.debug_checkbox.isChecked()
        if self.debug_mode:
            self.update_console("Debug mode enabled - showing all messages", "info")
        else:
            self.update_console(
                "Debug mode disabled - showing important messages only", "info"
            )

    def clear_console(self):
        """Clear the console output."""
        self.console.clear()

    def update_console(self, text, message_type="default"):
        """
        Update the console output with colored text.

        Args:
            text: Text to append to console
            message_type: Type of message for color formatting
                         Options: 'default', 'error', 'warning', 'debug',
                                 'command', 'success', 'info'
        """
        if not text.strip():
            return

        # Strip ANSI escape sequences before any formatting
        text = strip_ansi_codes(text)

        # Filter verbose messages if not in debug mode
        if not self.debug_mode and message_type == "debug":
            return

        # Format the output based on message type
        if message_type == "error":
            formatted_text = f'<span style="color: #ff5555;"><b>{text}</b></span>'
        elif message_type == "warning":
            formatted_text = f'<span style="color: #ffff55;">{text}</span>'
        elif message_type == "debug":
            formatted_text = f'<span style="color: #7f7f7f;">{text}</span>'
        elif message_type == "command":
            formatted_text = f'<span style="color: #55aaff;">{text}</span>'
        elif message_type == "success":
            formatted_text = f'<span style="color: #55ff55;"><b>{text}</b></span>'
        elif message_type == "info":
            formatted_text = f'<span style="color: #55ffff;">{text}</span>'
        else:
            # Default white text
            formatted_text = f'<span style="color: #ffffff;">{text}</span>'

        # Snapshot scrollbar state before append.
        # QTextEdit.append() internally moves the cursor to the end which can
        # cause an unsolicited scroll even when the user has scrolled up.
        # Explicitly restoring the position afterward is the only reliable fix.
        scrollbar = self.console.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
        saved_value = scrollbar.value()

        # Append to the console with HTML formatting
        self.console.append(formatted_text)

        # Sticky-scroll: if user was at the bottom, follow new content.
        # Otherwise, restore the exact position they were at.
        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(saved_value)

    def append_html(self, html_text):
        """
        Append raw HTML to the console (for custom formatted messages).

        Args:
            html_text: HTML formatted text to append
        """
        scrollbar = self.console.verticalScrollBar()
        at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
        saved_value = scrollbar.value()

        self.console.append(html_text)

        if at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(saved_value)

        QtWidgets.QApplication.processEvents()

    def get_console_widget(self):
        """Return the underlying QTextEdit console widget."""
        return self.console

    def is_debug_mode(self):
        """Return whether debug mode is currently enabled."""
        return self.debug_mode

    def set_debug_mode(self, enabled):
        """Programmatically set debug mode."""
        self.debug_mode = enabled
        if self.show_debug_checkbox:
            self.debug_checkbox.setChecked(enabled)
