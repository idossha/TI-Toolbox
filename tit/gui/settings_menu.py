#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Settings Menu - Gear icon menu for Help, Acknowledgments, and Contact
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from tit.gui.style import FONT_NOTE, _gfx_tokens  # graphics tokens


class FloatingGraphicsWindow(QtWidgets.QDialog):
    """Floating modal dialog for editing per-project graphics settings."""

    def __init__(self, parent=None):
        super(FloatingGraphicsWindow, self).__init__(parent)
        self.setWindowTitle("Graphics Settings")
        self.setMinimumSize(520, 440)
        self.setModal(True)
        self.setup_ui()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _project_loaded(self) -> bool:
        """Return True when PathManager is initialised (a project is open)."""
        try:
            from tit.gui.graphics_config import _config_path

            return _config_path() is not None
        except Exception:
            return False

    def _populate_from_config(self, config) -> None:
        """Fill all spin-boxes from *config*."""
        self._sb_width.setValue(config.window_width)
        self._sb_height.setValue(config.window_height)
        self._sb_console_min.setValue(config.console_min_height)
        self._sb_console_max.setValue(config.console_max_height)
        self._dsb_scale.setValue(config.font_scale)
        self._sb_body.setValue(config.font_size_body)
        self._sb_heading.setValue(config.font_size_heading)
        self._sb_console_font.setValue(config.font_size_console)
        self._sb_tab.setValue(config.font_size_tab)
        self._sb_font_sm.setValue(config.font_size_sm)
        self._sb_font_help.setValue(config.font_size_help)
        self._sb_font_section.setValue(config.font_size_section_title)
        self._sb_font_subheading.setValue(config.font_size_subheading)
        self._sb_font_monospace.setValue(config.font_size_monospace)
        self._sb_font_note.setValue(config.font_size_note)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def setup_ui(self):
        """Build the settings dialog layout."""
        from tit.gui.graphics_config import GraphicsConfig, get_graphics_config

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # ---- Warning label (shown when no project is open) ----------------
        self._warning_label = QtWidgets.QLabel(
            "Open a project first to save graphics settings."
        )
        self._warning_label.setStyleSheet(
            "QLabel { background-color: #FFD700; color: #5a4000;"
            " padding: 6px 10px; border-radius: 4px; font-weight: bold; }"
        )
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)
        main_layout.addWidget(self._warning_label)

        # ---- Scroll area --------------------------------------------------
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)

        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(4, 4, 4, 4)
        scroll_layout.setSpacing(12)

        # ---- Window Size group -------------------------------------------
        grp_window = QtWidgets.QGroupBox("Window Size")
        form_window = QtWidgets.QFormLayout(grp_window)
        form_window.setLabelAlignment(QtCore.Qt.AlignRight)

        self._sb_width = QtWidgets.QSpinBox()
        self._sb_width.setMinimum(100)
        self._sb_width.setMaximum(9999)
        self._sb_width.setSingleStep(10)

        self._sb_height = QtWidgets.QSpinBox()
        self._sb_height.setMinimum(100)
        self._sb_height.setMaximum(9999)
        self._sb_height.setSingleStep(10)

        form_window.addRow("Initial width (px):", self._sb_width)
        form_window.addRow("Initial height (px):", self._sb_height)
        scroll_layout.addWidget(grp_window)

        # ---- Console group -----------------------------------------------
        grp_console = QtWidgets.QGroupBox("Console")
        form_console = QtWidgets.QFormLayout(grp_console)
        form_console.setLabelAlignment(QtCore.Qt.AlignRight)

        self._sb_console_min = QtWidgets.QSpinBox()
        self._sb_console_min.setMinimum(0)
        self._sb_console_min.setMaximum(9999)

        self._sb_console_max = QtWidgets.QSpinBox()
        self._sb_console_max.setMinimum(0)
        self._sb_console_max.setMaximum(9999)

        form_console.addRow("Min height (px):", self._sb_console_min)
        form_console.addRow("Max height (px):", self._sb_console_max)
        scroll_layout.addWidget(grp_console)

        # ---- Font group --------------------------------------------------
        grp_font = QtWidgets.QGroupBox("Font")
        form_font = QtWidgets.QFormLayout(grp_font)
        form_font.setLabelAlignment(QtCore.Qt.AlignRight)

        self._dsb_scale = QtWidgets.QDoubleSpinBox()
        self._dsb_scale.setMinimum(0.1)
        self._dsb_scale.setMaximum(10.0)
        self._dsb_scale.setSingleStep(0.05)
        self._dsb_scale.setDecimals(2)

        self._sb_body = QtWidgets.QSpinBox()
        self._sb_body.setMinimum(1)
        self._sb_body.setMaximum(999)

        self._sb_heading = QtWidgets.QSpinBox()
        self._sb_heading.setMinimum(1)
        self._sb_heading.setMaximum(999)

        self._sb_console_font = QtWidgets.QSpinBox()
        self._sb_console_font.setMinimum(1)
        self._sb_console_font.setMaximum(999)

        self._sb_tab = QtWidgets.QSpinBox()
        self._sb_tab.setMinimum(1)
        self._sb_tab.setMaximum(999)

        self._sb_font_sm = QtWidgets.QSpinBox()
        self._sb_font_sm.setMinimum(1)
        self._sb_font_sm.setMaximum(999)

        self._sb_font_help = QtWidgets.QSpinBox()
        self._sb_font_help.setMinimum(1)
        self._sb_font_help.setMaximum(999)

        self._sb_font_section = QtWidgets.QSpinBox()
        self._sb_font_section.setMinimum(1)
        self._sb_font_section.setMaximum(999)

        self._sb_font_subheading = QtWidgets.QSpinBox()
        self._sb_font_subheading.setMinimum(1)
        self._sb_font_subheading.setMaximum(999)

        self._sb_font_monospace = QtWidgets.QSpinBox()
        self._sb_font_monospace.setMinimum(1)
        self._sb_font_monospace.setMaximum(999)

        self._sb_font_note = QtWidgets.QSpinBox()
        self._sb_font_note.setMinimum(1)
        self._sb_font_note.setMaximum(999)

        form_font.addRow("Scale (\u00d7):", self._dsb_scale)
        form_font.addRow("Body size (pt):", self._sb_body)
        form_font.addRow("Heading size (pt):", self._sb_heading)
        form_font.addRow("Console size (pt):", self._sb_console_font)
        form_font.addRow("Tab bar size (pt):", self._sb_tab)
        form_font.addRow("Hint text (pt):", self._sb_font_sm)
        form_font.addRow("Help text (pt):", self._sb_font_help)
        form_font.addRow("Section title (pt):", self._sb_font_section)
        form_font.addRow("Subheading (pt):", self._sb_font_subheading)
        form_font.addRow("Monospace (pt):", self._sb_font_monospace)
        form_font.addRow("Note / info (pt):", self._sb_font_note)
        scroll_layout.addWidget(grp_font)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)

        # ---- Note label --------------------------------------------------
        note_label = QtWidgets.QLabel("Changes apply on next launch.")
        note_label.setStyleSheet(
            f"QLabel {{ color: grey; font-style: italic; font-size: {FONT_NOTE}; }}"
        )
        note_label.setAlignment(QtCore.Qt.AlignCenter)
        main_layout.addWidget(note_label)

        # ---- Button row --------------------------------------------------
        btn_row = QtWidgets.QHBoxLayout()

        restore_btn = QtWidgets.QPushButton("Restore Defaults")
        restore_btn.clicked.connect(self._on_restore_defaults)
        btn_row.addWidget(restore_btn)

        btn_row.addStretch()

        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._save_btn = QtWidgets.QPushButton("Save")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        main_layout.addLayout(btn_row)

        # ---- Populate values and guard Save if no project open -----------
        config = get_graphics_config()
        self._loaded_config = config  # preserve removed-field values for _on_save
        self._populate_from_config(config)

        if not self._project_loaded():
            self._warning_label.setVisible(True)
            self._save_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_restore_defaults(self):
        """Reset all spin-boxes to compiled-in defaults (no disk write)."""
        from tit.gui.graphics_config import GraphicsConfig

        self._populate_from_config(GraphicsConfig())

    def _on_save(self):
        """Collect values, persist to disk, inform the user."""
        from tit.gui.graphics_config import GraphicsConfig, save_graphics_config

        _prev = self._loaded_config
        config = GraphicsConfig(
            window_width=self._sb_width.value(),
            window_height=self._sb_height.value(),
            console_min_height=self._sb_console_min.value(),
            console_max_height=self._sb_console_max.value(),
            font_scale=self._dsb_scale.value(),
            font_size_body=self._sb_body.value(),
            font_size_heading=self._sb_heading.value(),
            font_size_console=self._sb_console_font.value(),
            font_size_tab=self._sb_tab.value(),
            font_size_sm=self._sb_font_sm.value(),
            font_size_help=self._sb_font_help.value(),
            font_size_section_title=self._sb_font_section.value(),
            font_size_subheading=self._sb_font_subheading.value(),
            font_size_monospace=self._sb_font_monospace.value(),
            font_size_note=self._sb_font_note.value(),
            # Fields removed from UI — preserve whatever was previously saved.
            nifti_field_opacity=_prev.nifti_field_opacity,
            nifti_atlas_opacity=_prev.nifti_atlas_opacity,
            config_panel_max_height=_prev.config_panel_max_height,
            icon_size_gear=_prev.icon_size_gear,
            icon_size_extensions=_prev.icon_size_extensions,
        )

        try:
            save_graphics_config(config)
        except RuntimeError:
            # Project was closed between dialog open and Save — re-guard.
            self._warning_label.setVisible(True)
            self._save_btn.setEnabled(False)
            return

        QtWidgets.QMessageBox.information(
            self,
            "Saved",
            "Graphics settings saved.\nRestart the application to apply changes.",
        )
        self.accept()


