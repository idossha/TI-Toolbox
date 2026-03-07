#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Console Widget Component
Reusable console output widget with associated controls for TI-Toolbox GUI
"""

from PyQt5 import QtWidgets, QtCore

from tit.gui.utils import strip_ansi_codes

_COLOR_MAP = {
    "error": ("#ff5555", True),  # (color, bold)
    "warning": ("#ffff55", False),
    "debug": ("#7f7f7f", False),
    "command": ("#55aaff", False),
    "success": ("#55ff55", True),
    "info": ("#55ffff", False),
    "default": ("#ffffff", False),
}


def format_message(text: str, message_type: str = "default") -> str:
    """
    Return an HTML-formatted string with color based on message_type.

    Args:
        text: The text to format (may contain HTML entities / <br> already).
        message_type: One of 'error', 'warning', 'debug', 'command',
                      'success', 'info', or 'default'.

    Returns:
        An HTML ``<span>`` string with the appropriate color and optional bold.
    """
    color, bold = _COLOR_MAP.get(message_type, _COLOR_MAP["default"])
    if bold:
        return f'<span style="color: {color};"><b>{text}</b></span>'
    return f'<span style="color: {color};">{text}</span>'


def append_with_autoscroll(text_edit, html_text: str, process_events: bool = True):
    """
    Append *html_text* to a QTextEdit while preserving the user's scroll position.

    If the scrollbar was near the bottom before the append, the view follows
    the new content.  Otherwise the current position is kept.

    Args:
        text_edit: A QTextEdit (or compatible) widget.
        html_text: Pre-formatted HTML to append.
        process_events: Whether to call ``QApplication.processEvents()``
                        after the append (default True).
    """
    scrollbar = text_edit.verticalScrollBar()
    at_bottom = scrollbar.value() >= scrollbar.maximum() - 5
    saved_value = scrollbar.value()

    text_edit.append(html_text)

    if at_bottom:
        scrollbar.setValue(scrollbar.maximum())
    else:
        scrollbar.setValue(saved_value)

    if process_events:
        QtWidgets.QApplication.processEvents()


class ConsoleWidget(QtWidgets.QWidget):
    """
    Reusable console widget with output display and optional controls.

    Features:
    - Dark-themed console output (QTextEdit)
    - Optional Clear Console button
    - Auto-scrolling when user is at bottom
    - Colored output based on message type
    - ANSI escape sequence handling
    """

    def __init__(
        self,
        parent=None,
        show_clear_button=True,
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
            console_label: Label text for the console (None to hide)
            min_height: Minimum height of the console in pixels
            max_height: Maximum height of the console in pixels (None for unlimited)
            custom_buttons: List of custom QPushButton widgets to add before Clear button (optional)
        """
        super(ConsoleWidget, self).__init__(parent)
        self.parent = parent

        from tit.gui.style import CONSOLE_MIN_HEIGHT, FONT_SIZE_CONSOLE

        if min_height == 200:  # default sentinel
            min_height = CONSOLE_MIN_HEIGHT
        self._console_font_size = FONT_SIZE_CONSOLE

        # Store configuration
        self.show_clear_button = show_clear_button
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

        layout.addLayout(header_layout)

        # Console output with dark theme.
        # Height constraints are applied to the outer ConsoleWidget (self),
        # not to this QTextEdit, so the dark area always fills the wrapper.
        self.console = QtWidgets.QTextEdit()
        self.console.setReadOnly(True)
        self.console.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.console.setStyleSheet(f"""
            QTextEdit {{
                background-color: #1e1e1e;
                color: #f0f0f0;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: {self._console_font_size}pt;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                padding: 8px;
            }}
        """)
        self.console.setAcceptRichText(True)
        # stretch=1 ensures the QTextEdit fills all remaining vertical space
        # within whatever height the outer ConsoleWidget is given.
        layout.addWidget(self.console, 1)

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

        formatted_text = format_message(text, message_type)
        append_with_autoscroll(self.console, formatted_text, process_events=False)

    def append_html(self, html_text):
        """
        Append raw HTML to the console (for custom formatted messages).

        Args:
            html_text: HTML formatted text to append
        """
        append_with_autoscroll(self.console, html_text, process_events=True)

    def get_console_widget(self):
        """Return the underlying QTextEdit console widget."""
        return self.console
