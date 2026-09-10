"""The **fixed guide scene** — one immutable, project-independent head.

Plan of record: ``docs/dev/HISTORY.md § 2026-09-05`` R4. The three run pages'
3D panes used to draw *the first selected research subject*. That coupled a
form control to project data in three ways that each cost something real:

* it made the pane useless until a subject had a head model (a first-time
  project has none, and charm is an hour);
* it made every subject change a cache-cold rebuild of a 184 MB mesh, so
  ticking a second subject could stall the page for ~12 s;
* and it let a click on **one** subject's anatomy write a subject-RAS
  millimetre coordinate into a config that runs on a **different** subject —
  the coordinate is silently wrong, and nothing downstream can notice.

So the pane draws a guide instead: prebuilt, packaged, byte-identical on every
machine, and explicitly **not in any research subject's coordinate space**
(:data:`GUIDE_SPACE`). It is an anatomical *legend* for choosing names —
electrodes, nets, atlas regions — never coordinates.

What is packaged (:mod:`tit.scene.guide_build` generates it, this module only
reads it):

===========================  =============================================
``manifest.json``            every part, net, atlas and asset, with sizes
``surfaces/<part>.tvsc|gii`` skin and grey matter, within the §S3 budget
``labels/<atlas>.gii``       grey matter + per-vertex labels + label table
``legends/<atlas>.json``     the atlas' legend rows, as ``/api/scene/regions``
``nets/<net>.json``          one EEG net's electrode names and positions
===========================  =============================================

Never packaged: a full ``m2m_`` directory (184 MB of mesh plus volumes), the
label *volume*, or anything that would have to be rebuilt at runtime. The
whole point is that the server answers a guide request with a file read on a
machine that has no project bound at all.

Provenance and licence: ``tit/scene/guide/PROVENANCE.md``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

#: Coordinate space of every position in the packaged guide.
#:
#: Deliberately **not** ``"subject-ras"``. Those millimetres are the guide
#: head's own; a consumer that treats them as a research subject's own RAS
#: writes a wrong coordinate that no later validation can catch. The desktop
#: pane keys its "click-to-config is disabled here" behaviour off this string.
GUIDE_SPACE = "guide-ras"

#: Bumped whenever the packaged bytes or the manifest's shape change, so a
#: client can tell a stale cached manifest from a current one.
GUIDE_VERSION = 1

#: Where the packaged assets live, relative to this file.
GUIDE_DIR = Path(__file__).resolve().parent / "guide"

MANIFEST_NAME = "manifest.json"


class GuideUnavailable(Exception):
    """The packaged guide is missing or unreadable (a broken installation)."""


@dataclass(frozen=True)
class GuideAsset:
    """One packaged file: its bytes on disk plus what the manifest says of it."""

    path: Path
    meta: dict[str, Any]

    @property
    def sha256(self) -> str:
        return str(self.meta.get("sha256", ""))

    @property
    def bytes(self) -> int:
        return int(self.meta.get("bytes", 0))


def guide_dir() -> Path:
    """The packaged guide directory, overridable for tests.

    ``TIT_GUIDE_DIR`` exists so a test can point at a tiny fixture guide
    instead of the real ~15 MB one; nothing in the app sets it.
    """
    override = os.environ.get("TIT_GUIDE_DIR")
    return Path(override).resolve() if override else GUIDE_DIR


def _read_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GuideUnavailable(
            f"the packaged guide scene is missing: {path} does not exist. "
            "Reinstall TI-Toolbox, or regenerate it with "
            "`simnibs_python -m tit.scene.guide_build`."
        ) from exc
    except (OSError, ValueError) as exc:
        raise GuideUnavailable(f"the packaged guide manifest is unreadable: {exc}") from exc
    if not isinstance(body, dict) or "parts" not in body:
        raise GuideUnavailable(f"{path} is not a guide manifest")
    return body


@lru_cache(maxsize=4)
def _manifest_cached(root: str, stamp: tuple[int, int]) -> dict[str, Any]:
    return _read_manifest(Path(root))


def manifest() -> dict[str, Any]:
    """The guide manifest, read once per (path, mtime) pair.

    Cached on the manifest's own size+mtime rather than for ever: the file is
    immutable in an installation, but a developer regenerating it must not
    have to restart the server to see the new one.
    """
    root = guide_dir()
    try:
        stat = (root / MANIFEST_NAME).stat()
    except OSError as exc:
        raise GuideUnavailable(
            f"the packaged guide scene is missing: {root / MANIFEST_NAME} cannot be read "
            f"({exc}). Reinstall TI-Toolbox, or regenerate it with "
            "`simnibs_python -m tit.scene.guide_build`."
        ) from exc
    return _manifest_cached(str(root), (stat.st_size, int(stat.st_mtime_ns)))


def _entry(section: str, key: str, value: str) -> dict[str, Any]:
    body = manifest()
    for entry in body.get(section, []):
        if entry.get(key) == value:
            return entry
    listed = ", ".join(str(e.get(key)) for e in body.get(section, [])) or "nothing"
    raise GuideUnavailable(
        f"the guide has no {section[:-1]} {value!r}; it has: {listed}."
    )


def _asset(rel: str, meta: dict[str, Any]) -> GuideAsset:
    root = guide_dir()
    # `rel` never comes from a client: it is read out of the packaged manifest.
    # The resolve()/is_relative_to() pair is here so a hand-edited manifest
    # still cannot make the server read outside its own package directory.
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise GuideUnavailable(f"the guide asset {rel!r} is missing from {root}")
    return GuideAsset(path=path, meta=meta)


def part_ids() -> list[str]:
    return [str(part["id"]) for part in manifest().get("parts", [])]


def atlas_ids() -> list[str]:
    return [str(atlas["id"]) for atlas in manifest().get("atlases", [])]


def net_names() -> list[str]:
    return [str(net["name"]) for net in manifest().get("nets", [])]


def surface(part: str, fmt: str = "tvsc") -> GuideAsset:
    """The packaged surface bytes for *part* in *fmt* (``tvsc`` or ``gii``)."""
    entry = _entry("parts", "id", part)
    files = entry.get("files", {})
    if fmt not in files:
        raise GuideUnavailable(
            f"the guide's {part!r} surface is not packaged as {fmt!r}; "
            f"available: {', '.join(sorted(files)) or 'nothing'}."
        )
    return _asset(files[fmt], {**entry, **files.get(f"{fmt}_meta", {}), "format": fmt})


def labels(atlas: str, fmt: str = "gii") -> GuideAsset:
    """The packaged per-vertex label payload for *atlas*."""
    entry = _entry("atlases", "id", atlas)
    files = entry.get("files", {})
    if fmt not in files:
        raise GuideUnavailable(
            f"the guide's {atlas!r} labels are not packaged as {fmt!r}; "
            f"available: {', '.join(sorted(files)) or 'nothing'}."
        )
    return _asset(files[fmt], {**entry, **files.get(f"{fmt}_meta", {}), "format": fmt})


def legend(atlas: str) -> dict[str, Any]:
    """``{atlas, space, legend:[…], url, …}`` for one packaged atlas."""
    entry = _entry("atlases", "id", atlas)
    asset = _asset(entry["legend_file"], entry)
    try:
        body = json.loads(asset.path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GuideUnavailable(f"the guide legend for {atlas!r} is unreadable: {exc}") from exc
    return body


def electrodes(net: str) -> dict[str, Any]:
    """``{net, space, electrodes:[{name, world}]}`` for one packaged EEG net."""
    entry = _entry("nets", "name", net)
    asset = _asset(entry["file"], entry)
    try:
        body = json.loads(asset.path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GuideUnavailable(f"the guide net {net!r} is unreadable: {exc}") from exc
    return body


def iter_assets() -> list[tuple[str, GuideAsset]]:
    """Every file the manifest references, as ``(relative path, asset)``.

    The gate test walks this to prove nothing the manifest advertises is
    missing from the package.
    """
    body = manifest()
    out: list[tuple[str, GuideAsset]] = []
    for part in body.get("parts", []):
        for fmt, rel in part.get("files", {}).items():
            if fmt.endswith("_meta"):
                continue
            out.append((rel, _asset(rel, part)))
    for atlas in body.get("atlases", []):
        for fmt, rel in atlas.get("files", {}).items():
            if fmt.endswith("_meta"):
                continue
            out.append((rel, _asset(rel, atlas)))
        out.append((atlas["legend_file"], _asset(atlas["legend_file"], atlas)))
    for net in body.get("nets", []):
        out.append((net["file"], _asset(net["file"], net)))
    return out
