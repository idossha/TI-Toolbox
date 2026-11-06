"""A streamline file the user made for this head model: checked, labelled and kept under the subject.

``tractography/own/`` holds per file ``<name>.<trx|tck|trk>`` as uploaded, ``<name>.npz`` (the endpoint
labels the network stage would give it) and ``<name>.json``, written last, which says what was
checked. Coordinates are read as world RAS mm and never transformed. A file that does not fit is
refused before anything is stored or queued; no check here can show it was made for this subject.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from pathlib import Path

import numpy as np

from .config import NetworkConfig
from .io import load_streamlines
from .network import (
    assign_endpoints,
    default_label_volume,
    edges_from_labels,
    region_points,
)

logger = logging.getLogger(__name__)

EXTENSIONS = (".trx", ".tck", ".trk")
#: charm's ``final_tissues``: white matter, grey matter, CSF.
BRAIN_TISSUES = (1, 2, 3)
#: sub-CHN's tractogram has 100 % of its points in these tissues; shifted 20 mm, 92 %; the same
#: streamlines in QSIPrep's ACPC world, 69 % (2026-11-06, DECISIONS).
MIN_IN_BRAIN = 0.95
NOT_PROVEN = (
    "These checks show the streamlines fall inside this head model's brain. They cannot prove the "
    "file was made for this subject: another subject's file in a similar space, or one flipped "
    "left to right, can pass."
)


class OwnNetworkError(ValueError):
    """A file this head model cannot take, in words for the person who chose it."""


def stored_name(filename: str) -> tuple[str, str]:
    """``(name, extension)`` of an uploaded file; the name holds only letters, digits, ``_``, ``-``."""
    base = os.path.basename(filename.replace("\\", "/"))
    stem, extension = os.path.splitext(base)
    if extension.lower() not in EXTENSIONS:
        raise OwnNetworkError(
            f"{base} is not a streamline file: choose a .trx, .tck or .trk file."
        )
    name = re.sub(r"[^A-Za-z0-9_-]", "_", stem).strip("_")
    if not name:
        raise OwnNetworkError(
            f"{base} has no usable name; rename it and load it again."
        )
    return name, extension.lower()


def own_dir(pm, sid: str) -> Path:
    return Path(pm.tractography(sid)) / "own"


def tissues_path(pm, sid: str) -> str:
    return os.path.join(pm.m2m(sid), "final_tissues.nii.gz")


def check_fit(streamlines: list[np.ndarray], tissues: str) -> dict:
    """What was checked against the head model; :class:`OwnNetworkError` when the file does not fit."""
    import nibabel as nib

    if not streamlines:
        raise OwnNetworkError("This file holds no streamlines.")
    if min(len(s) for s in streamlines) < 2:
        raise OwnNetworkError(
            "This file holds a streamline with fewer than two points."
        )
    points = np.concatenate(streamlines)
    if not np.isfinite(points).all():
        raise OwnNetworkError(
            "This file holds coordinates that are not finite numbers."
        )
    img = nib.load(tissues)
    data = np.asanyarray(img.dataobj)
    data = data[..., 0] if data.ndim == 4 else data
    inverse = np.linalg.inv(img.affine)
    voxels = np.rint(points @ inverse[:3, :3].T + inverse[:3, 3]).astype(np.intp)
    inside = np.all((voxels >= 0) & (voxels < data.shape), axis=1)
    tissue = np.zeros(len(points), dtype=np.int64)
    tissue[inside] = data[tuple(voxels[inside].T)]
    in_head = float(np.mean(tissue > 0))
    in_brain = float(np.mean(np.isin(tissue, BRAIN_TISSUES)))
    if in_brain < MIN_IN_BRAIN:
        raise OwnNetworkError(
            f"Only {in_brain:.1%} of this file's points fall inside this head model's brain "
            f"(at least {MIN_IN_BRAIN:.0%} is needed; {in_head:.1%} are inside the head). It is "
            "probably in another space or from another subject. Coordinates are read as world "
            "millimetres and are not transformed: export the file in this head model's T1 space."
        )
    return {
        "coordinates": "read as world RAS mm, not transformed",
        "n_streamlines": len(streamlines),
        "n_points": len(points),
        "fraction_points_in_brain": round(in_brain, 4),
        "fraction_points_in_head": round(in_head, 4),
        "minimum_fraction_in_brain": MIN_IN_BRAIN,
        "checked_against": os.path.basename(tissues),
        "not_proven": NOT_PROVEN,
    }


def _network_config(pm, sid: str) -> NetworkConfig:
    """The subject's own network stage's atlas when it has run, else the stage's default."""
    record = Path(pm.tractography(sid)) / "network.json"
    if not record.is_file():
        return NetworkConfig()
    built = json.loads(record.read_text())
    return NetworkConfig(
        atlas=built.get("atlas", "DK40"),
        surface=built.get("surface", "central"),
        radius_mm=built.get("radius_mm", 3.0),
    )


