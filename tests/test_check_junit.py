"""Self-tests for dev/check_junit.py: a leg that skipped, collected nothing or broke is red.

What this pins
    Each rule driven red with a fixture report: zero collected, a planted skip, a skip whose
    test is allowed but whose reason changed, an error, a failure; the degraded modes (missing
    file, not XML, not JUnit) exit 2; a clean report exits 0. One report is written by pytest
    itself in a subprocess, so the reader is checked against the real format, not only
    against XML typed here.

Where the expectations come from
    The rules in the guard's docstring; the counts are the fixtures' own testcase elements.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_junit", ROOT / "dev" / "check_junit.py"
)
check_junit = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("check_junit", check_junit)  # dataclasses resolve their module
_spec.loader.exec_module(check_junit)


def _report(tmp_path: Path, cases: str, name: str = "report.xml") -> str:
    path = tmp_path / name
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
        + cases
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return str(path)


PASS = '<testcase classname="tests.numerical.test_a" name="test_ok" time="0.1"/>'
ENV_SKIP = (
    '<testcase classname="tests.numerical.test_dti_real" name="test_tensor">'
    '<skipped type="pytest.skip" message="skipping: TIT_DTI_REAL (Dataset 000 root) is unset"/>'
    "</testcase>"
)


def test_a_clean_report_passes(tmp_path, capsys):
    assert check_junit.main(["--leg", "no-skips", _report(tmp_path, PASS * 3)]) == 0
    assert "3 collected, 3 passed, 0 skipped" in capsys.readouterr().out


def test_a_report_with_no_tests_fails(tmp_path, capsys):
    assert check_junit.main(["--leg", "numerical-image", _report(tmp_path, "")]) == 1
    assert "no tests were collected" in capsys.readouterr().out


def test_a_planted_skip_fails_and_is_named(tmp_path, capsys):
    planted = (
        '<testcase classname="tests.numerical.test_stats" name="test_p">'
        '<skipped type="pytest.skip" message="real scipy/nibabel not importable"/></testcase>'
    )
    report = _report(tmp_path, PASS + planted)
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    out = capsys.readouterr().out
    assert "tests.numerical.test_stats.test_p" in out
    assert "real scipy/nibabel not importable" in out


def test_an_allowed_skip_passes_only_on_its_leg(tmp_path):
    report = _report(tmp_path, PASS + ENV_SKIP)
    assert check_junit.main(["--leg", "numerical-image", report]) == 0
    assert check_junit.main(["--leg", "no-skips", report]) == 1


def test_an_allowed_test_skipping_for_another_reason_fails(tmp_path, capsys):
    other_reason = ENV_SKIP.replace(
        "TIT_DTI_REAL (Dataset 000 root) is unset", "nibabel is mocked"
    )
    report = _report(tmp_path, PASS + other_reason)
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    assert "nibabel is mocked" in capsys.readouterr().out


@pytest.mark.parametrize("tag, word", [("error", "error"), ("failure", "failed")])
def test_errors_and_failures_fail(tmp_path, capsys, tag, word):
    broken = (
        '<testcase classname="tests.numerical.test_warp" name="test_mirror">'
        f'<{tag} message="ValueError: Unable to avoid copy"/></testcase>'
    )
    report = _report(tmp_path, PASS + broken)
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
    assert f"{word}: tests.numerical.test_warp.test_mirror" in capsys.readouterr().out


def test_several_reports_are_checked_together(tmp_path):
    clean = _report(tmp_path, PASS, "a.xml")
    skipped = _report(tmp_path, ENV_SKIP, "b.xml")
    assert check_junit.main(["--leg", "numerical-image", clean, skipped]) == 0
    assert check_junit.main(["--leg", "no-skips", clean, skipped]) == 1


@pytest.mark.parametrize(
    "content",
    [None, "not xml <", "<html><body/></html>"],
    ids=["missing", "garbage", "html"],
)
def test_an_unreadable_report_is_could_not_check(tmp_path, capsys, content):
    path = tmp_path / "report.xml"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    assert check_junit.main(["--leg", "no-skips", str(path)]) == 2
    assert "cannot check" in capsys.readouterr().err


def test_a_report_pytest_wrote_is_read_with_its_skip(tmp_path, capsys):
    """pytest itself writes the XML: two passes, one skip whose reason names a variable."""
    module = tmp_path / "test_sample.py"
    module.write_text(
        "import pytest\n"
        "def test_one():\n    assert True\n"
        "@pytest.mark.parametrize('x', [1])\n"
        "def test_two(x):\n    assert x == 1\n"
        "def test_gated():\n    pytest.skip('TIT_SAMPLE is unset')\n",
        encoding="utf-8",
    )
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    report = tmp_path / "out.xml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(module),
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(tmp_path / "pytest.ini"),
            f"--junitxml={report}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert report.is_file(), result.stdout + result.stderr
    cases = check_junit.read_cases(report.read_text(encoding="utf-8"))
    assert sorted(c.outcome for c in cases) == ["passed", "passed", "skipped"]
    skipped = [c for c in cases if c.outcome == "skipped"][0]
    assert skipped.test.endswith("test_sample.test_gated")
    assert "TIT_SAMPLE is unset" in skipped.message
    assert check_junit.main(["--leg", "no-skips", str(report)]) == 1


def test_every_allowlist_entry_says_why():
    for leg, entries in check_junit.ALLOWLISTS.items():
        for entry in entries:
            # pytest ids start at tests/; Playwright's (the e2e leg) at the spec file.
            test_id = entry["test"]
            assert test_id.startswith("tests.") or (
                leg.startswith("e2e") and ".spec.ts." in test_id
            ), (leg, entry)
            assert entry["message"], (leg, entry)
            assert len(entry["why"]) > 20, (leg, entry)
    assert check_junit.ALLOWLISTS["no-skips"] == []
