"""
Compatibility helpers for `tit/blender_exporter`.

The folder name `blender_exporter` is not a valid Python package name, so this codebase
often runs by adding the directory to `sys.path` and importing modules by filename.

These helpers centralize the common "relative import vs sys.path import" pattern
to keep modules cleaner and more professional.
"""

from __future__ import annotations

import importlib
from types import ModuleType


def import_module_fallback(relative_name: str, absolute_name: str) -> ModuleType:
    """
    Import a module with preference for package-relative import, falling back to sys.path import.

    Example:
        scene_setup = import_module_fallback(".scene_setup", "scene_setup")
    """
    try:
        return importlib.import_module(relative_name, package=__package__)
    except Exception:
        return importlib.import_module(absolute_name)


