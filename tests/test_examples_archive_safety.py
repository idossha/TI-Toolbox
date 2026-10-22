"""Example-data archives: unsafe members are refused untouched, ``--force`` replaces exactly.

What this pins (``tit.examples._safe_members`` / ``_place`` / ``fetch`` / ``status``):

* An archive holding a member that could escape or subvert the part's directory -- a parent
  reference, an absolute path, a symbolic or hard link, a member outside the archive's own
  ``m2m_<subject>/`` prefix, a FIFO, a character or block device -- or no member at all raises
  :class:`ValueError`, and the project tree (every directory, file and byte) is exactly as before,
  including an already installed head model a ``force=True`` re-fetch was meant to replace. The
  policy is a whitelist: only regular files and directories are unpacked (2026-10-22; before it,
  FIFOs and device nodes were extracted, and a refused archive still left the part's empty
  ``derivatives/SimNIBS/sub-<subject>`` directories behind).
* The other half of the whitelist: an archive whose directories are their own members -- as
  ``tar czf m2m_ernie`` and :meth:`tarfile.TarFile.add` write every real head model -- unpacks,
  into a fresh project and over an installed one. Refusing directory members would break every
  example fetch while every files-only fixture stayed green.
* ``force=True`` replaces an installed head model with exactly the archive's files (a stale file
  is gone), and keeps the on-disk case of an existing ``m2m_Ernie``.
* ``_resolve`` decides by the directory listing, the exact spelling first: with ``exists()`` made
  case-insensitive (the macOS host, emulated so it is red on a case-sensitive CI filesystem too)
  ``m2m_ernie`` still resolves to the ``m2m_Ernie`` on disk, and a listing holding both spellings
  (a faked one -- macOS cannot hold both) gives each its own.
* On Dataset 000 (env ``TIT_DATASET_000``, read-only): every catalogue part reports installed, each
  head-model part's target is ``PathManager.m2m(subject)``, and the catalog lists that subject
  with ``has_m2m``.

Expected file lists come from reading each fixture archive back with :mod:`tarfile`, not from the
code under test. No network: the URL opener is replaced by one serving the fixture's bytes, whose
sha256 is the catalogue entry, so every case reaches unpacking.
Run: python -m pytest tests/test_examples_archive_safety.py -q
(export TIT_DATASET_000=/path/to/000 for the real-data case).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from tit import examples

STORE = "https://example.invalid/store/"
ARCHIVE = "m2m_ernie.tar.gz"
GOOD = [
    ("m2m_ernie/ernie.msh", b"mesh v2"),
    ("m2m_ernie/segmentation/labeling.nii.gz", b"labels v2"),
]


def _member(name: str, kind: bytes = tarfile.REGTYPE, data: bytes = b"x", **extra):
    """A member spec: (TarInfo, payload); regular files carry *data*, other kinds none."""
    info = tarfile.TarInfo(name)
    info.type = kind
    info.size = len(data) if kind == tarfile.REGTYPE else 0
    for key, value in extra.items():
        setattr(info, key, value)
    return info, (data if kind == tarfile.REGTYPE else None)


def _tarball(members) -> bytes:
    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w|", format=tarfile.GNU_FORMAT) as tar,
    ):
        for info, data in members:
            tar.addfile(info, None if data is None else io.BytesIO(data))
    return buf.getvalue()


def _good_tarball(files=GOOD) -> bytes:
    return _tarball([_member(name, data=data) for name, data in files])


# GOOD as ``tar czf m2m_ernie`` lays it out: each directory is its own DIRTYPE member, ahead of
# its files. 0o755 because TarInfo defaults to 0o644, which unpacks an untraversable directory.
GOOD_WITH_DIRS = [
    _member("m2m_ernie", tarfile.DIRTYPE, mode=0o755),
    _member("m2m_ernie/ernie.msh", data=b"mesh v2"),
    _member("m2m_ernie/segmentation", tarfile.DIRTYPE, mode=0o755),
    _member("m2m_ernie/segmentation/labeling.nii.gz", data=b"labels v2"),
]
# GOOD's files as they land under the head-model directory.
GOOD_RELATIVE = [(name.removeprefix("m2m_ernie/"), data) for name, data in GOOD]


def _serve(monkeypatch, archive: bytes) -> list[str]:
    """Make the ernie head-model part this archive, served under its own sha256."""
    digest = hashlib.sha256(archive).hexdigest()
    catalog = {
        "store": STORE,
        "datasets": [
            {
                "id": "ernie",
                "title": "Ernie",
                "description": "d",
                "source": "SimNIBS example dataset",
                "source_url": "https://github.com/simnibs/example-dataset",
                "licence": "GPL-3.0",
                "subject": "ernie",
                "parts": [
                    {
                        "id": "headmodel",
                        "title": "Head model",
                        "meaning": "m",
                        "dest": "derivatives/SimNIBS/sub-{subject}",
                        "target": "derivatives/SimNIBS/sub-{subject}/m2m_{subject}",
                        "verify": ["m2m_{subject}/{subject}.msh"],
                        "derivative": "SimNIBS",
                        "files": [
                            {
                                "name": ARCHIVE,
                                "bytes": len(archive),
                                "sha256": digest,
                                "url": STORE + digest,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    opened: list[str] = []

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.close()

    def urlopen(url, **_kw):
        assert url == STORE + digest
        opened.append(url)
        return _Resp(archive)

    monkeypatch.setattr(examples, "_load_catalog", lambda: catalog)
    monkeypatch.setattr(examples.urllib.request, "urlopen", urlopen)
    return opened


def _tree(root: Path) -> dict[str, bytes | str]:
    """Every entry under *root*: a file's bytes, a directory, a link's target, any other kind."""
    out: dict[str, bytes | str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            rel = str(path.relative_to(root))
            if path.is_symlink():
                out[rel] = "link->" + os.readlink(path)
            elif path.is_dir():
                out[rel] = "dir"
            elif path.is_file():
                out[rel] = path.read_bytes()
            else:
                out[rel] = "special"
    return out


def _archive_files(archive: bytes, prefix: str) -> dict[str, bytes]:
    """The regular files of *archive* below *prefix*, read back independently of tit.examples."""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return {
            m.name[len(prefix) + 1 :]: tar.extractfile(m).read()
            for m in tar.getmembers()
            if m.isreg()
        }


def _files_under(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


UNSAFE = {
    "parent-reference": [_member("../evil")],
    "parent-inside-prefix": [_member("m2m_ernie/../../evil")],
    "absolute-path": [_member("/abs")],
    "symlink": [
        _member("m2m_ernie/ernie.msh"),
        _member("m2m_ernie/link", tarfile.SYMTYPE, linkname="/etc/passwd"),
    ],
    "hardlink": [
        _member("m2m_ernie/ernie.msh"),
        _member("m2m_ernie/hard", tarfile.LNKTYPE, linkname="m2m_ernie/ernie.msh"),
    ],
    "other-prefix": [_member("m2m_ernie/ernie.msh"), _member("other_prefix/x")],
    "empty": [],
    "fifo": [
        _member("m2m_ernie/ernie.msh"),
        _member("m2m_ernie/pipe", tarfile.FIFOTYPE),
    ],
    "char-device": [
        _member("m2m_ernie/ernie.msh"),
        _member("m2m_ernie/null", tarfile.CHRTYPE, devmajor=1, devminor=3),
    ],
    "block-device": [
        _member("m2m_ernie/ernie.msh"),
        _member("m2m_ernie/disk", tarfile.BLKTYPE, devmajor=8, devminor=0),
    ],
}


@pytest.mark.parametrize("case", sorted(UNSAFE))
def test_fixture_archives_hold_the_member_they_claim(case):
    """The writer did not normalise the hostile member away; a reader sees it as authored."""
    archive = _tarball(UNSAFE[case])
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        seen = [(m.name, m.type) for m in tar.getmembers()]
    assert seen == [(info.name, info.type) for info, _ in UNSAFE[case]]


@pytest.mark.parametrize("case", sorted(UNSAFE))
def test_unsafe_archive_is_refused_and_a_fresh_project_is_untouched(
    tmp_path, monkeypatch, case
):
    project = tmp_path / "project"
    (project / "sub-0042").mkdir(parents=True)
    (project / "sub-0042" / "notes.txt").write_bytes(b"keep me")
    before = _tree(project)
    opened = _serve(monkeypatch, _tarball(UNSAFE[case]))

    with pytest.raises(ValueError, match="archive"):
        examples.fetch("ernie", "headmodel", project, log=lambda *a, **k: None)

    assert opened, "the archive was downloaded and verified, so unpacking was reached"
    assert _tree(project) == before
    assert not (tmp_path / "evil").exists() and not Path("/abs").exists()


@pytest.mark.parametrize("case", sorted(UNSAFE))
def test_unsafe_archive_on_force_keeps_the_installed_head_model(
    tmp_path, monkeypatch, case
):
    project = tmp_path / "project"
    m2m = project / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie"
    m2m.mkdir(parents=True)
    (m2m / "ernie.msh").write_bytes(b"installed mesh")
    (m2m / "old.txt").write_bytes(b"user file")
    before = _tree(project)
    _serve(monkeypatch, _tarball(UNSAFE[case]))

    with pytest.raises(ValueError, match="archive"):
        examples.fetch(
            "ernie", "headmodel", project, force=True, log=lambda *a, **k: None
        )

    assert _tree(project) == before


def _member_kinds(archive: bytes) -> list[tuple[str, bytes]]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return [(m.name, m.type) for m in tar.getmembers()]


def test_directory_member_fixture_holds_explicit_directory_entries():
    """The fixture is the real-archive shape it claims: two DIRTYPE members, each before its files."""
    assert _member_kinds(_tarball(GOOD_WITH_DIRS)) == [
        ("m2m_ernie", tarfile.DIRTYPE),
        ("m2m_ernie/ernie.msh", tarfile.REGTYPE),
        ("m2m_ernie/segmentation", tarfile.DIRTYPE),
        ("m2m_ernie/segmentation/labeling.nii.gz", tarfile.REGTYPE),
    ]


def test_archive_with_directory_members_unpacks_into_a_fresh_project(
    tmp_path, monkeypatch
):
    project = tmp_path / "project"
    archive = _tarball(GOOD_WITH_DIRS)
    _serve(monkeypatch, archive)

    m2m = examples.fetch("ernie", "headmodel", project, log=lambda *a, **k: None)

    assert m2m == project / "derivatives" / "SimNIBS" / "sub-ernie" / "m2m_ernie"
    assert _files_under(m2m) == _archive_files(archive, "m2m_ernie")
    assert (m2m / "segmentation").is_dir()
    assert {s["id"]: s["installed"] for s in examples.status(project)} == {
        "ernie/headmodel": True
    }


def _write_with_tarfile_add(src: Path, out: Path) -> None:
    with tarfile.open(out, "w:gz") as tar:
        tar.add(src / "m2m_ernie", arcname="m2m_ernie")


def _write_with_system_tar(src: Path, out: Path) -> None:
    tar = shutil.which("tar")
    if tar is None:
        pytest.skip("skipping: no tar executable on PATH to write a real archive")
    # COPYFILE_DISABLE: macOS bsdtar would otherwise add AppleDouble ._* members for xattrs.
    env = {**os.environ, "COPYFILE_DISABLE": "1"}
    subprocess.run([tar, "czf", str(out), "m2m_ernie"], cwd=src, env=env, check=True)


@pytest.mark.parametrize(
    "writer",
    [_write_with_tarfile_add, _write_with_system_tar],
    ids=["tarfile-add", "tar-czf"],
)
def test_archive_a_real_writer_made_from_a_head_model_tree_unpacks(
    tmp_path, monkeypatch, writer
):
    """The store's archives come from a real writer, which records every directory as a member."""
    src = tmp_path / "src"
    for name, data in GOOD:
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_bytes(data)
    out = tmp_path / ARCHIVE
    writer(src, out)
    archive = out.read_bytes()
    kinds = dict(_member_kinds(archive))
    assert kinds.get("m2m_ernie") == tarfile.DIRTYPE, kinds
    assert kinds.get("m2m_ernie/segmentation") == tarfile.DIRTYPE, kinds
    _serve(monkeypatch, archive)
    project = tmp_path / "project"

    m2m = examples.fetch("ernie", "headmodel", project, log=lambda *a, **k: None)

    assert _files_under(m2m) == _files_under(src / "m2m_ernie") == dict(GOOD_RELATIVE)


