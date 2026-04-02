#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""QSIPrep and QSIRecon configuration dialogs."""

import multiprocessing

from PyQt5 import QtWidgets

from tit import constants as const
from tit.gui.style import FONT_SM, FONT_HELP


class QSIPrepConfigDialog(QtWidgets.QDialog):
    """Configuration dialog for QSIPrep DWI preprocessing parameters.

    Exposes output resolution, resource limits (CPUs, memory, OMP threads),
    denoising/unringing methods, BIDS validation toggle, and Docker image tag.

    Parameters
    ----------
    parent : QWidget or None
        Parent widget.
    config : dict or None
        Previously saved configuration to pre-populate the controls.
    """

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
        self.tag_edit.setText(self.config.get("image_tag", const.QSI_QSIPREP_IMAGE_TAG))
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
        self.tag_edit.setText(const.QSI_QSIPREP_IMAGE_TAG)

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


# ---------------------------------------------------------------------------
# Recon spec / atlas metadata for the QSIRecon dialog
# ---------------------------------------------------------------------------

# (spec_name, short_description)
_SPEC_CATEGORIES = [
    (
        "DTI / Scalar Extraction",
        "Produces tensor components for SimNIBS anisotropic modeling.",
        [
            (
                "dsi_studio_gqi",
                "GQI + deterministic tractography. Outputs tensor "
                "components (txx-tzz), QA, GFA, ISO.",
            ),
        ],
    ),
    (
        "Tractography -- MRTrix3",
        "CSD-based probabilistic tractography (iFOD2, 10M streamlines, SIFT2).",
        [
            (
                "mrtrix_multishell_msmt_ACT-hsvs",
                "Multi-shell MSMT CSD, ACT with hybrid surface-volume "
                "segmentation. Requires FreeSurfer.",
            ),
            (
                "mrtrix_multishell_msmt_ACT-fast",
                "Multi-shell MSMT CSD, ACT with FSL FAST segmentation. "
                "Requires FreeSurfer.",
            ),
            (
                "mrtrix_multishell_msmt_noACT",
                "Multi-shell MSMT CSD, no anatomical constraints.",
            ),
            (
                "mrtrix_singleshell_ss3t_ACT-hsvs",
                "Single-shell SS3T CSD, ACT with HSVS segmentation. "
                "Requires FreeSurfer.",
            ),
            (
                "mrtrix_singleshell_ss3t_ACT-fast",
                "Single-shell SS3T CSD, ACT with FSL FAST segmentation. "
                "Requires FreeSurfer.",
            ),
            (
                "mrtrix_singleshell_ss3t_noACT",
                "Single-shell SS3T CSD, no anatomical constraints.",
            ),
        ],
    ),
    (
        "Tractography -- Bundle Identification",
        "Automated white-matter tract recognition.",
        [
            (
                "dsi_studio_autotrack",
                "QSDR + AutoTrack: identifies 56 white-matter bundles " "in MNI space.",
            ),
            (
                "pyafq_tractometry",
                "Automated Fiber Quantification (PyAFQ): recognizes "
                "major WM pathways.",
            ),
            (
                "mrtrix_multishell_msmt_pyafq_tractometry",
                "MRTrix3 CSD tractography combined with PyAFQ bundle " "analysis.",
            ),
            (
                "ss3t_fod_autotrack",
                "Single-shell FOD variant of DSI Studio AutoTrack.",
            ),
        ],
    ),
    (
        "Microstructural Models",
        "Voxel-wise diffusion model fitting (no tractography).",
        [
            (
                "dipy_dki",
                "Diffusion Kurtosis Imaging: AK, RK, MK, KFA, plus "
                "all DTI scalars (FA, MD, AD, RD).",
            ),
            (
                "dipy_mapmri",
                "MAP-MRI: ensemble average propagator estimation. "
                "Outputs RTOP, RTAP, QIV, MSD + ODFs.",
            ),
            (
                "dipy_3dshore",
                "3dSHORE (BrainSuite): anisotropy scalars + ODFs.",
            ),
            (
                "amico_noddi",
                "NODDI via AMICO framework: ICVF, ISOVF, OD scalars.",
            ),
            (
                "TORTOISE",
                "TORTOISE tensor fitting + MAPMRI: NG, PA, RTOP, RTAP.",
            ),
        ],
    ),
    (
        "Composite Pipelines",
        "Run multiple models in one pass. These subsume individual specs above.",
        [
            (
                "multishell_scalarfest",
                "DKI + TORTOISE + GQI + NODDI, no tractography. "
                "Subsumes: dipy_dki, TORTOISE, dsi_studio_gqi, "
                "amico_noddi.",
            ),
            (
                "hbcd_scalar_maps",
                "DKI + TORTOISE + GQI + DSI AutoTrack. "
                "Subsumes: dipy_dki, TORTOISE, dsi_studio_gqi, "
                "dsi_studio_autotrack.",
            ),
            (
                "abcd_recon",
                "ABCD study-specific composite reconstruction.",
            ),
        ],
    ),
    (
        "Utility / Experimental",
        "",
        [
            (
                "reorient_fslstd",
                "Reorient preprocessed DWI to FSL standard orientation "
                "(no model fitting).",
            ),
            (
                "csdsi_3dshore",
                "Experimental: for DSI/CS-DSI data. Imputes a "
                "multi-shell HCP sampling scheme.",
            ),
        ],
    ),
]

