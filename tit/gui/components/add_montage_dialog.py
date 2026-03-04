#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
AddMontageDialog Component
Dialog for adding new montages to the simulator tab.
"""

import os

from PyQt5 import QtWidgets

from tit.core import get_path_manager
from tit.gui.style import FONT_SUBHEADING


class AddMontageDialog(QtWidgets.QDialog):
    """Dialog for adding new montages."""

    def __init__(self, parent=None):
        super(AddMontageDialog, self).__init__(parent)
        self.parent = parent
        # Get path manager from parent if available
        if parent and hasattr(parent, "pm"):
            self.pm = parent.pm
        else:
            self.pm = get_path_manager()
        self.setup_ui()

        # Connect radio buttons to update electrode inputs
        self.mode_unipolar.toggled.connect(self.update_electrode_inputs)

    def setup_ui(self):
        """Set up the dialog UI."""
        self.setWindowTitle("Add New Montage")
        self.setModal(True)
        self.resize(800, 500)  # Made wider to accommodate the side panel

        # Create main horizontal layout
        main_layout = QtWidgets.QHBoxLayout(self)

        # Left side (original form)
        left_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(left_widget)

        # Create form layout for better organization
        form_layout = QtWidgets.QFormLayout()

        # Montage name
        self.name_input = QtWidgets.QLineEdit()
        form_layout.addRow("Montage Name:", self.name_input)

        # Target EEG Net selection with Show Electrodes button
        net_layout = QtWidgets.QHBoxLayout()
        self.net_combo = QtWidgets.QComboBox()
        # Copy items from parent's EEG net combo
        if self.parent and hasattr(self.parent, "eeg_net_combo"):
            for i in range(self.parent.eeg_net_combo.count()):
                self.net_combo.addItem(self.parent.eeg_net_combo.itemText(i))
        # Set current net to match parent's selection
        if self.parent and hasattr(self.parent, "eeg_net_combo"):
            current_net = self.parent.eeg_net_combo.currentText()
            index = self.net_combo.findText(current_net)
            if index >= 0:
                self.net_combo.setCurrentIndex(index)

        self.show_electrodes_btn = QtWidgets.QPushButton("Show Electrodes")
        self.show_electrodes_btn.clicked.connect(self.toggle_electrode_list)
        net_layout.addWidget(self.net_combo)
        net_layout.addWidget(self.show_electrodes_btn)
        form_layout.addRow("Target EEG Net:", net_layout)

        # Add form layout to main layout
        layout.addLayout(form_layout)

        # Simulation mode (Unipolar/Multipolar)
        mode_group = QtWidgets.QGroupBox("Montage Type")
        mode_layout = QtWidgets.QHBoxLayout(mode_group)
        self.mode_unipolar = QtWidgets.QRadioButton("Unipolar")
        self.mode_multipolar = QtWidgets.QRadioButton("Multipolar")
        self.mode_unipolar.setChecked(True)  # Default to unipolar
        mode_layout.addWidget(self.mode_unipolar)
        mode_layout.addWidget(self.mode_multipolar)
        layout.addWidget(mode_group)

        # Create a stacked widget for electrode inputs
        self.electrode_stack = QtWidgets.QStackedWidget()

        # Unipolar electrode pairs (two pairs)
        uni_widget = QtWidgets.QWidget()
        uni_layout = QtWidgets.QVBoxLayout(uni_widget)

        # Add a label for the unipolar electrode section
        uni_label = QtWidgets.QLabel("Unipolar Electrode Pairs:")
        uni_label.setStyleSheet("font-weight: bold;")
        uni_layout.addWidget(uni_label)

        # Pair 1
        uni_pair1_layout = QtWidgets.QHBoxLayout()
        self.uni_pair1_label = QtWidgets.QLabel("Pair 1:")
        self.uni_pair1_e1 = QtWidgets.QLineEdit()
        self.uni_pair1_e1.setPlaceholderText("E10")
        self.uni_pair1_e2 = QtWidgets.QLineEdit()
        self.uni_pair1_e2.setPlaceholderText("E11")
        uni_pair1_layout.addWidget(self.uni_pair1_label)
        uni_pair1_layout.addWidget(self.uni_pair1_e1)
        uni_pair1_layout.addWidget(QtWidgets.QLabel("↔"))
        uni_pair1_layout.addWidget(self.uni_pair1_e2)
        uni_layout.addLayout(uni_pair1_layout)

        # Pair 2
        uni_pair2_layout = QtWidgets.QHBoxLayout()
        self.uni_pair2_label = QtWidgets.QLabel("Pair 2:")
        self.uni_pair2_e1 = QtWidgets.QLineEdit()
        self.uni_pair2_e1.setPlaceholderText("E12")
        self.uni_pair2_e2 = QtWidgets.QLineEdit()
        self.uni_pair2_e2.setPlaceholderText("E13")
        uni_pair2_layout.addWidget(self.uni_pair2_label)
        uni_pair2_layout.addWidget(self.uni_pair2_e1)
        uni_pair2_layout.addWidget(QtWidgets.QLabel("↔"))
        uni_pair2_layout.addWidget(self.uni_pair2_e2)
        uni_layout.addLayout(uni_pair2_layout)

        # Multipolar electrode pairs (four pairs)
        multi_widget = QtWidgets.QWidget()
        multi_layout = QtWidgets.QVBoxLayout(multi_widget)

        # Add a label for the multipolar electrode section
        multi_label = QtWidgets.QLabel("Multipolar Electrode Pairs:")
        multi_label.setStyleSheet("font-weight: bold;")
        multi_layout.addWidget(multi_label)

        # Create pairs for multipolar mode
        self.multi_pairs = []
        for i in range(1, 5):
            pair_layout = QtWidgets.QHBoxLayout()
            pair_label = QtWidgets.QLabel(f"Pair {i}:")
            e1 = QtWidgets.QLineEdit()
            e1.setPlaceholderText(f"E{10+2*(i-1)}")
            e2 = QtWidgets.QLineEdit()
            e2.setPlaceholderText(f"E{11+2*(i-1)}")

            pair_layout.addWidget(pair_label)
            pair_layout.addWidget(e1)
            pair_layout.addWidget(QtWidgets.QLabel("↔"))
            pair_layout.addWidget(e2)
            multi_layout.addLayout(pair_layout)

            # Store references
            self.multi_pairs.append((e1, e2))

        # Add the widgets to the stacked widget
        self.electrode_stack.addWidget(uni_widget)
        self.electrode_stack.addWidget(multi_widget)
        layout.addWidget(self.electrode_stack)

        # Add some spacing
        layout.addSpacing(10)

        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Add left widget to main layout
        main_layout.addWidget(left_widget)

        # Right side (electrode list panel)
        self.right_widget = QtWidgets.QWidget()
        self.right_widget.setVisible(False)  # Initially hidden
        right_layout = QtWidgets.QVBoxLayout(self.right_widget)

        # Add title for electrode list
        electrode_title = QtWidgets.QLabel("Available Electrodes")
        electrode_title.setStyleSheet(
            f"font-weight: bold; font-size: {FONT_SUBHEADING};"
        )
        right_layout.addWidget(electrode_title)

        # Add search box
        self.search_box = QtWidgets.QLineEdit()
        self.search_box.setPlaceholderText("Search electrodes...")
        self.search_box.textChanged.connect(self.filter_electrodes)
        right_layout.addWidget(self.search_box)

        # Add electrode list widget
        self.electrode_list = QtWidgets.QListWidget()
        self.electrode_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.electrode_list.setStyleSheet("""
            QListWidget {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #eee;
            }
        """)
        right_layout.addWidget(self.electrode_list)

        # Add right widget to main layout
        main_layout.addWidget(self.right_widget)

        # Connect net selection change to update electrode list
        self.net_combo.currentTextChanged.connect(self.update_electrode_list)

    def toggle_electrode_list(self):
        """Toggle the visibility of the electrode list panel."""
        if self.right_widget.isVisible():
            self.right_widget.setVisible(False)
            self.show_electrodes_btn.setText("Show Electrodes")
            self.resize(500, self.height())  # Return to original width
        else:
            self.right_widget.setVisible(True)
            self.show_electrodes_btn.setText("Hide Electrodes")
            self.resize(800, self.height())  # Expand width
            self.update_electrode_list()

    def update_electrode_list(self):
        """Update the list of available electrodes based on the selected net."""
        try:
            self.electrode_list.clear()
            net_file = self.net_combo.currentText()

            if not net_file:
                return

            # Get SimNIBS directory using path manager
            simnibs_dir = self.pm.path_optional("simnibs")
            if not simnibs_dir or not os.path.isdir(simnibs_dir):
                return

            subject_found = False

            # Look through all subject directories
            for subject_dir in os.listdir(simnibs_dir):
                if subject_dir.startswith("sub-"):
                    subject_id = subject_dir[4:]  # Remove 'sub-' prefix
                    m2m_dir = self.pm.path_optional("m2m", subject_id=subject_id)
                    if m2m_dir and os.path.isdir(m2m_dir):
                        # Use LeadfieldGenerator to get electrode names (handles both formats)
                        try:
                            from tit.opt.leadfield import LeadfieldGenerator

                            gen = LeadfieldGenerator(m2m_dir)

                            # Clean net file name (remove .csv extension if present)
                            clean_net_name = (
                                net_file.replace(".csv", "")
                                if net_file.endswith(".csv")
                                else net_file
                            )

                            # Get electrodes using the fixed method
                            electrodes = gen.get_electrode_names_from_cap(
                                cap_name=clean_net_name
                            )

                            if electrodes:
                                subject_found = True
                                # Add to list widget (already sorted by get_electrode_names_from_cap)
                                for electrode in electrodes:
                                    self.electrode_list.addItem(electrode)
                                break
                        except (FileNotFoundError, ValueError):
                            # Try next subject
                            continue

            if not subject_found:
                self.electrode_list.addItem("No electrode positions found")

        except Exception as e:
            self.electrode_list.addItem(f"Error loading electrodes: {str(e)}")

    def filter_electrodes(self, text):
        """Filter the electrode list based on search text."""
        for i in range(self.electrode_list.count()):
            item = self.electrode_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def get_montage_data(self):
        """Get montage data entered in the dialog."""
        name = self.name_input.text().strip()
        is_unipolar = self.mode_unipolar.isChecked()
        target_net = self.net_combo.currentText()

        electrode_pairs = []

        if is_unipolar:
            # Get unipolar pairs
            pair1_e1 = self.uni_pair1_e1.text().strip()
            pair1_e2 = self.uni_pair1_e2.text().strip()
            pair2_e1 = self.uni_pair2_e1.text().strip()
            pair2_e2 = self.uni_pair2_e2.text().strip()

            if pair1_e1 and pair1_e2:
                electrode_pairs.append([pair1_e1, pair1_e2])
            if pair2_e1 and pair2_e2:
                electrode_pairs.append([pair2_e1, pair2_e2])
        else:
            # Get multipolar pairs
            for e1, e2 in self.multi_pairs:
                e1_text = e1.text().strip()
                e2_text = e2.text().strip()
                if e1_text and e2_text:
                    electrode_pairs.append([e1_text, e2_text])

        return {
            "name": name,
            "is_unipolar": is_unipolar,
            "target_net": target_net,
            "electrode_pairs": electrode_pairs,
        }

    def update_electrode_inputs(self, checked):
        """Update the electrode input view based on the selected mode."""
        if checked:  # Unipolar selected
            self.electrode_stack.setCurrentIndex(0)
        else:  # Multipolar selected
            self.electrode_stack.setCurrentIndex(1)
