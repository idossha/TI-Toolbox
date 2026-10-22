"""Two same-kind reports for one subject written in the same second are two files, not one.

Pins (2026-10-22):
* the generators promise "one self-contained HTML record per run" (module docstrings of
  ``tit/reporting/generators/dti_qc.py`` and its siblings), but report files are named to the
  second and were written with ``write_text``: two ex-search jobs for one subject (they run in
  parallel under reader locks and can finish in seconds) collapsed into one file, and both jobs'
  artifact events pointed at it;
* a name that is taken moves to the next free second, so every file keeps the
  ``<kind>_<YYYYMMDD>_<HHMMSS>.html`` grammar the Reports list parses
  (``tit.catalog._report_kind_from_stem``) and the desktop mock's id grammar stays valid;
* a free name is used as is, a file already there is never modified, and the next second is
  real clock arithmetic (23:59:59 rolls over into the next day);
* a write that fails (a string UTF-8 cannot encode, a disk that fills halfway) leaves no empty or
  partial file under a report name, records no artifact, and frees the name for the next report.

Expected names are hand-computed from the frozen instant :data:`NOW`; kinds and titles are the
Reports list's (``tests/test_report_artifact_events.py``'s ``REPORT_TITLES``, from
docs/dev/DECISIONS.md 2026-09-28). Inputs are the synthetic run folders of
``tests/test_reporting_runs.py`` and ``tests/test_reporting_dti_qc.py``.

Reproduce: ``.venv/bin/python -m pytest tests/test_report_filename_collision.py -q -p no:cacheprovider``.
Deliberately elsewhere: serving the listed files (``tests/test_report_catalog_route_chain.py``).
"""

from __future__ import annotations

import errno
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.test_report_artifact_events import (  # noqa: F401  (events_file is a fixture)
    REPORT_TITLES,
    SUBJECT,
    artifacts,
    events_file,
    make_project,
    write_dti_report,
    write_ex_report,
    write_simulation_report,
)
from tit import catalog

NOW = datetime(2026, 10, 22, 3, 15, 0)


@contextmanager
def frozen(instant: datetime):
    """``datetime.now()`` is *instant* wherever a report writer reads the clock."""

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(
                instant.year,
                instant.month,
                instant.day,
                instant.hour,
                instant.minute,
                instant.second,
            )

    with (
        patch("tit.reporting.generators.common.datetime", _Frozen),
        patch("tit.reporting.generators.dti_qc.datetime", _Frozen),
    ):
        yield


def test_two_ex_search_reports_in_one_second_are_two_files(tmp_path, events_file):
    pm = make_project(tmp_path / "project")
    with frozen(NOW):
        first = write_ex_report(pm, tmp_path / "run-a", n=40)
        second = write_ex_report(pm, tmp_path / "run-b", n=10)

    assert first.name == "ex_search_report_20261022_031500.html"
    assert second.name == "ex_search_report_20261022_031501.html"
    # Each file is its own run's record: 40 random montages + the known winner, then 10 + 1.
    assert "leads 41 montages" in first.read_text()
    assert "leads 11 montages" in second.read_text()

    listed = catalog.reports(pm, SUBJECT)
    # Listed by the page title, which names the run folder: both runs' folders are named "ex".
    assert [(e["kind"], e["title"]) for e in listed] == [
        ("ex_search_report", "ex ex-search")
    ] * 2
    assert sorted(e["path"] for e in listed) == sorted([str(first), str(second)])
    assert len({e["id"] for e in listed}) == 2
    for entry in listed:
        assert catalog.find_report_path(pm, entry["id"]) == entry["path"]

    events = artifacts(events_file)
    assert [e["path"] for e in events] == [str(first), str(second)]


def test_two_dti_reports_in_one_second_are_two_files(tmp_path, events_file):
    pm = make_project(tmp_path / "project")
    with frozen(NOW):
        first = write_dti_report(pm, tmp_path)
        second = write_dti_report(pm, tmp_path)

    assert (first.name, second.name) == (
        "dti_qc_20261022_031500.html",
        "dti_qc_20261022_031501.html",
    )
    assert first.is_file() and second.is_file()
    assert [e["kind"] for e in catalog.reports(pm, SUBJECT)] == ["dti_qc", "dti_qc"]
    assert [e["path"] for e in artifacts(events_file)] == [str(first), str(second)]


