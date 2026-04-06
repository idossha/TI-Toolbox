#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

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
            new_val = input(
                "Press Enter to use this directory or enter a new path:\n"
            ).strip()
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


def allow_network_clients() -> None:
    run(
        [
            "defaults",
            "write",
            "org.macosforge.xquartz.X11",
            "nolisten_tcp",
            "-bool",
            "false",
        ],
        check=False,
    )
    if not is_process_running("XQuartz"):
        print("WARNING: XQuartz is NOT running. Start XQuartz if you need GUI support.")


def set_display_env() -> None:
    if platform.system() == "Linux":
        os.environ.setdefault("DISPLAY", ":0")
    else:
        os.environ["DISPLAY"] = "host.docker.internal:0"


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
    docker_version = capture(["docker", "--version"])
    lines += ["## Docker Version", docker_version, ""]
    info_file.write_text("\n".join(lines))


def read_toolbox_version() -> str:
    version_file = TOOLBOX_ROOT / "version.py"
    if not version_file.exists():
        return "unknown"
    match = re.search(r'__version__\s*=\s*"([^"]+)"', version_file.read_text())
    return match.group(1) if match else "unknown"


def update_project_status(project_dir: Path) -> None:
    status_file = project_dir / STATUS_RELATIVE_PATH
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


def initialize_project_structure(project_dir: Path) -> None:
    from tit.project_init import initializer

    initializer.initialize_project_structure(project_dir)
    initializer.setup_example_data(str(TOOLBOX_ROOT), project_dir)


def get_compose_images() -> list[str]:
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
    existing = set(
        capture(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]
        ).splitlines()
    )
    missing = [image for image in images if image not in existing]
    if not missing:
        return
    print("Pulling required Docker images...")
    subprocess.run(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "pull"], env=env
    )


def run_docker_compose(env: dict[str, str], dev_codebase_dir: Path) -> None:
    print("Starting services...")
    subprocess.run(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "up", "-d"], env=env
    )

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

    subprocess.run(
        ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), "down"], env=env
    )


def display_welcome() -> None:
    print("Welcome to the TI toolbox from the Center for Sleep and Consciousness")
    print("Developed by Ido Haber as a wrapper around modified SimNIBS")
    print("")
    print("#####################################################################")
    print("")


def _get_user_config_dir() -> str:
    """Return the host-side user config directory for TI-Toolbox.

    Mirrors the logic in ``tit.paths.PathManager.user_config_dir()`` and
    ``package/src/backend/env.js:getUserConfigDir()``.
    """
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / ".config"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    config_dir = base / "ti-toolbox"
    config_dir.mkdir(parents=True, exist_ok=True)
    return str(config_dir)


def is_process_running(name: str) -> bool:
    output = capture(["ps", "aux"])
    return name.lower() in output.lower()


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

    default_project, default_dev = load_default_paths()
    project_dir = (
        Path(os.path.expanduser(args.project_dir)).resolve()
        if args.project_dir
        else prompt_dir(
            "project directory", "Give path to local project dir:", default_project
        )
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
        allow_network_clients()

    set_display_env()

    save_default_paths(str(project_dir), str(dev_codebase_dir))

    initialize_project_structure(project_dir)
    update_project_status(project_dir)

    write_system_info(project_dir)

    env = os.environ.copy()
    env["LOCAL_PROJECT_DIR"] = str(project_dir)
    env["PROJECT_DIR_NAME"] = project_dir.name
    env["TZ"] = capture(["date", "+%Z"])
    env["DEV_CODEBASE_DIR"] = str(dev_codebase_dir)
    env["DEV_CODEBASE_NAME"] = dev_codebase_dir.name
    env["TIT_USER_CONFIG"] = _get_user_config_dir()
    env["TIT_HOST_OS"] = platform.system().lower()  # darwin, linux, windows
    env["TIT_HOST_OS_VERSION"] = platform.release()
    env["TIT_HOST_ARCH"] = platform.machine()  # x86_64, arm64
    ensure_images_pulled(env)
    run_docker_compose(env, dev_codebase_dir)


if __name__ == "__main__":
    main()
