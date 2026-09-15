"""Project initialization helpers for TI-Toolbox.

Provides utilities for detecting new projects, scaffolding BIDS-compliant
directory structures, and reading/writing ``project_status.json``. The example
data is :func:`tit.examples.fetch`.
"""

from .initializer import (
    initialize_project_structure,
    is_new_project,
    load_project_status,
    update_project_status,
)

__all__ = [
    "initialize_project_structure",
    "is_new_project",
    "load_project_status",
    "update_project_status",
]