def label_ends(pm, sid: str, streamlines: list[np.ndarray]) -> dict[str, np.ndarray]:
    """The network stage's endpoint labels and edges for *streamlines* (``run_network``'s method)."""
    cfg = _network_config(pm, sid)
    ends = np.stack([np.stack([s[0], s[-1]]) for s in streamlines])
    coords, region, names = region_points(
        pm.m2m(sid), default_label_volume(pm, sid), cfg.atlas, cfg.surface
    )
    labels = assign_endpoints(ends, coords, region, cfg.radius_mm)
    edge_id, pairs = edges_from_labels(labels)
    return {
        "labels": labels,
        "edge_id": edge_id,
        "pairs": pairs,
        "names": np.array(names),
        "counts": np.bincount(edge_id[edge_id >= 0], minlength=len(pairs)),
        "atlas": np.array(cfg.atlas),
        "radius_mm": np.array(cfg.radius_mm),
    }


def store(pm, sid: str, uploaded: Path, filename: str) -> dict:
    """Check *uploaded*, keep it as ``own/<name>``, and return its record. Moves the file on success.

    Raises:
        OwnNetworkError: it cannot be read, or does not fit, or the name holds another file.
    """
    name, extension = stored_name(filename)
    folder = own_dir(pm, sid)
    digest = hashlib.sha256()
    with uploaded.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    sha256 = digest.hexdigest()
    sidecar = folder / f"{name}.json"
    if sidecar.is_file():
        earlier = json.loads(sidecar.read_text())
        if earlier["sha256"] == sha256:
            return earlier  # the same file again: nothing to do
        raise OwnNetworkError(
            f"sub-{sid} already holds another file called {name}. Rename this one and load it again."
        )
    # The readers go by extension, and an upload's temporary name may have none.
    named = uploaded.with_name(f"upload{extension}")
    uploaded.rename(named)
    try:
        streamlines = load_streamlines(str(named))
    except (
        Exception
    ) as exc:  # noqa: BLE001 - many libraries' errors, one answer to the person
        raise OwnNetworkError(
            f"{os.path.basename(filename)} could not be read as a {extension} file: {exc}"
        ) from exc
    checks = check_fit(streamlines, tissues_path(pm, sid))
    network = label_ends(pm, sid, streamlines)
    n_labelled = int((network["edge_id"] >= 0).sum())
    folder.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(folder / f"{name}.npz", **network)
    shutil.move(str(named), str(folder / f"{name}{extension}"))
    record = {
        "name": name,
        "source_filename": os.path.basename(filename),
        "file": f"{name}{extension}",
        "sha256": sha256,
        "checks": checks,
        "atlas": str(network["atlas"]),
        "n_streamlines": len(streamlines),
        "n_both_ends_labelled": n_labelled,
        "n_unlabelled": len(streamlines) - n_labelled,
        "unlabelled_means": (
            f"an end more than {float(network['radius_mm']):g} mm from any {network['atlas']} region; "
            "these streamlines are drawn and assessed, and belong to no edge"
        ),
    }
    tmp = sidecar.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=1) + "\n")
    os.replace(tmp, sidecar)
    return record


def own_record(pm, sid: str, name: str) -> dict:
    """``own/<name>.json``. :class:`FileNotFoundError` when no such file was loaded."""
    return json.loads((own_dir(pm, sid) / f"{name}.json").read_text())


def list_own(pm, sid: str) -> list[dict]:
    """Every file loaded for this subject, by name."""
    folder = own_dir(pm, sid)
    return (
        [json.loads(p.read_text()) for p in sorted(folder.glob("*.json"))]
        if folder.is_dir()
        else []
    )


def own_counts(pm, sid: str, name: str):
    """``(pairs, streamlines per pair, n with an unlabelled end)``: what the automatic setup reads."""
    with np.load(own_dir(pm, sid) / f"{name}.npz", allow_pickle=False) as data:
        names = [str(n) for n in data["names"]]
        pairs = [(names[a], names[b]) for a, b in data["pairs"].tolist()]
        counts = dict(zip(pairs, data["counts"].tolist()))
    return (
        [list(pair) for pair in pairs],
        counts,
        own_record(pm, sid, name)["n_unlabelled"],
    )


def load_own(pm, sid: str, name: str) -> tuple[list[np.ndarray], dict[str, np.ndarray]]:
    """The file's streamlines and its ``network.npz``-shaped labels, for the assess stage."""
    record = own_record(pm, sid, name)
    streamlines = load_streamlines(str(own_dir(pm, sid) / record["file"]))
    with np.load(own_dir(pm, sid) / f"{name}.npz", allow_pickle=False) as data:
        return streamlines, {k: data[k] for k in data.files}