class FloatingHelpWindow(QtWidgets.QDialog):
    """Floating window for Help content."""

    def __init__(self, parent=None):
        super(FloatingHelpWindow, self).__init__(parent)
        self.setWindowTitle("TI-Toolbox - Help")
        self.setMinimumSize(800, 600)
        self.setup_ui()

    def setup_ui(self):
        """Set up the help window UI."""
        from tit.gui.help_tab import HelpTab

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create the help tab content
        self.help_content = HelpTab(self)
        layout.addWidget(self.help_content)

        # Add a close button at the bottom
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)


class FloatingContactWindow(QtWidgets.QDialog):
    """Floating window for Contact content."""

    def __init__(self, parent=None):
        super(FloatingContactWindow, self).__init__(parent)
        self.setWindowTitle("TI-Toolbox - Contact")
        self.setMinimumSize(700, 500)
        self.setup_ui()

    def setup_ui(self):
        """Set up the contact window UI."""
        from tit.gui.contact_tab import ContactTab

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create the contact tab content
        self.contact_content = ContactTab(self)
        layout.addWidget(self.contact_content)

        # Add a close button at the bottom
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)


class FloatingAcknowledgmentsWindow(QtWidgets.QDialog):
    """Floating window for Acknowledgments content."""

    def __init__(self, parent=None):
        super(FloatingAcknowledgmentsWindow, self).__init__(parent)
        self.setWindowTitle("TI-Toolbox - Acknowledgments")
        self.setMinimumSize(700, 500)
        self.setup_ui()

    def setup_ui(self):
        """Set up the acknowledgments window UI."""
        from tit.gui.acknowledgments_tab import AcknowledgmentsTab

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create the acknowledgments tab content
        self.acknowledgments_content = AcknowledgmentsTab(self)
        layout.addWidget(self.acknowledgments_content)

        # Add a close button at the bottom
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        close_btn = QtWidgets.QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        button_layout.addStretch()
        layout.addLayout(button_layout)


