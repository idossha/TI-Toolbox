"""Both loaders refuse a bad port, timeout or project alike, before any Docker call (2026-10-22).

The rules and sentences are the ones ``loader.sh`` enforced first: a port is decimal digits
naming 1-65535 (``08765`` is 8765), a timeout is ``N`` or ``N.N`` seconds above zero, and a
project is neither the filesystem root nor a path holding ``:`` or a newline (a Docker bind
source cannot). ``python loader.py`` used to print port 0, raise an uncaught ``OverflowError``
for ``--port -5``, accept ``--timeout -3``, and for ``--project /`` stop and remove the
selected container on ``--existing recreate`` before crashing with a traceback.

Expected values are those rules, written down by hand; nothing is derived from either loader.
Each case runs both loaders, with ``--print-config`` and as a browser start
(``--existing recreate --container X``), under a fake ``docker`` that records every call.

Run: python -m pytest tests/test_launcher_input_validation.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tit import launch

ROOT = Path(__file__).resolve().parents[1]

PORT = "port must be 1–65535"
SECONDS = "timeout must be positive seconds"
POSITIVE = "timeout must be positive"
ROOT_DIR = "choose a project directory, not the filesystem root"
COLON = "project path cannot contain newlines or colons"

# name -> (arguments, the refusal); "{project}" is a valid directory, "{colon}" one named a:b,
# "{newline}" one whose name holds a newline.
BAD = {
    "port 0": (["--port", "0"], PORT),
    "port 00": (["--port", "00"], PORT),
    "port -5": (["--port", "-5"], PORT),
    "port 65536": (["--port", "65536"], PORT),
    "port 99999": (["--port", "99999"], PORT),
    "port 1.5": (["--port", "1.5"], PORT),
    "port abc": (["--port", "abc"], PORT),
    "timeout -3": (["--timeout", "-3"], SECONDS),
    "timeout abc": (["--timeout", "abc"], SECONDS),
    "timeout nan": (["--timeout", "nan"], SECONDS),
    "timeout 1e3": (["--timeout", "1e3"], SECONDS),
    "timeout 0": (["--timeout", "0"], POSITIVE),
    "timeout 0.0": (["--timeout", "0.0"], POSITIVE),
    "project /": (["--project", "/"], ROOT_DIR),
    "project with a colon": (["--project", "{colon}"], COLON),
    "project with a newline": (["--project", "{newline}"], COLON),
}
MODES = {
    "print-config": ["--print-config", "--no-open"],
    "start": ["--no-open", "--existing", "recreate", "--container", "X"],
}
LOADERS = {"loader.sh": ["bash"], "loader.py": [sys.executable]}


def _environment(tmp_path: Path) -> tuple[dict[str, str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    docker = bin_dir / "docker"
    docker.write_text('#!/bin/sh\nprintf \'%s\\n\' "$*" >> "$DOCKER_LOG"\nexit 0\n')
    docker.chmod(0o755)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("TIT_", "WSL_", "XDG_"))
    }
    env.update(
        PATH=f"{bin_dir}:{os.environ['PATH']}",
        DOCKER_LOG=str(log),
        XDG_CONFIG_HOME=str(tmp_path / "config"),
        HOME=str(tmp_path / "home"),
        TIT_RELEASE_BASE_URL="file:///nonexistent",
    )
    return env, log


@pytest.mark.parametrize("mode", sorted(MODES))
@pytest.mark.parametrize("case", sorted(BAD), ids=sorted(BAD))
@pytest.mark.parametrize("loader", sorted(LOADERS))
def test_bad_input_is_refused_in_one_line_before_docker(tmp_path, loader, case, mode):
    arguments, refusal = BAD[case]
    project = tmp_path / "project"
    project.mkdir()
    colon = tmp_path / "a:b"
    colon.mkdir()
    newline = tmp_path / "a\nb"
    newline.mkdir()
    if "--project" not in arguments:
        arguments = [*arguments, "--project", "{project}"]
    arguments = [
        a.format(project=project, colon=colon, newline=newline) for a in arguments
    ]
    env, log = _environment(tmp_path)
    result = subprocess.run(
        [*LOADERS[loader], str(ROOT / loader), *arguments, *MODES[mode]],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    lines = result.stderr.strip().splitlines()
    assert len(lines) == 1 and "Traceback" not in result.stderr, result.stderr
    assert lines[0].endswith(f": {refusal}"), lines[0]
    assert not log.exists(), log.read_text()


@pytest.mark.parametrize("loader", sorted(LOADERS))
def test_a_leading_zero_port_is_decimal_in_both_loaders(tmp_path, loader):
    """bash arithmetic reads 08765 as octal ("value too great for base"); Python's int does not."""
    env, _ = _environment(tmp_path)
    result = subprocess.run(
        [*LOADERS[loader], str(ROOT / loader), "--print-config", "--no-open"]
        + ["--project", str(tmp_path), "--port", "08765"],
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "port      8765\n" in result.stdout
    assert "origin    http://127.0.0.1:8765\n" in result.stdout


@pytest.mark.parametrize("bad", ["/", "{colon}"], ids=["root", "colon"])
def test_recreate_of_an_invalid_project_touches_no_container(
    tmp_path, monkeypatch, bad
):
    """The selected session X must survive: validation comes before stop and rm."""
    colon = tmp_path / "a:b"
    colon.mkdir()
    project = bad.format(colon=colon)
    session = {
        "Id": "X",
        "Name": "/ti-toolbox-x-tit-1",
        "Config": {
            "Image": "idossha/ti-toolbox:v3.1.1",
            "Labels": {
                "tit.stack": "ti-toolbox-v3",
                "tit.service": "tit",
                "tit.host_project_dir": os.path.realpath(project),
            },
            "Env": [],
        },
        "State": {"Running": True},
    }
    calls = []

    def fake_docker(*args, check=True):
        calls.append(args)
        listing = "" if "--all" in args else "X\n"
        stdout = {"ps": listing, "inspect": json.dumps([session])}.get(args[0], "")
        return subprocess.CompletedProcess(args, 0, stdout, "")

    monkeypatch.setattr(launch, "_docker", fake_docker)
    monkeypatch.setattr(launch, "probe_container_gpu", lambda *a, **k: False)
    options = launch.LaunchOptions(
        project=project,
        existing="recreate",
        container="X",
        image="example/custom:tag",
        echo=lambda *_: None,
    )
    with pytest.raises(launch.LaunchError, match=ROOT_DIR if bad == "/" else COLON):
        launch.start(options)
    assert calls == []


@pytest.mark.parametrize("preferred", [0, -5, 65536])
def test_find_free_port_refuses_a_port_outside_the_range(preferred):
    """0 would bind "any port" and return 0; -5 raised OverflowError from bind()."""
    with pytest.raises(launch.LaunchError, match=PORT):
        launch.find_free_port(preferred)
