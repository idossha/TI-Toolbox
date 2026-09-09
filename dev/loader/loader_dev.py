#!/usr/bin/env python3
"""``dev/loader/loader_dev.py`` — the developer's equivalent of the root ``loader.py``.

    python dev/loader/loader_dev.py --project ~/datasets/000
    python dev/loader/loader_dev.py --project ~/datasets/000 --status | --logs | --stop
    python dev/loader/loader_dev.py --build                 # build the image, then exit
    python dev/loader/loader_dev.py --web                   # hand over to `npm run dev:web`

Same options as ``loader.py`` (they come from the same
:func:`tit.cli.launch_arguments`), plus the three a developer needs: ``--build``,
``--image`` and ``--web``.  The difference in what it *starts* is exactly the three
overrides ``docker-compose.dev.yml`` next to this file documents, and nothing else:

    TIT_REPO_DIR      this checkout, bind-mounted at /ti-toolbox
    TIT_SERVER_RELOAD 1, so uvicorn restarts on an edit under tit/
    TIT_STATIC_DIR    this worktree's built renderer, never the image's baked UI

**Where the dev loop lives.**  ``--web`` does not reimplement Vite: it execs
``npm run dev:web`` in ``desktop/``, which is ``desktop/scripts/dev.ts`` — the one
implementation of the container-plus-Vite-plus-Electron loop, driven by the same
``StackManager`` the packaged app uses.  A second copy of that orchestration in Python
would drift from it on the first change, and a developer would be testing a loop the
product does not have.  What this file owns instead is the Node-free path: starting the
dev container from Python alone, for a checkout with no ``npm install`` in it.

Standard library only, like the root loader.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DESKTOP = REPO / "desktop"
BUILD_SH = REPO / "container" / "blueprint" / "build.sh"

if (REPO / "tit" / "launch.py").is_file() and str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

DEV_EPILOG = """\
examples:
  python dev/loader/loader_dev.py --project ~/datasets/000     start (or attach), open the UI
  python dev/loader/loader_dev.py --project ~/datasets/000 --status | --logs | --stop
  python dev/loader/loader_dev.py --build                      build the image, then exit
  python dev/loader/loader_dev.py --web                        hand over to `npm run dev:web`

developer options (the user loader has none of these):
  --build          build idossha/ti-toolbox:<tag> from this checkout, then exit
                   (container/blueprint/build.sh; 30-60+ min, longer under emulation)
  --web            container + Vite with HMR at http://127.0.0.1:5173/, via
                   `npm run dev:web`. Needs `npm --prefix desktop install` first.
  --no-mount-repo  run the image's own `tit` instead of this worktree's

Without --web the dev container starts from Python alone: no Node, no Electron.
"""


def main(argv: list[str] | None = None) -> int:
    try:
        from tit.cli import launch_command, launch_parser, prepare_launch
    except ImportError as err:  # pragma: no cover
        sys.stderr.write(f"loader_dev.py: could not import `tit` from {REPO} ({err})\n")
        return 2

    parser = launch_parser(prog="python dev/loader/loader_dev.py")
    parser.epilog = DEV_EPILOG
    # Described in the epilog above rather than listed twice in the options block.
    parser.add_argument("--build", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--web", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-mount-repo", action="store_true", help=argparse.SUPPRESS)
    arguments = argv if argv is not None else sys.argv[1:]
    args = parser.parse_args(arguments)
    result = prepare_launch(args, arguments)
    if result is not None:
        return result

    if args.build:
        return build_image(args.image)
    if args.web:
        return run_npm_dev_web(args)

    repo_dir = "" if args.no_mount_repo else str(REPO)
    static_dir = ""
    if repo_dir:
        static_dir = "/ti-toolbox/desktop/out/renderer"
        if (
            not (args.status or args.logs or args.stop or args.no_open)
            and not (DESKTOP / "out" / "renderer" / "index.html").is_file()
        ):
            sys.stderr.write(
                "loader_dev.py: this checkout has no built renderer. Run "
                "`npm --prefix desktop run build`, or use --web for Vite with live edits. "
                "Use --no-open to start only the API server.\n"
            )
            return 2
    return launch_command(
        args,
        invocation="python dev/loader/loader_dev.py",
        repo_dir=repo_dir,
        server_reload=bool(repo_dir),
        static_dir=static_dir,
    )


def build_image(image: str | None) -> int:
    """``container/blueprint/build.sh --tag <image>`` — the only way to get a v3 image today."""
    if not BUILD_SH.is_file():
        sys.stderr.write(
            f"loader_dev.py: {BUILD_SH} not found; is this a full checkout?\n"
        )
        return 2
    tag = image or "idossha/ti-toolbox:dev"
    print(f"[dev] {BUILD_SH} --tag {tag}")
    return subprocess.run([str(BUILD_SH), "--tag", tag], cwd=str(REPO)).returncode


def run_npm_dev_web(args) -> int:
    """Hand over to ``desktop/scripts/dev.ts`` — the one dev-loop implementation."""
    from tit.launch import default_image

    image = args.image or default_image()
    if not image.startswith("idossha/ti-toolbox:") or "@" in image:
        sys.stderr.write(
            "loader_dev.py: --web supports tagged idossha/ti-toolbox images only. "
            "Use the Python loader without --web for a custom repository or digest.\n"
        )
        return 2
    if not (DESKTOP / "node_modules").is_dir():
        sys.stderr.write(
            "loader_dev.py: --web needs the desktop dependencies. Run:\n"
            "    npm --prefix desktop install\n"
        )
        return 2
    env = dict(os.environ)
    if args.project:
        env["TIT_DEV_PROJECT_DIR"] = str(Path(args.project).expanduser().resolve())
    if args.port:
        env["TIT_DEV_PORT"] = str(args.port)
    env["TIT_DEV_IMAGE_TAG"] = image.rsplit(":", 1)[-1]
    env["TIT_DEV_MOUNT_REPO"] = "0" if args.no_mount_repo else "1"
    print("[dev] npm run dev:web (desktop/scripts/dev.ts)")
    return subprocess.run(
        ["npm", "run", "dev:web"], cwd=str(DESKTOP), env=env
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
