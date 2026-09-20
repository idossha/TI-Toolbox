"""The container runner must preserve Python signal semantics before PETSc loads."""

import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("existing", [None, "-ksp_monitor", "-no_signal_handler"])
def test_container_runner_disables_petsc_signal_handler(tmp_path, existing):
    binary = tmp_path / "simnibs_python"
    log = tmp_path / "calls.jsonl"
    binary.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['RUNNER_CALLS'], 'a') as stream:\n"
        "    stream.write(json.dumps({'args': sys.argv[1:], "
        "'petsc': os.environ.get('PETSC_OPTIONS', '')}) + '\\n')\n"
    )
    binary.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "RUNNER_CALLS": str(log),
    }
    env.pop("PETSC_OPTIONS", None)
    if existing is not None:
        env["PETSC_OPTIONS"] = existing
    subprocess.run(
        [
            "bash",
            str(Path(__file__).with_name("run_tests.sh")),
            "--verbose",
            "-k",
            "runner",
        ],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(calls) == 2
    assert calls[-1]["args"][:3] == ["-m", "pytest", "-v"]
    assert calls[-1]["args"][-2:] == ["-k", "runner"]
    options = calls[-1]["petsc"].split()
    assert options.count("-no_signal_handler") == 1
    if existing == "-ksp_monitor":
        assert "-ksp_monitor" in options
