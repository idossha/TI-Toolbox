"""The three launchers agree on project identity, session discovery and the user-config dir.

What it pins (2026-10-22), each against a shared table under ``tests/fixtures/`` that
``desktop/tests/unit/launch-contract.test.ts`` reads for the Electron side:

- ``project_hash.json``: the compose project name per host directory. Written by
  ``node dev/gen_project_hash_fixture.mjs`` (an independent BigInt reference over UTF-16 code
  units, checked against names observed on a real container and from the shipping Electron
  hash). Checked here for ``tit.launch.project_name`` and for ``loader.sh``'s ``project_stack``
  under ``/bin/bash`` (3.2 on macOS) and the ``bash`` on PATH, each with ``LC_ALL=C`` and
  ``en_US.UTF-8``.
- ``session_labels.json``: which label sets are a running TI-Toolbox session (DECISIONS
  2026-10-22: launcher labels only, service ``tit``). Authored by hand from that rule.
  Checked for ``tit.launch.find_running_containers`` and the ``session_ids`` filter
  ``loader.sh`` applies to ``docker ps``.
- ``user_config_dirs.json``: the host directory mounted at ``/root/.config/ti-toolbox``
  (telemetry consent, prefs). Authored by hand. Checked for ``tit.launch.user_config_path`` and
  ``loader.sh``'s ``user_config_dir``, and end to end (macOS and Linux rules, from
  ``docs/wiki/telemetry.md``) through the volume ``loader.sh``'s compose run and
  ``tit.launch.start`` actually mount.
- ``launch_contract.json``: the container one start creates (environment, volumes, publish,
  labels, name), authored by reading ``docker-compose.yml``. Checked for
  ``tit.launch.build_run_argv`` and, through a fake ``docker``, for what ``loader.sh`` hands
  ``docker compose run`` (its exported environment and its rewritten YAML).
- The launcher -> Electron hand-off: every ``TIT_LAUNCH_*`` a loader exports is one Electron
  reads (source scan), and both loaders hand a recording fake desktop app the same, hand-written
  environment over a matrix of flags. Only a bare tag (no ``/`` and no ``:``) becomes an
  ``idossha/ti-toolbox`` reference; ``tit:dev`` is a local image, kept on every path.

Input validation lives in ``tests/test_launcher_input_validation.py``.

Run: python -m pytest tests/test_launch_contract.py -q
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tit import launch

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
LOADER_SH = ROOT / "loader.sh"

HASH_ROWS = json.loads((FIXTURES / "project_hash.json").read_text(encoding="utf-8"))[
    "rows"
]
SESSION_ROWS = json.loads(
    (FIXTURES / "session_labels.json").read_text(encoding="utf-8")
)["rows"]
CONFIG_ROWS = json.loads(
    (FIXTURES / "user_config_dirs.json").read_text(encoding="utf-8")
)["rows"]


def _shell_function(name: str) -> str:
    """One top-level function of loader.sh, verbatim (``name() {`` through the closing ``}``)."""
    match = re.search(
        rf"^{name}\(\) \{{\n.*?^\}}\n",
        LOADER_SH.read_text(encoding="utf-8"),
        re.S | re.M,
    )
    assert match, f"loader.sh has no top-level {name}() function"
    return match.group(0)


def _bashes() -> list[str]:
    found = ["/bin/bash"] if Path("/bin/bash").is_file() else []
    path_bash = shutil.which("bash")
    if path_bash and Path(path_bash).resolve() not in {
        Path(b).resolve() for b in found
    }:
        found.append(path_bash)
    return found


def _utf8_locale() -> str | None:
    """A UTF-8 locale this host has, or None (no ``locale`` binary in a minimal image)."""
    try:
        listing = subprocess.run(
            ["locale", "-a"], capture_output=True, text=True
        ).stdout.split()
    except OSError:
        return None
    for name in ("en_US.UTF-8", "en_US.utf8", "C.UTF-8", "C.utf8"):
        if name in listing:
            return name
    return None


UTF8_LOCALE = _utf8_locale()
LOCALES = ["C"] + ([UTF8_LOCALE] if UTF8_LOCALE else [])
SHELLS = [(bash, loc) for bash in _bashes() for loc in LOCALES]


def test_the_tables_have_rows_to_check():
    assert len(HASH_ROWS) >= 10
    assert any(ord(ch) > 0xFFFF for row in HASH_ROWS for ch in row["path"])
    assert {row["session"] for row in SESSION_ROWS} == {True, False}
    assert {row["platform"] for row in CONFIG_ROWS} == {"linux", "darwin", "win32"}
    assert SHELLS, "no bash to run loader.sh with"


# ---------------------------------------------------------------------------------------
# Project identity
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("row", HASH_ROWS, ids=[row["label"] for row in HASH_ROWS])
def test_python_project_name_matches_the_table(row):
    assert launch.project_name(row["path"]) == row["name"]
    assert launch.container_name(row["path"]) == f"{row['name']}-tit-1"


@pytest.mark.parametrize(
    ("bash", "locale"), SHELLS, ids=[f"{b}-{loc}" for b, loc in SHELLS]
)
def test_loader_sh_project_stack_matches_the_table_in_any_locale(
    tmp_path, bash, locale
):
    """bash 3.2's ``printf "'c"`` returns one signed byte; under ``LC_ALL=C`` every bash does."""
    script = tmp_path / "project_stack.sh"
    script.write_text(_shell_function("project_stack"), encoding="utf-8")
    paths = [row["path"] for row in HASH_ROWS]
    result = subprocess.run(
        [
            bash,
            "-c",
            'set -euo pipefail; source "$0"; for p in "$@"; do project_stack "$p"; echo; done',
            str(script),
            *paths,
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": locale, "LANG": locale},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [row["name"] for row in HASH_ROWS]


# ---------------------------------------------------------------------------------------
# Session discovery
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "row", SESSION_ROWS, ids=[row["label"] for row in SESSION_ROWS]
)
def test_python_discovery_follows_the_session_table(monkeypatch, row):
    def fake_docker(*args, check=True):
        if args[0] == "ps":
            return subprocess.CompletedProcess(args, 0, "cid\n", "")
        info = [{"Id": "cid", "Name": "/x", "Config": {"Labels": row["labels"]}}]
        return subprocess.CompletedProcess(args, 0, json.dumps(info), "")

    monkeypatch.setattr(launch, "_docker", fake_docker)
    assert bool(launch.find_running_containers()) is row["session"]


def _docker_ps_line(cid: str, labels: dict[str, str], *, reverse: bool) -> str:
    """``docker ps --format '{{.ID}}|{{.Names}}|{{.Image}}|{{.Labels}}'``: Go map order is random."""
    pairs = [f"{k}={v}" for k, v in labels.items()]
    return f"{cid}|ti-toolbox-name|idossha/ti-toolbox:v3.1.1|{','.join(reversed(pairs) if reverse else pairs)}"


@pytest.mark.parametrize("reverse", [False, True], ids=["label-order", "reversed"])
def test_loader_sh_discovery_follows_the_session_table(tmp_path, reverse):
    script = tmp_path / "session_ids.sh"
    script.write_text(_shell_function("session_ids"), encoding="utf-8")
    lines = [
        _docker_ps_line(f"c{index}", row["labels"], reverse=reverse)
        for index, row in enumerate(SESSION_ROWS)
    ]
    result = subprocess.run(
        ["bash", "-c", 'set -euo pipefail; source "$0"; session_ids', str(script)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    expected = [f"c{i}" for i, row in enumerate(SESSION_ROWS) if row["session"]]
    assert result.stdout.split() == expected


# ---------------------------------------------------------------------------------------
# User config dir
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("row", CONFIG_ROWS, ids=[row["label"] for row in CONFIG_ROWS])
def test_python_user_config_path_follows_the_table(row):
    env = {k: row[k] for k in ("XDG_CONFIG_HOME", "APPDATA") if row.get(k) is not None}
    assert (
        launch.user_config_path(
            host_platform=row["platform"], env=env, home=row["home"]
        )
        == row["expected"]
    )


def test_python_user_config_dir_creates_the_resolved_directory(tmp_path, monkeypatch):
    if (
        launch.sys.platform == "win32"
    ):  # pragma: no cover - %APPDATA%, covered by the table
        pytest.skip("Windows resolves %APPDATA%, covered by the table")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    created = launch.user_config_dir()
    assert created == tmp_path / ".config" / "ti-toolbox" and created.is_dir()


POSIX_CONFIG_ROWS = [row for row in CONFIG_ROWS if row["platform"] != "win32"]
# What bash itself sets OSTYPE to on each platform; an inherited value is kept.
OSTYPE = {"darwin": "darwin24", "linux": "linux-gnu"}


@pytest.mark.parametrize(
    "row", POSIX_CONFIG_ROWS, ids=[row["label"] for row in POSIX_CONFIG_ROWS]
)
def test_loader_sh_user_config_dir_follows_the_table(tmp_path, row):
    """loader.sh never runs on native Windows (WSL is Linux to it), so those rows are Python/TS only."""
    script = tmp_path / "user_config_dir.sh"
    script.write_text(_shell_function("user_config_dir"), encoding="utf-8")
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": row["home"],
        "OSTYPE": OSTYPE[row["platform"]],
    }
    env.update(
        {k: row[k] for k in ("XDG_CONFIG_HOME", "APPDATA") if row.get(k) is not None}
    )
    result = subprocess.run(
        ["bash", "-c", 'set -euo pipefail; source "$0"; user_config_dir', str(script)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == row["expected"]


# ---------------------------------------------------------------------------------------
# One container definition (tests/fixtures/launch_contract.json)
# ---------------------------------------------------------------------------------------

CONTRACT = json.loads((FIXTURES / "launch_contract.json").read_text(encoding="utf-8"))[
    "cases"
]


def _leg(value, leg: str):
    """A fixture value, or its ``{python, ts}`` spelling for one launcher."""
    return value[leg] if isinstance(value, dict) else value


def _expected_env(case: dict, leg: str) -> dict[str, str]:
    return {k: _leg(v, leg) for k, v in case["expected"]["environment"].items()}


def _argv_values(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, part in enumerate(argv[:-1]) if part == flag]


def test_contract_names_come_from_the_generated_hash_table():
    by_path = {row["path"]: row["name"] for row in HASH_ROWS}
    for case in CONTRACT:
        name = by_path[case["input"]["host_project_dir"]]
        assert case["expected"]["labels"]["tit.project"] == name
        assert case["expected"]["container_name"] == f"{name}-tit-1"


@pytest.mark.parametrize("case", CONTRACT, ids=[case["label"] for case in CONTRACT])
def test_python_run_argv_realises_the_contract(monkeypatch, case):
    given = case["input"]
    monkeypatch.delenv("TIT_COMPOSE_FILE", raising=False)
    monkeypatch.setenv("TZ", given["timezone"])
    monkeypatch.setenv("TIT_NO_TELEMETRY", given["no_telemetry"])
    monkeypatch.setattr(
        launch.platform, "system", lambda: _leg(given["host_os"], "python")
    )
    monkeypatch.setattr(launch.platform, "release", lambda: given["host_os_version"])
    monkeypatch.setattr(launch.platform, "machine", lambda: given["host_arch"])
    env = launch.build_env(
        host_project_dir=given["host_project_dir"],
        port=given["port"],
        token=given["token"],
        user_config=given["user_config"],
        image_tag="v3.1.1",
        repo_dir=given["repo_dir"],
        static_dir=given["static_dir"],
        server_reload=given["server_reload"],
    )
    argv = launch.build_run_argv(
        launch.load_spec(),
        env,
        host_project_dir=given["host_project_dir"],
        image="idossha/ti-toolbox:v3.1.1",
    )
    expected = case["expected"]
    assert _argv_values(argv, "--name") == [expected["container_name"]]
    labels = dict(pair.split("=", 1) for pair in _argv_values(argv, "--label"))
    assert labels == expected["labels"]
    environment = dict(pair.split("=", 1) for pair in _argv_values(argv, "--env"))
    assert environment == _expected_env(case, "python")
    assert _argv_values(argv, "--volume") == expected["volumes"]
    assert _argv_values(argv, "--publish") == [expected["publish"]]


def _port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) != 0


POSIX_CONTRACT = [case for case in CONTRACT if not case.get("windows")]
FAKE_COMPOSE_DOCKER = """#!/bin/bash
case "$1" in
 info|ps|image|pull|logs|rm) exit 0 ;;
 run) exit 125 ;;
 compose)
   [ "$2" != version ] || exit 0
   [[ "$*" != *'config --quiet'* ]] || exit 0
   env > "$CAPTURE/env"
   printf '%s\\n' "$@" > "$CAPTURE/args"
   prev=''; for arg in "$@"; do [ "$prev" != -f ] || cp "$arg" "$CAPTURE/compose.yml"; prev="$arg"; done
   echo cid ;;
 *) exit 99 ;;
esac
"""


def _loader_sh_compose_run(
    tmp_path: Path,
    given: dict,
    *,
    arguments: tuple[str, ...] = (),
    environment: dict[str, str] | None = None,
) -> tuple[Path, dict[str, str], launch.StackSpec, list[str]]:
    """Run loader.sh's browser start under the fake docker of ``FAKE_COMPOSE_DOCKER``.

    Returns the project directory, the environment ``docker compose run`` got, the YAML
    loader.sh rewrote, and the compose arguments. ``HOME`` is ``<tmp_path>/home`` and every
    inherited ``TIT_``/``XDG_``/``WSL_`` variable is dropped unless ``environment`` sets it.
    """
    if not _port_is_free(given["port"]):
        pytest.skip(f"port {given['port']} is taken on this host; loader.sh moves on")
    project = tmp_path / "My Data"
    project.mkdir()
    project = project.resolve()
    capture = tmp_path / "capture"
    capture.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(FAKE_COMPOSE_DOCKER)
    (bin_dir / "curl").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "uname").write_text(
        "#!/bin/sh\n"
        f'case "$1" in -r) echo {given["host_os_version"]} ;;'
        f' -m) echo {given["host_arch"]} ;; *) echo Darwin ;; esac\n'
    )
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("TIT_", "XDG_", "WSL_"))
    }
    env.update(
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        CAPTURE=str(capture),
        HOME=str(tmp_path / "home"),
        TZ=given["timezone"],
        TIT_NO_TELEMETRY=given["no_telemetry"],
        TIT_DEV_NO_BUILD="1",
        **(environment or {}),
    )
    dev = ["--dev", str(ROOT)] if given["repo_dir"] else []
    result = subprocess.run(
        ["bash", str(LOADER_SH), *dev, "--project", str(project), "--no-open"]
        + ["--port", str(given["port"]), *arguments],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    captured = dict(
        line.split("=", 1)
        for line in (capture / "env").read_text().splitlines()
        if "=" in line
    )
    spec = launch.parse_compose((capture / "compose.yml").read_text())
    args = (capture / "args").read_text().splitlines()
    return project, captured, spec, args


@pytest.mark.parametrize(
    "case", POSIX_CONTRACT, ids=[case["label"] for case in POSIX_CONTRACT]
)
def test_loader_sh_compose_run_realises_the_contract(tmp_path, case):
    """Fake docker captures the environment ``docker compose run`` gets and the rewritten YAML.

    Interpolating that YAML with that environment is what Compose would do; it shows the
    user's ``TIT_NO_TELEMETRY`` and ``TZ`` reach the container from bash too.
    """
    given = case["input"]
    project, captured, spec, args = _loader_sh_compose_run(tmp_path, given)
    real = {
        "/Users/x/My Data": str(project),
        "/Users/x/.config/ti-toolbox": str(
            tmp_path / "home" / ".config" / "ti-toolbox"
        ),
        "/Users/x/TI-toolbox": str(ROOT),
    }

    def localise(text: str) -> str:
        for fixture_path, actual in real.items():
            text = text.replace(fixture_path, actual)
        return text

    token = captured["TIT_SERVER_TOKEN"]
    assert re.fullmatch(r"[0-9a-f]{64}", token)
    expected_env = {k: localise(v) for k, v in _expected_env(case, "bash").items()}
    expected_env["TIT_SERVER_TOKEN"] = token
    environment = {
        key: launch.interpolate(template, captured)
        for key, template in spec.environment
    }
    assert environment == expected_env
    assert [launch.interpolate(v, captured) for v in spec.volumes] == [
        localise(v) for v in case["expected"]["volumes"]
    ]
    assert [launch.interpolate(p, captured) for p in spec.ports] == [
        case["expected"]["publish"]
    ]
    assert _argv_values(args, "--name") == [launch.container_name(str(project))]
    assert dict(pair.split("=", 1) for pair in _argv_values(args, "--label")) == {
        "tit.project": launch.project_name(str(project)),
        "tit.stack": "ti-toolbox-v3",
        "tit.service": "tit",
        "tit.host_project_dir": str(project),
    }


USER_RUN = next(
    case["input"] for case in POSIX_CONTRACT if not case["input"]["repo_dir"]
)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("tit:dev", "tit:dev"),
        ("v3.0.0", "idossha/ti-toolbox:v3.0.0"),
        ("example/custom:tag", "example/custom:tag"),
    ],
    ids=["local name:tag", "bare tag", "repository:tag"],
)
def test_loader_sh_runs_the_image_it_was_given(tmp_path, given, expected):
    """Only a bare tag (no ``/`` and no ``:``) names a release of idossha/ti-toolbox.

    ``--image tit:dev`` is a local image (the flag's metavar is ``IMAGE:TAG``); prefixing it
    gave the invalid reference ``idossha/ti-toolbox:tit:dev``.
    """
    _, _, spec, _ = _loader_sh_compose_run(
        tmp_path, USER_RUN, arguments=("--image", given)
    )
    assert spec.image == expected


