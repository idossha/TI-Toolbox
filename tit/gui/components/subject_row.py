"""
Shared SubjectRow widget and SubjectRowManager for extension panels.

SubjectRow provides:
- Subject ComboBox (populated from subjects list)
- Simulation ComboBox (cascaded from subject selection)
- Configurable extra widgets (group combo, response combo, etc.)
- Remove button

SubjectRowManager handles:
- Adding / removing SubjectRow widgets in a scroll area
- Maintaining the rows list
"""

from PyQt5 import QtWidgets, QtCore, QtGui

from tit.gui.style import COLOR_ERROR, COLOR_ERROR_DARK

# ---------------------------------------------------------------------------
# Remove-button stylesheet (shared across all rows)
# ---------------------------------------------------------------------------
_REMOVE_BTN_STYLE = f"""
    QPushButton {{
        background-color: {COLOR_ERROR};
        color: white;
        border-radius: 3px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: {COLOR_ERROR_DARK};
    }}
"""


class SubjectRow(QtWidgets.QWidget):
    """Reusable widget for a single subject-simulation row.

    Parameters
    ----------
    parent : QWidget | None
        Parent widget.
    subjects_list : list[str]
        Available subject IDs to populate the subject combo.
    simulations_dict : dict[str, list[str]]
        Mapping of subject_id -> list of simulation names.
    extra_widgets : list[tuple[QWidget, int]] | None
        Additional widgets to insert between the simulation combo and the
        remove button.  Each entry is ``(widget, stretch)`` where *stretch*
        is the layout stretch factor.
    """

    remove_requested = QtCore.pyqtSignal(object)

    def __init__(
        self,
        parent=None,
        subjects_list=None,
        simulations_dict=None,
        extra_widgets=None,
    ):
        super().__init__(parent)
        self.subjects_list = subjects_list or []
        self.simulations_dict = simulations_dict or {}
        self._extra_widgets = extra_widgets or []
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Subject combo
        self.subject_combo = QtWidgets.QComboBox()
        self.subject_combo.addItems(self.subjects_list)
        self.subject_combo.currentTextChanged.connect(self.on_subject_changed)
        layout.addWidget(self.subject_combo, 2)

        # Simulation combo
        self.simulation_combo = QtWidgets.QComboBox()
        layout.addWidget(self.simulation_combo, 3)

        # Extra widgets supplied by the caller
        for widget, stretch in self._extra_widgets:
            layout.addWidget(widget, stretch)

        # Remove button
        self.remove_btn = QtWidgets.QPushButton("\u2715")
        self.remove_btn.setFixedWidth(30)
        self.remove_btn.setStyleSheet(_REMOVE_BTN_STYLE)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(self.remove_btn)

        # Initialise simulation list for the current subject
        self.on_subject_changed(self.subject_combo.currentText())

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def on_subject_changed(self, subject_id: str):
        """Populate the simulation combo when the subject changes."""
        self.simulation_combo.clear()
        if subject_id in self.simulations_dict:
            self.simulation_combo.addItems(self.simulations_dict[subject_id])

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def current_subject(self) -> str:
        return self.subject_combo.currentText()

    def current_simulation(self) -> str:
        return self.simulation_combo.currentText()

    def set_subject(self, subject_id: str):
        idx = self.subject_combo.findText(subject_id)
        if idx >= 0:
            self.subject_combo.setCurrentIndex(idx)

    def set_simulation(self, simulation_name: str):
        idx = self.simulation_combo.findText(simulation_name)
        if idx >= 0:
            self.simulation_combo.setCurrentIndex(idx)


class SubjectRowManager:
    """Manages a collection of SubjectRow widgets inside a scrollable area.

    Parameters
    ----------
    container_layout : QVBoxLayout
        The layout inside the scroll area's widget.  A trailing stretch is
        expected at the end (added by the caller on first setup).
    """

    def __init__(self, container_layout: QtWidgets.QVBoxLayout):
        self._layout = container_layout
        self._rows: list[SubjectRow] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def rows(self) -> list[SubjectRow]:
        return self._rows

    def add_row(self, row: SubjectRow):
        """Insert *row* before the trailing stretch and wire up removal."""
        row.remove_requested.connect(self.remove_row)
        self._layout.insertWidget(len(self._rows), row)
        self._rows.append(row)

    def remove_row(self, row: SubjectRow):
        """Remove *row* from the manager and delete the widget."""
        if row in self._rows:
            self._rows.remove(row)
            row.deleteLater()

    def clear(self):
        """Remove all rows."""
        for row in self._rows[:]:
            self.remove_row(row)

    def __len__(self):
        return len(self._rows)

    def __iter__(self):
        return iter(self._rows)
