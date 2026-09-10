"""Container decisions against authored Docker responses; no live Docker.

Run python3 -m pytest tests/test_launch_image.py -q. These cases pin cross-project
selection, explicit consent, and stop-before-remove ordering. UI is tested elsewhere.
"""

import json
import subprocess
from unittest.mock import Mock

import pytest
from tit import launch


@pytest.fixture
def docker(monkeypatch, tmp_path):
    running = [
        {
            "Id": "other-id",
            "Name": "/ti-toolbox-other",
            "State": {"Running": True},
            "Config": {
                "Image": "idossha/ti-toolbox:old",
                "Labels": {"tit.host_project_dir": "/other"},
                "Env": ["TIT_SERVER_TOKEN=secret", "TIT_SERVER_PORT=8888"],
            },
        }
    ]
    commands = []

    def call(*args, **kwargs):
        commands.append(args)
        stdout = ""
        if args[:2] == ("ps", "--format"):
            stdout = "\n".join(item["Id"] for item in running)
        elif args[0] == "inspect":
            stdout = json.dumps(
                [next(item for item in running if item["Id"] == args[1])]
            )
        elif args[0] == "rm":
            running[:] = [item for item in running if item["Id"] != args[1]]
        elif args[0] == "run":
            stdout = "new-id"
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(launch, "_docker", call)
    monkeypatch.setattr(launch.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(launch, "wait_for_health", lambda *a, **k: None)
    monkeypatch.setattr(launch, "find_free_port", lambda _: 8765)
    monkeypatch.setattr(launch, "user_config_dir", lambda: tmp_path)
    return running, commands, tmp_path


def test_running_other_project_requires_decision_without_mutation(docker):
    _, commands, project = docker
    with pytest.raises(launch.LaunchError, match="choose --existing"):
        launch.start(launch.LaunchOptions(project=str(project)))
    assert not any(cmd[0] in ("stop", "rm", "run") for cmd in commands)


def test_explicit_attach_uses_running_session_despite_requested_image(docker):
    _, commands, project = docker
    options = launch.LaunchOptions(
        project=str(project), image="different:new", existing="attach"
    )
    assert launch.start(options) == ("http://127.0.0.1:8888", "secret")
    assert options.session_container == "other-id"
    assert options.session_project == "/other"
    assert not any(cmd[0] in ("stop", "rm", "run") for cmd in commands)


def test_recreate_stops_then_removes_selected_and_uses_requested_yaml_project(docker):
    _, commands, project = docker
    options = launch.LaunchOptions(
        project=str(project), image="requested:new", existing="recreate"
    )
    launch.start(options)
    mutations = [cmd for cmd in commands if cmd[0] in ("stop", "rm", "run")]
    assert mutations[:2] == [("stop", "other-id"), ("rm", "other-id")]
    assert mutations[2][-1] == "requested:new"
    assert str(project) + ":/mnt/" + project.name in mutations[2]
    assert options.session_container == "new-id"


def test_multiple_sessions_require_named_selection(docker):
    running, commands, project = docker
    running.append({**running[0], "Id": "second-id", "Name": "/ti-toolbox-second"})
    with pytest.raises(launch.LaunchError, match="multiple containers"):
        launch.start(launch.LaunchOptions(project=str(project), existing="attach"))
    options = launch.LaunchOptions(
        project=str(project), existing="attach", container="ti-toolbox-second"
    )
    launch.start(options)
    assert options.session_container == "second-id"


def test_unrelated_container_does_not_trigger_prompt(docker):
    running, _, project = docker
    running[0]["Name"] = "/postgres"
    running[0]["Config"]["Image"] = "postgres:17"
    launch.start(launch.LaunchOptions(project=str(project)))


def test_interactive_attach_requires_answer(docker, monkeypatch):
    _, _, project = docker
    monkeypatch.setattr(launch.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "attach")
    assert launch.start(launch.LaunchOptions(project=str(project)))[0].endswith(":8888")


def test_regular_cli_hands_off_before_docker(docker, monkeypatch):
    from tit import cli

    _, commands, project = docker
    monkeypatch.setenv("TIT_ELECTRON_EXECUTABLE", "/installed/electron")
    for key in (
        "ELECTRON_RUN_AS_NODE",
        "ELECTRON_RENDERER_URL",
        "TIT_LAUNCH_CONTAINER_ID",
        "TIT_DEV_SERVER_URL",
        "TIT_DEV_SERVER_TOKEN",
        "TIT_DEV_PROJECT_DIR",
    ):
        monkeypatch.setenv(key, "stale-session")
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/installed/electron")
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(cli.subprocess, "run", run)
    args = cli.launch_parser().parse_args(
        [
            "--desktop",
            "--project",
            str(project),
            "--existing",
            "attach",
            "--container",
            "other-id",
        ]
    )
    assert cli.launch_command(args) == 0
    assert commands == []
    assert run.call_args.args[0] == ["/installed/electron"]
    assert "stale-session" not in run.call_args.kwargs["env"].values()
    assert run.call_args.kwargs["env"]["TIT_LAUNCH_IMAGE"].startswith(
        "idossha/ti-toolbox:"
    )
    assert "TIT_IMAGE_TAG" not in run.call_args.kwargs["env"]
    assert run.call_args.kwargs["env"]["TIT_LAUNCH_CONTAINER"] == "other-id"
    assert run.call_args.kwargs["env"]["TIT_LAUNCH_EXISTING"] == "attach"


def test_project_collision_refuses_before_stopping_selected(docker, monkeypatch):
    running, commands, project = docker
    owner = {**running[0], "Id": "project-owner"}
    monkeypatch.setattr(launch, "find_container", lambda _: owner)
    with pytest.raises(launch.LaunchError, match="another running container owns"):
        launch.start(launch.LaunchOptions(project=str(project), existing="recreate"))
    assert not any(cmd[0] in ("stop", "rm", "run") for cmd in commands)


def test_cached_install_discovers_path_executable_before_docker(docker, monkeypatch):
    from tit import cli

    _, commands, project = docker
    monkeypatch.delenv("TIT_ELECTRON_EXECUTABLE", raising=False)
    monkeypatch.setattr(cli, "__file__", str(project / "tit" / "cli.py"))
    monkeypatch.setattr(cli.shutil, "which", lambda _: "/installed/ti-toolbox")
    run = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(cli.subprocess, "run", run)
    args = cli.launch_parser().parse_args(["--desktop", "--project", str(project)])
    assert cli.launch_command(args) == 0
    assert commands == []
    assert run.call_args.args[0][0] != "bash"


@pytest.mark.parametrize(
    "answer, expected",
    [("", "recreate"), ("1", "recreate"), ("2", "attach"), ("attach", "attach")],
)
def test_clean_interactive_choice_defaults_to_recreate(monkeypatch, answer, expected):
    output = []
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    info = {
        "Id": "private-id",
        "Name": "/ti-toolbox-example",
        "Config": {"Image": "idossha/ti-toolbox:test"},
    }
    selected, action = launch.choose_existing(
        [info], launch.LaunchOptions(project="/project", echo=output.append)
    )
    assert selected is info
    assert action == expected
    rendered = "\n".join(output)
    assert "idossha/ti-toolbox:test" in rendered and "Recreate (default)" in rendered
    assert "private-id" not in rendered and "ti-toolbox-example" not in rendered
    assert "Available actions\n-----------------" in rendered


def test_interactive_eof_does_not_accept_recreate_default(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def eof(prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    with pytest.raises(launch.LaunchError):
        launch.choose_existing(
            [{"Id": "id", "Name": "/ti-toolbox-test"}],
            launch.LaunchOptions(project="/project", echo=lambda _: None),
        )


def test_discovery_ignores_unrelated_similarly_named_containers(docker):
    running, _, _ = docker
    running.append(
        {
            "Id": "unrelated",
            "Name": "/not-ti-toolbox-backup",
            "Config": {"Image": "example/not-ti-toolbox:latest", "Labels": {}},
        }
    )
    assert [item["Id"] for item in launch.find_running_containers()] == ["other-id"]