# The host directory mounted at /root/.config/ti-toolbox, through the code path that mounts
# it (not only the helper). Expected: the table in docs/wiki/telemetry.md (macOS
# ~/.config/ti-toolbox always; Linux ${XDG_CONFIG_HOME:-~/.config}/ti-toolbox). HOME and
# XDG_CONFIG_HOME are set to different directories, so honouring XDG on macOS (the old
# launcher rule) or mounting any other directory gives a different answer on every host.
CONFIG_MOUNT = ":/root/.config/ti-toolbox"
PLATFORM_CONFIG = (
    {  # host -> (bash's own OSTYPE there, the expected dir under tmp_path)
        "darwin": ("darwin24", ("home", ".config", "ti-toolbox")),
        "linux": ("linux-gnu", ("xdg", "ti-toolbox")),
    }
)


def _mounted_config(volumes) -> list[str]:
    return [v[: -len(CONFIG_MOUNT)] for v in volumes if v.endswith(CONFIG_MOUNT)]


@pytest.mark.parametrize("host", sorted(PLATFORM_CONFIG))
def test_loader_sh_mounts_the_documented_config_dir(tmp_path, host):
    """bash keeps an inherited ``OSTYPE``, so the macOS and Linux rules both run on any host."""
    ostype, parts = PLATFORM_CONFIG[host]
    expected = tmp_path.joinpath(*parts)
    project, captured, spec, _ = _loader_sh_compose_run(
        tmp_path,
        USER_RUN,
        environment={"OSTYPE": ostype, "XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    volumes = [launch.interpolate(v, captured) for v in spec.volumes]
    assert _mounted_config(volumes) == [str(expected)]
    # The same directory remembers the project for the next interactive start.
    assert (expected / "last-project.txt").read_text() == f"{project}\n"


@pytest.mark.parametrize("host", sorted(PLATFORM_CONFIG))
def test_python_start_mounts_the_documented_config_dir(tmp_path, monkeypatch, host):
    if os.name == "nt":  # pragma: no cover - the table covers %APPDATA%
        pytest.skip("a Windows host mounts %APPDATA%\\ti-toolbox, covered by the table")
    expected = tmp_path.joinpath(*PLATFORM_CONFIG[host][1])
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(launch.sys, "platform", host)
    calls = []

    def fake_docker(*args, check=True):
        calls.append(args)
        stdout = "new-id" if args[0] == "run" else ""
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(launch, "_docker", fake_docker)
    monkeypatch.setattr(launch, "probe_container_gpu", lambda *a, **k: False)
    monkeypatch.setattr(launch, "wait_for_health", lambda *a, **k: None)
    monkeypatch.setattr(launch, "find_free_port", lambda preferred: preferred)
    project = tmp_path / "project"
    project.mkdir()
    launch.start(
        launch.LaunchOptions(
            project=str(project), image="example/custom:tag", echo=lambda *_: None
        )
    )
    (run,) = [call for call in calls if call[0] == "run"]
    assert _mounted_config(_argv_values(list(run), "--volume")) == [str(expected)]
    assert expected.is_dir()


# ---------------------------------------------------------------------------------------
# The launcher -> Electron hand-off
# ---------------------------------------------------------------------------------------


def _produced_by_loader_sh() -> set[str]:
    names = set()
    for exported in re.findall(
        r"\bexport\s+([^;\n]*)", LOADER_SH.read_text(encoding="utf-8")
    ):
        names |= set(re.findall(r"\b(TIT_LAUNCH_\w+|TIT_DEV_REPO_DIR)\b", exported))
    return names


def _produced_by_cli() -> set[str]:
    text = (ROOT / "tit" / "cli.py").read_text(encoding="utf-8")
    return set(re.findall(r'env\["(TIT_LAUNCH_\w+|TIT_DEV_REPO_DIR)"\]\s*=', text))


def _read_by_desktop_main() -> set[str]:
    names = set()
    for source in (ROOT / "desktop" / "src" / "main").rglob("*.ts"):
        names |= set(
            re.findall(
                r"""(?:process\.env\.|process\.env\[["']|FromEnv\(["'])"""
                r"(TIT_LAUNCH_\w+|TIT_DEV_REPO_DIR)",
                source.read_text(encoding="utf-8"),
            )
        )
    return names


def test_every_handoff_variable_a_loader_sets_is_read_by_electron_and_back():
    """A variable renamed on one side would be dropped without an error on the other.

    ``TIT_LAUNCH_CONTAINER_ID`` is the one Electron reads that no loader sets:
    ``desktop/scripts/dev.ts`` sets it, and both loaders clear it.
    """
    read = _read_by_desktop_main()
    assert {"TIT_LAUNCH_PROJECT_DIR", "TIT_LAUNCH_IMAGE", "TIT_DEV_REPO_DIR"} <= read
    assert _produced_by_loader_sh() == read - {"TIT_LAUNCH_CONTAINER_ID"}
    assert _produced_by_cli() == read - {"TIT_LAUNCH_CONTAINER_ID"}


UNSET = None
# The compose default, read from the spec itself rather than from either launcher.
DEFAULT_IMAGE = "idossha/ti-toolbox:" + re.search(
    r"image: idossha/ti-toolbox:\$\{TIT_IMAGE_TAG:-([^}]+)\}",
    (ROOT / "docker-compose.yml").read_text(encoding="utf-8"),
).group(1)
BASE_HANDOFF = {
    "TIT_LAUNCH_PROJECT_DIR": UNSET,
    "TIT_LAUNCH_PORT": "8765",
    "TIT_LAUNCH_TIMEOUT": "180",
    "TIT_LAUNCH_IMAGE": DEFAULT_IMAGE,
    "TIT_LAUNCH_EXISTING": "",
    "TIT_LAUNCH_CONTAINER": "",
    "TIT_LAUNCH_CONTAINER_ID": UNSET,
    "TIT_IMAGE_TAG": UNSET,
    "TIT_DEV_REPO_DIR": UNSET,
    "TIT_NO_TELEMETRY": UNSET,
    "ELECTRON_RUN_AS_NODE": UNSET,
}
# name -> (arguments, extra environment, differences from BASE_HANDOFF); {project} is tmp_path.
HANDOFF_CASES = {
    "no flags": ([], {}, {}),
    "project": (
        ["--project", "{project}"],
        {},
        {"TIT_LAUNCH_PROJECT_DIR": "{project}"},
    ),
    "image": (
        ["--image", "example/custom:tag"],
        {},
        {"TIT_LAUNCH_IMAGE": "example/custom:tag"},
    ),
    "image as a bare tag": (
        ["--image", "v3.0.0"],
        {},
        {"TIT_LAUNCH_IMAGE": "idossha/ti-toolbox:v3.0.0"},
    ),
    "image named locally": (
        ["--image", "tit:dev"],
        {},
        {"TIT_LAUNCH_IMAGE": "tit:dev"},
    ),
    "TIT_IMAGE_TAG bare": (
        [],
        {"TIT_IMAGE_TAG": "v3.0.0"},
        {"TIT_LAUNCH_IMAGE": "idossha/ti-toolbox:v3.0.0"},
    ),
    "TIT_IMAGE_TAG full": (
        [],
        {"TIT_IMAGE_TAG": "example/custom:v9"},
        {"TIT_LAUNCH_IMAGE": "example/custom:v9"},
    ),
    "port": (["--port", "9000"], {}, {"TIT_LAUNCH_PORT": "9000"}),
    "port with a leading zero": (["--port", "09000"], {}, {"TIT_LAUNCH_PORT": "9000"}),
    "timeout rounds up to whole seconds": (
        ["--timeout", "30.5"],
        {},
        {"TIT_LAUNCH_TIMEOUT": "31"},
    ),
    # str(float) spells these 1e-05 and 1e+16; the text must be read once, as loader.sh does.
    "timeout under a second rounds up to one": (
        ["--timeout", "0.00001"],
        {},
        {"TIT_LAUNCH_TIMEOUT": "1"},
    ),
    # Linux CI runs loader.sh under mawk, whose print spells whole numbers from 2^31 up as
    # %.6g (1e+16, 4.29497e+09), which bash's [ -gt ] refuses; macOS awk prints every digit.
    "timeout of seventeen digits": (
        ["--timeout", "10000000000000000"],
        {},
        {"TIT_LAUNCH_TIMEOUT": "10000000000000000"},
    ),
    "timeout past 2^32 rounds up": (
        ["--timeout", "4294967296.5"],
        {},
        {"TIT_LAUNCH_TIMEOUT": "4294967297"},
    ),
    "existing session": (
        ["--existing", "attach", "--container", "c"],
        {},
        {"TIT_LAUNCH_EXISTING": "attach", "TIT_LAUNCH_CONTAINER": "c"},
    ),
    "telemetry opt-out": ([], {"TIT_NO_TELEMETRY": "1"}, {"TIT_NO_TELEMETRY": "1"}),
}
RECORDING_APP = """#!/bin/sh
: > "$DUMP"
for k in {names}; do
  eval "present=\\${{$k+1}} value=\\${{$k-}}"
  if [ -n "$present" ]; then printf '%s=%s\\n' "$k" "$value" >> "$DUMP"; fi
done
"""


@pytest.mark.parametrize("case", sorted(HANDOFF_CASES), ids=sorted(HANDOFF_CASES))
@pytest.mark.parametrize("loader", ["loader.sh", "loader.py"])
def test_both_loaders_hand_electron_the_contract_environment(tmp_path, loader, case):
    """``TIT_LAUNCH_IMAGE`` is a full reference, ``TIT_IMAGE_TAG`` never reaches Electron, the
    timeout is whole seconds, and the user's telemetry opt-out passes through unchanged.
    """
    arguments, extra, differences = HANDOFF_CASES[case]
    project = str(tmp_path.resolve())
    dump = tmp_path / "electron-env"
    app = tmp_path / "fake-desktop-app"
    app.write_text(RECORDING_APP.format(names=" ".join(BASE_HANDOFF)))
    app.chmod(0o755)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("TIT_", "WSL_", "ELECTRON_"))
    }
    env.update(
        TIT_ELECTRON_EXECUTABLE=str(app),
        DUMP=str(dump),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        HOME=str(tmp_path / "home"),
        ELECTRON_RUN_AS_NODE="1",
        TIT_LAUNCH_CONTAINER_ID="stale",
        **extra,
    )
    command = ["bash"] if loader == "loader.sh" else [sys.executable]
    result = subprocess.run(
        [*command, str(ROOT / loader), *(a.format(project=project) for a in arguments)],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    recorded = dict(line.split("=", 1) for line in dump.read_text().splitlines())
    expected = {
        k: v.format(project=project)
        for k, v in {**BASE_HANDOFF, **differences}.items()
        if v is not UNSET
    }
    assert recorded == expected
