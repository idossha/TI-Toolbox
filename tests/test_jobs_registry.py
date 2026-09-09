"""registry.py (on-disk job store) and tailer.py (events.jsonl reading)."""

from __future__ import annotations

import json
import os

import pytest

from tit.jobs.registry import (
    BIDSIGNORE_LINE,
    JobRegistry,
    ensure_bidsignore,
    events_path,
    job_dir,
    job_file_path,
    jobs_root,
)
from tit.jobs.spec import Cost, JobSpec, JobStatus
from tit.jobs.tailer import EventTailer, line_count, read_events


def _spec(job_id: str, **overrides) -> JobSpec:
    defaults = dict(
        id=job_id,
        kind="sim",
        config={"subject_id": "001"},
        subject_ids=["001"],
        cost=Cost(cpus=1, mem_gb=4),
    )
    defaults.update(overrides)
    return JobSpec(**defaults)


def test_registry_create_and_read_round_trip(tmp_path):
    registry = JobRegistry(str(tmp_path))
    spec = _spec("j1")
    status = JobStatus.queued(spec)
    registry.create(spec, status)

    assert os.path.isdir(job_dir(str(tmp_path), "j1"))
    assert registry.read_spec("j1") == spec
    assert registry.read_status("j1") == status
    assert os.path.exists(events_path(str(tmp_path), "j1"))
    assert registry.list_ids() == ["j1"]


@pytest.mark.parametrize(
    "component",
    ["root", "job", "spec.json", "status.json", "events.jsonl", "stdout.log"],
)
def test_registry_rejects_outward_storage_symlinks(tmp_path, component):
    """2026-09-09: authored outside sentinel must survive job-store operations.

    Reproduce: python3 -m pytest tests/test_jobs_registry.py -k storage_symlink -q.
    These preexisting links test containment; concurrent link replacement is separate.
    """
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    registry = JobRegistry(str(project))
    root = project / "code" / "ti-toolbox" / "jobs"
    spec = _spec("legacy-job_1")
    target = root if component == "root" else root / spec.id
    if component not in ("root", "job"):
        target.mkdir()
        target = target / component
        destination = outside / component
        destination.write_text("outside sentinel")
    else:
        if component == "root":
            target.rmdir()
        destination = outside
    target.symlink_to(destination, target_is_directory=component in ("root", "job"))
    with pytest.raises(PermissionError):
        registry.create(spec, JobStatus.queued(spec))
    assert sorted(p.name for p in outside.iterdir()) == (
        [] if component in ("root", "job") else [component]
    )
    if component not in ("root", "job"):
        assert destination.read_text() == "outside sentinel"


