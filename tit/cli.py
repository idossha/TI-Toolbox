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
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

import tit
from tit.launch import (
    LaunchError,
    LaunchOptions,
    container_name,
    default_image,
    logs as launch_logs,
    open_in_browser,
    resolve_project,
    session_url,
    start,
    status as launch_status,
    stop as launch_stop,
    user_config_dir,
)

LAUNCH_EPILOG = """\
examples:
  tit launch --project ~/datasets/000 [--status|--logs|--stop]

The desktop app is downloaded and checksum-verified on first run; without --project it opens
its own project page. --browser, --no-open and a failed download use the browser, which does
need --project. --dev changes only the *source* of the server and renderer (mount + reload).
  --dev [DIR] run a checkout   --dev --build build the image   --dev --web Vite HMR
"""

DEV_RENDERER = "/ti-toolbox/desktop/out/renderer"

# The desktop app is the product; the loader bootstraps it (docs/dev/DECISIONS.md, 2026-09-15).
# Repository and asset names come from desktop/electron-builder.yml (`publish:`, `artifactName`)
# and from dev/update/verify_release_assets.py, which is what the release actually attaches.
RELEASE_REPO = "idossha/TI-Toolbox"
RELEASE_BASE_URL = "https://github.com/idossha/TI-Toolbox/releases/download"
CHECKSUM_ASSET = "SHA256SUMS"


def release_base_url() -> str:
    """Where release assets are fetched from; overridable so tests never touch the network."""
    return os.environ.get("TIT_RELEASE_BASE_URL") or RELEASE_BASE_URL


