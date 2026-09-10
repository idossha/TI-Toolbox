"""The scene cache under ``derivatives/`` (plan §2.2, lane SCA, 2026-09-04).

What this pins
    That a fingerprint actually changes when a source file changes, that a
    reader never sees a half-written payload, that a stale generation is
    deleted rather than accumulating a copy per ``charm`` run, that the cache
    directory reaches ``.bidsignore``, and that two subjects do not share one
    build lock.

Where the numbers come from
    ``os.stat``: every fingerprint expectation is derived by mutating a file
    and re-reading its own ``st_size``/``st_mtime_ns``, never by recording a
    hash literal (a recorded hash would pin the hash function, not the
    behaviour).

Deliberately elsewhere
    Route-level 202/ETag behaviour is ``tests/test_scene_routes.py``; real
    build timings are ``tests/test_scene_realdata.py`` (env-gated).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from tit.scene import cache


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / "dataset_description.json").write_text("{}")
    return tmp_path


def _source(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


# ── fingerprints ─────────────────────────────────────────────────────────────


def test_fingerprint_changes_when_a_source_file_changes(tmp_path: Path) -> None:
    """A re-run of charm must invalidate the surfaces it produced."""
    source = _source(tmp_path, "ernie.msh", "one")
    before = cache.fingerprint([source])

    os.utime(source, (1_000_000, 1_000_000))
    assert cache.fingerprint([source]) != before

    source.write_text("one two three")  # size changes too
    assert cache.fingerprint([source]) != before


def test_fingerprint_is_stable_for_an_untouched_file(tmp_path: Path) -> None:
    source = _source(tmp_path, "ernie.msh", "one")
    assert cache.fingerprint([source]) == cache.fingerprint([source])


def test_fingerprint_distinguishes_a_missing_source(tmp_path: Path) -> None:
    """A subject with no rh annotation still gets a distinct, stable key."""
    present = _source(tmp_path, "lh.annot", "x")
    missing = tmp_path / "rh.annot"
    both_missing = cache.fingerprint([tmp_path / "lh.annot.nope", missing])
    one_present = cache.fingerprint([present, missing])
    assert both_missing != one_present
    assert cache.fingerprint([present, missing]) == one_present


def test_fingerprint_depends_on_the_order_and_identity_of_sources(
    tmp_path: Path,
) -> None:
    a = _source(tmp_path, "a.bin", "aaa")
    b = _source(tmp_path, "b.bin", "aaa")  # same size, different name
    assert cache.fingerprint([a, b]) != cache.fingerprint([b, a])


# ── publish / find / prune ───────────────────────────────────────────────────


def test_publish_then_find_returns_the_bytes_and_the_sidecar(project: Path) -> None:
    published = cache.publish(project, "ernie", "gm", "abc123", b"BLOB", {"triangles": 7})

    assert published.path.read_bytes() == b"BLOB"
    assert published.meta["triangles"] == 7
    assert published.meta["bytes"] == 4  # publish() records the real length
    assert published.meta["fingerprint"] == "abc123"
    assert published.meta["key"] == "gm"

    found = cache.find_cached(project, "ernie", "gm", "abc123")
    assert found is not None
    assert found.path == published.path
    assert found.meta == published.meta


def test_cache_lives_under_derivatives_ti_toolbox(project: Path) -> None:
    """§2.2's path, spelled out -- other tooling globs for it."""
    cache.publish(project, "ernie", "skin", "f0", b"x", {})
    expected = project / "derivatives" / "ti-toolbox" / "scene_cache" / "sub-ernie"
    assert expected.is_dir()
    assert (expected / "skin.f0.tvsc").is_file()
    assert (expected / "skin.f0.json").is_file()
    assert cache.cache_dir(project, "ernie") == expected


def test_find_cached_is_none_for_another_fingerprint(project: Path) -> None:
    cache.publish(project, "ernie", "gm", "old", b"x", {})
    assert cache.find_cached(project, "ernie", "gm", "new") is None


def test_a_payload_without_its_sidecar_is_not_a_cache_hit(project: Path) -> None:
    """Half an entry carries no counts, and the manifest would have to guess."""
    published = cache.publish(project, "ernie", "gm", "f0", b"x", {})
    published.sidecar.unlink()
    assert cache.find_cached(project, "ernie", "gm", "f0") is None


