"""A simulation links to its own report, never to a report whose path merely contains its name.

What this pins (2026-10-22, package p04 "sim-report-link")
    ``simulation_detail()['report_ids']`` decides which report the Results page previews for a
    simulation (``outputsTree.ts`` opens ``report_ids[0]``). It used to keep every report whose
    *path* contained the simulation name, case-folded. Report paths contain
    ``derivatives/ti-toolbox/reports/sub-<id>/`` and a timestamp, so a simulation called ``TI``,
    ``report``, ``2026`` or the subject's own id claimed every report of the subject, the
    charm report first, while a real simulation never matched its own
    ``simulation_report_<timestamp>.html``. The link is now the report's exact title, so a
    simulation whose name ends (``L_TI``) or starts (``TI_L``) with another's never takes the
    other's report, and a report rewritten in place is re-read.

Where the expected values come from
    The simulation report generator itself: ``build_html`` names the page
    ``<title>{simulation} simulation</title>``. The test writes real ``build_html`` output for
    every simulation in :data:`OWN` and reads every report's title back with the standard
    library's ``html.parser`` -- not with the catalog -- to decide which simulation each one
    belongs to. The Dataset 000 legs read the real reports' titles the same way.

Reproduce
    .venv/bin/python -m pytest tests/test_catalog_report_link.py -q -p no:cacheprovider
    TIT_DATASET_000=/path/to/000 .venv/bin/python -m pytest tests/test_catalog_report_link.py -q

Deliberately elsewhere
    The desktop side (a simulation without a report previews its artifacts):
    ``desktop/tests/unit/results-report-link.test.ts``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

from tit import catalog
from tit.paths import get_path_manager
from tit.reporting.generators import simulation as sim_report

SID = "ernie"
OWN = {
    "TI": "simulation_report_20260923_184500",
    "AF3_PO10_and_AF4_Oz": "simulation_report_20260923_190000",
    "my montage": "simulation_report_20260924_090000",
    # ``TI`` is the end of ``L_TI`` and the start of ``TI_L``: "L_TI simulation" contains
    # "TI simulation", so a containment test instead of equality cross-links them.
    "L_TI": "simulation_report_20260925_100000",
    "TI_L": "simulation_report_20260925_110000",
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
#: ``montage_webp`` draws the cap overlay; a report without it is still the generator's page.
_CAP = "tit.tools.montage_visualizer.montage_webp"


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
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.title


def _real_report(scratch: Path, name: str) -> str:
    """``build_html`` output for a 2-pair simulation called *name*, collected from its folder."""
    sim_dir = scratch / "Simulations" / name.replace(" ", "_")
    (sim_dir / "documentation").mkdir(parents=True)
    config = {
        "subject_id": SID,
        "simulation_name": name,
        "simulation_mode": "TI",
        "conductivity": "scalar",
        "electrode_pairs": [["AF3", "PO10"], ["AF4", "Oz"]],
        "intensities": [1.0, 1.0],
        "electrode_geometry": {
            "shape": "ellipse",
            "dimensions": [8, 8],
            "gel_thickness": 4,
            "rubber_thickness": 2.0,
        },
    }
    (sim_dir / "documentation" / "config.json").write_text(json.dumps(config))
    with patch(_CAP, return_value=None):
        return sim_report.build_html(sim_report.collect(sim_dir), None, SID)


def _make_project(root: Path, sims: tuple[str, ...]) -> Path:
    """A project with subject :data:`SID` and an empty folder per simulation in *sims*."""
    root.mkdir()
    pm = get_path_manager(str(root))
    os.makedirs(pm.m2m(SID))
    for name in sims:
        os.makedirs(os.path.join(pm.simulation(SID, name), "documentation"))
    reports = Path(pm.reports()) / f"sub-{SID}"
    reports.mkdir(parents=True)
    return reports


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    reports = _make_project(root, (*OWN, *SUBSTRING_NAMES))
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


def _reports_dir(project: Path) -> Path:
    return Path(get_path_manager(str(project)).reports()) / f"sub-{SID}"


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
    owners = {p.stem: _owner_by_title(p) for p in _reports_dir(project).glob("*.html")}
    # The generator's title is the association: one report per simulation in OWN.
    assert {s: o for s, o in owners.items() if o} == {v: k for k, v in OWN.items()}
    for name, stem in OWN.items():
        assert _report_ids(project, name) == [f"{SID}/{stem}"]


@pytest.mark.parametrize("other", ["L_TI", "TI_L"])
def test_a_name_that_ends_or_starts_another_never_takes_its_report(project, other):
    """``TI`` against ``L_TI`` (a suffix of it) and ``TI_L`` (a prefix of it)."""
    reports = _reports_dir(project)
    titles = {name: _title(reports / f"{OWN[name]}.html") for name in ("TI", other)}
    # The fixture is adversarial: one simulation's name is inside the other's.
    assert "TI" in other and titles["TI"] != titles[other]
    assert _report_ids(project, "TI") == [f"{SID}/{OWN['TI']}"]
    assert _report_ids(project, other) == [f"{SID}/{OWN[other]}"]


@pytest.mark.parametrize("name", SUBSTRING_NAMES)
def test_a_name_inside_report_paths_or_titles_links_nothing(project, name):
    assert _report_ids(project, name) == []


def test_a_rerun_lists_the_newest_report_first(project, tmp_path):
    newer = "simulation_report_20261001_080000"
    (_reports_dir(project) / f"{newer}.html").write_text(
        _real_report(tmp_path / "gen2", "TI")
    )
    assert _report_ids(project, "TI") == [f"{SID}/{newer}", f"{SID}/{OWN['TI']}"]
    assert _report_ids(project, "AF3_PO10_and_AF4_Oz") == [
        f"{SID}/{OWN['AF3_PO10_and_AF4_Oz']}"
    ]


def _retitle(path: Path, old: str, new: str, mtime_s: int) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(f"<title>{old}</title>") == 1
    path.write_text(text.replace(f"<title>{old}</title>", f"<title>{new}</title>"))
    os.utime(path, ns=(mtime_s * 10**9, mtime_s * 10**9))


def test_a_report_rewritten_in_place_is_linked_by_its_new_title(project):
    """A cached title is dropped when the file changes, by modification time or by size."""
    report = _reports_dir(project) / f"{OWN['L_TI']}.html"
    own_ti_l = f"{SID}/{OWN['TI_L']}"
    rewritten = f"{SID}/{OWN['L_TI']}"
    assert _report_ids(project, "L_TI") == [rewritten]  # its title is read (and kept)

    # Same size, newer modification time: only the time says the title changed.
    size = report.stat().st_size
    _retitle(report, "L_TI simulation", "TI_L simulation", mtime_s=1_800_000_000)
    assert report.stat().st_size == size
    assert _title(report) == "TI_L simulation"
    assert _report_ids(project, "L_TI") == []
    assert _report_ids(project, "TI_L") == [own_ti_l, rewritten]

    # New size, the same modification time: only the size says the title changed.
    mtime_ns = report.stat().st_mtime_ns
    _retitle(report, "TI_L simulation", "my montage simulation", mtime_s=1_800_000_000)
    assert report.stat().st_mtime_ns == mtime_ns and report.stat().st_size != size
    assert _report_ids(project, "TI_L") == [own_ti_l]
    # Ids sort by their timestamp: the rewritten report (2026-09-25) is newer than its own.
    assert _report_ids(project, "my montage") == [
        rewritten,
        f"{SID}/{OWN['my montage']}",
    ]


# ── Dataset 000 ──────────────────────────────────────────────────────────────

_DATASET = os.environ.get("TIT_DATASET_000")
_needs_dataset = pytest.mark.skipif(
    not _DATASET or not os.path.isdir(_DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)


@_needs_dataset
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


@_needs_dataset
def test_dataset_000_report_titled_by_the_generator_links_its_simulation(tmp_path):
    """A real (3 MB) simulation report, copied and given the generator's title, is linked.

    Dataset 000's reports predate the title that names the run, so the read-only leg above
    can only show that nothing is linked wrongly. Here one is copied twice into a scratch
    project: as it is (not linked) and with ``<title>`` replaced by ``<sim> simulation``,
    the only change ``build_html`` now makes to that head (linked).
    """
    root = Path(_DATASET)
    source_dir = root / "derivatives" / "ti-toolbox" / "reports" / f"sub-{SID}"
    sources = sorted(source_dir.glob("simulation_report_*.html"))
    sims = sorted(
        p.name
        for p in (
            root / "derivatives" / "SimNIBS" / f"sub-{SID}" / "Simulations"
        ).iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    assert sources and sims, "Dataset 000 has no ernie simulation report to copy"
    before = {p: p.stat().st_mtime_ns for p in sources}
    source, sim = sources[-1], sims[0]
    old_title = _title(source)
    assert old_title and not old_title.endswith(" simulation")

    reports = _make_project(tmp_path / "project", (sim,))
    shutil.copyfile(source, reports / source.name)
    retitled = reports / "simulation_report_20261022_120000.html"
    text = source.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r"<title>.*?</title>", f"<title>{sim} simulation</title>", text, count=1
    )
    assert n == 1
    retitled.write_text(new_text, encoding="utf-8")

    assert _title(retitled) == f"{sim} simulation"
    assert _report_ids(tmp_path / "project", sim) == [f"{SID}/{retitled.stem}"]
    assert before == {p: p.stat().st_mtime_ns for p in sources}
