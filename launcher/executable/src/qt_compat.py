"""
Qt Compatibility Layer
This module provides a unified interface for both PyQt6 and PySide6,
allowing the application to work with either framework.
"""

try:
    # Try PyQt6 first
    from PyQt6.QtWidgets import *
    from PyQt6.QtCore import *
    from PyQt6.QtGui import *
    
    # PyQt6 uses pyqtSignal
    Signal = pyqtSignal
    
    QT_FRAMEWORK = "PyQt6"
    
except ImportError:
    try:
        # Fall back to PySide6
        from PySide6.QtWidgets import *
        from PySide6.QtCore import *
        from PySide6.QtGui import *
        
        # PySide6 uses Signal (already defined)
        # No need to alias Signal
        
        QT_FRAMEWORK = "PySide6"
        
    except ImportError:
        raise ImportError("Neither PyQt6 nor PySide6 is installed. Please install one of them.")

# Debug info (remove for production)
# print(f"Using {QT_FRAMEWORK} for Qt framework") 