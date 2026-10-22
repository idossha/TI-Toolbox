"""The scene real-data suite's mirror keeps writes out of the dataset it reads.

What this pins
    tests/test_scene_realdata.py used to build its scene cache inside the project it was
    pointed at, which for Dataset 000 is a read-only, shared dataset. It now builds in a tree
    of symlinks under tmp_path. Checked here on a synthetic project, on every host: a file
    written into the mirror stays in the mirror, the project's own ``.ti-toolbox`` cache is
    not carried over (so the suite cannot reuse a stale cache), every project file is
    reachable through the mirror, and the before/after listing notices a changed file.
"""

from __future__ import annotations

import os

from tests.test_scene_realdata import _file_listing, _symlink_mirror


def _project(tmp_path):
    source = tmp_path / "000"
    (source / "derivatives" / "SimNIBS" / "sub-ernie").mkdir(parents=True)
    (source / "derivatives" / "SimNIBS" / "sub-ernie" / "ernie.msh").write_bytes(
        b"mesh"
    )
    (source / "dataset_description.json").write_text("{}", encoding="utf-8")
    (source / ".ti-toolbox" / "cache" / "scene").mkdir(parents=True)
    (source / ".ti-toolbox" / "cache" / "scene" / "old.tvsc").write_bytes(b"stale")
    return source


def test_writes_land_in_the_mirror_and_never_in_the_project(tmp_path):
    source = _project(tmp_path)
    before = _file_listing(source)
    mirror = tmp_path / "mirror"

    _symlink_mirror(source, mirror)
    cache = mirror / ".ti-toolbox" / "cache" / "scene" / "sub-ernie"
    cache.mkdir(parents=True)
    (cache / "skin.tvsc").write_bytes(b"new")

    assert _file_listing(source) == before
    assert not (source / ".ti-toolbox" / "cache" / "scene" / "sub-ernie").exists()
    mesh = mirror / "derivatives" / "SimNIBS" / "sub-ernie" / "ernie.msh"
    assert mesh.is_symlink() and mesh.read_bytes() == b"mesh"
    assert not (mirror / ".ti-toolbox" / "cache" / "scene" / "old.tvsc").exists()
    assert set(_file_listing(mirror)) == {
        "dataset_description.json",
        os.path.join("derivatives", "SimNIBS", "sub-ernie", "ernie.msh"),
        os.path.join(".ti-toolbox", "cache", "scene", "sub-ernie", "skin.tvsc"),
    }


def test_copied_sources_resolve_inside_the_mirror(tmp_path):
    """The scene builders refuse a source whose real path leaves the project."""
    source = _project(tmp_path)
    mirror = tmp_path / "mirror"
    _symlink_mirror(source, mirror, ("derivatives/SimNIBS/sub-ernie",))
    mesh = mirror / "derivatives" / "SimNIBS" / "sub-ernie" / "ernie.msh"
    assert not mesh.is_symlink() and mesh.read_bytes() == b"mesh"
    assert os.path.realpath(mesh).startswith(os.path.realpath(mirror))
    original = source / "derivatives" / "SimNIBS" / "sub-ernie" / "ernie.msh"
    assert mesh.stat().st_mtime_ns == original.stat().st_mtime_ns
    assert (mirror / "dataset_description.json").is_symlink()


def test_the_listing_notices_a_changed_project_file(tmp_path):
    source = _project(tmp_path)
    before = _file_listing(source)
    (source / "dataset_description.json").write_text('{"Name": "x"}', encoding="utf-8")
    assert _file_listing(source) != before
