import sys
from pathlib import Path

import loader
from tit.project_init import initializer


def test_is_new_project_true_for_empty_dir(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    assert initializer.is_new_project(project_dir) is True


def test_is_new_project_false_with_marker(tmp_path):
    project_dir = tmp_path / "project"
    marker_path = project_dir / "code" / "ti-toolbox" / "config" / ".initialized"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text("init")
    assert initializer.is_new_project(project_dir) is False


def test_ensure_images_pulled_calls_compose_pull(monkeypatch, tmp_path):
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        "services:\n"
        "  simnibs:\n"
        "    image: foo/bar:1\n"
        "  freesurfer:\n"
        "    image: existing/image:2\n"
    )
    monkeypatch.setattr(loader, "DOCKER_COMPOSE_FILE", compose)
    monkeypatch.setattr(loader, "capture", lambda _cmd: "existing/image:2\n")

    calls = []

    def fake_run(cmd, env=None, **_kwargs):
        calls.append((cmd, env))
        class Result:
            returncode = 0
        return Result()

    monkeypatch.setattr(loader.subprocess, "run", fake_run)

    env = {"LOCAL_PROJECT_DIR": "/tmp/project"}
    loader.ensure_images_pulled(env)

    assert calls
    assert calls[0][0][:4] == ["docker", "compose", "-f", str(compose)]
    assert calls[0][1] == env


def test_loader_main_calls_docker_compose(monkeypatch, tmp_path):
    """Test that loader.main() calls run_docker_compose with the correct project directory."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    docker_calls = []

    def fake_docker_compose(project_dir_arg, project_name):
        docker_calls.append((str(project_dir_arg), project_name))

    monkeypatch.setattr(loader, "check_docker_available", lambda: None)
    monkeypatch.setattr(loader, "check_x_forwarding", lambda: None)
    monkeypatch.setattr(loader, "display_welcome", lambda: None)
    monkeypatch.setattr(loader, "set_display_env", lambda: None)
    monkeypatch.setattr(loader, "allow_xhost", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(loader, "revert_xhost", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(loader, "run_docker_compose", fake_docker_compose)
    monkeypatch.setattr(loader, "save_default_project_dir", lambda *_args, **_kwargs: None)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["loader.py", "--project-dir", str(project_dir), "--yes"])

    loader.main()

    assert len(docker_calls) == 1
    assert docker_calls[0][0] == str(project_dir)  # Project directory passed correctly
    assert docker_calls[0][1] == project_dir.name  # Project name passed correctly
