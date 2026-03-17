"""
Shared fixtures and configuration for TI-Toolbox tests.

Mocks heavy/unavailable dependencies (simnibs, bpy) at import level
and provides BIDS-compliant temporary project structures.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# ============================================================================
# Mock unavailable dependencies before any tit imports
# ============================================================================


def _install_mock_module(name: str) -> MagicMock:
    """Insert a MagicMock into sys.modules for *name* and all dotted parents."""
    mock = MagicMock(spec=[])
    parts = name.split(".")
    for i in range(len(parts)):
        partial = ".".join(parts[: i + 1])
        if partial not in sys.modules:
            sys.modules[partial] = MagicMock() if i < len(parts) - 1 else mock
    return mock


_MOCK_PACKAGES = [
    "simnibs",
    "simnibs.simulation",
    "simnibs.simulation.sim_struct",
    "simnibs.mesh_tools",
    "simnibs.mesh_tools.mesh_io",
    "simnibs.utils",
    "simnibs.utils.transformations",
    "bpy",
    "scipy",
    "scipy.optimize",
    "scipy.spatial",
    "scipy.spatial.transform",
    "nibabel",
    "nibabel.freesurfer",
    "h5py",
    "matplotlib",
    "matplotlib.pyplot",
    "matplotlib.backends",
    "matplotlib.backends.backend_pdf",
    "matplotlib.lines",
    "pandas",
    "joblib",
    "nilearn",
    "nilearn.plotting",
    "nilearn.image",
    "trimesh",
]


def pytest_configure(config):
    """Mock heavy third-party packages that are unavailable outside Docker.

    Builds a hierarchy of MagicMock modules so that dotted imports
    (e.g. ``from matplotlib.lines import Line2D``) resolve correctly.
    """
    # Group packages by top-level name so children share the parent mock.
    _mocks: dict[str, MagicMock] = {}
    for pkg in _MOCK_PACKAGES:
        if pkg in sys.modules:
            continue
        parts = pkg.split(".")
        # Ensure all ancestor mocks exist
        for i in range(len(parts)):
            partial = ".".join(parts[: i + 1])
            if partial not in sys.modules and partial not in _mocks:
                _mocks[partial] = MagicMock()
                sys.modules[partial] = _mocks[partial]
            elif partial in sys.modules:
                _mocks[partial] = sys.modules[partial]
        # Wire child as attribute of parent
        for i in range(1, len(parts)):
            parent_key = ".".join(parts[:i])
            child_key = ".".join(parts[: i + 1])
            setattr(_mocks[parent_key], parts[i], _mocks[child_key])


# ============================================================================
# PathManager reset — runs after every test automatically
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_path_manager():
    """Reset the PathManager singleton after each test."""
    yield
    from tit.paths import reset_path_manager

    reset_path_manager()


# ============================================================================
# Temporary BIDS project directory
# ============================================================================


@pytest.fixture()
def tmp_project(tmp_path):
    """Create a minimal BIDS-compliant project directory tree.

    Layout::

        tmp_path/
        ├── sub-001/anat/
        ├── derivatives/
        │   ├── SimNIBS/sub-001/m2m_001/segmentation/
        │   ├── SimNIBS/sub-001/Simulations/
        │   ├── freesurfer/sub-001/
        │   └── ti-toolbox/
        ├── code/ti-toolbox/config/
        └── sourcedata/

    Returns the *tmp_path* (project root).
    """
    dirs = [
        tmp_path / "sub-001" / "anat",
        tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "m2m_001" / "segmentation",
        tmp_path / "derivatives" / "SimNIBS" / "sub-001" / "Simulations",
        tmp_path / "derivatives" / "freesurfer" / "sub-001",
        tmp_path / "derivatives" / "ti-toolbox",
        tmp_path / "code" / "ti-toolbox" / "config",
        tmp_path / "sourcedata",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    return tmp_path


@pytest.fixture()
def init_pm(tmp_project):
    """Initialize and return a PathManager pointed at *tmp_project*."""
    from tit.paths import get_path_manager

    return get_path_manager(str(tmp_project))
