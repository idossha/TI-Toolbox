"""The regular CLI helper starts the selected executable without Node-mode leakage.

The executable is a local recording fixture; these checks never launch Electron or Docker.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

HELPER = Path(__file__).resolve().parents[1] / "dev" / "launch-electron.sh"


def test_explicit_executable_receives_project_but_not_electron_node_mode(tmp_path):
    executable = tmp_path / "desktop app"
    executable.write_text(
        '#!/bin/bash\nprintf "%s|%s" "$TIT_LAUNCH_PROJECT_DIR" '
        '"${ELECTRON_RUN_AS_NODE:-unset}:${TIT_LAUNCH_CONTAINER_ID:-unset}:${ELECTRON_RENDERER_URL:-unset}"\n'
    )
    executable.chmod(0o755)
    result = subprocess.run(
        ["bash", str(HELPER)],
        env={
            **os.environ,
            "TIT_ELECTRON_EXECUTABLE": str(executable),
            "TIT_LAUNCH_PROJECT_DIR": str(tmp_path),
            "ELECTRON_RUN_AS_NODE": "1",
            "TIT_LAUNCH_CONTAINER_ID": "stale-session",
            "ELECTRON_RENDERER_URL": "http://127.0.0.1:9999",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{tmp_path}|unset:unset:unsetTI-Toolbox closed.\n"


def test_invalid_explicit_executable_fails_instead_of_falling_back(tmp_path):
    result = subprocess.run(
        ["bash", str(HELPER), "--check"],
        env={**os.environ, "TIT_ELECTRON_EXECUTABLE": str(tmp_path / "missing")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "must name an executable" in result.stderr


def test_source_runtime_receives_package_directory_for_compose_resolution(tmp_path):
    helper = tmp_path / "dev" / "launch-electron.sh"
    helper.parent.mkdir()
    helper.write_text(HELPER.read_text())
    runtime = tmp_path / "desktop" / "node_modules" / ".bin" / "electron"
    runtime.parent.mkdir(parents=True)
    runtime.write_text('#!/bin/bash\nprintf "%s" "$1"\n')
    runtime.chmod(0o755)
    main = tmp_path / "desktop" / "out" / "main" / "index.js"
    main.parent.mkdir(parents=True)
    main.touch()
    env = dict(os.environ)
    env.pop("TIT_ELECTRON_EXECUTABLE", None)
    result = subprocess.run(
        ["bash", str(helper)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(tmp_path / "desktop") + "TI-Toolbox closed.\n"


@pytest.mark.parametrize("entrypoint", ["helper", "bash", "standalone-bash", "python"])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_loaders_report_success_once_and_preserve_failure(
    tmp_path, entrypoint, exit_code
):
    """Fake app exits pin completion and failure status without Docker or a GUI."""
    root = HELPER.parent.parent
    executable = tmp_path / "fake-electron"
    executable.write_text(f"#!/bin/bash\nexit {exit_code}\n")
    executable.chmod(0o755)
    if entrypoint == "helper":
        command = ["bash", str(HELPER)]
    elif entrypoint == "python":
        command = [
            sys.executable,
            str(root / "loader.py"),
            "--desktop",
            "--project",
            str(tmp_path),
        ]
    else:
        loader = root / "loader.sh"
        if entrypoint == "standalone-bash":
            loader = tmp_path / "loader.sh"
            loader.write_text((root / "loader.sh").read_text())
        command = ["bash", str(loader), "--desktop", "--project", str(tmp_path)]
    result = subprocess.run(
        command,
        env={**os.environ, "TIT_ELECTRON_EXECUTABLE": str(executable)},
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode == exit_code, result.stderr
    assert result.stdout == ("TI-Toolbox closed.\n" if exit_code == 0 else "")


@pytest.mark.parametrize("loader", ["loader.py", "loader.sh"])
@pytest.mark.parametrize("other", ["--browser", "--no-open"])
def test_desktop_conflicts_with_browser_modes_before_launch(tmp_path, loader, other):
    root = HELPER.parent.parent
    command = [sys.executable if loader.endswith(".py") else "bash", str(root / loader)]
    result = subprocess.run(
        [*command, "--project", str(tmp_path), "--desktop", other],
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )
    assert result.returncode != 0
    assert "--desktop" in result.stderr
    assert other in result.stderr


def test_regular_python_launch_defaults_to_browser(tmp_path, monkeypatch):
    from tit import cli

    calls = []
    urls = []
    monkeypatch.setattr(
        cli,
        "start",
        lambda options: calls.append(options) or ("http://localhost:1234", "fixture"),
    )
    monkeypatch.setattr(cli, "open_in_browser", urls.append)
    args = cli.launch_parser().parse_args(["--project", str(tmp_path)])
    assert cli.launch_command(args) == 0
    assert calls[0].open_browser is True
    assert len(urls) == 1
    assert urls[0].startswith("http://localhost:1234")


def test_python_browser_no_open_remain_compatible(tmp_path):
    from tit import cli

    argv = ["--project", str(tmp_path), "--browser", "--no-open"]
    args = cli.launch_parser().parse_args(argv)
    assert cli.prepare_launch(args, argv) is None
