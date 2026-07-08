#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Reusable click-to-popup help affordance.

This module provides :class:`HelpIcon`, a tiny clickable ``"?"`` button that
reveals contextual help in a small popup when clicked. It keeps a consistent
circular appearance across the GUI and is intentionally small and reusable.
"""

from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtWidgets


class HelpIcon(QtWidgets.QToolButton):
    """A small circular ``"?"`` button that shows help text on click.

    The icon is an interactive affordance: clicking it opens a small
    information popup containing ``help_text``. The same text is also set as a
    tooltip so it remains discoverable on hover.

    Args:
        help_text: The text shown in the popup (and as a tooltip) on demand.
        title: Window title for the popup dialog. Defaults to ``"Help"``.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        help_text: str,
        title: str = "Help",
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._help_text = help_text
        self._title = title
        self.setText("?")
        self.setToolTip(help_text)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFixedSize(15, 15)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setStyleSheet(
            "QToolButton { color:#666; border:1px solid #999; "
            "border-radius:7px; font-weight:bold; font-size:10px; "
            "padding:0px; }"
            "QToolButton:hover { color:#333; border-color:#666; }"
        )
        self.clicked.connect(self._show_popup)

    def _show_popup(self) -> None:
        """Show the help text in a small information popup near the button."""
        QtWidgets.QMessageBox.information(self, self._title, self._help_text)
