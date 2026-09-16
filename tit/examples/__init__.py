"""Example data: a content-addressed catalogue of **datasets with independent parts**.

Modelled on 3D Slicer's ``SampleData`` module (and Tetravox's *Sample Data* dialog): the catalogue
(:file:`catalog.json`, package data) lists every file by its **sha256**, and the store is one
GitHub release (``v1`` on `idossha/ti-toolbox-example-data
<https://github.com/idossha/ti-toolbox-example-data>`_, a repository of its own) whose assets carry
those hashes as names. Nothing is placed in a project until the downloaded bytes hash to the
catalogue entry.

**A dataset is one head; a part is one thing you can download.** Two datasets ship today --
``ernie`` (the SimNIBS example subject) and ``mni152`` (the template) -- each with a ``nifti`` part
and a ``headmodel`` part::

    ernie/nifti      sub-ernie/anat/sub-ernie_T1w.nii.gz, _T2w.nii.gz
    ernie/headmodel  derivatives/SimNIBS/sub-ernie/m2m_ernie/   (m2m_ernie.tar.gz, unpacked)
    mni152/nifti     sub-MNI152/anat/sub-MNI152_T1w.nii.gz
    mni152/headmodel derivatives/SimNIBS/sub-MNI152/m2m_MNI152/

Each part is fetched and **detected on its own**: deleting ``sub-ernie/anat`` leaves
``ernie/headmodel`` installed, and vice versa. This is what the old four-overlapping-samples
catalogue could not say -- its head-model sample *contained* the NIfTIs, so removing them flipped
the head model to "not installed" too.

Where a part lands is **declared in the catalogue**, not in this module: ``dest`` (a project-root
template with ``{subject}``) is the directory its files go into -- a ``.tar.gz`` is unpacked there
-- ``verify`` the paths that must exist for it to count as installed (default: the plain file
names), and ``target`` what :func:`fetch` returns (default: ``dest``). Adding a third part later
(a FreeSurfer tree, a worked simulation) is therefore an edit to :file:`catalog.json` alone.

**This module is plain functions** -- :func:`catalogue`, :func:`status`, :func:`fetch` -- and
knows nothing about jobs, stages or :mod:`tit.jobs.events`. Downloading example data is not a
pipeline: it was briefly wired as a ``project_init`` job, which made asking an established
project for a sample reprint the initializer's "New project detected" banner.

Entry points: ``python -m tit.examples --project DIR [--list] [ernie/headmodel ...]``, the server
routes ``GET /api/example-data`` and ``POST /api/example-data/{dataset_id}/{part_id}``
(:mod:`tit.server.routes.example_data`, a background thread and a poll), and the desktop's *Add
example data?* chooser and *Help > Example data* tab. Stdlib only, so it runs on the host and in
the container, over a verified TLS context from :mod:`tit.certs`. :func:`fetch_ernie` is kept as
the notebook's one-liner and means **both** ernie parts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import ssl
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from tit.certs import ca_bundle_hint, ssl_context

__all__ = [
    "Dataset",
    "Part",
    "PartFile",
    "catalogue",
    "dataset_by_id",
    "fetch",
    "fetch_ernie",
    "parse_part_id",
    "part_by_id",
    "status",
]

#: The dataset :func:`fetch_ernie` (the notebook, the docs) stands for.
ERNIE = "ernie"

#: The part a fresh project is offered first: ready for the optimizer, simulator and analyzer.
DEFAULT_PART = "ernie/headmodel"

Progress = Callable[[str, str, int, int], None]
"""``progress(part_id, file_name, received_bytes, total_bytes)`` across the whole part."""


@dataclass(frozen=True)
class PartFile:
    name: str
    bytes: int
    sha256: str
    url: str


@dataclass(frozen=True)
class Part:
    """One independently downloadable piece of a dataset.

    ``dest``/``verify``/``target`` are project-root-relative templates carrying ``{subject}``;
    they are the whole of this part's placement policy, which is why a new part kind is a
    catalogue edit rather than a code change.
    """

    id: str
    title: str
    meaning: str
    dest: str
    files: tuple[PartFile, ...]
    dataset_id: str = ""
    subject: str = ""
    target: str = ""
    verify: tuple[str, ...] = ()
    derivative: str = ""

    @property
    def full_id(self) -> str:
        """``ernie/headmodel`` -- how the CLI, the route and the desktop name this part."""
        return f"{self.dataset_id}/{self.id}"

    @property
    def bytes(self) -> int:
        return sum(f.bytes for f in self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.full_id,
            "dataset": self.dataset_id,
            "part": self.id,
            "title": self.title,
            "meaning": self.meaning,
            "subject": self.subject,
            "bytes": self.bytes,
            "files": [f.__dict__ for f in self.files],
        }


@dataclass(frozen=True)
class Dataset:
    id: str
    title: str
    description: str
    source: str
    source_url: str
    licence: str
    subject: str
    parts: tuple[Part, ...] = field(default=())

    @property
    def bytes(self) -> int:
        return sum(p.bytes for p in self.parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "source": self.source,
            "source_url": self.source_url,
            "licence": self.licence,
            "subject": self.subject,
            "bytes": self.bytes,
            "parts": [p.to_dict() for p in self.parts],
        }


def _load_catalog() -> dict[str, Any]:
    with resources.files(__package__).joinpath("catalog.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def catalogue() -> list[Dataset]:
    """Every dataset, in catalogue order, each with its parts."""
    out = []
    for raw in _load_catalog()["datasets"]:
        subject = raw["subject"]
        parts = []
        for p in raw["parts"]:
            files = tuple(PartFile(**f) for f in p["files"])
            parts.append(
                Part(
                    id=p["id"],
                    title=p["title"],
                    meaning=p["meaning"],
                    dest=p["dest"],
                    files=files,
                    dataset_id=raw["id"],
                    subject=subject,
                    target=p.get("target", p["dest"]),
                    verify=tuple(p.get("verify", [f.name for f in files])),
                    derivative=p.get("derivative", ""),
                )
            )
        out.append(
            Dataset(**{k: v for k, v in raw.items() if k != "parts"}, parts=tuple(parts))
        )
    return out


def parse_part_id(part_id: str) -> tuple[str, str]:
    """``"ernie/headmodel"`` -> ``("ernie", "headmodel")``; also accepts ``ernie:headmodel``."""
    text = part_id.replace(":", "/")
    dataset, sep, part = text.partition("/")
    if not sep or not dataset or not part:
        raise KeyError(
            f"{part_id!r} is not a DATASET/PART id; see `python -m tit.examples --list`"
        )
    return dataset, part


def dataset_by_id(dataset_id: str) -> Dataset:
    for d in catalogue():
        if d.id == dataset_id:
            return d
    raise KeyError(f"unknown example dataset {dataset_id!r}; see `python -m tit.examples --list`")


def part_by_id(dataset_id: str, part_id: str | None = None) -> Part:
    """The part named either as ``part_by_id("ernie", "headmodel")`` or ``("ernie/headmodel")``."""
    if part_id is None:
        dataset_id, part_id = parse_part_id(dataset_id)
    for p in dataset_by_id(dataset_id).parts:
        if p.id == part_id:
            return p
    raise KeyError(
        f"unknown example part {dataset_id}/{part_id}; see `python -m tit.examples --list`"
    )


def parts() -> list[Part]:
    """Every part of every dataset, in catalogue order."""
    return [p for d in catalogue() for p in d.parts]


# ------------------------------------------------------------- placement and detection
#
# The toolbox always *writes* the catalogue's own subject label (``ernie``, ``MNI152``) --
# ``sub-ernie/anat``, ``derivatives/SimNIBS/sub-ernie/m2m_ernie``. It *reads* case-insensitively:
# SimNIBS itself ships ``m2m_ernie`` while plenty of projects on disk say ``sub-Ernie``/``m2m_Ernie``,
# and the container filesystem is case-sensitive where macOS is not -- which is exactly why an
# already-installed ernie showed up as absent in the container and not on the host.


def _resolve(parent: Path, name: str) -> Path:
    """*parent*/*name*, or an existing sibling that differs only in case."""
    exact = parent / name
    if exact.exists() or not parent.is_dir():
        return exact
    lowered = name.lower()
    for entry in parent.iterdir():
        if entry.name.lower() == lowered:
            return entry
    return exact


def _resolve_template(root: Path, template: str, subject: str) -> Path:
    """A catalogue template under *root*, each segment matched case-insensitively on disk."""
    out = root
    for segment in template.format(subject=subject).split("/"):
        if segment:
            out = _resolve(out, segment)
    return out


def _dest_dir(project_dir: Path, part: Part) -> Path:
    return _resolve_template(project_dir, part.dest, part.subject)


def _target_dir(project_dir: Path, part: Part) -> Path:
    """The directory :func:`fetch` reports as the one it filled."""
    return _resolve_template(project_dir, part.target, part.subject)


def _is_archive(f: PartFile) -> bool:
    return f.name.endswith(".tar.gz")


def _installed(project_dir: Path, part: Part) -> bool:
    dest = _dest_dir(project_dir, part)
    for rel in part.verify:
        path = _resolve_template(dest, rel, part.subject)
        if not path.exists():
            return False
    return bool(part.verify)


def status(project_dir: str | Path) -> list[dict[str, Any]]:
    """Per-part ``{id, dataset, part, installed, bytes}`` from the disk alone -- no network."""
    root = Path(project_dir).expanduser()
    return [
        {
            "id": p.full_id,
            "dataset": p.dataset_id,
            "part": p.id,
            "installed": _installed(root, p),
            "bytes": p.bytes,
        }
        for p in parts()
    ]


# ------------------------------------------------------------------- download and install


def _download(f: PartFile, dest: Path, on_bytes: Callable[[int], None]) -> None:
    """Stream ``f.url`` to *dest* in one pass, verifying size and sha256 before returning.

    Raises :class:`ValueError` on a size/hash mismatch and :class:`OSError` on a transport
    failure -- a TLS failure carries :func:`~tit.certs.ca_bundle_hint`.
    """
    digest = hashlib.sha256()
    received = 0
    try:
        with (
            urllib.request.urlopen(  # noqa: S310 - pinned https URL, verified context
                f.url, context=ssl_context(), timeout=60
            ) as resp,
            dest.open("wb") as out,
        ):
            while chunk := resp.read(1 << 20):
                out.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                on_bytes(received)
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLError):
            raise OSError(f"{f.name}: {ca_bundle_hint()} ({exc.reason})") from exc
        raise OSError(f"{f.name}: download failed ({exc.reason})") from exc
    if received != f.bytes or digest.hexdigest() != f.sha256:
        raise ValueError(
            f"{f.name}: downloaded {received} B with sha256 {digest.hexdigest()}; the catalogue "
            f"says {f.bytes} B / {f.sha256} -- refusing to install it"
        )


def _safe_members(tar: tarfile.TarFile, prefix: str) -> list[tarfile.TarInfo]:
    members = []
    for m in tar.getmembers():
        parts_ = Path(m.name).parts
        if not parts_ or parts_[0] != prefix or ".." in parts_ or m.issym() or m.islnk():
            raise ValueError(f"unsafe archive member: {m.name}")
        members.append(m)
    if not members:
        raise ValueError(f"archive has no {prefix}/ members")
    return members


def _place(project_dir: Path, part: Part, f: PartFile, tmp_file: Path) -> None:
    """Move one staged file into the part's ``dest``: unpack an archive, otherwise drop it in."""
    dest_dir = _dest_dir(project_dir, part)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not _is_archive(f):
        shutil.move(str(tmp_file), _resolve(dest_dir, f.name))
        return
    prefix = f.name[: -len(".tar.gz")]
    with tarfile.open(tmp_file, "r:gz") as tar:
        members = _safe_members(tar, prefix)
        existing = _resolve(dest_dir, prefix)
        if existing.exists():
            shutil.rmtree(existing)
        tar.extractall(dest_dir, members=members)  # noqa: S202 - members vetted above
        extracted = dest_dir / prefix
        if extracted != existing:  # the project uses another case; keep the case already on disk
            extracted.rename(existing)


def _register(project_dir: Path, part: Part) -> None:
    """Record the subject and part in the manifests ``tit.project_init`` writes (best effort)."""
    from tit.project_init.initializer import (
        initialize_dataset_description,
        initialize_derivative_dataset_description,
        initialize_project_status,
        load_project_status,
        update_project_status,
    )

    initialize_dataset_description(project_dir)
    if part.derivative:
        initialize_derivative_dataset_description(project_dir, part.derivative)
    initialize_project_status(project_dir)
    current = load_project_status(project_dir)
    subjects = list(current.get("example_subjects") or [])
    if part.subject not in subjects:
        subjects.append(part.subject)
    installed = list(current.get("example_samples") or [])
    if part.full_id not in installed:
        installed.append(part.full_id)
    update_project_status(
        project_dir,
        {
            "example_subjects": subjects,
            "example_samples": installed,
            "example_subject_source": _load_catalog()["store"],
        },
    )


def fetch(
    dataset_id: str,
    part_id: str | None = None,
    project_dir: str | Path | None = None,
    *,
    force: bool = False,
    progress: Progress | None = None,
    log=print,
) -> Path:
    """Download one part into *project_dir* and return the directory it filled.

    Called either as ``fetch("ernie", "headmodel", project)`` or ``fetch("ernie/headmodel",
    project)`` -- the two-argument form is what the CLI and the notebook use.

    Idempotent: returns at once when the part's ``verify`` paths are already in place unless
    *force*. Each file is streamed to a temporary directory and sha256-verified **before** it
    touches the project; a mismatch raises :class:`ValueError` and leaves the project as it was.
    """
    if project_dir is None:
        # Two-argument form: fetch("ernie/headmodel", project) -- the second positional is the
        # project directory, not a part.
        if part_id is None:
            raise TypeError("fetch() needs a project directory")
        project_dir = part_id
        dataset_id, part_id = parse_part_id(dataset_id)
    part = part_by_id(dataset_id, part_id)
    root = Path(project_dir).expanduser().resolve()
    if _installed(root, part) and not force:
        log(f"{part.full_id} already present: {_target_dir(root, part)}", flush=True)
        return _target_dir(root, part)

    total = max(part.bytes, 1)
    done = 0
    last_pct = -1

    def report(name: str, base: int, received: int) -> None:
        nonlocal last_pct
        if progress:
            progress(part.full_id, name, base + received, total)
        pct = (base + received) * 100 // total
        if pct != last_pct:
            last_pct = pct
            log(f"download {pct}%", flush=True)

    with tempfile.TemporaryDirectory(prefix="tit-examples-") as tmp:
        staged: list[tuple[PartFile, Path]] = []
        for f in part.files:
            tmp_file = Path(tmp) / f.name
            log(f"downloading {f.name} ({f.bytes / 1e6:.0f} MB)", flush=True)
            _download(f, tmp_file, lambda n, name=f.name, base=done: report(name, base, n))
            staged.append((f, tmp_file))
            done += f.bytes
        log("checksums ok; installing", flush=True)
        for f, tmp_file in staged:
            _place(root, part, f, tmp_file)

    _register(root, part)
    target = _target_dir(root, part)
    log(f"{part.full_id} ready: {target}", flush=True)
    return target


def fetch_ernie(project_dir: str | Path, *, force: bool = False, log=print) -> Path:
    """The example notebook's one-liner: **both** ernie parts (T1+T2 and ``m2m_ernie``).

    Returns the head model directory, which is what the notebook goes on to simulate on.
    """
    target = None
    for part in dataset_by_id(ERNIE).parts:
        target = fetch(ERNIE, part.id, project_dir, force=force, log=log)
    assert target is not None  # noqa: S101 - the catalogue always ships ernie with parts
    return target
