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
container. :func:`fetch_ernie` is kept as the notebook's one-liner for ``ernie-headmodel``.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable

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


# ----------------------------------------------------------------------------- placement


def _anat_dir(project_dir: Path, subject: str) -> Path:
    return project_dir / f"sub-{subject}" / "anat"


def _m2m_dir(project_dir: Path, subject: str) -> Path:
    return project_dir / "derivatives" / "SimNIBS" / f"sub-{subject}" / f"m2m_{subject}"


def _is_headmodel_archive(f: SampleFile) -> bool:
    return f.name.endswith(".tar.gz")


def _destination(project_dir: Path, sample: Sample, f: SampleFile) -> Path:
    """Where the file's *content* ends up: the unpacked ``m2m_<id>`` for an archive, else anat."""
    if _is_headmodel_archive(f):
        return _m2m_dir(project_dir, sample.subject)
    return _anat_dir(project_dir, sample.subject) / f.name


def _installed(project_dir: Path, sample: Sample) -> bool:
    for f in sample.files:
        dest = _destination(project_dir, sample, f)
        if _is_headmodel_archive(f):
            if not dest.is_dir() or not (dest / f"{sample.subject}.msh").is_file():
                return False
        elif not dest.is_file():
            return False
    return True


def status(project_dir: str | Path) -> list[dict[str, Any]]:
    """Per-sample ``{id, installed, bytes}`` from the disk alone -- no network."""
    root = Path(project_dir).expanduser()
    return [{"id": s.id, "installed": _installed(root, s), "bytes": s.bytes} for s in catalogue()]


# ------------------------------------------------------------------------------ download


def _download(f: SampleFile, dest: Path, *, on_bytes: Callable[[int], None] | None = None) -> str:
    """Stream ``f.url`` to *dest*, returning its sha256; whole-percent progress via *on_bytes*."""
    h = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(f.url) as resp, open(dest, "wb") as out:  # noqa: S310 - pinned https URL
        while chunk := resp.read(1 << 20):
            out.write(chunk)
            h.update(chunk)
            received += len(chunk)
            if on_bytes:
                on_bytes(received)
    return h.hexdigest()


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
    dest = _destination(project_dir, sample, f)
    if _is_headmodel_archive(f):
        prefix = f"m2m_{sample.subject}"
        with tarfile.open(tmp_file, "r:gz") as tar:
            members = _safe_members(tar, prefix)
            if dest.exists():
                shutil.rmtree(dest)
            dest.parent.mkdir(parents=True, exist_ok=True)
            tar.extractall(dest.parent, members=members)  # noqa: S202 - members vetted above
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_file), dest)


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
    target = (_m2m_dir if sample.layout == "headmodel" else _anat_dir)(root, sample.subject)
    if _installed(root, sample) and not force:
        log(f"{sample.id} already present: {target}", flush=True)
        return target

    total = sample.bytes
    done_before = 0
    last_pct = -1
    with tempfile.TemporaryDirectory(prefix="tit-examples-") as tmp:
        staged: list[tuple[SampleFile, Path]] = []
        for f in sample.files:
            tmp_file = Path(tmp) / f.name
            log(f"downloading {f.name} ({f.bytes / 1e6:.0f} MB)", flush=True)

            def on_bytes(received: int, *, name: str = f.name, base: int = done_before) -> None:
                nonlocal last_pct
                if progress:
                    progress(sample.id, name, base + received, total)
                pct = (base + received) * 100 // max(total, 1)
                if pct != last_pct:
                    log(f"download {pct}%", flush=True)
                    last_pct = pct

            digest = _download(f, tmp_file, on_bytes=on_bytes)
            size = tmp_file.stat().st_size
            if digest != f.sha256 or size != f.bytes:
                raise ValueError(
                    f"{f.name}: downloaded {size} B with sha256 {digest}; the catalogue says "
                    f"{f.bytes} B / {f.sha256} -- refusing to install it"
                )
            staged.append((f, tmp_file))
            done_before += f.bytes
        log("checksums ok; installing", flush=True)
        for f, tmp_file in staged:
            _place(root, sample, f, tmp_file)

    _register(root, sample)
    log(f"{sample.id} ready: {target}", flush=True)
    return target


def fetch_ernie(project_dir: str | Path, *, force: bool = False, log=print) -> Path:
    """The example notebook's one-liner: ``ernie-headmodel`` (T1+T2 and ``m2m_ernie``)."""
    return fetch(ERNIE_HEADMODEL, project_dir, force=force, log=log)
