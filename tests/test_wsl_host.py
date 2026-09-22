"""WSL is a Windows host to the loaders (loader.sh and tit/launch.py, ``is_wsl``).

There the Linux AppImage cannot run and no Linux browser exists, so both loaders skip the
desktop download, print the session URL, and open it on the Windows side. Detection is by
the variables WSL sets in every process, so a plain Linux run can stand in for WSL, and a
Docker Desktop container (whose kernel string also says "microsoft") is never mistaken for
it.

Run: python3 -m pytest tests/test_wsl_host.py -q.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest

from tit import launch
from tit.cli import desktop_asset_name, no_desktop_reason

ROOT = Path(__file__).resolve().parents[1]
WSL_REASON = "runs from Windows, not WSL"

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="WSL is a Linux platform"
)


def wsl_environment(tmp_path, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("TIT_", "WSL_"))}
    env["WSL_DISTRO_NAME"] = "Ubuntu-24.04"
    env["TIT_DATA_DIR"] = str(tmp_path / "data")
    env["TIT_RELEASE_BASE_URL"] = f"file://{tmp_path}/missing"
    env.update(extra)
    return env


def run_loaders(tmp_path, arguments, env):
    common = ["--project", str(tmp_path), *arguments]
    return tuple(
        subprocess.run(
            command + common, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL
        )
        for command in (
            ["bash", str(ROOT / "loader.sh")],
            [sys.executable, str(ROOT / "loader.py")],
        )
    )


def test_detection_uses_wsl_variables_not_the_kernel_string(monkeypatch, tmp_path):
    for name in ("WSL_DISTRO_NAME", "WSL_INTEROP"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(launch.Path, "is_dir", lambda self: False)
    assert not launch.is_wsl()
    assert desktop_asset_name("3.0.0").endswith(".AppImage")
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert launch.is_wsl()
    assert desktop_asset_name("3.0.0") == ""
    assert WSL_REASON in no_desktop_reason()


def test_both_loaders_skip_the_desktop_download_on_wsl(tmp_path):
    env = wsl_environment(tmp_path)
    bash, python = run_loaders(tmp_path, ["--print-config"], env)
    assert bash.returncode == 0 and python.returncode == 0, (bash.stderr, python.stderr)
    assert bash.stdout == python.stdout, (bash.stdout, python.stdout)
    assert "desktop_executable \n" in bash.stdout or bash.stdout.endswith("desktop_executable\n")
    bash, python = run_loaders(tmp_path, ["--desktop"], env)
    for result in (bash, python):
        assert result.returncode != 0
        assert WSL_REASON in result.stderr, result.stderr
    assert not (tmp_path / "data").exists()


def test_bash_loader_prints_the_url_and_opens_it_on_windows(tmp_path):
    """A stub Docker with a healthy container plays the whole start; a stub ``wslview`` and
    ``xdg-open`` show which side the URL went to."""
    stub = tmp_path / "bin"
    stub.mkdir()
    log = tmp_path / "opened.log"
    (stub / "docker").write_text(
        "#!/bin/sh\n"
        "# No containers exist (ps prints nothing); the GPU probe fails; compose creates one.\n"
        "case \"$1 $2\" in\n"
        "  'run --detach') exit 1 ;;\n"
        "  'inspect --format') echo exited:1 ;;\n"
        "  'compose version'|'compose --project-name') case \"$*\" in *' config '*) ;; *' run '*) echo stub-id ;; esac ;;\n"
        "esac\n"
        "exit 0\n"
    )
    (stub / "curl").write_text("#!/bin/sh\nexit 0\n")
    (stub / "wslview").write_text(f"#!/bin/sh\nprintf 'wslview %s\\n' \"$1\" >> '{log}'\n")
    (stub / "xdg-open").write_text(f"#!/bin/sh\nprintf 'xdg-open %s\\n' \"$1\" >> '{log}'\n")
    for name in ("docker", "curl", "wslview", "xdg-open"):
        (stub / name).chmod(0o755)
    env = wsl_environment(
        tmp_path,
        PATH=f"{stub}:{os.environ['PATH']}",
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        TIT_COMPOSE_FILE=str(ROOT / "docker-compose.yml"),
    )
    result = subprocess.run(
        ["bash", str(ROOT / "loader.sh"), "--project", str(tmp_path), "--browser"],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    urls = [line.strip() for line in result.stdout.splitlines() if "/auth/session?token=" in line]
    assert len(urls) == 1, result.stdout
    assert "opened your browser" in result.stdout
    assert log.read_text() == f"wslview {urls[0]}\n"


def test_python_opener_reports_honestly(monkeypatch):
    monkeypatch.setattr(launch, "is_wsl", lambda: True)
    monkeypatch.setattr(launch.shutil, "which", lambda name: None)
    lines = []
    launch.open_in_browser("http://127.0.0.1:1/auth/session?token=t", echo=lines.append)
    assert lines == ["could not open a browser automatically; paste the URL above into one"]

    monkeypatch.setattr(launch.shutil, "which", lambda name: "/bin/true" if name == "wslview" else None)
    lines.clear()
    launch.open_in_browser("http://127.0.0.1:1/auth/session?token=t", echo=lines.append)
    assert lines == ["opened your browser"]


def test_python_opener_falls_back_to_windows_shells(monkeypatch):
    """Without wslu, PowerShell (then cmd.exe) opens the URL; a failing opener is not success."""
    monkeypatch.setattr(launch, "is_wsl", lambda: True)
    monkeypatch.setattr(
        launch.shutil, "which",
        lambda name: {"powershell.exe": "/bin/false", "cmd.exe": "/bin/true"}.get(name),
    )
    commands = launch.windows_openers("http://127.0.0.1:1/auth/session?token=t")
    assert [c[0] for c in commands] == ["/bin/false", "/bin/true"]
    assert commands[0][-1] == "Start-Process -FilePath 'http://127.0.0.1:1/auth/session?token=t'"
    assert commands[1] == ["/bin/true", "/c", "start", "", "http://127.0.0.1:1/auth/session?token=t"]
    lines = []
    launch.open_in_browser("http://127.0.0.1:1/auth/session?token=t", echo=lines.append)
    assert lines == ["opened your browser"]
    # Only URL characters may reach a Windows shell; anything else is printed, never passed on.
    assert launch.windows_openers("http://127.0.0.1:1/x?token=a'b") == []


def test_bash_checkout_shortcuts_refuse_before_asking_for_a_project(tmp_path):
    """On WSL the browser is the default, which must not make --build demand a project first."""
    env = wsl_environment(tmp_path)
    for flag in ("--build", "--web"):
        result = subprocess.run(
            ["bash", str(ROOT / "loader.sh"), flag], capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL
        )
        assert result.returncode != 0
        assert "--build and --web need --dev" in result.stderr, result.stderr
