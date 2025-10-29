# TI-Toolbox Extension Development Guide

## Extension Architecture Fix (2025)

### Problem
Extensions that inherit from `QtWidgets.QDialog` break when added as tabs to the main window. Only the console component remains visible, while other UI elements disappear.

### Root Cause
When a `QDialog` is converted to a `QWidget` using `setWindowFlags(QtCore.Qt.Widget)` after UI setup, it causes layout and sizing issues because:
- `QDialog` and `QWidget` have different default size policies
- Layout constraints change when window flags are modified post-creation
- Tab embedding requires proper `QWidget` behavior from the start

### Solution
Extensions must be designed as `QWidget` subclasses from the beginning, with optional `QDialog` wrappers for floating windows.

#### Extension Structure Pattern
```python
class MyExtensionWidget(QtWidgets.QWidget):
    """Main widget class - inherits from QWidget"""
    def __init__(self, parent=None):
        super().__init__(parent)
        # Setup UI as QWidget
        self.setup_ui()

class MyExtensionWindow(QtWidgets.QDialog):
    """Dialog wrapper for floating windows"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("My Extension")
        self.setMinimumSize(900, 700)
        self.setWindowFlag(QtCore.Qt.Window)

        # Embed the widget
        self.widget = MyExtensionWidget(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.widget)

def main(parent=None):
    """Entry point - creates dialog for floating windows"""
    window = MyExtensionWindow(parent)
    window.show()
    return window
```

### Framework Changes
- Extension loading logic now prefers `QWidget` subclasses over `QDialog` subclasses
- Removed `setWindowFlags()` conversion - widgets are used directly as tabs
- Dialog wrappers handle floating window presentation

### Best Practices
1. **Always inherit from `QWidget`** for extension main classes
2. **Create separate `QDialog` wrapper** for floating window support
3. **Test both modes**: floating window (`main()`) and tab embedding
4. **Use proper size policies** and layout management
5. **Avoid window-specific flags** in the main widget class

### Files Modified
- `ti-toolbox/gui/extensions/nifti_group_average.py`
- `ti-toolbox/gui/extensions/cbp.py`
- `ti-toolbox/gui/extensions.py`
- `ti-toolbox/gui/main.py`

This ensures extensions work consistently in both tab and floating window modes.
