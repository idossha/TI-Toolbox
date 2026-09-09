---
layout: wiki
title: Extension System
permalink: /wiki/extension/
---

Optional tools extend TI-Toolbox through panels in the desktop application. Computational
panels run through the job server; see [Jobs]({{ site.baseurl }}/wiki/jobs/) for tracking runs.
The removed Qt extension API is retained at the end of this page as historical reference.

## Optional tools in v3

Every optional tool is a **panel** you switch on per project in **Settings &#9656; Optional tools**.
An enabled panel gets its own row in the nav rail; a disabled one is not loaded at all.

<img src="{{ site.baseurl }}/assets/imgs/v3/settings.png" alt="Settings, with the Optional tools card" style="width: 100%; max-width: 1000px;">
<em>Settings (&#8984;,). Optional tools is a checkbox per panel; the Viewer engine card below it updates Tetravox without updating the toolbox.</em>

The panels are [Source]({{ site.baseurl }}/wiki/extension/), [Cluster
permutation]({{ site.baseurl }}/wiki/cluster-permutation-testing/), [NIfTI group
averaging]({{ site.baseurl }}/wiki/nifti-group-averaging/), [Nilearn
visuals]({{ site.baseurl }}/wiki/nilearn-visuals/), [Quick
notes]({{ site.baseurl }}/wiki/quick-notes/) and the [3D visual
exporter]({{ site.baseurl }}/wiki/blender/).

Computational tools use the same layout as the main run pages: **inputs on the left**, with
the **plan and live terminal on the right**. Submitted jobs remain available in that terminal
after completion and when you return to the page. Source builds EEG forward solutions. Field mapping is an opt-in in each Simulator job’s settings. Quick Notes remains a note editor, not a job runner.

The 3D visual exporter adds **Scene / Terminal** tabs. Its scene follows the selected export
type; see the [export preview guide]({{ site.baseurl }}/wiki/blender/#preview-and-export).

### Map existing fields from a notebook or terminal

In the supplied Jupyter environment, initialize the project and use the existing Python API:

```python
from tit import get_path_manager
from tit.source.config import FsavgMapConfig
from tit.source.fsaverage import project_fields_to_fsaverage

get_path_manager("/data/my-project")  # Use your project's path inside the container.
results = project_fields_to_fsaverage(
    [("101", "L_Insula")],
    FsavgMapConfig(fields=("TI_max", "TI_normal"), fsaverage_spacing=5),
)
```

For a terminal run, save that code as a script and run `simnibs_python map_fields.py`.
This maps existing outputs without rerunning simulation. For new simulations, enable
**Map fields to fsaverage** in the job’s settings before running it.

Two former extensions no longer exist as panels: **Electrode Placement** is now the Simulator's
[free-hand mode]({{ site.baseurl }}/wiki/electrode-placement/), and **Subject Info** is the
[Overview]({{ site.baseurl }}/wiki/overview/) page.

---

## Architecture (historical)

> **V2 archive (deprecated).** The Qt extension system below was removed with the PyQt GUI in
> v3.0.0. Panels now live in the [Desktop Application]({{ site.baseurl }}/wiki/desktop-app/)
> (`desktop/src/renderer/pages/panels/`), each backed by a `tit` job runner.
> These examples are retained for legacy developers; see the [v2 development archive]({{ site.baseurl }}/wiki/v2-development/).

```
tit/gui/  (removed in v3.0.0)
├── extensions.py              # Main extension interface
├── settings_menu.py           # Settings menu + top-right Extensions button
├── extensions_config.py       # Persists enabled/disabled tab state (extensions.json)
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

Each extension is shown as a card with a **Launch** button (opens it in its own window) and, when the module sets `allow_tab_integration = True`, an **Add Tab / Remove Tab** button that embeds it as a tab of the main window. The tab state is remembered between sessions in `extensions.json`.

Shipped extensions: `Permutation Analysis` (`cbp.py`), `Electrode Placement`, `NIfTI Group Averaging`, `Nilearn Visuals`, `Quick Notes`, `Source`, `Subject Info Viewer`, `3D Visual Exporter`.

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
from tit import paths, constants

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
from tit import paths, constants
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
4. Access via the **Extensions** button in the top-right toolbar (also available from the Settings menu)

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