class SettingsMenuButton(QtWidgets.QPushButton):
    """Gear icon button with dropdown menu for settings/info."""

    def __init__(self, parent=None):
        super(SettingsMenuButton, self).__init__(parent)
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        """Set up the gear button and menu."""
        # Set gear icon (using Unicode gear symbol)
        self.setText("⚙")  # Gear emoji/symbol
        self.setStyleSheet(
            f"""
            QPushButton {{
                font-size: {_gfx_tokens.icon_size_gear}px;
                border: none;
                background: transparent;
                padding: 5px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }}
            QPushButton::menu-indicator {{
                width: 0px;
            }}
        """
        )
        self.setToolTip("Settings and Information")
        self.setCursor(QtCore.Qt.PointingHandCursor)

        # Create the dropdown menu
        self.menu = QtWidgets.QMenu(self)

        # Add menu actions
        graphics_action = self.menu.addAction("Graphics...")
        graphics_action.triggered.connect(self.open_graphics)

        help_action = self.menu.addAction("Help")
        help_action.triggered.connect(self.open_help)

        contact_action = self.menu.addAction("Contact")
        contact_action.triggered.connect(self.open_contact)

        acknowledgments_action = self.menu.addAction("Acknowledgments")
        acknowledgments_action.triggered.connect(self.open_acknowledgments)

        # Set the menu to the button
        self.setMenu(self.menu)

    def open_graphics(self):
        """Open the Graphics Settings dialog (modal)."""
        graphics_window = FloatingGraphicsWindow(self.parent)
        graphics_window.exec_()

    def open_help(self):
        """Open the Help window."""
        help_window = FloatingHelpWindow(self.parent)
        help_window.show()

    def open_extensions(self):
        """Open the Extensions window."""
        from tit.gui.extensions import FloatingExtensionsWindow

        extensions_window = FloatingExtensionsWindow(
            self.parent, main_window=self.parent
        )
        extensions_window.show()

    def open_contact(self):
        """Open the Contact window."""
        contact_window = FloatingContactWindow(self.parent)
        contact_window.show()

    def open_acknowledgments(self):
        """Open the Acknowledgments window."""
        acknowledgments_window = FloatingAcknowledgmentsWindow(self.parent)
        acknowledgments_window.show()


class ExtensionsButton(QtWidgets.QPushButton):
    """Extensions icon button for opening extensions window."""

    def __init__(self, parent=None):
        super(ExtensionsButton, self).__init__(parent)
        self.parent = parent
        self.setup_ui()

    def setup_ui(self):
        """Set up the extensions button."""
        # Set extensions icon (using Unicode symbol compatible with Ubuntu containers)
        self.setText(
            "◳"
        )  # Square with top right quadrant - represents extensions/modules
        self.setStyleSheet(
            f"""
            QPushButton {{
                font-size: {_gfx_tokens.icon_size_extensions}px;
                font-weight: bold;
                border: none;
                background: transparent;
                padding: 5px;
            }}
            QPushButton:hover {{
                background: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }}
        """
        )
        self.setToolTip("Extensions")
        self.setCursor(QtCore.Qt.PointingHandCursor)

        # Connect click to open extensions
        self.clicked.connect(self.open_extensions)

    def open_extensions(self):
        """Open the Extensions window."""
        from tit.gui.extensions import FloatingExtensionsWindow

        extensions_window = FloatingExtensionsWindow(
            self.parent, main_window=self.parent
        )
        extensions_window.show()
