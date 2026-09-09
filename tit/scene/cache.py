"""The scene cache (plan §2.2): fingerprinted files under ``derivatives/``.

Layout, exactly as decision S2 freezes it::

    <project>/derivatives/ti-toolbox/scene_cache/sub-<id>/
        skin.<fingerprint>.tvsc  skin.<fingerprint>.gii  + skin.<fingerprint>.json
        gm.<fingerprint>.tvsc    gm.<fingerprint>.gii    + gm.<fingerprint>.json
        labels-DK40.<fingerprint>.{tvsc,gii}             + labels-DK40.<fingerprint>.json

One key, one fingerprint, one sidecar -- and one payload file per
serialisation in :data:`FORMATS`. ``tvsc`` remains the frozen compatibility
payload and ``gii`` is what the Tetravox embed reads (plan decision E7); the
sidecar describes the surface rather than its encoding, so there is exactly
one of it.

The fingerprint is a hash of ``(name, size, mtime_ns)`` of **every** source
file that fed the artifact, so a re-run of ``charm`` (new ``ernie.msh``) or a
re-run of the atlas step (new ``.annot``) produces a different name and the
stale file is deleted on the next write. Fingerprinting the *content* was
rejected: hashing a 184 MB mesh costs more than rebuilding the surface from
it (measured: 1.26 s to read and crop the whole mesh).

Concurrency, and the failure each measure prevents:

* **Per-subject build lock** (in-process ``threading.Lock``) -- FastAPI runs a
  ``def`` route in a threadpool, so two panes opening at once would otherwise
  both read the 184 MB mesh and both spend ~600 MB of RSS. The lock is keyed
  by ``(project_dir, subject)`` so two different subjects still build in
  parallel.
* **Atomic publish** (write ``<name>.tmp-<pid>-<uid>``, ``os.replace``) --
  a reader must never see a half-written ``.tvsc``. ``os.replace`` is atomic
  within a filesystem, and the temp file is created in the same directory so
  it always is. This is what makes the design correct even if a second
  *process* (a second uvicorn worker, a stray CLI) builds at the same time:
  the lock is an efficiency measure, the atomic rename is the correctness one.

The directory is bookkeeping, not a BIDS entity, so it is added to the
project's ``.bidsignore`` the same way ``code/ti-toolbox/jobs/`` is
(:func:`tit.jobs.registry.ensure_bidsignore`); the helper is duplicated here
rather than imported so :mod:`tit.scene` never has to import
:mod:`tit.jobs`.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from tit.paths import is_within, validate_subject_id

__all__ = [
    "BIDSIGNORE_LINE",
    "CachedArtifact",
    "cache_dir",
    "ensure_bidsignore",
    "fingerprint",
    "FORMATS",
    "artifact_paths",
    "find_cached",
    "publish",
    "prune_stale",
    "subject_lock",
]

#: Same convention as ``tit.jobs.registry.BIDSIGNORE_LINE``: a generated cache
#: of scene payloads is server bookkeeping, and bids-validator would flag every
#: ``.tvsc`` in it as an unrecognised data file.
BIDSIGNORE_LINE = "derivatives/ti-toolbox/scene_cache/"

_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class CachedArtifact:
    """One published cache entry: its bytes, its sidecar, and the sidecar's data."""

    path: Path
    sidecar: Path
    meta: dict


def _cache_path(project_dir: str | os.PathLike[str], path: Path) -> Path:
    """Check a resolved cache target while retaining its final replace/unlink entry."""
    resolved = os.path.realpath(path)
    parent = os.path.realpath(path.parent)
    if (
        not is_within(str(project_dir), parent)
        or not is_within(str(project_dir), resolved)
        or resolved == os.path.realpath(project_dir)
    ):
        raise PermissionError("Scene cache resolves outside the project")
    return Path(parent) / path.name


def cache_dir(project_dir: str | os.PathLike[str], subject_id: str) -> Path:
    """``<project>/derivatives/ti-toolbox/scene_cache/sub-<id>/``."""
    validate_subject_id(subject_id)
    return _cache_path(
        project_dir,
        (
            Path(project_dir)
            / "derivatives"
            / "ti-toolbox"
            / "scene_cache"
            / f"sub-{subject_id}"
        ),
    )


def ensure_bidsignore(project_dir: str | os.PathLike[str]) -> None:
    """Make sure the project's ``.bidsignore`` lists :data:`BIDSIGNORE_LINE`.

    Idempotent, and appends without touching any existing line -- users curate
    that file by hand, so rewriting it would throw away their entries.
    """
    try:
        target = _cache_path(project_dir, Path(project_dir) / ".bidsignore")
    except PermissionError:
        return  # Bookkeeping is optional; an outward link must never be followed.
    try:
        existing = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        existing = []
    if BIDSIGNORE_LINE in existing:
        return
    lines = [*existing, BIDSIGNORE_LINE] if existing else [BIDSIGNORE_LINE]
    try:
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        # A read-only project must not stop a scene from being served; the
        # only consequence is a bids-validator warning the user can silence.
        pass


