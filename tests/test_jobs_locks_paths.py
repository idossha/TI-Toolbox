"""2026-09-09: lock metadata cannot follow preexisting links outside its project.

Authored sentinel fixtures prove no outside overwrite/deletion. Run:
python3 -m pytest tests/test_jobs_locks_paths.py tests/test_jobs_model.py -q.
Normal contention/stale-owner policy lives in test_jobs_model; concurrent filesystem
replacement races are not modeled by these preexisting-link tests.
"""

import hashlib
import json

import pytest

from tit.jobs import locks


@pytest.mark.parametrize("component", ["root", "directory", "descriptor"])
@pytest.mark.parametrize("operation", ["acquire", "release", "reconcile"])
def test_lock_storage_rejects_outward_links(tmp_path, component, operation):
    project = tmp_path / "project"
    project.mkdir()
    root = project / "code" / "ti-toolbox" / "jobs" / ".locks"
    root.mkdir(parents=True)
    request = locks.LockRequest("subject:001:m2m")
    digest = hashlib.sha1(request.resource.encode()).hexdigest()[:16]
    lock_dir = root / digest
    outside = tmp_path / "outside"
    outside.mkdir()
    if component == "root":
        root.rmdir()
        root.symlink_to(outside, target_is_directory=True)
        foreign_dir = outside / digest
        foreign_dir.mkdir()
    elif component == "directory":
        lock_dir.symlink_to(outside, target_is_directory=True)
        foreign_dir = outside
    else:
        lock_dir.mkdir()
        foreign_dir = outside
        (lock_dir / "lock.json").symlink_to(outside / "lock.json")
    descriptor = foreign_dir / "lock.json"
    authored = json.dumps({"job_id": "foreign", "pid": 99999999, "create_time": 1.0})
    descriptor.write_text(authored)
    sentinel = foreign_dir / "sentinel"
    sentinel.write_text("keep me")

    if operation == "acquire":
        with pytest.raises(PermissionError):
            with locks.hold(str(project), "current", [request]):
                pass
    elif component == "root":
        with pytest.raises(PermissionError):
            if operation == "release":
                locks.release_job(str(project), "foreign")
            else:
                locks.reconcile(str(project))
    elif operation == "release":
        assert locks.release_job(str(project), "foreign") == 0
    else:
        assert locks.reconcile(str(project)) == 0
    assert descriptor.read_text() == authored
    assert sentinel.read_text() == "keep me"


@pytest.mark.parametrize("component", ["root", "directory", "descriptor"])
def test_lock_storage_supports_in_project_links(tmp_path, monkeypatch, component):
    root = tmp_path / "code" / "ti-toolbox" / "jobs" / ".locks"
    root.mkdir(parents=True)
    request = locks.LockRequest("subject:001:m2m")
    digest = hashlib.sha1(request.resource.encode()).hexdigest()[:16]
    destination = tmp_path / "relocated"
    if component == "root":
        root.rmdir()
        destination.mkdir()
        root.symlink_to(destination, target_is_directory=True)
    elif component == "directory":
        destination.mkdir()
        (destination / "sentinel").write_text("keep me")
        (root / digest).symlink_to(destination, target_is_directory=True)
    else:
        (root / digest).mkdir()
        destination.write_text("{}")
        (root / digest / "lock.json").symlink_to(destination)
    monkeypatch.setattr(locks, "_is_alive", lambda *_: True)
    with locks.hold(str(tmp_path), "current", [request]):
        assert [item["job_id"] for item in locks.holders(str(tmp_path))] == ["current"]
    assert locks.holders(str(tmp_path)) == []
    if component == "directory":
        assert (destination / "sentinel").read_text() == "keep me"