@pytest.mark.parametrize("layout", ["files-only", "directory-members"])
def test_force_replaces_the_head_model_with_exactly_the_archive(
    tmp_path, monkeypatch, layout
):
    project = tmp_path / "project"
    _serve(monkeypatch, _good_tarball([("m2m_ernie/ernie.msh", b"mesh v1")]))
    m2m = examples.fetch("ernie", "headmodel", project, log=lambda *a, **k: None)
    (m2m / "old.txt").write_bytes(b"stale")
    (m2m / "stale_dir").mkdir()
    (m2m / "stale_dir" / "x").write_bytes(b"stale")

    archive = _good_tarball() if layout == "files-only" else _tarball(GOOD_WITH_DIRS)
    _serve(monkeypatch, archive)
    again = examples.fetch(
        "ernie", "headmodel", project, force=True, log=lambda *a, **k: None
    )

    assert again == m2m
    assert _files_under(m2m) == _archive_files(archive, "m2m_ernie")
    assert sorted(p.name for p in m2m.iterdir()) == ["ernie.msh", "segmentation"]


def test_force_keeps_the_on_disk_case_of_an_existing_tree(tmp_path, monkeypatch):
    """``m2m_Ernie`` stays ``m2m_Ernie``. Red before 2026-10-22 on a case-insensitive filesystem
    (the macOS host, a macOS project mounted into the container), where ``m2m_ernie`` "existed"
    and the re-fetch wrote the catalogue's spelling; on a case-sensitive one it pins the rename.
    """
    project = tmp_path / "project"
    subject = project / "derivatives" / "SimNIBS" / "sub-Ernie"
    (subject / "m2m_Ernie").mkdir(parents=True)
    (subject / "m2m_Ernie" / "Ernie.msh").write_bytes(b"old mesh")
    (subject / "m2m_Ernie" / "old.txt").write_bytes(b"stale")
    archive = _good_tarball()
    _serve(monkeypatch, archive)

    target = examples.fetch(
        "ernie", "headmodel", project, force=True, log=lambda *a, **k: None
    )

    simnibs = project / "derivatives" / "SimNIBS"
    assert [p.name for p in simnibs.iterdir() if p.is_dir()] == ["sub-Ernie"]
    assert [p.name for p in subject.iterdir()] == ["m2m_Ernie"]
    assert target.samefile(subject / "m2m_Ernie")
    assert _files_under(subject / "m2m_Ernie") == _archive_files(archive, "m2m_ernie")
    assert {s["id"]: s["installed"] for s in examples.status(project)} == {
        "ernie/headmodel": True
    }


