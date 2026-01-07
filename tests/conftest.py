#!/usr/bin/env python3
"""
Pytest configuration for TI-Toolbox tests.

Since all tests run in Docker with full dependencies, we only mock what needs
to be mocked for headless GUI testing.
"""

import sys
from unittest.mock import MagicMock
import pytest

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

    sys.modules.setdefault("bpy", MagicMock())


@pytest.fixture(autouse=True)
def _reset_path_manager_singleton():
    # PathManager is a singleton; tests patch PROJECT_DIR across cases.
    try:
        from tit.core import reset_path_manager

        reset_path_manager()
    except Exception:
        pass
