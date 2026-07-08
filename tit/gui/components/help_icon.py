#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Reusable hover-only help affordance.

This module provides :class:`HelpIcon`, a tiny non-interactive ``"?"`` label
that reveals contextual help on hover via a tooltip. It follows the repo's
``setToolTip`` convention for inline help and keeps a consistent circular
appearance across the GUI.
"""

from __future__ import annotations

from typing import Optional

from PyQt5 import QtCore, QtWidgets


class HelpIcon(QtWidgets.QLabel):
    """A small circular ``"?"`` icon that shows help text on hover.

    The icon is purely informational: it has no click behaviour and simply
    displays ``help_text`` as a tooltip when hovered.

    Args:
        help_text: The text shown as a tooltip on hover.
        parent: Optional parent widget.
    """

    def __init__(
        self, help_text: str, parent: Optional[QtWidgets.QWidget] = None
    ) -> None:
        super().__init__("?", parent)
        self.setToolTip(help_text)
        self.setCursor(QtCore.Qt.WhatsThisCursor)
        self.setFixedSize(15, 15)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setStyleSheet(
            "QLabel { color:#666; border:1px solid #999; "
            "border-radius:7px; font-weight:bold; font-size:10px; }"
        )