# (atlas_name, short_description)
_ATLAS_CATEGORIES = [
    (
        "4S Series -- Schaefer cortical + 56 subcortical ROIs",
        "Resolution variants of the same parcellation. The 56 subcortical "
        "regions come from CIT168, HCP Thalamus, HCP Amygdala/Hippocampus, "
        "and MDTB Cerebellum.",
        [
            ("4S156Parcels", "Schaefer 100 cortical + 56 subcortical"),
            ("4S256Parcels", "Schaefer 200 + 56 subcortical"),
            ("4S356Parcels", "Schaefer 300 + 56 subcortical"),
            ("4S456Parcels", "Schaefer 400 + 56 subcortical"),
            ("4S556Parcels", "Schaefer 500 + 56 subcortical"),
            ("4S656Parcels", "Schaefer 600 + 56 subcortical"),
            ("4S756Parcels", "Schaefer 700 + 56 subcortical"),
            ("4S856Parcels", "Schaefer 800 + 56 subcortical"),
            ("4S956Parcels", "Schaefer 900 + 56 subcortical"),
            ("4S1056Parcels", "Schaefer 1000 + 56 subcortical"),
        ],
    ),
    (
        "Classic Atlases (extended with subcortical regions)",
        "",
        [
            (
                "AAL116",
                "Automated Anatomical Labeling: 116 macro-anatomical "
                "regions (Tzourio-Mazoyer et al. 2002).",
            ),
            (
                "Brainnetome246Ext",
                "Connectivity-based parcellation: 246 regions " "(Fan et al. 2016).",
            ),
            (
                "AICHA384Ext",
                "Homotopic connectivity atlas: 384 regions " "(Joliot et al. 2015).",
            ),
            (
                "Gordon333Ext",
                "Resting-state fMRI boundary mapping: 333 regions "
                "(Gordon et al. 2016).",
            ),
        ],
    ),
]

# CSS fragments for category headers inside the scroll area.
_CSS_CATEGORY = (
    "font-weight: bold; font-size: {font}; margin-top: 6px; "
    "padding: 2px 0px; color: #333333;"
)
_CSS_HINT = "color: #888888; font-size: {font}; margin-bottom: 2px;"


