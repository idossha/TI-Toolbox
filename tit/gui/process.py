"""Process utilities for TI-Toolbox GUI.

Provides safe child-process discovery via ``psutil``, used by the
system monitor and process termination helpers.

See Also
--------
tit.gui.system_monitor_tab.ProcessMonitorThread : Uses this for tree walking.
"""

import psutil

__all__ = ["get_child_pids"]


def get_child_pids(parent_pid: int) -> list:
    """Return direct child PIDs of *parent_pid*.

    Parameters
    ----------
    parent_pid : int
        PID of the parent process to query.

    Returns
    -------
    list[int]
        Child process IDs.  Returns an empty list on any error.
    """
    parent = psutil.Process(parent_pid)
    children = parent.children(recursive=False)
    return [child.pid for child in children]
