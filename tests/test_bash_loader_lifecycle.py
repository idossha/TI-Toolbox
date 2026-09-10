"""Bash session decisions against authored fake Docker output (2026-09-09).

Run: python3 -m pytest tests/test_bash_loader_lifecycle.py -q.
Real Docker and Electron integration are deliberately outside these offline checks.
"""

import os
import pty
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run_loader(
    tmp_path,
    args,
    *,
    multiple=False,
    project_container="",
    invalid_spec=False,
    running=True,
    terminal_input=None,
):
    """Record subprocess side effects using an isolated command boundary."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    docker = bin_dir / "docker"
    docker.write_text("""#!/bin/bash
printf '%s\\n' "$*" >> "$DOCKER_LOG"
case "$1" in
 info) exit 0 ;;
 ps)
   if [[ "$*" == *--format* ]]; then
     [ "$RUNNING" = 1 ] || exit 0
     echo 'abc|ti-toolbox-other|idossha/ti-toolbox:test|tit.stack=ti-toolbox-v3'
     echo 'unrelated|not-ti-toolbox-backup|example/not-ti-toolbox-backup:test|'
     echo 'sibling|ti-toolbox-worker|idossha/ti-toolbox:test|tit.stack=ti-toolbox-v3,tit.service=worker'
     if [ "$MULTIPLE" = 1 ]; then echo 'def|legacy|idossha/ti-toolbox:v2.5.0|'; fi
   elif [ -n "$PROJECT_CONTAINER" ]; then echo "$PROJECT_CONTAINER"; fi ;;
 inspect)
   case "$3" in
     *Config.Env*) printf 'TIT_SERVER_TOKEN=fixture-token\\nTIT_SERVER_PORT=18765\\n' ;;
     '{{.Config.Image}}') echo 'idossha/ti-toolbox:test' ;;
     '{{.Id}}') echo "$4" ;;
     '{{.Name}}') if [ "$4" = unrelated ]; then echo '/not-ti-toolbox-backup'; elif [ "$4" = def ]; then echo '/legacy'; else echo '/ti-toolbox-other'; fi ;;
     '{{.State.Running}}') echo true ;;
     *host_project_dir*) echo "$TEST_PROJECT" ;;
     *) echo 'abc /ti-toolbox-other (idossha/ti-toolbox:test)' ;;
   esac ;;
 stop|rm) exit 0 ;;
 compose)
   if [ "$2" = version ]; then exit 0; fi
   if [[ "$*" == *'config --quiet'* ]]; then exit "$INVALID_SPEC"; fi
   exit 9 ;;
 image) exit 0 ;;