class QSIReconConfigDialog(QtWidgets.QDialog):
    """Configuration dialog for QSIRecon reconstruction parameters.

    Provides categorised checkbox lists for reconstruction specifications
    and connectivity atlases, plus resource and GPU settings.

    Parameters
    ----------
    parent : QWidget or None
        Parent widget.
    config : dict or None
        Previously saved configuration to pre-populate the controls.
    """

    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("QSIRecon Configuration")
        self.setMinimumWidth(520)
        self.setMinimumHeight(600)
        self.config = config or {}
        self.setup_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

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

        # ---------- scrollable area for specs + atlases ----------
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll_widget = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        self.spec_checkboxes = {}
        self.atlas_checkboxes = {}

        default_specs = self.config.get("recon_specs", [const.QSI_DEFAULT_RECON_SPEC])

        from tit.pre.qsi.config import QSIReconConfig

        temp_config = QSIReconConfig(subject_id="temp")
        default_atlases = self.config.get("atlases", temp_config.atlases) or []

        # -- Reconstruction Specifications --
        specs_group = QtWidgets.QGroupBox("Reconstruction Specifications")
        specs_inner = QtWidgets.QVBoxLayout(specs_group)
        specs_inner.setSpacing(2)

        for cat_title, cat_hint, items in _SPEC_CATEGORIES:
            self._add_category_header(specs_inner, cat_title, cat_hint)
            for spec_name, tooltip in items:
                cb = QtWidgets.QCheckBox(spec_name)
                cb.setToolTip(tooltip)
                cb.setChecked(spec_name in default_specs)
                self.spec_checkboxes[spec_name] = cb
                specs_inner.addWidget(cb)

        scroll_layout.addWidget(specs_group)

        # -- Atlases --
        atlases_group = QtWidgets.QGroupBox("Atlases for Connectivity (Optional)")
        atlases_inner = QtWidgets.QVBoxLayout(atlases_group)
        atlases_inner.setSpacing(2)

        hint = QtWidgets.QLabel("Not required for the DTI-to-SimNIBS workflow.")
        hint.setStyleSheet(_CSS_HINT.format(font=FONT_HELP))
        hint.setWordWrap(True)
        atlases_inner.addWidget(hint)

        for cat_title, cat_hint, items in _ATLAS_CATEGORIES:
            self._add_category_header(atlases_inner, cat_title, cat_hint)
            for atlas_name, tooltip in items:
                cb = QtWidgets.QCheckBox(atlas_name)
                cb.setToolTip(tooltip)
                cb.setChecked(atlas_name in default_atlases)
                self.atlas_checkboxes[atlas_name] = cb
                atlases_inner.addWidget(cb)

        scroll_layout.addWidget(atlases_group)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, stretch=1)

        # ---------- fixed bottom: resources, options, buttons ----------

        # Resource settings
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

        # Options
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
        self.tag_edit.setText(
            self.config.get("image_tag", const.QSI_QSIRECON_IMAGE_TAG)
        )
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_category_header(parent_layout, title, hint=""):
        """Add a styled category label (+ optional hint) with a separator."""
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        parent_layout.addWidget(line)

        label = QtWidgets.QLabel(title)
        label.setStyleSheet(_CSS_CATEGORY.format(font=FONT_SM))
        parent_layout.addWidget(label)

        if hint:
            hint_label = QtWidgets.QLabel(hint)
            hint_label.setStyleSheet(_CSS_HINT.format(font=FONT_HELP))
            hint_label.setWordWrap(True)
            parent_layout.addWidget(hint_label)

    # ------------------------------------------------------------------
    # Reset / read
    # ------------------------------------------------------------------

    def reset_defaults(self):
        """Reset all settings to defaults."""
        for spec, cb in self.spec_checkboxes.items():
            cb.setChecked(spec == const.QSI_DEFAULT_RECON_SPEC)

        for atlas, cb in self.atlas_checkboxes.items():
            cb.setChecked(False)

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
        self.tag_edit.setText(const.QSI_QSIRECON_IMAGE_TAG)

    def get_config(self):
        """Return the configuration as a dictionary."""
        selected_specs = [
            spec for spec, cb in self.spec_checkboxes.items() if cb.isChecked()
        ]
        selected_atlases = [
            atlas for atlas, cb in self.atlas_checkboxes.items() if cb.isChecked()
        ]

        return {
            "recon_specs": (
                selected_specs if selected_specs else [const.QSI_DEFAULT_RECON_SPEC]
            ),
            "atlases": selected_atlases or None,
            "cpus": self.cpus_spin.value(),
            "memory_gb": self.memory_spin.value(),
            "use_gpu": self.gpu_cb.isChecked(),
            "skip_odf_reports": self.skip_odf_cb.isChecked(),
            "image_tag": self.tag_edit.text(),
        }
