"""Viewer boundary regression fixtures use real links and authored sentinel bytes.

Run: python3 -m pytest tests/test_viewspec_path_boundaries.py -q.
Numerical behavior belongs to the existing volume-statistics suites; these tests
prove which files may be read or modified before any scientific computation.
"""

import json
import os
from pathlib import Path

import pytest

from tit import viewspec
from tit.paths import PathManager


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    pm = PathManager(str(root))
    monkeypatch.setattr(viewspec, "get_path_manager", lambda: pm)
    return root


@pytest.mark.parametrize("component", ["directory", "leaf"])
@pytest.mark.parametrize("outside", [False, True])
def test_stats_cache_symlinks_cannot_escape_project(project, component, outside):
    volume = project / "volume.nii"
    volume.write_bytes(b"volume")
    st = volume.stat()
    stats = {key: 1.0 for key in viewspec._STATS_KEYS}
    original = json.dumps(
        {
            "version": viewspec._STATS_VERSION,
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "stats": stats,
        }
    )
    cache = Path(viewspec.stats_cache_dir())
    cache.mkdir(parents=True)
    entry = Path(viewspec._stats_sidecar_path(str(volume)))
    destination = (project.parent if outside else project) / "relocated"
    destination.mkdir()
    target = destination / entry.name
    target.write_text(original)
    if component == "directory":
        cache.rmdir()
        cache.symlink_to(destination, target_is_directory=True)
    else:
        entry.symlink_to(target)
    result = viewspec._read_stats_sidecar(str(volume), st)
    assert result == (None if outside else stats)
    viewspec._write_stats_sidecar(str(volume), st, {"replacement": 2.0})
    if outside or component == "leaf":
        assert target.read_text() == original
    else:
        assert json.loads(target.read_text())["stats"] == {"replacement": 2.0}
    if not outside and component == "leaf":
        assert not entry.is_symlink()
        assert json.loads(entry.read_text())["stats"] == {"replacement": 2.0}


@pytest.mark.parametrize("outside", [False, True])
def test_stats_cache_predictable_partial_link_is_untouched(project, outside):
    volume = project / "volume.nii"
    volume.write_bytes(b"volume")
    target = Path(viewspec._stats_sidecar_path(str(volume)))
    target.parent.mkdir(parents=True)
    sentinel = (project.parent if outside else project) / "sentinel"
    sentinel.write_text("unchanged")
    partial = Path(f"{target}.{os.getpid()}.partial")
    partial.symlink_to(sentinel)
    viewspec._write_stats_sidecar(str(volume), volume.stat(), {"min": 1.0})
    assert sentinel.read_text() == "unchanged"
    assert partial.is_symlink()
    assert json.loads(target.read_text())["stats"] == {"min": 1.0}


@pytest.mark.parametrize("outside", [False, True])
@pytest.mark.parametrize("component", ["directory", "leaf"])
def test_named_subject_view_checks_volume_before_reading(
    project, monkeypatch, outside, component
):
    pm = viewspec.get_path_manager()
    m2m = Path(pm.m2m("ernie"))
    destination = (project.parent if outside else project) / "anatomy"
    destination.mkdir()
    volume = destination / "T1.nii.gz"
    volume.write_bytes(b"volume")
    if component == "directory":
        m2m.parent.mkdir(parents=True)
        m2m.symlink_to(destination, target_is_directory=True)
    else:
        m2m.mkdir(parents=True)
        (m2m / "T1.nii.gz").symlink_to(volume)
    reads = []

    def record_stats(path):
        reads.append(os.path.realpath(path))
        return None

    # Record at the numerical-reader boundary; a rejected file must never get here.
    monkeypatch.setattr(viewspec, "_volume_stats", record_stats)
    monkeypatch.setattr(viewspec, "_volume_bounds", lambda _: None)
    result = viewspec.build_view("subject", subject="ernie")
    assert (str(volume) in reads) is not outside
    assert bool(result["layers"]) is not outside


@pytest.mark.parametrize("outside", [False, True])
def test_analysis_cursor_checks_json_link_before_reading(project, outside):
    pm = viewspec.get_path_manager()
    analysis = Path(pm.simulation("ernie", "run")) / "Analyses/Voxel/Boundary"
    analysis.mkdir(parents=True)
    target = (project.parent if outside else project) / "analysis.json"
    target.write_text('{"center":[11,22,33]}')
    (analysis / "analysis.json").symlink_to(target)
    assert viewspec._analysis_cursor(pm, "ernie", "run", "Boundary") == (
        None if outside else [11.0, 22.0, 33.0]
    )


@pytest.mark.parametrize("failure", ["collision", "replace"])
def test_stats_cache_atomic_failure_cleans_only_owned_temp(
    project, monkeypatch, failure
):
    volume = project / "volume.nii"
    volume.write_bytes(b"volume")
    target = Path(viewspec._stats_sidecar_path(str(volume)))
    target.parent.mkdir(parents=True)
    target.write_text("original cache")
    monkeypatch.setattr(viewspec.secrets, "token_hex", lambda _: "fixed")
    temporary = target.parent / ".stats-fixed.partial"
    sentinel = project.parent / "sentinel"
    sentinel.write_text("unchanged")
    if failure == "collision":
        temporary.symlink_to(sentinel)
    else:

        def fail_replace(*args):
            raise OSError("authored replace failure")

        monkeypatch.setattr(viewspec.os, "replace", fail_replace)
    viewspec._write_stats_sidecar(str(volume), volume.stat(), {"min": 1.0})
    assert target.read_text() == "original cache"
    assert sentinel.read_text() == "unchanged"
    assert temporary.is_symlink() if failure == "collision" else not temporary.exists()


def test_analysis_cursor_refuses_absolute_directory(project):
    pm = viewspec.get_path_manager()
    outside = project.parent / "outside-analysis"
    outside.mkdir()
    (outside / "analysis.json").write_text('{"center":[11,22,33]}')
    assert viewspec._analysis_cursor(pm, "ernie", "run", str(outside)) is None