def test_resolve_keeps_the_on_disk_case_where_exists_ignores_case(
    tmp_path, monkeypatch
):
    """Emulates the macOS host on any filesystem: ``exists()`` answers case-insensitively.

    Only ``m2m_Ernie`` is on disk, so ``m2m_ernie`` must resolve to it. Red before 2026-10-22 on
    every filesystem with this emulation: ``_resolve`` trusted ``exists()`` and kept the requested
    spelling, which a forced re-fetch then wrote to disk.
    """
    (tmp_path / "m2m_Ernie").mkdir()
    on_disk = {p.name.lower() for p in tmp_path.iterdir()}
    real_exists = Path.exists

    def exists_ignoring_case(self, *args, **kwargs):
        if self.parent == tmp_path:
            return self.name.lower() in on_disk
        return real_exists(self, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", exists_ignoring_case)
    assert (tmp_path / "m2m_ernie").exists(), "the emulation ignores case"

    assert examples._resolve(tmp_path, "m2m_ernie").name == "m2m_Ernie"
    assert examples._resolve(tmp_path, "sub-0042").name == "sub-0042"


def test_resolve_prefers_the_exact_spelling_over_a_case_variant(tmp_path, monkeypatch):
    """A case-sensitive directory holding ``m2m_Ernie`` and ``m2m_ernie``, the variant listed first.

    The listing is faked (the macOS host cannot hold both). Each exact name resolves to itself; a
    spelling that is on disk only in other cases resolves to one of those, never to itself.
    """
    listing = ["m2m_Ernie", "m2m_ernie", "sub-0042"]
    real_iterdir = Path.iterdir

    def iterdir(self):
        if self == tmp_path:
            return iter([tmp_path / name for name in listing])
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)

    assert examples._resolve(tmp_path, "m2m_ernie").name == "m2m_ernie"
    assert examples._resolve(tmp_path, "m2m_Ernie").name == "m2m_Ernie"
    variant = examples._resolve(tmp_path, "M2M_ERNIE").name
    assert variant in {"m2m_Ernie", "m2m_ernie"}
    assert examples._resolve(tmp_path, "m2m_MNI152") == tmp_path / "m2m_MNI152"
    assert examples._resolve(tmp_path / "absent", "x") == tmp_path / "absent" / "x"


