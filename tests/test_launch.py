"""Unit tests for ``tit launch`` (:mod:`tit.launch`, :mod:`tit.cli`).

Nothing here talks to Docker: every test asserts a *pure* function — the compose
parser, the interpolator, the project hash, the argv builder, the CLI parser.
The live check that the argv these produce actually starts a container is a
manual step recorded in ``docs/installation/bash-cli.md``; what is guarded here
is that the spec cannot drift.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tit import launch
from tit.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = REPO_ROOT / "docker-compose.yml"

# One host directory, used everywhere below so the expected container name is stable.
PROJECT = "/Users/you/datasets/000"


# ---------------------------------------------------------------------------------------
# The run spec has exactly one source of truth
# ---------------------------------------------------------------------------------------


@pytest.mark.skipif(
    not COMPOSE.is_file(), reason="compose file only exists in a checkout"
)
def test_builtin_spec_matches_compose():
    """The wheel's fallback spec must equal what the compose file actually says.

    An installed ``tit`` has no repository above it, so :data:`launch.BUILTIN_SPEC`
    stands in for the file.  If someone edits the compose file, this fails — which
    is the whole point: the two must not describe different containers.
    """
    assert (
        launch.parse_compose(COMPOSE.read_text(encoding="utf-8")) == launch.BUILTIN_SPEC
    )


@pytest.mark.skipif(
    not COMPOSE.is_file(), reason="compose file only exists in a checkout"
)
def test_load_spec_prefers_the_checkout():
    assert launch.load_spec() == launch.parse_compose(
        COMPOSE.read_text(encoding="utf-8")
    )


def test_parse_compose_rejects_a_file_without_the_service():
    with pytest.raises(launch.LaunchError, match="services.tit"):
        launch.parse_compose("services:\n  other:\n    image: x\n")


# ---------------------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "env", "expected"),
    [
        ("${A}", {"A": "x"}, "x"),
        ("${A:-fallback}", {}, "fallback"),
        (
            "${A:-fallback}",
            {"A": ""},
            "fallback",
        ),  # empty counts as unset, as compose does
        ("${A:-}", {}, ""),
        ("p:${A}/q", {"A": "v"}, "p:v/q"),
        ("${MISSING}", {}, ""),
    ],
)
def test_interpolate(template, env, expected):
    assert launch.interpolate(template, env) == expected


def test_interpolate_never_reads_the_ambient_environment(monkeypatch):
    """A stray ``TIT_REPO_DIR`` in the user's shell must not become a bind mount."""
    monkeypatch.setenv("TIT_REPO_DIR", "/somewhere/dangerous")
    assert launch.interpolate("${TIT_REPO_DIR:-}", {}) == ""


# ---------------------------------------------------------------------------------------
# Naming parity with the Electron app
# ---------------------------------------------------------------------------------------


def test_hash8_matches_the_electron_implementation():
    """Verified live on 2026-09-07 against a container the desktop app itself created:
    ``tit.host_project_dir=/Users/idohaber/datasets/000`` was named
    ``ti-toolbox-fad740e5-tit-1``.  Both launchers must derive that same name, or
    ``--status``/``--stop`` and the app's attach-by-label would see two populations.
    """
    assert (
        launch.container_name("/Users/idohaber/datasets/000")
        == "ti-toolbox-fad740e5-tit-1"
    )
    assert launch.project_name("/Users/idohaber/datasets/000") == "ti-toolbox-fad740e5"


def test_hash8_is_eight_lowercase_hex_for_any_input():
    for text in ("", "/", "/a/b/c", "x" * 500, "/ü/nicode"):
        digest = launch.hash8(text)
        assert len(digest) == 8 and digest == digest.lower()
        int(digest, 16)


# ---------------------------------------------------------------------------------------
# The docker run argv
# ---------------------------------------------------------------------------------------


def _argv(**overrides) -> list[str]:
    env = launch.build_env(
        host_project_dir=PROJECT,
        port=8765,
        token="TOK",
        user_config="/home/you/.config/ti-toolbox",
        image_tag="dev",
        **overrides,
    )
    return launch.build_run_argv(
        launch.load_spec(),
        env,
        host_project_dir=PROJECT,
        image="idossha/ti-toolbox:dev",
    )


