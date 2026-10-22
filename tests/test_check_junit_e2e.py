"""``dev/check_junit.py --leg e2e-mock`` reads Playwright's JUnit report the way CI needs.

Playwright's JUnit reporter writes a skipped test as an empty ``<skipped>`` and puts the
reason in ``<properties><property name="skip" value="..."/>``. The CircleCI
``desktop-e2e-mock`` job hands that report to check_junit, so a skip must be matched on that
reason: the allowed packaged-launch skip passes only for *its* reason ("no packaged app"),
any other skipped spec fails, a failure fails, and an empty report fails.

The XML below is cut verbatim from the report of a full offscreen mock run
(``TIT_E2E_OFFSCREEN=1 PLAYWRIGHT_JUNIT_OUTPUT_NAME=... npx playwright test --project=default
--reporter=junit``, Playwright 1.62.1, 2026-10-22: 364 tests, 3 skipped), with the passing
case shortened. tests/test_check_junit.py covers the pytest legs.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

PACKAGED_SKIP = """<testcase name="packaged Docker launcher › opens usable Docker controls with the packaged version, stays hidden, and closes normally" classname="packaged-launch.spec.ts">
<properties>
<property name="skip" value="no packaged app under release/ — run npm run package:dir first">
</property>
</properties>
<skipped>
</skipped>
</testcase>"""

FILL_SKIP = """<testcase name="a deliberate pointer click is not inverted by the fill controller" classname="page-memory.spec.ts">
<properties>
<property name="skip" value="no run page currently renders a page-level collapsible fill section">
</property>
</properties>
<skipped>
</skipped>
</testcase>"""

PASSED = """<testcase name="changing another tab&apos;s subject preserves preprocessing and the live viewer session" classname="page-memory.spec.ts" time="1.374">
</testcase>"""


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_junit_e2e", REPO / "dev" / "check_junit.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_junit_e2e"] = module  # dataclasses resolve their module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def check_junit():
    return _load()


def _report(tmp_path: Path, *cases: str) -> str:
    body = "\n".join(cases)
    path = tmp_path / "e2e.xml"
    path.write_text(
        f'<testsuites id="" name="" tests="{len(cases)}">\n'
        f'<testsuite name="x.spec.ts" tests="{len(cases)}">\n{body}\n</testsuite>\n'
        "</testsuites>\n",
        encoding="utf-8",
    )
    return str(path)


def test_the_skip_reason_is_read_from_playwrights_skip_property(check_junit) -> None:
    (case,) = check_junit.read_cases(f"<testsuites>{PACKAGED_SKIP}</testsuites>")
    assert case.outcome == "skipped"
    assert case.test == (
        "packaged-launch.spec.ts.packaged Docker launcher › opens usable Docker controls "
        "with the packaged version, stays hidden, and closes normally"
    )
    assert (
        case.message == "no packaged app under release/ — run npm run package:dir first"
    )


def test_the_measured_run_passes_the_e2e_mock_leg(check_junit, tmp_path) -> None:
    report = _report(tmp_path, PASSED, PACKAGED_SKIP, FILL_SKIP)
    assert check_junit.main(["--leg", "e2e-mock", report]) == 0


def test_an_allowed_spec_skipping_for_another_reason_fails(
    check_junit, tmp_path
) -> None:
    other_reason = PACKAGED_SKIP.replace(
        "no packaged app under release/ — run npm run package:dir first",
        "electron failed to start",
    )
    assert (
        check_junit.main(["--leg", "e2e-mock", _report(tmp_path, PASSED, other_reason)])
        == 1
    )


def test_any_other_skipped_spec_fails(check_junit, tmp_path) -> None:
    other_spec = FILL_SKIP.replace(
        'classname="page-memory.spec.ts"', 'classname="results.spec.ts"'
    )
    assert (
        check_junit.main(["--leg", "e2e-mock", _report(tmp_path, PASSED, other_spec)])
        == 1
    )


def test_a_failed_spec_fails(check_junit, tmp_path) -> None:
    failed = PASSED.replace(
        "</testcase>",
        '<failure message="expected 1 got 2" type="FAILURE">x</failure>\n</testcase>',
    )
    assert check_junit.main(["--leg", "e2e-mock", _report(tmp_path, failed)]) == 1


def test_an_empty_e2e_report_fails(check_junit, tmp_path) -> None:
    assert check_junit.main(["--leg", "e2e-mock", _report(tmp_path)]) == 1


def test_the_e2e_allowlist_does_not_leak_into_the_pytest_legs(
    check_junit, tmp_path
) -> None:
    report = _report(tmp_path, PASSED, PACKAGED_SKIP)
    assert check_junit.main(["--leg", "no-skips", report]) == 1
    assert check_junit.main(["--leg", "numerical-image", report]) == 1
