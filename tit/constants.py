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
    Configuration filenames (``FILE_*``), NIfTI filenames, and common
    extensions (``EXT_*``).
Subject and Naming Patterns
    BIDS prefixes (``PREFIX_*``).
Environment Variables
    Expected ``os.environ`` keys (``ENV_*``).
Docker and Mount Paths
    Container-specific path constants.
Analysis Constants
    Field names (``FIELD_*``), default percentiles, and focality cutoffs.
Simulation Constants
    Simulation types (``SIM_TYPE_*``), modes, electrode shapes, and default
    electrode parameters.
Atlas Names
    Cortical (``ATLAS_DK40``, ``ATLAS_A2009S``) and subcortical atlas
    identifiers.
Logging Constants
    Log levels (``LOG_LEVEL_*``) and format strings (``LOG_FORMAT_*``).
Numerical Constants
    Floating-point tolerances and tissue conductivities (S/m) with
    literature references.
Tissue Conductivity Table
    ``TISSUE_PROPERTIES`` lookup list mapping SimNIBS tissue tag numbers
    to names, conductivities, and references.
GUI Constants
    Window dimensions, tab names, and console buffer sizes.
QSI Integration
    QSIPrep / QSIRecon Docker images, recon specs, atlases, and resource
    defaults.
Validation Bounds
    Min/max ranges for frontend and API input validation.
Default Parameters
    ``DEFAULT_ELECTRODE``, ``DEFAULT_OPTIMIZATION``,
    ``DEFAULT_STATISTICS`` dictionaries.
Telemetry Constants
    GA4 Measurement Protocol settings and operation event names.

