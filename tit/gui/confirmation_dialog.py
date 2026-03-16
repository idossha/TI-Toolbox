#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox Confirmation Dialog
This module provides a reusable confirmation dialog for the GUI.
"""

from PyQt5 import QtWidgets


class ConfirmationDialog(QtWidgets.QMessageBox):
    """A reusable confirmation dialog that centers itself relative to the main window."""

    def __init__(
        self, parent=None, title="Confirm Action", message="Are you sure?", details=None
    ):
        """Initialize the confirmation dialog.

        Args:
            parent: The parent widget
            title: The dialog title
            message: The main message
            details: Additional details to show (optional)
        """
        super().__init__(parent)

        self.setIcon(QtWidgets.QMessageBox.Question)
        self.setWindowTitle(title)
        self.setText(message)
        if details:
            self.setInformativeText(details)

        self.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        self.setDefaultButton(QtWidgets.QMessageBox.No)

        if parent:
            main_window = parent.window()
            if main_window:
                main_rect = main_window.geometry()

                dialog_size = self.sizeHint()

                x = main_rect.x() + (main_rect.width() - dialog_size.width()) // 2
                y = main_rect.y() + (main_rect.height() - dialog_size.height()) // 2

                self.move(x, y)

    @staticmethod
    def confirm(parent, title="Confirm Action", message="Are you sure?", details=None):
        """Show the confirmation dialog and return True if confirmed.

        Args:
            parent: The parent widget
            title: The dialog title
            message: The main message
            details: Additional details to show (optional)

        Returns:
            bool: True if the user confirmed, False otherwise
        """
        dialog = ConfirmationDialog(parent, title, message, details)
        return dialog.exec_() == QtWidgets.QMessageBox.Yes