def test_a_corrupt_sidecar_is_not_a_cache_hit(project: Path) -> None:
    published = cache.publish(project, "ernie", "gm", "f0", b"x", {})
    published.sidecar.write_text("{not json")
    assert cache.find_cached(project, "ernie", "gm", "f0") is None


def test_publishing_a_new_generation_deletes_the_old_one(project: Path) -> None:
    """Otherwise the cache grows a full copy of every surface per charm run."""
    cache.publish(project, "ernie", "gm", "old", b"x" * 10, {})
    cache.publish(project, "ernie", "gm", "new", b"y" * 10, {})

    root = cache.cache_dir(project, "ernie")
    assert sorted(p.name for p in root.iterdir()) == ["gm.new.json", "gm.new.tvsc"]


def test_pruning_one_key_leaves_the_other_keys_alone(project: Path) -> None:
    cache.publish(project, "ernie", "gm", "f1", b"a", {})
    cache.publish(project, "ernie", "skin", "f1", b"b", {})
    cache.publish(project, "ernie", "labels-DK40", "f1", b"c", {})

    cache.publish(project, "ernie", "gm", "f2", b"a2", {})

    names = sorted(p.name for p in cache.cache_dir(project, "ernie").iterdir())
    assert "skin.f1.tvsc" in names
    assert "labels-DK40.f1.tvsc" in names
    assert "gm.f1.tvsc" not in names
    assert "gm.f2.tvsc" in names


def test_publish_leaves_no_temporary_files_behind(project: Path) -> None:
    """A leaked ``.tmp-*`` would be served to nobody and deleted by nothing."""
    cache.publish(project, "ernie", "gm", "f0", b"x", {})
    leftovers = [p.name for p in cache.cache_dir(project, "ernie").iterdir() if ".tmp-" in p.name]
    assert leftovers == []


def test_sidecar_is_valid_json_a_second_process_can_read(project: Path) -> None:
    published = cache.publish(project, "ernie", "gm", "f0", b"x", {"vertices": 3})
    assert json.loads(published.sidecar.read_text())["vertices"] == 3


# ── .bidsignore ──────────────────────────────────────────────────────────────


def test_publishing_adds_the_cache_to_bidsignore(project: Path) -> None:
    cache.publish(project, "ernie", "gm", "f0", b"x", {})
    assert cache.BIDSIGNORE_LINE in (project / ".bidsignore").read_text().splitlines()


def test_bidsignore_keeps_the_user_s_own_lines(project: Path) -> None:
    """Users curate this file by hand; rewriting it would delete their entries."""
    (project / ".bidsignore").write_text("*_ct.nii.gz\n*_ct.json\n")
    cache.ensure_bidsignore(project)
    lines = (project / ".bidsignore").read_text().splitlines()
    assert lines == ["*_ct.nii.gz", "*_ct.json", cache.BIDSIGNORE_LINE]


def test_bidsignore_is_idempotent(project: Path) -> None:
    cache.ensure_bidsignore(project)
    cache.ensure_bidsignore(project)
    lines = (project / ".bidsignore").read_text().splitlines()
    assert lines.count(cache.BIDSIGNORE_LINE) == 1


def test_a_read_only_project_still_serves_scenes(tmp_path: Path) -> None:
    """A validator warning must never be the reason a pane fails to load."""
    project = tmp_path / "ro"
    project.mkdir()
    (project / ".bidsignore").write_text("keep\n")
    os.chmod(project / ".bidsignore", 0o444)
    try:
        cache.ensure_bidsignore(project)  # must not raise
    finally:
        os.chmod(project / ".bidsignore", 0o644)


# ── locking ──────────────────────────────────────────────────────────────────


def test_one_lock_per_subject_and_project(project: Path) -> None:
    """Two subjects must be able to build at the same time; one must not."""
    assert cache.subject_lock(project, "ernie") is cache.subject_lock(project, "ernie")
    assert cache.subject_lock(project, "ernie") is not cache.subject_lock(project, "101")
    assert cache.subject_lock(project, "ernie") is not cache.subject_lock(
        project / "other", "ernie"
    )


def test_the_subject_lock_actually_serialises(project: Path) -> None:
    lock = cache.subject_lock(project, "ernie")
    order: list[str] = []

    def worker() -> None:
        with lock:
            order.append("in")
            order.append("out")

    with lock:
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(timeout=0.2)
        assert order == [], "the second builder entered while the lock was held"
    thread.join(timeout=2.0)
    assert order == ["in", "out"]
