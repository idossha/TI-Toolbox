#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Electrode Configuration Widget

Self-contained widget for configuring electrode parameters:
current, shape, dimensions, and thickness.
"""

from PyQt5 import QtWidgets


class ElectrodeConfigWidget(QtWidgets.QGroupBox):
    """Electrode configuration: current, shape, dimensions, thickness."""

    def __init__(self, parent=None, title="Electrode Parameters"):
        super().__init__(title, parent)

        # --- Current ---
        self.current_input = QtWidgets.QDoubleSpinBox()
        self.current_input.setRange(0.1, 100)
        self.current_input.setValue(1.0)
        self.current_input.setDecimals(1)

        # --- Shape radio buttons ---
        self.shape_rect = QtWidgets.QRadioButton("Rectangle")
        self.shape_rect.setProperty("value", "rect")
        self.shape_ellipse = QtWidgets.QRadioButton("Ellipse")
        self.shape_ellipse.setProperty("value", "ellipse")
        self.shape_ellipse.setChecked(True)

        # --- Dimensions ---
        self.dimensions_input = QtWidgets.QLineEdit()
        self.dimensions_input.setPlaceholderText("8,8")
        self.dimensions_input.setText("8,8")

        # --- Thickness ---
        self.thickness_input = QtWidgets.QLineEdit()
        self.thickness_input.setPlaceholderText("4")
        self.thickness_input.setText("4")

        # --- Layout ---
        layout = QtWidgets.QFormLayout(self)

        layout.addRow("Electrode Current (mA):", self.current_input)

        shape_layout = QtWidgets.QHBoxLayout()
        shape_layout.addWidget(self.shape_rect)
        shape_layout.addWidget(self.shape_ellipse)
        shape_layout.addStretch()
        layout.addRow("Electrode Shape:", shape_layout)

        layout.addRow("Dimensions (mm, x,y):", self.dimensions_input)
        layout.addRow("Gel Thickness (mm):", self.thickness_input)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_config(self):
        """Return ``(FlexElectrodeConfig, current_mA)`` tuple."""
        from tit.opt.config import FlexElectrodeConfig

        shape = self.get_shape()
        dims = [float(d.strip()) for d in self.get_dimensions_text().split(",")]
        thickness = float(self.get_thickness_text())
        electrode = FlexElectrodeConfig(
            shape=shape, dimensions=dims, gel_thickness=thickness
        )
        return electrode, self.current_input.value()

    def get_shape(self) -> str:
        """Return ``'rect'`` or ``'ellipse'``."""
        return "rect" if self.shape_rect.isChecked() else "ellipse"

    def get_dimensions_text(self) -> str:
        """Return raw dimensions text, defaulting to ``'8,8'``."""
        return self.dimensions_input.text() or "8,8"

    def get_thickness_text(self) -> str:
        """Return raw thickness text, defaulting to ``'4'``."""
        return self.thickness_input.text() or "4"

    def setEnabled(self, enabled: bool):
        """Enable or disable all child widgets."""
        super().setEnabled(enabled)
