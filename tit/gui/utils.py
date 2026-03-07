#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
TI-Toolbox GUI Utilities
This module provides utility functions for the GUI.
"""

import logging
import os
import platform
import re
import subprocess
import webbrowser

from PyQt5 import QtWidgets

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ANSI escape-code handling
# ---------------------------------------------------------------------------

# Comprehensive ANSI escape pattern covering CSI sequences AND single-char escapes.
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color / control sequences from *text*.

    This is the single canonical implementation used across the entire GUI.
    """
    if not text:
        return text
    cleaned = ANSI_ESCAPE_PATTERN.sub("", text)
    # Remove any stray ESC characters that might remain
    cleaned = cleaned.replace("\x1b", "")
    return cleaned


# ---------------------------------------------------------------------------
# Platform-aware file / directory opening helpers
# ---------------------------------------------------------------------------


def open_file(file_path: str) -> None:
    """Open *file_path* in the platform default application.

    Tries ``webbrowser.open`` first, then falls back to platform-specific
    commands (``xdg-open``, ``open``, ``os.startfile``).

    Raises:
        OSError: If the file could not be opened by any method.
    """
    abs_path = os.path.abspath(file_path)

    # Try webbrowser first (works on most desktops)
    try:
        webbrowser.open("file://" + abs_path)
        return
    except OSError:
        pass

    system = platform.system().lower()
    if system == "linux":
        try:
            subprocess.run(["xdg-open", abs_path], check=True)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        # Fall through to browser fallback
        for browser in ("firefox", "chromium", "google-chrome", "chrome"):
            try:
                subprocess.run([browser, abs_path], check=True)
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
    elif system == "darwin":
        subprocess.run(["open", abs_path], check=True)
        return
    elif system == "windows":
        os.startfile(abs_path)  # type: ignore[attr-defined]
        return

    raise OSError(f"Could not open file: {abs_path}")


def open_directory(dir_path: str) -> None:
    """Open *dir_path* in the platform file manager.

    Raises:
        OSError: If the directory could not be opened by any method.
    """
    system = platform.system().lower()
    if system == "linux":
        try:
            subprocess.run(["xdg-open", dir_path], check=True)
            return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        for fm in ("nautilus", "dolphin", "thunar", "pcmanfm", "nemo"):
            try:
                subprocess.run([fm, dir_path], check=True)
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                continue
    elif system == "darwin":
        subprocess.run(["open", dir_path], check=True)
        return
    elif system == "windows":
        os.startfile(dir_path)  # type: ignore[attr-defined]
        return

    raise OSError(f"Could not open directory: {dir_path}")


# ---------------------------------------------------------------------------
# Message filtering helpers (used by ex_search_tab in non-debug mode)
# ---------------------------------------------------------------------------

# Keywords that mark a message as "important" even when verbose output is off.
_IMPORTANT_KEYWORDS = (
    "error",
    "warning",
    "success",
    "completed",
    "failed",
    "beginning",
    "starting",
    "results available",
    "saved to",
    "✓",
    "✗",
    "└─",
)


def is_important_message(
    text: str, message_type: str = "default", context: str = ""
) -> bool:
    """Return ``True`` if *text* should be displayed in non-debug / summary mode.

    Args:
        text: The raw message text.
        message_type: The classified type ('error', 'warning', 'info', etc.).
        context: Optional context tag (e.g. ``"exsearch"``) — reserved for
            future per-module filtering.
    """
    if message_type in ("error", "warning", "success"):
        return True
    lower = text.lower()
    return any(kw in lower for kw in _IMPORTANT_KEYWORDS)


def is_verbose_message(
    text: str, message_type: str = "default", context: str = ""
) -> bool:
    """Return ``True`` if *text* is a verbose / debug message.

    This is the logical complement of :func:`is_important_message` — it
    returns ``True`` for lines that would normally be hidden in summary mode.
    """
    return not is_important_message(text, message_type, context)


# ---------------------------------------------------------------------------
# Overwrite-protection dialog
# ---------------------------------------------------------------------------


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
