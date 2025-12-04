#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Optimize Tab - Combined interface for Ex-Search, Flex-Search, and MOVEA
"""

from PyQt5 import QtWidgets, QtCore


class OptimizerTab(QtWidgets.QWidget):
    """Combined tab for all optimization methods."""
    
    def __init__(self, parent=None):
        super(OptimizerTab, self).__init__(parent)
        self.parent = parent
        self.setup_ui()
    
    def setup_ui(self):
        """Set up the user interface."""
        main_layout = QtWidgets.QVBoxLayout(self)
        
        # Create a horizontal layout for the dropdown selector
        selector_layout = QtWidgets.QHBoxLayout()
        
        # Add label
        label = QtWidgets.QLabel("Select Optimization Method:")
        label.setStyleSheet("font-weight: bold; font-size: 14px;")
        selector_layout.addWidget(label)
        
        # Create dropdown menu
        self.method_combo = QtWidgets.QComboBox()
        self.method_combo.addItems(["Flex-Search; Weise et. al. 2025", "Ex-Search", "MOVEA; Wang et. al. 2023"])
        self.method_combo.setMinimumWidth(200)
        self.method_combo.currentIndexChanged.connect(self.on_method_changed)
        selector_layout.addWidget(self.method_combo)
        
        # Add stretch to push everything to the left
        selector_layout.addStretch()
        
        main_layout.addLayout(selector_layout)
        
        # Add a separator line
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        main_layout.addWidget(line)
        
        # Create a stacked widget to hold the three optimization tabs
        self.stacked_widget = QtWidgets.QStackedWidget()
        
        # Import and create the three optimization tabs
        from ex_search_tab import ExSearchTab
        from flex_search_tab import FlexSearchTab
        from movea_tab import MOVEATab
        
        self.ex_search_tab = ExSearchTab(self.parent)
        self.flex_search_tab = FlexSearchTab(self.parent)
        self.movea_tab = MOVEATab(self.parent)
        
        # Add them to the stacked widget
        self.stacked_widget.addWidget(self.flex_search_tab)
        self.stacked_widget.addWidget(self.ex_search_tab)
        self.stacked_widget.addWidget(self.movea_tab)
        
        main_layout.addWidget(self.stacked_widget)
        
        self.stacked_widget.setCurrentIndex(0)
    
    def on_method_changed(self, index):
        """Handle optimization method change."""
        self.stacked_widget.setCurrentIndex(index)

