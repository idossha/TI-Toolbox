"""Host tests for :mod:`tit.storage` — what the project costs, by kind.

The figures on the System page's Storage card are only worth showing if they
agree with `du`, so the three things that make them disagree are what these
tests are about: apparent size vs real disk usage, hardlinks counted twice, and
a classification that quietly drops real outputs into "Other".
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
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
    assert (
        storage.is_stale(loaded, now=loaded.scanned_at + storage.STALE_AFTER_S + 1)
        is True
    )


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


# ── p24: QSIPrep/QSIRecon work dirs, wrong-shaped caches, Dataset 000 ─────────
#
# What these pin (package p24, audit_jobs-telemetry.md "realdata storage scan",
# 2026-10-22): a read-only scan of Dataset 000 put 1.73 GB in "Other", almost all
# of it derivatives/.qsiprep_work -- the scratch dirs the QSIPrep/QSIRecon
# containers are given -- because those paths were written by hand in the docker
# builder and nowhere in the storage classification. And a cache file whose JSON
# is valid but the wrong shape (a list, a non-dict kind) made load_cache raise
# AttributeError, so GET /api/system/storage answered 500 until the file was
# deleted by hand. Expected values: the work dir is whatever the builder mounts
# (read from the docker argv, not retyped); sizes are st_blocks * 512 (POSIX);
# Dataset 000's total is checked against `du -sk`, an independent reader.


def _mount_source(cmd: list[str], target: str) -> str:
    """The host source of the ``--mount`` whose target is *target*."""
    for i, arg in enumerate(cmd[:-1]):
        if arg != "--mount":
            continue
        row = next(csv.reader([cmd[i + 1]]))
        fields = dict(f.split("=", 1) for f in row if "=" in f)
        if fields.get("target") == target:
            return fields["source"]
    raise AssertionError(f"no mount targets {target}: {cmd}")


@pytest.mark.parametrize("stage", ["qsiprep", "qsirecon"])
def test_qsi_work_dirs_are_rebuildable_cache_not_other(
    tmp_path: Path, monkeypatch, stage: str
) -> None:
    from tit.pre.qsi import docker_builder
    from tit.pre.qsi.config import QSIPrepConfig, QSIReconConfig

    get_path_manager(str(tmp_path))
    (tmp_path / "dataset_description.json").write_text("{}")
    monkeypatch.setattr(docker_builder, "get_host_project_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        docker_builder, "get_inherited_dood_resources", lambda *a, **k: (4, 16)
    )
    builder = docker_builder.DockerCommandBuilder(str(tmp_path))
    builder._host_license_path = None
    if stage == "qsiprep":
        cmd = builder.build_qsiprep_cmd(QSIPrepConfig(subject_id="001"))
    else:
        cmd = builder.build_qsirecon_cmd(QSIReconConfig(subject_id="001"), "dipy_dki")
    work = Path(_mount_source(cmd, builder.paths.work_dir))
    assert work.parent == tmp_path / "derivatives"  # the builder's own scratch dir
    scratch = work / "qsiprep_wf" / "sub_001_wf" / "fmap.nii.gz"
    _write(scratch, 50_000)

    kinds = _by_kind(storage.scan_project())
    expected = os.stat(scratch).st_blocks * storage.BLOCK_BYTES
    # Everything else here (dataset_description.json, the license the builder
    # stages) belongs to no kind: "Other" is exactly those files, not the scratch.
    rest = sum(
        os.stat(p).st_blocks * storage.BLOCK_BYTES
        for p in tmp_path.rglob("*")
        if p.is_file() and work not in p.parents
    )
    assert kinds.get("cache", 0) == expected
    assert kinds.get("other", 0) == rest


@pytest.mark.parametrize(
    "payload",
    [
        [],
        ["kinds"],
        {"kinds": [1]},
        {"kinds": "abc"},
        {"largest": ["sub-101"]},
        {"total_bytes": [1]},
        {"scanned_at": {"t": 1}},
    ],
    ids=[
        "list",
        "list-of-str",
        "kind-int",
        "kinds-str",
        "largest-str",
        "bytes-list",
        "time-dict",
    ],
)
def test_a_wrong_shaped_cache_is_no_cache(tmp_path: Path, payload) -> None:
    pm = get_path_manager(str(tmp_path))
    path = Path(storage.cache_path(pm))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))
    assert storage.load_cache(pm) is None


def test_the_storage_route_answers_over_a_wrong_shaped_cache(
    tmp_path: Path, monkeypatch
) -> None:
    """No 500 for good: the route answers "never scanned" and starts the scan that
    replaces the bad file."""
    pytest.importorskip("fastapi")
    from tit.server.routes import system

    pm = get_path_manager(str(tmp_path))
    path = Path(storage.cache_path(pm))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"kinds": [1], "total_bytes": 7}')
    started: list[bool] = []
    monkeypatch.setattr(system, "start_scan", lambda: started.append(True) or True)
    snapshot = system.storage_snapshot()
    assert started == [True]
    assert snapshot.total_bytes == 0
    assert snapshot.kinds == []


_DATASET = os.environ.get("TIT_DATASET_000", "")
_HAVE_DATASET = bool(_DATASET) and os.path.isdir(
    os.path.join(_DATASET, "derivatives", "SimNIBS")
)


def _mtimes(root: str) -> dict[str, int]:
    """Every path under *root* with its mtime, to prove a read left it untouched."""
    out = {root: os.lstat(root).st_mtime_ns}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = os.path.join(dirpath, name)
            out[path] = os.lstat(path).st_mtime_ns
    return out


@pytest.mark.skipif(
    not _HAVE_DATASET,
    reason="skipping: TIT_DATASET_000 is unset or not a Dataset 000 copy",
)
def test_dataset_000_scan_sums_agrees_with_du_and_leaves_little_in_other() -> None:
    """Read-only (never save_cache): the scan of Dataset 000 against ``du -sk``.

    Run: ``TIT_DATASET_000=/Users/idohaber/datasets/000 .venv/bin/python -m pytest
    tests/test_storage_scan.py -q -k dataset_000``.
    """
    root = os.path.realpath(_DATASET)
    before = _mtimes(root)
    result = storage.scan_project(pm=get_path_manager(root))
    assert _mtimes(root) == before, "the scan wrote into the dataset"

    assert result.partial is False
    assert result.total_files > 0
    assert sum(k.bytes for k in result.kinds) == result.total_bytes
    assert sum(k.files for k in result.kinds) == result.total_files

    du = subprocess.run(["du", "-sk", root], capture_output=True, text=True, check=True)
    du_bytes = int(du.stdout.split()[0]) * 1024
    # du also charges each directory's own blocks; the scan counts files only.
    assert abs(result.total_bytes - du_bytes) <= 0.02 * du_bytes, (
        result.total_bytes,
        du_bytes,
    )

    by_kind = _by_kind(result)
    assert by_kind.get("other", 0) < 0.01 * result.total_bytes, by_kind
    # Dataset 000 has QSIPrep/QSIRecon scratch on disk: it is rebuildable cache.
    qsi_work = 0
    for name in (".qsiprep_work", ".qsirecon_work"):
        for dirpath, _, files in os.walk(os.path.join(root, "derivatives", name)):
            for f in files:
                st = os.lstat(os.path.join(dirpath, f))
                if not os.path.islink(os.path.join(dirpath, f)):
                    qsi_work += st.st_blocks * storage.BLOCK_BYTES
    assert qsi_work > 0
    assert by_kind.get("cache", 0) >= qsi_work

    sizes = [item.bytes for item in result.largest]
    assert 0 < len(sizes) <= 8
    assert sizes == sorted(sizes, reverse=True)
    for item in result.largest:
        assert item.bytes <= by_kind[item.kind], item
