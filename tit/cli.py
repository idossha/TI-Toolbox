"""The ``tit`` console command.

Installed by ``pyproject.toml``'s ``[project.scripts]``, so ``pip install tit``
(or ``pipx run tit``) on any host with CPython >= 3.11 and the ``docker`` CLI
gets a working launcher — no SimNIBS, no Electron, no Node.

Today there is one subcommand, ``launch``.  It is a subcommand rather than a
second console script because the natural next ones (``tit doctor``,
``tit version``) belong under the same name, and adding them later must not
change how ``launch`` is spelled.
"""

from __future__ import annotations

import argparse
import os
import sys

import tit
from tit.launch import (
    LaunchError,
    LaunchOptions,
    default_image,
    logs as launch_logs,
    open_in_browser,
    session_url,
    start,
    status as launch_status,
    stop as launch_stop,
)

LAUNCH_EPILOG = """\
examples:
  tit launch --project ~/datasets/000        start (or attach) and open the UI
  tit launch --project ~/datasets/000 --status
  tit launch --project ~/datasets/000 --logs --follow
  tit launch --project ~/datasets/000 --stop

The UI runs in your browser and is the same one the desktop app shows. Everything
that talks to the server works identically; the few Electron-only conveniences
(reveal a file in your file manager, native notifications) say so when used.
"""


def build_parser() -> argparse.ArgumentParser:
    """The whole CLI surface, built separately so a test can assert it without running it."""
    parser = argparse.ArgumentParser(prog="tit", description="TI-Toolbox command line.")
    parser.add_argument("--version", action="version", version=f"TI-Toolbox {tit.__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch = subparsers.add_parser(
        "launch",
        help="run the TI-Toolbox UI in a browser (no Electron required)",
        description="Start the TI-Toolbox container for one project and open its UI in a browser.",
        epilog=LAUNCH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    launch.add_argument(
        "--project",
        default=os.environ.get("TIT_PROJECT_DIR"),
        metavar="DIR",
        help="the BIDS project directory to open (default: $TIT_PROJECT_DIR)",
    )
    launch.add_argument(
        "--port", type=int, default=8765,
        help="first host port to try (default: 8765; the next free one is used if it is taken)",
    )
    launch.add_argument(
        "--image", default=None, metavar="IMAGE:TAG",
        help=f"container image to run (default: {default_image()})",
    )
    launch.add_argument("--no-open", action="store_true", help="print the URL instead of opening a browser")
    launch.add_argument(
        "--timeout", type=float, default=180.0, metavar="SECONDS",
        help="how long to wait for the server to answer (default: 180)",
    )
    mode = launch.add_mutually_exclusive_group()
    mode.add_argument("--stop", action="store_true", help="stop and remove this project's container")
    mode.add_argument("--status", action="store_true", help="report the container's state and URL")
    mode.add_argument("--logs", action="store_true", help="print the container's logs")
    launch.add_argument("--follow", "-f", action="store_true", help="with --logs, keep streaming")
    return parser


def _launch(args: argparse.Namespace) -> int:
    if args.stop:
        removed = launch_stop(args.project)
        print(f"stopped and removed {', '.join(removed)}" if removed else "nothing to stop for that project")
        return 0
    if args.status:
        info = launch_status(args.project)
        if info is None:
            print("no TI-Toolbox container exists for that project directory")
            return 1
        for key in ("name", "state", "health", "image", "origin"):
            print(f"{key:8} {info[key]}")
        return 0
    if args.logs:
        return launch_logs(args.project, follow=args.follow)

    origin, token = start(
        LaunchOptions(
            project=args.project,
            port=args.port,
            image=args.image,
            open_browser=not args.no_open,
            timeout=args.timeout,
        )
    )
    url = session_url(origin, token)
    print()
    print(f"TI-Toolbox is running at {origin}")
    print(f"Open this URL to sign in (it is single-use per session):\n  {url}")
    print()
    print("The container keeps running after this command exits.")
    print(f"  tit launch --project {args.project} --status   state and URL")
    print(f"  tit launch --project {args.project} --stop     shut it down")
    if not args.no_open:
        open_in_browser(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point; every :class:`~tit.launch.LaunchError` becomes one actionable line."""
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.command == "launch":
            return _launch(args)
    except LaunchError as err:
        print(f"tit launch: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