def test_a_taken_name_is_left_untouched_and_the_next_free_second_is_used(tmp_path):
    pm = make_project(tmp_path / "project")
    reports = Path(pm.reports()) / f"sub-{SUBJECT}"
    reports.mkdir(parents=True)
    taken = {
        "ex_search_report_20261022_031500.html": "<html>job A</html>",
        "ex_search_report_20261022_031501.html": "<html>job B</html>",
    }
    for name, body in taken.items():
        (reports / name).write_text(body)

    with frozen(NOW):
        path = write_ex_report(pm, tmp_path / "run-c")

    assert path.name == "ex_search_report_20261022_031502.html"
    assert {name: (reports / name).read_text() for name in taken} == taken
    assert "leads 41 montages" in path.read_text()
    assert len(catalog.reports(pm, SUBJECT)) == 3


def test_the_next_second_after_midnight_is_the_next_day(tmp_path):
    pm = make_project(tmp_path / "project")
    reports = Path(pm.reports()) / f"sub-{SUBJECT}"
    reports.mkdir(parents=True)
    (reports / "ex_search_report_20261022_235959.html").write_text("<html>A</html>")

    with frozen(datetime(2026, 10, 22, 23, 59, 59)):
        path = write_ex_report(pm, tmp_path / "run-d")

    assert path.name == "ex_search_report_20261023_000000.html"
    kinds = {e["path"]: e["kind"] for e in catalog.reports(pm, SUBJECT)}
    assert kinds[str(path)] == "ex_search_report"


def test_reports_of_different_kinds_share_a_second_without_moving(tmp_path):
    pytest.importorskip("PIL.Image")
    pm = make_project(tmp_path / "project")
    with frozen(NOW):
        ex = write_ex_report(pm, tmp_path / "run-e")
        sim = write_simulation_report(pm, tmp_path)
        dti = write_dti_report(pm, tmp_path)

    assert (ex.name, sim.name, dti.name) == (
        "ex_search_report_20261022_031500.html",
        "simulation_report_20261022_031500.html",
        "dti_qc_20261022_031500.html",
    )


def _disk_fills_halfway(path_open):
    """``Path.open`` whose file takes half of a write and then reports a full disk."""

    def open_(self, *args, **kwargs):
        f = path_open(self, *args, **kwargs)
        write = f.write

        def half_then_full(text):
            write(text[: len(text) // 2])
            f.flush()
            raise OSError(errno.ENOSPC, "No space left on device")

        f.write = half_then_full
        return f

    return open_


@pytest.mark.parametrize("failure", ["unencodable", "disk-full"])
def test_a_report_that_fails_to_write_leaves_no_file_behind(
    tmp_path, events_file, failure
):
    """A failed write must not leave an empty or partial file under a report name: the Reports
    list would show it, and the next report of that second would be pushed one second on.
    """
    from tit.reporting.generators import common

    pm = make_project(tmp_path / "project")
    reports = Path(pm.reports()) / f"sub-{SUBJECT}"
    if failure == "unencodable":  # a lone surrogate: UTF-8 cannot encode it
        html, error, disk = (
            "<html>half a report \ud800</html>",
            UnicodeEncodeError,
            None,
        )
    else:
        html, error = "<html>" + "x" * 10_000 + "</html>", OSError
        disk = patch.object(Path, "open", _disk_fills_halfway(Path.open))
    with frozen(NOW), pytest.raises(error), disk or nullcontext():
        common.write_report(
            html,
            pm.project_dir,
            SUBJECT,
            "ex_search_report",
            1_000_000,
            label=REPORT_TITLES["ex_search_report"],
        )

    assert list(reports.iterdir()) == []
    assert catalog.reports(pm, SUBJECT) == []
    assert artifacts(events_file) == []

    with frozen(NOW):
        path = write_ex_report(pm, tmp_path / "run-f")

    assert path.name == "ex_search_report_20261022_031500.html"
    assert [e["path"] for e in artifacts(events_file)] == [str(path)]
