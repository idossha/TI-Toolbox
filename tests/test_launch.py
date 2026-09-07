"""Unit tests for ``tit launch`` (:mod:`tit.launch`, :mod:`tit.cli`).

Nothing here talks to Docker: every test asserts a *pure* function — the compose
parser, the interpolator, the project hash, the argv builder, the CLI parser.
The live check that the argv these produce actually starts a container is a
manual step recorded in ``docs/installation/bash-cli.md``; what is guarded here
is that the spec cannot drift.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tit import launch
from tit.cli import build_parser

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE = REPO_ROOT / "desktop" / "docker" / "docker-compose.v3.yml"

# One host directory, used everywhere below so the expected container name is stable.
PROJECT = "/Users/you/datasets/000"


# ---------------------------------------------------------------------------------------
# The run spec has exactly one source of truth
# ---------------------------------------------------------------------------------------


@pytest.mark.skipif(not COMPOSE.is_file(), reason="compose file only exists in a checkout")
def test_builtin_spec_matches_compose():
    """The wheel's fallback spec must equal what the compose file actually says.

    An installed ``tit`` has no ``desktop/`` directory, so :data:`launch.BUILTIN_SPEC`
    stands in for the file.  If someone edits the compose file, this fails — which
    is the whole point: the two must not describe different containers.
    """
    assert launch.parse_compose(COMPOSE.read_text(encoding="utf-8")) == launch.BUILTIN_SPEC


@pytest.mark.skipif(not COMPOSE.is_file(), reason="compose file only exists in a checkout")
def test_load_spec_prefers_the_checkout():
    assert launch.load_spec() == launch.parse_compose(COMPOSE.read_text(encoding="utf-8"))


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
        ("${A:-fallback}", {"A": ""}, "fallback"),  # empty counts as unset, as compose does
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
    assert launch.container_name("/Users/idohaber/datasets/000") == "ti-toolbox-fad740e5-tit-1"
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
        launch.load_spec(), env, host_project_dir=PROJECT, image="idossha/ti-toolbox:dev"
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
    assert not any(entry.endswith(":/ti-toolbox") for entry in _flag_values(_argv(), "--volume"))
    with_repo = _flag_values(_argv(repo_dir="/src/TI-toolbox"), "--volume")
    assert "/src/TI-toolbox:/ti-toolbox" in with_repo


def test_argv_publishes_the_same_port_inside_and_out_on_loopback_only():
    env = launch.build_env(
        host_project_dir=PROJECT, port=8777, token="TOK",
        user_config="/c", image_tag="dev",
    )
    argv = launch.build_run_argv(launch.load_spec(), env, host_project_dir=PROJECT, image="i:t")
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
    assert _flag_values(argv, "--name") == ["ti-toolbox-" + launch.hash8(PROJECT) + "-tit-1"]
    assert argv[-1] == "idossha/ti-toolbox:dev"
    assert "--init" in argv


def test_argv_carries_the_compose_healthcheck():
    argv = _argv()
    assert _flag_values(argv, "--health-cmd") == ["curl -fsS http://127.0.0.1:8765/api/health"]


# ---------------------------------------------------------------------------------------
# Image tag resolution
# ---------------------------------------------------------------------------------------


def test_default_image_honours_the_environment(monkeypatch):
    monkeypatch.setenv("TIT_IMAGE_TAG", "3.0.0")
    assert launch.default_image() == "idossha/ti-toolbox:3.0.0"
    monkeypatch.setenv("TIT_IMAGE_TAG", "ghcr.io/someone/ti-toolbox:x")
    assert launch.default_image() == "ghcr.io/someone/ti-toolbox:x"


def test_default_image_falls_back_to_dev_below_v3(monkeypatch):
    """No ``idossha/ti-toolbox`` image is published for any 2.x version — the repository
    did not exist on Docker Hub as of 2026-09-07 — so a 2.x package must not ask for one."""
    monkeypatch.delenv("TIT_IMAGE_TAG", raising=False)
    monkeypatch.setattr(launch.tit, "__version__", "2.4.0")
    assert launch.default_image() == "idossha/ti-toolbox:dev"
    monkeypatch.setattr(launch.tit, "__version__", "3.0.0")
    assert launch.default_image() == "idossha/ti-toolbox:3.0.0"


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
        "launch", "/p", 8777, "i:t", True,
    )


@pytest.mark.parametrize("flag", ["--stop", "--status", "--logs"])
def test_cli_accepts_each_mode(flag):
    assert getattr(build_parser().parse_args(["launch", "--project", "/p", flag]), flag[2:]) is True


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
    result = subprocess.run([sys.executable, "-I", "-c", program], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--project" in result.stdout
