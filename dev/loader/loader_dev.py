#!/usr/bin/env python3
"""Thin shim for ``python loader.py --dev <checkout>``.

There is one launcher with one behaviour; ``--dev`` changes only the *source* of the
server and renderer (checkout mount, server reload, the checkout's built renderer).
This wrapper exists so a copy placed outside the checkout can still select one through
``TIT_DEV_REPO_DIR``, and so existing muscle memory keeps working.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = (
    Path(os.environ.get("TIT_DEV_REPO_DIR", str(HERE.parent.parent)))
    .expanduser()
    .resolve()
)

INVOCATION = "python dev/loader/loader_dev.py"


def main(argv: list[str] | None = None) -> int:
    if not (REPO / "tit" / "launch.py").is_file() or not (REPO / "loader.py").is_file():
        sys.stderr.write(
            f"loader_dev.py: not a TI-Toolbox checkout: {REPO}. "
            "Set TIT_DEV_REPO_DIR to your local checkout.\n"
        )
        return 2
    if "TIT_COMPOSE_FILE" not in os.environ and (HERE / "docker-compose.yml").is_file():
        os.environ["TIT_COMPOSE_FILE"] = str(HERE / "docker-compose.yml")
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    try:
        from tit.cli import launch_command, launch_parser, prepare_launch
    except ImportError as err:  # pragma: no cover - exercised by the message, not a test
        sys.stderr.write(f"loader_dev.py: could not import `tit` from {REPO} ({err})\n")
        return 2

    arguments = argv if argv is not None else sys.argv[1:]
    args = launch_parser(prog=INVOCATION).parse_args(arguments)
    args.dev = args.dev if args.dev else str(REPO)
    result = prepare_launch(args, arguments)
    if result is not None:
        return result
    return launch_command(args, invocation=INVOCATION)


if __name__ == "__main__":
    raise SystemExit(main())
