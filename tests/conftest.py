#!/usr/bin/env python3
"""
Pytest configuration for TI-Toolbox tests.

Since all tests run in Docker with full dependencies, we only mock what needs
to be mocked for headless GUI testing.
"""

import sys
from unittest.mock import MagicMock
import pytest
import types

def pytest_configure(config):
    """Configure minimal mocking for headless testing"""
    # Mock matplotlib for test isolation (prevents backend changes from affecting other tests)
    mock_mpl = MagicMock()
    mock_mpl.__version__ = "3.5.0"
    mock_mpl.use = MagicMock()
    mock_mpl.pyplot = MagicMock()
    mock_mpl.backends = MagicMock()
    mock_mpl.colors = MagicMock()
    mock_mpl.patches = MagicMock()

    # Mock nilearn for headless viz tests
    mock_nl = MagicMock()
    mock_nl.datasets = MagicMock()
    mock_nl.plotting = MagicMock()
    mock_nl.image = MagicMock()

    # Apply mocks for GUI libraries
    sys.modules['matplotlib'] = mock_mpl
    sys.modules['matplotlib.pyplot'] = mock_mpl.pyplot
    sys.modules['matplotlib.backends'] = mock_mpl.backends
    sys.modules['matplotlib.use'] = mock_mpl.use
    sys.modules['matplotlib.colors'] = mock_mpl.colors
    sys.modules['matplotlib.patches'] = mock_mpl.patches

    sys.modules['nilearn'] = mock_nl
    sys.modules['nilearn.datasets'] = mock_nl.datasets
    sys.modules['nilearn.plotting'] = mock_nl.plotting
    sys.modules['nilearn.image'] = mock_nl.image

    # Mock seaborn to avoid complex matplotlib dependencies
    sys.modules['seaborn'] = MagicMock()

    # Prefer real SimNIBS when available (Docker test image has it via simnibs_python).
    # Fall back to stubs for local/unit environments without SimNIBS.
    try:
        import simnibs as _simnibs  # noqa: F401
    except Exception:
        simnibs = types.ModuleType("simnibs")
        simnibs.__path__ = []  # mark as package
        simnibs.opt_struct = MagicMock()
        simnibs.run_simnibs = MagicMock()
        simnibs.mesh_io = MagicMock()
        simnibs.sim_struct = MagicMock()
        simnibs.mni2subject_coords = MagicMock()
        simnibs.subject2mni_coords = MagicMock()
        sys.modules["simnibs"] = simnibs

        simnibs_optimization = types.ModuleType("simnibs.optimization")
        simnibs_optimization.__path__ = []
        sys.modules["simnibs.optimization"] = simnibs_optimization

        tfo = types.ModuleType("simnibs.optimization.tes_flex_optimization")
        tfo.__path__ = []
        sys.modules["simnibs.optimization.tes_flex_optimization"] = tfo

        electrode_layout = types.ModuleType("simnibs.optimization.tes_flex_optimization.electrode_layout")
        electrode_layout.ElectrodeArrayPair = MagicMock()
        sys.modules["simnibs.optimization.tes_flex_optimization.electrode_layout"] = electrode_layout

        simnibs_utils = types.ModuleType("simnibs.utils")
        simnibs_utils.__path__ = []
        simnibs_utils.TI_utils = MagicMock()
        sys.modules["simnibs.utils"] = simnibs_utils

        sys.modules["simnibs.sim_struct"] = types.ModuleType("simnibs.sim_struct")

        simnibs_mesh_tools = types.ModuleType("simnibs.mesh_tools")
        simnibs_mesh_tools.__path__ = []
        sys.modules["simnibs.mesh_tools"] = simnibs_mesh_tools
        simnibs_mesh_tools_mesh_io = types.ModuleType("simnibs.mesh_tools.mesh_io")
        simnibs_mesh_tools_mesh_io.ElementTags = MagicMock()
        sys.modules["simnibs.mesh_tools.mesh_io"] = simnibs_mesh_tools_mesh_io

    sys.modules.setdefault("bpy", MagicMock())

    # Prefer real nibabel/pandas/h5py when available (Docker test image has them);
    # fall back to lightweight stubs for local/unit environments without these deps.
    try:
        import nibabel as _nibabel  # noqa: F401
    except Exception:
        nibabel = types.ModuleType("nibabel")
        nibabel.__path__ = []
        nibabel.Nifti1Image = MagicMock()
        nibabel.load = MagicMock()
        nibabel.save = MagicMock()
        sys.modules["nibabel"] = nibabel

        nibabel_processing = types.ModuleType("nibabel.processing")
        nibabel_processing.resample_from_to = MagicMock()
        sys.modules["nibabel.processing"] = nibabel_processing

    try:
        import pandas as _pandas  # noqa: F401
    except Exception:
        sys.modules.setdefault("pandas", MagicMock())

    try:
        import h5py as _h5py  # noqa: F401
    except Exception:
        sys.modules.setdefault("h5py", MagicMock())


@pytest.fixture(autouse=True)
def _reset_path_manager_singleton():
    # PathManager is a singleton; tests patch PROJECT_DIR across cases.
    try:
        from tit.core import reset_path_manager

        reset_path_manager()
    except Exception:
        pass
