"""The CircleCI ``desktop-e2e-mock`` job can go red, never reaches a real server, and keeps its reports.

What this pins (read off ``.circleci/config.yml``; the other side of each check is
read from the file it must agree with, not typed here):

* The guard step really fails when the variable that turns the mock server off is
  set. That variable is read from ``desktop/playwright.config.ts``
  (``const realServer = process.env.<VAR>``), and the guard's own shell is run.
* The Playwright step's verdict is ``dev/check_junit.py --leg e2e-mock``: it is the
  step's last command, nothing swallows its exit code, it reads the report
  Playwright was told to write, and ``e2e-mock`` is a leg check_junit knows.
  Playwright itself ends in ``|| true``, so without this the job is always green.
* Playwright runs the ``default`` project offscreen, under Xvfb, with a ``timeout``.
* Every ``store_test_results`` / ``store_artifacts`` step in every job has
  ``when: always``: the red runs are the ones whose JUnit, traces and screenshots
  are needed. The e2e job stores Playwright's ``outputDir`` (from the config).
* The job is opt-in: one workflow runs it, gated on the boolean pipeline parameter
  ``run_e2e_mock`` (default false), so no push or PR runs it until the Linux path in
  docs/dev/TESTING.md is done.

Reproduce: ``.venv/bin/python -m pytest tests/test_circleci_e2e_mock_job.py -q``.
Running the job itself needs CircleCI (Linux, Xvfb); that is not done here.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
CONFIG = yaml.safe_load((REPO / ".circleci" / "config.yml").read_text(encoding="utf-8"))
PLAYWRIGHT_CONFIG = (REPO / "desktop" / "playwright.config.ts").read_text(
    encoding="utf-8"
)
JOB = "desktop-e2e-mock"


def _steps(job: str) -> list[tuple[str, dict]]:
    """``(kind, body)`` per step; a bare string step (``checkout``) gets ``{}``."""
    steps = []
    for step in CONFIG["jobs"][job]["steps"]:
        if isinstance(step, str):
            steps.append((step, {}))
        else:
            ((kind, body),) = step.items()
            steps.append((kind, body if isinstance(body, dict) else {}))
    return steps


def _run_index(job: str, needle: str) -> int:
    hits = [
        i
        for i, (kind, body) in enumerate(_steps(job))
        if kind == "run" and needle in body.get("command", "")
    ]
    assert len(hits) == 1, f"{job}: {len(hits)} run steps contain {needle!r}"
    return hits[0]


def _logical_lines(command: str) -> list[str]:
    """Shell lines with ``\\`` continuations joined and comments/blank lines dropped."""
    joined = re.sub(r"\\\n\s*", " ", command)
    lines = []
    for line in joined.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def _real_server_variable() -> str:
    match = re.search(r"const realServer = process\.env\.(\w+);", PLAYWRIGHT_CONFIG)
    assert match, "playwright.config.ts no longer reads realServer from one variable"
    return match.group(1)


def _guard(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    command = _steps(JOB)[_run_index(JOB, "must never reach a real server")][1][
        "command"
    ]
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("TIT_E2E_") and k != "TIT_DATASET_000"
    }
    env.update(env_extra)
    return subprocess.run(
        ["bash", "-c", command], env=env, capture_output=True, text=True, timeout=30
    )


def test_the_guard_passes_with_no_real_server_configured() -> None:
    result = _guard({})
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    "variable", [_real_server_variable(), "TIT_E2E_TOKEN", "TIT_DATASET_000"]
)
def test_the_guard_fails_when_a_real_server_or_dataset_is_configured(
    variable: str,
) -> None:
    result = _guard({variable: "http://127.0.0.1:8765"})
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stdout.startswith(f"{variable} is set"), result.stdout


def test_the_guard_runs_before_playwright() -> None:
    assert _run_index(JOB, "must never reach a real server") < _run_index(
        JOB, "playwright test"
    )
    assert _run_index(JOB, "npm run pree2e") < _run_index(JOB, "playwright test")


def test_check_junit_decides_the_playwright_step() -> None:
    index = _run_index(JOB, "playwright test")
    kind, body = _steps(JOB)[index]
    lines = _logical_lines(body["command"])
    assert lines[0] == "set -euo pipefail", lines
    (playwright,) = [line for line in lines if "playwright test" in line]
    verdict = lines[-1]
    # The verdict is the last command and nothing turns its failure into success.
    assert lines.index(playwright) < len(lines) - 1, lines
    assert "||" not in verdict and "&&" not in verdict, verdict
    words = shlex.split(verdict)
    assert words[:4] == ["python3", "../dev/check_junit.py", "--leg", "e2e-mock"], words
    # It reads the report Playwright writes.
    report = re.search(r"PLAYWRIGHT_JUNIT_OUTPUT_NAME=(\S+)", playwright)
    assert report and words[4:] == [report.group(1)], (playwright, verdict)
    assert re.search(r"--reporter=\S*\bjunit\b", playwright), playwright
    # check_junit lives where the step's working directory points, and knows the leg.
    script = (REPO / body["working_directory"] / words[1]).resolve()
    assert script == REPO / "dev" / "check_junit.py"
    spec = importlib.util.spec_from_file_location("check_junit_for_ci_pin", script)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert "e2e-mock" in module.ALLOWLISTS


def test_playwright_runs_the_mock_project_offscreen_with_a_ceiling() -> None:
    (playwright,) = [
        line
        for line in _logical_lines(
            _steps(JOB)[_run_index(JOB, "playwright test")][1]["command"]
        )
        if "playwright test" in line
    ]
    assert "TIT_E2E_OFFSCREEN=1" in playwright
    assert "--project=default" in playwright
    assert re.search(r"\btimeout \d+m xvfb-run -a npx playwright test\b", playwright)
    assert "TIT_E2E_SERVER_URL" not in playwright


def test_every_store_step_runs_on_red_too() -> None:
    missing = [
        f"{job}: {kind} {body.get('path')}"
        for job in CONFIG["jobs"]
        for kind, body in _steps(job)
        if kind in ("store_test_results", "store_artifacts")
        and body.get("when") != "always"
    ]
    assert not missing, "store steps without `when: always`:\n" + "\n".join(missing)


def test_the_e2e_job_stores_its_junit_and_playwrights_output_dir() -> None:
    output_dir = re.search(r"outputDir: `([\w-]+)/", PLAYWRIGHT_CONFIG)
    assert output_dir, "playwright.config.ts outputDir moved"
    playwright_index = _run_index(JOB, "playwright test")
    after = _steps(JOB)[playwright_index + 1 :]
    stored = {(kind, body["path"]) for kind, body in after if "path" in body}
    assert ("store_test_results", "/tmp/test-results") in stored
    assert ("store_artifacts", f"desktop/{output_dir.group(1)}") in stored
    report = re.search(
        r"PLAYWRIGHT_JUNIT_OUTPUT_NAME=(\S+)",
        _steps(JOB)[playwright_index][1]["command"],
    )
    assert report and report.group(1).startswith("/tmp/test-results/")


def test_the_job_runs_only_when_a_pipeline_asks_for_it() -> None:
    runs_in = {}
    for name, workflow in CONFIG["workflows"].items():
        for entry in workflow.get("jobs", []):
            job = entry if isinstance(entry, str) else next(iter(entry))
            if job == JOB:
                runs_in[name] = workflow
    assert list(runs_in) == ["e2e_mock"], runs_in
    workflow = runs_in["e2e_mock"]
    assert workflow["when"] == "<< pipeline.parameters.run_e2e_mock >>", workflow
    assert "triggers" not in workflow, workflow
    assert CONFIG["parameters"]["run_e2e_mock"] == {"type": "boolean", "default": False}
