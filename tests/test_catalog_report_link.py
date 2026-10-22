"""A simulation links to its own report, never to a report whose path merely contains its name.

What this pins (2026-10-22, package p04 "sim-report-link")
    ``simulation_detail()['report_ids']`` decides which report the Results page previews for a
    simulation (``outputsTree.ts`` opens ``report_ids[0]``). It used to keep every report whose
    *path* contained the simulation name, case-folded. Report paths contain
    ``derivatives/ti-toolbox/reports/sub-<id>/`` and a timestamp, so a simulation called ``TI``,
    ``report``, ``2026`` or the subject's own id claimed every report of the subject, the
    charm report first, while a real simulation never matched its own
    ``simulation_report_<timestamp>.html``.

Where the expected values come from
    The simulation report generator itself: ``build_html`` names the page
    ``<title>{simulation} simulation</title>``. The test writes real ``build_html`` output for
    two simulations and reads every report's title back with the standard library's
    ``html.parser`` -- not with the catalog -- to decide which simulation each one belongs to.

Reproduce
    .venv/bin/python -m pytest tests/test_catalog_report_link.py -q -p no:cacheprovider

Deliberately elsewhere
    The desktop side (a simulation without a report previews its artifacts):
    ``desktop/tests/unit/results-report-link.test.ts``.
"""

from __future__ import annotations

import os
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_reporting_runs import CAP, _sim_dir, _with_envelope
from tit import catalog
from tit.paths import get_path_manager
from tit.reporting.generators import simulation as sim_report

SID = "ernie"
OWN = {
    "TI": "simulation_report_20260923_184500",
    "AF3_PO10_and_AF4_Oz": "simulation_report_20260923_190000",
    "my montage": "simulation_report_20260924_090000",
}
#: Simulation names that are substrings of some report path in this project (or of a title),
#: matched case-folded by the old rule (``TI`` itself is in :data:`OWN`). No two differ only
#: in case: macOS hosts are case-insensitive, and ``ti`` would be the folder ``TI``.
SUBSTRING_NAMES = (
    "ernie",
    "Report",
    "sim",
    "2026",
    "000",
    "derivatives",
    "charm",
    "simulation",
    "TI simulation",
    "Thalamus",
)


class _Title(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self._in = False

    def handle_starttag(self, tag, attrs):
        self._in = tag == "title"

    def handle_endtag(self, tag):
        self._in = False

    def handle_data(self, data):
        if self._in:
            self.title = (self.title or "") + data


def _title(path: Path) -> str | None:
    parser = _Title()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.title


def _real_report(tmp_path: Path, name: str) -> str:
    """``build_html`` output for a simulation called *name* (the generator's fixtures)."""
    rec = _with_envelope(
        sim_report.collect(_sim_dir(tmp_path / name.replace(" ", "_")))
    )
    rec["name"] = name
    rec["config"]["simulation_name"] = name
    with patch(CAP, return_value=None):
        return sim_report.build_html(rec, None, SID)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    pm = get_path_manager(str(root))
    os.makedirs(pm.m2m(SID))
    for name in (*OWN, *SUBSTRING_NAMES):
        os.makedirs(os.path.join(pm.simulation(SID, name), "documentation"))
    reports = Path(pm.reports()) / f"sub-{SID}"
    reports.mkdir(parents=True)
    for name, stem in OWN.items():
        (reports / f"{stem}.html").write_text(_real_report(tmp_path / "gen", name))
    # Stand-ins for the other kinds and for a report from before the generator named its run.
    (reports / "charm_report.html").write_text(
        "<html><head><title>charm report TI simulation</title></head></html>"
    )
    (reports / "dti_qc_20260927_230922.html").write_text(
        "<html><head><title>TI simulation</title></head></html>"
    )
    (reports / "flex_search_report_20260919_140300.html").write_text(
        "<html><head><title>TI simulation</title></head></html>"
    )
    (reports / "simulation_report_20260505_224149.html").write_text(
        "<html><head><title>TI Simulation Report - Subject ernie</title></head></html>"
    )
    return root


def _report_ids(project: Path, name: str) -> list[str]:
    detail = catalog.simulation_detail(get_path_manager(str(project)), SID, name)
    assert detail is not None
    return detail["report_ids"]


def _owner_by_title(path: Path) -> str | None:
    """The simulation a report names, read independently of the catalog."""
    title = _title(path)
    stem = path.stem
    if not stem.startswith("simulation_report_") or title is None:
        return None
    return title.removesuffix(" simulation") if title.endswith(" simulation") else None


def test_each_simulation_links_exactly_its_own_report(project):
    reports = Path(get_path_manager(str(project)).reports()) / f"sub-{SID}"
    owners = {p.stem: _owner_by_title(p) for p in reports.glob("*.html")}
    # The generator's title is the association: three reports, three simulations.
    assert {s: o for s, o in owners.items() if o} == {v: k for k, v in OWN.items()}
    for name, stem in OWN.items():
        assert _report_ids(project, name) == [f"{SID}/{stem}"]


@pytest.mark.parametrize("name", SUBSTRING_NAMES)
def test_a_name_inside_report_paths_or_titles_links_nothing(project, name):
    assert _report_ids(project, name) == []


def test_a_rerun_lists_the_newest_report_first(project, tmp_path):
    reports = Path(get_path_manager(str(project)).reports()) / f"sub-{SID}"
    newer = "simulation_report_20261001_080000"
    (reports / f"{newer}.html").write_text(_real_report(tmp_path / "gen2", "TI"))
    assert _report_ids(project, "TI") == [f"{SID}/{newer}", f"{SID}/{OWN['TI']}"]
    assert _report_ids(project, "AF3_PO10_and_AF4_Oz") == [
        f"{SID}/{OWN['AF3_PO10_and_AF4_Oz']}"
    ]


_DATASET = os.environ.get("TIT_DATASET_000")


@pytest.mark.skipif(
    not _DATASET or not os.path.isdir(_DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
def test_dataset_000_links_only_reports_that_name_their_simulation():
    root = Path(_DATASET)
    reports_root = root / "derivatives" / "ti-toolbox" / "reports"
    before = {p: p.stat().st_mtime_ns for p in reports_root.rglob("*.html")}
    pm = get_path_manager(str(root))
    checked = 0
    sims = sorted((root / "derivatives" / "SimNIBS").glob("sub-*/Simulations/*"))
    for sim_dir in (s for s in sims if s.is_dir() and not s.name.startswith(".")):
        sid = sim_dir.parent.parent.name.removeprefix("sub-")
        detail = catalog.simulation_detail(pm, sid, sim_dir.name)
        assert detail is not None
        for report_id in detail["report_ids"]:
            path = reports_root / f"sub-{sid}" / f"{report_id.split('/', 1)[1]}.html"
            assert path.name.startswith("simulation_report_")
            assert _title(path) == f"{sim_dir.name} simulation"
        checked += 1
    assert checked >= 5
    assert before == {p: p.stat().st_mtime_ns for p in reports_root.rglob("*.html")}