See Also
--------
tit.paths : Uses many of these constants for BIDS path resolution.
"""

# ============================================================================
# DIRECTORY NAMES
# ============================================================================

# BIDS-compliant directory structure
DIR_DERIVATIVES = "derivatives"
DIR_SOURCEDATA = "sourcedata"
DIR_CODE = "code"
DIR_REPORTS = "reports"

# Derivative subdirectories
DIR_SIMNIBS = "SimNIBS"
DIR_TI_TOOLBOX = "ti-toolbox"
DIR_LOGS = "logs"
DIR_NILEARN_VISUALS = "nilearn_visuals"

# Subject-level directories
DIR_EEG_POSITIONS = "eeg_positions"
DIR_ROIS = "ROIs"
DIR_EX_SEARCH = "ex-search"
DIR_FLEX_SEARCH = "flex-search"
DIR_LEADFIELDS = "leadfields"
DIR_ANALYSIS = "Analyses"

# Configuration directory
DIR_CONFIG = "config"
DIR_CODE_TI_TOOLBOX = "ti-toolbox"

# ============================================================================
# FILE NAMES AND EXTENSIONS
# ============================================================================

# Configuration files
FILE_MONTAGE_LIST = "montage_list.json"
FILE_ANALYZER_CONFIG = "analyzer.json"
FILE_SIMULATOR_CONFIG = "simulator.json"
FILE_PREPROCESS_CONFIG = "preprocess.json"

# Template files
FILE_EGI_TEMPLATE = "GSN-HydroCel-185.csv"

# NIfTI files
FILE_T1 = "T1.nii.gz"
FILE_DTI_TENSOR = "DTI_coregT1_tensor.nii.gz"

# File extensions
EXT_NIFTI = ".nii.gz"
EXT_MESH = ".msh"
EXT_CSV = ".csv"
EXT_JSON = ".json"
EXT_MAT = ".mat"
EXT_LOG = ".log"
EXT_PNG = ".png"
EXT_PDF = ".pdf"
EXT_HTML = ".html"

# ============================================================================
# SUBJECT AND NAMING PATTERNS
# ============================================================================

# BIDS naming conventions
PREFIX_SUBJECT = "sub-"
PREFIX_SESSION = "ses-"

# ============================================================================
# ENVIRONMENT VARIABLES
# ============================================================================

# Project environment variables
ENV_PROJECT_DIR = "PROJECT_DIR"
ENV_PROJECT_DIR_NAME = "PROJECT_DIR_NAME"
ENV_SUBJECT_NAME = "SUBJECT_NAME"
ENV_SUBJECT_ID = "SUBJECT_ID"

# Tool-specific environment variables
ENV_SELECTED_EEG_NET = "SELECTED_EEG_NET"
ENV_ROI_NAME = "ROI_NAME"
ENV_TI_LOG_FILE = "TI_LOG_FILE"
ENV_FLEX_MONTAGES_FILE = "FLEX_MONTAGES_FILE"

# Display and system variables
ENV_DISPLAY = "DISPLAY"
ENV_HOST_IP = "HOST_IP"

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
FIELD_MTI_MAX = "TI_Max"  # mTI field name in 4-pair simulation meshes
FIELD_TI_NORMAL = "TI_normal"  # Normal component field name

# Default analysis parameters
DEFAULT_PERCENTILES = [95, 99, 99.9]
DEFAULT_FOCALITY_CUTOFFS = [50, 75, 90, 95]
DEFAULT_RADIUS_MM = 5.0

# ============================================================================
# SIMULATION CONSTANTS
# ============================================================================

# Simulation types
SIM_TYPE_TI = "TI"
SIM_TYPE_MTI = "mTI"
SIM_TYPE_TDCS = "tDCS"

# Simulation modes
SIM_MODE_NORMAL = "normal"
SIM_MODE_QUIET = "quiet"
SIM_MODE_DEBUG = "debug"

# Electrode shapes
ELECTRODE_SHAPE_ELLIPSE = "ellipse"
ELECTRODE_SHAPE_RECT = "rect"

# Default electrode parameters
DEFAULT_GEL_THICKNESS = 4.0  # mm (saline gel layer)
DEFAULT_ELECTRODE_RADIUS = 4.0  # mm
DEFAULT_INTENSITY = 1.0  # mA

# Mesh tissue tag ranges for brain cropping
BRAIN_TISSUE_TAG_RANGES = ((1, 100), (1001, 1100))

# Tissue tag values
GM_TISSUE_TAG = 2  # Grey matter element tag in SimNIBS meshes
WM_TISSUE_TAG = 1  # White matter element tag in SimNIBS meshes

# ============================================================================
# ATLAS NAMES
# ============================================================================

# Cortical atlases
ATLAS_DK40 = "DK40"
ATLAS_A2009S = "a2009s"
ATLAS_DESIKAN_KILLIANY = "desikan-killiany"

# Subcortical atlases
ATLAS_ASEG = "aseg"
ATLAS_APARC_ASEG = "aparc+aseg"

# ============================================================================
# LOGGING CONSTANTS
# ============================================================================

# Log levels
LOG_LEVEL_DEBUG = "DEBUG"
LOG_LEVEL_INFO = "INFO"
LOG_LEVEL_WARNING = "WARNING"
LOG_LEVEL_ERROR = "ERROR"
LOG_LEVEL_CRITICAL = "CRITICAL"

# Log format
LOG_FORMAT_STANDARD = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FORMAT_SIMPLE = "%(levelname)s: %(message)s"
LOG_FORMAT_DETAILED = (
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
)

# ============================================================================
# FILE PERMISSIONS
# ============================================================================

# Default permissions for created files/directories
PERM_FULL_ACCESS = 0o777
PERM_READ_WRITE = 0o666
PERM_READ_ONLY = 0o444

# ============================================================================
# VISUALIZATION CONSTANTS
# ============================================================================

# Color schemes
COLOR_RED = "\033[0;31m"
COLOR_GREEN = "\033[0;32m"
COLOR_YELLOW = "\033[0;33m"
COLOR_CYAN = "\033[0;36m"
COLOR_BOLD = "\033[1m"
COLOR_BOLD_CYAN = "\033[1;36m"
COLOR_BOLD_YELLOW = "\033[1;33m"
COLOR_UNDERLINE = "\033[4m"
COLOR_RESET = "\033[0m"

# Plot parameters
PLOT_DPI = 600
PLOT_FIGSIZE_DEFAULT = (10, 8)
PLOT_FIGSIZE_WIDE = (12, 6)
PLOT_FIGSIZE_TALL = (8, 12)

# ============================================================================
# MONTAGE TYPES
# ============================================================================

MONTAGE_TYPE_UNI_POLAR = "uni_polar_montages"
MONTAGE_TYPE_MULTI_POLAR = "multi_polar_montages"

# ============================================================================
# VALIDATION CONSTANTS
# ============================================================================

# Minimum required files for a valid subject
REQUIRED_SUBJECT_FILES = [FILE_T1]

# Valid file extensions for different data types
VALID_MESH_EXTENSIONS = [".msh", ".stl", ".vtk", ".vtu"]
VALID_IMAGE_EXTENSIONS = [".nii", ".nii.gz", ".mgz"]
VALID_ELECTRODE_EXTENSIONS = [".csv", ".txt"]

# ============================================================================
# REPORT GENERATION
# ============================================================================

# Report types
REPORT_TYPE_PREPROCESSING = "preprocessing"
REPORT_TYPE_SIMULATION = "simulation"
REPORT_TYPE_ANALYSIS = "analysis"
REPORT_TYPE_GROUP = "group"

# Report formats
REPORT_FORMAT_HTML = "html"
REPORT_FORMAT_PDF = "pdf"

# ============================================================================
# TIMESTAMP FORMATS
# ============================================================================

TIMESTAMP_FORMAT_DEFAULT = "%Y%m%d_%H%M%S"
TIMESTAMP_FORMAT_READABLE = "%Y-%m-%d %H:%M:%S"
TIMESTAMP_FORMAT_DATE_ONLY = "%Y-%m-%d"
TIMESTAMP_FORMAT_TIME_ONLY = "%H:%M:%S"

# ============================================================================
# NUMERICAL CONSTANTS
# ============================================================================

# Tolerance values
TOLERANCE_FLOAT = 1e-6
TOLERANCE_COORDINATE = 0.1  # mm

# Physical constants
CONDUCTIVITY_GRAY_MATTER = 0.275  # S/m
CONDUCTIVITY_WHITE_MATTER = 0.126  # S/m
CONDUCTIVITY_CSF = 1.654  # S/m
CONDUCTIVITY_BONE = 0.01  # S/m
CONDUCTIVITY_SCALP = 0.465  # S/m
CONDUCTIVITY_EYE = 0.5  # S/m
CONDUCTIVITY_COMPACT_BONE = 0.008  # S/m
CONDUCTIVITY_SPONGY_BONE = 0.025  # S/m
CONDUCTIVITY_BLOOD = 0.6  # S/m
CONDUCTIVITY_MUSCLE = 0.16  # S/m
CONDUCTIVITY_SILICONE_RUBBER = 29.4  # S/m
CONDUCTIVITY_SALINE = 1.0  # S/m

# ============================================================================
# GUI CONSTANTS
# ============================================================================

# Window sizes
GUI_MIN_WIDTH = 800
GUI_MIN_HEIGHT = 600
GUI_DEFAULT_WIDTH = 1200
GUI_DEFAULT_HEIGHT = 800

# Tab names
TAB_SIMULATOR = "Simulator"
TAB_ANALYZER = "Analyzer"
TAB_PREPROCESSOR = "Pre-processor"
TAB_FLEX_SEARCH = "Flex-Search"
TAB_EX_SEARCH = "Ex-Search"
TAB_NIFTI_VIEWER = "NIfTI Viewer"
TAB_SYSTEM_MONITOR = "System Monitor"
TAB_HELP = "Help"
TAB_ACKNOWLEDGMENTS = "Acknowledgments"

# Console buffer sizes
CONSOLE_MAX_LINES = 10000
CONSOLE_MAX_HISTORY = 1000

# ============================================================================
# SYSTEM CONSTANTS
# ============================================================================

# Platform identifiers
PLATFORM_LINUX = "Linux"
PLATFORM_DARWIN = "Darwin"
PLATFORM_WINDOWS = "Windows"

# ============================================================================
# REGEX PATTERNS
# ============================================================================

# Subject ID pattern (matches sub-001, sub-101, etc.)
PATTERN_SUBJECT_ID = r"sub-(\d+)"

# Montage name pattern
PATTERN_MONTAGE_NAME = r"^[a-zA-Z0-9_-]+$"

# Coordinate pattern (matches numbers with optional decimal and sign)
PATTERN_COORDINATE = r"^-?\d+\.?\d*$"


# ============================================================================
# QSI (QSIPrep/QSIRecon) INTEGRATION
# ============================================================================

# QSI Docker images
QSI_QSIPREP_IMAGE = "pennlinc/qsiprep"
QSI_QSIRECON_IMAGE = "pennlinc/qsirecon"
QSI_QSIPREP_IMAGE_TAG = "1.2.0"
QSI_QSIRECON_IMAGE_TAG = "1.2.0"

# QSI directories
DIR_QSIPREP = "qsiprep"
DIR_QSIRECON = "qsirecon"
DIR_DWI = "dwi"

# QSI recon specs (available reconstruction pipelines)
# Organized by category. The full list is flat for validation; comments mark groups.
QSI_RECON_SPECS = [
    # --- Primary: DTI/scalar extraction for SimNIBS anisotropic modeling ---
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

# Default spec for SimNIBS anisotropic DTI extraction
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

# Default atlases for connectivity (optional, not needed for DTI)
QSI_DEFAULT_ATLASES = ["4S156Parcels", "AAL116"]

# QSI default resource settings
QSI_DEFAULT_CPUS = 8
QSI_DEFAULT_MEMORY_GB = 32
QSI_DEFAULT_OMP_THREADS = 1
QSI_DEFAULT_OUTPUT_RESOLUTION = 2.0

# QSI environment variables
ENV_LOCAL_PROJECT_DIR = "LOCAL_PROJECT_DIR"

# FreeSurfer license (always present in SimNIBS container)
FS_LICENSE_PATH = "/usr/local/freesurfer/license.txt"

# ============================================================================
# VERSION INFORMATION
# ============================================================================

# This will be imported from version.py in the root
# Kept here for reference
VERSION_FILE = "version.py"

# ============================================================================
# TISSUE CONDUCTIVITY TABLE
# ============================================================================

TISSUE_PROPERTIES = [
    {
        "number": 1,
        "name": "White Matter",
        "conductivity": CONDUCTIVITY_WHITE_MATTER,
        "reference": "Wagner et al. 2004",
    },
    {
        "number": 2,
        "name": "Gray Matter",
        "conductivity": CONDUCTIVITY_GRAY_MATTER,
        "reference": "Opitz et al. 2015",
    },
    {
        "number": 3,
        "name": "CSF",
        "conductivity": CONDUCTIVITY_CSF,
        "reference": "Wagner et al. 2004",
    },
    {
        "number": 4,
        "name": "Bone",
        "conductivity": CONDUCTIVITY_BONE,
        "reference": "Wagner et al. 2004",
    },
    {
        "number": 5,
        "name": "Scalp",
        "conductivity": CONDUCTIVITY_SCALP,
        "reference": "Wagner et al. 2004",
    },
    {
        "number": 6,
        "name": "Eye balls",
        "conductivity": CONDUCTIVITY_EYE,
        "reference": "Wagner et al. 2004",
    },
    {
        "number": 7,
        "name": "Compact Bone",
        "conductivity": CONDUCTIVITY_COMPACT_BONE,
        "reference": "Gabriel et al. 2009",
    },
    {
        "number": 8,
        "name": "Spongy Bone",
        "conductivity": CONDUCTIVITY_SPONGY_BONE,
        "reference": "Gabriel et al. 2009",
    },
    {
        "number": 9,
        "name": "Blood",
        "conductivity": CONDUCTIVITY_BLOOD,
        "reference": "Gabriel et al. 2009",
    },
    {
        "number": 10,
        "name": "Muscle",
        "conductivity": CONDUCTIVITY_MUSCLE,
        "reference": "Gabriel et al. 2009",
    },
    {
        "number": 11,
        "name": "Silicone Rubber",
        "conductivity": CONDUCTIVITY_SILICONE_RUBBER,
        "reference": "SimNIBS default",
    },
    {
        "number": 12,
        "name": "Saline",
        "conductivity": CONDUCTIVITY_SALINE,
        "reference": "SimNIBS default",
    },
]

# ============================================================================
# EEG NET DEFINITIONS
# ============================================================================

EEG_NETS = [
    {"value": "EGI-256", "label": "EGI HydroCel 256", "electrode_count": 256},
    {"value": "10-10", "label": "10-10 System", "electrode_count": 71},
    {"value": "10-20", "label": "10-20 System", "electrode_count": 21},
]

# ============================================================================
# VALIDATION BOUNDS (for frontend/API)
# ============================================================================

VALIDATION_BOUNDS = {
    "radius": {"min": 1, "max": 100},
    "coordinates": {"min": -150, "max": 150},
    "current_mA": {"min": 0.1, "max": 100},
    "max_iterations": {"min": 50, "max": 2000},
    "population_size": {"min": 4, "max": 100},
    "tolerance": {"min": 0.0001, "max": 1.0},
    "parallel_cores": {"min": 1, "max": 64},
    "electrode_thickness": {"min": 1, "max": 20},
    "n_permutations": {"min": 100, "max": 100000},
}

# ============================================================================
# DEFAULT PARAMETERS (for API/frontend)
# ============================================================================

DEFAULT_ELECTRODE = {
    "shape": ELECTRODE_SHAPE_ELLIPSE,
    "dimensions": [8.0, 8.0],
    "gel_thickness": DEFAULT_GEL_THICKNESS,
    "rubber_thickness": 2.0,
}

DEFAULT_OPTIMIZATION = {
    "max_iterations": 500,
    "population_size": 13,
    "tolerance": 0.1,
    "mutation_min": 0.01,
    "mutation_max": 0.5,
    "recombination": 0.7,
    "current_mA": DEFAULT_INTENSITY,
    "n_multistart": 1,
}

DEFAULT_STATISTICS = {
    "n_permutations": 1000,
    "alpha": 0.05,
    "cluster_threshold": 0.05,
}

# ============================================================================
# TELEMETRY CONSTANTS
# ============================================================================

# Environment variable to disable telemetry (any truthy value)
ENV_NO_TELEMETRY = "TIT_NO_TELEMETRY"

# Config directory and file (under ~/.config)
TELEMETRY_CONFIG_DIR = "ti-toolbox"
TELEMETRY_CONFIG_FILE = "telemetry.json"

# Google Analytics 4 Measurement Protocol
# Replace these placeholders after creating your GA4 property.
# See: https://developers.google.com/analytics/devguides/collection/protocol/ga4
GA4_MEASUREMENT_ID = "G-2GGJF2D8C7"
GA4_API_SECRET = "6ZFk0B3STC-t3ZJsZmTPbg"
GA4_ENDPOINT = "https://www.google-analytics.com/mp/collect"

# Telemetry HTTP timeout (seconds) — keep short so it never blocks
TELEMETRY_TIMEOUT_S = 5

# Operation event names (used as GA4 event names)
TELEMETRY_OP_SIM_TI = "sim_ti"
TELEMETRY_OP_SIM_MTI = "sim_mti"
TELEMETRY_OP_FLEX_SEARCH = "flex_search"
TELEMETRY_OP_EX_SEARCH = "ex_search"
TELEMETRY_OP_ANALYSIS = "analysis"
TELEMETRY_OP_GUI_LAUNCH = "gui_launch"