def _flag_values(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, item in enumerate(argv) if item == flag]


def test_argv_carries_all_four_labels():
    labels = dict(pair.split("=", 1) for pair in _flag_values(_argv(), "--label"))
    assert labels == {
        launch.LABEL_PROJECT: "ti-toolbox-" + launch.hash8(PROJECT),
        launch.LABEL_STACK: "ti-toolbox-v3",
        launch.LABEL_SERVICE: "tit",
        launch.LABEL_HOST_DIR: PROJECT,
    }


def test_argv_mounts_the_project_the_docker_socket_and_the_user_config():
    assert _flag_values(_argv(), "--volume") == [
        f"{PROJECT}:/mnt/000",
        "/home/you/.config/ti-toolbox:/root/.config/ti-toolbox",
        "/var/run/docker.sock:/var/run/docker.sock",
    ]


def test_the_dev_repo_mount_is_off_unless_asked_for_by_name():
    """An empty ``TIT_REPO_DIR`` drops the whole volume entry.

    Handing Docker ``:/ti-toolbox`` would be an error; worse, mounting a host
    directory there in a packaged run replaces the image's own ``tit``.
    """
    assert not any(
        entry.endswith(":/ti-toolbox") for entry in _flag_values(_argv(), "--volume")
    )
    with_repo = _flag_values(_argv(repo_dir="/src/TI-toolbox"), "--volume")
    assert "/src/TI-toolbox:/ti-toolbox" in with_repo


def test_argv_publishes_the_same_port_inside_and_out_on_loopback_only():
    env = launch.build_env(
        host_project_dir=PROJECT,
        port=8777,
        token="TOK",
        user_config="/c",
        image_tag="dev",
    )
    argv = launch.build_run_argv(
        launch.load_spec(), env, host_project_dir=PROJECT, image="i:t"
    )
    assert _flag_values(argv, "--publish") == ["127.0.0.1:8777:8777"]
    env_map = dict(pair.split("=", 1) for pair in _flag_values(argv, "--env"))
    assert env_map["TIT_SERVER_PORT"] == "8777"


def test_argv_environment_matches_the_compose_environment_block():
    env_map = dict(pair.split("=", 1) for pair in _flag_values(_argv(), "--env"))
    assert env_map["TIT_SERVER_TOKEN"] == "TOK"
    assert env_map["PROJECT_DIR_NAME"] == "000"
    assert env_map["LOCAL_PROJECT_DIR"] == PROJECT
    assert env_map["PYTHONPATH"] == "/ti-toolbox"
    # Present-and-empty, not absent: see the comment in shared/compose.ts.
    assert env_map["TIT_REPO_DIR"] == ""
    assert env_map["TIT_SERVER_RELOAD"] == ""
    assert env_map["TIT_STATIC_DIR"] == ""


def test_argv_pins_amd64_and_names_the_container_deterministically():
    argv = _argv()
    assert _flag_values(argv, "--platform") == ["linux/amd64"]
    assert _flag_values(argv, "--name") == [
        "ti-toolbox-" + launch.hash8(PROJECT) + "-tit-1"
    ]
    assert argv[-1] == "idossha/ti-toolbox:dev"
    assert "--init" in argv


def test_argv_carries_the_compose_healthcheck():
    argv = _argv()
    assert _flag_values(argv, "--health-cmd") == [
        "curl -fsS http://127.0.0.1:8765/api/health"
    ]


# ---------------------------------------------------------------------------------------
# Image tag resolution
# ---------------------------------------------------------------------------------------


def test_default_image_honours_the_environment(monkeypatch):
    monkeypatch.setenv("TIT_IMAGE_TAG", "3.0.0")
    assert launch.default_image() == "idossha/ti-toolbox:3.0.0"
    monkeypatch.setenv("TIT_IMAGE_TAG", "ghcr.io/someone/ti-toolbox:x")
    assert launch.default_image() == "ghcr.io/someone/ti-toolbox:x"


