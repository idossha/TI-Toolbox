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
from tit.gui.components.atlas_region_finder import (
    AtlasRegionFinderDialog,
    merge_into_lineedit,
)
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

        The region field uses analyzer-style, hemisphere-prefixed region
        *names* (e.g. ``lh.precentral, rh.superiorfrontal``); the hemisphere is
        carried in each name, so there is no separate hemisphere selector.
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

        atlas_layout.addStretch()
        layout.addRow(QtWidgets.QLabel("Atlas:"), atlas_widget)

        # Region name(s) — one hemisphere-prefixed name, or several
        # comma-separated to union multiple regions into one combined target.
        self.label_value_input = QtWidgets.QLineEdit()
        self.label_value_input.setPlaceholderText("lh.precentral, rh.superiorfrontal")
        self.label_value_input.setToolTip(
            "Hemisphere-prefixed region name(s), e.g. lh.precentral. "
            "Comma-separate several names to union them into one combined "
            "target, e.g. lh.precentral, rh.superiorfrontal. Use 'List Regions' "
            "to browse available names."
        )
        layout.addRow(QtWidgets.QLabel("Region Name(s):"), self.label_value_input)

        return page

    def _build_subcortical_page(self) -> QtWidgets.QWidget:
        """Build the subcortical (volumetric atlas) ROI input page."""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.setVerticalSpacing(3)
        layout.setContentsMargins(0, 5, 0, 5)

        # Volume atlas combo + refresh + list regions
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

        volume_layout.addStretch()
        layout.addRow(QtWidgets.QLabel("Volume Atlas:"), volume_widget)

        # Region label value(s) — one integer, or several comma-separated to
        # union multiple regions (e.g. both hippocampi) into one combined target.
        self.volume_label_input = QtWidgets.QLineEdit()
        self.volume_label_input.setText("10")
        self.volume_label_input.setPlaceholderText("10  or  17,53")
        self.volume_label_input.setToolTip(
            "Integer atlas label(s). Comma-separate several labels to union them "
            "into one combined target (e.g. 17,53 = both hippocampi). "
            "Common values: 10=Left-Thalamus, 49=Right-Thalamus, "
            "17=Left-Hippocampus, 53=Right-Hippocampus"
        )
        layout.addRow(
            QtWidgets.QLabel("Region Label Value(s):"), self.volume_label_input
        )

        # Tissue type
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
        self.label_value_input.textChanged.connect(self.roi_changed)
        self.volume_atlas_combo.currentIndexChanged.connect(self.roi_changed)
        self.volume_subject_radio.toggled.connect(self.roi_changed)
        self.volume_mni_radio.toggled.connect(self.roi_changed)
        self.volume_label_input.textChanged.connect(self.roi_changed)
        self.tissue_combo.currentIndexChanged.connect(self.roi_changed)
        self._mode_group.buttonClicked.connect(lambda: self.roi_changed.emit())

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
                "region": self.label_value_input.text().strip(),
            }
        else:  # subcortical
            return {
                "method": "subcortical",
                "volume_atlas": self.volume_atlas_combo.currentText(),
                "volume_atlas_space": self._selected_volume_atlas_space(),
                "volume_region": self.volume_label_input.text().strip(),
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
            tokens = self._parse_region_names(self.label_value_input.text())
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
            labels = self._parse_labels(self.volume_label_input.text())
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
            error = self._validate_region_names(self.label_value_input.text())
            if error:
                return error
        elif roi_type == "subcortical":
            if not self.volume_atlas_combo.currentText():
                return (
                    "No volume atlas selected. Use Refresh to discover volume atlases."
                )
            error = self._validate_labels(self.volume_label_input.text())
            if error:
                return error
        return None

    def _validate_region_names(self, text: str) -> str | None:
        """Validate the comma-separated cortical region-name field.

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
            return "Enter at least one cortical region name."
        name_map = self._cortical_name_index_map()
        if name_map:
            unknown = [f"{h}.{n}" for h, n in tokens if (h, n) not in name_map]
            if unknown:
                return "Unknown cortical region(s): " + ", ".join(unknown)
        return None

    def _validate_labels(self, text: str) -> str | None:
        """Validate a comma-separated region-label field. Returns an error or None."""
        try:
            labels = self._parse_labels(text)
        except ValueError:
            return "Region label value(s) must be integers (comma-separated)."
        if not labels:
            return "Enter at least one region label value."
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
        ``.annot`` files and displayed as ``lh.<name>`` / ``rh.<name>``. The
        finder returns the selected names, which are merged into the region
        field.
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
        )
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            merge_into_lineedit(self.label_value_input, dlg.selected_values())

    def _on_list_volume_regions(self):
        """Show regions for the currently selected volume atlas."""
        volume_atlas = self.volume_atlas_combo.currentText()
        self._show_volume_regions_dialog(volume_atlas)

    def _show_volume_regions_dialog(self, volume_atlas: str):
        """Open the region finder for the selected volume atlas.

        Selected region ids are appended to the volume region-label field.

        Args:
            volume_atlas: Volume atlas display name from the combo box.
        """
        if self._subject_id is None or self._project_dir is None:
            QtWidgets.QMessageBox.warning(
                self, "No Subject Selected", "Please select a subject first."
            )
            return

        atlas_path = self.volume_atlas_combo.currentData()
        lut_file = self._find_volume_lut(str(atlas_path)) if atlas_path else None
        if lut_file is None:
            QtWidgets.QMessageBox.warning(
                self,
                "LUT File Not Found",
                f"Could not find a label table for {volume_atlas}.",
            )
            return

        entries = []
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

        dlg = AtlasRegionFinderDialog(
            self,
            f"Subcortical Regions - {volume_atlas}",
            entries,
            return_field="id",
            multi=True,
        )
        if dlg.exec_() == QtWidgets.QDialog.Accepted:
            merge_into_lineedit(
                self.volume_label_input, dlg.selected_values(), replace_default="10"
            )

    def _find_volume_lut(self, atlas_path: str) -> Path | None:
        atlas = Path(atlas_path)
        if self._selected_volume_atlas_space() == "subject":
            if atlas.name == "labeling.nii.gz":
                lut_path = atlas.with_name("labeling_LUT.txt")
                return lut_path if lut_path.is_file() else None
            labels_file = atlas.with_name(
                f"{self._strip_nifti_suffix(atlas.name)}_labels.txt"
            )
            return labels_file if labels_file.is_file() else None

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

        color_start = None
        for i in range(2, len(parts) - 2):
            if all(part.lstrip("-").isdigit() for part in parts[i : i + 3]):
                color_start = i
                break

        if color_start is None:
            return label_id, " ".join(parts[1:]), None

        label_name = " ".join(parts[1:color_start])
        rgb = tuple(parts[color_start : color_start + 3])
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
