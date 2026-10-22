"""A flex run whose every restart failed writes strict JSON, and its result reaches the desktop.

What this pins (audit_flex #5 / jobs #15, package p08, 2026-10-22): a failed restart leaves
``inf`` in ``function_values`` and ``best_value``. Python's ``json`` writes that as the bare token
``Infinity``, which RFC 8259 does not allow and the browser's ``JSON.parse`` rejects -- so
``flex_meta.json`` could not be parsed by the desktop, the ``result`` event line in
``events.jsonl`` was invalid, and ``/ws/jobs`` forwarded the frame as invalid JSON, which the
desktop's stream dropped. Every writer now emits a non-finite number as ``null``.

How it is checked: each document is parsed with ``json.loads(text, parse_constant=_refuse)``,
which raises on ``Infinity``/``-Infinity``/``NaN`` exactly as a strict (RFC 8259) parser does.
Expected values: ``null`` where the run had no finite value -- the runner's own documented
failure shape (``success=False, best_value=inf, best_run_index=-1``) -- and the finite values
untouched.

Reproduce: ``.venv/bin/python -m pytest tests/test_flex_strict_json.py -q``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tit.opt.config import FlexConfig, FlexResult


def _refuse(token: str):
    raise ValueError(f"non-standard JSON constant {token!r}")


def strict_loads(text: str):
    return json.loads(text, parse_constant=_refuse)


def _config(**overrides) -> FlexConfig:
    fields = dict(
        subject_id="001",
        goal="mean",
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        roi=FlexConfig.SphericalROI(x=-42, y=-20, z=55, radius=10),
    )
    fields.update(overrides)
    return FlexConfig(**fields)


def test_strict_parser_refuses_what_python_writes_by_default():
    """The check below is not vacuous: the default writer's output fails it."""
    with pytest.raises(ValueError, match="Infinity"):
        strict_loads(json.dumps({"best_value": math.inf}))


@patch("tit.opt.flex.utils.generate_label", return_value="mean_maxTI")
@patch("tit.opt.flex.flex.create_valid_skin_region_visualization")
@patch("tit.opt.flex.flex._write_report")
@patch("tit.opt.flex.flex.confirm_roi")
@patch("tit.opt.flex.flex.builder")
@patch("tit.opt.flex.flex.get_path_manager")
def test_a_run_whose_restarts_all_failed_writes_a_strict_manifest(
    mock_gpm, mock_builder, _confirm, _report, _skin, _label, tmp_path
):
    pm = MagicMock()
    pm.flex_search.return_value = str(tmp_path / "flex")
    pm.logs.return_value = str(tmp_path / "logs")
    pm.m2m.return_value = str(tmp_path / "m2m")
    (tmp_path / "m2m").mkdir()
    (tmp_path / "m2m" / "001.msh").touch()
    mock_gpm.return_value = pm
    opt = MagicMock(_accepted_candidate_valid=True, _accepted_candidate_id="c")
    opt.optim_funvalue = float("inf")
    mock_builder.build_optimization.return_value = opt

    from tit.opt.flex.flex import run_flex_search

    out = tmp_path / "output"
    result = run_flex_search(_config(n_multistart=2, output_folder=str(out)))

    # In memory the failure stays inf (the drivers' achievable-intensity check reads it).
    assert result.success is False and result.best_value == math.inf
    manifest = strict_loads((out / "flex_meta.json").read_text())
    assert manifest["result"] == {
        "success": False,
        "best_value": None,
        "best_run_index": -1,
        "all_values": [None, None],
    }


def test_the_manifest_keeps_finite_values_and_nulls_only_the_failed_restart(tmp_path):
    from tit.opt.flex.manifest import write_manifest

    result = FlexResult(
        success=True,
        output_folder=str(tmp_path),
        function_values=[-0.25, math.inf, -0.5],
        best_value=-0.5,
        best_run_index=2,
    )
    write_manifest(str(tmp_path), _config(), result, "label")
    data = strict_loads((tmp_path / "flex_meta.json").read_text())
    assert data["result"]["all_values"] == [-0.25, None, -0.5]
    assert data["result"]["best_value"] == -0.5
    assert data["current_mA"] == 2.0


def test_a_result_event_with_inf_and_nan_is_written_as_strict_json(
    tmp_path, monkeypatch
):
    from tit.jobs import events
    from tit.logger import TIT_EVENTS_FILE_ENV

    path = tmp_path / "events.jsonl"
    monkeypatch.setenv(TIT_EVENTS_FILE_ENV, str(path))
    events.emit_result(
        {"best_value": math.inf, "x": math.nan, "nested": [1.5, -math.inf]}
    )
    (line,) = path.read_text().splitlines()
    event = strict_loads(line)
    assert event["type"] == "result"
    assert event["outputs"] == {"best_value": None, "x": None, "nested": [1.5, None]}


def test_the_jobs_websocket_forwards_an_inf_event_as_strict_json(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tit.jobs import bootstrap
    from tit.jobs.manager import JobManager
    from tit.jobs.registry import events_path
    from tit.jobs.spec import Cost
    from tit.paths import get_path_manager
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings

    token = "strict-json-token"
    get_path_manager(str(tmp_path))
    manager = JobManager(str(tmp_path), budget=Cost(cpus=1, mem_gb=1))
    job_id = manager.submit("tools", {"__fake": {"duration_s": 0.1}}, [])["id"]
    # What a flex runner whose restarts all failed wrote before 2026-10-22 (and what an
    # older job's log on disk still holds).
    record = '{"seq": 0, "ts": 1.0, "type": "result", "outputs": {"best_value": Infinity, "best_run_index": -1}}'
    Path(events_path(str(tmp_path), job_id)).parent.mkdir(parents=True, exist_ok=True)
    Path(events_path(str(tmp_path), job_id)).write_text(record + "\n")

    bootstrap.set_manager_for_testing(manager)
    try:
        client = TestClient(
            create_app(ServerSettings(project_dir=str(tmp_path), token=token)),
            base_url="http://127.0.0.1:8765",
        )
        with client.websocket_connect(
            f"ws://127.0.0.1:8765/ws/jobs?token={token}"
        ) as ws:
            ws.send_text(json.dumps({"subscribe": {job_id: 0}}))
            for _ in range(50):
                raw = ws.receive_text()
                message = strict_loads(raw)
                if message["type"] == "event" and message["job_id"] == job_id:
                    break
            else:  # pragma: no cover - the backfill always carries the event
                raise AssertionError("the subscribed event never arrived")
    finally:
        bootstrap.reset_manager()
    assert message["event"]["outputs"] == {"best_value": None, "best_run_index": -1}
