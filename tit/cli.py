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
from pathlib import Path
import sys
import subprocess
import shutil

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
    user_config_dir,
)

LAUNCH_EPILOG = """\
examples:
  tit launch --project ~/datasets/000        start (or attach) and open the UI
  tit launch --project ~/datasets/000 --status
  tit launch --project ~/datasets/000 --logs --follow
  tit launch --project ~/datasets/000 --stop

Regular launches open the browser; its container persists after closing the tab.
Use --desktop to open Electron and stop its container on app close.
"""


def launch_arguments() -> argparse.ArgumentParser:
    """The ``launch`` options, as a reusable parent parser.

    Declared once and shared by three front doors so they cannot drift: the ``tit
    launch`` subcommand below, ``loader.py`` at the repository root, and
    ``dev/loader/loader_dev.py``.  ``add_help=False`` because a parent parser must not
    install a second ``-h``.
    """
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--interactive",
        action="store_true",
        help="prompt for a project (automatic with no arguments)",
    )
    parent.add_argument(
        "--project",
        "--project-dir",
        default=os.environ.get("TIT_PROJECT_DIR"),
        metavar="DIR",
        help="the BIDS project directory to open (default: $TIT_PROJECT_DIR)",
    )
    parent.add_argument(
        "--port",
        type=int,
        default=8765,
        help="first host port to try (default: 8765; the next free one is used if it is taken)",
    )
    parent.add_argument(
        "--image",
        default=None,
        metavar="IMAGE:TAG",
        help=f"container image to run (default: {default_image()})",
    )
    parent.add_argument(
        "--desktop",
        action="store_true",
        help="open Electron and stop its container on app close",
    )
    parent.add_argument(
        "--no-open",
        action="store_true",
        help="print the URL instead of opening a browser",
    )
    parent.add_argument(
        "--browser",
        action="store_true",
        help="explicitly use the browser UI instead of Electron",
    )
    parent.add_argument(
        "--existing",
        choices=("attach", "recreate"),
        help="explicit existing-container decision; recreate stops jobs and removes it",
    )
    parent.add_argument(
        "--container", help="running container name or full ID to select"
    )
    parent.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        metavar="SECONDS",
        help="how long to wait for the server to answer (default: 180)",
    )
    mode = parent.add_mutually_exclusive_group()
    mode.add_argument(
        "--stop", action="store_true", help="stop and remove this project's container"
    )
    mode.add_argument(
        "--status", action="store_true", help="report the container's state and URL"
    )
    mode.add_argument("--logs", action="store_true", help="print the container's logs")
    parent.add_argument(
        "--follow", "-f", action="store_true", help="with --logs, keep streaming"
    )
    return parent


def launch_parser(prog: str = "tit launch") -> argparse.ArgumentParser:
    """A standalone parser for the launch options, for front doors with no subcommand.

    ``loader.py`` and ``dev/loader/loader_dev.py`` use this so that their ``--help`` is
    the same one screen ``tit launch --help`` prints, under their own name.
    """
    return argparse.ArgumentParser(
        prog=prog,
        description="Start the TI-Toolbox container for one project and open its UI in a browser.",
        epilog=LAUNCH_EPILOG.replace("tit launch", prog),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[launch_arguments()],
    )


def prompt_launch(args: argparse.Namespace, *, requested: bool) -> None:
    """Collect launch settings before Docker is touched; explicit CLI runs stay scriptable."""
    if not requested:
        return
    if not sys.stdin.isatty():
        raise LaunchError(
            "interactive setup needs a terminal; pass --project /path/to/project and any other options explicitly"
        )
    print("\nWelcome to TI-Toolbox")
    print("Center for Sleep and Consciousness · UW–Madison")
    print("Simulate, optimize and analyze temporal interference stimulation.")
    print("\nChoose your project directory to get started.\n")
    saved_path = user_config_dir() / "last-project.txt"
    default = args.project
    if not default:
        try:
            default = saved_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            default = ""
        except (OSError, UnicodeError):
            print(
                "Could not read the previous project; enter its path again.",
                file=sys.stderr,
            )
    while True:
        prompt = (
            f"Project directory [{default}]: " if default else "Project directory: "
        )
        value = input(prompt).strip() or default
        if not value:
            print("Enter a project directory.")
            continue
        path = Path(value).expanduser()
        if not path.is_dir():
            print(f"Directory does not exist: {path}")
            continue
        args.project = str(path.resolve())
        try:
            saved_path.write_text(args.project + "\n", encoding="utf-8")
        except OSError:
            print("Could not remember this project for next time.", file=sys.stderr)
        args.resume_session = (
            not args.image and not os.environ.get("TIT_IMAGE_TAG", "").strip()
        )
        return


def prepare_launch(args: argparse.Namespace, argv: list[str]) -> int | None:
    """Return an exit code on cancelled/unavailable input, otherwise prepare the options."""
    if args.desktop and (args.browser or args.no_open):
        print(
            "--desktop cannot be combined with --browser or --no-open", file=sys.stderr
        )
        return 2
    try:
        prompt_launch(args, requested=not argv or args.interactive)
    except EOFError:
        print("\nSetup cancelled: no input received.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nSetup cancelled.", file=sys.stderr)
        return 130
    except (LaunchError, OSError) as err:
        print(str(err), file=sys.stderr)
        return 2
    return None


