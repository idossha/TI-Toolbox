"""The loaders bootstrap the desktop app (docs/dev/DECISIONS.md, 2026-09-15).

Offline throughout: the "release" is a directory served to ``curl``/``urllib`` over
``file://`` through ``TIT_RELEASE_BASE_URL``, and ``TIT_DATA_DIR`` redirects the managed
install root. Every case is asserted for ``loader.sh`` and ``loader.py`` together, so the
two ``resolve_desktop_executable`` implementations cannot drift.

Run: python3 -m pytest tests/test_desktop_bootstrap.py -q.
"""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import tit
from tit.cli import desktop_asset_name, managed_executable

ROOT = Path(__file__).resolve().parents[1]
VERSION = tit.__version__
LAUNCHED = "LAUNCHED-THE-DESKTOP-APP"
APP_SCRIPT = f'#!/bin/sh\nprintf "{LAUNCHED} %s\\n" "$TIT_LAUNCH_PROJECT_DIR"\n'

pytestmark = pytest.mark.skipif(
    not desktop_asset_name(VERSION),
    reason="no managed desktop build for this platform",
)


def build_release(tmp_path, *, valid_checksum=True, list_asset=True):
    """A fake GitHub release directory with the real asset and checksum names."""
    asset = desktop_asset_name(VERSION)
    payload = tmp_path / "payload"
    executable = managed_executable(payload)
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text(APP_SCRIPT)
    executable.chmod(0o755)
    release = tmp_path / "release" / f"v{VERSION}"
    release.mkdir(parents=True)
    if asset.endswith(".zip"):
        shutil.make_archive(str(release / asset)[:-4], "zip", root_dir=str(payload))
    else:
        shutil.copy(executable, release / asset)
    digest = hashlib.sha256((release / asset).read_bytes()).hexdigest()
    recorded = digest if valid_checksum else "0" * 64
    (release / "SHA256SUMS").write_text(
        f"{recorded}  {asset if list_asset else 'other-file'}\n", encoding="utf-8"
    )
    return tmp_path / "release"


def environment(tmp_path, **extra):
    env = dict(os.environ)
    env.pop("TIT_ELECTRON_EXECUTABLE", None)
    env.pop("TIT_DEV", None)
    env.pop("TIT_DEV_REPO_DIR", None)
    env["TIT_DATA_DIR"] = str(tmp_path / "data")
    env.update(extra)
    return env


def run_loaders(tmp_path, arguments, env, project=None):
    """The same invocation through both front doors; returns (bash, python) results."""
    project = str(project or tmp_path)
    common = ["--project", project, *arguments]
    return (
        subprocess.run(
            ["bash", str(ROOT / "loader.sh"), *common],
            capture_output=True,
            text=True,
            env=env,
            stdin=subprocess.DEVNULL,
        ),
        subprocess.run(
            [sys.executable, str(ROOT / "loader.py"), *common],
            capture_output=True,
            text=True,
            env=env,
            stdin=subprocess.DEVNULL,
        ),
    )


def resolved(result):
    for line in result.stdout.splitlines():
        if line.startswith("desktop_executable"):
            return line.split(" ", 1)[1].strip()
    raise AssertionError(f"no desktop_executable line in:\n{result.stdout}")


def test_managed_install_is_used_without_downloading(tmp_path):
    install = tmp_path / "data" / "app" / VERSION
    executable = managed_executable(install)
    executable.parent.mkdir(parents=True)
    executable.write_text(APP_SCRIPT)
    executable.chmod(0o755)
    env = environment(tmp_path, TIT_RELEASE_BASE_URL="file:///nonexistent")
    bash, python = run_loaders(tmp_path, ["--print-config"], env)
    assert bash.stdout == python.stdout, (bash.stdout, python.stdout)
    assert resolved(bash) == str(executable)

    bash, python = run_loaders(tmp_path, ["--desktop"], env)
    for result in (bash, python):
        assert result.returncode == 0, result.stderr
        assert LAUNCHED in result.stdout


def test_absent_install_is_downloaded_verified_and_reused(tmp_path):
    release = build_release(tmp_path)
    env = environment(tmp_path, TIT_RELEASE_BASE_URL=f"file://{release}")
    bash, python = run_loaders(tmp_path, ["--print-config"], env)
    assert bash.stdout == python.stdout
    assert resolved(bash) == "download"

    bash, _ = run_loaders(tmp_path, ["--desktop"], env)
    assert bash.returncode == 0, bash.stderr
    assert LAUNCHED in bash.stdout
    installed = managed_executable(tmp_path / "data" / "app" / VERSION)
    assert installed.is_file() and os.access(installed, os.X_OK)

    # The install is now the resolution, for both loaders, with no network at all.
    offline = environment(tmp_path, TIT_RELEASE_BASE_URL="file:///nonexistent")
    bash, python = run_loaders(tmp_path, ["--print-config"], offline)
    assert bash.stdout == python.stdout
    assert resolved(bash) == str(installed)


