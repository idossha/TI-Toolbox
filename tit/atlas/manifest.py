"""The one description of every atlas TI-Toolbox ships in MNI space.

``resources/atlas/manifest.json`` is the source of truth. Before it existed the
MNI atlas list was a bare list of filenames in :mod:`tit.atlas.constants`, and
nothing recorded whether a file was a **surface** parcellation or a **volume**
one -- so the ROI picker could only guess which targeting flow an MNI atlas
belongs to, and offered every shipped MNI atlas under "Subcortical" whatever it
was.  ``kind`` is that missing fact, and the licence fields beside it are the
second thing that was written down only in prose: what may be redistributed, by
whom, with what attribution.

Every shipped MNI atlas today is ``kind: "volume"`` -- including the Glasser
HCP-MMP1.0 cortical parcellation, which is a *cortical* atlas distributed as a
label volume.  ``kind`` describes the file, not the anatomy: it says which
targeting flow can read it.  A surface (``.annot``/``.gii``) MNI atlas would
carry ``kind: "surface"`` and route to the cortical flow; none is shipped yet.

Subject-space atlases are not listed here -- they are discovered per subject --
but they carry the same ``kind`` field, detected from the extension
(:func:`kind_for_path`), so one vocabulary describes both.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"

#: Surface parcellations are FreeSurfer annotations or GIFTI label files.
SURFACE_SUFFIXES = (".annot", ".gii", ".label.gii")

#: What a targeting mode may offer: cortical reads surfaces, subcortical volumes.
KIND_FOR_MODE = {"cortical": "surface", "subcortical": "volume"}


def kind_for_path(path: str) -> str:
    """``"surface"`` for a ``.annot``/``.gii`` parcellation, else ``"volume"``.

    The subject-space rule, unchanged in behaviour and now named: a cortical
    atlas is a per-hemisphere FreeSurfer annotation, everything else
    (``.nii``/``.nii.gz``/``.mgz``) is a label volume.
    """
    lowered = str(path).lower()
    return "surface" if lowered.endswith(SURFACE_SUFFIXES) else "volume"


@lru_cache(maxsize=8)
def _load(directory: str) -> dict[str, Any]:
    path = os.path.join(directory, MANIFEST_NAME)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning("Could not read the atlas manifest %s: %s", path, exc)
        return {"version": 0, "atlases": []}


def mni_atlas_entries(directory: str | None = None) -> list[dict[str, Any]]:
    """Every manifest entry, in manifest order, whose file is present on disk.

    An entry whose file is missing is dropped rather than offered: the manifest
    describes what the repository ships, and a trimmed image (or an atlas moved
    to an optional download) must not put an unusable name in the picker.
    """
    from tit.atlas.constants import mni_resources_dir

    packaged = mni_resources_dir()
    root = directory or packaged
    # A caller may point at a *copy* of the atlas directory (a trimmed image, a
    # test fixture) that holds the volumes but not the manifest; the packaged
    # manifest still describes them, so fall back to it and resolve the files
    # against the directory that was asked for.
    described = _load(root)
    if not described.get("atlases") and root != packaged:
        described = _load(packaged)
    entries = []
    for entry in described.get("atlases", []):
        file_name = entry.get("file")
        if not file_name:
            continue
        full = os.path.join(root, file_name)
        if not os.path.isfile(full):
            continue
        item = dict(entry)
        item["path"] = full
        item.setdefault("id", file_name)
        item.setdefault("name", file_name)
        item.setdefault("kind", kind_for_path(file_name))
        entries.append(item)
    return entries


def mni_atlas_files(directory: str | None = None) -> list[str]:
    """Manifest-ordered basenames of the shipped MNI atlases."""
    return [entry["file"] for entry in mni_atlas_entries(directory)]


def not_shipped_message(atlas: str, directory: str | None = None) -> str | None:
    """The one-sentence reason *atlas* is no longer shipped, or ``None``.

    An atlas that was removed from the repository (a licence that forbids
    redistribution, for instance) is listed under ``not_shipped`` in the
    manifest with the sentence a user should read.  *atlas* may be a bare
    filename or a full path; only its basename is compared.  A configuration
    that still names such an atlas must fail with that sentence rather than
    with "file not found".
    """
    from tit.atlas.constants import mni_resources_dir

    name = os.path.basename(str(atlas))
    for entry in _load(directory or mni_resources_dir()).get("not_shipped", []):
        if entry.get("id") == name:
            return entry.get("message") or f"The {name} atlas is no longer shipped."
    return None


def check_shipped(atlas: str) -> None:
    """Raise ``ValueError`` with the manifest's sentence if *atlas* was removed."""
    message = not_shipped_message(atlas)
    if message:
        raise ValueError(message)


def mni_atlas_entry(
    atlas_id: str, directory: str | None = None
) -> dict[str, Any] | None:
    """The manifest entry whose ``id`` (its filename) is *atlas_id*, or ``None``."""
    for entry in mni_atlas_entries(directory):
        if entry["id"] == atlas_id:
            return entry
    return None
