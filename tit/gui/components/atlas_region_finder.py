#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Interactive, searchable, multi-select atlas region picker.

This module provides :class:`AtlasRegionFinderDialog`, a reusable dialog that
lets the user search and select one or more atlas regions from a supplied list
of ``(id, name, rgb)`` entries. It replaces several hand-rolled dialogs across
the GUI (the flex tab's two read-only region listers and the analyzer tab's
inline picker) with a single, unambiguous, id-aware component.

The dialog is *pure UI*: it performs no disk access. Callers are responsible
for loading atlas labels (e.g. via ``MeshAtlasManager`` / ``VoxelAtlasManager``)
and passing them in as ``entries``.

A module-level helper, :func:`merge_into_lineedit`, writes selected values back
into an existing ``QLineEdit``, de-duplicating while preserving order.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

from PyQt5 import QtCore, QtGui, QtWidgets


class AtlasRegionFinderDialog(QtWidgets.QDialog):
    """Searchable, multi-select dialog for choosing atlas regions.

    Each entry is displayed as ``"{id}: {name}"`` with an optional RGB colour
    swatch. The ``(id, name)`` pair is stored on every list item via
    ``Qt.UserRole`` so selections are resolved unambiguously (no fragile string
    parsing). A search field filters items by id *or* name substring
    (case-insensitive).

    Args:
        parent: Parent widget (``QWidget`` or ``None``).
        title: Window title for the dialog.
        entries: Sequence of ``(id, name, rgb)`` tuples where ``id`` is an int,
            ``name`` a str, and ``rgb`` a ``(r, g, b)`` tuple or ``None``.
        return_field: Which field :meth:`selected_values` returns -- ``"id"``
            or ``"name"``. Defaults to ``"id"``.
        multi: If ``True`` (default) allow multi-selection
            (``ExtendedSelection``); otherwise single selection.
        preselected: Optional iterable of ids to pre-select on open.
    """

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget],
        title: str,
        entries: Sequence[Tuple[int, str, Optional[Tuple]]],
        return_field: str = "id",
        multi: bool = True,
        preselected: Optional[Iterable[int]] = None,
    ) -> None:
        super().__init__(parent)

        if return_field not in ("id", "name"):
            raise ValueError(
                f"return_field must be 'id' or 'name', got {return_field!r}"
            )
        self._return_field = return_field

        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setMinimumHeight(500)

        layout = QtWidgets.QVBoxLayout(self)

        # ── Search box ───────────────────────────────────────────────────
        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("Search:"))
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Filter by id or name...")
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # ── Region list ──────────────────────────────────────────────────
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
            if multi
            else QtWidgets.QAbstractItemView.SingleSelection
        )
        preselected_set = {int(i) for i in preselected} if preselected else set()
        for entry in entries or []:
            self._add_entry(entry, preselected_set)
        layout.addWidget(self.list_widget)

        # ── Buttons ──────────────────────────────────────────────────────
        btn_layout = QtWidgets.QHBoxLayout()
        self.add_btn = QtWidgets.QPushButton("Add Selected")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # ── Wiring ───────────────────────────────────────────────────────
        self.search_input.textChanged.connect(self._filter)
        self.add_btn.clicked.connect(self._on_accept)
        self.cancel_btn.clicked.connect(self.reject)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._on_accept())

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _add_entry(
        self,
        entry: Tuple[int, str, Optional[Tuple]],
        preselected: set,
    ) -> None:
        """Create and append a list item for a single ``(id, name, rgb)`` entry."""
        region_id, name, rgb = entry
        item = QtWidgets.QListWidgetItem(f"{region_id}: {name}")
        item.setData(QtCore.Qt.UserRole, (int(region_id), str(name)))
        swatch = self._make_swatch(rgb)
        if swatch is not None:
            item.setIcon(swatch)
        self.list_widget.addItem(item)
        if int(region_id) in preselected:
            item.setSelected(True)

    @staticmethod
    def _make_swatch(rgb: Optional[Tuple]) -> Optional[QtGui.QIcon]:
        """Build a small colour-swatch icon from an ``(r, g, b)`` tuple.

        Returns ``None`` when ``rgb`` is missing or cannot be parsed.
        """
        if not rgb:
            return None
        try:
            r, g, b = (int(c) for c in rgb)
        except (TypeError, ValueError):
            return None
        pixmap = QtGui.QPixmap(12, 12)
        pixmap.fill(QtGui.QColor(r, g, b))
        return QtGui.QIcon(pixmap)

    # ------------------------------------------------------------------
    # Behaviour
    # ------------------------------------------------------------------

    def _filter(self, text: str) -> None:
        """Hide items whose id and name do not contain ``text`` (case-insensitive)."""
        query = text.strip().lower()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            region_id, name = item.data(QtCore.Qt.UserRole)
            haystack = f"{region_id} {name}".lower()
            item.setHidden(query not in haystack)

    def _on_accept(self) -> None:
        """Accept the dialog if at least one region is selected."""
        if not self.list_widget.selectedItems():
            return
        self.accept()

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def _selected_pairs(self) -> List[Tuple[int, str]]:
        """Return selected ``(id, name)`` pairs in top-to-bottom list order."""
        pairs: List[Tuple[int, str]] = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.isSelected():
                pairs.append(item.data(QtCore.Qt.UserRole))
        return pairs

    def selected_ids(self) -> List[int]:
        """Return the ids of the selected regions."""
        return [pair[0] for pair in self._selected_pairs()]

    def selected_names(self) -> List[str]:
        """Return the names of the selected regions."""
        return [pair[1] for pair in self._selected_pairs()]

    def selected_values(self) -> List:
        """Return selected ids or names according to ``return_field``."""
        if self._return_field == "name":
            return self.selected_names()
        return self.selected_ids()


def merge_into_lineedit(
    line_edit: QtWidgets.QLineEdit,
    values: Iterable,
    *,
    replace_default: Optional[object] = None,
) -> None:
    """Append comma-separated ``values`` into ``line_edit``, de-duplicating.

    Existing entries are preserved in order; new values are appended only if
    not already present. If the field currently holds *only* ``replace_default``
    (e.g. ``"1"`` or ``"10"``), that placeholder is replaced rather than
    appended to.

    Args:
        line_edit: The target ``QLineEdit`` to update in place.
        values: Iterable of values (str/int) to merge in.
        replace_default: Optional placeholder value; when the field contains
            only this value it is cleared before appending.
    """
    existing = line_edit.text().strip()
    current = [v.strip() for v in existing.split(",") if v.strip()]

    if replace_default is not None and current == [str(replace_default)]:
        current = []

    for value in values:
        token = str(value).strip()
        if token and token not in current:
            current.append(token)

    line_edit.setText(", ".join(current))
