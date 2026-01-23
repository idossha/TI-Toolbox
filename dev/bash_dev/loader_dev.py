#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PATHS_FILE = SCRIPT_DIR / ".default_paths.dev"
DOCKER_COMPOSE_FILE = SCRIPT_DIR / "docker-compose.dev.yml"
TOOLBOX_ROOT = (SCRIPT_DIR / ".." / "..").resolve()
STATUS_RELATIVE_PATH = Path("code/ti-toolbox/config/project_status.json")
SYSTEM_INFO_RELATIVE_DIR = Path("derivatives/ti-toolbox/.ti-toolbox-info")


def run(
    cmd: list[str],
    *,
    check: bool = True,
    env: Optional[dict[str, str]] = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=check,
        env=env,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
        text=True,
    )


def capture(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def load_default_paths() -> tuple[str, str]:
    if not DEFAULT_PATHS_FILE.exists():
        return "", ""
    content = DEFAULT_PATHS_FILE.read_text(errors="ignore")
    local_match = re.search(r'LOCAL_PROJECT_DIR="([^"]*)"', content)
    dev_match = re.search(r'DEV_CODEBASE_DIR="([^"]*)"', content)
    return (
        local_match.group(1) if local_match else "",
        dev_match.group(1) if dev_match else "",
    )


def save_default_paths(project_dir: str, dev_codebase_dir: str) -> None:
    DEFAULT_PATHS_FILE.write_text(
        f'LOCAL_PROJECT_DIR="{project_dir}"\nDEV_CODEBASE_DIR="{dev_codebase_dir}"\n'
    )


def prompt_dir(label: str, prompt: str, current: str) -> Path:
    while True:
        if current:
            print(f"Current {label}: {current}")
            new_val = input("Press Enter to use this directory or enter a new path:\n").strip()
            if new_val:
                current = new_val
        else:
            current = input(f"{prompt}\n").strip()

        current = os.path.expanduser(current)
        if not current:
            print("Please provide a valid directory path.")
            continue
        path = Path(current)
        if path.is_dir():
            return path
        print("Invalid directory. Please provide a valid path.")


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


def check_xquartz_version() -> None:
    xquartz_app = Path("/Applications/Utilities/XQuartz.app")
    if not xquartz_app.exists():
        return
    try:
        version = capture(["mdls", "-name", "kMDItemVersion", str(xquartz_app)])
        version = version.split('"')[-2] if '"' in version else version
    except Exception:
        return
    if version and version > "2.8.0":
        print("Warning: XQuartz version is above 2.8.0. Consider 2.7.7 for compatibility.")


def allow_network_clients() -> None:
    run(["defaults", "write", "org.macosforge.xquartz.X11", "nolisten_tcp", "-bool", "false"], check=False)
    if not is_process_running("XQuartz"):
        print("WARNING: XQuartz is NOT running. Start XQuartz if you need GUI support.")


def set_display_env() -> None:
    system = platform.system()
    if system == "Linux":
        os.environ.setdefault("DISPLAY", os.environ.get("DISPLAY", ""))
    else:
        os.environ["DISPLAY"] = "host.docker.internal:0"


def set_macos_opengl_env(env: dict[str, str]) -> None:
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    env["LIBGL_ALWAYS_INDIRECT"] = "1"
    env["QT_X11_NO_MITSHM"] = "1"
    env["QT_OPENGL"] = "desktop"
    env["TI_GUI_QGL_FALLBACK"] = "1"


def initialize_volumes() -> None:
    for volume in ("ti-toolbox_fsl_data", "ti-toolbox_freesurfer_data"):
        result = subprocess.run(
            ["docker", "volume", "inspect", volume],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            run(["docker", "volume", "create", volume], check=False)


def write_system_info(project_dir: Path) -> None:
    info_dir = project_dir / SYSTEM_INFO_RELATIVE_DIR
    info_dir.mkdir(parents=True, exist_ok=True)
    info_file = info_dir / "system_info.txt"
    lines = [
        "# TI-Toolbox System Info",
        f"Date: {time.ctime()}",
        f"User: {os.getenv('USER', '')}",
        f"Host: {platform.node()}",
        f"OS: {platform.platform()}",
        "",
        "## DISPLAY",
        os.environ.get("DISPLAY", ""),
        "",
    ]
    try:
        docker_version = capture(["docker", "--version"])
        lines += ["## Docker Version", docker_version, ""]
    except Exception:
        lines += ["## Docker Version", "Docker not found", ""]
    info_file.write_text("\n".join(lines))


def read_toolbox_version() -> str:
    version_file = TOOLBOX_ROOT / "version.py"
    if not version_file.exists():
        return "unknown"
    match = re.search(r'__version__\s*=\s*"([^"]+)"', version_file.read_text())
    return match.group(1) if match else "unknown"


def project_status_path(project_dir: Path) -> Path:
    return project_dir / STATUS_RELATIVE_PATH


def update_project_status(project_dir: Path) -> None:
    status_file = project_status_path(project_dir)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    payload = {
        "project_created": now,
        "last_updated": now,
        "config_created": True,
        "example_data_copied": False,
        "user_preferences": {"show_welcome": True},
        "project_metadata": {
            "name": project_dir.name,
            "path": str(project_dir),
            "version": read_toolbox_version(),
        },
    }
    if status_file.exists():
        try:
            existing = json.loads(status_file.read_text())
            payload.update(existing)
        except Exception:
            pass
        payload["last_updated"] = now
    status_file.write_text(json.dumps(payload, indent=2))


def initialize_project_structure(project_dir: Path) -> bool:
    try:
        from tit.project_init import initializer
    except Exception:
        return False
    if initializer.is_new_project(project_dir):
        initializer.initialize_project_structure(project_dir)
        try:
            initializer.setup_example_data(str(TOOLBOX_ROOT), project_dir)
        except Exception:
            pass
        return True
    return False


def ensure_images_pulled(env: dict[str, str]) -> None:
    images: list[str] = []
    for line in DOCKER_COMPOSE_FILE.read_text().splitlines():
        match = re.match(r"^\s*image:\s*(\S+)\s*$", line)
        if match:
            images.append(match.group(1))
    if not images:
        return
    try:
        existing = set(
            capture(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]).splitlines()
        )
    except Exception:
        existing = set()
    missing = [image for image in images if image not in existing]
    if not missing:
        return
    print("Pulling required Docker images...")
    subprocess.run(["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "pull"], env=env)


def run_docker_compose(env: dict[str, str], dev_codebase_dir: Path) -> None:
    print("Starting services...")
    subprocess.run(["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "up", "-d"], env=env)

    print("Waiting for services to initialize...")
    time.sleep(3)

    print("Copying development codebase to container...")
    if dev_codebase_dir.is_dir():
        subprocess.run(
            ["docker", "cp", f"{dev_codebase_dir}/.", "simnibs_container:/ti-toolbox/"],
            check=False,
        )
        print("✓ Development codebase copied to container")
    else:
        print(f"Warning: Development codebase directory {dev_codebase_dir} not found")

    print("Attaching to the simnibs_container...")
    if sys.stdin.isatty():
        subprocess.run(["docker", "exec", "-ti", "simnibs_container", "bash"])
    else:
        subprocess.run(["docker", "exec", "-i", "simnibs_container", "bash"])

    subprocess.run(["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "down"])


def display_welcome() -> None:
    print("Welcome to the TI toolbox from the Center for Sleep and Consciousness")
    print("Developed by Ido Haber as a wrapper around modified SimNIBS")
    print("")
    print("#####################################################################")
    print("")


def is_process_running(name: str) -> bool:
    try:
        output = capture(["ps", "aux"])
    except Exception:
        return False
    return name.lower() in output.lower()


def shutil_which(cmd: str) -> Optional[str]:
    for path in os.environ.get("PATH", "").split(os.pathsep):
        full = Path(path) / cmd
        if full.exists() and os.access(full, os.X_OK):
            return str(full)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TI-Toolbox dev loader (Python)")
    parser.add_argument("--project-dir", help="Path to the local project directory")
    parser.add_argument("--dev-codebase-dir", help="Path to the dev codebase directory")
    return parser.parse_args()


def main() -> None:
    if not DOCKER_COMPOSE_FILE.exists():
        print(f"Error: docker-compose.dev.yml not found in {SCRIPT_DIR}")
        sys.exit(1)

    args = parse_args()
    display_welcome()
    check_docker_available()
    initialize_volumes()

    default_project, default_dev = load_default_paths()
    project_dir = (
        Path(os.path.expanduser(args.project_dir)).resolve()
        if args.project_dir
        else prompt_dir("project directory", "Give path to local project dir:", default_project)
    )
    dev_codebase_dir = (
        Path(os.path.expanduser(args.dev_codebase_dir)).resolve()
        if args.dev_codebase_dir
        else prompt_dir(
            "development codebase directory",
            "Enter path to development codebase:",
            default_dev,
        )
    )

    if platform.system() == "Darwin":
        check_xquartz_version()
        allow_network_clients()

    set_display_env()

    save_default_paths(str(project_dir), str(dev_codebase_dir))

    is_new = initialize_project_structure(project_dir)
    if not is_new:
        update_project_status(project_dir)
    else:
        update_project_status(project_dir)

    write_system_info(project_dir)

    env = os.environ.copy()
    env["LOCAL_PROJECT_DIR"] = str(project_dir)
    env["PROJECT_DIR_NAME"] = project_dir.name
    env["DEV_CODEBASE_DIR"] = str(dev_codebase_dir)
    env["DEV_CODEBASE_DIR_NAME"] = dev_codebase_dir.name
    env["DEV_CODEBASE_NAME"] = dev_codebase_dir.name
    if platform.system() == "Darwin":
        set_macos_opengl_env(env)

    ensure_images_pulled(env)
    run_docker_compose(env, dev_codebase_dir)


if __name__ == "__main__":
    main()
