"""Project initialization helpers for TI-Toolbox.

Provides utilities for detecting new projects, scaffolding BIDS-compliant
directory structures, and copying bundled example data into a fresh project.
"""

from .initializer import (
    initialize_project_structure,
    is_new_project,
    load_project_status,
    setup_example_data,
    update_project_status,
)

__all__ = [
    "initialize_project_structure",
    "is_new_project",
    "load_project_status",
    "setup_example_data",
    "update_project_status",
]
