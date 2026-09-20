"""Release runner keeps failed/inconclusive commands red and captures their output."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location(
    "verify_release", Path(__file__).resolve().parents[1] / "dev/verify_release.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.mark.parametrize("status", [1, 2, 5])
def test_failed_or_inconclusive_stage_is_not_a_pass(tmp_path, status):
    with pytest.raises(subprocess.CalledProcessError) as exc:
        gate.run_stage(
            "check",
            [sys.executable, "-c", f'print("evidence"); exit({status})'],
            tmp_path,
            tmp_path,
            dict(os.environ),
        )
    assert exc.value.returncode == status
    assert (tmp_path / "check.log").read_text() == "evidence\n"


def test_pass_records_real_exit_code(tmp_path):
    record = gate.run_stage(
        "check",
        [sys.executable, "-c", 'print("passed")'],
        tmp_path,
        tmp_path,
        dict(os.environ),
    )
    assert record["exit_code"] == 0
    assert record["seconds"] >= 0
    assert (tmp_path / "check.log").read_text() == "passed\n"


def test_missing_executable_records_failure(tmp_path):
    records = []
    with pytest.raises(subprocess.CalledProcessError) as exc:
        gate.run_stage(
            "missing",
            [str(tmp_path / "absent")],
            tmp_path,
            tmp_path,
            dict(os.environ),
            records,
        )
    assert exc.value.returncode == 127
    assert records[0]["stage"] == "missing"
    assert records[0]["exit_code"] == 127
    assert "Cannot start stage" in (tmp_path / "missing.log").read_text()


@pytest.mark.parametrize("failure", [2, 127])
def test_gate_failure_still_restores_build_and_writes_receipt(
    tmp_path, monkeypatch, failure
):
    import json

    out = tmp_path / "evidence"
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_release.py",
            "--image",
            "candidate",
            "--container",
            "copied-stack",
            "--notebook-project",
            str(tmp_path / "project"),
            "--package",
            str(tmp_path / "app"),
            "--real-spec",
            "real.spec.ts",
            "--smoke-row",
            "sim",
            "--out",
            str(out),
        ],
    )
    for key in ("TIT_E2E_PROJECT_HOST", "TIT_E2E_SERVER_URL", "TIT_E2E_TOKEN"):
        monkeypatch.setenv(key, "fixture")

    def inspect(command, **kwargs):
        if command[:2] == ["git", "status"]:
            return ""
        if command[:2] == ["git", "rev-parse"]:
            return "candidate-sha\n"
        if command[:3] == ["docker", "image", "inspect"]:
            return "sha256:immutable\n"
        return json.dumps(
            {
                "id": "container-id",
                "image_id": "server-image-id",
                "mounts": [{"Destination": "/ti-toolbox", "Source": str(gate.ROOT)}],
            }
        )

    monkeypatch.setattr(gate.subprocess, "check_output", inspect)
    monkeypatch.setattr(gate.fcntl, "flock", lambda *args: None)
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            if failure == 127:
                raise FileNotFoundError("missing test executable")
            return subprocess.CompletedProcess(command, failure)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(gate.subprocess, "run", execute)
    assert gate.main() == 1
    assert calls[-1] == ["npm", "run", "build"]
    assert len(calls) == 2
    receipt = json.loads((out / "receipt.json").read_text())
    assert receipt["status"] == "failed"
    assert receipt["stages"][0]["exit_code"] == failure
    assert receipt["stages"][-1]["stage"] == "final-build"
    assert receipt["container"]["id"] == "container-id"
