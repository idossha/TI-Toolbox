#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Utility functions shared across the TI-Toolbox GUI.

Includes ANSI escape-code stripping, platform-aware file/directory openers,
message-importance filtering for console output, and a confirmation dialog
helper.

See Also
--------
tit.gui.components.console : Console widget that consumes these helpers.
tit.gui.components.base_thread : Uses ``strip_ansi_codes`` for output parsing.
"""

import logging
import os
import platform
import re
import subprocess
import webbrowser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ANSI escape-code handling
# ---------------------------------------------------------------------------

# Comprehensive ANSI escape pattern covering CSI sequences AND single-char escapes.
ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI colour / control sequences from *text*.

    This is the single canonical implementation used across the entire GUI.

    Parameters
    ----------
    text : str
        Raw text that may contain ANSI escape codes.

    Returns
    -------
    str
        Cleaned text with all escape sequences removed.
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

    Parameters
    ----------
    file_path : str
        Path to the file to open.

    Raises
    ------
    OSError
        If the file could not be opened by any method.
    """
    abs_path = os.path.abspath(file_path)

    # Try webbrowser first (works on most desktops)
    try:
        webbrowser.open("file://" + abs_path)
        return
    except OSError:
        pass

    match platform.system().lower():
        case "linux":
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
        case "darwin":
            subprocess.run(["open", abs_path], check=True)
            return
        case "windows":
            os.startfile(abs_path)  # type: ignore[attr-defined]
            return

    raise OSError(f"Could not open file: {abs_path}")


def open_directory(dir_path: str) -> None:
    """Open *dir_path* in the platform file manager.

    Parameters
    ----------
    dir_path : str
        Path to the directory to open.

    Raises
    ------
    OSError
        If the directory could not be opened by any method.
    """
    match platform.system().lower():
        case "linux":
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
        case "darwin":
            subprocess.run(["open", dir_path], check=True)
            return
        case "windows":
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

    Parameters
    ----------
    text : str
        The raw message text.
    message_type : str, optional
        Classified type (``'error'``, ``'warning'``, ``'info'``, etc.).
    context : str, optional
        Context tag (e.g. ``"exsearch"``) -- reserved for future filtering.

    Returns
    -------
    bool
    """
    if message_type in ("error", "warning", "success"):
        return True
    lower = text.lower()
    return any(kw in lower for kw in _IMPORTANT_KEYWORDS)


def is_verbose_message(
    text: str, message_type: str = "default", context: str = ""
) -> bool:
    """Return ``True`` if *text* is a verbose / debug message.

    Logical complement of :func:`is_important_message` -- returns ``True``
    for lines that would normally be hidden in summary mode.

    Parameters
    ----------
    text : str
        The raw message text.
    message_type : str, optional
        Classified type.
    context : str, optional
        Context tag.

    Returns
    -------
    bool
    """
    return not is_important_message(text, message_type, context)


def confirm_overwrite(parent, path, item_type="directory"):
    """Show a Yes/No dialog asking the user to confirm overwriting *path*.

    Parameters
    ----------
    parent : QWidget
        Parent widget for the dialog.
    path : str
        Filesystem path that would be overwritten.
    item_type : str, optional
        Label shown in the dialog (e.g. ``"directory"``, ``"file"``).

    Returns
    -------
    bool
        ``True`` if the user confirmed, ``False`` otherwise.
    """
    from PyQt5 import QtWidgets

    reply = QtWidgets.QMessageBox.question(
        parent,
        "Confirm Overwrite",
        f"{item_type.capitalize()} '{os.path.basename(path)}' already exists.\nOverwrite?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
    )
    return reply == QtWidgets.QMessageBox.Yes
