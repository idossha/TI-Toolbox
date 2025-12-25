#!/usr/bin/env python3
"""
Pytest configuration for TI-Toolbox tests.

Since all tests run in Docker with full dependencies, we only mock what needs
to be mocked for headless GUI testing.
"""

import sys
from unittest.mock import MagicMock

def pytest_configure(config):
    """Configure minimal mocking for headless testing"""
    # Mock matplotlib/nilearn for headless viz tests
    mock_mpl = MagicMock()
    mock_mpl.__version__ = "3.5.0"
    mock_mpl.use = MagicMock()
    mock_mpl.pyplot = MagicMock()
    mock_mpl.backends = MagicMock()
    mock_mpl.colors = MagicMock()
    mock_mpl.cm = MagicMock()
    mock_mpl.patches = MagicMock()
    mock_mpl.cbook = MagicMock()
    mock_mpl.ticker = MagicMock()
    mock_mpl.axis = MagicMock()
    mock_mpl.axes = MagicMock()
    mock_mpl.figure = MagicMock()
    mock_mpl.artist = MagicMock()
    mock_mpl.collections = MagicMock()
    mock_mpl.markers = MagicMock()

    mock_nl = MagicMock()
    mock_nl.datasets = MagicMock()
    mock_nl.plotting = MagicMock()
    mock_nl.image = MagicMock()

    # Apply mocks for GUI libraries
    sys.modules['matplotlib'] = mock_mpl
    sys.modules['matplotlib.pyplot'] = mock_mpl.pyplot
    sys.modules['matplotlib.backends'] = mock_mpl.backends
    sys.modules['matplotlib.colors'] = mock_mpl.colors
    sys.modules['matplotlib.cm'] = mock_mpl.cm
    sys.modules['matplotlib.patches'] = mock_mpl.patches
    sys.modules['matplotlib.cbook'] = mock_mpl.cbook
    sys.modules['matplotlib.ticker'] = mock_mpl.ticker
    sys.modules['matplotlib.axis'] = mock_mpl.axis
    sys.modules['matplotlib.axes'] = mock_mpl.axes
    sys.modules['matplotlib.figure'] = mock_mpl.figure
    sys.modules['matplotlib.artist'] = mock_mpl.artist
    sys.modules['matplotlib.collections'] = mock_mpl.collections
    sys.modules['matplotlib.markers'] = mock_mpl.markers
    sys.modules['mpl_toolkits'] = MagicMock()
    sys.modules['mpl_toolkits.mplot3d'] = MagicMock()

    sys.modules['nilearn'] = mock_nl
    sys.modules['nilearn.datasets'] = mock_nl.datasets
    sys.modules['nilearn.plotting'] = mock_nl.plotting
    sys.modules['nilearn.image'] = mock_nl.image

    # Mock seaborn to avoid complex matplotlib dependencies
    sys.modules['seaborn'] = MagicMock()
