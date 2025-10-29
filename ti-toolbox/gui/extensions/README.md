=31;OK\# Extension Development Guide

## Overview

The TI-Toolbox extension system allows developers to create modular, plug-and-play tools that enhance the main application without modifying its core codebase. Extensions are Python scripts that can be easily added, removed, or updated independently.

## Architecture

```
ti-toolbox/gui/
├── extensions.py              # Main extension interface
├── settings_menu.py           # Settings menu with Extensions option
└── extentions/                # Extension directory
    ├── README.md              # User-friendly guide
    ├── EXTENSION_DEVELOPMENT.md  # This file
    ├── quick_notes.py         # Example: Note-taking
    └── subject_info_viewer.py # Example: Subject status viewer
```

## How It Works

### 1. Extension Discovery

The `ExtensionsTab` class in `extensions.py` automatically discovers all `.py` files in the `extentions/` directory:

```python
def load_extensions(self):
    extension_files = list(self.extensions_dir.glob("*.py"))
    for extension_file in sorted(extension_files):
        # Load and display extension
```

### 2. Extension Metadata

Each extension must define metadata constants:

```python
EXTENSION_NAME = "My Extension"
EXTENSION_DESCRIPTION = "What this extension does"
```

These are displayed in the Extensions list in the GUI.

### 3. Extension Execution

Extensions must provide either a `main()` or `run()` function:

```python
def main(parent=None):
    """Entry point called when extension is launched"""
    # Extension code here
```

The extension system dynamically imports and executes this function:

```python
spec = importlib.util.spec_from_file_location(name, module_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if hasattr(module, 'main'):
    module.main(parent=parent)
```

### 4. User Interface

Extensions typically create a PyQt5 dialog window:

```python
class MyExtensionWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(MyExtensionWindow, self).__init__(parent)
        self.setup_ui()
```


## Best Practices

### 1. Error Handling

Always wrap your main logic in try-except blocks:

```python
def launch_extension(self):
    try:
        # Extension logic
        module.main(parent=self.parent)
    except Exception as e:
        QtWidgets.QMessageBox.critical(
            self,
            "Extension Launch Error",
            f"Failed to launch: {str(e)}"
        )
```

### 2. Resource Management

Clean up resources when the extension closes:

```python
def closeEvent(self, event):
    """Handle window close event."""
    # Close open files
    # Stop background threads
    # Save state if needed
    event.accept()
```

### 3. User Feedback

Provide clear feedback for all operations:

```python
# Progress indicators
progress = QtWidgets.QProgressBar()

# Status messages
self.status_label.setText("Processing...")

# Message boxes for completion/errors
QtWidgets.QMessageBox.information(self, "Done", "Processing complete!")
```


## Integration with TI-Toolbox Core

### Importing Core Modules

Extensions can import and use TI-Toolbox modules:

```python
import sys
from pathlib import Path

# Add TI-Toolbox to path
ti_toolbox_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ti_toolbox_path))

# Import core modules
from core.paths import Paths
from core.utils import Utils
from core.constants import Constants
```

### Following BIDS Conventions

Respect the BIDS directory structure:

```
project_dir/
├── sub-{id}/
│   └── anat/
├── sourcedata/
│   └── sub-{id}/
└── derivatives/
    ├── freesurfer/
    ├── SimNIBS/
    └── ti-toolbox/
```

## Testing Extensions

### Manual Testing

1. Place extension in `gui/extentions/` directory
2. Launch TI-Toolbox GUI
3. Click Settings (⚙) → Extensions
4. Find your extension in the list
5. Click "Launch" and test functionality

### Edge Cases to Test

- [ ] Extension launches without errors
- [ ] UI is responsive and usable
- [ ] Error messages are clear and helpful
- [ ] Extension handles missing data gracefully
- [ ] Close button works correctly
- [ ] Extension cleans up resources on close

## Distribution

### Sharing Extensions

Extensions are single files that can be easily shared:

1. **Direct File Sharing**: Send the `.py` file
2. **Pull Request**: Contribute to TI-Toolbox repository

### Installation Instructions

For users installing your extension:

1. Download the extension `.py` file
2. Place it in `ti-toolbox/gui/extentions/` directory
3. Restart TI-Toolbox or click "Refresh Extensions"
4. Find the extension in Settings → Extensions

## Advanced Topics

### Background Processing

For long-running operations, use QThread:

```python
class ProcessingThread(QtCore.QThread):
    finished = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal(int)
    
    def run(self):
        # Long-running task
        result = self.process_data()
        self.finished.emit(result)
```

### State Persistence

Save extension state between sessions:

```python
import json

def save_state(self):
    state = {
        'last_directory': str(self.project_dir),
        'preferences': self.preferences
    }
    with open('extension_state.json', 'w') as f:
        json.dump(state, f)

def load_state(self):
    try:
        with open('extension_state.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
```

### Custom Signals

Create custom signals for inter-component communication:

```python
class MyExtension(QtWidgets.QDialog):
    data_processed = QtCore.pyqtSignal(dict)
    
    def process(self):
        result = self.do_processing()
        self.data_processed.emit(result)
```

## Troubleshooting

### Common Issues

**Extension doesn't appear:**
- Check file has `.py` extension
- Verify `EXTENSION_NAME` and `EXTENSION_DESCRIPTION` are defined
- Look for syntax errors
- Click "Refresh Extensions"

**Import errors:**
- Ensure required packages are installed
- Check Python path configuration
- Verify module names are correct


## Resources

- **PyQt5 Documentation**: https://doc.qt.io/qtforpython/
- **Python importlib**: https://docs.python.org/3/library/importlib.html
- **TI-Toolbox GitHub**: https://github.com/idossha/TI-Toolbox

## Contributing

To contribute an extension to the TI-Toolbox repository:

1. Create your extension following these guidelines
2. Test thoroughly
3. Add clear documentation
4. Submit a pull request
5. Include example usage and screenshots

---
