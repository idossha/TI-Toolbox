#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""QSIPrep and QSIRecon configuration dialogs."""

import multiprocessing

from PyQt5 import QtWidgets

from tit import constants as const
from tit.gui.style import FONT_SM, FONT_HELP


class QSIPrepConfigDialog(QtWidgets.QDialog):
    """Configuration dialog for QSIPrep parameters."""

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("QSIPrep Configuration")
        self.setMinimumWidth(400)
        self.config = config or {}
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        # Use DooD-inherited defaults (current container limits) unless user overrides.
        try:
            from tit.pre.qsi.utils import get_inherited_dood_resources

            inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        except Exception:
            inherited_cpus, inherited_mem_gb = (
                const.QSI_DEFAULT_CPUS,
                const.QSI_DEFAULT_MEMORY_GB,
            )

        # Output resolution
        resolution_layout = QtWidgets.QHBoxLayout()
        resolution_layout.addWidget(QtWidgets.QLabel("Output Resolution (mm):"))
        self.resolution_spin = QtWidgets.QDoubleSpinBox()
        self.resolution_spin.setRange(0.5, 3.0)
        self.resolution_spin.setSingleStep(0.5)
        self.resolution_spin.setValue(self.config.get("output_resolution", 2.0))
        self.resolution_spin.setToolTip("Target output resolution in mm")
        resolution_layout.addWidget(self.resolution_spin)
        resolution_layout.addStretch()
        layout.addLayout(resolution_layout)

        # Resource settings group
        resource_group = QtWidgets.QGroupBox("Resource Settings")
        resource_layout = QtWidgets.QFormLayout(resource_group)

        self.cpus_spin = QtWidgets.QSpinBox()
        self.cpus_spin.setRange(1, multiprocessing.cpu_count())
        self.cpus_spin.setValue(self.config.get("cpus", inherited_cpus))
        resource_layout.addRow("CPUs:", self.cpus_spin)

        self.memory_spin = QtWidgets.QSpinBox()
        self.memory_spin.setRange(4, max(256, int(inherited_mem_gb)))
        self.memory_spin.setValue(self.config.get("memory_gb", inherited_mem_gb))
        self.memory_spin.setSuffix(" GB")
        resource_layout.addRow("Memory:", self.memory_spin)

        self.omp_threads_spin = QtWidgets.QSpinBox()
        self.omp_threads_spin.setRange(1, multiprocessing.cpu_count())
        self.omp_threads_spin.setValue(
            self.config.get("omp_threads", const.QSI_DEFAULT_OMP_THREADS)
        )
        resource_layout.addRow("OMP Threads:", self.omp_threads_spin)

        layout.addWidget(resource_group)

        # Processing options group
        options_group = QtWidgets.QGroupBox("Processing Options")
        options_layout = QtWidgets.QFormLayout(options_group)

        self.denoise_combo = QtWidgets.QComboBox()
        self.denoise_combo.addItems(["dwidenoise", "patch2self", "none"])
        self.denoise_combo.setCurrentText(
            self.config.get("denoise_method", "dwidenoise")
        )
        self.denoise_combo.setToolTip("Denoising method to apply to DWI data")
        options_layout.addRow("Denoise Method:", self.denoise_combo)

        self.unringing_combo = QtWidgets.QComboBox()
        self.unringing_combo.addItems(["mrdegibbs", "rpg", "none"])
        self.unringing_combo.setCurrentText(
            self.config.get("unringing_method", "mrdegibbs")
        )
        self.unringing_combo.setToolTip("Gibbs ringing removal method")
        options_layout.addRow("Unringing Method:", self.unringing_combo)

        self.skip_bids_cb = QtWidgets.QCheckBox()
        self.skip_bids_cb.setChecked(self.config.get("skip_bids_validation", True))
        self.skip_bids_cb.setToolTip(
            "Skip BIDS validation (useful for non-BIDS datasets)"
        )
        options_layout.addRow("Skip BIDS Validation:", self.skip_bids_cb)

        layout.addWidget(options_group)

        # Docker image tag
        tag_layout = QtWidgets.QHBoxLayout()
        tag_layout.addWidget(QtWidgets.QLabel("Image Tag:"))
        self.tag_edit = QtWidgets.QLineEdit()
        self.tag_edit.setText(self.config.get("image_tag", const.QSI_DEFAULT_IMAGE_TAG))
        self.tag_edit.setToolTip("Docker image tag for QSIPrep")
        tag_layout.addWidget(self.tag_edit)
        layout.addLayout(tag_layout)

        layout.addStretch()

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self.reset_defaults)
        button_layout.addWidget(self.reset_btn)
        button_layout.addStretch()

        self.ok_btn = QtWidgets.QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

    def reset_defaults(self):
        """Reset all settings to defaults."""
        try:
            from tit.pre.qsi.utils import get_inherited_dood_resources

            inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        except Exception:
            inherited_cpus, inherited_mem_gb = (
                const.QSI_DEFAULT_CPUS,
                const.QSI_DEFAULT_MEMORY_GB,
            )
        self.resolution_spin.setValue(const.QSI_DEFAULT_OUTPUT_RESOLUTION)
        self.cpus_spin.setValue(inherited_cpus)
        self.memory_spin.setValue(inherited_mem_gb)
        self.omp_threads_spin.setValue(const.QSI_DEFAULT_OMP_THREADS)
        self.denoise_combo.setCurrentText("dwidenoise")
        self.unringing_combo.setCurrentText("mrdegibbs")
        self.skip_bids_cb.setChecked(True)
        self.tag_edit.setText(const.QSI_DEFAULT_IMAGE_TAG)

    def get_config(self):
        """Return the configuration as a dictionary."""
        return {
            "output_resolution": self.resolution_spin.value(),
            "cpus": self.cpus_spin.value(),
            "memory_gb": self.memory_spin.value(),
            "omp_threads": self.omp_threads_spin.value(),
            "denoise_method": self.denoise_combo.currentText(),
            "unringing_method": self.unringing_combo.currentText(),
            "skip_bids_validation": self.skip_bids_cb.isChecked(),
            "image_tag": self.tag_edit.text(),
        }


