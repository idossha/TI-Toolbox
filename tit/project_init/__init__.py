"""Project initialization helpers for TI-Toolbox.

Provides utilities for detecting new projects, scaffolding BIDS-compliant
directory structures, and copying bundled example data into a fresh project.
"""

from .initializer import (
    initialize_project_structure,
    is_new_project,
    setup_example_data,
)

__all__ = [
    "initialize_project_structure",
    "is_new_project",
    "setup_example_data",
]