def desktop_data_dir() -> Path:
    """Per-user data root that holds managed desktop installs (``<data>/app/<version>``)."""
    override = os.environ.get("TIT_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "TI-Toolbox"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "TI-Toolbox"
    root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / "ti-toolbox"


def desktop_asset_name(version: str) -> str:
    """The release asset for this platform, or ``""`` where no managed install exists."""
    machine = platform.machine().lower()
    if sys.platform == "darwin":
        if machine in ("arm64", "aarch64"):
            return f"TI-Toolbox-{version}-arm64-mac.zip"
        return f"TI-Toolbox-{version}-mac.zip"
    if sys.platform.startswith("linux") and machine in ("x86_64", "amd64"):
        return f"TI-Toolbox-{version}.AppImage"
    return ""


def managed_executable(install_dir: Path) -> Path | None:
    """Where the executable lands inside one managed ``<data>/app/<version>`` directory."""
    if sys.platform == "darwin":
        return install_dir / "TI-Toolbox.app" / "Contents" / "MacOS" / "TI-Toolbox"
    if sys.platform.startswith("linux"):
        return install_dir / "TI-Toolbox.AppImage"
    return None


def resolve_desktop_executable() -> str:
    """``TIT_ELECTRON_EXECUTABLE`` -> managed install -> ``"download"`` -> ``""``.

    ``loader.sh`` implements the same three steps in a function of the same name; the two
    must agree, which ``--print-config``'s ``desktop_executable`` line lets a test assert
    without any network.
    """
    override = os.environ.get("TIT_ELECTRON_EXECUTABLE", "")
    if override and os.access(override, os.X_OK) and Path(override).is_file():
        return override
    version = tit.__version__
    executable = managed_executable(desktop_data_dir() / "app" / version)
    if executable is not None and os.access(executable, os.X_OK):
        return str(executable)
    return "download" if desktop_asset_name(version) else ""


def _fetch(url: str, destination: Path, *, progress: bool = False) -> None:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 - fixed https/file base
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(262144)
                if not chunk:
                    break
                handle.write(chunk)
                done += len(chunk)
                if progress and total:
                    print(
                        f"\rdownloading TI-Toolbox {done * 100 // total}%",
                        end="",
                        file=sys.stderr,
                    )
    if progress and total:
        print("", file=sys.stderr)


def _expected_checksum(base: str, asset: str) -> str:
    """The recorded sha256 for ``asset``; installing unverified bytes is never allowed."""
    with tempfile.TemporaryDirectory() as scratch:
        sums = Path(scratch) / CHECKSUM_ASSET
        _fetch(f"{base}/{CHECKSUM_ASSET}", sums)
        for line in sums.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == asset:
                return parts[0]
    raise LaunchError(f"{CHECKSUM_ASSET} does not list {asset}")


def install_desktop_executable() -> str:
    """Download, verify and atomically install the desktop app; return its path.

    Raises :class:`LaunchError` with one printable reason; the caller falls back to the
    browser unless ``--desktop`` was explicit.
    """
    version = tit.__version__
    asset = desktop_asset_name(version)
    if not asset:
        raise LaunchError(
            f"no desktop build for {sys.platform}/{platform.machine()}"
        )
    base = f"{release_base_url()}/v{version}"
    root = desktop_data_dir() / "app"
    root.mkdir(parents=True, exist_ok=True)
    print(f"downloading the TI-Toolbox desktop app ({asset})", file=sys.stderr)
    try:
        expected = _expected_checksum(base, asset)
        with tempfile.TemporaryDirectory(dir=str(root)) as scratch:
            archive = Path(scratch) / asset
            _fetch(f"{base}/{asset}", archive, progress=True)
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            if digest != expected:
                raise LaunchError(f"checksum mismatch for {asset}")
            staged = Path(scratch) / "app"
            staged.mkdir()
            if asset.endswith(".zip"):
                # ``unzip`` preserves the symlinks and the executable bits inside a .app
                # bundle; zipfile does not, and an unsigned-looking bundle will not start.
                subprocess.run(
                    ["unzip", "-q", str(archive), "-d", str(staged)],
                    check=True,
                    capture_output=True,
                )
            else:
                target = staged / "TI-Toolbox.AppImage"
                shutil.move(str(archive), str(target))
                target.chmod(0o755)
            executable = managed_executable(staged)
            if executable is None or not executable.is_file():
                raise LaunchError(f"{asset} did not contain the expected executable")
            executable.chmod(0o755)
            final = root / version
            if final.exists():
                shutil.rmtree(final, ignore_errors=True)
            os.rename(staged, final)
    except LaunchError:
        raise
    except (OSError, urllib.error.URLError, subprocess.CalledProcessError) as err:
        raise LaunchError(f"could not download the desktop app ({err})") from err
    for stale in root.iterdir():
        if stale.is_dir() and stale.name != version:
            shutil.rmtree(stale, ignore_errors=True)
    return str(managed_executable(root / version))


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
        help="prompt for a project (browser; automatic with no args)",
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
        help="require the desktop app, never the browser",
    )
    parent.add_argument(
        "--no-open",
        action="store_true",
        help="print the URL instead of opening a browser",
    )
    parent.add_argument(
        "--browser",
        action="store_true",
        help="use the browser UI instead of the desktop app",
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
    parent.add_argument(
        "--dev",
        nargs="?",
        const="",
        default=os.environ.get("TIT_DEV_REPO_DIR")
        or ("" if os.environ.get("TIT_DEV") else None),
        metavar="DIR",
        help="run this checkout's code, not the image's (see below)",
    )
    parent.add_argument(
        "--print-config",
        action="store_true",
        help="print the resolved settings and exit; no Docker calls",
    )
    # Developer extras; described in the epilog rather than listed twice in the options block.
    parent.add_argument("--no-mount-repo", action="store_true", help=argparse.SUPPRESS)
    parent.add_argument("--build", action="store_true", help=argparse.SUPPRESS)
    parent.add_argument("--web", action="store_true", help=argparse.SUPPRESS)
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
        description="Start the TI-Toolbox container for one project and open its UI.",
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


def dev_repo(args: argparse.Namespace) -> Path | None:
    """The checkout ``--dev`` selects, or ``None`` for a regular user run.

    ``--dev`` with no value means "the checkout this launcher lives in"; ``TIT_DEV_REPO_DIR``
    (or ``TIT_DEV=1``) is the environment spelling of the same flag.  Only the *source* of
    the server and renderer differs between the two modes; nothing else does.
    """
    if args.dev is None:
        return None
    root = (
        Path(args.dev).expanduser()
        if args.dev
        else Path(__file__).resolve().parent.parent
    )
    root = root.resolve()
    if not (root / "tit" / "launch.py").is_file() or not (root / "loader.py").is_file():
        raise LaunchError(
            f"not a TI-Toolbox checkout: {root}. Pass --dev DIR or set TIT_DEV_REPO_DIR."
        )
    return root


def dev_overrides(args: argparse.Namespace) -> tuple[str, str, bool]:
    """``(repo_dir, static_dir, server_reload)`` — the only three settings ``--dev`` changes.

    They are the same three the root ``docker-compose.yml`` exposes as ``${TIT_REPO_DIR:-}``,
    ``${TIT_STATIC_DIR:-}`` and ``${TIT_SERVER_RELOAD:-}``.  All three are empty for a user run.
    """
    root = dev_repo(args)
    if root is None or args.no_mount_repo:
        return "", "", False
    return str(root), DEV_RENDERER, True


def prepare_launch(args: argparse.Namespace, argv: list[str]) -> int | None:
    """Return an exit code on cancelled/unavailable input, otherwise prepare the options."""
    if args.desktop and (args.browser or args.no_open):
        print(
            "--desktop cannot be combined with --browser or --no-open", file=sys.stderr
        )
        return 2
    try:
        requested = (not argv or args.interactive) and not desktop_without_project(args)
        prompt_launch(args, requested=requested)
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
        help="run the TI-Toolbox UI (desktop app by default, --browser for a browser)",
        description="Start the TI-Toolbox container for one project and open its UI.",
        epilog=LAUNCH_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        parents=[launch_arguments()],
    )
    return parser