def fingerprint(sources: list[str | os.PathLike[str]], version: str = "") -> str:
    """16 hex chars over ``(basename, size, mtime_ns)`` of each source file.

    A missing source contributes ``"-"`` rather than raising, so a subject
    with (say) no ``rh`` annotation still gets a stable, distinct fingerprint
    instead of no cache at all.

    *version* is the **builder's** own contribution, and it is not optional
    for a real caller (:data:`tit.scene.build.BUILDER_VERSION` is what every
    one of them passes). The source files say what went *in*; they cannot say
    what the code made of it, so without a version salt an entry written by an
    older builder is served for ever from unchanged inputs -- which is exactly
    what happened to the inward-wound ``gm`` surface fixed on 2026-09-04: the
    mesh had not changed, so neither had the fingerprint, so the corrected
    build was never reached. It defaults to ``""`` (no salt) only so the pure
    cache tests can exercise the source half on its own.
    """
    digest = hashlib.sha256()
    if version:
        digest.update(f"builder:{version}\n".encode())
    for source in sources:
        path = Path(source)
        try:
            st = path.stat()
            digest.update(f"{path.name}:{st.st_size}:{st.st_mtime_ns}\n".encode())
        except OSError:
            digest.update(f"{path.name}:-\n".encode())
    return digest.hexdigest()[:16]


#: The serialisations one key can be cached in, and the file extension each
#: uses. ``tvsc`` is :mod:`tit.scene.tvsc`, the frozen compatibility payload;
#: ``gii`` is :mod:`tit.scene.gifti`, read by the Tetravox embed (decision E7).
#: They are separate *files* under the same key and fingerprint, so a
#: fingerprint change still expires both together and dropping one is dropping
#: one entry from this tuple.
FORMATS: tuple[str, ...] = ("tvsc", "gii")


def artifact_paths(
    project_dir: str | os.PathLike[str],
    subject_id: str,
    key: str,
    fp: str,
    ext: str = "tvsc",
) -> tuple[Path, Path]:
    """``(<key>.<fp>.<ext>, <key>.<fp>.json)`` inside the subject's cache dir.

    The sidecar is **shared** between formats: it describes the surface (vertex
    and triangle counts, the simplification, the bbox), not its encoding, and
    two sidecars would be two answers to "how many triangles is this".
    """
    if ext not in FORMATS:
        raise ValueError(
            f"unknown scene cache format {ext!r}; expected one of {FORMATS}"
        )
    for value in (key, fp):
        if not value or value in (".", "..") or "/" in value or "\\" in value:
            raise ValueError("Scene cache keys and fingerprints must be single entries")
    root = cache_dir(project_dir, subject_id)
    return (
        _cache_path(project_dir, root / f"{key}.{fp}.{ext}"),
        _cache_path(project_dir, root / f"{key}.{fp}.json"),
    )


def find_cached(
    project_dir: str | os.PathLike[str],
    subject_id: str,
    key: str,
    fp: str,
    ext: str = "tvsc",
) -> CachedArtifact | None:
    """The published entry for ``key``/``fp``, or ``None`` if it is not there.

    Both halves must exist: a payload whose sidecar is missing carries no
    triangle counts or build time, and the manifest would then have to lie
    about what it is serving.
    """
    blob, sidecar = artifact_paths(project_dir, subject_id, key, fp, ext)
    if not (blob.is_file() and sidecar.is_file()):
        return None
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    return CachedArtifact(path=blob, sidecar=sidecar, meta=meta)


def publish(
    project_dir: str | os.PathLike[str],
    subject_id: str,
    key: str,
    fp: str,
    blob: bytes,
    meta: dict,
    ext: str = "tvsc",
) -> CachedArtifact:
    """Write ``blob``/``meta`` atomically and delete this key's stale entries."""
    root = cache_dir(project_dir, subject_id)
    blob_path, sidecar_path = artifact_paths(project_dir, subject_id, key, fp, ext)
    root.mkdir(parents=True, exist_ok=True)
    ensure_bidsignore(project_dir)
    stamp = f"{os.getpid()}-{os.urandom(16).hex()}"
    tmp_blob = blob_path.with_name(blob_path.name + f".tmp-{stamp}")
    tmp_sidecar = sidecar_path.with_name(sidecar_path.name + f".tmp-{stamp}")
    payload = dict(meta, bytes=len(blob), fingerprint=fp, key=key)
    created: list[Path] = []
    try:
        with tmp_blob.open("xb") as handle:
            created.append(tmp_blob)
            handle.write(blob)
        with tmp_sidecar.open("x", encoding="utf-8") as handle:
            created.append(tmp_sidecar)
            handle.write(json.dumps(payload, indent=2) + "\n")
        # Sidecar first: a reader that sees the .tvsc must always find the
        # sidecar next to it (find_cached requires both), never the reverse.
        os.replace(tmp_sidecar, sidecar_path)
        os.replace(tmp_blob, blob_path)
    finally:
        for leftover in created:
            leftover.unlink(missing_ok=True)
    prune_stale(project_dir, subject_id, key, fp)
    return CachedArtifact(path=blob_path, sidecar=sidecar_path, meta=payload)


def prune_stale(
    project_dir: str | os.PathLike[str], subject_id: str, key: str, keep_fp: str
) -> list[Path]:
    """Delete ``<key>.<other>.{tvsc,json}`` files, keeping ``keep_fp``.

    Without this the cache grows a new copy of every surface each time charm
    is re-run, and nothing ever reclaims the old ones.
    """
    root = cache_dir(project_dir, subject_id)
    removed: list[Path] = []
    if not root.is_dir():
        return removed
    for path in root.iterdir():
        name = path.name
        if not name.startswith(f"{key}."):
            continue
        if not (name.endswith(".json") or any(name.endswith(f".{e}") for e in FORMATS)):
            continue
        middle = name[len(key) + 1 : name.rindex(".")]
        if middle == keep_fp:
            continue
        try:
            path.unlink()
            removed.append(path)
        except OSError:  # pragma: no cover - another process got there first
            pass
    return removed


def subject_lock(
    project_dir: str | os.PathLike[str], subject_id: str
) -> threading.Lock:
    """The one build lock for this project+subject, created on first use."""
    key = (str(project_dir), subject_id)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = _LOCKS[key] = threading.Lock()
        return lock
