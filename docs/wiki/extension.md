---
layout: wiki
title: Extension System
permalink: /wiki/extension/
---

The TI-Toolbox Extension System provides a modular framework for adding new tools and features without modifying the core application codebase. Extensions are self-contained Python scripts that can be easily installed, updated, or removed.

## Architecture

```
tit/gui/
├── extensions.py              # Main extension interface
├── settings_menu.py           # Settings menu with Extensions option
└── extensions/                # Extension directory
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
from core.roi import ROICoordinateHelper
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


## Installation and Distribution

### Installing Extensions

Extensions are distributed as single Python files. To install:

1. Download the extension `.py` file
2. Place it in `tit/gui/extensions/` directory
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