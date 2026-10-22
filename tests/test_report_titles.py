"""Each report in Results is listed under its own run, not only its kind.

What this pins (package c1_5, 2026-10-22): ``tit.catalog.reports`` titled every report by its
kind, so Dataset 000's sub-101 lists seventeen flex-search reports all called "Flex-search
report" (the Results tree labels a report node with this ``title``), and the flex-/ex-search
generators titled their page ``sub-<id> flex-search`` / ``sub-<id> ex-search``, naming no run.
Now the generators title the page ``<run folder> flex-search`` / ``<run folder> ex-search``
(simulation pages already read ``<simulation> simulation``), and the catalog lists a report of
those kinds by its page title, read from the head of the file only; a legacy page that names
only the subject, a page with no title, and every other kind are listed by kind plus the
date and time in the file name. ``kind`` is unchanged.

Where the expected values come from: the report files are written here by hand (their
``<title>`` and file-name stamp are the inputs), so each expected title is spelled from those
inputs, not from the catalog; the generator pages are the real generators run on the synthetic
run folders of ``tests/test_reporting_runs.py``, renamed to the folder names asserted.
The Dataset 000 case checks properties (distinct, the stamp of each file name), not counts.

Reproduce: ``.venv/bin/python -m pytest tests/test_report_titles.py -q -p no:cacheprovider``;
with ``TIT_DATASET_000=/path/to/000`` (read-only) the real sub-101 reports are listed too.
Deliberately elsewhere: serving and the CSP (``tests/test_report_catalog_route_chain.py``),
linking a simulation to its report (``tests/test_catalog_report_link.py``).
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from tit import catalog
from tit.paths import get_path_manager

SID = "X"


def _page(title: str | None, body: str = "<p>report</p>") -> str:
    head = f"<title>{title}</title>" if title is not None else ""
    return f'<!doctype html><html><head><meta charset="utf-8">{head}</head><body>{body}</body></html>'


#: file name -> (page text, the title Results must list it under, from the inputs above)
HAND_WRITTEN = {
    # New-style pages name their run.
    "simulation_report_20260801_110000.html": (
        _page("Thalamus simulation"),
        "Thalamus simulation",
    ),
    "flex_search_report_20260730_002424.html": (
        _page("20260730_002424_L_Insula flex-search"),
        "20260730_002424_L_Insula flex-search",
    ),
    "ex_search_report_20260812_093000.html": (
        _page("ex_L_Insula_20260812_090000 ex-search"),
        "ex_L_Insula_20260812_090000 ex-search",
    ),
    # An entity in the title is read as the browser shows it.
    "simulation_report_20260802_120000.html": (
        _page("Left &amp; right simulation"),
        "Left & right simulation",
    ),
    # Legacy pages name only the subject: kind plus the file name's date and time.
    "flex_search_report_20260729_233612.html": (
        _page(f"sub-{SID} flex-search"),
        "Flex-search report, 2026-07-29 23:36:12",
    ),
    "flex_search_report_20260720_170024.html": (
        _page(f"Flex-Search Optimization Report - Subject {SID}"),
        "Flex-search report, 2026-07-20 17:00:24",
    ),
    "simulation_report_20260720_234622.html": (
        _page(f"TI Simulation Report - Subject {SID}"),
        "Simulation report, 2026-07-20 23:46:22",
    ),
    # No title at all.
    "ex_search_report_20260813_080910.html": (
        _page(None),
        "Ex-search report, 2026-08-13 08:09:10",
    ),
    # A title that is only the words after the run names no run.
    "ex_search_report_20260814_000001.html": (
        _page(" ex-search"),
        "Ex-search report, 2026-08-14 00:00:01",
    ),
    # Kinds whose page names no run: kind plus date and time (or the kind alone).
    "dti_qc_20260927_230922.html": (
        _page(f"sub-{SID} DTI QC"),
        "DTI QC report, 2026-09-27 23:09:22",
    ),
    "pre_processing_report_20260903_225836.html": (
        _page(f"Preprocessing Report - Subject {SID}"),
        "Pre processing report, 2026-09-03 22:58:36",
    ),
    "pre_processing_report_20260903_225844.html": (
        _page(f"Preprocessing Report - Subject {SID}"),
        "Pre processing report, 2026-09-03 22:58:44",
    ),
    "charm_report.html": (_page("CHARM report"), "Head model (charm) report"),
}

#: 2 MB of body after the head: the title is still read, from the head.
BIG = "simulation_report_20260803_061809.html"
#: The only <title> sits 1 MB into the file: past any head read, so it is not found.
DEEP = "simulation_report_20260804_000000.html"


@pytest.fixture()
def project(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "dataset_description.json").write_text("{}")
    pm = get_path_manager(str(root))
    Path(pm.m2m(SID)).mkdir(parents=True)
    reports = Path(pm.reports()) / f"sub-{SID}"
    reports.mkdir(parents=True)
    return pm, reports


def test_hand_written_reports_are_listed_under_their_run_or_kind_and_time(project):
    pm, reports = project
    for name, (text, _) in HAND_WRITTEN.items():
        (reports / name).write_text(text, encoding="utf-8")
    padding = "<p>" + "x" * 1000 + "</p>"
    (reports / BIG).write_text(
        _page("Big simulation", padding * 2048), encoding="utf-8"
    )
    (reports / DEEP).write_text(
        _page(None, padding * 1024 + "<title>Deep simulation</title>"),
        encoding="utf-8",
    )
    assert (reports / BIG).stat().st_size > 2_000_000

    listed = {Path(e["path"]).name: e for e in catalog.reports(pm, SID)}

    expected = {name: title for name, (_, title) in HAND_WRITTEN.items()}
    expected[BIG] = "Big simulation"
    expected[DEEP] = "Simulation report, 2026-08-04 00:00:00"
    assert {name: e["title"] for name, e in listed.items()} == expected
    # The kind is still the file name's.
    assert listed["flex_search_report_20260730_002424.html"]["kind"] == (
        "flex_search_report"
    )
    assert listed["charm_report.html"]["kind"] == "charm_report"
    # Every report of the subject is distinguishable by its title alone.
    assert len({e["title"] for e in listed.values()}) == len(listed)


def test_an_unreadable_report_falls_back_to_kind_and_time(project, monkeypatch):
    pm, reports = project
    (reports / "flex_search_report_20260730_010340.html").write_text(
        _page("named_run flex-search")
    )
    real_open = open

    def refuse(path, *args, **kwargs):
        if str(path).endswith("flex_search_report_20260730_010340.html"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *args, **kwargs)

    catalog._report_title.cache_clear()
    monkeypatch.setattr("builtins.open", refuse)
    (entry,) = catalog.reports(pm, SID)
    assert entry["title"] == "Flex-search report, 2026-07-30 01:03:40"


def _rename(run: Path, name: str) -> Path:
    target = run.parent / name
    shutil.move(str(run), str(target))
    return target


def test_two_flex_runs_written_by_the_generator_are_listed_by_their_folders(
    project, tmp_path
):
    from unittest.mock import patch

    from tests.test_report_artifact_events import CAP, FAKE
    from tests.test_reporting_runs import _ex_dir, _flex_dir
    from tit.reporting.generators import ex_search, flex_search

    pm, _ = project
    folders = ["20260730_002424_L_Insula", "20260730_010340_R_Hippocampus"]
    pages = []
    with patch(CAP, return_value=FAKE):
        for i, folder in enumerate(folders):
            run = _rename(_flex_dir(tmp_path / f"flex{i}"), folder)
            pages.append(
                flex_search.create_flex_search_report(pm.project_dir, SID, run)
            )
        (tmp_path / "ex0").mkdir()
        ex_run = _rename(_ex_dir(tmp_path / "ex0"), "ex_L_Insula_20260812_090000")
        pages.append(ex_search.create_ex_search_report(pm.project_dir, SID, ex_run))

    for path, folder in zip(pages, [*folders, ex_run.name]):
        kind = "ex-search" if path.name.startswith("ex_search") else "flex-search"
        assert f"<title>{folder} {kind}</title>" in path.read_text(encoding="utf-8")
    titles = sorted(e["title"] for e in catalog.reports(pm, SID))
    assert titles == sorted(
        [f"{folders[0]} flex-search", f"{folders[1]} flex-search"]
        + ["ex_L_Insula_20260812_090000 ex-search"]
    )


_DATASET = os.environ.get("TIT_DATASET_000", "")
_SUB101 = Path(_DATASET) / "derivatives" / "ti-toolbox" / "reports" / "sub-101"


@pytest.mark.skipif(
    not _DATASET or not _SUB101.is_dir(),
    reason="skipping: TIT_DATASET_000 unset or its sub-101 reports folder is absent",
)
def test_dataset_000_sub_101_flex_reports_each_have_their_own_title():
    files = sorted(_SUB101.glob("flex_search_report_*.html"))
    assert files, "sub-101 flex-search reports to check"
    before = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in _SUB101.iterdir()}

    pm = get_path_manager(_DATASET)
    entries = [
        e for e in catalog.reports(pm, "101") if e["kind"] == "flex_search_report"
    ]

    assert sorted(Path(e["path"]).name for e in entries) == [p.name for p in files]
    titles = [e["title"] for e in entries]
    assert len(set(titles)) == len(titles), titles
    for entry in entries:
        stamp = re.search(r"_(\d{8}_\d{6})\.html$", entry["path"])[1]
        when = datetime.strptime(stamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
        # Each page is either titled by its run folder or listed by its own file's time.
        assert entry["title"].endswith(" flex-search") or entry["title"] == (
            f"Flex-search report, {when}"
        ), entry
    after = {p: (p.stat().st_mtime_ns, p.stat().st_size) for p in _SUB101.iterdir()}
    assert after == before
