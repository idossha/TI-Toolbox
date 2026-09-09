"""Fixture verifier rejects incomplete/corrupt results; no FEM or dataset writes."""

import json
import sys

import pytest

from tests.smoke.prepare_flex_fixture import main, verify_result


def _result(tmp_path, *, objective=-0.25, success=True, xyz=None, channels=None):
    # Synthetic unit data is confined to pytest's temporary directory. The actual
    # fixture command never writes these result files; only the real runner does.
    (tmp_path / "flex_meta.json").write_text(
        json.dumps({"result": {"success": success, "best_value": objective}})
    )
    (tmp_path / "electrode_positions.json").write_text(
        json.dumps(
            {
                "optimized_positions": (
                    xyz
                    if xyz is not None
                    else [[1, 2, 3], [4, 5, 6], [7, 8, 9], [10, 11, 12]]
                ),
                "channel_array_indices": (
                    channels
                    if channels is not None
                    else [[0, 0], [0, 1], [1, 0], [1, 1]]
                ),
            }
        )
    )


def test_success_reports_measured_values(tmp_path):
    _result(tmp_path)
    result = verify_result(tmp_path)
    assert result["objective"] == -0.25
    assert result["xyz"][3] == [10, 11, 12]
    assert result["channels"] == [[0, 0], [0, 1], [1, 0], [1, 1]]


@pytest.mark.parametrize(
    "changes",
    [
        {"success": False},
        {"objective": float("inf")},
        {"objective": float("nan")},
        {"xyz": [[1, 2, 3]]},
        {"xyz": [[1, 2, 3]] * 3 + [[1, 2, float("nan")]]},
        {"channels": [[0, 0], [0, 0], [1, 0], [1, 1]]},
    ],
)
def test_rejects_unusable_results(tmp_path, changes):
    _result(tmp_path, **changes)
    with pytest.raises(ValueError):
        verify_result(tmp_path)


def test_refuses_original_project_before_docker_or_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fixture",
            "--container",
            "unused",
            "--project-host",
            str(tmp_path),
            "--source-project",
            str(tmp_path),
            "--run-name",
            "smoke-unit",
            "--execute",
        ],
    )
    with pytest.raises(ValueError, match="separate"):
        main()
    assert list(tmp_path.iterdir()) == []


def _preflight(monkeypatch, jobs, port=None, failure=None):
    """Exercise the real stdlib request code with synthetic transport/config seams."""
    import io
    from types import SimpleNamespace
    import urllib.request

    from tests.smoke.prepare_flex_fixture import PREFLIGHT

    stubs = {
        "tit.config_io": SimpleNamespace(
            deserialize_config=lambda cls, value, **kw: value
        ),
        "tit.opt.config": SimpleNamespace(FlexConfig=object),
        "tit.opt.flex.flex": SimpleNamespace(_validate_flex_inputs=lambda config: None),
        "tit.paths": SimpleNamespace(get_path_manager=lambda root: None),
    }
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"project_dir":"/copied-project"}'))
    monkeypatch.setenv("TIT_SERVER_TOKEN", "fixture-token")
    if port is None:
        monkeypatch.delenv("TIT_SERVER_PORT", raising=False)
    else:
        monkeypatch.setenv("TIT_SERVER_PORT", port)
    requests = []

    def open_request(request, timeout):
        requests.append((request, timeout))
        if failure:
            raise failure
        return io.StringIO(json.dumps(jobs))

    monkeypatch.setattr(urllib.request, "urlopen", open_request)
    exec(compile(PREFLIGHT, "fixture-preflight", "exec"), {})
    return requests


@pytest.mark.parametrize("port,expected", [(None, 8765), ("18767", 18767)])
def test_preflight_honors_container_port_and_keeps_token_private(
    monkeypatch, capsys, port, expected
):
    requests = _preflight(monkeypatch, [{"state": "lost"}], port)
    assert len(requests) == 1
    request, timeout = requests[0]
    assert request.full_url == f"http://127.0.0.1:{expected}/api/jobs"
    assert request.get_header("Authorization") == "Bearer fixture-token"
    assert timeout == 10
    assert "fixture-token" not in capsys.readouterr().out


@pytest.mark.parametrize("state", ["running", "queued"])
def test_preflight_refuses_live_jobs(monkeypatch, state):
    with pytest.raises(RuntimeError, match="Heavy slot is not idle"):
        _preflight(monkeypatch, [{"state": state}])


def test_preflight_cannot_claim_idle_when_server_is_unreadable(monkeypatch):
    from urllib.error import URLError

    with pytest.raises(URLError):
        _preflight(monkeypatch, [], failure=URLError("fixture connection refused"))
