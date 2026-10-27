#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""Project-wide constants for TI-Toolbox.

Centralises all hard-coded values, magic numbers, and configuration defaults
used across the TI-Toolbox codebase.  Constants are grouped by domain:

Sections
--------
Directory Names
    BIDS-compliant directory structure names (``DIR_*``).
File Names and Extensions
    Configuration and NIfTI filenames (``FILE_*``) and ``EXT_CSV``.
Subject and Naming Patterns
    BIDS prefixes (``PREFIX_*``).
Environment Variables
    Expected ``os.environ`` keys (``ENV_*``).
Docker and Mount Paths
    Container-specific path constants.
Analysis Constants
    Field names (``FIELD_*``), the output-field registry and the fsaverage
    node counts.
Simulation Constants
    Electrode-pair counts and brain tissue tags.
Numerical Constants
    White-matter conductivity (S/m) for the DTI advisories.
QSI Integration
    QSIPrep / QSIRecon Docker images, recon specs, atlases, and resource
    defaults.
Telemetry Constants
    GA4 Measurement Protocol settings and operation event names.

See Also
--------
tit.paths : Uses many of these constants for BIDS path resolution.
"""

import os
from dataclasses import dataclass

# ============================================================================
# DIRECTORY NAMES
# ============================================================================

# BIDS-compliant directory structure
DIR_DERIVATIVES = "derivatives"
# Derivative subdirectories
DIR_TI_TOOLBOX = "ti-toolbox"
DIR_NILEARN_VISUALS = "nilearn_visuals"


# ============================================================================
# FILE NAMES AND EXTENSIONS
# ============================================================================

# Configuration files
FILE_MONTAGE_LIST = "montage_list.json"
# NIfTI files
FILE_T1 = "T1.nii.gz"
FILE_DTI_TENSOR = "DTI_coregT1_tensor.nii.gz"
FILE_DTI_QC = "DTI_coregT1_qc.json"

# File extensions
EXT_CSV = ".csv"


# ============================================================================
# SUBJECT AND NAMING PATTERNS
# ============================================================================

# BIDS naming conventions
PREFIX_SUBJECT = "sub-"


# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

# Project environment variables
ENV_PROJECT_DIR = "PROJECT_DIR"
ENV_PROJECT_DIR_NAME = "PROJECT_DIR_NAME"


# ============================================================================
# DOCKER AND MOUNT PATHS
# ============================================================================

# Docker mount point
DOCKER_MOUNT_PREFIX = "/mnt"


# ============================================================================
# ANALYSIS CONSTANTS
# ============================================================================

# Field names (SimNIBS convention)
FIELD_TI_MAX = "TI_max"  # TI field name in 2-pair simulation meshes
FIELD_MTI_MAX = "mTI_max"  # mTI field name in 4-pair simulation meshes
FIELD_TI_NORMAL = "TI_normal"  # Normal component field name
FIELD_TI_AVG = "TI_avg"  # envelope averaged over direction (calc.envelope_mean)
FIELD_HF_PEAK = "hf_peak"  # peak carrier field, max over sign choices of the
# vector sum; at N=2 this is max(|E1+E2|,|E1-E2|) (Cassarà 2025)
FIELD_HF_SAR = "hf_sar"  # sum_i |E_i|^2 = 2 * calc.hf_power (rename pending)
FIELD_HF_POWER_DENSITY = "hf_power_density"  # sigma * calc.hf_power, W/m^3

# Field "kind" classification used by FieldSpec below. This groups fields by
# what they are computed from -- the low-frequency envelope versus the carrier
# fields themselves -- and is used only to select subsets programmatically. It
# is deliberately not surfaced in the UI: which of these bear on efficacy and
# which on safety is still debated, so the interface states each field's
# definition and lets the user decide.
FIELD_KIND_FUNCTIONAL = "functional"  # envelope-derived
FIELD_KIND_SAFETY = "safety"  # carrier-derived


@dataclass(frozen=True)
class FieldSpec:
    """Metadata for one output field quantity (mesh/NIfTI field name).

    Attributes
    ----------
    name : str
        Exact on-disk / in-mesh field name (matches a ``FIELD_*`` constant).
    label : str
        Short label for UI widgets (checkboxes, combo boxes).
    kind : str
        ``FIELD_KIND_FUNCTIONAL`` or ``FIELD_KIND_SAFETY``.
    units : str
        Physical units of the field values.
    description : str
        One-line tooltip text.
    """

    name: str
    label: str
    kind: str
    units: str
    description: str


#: Single source of truth for the seven output field quantities. Order here
#: is the canonical display order (``get_field_names()`` preserves it; the
#: desktop app's field lists mirror it).
FIELD_REGISTRY: tuple[FieldSpec, ...] = (
    FieldSpec(
        name=FIELD_TI_MAX,
        label=FIELD_TI_MAX,
        kind=FIELD_KIND_FUNCTIONAL,
        units="V/m",
        description=(
            "Envelope modulation depth (peak-to-trough), maximised over "
            "direction (Grossman et al. 2017; Hirata et al. 2024)."
        ),
    ),
    FieldSpec(
        name=FIELD_MTI_MAX,
        label=FIELD_MTI_MAX,
        kind=FIELD_KIND_FUNCTIONAL,
        units="V/m",
        description=(
            "Modulation depth (peak-to-trough envelope), maximum over direction "
            "(4-pair/mTI mesh spelling)."
        ),
    ),
    FieldSpec(
        name=FIELD_TI_NORMAL,
        label=FIELD_TI_NORMAL,
        kind=FIELD_KIND_FUNCTIONAL,
        units="V/m",
        description="Modulation depth along the cortical surface normal.",
    ),
    FieldSpec(
        name=FIELD_TI_AVG,
        label=FIELD_TI_AVG,
        kind=FIELD_KIND_FUNCTIONAL,
        units="V/m",
        description=(
            "Envelope modulation depth (peak-to-trough), averaged over "
            "all directions rather than maximised."
        ),
    ),
    FieldSpec(
        name=FIELD_HF_PEAK,
        label=FIELD_HF_PEAK,
        kind=FIELD_KIND_SAFETY,
        units="V/m",
        description=(
            "Largest instantaneous magnitude of the summed carrier fields "
            "(peak-to-zero): max over sign choices of |sum_i s_i*E_i| "
            "(Cassarà et al. 2025, Eq. 3)."
        ),
    ),
    FieldSpec(
        name=FIELD_HF_SAR,
        label=FIELD_HF_SAR,
        kind=FIELD_KIND_SAFETY,
        units="(V/m)^2",
        description=(
            "Sum of carrier power, sum_i |E_i|^2. Proportional to SAR but not "
            "calibrated: SAR = (sigma/2*rho)*hf_sar (Cassarà et al. 2025)."
        ),
    ),
    FieldSpec(
        name=FIELD_HF_POWER_DENSITY,
        label=FIELD_HF_POWER_DENSITY,
        kind=FIELD_KIND_SAFETY,
        units="W/m^3",
        description=(
            "Time-averaged carrier power absorbed per volume, "
            "(1/2) sum_i E_i.sigma.E_i with the simulation's own conductivity; "
            "SAR = hf_power_density/rho (IEEE C95.1-2019)."
        ),
    ),
)


def get_field_names(kind: str | None = None) -> tuple[str, ...]:
    """Return registered field names in registry order.

    Parameters
    ----------
    kind : str, optional
        If given, restrict to ``FIELD_KIND_FUNCTIONAL`` or ``FIELD_KIND_SAFETY``.
    """
    if kind is None:
        return tuple(spec.name for spec in FIELD_REGISTRY)
    return tuple(spec.name for spec in FIELD_REGISTRY if spec.kind == kind)


#: Definition of each selectable output field, as
#: ``(name, units, definition, equation, reference)``. Equations match the
#: implementations in :mod:`tit.calc`; ``E_i`` is the
#: field from electrode pair *i* and ``n`` a unit direction. No route serves
#: it and the desktop app writes its own help text; it is the cited statement
#: of each equation that the test suite checks against the registry.
OUTPUT_FIELD_DEFINITIONS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        FIELD_TI_MAX,
        "V/m",
        "Depth of the low-frequency envelope modulation (peak-to-trough), "
        "maximised over direction.",
        "Two pairs: 2*min(|E1.n|, |E2.n|) at the optimal n, evaluated via a "
        "closed form. K channels: | |S n| - |D n| | = 4|sum_k a_k*b_k| / "
        "(|S n| + |D n|), where a_k = E_ka.n, b_k = E_kb.n and S, D have rows "
        "E_ka + E_kb, E_ka - E_kb; maximised over n by an eigen-branch "
        "root-find.",
        "Grossman et al. 2017, Cell 169(6):1029-1041; "
        "Hirata et al. 2024, Comput Biol Med 178:108697.",
    ),
    (
        FIELD_TI_AVG,
        "V/m",
        "The same envelope depth averaged over all directions instead of "
        "maximised, i.e. what an arbitrarily oriented element sees on average.",
        "Mean over all directions of the expression above: exact closed form "
        "|E1| + |E2| - (|E1+E2| + |E1-E2|)/2 for two pairs, a 4096-direction "
        "sphere quadrature for K channels.",
        "Direction-averaged form of Grossman et al. 2017.",
    ),
    (
        FIELD_HF_PEAK,
        "V/m",
        "Largest instantaneous magnitude the summed carrier fields can reach "
        "(peak-to-zero, not peak-to-trough).",
        "max over s_i in {-1,+1} of |sum_i s_i*E_i|, exact for any number of "
        "fields (zonotope vertices).",
        "Cassara et al. 2025, Eq. 3.",
    ),
    (
        FIELD_HF_SAR,
        "(V/m)^2",
        "Sum of carrier power. The carriers sit at different, incommensurate "
        "frequencies, so their power adds rather than their amplitudes. This "
        "is a field-domain quantity, not calibrated SAR: that is "
        "(sigma/2*rho)*hf_sar and needs per-tissue conductivity and density.",
        "sum_i |E_i|^2",
        "Cassara et al. 2025.",
    ),
    (
        FIELD_HF_POWER_DENSITY,
        "W/m^3",
        "Time-averaged carrier power absorbed per unit volume (Joule heating), "
        "with the per-element conductivity the simulation solved with. Divided "
        "by tissue density it is SAR; at 1-10 kHz, though, the exposure "
        "standards limit the RMS in-situ field, not SAR.",
        "(1/2) sum_i E_i^T sigma E_i: sigma*hf_power for isotropic conductivity, "
        "the conductivity tensor for anisotropic (DTI) models.",
        "IEEE C95.1-2019, p. 35; Cassara et al. 2025, Part II Eq. 1.",
    ),
)


def get_field_spec(name: str) -> FieldSpec:
    """Look up a :class:`FieldSpec` by its exact field name.

    Raises
    ------
    KeyError
        If ``name`` is not in :data:`FIELD_REGISTRY`.
    """
    for spec in FIELD_REGISTRY:
        if spec.name == name:
            return spec
    raise KeyError(f"Unknown field name: {name!r}")


#: The five volume-mesh output fields a simulation may selectively compute
#: and write (``SimulationConfig.output_fields``). Excludes ``FIELD_MTI_MAX``
#: (the mTI on-disk spelling of ``FIELD_TI_MAX``, not a distinct user choice)
#: and ``FIELD_TI_NORMAL`` (a node field on a separate surface mesh, not a
#: volume field produced by the same post-processing step).
SELECTABLE_OUTPUT_FIELDS: tuple[str, ...] = tuple(
    spec.name
    for spec in FIELD_REGISTRY
    if spec.name not in (FIELD_MTI_MAX, FIELD_TI_NORMAL)
)


#: The selectable fields defined without an envelope: what a carrier-only
#: (ΔF = 0) simulation may compute (``SimulationConfig.carrier_only``).
CARRIER_OUTPUT_FIELDS: tuple[str, ...] = (
    FIELD_HF_PEAK,
    FIELD_HF_SAR,
    FIELD_HF_POWER_DENSITY,
)


#: Field names valid on the fsaverage surface: every registered field except
#: ``FIELD_MTI_MAX`` ("mTI_max"), ``FIELD_TI_AVG`` ("TI_avg") and
#: ``FIELD_HF_POWER_DENSITY`` ("hf_power_density"). The
#: central-surface pipeline always emits ``TI_max`` regardless of whether the
#: simulation was 2-pair or 4-pair, so there is no separate mTI fsaverage
#: field; ``TI_avg`` has no central-surface overlay to project (it is only
#: written as a volume field), so it is excluded too rather than added to
#: :mod:`tit.source.fsaverage` sight-unseen. ``hf_power_density`` is excluded
#: because that module interpolates only the carrier E-fields onto the central
#: surface; the conductivity (a tensor field under DTI models) would have to be
#: interpolated with them, which it does not do. Derived here (rather than in
#: each consumer) so :mod:`tit.source.config` and :mod:`tit.stats.config`
#: cannot drift apart. Lives in this leaf module because importing
#: ``tit.source.config`` would execute ``tit/source/__init__.py`` and pull in
#: ``mne`` via ``tit.source.forward``.
FSAVG_FIELD_NAMES: tuple[str, ...] = tuple(
    spec.name
    for spec in FIELD_REGISTRY
    if spec.name not in (FIELD_MTI_MAX, FIELD_TI_AVG, FIELD_HF_POWER_DENSITY)
)


# fsaverage total node counts (both hemispheres) per subdivision factor.
# ico5/6/7 surfaces: 10242/40962/163842 vertices per hemisphere, doubled.
# Lives here (a leaf module) so surface/stats/plotting can share it without
# importing tit.source, which would pull in mne via tit.source.forward.
FSAVG_NODES = {5: 20484, 6: 81924, 7: 327684}


# ============================================================================
# SIMULATION CONSTANTS
# ============================================================================

# ----------------------------------------------------------------------------
# Electrode-pair (channel) counts
# ----------------------------------------------------------------------------
# One electrode pair is one current channel. The engine is quasi-static: each
# FEM field is a phasor amplitude vector, and every channel must be paired with
# another to form a beat, so the pair count is always **even**. Two pairs is
# standard TI (one beat); four or more even pairs is mTI (2, 4, 6, 8, 12, 16 …).
# This is the single rule -- the config validators, tit.calc's field-list
# validation and the montage editors all state it in terms of these constants.

#: Fewest electrode pairs a montage can have (standard TI).
MIN_ELECTRODE_PAIRS = 2

#: Electrode-pair count that means standard TI rather than mTI.
TI_ELECTRODE_PAIRS = 2


def is_valid_pair_count(n: int) -> bool:
    """Is *n* an allowed electrode-pair (channel) count?

    ``True`` for even counts of at least `MIN_ELECTRODE_PAIRS`: 2, 4, 6, 8, …
    Odd counts leave a channel with nothing to beat against, and a single
    pair is tACS, not TI.
    """
    return n >= MIN_ELECTRODE_PAIRS and n % 2 == 0


#: Human-readable form of `is_valid_pair_count`, for error messages.
PAIR_COUNT_RULE = (
    f"an even number of electrode pairs, at least {MIN_ELECTRODE_PAIRS} "
    f"({TI_ELECTRODE_PAIRS} = TI, 4 or more = mTI)"
)


# Mesh tissue tag ranges for brain cropping
BRAIN_TISSUE_TAG_RANGES = ((1, 100), (1001, 1100))


# ============================================================================
# NUMERICAL CONSTANTS
# ============================================================================

CONDUCTIVITY_WHITE_MATTER = 0.126  # S/m


# ============================================================================
# QSI (QSIPrep/QSIRecon) INTEGRATION
# ============================================================================

# QSI Docker images
QSI_QSIPREP_IMAGE = "pennlinc/qsiprep"
QSI_QSIRECON_IMAGE = "pennlinc/qsirecon"
QSI_QSIPREP_IMAGE_TAG = "26.0.0"
QSI_QSIRECON_IMAGE_TAG = "26.0.0"

# QSI recon specs (available reconstruction pipelines)
# Organized by category. The full list is flat for validation; comments mark groups.
QSI_RECON_SPECS = [
    # --- Scalars: GQI + DTI maps from DSI Studio (no tractography in our spec) ---
    "dsi_studio_gqi",
    # --- Tractography: MRTrix CSD-based pipelines ---
    "mrtrix_multishell_msmt_ACT-hsvs",
    "mrtrix_multishell_msmt_ACT-fast",
    "mrtrix_multishell_msmt_noACT",
    "mrtrix_singleshell_ss3t_ACT-hsvs",
    "mrtrix_singleshell_ss3t_ACT-fast",
    "mrtrix_singleshell_ss3t_noACT",
    # --- Tractography: PyAFQ and autotrack ---
    "pyafq_tractometry",
    "mrtrix_multishell_msmt_pyafq_tractometry",
    "ss3t_fod_autotrack",
    "dsi_studio_autotrack",
    # --- Scalar / microstructural models ---
    "dipy_dki",
    "dipy_mapmri",
    "dipy_3dshore",
    "amico_noddi",
    "TORTOISE",
    "multishell_scalarfest",
    "hbcd_scalar_maps",
    # --- Utility / experimental ---
    "reorient_fslstd",
    "csdsi_3dshore",
    "abcd_recon",
]

# Default QSIRecon spec. QSIRecon is optional: the SimNIBS DTI tensor is fitted from
# QSIPrep output directly (tit.pre.qsi.dti_extractor), so this only preselects scalar maps.
QSI_DEFAULT_RECON_SPEC = "dsi_studio_gqi"

# QSI atlases (available for connectivity analysis)
# The 4S series (Schaefer cortical + 56 subcortical ROIs) are resolution
# variants of the same parcellation (100–1000 cortical parcels + 56 subcortical).
QSI_ATLASES = [
    "4S156Parcels",
    "4S256Parcels",
    "4S356Parcels",
    "4S456Parcels",
    "4S556Parcels",
    "4S656Parcels",
    "4S756Parcels",
    "4S856Parcels",
    "4S956Parcels",
    "4S1056Parcels",
    "AAL116",
    "Brainnetome246Ext",
    "AICHA384Ext",
    "Gordon333Ext",
]

# QSI default resource settings
QSI_DEFAULT_MEMORY_GB = 32
# Threads per process, mirroring QSIPrep's own default of min(nprocs - 1, 8).
# This was pinned at 1, which left every ANTs registration single-threaded --
# one subject's anatomical normalization took 72 minutes on a 24-core host.
# The cap is QSIPrep's: ANTs stops scaling well past 8 threads.
QSI_DEFAULT_OMP_THREADS = min(max((os.cpu_count() or 2) - 1, 1), 8)
# Only the default of the low-level QSIPrepConfig; the pipeline setting defaults to None,
# which means the native DWI voxel size (tit.pre.qsi.utils.native_dwi_resolution).
QSI_DEFAULT_OUTPUT_RESOLUTION = 2.0

# QSI DWI validation. The b=0 cutoff matches QSIPrep's own --b0-threshold
# default, and six directions is the algebraic minimum for a diffusion tensor.
QSI_B0_THRESHOLD = 100.0
QSI_MIN_DWI_DIRECTIONS = 6

# Written into a DWI sidecar that has no TotalReadoutTime and nothing to derive
# one from. Only used when the subject has no fieldmap and a single
# phase-encoding direction, where the value is a scale factor that cancels;
# 0.05 s is the conventional FSL stand-in for that case.
QSI_FALLBACK_TOTAL_READOUT_TIME = 0.05

# QSI environment variables
ENV_LOCAL_PROJECT_DIR = "LOCAL_PROJECT_DIR"

# License for optional FreeSurfer and QSI workflows that require it.
# The core FastSurfer workflow needs none. Override with $FS_LICENSE; see
# tit.pre.qsi.docker_builder.resolve_fs_license_path.
FS_LICENSE_PATH = "/usr/local/freesurfer/license.txt"


# ============================================================================
# TELEMETRY CONSTANTS
# ============================================================================

# Environment variable to disable telemetry (any truthy value)
ENV_NO_TELEMETRY = "TIT_NO_TELEMETRY"

# Config file
TELEMETRY_CONFIG_FILE = "telemetry.json"

# User-level config directory inside Docker container
# The Electron launcher mounts the host config dir here.
USER_CONFIG_CONTAINER_PATH = "/root/.config/ti-toolbox"

# Google Analytics 4 Measurement Protocol
# Replace these placeholders after creating your GA4 property.
# See: https://developers.google.com/analytics/devguides/collection/protocol/ga4
GA4_MEASUREMENT_ID = "G-2GGJF2D8C7"
GA4_API_SECRET = "6ZFk0B3STC-t3ZJsZmTPbg"
GA4_ENDPOINT = "https://www.google-analytics.com/mp/collect"

# Telemetry HTTP timeout (seconds) — keep short so it never blocks
TELEMETRY_TIMEOUT_S = 5

# Operation event names (used as GA4 event names)
# -- Simulation --
TELEMETRY_OP_SIM_TI = "sim_ti"
TELEMETRY_OP_SIM_MTI = "sim_mti"
# -- Optimization --
TELEMETRY_OP_FLEX_SEARCH = "flex_search"
TELEMETRY_OP_EX_SEARCH = "ex_search"
# -- Analysis --
TELEMETRY_OP_ANALYSIS = "analysis"
TELEMETRY_OP_GROUP_ANALYSIS = "group_analysis"
# -- Preprocessing --
TELEMETRY_OP_PRE_PIPELINE = "pre_pipeline"
TELEMETRY_OP_PRE_CHARM = "pre_charm"
TELEMETRY_OP_PRE_FASTSURFER = "pre_fastsurfer"
TELEMETRY_OP_PRE_DICOM = "pre_dicom"
TELEMETRY_OP_PRE_QSIPREP = "pre_qsiprep"
TELEMETRY_OP_PRE_QSIRECON = "pre_qsirecon"
# -- Statistics --
TELEMETRY_OP_STATS = "stats_comparison"
# -- Blender / visualization --
TELEMETRY_OP_BLENDER_MONTAGE = "blender_montage"
TELEMETRY_OP_BLENDER_REGIONS = "blender_regions"
TELEMETRY_OP_BLENDER_VECTORS = "blender_vectors"
# -- Lifecycle --
TELEMETRY_OP_FIRST_OPEN = "first_open"
