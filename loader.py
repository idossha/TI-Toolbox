#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PATHS_FILE = SCRIPT_DIR / ".default_paths.user"
DOCKER_COMPOSE_FILE = SCRIPT_DIR / "docker-compose.yml"
VERBOSE = False


def run(
    cmd: list[str],
    *,
    check: bool = True,
    env: Optional[dict[str, str]] = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    if VERBOSE and not capture_output:
        return subprocess.run(cmd, check=check, env=env)
    return subprocess.run(
        cmd,
        check=check,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def capture(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def load_default_project_dir() -> str:
    if not DEFAULT_PATHS_FILE.exists():
        return ""
    content = DEFAULT_PATHS_FILE.read_text(errors="ignore")
    match = re.search(r'LOCAL_PROJECT_DIR="([^"]*)"', content)
    return match.group(1) if match else ""


def save_default_project_dir(project_dir: str) -> None:
    DEFAULT_PATHS_FILE.write_text(f'LOCAL_PROJECT_DIR="{project_dir}"\n')


def prompt_project_dir(default_dir: str, auto_create: bool) -> Tuple[Path, bool, bool]:
    project_dir = default_dir
    while True:
        if project_dir:
            print(f"Current project directory: {project_dir}")
            new_path = input(
                "Press Enter to use this directory or enter a new path:\n"
            ).strip()
            if new_path:
                project_dir = new_path
        else:
            project_dir = input("Give path to local project dir:\n").strip()

        project_dir = os.path.expanduser(project_dir)
        if not project_dir:
            print("Please provide a valid directory path.")
            continue

        path = Path(project_dir)
        if path.exists():
            if not path.is_dir():
                print(f"Path exists but is not a directory: {path}")
                continue
            if not os.access(path, os.W_OK):
                print(f"Warning: No write permissions in directory {path}")
                response = (
                    input("Do you want to continue anyway? (y/n): ").strip().lower()
                )
                if response != "y":
                    continue
            is_empty = not any(path.iterdir())
            return path, False, is_empty

        print(f"Directory does not exist: {path}")
        if auto_create:
            response = "y"
        else:
            response = input("Create it? (y/n): ").strip().lower()
        if response == "y":
            path.mkdir(parents=True, exist_ok=True)
            return path, True, True


def display_welcome() -> None:
    print("Welcome to the TI-Toolbox from the Center for Sleep and Consciousness")
    print("")
    print("#####################################################################")
    print("")


def get_host_timezone() -> str:
    try:
        return capture(["date", "+%Z"])
    except Exception:
        return "UTC"


def check_docker_available() -> None:
    if not shutil_which("docker"):
        print("Error: Docker is not installed or not in PATH.")
        sys.exit(1)
    try:
        run(["docker", "info"], capture_output=True)
    except subprocess.CalledProcessError:
        print("Error: Docker daemon is not running. Please start Docker and try again.")
        sys.exit(1)
    try:
        run(["docker", "compose", "version"], capture_output=True)
    except subprocess.CalledProcessError:
        print("Error: Docker Compose (v2) is not available.")
        sys.exit(1)


def find_xhost() -> Optional[str]:
    for candidate in ("xhost", "/opt/X11/bin/xhost"):
        if shutil_which(candidate):
            return candidate
    return None


def check_x_forwarding() -> Optional[str]:
    system = platform.system()
    if system == "Linux":
        os.environ.setdefault("DISPLAY", ":0")
        return find_xhost()
    if system == "Darwin":
        xquartz_app = Path("/Applications/Utilities/XQuartz.app")
        if not xquartz_app.exists():
            print("Error: XQuartz is not installed. Please install XQuartz.")
            sys.exit(1)
        return find_xhost()
    if system == "Windows":
        print(
            "Windows detected. Please ensure your X server (VcXsrv/Xming) is running with:"
        )
        print("  - 'Multiple windows' mode")
        print("  - 'Disable access control' checked")
        print("  - Firewall configured to allow X server connections")
        print("")
        input("Press Enter to continue once X server is configured...")
        return None
    print("Unsupported OS for X11 display configuration.")
    sys.exit(1)


def set_display_env() -> None:
    system = platform.system()
    if system == "Linux":
        os.environ.setdefault("DISPLAY", ":0")
    elif system in ("Darwin", "Windows"):
        os.environ["DISPLAY"] = "host.docker.internal:0"
    else:
        print("Unsupported OS for X11 display configuration.")
        sys.exit(1)


def allow_xhost(xhost_bin: Optional[str]) -> None:
    if not xhost_bin:
        return
    system = platform.system()
    if system == "Linux":
        run([xhost_bin, "+local:root"], check=False, capture_output=True)
        run([xhost_bin, "+local:docker"], check=False, capture_output=True)
    elif system in ("Darwin", "Windows"):
        env = os.environ.copy()
        env["DISPLAY"] = ":0"
        run([xhost_bin, "+localhost"], check=False, env=env, capture_output=True)
        run([xhost_bin, platform.node()], check=False, env=env, capture_output=True)


def revert_xhost(xhost_bin: Optional[str]) -> None:
    if not xhost_bin:
        return
    system = platform.system()
    if system in ("Linux", "Darwin"):
        run([xhost_bin, "-local:root"], check=False, capture_output=True)
        run([xhost_bin, "-local:docker"], check=False, capture_output=True)


def ensure_docker_volume(volume_name: str) -> None:
    result = subprocess.run(
        ["docker", "volume", "inspect", volume_name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        run(["docker", "volume", "create", volume_name], check=False)


def get_compose_images() -> list[str]:
    if not DOCKER_COMPOSE_FILE.exists():
        return []
    images: list[str] = []
    for line in DOCKER_COMPOSE_FILE.read_text().splitlines():
        match = re.match(r"^\s*image:\s*(\S+)\s*$", line)
        if match:
            images.append(match.group(1))
    return images


def ensure_images_pulled(env: dict[str, str]) -> None:
    images = get_compose_images()
    if not images:
        return

    try:
        existing = set(
            capture(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]
            ).splitlines()
        )
    except Exception:
        existing = set()

    missing = [image for image in images if image not in existing]
    if not missing:
        return

    print("Pulling required Docker images...")
    # Show progress like docker does
    subprocess.run(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "pull"], env=env
    )


def run_project_init_in_container(container_name: str, project_dir_name: str) -> None:
    container_project_dir = f"/mnt/{project_dir_name}"

    local_manager = SCRIPT_DIR / "tit" / "project_init" / "example_data_manager.py"
    if local_manager.exists():
        subprocess.run(
            [
                "docker",
                "cp",
                str(local_manager),
                f"{container_name}:/ti-toolbox/tit/project_init/example_data_manager.py",
            ],
            check=False,
        )

    # Run project init + optional example-data setup entirely in container python.
    # The snippet always exits 0 to avoid treating "no-op" as failure.
    cmd = [
        "docker",
        "exec",
        "-e",
        f"PROJECT_DIR={container_project_dir}",
        container_name,
        "bash",
        "-lc",
        "PYTHONPATH=/ti-toolbox simnibs_python - <<'PY'\n"
        "import os\n"
        "from pathlib import Path\n"
        "\n"
        "def main() -> int:\n"
        "    try:\n"
        "        from tit.project_init import is_new_project, initialize_project_structure, setup_example_data\n"
        "    except Exception as exc:\n"
        '        print(f"  ⚠ Could not import tit.project_init in container: {exc}")\n'
        "        return 0\n"
        "\n"
        "    project_dir = Path(os.environ['PROJECT_DIR'])\n"
        "    toolbox_root = Path('/ti-toolbox')\n"
        "\n"
        "    try:\n"
        "        if is_new_project(project_dir):\n"
        "            initialize_project_structure(project_dir)\n"
        "\n"
        "        # Returns False when it is a no-op; that's not an error.\n"
        "        setup_example_data(toolbox_root, project_dir)\n"
        "    except Exception as exc:\n"
        '        print(f"  ⚠ Project initialization failed: {exc}")\n'
        "\n"
        "    return 0\n"
        "\n"
        "raise SystemExit(main())\n"
        "PY",
    ]
    subprocess.run(cmd, check=False)


def run_docker_compose(project_dir: Path, project_dir_name: str) -> None:
    ensure_docker_volume("ti-toolbox_freesurfer_data")

    env = os.environ.copy()
    env["LOCAL_PROJECT_DIR"] = str(project_dir)
    env["PROJECT_DIR_NAME"] = project_dir_name
    env["TZ"] = get_host_timezone()
    env["HOME"] = env.get("HOME") or env.get("USERPROFILE", "")
    ensure_images_pulled(env)

    print("Starting services...")
    run(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "up", "--build", "-d"],
        env=env,
        check=False,
        capture_output=True,
    )

    print("Waiting for services to initialize...")
    time.sleep(3)

    if (
        subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.find("simnibs_container")
        == -1
    ):
        print(
            "Error: simnibs service is not running. Please check your docker-compose.yml and container logs."
        )
        run(
            ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "logs"],
            env=env,
            check=False,
        )
        sys.exit(1)

    print("Initializing project (inside container)...")
    run_project_init_in_container("simnibs_container", project_dir_name)

    print("Attaching to the simnibs_container...")
    if sys.stdin.isatty():
        subprocess.run(["docker", "exec", "-ti", "simnibs_container", "bash"])
    else:
        subprocess.run(["docker", "exec", "-i", "simnibs_container", "bash"])
    run(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "down"],
        env=env,
        check=False,
    )


