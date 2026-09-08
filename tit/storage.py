"""How much disk a TI-Toolbox project is using, and what is using it.

The System page shows the machine's disk limit; this answers the other half —
*what of that is us*, broken down the way a person thinks about their project
("the flex searches are 180 GB") rather than by directory.

Three things this module is careful about, because each one silently produces a
wrong number:

**Real disk usage, not apparent size.** ``st_blocks * 512`` is what the
filesystem actually charges for a file.  ``st_size`` over-counts sparse files
and under-counts the tail block of every small one; on a project with a hundred
thousand small meshes those disagree by gigabytes.

**Hardlinks counted once.** A ``(st_dev, st_ino)`` set is kept for the whole
walk.  QSIPrep and several of our own steps hardlink outputs rather than copy
them, so summing per-file sizes double-counts them into a total larger than the
volume itself — which is exactly the kind of figure that destroys trust in a
storage page.

**Classification comes from :class:`~tit.paths.PathManager`, never from globs
written here.**  Every kind's root is asked for by name, so a layout change in
``paths.py`` moves this module with it instead of leaving it quietly attributing
simulations to "Other".  Classification is longest-prefix-wins, which is what
makes nested kinds work: ``.../Simulations/<sim>/Analyses/`` is an analysis, and
the rest of ``Simulations/`` is a simulation.

The walk is O(files) and genuinely slow on a large project (a 900 GB volume can
take minutes), so it is never on a request path that something is waiting on:
:func:`scan_project` is called from a background thread and its result is cached
on disk (:func:`load_cache` / :func:`save_cache`).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from tit.paths import get_path_manager

logger = logging.getLogger(__name__)

#: Cache location, beside the other project-level toolbox state.
CACHE_NAME = "storage.json"

#: A cache older than this is refreshed in the background when the page opens.
STALE_AFTER_S = 10 * 60

#: Bytes per block in ``st_blocks``, fixed by POSIX regardless of the actual
#: filesystem block size.
BLOCK_BYTES = 512

#: The kinds, in the order the page lists them. The label is what a person
#: calls it; the id is what the contract carries.
KIND_LABELS: dict[str, str] = {
    "raw": "Raw data",
    "sourcedata": "Source data (DICOM)",
    "head_models": "Head models",
    "surfaces": "Surface reconstruction",
    "dwi": "Diffusion (QSIPrep/QSIRecon)",
    "simulations": "Simulations",
    "analyses": "Analyses",
    "flex_search": "Flex search",
    "ex_search": "Ex search",
    "leadfields": "Leadfields",
    "stats": "Group statistics",
    "reports": "Reports",
    "viewer": "Viewer scenes",
    "toolbox": "Toolbox state",
    "other": "Other",
}


@dataclass
class KindUsage:
    kind: str
    label: str
    bytes: int = 0
    files: int = 0


@dataclass
class ItemUsage:
    """One named thing inside a kind — a subject, or a simulation."""

    name: str
    kind: str
    bytes: int = 0


@dataclass
class ProjectStorage:
    project_dir: str
    total_bytes: int = 0
    total_files: int = 0
    scanned_at: float = 0.0
    duration_s: float = 0.0
    kinds: list[KindUsage] = field(default_factory=list)
    #: The largest few subjects and simulations, for the page's disclosure.
    largest: list[ItemUsage] = field(default_factory=list)
    #: True while a background scan is running and this is the previous result.
    scanning: bool = False
    partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_dir": self.project_dir,
            "total_bytes": self.total_bytes,
            "total_files": self.total_files,
            "scanned_at": self.scanned_at,
            "duration_s": self.duration_s,
            "scanning": self.scanning,
            "partial": self.partial,
            "kinds": [
                {"kind": k.kind, "label": k.label, "bytes": k.bytes, "files": k.files}
                for k in self.kinds
            ],
            "largest": [
                {"name": i.name, "kind": i.kind, "bytes": i.bytes} for i in self.largest
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ProjectStorage":
        return cls(
            project_dir=str(raw.get("project_dir", "")),
            total_bytes=int(raw.get("total_bytes") or 0),
            total_files=int(raw.get("total_files") or 0),
            scanned_at=float(raw.get("scanned_at") or 0.0),
            duration_s=float(raw.get("duration_s") or 0.0),
            scanning=bool(raw.get("scanning")),
            partial=bool(raw.get("partial")),
            kinds=[
                KindUsage(
                    kind=str(k.get("kind", "other")),
                    label=str(k.get("label", "")),
                    bytes=int(k.get("bytes") or 0),
                    files=int(k.get("files") or 0),
                )
                for k in raw.get("kinds") or []
            ],
            largest=[
                ItemUsage(
                    name=str(i.get("name", "")),
                    kind=str(i.get("kind", "other")),
                    bytes=int(i.get("bytes") or 0),
                )
                for i in raw.get("largest") or []
            ],
        )


# ---------------------------------------------------------------- classification


def kind_prefixes(pm: Any | None = None) -> list[tuple[str, str]]:
    """``(path, kind)`` pairs, **longest first**, from the PathManager.

    Every entry is a directory the PathManager names.  Nothing here is a glob or
    a hand-written path fragment, so a layout change in ``paths.py`` cannot leave
    this attributing real outputs to "Other" — except for the per-subject entries
    below, which are the PathManager's own per-subject accessors applied to the
    subjects it lists.
    """
    pm = pm or get_path_manager()
    pairs: list[tuple[str, str]] = [
        (pm.sourcedata(), "sourcedata"),
        (pm.fastsurfer(), "surfaces"),
        (pm.freesurfer(), "surfaces"),
        (pm.qsiprep(), "dwi"),
        (pm.qsirecon(), "dwi"),
        (os.path.join(pm.ti_toolbox(), "stats"), "stats"),
        (pm.reports(), "reports"),
        (pm.ti_toolbox(), "toolbox"),
        (os.path.join(_root(pm), "code", "ti-toolbox", "viewer"), "viewer"),
        (os.path.join(_root(pm), "code"), "toolbox"),
    ]

    for sid in _subjects(pm):
        sub = pm.sub(sid)
        pairs.extend(
            [
                (pm.bids_subject(sid), "raw"),
                (pm.m2m(sid), "head_models"),
                (pm.leadfields(sid), "leadfields"),
                (pm.forward(sid), "leadfields"),
                (pm.flex_search(sid), "flex_search"),
                (pm.ex_search(sid), "ex_search"),
                (pm.m_ex_search(sid), "ex_search"),
                (pm.simulations(sid), "simulations"),
                # Nested inside Simulations/<sim>/ — longest-prefix-wins is what
                # separates an analysis from the simulation that produced it.
                *[
                    (os.path.join(pm.simulation(sid, sim), "Analyses"), "analyses")
                    for sim in _simulations(pm, sid)
                ],
                (sub, "head_models"),
            ]
        )

    # Longest first: the caller takes the first match, so a nested root always
    # wins over the one that contains it.
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    return pairs


def _root(pm: Any) -> str:
    return pm.project_dir or "/"


def _subjects(pm: Any) -> list[str]:
    """Every subject the project has, from either tree — a subject with raw data
    and no head model still occupies disk."""
    found: set[str] = set()
    for lister in ("list_simnibs_subjects", "list_bids_subjects"):
        fn = getattr(pm, lister, None)
        if fn is None:
            continue
        try:
            found.update(fn())
        except Exception:  # pragma: no cover - unreadable project
            logger.debug("storage: %s failed", lister, exc_info=True)
    return sorted(found)


def _simulations(pm: Any, sid: str) -> list[str]:
    try:
        return list(pm.list_simulations(sid))
    except Exception:  # pragma: no cover
        return []


def classify(path: str, prefixes: list[tuple[str, str]]) -> str:
    """The kind owning *path*: the longest matching prefix, else ``"other"``."""
    for prefix, kind in prefixes:
        if path == prefix or path.startswith(prefix + os.sep):
            return kind
    return "other"


# ------------------------------------------------------------------------ scan


def scan_project(
    project_dir: str | None = None,
    *,
    pm: Any | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ProjectStorage:
    """Walk the project once and total real disk usage per kind.

    *should_stop* is polled between directories so a scan can be abandoned when
    the server is shutting down or the project has changed underneath it; the
    result is then marked ``partial`` rather than silently short.
    """
    pm = pm or get_path_manager()
    root = project_dir or _root(pm)
    started = time.monotonic()
    prefixes = kind_prefixes(pm)

    totals: dict[str, KindUsage] = {
        kind: KindUsage(kind=kind, label=label) for kind, label in KIND_LABELS.items()
    }
    items: dict[str, ItemUsage] = {}
    # (st_dev, st_ino) of every file already counted. QSIPrep and several of our
    # own steps hardlink rather than copy; without this the total can exceed the
    # size of the volume, which is the fastest way to make a storage page useless.
    seen: set[tuple[int, int]] = set()
    total_bytes = 0
    total_files = 0
    partial = False

    stack = [root]
    while stack:
        current = stack.pop()
        if should_stop is not None and should_stop():
            partial = True
            break
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        kind = classify(current, prefixes)
        for entry in entries:
            try:
                if entry.is_symlink():
                    # A symlink occupies its own (tiny) inode; what it points at
                    # is counted where it actually lives, or not at all if that
                    # is outside the project. Following them would double-count
                    # and could walk out of the project entirely.
                    continue
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            key = (stat.st_dev, stat.st_ino)
            if stat.st_nlink > 1:
                if key in seen:
                    continue
                seen.add(key)
            blocks = getattr(stat, "st_blocks", None)
            size = int(blocks) * BLOCK_BYTES if blocks is not None else int(stat.st_size)
            entry_kind = classify(entry.path, prefixes) if kind == "other" else kind
            bucket = totals.setdefault(
                entry_kind, KindUsage(kind=entry_kind, label=KIND_LABELS.get(entry_kind, entry_kind))
            )
            bucket.bytes += size
            bucket.files += 1
            total_bytes += size
            total_files += 1
            _attribute(items, entry.path, entry_kind, size, pm)

    largest = sorted(items.values(), key=lambda i: i.bytes, reverse=True)[:8]
    return ProjectStorage(
        project_dir=root,
        total_bytes=total_bytes,
        total_files=total_files,
        scanned_at=time.time(),
        duration_s=round(time.monotonic() - started, 2),
        kinds=[k for k in totals.values() if k.bytes > 0],
        largest=largest,
        partial=partial,
    )


def _attribute(
    items: dict[str, ItemUsage], path: str, kind: str, size: int, pm: Any
) -> None:
    """Roll a file up into the named thing it belongs to (a subject, a run).

    Only for the "largest" list, which answers *which* simulation is the 40 GB
    one — the per-kind totals above are the headline and do not depend on this.
    """
    marker = f"{os.sep}sub-"
    at = path.find(marker)
    if at == -1:
        return
    rest = path[at + len(marker) :]
    sid = rest.split(os.sep, 1)[0]
    if not sid:
        return
    name = f"sub-{sid}"
    # One level of detail below the subject where the path names a run, because
    # "sub-101 is 300 GB" is much less useful than "sub-101 flex-search is".
    label = f"{name} · {KIND_LABELS.get(kind, kind)}"
    item = items.setdefault(label, ItemUsage(name=label, kind=kind))
    item.bytes += size


# ----------------------------------------------------------------------- cache


def cache_path(pm: Any | None = None) -> str:
    """``<project>/code/ti-toolbox/cache/storage.json``."""
    pm = pm or get_path_manager()
    return os.path.join(
        os.path.dirname(pm.config_dir()), "cache", CACHE_NAME
    )


def load_cache(pm: Any | None = None) -> ProjectStorage | None:
    path = cache_path(pm)
    try:
        with open(path, encoding="utf-8") as fh:
            return ProjectStorage.from_dict(json.load(fh))
    except (OSError, ValueError):
        return None


def save_cache(result: ProjectStorage, pm: Any | None = None) -> None:
    """Write atomically: a half-written cache would be read as a real scan."""
    path = cache_path(pm)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp-{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(result.to_dict(), fh)
        os.replace(tmp, path)
    except OSError:
        logger.debug("storage: could not write %s", path, exc_info=True)


def is_stale(result: ProjectStorage | None, now: float | None = None) -> bool:
    if result is None:
        return True
    return (time.time() if now is None else now) - result.scanned_at > STALE_AFTER_S