esac
""")
    docker.chmod(0o755)
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/bash\nexit 0\n")
    curl.chmod(0o755)
    env = dict(
        os.environ,
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        DOCKER_LOG=str(log),
        TEST_PROJECT=str(tmp_path),
        MULTIPLE=str(int(multiple)),
        RUNNING=str(int(running)),
        PROJECT_CONTAINER=project_container,
        INVALID_SPEC=str(int(invalid_spec)),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
    )
    master = slave = None
    if terminal_input is not None:
        master, slave = pty.openpty()
        os.write(master, terminal_input.encode())
    result = subprocess.run(
        [
            "bash",
            str(ROOT / "loader.sh"),
            "--project",
            str(tmp_path),
            "--no-open",
            *args,
        ],
        env=env,
        text=True,
        capture_output=True,
        stdin=slave if slave is not None else subprocess.DEVNULL,
        timeout=10,
    )
    if master is not None:
        os.close(master)
        os.close(slave)
    return result, log.read_text()


def test_running_container_requires_explicit_decision(tmp_path):
    result, calls = run_loader(tmp_path, [])
    assert result.returncode != 0
    assert "--existing attach" in result.stderr
    assert "stop " not in calls and "rm " not in calls


def test_attach_uses_other_project_running_session(tmp_path):
    result, calls = run_loader(tmp_path, ["--existing", "attach"])
    assert result.returncode == 0, result.stderr
    assert "http://127.0.0.1:18765/auth/session?token=fixture-token" in result.stdout
    assert "stop " not in calls and "compose " not in calls


def test_multiple_sessions_need_selection(tmp_path):
    result, calls = run_loader(tmp_path, ["--existing", "attach"], multiple=True)
    assert result.returncode != 0
    assert "--container ID" in result.stderr
    assert "stop " not in calls


def test_explicit_selection_attaches_without_mutation(tmp_path):
    result, calls = run_loader(
        tmp_path, ["--existing", "attach", "--container", "def"], multiple=True
    )
    assert result.returncode == 0, result.stderr
    assert "stop " not in calls and "compose " not in calls


def test_recreate_stops_only_selected_before_attempting_new_compose(tmp_path):
    result, calls = run_loader(
        tmp_path, ["--existing", "recreate", "--container", "def"], multiple=True
    )
    # Fake Compose deliberately fails: no live container or network is touched.
    assert result.returncode != 0
    assert "stop abc" not in calls and "rm abc" not in calls
    assert calls.index("stop def") < calls.index("rm def")
    assert (
        calls.index("compose version")
        < calls.index("config --quiet")
        < calls.index("stop def")
    )


def test_recreate_multiple_requires_selection_before_mutation(tmp_path):
    result, calls = run_loader(tmp_path, ["--existing", "recreate"], multiple=True)
    assert result.returncode != 0
    assert "--container ID" in result.stderr
    assert "stop " not in calls and "rm " not in calls


def test_regular_loader_hands_off_before_docker(tmp_path):
    checkout = tmp_path / "checkout"
    helper_dir = checkout / "dev"
    helper_dir.mkdir(parents=True)
    (checkout / "loader.sh").write_text((ROOT / "loader.sh").read_text())
    (helper_dir / "launch-electron.sh").write_text(
        '#!/bin/bash\nprintf "%s|%s|%s|%s|%s" "$TIT_LAUNCH_PROJECT_DIR" '
        '"$TIT_LAUNCH_EXISTING" "$TIT_LAUNCH_CONTAINER" "$TIT_LAUNCH_PORT" "$TIT_LAUNCH_TIMEOUT"\n'
    )
    result = subprocess.run(
        [
            "bash",
            str(checkout / "loader.sh"),
            "--desktop",
            "--project",
            str(tmp_path),
            "--existing",
            "attach",
            "--container",
            "chosen",
            "--port",
            "19876",
            "--timeout",
            "45",
        ],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{tmp_path}|attach|chosen|19876|45"


def test_recreate_refuses_project_collision_before_stopping_selected(tmp_path):
    result, calls = run_loader(
        tmp_path,
        ["--existing", "recreate", "--container", "def"],
        multiple=True,
        project_container="abc",
    )
    assert result.returncode != 0
    assert "another running container" in result.stderr
    assert "stop " not in calls and "rm " not in calls


def test_invalid_compose_preserves_running_container(tmp_path):
    result, calls = run_loader(tmp_path, ["--existing", "recreate"], invalid_spec=True)
    assert result.returncode != 0
    assert "invalid container specification" in result.stderr
    assert "stop " not in calls and "rm " not in calls


def test_standalone_loader_launches_explicit_executable_with_clean_environment(
    tmp_path,
):
    script = tmp_path / "loader.sh"
    script.write_text((ROOT / "loader.sh").read_text())
    executable = tmp_path / "desktop-app"
    executable.write_text(
        '#!/bin/bash\nprintf "%s|%s|%s" "$TIT_LAUNCH_IMAGE" '
        '"${ELECTRON_RUN_AS_NODE:-clean}" "${TIT_DEV_SERVER_URL:-clean}"\n'
    )
    executable.chmod(0o755)
    env = dict(
        os.environ,
        TIT_ELECTRON_EXECUTABLE=str(executable),
        ELECTRON_RUN_AS_NODE="1",
        TIT_DEV_SERVER_URL="stale",
    )
    result = subprocess.run(
        [
            "bash",
            str(script),
            "--desktop",
            "--project",
            str(tmp_path),
            "--image",
            "idossha/ti-toolbox:custom",
        ],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "idossha/ti-toolbox:custom|clean|cleanTI-Toolbox closed.\n"


def test_unresolved_container_selector_does_not_create_session(tmp_path):
    result, calls = run_loader(
        tmp_path,
        ["--existing", "recreate", "--container", "missing"],
        running=False,
    )
    assert result.returncode != 0
    assert "no running TI-Toolbox container" in result.stderr
    assert "compose " not in calls and "stop " not in calls and "rm " not in calls


def test_terminal_prompt_lists_images_and_separate_actions(tmp_path):
    result, calls = run_loader(tmp_path, [], terminal_input="2\n")
    assert result.returncode == 0, result.stderr
    assert "  1. idossha/ti-toolbox:test" in result.stdout
    assert "1. Recreate (default)" in result.stdout
    assert "2. Attach" in result.stdout
    assert "Choose [1]: " in result.stderr
    assert "Available actions\n-----------------" in result.stdout
    assert "ti-toolbox-other" not in result.stdout
    assert "project=" not in result.stdout
    assert "abc" not in result.stdout
    assert "worker" not in result.stdout
    assert "not-ti-toolbox-backup" not in result.stdout
    assert "unrelated" not in calls
    assert "stop " not in calls


def test_terminal_enter_defaults_to_recreate(tmp_path):
    result, calls = run_loader(tmp_path, [], terminal_input="\n")
    assert result.returncode != 0  # Fake Compose refuses to launch.
    assert "stop abc" in calls and "rm abc" in calls


def test_terminal_number_selects_only_named_container(tmp_path):
    result, calls = run_loader(tmp_path, [], multiple=True, terminal_input="2\n\n")
    assert "  2. idossha/ti-toolbox:test" in result.stdout
    assert "stop def" in calls and "rm def" in calls
    assert "stop abc" not in calls and "rm abc" not in calls


def test_terminal_eof_leaves_container_unchanged(tmp_path):
    result, calls = run_loader(tmp_path, [], terminal_input="\x04")
    assert result.returncode != 0
    assert "stop " not in calls and "rm " not in calls


def test_terminal_invalid_selection_leaves_containers_unchanged(tmp_path):
    result, calls = run_loader(tmp_path, [], multiple=True, terminal_input="3\n")
    assert result.returncode != 0
    assert "invalid container number" in result.stderr
    assert "stop " not in calls and "rm " not in calls


def test_unrelated_container_cannot_be_selected(tmp_path):
    result, calls = run_loader(
        tmp_path, ["--existing", "recreate", "--container", "unrelated"]
    )
    assert result.returncode != 0
    assert "not a running TI-Toolbox container" in result.stderr
    assert "stop " not in calls and "rm " not in calls