def test_default_image_uses_the_compose_default(monkeypatch):
    monkeypatch.delenv("TIT_IMAGE_TAG", raising=False)
    spec = launch.parse_compose(
        "services:\n  tit:\n    image: idossha/ti-toolbox:${TIT_IMAGE_TAG:-internal-fixture}"
    )
    monkeypatch.setattr(launch, "load_spec", lambda: spec)
    assert launch.default_image() == "idossha/ti-toolbox:internal-fixture"


def test_default_image_from_wheel_uses_internal_cohort(monkeypatch):
    monkeypatch.delenv("TIT_IMAGE_TAG", raising=False)
    monkeypatch.setattr(launch, "compose_path", lambda: None)
    assert launch.default_image() == "idossha/ti-toolbox:internal-20260908.1"


# ---------------------------------------------------------------------------------------
# Session URL and project resolution
# ---------------------------------------------------------------------------------------


def test_session_url_percent_encodes_the_token():
    assert launch.session_url("http://127.0.0.1:8765", "a/b+c=") == (
        "http://127.0.0.1:8765/auth/session?token=a%2Fb%2Bc%3D"
    )


def test_resolve_project_says_what_to_do_when_none_was_given():
    with pytest.raises(launch.LaunchError, match="--project"):
        launch.resolve_project(None)


def test_resolve_project_rejects_a_path_that_is_not_a_directory(tmp_path):
    with pytest.raises(launch.LaunchError, match="does not exist"):
        launch.resolve_project(str(tmp_path / "nope"))


def test_resolve_project_returns_a_real_absolute_path(tmp_path):
    assert launch.resolve_project(str(tmp_path)) == str(Path(tmp_path).resolve())


# ---------------------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------------------


def test_cli_parses_the_documented_flags():
    args = build_parser().parse_args(
        ["launch", "--project", "/p", "--port", "8777", "--image", "i:t", "--no-open"]
    )
    assert (args.command, args.project, args.port, args.image, args.no_open) == (
        "launch",
        "/p",
        8777,
        "i:t",
        True,
    )


@pytest.mark.parametrize("flag", ["--stop", "--status", "--logs"])
def test_cli_accepts_each_mode(flag):
    assert (
        getattr(
            build_parser().parse_args(["launch", "--project", "/p", flag]), flag[2:]
        )
        is True
    )


def test_cli_modes_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["launch", "--project", "/p", "--stop", "--status"])


def test_cli_project_defaults_to_the_environment(monkeypatch):
    monkeypatch.setenv("TIT_PROJECT_DIR", "/from/env")
    assert build_parser().parse_args(["launch"]).project == "/from/env"


def test_cli_runs_on_a_bare_interpreter_with_no_third_party_imports():
    """``tit launch --help`` must work with nothing installed but the standard library.

    Run in a subprocess with ``-I`` — isolated mode: no user site-packages, no
    ``PYTHONPATH``, no ``sitecustomize`` — with the repository put on ``sys.path`` by
    hand, so an accidental ``import numpy`` anywhere in the launcher's import chain
    fails here rather than on a user's laptop.  ``-I`` also ignores ``PYTHONPATH``,
    which is why the path is injected in the program text rather than the environment.
    """
    program = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r});"
        "from tit.cli import main; raise SystemExit(main(['launch', '--help']))"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", program], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "--project" in result.stdout


# ---------------------------------------------------------------------------------------
# The four front doors: loader.py, loader.sh, dev/loader/loader_dev.{py,sh}
# ---------------------------------------------------------------------------------------

LOADER = REPO_ROOT / "loader.py"
LOADER_SH = REPO_ROOT / "loader.sh"
LOADER_DEV = REPO_ROOT / "dev" / "loader" / "loader_dev.py"
LOADER_DEV_SH = REPO_ROOT / "dev" / "loader" / "loader_dev.sh"
COMPOSE_DEV = REPO_ROOT / "dev" / "loader" / "docker-compose.dev.yml"


