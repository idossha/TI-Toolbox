"""Portable wrapper selection with authored subprocess fixtures (2026-09-10).

Run: python3 -m pytest tests/test_portable_dev_loader.py -q.
Records selected checkout, YAML and mount at process boundaries; no Docker runs.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("language", ["py", "sh"])
@pytest.mark.parametrize("relocated", [False, True])
def test_dev_wrapper_selects_checkout_and_adjacent_yaml(tmp_path, language, relocated):
    repo = tmp_path / "source checkout"
    (repo / "tit").mkdir(parents=True)
    (repo / "tit/__init__.py").touch()
    (repo / "tit/launch.py").touch()
    (repo / "tit/cli.py").write_text("""
import argparse, json, os
from types import SimpleNamespace
def launch_parser(**kwargs):
    p = argparse.ArgumentParser(**kwargs)
    p.set_defaults(status=False, logs=False, stop=False, no_open=True)
    return p
def prepare_launch(args, argv): return None
def launch_command(args, **kwargs):
    print(json.dumps({'repo': kwargs['repo_dir'], 'compose': os.environ.get('TIT_COMPOSE_FILE')}))
    return 0
""")
    (repo / "loader.sh").write_text(
        'printf \'%s\\n%s\\n\' "$TIT_DEV_REPO_DIR" "$TIT_COMPOSE_FILE"\n'
    )
    location = tmp_path / "launch files" if relocated else repo / "dev/loader"
    location.mkdir(parents=True)
    script = location / f"loader_dev.{language}"
    shutil.copyfile(ROOT / "dev/loader" / script.name, script)
    (location / "docker-compose.yml").write_text("services: {}\n")
    env = dict(os.environ)
    env.pop("TIT_COMPOSE_FILE", None)
    env.pop("TIT_DEV_REPO_DIR", None)
    if relocated:
        env["TIT_DEV_REPO_DIR"] = str(repo)
    result = subprocess.run(
        [sys.executable if language == "py" else "bash", str(script)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    if language == "py":
        actual = json.loads(result.stdout)
    else:
        selected_repo, compose = result.stdout.splitlines()
        actual = {"repo": selected_repo, "compose": compose}
    assert actual == {
        "repo": str(repo.resolve()),
        "compose": str((location / "docker-compose.yml").resolve()),
    }


@pytest.mark.parametrize("language", ["py", "sh"])
def test_explicit_invalid_checkout_does_not_fall_back(tmp_path, language):
    result = subprocess.run(
        [
            sys.executable if language == "py" else "bash",
            str(ROOT / f"dev/loader/loader_dev.{language}"),
            "--help",
        ],
        env=dict(os.environ, TIT_DEV_REPO_DIR=str(tmp_path / "missing")),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 2
    assert "not a TI-Toolbox checkout" in result.stderr
    assert str(tmp_path / "missing") in result.stderr