def shutil_which(cmd: str) -> Optional[str]:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        full = Path(path) / cmd
        if full.exists() and os.access(full, os.X_OK):
            return str(full)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TI-Toolbox CLI loader")
    parser.add_argument("--project-dir", help="Path to the local project directory")
    parser.add_argument(
        "--yes", action="store_true", help="Auto-create missing project directory"
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    return parser.parse_args()


def main() -> None:
    if not DOCKER_COMPOSE_FILE.exists():
        print(
            f"Error: docker-compose.yml not found in {SCRIPT_DIR}. Please make sure the file is present."
        )
        sys.exit(1)

    global VERBOSE
    args = parse_args()
    VERBOSE = args.verbose

    check_docker_available()
    xhost_bin = check_x_forwarding()
    display_welcome()

    default_dir = load_default_project_dir()
    if args.project_dir:
        project_dir = Path(os.path.expanduser(args.project_dir))
        if not project_dir.exists():
            if args.yes:
                project_dir.mkdir(parents=True, exist_ok=True)
            else:
                print(f"Directory does not exist: {project_dir}")
                sys.exit(1)
    else:
        project_dir, _created, _is_empty = prompt_project_dir(default_dir, args.yes)

    save_default_project_dir(str(project_dir))

    set_display_env()
    allow_xhost(xhost_bin)

    try:
        run_docker_compose(project_dir, project_dir.name)
    finally:
        revert_xhost(xhost_bin)


if __name__ == "__main__":
    main()