class QSIReconConfigDialog(QtWidgets.QDialog):
    """Configuration dialog for QSIRecon parameters."""

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("QSIRecon Configuration")
        self.setMinimumWidth(450)
        self.setMinimumHeight(500)
        self.config = config or {}
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        try:
            from tit.pre.qsi.utils import get_inherited_dood_resources

            inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        except Exception:
            inherited_cpus, inherited_mem_gb = (
                const.QSI_DEFAULT_CPUS,
                const.QSI_DEFAULT_MEMORY_GB,
            )

        # Reconstruction specs group
        specs_group = QtWidgets.QGroupBox("Reconstruction Specifications")
        specs_layout = QtWidgets.QVBoxLayout(specs_group)

        specs_label = QtWidgets.QLabel("Select reconstruction pipelines to run:")
        specs_label.setStyleSheet(f"color: #888888; font-size: {FONT_HELP};")
        specs_layout.addWidget(specs_label)

        self.spec_checkboxes = {}
        default_specs = self.config.get("recon_specs", ["dipy_dki"])

        for spec in const.QSI_RECON_SPECS:
            cb = QtWidgets.QCheckBox(spec)
            cb.setChecked(spec in default_specs)
            self.spec_checkboxes[spec] = cb
            specs_layout.addWidget(cb)

        layout.addWidget(specs_group)

        # Atlases group (optional)
        atlases_group = QtWidgets.QGroupBox("Atlases for Connectivity (Optional)")
        atlases_layout = QtWidgets.QVBoxLayout(atlases_group)

        self.atlas_checkboxes = {}
        from tit.pre.qsi.config import QSIReconConfig

        temp_config = QSIReconConfig(subject_id="temp")
        default_atlases = self.config.get("atlases", temp_config.atlases) or []

        for atlas in const.QSI_ATLASES:
            cb = QtWidgets.QCheckBox(atlas)
            cb.setChecked(atlas in default_atlases)
            self.atlas_checkboxes[atlas] = cb
            atlases_layout.addWidget(cb)

        layout.addWidget(atlases_group)

        # Resource settings group
        resource_group = QtWidgets.QGroupBox("Resource Settings")
        resource_layout = QtWidgets.QFormLayout(resource_group)

        self.cpus_spin = QtWidgets.QSpinBox()
        self.cpus_spin.setRange(1, multiprocessing.cpu_count())
        self.cpus_spin.setValue(self.config.get("cpus", inherited_cpus))
        resource_layout.addRow("CPUs:", self.cpus_spin)

        self.memory_spin = QtWidgets.QSpinBox()
        self.memory_spin.setRange(4, max(256, int(inherited_mem_gb)))
        self.memory_spin.setValue(self.config.get("memory_gb", inherited_mem_gb))
        self.memory_spin.setSuffix(" GB")
        resource_layout.addRow("Memory:", self.memory_spin)

        layout.addWidget(resource_group)

        # GPU and other options
        options_group = QtWidgets.QGroupBox("Options")
        options_layout = QtWidgets.QFormLayout(options_group)

        self.gpu_cb = QtWidgets.QCheckBox()
        self.gpu_cb.setChecked(self.config.get("use_gpu", False))
        self.gpu_cb.setToolTip(
            "Enable GPU acceleration (requires NVIDIA Docker runtime)"
        )
        options_layout.addRow("Use GPU:", self.gpu_cb)

        self.skip_odf_cb = QtWidgets.QCheckBox()
        self.skip_odf_cb.setChecked(self.config.get("skip_odf_reports", True))
        self.skip_odf_cb.setToolTip("Skip ODF report generation to save time")
        options_layout.addRow("Skip ODF Reports:", self.skip_odf_cb)

        layout.addWidget(options_group)

        # Docker image tag
        tag_layout = QtWidgets.QHBoxLayout()
        tag_layout.addWidget(QtWidgets.QLabel("Image Tag:"))
        self.tag_edit = QtWidgets.QLineEdit()
        self.tag_edit.setText(self.config.get("image_tag", const.QSI_DEFAULT_IMAGE_TAG))
        tag_layout.addWidget(self.tag_edit)
        layout.addLayout(tag_layout)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self.reset_defaults)
        button_layout.addWidget(self.reset_btn)
        button_layout.addStretch()

        self.ok_btn = QtWidgets.QPushButton("OK")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_btn)
        button_layout.addWidget(self.cancel_btn)
        layout.addLayout(button_layout)

    def reset_defaults(self):
        """Reset all settings to defaults."""
        for spec, cb in self.spec_checkboxes.items():
            cb.setChecked(spec == "mrtrix_multishell_msmt_ACT-fast")
        from tit.pre.qsi.config import QSIReconConfig

        temp_config = QSIReconConfig(subject_id="temp")
        default_atlases = temp_config.atlases or []
        for atlas, cb in self.atlas_checkboxes.items():
            cb.setChecked(atlas in default_atlases)
        try:
            from tit.pre.qsi.utils import get_inherited_dood_resources

            inherited_cpus, inherited_mem_gb = get_inherited_dood_resources()
        except Exception:
            inherited_cpus, inherited_mem_gb = (
                const.QSI_DEFAULT_CPUS,
                const.QSI_DEFAULT_MEMORY_GB,
            )
        self.cpus_spin.setValue(inherited_cpus)
        self.memory_spin.setValue(inherited_mem_gb)
        self.gpu_cb.setChecked(False)
        self.skip_odf_cb.setChecked(True)
        self.tag_edit.setText(const.QSI_DEFAULT_IMAGE_TAG)

    def get_config(self):
        """Return the configuration as a dictionary."""
        selected_specs = [
            spec for spec, cb in self.spec_checkboxes.items() if cb.isChecked()
        ]
        selected_atlases = [
            atlas for atlas, cb in self.atlas_checkboxes.items() if cb.isChecked()
        ]

        # Use QSIReconConfig defaults if nothing selected
        if not selected_atlases:
            from tit.pre.qsi.config import QSIReconConfig

            temp_config = QSIReconConfig(subject_id="temp")
            selected_atlases = temp_config.atlases

        return {
            "recon_specs": (
                selected_specs
                if selected_specs
                else ["mrtrix_multishell_msmt_ACT-fast"]
            ),
            "atlases": selected_atlases,
            "cpus": self.cpus_spin.value(),
            "memory_gb": self.memory_spin.value(),
            "use_gpu": self.gpu_cb.isChecked(),
            "skip_odf_reports": self.skip_odf_cb.isChecked(),
            "image_tag": self.tag_edit.text(),
        }
