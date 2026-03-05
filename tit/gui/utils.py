#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox GUI Utilities
This module provides utility functions for the GUI.
"""

import os
from PyQt5 import QtWidgets


def confirm_overwrite(parent, path, item_type="file"):
    """
    Show an error dialog when an existing output directory is found.

    Args:
        parent: The parent widget for the dialog
        path: The path to the file/directory that already exists
        item_type: String describing the type of item ("file" or "directory")

    Returns:
        bool: Always False when path exists; True otherwise.
    """
    if os.path.exists(path):
        msg = QtWidgets.QMessageBox(parent)
        msg.setIcon(QtWidgets.QMessageBox.Critical)
        msg.setWindowTitle("Output Already Exists")
        msg.setText(
            f"The {item_type} already exists:\n{path}\n\n"
            "Please remove it manually before rerunning."
        )
        msg.setStandardButtons(QtWidgets.QMessageBox.Ok)
        msg.exec_()
        return False
    return True
