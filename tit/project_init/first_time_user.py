"""First-time user experience for the TI-Toolbox GUI.

Thin GUI layer that reads project status and shows the welcome dialog.
All status persistence is delegated to :mod:`tit.project_init.initializer`.
This module **never** creates or recreates ``project_status.json``.
"""

import logging
from pathlib import Path

from PyQt5 import QtWidgets, QtCore

from tit.paths import get_path_manager
from .initializer import load_project_status, update_project_status

logger = logging.getLogger(__name__)


def _resolve_project_dir() -> Path | None:
    """Return the project root from the active :class:`PathManager`.

    Returns ``None`` when the PathManager is not initialised.
    """
    try:
        pm = get_path_manager()
        return Path(pm._root())
    except Exception:
        logger.warning("PathManager not initialised — cannot resolve project dir")
        return None


def check_first_time_user() -> bool:
    """Return ``True`` when the welcome dialog should be shown.

    Reads ``show_welcome`` from the persisted status.  If the status file
    is missing the user is treated as *new* (returns ``True``) but no file
    is created on disk.
    """
    project_dir = _resolve_project_dir()
    if project_dir is None:
        return True

    status = load_project_status(project_dir)
    if not status:
        # File missing — treat as first-time but don't create anything.
        return True

    return status.get("user_preferences", {}).get("show_welcome", True)


def mark_user_as_experienced() -> bool:
    """Persist ``show_welcome = False`` so the dialog is not shown again."""
    project_dir = _resolve_project_dir()
    if project_dir is None:
        return False

    return update_project_status(
        project_dir, {"user_preferences": {"show_welcome": False}}
    )


def show_welcome_message(parent: QtWidgets.QWidget | None = None) -> None:
    """Show a welcome dialog with a *Don't show again* checkbox."""
    try:
        msg_box = QtWidgets.QMessageBox(parent)
        msg_box.setWindowTitle("Welcome to TI-Toolbox")
        msg_box.setIcon(QtWidgets.QMessageBox.Information)

        message = """
Welcome to the TI-Toolbox!

This toolbox provides a user-friendly interface for:
• Pre-processing structural MRI data and analyze anatomical structures
• Optimizing electrode positions for ROI targeting
• Running flexible uTI & mTI simulations
• Analyzing and visualizing results

The interface is organized into several tabs:
1. Pre-process: Prepare your structural data
3. ex/flex-search: Find optimal electrode positions
2. Simulator: Run TI simulations
4. Analyzer: Analyze results & view in mesh/voxel spaces
5. Nifti-viewer: View simulations and analyses in voxel space

Each tab has its own configuration options and help buttons.
Feel free to explore the interface and check the documentation for more details.
        """

        msg_box.setText(message)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.Ok)

        checkbox = QtWidgets.QCheckBox("Don't show this message again")
        msg_box.setCheckBox(checkbox)

        if parent and parent.isVisible():
            main_rect = parent.geometry()
            dialog_size = msg_box.sizeHint()
            x = main_rect.x() + (main_rect.width() - dialog_size.width()) // 2
            y = main_rect.y() + (main_rect.height() - dialog_size.height()) // 2
            msg_box.move(x, y)

        msg_box.exec_()

        if checkbox.isChecked():
            mark_user_as_experienced()

    except Exception as exc:
        logger.error("Error showing welcome message: %s", exc)


def assess_user_status(parent: QtWidgets.QWidget | None = None) -> None:
    """Entry point called on GUI startup (after a short delay).

    Shows the welcome dialog when ``show_welcome`` is ``True`` (or the
    status file is absent).  Never creates or recreates the status file.
    """
    try:
        if not check_first_time_user():
            return

        # Ensure we run in the main (GUI) thread.
        app = QtWidgets.QApplication.instance()
        if app is None:
            return

        if QtCore.QThread.currentThread() == app.thread():
            show_welcome_message(parent)
        else:
            QtCore.QMetaObject.invokeMethod(
                app,
                "show_welcome_message",
                QtCore.Qt.QueuedConnection,
                QtCore.Q_ARG(QtWidgets.QWidget, parent),
            )
    except Exception as exc:
        logger.error("Error in assess_user_status: %s", exc)
