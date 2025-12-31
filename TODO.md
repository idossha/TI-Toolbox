To-Do List:

- [ ] Ex-search viewer - graphical UI for electrode visualization and selection.
- [X] AMV - fix location and size of rings for the new template `10-10-net`     
- [ ] docs maintenance - wiki, gallery, API (sphinx), etc.
- [ ] codecov 
- [ ] SAR calculation for HF signal
- [ ] look into changing the GUI to % instead of fixed pixel count
- [ ] continue cleanup & efficiency increase

---

# TI-Toolbox Codebase Improvement Guide

## Overview
This document provides actionable recommendations to improve the TI-Toolbox codebase efficiency and simplicity while maintaining functionality. The recommendations are organized by priority and impact.

## Executive Summary
The TI-Toolbox codebase shows good organization but has opportunities for significant efficiency improvements through:
- Consolidating duplicate code patterns
- Standardizing error handling and logging
- Simplifying subprocess management
- Improving GUI architecture
- Reducing shell script complexity

---

## High Priority Improvements

### 1. Consolidate Process Management Code (High Impact, Medium Effort)

**Current State:**
- Each GUI tab has its own Thread class with nearly identical subprocess handling
- Code duplication across: SimulationThread, AnalysisThread, ExSearchThread, PreProcessThread, FlexSearchThread, WorkerThread
- Multiple implementations of ANSI code stripping

**Recommendation:**
Create a unified process management system in `tit/core/process.py`:

```python
# tit/core/process.py
class ProcessRunner(QtCore.QThread):
    """Unified process runner for all GUI tabs"""
    output_signal = QtCore.pyqtSignal(str, str)
    progress_signal = QtCore.pyqtSignal(int)
    finished_signal = QtCore.pyqtSignal(int)
    error_signal = QtCore.pyqtSignal(str)
    
    def __init__(self, cmd, env=None, stdin_data=None, message_parser=None):
        super().__init__()
        self.cmd = cmd
        self.env = env or os.environ.copy()
        self.stdin_data = stdin_data
        self.message_parser = message_parser or self.default_message_parser
        self.process = None
        self.terminated = False
```

**Benefits:**
- Eliminate ~500+ lines of duplicate code
- Centralized bug fixes and improvements
- Consistent behavior across all tools
- Easier testing and maintenance

### 2. Create Centralized Error Handling (High Impact, Low Effort)

**Current State:**
- Inconsistent error handling patterns
- Error messages scattered throughout code
- No unified error recovery mechanism

**Recommendation:**
Create error handling utilities in `tit/core/errors.py`:

```python
# tit/core/errors.py
class TIToolboxError(Exception):
    """Base exception for all TI-Toolbox errors"""
    def __init__(self, message, error_code=None, details=None):
        self.message = message
        self.error_code = error_code
        self.details = details
        super().__init__(self.message)

class ProcessError(TIToolboxError):
    """Raised when a subprocess fails"""
    pass

class ValidationError(TIToolboxError):
    """Raised when input validation fails"""
    pass

def handle_error(error, logger=None, gui_callback=None):
    """Centralized error handling with logging and GUI notification"""
    # Implementation here
```

**Benefits:**
- Consistent error messages and handling
- Better error tracking and debugging
- Improved user experience with clear error messages

### 3. Simplify Logging Architecture (Medium Impact, Medium Effort)

**Current State:**
- Complex interaction between Python and bash logging
- Multiple logging utilities with overlapping functionality
- Embedded Python code in bash scripts for logging

**Recommendation:**
Consolidate logging into a single Python-based system:

```python
# tit/core/logging.py
class TILogger:
    """Unified logging system for all TI-Toolbox components"""
    def __init__(self, name, log_file=None, console_level='INFO', file_level='DEBUG'):
        self.logger = self._setup_logger(name, log_file, console_level, file_level)
    
    def log_process_step(self, step_name, status='started', details=None):
        """Standardized process step logging"""
        # Implementation here

# Export convenience functions
def get_logger(name):
    """Get or create a logger instance"""
    return TILogger(name)
```

**Benefits:**
- Simplified logging configuration
- Consistent log formats
- Easier debugging and monitoring
- Remove complex bash/Python interactions

### 4. Standardize GUI Tab Architecture (Medium Impact, Medium Effort)

**Current State:**
- Each tab implements similar patterns differently
- Duplicate console widget handling
- Inconsistent state management

**Recommendation:**
Create a base tab class in `tit/gui/base_tab.py`:

```python
# tit/gui/base_tab.py
class BaseToolTab(QtWidgets.QWidget):
    """Base class for all tool tabs"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_common_ui()
        self.setup_tool_specific_ui()
    
    def setup_common_ui(self):
        """Setup UI elements common to all tabs"""
        self.console = ConsoleWidget()
        self.run_stop_buttons = RunStopButtons()
        self.process_runner = None
        # Common layout and connections
    
    def setup_tool_specific_ui(self):
        """Override in subclasses for tool-specific UI"""
        raise NotImplementedError
    
    def run_process(self, cmd, env=None):
        """Standardized process execution"""
        self.process_runner = ProcessRunner(cmd, env)
        self.process_runner.output_signal.connect(self.update_console)
        self.process_runner.start()
```

**Benefits:**
- Reduce code duplication by ~40%
- Consistent behavior across all tabs
- Easier to add new tools
- Centralized bug fixes

---

## Medium Priority Improvements

### 5. Migrate Shell Scripts to Python (Medium Impact, High Effort)

**Current State:**
- Complex bash scripts with embedded Python code
- Difficult to maintain and debug
- Platform-specific issues

**Recommendation:**
Gradually migrate shell scripts to Python modules:

```python
# Example: tit/pre/dicom2nifti.py
class DicomConverter:
    """DICOM to NIfTI conversion with BIDS compliance"""
    
    def __init__(self, subject_dir, output_dir):
        self.subject_dir = Path(subject_dir)
        self.output_dir = Path(output_dir)
    
    def convert(self):
        """Run DICOM to NIfTI conversion"""
        # Python implementation of dicom2nifti.sh
```

**Benefits:**
- Better cross-platform compatibility
- Easier testing and debugging
- Type checking and IDE support
- Simplified deployment

### 6. Implement Configuration Management (Low Impact, Low Effort)

**Current State:**
- Configuration scattered across JSON files and environment variables
- No validation of configuration values
- Difficult to manage defaults

**Recommendation:**
Create a configuration management system:

```python
# tit/core/config.py
from dataclasses import dataclass
from typing import Optional, List

@dataclass
class SimulatorConfig:
    """Configuration for simulator tool"""
    intensity: float = 1.0
    electrode_shape: str = "ellipse"
    debug_mode: bool = False
    
    def validate(self):
        """Validate configuration values"""
        if self.intensity <= 0:
            raise ValidationError("Intensity must be positive")

class ConfigManager:
    """Centralized configuration management"""
    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.configs = {}
    
    def get_config(self, tool_name):
        """Get configuration for a specific tool"""
        # Load and validate configuration
```

**Benefits:**
- Type-safe configuration
- Validation at load time
- Clear defaults
- Better documentation

### 7. Optimize Import Structure (Low Impact, Low Effort)

**Current State:**
- Inconsistent import patterns
- sys.path manipulation in multiple files
- Circular import risks

**Recommendation:**
Standardize imports and create proper package structure:

```python
# tit/__init__.py
# Make tit a proper package
from .core import get_path_manager, PathManager
from .version import __version__

__all__ = ['get_path_manager', 'PathManager', '__version__']
```

**Benefits:**
- Cleaner import statements
- Better IDE support
- Reduced circular import risks
- Faster startup times

---

## Low Priority Improvements

### 8. Implement Caching for Expensive Operations (Low Impact, Medium Effort)

**Current State:**
- Repeated calculations without caching
- File I/O operations without caching
- No memoization of expensive functions

**Recommendation:**
Add caching layer for expensive operations:

```python
# tit/core/cache.py
from functools import lru_cache
import pickle
from pathlib import Path

class CacheManager:
    """Manage cached data for expensive operations"""
    
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def cache_result(self, key, data):
        """Cache computation results"""
        cache_file = self.cache_dir / f"{key}.pkl"
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
```

### 9. Add Type Hints Throughout (Low Impact, Medium Effort)

**Current State:**
- Limited type hints
- Difficult to understand function signatures
- No static type checking

**Recommendation:**
Add comprehensive type hints:

```python
from typing import List, Dict, Optional, Tuple

def analyze_roi(
    mesh: 'SimNIBSMesh',
    roi_coords: Tuple[float, float, float],
    radius: float = 5.0
) -> Dict[str, float]:
    """Analyze ROI with type hints for clarity"""
```

### 10. Improve Documentation Generation (Low Impact, Low Effort)

**Current State:**
- Inconsistent docstring formats
- No automated documentation generation

**Recommendation:**
Standardize docstrings and add documentation generation:

```python
def calculate_focality(
    ti_field: np.ndarray,
    roi_mask: np.ndarray,
    gm_mask: np.ndarray
) -> float:
    """
    Calculate focality metric for TI stimulation.
    
    Args:
        ti_field: TI field values array
        roi_mask: Boolean mask for ROI elements  
        gm_mask: Boolean mask for gray matter elements
        
    Returns:
        Focality value (higher = more focal)
        
    Raises:
        ValueError: If masks have incompatible shapes
    """
```

---

## Implementation Strategy

### Phase 1: Foundation (Weeks 1-2)
1. Create core utilities (process.py, errors.py, logging.py)
2. Add comprehensive tests for new modules
3. Document new APIs

### Phase 2: Migration (Weeks 3-6)
1. Migrate one GUI tab to use new utilities
2. Verify functionality and fix issues
3. Progressively migrate remaining tabs
4. Update shell scripts to use new logging

### Phase 3: Optimization (Weeks 7-8)
1. Remove duplicate code
2. Standardize imports
3. Add type hints to critical paths
4. Performance profiling and optimization

### Phase 4: Documentation (Week 9)
1. Update all docstrings
2. Generate API documentation
3. Update user guides
4. Create migration guide for extensions

---

## Expected Benefits

### Quantitative
- **Code Reduction**: ~30-40% fewer lines of code
- **Bug Reduction**: Estimated 50% fewer bugs from duplicate code
- **Performance**: 10-20% faster startup and execution
- **Test Coverage**: Easier to achieve >80% coverage

### Qualitative
- **Maintainability**: Much easier to fix bugs and add features
- **Onboarding**: New developers can understand codebase faster
- **Reliability**: Consistent behavior across all tools
- **User Experience**: Clearer error messages and smoother operation

---

## Risk Mitigation

1. **Backward Compatibility**: Maintain old interfaces during transition
2. **Testing**: Comprehensive test suite before major changes
3. **Gradual Migration**: Implement changes incrementally
4. **Feature Flags**: Allow switching between old/new implementations
5. **Documentation**: Keep detailed migration notes

---

## Conclusion

These improvements will transform the TI-Toolbox codebase into a more professional, efficient, and maintainable system. The key is to implement changes gradually while maintaining functionality and ensuring thorough testing at each step.

Priority should be given to high-impact improvements that reduce code duplication and standardize core functionality. This will create a solid foundation for future development and make the codebase more accessible to new contributors.
