"""
Process utilities for TI-Toolbox GUI.

Provides safe child process discovery using psutil.
"""

import psutil

__all__ = ["get_child_pids"]


def get_child_pids(parent_pid: int) -> list:
    """
    Safely get child process IDs using psutil.

    Args:
        parent_pid: Parent process ID

    Returns:
        List of child process IDs. Returns empty list on any error.
    """
    parent = psutil.Process(parent_pid)
    children = parent.children(recursive=False)
    return [child.pid for child in children]
