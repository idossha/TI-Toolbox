"""Tests for the JSON event sink (`tit.logger`) and structured events (`tit.jobs.events`).

Covers:
- `tit.logger.JsonEventSink` / `get_event_sink`: one JSON object per line, monotonic `seq`,
  <= 4 KB per line (long `msg` truncated), and every produced line validates against
  `contracts/events.schema.json`.
- `tit.logger.setup_logging` attaching a `JsonEventHandler` to the `tit` and `simnibs` loggers
  exactly when `$TIT_EVENTS_FILE` is set, without duplicating the handler on repeat calls.
- `tit.logger.add_file_handler` de-duplicating handlers for the same (logger, path) pair.
- `tit.jobs.events.emit_stage/emit_progress/emit_artifact/emit_result/emit_exit`: no-ops (plus a
  debug log) when the env var is unset, schema-valid events when it is set, and `emit_progress`
  carrying over the `stage`/`i`/`n` most recently set by `emit_stage` (the events schema requires
  them on every `progress` event, but `emit_progress`'s signature -- fixed by this track's spec --
  is `(pct, msg=None)` with no stage/index arguments of its own).
"""

from __future__ import annotations

import importlib
import json
import logging
from pathlib import Path

import pytest

jsonschema = pytest.importorskip(
    "jsonschema",
    reason=(
        "jsonschema is not a runtime dependency; install with "
        "`python3 -m pip install --user --break-system-packages jsonschema` "
        "to run these tests"
    ),
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EVENTS_SCHEMA = json.loads((REPO_ROOT / "contracts" / "events.schema.json").read_text())


def _validate(line: str) -> dict:
    """Parse one events.jsonl line and assert it validates against the schema."""
    record = json.loads(line)
    jsonschema.Draft202012Validator(EVENTS_SCHEMA).validate(record)
    return record


def _read_lines(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _fresh_event_state(monkeypatch):
    """Isolate every test: no env var by default, and a clean logger/sink/module state.

    `tit.logger`/`tit.jobs.events` cache the sink and stage state at module scope (by
    design -- see their docstrings), so tests must reset both or leak into each other.
    """
    monkeypatch.delenv("TIT_EVENTS_FILE", raising=False)
    import tit.logger as logger_mod
    import tit.jobs.events as events_mod

    logger_mod._event_sinks.clear()
    events_mod._reset_state()
    for name in ("tit", "simnibs"):
        log = logging.getLogger(name)
        for h in list(log.handlers):
            if isinstance(h, logger_mod.JsonEventHandler):
                log.removeHandler(h)
    yield
    logger_mod._event_sinks.clear()
    events_mod._reset_state()
    for name in ("tit", "simnibs"):
        log = logging.getLogger(name)
        for h in list(log.handlers):
            if isinstance(h, logger_mod.JsonEventHandler):
                log.removeHandler(h)


# ---------------------------------------------------------------------------
# JsonEventSink
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJsonEventSink:
    def test_seq_is_monotonic_and_schema_valid(self, tmp_path):
        from tit.logger import JsonEventSink

        sink = JsonEventSink(tmp_path / "events.jsonl")
        sink.write({"type": "stage", "stage": "a"})
        sink.write({"type": "stage", "stage": "b"})
        sink.close()

        lines = _read_lines(tmp_path / "events.jsonl")
        assert len(lines) == 2
        first, second = (_validate(line) for line in lines)
        assert first["seq"] == 0
        assert second["seq"] == 1
        assert "ts" in first and isinstance(first["ts"], (int, float))

    def test_get_event_sink_is_a_singleton_per_path(self, tmp_path, monkeypatch):
        from tit.logger import get_event_sink

        path = str(tmp_path / "events.jsonl")
        monkeypatch.setenv("TIT_EVENTS_FILE", path)
        assert get_event_sink() is get_event_sink()
        assert get_event_sink() is get_event_sink(path)

    def test_get_event_sink_returns_none_when_unset(self):
        from tit.logger import get_event_sink

        assert get_event_sink() is None

    def test_oversized_msg_is_truncated_not_dropped(self, tmp_path):
        from tit.logger import JsonEventSink, _EVENT_LINE_LIMIT

        sink = JsonEventSink(tmp_path / "events.jsonl")
        sink.write({"type": "log", "level": "info", "logger": "x", "msg": "a" * 10_000})
        sink.close()

        (line,) = _read_lines(tmp_path / "events.jsonl")
        assert len(line.encode("utf-8")) <= _EVENT_LINE_LIMIT
        record = _validate(line)
        assert record["msg"].endswith("...[truncated]")


# ---------------------------------------------------------------------------
# setup_logging / add_file_handler wiring
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSetupLoggingEventWiring:
    def test_no_handler_attached_when_env_unset(self):
        from tit.logger import JsonEventHandler, setup_logging

        setup_logging()
        assert not any(
            isinstance(h, JsonEventHandler) for h in logging.getLogger("tit").handlers
        )

    def test_handler_attached_to_tit_and_simnibs_when_env_set(
        self, tmp_path, monkeypatch
    ):
        from tit.logger import JsonEventHandler, setup_logging

        monkeypatch.setenv("TIT_EVENTS_FILE", str(tmp_path / "events.jsonl"))
        setup_logging()
        for name in ("tit", "simnibs"):
            handlers = [
                h
                for h in logging.getLogger(name).handlers
                if isinstance(h, JsonEventHandler)
            ]
            assert len(handlers) == 1

    def test_repeat_setup_logging_does_not_duplicate_handler(
        self, tmp_path, monkeypatch
    ):
        from tit.logger import JsonEventHandler, setup_logging

        monkeypatch.setenv("TIT_EVENTS_FILE", str(tmp_path / "events.jsonl"))
        setup_logging()
        setup_logging()
        handlers = [
            h
            for h in logging.getLogger("tit").handlers
            if isinstance(h, JsonEventHandler)
        ]
        assert len(handlers) == 1

    def test_log_record_becomes_a_valid_log_event(self, tmp_path, monkeypatch):
        from tit.logger import setup_logging

        events_path = tmp_path / "events.jsonl"
        monkeypatch.setenv("TIT_EVENTS_FILE", str(events_path))
        setup_logging()
        logging.getLogger("tit.pre").warning("disk nearly full")

        (line,) = _read_lines(events_path)
        record = _validate(line)
        assert record["type"] == "log"
        assert record["level"] == "warning"
        assert record["logger"] == "tit.pre"
        assert record["msg"] == "disk nearly full"

    def test_simnibs_logger_records_reach_the_sink_too(self, tmp_path, monkeypatch):
        """flex/ex/mex/sim attach file handlers to the `simnibs` logger for FEM progress;
        the JSON sink must see those records as well."""
        from tit.logger import setup_logging

        events_path = tmp_path / "events.jsonl"
        monkeypatch.setenv("TIT_EVENTS_FILE", str(events_path))
        setup_logging()
        logging.getLogger("simnibs.solver").info("FEM iteration 3")

        (line,) = _read_lines(events_path)
        record = _validate(line)
        assert record["logger"] == "simnibs.solver"


@pytest.mark.unit
class TestAddFileHandlerDeduplicates:
    def test_same_path_returns_the_same_handler(self, tmp_path):
        from tit.logger import add_file_handler

        log_file = tmp_path / "run.log"
        h1 = add_file_handler(log_file, logger_name="tit.dedupe_test")
        h2 = add_file_handler(log_file, logger_name="tit.dedupe_test")
        assert h1 is h2
        handlers = [
            h
            for h in logging.getLogger("tit.dedupe_test").handlers
            if isinstance(h, logging.FileHandler)
        ]
        assert len(handlers) == 1

    def test_different_paths_get_different_handlers(self, tmp_path):
        from tit.logger import add_file_handler

        h1 = add_file_handler(tmp_path / "a.log", logger_name="tit.dedupe_test2")
        h2 = add_file_handler(tmp_path / "b.log", logger_name="tit.dedupe_test2")
        assert h1 is not h2


# ---------------------------------------------------------------------------
# tit.jobs.events emit_* helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEmitHelpersNoOpWithoutEnv:
    def test_all_helpers_are_silent_no_ops(self):
        """No exception, no file written, and a debug breadcrumb logged for each call.

        `tit/__init__.py` sets the ``tit`` logger's ``propagate = False`` at import
        time (by design -- see ``tit.logger``'s module docstring), so a record on
        the child ``tit.jobs.events`` logger never reaches the root logger; caplog's
        capture handler lives on root, so this attaches directly to the child logger
        instead of going through caplog.
        """
        from tit.jobs import events

        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = records.append  # type: ignore[method-assign]
        target = logging.getLogger("tit.jobs.events")
        target.addHandler(handler)
        target.setLevel(logging.DEBUG)
        try:
            events.emit_stage("charm")
            events.emit_progress(50.0)
            events.emit_artifact("/out.csv", kind="csv")
            events.emit_result({"success": True})
            events.emit_exit(0)
        finally:
            target.removeHandler(handler)

        assert len(records) == 5
        assert all(r.levelno == logging.DEBUG for r in records)


@pytest.mark.unit
class TestEmitHelpersWriteSchemaValidEvents:
    @pytest.fixture()
    def events_path(self, tmp_path, monkeypatch):
        path = tmp_path / "events.jsonl"
        monkeypatch.setenv("TIT_EVENTS_FILE", str(path))
        return path

    def test_emit_stage(self, events_path):
        from tit.jobs import events

        events.emit_stage("charm", i=1, n=4)
        (line,) = _read_lines(events_path)
        record = _validate(line)
        assert record == {
            "seq": 0,
            "ts": pytest.approx(record["ts"]),
            "type": "stage",
            "stage": "charm",
            "i": 1,
            "n": 4,
        }

    def test_emit_progress_carries_over_stage_from_emit_stage(self, events_path):
        """The schema requires stage/i/n on every progress event; emit_progress's
        fixed (pct, msg) signature has no way to pass them itself."""
        from tit.jobs import events

        events.emit_stage("pair1", i=0, n=2)
        events.emit_progress(37.5, msg="halfway")
        lines = _read_lines(events_path)
        progress = _validate(lines[1])
        assert progress["type"] == "progress"
        assert progress["stage"] == "pair1"
        assert progress["i"] == 0
        assert progress["n"] == 2
        assert progress["pct"] == 37.5
        assert progress["msg"] == "halfway"

    def test_emit_progress_without_a_prior_stage_still_validates(self, events_path):
        from tit.jobs import events

        events.emit_progress(10.0)
        (line,) = _read_lines(events_path)
        record = _validate(line)
        assert record["type"] == "progress"

    def test_emit_progress_clamps_to_0_100(self, events_path):
        from tit.jobs import events

        events.emit_progress(150.0)
        events.emit_progress(-5.0)
        lines = _read_lines(events_path)
        assert _validate(lines[0])["pct"] == 100.0
        assert _validate(lines[1])["pct"] == 0.0

    def test_emit_artifact(self, events_path):
        from tit.jobs import events

        events.emit_artifact("/out/report.html", kind="report", label="Report")
        (line,) = _read_lines(events_path)
        record = _validate(line)
        assert record["path"] == "/out/report.html"
        assert record["kind"] == "report"
        assert record["label"] == "Report"

    def test_emit_result_includes_prior_artifacts(self, events_path):
        from tit.jobs import events

        events.emit_artifact("/out/a.csv", kind="csv")
        events.emit_artifact("/out/b.json", kind="json")
        events.emit_result({"success": True, "n": 2})
        lines = _read_lines(events_path)
        result = _validate(lines[-1])
        assert result["type"] == "result"
        assert result["outputs"] == {"success": True, "n": 2}
        assert {o["path"] for o in result["artifacts"]} == {"/out/a.csv", "/out/b.json"}

    def test_emit_result_with_no_artifacts_is_still_schema_valid(self, events_path):
        from tit.jobs import events

        events.emit_result({"success": False})
        (line,) = _read_lines(events_path)
        record = _validate(line)
        assert record["outputs"] == {"success": False}
        assert "artifacts" not in record

    def test_emit_exit(self, events_path):
        from tit.jobs import events

        events.emit_exit(2)
        (line,) = _read_lines(events_path)
        record = _validate(line)
        assert record["type"] == "exit"
        assert record["code"] == 2

    def test_seq_is_shared_across_log_and_structured_events(
        self, events_path, monkeypatch
    ):
        """Log events (via JsonEventHandler) and structured events (via emit_*) must
        interleave into one ordered stream, sharing a single seq counter."""
        from tit.logger import setup_logging
        from tit.jobs import events

        setup_logging()
        events.emit_stage("run")
        logging.getLogger("tit.pre").info("doing work")
        events.emit_exit(0)

        lines = [_validate(line) for line in _read_lines(events_path)]
        seqs = [r["seq"] for r in lines]
        assert seqs == sorted(seqs)
        assert seqs == list(range(len(seqs)))
        assert [r["type"] for r in lines] == ["stage", "log", "exit"]


def test_emit_new_artifacts_lists_files_written_since(tmp_path, monkeypatch):
    """Files under the root modified after ``since`` become artifact events; older ones don't."""
    import json
    import os
    import time

    from tit.jobs import events

    events_file = tmp_path / "ev.jsonl"
    monkeypatch.setenv("TIT_EVENTS_FILE", str(events_file))
    if hasattr(events, "_reset_for_tests"):
        events._reset_for_tests()
    root = tmp_path / "Analyses"
    (root / "old").mkdir(parents=True)
    old = root / "old" / "stale.csv"
    old.write_text("x")
    os.utime(old, (time.time() - 3600, time.time() - 3600))
    since = time.time()
    new_csv = root / "sphere" / "results.csv"
    new_csv.parent.mkdir()
    new_csv.write_text("a,b")
    (root / "sphere" / "roi_overlay.msh").write_bytes(b"\x00")
    (root / "sphere" / "histogram.pdf").write_bytes(b"%PDF")
    emitted = events.emit_new_artifacts(str(root), since)
    assert [os.path.basename(p) for p in emitted] == [
        "histogram.pdf",
        "results.csv",
        "roi_overlay.msh",
    ]
    if events_file.exists():
        kinds = {
            json.loads(l)["path"]: json.loads(l)["kind"]
            for l in events_file.read_text().splitlines()
            if '"artifact"' in l
        }
        assert kinds.get(str(new_csv)) == "csv"
        assert kinds.get(str(root / "sphere" / "roi_overlay.msh")) == "mesh"