def test_registry_ignores_outward_job_link_and_keeps_valid_jobs(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    registry = JobRegistry(str(project))
    outside = tmp_path / "outside"
    external = JobRegistry(str(outside))
    external.create(_spec("foreign"), JobStatus.queued(_spec("foreign")))
    root = project / "code" / "ti-toolbox" / "jobs"
    (root / "foreign").symlink_to(outside / "code" / "ti-toolbox" / "jobs" / "foreign")
    registry.create(_spec("local"), JobStatus.queued(_spec("local")))
    assert registry.list_ids() == ["local"]
    assert registry.read_spec("foreign") is None
    assert registry.delete("foreign") is False
    assert external.read_spec("foreign") is not None


@pytest.mark.parametrize("component", ["root", "job", "events.jsonl"])
def test_registry_allows_in_project_storage_symlinks(tmp_path, component):
    registry = JobRegistry(str(tmp_path))
    root = tmp_path / "code" / "ti-toolbox" / "jobs"
    destination = tmp_path / "relocated"
    if component == "root":
        root.rmdir()
        target = root
    else:
        target = root / "legacy-job_1"
        if component == "events.jsonl":
            target.mkdir()
            target = target / component
    if component == "events.jsonl":
        destination.write_text("")
    else:
        destination.mkdir()
    target.symlink_to(destination, target_is_directory=component != "events.jsonl")
    spec = _spec("legacy-job_1")
    registry.create(spec, JobStatus.queued(spec))
    assert registry.read_spec(spec.id) == spec
    assert registry.list_ids() == [spec.id]


def test_job_file_path_refuses_outward_config_symlink(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    registry = JobRegistry(str(project))
    registry.create(_spec("j1"), JobStatus.queued(_spec("j1")))
    outside = tmp_path / "config.json"
    outside.write_text("outside sentinel")
    target = project / "code" / "ti-toolbox" / "jobs" / "j1" / "config.json"
    target.symlink_to(outside)
    with pytest.raises(PermissionError):
        job_file_path(str(project), "j1", "config.json")
    assert outside.read_text() == "outside sentinel"


@pytest.mark.parametrize("filename", ["spec.json", "status.json", "events.jsonl", "stdout.log"])
def test_registry_reopen_skips_outward_metadata_link(tmp_path, filename):
    project = tmp_path / "project"
    project.mkdir()
    registry = JobRegistry(str(project))
    for name in ("unsafe", "valid"):
        registry.create(_spec(name), JobStatus.queued(_spec(name)))
    target = project / "code" / "ti-toolbox" / "jobs" / "unsafe" / filename
    outside = tmp_path / filename
    target.rename(outside)
    target.symlink_to(outside)
    assert JobRegistry(str(project)).list_ids() == ["valid"]


def test_registry_does_not_follow_outward_bidsignore(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "ignore"
    outside.write_text("outside sentinel")
    (project / ".bidsignore").symlink_to(outside)
    with pytest.raises(PermissionError):
        JobRegistry(str(project))
    assert outside.read_text() == "outside sentinel"


def test_registry_deleting_in_project_alias_preserves_target(tmp_path):
    registry = JobRegistry(str(tmp_path))
    target = tmp_path / "keep"
    target.mkdir()
    sentinel = target / "sentinel"
    sentinel.write_text("keep me")
    alias = tmp_path / "code" / "ti-toolbox" / "jobs" / "alias"
    alias.symlink_to(target, target_is_directory=True)
    assert registry.delete("alias")
    assert sentinel.read_text() == "keep me"
    assert not alias.is_symlink()


@pytest.mark.parametrize("filename", ["spec.json", "status.json"])
def test_registry_atomic_write_replaces_in_project_alias(tmp_path, filename):
    registry = JobRegistry(str(tmp_path))
    spec = _spec("j1")
    registry.create(spec, JobStatus.queued(spec))
    target = tmp_path / "keep.json"
    target.write_text("keep me")
    alias = tmp_path / "code" / "ti-toolbox" / "jobs" / "j1" / filename
    alias.unlink()
    alias.symlink_to(target)
    if filename == "spec.json":
        registry.write_spec(spec)
    else:
        registry.write_status(JobStatus.queued(spec))
    assert target.read_text() == "keep me"
    assert not alias.is_symlink()


def test_registry_reads_legacy_viewer_kind_job_without_crashing(tmp_path):
    # "viewer" was removed from JobKind/JOB_KINDS (D3 -- no server-side job for the embedded
    # Tetravox viewer any more), but a spec.json/status.json written before that change may
    # still have kind="viewer" on disk. JobSpec/JobStatus.kind is a plain str field with no
    # enum validation on load, so the registry must read it back as unknown/legacy data, never
    # raise.
    registry = JobRegistry(str(tmp_path))
    spec = _spec("legacy1", kind="viewer", config={"program": "freeview", "args": []})
    status = JobStatus.queued(spec)
    registry.create(spec, status)

    read_back = registry.read_spec("legacy1")
    assert read_back is not None
    assert read_back.kind == "viewer"
    assert registry.read_status("legacy1").kind == "viewer"
    assert "legacy1" in registry.list_ids()


def test_registry_creation_adds_bidsignore_line(tmp_path):
    assert not (tmp_path / ".bidsignore").exists()
    JobRegistry(str(tmp_path))
    lines = (tmp_path / ".bidsignore").read_text(encoding="utf-8").splitlines()
    assert BIDSIGNORE_LINE in lines


def test_registry_creation_does_not_duplicate_bidsignore_line_on_reopen(tmp_path):
    JobRegistry(str(tmp_path))
    JobRegistry(str(tmp_path))  # a second open (e.g. server restart) is idempotent
    lines = (tmp_path / ".bidsignore").read_text(encoding="utf-8").splitlines()
    assert lines.count(BIDSIGNORE_LINE) == 1


def test_ensure_bidsignore_preserves_existing_lines(tmp_path):
    (tmp_path / ".bidsignore").write_text("*_ct.nii.gz\n", encoding="utf-8")
    ensure_bidsignore(str(tmp_path))
    lines = (tmp_path / ".bidsignore").read_text(encoding="utf-8").splitlines()
    assert lines == ["*_ct.nii.gz", BIDSIGNORE_LINE]


def test_ensure_bidsignore_is_idempotent_when_line_already_present(tmp_path):
    (tmp_path / ".bidsignore").write_text(f"{BIDSIGNORE_LINE}\n", encoding="utf-8")
    ensure_bidsignore(str(tmp_path))
    lines = (tmp_path / ".bidsignore").read_text(encoding="utf-8").splitlines()
    assert lines == [BIDSIGNORE_LINE]


def test_ensure_bidsignore_creates_file_when_missing(tmp_path):
    assert not (tmp_path / ".bidsignore").exists()
    ensure_bidsignore(str(tmp_path))
    lines = (tmp_path / ".bidsignore").read_text(encoding="utf-8").splitlines()
    assert lines == [BIDSIGNORE_LINE]


def test_registry_write_status_is_atomic_no_partial_file(tmp_path):
    registry = JobRegistry(str(tmp_path))
    spec = _spec("j1")
    status = JobStatus.queued(spec)
    registry.create(spec, status)
    status.state = "running"
    status.started_at = "2026-01-01T00:00:00+00:00"
    registry.write_status(status)
    # no leftover temp files
    leftovers = [f for f in os.listdir(job_dir(str(tmp_path), "j1")) if ".tmp-" in f]
    assert leftovers == []
    assert registry.read_status("j1").state == "running"


def test_registry_read_missing_job_returns_none(tmp_path):
    registry = JobRegistry(str(tmp_path))
    assert registry.read_spec("nope") is None
    assert registry.read_status("nope") is None


def test_registry_log_tail(tmp_path):
    registry = JobRegistry(str(tmp_path))
    spec = _spec("j1")
    registry.create(spec, JobStatus.queued(spec))
    log_path = os.path.join(job_dir(str(tmp_path), "j1"), "stdout.log")
    with open(log_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(f"line {i}" for i in range(10)) + "\n")
    assert (
        registry.read_log_tail("j1") == "\n".join(f"line {i}" for i in range(10)) + "\n"
    )
    assert registry.read_log_tail("j1", tail=3) == "line 7\nline 8\nline 9\n"


def test_registry_delete(tmp_path):
    registry = JobRegistry(str(tmp_path))
    spec = _spec("j1")
    registry.create(spec, JobStatus.queued(spec))
    assert registry.delete("j1") is True
    assert registry.read_spec("j1") is None
    assert registry.delete("j1") is False


def test_registry_list_ids_excludes_locks_dir(tmp_path):
    registry = JobRegistry(str(tmp_path))
    registry.create(_spec("j1"), JobStatus.queued(_spec("j1")))
    os.makedirs(os.path.join(jobs_root(str(tmp_path)), ".locks", "abcd"), exist_ok=True)
    assert registry.list_ids() == ["j1"]


def test_registry_prune_keeps_running_and_recent_terminal(tmp_path):
    registry = JobRegistry(str(tmp_path))
    now = 2_000_000_000.0  # arbitrary fixed "now"
    import datetime as dt

    def iso(offset_days: float) -> str:
        return (
            dt.datetime.fromtimestamp(now, tz=dt.timezone.utc)
            - dt.timedelta(days=offset_days)
        ).isoformat()

    old_done = _spec("old")
    old_status = JobStatus.queued(old_done)
    old_status.state = "succeeded"
    old_status.finished_at = iso(60)  # 60 days old -> pruned
    registry.create(old_done, old_status)

    recent_done = _spec("recent")
    recent_status = JobStatus.queued(recent_done)
    recent_status.state = "failed"
    recent_status.finished_at = iso(1)
    registry.create(recent_done, recent_status)

    running = _spec("running")
    running_status = JobStatus.queued(running)
    running_status.state = "running"
    registry.create(running, running_status)

    removed = registry.prune(keep_count=200, keep_days=30, now=now)
    assert removed == ["old"]
    remaining = set(registry.list_ids())
    assert remaining == {"recent", "running"}


def test_registry_prune_keep_count(tmp_path):
    registry = JobRegistry(str(tmp_path))
    for i in range(5):
        spec = _spec(f"j{i}")
        status = JobStatus.queued(spec)
        status.state = "succeeded"
        status.created_at = f"2026-01-0{i + 1}T00:00:00+00:00"
        status.finished_at = status.created_at
        registry.create(spec, status)
    removed = registry.prune(keep_count=2, keep_days=3650)
    assert set(removed) == {"j0", "j1", "j2"}
    assert set(registry.list_ids()) == {"j3", "j4"}


# ---------------------------------------------------------------------------------------------
# tailer.py
# ---------------------------------------------------------------------------------------------


def test_read_events_assigns_seq_by_line_and_skips_malformed(tmp_path):
    path = tmp_path / "events.jsonl"
    lines = [
        json.dumps({"type": "log", "ts": 1, "msg": "a"}),
        "not json",
        json.dumps({"type": "log", "ts": 2, "msg": "b"}),
    ]
    path.write_text("\n".join(lines) + "\n")
    events = read_events(str(path))
    assert [e["seq"] for e in events] == [0, 2]
    assert [e["msg"] for e in events] == ["a", "b"]


def test_read_events_since(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(json.dumps({"type": "log", "msg": str(i)}) for i in range(5)) + "\n"
    )
    events = read_events(str(path), since=3)
    assert [e["seq"] for e in events] == [3, 4]


def test_read_events_missing_file(tmp_path):
    assert read_events(str(tmp_path / "nope.jsonl")) == []


def test_line_count(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("a\nb\n\nc\n")
    assert line_count(str(path)) == 3


def test_event_tailer_incremental_poll(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text("")
    tailer = EventTailer(str(path))
    assert tailer.poll() == []

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "log", "msg": "1"}) + "\n")
    first = tailer.poll()
    assert [e["seq"] for e in first] == [0]
    assert tailer.poll() == []  # no new bytes -> no re-read

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "log", "msg": "2"}) + "\n")
        fh.write(json.dumps({"type": "log", "msg": "3"}) + "\n")
    second = tailer.poll()
    assert [e["seq"] for e in second] == [1, 2]


def test_event_tailer_start_seq_for_reattach(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        "\n".join(json.dumps({"type": "log", "msg": str(i)}) for i in range(3)) + "\n"
    )
    tailer = EventTailer(str(path), start_seq=line_count(str(path)))
    assert tailer.poll() == []
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "log", "msg": "new"}) + "\n")
    events = tailer.poll()
    assert [e["seq"] for e in events] == [3]
