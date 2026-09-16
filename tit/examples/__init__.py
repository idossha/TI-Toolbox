"""Example datasets: a content-addressed catalogue fetched into a project's BIDS layout.

Modelled on 3D Slicer's ``SampleData`` module (and Tetravox's *Sample Data* dialog): the catalogue
(:file:`catalog.json`, package data) lists every sample as a *set of files*, each named by its
**sha256**, and the store is one GitHub release (``example-data`` on ``idossha/TI-Toolbox``) whose
assets carry those hashes as names. Nothing is placed in a project until the downloaded bytes hash
to the catalogue entry -- ``dev/example-data/`` stages and publishes the assets.

Four samples: raw T1(+T2) MRIs that need pre-processing (``mni152-t1``, ``ernie-t1``) and finished
charm head models ready for the optimizer, simulator and analyzer (``ernie-headmodel``,
``mni152-headmodel``). A sample's ``layout`` says where its files land::

    raw        <project>/sub-<id>/anat/sub-<id>_T1w.nii.gz (+ _T2w)
    headmodel  the same anat files + m2m_<id>.tar.gz unpacked into
               <project>/derivatives/SimNIBS/sub-<id>/m2m_<id>/

Entry points: ``python -m tit.examples --project DIR [--list] [SAMPLE_ID ...]``, the server routes
``GET/POST /api/project/example-data`` (a ``project_init`` job) and the desktop's *Add example
data?* chooser and *Help > Example data* tab. Stdlib only, so it runs on the host and in the
container, over a verified TLS context from :mod:`tit.certs`. :func:`fetch_ernie` is kept as the
notebook's one-liner for ``ernie-headmodel``.
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
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable

from tit.certs import ca_bundle_hint, ssl_context

__all__ = [
    "Sample",
    "SampleFile",
    "catalogue",
    "fetch",
    "fetch_ernie",
    "sample_by_id",
    "status",
]

#: The head-model sample :func:`fetch_ernie` (the notebook, the docs) stands for.
ERNIE_HEADMODEL = "ernie-headmodel"

Progress = Callable[[str, str, int, int], None]
"""``progress(sample_id, file_name, received_bytes, total_bytes)`` across the whole sample."""


@dataclass(frozen=True)
class SampleFile:
    name: str
    bytes: int
    sha256: str
    url: str


@dataclass(frozen=True)
class Sample:
    id: str
    title: str
    group: str
    description: str
    source: str
    source_url: str
    licence: str
    subject: str
    layout: str  # "raw" | "headmodel"
    files: tuple[SampleFile, ...]

    @property
    def bytes(self) -> int:
        return sum(f.bytes for f in self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "group": self.group,
            "description": self.description,
            "source": self.source,
            "source_url": self.source_url,
            "licence": self.licence,
            "subject": self.subject,
            "layout": self.layout,
            "bytes": self.bytes,
            "files": [f.__dict__ for f in self.files],
        }


def _load_catalog() -> dict[str, Any]:
    with resources.files(__package__).joinpath("catalog.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


def catalogue() -> list[Sample]:
    """Every sample, in catalogue order."""
    out = []
    for raw in _load_catalog()["samples"]:
        files = tuple(SampleFile(**f) for f in raw["files"])
        out.append(Sample(**{k: v for k, v in raw.items() if k != "files"}, files=files))
    return out


def sample_by_id(sample_id: str) -> Sample:
    for s in catalogue():
        if s.id == sample_id:
            return s
    raise KeyError(f"unknown example sample {sample_id!r}; see `python -m tit.examples --list`")


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


def _subject_dir(project_dir: Path, subject: str) -> Path:
    """``<project>/sub-<subject>``, matching an existing directory of any case."""
    return _resolve(project_dir, f"sub-{subject}")


def _anat_dir(project_dir: Path, subject: str) -> Path:
    return _subject_dir(project_dir, subject) / "anat"


def _m2m_dir(project_dir: Path, subject: str) -> Path:
    """``<project>/derivatives/SimNIBS/sub-<subject>/m2m_<subject>``, of any case on disk."""
    simnibs = project_dir / "derivatives" / "SimNIBS"
    sub = _resolve(simnibs, f"sub-{subject}")
    # Reuse the case the subject directory settled on, so sub-Ernie/m2m_Ernie is found.
    label = sub.name[len("sub-") :]
    return _resolve(sub, f"m2m_{label}")


def _is_archive(f: SampleFile) -> bool:
    return f.name.endswith(".tar.gz")


def _destination(project_dir: Path, sample: Sample, f: SampleFile) -> Path:
    """Where the file's *content* ends up: the unpacked ``m2m_<id>`` for an archive, else anat."""
    if _is_archive(f):
        return _m2m_dir(project_dir, sample.subject)
    return _resolve(_anat_dir(project_dir, sample.subject), f.name)


def _target_dir(project_dir: Path, sample: Sample) -> Path:
    """The directory :func:`fetch` reports as the one it filled."""
    if sample.layout == "headmodel":
        return _m2m_dir(project_dir, sample.subject)
    return _anat_dir(project_dir, sample.subject)