def test_the_entry_points_exist_and_the_v2_ones_are_gone():
    """Two user entry points at the root, two dev equivalents beside the dev compose."""
    for path in (LOADER, LOADER_SH, LOADER_DEV, LOADER_DEV_SH, COMPOSE_DEV):
        assert path.is_file(), f"missing entry point: {path}"
    assert not (
        REPO_ROOT / "ti-toolbox.sh"
    ).exists(), "ti-toolbox.sh was replaced by loader.sh"
    assert not (
        REPO_ROOT / "desktop" / "docker"
    ).exists(), "the compose file moved to the root"


@pytest.mark.parametrize("script", [LOADER, LOADER_DEV])
def test_loader_help_is_one_screen(script):
    """``--help`` has to fit a terminal, or nobody reads the one line they needed."""
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert len(lines) <= 45, f"{script.name} --help is {len(lines)} lines"
    # Its own name, not the name of the thing it delegates to.
    assert script.name in result.stdout


@pytest.mark.parametrize("script", [LOADER, LOADER_DEV])
def test_loader_offers_the_same_options_as_tit_launch(script):
    """The front doors share one option set (``tit.cli.launch_arguments``), so this cannot drift."""
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    for flag in (
        "--project",
        "--port",
        "--image",
        "--no-open",
        "--timeout",
        "--stop",
        "--status",
        "--logs",
    ):
        assert flag in result.stdout, f"{script.name} --help does not mention {flag}"