# ------------------------------------------------------------------ Dataset 000 (read-only)

DATASET = os.environ.get("TIT_DATASET_000", "")


def _mtimes(paths) -> dict[str, tuple[int, int]]:
    out = {}
    for top in paths:
        for dirpath, dirnames, filenames in os.walk(top):
            for name in [*dirnames, *filenames, "."]:
                st = os.lstat(os.path.join(dirpath, name))
                out[os.path.join(dirpath, name)] = (st.st_mtime_ns, st.st_size)
    return out


@pytest.mark.skipif(
    not DATASET or not os.path.isdir(DATASET),
    reason="skipping: TIT_DATASET_000 is unset or not a directory (Dataset 000 copy)",
)
def test_dataset_000_reports_every_part_installed_where_path_manager_looks():
    from tit import catalog
    from tit.paths import PathManager

    root = Path(DATASET)
    parts = examples.parts()
    watched = [root / "derivatives" / "SimNIBS"] + [
        root / f"sub-{p.subject}" for p in parts
    ]
    before = _mtimes(watched)

    statuses = examples.status(root)
    pm = PathManager(str(root))
    subjects = {row["id"]: row for row in catalog.list_subjects(pm)}

    assert {s["id"] for s in statuses} == {p.full_id for p in parts}
    assert all(s["installed"] for s in statuses), statuses
    headmodels = [p for p in parts if p.id == "headmodel"]
    assert {p.subject for p in headmodels} == {"ernie", "MNI152"}
    for part in headmodels:
        assert str(examples._target_dir(root, part)) == pm.m2m(part.subject)
        assert subjects[part.subject]["has_m2m"] is True
        assert (Path(pm.m2m(part.subject)) / f"{part.subject}.msh").is_file()
    assert _mtimes(watched) == before, "status/list_subjects must not write"