def _installed(project_dir: Path, sample: Sample) -> bool:
    for f in sample.files:
        dest = _destination(project_dir, sample, f)
        if not _is_archive(f):
            if not dest.is_file():
                return False
        elif not dest.is_dir() or not _resolve(dest, f"{dest.name[len('m2m_') :]}.msh").is_file():
            return False
    return True


def status(project_dir: str | Path) -> list[dict[str, Any]]:
    """Per-sample ``{id, installed, bytes}`` from the disk alone -- no network."""
    root = Path(project_dir).expanduser()
    return [{"id": s.id, "installed": _installed(root, s), "bytes": s.bytes} for s in catalogue()]


# ------------------------------------------------------------------- download and install


def _download(f: SampleFile, dest: Path, on_bytes: Callable[[int], None]) -> None:
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
        parts = Path(m.name).parts
        if not parts or parts[0] != prefix or ".." in parts or m.issym() or m.islnk():
            raise ValueError(f"unsafe archive member: {m.name}")
        members.append(m)
    if not members:
        raise ValueError(f"archive has no {prefix}/ members")
    return members


def _place(project_dir: Path, sample: Sample, f: SampleFile, tmp_file: Path) -> None:
    """Move one staged file into the project: unpack an archive, otherwise drop it in ``anat``."""
    dest = _destination(project_dir, sample, f)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not _is_archive(f):
        shutil.move(str(tmp_file), dest)
        return
    with tarfile.open(tmp_file, "r:gz") as tar:
        members = _safe_members(tar, f.name[: -len(".tar.gz")])
        if dest.exists():
            shutil.rmtree(dest)
        tar.extractall(dest.parent, members=members)  # noqa: S202 - members vetted above
        extracted = dest.parent / f.name[: -len(".tar.gz")]
        if extracted != dest:  # the project uses another case; keep the case already on disk
            extracted.rename(dest)


def _register(project_dir: Path, sample: Sample) -> None:
    """Record the subject in the manifests ``tit.project_init`` writes (best effort)."""
    from tit.project_init.initializer import (
        initialize_dataset_description,
        initialize_derivative_dataset_description,
        initialize_project_status,
        load_project_status,
        update_project_status,
    )

    initialize_dataset_description(project_dir)
    if sample.layout == "headmodel":
        initialize_derivative_dataset_description(project_dir, "SimNIBS")
    initialize_project_status(project_dir)
    current = load_project_status(project_dir)
    subjects = list(current.get("example_subjects") or [])
    if sample.subject not in subjects:
        subjects.append(sample.subject)
    samples = list(current.get("example_samples") or [])
    if sample.id not in samples:
        samples.append(sample.id)
    update_project_status(
        project_dir,
        {
            "example_subjects": subjects,
            "example_samples": samples,
            "example_subject_source": _load_catalog()["store"],
        },
    )


def fetch(
    sample_id: str,
    project_dir: str | Path,
    *,
    force: bool = False,
    progress: Progress | None = None,
    log=print,
) -> Path:
    """Download *sample_id* into *project_dir* and return the subject's directory it filled.

    Idempotent: returns at once when every file of the sample is already in place unless *force*.
    Each file is streamed to a temporary directory and sha256-verified **before** it touches the
    project; a mismatch raises :class:`ValueError` and leaves the project as it was.
    """
    sample = sample_by_id(sample_id)
    root = Path(project_dir).expanduser().resolve()
    target = _target_dir(root, sample)
    if _installed(root, sample) and not force:
        log(f"{sample.id} already present: {target}", flush=True)
        return target

    total = max(sample.bytes, 1)
    done = 0
    last_pct = -1

    def report(name: str, base: int, received: int) -> None:
        nonlocal last_pct
        if progress:
            progress(sample.id, name, base + received, total)
        pct = (base + received) * 100 // total
        if pct != last_pct:
            last_pct = pct
            log(f"download {pct}%", flush=True)

    with tempfile.TemporaryDirectory(prefix="tit-examples-") as tmp:
        staged: list[tuple[SampleFile, Path]] = []
        for f in sample.files:
            tmp_file = Path(tmp) / f.name
            log(f"downloading {f.name} ({f.bytes / 1e6:.0f} MB)", flush=True)
            _download(f, tmp_file, lambda n, name=f.name, base=done: report(name, base, n))
            staged.append((f, tmp_file))
            done += f.bytes
        log("checksums ok; installing", flush=True)
        for f, tmp_file in staged:
            _place(root, sample, f, tmp_file)

    _register(root, sample)
    target = _target_dir(root, sample)
    log(f"{sample.id} ready: {target}", flush=True)
    return target


def fetch_ernie(project_dir: str | Path, *, force: bool = False, log=print) -> Path:
    """The example notebook's one-liner: ``ernie-headmodel`` (T1+T2 and ``m2m_ernie``)."""
    return fetch(ERNIE_HEADMODEL, project_dir, force=force, log=log)
