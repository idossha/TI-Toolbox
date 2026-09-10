"""Project summaries: authored bytes, UTC boundary jobs and nonblocking scan (2026-09-09).

Run: python3 -m pytest tests/test_project_summary.py. Browser presentation lives in e2e.
"""

from datetime import datetime, timezone
from pathlib import Path
import threading

from tit.server.routes.project_summary import scan_storage, build_activity, StorageCache


def test_storage_sizes_exclude_links_and_omit_empty_derivatives(tmp_path):
    derivatives = tmp_path / "derivatives"
    (derivatives / "SimNIBS").mkdir(parents=True)
    (derivatives / "empty").mkdir()
    raw = b"raw input"
    output = b"completed derivative"
    (tmp_path / "raw.nii").write_bytes(raw)
    (derivatives / "SimNIBS" / "result").write_bytes(output)
    (tmp_path / "duplicate").symlink_to(tmp_path / "raw.nii")
    (tmp_path / "outside").symlink_to(tmp_path.parent, target_is_directory=True)
    result = scan_storage(tmp_path, derivatives)
    assert result.state == "ready"
    assert result.total_bytes == len(raw) + len(output)
    assert result.other_bytes == len(raw)
    assert {item.name: item.bytes for item in result.derivatives} == {
        "SimNIBS": len(output),
    }


def test_storage_permission_failure_is_not_reported_as_complete(tmp_path, monkeypatch):
    import tit.server.routes.project_summary as module

    def denied(_):
        raise PermissionError("not readable")

    monkeypatch.setattr(module.os, "scandir", denied)
    result = scan_storage(tmp_path, tmp_path / "derivatives")
    assert result.state == "error"
    assert result.total_bytes is None


def test_scan_is_nonblocking_and_deduplicated(tmp_path, monkeypatch):
    import tit.server.routes.project_summary as module

    entered, release = threading.Event(), threading.Event()
    original = module.scan_storage
    calls = []

    def blocked(*args):
        calls.append(1)
        entered.set()
        release.wait(3)
        return original(*args)

    monkeypatch.setattr(module, "scan_storage", blocked)
    cache = StorageCache()
    try:
        assert cache.get(tmp_path, tmp_path / "derivatives").state == "scanning"
        assert entered.wait(1)
        assert cache.get(tmp_path, tmp_path / "derivatives").state == "scanning"
        assert len(calls) == 1
    finally:
        release.set()


def test_activity_utc_boundary_deduplication_and_latest_finish():
    def job(id, at, **kwargs):
        return dict(
            id=id,
            created_at=at,
            kind="sim",
            state="succeeded",
            subject_ids=["a", "b"],
            **kwargs,
        )

    first = job("one", "2026-09-08T23:30:00-05:00", finished_at="2026-09-09T06:00:00Z")
    jobs = [
        first,
        first,
        job("old", "2020-01-01T00:00:00Z"),
        job("two", "2026-09-09T05:00:00Z"),
    ]
    result = build_activity(jobs, datetime(2026, 9, 9, 12, tzinfo=timezone.utc))
    assert len(result["days"]) == 365
    assert sum(day["count"] for day in result["days"]) == 2
    assert result["days"][-1] == {"date": "2026-09-09", "count": 2}
    assert len(result["recent"]) == 3
    assert result["history_since"].startswith("2020-01-01")
    assert result["last_activity_at"].startswith("2026-09-09T06:00:00")


def test_worker_exception_recovers_to_error(tmp_path, monkeypatch):
    import tit.server.routes.project_summary as module

    def broken(*args):
        raise RuntimeError("unexpected scanner failure")

    monkeypatch.setattr(module, "scan_storage", broken)
    cache = StorageCache()
    cache.running = True
    cache._scan(tmp_path, tmp_path / "derivatives")
    assert not cache.running
    assert cache.get(tmp_path, tmp_path / "derivatives").state == "error"


def test_route_identity_auth_and_single_job_read(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from tit.server.app import create_app
    from tit.server.settings import ServerSettings
    from tit.paths import get_path_manager
    import tit.jobs.bootstrap as bootstrap
    import tit.server.routes.project_summary as module

    get_path_manager(str(tmp_path))
    calls = []

    def jobs():
        calls.append(1)
        return []

    monkeypatch.setattr(
        bootstrap, "get_manager", lambda app: SimpleNamespace(list_jobs=jobs)
    )
    monkeypatch.setattr(
        module,
        "project",
        lambda: SimpleNamespace(
            name="Project", host_path="/host/project", container_path=str(tmp_path)
        ),
    )
    monkeypatch.setattr(
        StorageCache,
        "get",
        lambda self, *args: module.SummaryStorage(
            state="scanning",
            total_bytes=None,
            other_bytes=None,
            derivatives=[],
            scanned_at=None,
        ),
    )
    client = TestClient(
        create_app(ServerSettings(project_dir=str(tmp_path), token="test-token")),
        base_url="http://127.0.0.1:8765",
    )
    assert client.get("/api/catalog/project-summary").status_code == 401
    response = client.get(
        "/api/catalog/project-summary", headers={"Authorization": "Bearer test-token"}
    )
    assert response.status_code == 200
    assert response.json()["identity"] == dict(
        name="Project", path="/host/project", created_at=None
    )
    assert response.json()["activity"]["history_since"] is None
    assert calls == [1]


def test_workflow_breakdown_and_future_derivatives(tmp_path):
    paths = {
        "derivatives/SimNIBS/sub-101/m2m_101/head.msh": ("Head models", b"head"),
        "derivatives/SimNIBS/sub-101/Simulations/run/field.msh": (
            "Simulations",
            b"field",
        ),
        "derivatives/SimNIBS/sub-101/flex-search/run/result": ("Flex search", b"flex"),
        "derivatives/SimNIBS/sub-101/ex-search/run/result": ("Ex search", b"ex"),
        "derivatives/future-extension/result": ("future-extension", b"new"),
    }
    for name, (_, content) in paths.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    result = scan_storage(tmp_path, tmp_path / "derivatives")
    assert result.state == "ready"
    assert {row.name: row.bytes for row in result.derivatives} == {
        label: len(content) for label, content in paths.values()
    }
    assert result.total_bytes == sum(len(content) for _, content in paths.values())
    assert result.other_bytes == 0
