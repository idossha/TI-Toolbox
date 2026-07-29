#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
ROI Picker Widget Component
Reusable ROI selection widget with spherical/atlas/subcortical modes.
"""

import os
import subprocess
from pathlib import Path

from PyQt5 import QtWidgets, QtCore

from tit.paths import get_path_manager
from tit.atlas import MNI_ATLAS_DIR, MeshAtlasManager, VoxelAtlasManager
from tit.gui.components.atlas_region_finder import AtlasRegionFinderDialog
from tit.gui.components.region_chips import RegionChipsWidget
from tit.opt.config import FlexConfig


class ROIPickerWidget(QtWidgets.QWidget):
    """Reusable ROI selection widget with spherical/atlas/subcortical modes.

    Provides a self-contained composite widget that handles ROI selection
    with three modes: spherical (coordinates and radius), cortical (surface
    atlas annotation), and subcortical (volumetric atlas).

    Signals:
        roi_changed: Emitted whenever any ROI input value changes.
    """

    roi_changed = QtCore.pyqtSignal()

    def __init__(
        self,
        parent=None,
        label="ROI",
        enable_spherical=True,
        enable_atlas=True,
        enable_subcortical=True,
        enable_freeview_button=True,
        enable_mni_toggle=True,
    ):
        """Initialize the ROI picker widget.

        Args:
            parent: Parent widget.
            label: Label text shown for the ROI group (not currently displayed
                as a group box title, but stored for identification).
            enable_spherical: Whether spherical mode radio is available.
            enable_atlas: Whether cortical (atlas) mode radio is available.
            enable_subcortical: Whether subcortical mode radio is available.
            enable_freeview_button: Whether to show the Freeview launch button
                in spherical mode.
            enable_mni_toggle: Whether to show the Subject/MNI coordinate
                space toggle in spherical mode.
        """
        super().__init__(parent)
        self._label = label
        self._enable_spherical = enable_spherical
        self._enable_atlas = enable_atlas
        self._enable_subcortical = enable_subcortical
        self._enable_freeview_button = enable_freeview_button
        self._enable_mni_toggle = enable_mni_toggle

        # Atlas data caches (populated by set_subject)
        self.atlases: dict = {}  # (hemi, name) -> path
        self.volume_atlases: dict = {}  # name -> path
        self.atlas_display_map: dict = {}  # display name -> full atlas name

        # Subject context (set by set_subject)
        self._subject_id: str | None = None
        self._project_dir: str | None = None

        # Atlas/space the current chips belong to, so re-selecting the SAME
        # value in a combo does not needlessly wipe the selection.
        self._last_cortical_atlas = None
        self._last_volume_key = None

        self._setup_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        """Build the widget tree."""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Radio buttons row ---
        radio_container = QtWidgets.QWidget()
        radio_layout = QtWidgets.QHBoxLayout(radio_container)
        radio_layout.setContentsMargins(0, 0, 0, 0)

        self._mode_group = QtWidgets.QButtonGroup(self)
        self._radios = []

        # Display / stacked order: Cortical (default), Subcortical, Spherical.
        # Button ids match the stacked-page indices below.
        if self._enable_atlas:
            self.radio_cortical = QtWidgets.QRadioButton("Cortical")
            radio_layout.addWidget(self.radio_cortical)
            self._mode_group.addButton(self.radio_cortical, 0)
            self._radios.append(self.radio_cortical)
        else:
            self.radio_cortical = None

        if self._enable_subcortical:
            self.radio_subcortical = QtWidgets.QRadioButton("Subcortical")
            radio_layout.addWidget(self.radio_subcortical)
            self._mode_group.addButton(self.radio_subcortical, 1)
            self._radios.append(self.radio_subcortical)
        else:
            self.radio_subcortical = None

        if self._enable_spherical:
            self.radio_spherical = QtWidgets.QRadioButton(
                "Spherical (coordinates and radius)"
            )
            radio_layout.addWidget(self.radio_spherical)
            self._mode_group.addButton(self.radio_spherical, 2)
            self._radios.append(self.radio_spherical)
        else:
            self.radio_spherical = None

        radio_layout.addStretch()

        # Default: first enabled mode is checked (Cortical when available)
        if self._radios:
            self._radios[0].setChecked(True)

        main_layout.addWidget(radio_container)

        # --- Stacked widget ---
        self.stacked = QtWidgets.QStackedWidget()

        # Page 0 — Cortical (Atlas)
        self._cortical_page = self._build_cortical_page()
        self.stacked.addWidget(self._cortical_page)

        # Page 1 — Subcortical (Volume)
        self._subcortical_page = self._build_subcortical_page()
        self.stacked.addWidget(self._subcortical_page)

        # Page 2 — Spherical
        self._spherical_page = self._build_spherical_page()
        self.stacked.addWidget(self._spherical_page)

        # Keep the stack sized to the current page (see _resize_stack_to_current).
        self.stacked.currentChanged.connect(self._resize_stack_to_current)

        # Set initial page
        if self._radios:
            checked_id = self._mode_group.checkedId()
            self.stacked.setCurrentIndex(max(0, checked_id))

        main_layout.addWidget(self.stacked)

        # Collapse non-current pages so the stack hugs the initial page height.
        self._resize_stack_to_current()

    def _build_spherical_page(self) -> QtWidgets.QWidget:
        """Build the spherical ROI input page.

        All spheres live in a single full-width table (one row per sphere). A
        single row reproduces the classic single-sphere behavior; extra rows
        union into one combined target.
        """
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setSpacing(5)
        layout.setContentsMargins(0, 5, 0, 5)

        # Coordinate space toggle
        if self._enable_mni_toggle:
            space_widget = QtWidgets.QWidget()
            space_layout = QtWidgets.QHBoxLayout(space_widget)
            space_layout.setContentsMargins(0, 0, 0, 0)
            space_layout.addWidget(QtWidgets.QLabel("Coordinate Space:"))
            self.space_subject_radio = QtWidgets.QRadioButton("Subject Space")
            self.space_mni_radio = QtWidgets.QRadioButton("MNI Space")
            self.space_subject_radio.setChecked(True)
            space_layout.addWidget(self.space_subject_radio)
            space_layout.addWidget(self.space_mni_radio)
            space_layout.addStretch()
            layout.addWidget(space_widget)
        else:
            self.space_subject_radio = None
            self.space_mni_radio = None

        self.mni_info_label = None

        # Header row: coordinate-space label + Freeview button
        header_widget = QtWidgets.QWidget()
        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.coords_label = QtWidgets.QLabel("ROI Center RAS Coordinates (mm):")
        header_layout.addWidget(self.coords_label)
        header_layout.addStretch()

        if self._enable_freeview_button:
            self.view_t1_btn = QtWidgets.QPushButton("View T1 in Freeview")
            self.view_t1_btn.setToolTip(
                "Open subject's T1 scan in Freeview to find RAS coordinates"
            )
            header_layout.addWidget(self.view_t1_btn)
        else:
            self.view_t1_btn = None

        layout.addWidget(header_widget)

        # Unified spheres table — every sphere is a row.
        self.spheres_table = QtWidgets.QTableWidget(0, 5)
        self.spheres_table.setHorizontalHeaderLabels(
            ["X (mm)", "Y (mm)", "Z (mm)", "Radius (mm)", ""]
        )
        sph_header = self.spheres_table.horizontalHeader()
        for col in range(4):
            sph_header.setSectionResizeMode(col, QtWidgets.QHeaderView.Stretch)
        sph_header.setSectionResizeMode(4, QtWidgets.QHeaderView.Fixed)
        self.spheres_table.setColumnWidth(4, 40)
        self.spheres_table.verticalHeader().setVisible(True)
        self.spheres_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.spheres_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.spheres_table.setMinimumHeight(190)
        self.spheres_table.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self.spheres_table.setToolTip(
            "Each row is a sphere. Multiple rows union into one combined target; "
            "a single row is a plain single-sphere ROI (unchanged behavior)."
        )
        layout.addWidget(self.spheres_table)

        # Sphere management buttons
        sphere_btn_widget = QtWidgets.QWidget()
        sphere_btn_layout = QtWidgets.QHBoxLayout(sphere_btn_widget)
        sphere_btn_layout.setContentsMargins(0, 0, 0, 0)
        self.add_sphere_btn = QtWidgets.QPushButton("Add Sphere")
        self.add_sphere_btn.setToolTip("Union another sphere into this ROI.")
        self.duplicate_sphere_btn = QtWidgets.QPushButton("Duplicate Selected")
        self.duplicate_sphere_btn.setToolTip(
            "Copy the selected sphere row(s) as new rows."
        )
        self.remove_sphere_btn = QtWidgets.QPushButton("Remove Selected")
        self.remove_sphere_btn.setToolTip("Remove the selected sphere row(s).")
        sphere_btn_layout.addWidget(self.add_sphere_btn)
        sphere_btn_layout.addWidget(self.duplicate_sphere_btn)
        sphere_btn_layout.addWidget(self.remove_sphere_btn)
        sphere_btn_layout.addStretch()
        layout.addWidget(sphere_btn_widget)

        # Volumetric toggle + tissue type
        vol_widget = QtWidgets.QWidget()
        vol_layout = QtWidgets.QHBoxLayout(vol_widget)
        vol_layout.setContentsMargins(0, 0, 0, 0)

        self.volumetric_checkbox = QtWidgets.QCheckBox("Volumetric")
        self.volumetric_checkbox.setToolTip(
            "Evaluate field on volume tetrahedra instead of the cortical surface. "
            "Use this for deep/subcortical targets (e.g. amygdala, hippocampus) "
            "where surface-only evaluation would capture overlying cortex."
        )
        vol_layout.addWidget(self.volumetric_checkbox)

        self.sphere_tissue_label = QtWidgets.QLabel("Tissue:")
        self.sphere_tissue_label.setEnabled(False)
        vol_layout.addWidget(self.sphere_tissue_label)

        self.sphere_tissue_combo = QtWidgets.QComboBox()
        self.sphere_tissue_combo.addItem("Gray Matter (GM)", "GM")
        self.sphere_tissue_combo.addItem("White Matter (WM)", "WM")
        self.sphere_tissue_combo.addItem("GM + WM (both)", "both")
        self.sphere_tissue_combo.setToolTip(
            "Tissue compartment(s) to include when evaluating the volumetric sphere. "
            "GM is appropriate for most targets."
        )
        self.sphere_tissue_combo.setEnabled(False)
        vol_layout.addWidget(self.sphere_tissue_combo)

        vol_layout.addStretch()
        layout.addWidget(vol_widget)

        # Wire checkbox to enable/disable tissue combo
        self.volumetric_checkbox.toggled.connect(self.sphere_tissue_combo.setEnabled)
        self.volumetric_checkbox.toggled.connect(self.sphere_tissue_label.setEnabled)

        # Seed one default sphere so the table is never empty.
        self._add_sphere_row()

        return page

    def _build_cortical_page(self) -> QtWidgets.QWidget:
        """Build the cortical (atlas annotation) ROI input page.

        Selected regions are shown as removable chips (:class:`RegionChipsWidget`)
        rather than typed free-text. Each chip carries a hemisphere-prefixed
        region *name* (e.g. ``lh.precentral``) as its key and displays both the
        name and its ``.annot`` label index. Regions are added via the
        "List Regions" finder (which lists both hemispheres by name); the
        hemisphere is carried in each name, so there is no separate hemisphere
        selector.
        """
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.setVerticalSpacing(3)
        layout.setContentsMargins(0, 5, 0, 5)

        # Atlas combo + refresh + list regions
        atlas_widget = QtWidgets.QWidget()
        atlas_layout = QtWidgets.QHBoxLayout(atlas_widget)
        atlas_layout.setContentsMargins(0, 0, 0, 0)

        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        atlas_layout.addWidget(self.atlas_combo)

        self.refresh_atlases_btn = QtWidgets.QPushButton("Refresh")
        atlas_layout.addWidget(self.refresh_atlases_btn)

        self.list_regions_btn = QtWidgets.QPushButton("List Regions")
        atlas_layout.addWidget(self.list_regions_btn)

        self.clear_regions_btn = QtWidgets.QPushButton("Clear")
        self.clear_regions_btn.setToolTip("Remove all selected cortical regions.")
        atlas_layout.addWidget(self.clear_regions_btn)

        atlas_layout.addStretch()
        layout.addRow(QtWidgets.QLabel("Atlas:"), atlas_widget)

        # Selected region(s) shown as removable chips. Regions are added via
        # "List Regions" (both hemispheres, by name), de-duplicated by chip key
        # ("hemi.name"). Multiple regions union into one combined target.
        self.cortical_chips = RegionChipsWidget(
            placeholder="No regions selected — use List Regions…"
        )
        self.cortical_chips.setToolTip(
            "Selected cortical regions. Use 'List Regions' to add hemisphere-"
            "prefixed regions (e.g. lh.precentral); each chip shows the name and "
            "its .annot label index. Multiple regions union into one combined "
            "target; press ✕ on a chip to remove it."
        )
        layout.addRow(QtWidgets.QLabel("Region(s):"), self.cortical_chips)

        return page

    def _build_subcortical_page(self) -> QtWidgets.QWidget:
        """Build the subcortical (volumetric atlas) ROI input page."""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.setVerticalSpacing(3)
        layout.setContentsMargins(0, 5, 0, 5)

        # Atlas space (subject / MNI) toggle — kept at the top.
        source_widget = QtWidgets.QWidget()
        source_layout = QtWidgets.QHBoxLayout(source_widget)
        source_layout.setContentsMargins(0, 0, 0, 0)

        self.volume_subject_radio = QtWidgets.QRadioButton("Subject Space")
        self.volume_mni_radio = QtWidgets.QRadioButton("MNI Space")
        self.volume_subject_radio.setChecked(True)
        self._volume_space_group = QtWidgets.QButtonGroup(self)
        self._volume_space_group.addButton(self.volume_subject_radio)
        self._volume_space_group.addButton(self.volume_mni_radio)
        self.volume_mni_radio.setToolTip(
            "Use an atlas from resources/atlas in MNI space. SimNIBS transforms "
            "the selected label to subject space during flex optimization."
        )
        source_layout.addWidget(self.volume_subject_radio)
        source_layout.addWidget(self.volume_mni_radio)
        source_layout.addStretch()
        layout.addRow(QtWidgets.QLabel("Atlas Space:"), source_widget)

        # Tissue type — placed above the volume atlas selector.
        self.tissue_combo = QtWidgets.QComboBox()
        self.tissue_combo.addItem("Gray Matter (GM)", "GM")
        self.tissue_combo.addItem("White Matter (WM)", "WM")
        self.tissue_combo.addItem("GM + WM (both)", "both")
        self.tissue_combo.setToolTip(
            "Tissue compartment(s) to include when evaluating the volume ROI. "
            "GM is appropriate for most subcortical targets (e.g. thalamus, "
            "hippocampus). WM or Both can be used when the target overlaps "
            "white-matter tracts."
        )
        layout.addRow(QtWidgets.QLabel("Tissue Type:"), self.tissue_combo)

        # Volume atlas combo + refresh + list regions + clear.
        volume_widget = QtWidgets.QWidget()
        volume_layout = QtWidgets.QHBoxLayout(volume_widget)
        volume_layout.setContentsMargins(0, 0, 0, 0)

        self.volume_atlas_combo = QtWidgets.QComboBox()
        self.volume_atlas_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        volume_layout.addWidget(self.volume_atlas_combo)

        self.refresh_volume_btn = QtWidgets.QPushButton("Refresh")
        volume_layout.addWidget(self.refresh_volume_btn)

        self.list_volume_regions_btn = QtWidgets.QPushButton("List Regions")
        volume_layout.addWidget(self.list_volume_regions_btn)

        self.clear_volume_regions_btn = QtWidgets.QPushButton("Clear")
        self.clear_volume_regions_btn.setToolTip(
            "Remove all selected subcortical regions."
        )
        volume_layout.addWidget(self.clear_volume_regions_btn)

        volume_layout.addStretch()
        layout.addRow(QtWidgets.QLabel("Volume Atlas:"), volume_widget)

        # Selected region(s) shown as removable chips, below the volume atlas.
        # Regions are added via "List Regions" (present labels, by name),
        # de-duplicated by chip key (the integer atlas label id). Multiple
        # regions union into one target.
        self.subcortical_chips = RegionChipsWidget(
            placeholder="No regions selected — use List Regions…"
        )
        self.subcortical_chips.setToolTip(
            "Selected subcortical regions. Use 'List Regions' to add atlas "
            "labels by name (e.g. Left-Hippocampus); each chip shows the name "
            "and its integer label id. Multiple regions union into one combined "
            "target (e.g. 17,53 = both hippocampi); press ✕ on a chip to remove "
            "it."
        )
        layout.addRow(QtWidgets.QLabel("Region(s):"), self.subcortical_chips)

        return page

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self):
        """Wire up internal signals."""
        # Mode switching
        self._mode_group.buttonClicked.connect(self._on_mode_changed)

        # Coordinate space toggle
        if self.space_subject_radio is not None:
            self.space_subject_radio.toggled.connect(
                self._update_coordinate_space_labels
            )
            self.space_mni_radio.toggled.connect(self._update_coordinate_space_labels)

        # Freeview button
        if self.view_t1_btn is not None:
            self.view_t1_btn.clicked.connect(self.load_t1_in_freeview)

        # Atlas refresh / list buttons
        self.refresh_atlases_btn.clicked.connect(self._refresh_cortical_atlases)
        self.list_regions_btn.clicked.connect(self._on_list_atlas_regions)
        self.refresh_volume_btn.clicked.connect(self._refresh_volume_atlases)
        self.list_volume_regions_btn.clicked.connect(self._on_list_volume_regions)
        self.volume_subject_radio.toggled.connect(self._refresh_volume_atlases)
        self.volume_mni_radio.toggled.connect(self._refresh_volume_atlases)

        # Clear buttons drop the whole current selection.
        self.clear_regions_btn.clicked.connect(self.cortical_chips.clear)
        self.clear_volume_regions_btn.clicked.connect(self.subcortical_chips.clear)

        # No cross-atlas mixing: regions are atlas-specific, so switching the
        # cortical atlas, the volume atlas, or the volume atlas space starts a
        # fresh selection. These are wired to *user-only* signals
        # (QComboBox.activated / QButtonGroup.buttonClicked) rather than
        # currentIndexChanged / toggled, so programmatic repopulation during a
        # refresh does not spuriously wipe a restored selection.
        self.atlas_combo.activated.connect(self._on_cortical_atlas_changed)
        self.volume_atlas_combo.activated.connect(self._on_volume_atlas_changed)
        self._volume_space_group.buttonClicked.connect(self._on_volume_atlas_changed)

        # Multi-sphere add/duplicate/remove (lambdas so the button's bool
        # 'checked' arg is not passed as a coordinate/row argument).
        self.add_sphere_btn.clicked.connect(lambda: self._add_sphere_row())
        self.duplicate_sphere_btn.clicked.connect(
            lambda: self._duplicate_selected_sphere_rows()
        )
        self.remove_sphere_btn.clicked.connect(
            lambda: self._remove_selected_sphere_rows()
        )

        # Emit roi_changed on any value change (per-row sphere spin boxes wire
        # themselves in _add_sphere_row).
        self.volumetric_checkbox.toggled.connect(self.roi_changed)
        self.sphere_tissue_combo.currentIndexChanged.connect(self.roi_changed)
        self.atlas_combo.currentIndexChanged.connect(self.roi_changed)
        self.cortical_chips.changed.connect(self.roi_changed)
        self.volume_atlas_combo.currentIndexChanged.connect(self.roi_changed)
        self.volume_subject_radio.toggled.connect(self.roi_changed)
        self.volume_mni_radio.toggled.connect(self.roi_changed)
        self.subcortical_chips.changed.connect(self.roi_changed)
        self.tissue_combo.currentIndexChanged.connect(self.roi_changed)
        self._mode_group.buttonClicked.connect(lambda: self.roi_changed.emit())

    def _on_cortical_atlas_changed(self, *_):
        """Clear the cortical region chips when the user picks a new atlas.

        Region names/indices are specific to a parcellation, so a chip added
        under one atlas is meaningless under another; switching atlases must
        start fresh. Wired to ``activated`` (user-only), so a programmatic
        repopulation during refresh does not clear a restored selection.
        """
        atlas = self.atlas_combo.currentText()
        if atlas == self._last_cortical_atlas:
            return
        self._last_cortical_atlas = atlas
        self.cortical_chips.clear()

    def _on_volume_atlas_changed(self, *_):
        """Clear the subcortical region chips when the user picks a new volume
        atlas or switches the atlas space (subject/MNI).

        Label ids are specific to a given atlas volume, so mixing regions across
        atlases/spaces is invalid; changing either starts fresh. Wired to
        user-only signals (``activated`` / ``buttonClicked``), so programmatic
        repopulation during refresh does not clear a restored selection.
        """
        space = "mni" if self.volume_mni_radio.isChecked() else "subject"
        key = (space, self.volume_atlas_combo.currentText())
        if key == self._last_volume_key:
            return
        self._last_volume_key = key
        self.subcortical_chips.clear()

    # ------------------------------------------------------------------
    # Mode switching
    # ------------------------------------------------------------------

    def _on_mode_changed(self, button):
        """Handle ROI mode radio button change."""
        checked_id = self._mode_group.checkedId()
        self.stacked.setCurrentIndex(max(0, checked_id))

        # Show/hide Freeview button (only visible in spherical mode)
        if self.view_t1_btn is not None:
            self.view_t1_btn.setVisible(self.get_roi_type() == "spherical")

        self._update_coordinate_space_labels()

    def _resize_stack_to_current(self, index=None):
        """Size the stacked widget to the current page instead of the tallest.

        A ``QStackedWidget`` normally reserves the height of its tallest page
        (here the spherical spheres-table page), leaving large empty space on
        the compact cortical/subcortical pages. Collapsing every non-current
        page's vertical size policy to ``Ignored`` (and keeping the current
        page ``Preferred``) makes the stack size to whichever page is showing.
        The spherical table keeps its own minimum height, so it still gets
        adequate room when active.

        Args:
            index: Unused; accepted so this can be wired to ``currentChanged``.
        """
        current = self.stacked.currentWidget()
        for i in range(self.stacked.count()):
            page = self.stacked.widget(i)
            if page is None:
                continue
            policy = page.sizePolicy()
            policy.setVerticalPolicy(
                QtWidgets.QSizePolicy.Preferred
                if page is current
                else QtWidgets.QSizePolicy.Ignored
            )
            page.setSizePolicy(policy)
        if current is not None:
            current.adjustSize()
        self.stacked.updateGeometry()
        self.stacked.adjustSize()
        self.updateGeometry()

    def _update_coordinate_space_labels(self):
        """Update coordinate labels and tooltips based on space selection."""
        if self.get_roi_type() != "spherical":
            return

        if self.is_mni_space():
            self.coords_label.setText("ROI Center MNI Coordinates (mm):")
            self.coords_label.setToolTip(
                "MNI space coordinates (will be transformed to subject space "
                "for each subject)"
            )
            self.coords_label.setStyleSheet("color: #007ACC; font-weight: bold;")
            if self.view_t1_btn is not None:
                self.view_t1_btn.setText("View MNI Template")
                self.view_t1_btn.setToolTip(
                    "Open MNI152 template to find MNI coordinates"
                )
        else:
            self.coords_label.setText("ROI Center RAS Coordinates (mm):")
            self.coords_label.setToolTip("Subject-specific RAS coordinates")
            self.coords_label.setStyleSheet("")
            if self.view_t1_btn is not None:
                self.view_t1_btn.setText("View T1 in Freeview")
                self.view_t1_btn.setToolTip(
                    "Open subject's T1 scan in Freeview to find RAS coordinates"
                )

    # ------------------------------------------------------------------
    # Multi-sphere / multi-label helpers
    # ------------------------------------------------------------------

    def _add_sphere_row(
        self, x: float = 0.0, y: float = 0.0, z: float = 0.0, r: float = 10.0
    ):
        """Append a sphere row (X/Y/Z/Radius spin boxes + delete button)."""
        table = self.spheres_table
        row = table.rowCount()
        table.insertRow(row)
        specs = [(-150, 150, x), (-150, 150, y), (-150, 150, z), (1, 50, r)]
        for col, (lo, hi, val) in enumerate(specs):
            spin = QtWidgets.QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setDecimals(2)
            spin.setValue(val)
            spin.valueChanged.connect(self.roi_changed)
            table.setCellWidget(row, col, spin)

        del_btn = QtWidgets.QPushButton("✕")
        del_btn.setFixedWidth(32)
        del_btn.setToolTip("Remove this sphere.")
        del_btn.clicked.connect(lambda: self._remove_sphere_row_widget(del_btn))
        table.setCellWidget(row, 4, del_btn)

        self.roi_changed.emit()

    def _row_values(self, row: int) -> tuple[float, float, float, float] | None:
        """Return ``(x, y, z, radius)`` for a table row, or ``None`` if empty."""
        table = self.spheres_table
        widgets = [table.cellWidget(row, col) for col in range(4)]
        if any(w is None for w in widgets):
            return None
        xw, yw, zw, rw = widgets
        return xw.value(), yw.value(), zw.value(), rw.value()

    def _remove_sphere_at(self, row: int):
        """Remove the sphere at ``row``, always keeping at least one row."""
        table = self.spheres_table
        if table.rowCount() <= 1:
            return
        table.removeRow(row)
        self.roi_changed.emit()

    def _remove_sphere_row_widget(self, button: QtWidgets.QPushButton):
        """Remove the row whose trailing delete button is ``button``.

        Rows shift as siblings are removed, so the owning row is resolved by
        widget identity rather than a captured index.
        """
        table = self.spheres_table
        for row in range(table.rowCount()):
            if table.cellWidget(row, 4) is button:
                self._remove_sphere_at(row)
                return

    def _remove_selected_sphere_rows(self):
        """Remove the selected sphere rows, always keeping at least one row."""
        table = self.spheres_table
        rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        changed = False
        for row in rows:
            if table.rowCount() <= 1:
                break
            table.removeRow(row)
            changed = True
        if changed:
            self.roi_changed.emit()

    def _duplicate_selected_sphere_rows(self):
        """Append a copy of each selected sphere row (last row if none selected)."""
        table = self.spheres_table
        rows = sorted({idx.row() for idx in table.selectedIndexes()})
        if not rows and table.rowCount():
            rows = [table.rowCount() - 1]
        # Snapshot values first so appended rows are not re-copied.
        values = [self._row_values(row) for row in rows]
        for vals in values:
            if vals is None:
                continue
            x, y, z, r = vals
            self._add_sphere_row(x, y, z, r)

    def _collect_spheres(self) -> tuple[list[list[float]], list[float]]:
        """Return ``(centers, radii)`` for every sphere row in the table.

        A single row reproduces the pre-union behavior exactly. If the table is
        somehow empty, a single default sphere is returned so callers always see
        at least one sphere.
        """
        centers: list[list[float]] = []
        radii: list[float] = []
        table = self.spheres_table
        for row in range(table.rowCount()):
            vals = self._row_values(row)
            if vals is None:
                continue
            x, y, z, r = vals
            centers.append([x, y, z])
            radii.append(r)
        if not centers:
            centers = [[0.0, 0.0, 0.0]]
            radii = [10.0]
        return centers, radii

    def set_spheres(
        self,
        centers: list[list[float]],
        radii: list[float],
    ):
        """Repopulate the spheres table from saved coordinates and radii.

        The inverse of :meth:`_collect_spheres`: clears existing rows and adds
        one row per ``(center, radius)`` pair. When no spheres are supplied a
        single default row is seeded so the table is never empty.

        Args:
            centers: Sequence of ``[x, y, z]`` coordinate triples.
            radii: Sequence of radii, one per center.
        """
        table = self.spheres_table
        table.setRowCount(0)
        if not centers:
            self._add_sphere_row()
            return
        for center, radius in zip(centers, radii):
            x, y, z = center
            self._add_sphere_row(float(x), float(y), float(z), float(radius))

    def set_cortical_regions(self, names: list[str]):
        """Repopulate the cortical region chips from saved region names.

        The inverse of the cortical branch of :meth:`get_roi_params`: replaces
        every chip with one per hemisphere-prefixed name. Where the current
        atlas annotation resolves a name to its ``.annot`` label index the chip
        shows both name and index; otherwise the name is shown alone.

        Args:
            names: Sequence of ``"hemi.name"`` tokens (e.g. ``"lh.precentral"``).
        """
        name_map = self._cortical_name_index_map()
        items: list[tuple[str, str]] = []
        for token in names:
            token = str(token).strip()
            if not token:
                continue
            display = token
            hemi, sep, name = token.partition(".")
            if sep == ".":
                index = name_map.get((hemi, name))
                if index is not None:
                    display = f"{token} · {index}"
            items.append((token, display))
        self.cortical_chips.set_items(items)

    def set_subcortical_regions(self, ids: list):
        """Repopulate the subcortical region chips from saved label ids.

        The inverse of the subcortical branch of :meth:`get_roi_params`:
        replaces every chip with one per integer atlas label id. Where the
        current volume atlas resolves an id to a region name the chip shows
        both name and id; otherwise the id is shown alone.

        Args:
            ids: Sequence of integer atlas label ids (ints or numeric strings).
        """
        id_name = self._subcortical_id_name_map()
        items: list[tuple[str, str]] = []
        for value in ids:
            token = str(value).strip()
            if not token:
                continue
            name = None
            if token.lstrip("-").isdigit():
                name = id_name.get(int(token))
            display = f"{name} · {token}" if name else token
            items.append((token, display))
        self.subcortical_chips.set_items(items)

    @staticmethod
    def _parse_region_names(text: str) -> list[tuple[str, str]]:
        """Parse comma-separated hemisphere-prefixed cortical region names.

        Accepts analyzer-style tokens such as ``lh.precentral`` or
        ``rh.superiorfrontal``.

        Returns:
            List of ``(hemisphere, region_name)`` tuples, e.g.
            ``("lh", "precentral")``.

        Raises:
            ValueError: If any non-empty token is not of the form
                ``lh.<name>`` or ``rh.<name>``.
        """
        tokens: list[tuple[str, str]] = []
        for part in text.split(","):
            part = part.strip()
            if not part:
                continue
            hemi, sep, name = part.partition(".")
            if sep != "." or hemi not in ("lh", "rh") or not name:
                raise ValueError(f"Invalid cortical region name: {part!r}")
            tokens.append((hemi, name))
        return tokens

    def _cortical_name_index_map(self) -> dict[tuple[str, str], int]:
        """Map ``(hemi, region_name) -> annot label index`` for the current atlas.

        Built from the cached lh/rh ``.annot`` files discovered for the current
        subject. Region label indices are intrinsic to an atlas parcellation
        (the ``.annot`` colour-table ordering), so the same indices apply to
        every subject sharing that atlas. Returns an empty dict when the atlas
        files cannot be read (e.g. no subject set yet).
        """
        atlas_display = self.atlas_combo.currentText()
        mapping: dict[tuple[str, str], int] = {}
        for hemi in ("lh", "rh"):
            annot_file = self.atlases.get((hemi, atlas_display))
            if not annot_file:
                continue
            try:
                regions = MeshAtlasManager("").list_annot_regions(annot_file)
            except (OSError, ValueError):
                continue
            for idx, name in regions:
                mapping[(hemi, name)] = idx
        return mapping

    def _subcortical_id_name_map(self) -> dict[int, str]:
        """Map ``label_id -> region name`` for the currently selected volume atlas.

        Resolves names from a sidecar LUT when present, otherwise from the
        atlas volume's own integer labels via the bundled FreeSurfer colour
        table (Agent A's resolver, :meth:`_resolve_volume_label_entries`).
        Returns an empty dict when the atlas cannot be read (e.g. no subject
        set yet); callers fall back to showing the bare id.
        """
        atlas_path = self.volume_atlas_combo.currentData()
        if not atlas_path:
            return {}
        atlas_path = str(atlas_path)
        mapping: dict[int, str] = {}
        try:
            lut_file = self._find_volume_lut(atlas_path)
            if lut_file is not None:
                with open(lut_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parsed = self._parse_lut_line(line)
                        if parsed is None:
                            continue
                        label_id, label_name, _ = parsed
                        mapping[int(label_id)] = label_name
            else:
                for label_id, name, _ in self._resolve_volume_label_entries(atlas_path):
                    mapping[int(label_id)] = name
        except Exception:
            # nibabel can raise ImageFileError (not an OSError) on an unreadable
            # atlas; match the finder path and degrade to bare-id chips.
            return {}
        return mapping

    @staticmethod
    def _parse_labels(text: str) -> list[int]:
        """Parse comma-separated integer atlas labels (mirrors analyzer input).

        Raises:
            ValueError: If any non-empty token is not an integer.
        """
        return [int(part.strip()) for part in text.split(",") if part.strip()]

    @staticmethod
    def _collapse(values: list):
        """Collapse a single-element list to a scalar; pass longer lists through.

        Keeps single-region ROI dataclasses (and their serialized JSON)
        byte-identical to the pre-union format, while a union yields a list.
        """
        return values[0] if len(values) == 1 else values

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_subject(self, subject_id: str, project_dir: str):
        """Refresh atlas combos for this subject.

        Uses MeshAtlasManager and VoxelAtlasManager to discover available
        atlases on disk.

        Args:
            subject_id: Subject identifier (without ``sub-`` prefix).
            project_dir: Absolute path to the BIDS project root.
        """
        self._subject_id = subject_id
        self._project_dir = project_dir

        self._refresh_cortical_atlases()
        self._refresh_volume_atlases()

    def get_roi_type(self) -> str:
        """Return the currently selected ROI type.

        Returns:
            One of ``'spherical'``, ``'atlas'``, or ``'subcortical'``.
        """
        checked_id = self._mode_group.checkedId()
        return {0: "atlas", 1: "subcortical", 2: "spherical"}.get(checked_id, "atlas")

    def get_roi_params(self) -> dict:
        """Return a dict describing the current ROI selection.

        The dict always contains a ``'method'`` key. The remaining keys
        depend on the selected method:

        - spherical: ``center``, ``radius``
        - atlas: ``atlas``, ``region``
        - subcortical: ``volume_atlas``, ``volume_region``, ``tissues``
        """
        roi_type = self.get_roi_type()
        if roi_type == "spherical":
            centers, radii = self._collect_spheres()
            d = {
                "method": "spherical",
                "center": centers[0],
                "radius": radii[0],
                "centers": centers,
                "radii": radii,
                "num_spheres": len(centers),
                "volumetric": self.volumetric_checkbox.isChecked(),
            }
            if self.volumetric_checkbox.isChecked():
                d["tissues"] = self.sphere_tissue_combo.currentData()
            return d
        elif roi_type == "atlas":
            return {
                "method": "atlas",
                "atlas": self.atlas_combo.currentText(),
                "region": ", ".join(self.cortical_chips.keys()),
            }
        else:  # subcortical
            return {
                "method": "subcortical",
                "volume_atlas": self.volume_atlas_combo.currentText(),
                "volume_atlas_space": self._selected_volume_atlas_space(),
                "volume_region": ", ".join(self.subcortical_chips.keys()),
                "tissues": self.tissue_combo.currentData(),
            }

    def get_roi_spec(self, subject_id: str, project_dir: str):
        """Build and return the appropriate ROI dataclass.

        Args:
            subject_id: Subject identifier (without ``sub-`` prefix).
            project_dir: Absolute path to the BIDS project root.

        Returns:
            A ``SphericalROI``, ``AtlasROI``, or ``SubcorticalROI`` instance.
        """
        seg_dir = os.path.join(
            project_dir,
            "derivatives",
            "SimNIBS",
            f"sub-{subject_id}",
            f"m2m_{subject_id}",
            "segmentation",
        )

        roi_type = self.get_roi_type()
        if roi_type == "spherical":
            vol = self.volumetric_checkbox.isChecked()
            centers, radii = self._collect_spheres()
            return FlexConfig.SphericalROI(
                x=self._collapse([c[0] for c in centers]),
                y=self._collapse([c[1] for c in centers]),
                z=self._collapse([c[2] for c in centers]),
                radius=self._collapse(radii),
                use_mni=self.is_mni_space(),
                volumetric=vol,
                tissues=self.sphere_tissue_combo.currentData() if vol else "GM",
            )
        elif roi_type == "atlas":
            atlas_name = self._resolve_atlas_name_for_subject(
                self.atlas_combo.currentText(), subject_id
            )
            # Resolve each hemisphere-prefixed name to its annot label index.
            # Region indices are intrinsic to the atlas parcellation, so the map
            # built from the current subject's .annot applies to every subject.
            name_map = self._cortical_name_index_map()
            tokens = self._parse_region_names(", ".join(self.cortical_chips.keys()))
            # Build equal-length parallel lists so a target can union across
            # regions and/or hemispheres; each entry carries its own lh/rh
            # .annot path and label index. The serialized AtlasROI contract
            # (parallel atlas_path/hemisphere/label lists) is unchanged.
            atlas_paths, hemispheres, out_labels = [], [], []
            for hemi, name in tokens:
                index = name_map.get((hemi, name))
                if index is None:
                    continue
                out_labels.append(index)
                hemispheres.append(hemi)
                atlas_paths.append(os.path.join(seg_dir, f"{hemi}.{atlas_name}.annot"))
            if not out_labels:
                raise ValueError(
                    f"Could not resolve any cortical region name(s) for atlas "
                    f"'{atlas_name}'; the annotation files could not be read."
                )
            return FlexConfig.AtlasROI(
                atlas_path=self._collapse(atlas_paths),
                label=self._collapse(out_labels),
                hemisphere=self._collapse(hemispheres),
            )
        else:  # subcortical
            volume_atlas_path = self._selected_volume_atlas_path(subject_id, seg_dir)
            labels = self._parse_labels(", ".join(self.subcortical_chips.keys()))
            return FlexConfig.SubcorticalROI(
                atlas_path=volume_atlas_path,
                label=self._collapse(labels),
                tissues=self.tissue_combo.currentData(),
                atlas_space=self._selected_volume_atlas_space(),
            )

    def is_mni_space(self) -> bool:
        """Return True if MNI coordinate space is selected (spherical mode only)."""
        if self.space_mni_radio is not None:
            return self.space_mni_radio.isChecked()
        return False

    def set_enabled(self, enabled: bool):
        """Enable or disable all child widgets at once.

        Args:
            enabled: True to enable, False to disable.
        """
        for radio in self._radios:
            radio.setEnabled(enabled)
        self._spherical_page.setEnabled(enabled)
        self._cortical_page.setEnabled(enabled)
        self._subcortical_page.setEnabled(enabled)

    def validate(self) -> str | None:
        """Validate the current ROI configuration.

        Returns:
            An error message string if invalid, or ``None`` if the
            configuration is valid.
        """
        roi_type = self.get_roi_type()
        if roi_type == "spherical":
            _, radii = self._collect_spheres()
            if any(r <= 0 for r in radii):
                return "ROI radius must be greater than zero."
        elif roi_type == "atlas":
            if not self.atlas_combo.currentText():
                return "No cortical atlas selected. Use Refresh to discover atlases."
            error = self._validate_region_names(", ".join(self.cortical_chips.keys()))
            if error:
                return error
        elif roi_type == "subcortical":
            if not self.volume_atlas_combo.currentText():
                return (
                    "No volume atlas selected. Use Refresh to discover volume atlases."
                )
            error = self._validate_labels(", ".join(self.subcortical_chips.keys()))
            if error:
                return error
        return None

    def _validate_region_names(self, text: str) -> str | None:
        """Validate the selected cortical region chips (as a comma string).

        Returns an error message string, or ``None`` when valid. Unknown names
        are reported only when the atlas annotation files can actually be read;
        otherwise name membership is left to the flex backend.
        """
        try:
            tokens = self._parse_region_names(text)
        except ValueError:
            return (
                "Cortical region(s) must be hemisphere-prefixed names, "
                "e.g. lh.precentral, rh.superiorfrontal."
            )
        if not tokens:
            return "Select at least one cortical region (use 'List Regions')."
        name_map = self._cortical_name_index_map()
        if name_map:
            unknown = [f"{h}.{n}" for h, n in tokens if (h, n) not in name_map]
            if unknown:
                return "Unknown cortical region(s): " + ", ".join(unknown)
        return None

    def _validate_labels(self, text: str) -> str | None:
        """Validate the selected subcortical region chips (as a comma string).

        Returns an error message string, or ``None`` when valid.
        """
        try:
            labels = self._parse_labels(text)
        except ValueError:
            return "Region label value(s) must be integers (comma-separated)."
        if not labels:
            return "Select at least one subcortical region (use 'List Regions')."
        if any(label < 1 for label in labels):
            return "Region label value(s) must be at least 1."
        return None

    # ------------------------------------------------------------------
    # Atlas discovery (internal)
    # ------------------------------------------------------------------

    def _refresh_cortical_atlases(self):
        """Discover cortical atlas annotation files for the current subject."""
        if self._subject_id is None or self._project_dir is None:
            return

        self.atlases.clear()
        self.atlas_display_map.clear()
        self.atlas_combo.clear()

        try:
            pm = get_path_manager()
            seg_dir = pm.segmentation(self._subject_id)
            mesh_mgr = MeshAtlasManager(seg_dir)
            lh_atlases = mesh_mgr.find_all_atlases("lh")
            rh_atlases = mesh_mgr.find_all_atlases("rh")
        except Exception:
            return

        all_atlas_names = set(lh_atlases.keys()) | set(rh_atlases.keys())
        for atlas_name in sorted(all_atlas_names):
            self.atlas_combo.addItem(atlas_name)
            self.atlas_display_map[atlas_name] = atlas_name
            if atlas_name in lh_atlases:
                self.atlases[("lh", atlas_name)] = lh_atlases[atlas_name]
            if atlas_name in rh_atlases:
                self.atlases[("rh", atlas_name)] = rh_atlases[atlas_name]

    def _refresh_volume_atlases(self):
        """Discover volumetric atlas files for the selected atlas space."""
        if self._subject_id is None or self._project_dir is None:
            return

        self.volume_atlases.clear()
        self.volume_atlas_combo.clear()

        try:
            if self._selected_volume_atlas_space() == "mni":
                atlases = [
                    (os.path.basename(path), path)
                    for path in VoxelAtlasManager.detect_mni_atlases(
                        self._mni_atlas_dir()
                    )
                ]
            else:
                pm = get_path_manager()
                m2m_dir = pm.m2m(self._subject_id)
                if not m2m_dir:
                    return
                seg_dir = str(Path(m2m_dir) / "segmentation")
                voxel_mgr = VoxelAtlasManager(
                    freesurfer_mri_dir=pm.freesurfer_mri(self._subject_id),
                    seg_dir=seg_dir,
                )
                atlases = voxel_mgr.list_atlases()
        except Exception:
            return

        self.volume_atlases = {name: path for name, path in atlases}
        for name, path in self.volume_atlases.items():
            self.volume_atlas_combo.addItem(name, path)

    def _selected_volume_atlas_space(self) -> str:
        return "mni" if self.volume_mni_radio.isChecked() else "subject"

    def _selected_volume_atlas_path(self, subject_id: str, seg_dir: str) -> str:
        atlas_path = self.volume_atlas_combo.currentData()
        if atlas_path:
            return str(atlas_path)

        atlas_filename = self.volume_atlas_combo.currentText()
        if self._selected_volume_atlas_space() == "mni":
            return os.path.join(self._mni_atlas_dir(), atlas_filename)
        if atlas_filename == "labeling.nii.gz":
            return os.path.join(seg_dir, atlas_filename)

        pm = get_path_manager()
        return os.path.join(pm.freesurfer_mri(subject_id), atlas_filename)

    def _mni_atlas_dir(self) -> str:
        if os.path.isdir(MNI_ATLAS_DIR):
            return MNI_ATLAS_DIR
        return str(Path(__file__).resolve().parents[3] / "resources" / "atlas")

    def _resolve_atlas_name_for_subject(
        self, display_name: str, subject_id: str
    ) -> str:
        """Convert a UI atlas display name to the subject-specific atlas base name.

        The display name is already the atlas type (e.g. "DK40", "HCP_MMP1")
        because ``find_all_atlases`` strips the subject prefix. We just prepend
        the target subject ID.
        """
        atlas_type = self.atlas_display_map.get(display_name, display_name)
        return f"{subject_id}_{atlas_type}"

    # ------------------------------------------------------------------
    # Region listing dialogs
    # ------------------------------------------------------------------

    def _on_list_atlas_regions(self):
        """Show cortical regions from BOTH hemispheres as hemi-prefixed names.

        Entries are built from ``list_annot_regions`` on the lh and rh
        ``.annot`` files and displayed as ``lh.<name>`` / ``rh.<name>``. Each
        selected region is added as a chip whose key is the hemisphere-prefixed
        name and whose display carries both the name and its ``.annot`` index.
        """
        atlas_display = self.atlas_combo.currentText()
        if not atlas_display:
            QtWidgets.QMessageBox.warning(
                self,
                "No Atlas Selected",
                "Select a cortical atlas first (use Refresh to discover atlases).",
            )
            return

        entries = []
        for hemi in ("lh", "rh"):
            annot_file = self.atlases.get((hemi, atlas_display))
            if not annot_file:
                continue
            try:
                regions = MeshAtlasManager("").list_annot_regions(annot_file)
            except (OSError, ValueError) as e:
                QtWidgets.QMessageBox.warning(self, "Error Listing Regions", str(e))
                return
            for idx, name in regions:
                entries.append((idx, f"{hemi}.{name}", None))

        if not entries:
            QtWidgets.QMessageBox.warning(
                self,
                "Atlas File Not Found",
                f"Could not find atlas files for {atlas_display}.",
            )
            return

        dlg = AtlasRegionFinderDialog(
            self,
            f"Cortical Regions - {atlas_display}",
            entries,
            return_field="name",
            multi=True,
            preselected=list(self.cortical_chips.keys()),
        )
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            # selected_ids()/selected_names() are parallel: names are the
            # "hemi.name" tokens, ids are the .annot label indices.
            for index, name_token in zip(dlg.selected_ids(), dlg.selected_names()):
                self.cortical_chips.add_item(
                    key=name_token, display=f"{name_token} · {index}"
                )

    def _on_list_volume_regions(self):
        """Show regions for the currently selected volume atlas."""
        volume_atlas = self.volume_atlas_combo.currentText()
        self._show_volume_regions_dialog(volume_atlas)

    def _show_volume_regions_dialog(self, volume_atlas: str):
        """Open the region finder for the selected volume atlas.

        Each selected region is added as a chip whose key is the integer atlas
        label id and whose display carries both the region name and the id.

        Args:
            volume_atlas: Volume atlas display name from the combo box.
        """
        if self._subject_id is None or self._project_dir is None:
            QtWidgets.QMessageBox.warning(
                self, "No Subject Selected", "Please select a subject first."
            )
            return

        atlas_path = self.volume_atlas_combo.currentData()
        if not atlas_path:
            QtWidgets.QMessageBox.warning(
                self,
                "Atlas Not Found",
                f"Could not resolve a file path for {volume_atlas}.",
            )
            return

        atlas_path = str(atlas_path)
        lut_file = self._find_volume_lut(atlas_path)

        entries = []
        if lut_file is not None:
            try:
                with open(lut_file, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            parsed = self._parse_lut_line(line)
                            if parsed is None:
                                continue
                            label_id, label_name, rgb = parsed
                            entries.append((int(label_id), label_name, rgb))
            except OSError as e:
                QtWidgets.QMessageBox.warning(
                    self, "Error Reading LUT File", f"Error reading LUT file: {str(e)}"
                )
                return
        else:
            # No sidecar LUT (e.g. a subject-space FreeSurfer atlas such as
            # aparc.DKTatlas+aseg.mgz). Resolve names from the atlas volume's own
            # integer labels using the bundled standard FreeSurfer color table,
            # so no FreeSurfer / mri_segstats invocation is required.
            try:
                entries = self._resolve_volume_label_entries(atlas_path)
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Error Reading Atlas",
                    f"Could not read labels from {volume_atlas}: {str(e)}",
                )
                return

        if not entries:
            QtWidgets.QMessageBox.warning(
                self,
                "No Regions Found",
                f"Could not find any labeled regions for {volume_atlas}.",
            )
            return

        dlg = AtlasRegionFinderDialog(
            self,
            f"Subcortical Regions - {volume_atlas}",
            entries,
            return_field="id",  # unused: chips read selected_ids()/selected_names() directly
            multi=True,
            preselected=list(self.subcortical_chips.keys()),
        )
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            for region_id, name in zip(dlg.selected_ids(), dlg.selected_names()):
                self.subcortical_chips.add_item(
                    key=str(region_id), display=f"{name} · {region_id}"
                )

    def _find_volume_lut(self, atlas_path: str) -> Path | None:
        atlas = Path(atlas_path)
        if self._selected_volume_atlas_space() == "subject":
            if atlas.name == "labeling.nii.gz":
                lut_path = atlas.with_name("labeling_LUT.txt")
                return lut_path if lut_path.is_file() else None
            # For FreeSurfer subject atlases (e.g. aparc.DKTatlas+aseg) a
            # "<atlas>_labels.txt" sidecar is an mri_segstats SUMMARY
            # (Index SegId NVoxels Volume StructName) — NOT a colour LUT — so we
            # do NOT parse it here (that would show "1: 245555.0 <name>"). Return
            # None so the caller resolves names from the volume's own labels via
            # the bundled FreeSurferColorLUT (_resolve_volume_label_entries).
            return None

        stem = self._strip_nifti_suffix(atlas.name)
        candidates = [
            atlas.with_name(f"{stem}_LUT.txt"),
            atlas.with_name(f"{stem}_labels.txt"),
            atlas.with_name(f"{stem}.txt"),
        ]
        if stem.lower().startswith("massp"):
            candidates.append(atlas.with_name("massp2021_labels.txt"))

        for candidate in candidates:
            if candidate.is_file():
                return candidate
        return None

    def _resolve_volume_label_entries(
        self, atlas_path: str
    ) -> list[tuple[int, str, tuple[str, str, str] | None]]:
        """Resolve region entries for a volume atlas that has no sidecar LUT.

        Reads the unique nonzero integer labels present in the atlas volume via
        nibabel and maps them to names/colours using the bundled standard
        FreeSurfer colour table (``resources/atlas/FreeSurferColorLUT.txt``).
        Only labels actually present in the volume are returned, so subject-space
        FreeSurfer atlases (e.g. ``aparc.DKTatlas+aseg.mgz``) can be browsed by
        name without FreeSurfer / ``mri_segstats``.

        Args:
            atlas_path: Absolute path to the atlas volume (``.mgz``/``.nii``/
                ``.nii.gz``).

        Returns:
            List of ``(id, name, rgb)`` entries, sorted by id, for labels found
            in both the volume and the bundled colour table. ``rgb`` is a tuple
            of decimal string components, or ``None`` when unavailable.
        """
        import numpy as np
        import nibabel as nib

        lut = self._load_freesurfer_lut()
        if not lut:
            return []

        img = nib.load(atlas_path)
        # Label maps carry identity scaling, so np.asarray(dataobj) returns the
        # native integer labels; int() below normalises regardless.
        present = np.unique(np.asarray(img.dataobj))

        entries: list[tuple[int, str, tuple[str, str, str] | None]] = []
        for value in present:
            label_id = int(value)
            if label_id == 0:
                continue
            info = lut.get(label_id)
            if info is None:
                continue
            name, rgb = info
            entries.append((label_id, name, rgb))
        return entries

    def _load_freesurfer_lut(
        self,
    ) -> dict[int, tuple[str, tuple[str, str, str] | None]]:
        """Parse the bundled standard FreeSurfer colour table.

        Returns:
            Mapping of ``label_id -> (name, rgb)``, where ``rgb`` is a tuple of
            decimal string components (or ``None`` when the row has no colour).
            Empty dict when the bundled table cannot be located or read.
        """
        lut_path = self._freesurfer_lut_path()
        if lut_path is None:
            return {}

        lut: dict[int, tuple[str, tuple[str, str, str] | None]] = {}
        try:
            with open(lut_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parsed = self._parse_lut_line(line)
                    if parsed is None:
                        continue
                    label_id, label_name, rgb = parsed
                    lut[int(label_id)] = (label_name, rgb)
        except OSError:
            return {}
        return lut

    def _freesurfer_lut_path(self) -> str | None:
        """Return the path to the bundled standard FreeSurfer colour table.

        Reuses the same resources/atlas directory resolution as the MNI atlases
        (container path first, then the repo-relative fallback).

        Returns:
            Absolute path to ``FreeSurferColorLUT.txt``, or ``None`` if missing.
        """
        candidate = os.path.join(self._mni_atlas_dir(), "FreeSurferColorLUT.txt")
        return candidate if os.path.isfile(candidate) else None

    @staticmethod
    def _strip_nifti_suffix(filename: str) -> str:
        if filename.endswith(".nii.gz"):
            return filename[:-7]
        return os.path.splitext(filename)[0]

    @staticmethod
    def _parse_lut_line(
        line: str,
    ) -> tuple[str, str, tuple[str, str, str] | None] | None:
        parts = line.split()
        if len(parts) < 2:
            return None

        label_id = parts[0]
        if not label_id.lstrip("-").isdigit():
            return None

        # The name is every non-integer token after the id; the RGB(A) columns
        # are the integer tokens. This is column-order agnostic, so both a
        # "ID Name R G B A" table and a "ID R G B Name" table yield a clean name
        # (never "12 48 255 Left-Pallidum").
        rest = parts[1:]
        name_tokens = [p for p in rest if not p.lstrip("-").isdigit()]
        int_tokens = [p for p in rest if p.lstrip("-").isdigit()]
        if not name_tokens:
            return None
        label_name = " ".join(name_tokens)
        rgb = tuple(int_tokens[:3]) if len(int_tokens) >= 3 else None
        return label_id, label_name, rgb

    # ------------------------------------------------------------------
    # Freeview integration
    # ------------------------------------------------------------------

    def load_t1_in_freeview(self):
        """Launch Freeview with the subject's T1 or the MNI152 template.

        In MNI mode (or when no subject_id is set), attempts to open the
        MNI152 template. Otherwise opens the subject's T1 NIfTI file.
        """
        try:
            use_mni = self.is_mni_space() or self._subject_id is None

            if use_mni:
                mni_paths = [
                    "/usr/share/fsl/data/standard/MNI152_T1_1mm.nii.gz",
                    "/opt/fsl/data/standard/MNI152_T1_1mm.nii.gz",
                    "$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz",
                    os.path.join(
                        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "..",
                        "assets",
                        "atlas",
                        "MNI152_T1_1mm.nii.gz",
                    ),
                ]

                mni_file = None
                for path in mni_paths:
                    expanded = os.path.expandvars(path)
                    if os.path.isfile(expanded):
                        mni_file = expanded
                        break

                if not mni_file:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        "MNI152 template not found. Please ensure FSL is installed "
                        "or place MNI152_T1_1mm.nii.gz in resources/atlas/",
                    )
                    return

                try:
                    subprocess.Popen(["freeview", mni_file])
                except FileNotFoundError:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        "Freeview not found. Please install FreeSurfer or "
                        "ensure it's in your PATH",
                    )
                except (OSError, subprocess.SubprocessError) as e:
                    QtWidgets.QMessageBox.warning(
                        self, "Error", f"Failed to launch Freeview: {str(e)}"
                    )
            else:
                # Single subject T1
                pm = get_path_manager()
                t1_paths = []
                m2m_dir = pm.m2m(self._subject_id)
                if m2m_dir:
                    t1_paths.append(str(Path(m2m_dir) / "T1.nii.gz"))

                bids_anat_dir = pm.bids_anat(self._subject_id)
                if bids_anat_dir:
                    t1_paths.append(
                        str(Path(bids_anat_dir) / f"sub-{self._subject_id}_T1w.nii.gz")
                    )
                    t1_paths.append(
                        str(Path(bids_anat_dir) / "anat-T1w_acq-MPRAGE.nii.gz")
                    )

                t1_file = None
                for path in t1_paths:
                    if os.path.isfile(path):
                        t1_file = path
                        break

                if not t1_file:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        f"T1 file not found for subject {self._subject_id}",
                    )
                    return

                try:
                    subprocess.Popen(["freeview", t1_file])
                except FileNotFoundError:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Error",
                        "Freeview not found. Please install FreeSurfer or "
                        "ensure it's in your PATH",
                    )
                except (OSError, subprocess.SubprocessError) as e:
                    QtWidgets.QMessageBox.warning(
                        self, "Error", f"Failed to launch Freeview: {str(e)}"
                    )

        except (OSError, subprocess.SubprocessError) as e:
            QtWidgets.QMessageBox.warning(
                self, "Error", f"Error loading image in Freeview: {str(e)}"
            )