def build_parser() -> argparse.ArgumentParser:
    """The whole CLI surface, built separately so a test can assert it without running it."""
    parser = argparse.ArgumentParser(prog="tit", description="TI-Toolbox command line.")
    parser.add_argument(
        "--version", action="version", version=f"TI-Toolbox {tit.__version__}"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "launch",
        help="run the TI-Toolbox UI in a browser (no Electron required)",
        description="Start the TI-Toolbox container for one project and open its UI in a browser.",
        epilog=LAUNCH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[launch_arguments()],
    )
    return parser


def launch_command(
    args: argparse.Namespace,
    *,
    invocation: str = "tit launch",
    repo_dir: str = "",
    server_reload: bool = False,
    static_dir: str = "",
) -> int:
    """Run one launch invocation, turning every failure into one actionable line.

    ``invocation`` is how this front door is spelled (``tit launch``, ``python
    loader.py``, ``python dev/loader/loader_dev.py``); it appears in the follow-up hints
    and in error messages, so the line printed is a line the user can actually retype.

    ``repo_dir``/``server_reload``/``static_dir`` are the dev overrides — the same three
    the root ``docker-compose.yml`` exposes as ``${TIT_REPO_DIR:-}``,
    ``${TIT_SERVER_RELOAD:-}`` and ``${TIT_STATIC_DIR:-}``, and the only thing
    ``dev/loader/docker-compose.dev.yml`` sets.  All three are off for a user run.
    """
    try:
        return _dispatch(
            args,
            invocation=invocation,
            repo_dir=repo_dir,
            server_reload=server_reload,
            static_dir=static_dir,
        )
    except (LaunchError, OSError) as err:
        print(f"{invocation}: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


def _dispatch(
    args: argparse.Namespace,
    *,
    invocation: str,
    repo_dir: str,
    server_reload: bool,
    static_dir: str,
) -> int:
    if args.stop:
        removed = launch_stop(args.project)
        print(
            f"stopped and removed {', '.join(removed)}"
            if removed
            else "nothing to stop for that project"
        )
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

    if args.desktop and not getattr(args, "dev_loader", False):
        helper = Path(__file__).resolve().parent.parent / "dev" / "launch-electron.sh"
        executable = os.environ.get("TIT_ELECTRON_EXECUTABLE", "")
        if not executable and not helper.is_file():
            candidates = [
                Path("/Applications/TI-Toolbox.app/Contents/MacOS/TI-Toolbox"),
                Path.home() / "Applications/TI-Toolbox.app/Contents/MacOS/TI-Toolbox",
            ]
            executable = next((str(path) for path in candidates if path.is_file()), "")
            executable = executable or shutil.which("ti-toolbox") or ""
        if not executable and not helper.is_file():
            raise LaunchError(
                "Electron launcher is unavailable in this installation. Run loader.py from "
                "a full checkout, install the desktop app, or explicitly pass --browser."
            )
        env = dict(os.environ)
        for key in (
            "ELECTRON_RUN_AS_NODE",
            "ELECTRON_RENDERER_URL",
            "TIT_LAUNCH_CONTAINER_ID",
            "TIT_DEV_SERVER_URL",
            "TIT_DEV_SERVER_TOKEN",
            "TIT_DEV_PROJECT_DIR",
            "TIT_DEV_REPO_DIR",
            "TIT_REPO_DIR",
            "TIT_SERVER_RELOAD",
            "TIT_STATIC_DIR",
        ):
            env.pop(key, None)
        from tit.launch import resolve_project

        env["TIT_LAUNCH_PROJECT_DIR"] = resolve_project(args.project)
        env["TIT_LAUNCH_PORT"] = str(args.port)
        env["TIT_LAUNCH_TIMEOUT"] = str(args.timeout)
        env["TIT_LAUNCH_IMAGE"] = args.image or default_image()
        env.pop("TIT_IMAGE_TAG", None)
        env["TIT_LAUNCH_EXISTING"] = args.existing or ""
        env["TIT_LAUNCH_CONTAINER"] = args.container or ""
        command = [executable] if executable else ["bash", str(helper)]
        if not shutil.which(command[0]):
            raise LaunchError(
                "Electron launcher executable is unavailable; set TIT_ELECTRON_EXECUTABLE "
                "to the installed desktop executable or explicitly use --browser."
            )
        returncode = subprocess.run(command, env=env, check=False).returncode
        if returncode == 0 and executable:
            print("TI-Toolbox closed.")
        return returncode

    options = LaunchOptions(
        project=args.project,
        port=args.port,
        image=args.image,
        open_browser=not args.no_open,
        timeout=args.timeout,
        repo_dir=repo_dir,
        server_reload=server_reload,
        static_dir=static_dir,
        existing=args.existing,
        container=args.container,
    )
    origin, token = start(options)
    url = session_url(origin, token)
    print()
    print(f"TI-Toolbox is running at {origin}")
    print(f"Open this URL to sign in (it is single-use per session):\n  {url}")
    print()
    print("The container keeps running after this command exits.")
    print(
        f"  {invocation} --project {options.session_project or args.project} --status   state and URL"
    )
    print(
        f"  {invocation} --project {options.session_project or args.project} --stop     shut it down"
    )
    if not args.no_open:
        open_in_browser(url)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point; every :class:`~tit.launch.LaunchError` becomes one actionable line."""
    arguments = argv if argv is not None else sys.argv[1:]
    args = build_parser().parse_args(arguments)
    if args.command == "launch":
        result = prepare_launch(args, arguments[1:])
        if result is not None:
            return result
        return launch_command(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
