---
layout: wiki
title: Extension System
permalink: /wiki/extension/
---

The TI-Toolbox Extension System provides a modular framework for adding new tools and features without modifying the core application codebase. Extensions are self-contained Python scripts that can be easily installed, updated, or removed.

## Overview

Extensions enable developers to create plug-and-play tools that enhance TI-Toolbox functionality. The system automatically discovers and loads extensions from the `gui/extensions/` directory, providing a seamless integration experience.

## Architecture

```
ti-toolbox/gui/
├── extensions.py              # Main extension interface
├── settings_menu.py           # Settings menu with Extensions option
└── extensions/                # Extension directory
    ├── README.md              # Developer documentation
    ├── *.py                   # Individual extension files
    └── ...
```

## Extension Discovery

The system automatically scans the `extensions/` directory for Python files and loads them dynamically:

```python
def load_extensions(self):
    extension_files = list(self.extensions_dir.glob("*.py"))
    for extension_file in sorted(extension_files):
        # Load and display extension
```

## Extension Metadata

Each extension must define required metadata constants:

```python
EXTENSION_NAME = "My Extension"
EXTENSION_DESCRIPTION = "What this extension does"
```

## User Interface

Extensions integrate directly into the TI-Toolbox GUI through the **Settings → Extensions** menu. Users can:

- Browse available extensions
- Launch extensions with a single click
- Access extension-specific help

## Development

### Creating Extensions

Extensions are Python scripts that follow a simple structure:

```python
#!/usr/bin/env simnibs_python
# -*- coding: utf-8 -*-

"""
Extension: My Custom Tool
Brief description of what it does.
"""

# Required metadata
EXTENSION_NAME = "My Custom Tool"
EXTENSION_DESCRIPTION = "Detailed description of the tool's purpose"

# Add TI-Toolbox to path
import sys
from pathlib import Path
ti_toolbox_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ti_toolbox_path))

# Import required modules
from core import get_path_manager

# Extension implementation
def main(parent=None):
    """Main entry point called when extension is launched"""
    # Your extension code here
    pass

# Alternative entry point
def run(parent=None):
    """Alternative entry point for flexibility"""
    main(parent)
```

### GUI Integration

Extensions typically create PyQt5 dialog windows:

```python
from PyQt5 import QtWidgets

class MyExtensionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(EXTENSION_NAME)
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface"""
        layout = QtWidgets.QVBoxLayout(self)
        # Add your UI components here
```

### Core Module Access

Extensions can import and use TI-Toolbox core modules:

```python
from core.paths import Paths
from core.utils import Utils
from core.constants import Constants
from core import get_path_manager
```

### BIDS Convention Compliance

Extensions should respect the TI-Toolbox BIDS directory structure:

```
project_dir/
├── sub-{id}/
├── sourcedata/
│   └── sub-{id}/
└── derivatives/
    ├── freesurfer/
    ├── SimNIBS/
    └── ti-toolbox/
```

## Available Extensions

### Nilearn Visuals

Create publication-ready visualizations using Nilearn for high-quality brain imaging.

**Features:**
- Group-averaged TI field visualization
- Multiple view orientations (sagittal, coronal, axial)
- Atlas contour overlays
- Glass brain visualizations
- Percentile-based or absolute cutoff thresholds

### Cluster-Based Permutation Testing

Perform non-parametric statistical analysis to identify brain regions with significant differences between groups.

**Features:**
- Responder vs non-responder analysis
- Unpaired and paired t-test support
- Cluster-level correction for multiple comparisons
- Parallel processing with multi-core support
- Comprehensive statistical reporting

### Quick Notes

Take timestamped notes during analysis sessions for documentation and reproducibility.

**Features:**
- Automatic timestamping with timezone support
- Persistent storage in project derivatives
- Copy to clipboard functionality
- Clear and searchable note format

### NIfTI Group Averaging

Compute group averages and differences for NIfTI files organized by experimental groups.

**Features:**
- Flexible group assignment
- Automatic group average computation
- Pairwise group difference calculations
- CSV import/export for subject configurations
- Memory-efficient processing for large datasets

## Installation and Distribution

### Installing Extensions

Extensions are distributed as single Python files. To install:

1. Download the extension `.py` file
2. Place it in `ti-toolbox/gui/extensions/` directory
3. Restart TI-Toolbox or refresh extensions
4. Access via **Settings → Extensions**

### Developing Extensions

To contribute new extensions:

1. Follow the extension template structure
2. Implement proper error handling
3. Add comprehensive documentation
4. Test thoroughly across different scenarios
5. Submit a pull request to the TI-Toolbox repository

## Best Practices

### Error Handling

Always wrap main logic in try-except blocks:

```python
def launch_extension(self):
    try:
        module.main(parent=self.parent)
    except Exception as e:
        QtWidgets.QMessageBox.critical(
            self,
            "Extension Launch Error",
            f"Failed to launch: {str(e)}"
        )
```

### Resource Management

Clean up resources when extensions close:

```python
def closeEvent(self, event):
    """Handle window close event."""
    # Close open files
    # Stop background threads
    # Save state if needed
    event.accept()
```

### User Feedback

Provide clear progress indicators and status messages:

```python
# Progress indicators
progress = QtWidgets.QProgressBar()

# Status messages
self.status_label.setText("Processing...")

# Completion messages
QtWidgets.QMessageBox.information(self, "Done", "Processing complete!")
```

## Troubleshooting

### Common Issues

**Extension doesn't appear:**
- Verify file has `.py` extension
- Check `EXTENSION_NAME` and `EXTENSION_DESCRIPTION` are defined
- Ensure file is in `gui/extensions/` directory
- Try clicking "Refresh Extensions"

**Import errors:**
- Verify required packages are installed
- Check Python path configuration
- Ensure module names are correct

**Runtime errors:**
- Check console output for detailed error messages
- Verify project directory structure
- Ensure necessary data files exist

## Resources

- **PyQt5 Documentation**: https://doc.qt.io/qtforpython/
- **Python importlib**: https://docs.python.org/3/library/importlib.html
- **TI-Toolbox GitHub**: https://github.com/idossha/TI-Toolbox