def launch_command(args: argparse.Namespace, *, invocation: str = "tit launch") -> int:
    """Run one launch invocation, turning every failure into one actionable line.

    ``invocation`` is how this front door is spelled (``tit launch``, ``python
    loader.py``, ``python dev/loader/loader_dev.py``); it appears in the follow-up hints
    and in error messages, so the line printed is a line the user can actually retype.

    The dev overrides come from ``--dev`` via :func:`dev_overrides`, so every front door
    computes them the same way.
    """
    try:
        return _dispatch(args, invocation=invocation)
    except (LaunchError, OSError) as err:
        print(f"{invocation}: {err}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


def build_image(root: Path, image: str | None) -> int:
    """``container/blueprint/build.sh --tag <image>`` — the only way to get a v3 image today."""
    script = root / "container" / "blueprint" / "build.sh"
    if not script.is_file():
        raise LaunchError(f"{script} not found; is this a full checkout?")
    tag = image or "idossha/ti-toolbox:dev"
    print(f"[dev] {script} --tag {tag}")
    return subprocess.run([str(script), "--tag", tag], cwd=str(root)).returncode


def run_dev_web(root: Path, args: argparse.Namespace) -> int:
    """Hand over to ``desktop/scripts/dev.ts`` — the one dev-loop implementation."""
    desktop = root / "desktop"
    image = args.image or default_image()
    if not image.startswith("idossha/ti-toolbox:") or "@" in image:
        raise LaunchError(
            "--web supports tagged idossha/ti-toolbox images only. Drop --web for a "
            "custom repository or digest."
        )
    if not (desktop / "node_modules").is_dir():
        raise LaunchError("--web needs the desktop dependencies: npm --prefix desktop install")
    env = dict(os.environ)
    if args.project:
        env["TIT_DEV_PROJECT_DIR"] = str(Path(args.project).expanduser().resolve())
    if args.port:
        env["TIT_DEV_PORT"] = str(args.port)
    env["TIT_DEV_IMAGE_TAG"] = image.rsplit(":", 1)[-1]
    env["TIT_LAUNCH_EXISTING"] = args.existing or ""
    env["TIT_LAUNCH_CONTAINER"] = args.container or ""
    env["TIT_DEV_MOUNT_REPO"] = "0" if args.no_mount_repo else "1"
    print("[dev] npm run dev:web (desktop/scripts/dev.ts)")
    return subprocess.run(["npm", "run", "dev:web"], cwd=str(desktop), env=env).returncode


def wants_desktop(args: argparse.Namespace, root: Path | None) -> bool:
    """The desktop app is the default UI; the browser is the fallback and the opt-out.

    ``--browser`` and ``--no-open`` mean the browser explicitly, and a ``--dev`` checkout
    keeps its historical browser default (developers ask for Electron with ``--desktop``).
    """
    if args.desktop:
        return True
    if args.browser or args.no_open or root is not None:
        return False
    return (os.environ.get("TIT_LAUNCH_UI") or "desktop") == "desktop"


def desktop_without_project(args: argparse.Namespace) -> bool:
    """True when the desktop app should open its own project page instead of one project.

    The app has a project-entry page and starts its own container; a Dock launch carries no
    ``TIT_LAUNCH_PROJECT_DIR`` at all. So ``--desktop`` without ``--project`` is not an error:
    neither the prompt nor the project requirement applies. loader.sh's ``desktop_no_project``
    is the same predicate.
    """
    if args.project or args.stop or args.status or args.logs or args.build or args.web:
        return False
    return wants_desktop(args, dev_repo(args))


def _run_desktop(
    args: argparse.Namespace,
    executable: str,
    helper: Path | None,
    repo_dir: str,
) -> int:
    """Hand the container lifecycle to Electron; identical to double-clicking the app."""
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
    if repo_dir:
        env["TIT_DEV_REPO_DIR"] = repo_dir
    # No project means "show the app's project page"; an unset variable is what a Dock launch has.
    if args.project:
        env["TIT_LAUNCH_PROJECT_DIR"] = resolve_project(args.project)
    else:
        env.pop("TIT_LAUNCH_PROJECT_DIR", None)
    env["TIT_LAUNCH_PORT"] = str(args.port)
    env["TIT_LAUNCH_TIMEOUT"] = str(args.timeout)
    env["TIT_LAUNCH_IMAGE"] = args.image or default_image()
    env.pop("TIT_IMAGE_TAG", None)
    env["TIT_LAUNCH_EXISTING"] = args.existing or ""
    env["TIT_LAUNCH_CONTAINER"] = args.container or ""
    command = [executable] if executable else ["bash", str(helper)]
    if not (Path(command[0]).is_file() or shutil.which(command[0])):
        raise LaunchError(
            "Electron launcher executable is unavailable; set TIT_ELECTRON_EXECUTABLE "
            "to the installed desktop executable or explicitly use --browser."
        )
    returncode = subprocess.run(command, env=env, check=False).returncode
    if returncode == 0 and executable:
        print("TI-Toolbox closed.")
    return returncode



def _dispatch(args: argparse.Namespace, *, invocation: str) -> int:
    repo_dir, static_dir, server_reload = dev_overrides(args)
    root = dev_repo(args)
    if args.build or args.web:
        if root is None:
            raise LaunchError("--build and --web need --dev; add --dev [DIR]")
        return build_image(root, args.image) if args.build else run_dev_web(root, args)
    desktop = wants_desktop(args, root)
    if args.print_config:
        project = resolve_project(args.project) if args.project else ""
        executable = (
            resolve_desktop_executable() if desktop and root is None else ""
        )
        print(f"mode      {'dev' if root else 'user'}")
        print(f"project   {project}")
        print(f"port      {args.port}")
        print(f"image     {args.image or default_image()}")
        print(f"container {container_name(project) if project else ''}")
        print(f"origin    http://127.0.0.1:{args.port}")
        print(f"ui        {'desktop' if desktop else 'browser'}")
        print(f"repo_dir  {repo_dir}")
        print(f"static    {static_dir}")
        print(f"reload    {'1' if server_reload else ''}")
        print(f"desktop_executable {executable}")
        return 0
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

    if repo_dir and not args.no_open:
        built = Path(repo_dir) / "desktop" / "out" / "renderer" / "index.html"
        if not built.is_file():
            raise LaunchError(
                f"this checkout has no built renderer ({built}). Run "
                "`npm --prefix desktop run build`, or use --dev --web for Vite with live "
                "edits, or --no-open to start only the API server."
            )
    if desktop:
        helper = Path(__file__).resolve().parent.parent / "dev" / "launch-electron.sh"
        executable = ""
        if repo_dir and helper.is_file():
            pass  # developer path: Electron from desktop/node_modules
        else:
            helper = None
            executable = resolve_desktop_executable()
            if executable == "download":
                try:
                    executable = install_desktop_executable()
                except LaunchError as err:
                    executable = ""
                    reason = str(err)
            elif not executable:
                reason = (
                    f"no desktop build for {sys.platform}/{platform.machine()}"
                )
            if not executable:
                if args.desktop:
                    raise LaunchError(reason)
                print(f"{invocation}: {reason}; opening the browser instead.", file=sys.stderr)
        if executable or helper is not None:
            return _run_desktop(args, executable, helper, repo_dir)

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
