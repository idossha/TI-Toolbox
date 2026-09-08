"""Host tests for :mod:`tit.storage` — what the project costs, by kind.

The figures on the System page's Storage card are only worth showing if they
agree with `du`, so the three things that make them disagree are what these
tests are about: apparent size vs real disk usage, hardlinks counted twice, and
a classification that quietly drops real outputs into "Other".
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from tit.paths import get_path_manager  # noqa: E402
from tit import storage  # noqa: E402


def _write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """A project with one file in each of the kinds the card lists."""
    pm = get_path_manager(str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    _write(Path(pm.bids_anat("101")) / "sub-101_T1w.nii.gz", 4096)
    _write(Path(pm.sourcedata_subject("101")) / "dicom" / "0001.dcm", 8192)
    _write(Path(pm.m2m("101")) / "final_tissues.nii.gz", 16384)
    _write(Path(pm.leadfields("101")) / "leadfield.hdf5", 32768)
    _write(Path(pm.flex_search("101")) / "run1" / "result.csv", 2048)
    _write(Path(pm.ex_search("101")) / "run1" / "final.csv", 2048)
    _write(Path(pm.ti_mesh_dir("101", "simA")) / "TI.msh", 65536)
    _write(Path(pm.analysis_dir("101", "simA", "mesh")) / "summary.csv", 1024)
    _write(Path(pm.reports()) / "report.html", 1024)
    _write(Path(pm.fastsurfer()) / "sub-101" / "aparc.mgz", 4096)
    _write(tmp_path / "notes" / "scratch.txt", 512)
    return tmp_path


def _by_kind(result: storage.ProjectStorage) -> dict[str, int]:
    return {k.kind: k.bytes for k in result.kinds}


def test_every_kind_lands_in_its_own_bucket(project: Path) -> None:
    kinds = _by_kind(storage.scan_project())
    for expected in (
        "raw",
        "sourcedata",
        "head_models",
        "leadfields",
        "flex_search",
        "ex_search",
        "simulations",
        "analyses",
        "reports",
        "surfaces",
    ):
        assert kinds.get(expected, 0) > 0, f"{expected} was not attributed"
    # A file that belongs to nothing the toolbox writes is "Other", not silently
    # folded into whichever kind happens to be nearest in the tree.
    assert kinds.get("other", 0) > 0


def test_an_analysis_is_not_counted_as_the_simulation_that_produced_it(
    project: Path,
) -> None:
    """Longest-prefix-wins is the whole mechanism: `Simulations/<sim>/Analyses/`
    is nested inside `Simulations/`, and a plain "starts with" match would put
    every analysis in the simulations bucket."""
    pm = get_path_manager()
    prefixes = storage.kind_prefixes(pm)
    analysis = os.path.join(pm.analysis_dir("101", "simA", "mesh"), "summary.csv")
    mesh = os.path.join(pm.ti_mesh_dir("101", "simA"), "TI.msh")
    assert storage.classify(analysis, prefixes) == "analyses"
    assert storage.classify(mesh, prefixes) == "simulations"


def test_the_kinds_sum_to_the_total(project: Path) -> None:
    result = storage.scan_project()
    assert sum(k.bytes for k in result.kinds) == result.total_bytes
    assert sum(k.files for k in result.kinds) == result.total_files


def test_a_hardlinked_file_is_counted_once(tmp_path: Path) -> None:
    """QSIPrep and several of our own steps hardlink rather than copy. Summing
    per-file sizes made the project total exceed the size of the volume."""
    get_path_manager(str(tmp_path))
    original = tmp_path / "sourcedata" / "big.nii"
    _write(original, 100_000)
    link = tmp_path / "sourcedata" / "same-file.nii"
    os.link(original, link)

    result = storage.scan_project()
    single = storage.scan_project(pm=get_path_manager())
    assert result.total_bytes == single.total_bytes
    # One inode, one count -- despite two directory entries.
    assert result.total_files == 1


def test_a_symlink_is_not_followed_out_of_the_project(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-the-project"
    outside.mkdir(exist_ok=True)
    _write(outside / "huge.bin", 50_000)
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    get_path_manager(str(project_dir))
    _write(project_dir / "sourcedata" / "real.dcm", 1024)
    os.symlink(outside, project_dir / "sourcedata" / "linked")

    result = storage.scan_project()
    # The 50 kB outside the project is not ours to report, and following the
    # link would also have double-counted anything inside it.
    assert result.total_files == 1


def test_real_disk_usage_not_apparent_size(tmp_path: Path) -> None:
    """`st_blocks * 512` is what the filesystem charges. A 1-byte file does not
    cost one byte, and a storage page that says it does is wrong in the
    direction that matters (thousands of small meshes)."""
    get_path_manager(str(tmp_path))
    _write(tmp_path / "sourcedata" / "tiny.txt", 1)
    result = storage.scan_project()
    st = os.stat(tmp_path / "sourcedata" / "tiny.txt")
    if hasattr(st, "st_blocks"):
        assert result.total_bytes == st.st_blocks * storage.BLOCK_BYTES
        assert result.total_bytes > 1


def test_the_cache_round_trips_and_ages(project: Path) -> None:
    result = storage.scan_project()
    storage.save_cache(result)
    loaded = storage.load_cache()
    assert loaded is not None
    assert loaded.total_bytes == result.total_bytes
    assert _by_kind(loaded) == _by_kind(result)

    assert storage.is_stale(None) is True
    assert storage.is_stale(loaded, now=loaded.scanned_at + 1) is False
    assert storage.is_stale(loaded, now=loaded.scanned_at + storage.STALE_AFTER_S + 1) is True


def test_a_scan_can_be_abandoned_and_says_so(project: Path) -> None:
    """A partial result is labelled, never presented as a complete total."""
    result = storage.scan_project(should_stop=lambda: True)
    assert result.partial is True


def test_an_unreadable_directory_does_not_abort_the_walk(project: Path) -> None:
    blocked = project / "sourcedata" / "locked"
    blocked.mkdir(parents=True, exist_ok=True)
    (blocked / "f.bin").write_bytes(b"x" * 1024)
    os.chmod(blocked, 0o000)
    try:
        result = storage.scan_project()
        # The rest of the project is still counted.
        assert result.total_bytes > 0
        assert _by_kind(result).get("head_models", 0) > 0
    finally:
        os.chmod(blocked, 0o755)


def test_scanned_at_is_stamped(project: Path) -> None:
    before = time.time()
    result = storage.scan_project()
    assert result.scanned_at >= before
    assert result.duration_s >= 0