def test_loader_reports_a_missing_project_without_touching_docker():
    """No ``--project`` is a message, not a traceback — and not a Docker call either."""
    result = subprocess.run(
        [sys.executable, str(LOADER), "--status"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={"PATH": "/nonexistent", "HOME": str(REPO_ROOT)},
    )
    assert result.returncode == 1
    assert "python loader.py:" in result.stderr


@pytest.mark.parametrize("script", [LOADER_SH, LOADER_DEV_SH])
def test_shell_loaders_are_executable_and_parse(script):
    """``bash -n`` catches a syntax error that would otherwise surface on a user's machine."""
    assert os.access(script, os.X_OK), f"{script} is not executable"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------------------
# The dev overrides have one definition too
# ---------------------------------------------------------------------------------------


def test_dev_overrides_match_compose():
    """``docker-compose.dev.yml`` and ``loader_dev.py`` must set the same three variables.

    The dev file is what ``docker compose -f docker-compose.yml -f
    dev/loader/docker-compose.dev.yml`` layers on; ``loader_dev.py`` sets the same three
    through :func:`tit.launch.build_env`.  Two ways to say the same thing is fine; two
    ways that say *different* things is a developer debugging the wrong container.
    """
    text = COMPOSE_DEV.read_text(encoding="utf-8")
    assert "services:" in text and "tit:" in text
    for key in ("TIT_REPO_DIR", "TIT_SERVER_RELOAD", "TIT_STATIC_DIR"):
        assert key in text, f"{COMPOSE_DEV.name} does not set {key}"
    # Overrides only: no image, no ports, no volumes — the root file owns those.
    for owned_by_root in ("image:", "ports:", "volumes:", "healthcheck:"):
        assert (
            owned_by_root not in text
        ), f"{COMPOSE_DEV.name} redefines {owned_by_root}"


def test_dev_overrides_reach_the_container_env():
    """``repo_dir``/``server_reload``/``static_dir`` end up on the ``docker run`` argv."""
    env = launch.build_env(
        host_project_dir=PROJECT,
        port=8765,
        token="t",
        user_config="/tmp/cfg",
        image_tag="dev",
        repo_dir="/checkout",
        static_dir="/ti-toolbox/desktop/out/renderer",
        server_reload=True,
    )
    argv = launch.build_run_argv(
        launch.BUILTIN_SPEC, env, host_project_dir=PROJECT, image="img"
    )
    assert "TIT_REPO_DIR=/checkout" in argv
    assert "TIT_SERVER_RELOAD=1" in argv
    assert "TIT_STATIC_DIR=/ti-toolbox/desktop/out/renderer" in argv
    assert "/checkout:/ti-toolbox" in argv


def test_a_user_run_mounts_no_repo():
    """The default is off: a user run must never bind-mount a host dir over ``/ti-toolbox``."""
    env = launch.build_env(
        host_project_dir=PROJECT,
        port=8765,
        token="t",
        user_config="/tmp/cfg",
        image_tag="3.0.0",
    )
    argv = launch.build_run_argv(
        launch.BUILTIN_SPEC, env, host_project_dir=PROJECT, image="img"
    )
    assert "TIT_REPO_DIR=" in argv
    assert "TIT_SERVER_RELOAD=" in argv
    assert not any(
        a.endswith(":/ti-toolbox") for a in argv
    ), "a user run mounted something at /ti-toolbox"


def test_python_m_tit_cli_is_runnable():
    """``python -m tit.cli`` must actually run — ``loader.sh`` execs exactly that.

    Regression: the ``if __name__ == "__main__"`` guard went missing once during a
    refactor of this module.  Nothing failed — ``python -m tit.cli launch --status``
    simply printed nothing and exited 0, so ``loader.sh`` looked like it had worked.
    Importing the module is not enough to catch that; it has to be *run*.
    """
    result = subprocess.run(
        [sys.executable, "-m", "tit.cli", "launch", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "--project" in result.stdout, "python -m tit.cli produced no help output"


def _skip_without_host_python() -> None:
    """Skip when the machine has no CPython >= 3.11 that ``loader.sh`` would find.

    ``loader.sh`` is the *host* entry point: it looks for python3.14…python3.11, python3,
    python on PATH and refuses with a diagnostic when none is a CPython >= 3.11. Inside the
    SimNIBS container that is exactly the case -- ``python3`` there is 3.10, and the 3.11 is
    ``simnibs_python``, which is not one of the names loader.sh probes. The script is behaving
    correctly; the container is simply not a host. Skipping on the script's own precondition
    keeps this test real everywhere it can run (the host gate does run it) instead of asserting
    an environment.
    """
    for candidate in (
        "python3.14",
        "python3.13",
        "python3.12",
        "python3.11",
        "python3",
        "python",
    ):
        exe = shutil.which(candidate)
        if exe is None:
            continue
        probe = subprocess.run(
            [
                exe,
                "-c",
                "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)",
            ],
            capture_output=True,
        )
        if probe.returncode == 0:
            return
    pytest.skip("no CPython >= 3.11 on PATH, so loader.sh correctly refuses to run")


def test_loader_sh_in_a_checkout_runs_the_checkout(tmp_path):
    """``./loader.sh`` from a checkout must run *that* checkout, and say so.

    The installed-package branch used to come first, and its probe (``python -c 'import
    tit.launch'``) succeeds merely by being run from the repository root, because ``-c``
    puts the current directory on ``sys.path``.  So a checkout with no ``tit`` installed
    anywhere still took the installed branch and printed ``tit launch …`` follow-up hints
    naming a command that did not exist on the machine.
    """
    _skip_without_host_python()
    # Run with a `docker` whose daemon is DOWN, so this proves the dispatch rather than the
    # machine. The old form ran with the ambient PATH and passed only where a daemon happened to
    # be running: the preconditions were the first thing `loader.sh` did, so with the daemon down
    # it exited 1 before reaching the checkout branch this test is about. Asking a script for its
    # flags is not asking it to start a container.
    shim = tmp_path / "docker"
    shim.write_text("#!/bin/sh\nexit 1\n")
    shim.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ.get('PATH', '')}")
    result = subprocess.run(
        ["bash", str(LOADER_SH), "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "python loader.py" in result.stdout, result.stdout[:400]


@pytest.mark.parametrize("piped", [False, True])
@pytest.mark.parametrize("cached", [False, True])
def test_standalone_loader_refreshes_main_even_with_cached_environment(
    tmp_path, piped, cached
):
    """A same-version cached or globally installed release must not hide main updates."""
    script = tmp_path / "loader.sh"
    script.write_text(LOADER_SH.read_text())
    venv = tmp_path / "cached venv"
    (venv / "bin").mkdir(parents=True)
    trace = tmp_path / "calls.jsonl"
    shim = tmp_path / "python"
    shim.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, pathlib, shutil\n"
        "with open(os.environ['LOADER_TRACE'], 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if 'venv' in sys.argv:\n"
        "    target = pathlib.Path(sys.argv[-1]) / 'bin' / 'python'\n"
        "    target.parent.mkdir(parents=True, exist_ok=True)\n"
        "    shutil.copy2(sys.argv[0], target)\n"
        "if 'tit.cli' in sys.argv: print('fixture launcher')\n"
        "if 'pip' in sys.argv and os.environ.get('FAIL_REFRESH'): sys.exit(1)\n"
    )
    shim.chmod(0o755)
    if cached:
        shutil.copy2(shim, venv / "bin" / "python")
    env = dict(
        os.environ,
        TIT_PYTHON=str(shim),
        TIT_VENV_DIR=str(venv),
        LOADER_TRACE=str(trace),
    )
    command = (
        ["bash", "-s", "--", "--help"] if piped else ["bash", str(script), "--help"]
    )
    for _ in range(2):
        result = subprocess.run(
            command,
            input=script.read_text() if piped else None,
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env=env,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "fixture launcher"
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    installs = [call for call in calls if "pip" in call]
    assert len(installs) == 2
    for call in installs:
        assert call == [
            "-I",
            "-m",
            "pip",
            "install",
            "--quiet",
            "--upgrade",
            "--force-reinstall",
            "--no-deps",
            "https://github.com/idossha/TI-toolbox/archive/refs/heads/main.zip",
        ]
    assert [call for call in calls if "tit.cli" in call] == [
        ["-I", "-m", "tit.cli", "launch", "--help"],
        ["-I", "-m", "tit.cli", "launch", "--help"],
    ]
    trace.write_text("")
    result = subprocess.run(
        command,
        input=script.read_text() if piped else None,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env=dict(env, FAIL_REFRESH="1"),
    )
    assert result.returncode != 0
    assert "could not refresh the launcher from main" in result.stderr
    assert all(
        "tit.cli" not in json.loads(line) for line in trace.read_text().splitlines()
    )


@pytest.mark.parametrize("operation", ["--stop", "--status", "--logs"])
@pytest.mark.parametrize("cached", [True, False])
def test_standalone_shell_management_works_offline_with_cache(
    tmp_path, operation, cached
):
    script = tmp_path / "loader.sh"
    script.write_text(LOADER_SH.read_text())
    venv = tmp_path / "cache"
    (venv / "bin").mkdir(parents=True)
    trace = tmp_path / "calls.jsonl"
    shim = tmp_path / "python"
    shim.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, pathlib, shutil\n"
        "with open(os.environ['LOADER_TRACE'], 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if 'venv' in sys.argv:\n"
        "    target = pathlib.Path(sys.argv[-1]) / 'bin' / 'python'\n"
        "    target.parent.mkdir(parents=True, exist_ok=True)\n"
        "    shutil.copy2(sys.argv[0], target)\n"
        "if 'pip' in sys.argv: sys.exit(73)  # offline\n"
        "if 'tit.cli' in sys.argv: print('managed existing container')\n"
    )
    shim.chmod(0o755)
    if cached:
        shutil.copy2(shim, venv / "bin" / "python")
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nexit 0\n")
    docker.chmod(0o755)
    env = dict(
        os.environ,
        TIT_PYTHON=str(shim),
        TIT_VENV_DIR=str(venv),
        LOADER_TRACE=str(trace),
        PATH=str(tmp_path) + os.pathsep + os.environ["PATH"],
    )
    result = subprocess.run(
        ["bash", str(script), operation, "--project", "/tmp/existing project"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    if cached:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "managed existing container"
        assert not any("pip" in call for call in calls)
        assert calls[-1] == [
            "-I",
            "-m",
            "tit.cli",
            "launch",
            operation,
            "--project",
            "/tmp/existing project",
        ]
    else:
        assert result.returncode != 0
        assert any("pip" in call for call in calls)
        assert not any("tit.cli" in call for call in calls)
        assert "could not refresh" in result.stderr
