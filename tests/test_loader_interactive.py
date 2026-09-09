"""Terminal setup regressions; all Docker/browser boundaries are stubbed.

Run: python -m pytest tests/test_loader_interactive.py -q
Authored inputs cover all front doors, invalid answers, defaults and cancellation.
"""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
from tit import cli

ROOT = Path(__file__).resolve().parents[1]


def load_script(path):
    spec = importlib.util.spec_from_file_location("interactive_loader", ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "script,dev", [("loader.py", False), ("dev/loader/loader_dev.py", True)]
)
def test_no_arguments_reach_launch_with_selected_settings(
    monkeypatch, tmp_path, script, dev
):
    answers = iter([str(tmp_path)])
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    calls = []
    monkeypatch.setattr(
        cli, "launch_command", lambda args, **kw: calls.append((args, kw)) or 0
    )
    assert load_script(script).main([]) == 0
    args, kwargs = calls[0]
    assert (args.project, args.image, args.port, args.no_open, args.timeout) == (
        str(tmp_path),
        None,
        8765,
        False,
        180,
    )
    if dev:
        assert kwargs["repo_dir"] == str(ROOT) and kwargs["server_reload"] is True


def test_invalid_path_retries_and_explicit_settings_survive(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    args = cli.launch_parser().parse_args(
        [
            "--interactive",
            "--project",
            str(tmp_path),
            "--port",
            "19999",
            "--image",
            "example/tool:pinned",
            "--no-open",
        ]
    )
    answers = iter(["/missing/project", ""])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert cli.prepare_launch(args, ["--interactive"]) is None
    assert (args.project, args.image, args.port, args.no_open, args.timeout) == (
        str(tmp_path),
        "example/tool:pinned",
        19999,
        True,
        180,
    )
    assert not args.resume_session


def test_remembers_project_for_enter_next_time(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("TIT_PROJECT_DIR", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    answers = iter([str(tmp_path), ""])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    for _ in range(2):
        args = cli.launch_parser().parse_args([])
        assert cli.prepare_launch(args, []) is None
        assert args.project == str(tmp_path)


@pytest.mark.parametrize("error,code", [(EOFError, 2), (KeyboardInterrupt, 130)])
def test_cancel_before_dispatch(monkeypatch, tmp_path, error, code):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    def cancel(_):
        raise error

    monkeypatch.setattr("builtins.input", cancel)
    assert cli.prepare_launch(cli.launch_parser().parse_args([]), []) == code


@pytest.mark.parametrize(
    "script",
    ["loader.py", "dev/loader/loader_dev.py", "loader.sh", "dev/loader/loader_dev.sh"],
)
def test_all_front_doors_without_terminal_fail_actionably(script):
    command = ["bash"] if script.endswith(".sh") else [sys.executable]
    result = subprocess.run(
        command + [str(ROOT / script)],
        input="",
        capture_output=True,
        text=True,
        env={**os.environ, "TIT_PYTHON": sys.executable},
        timeout=15,
    )
    assert result.returncode == 2
    assert "interactive setup needs a terminal" in result.stderr
    assert "Traceback" not in result.stderr


def test_explicit_arguments_do_not_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("unexpected prompt"))
    args = cli.launch_parser().parse_args(["--project", str(tmp_path)])
    assert cli.prepare_launch(args, ["--project", str(tmp_path)]) is None


def test_management_prompt_only_requests_project(monkeypatch, tmp_path):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    prompts = []
    monkeypatch.setattr(
        "builtins.input", lambda prompt: prompts.append(prompt) or str(tmp_path)
    )
    args = cli.launch_parser().parse_args(["--interactive", "--status"])
    assert cli.prepare_launch(args, ["--interactive", "--status"]) is None
    assert len(prompts) == 1 and args.project == str(tmp_path)


@pytest.mark.skipif(
    os.name == "nt",
    reason="PTY transport is POSIX; prompt logic is platform-independent",
)
@pytest.mark.parametrize(
    "script",
    ["loader.py", "dev/loader/loader_dev.py", "loader.sh", "dev/loader/loader_dev.sh"],
)
def test_real_terminal_opens_wizard_and_eof_cancels(script, tmp_path):
    import pty
    import select
    import time

    master, slave = pty.openpty()
    command = ["bash"] if script.endswith(".sh") else [sys.executable]
    process = subprocess.Popen(
        command + [str(ROOT / script)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={
            **os.environ,
            "TIT_PYTHON": sys.executable,
            "XDG_CONFIG_HOME": str(tmp_path),
        },
    )
    os.close(slave)
    output = b""
    try:
        deadline = time.monotonic() + 15
        while b"Project directory" not in output and time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                output += os.read(master, 8192)
        assert b"Project directory" in output, output
        os.write(master, b"\x04")
        assert process.wait(timeout=5) == 2
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)


@pytest.mark.parametrize(
    "explicit,env_tag,expected",
    [
        (None, "", "example/tool:existing"),
        ("example/tool:requested", "", "example/tool:requested"),
        (None, "pinned", None),
    ],
)
def test_reconnect_only_when_interactive_image_is_unspecified(
    monkeypatch, tmp_path, explicit, env_tag, expected
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("TIT_IMAGE_TAG", env_tag)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: str(tmp_path))
    args = cli.launch_parser().parse_args(
        ["--interactive", "--no-open"] + (["--image", explicit] if explicit else [])
    )
    assert cli.prepare_launch(args, ["--interactive", "--no-open"]) is None

    def status(_):
        assert not explicit and not env_tag
        return {"state": "running", "image": "example/tool:existing"}

    monkeypatch.setattr(cli, "launch_status", status)
    calls = []
    monkeypatch.setattr(
        cli,
        "start",
        lambda opts: calls.append(opts) or ("http://localhost:1234", "test-token"),
    )
    assert cli.launch_command(args) == 0
    assert calls[0].image == expected


def test_corrupt_remembered_path_still_prompts(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("TIT_PROJECT_DIR", raising=False)
    (cli.user_config_dir() / "last-project.txt").write_bytes(b"\xff")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: str(tmp_path))
    args = cli.launch_parser().parse_args([])
    assert cli.prepare_launch(args, []) is None
    assert args.project == str(tmp_path)
