#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
ConductivityEditorDialog Component
Dialog for editing tissue conductivity values in the simulator tab.
"""

import os

from PyQt5 import QtWidgets, QtCore, QtGui

from tit.gui.style import FONT_MD


class ConductivityEditorDialog(QtWidgets.QDialog):
    """Editable table dialog for tissue conductivity values.

    Displays default SimNIBS tissue conductivities with literature references
    and allows the user to override individual values for simulation.

    Parameters
    ----------
    parent : QWidget or None
        Parent widget.
    custom_conductivities : dict or None
        Mapping of tissue number to conductivity (S/m) overrides.
    """

    def __init__(self, parent=None, custom_conductivities=None):
        super(ConductivityEditorDialog, self).__init__(parent)
        self.setWindowTitle("Tissue Conductivity Editor")
        # Use integer keys for tissue numbers
        self.custom_conductivities = {
            int(k): v for k, v in (custom_conductivities or {}).items()
        }
        self.setup_ui()

    def setup_ui(self):
        # Remove fixed size, use resize and minimum size for flexibility
        self.resize(900, 480)
        self.setMinimumSize(800, 400)

        # Main layout, no margins or spacing
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Info label
        info_label = QtWidgets.QLabel(
            "Double-click on a value in the 'Value (S/m)' column to edit it."
        )
        info_label.setStyleSheet("""
            QLabel {
                background-color: #f0f0f0;
                color: #333;
                padding: 4px 8px 4px 8px;
                border-bottom: 1px solid #ddd;
                font-style: italic;
            }
        """)
        layout.addWidget(info_label)

        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["Tissue Number", "Tissue Name", "Value (S/m)", "Reference"]
        )
        self.table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )

        self.tissue_data = [
            (1, "White Matter", 0.126, "Wagner et al., 2004"),
            (2, "Gray Matter", 0.275, "Wagner et al., 2004"),
            (3, "CSF", 1.654, "Wagner et al., 2004"),
            (4, "Bone", 0.01, "Wagner et al., 2004"),
            (5, "Scalp", 0.465, "Wagner et al., 2004"),
            (6, "Eye balls", 0.5, "Opitz et al., 2015"),
            (7, "Compact Bone", 0.008, "Opitz et al., 2015"),
            (8, "Spongy Bone", 0.025, "Opitz et al., 2015"),
            (9, "Blood", 0.6, "Gabriel et al., 2009"),
            (10, "Muscle", 0.16, "Gabriel et al., 2009"),
            (
                100,
                "Silicone Rubber",
                29.4,
                "NeuroConn electrodes: Wacker Elastosil R 570/60 RUSS",
            ),
            (500, "Saline", 1.0, "Saturnino et al., 2015"),
        ]
        self.table.setRowCount(len(self.tissue_data))
        for row, (number, name, value, ref) in enumerate(self.tissue_data):
            item = QtWidgets.QTableWidgetItem(str(number))
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(name)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 1, item)
            item = QtWidgets.QTableWidgetItem(str(value))
            item.setBackground(QtGui.QColor("#f0f8ff"))
            self.table.setItem(row, 2, item)
            item = QtWidgets.QTableWidgetItem(ref)
            item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
            self.table.setItem(row, 3, item)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: white;
                alternate-background-color: #f5f5f5;
                selection-background-color: #2196F3;
                selection-color: white;
                gridline-color: #e0e0e0;
                border: none;
            }}
            QHeaderView::section {{
                background-color: #4a4a4a;
                color: white;
                padding: 4px;
                border: none;
                font-weight: bold;
            }}
            QTableWidget::item {{
                padding: 1px;
                font-size: {FONT_MD};
            }}
        """)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.DoubleClicked
            | QtWidgets.QAbstractItemView.EditKeyPressed
        )
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(28)
        layout.addWidget(self.table)

        # Button container
        button_container = QtWidgets.QWidget()
        button_container.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        button_container.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                border-top: 1px solid #ddd;
            }
            QPushButton {
                min-width: 100px;
                padding: 6px 12px;
                margin: 6px;
                background-color: #ffffff;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
            }
        """)
        button_layout = QtWidgets.QHBoxLayout(button_container)
        button_layout.setContentsMargins(10, 0, 10, 0)
        button_layout.setSpacing(0)
        save_btn = QtWidgets.QPushButton("Save")
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(cancel_btn)
        save_btn.clicked.connect(self.save_conductivities)
        reset_btn.clicked.connect(self.reset_to_defaults)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(button_container)

        # After populating the table, override values with custom_conductivities if present
        for row, (number, name, value, ref) in enumerate(self.tissue_data):
            if self.custom_conductivities.get(number) is not None:
                self.table.item(row, 2).setText(str(self.custom_conductivities[number]))

    def save_conductivities(self):
        """Save the modified conductivity values."""
        modified_values = {}
        for row in range(self.table.rowCount()):
            tissue_num = int(self.table.item(row, 0).text())
            try:
                value = float(self.table.item(row, 2).text())
                if value <= 0:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Invalid Value",
                        f"Conductivity value for tissue {tissue_num} must be positive.",
                    )
                    return
                modified_values[tissue_num] = value
                os.environ[f"TISSUE_COND_{tissue_num}"] = str(value)
            except ValueError:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid Value",
                    f"Invalid conductivity value for tissue {tissue_num}. Please enter a valid number.",
                )
                return
        self.custom_conductivities = modified_values
        self.accept()

    def reset_to_defaults(self):
        """Reset all values to their defaults."""
        for row, (number, _, value, _) in enumerate(self.tissue_data):
            self.table.item(row, 2).setText(str(value))

    def get_conductivities(self):
        return self.custom_conductivities.copy()
