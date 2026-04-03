#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
ROI Picker Widget Component
Reusable ROI selection widget with spherical/atlas/subcortical modes.
"""

import os
import subprocess
from pathlib import Path

from PyQt5 import QtWidgets, QtCore, QtGui

from tit.paths import get_path_manager
from tit.atlas import MeshAtlasManager, VoxelAtlasManager
from tit.gui.style import FONT_HELP, FONT_SIZE_MONOSPACE
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

        if self._enable_spherical:
            self.radio_spherical = QtWidgets.QRadioButton(
                "Spherical (coordinates and radius)"
            )
            radio_layout.addWidget(self.radio_spherical)
            self._mode_group.addButton(self.radio_spherical, 0)
            self._radios.append(self.radio_spherical)
        else:
            self.radio_spherical = None

        if self._enable_atlas:
            self.radio_cortical = QtWidgets.QRadioButton("Cortical")
            radio_layout.addWidget(self.radio_cortical)
            self._mode_group.addButton(self.radio_cortical, 1)
            self._radios.append(self.radio_cortical)
        else:
            self.radio_cortical = None

        if self._enable_subcortical:
            self.radio_subcortical = QtWidgets.QRadioButton("Subcortical")
            radio_layout.addWidget(self.radio_subcortical)
            self._mode_group.addButton(self.radio_subcortical, 2)
            self._radios.append(self.radio_subcortical)
        else:
            self.radio_subcortical = None

        radio_layout.addStretch()

        # Default: first enabled mode is checked
        if self._radios:
            self._radios[0].setChecked(True)

        main_layout.addWidget(radio_container)

        # --- Stacked widget ---
        self.stacked = QtWidgets.QStackedWidget()

        # Page 0 — Spherical
        self._spherical_page = self._build_spherical_page()
        self.stacked.addWidget(self._spherical_page)

        # Page 1 — Cortical (Atlas)
        self._cortical_page = self._build_cortical_page()
        self.stacked.addWidget(self._cortical_page)

        # Page 2 — Subcortical (Volume)
        self._subcortical_page = self._build_subcortical_page()
        self.stacked.addWidget(self._subcortical_page)

        # Set initial page
        if self._radios:
            checked_id = self._mode_group.checkedId()
            self.stacked.setCurrentIndex(max(0, checked_id))

        main_layout.addWidget(self.stacked)

    def _build_spherical_page(self) -> QtWidgets.QWidget:
        """Build the spherical ROI input page."""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.setVerticalSpacing(3)
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
            layout.addRow(space_widget)
        else:
            self.space_subject_radio = None
            self.space_mni_radio = None

        # MNI info label (initially hidden)
        self.mni_info_label = QtWidgets.QLabel(
            "Coordinates will be treated as MNI space and transformed "
            "to each subject's native space."
        )
        self.mni_info_label.setStyleSheet(
            f"background-color: #E3F2FD; color: #1976D2; padding: 8px; "
            f"border-radius: 4px; font-size: {FONT_HELP};"
        )
        self.mni_info_label.setWordWrap(True)
        self.mni_info_label.setVisible(False)
        layout.addRow(self.mni_info_label)

        # Coordinate inputs + Freeview button
        self.coords_label = QtWidgets.QLabel("ROI Center RAS Coordinates (mm):")
        coords_widget = QtWidgets.QWidget()
        coords_layout = QtWidgets.QHBoxLayout(coords_widget)
        coords_layout.setContentsMargins(0, 0, 0, 0)

        coords_layout.addWidget(QtWidgets.QLabel("X:"))
        self.x_input = QtWidgets.QDoubleSpinBox()
        self.x_input.setRange(-150, 150)
        self.x_input.setValue(0)
        self.x_input.setDecimals(2)
        coords_layout.addWidget(self.x_input)

        coords_layout.addWidget(QtWidgets.QLabel("Y:"))
        self.y_input = QtWidgets.QDoubleSpinBox()
        self.y_input.setRange(-150, 150)
        self.y_input.setValue(0)
        self.y_input.setDecimals(2)
        coords_layout.addWidget(self.y_input)

        coords_layout.addWidget(QtWidgets.QLabel("Z:"))
        self.z_input = QtWidgets.QDoubleSpinBox()
        self.z_input.setRange(-150, 150)
        self.z_input.setValue(0)
        self.z_input.setDecimals(2)
        coords_layout.addWidget(self.z_input)

        if self._enable_freeview_button:
            self.view_t1_btn = QtWidgets.QPushButton("View T1 in Freeview")
            self.view_t1_btn.setToolTip(
                "Open subject's T1 scan in Freeview to find RAS coordinates"
            )
            coords_layout.addWidget(self.view_t1_btn)
        else:
            self.view_t1_btn = None

        coords_layout.addStretch()
        layout.addRow(self.coords_label, coords_widget)

        # Radius
        self.radius_label = QtWidgets.QLabel("ROI Radius (mm):")
        self.radius_input = QtWidgets.QDoubleSpinBox()
        self.radius_input.setRange(1, 50)
        self.radius_input.setValue(10)
        self.radius_input.setDecimals(2)
        layout.addRow(self.radius_label, self.radius_input)

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
        layout.addRow(vol_widget)

        # Wire checkbox to enable/disable tissue combo
        self.volumetric_checkbox.toggled.connect(self.sphere_tissue_combo.setEnabled)
        self.volumetric_checkbox.toggled.connect(self.sphere_tissue_label.setEnabled)

        return page

    def _build_cortical_page(self) -> QtWidgets.QWidget:
        """Build the cortical (atlas annotation) ROI input page."""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.setVerticalSpacing(3)
        layout.setContentsMargins(0, 5, 0, 5)

        # Atlas combo + hemisphere + refresh + list regions
        atlas_widget = QtWidgets.QWidget()
        atlas_layout = QtWidgets.QHBoxLayout(atlas_widget)
        atlas_layout.setContentsMargins(0, 0, 0, 0)

        self.atlas_combo = QtWidgets.QComboBox()
        self.atlas_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        atlas_layout.addWidget(self.atlas_combo)

        self.hemi_label = QtWidgets.QLabel("Hemisphere:")
        atlas_layout.addWidget(self.hemi_label)

        self.hemi_combo = QtWidgets.QComboBox()
        self.hemi_combo.addItems(["Left (lh)", "Right (rh)"])
        atlas_layout.addWidget(self.hemi_combo)

        self.refresh_atlases_btn = QtWidgets.QPushButton("Refresh")
        atlas_layout.addWidget(self.refresh_atlases_btn)

        self.list_regions_btn = QtWidgets.QPushButton("List Regions")
        atlas_layout.addWidget(self.list_regions_btn)

        atlas_layout.addStretch()
        layout.addRow(QtWidgets.QLabel("Atlas:"), atlas_widget)

        # Region label value
        self.label_value_input = QtWidgets.QSpinBox()
        self.label_value_input.setRange(1, 10000)
        self.label_value_input.setValue(1)
        layout.addRow(QtWidgets.QLabel("Region Label Value:"), self.label_value_input)

        return page

    def _build_subcortical_page(self) -> QtWidgets.QWidget:
        """Build the subcortical (volumetric atlas) ROI input page."""
        page = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(page)
        layout.setVerticalSpacing(3)
        layout.setContentsMargins(0, 5, 0, 5)

        # Volume atlas combo + refresh + list regions
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

        # Region label value
        self.volume_label_input = QtWidgets.QSpinBox()
        self.volume_label_input.setRange(1, 10000)
        self.volume_label_input.setValue(10)
        self.volume_label_input.setToolTip(
            "Common values: 10=Left-Thalamus, 49=Right-Thalamus, "
            "17=Left-Hippocampus, 53=Right-Hippocampus"
        )
        layout.addRow(QtWidgets.QLabel("Region Label Value:"), self.volume_label_input)

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

        # Emit roi_changed on any value change
        self.x_input.valueChanged.connect(self.roi_changed)
        self.y_input.valueChanged.connect(self.roi_changed)
        self.z_input.valueChanged.connect(self.roi_changed)
        self.radius_input.valueChanged.connect(self.roi_changed)
        self.volumetric_checkbox.toggled.connect(self.roi_changed)
        self.sphere_tissue_combo.currentIndexChanged.connect(self.roi_changed)
        self.atlas_combo.currentIndexChanged.connect(self.roi_changed)
        self.hemi_combo.currentIndexChanged.connect(self.roi_changed)
        self.label_value_input.valueChanged.connect(self.roi_changed)
        self.volume_atlas_combo.currentIndexChanged.connect(self.roi_changed)
        self.volume_label_input.valueChanged.connect(self.roi_changed)
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
            self.view_t1_btn.setVisible(checked_id == 0)

        self._update_coordinate_space_labels()

    def _update_coordinate_space_labels(self):
        """Update coordinate labels and tooltips based on space selection."""
        if self.get_roi_type() != "spherical":
            self.mni_info_label.setVisible(False)
            return

        if self.is_mni_space():
            self.coords_label.setText("ROI Center MNI Coordinates (mm):")
            self.coords_label.setToolTip(
                "MNI space coordinates (will be transformed to subject space "
                "for each subject)"
            )
            self.coords_label.setStyleSheet("color: #007ACC; font-weight: bold;")
            self.mni_info_label.setVisible(True)
            self.x_input.setToolTip("X coordinate in MNI space")
            self.y_input.setToolTip("Y coordinate in MNI space")
            self.z_input.setToolTip("Z coordinate in MNI space")
            if self.view_t1_btn is not None:
                self.view_t1_btn.setText("View MNI Template")
                self.view_t1_btn.setToolTip(
                    "Open MNI152 template to find MNI coordinates"
                )
        else:
            self.coords_label.setText("ROI Center RAS Coordinates (mm):")
            self.coords_label.setToolTip("Subject-specific RAS coordinates")
            self.coords_label.setStyleSheet("")
            self.mni_info_label.setVisible(False)
            self.x_input.setToolTip("X coordinate in subject RAS space")
            self.y_input.setToolTip("Y coordinate in subject RAS space")
            self.z_input.setToolTip("Z coordinate in subject RAS space")
            if self.view_t1_btn is not None:
                self.view_t1_btn.setText("View T1 in Freeview")
                self.view_t1_btn.setToolTip(
                    "Open subject's T1 scan in Freeview to find RAS coordinates"
                )

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
        return {0: "spherical", 1: "atlas", 2: "subcortical"}.get(
            checked_id, "spherical"
        )

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
            d = {
                "method": "spherical",
                "center": [
                    self.x_input.value(),
                    self.y_input.value(),
                    self.z_input.value(),
                ],
                "radius": self.radius_input.value(),
                "volumetric": self.volumetric_checkbox.isChecked(),
            }
            if self.volumetric_checkbox.isChecked():
                d["tissues"] = self.sphere_tissue_combo.currentData()
            return d
        elif roi_type == "atlas":
            return {
                "method": "atlas",
                "atlas": self.atlas_combo.currentText(),
                "region": str(self.label_value_input.value()),
            }
        else:  # subcortical
            return {
                "method": "subcortical",
                "volume_atlas": self.volume_atlas_combo.currentText(),
                "volume_region": str(self.volume_label_input.value()),
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
            return FlexConfig.SphericalROI(
                x=self.x_input.value(),
                y=self.y_input.value(),
                z=self.z_input.value(),
                radius=self.radius_input.value(),
                use_mni=self.is_mni_space(),
                volumetric=vol,
                tissues=self.sphere_tissue_combo.currentData() if vol else "GM",
            )
        elif roi_type == "atlas":
            atlas_name = self._resolve_atlas_name_for_subject(
                self.atlas_combo.currentText(), subject_id
            )
            hemi = "lh" if self.hemi_combo.currentIndex() == 0 else "rh"
            atlas_path = os.path.join(seg_dir, f"{hemi}.{atlas_name}.annot")
            return FlexConfig.AtlasROI(
                atlas_path=atlas_path,
                label=int(self.label_value_input.value()),
                hemisphere=hemi,
            )
        else:  # subcortical
            atlas_filename = self.volume_atlas_combo.currentText()
            if atlas_filename == "labeling.nii.gz":
                volume_atlas_path = os.path.join(seg_dir, atlas_filename)
            else:
                pm = get_path_manager()
                volume_atlas_path = os.path.join(
                    pm.freesurfer_mri(subject_id), atlas_filename
                )
            return FlexConfig.SubcorticalROI(
                atlas_path=volume_atlas_path,
                label=int(self.volume_label_input.value()),
                tissues=self.tissue_combo.currentData(),
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
            if self.radius_input.value() <= 0:
                return "ROI radius must be greater than zero."
        elif roi_type == "atlas":
            if not self.atlas_combo.currentText():
                return "No cortical atlas selected. Use Refresh to discover atlases."
            if self.label_value_input.value() < 1:
                return "Region label value must be at least 1."
        elif roi_type == "subcortical":
            if not self.volume_atlas_combo.currentText():
                return (
                    "No volume atlas selected. Use Refresh to discover volume atlases."
                )
            if self.volume_label_input.value() < 1:
                return "Region label value must be at least 1."
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
        """Discover volumetric atlas files for the current subject."""
        if self._subject_id is None or self._project_dir is None:
            return

        self.volume_atlases.clear()
        self.volume_atlas_combo.clear()

        try:
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
        for name in self.volume_atlases:
            self.volume_atlas_combo.addItem(name)

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
        """Show regions for the currently selected cortical atlas."""
        atlas = self.atlas_combo.currentText()
        hemi = "lh" if self.hemi_combo.currentIndex() == 0 else "rh"
        self._show_atlas_regions_dialog(atlas, hemi)

    def _on_list_volume_regions(self):
        """Show regions for the currently selected volume atlas."""
        volume_atlas = self.volume_atlas_combo.currentText()
        self._show_volume_regions_dialog(volume_atlas)

    def _show_atlas_regions_dialog(self, atlas_display: str, hemi: str):
        """Show a dialog listing regions in the selected cortical atlas.

        Args:
            atlas_display: Atlas display name from the combo box.
            hemi: Hemisphere string (``'lh'`` or ``'rh'``).
        """
        atlas_key = (hemi, atlas_display)
        if atlas_key not in self.atlases:
            QtWidgets.QMessageBox.warning(
                self,
                "Atlas File Not Found",
                f"Could not find atlas file for {hemi}.{atlas_display}",
            )
            return

        annot_file = self.atlases[atlas_key]

        try:
            mesh_mgr = MeshAtlasManager("")
            regions = mesh_mgr.list_annot_regions(annot_file)
            output_lines = []
            for idx, name in regions:
                output_lines.append(f"{idx:3d}: {name}")
            output = "\n".join(output_lines)
        except (OSError, ValueError) as e:
            QtWidgets.QMessageBox.warning(self, "Error Listing Regions", str(e))
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Regions in {hemi}.{atlas_display}")
        dlg.setMinimumWidth(600)
        layout = QtWidgets.QVBoxLayout(dlg)

        search_box = QtWidgets.QLineEdit()
        search_box.setPlaceholderText("Search regions...")
        layout.addWidget(search_box)

        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setText(output)
        layout.addWidget(text)

        def filter_regions():
            query = search_box.text().strip().lower()
            if not query:
                text.setText(output)
                return
            filtered = "\n".join(
                line for line in output.splitlines() if query in line.lower()
            )
            text.setText(filtered)

        search_box.textChanged.connect(filter_regions)
        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()

    def _show_volume_regions_dialog(self, volume_atlas: str):
        """Show a dialog listing regions in the selected volume atlas.

        Reads ``labeling_LUT.txt`` from the subject's segmentation directory.

        Args:
            volume_atlas: Volume atlas display name from the combo box.
        """
        if self._subject_id is None or self._project_dir is None:
            QtWidgets.QMessageBox.warning(
                self, "No Subject Selected", "Please select a subject first."
            )
            return

        pm = get_path_manager()
        m2m_dir = pm.m2m(self._subject_id)
        if not m2m_dir:
            QtWidgets.QMessageBox.warning(
                self,
                "m2m Folder Missing",
                f"m2m directory not found for subject {self._subject_id}.",
            )
            return

        seg_dir = Path(m2m_dir) / "segmentation"
        labeling_lut_file = seg_dir / "labeling_LUT.txt"

        if not labeling_lut_file.is_file():
            QtWidgets.QMessageBox.warning(
                self,
                "LUT File Not Found",
                f"Could not find labeling_LUT.txt file at: {labeling_lut_file}",
            )
            return

        try:
            output = "Subcortical Regions (labeling.nii.gz):\n"
            output += "=" * 50 + "\n"
            output += f"{'ID':<4} {'Structure Name':<35} {'RGB'}\n"
            output += "-" * 50 + "\n"

            with open(labeling_lut_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            try:
                                label_id = parts[0].strip()
                                label_name = parts[1].strip()
                                remaining = (
                                    "\t".join(parts[2:]) if len(parts) > 2 else ""
                                )
                                rgb_parts = remaining.split()
                                if len(rgb_parts) >= 3:
                                    r, g, b = rgb_parts[0], rgb_parts[1], rgb_parts[2]
                                    output += (
                                        f"{label_id:<4} {label_name:<35} "
                                        f"({r},{g},{b})\n"
                                    )
                                else:
                                    output += (
                                        f"{label_id:<4} {label_name:<35} (no color)\n"
                                    )
                            except (ValueError, IndexError):
                                continue
        except OSError as e:
            QtWidgets.QMessageBox.warning(
                self, "Error Reading LUT File", f"Error reading LUT file: {str(e)}"
            )
            return

        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(f"Subcortical Regions - {volume_atlas}")
        dlg.setMinimumWidth(700)
        layout = QtWidgets.QVBoxLayout(dlg)

        search_box = QtWidgets.QLineEdit()
        search_box.setPlaceholderText("Search regions (by ID or name)...")
        layout.addWidget(search_box)

        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        text.setFont(QtGui.QFont("Consolas", FONT_SIZE_MONOSPACE))
        text.setText(output)
        layout.addWidget(text)

        def filter_regions():
            query = search_box.text().strip().lower()
            if not query:
                text.setText(output)
                return
            filtered_lines = [
                line for line in output.splitlines() if query in line.lower()
            ]
            text.setText("\n".join(filtered_lines))

        search_box.textChanged.connect(filter_regions)

        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(dlg.accept)
        layout.addWidget(btn)
        dlg.exec_()

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
