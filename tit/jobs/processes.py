"""Cross-platform process-tree primitives for ``tit/jobs/runner.py`` (N0.6 spike; see
``docs/dev/SPIKES.md``).

POSIX and Windows disagree about almost everything a "kill this job's whole process tree"
primitive needs: how a child gets its own process group at spawn time, and what a caller sends
to ask for a graceful vs. a hard stop. Each function below picks the right primitive for the
current OS in exactly one place, so ``runner.py`` reads the same on every platform.

Every symbol here is safe to *reference* on any OS -- including the Windows-only
``subprocess.CREATE_NEW_PROCESS_GROUP``-shaped constant -- because it never appears as a bare
attribute access in this module. Attempting that on the "wrong" platform is exactly the class of
bug this module exists to remove: ``signal.SIGKILL`` does not exist in the Windows build of the
``signal`` module at all ("Availability: Unix", docs.python.org/3/library/signal.html), and the
mirror problem is equally real for ``subprocess``'s Windows-only creation-flag names on a POSIX
build (CPython's own ``subprocess.py`` only defines them inside its ``if _mswindows:`` block).

``is_windows()`` is deliberately its own function, not an inline ``sys.platform``/``os.name``
check spread across call sites -- tests monkeypatch *this* function, so the Windows branches
below are exercised by the suite on every OS, including this one, which has no Windows
interpreter to run them on natively.
"""

from __future__ import annotations

import signal
import sys

import psutil

# winbase.h CREATE_NEW_PROCESS_GROUP == 0x00000200 (also `_winapi.CREATE_NEW_PROCESS_GROUP`,
# which is what `subprocess.CREATE_NEW_PROCESS_GROUP` aliases on a Windows build). Hardcoded
# here rather than read off `subprocess`/`_winapi` so this module never performs a
# platform-conditional attribute lookup that would itself raise AttributeError when merely
# imported (or monkeypatched-and-exercised, see module docstring) on a non-Windows interpreter.
CREATE_NEW_PROCESS_GROUP = 0x00000200


def is_windows() -> bool:
    """True when running on Windows."""
    return sys.platform == "win32"


def spawn_kwargs() -> dict[str, int | bool]:
    """Extra kwargs for ``asyncio.create_subprocess_exec``/``subprocess.Popen`` that give a
    spawned job its own process group, so a later :func:`send_terminate`/:func:`send_kill` can
    signal the whole tree without also hitting whatever spawned it.

    POSIX: ``start_new_session=True`` -- the libc ``setsid()`` call, made safely by the C
    runtime around fork+exec (never ``preexec_fn=os.setsid``, which runs user Python code
    between fork and exec and is unsafe in a process with other threads alive -- see
    ``tit/pre/utils.py``'s own comment on the same tradeoff for the *other* runner in this repo).

    Windows: ``creationflags=CREATE_NEW_PROCESS_GROUP``. ``start_new_session`` is a *silent*
    no-op there -- CPython's Windows ``subprocess._execute_child`` receives it as
    ``unused_start_new_session`` (verified by reading this host's own installed ``subprocess.py``;
    the parameter is documented POSIX-only) -- so passing it alone would leave a spawned job in
    the *server's own* process group on Windows, with no group ``terminate_tree`` could target
    independently of the server itself.
    """
    if is_windows():
        return {"creationflags": CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def send_terminate(proc: psutil.Process) -> None:
    """Graceful stop. POSIX: SIGTERM (a signal the child can trap/ignore/clean up on).

    Windows: ``psutil.Process.terminate()``, itself an alias for ``TerminateProcess`` there
    (psutil's own docs: "On Windows this is an alias for kill()") -- Windows has no signal a
    receiving process can trap the way POSIX SIGTERM allows, so this and :func:`send_kill`
    necessarily converge on the same primitive there; kept as two call sites (not one) so a
    future Windows-specific graceful path (e.g. ``GenerateConsoleCtrlEvent`` for console
    subprocesses) has exactly one place to change.
    """
    if is_windows():
        proc.terminate()
    else:
        proc.send_signal(signal.SIGTERM)


def send_kill(proc: psutil.Process) -> None:
    """Hard kill, no grace. POSIX: SIGKILL, via ``proc.send_signal(signal.SIGKILL)`` -- the
    exact call ``tit/jobs/runner.py`` made before this module existed, unchanged here.

    Windows: ``psutil.Process.kill()`` -- *never* ``signal.SIGKILL``, which is not merely
    unsupported on Windows but does not exist as a ``signal`` module attribute there at all
    ("Availability: Unix", per the signal docs cited in the module docstring); referencing it
    unconditionally raises ``AttributeError`` at the point of use, before ``runner.py``'s own
    ``psutil.NoSuchProcess``/``AccessDenied`` guard around the call site ever gets a chance to
    catch it (that guard's exception tuple never included ``AttributeError``). This was the bug
    at ``tit/jobs/runner.py:213`` before this module existed -- see
    ``docs/dev/SPIKES.md`` for the fix and how it was verified.
    """
    if is_windows():
        proc.kill()
    else:
        proc.send_signal(signal.SIGKILL)