def test_python_loader_downloads_and_prunes_older_installs(tmp_path):
    release = build_release(tmp_path)
    stale = tmp_path / "data" / "app" / "0.0.1"
    stale.mkdir(parents=True)
    (stale / "marker").write_text("old")
    env = environment(tmp_path, TIT_RELEASE_BASE_URL=f"file://{release}")
    _, python = run_loaders(tmp_path, ["--desktop"], env)
    assert python.returncode == 0, python.stderr
    assert LAUNCHED in python.stdout
    assert managed_executable(tmp_path / "data" / "app" / VERSION).is_file()
    assert not stale.exists()


def test_download_failure_falls_back_to_the_browser_with_one_line(tmp_path):
    # A Docker that refuses stops the run right after the fallback decision is printed,
    # so the notice is asserted without starting a container.
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "docker").write_text("#!/bin/sh\nexit 1\n")
    (stub / "docker").chmod(0o755)
    env = environment(
        tmp_path,
        TIT_RELEASE_BASE_URL=f"file://{tmp_path}/missing",
        PATH=f"{stub}:{os.environ['PATH']}",
    )
    bash, python = run_loaders(tmp_path, ["--print-config"], env)
    assert bash.stdout == python.stdout
    assert resolved(bash) == "download"
    bash, python = run_loaders(tmp_path, [], env)
    for result in (bash, python):
        assert "opening the browser instead" in result.stderr, result.stderr
    assert not (tmp_path / "data" / "app" / VERSION).exists()


def test_explicit_desktop_errors_instead_of_falling_back(tmp_path):
    env = environment(tmp_path, TIT_RELEASE_BASE_URL=f"file://{tmp_path}/missing")
    bash, python = run_loaders(tmp_path, ["--desktop"], env)
    for result in (bash, python):
        assert result.returncode != 0
        assert "opening the browser instead" not in result.stderr
        assert "SHA256SUMS" in result.stderr or "download" in result.stderr.lower()
    assert not (tmp_path / "data" / "app" / VERSION).exists()


def test_checksum_mismatch_installs_nothing(tmp_path):
    release = build_release(tmp_path, valid_checksum=False)
    env = environment(tmp_path, TIT_RELEASE_BASE_URL=f"file://{release}")
    bash, python = run_loaders(tmp_path, ["--desktop"], env)
    for result in (bash, python):
        assert result.returncode != 0
        assert "checksum mismatch" in result.stderr
        assert LAUNCHED not in result.stdout
    assert not (tmp_path / "data" / "app" / VERSION).exists()


def test_unlisted_asset_is_never_installed(tmp_path):
    release = build_release(tmp_path, list_asset=False)
    env = environment(tmp_path, TIT_RELEASE_BASE_URL=f"file://{release}")
    bash, python = run_loaders(tmp_path, ["--desktop"], env)
    for result in (bash, python):
        assert result.returncode != 0
        assert "SHA256SUMS" in result.stderr
    assert not (tmp_path / "data" / "app" / VERSION).exists()


@pytest.mark.parametrize("flag", ["--browser", "--no-open"])
def test_browser_flags_skip_the_download(tmp_path, flag):
    release = build_release(tmp_path)
    env = environment(tmp_path, TIT_RELEASE_BASE_URL=f"file://{release}")
    bash, python = run_loaders(tmp_path, ["--print-config", flag], env)
    assert bash.stdout == python.stdout
    assert "ui        browser" in bash.stdout
    assert resolved(bash) == ""
    assert not (tmp_path / "data" / "app").exists()


def test_environment_override_wins_over_a_managed_install(tmp_path):
    override = tmp_path / "custom-app"
    override.write_text(APP_SCRIPT)
    override.chmod(0o755)
    install = managed_executable(tmp_path / "data" / "app" / VERSION)
    install.parent.mkdir(parents=True)
    install.write_text(APP_SCRIPT)
    install.chmod(0o755)
    env = environment(tmp_path, TIT_ELECTRON_EXECUTABLE=str(override))
    bash, python = run_loaders(tmp_path, ["--print-config"], env)
    assert bash.stdout == python.stdout
    assert resolved(bash) == str(override)


def test_dev_checkout_keeps_the_electron_helper(tmp_path):
    """``--dev`` never downloads: developers run Electron from desktop/node_modules."""
    env = environment(tmp_path, TIT_RELEASE_BASE_URL="file:///nonexistent")
    bash, python = run_loaders(
        tmp_path, ["--print-config", "--dev", str(ROOT)], env
    )
    assert bash.stdout == python.stdout
    assert resolved(bash) == ""
