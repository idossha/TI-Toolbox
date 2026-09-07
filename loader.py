#!/usr/bin/env python3
"""``loader.py`` — start the TI-Toolbox UI from this checkout, with nothing installed.

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
virtualenv, nothing written anywhere); otherwise the pip-installed package is used and
``tit launch`` is the same command by another name.

Standard library only.  The host needs CPython >= 3.11 and the ``docker`` CLI; it does
not need SimNIBS, Node or Electron — the toolbox itself lives in the container.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def bootstrap() -> None:
    """Make ``tit`` importable from this checkout, in preference to any installed copy.

    Only when the checkout really is one: a stray ``loader.py`` copied elsewhere must
    not put an unrelated directory on ``sys.path``.
    """
    if (HERE / "tit" / "launch.py").is_file() and (HERE / "pyproject.toml").is_file():
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))


def main(argv: list[str] | None = None) -> int:
    bootstrap()
    try:
        from tit.cli import launch_command, launch_parser
    except ImportError as err:  # pragma: no cover - exercised by the message, not a test
        sys.stderr.write(
            f"loader.py: could not import the `tit` package ({err}).\n"
            "  Run this file from a TI-Toolbox checkout, or install it first:\n"
            "    pip install tit\n"
        )
        return 2

    invocation = "python loader.py"
    parser = launch_parser(prog=invocation)
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return launch_command(args, invocation=invocation)


if __name__ == "__main__":
    raise SystemExit(main())
