#!/usr/bin/env python3
"""Fail a test leg whose JUnit XML shows it checked nothing, broke, or skipped more than it may.

A pytest leg can exit 0 while proving nothing: every test skipped because an environment
variable or a library was missing, or nothing collected at all. This reads the JUnit XML a
leg wrote (``pytest --junitxml``) and exits

* 0 -- at least one test ran, none failed or errored, and every skip is on the leg's allowlist
  with the reason it is allowed for;
* 1 -- nothing was collected, a test failed or errored, or a skip is not allowed;
* 2 -- the report could not be read (missing or not JUnit XML), so nothing was checked.

Allowlists are per leg and live here, each skip with the reason it may be skipped. A skip
matches an entry when its ``classname.name`` matches the entry's glob *and* its message
contains the entry's text, so the same test skipping for a different reason (an import error
instead of an unset variable) is not allowed.

Usage::

    python3 dev/check_junit.py --leg numerical-image /out/numerical.xml
    python3 dev/check_junit.py --leg no-skips /out/realdata.xml

Self-tests: tests/test_check_junit.py.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

#: Skips the image's ``tests/numerical`` leg may report (measured on idossha/ti-toolbox:v3.1.1,
#: 2026-10-22: 13 skips). Real-data tests are not on it for CI, which has no Dataset 000 --
#: dev/run_realdata_tests.sh runs them with ``--leg no-skips``.
ALLOWLISTS: dict[str, list[dict[str, str]]] = {
    "no-skips": [],
    # dev/run_realdata_tests.sh: every Dataset 000 gate is set, so only the variables Dataset 000
    # cannot satisfy may skip.
    "realdata": [
        {
            "test": "tests.numerical.test_roi_islands.*",
            "message": "TIT_ERNIE_LABELING",
            "why": "Dataset 000 keeps no m2m_ernie/segmentation/labeling.nii.gz",
        },
        {
            "test": "tests.numerical.test_dti_real.*",
            "message": "TIT_DTI_PROTO",
            "why": "the prototype CHN tensor it compares with is not part of Dataset 000",
        },
        {
            "test": "tests.test_scene_realdata.test_the_gifti_label_table_*format=tvsc*",
            "message": "the label table only exists in the GIfTI serialisation",
            "why": "a .tvsc payload has no label table; the format=gii case checks it",
        },
        {
            "test": "tests.test_ex_mirror_map.test_real_*",
            "message": "stale cap with many electrodes at one position",
            "why": "Dataset 000's sub-CHN and sub-LA BioSemi-64 and GSN-HydroCel-128 nets were "
            "applied before v3.1.1 and are collapsed until the caps are re-applied there",
        },
        {
            "test": "tests.test_examples_archive_safety.test_status_sees_a_head_model_under_an_"
            "unlistable_subject_directory",
            "message": "root lists a 0o111 directory anyway",
            "why": "the image runs as root, which a directory mode cannot restrict; the host "
            "suite runs it as a user",
        },
    ],
    # CircleCI desktop-e2e-mock: Playwright `--project=default` against the mock server
    # (measured 2026-10-22: 364 tests, these 3 skipped). Ids are `<spec file>.<title>`.
    "e2e-mock": [
        {
            "test": "packaged-launch.spec.ts.packaged Docker launcher › *",
            "message": "no packaged app under release/",
            "why": "the packaged-app specs need `npm run package:dir`, which this job does not build",
        },
        {
            "test": "page-memory.spec.ts.a deliberate pointer click is not inverted by the fill controller",
            "message": "no run page currently renders a page-level collapsible fill section",
            "why": "its precondition (a collapsible fill section) left the run pages on 2026-09-06",
        },
    ],
    "numerical-image": [
        {
            "test": "tests.numerical.test_bids_fieldmap_tools.*",
            "message": "sdcflows absent",
            "why": "sdcflows lives in the QSIPrep container, not the toolbox image",
        },
        {
            "test": "tests.numerical.test_bids_fieldmap_tools.*",
            "message": "qsiprep absent",
            "why": "QSIPrep runs as its own container, not inside the toolbox image",
        },
        {
            "test": "tests.numerical.test_bids_fieldmap_tools.*",
            "message": "TIT_BIDS_VALIDATOR is unset",
            "why": "the BIDS validator downloads itself; CI legs stay offline",
        },
        {
            "test": "tests.numerical.test_fsaverage_msh.*",
            "message": "the gmsh Python module is not importable",
            "why": "the image ships SimNIBS's gmsh binary, not the gmsh Python module",
        },
        {
            "test": "tests.numerical.test_fsaverage_msh.*",
            "message": "FreeSurfer fsaverage sphere not found",
            "why": "the fsaverage sphere is fetched into ~/mne_data on first use (network)",
        },
        {
            "test": "tests.numerical.test_caps_warp_realdata.*",
            "message": "TIT_SCENE_TESTDATA is unset",
            "why": "Dataset 000 is not in CI; dev/run_realdata_tests.sh runs it",
        },
        {
            "test": "tests.numerical.test_dot_cache_layout.*",
            "message": "TIT_DOTCACHE_PROJECT is unset",
            "why": "Dataset 000 is not in CI; dev/run_realdata_tests.sh runs it",
        },
        {
            "test": "tests.numerical.test_dti_real.*",
            "message": "TIT_DTI_REAL",
            "why": "Dataset 000 is not in CI; dev/run_realdata_tests.sh runs it",
        },
        {
            "test": "tests.numerical.test_roi_islands.*",
            "message": "TIT_ERNIE_LABELING",
            "why": "Dataset 000 is not in CI; dev/run_realdata_tests.sh runs it",
        },
    ],
}


@dataclass(frozen=True)
class Case:
    """One ``<testcase>``: its id, outcome and the skip/failure message."""

    test: str
    outcome: str  # "passed" | "skipped" | "failed" | "error"
    message: str


def read_cases(xml_text: str) -> list[Case]:
    """Parse JUnit XML into cases.

    Raises:
        ValueError: If the text is not JUnit XML.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"not XML: {exc}") from exc
    if root.tag not in {"testsuites", "testsuite"}:
        raise ValueError(f"not JUnit XML (root element <{root.tag}>)")
    cases = []
    for case in root.iter("testcase"):
        test = f"{case.get('classname', '')}.{case.get('name', '')}".strip(".")
        outcome, message = "passed", ""
        for tag in ("error", "failure", "skipped"):
            element = case.find(tag)
            if element is not None:
                outcome = {"failure": "failed", "skipped": "skipped"}.get(tag, tag)
                message = element.get("message") or (element.text or "").strip()
                if not message and tag == "skipped":
                    # Playwright's reporter leaves <skipped/> empty and records the reason
                    # as <property name="skip" value="...">.
                    prop = case.find("properties/property[@name='skip']")
                    message = prop.get("value", "") if prop is not None else ""
                break
        cases.append(Case(test, outcome, message))
    return cases


