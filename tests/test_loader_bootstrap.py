"""Standalone bootstrap boundaries; no network, Docker, Node or science imports needed."""

import importlib.util
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("standalone_loader", ROOT / "loader.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


@pytest.fixture
def standalone(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "HERE", tmp_path / "download")
    cache = tmp_path / "isolated cache"
    monkeypatch.setenv("TIT_VENV_DIR", str(cache))
    return cache


def test_checkout_help_uses_checkout_even_with_unusable_cache(tmp_path):
    import os

    env = {**os.environ, "TIT_VENV_DIR": str(tmp_path / "never-created")}
    result = subprocess.run(
        [sys.executable, "-I", str(ROOT / "loader.py"), "--help"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--project" in result.stdout
    assert "refreshing launcher" not in result.stderr
    assert not (tmp_path / "never-created").exists()


def test_standalone_creates_isolated_environment_and_passes_argv_verbatim(standalone):
    args = ["--project", "/tmp/project with spaces;$(echo nope)", "--status"]
    with patch.object(
        loader.subprocess, "run", return_value=subprocess.CompletedProcess([], 7)
    ) as run:
        assert loader.main(args) == 7
    create, install, launch = run.call_args_list
    assert create.args[0] == [sys.executable, "-m", "venv", str(standalone)]
    assert "--no-deps" in install.args[0]
    assert "--force-reinstall" in install.args[0]
    assert (
        install.args[0][-1]
        == "https://github.com/idossha/TI-toolbox/archive/main.zip"
    )
    assert launch.args[0][1:] == ["-I", "-m", "tit.cli", "launch", *args]
    assert all(call.kwargs.get("shell") is not True for call in run.call_args_list)
    assert all(
        call.args[0][0].startswith(str(standalone)) for call in (install, launch)
    )


def test_standalone_refreshes_an_existing_cache_every_time(standalone):
    python = standalone / (
        "Scripts/python.exe" if loader.os.name == "nt" else "bin/python"
    )
    python.parent.mkdir(parents=True)
    python.touch()
    with patch.object(
        loader.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
    ) as run:
        assert loader.main(["--help"]) == 0
        assert loader.main(["--help"]) == 0
    assert len(run.call_args_list) == 4
    assert all("--force-reinstall" in call.args[0] for call in run.call_args_list[::2])


def test_network_failure_does_not_run_stale_installed_package(standalone, capsys):
    with patch.object(
        loader.subprocess,
        "run",
        side_effect=[
            subprocess.CompletedProcess([], 0),
            subprocess.CalledProcessError(1, ["pip"], stderr="network unavailable"),
        ],
    ) as run:
        assert loader.main(["--status"]) == 2
    assert run.call_count == 2
    error = capsys.readouterr().err
    assert "Check your network" in error
    assert "clone TI-Toolbox" in error
    assert "pip install tit" not in error


def test_environment_creation_failure_is_actionable(standalone, capsys):
    with patch.object(
        loader.subprocess, "run", side_effect=PermissionError("denied")
    ) as run:
        assert loader.main([]) == 2
    assert run.call_count == 1
    assert "cache-directory permissions" in capsys.readouterr().err


def test_refresh_timeout_is_actionable_and_does_not_launch(standalone, capsys):
    with patch.object(
        loader.subprocess,
        "run",
        side_effect=[
            subprocess.CompletedProcess([], 0),
            subprocess.TimeoutExpired("pip", 300),
        ],
    ) as run:
        assert loader.main([]) == 2
    assert run.call_count == 2
    assert "could not prepare the launcher" in capsys.readouterr().err


@pytest.mark.parametrize("operation", ["--stop", "--status", "--logs"])
def test_management_uses_working_cache_without_network(standalone, operation):
    python = standalone / (
        "Scripts/python.exe" if loader.os.name == "nt" else "bin/python"
    )
    python.parent.mkdir(parents=True)
    python.touch()

    def offline_run(argv, **kwargs):
        assert "pip" not in argv, "management must remain usable offline"
        return subprocess.CompletedProcess(argv, 0)

    with patch.object(loader.subprocess, "run", side_effect=offline_run) as run:
        assert loader.main([operation, "--project", "/tmp/existing project"]) == 0
    assert run.call_count == 2
    assert run.call_args_list[0].args[0][1:3] == ["-I", "-c"]
    assert run.call_args_list[1].args[0][1:] == [
        "-I",
        "-m",
        "tit.cli",
        "launch",
        operation,
        "--project",
        "/tmp/existing project",
    ]


def test_management_repairs_unusable_cache_before_launch(standalone):
    python = standalone / (
        "Scripts/python.exe" if loader.os.name == "nt" else "bin/python"
    )
    python.parent.mkdir(parents=True)
    python.touch()
    with patch.object(
        loader.subprocess,
        "run",
        side_effect=[
            subprocess.CompletedProcess([], 1),
            subprocess.CompletedProcess([], 0),
            subprocess.CompletedProcess([], 0),
        ],
    ) as run:
        assert loader.main(["--stop"]) == 0
    assert "pip" in run.call_args_list[1].args[0]
    assert "tit.cli" in run.call_args_list[2].args[0]


def test_standalone_uses_adjacent_yaml_even_from_another_directory(
    standalone, monkeypatch, tmp_path
):
    """A downloaded YAML must reach the installed launcher, not its built-in spec."""
    loader.HERE.mkdir()
    compose = loader.HERE / "docker-compose.yml"
    compose.write_text("services:\n  tit:\n    image: idossha/ti-toolbox:custom\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TIT_COMPOSE_FILE", raising=False)
    with patch.object(
        loader.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
    ) as run:
        assert loader.main([]) == 0
    assert run.call_args.kwargs["env"]["TIT_COMPOSE_FILE"] == str(compose.resolve())


def test_standalone_preserves_explicit_source_and_compose(standalone, monkeypatch):
    """Explicit source and YAML settings survive the isolated subprocess boundary."""
    monkeypatch.setenv("TIT_SOURCE_REF", "v3.0.0")
    monkeypatch.setenv("TIT_COMPOSE_FILE", "/custom/compose.yml")
    with patch.object(
        loader.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
    ) as run:
        assert loader.main([]) == 0
    assert (
        run.call_args_list[1].args[0][-1]
        == "https://github.com/idossha/TI-toolbox/archive/v3.0.0.zip"
    )
    assert run.call_args.kwargs["env"]["TIT_COMPOSE_FILE"] == "/custom/compose.yml"
