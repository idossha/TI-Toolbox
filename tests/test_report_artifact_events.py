"""Every report writer records its file as exactly one ``report`` artifact of the running job.

Pins (2026-10-22):
* with ``TIT_EVENTS_FILE`` pointing at a file (what the job manager sets for a runner process),
  each of the five report writers -- simulation, flex-search, ex-search, DTI QC and the charm
  copy -- appends exactly one ``{"type": "artifact", "kind": "report"}`` line whose ``path`` is the
  file it returned, that file exists, and it sits in ``reports/sub-<id>/`` where the Reports list
  reads (``tit.catalog.reports``);
* the artifact's ``label`` is the title the Reports list gives that file's kind, so the job's
  attachment and the Reports entry name one file the same way;
* the job's ``result`` event lists the report among its artifacts (``tit.jobs.events.emit_result``);
* the documented DTI QC rebuild command (``python -m tit.reporting.generators.dti_qc``) on a QC
  record without advisories measures them with a real :class:`logging.Logger`, renders them, and
  records its report like the extractor does (it raised ``NameError`` for a while).

Why it matters: the desktop treats the charm and DTI reports as attachments of the stage job that
wrote them (``desktop/src/renderer/pages/preprocess/index.tsx``, ``plannedStageIds``: "a report is
an attachment of the stage job that wrote it (charm: G2a, DTI: G6)"); before this file the DTI QC
writer wrote its report and emitted nothing, so the G6 job had no report attached.

Expected values: the event contract (``tit/jobs/events.py`` module docstring,
``contracts/events.schema.json``), the path each writer returns, the reports directory from the
real :class:`tit.paths.PathManager`, and the report titles in :data:`REPORT_TITLES` (the kinds
TI-Toolbox keeps, docs/dev/DECISIONS.md 2026-09-28, as the Reports list titles them). Inputs are the
synthetic run folders of ``tests/test_reporting_runs.py`` and ``tests/test_reporting_dti_qc.py``;
the cap image and the DTI renderer are stubbed (their pixels are not the subject here).

Reproduce: ``.venv/bin/python -m pytest tests/test_report_artifact_events.py -q -p no:cacheprovider``.
Deliberately elsewhere: file naming under collisions (``tests/test_report_filename_collision.py``),
listing and serving (``tests/test_report_catalog_route_chain.py``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_reporting_dti_qc import FAKE, _images, _record
from tests.test_reporting_runs import (
    CAP,
    LEADFIELD_LOG,
    _ex_dir,
    _flex_dir,
    _sim_dir,
)
from tit.paths import PathManager, get_path_manager

SUBJECT = "X"

#: What the Reports list titles each kept report kind (docs/dev/DECISIONS.md 2026-09-28: charm,
#: DTI, flex-search, ex-search and simulator are the reports TI-Toolbox keeps). Typed here from
#: that decision, not imported from the catalog, so a drift on either side is caught.
REPORT_TITLES = {
    "simulation_report": "Simulation report",
    "flex_search_report": "Flex-search report",
    "ex_search_report": "Ex-search report",
    "dti_qc": "DTI QC report",
    "charm_report": "Head model (charm) report",
}

#: A stand-in for SimNIBS's own charm report: self-contained, images inline.
CHARM_HTML = (
    "<!DOCTYPE html><html><head><title>charm report sub-X</title></head>"
    '<body><h1>charm</h1><img alt="segmentation" src="data:image/png;base64,iVBORw0KGgo="></body></html>'
)


# ── project and report builders (also used by the collision and route-chain tests) ──


def make_project(root: Path) -> PathManager:
    """A BIDS project at *root* with one subject that has a head model, via the real PathManager."""
    root.mkdir(parents=True, exist_ok=True)
    pm = get_path_manager(str(root))
    Path(pm.m2m(SUBJECT)).mkdir(parents=True)
    return pm


def write_simulation_report(pm: PathManager, scratch: Path) -> Path:
    from tit.reporting.generators import simulation

    if not Path(pm.simulation(SUBJECT, "M")).is_dir():
        _sim_dir(Path(pm.sub(SUBJECT)))  # -> <sub-X>/Simulations/M
    with patch(CAP, return_value=FAKE):
        return simulation.create_simulation_report(pm.project_dir, SUBJECT, "M")


def write_flex_report(pm: PathManager, scratch: Path) -> Path:
    from tit.reporting.generators import flex_search

    run = scratch / "run"
    if not run.is_dir():
        run = _flex_dir(scratch)
    with patch(CAP, return_value=FAKE):
        return flex_search.create_flex_search_report(pm.project_dir, SUBJECT, run)


def write_ex_report(pm: PathManager, scratch: Path, n: int = 40) -> Path:
    from tit.reporting.generators import ex_search

    leadfields = Path(pm.leadfields(SUBJECT))
    leadfields.mkdir(parents=True, exist_ok=True)
    (leadfields / "simnibs_simulation_20260923-173824.log").write_text(LEADFIELD_LOG)
    scratch.mkdir(parents=True, exist_ok=True)
    run = scratch / "ex"
    if not run.is_dir():
        run = _ex_dir(scratch, n=n)
    with patch(CAP, return_value=FAKE):
        return ex_search.create_ex_search_report(pm.project_dir, SUBJECT, run)


def write_dti_report(pm: PathManager, scratch: Path) -> Path:
    from tit.reporting.generators import dti_qc

    with patch("tit.plotting.dti_qc.render_all", return_value=_images()):
        return dti_qc.create_dti_qc_report(
            pm.project_dir, SUBJECT, _record(), vols=None
        )


def write_charm_report(pm: PathManager, scratch: Path) -> Path:
    from tit.pre.charm import copy_charm_report

    (Path(pm.m2m(SUBJECT)) / "charm_report.html").write_text(CHARM_HTML)
    path = copy_charm_report(pm.project_dir, SUBJECT, logger=MagicMock())
    assert path is not None, "the charm report was not copied"
    return path


WRITERS = {
    "simulation_report": write_simulation_report,
    "flex_search_report": write_flex_report,
    "ex_search_report": write_ex_report,
    "dti_qc": write_dti_report,
    "charm_report": write_charm_report,
}


def kind_of(path: Path) -> str:
    """The report kind a file name states: ``<kind>_<YYYYMMDD>_<HHMMSS>`` or ``charm_report``."""
    stem = path.stem
    if stem == "charm_report":
        return stem
    head, date, time_ = stem.rsplit("_", 2)
    assert (
        len(date) == 8 and date.isdigit() and len(time_) == 6 and time_.isdigit()
    ), stem
    return head


# ── the events file a job's runner writes ────────────────────────────────


def _clear_event_state() -> None:
    import tit.jobs.events as events_mod
    import tit.logger as logger_mod

    for sink in logger_mod._event_sinks.values():
        sink.close()
    logger_mod._event_sinks.clear()
    events_mod._reset_state()


@pytest.fixture()
def events_file(tmp_path, monkeypatch) -> Path:
    """``TIT_EVENTS_FILE`` set to a fresh file, with the real sink and module state reset."""
    path = tmp_path / "job" / "events.jsonl"
    _clear_event_state()
    monkeypatch.setenv("TIT_EVENTS_FILE", str(path))
    yield path
    _clear_event_state()


def read_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def artifacts(path: Path) -> list[dict]:
    return [e for e in read_events(path) if e["type"] == "artifact"]


# ── the tests ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", sorted(WRITERS))
def test_each_report_writer_records_exactly_one_report_artifact(
    tmp_path, events_file, kind
):
    pm = make_project(tmp_path / "project")
    pytest.importorskip("PIL.Image")  # the flex run folder holds real PNGs

    path = WRITERS[kind](pm, tmp_path / "scratch")

    assert kind_of(path) == kind
    found = artifacts(events_file)
    assert len(found) == 1, f"{kind}: {len(found)} artifact events: {found}"
    event = found[0]
    assert event["kind"] == "report"
    assert event["path"] == str(path)
    assert path.is_file() and path.stat().st_size > 0
    assert path.parent == Path(pm.reports()) / f"sub-{SUBJECT}"
    assert event["label"] == REPORT_TITLES[kind]


@pytest.mark.parametrize("kind", sorted(WRITERS))
def test_the_jobs_result_event_lists_the_report(tmp_path, events_file, kind):
    from tit.jobs import events

    pm = make_project(tmp_path / "project")
    pytest.importorskip("PIL.Image")
    path = WRITERS[kind](pm, tmp_path / "scratch")
    events.emit_result({"ok": True})

    result = [e for e in read_events(events_file) if e["type"] == "result"]
    assert len(result) == 1
    assert result[0]["artifacts"] == [
        {"path": str(path), "kind": "report", "label": REPORT_TITLES[kind]}
    ]


def test_dti_report_into_an_explicit_folder_is_still_the_jobs_artifact(
    tmp_path, events_file
):
    """``--out`` rebuilds and the extractor share one writer: the file written is the one recorded."""
    from tit.reporting.generators import dti_qc

    pm = make_project(tmp_path / "project")
    out = tmp_path / "elsewhere"
    with patch("tit.plotting.dti_qc.render_all", return_value=_images()):
        path = dti_qc.create_dti_qc_report(
            pm.project_dir, SUBJECT, _record({"pct_pd": 50.0}), vols=None, out_dir=out
        )

    assert path.parent == out and kind_of(path) == "dti_qc"
    assert "Software check failed: Positive-definite tensors" in path.read_text()
    assert [(e["kind"], e["path"]) for e in artifacts(events_file)] == [
        ("report", str(path))
    ]


def test_dti_report_logs_its_size_against_its_own_budget(tmp_path, caplog):
    """The shared writer keeps the DTI budget (2.5 MB), not another report's (1 MB)."""
    from tit.reporting.generators import dti_qc

    pm = make_project(tmp_path / "project")
    big = "<!--" + "x" * 1_200_000 + "-->"  # over 1 MB, under 2.5 MB
    with (
        patch.object(dti_qc, "build_html", return_value=big),
        patch("tit.plotting.dti_qc.render_all", return_value=_images()),
        caplog.at_level(logging.INFO, logger="tit.reporting"),
    ):
        path = dti_qc.create_dti_qc_report(
            pm.project_dir, SUBJECT, _record(), vols=None
        )

    assert path.read_text() == big
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(str(path) in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("to_folder", [False, True], ids=["into-project", "--out"])
def test_dti_rebuild_command_measures_missing_advisories_and_records_its_report(
    tmp_path, events_file, capsys, to_folder
):
    """``python -m tit.reporting.generators.dti_qc <project> <subject> [--out DIR]`` on a QC record
    written before advisories existed (the main reason to rebuild): the advisories are measured
    with a real logger, land in the report, and the report is the job's artifact. It raised
    ``NameError: name 'logger' is not defined`` once the module logger was dropped."""
    from tit.reporting.generators import dti_qc

    pm = make_project(tmp_path / "project")
    m2m = Path(pm.m2m(SUBJECT))
    record = _record()
    measured = record.pop("advisories")  # what a measurement would add
    (m2m / "DTI_coregT1_qc.json").write_text(json.dumps(record))
    vols = object()  # stands for the tensor, T1, labels and warp read from m2m
    calls = []

    def measure(qc, volumes, project_dir, subject_id, *, recorded_by, logger):
        calls.append((volumes, project_dir, subject_id, recorded_by, logger))
        qc["advisories"] = measured

    out = tmp_path / "rebuilt"
    argv = [pm.project_dir, SUBJECT] + (["--out", str(out)] if to_folder else [])
    with (
        patch("tit.pre.qsi.dti_advisories.load_volumes", return_value=vols) as load,
        patch("tit.pre.qsi.dti_extractor.record_advisories", side_effect=measure),
        patch("tit.plotting.dti_qc.render_all", return_value=_images()),
    ):
        assert dti_qc.main(argv) == 0

    assert [Path(a) for a in load.call_args.args] == [m2m]
    assert len(calls) == 1
    volumes, project_dir, subject_id, recorded_by, logger = calls[0]
    assert (volumes, project_dir, subject_id) == (vols, pm.project_dir, SUBJECT)
    assert recorded_by == "report rebuild"
    assert isinstance(logger, logging.Logger)

    folder = out if to_folder else Path(pm.reports()) / f"sub-{SUBJECT}"
    (path,) = folder.glob("*.html")
    assert kind_of(path) == "dti_qc"
    note = next(a["note"] for a in measured if a["id"] == "residual_shift_mm")
    assert note and note in path.read_text()
    assert [(e["kind"], e["path"], e["label"]) for e in artifacts(events_file)] == [
        ("report", str(path), REPORT_TITLES["dti_qc"])
    ]
    assert capsys.readouterr().out.startswith(f"{path} ")
    # The completed record goes beside an --out report; the project's own record is not rewritten.
    assert json.loads((m2m / "DTI_coregT1_qc.json").read_text()) == record
    if to_folder:
        completed = json.loads((out / "DTI_coregT1_qc.json").read_text())
        assert completed["advisories"] == measured