def allowed(case: Case, allowlist: list[dict[str, str]]) -> bool:
    """Whether a skipped case matches an allowlist entry (glob on id, text in message)."""
    return any(
        fnmatch.fnmatchcase(case.test, entry["test"])
        and entry["message"] in case.message
        for entry in allowlist
    )


def problems(cases: list[Case], allowlist: list[dict[str, str]]) -> list[str]:
    """Every reason this leg is not a pass; empty when it is one."""
    if not cases:
        return ["no tests were collected: the leg checked nothing"]
    found = []
    for case in cases:
        if case.outcome in {"failed", "error"}:
            found.append(f"{case.outcome}: {case.test}: {case.message[:200]}")
        elif case.outcome == "skipped" and not allowed(case, allowlist):
            found.append(
                f"skip not on the allowlist: {case.test}: {case.message[:200]}"
            )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--leg", required=True, choices=sorted(ALLOWLISTS))
    parser.add_argument("reports", nargs="+", help="JUnit XML files")
    args = parser.parse_args(argv)
    cases: list[Case] = []
    for path in args.reports:
        try:
            with open(path, encoding="utf-8") as handle:
                cases.extend(read_cases(handle.read()))
        except (OSError, ValueError) as exc:
            print(f"check_junit: cannot check {path}: {exc}", file=sys.stderr)
            return 2
    counts = {o: sum(c.outcome == o for c in cases) for o in ("passed", "skipped")}
    print(
        f"check_junit[{args.leg}]: {len(cases)} collected, {counts['passed']} passed, "
        f"{counts['skipped']} skipped"
    )
    found = problems(cases, ALLOWLISTS[args.leg])
    for line in found:
        print(f"  {line}")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
