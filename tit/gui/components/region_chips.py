#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Reusable "chips/tags" widget for compact, removable region selections.

This module provides :class:`RegionChipsWidget`, a small widget that displays a
set of selected regions as rounded pills ("chips"). Each chip shows a display
string and a "✕" remove button, and the chips wrap onto new rows when the
host is narrow. When nothing is selected, a muted placeholder is shown instead.

A minimal Qt :class:`FlowLayout` helper (the standard wrapping layout from the
Qt examples) is implemented here so the widget has no external layout
dependency.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt5 import QtCore, QtWidgets

from tit.gui.style import (
    COLOR_ACCENT,
    COLOR_ERROR,
    COLOR_TEXT_MUTED,
    FONT_HELP,
    SP_XS,
)


# ---------------------------------------------------------------------------
# FlowLayout: a layout that lays items left-to-right and wraps to new rows.
# ---------------------------------------------------------------------------
class FlowLayout(QtWidgets.QLayout):
    """A layout that arranges child items in rows, wrapping as needed.

    This is the standard Qt "flow layout" helper: items are placed
    left-to-right and flow onto a new row whenever the current row runs out
    of horizontal space. It supports ``heightForWidth`` so hosts can size it
    correctly inside vertical layouts and scroll areas.

    Args:
        parent: Optional parent widget. When given, the layout installs
            itself on that widget.
        margin: Uniform content margin in pixels.
        spacing: Gap between items (both horizontal and vertical) in pixels.
    """

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        margin: int = 0,
        spacing: int = SP_XS,
    ) -> None:
        super().__init__(parent)
        self._items: List[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> QtCore.Qt.Orientations:  # noqa: N802
        return QtCore.Qt.Orientations(QtCore.Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QtCore.QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:  # noqa: N802
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        return size

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        """Position items within ``rect`` and return the total height.

        Args:
            rect: The rectangle to lay items out in.
            test_only: When ``True``, only compute the required height without
                moving any widgets.

        Returns:
            The total height required for the laid-out content.
        """
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(),
            margins.top(),
            -margins.right(),
            -margins.bottom(),
        )
        x = effective.x()
        y = effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()


# ---------------------------------------------------------------------------
# Chip styling
# ---------------------------------------------------------------------------
_CHIP_STYLE = f"""
QFrame#regionChip {{
    background-color: #eef3f8;
    border: 1px solid #ccd7e0;
    border-radius: 9px;
}}
QFrame#regionChip:hover {{
    border-color: {COLOR_ACCENT};
}}
"""

_CHIP_LABEL_STYLE = (
    f"border: none; background: transparent; font-size: {FONT_HELP}; color: #333;"
)

_CHIP_REMOVE_STYLE = f"""
QToolButton {{
    border: none;
    background: transparent;
    color: {COLOR_TEXT_MUTED};
    font-size: {FONT_HELP};
    font-weight: bold;
    padding: 0px;
}}
QToolButton:hover {{
    color: {COLOR_ERROR};
}}
"""


class _ChipWidget(QtWidgets.QFrame):
    """A single rounded pill showing a display string and a remove button.

    Args:
        key: Opaque identifier carried by the chip (emitted on removal).
        display: Human-readable text shown on the chip.
        parent: Optional parent widget.
    """

    removed = QtCore.pyqtSignal(str)

    def __init__(
        self,
        key: str,
        display: str,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._key = key
        self.setObjectName("regionChip")
        self.setStyleSheet(_CHIP_STYLE)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(SP_XS + 2, 2, SP_XS, 2)
        layout.setSpacing(SP_XS)

        label = QtWidgets.QLabel(display)
        label.setStyleSheet(_CHIP_LABEL_STYLE)
        label.setToolTip(display)
        layout.addWidget(label)

        remove_btn = QtWidgets.QToolButton()
        remove_btn.setText("✕")
        remove_btn.setToolTip(f"Remove {display}")
        remove_btn.setCursor(QtCore.Qt.PointingHandCursor)
        remove_btn.setFocusPolicy(QtCore.Qt.NoFocus)
        remove_btn.setFixedSize(14, 14)
        remove_btn.setStyleSheet(_CHIP_REMOVE_STYLE)
        remove_btn.clicked.connect(lambda: self.removed.emit(self._key))
        layout.addWidget(remove_btn)

    @property
    def key(self) -> str:
        """The opaque key this chip represents."""
        return self._key


class RegionChipsWidget(QtWidgets.QWidget):
    """Compact, removable display of selected regions as wrapping chips.

    Each chip carries an opaque ``key`` plus its ``display`` text. Adding a
    key that is already present is a no-op (de-duplication by key). Chips are
    laid out left-to-right and wrap onto new rows via :class:`FlowLayout`.
    When empty, a muted placeholder is shown instead.

    Signals:
        changed: Emitted whenever the set of chips changes (add/remove/clear).

    Args:
        parent: Optional parent widget.
        placeholder: Text shown when no regions are selected. Falls back to a
            sensible default when omitted.
    """

    changed = QtCore.pyqtSignal()

    _PLACEHOLDER_TEXT = "No regions selected — use Browse…"

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        placeholder: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._placeholder_text = placeholder or self._PLACEHOLDER_TEXT
        # Insertion-ordered mapping of key -> display text.
        self._items: "dict[str, str]" = {}

        self._flow = FlowLayout(self, margin=0, spacing=SP_XS)

        self._placeholder = QtWidgets.QLabel(self._placeholder_text)
        self._placeholder.setStyleSheet(
            f"color: {COLOR_TEXT_MUTED}; font-size: {FONT_HELP}; font-style: italic;"
        )

        # Keep at least ~1 row visible even when empty.
        self.setMinimumHeight(24)
        policy = self.sizePolicy()
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

        self._rebuild()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def add_item(self, key: str, display: str) -> None:
        """Add a chip. Adding an existing key is a no-op.

        Args:
            key: Opaque identifier for the chip.
            display: Text shown on the chip.
        """
        if key in self._items:
            return
        self._items[key] = display
        self._rebuild()
        self.changed.emit()

    def remove(self, key: str) -> None:
        """Remove the chip with ``key`` if present.

        Args:
            key: The key of the chip to remove.
        """
        if key not in self._items:
            return
        del self._items[key]
        self._rebuild()
        self.changed.emit()

    def clear(self) -> None:
        """Remove all chips. No-op (and no signal) when already empty."""
        if not self._items:
            return
        self._items.clear()
        self._rebuild()
        self.changed.emit()

    def set_items(self, items: List[Tuple[str, str]]) -> None:
        """Replace all chips with ``items``.

        Later duplicates of the same key overwrite the earlier display text
        while preserving the key's original position.

        Args:
            items: Sequence of ``(key, display)`` tuples.
        """
        new_items: "dict[str, str]" = {}
        for key, display in items:
            new_items[key] = display
        self._items = new_items
        self._rebuild()
        self.changed.emit()

    def keys(self) -> List[str]:
        """Return the chip keys in insertion order."""
        return list(self._items.keys())

    def items(self) -> List[Tuple[str, str]]:
        """Return the chips as ``(key, display)`` tuples in insertion order.

        Suitable for snapshotting the current selection and restoring it later
        via :meth:`set_items`.
        """
        return list(self._items.items())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _clear_layout(self) -> None:
        """Detach every item from the flow layout, deleting spent chips."""
        while self._flow.count():
            item = self._flow.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            widget.setParent(None)
            if widget is not self._placeholder:
                widget.deleteLater()

    def _rebuild(self) -> None:
        """Rebuild the flow layout from the current item mapping."""
        self._clear_layout()
        if not self._items:
            self._flow.addWidget(self._placeholder)
            self._placeholder.setVisible(True)
        else:
            for key, display in self._items.items():
                chip = _ChipWidget(key, display, self)
                chip.removed.connect(self.remove)
                self._flow.addWidget(chip)
        self._flow.invalidate()
        self.updateGeometry()

    # ------------------------------------------------------------------
    # Height-for-width plumbing so hosts size the widget correctly.
    # ------------------------------------------------------------------
    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._flow.heightForWidth(width)
