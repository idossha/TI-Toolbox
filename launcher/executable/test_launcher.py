#!/usr/bin/env python3
"""
Quick test script to debug launcher issues
"""

import sys
import os

print("Testing launcher import...")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"Script location: {__file__}")

# Add the src directory to path
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)
print(f"Added to path: {src_path}")

try:
    print("Importing qt_compat...")
    from qt_compat import QApplication
    print("✓ qt_compat imported successfully")
except Exception as e:
    print(f"✗ qt_compat import failed: {e}")

try:
    print("Importing dialogs...")
    from dialogs import SystemRequirementsDialog
    print("✓ dialogs imported successfully")
except Exception as e:
    print(f"✗ dialogs import failed: {e}")

try:
    print("Importing shortcuts_manager...")
    from shortcuts_manager import ShortcutsManager
    print("✓ shortcuts_manager imported successfully")
except Exception as e:
    print(f"✗ shortcuts_manager import failed: {e}")

try:
    print("Importing docker_worker...")
    from docker_worker import DockerWorkerThread
    print("✓ docker_worker imported successfully")
except Exception as e:
    print(f"✗ docker_worker import failed: {e}")

try:
    print("Importing progress_widget...")
    from progress_widget import ProgressWidget
    print("✓ progress_widget imported successfully")
except Exception as e:
    print(f"✗ progress_widget import failed: {e}")

try:
    print("Importing main launcher...")
    from ti_csc_launcher import TIToolboxLoaderApp
    print("✓ ti_csc_launcher imported successfully")
except Exception as e:
    print(f"✗ ti_csc_launcher import failed: {e}")

print("Import test completed.")
