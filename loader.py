#!/usr/bin/env python3
"""``loader.py`` — start the TI-Toolbox UI from a checkout or a standalone download.

    python loader.py --project ~/datasets/000
    python loader.py --project ~/datasets/000 --status | --logs | --stop

This is a BOOTSTRAP, not a second launcher.  Every option below is the option
:mod:`tit.cli` defines for ``tit launch``, reused here through ``parents=`` rather
than re-declared, and the work is done by :mod:`tit.launch` — which owns the run
spec, read from the one ``docker-compose.yml`` beside this file.  A ``docker run``
written out again here would drift from the Electron app's container on the first
change to a label, a mount or an environment variable, and the two would stop being
interchangeable.

``tit`` is imported from this checkout when this file sits in one (no install, no
virtualenv, nothing written anywhere). A standalone copy refreshes main into a cached
virtualenv for each start, so an older system-installed package cannot redirect it
back to the public release. ``TIT_VENV_DIR`` selects that cache, shared with ``loader.sh``;
otherwise it lives under ``XDG_CACHE_HOME`` or ``~/.cache/ti-toolbox/venv``. Stop, status
and logs use a working cached launcher without a network refresh.

Standard library only.  The host needs CPython >= 3.11 and the ``docker`` CLI; it does
not need SimNIBS, Node or Electron — the toolbox itself lives in the container.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAIN_ARCHIVE = "https://github.com/idossha/TI-toolbox/archive/refs/heads/main.zip"


def bootstrap() -> bool:
    """Make ``tit`` importable from this checkout, in preference to any installed copy.

    Only when the checkout really is one: a stray ``loader.py`` copied elsewhere must
    not put an unrelated directory on ``sys.path``.
    """
    if (HERE / "tit" / "launch.py").is_file() and (HERE / "pyproject.toml").is_file():
        if str(HERE) in sys.path:
            sys.path.remove(str(HERE))
        sys.path.insert(0, str(HERE))
        return True
    return False


def cached_management_available(python: Path, argv: list[str]) -> bool:
    """Keep management of existing containers available when the network is offline."""
    if not python.is_file() or not any(
        flag in argv for flag in ("--stop", "--status", "--logs")
    ):
        return False
    try:
        return (
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-c",
                    "from tit.cli import launch_command, launch_parser",
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def run_standalone(argv: list[str]) -> int:
    """Refresh and run the main launcher in an isolated environment, without science dependencies."""
    cache_root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    environment = (
        Path(os.environ.get("TIT_VENV_DIR") or cache_root / "ti-toolbox" / "venv")
        .expanduser()
        .resolve()
    )
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    use_cached = cached_management_available(python, argv)
    try:
        if not python.is_file():
            sys.stderr.write(
                f"loader.py: creating launcher environment at {environment}\n"
            )
            subprocess.run(
                [sys.executable, "-m", "venv", str(environment)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        if not use_cached:
            sys.stderr.write("loader.py: refreshing launcher from TI-Toolbox main\n")
            subprocess.run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--disable-pip-version-check",
                    "--no-input",
                    "--upgrade",
                    "--force-reinstall",
                    "--no-deps",
                    MAIN_ARCHIVE,
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        sys.stderr.write(
            "loader.py: could not prepare the launcher from main. Check your network and "
            "cache-directory permissions, and ensure Python includes venv/pip. "
            "Alternatively, clone TI-Toolbox and run loader.py from the checkout.\n"
        )
        return 2
    try:
        return subprocess.run(
            [str(python), "-I", "-m", "tit.cli", "launch", *argv], check=False
        ).returncode
    except OSError as err:
        sys.stderr.write(f"loader.py: could not start the cached launcher: {err}\n")
        return 2


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        sys.stderr.write("loader.py: CPython >= 3.11 is required.\n")
        return 2
    arguments = argv if argv is not None else sys.argv[1:]
    if not bootstrap():
        return run_standalone(arguments)
    try:
        from tit.cli import launch_command, launch_parser
    except (
        ImportError
    ) as err:  # pragma: no cover - exercised by the message, not a test
        sys.stderr.write(
            f"loader.py: could not import the `tit` package ({err}).\n"
            "  Check that this TI-Toolbox checkout is complete and uses CPython >= 3.11.\n"
        )
        return 2

    invocation = "python loader.py"
    parser = launch_parser(prog=invocation)
    args = parser.parse_args(arguments)
    return launch_command(args, invocation=invocation)


if __name__ == "__main__":
    raise SystemExit(main())
