"""EEG caps on an existing head model, without re-running charm.

Two jobs, both plain functions:

* :func:`warp_caps` does exactly what charm does at the end of a head-model
  build (SimNIBS 4.6 ``segmentation/charm_main.py``, "Transforming EEG
  positions"): crop the head mesh to its skin triangles and call
  ``simnibs.utils.transformations.warp_coordinates(cap, m2m, "mni2subject",
  out_name=<eeg_positions>/<cap>.csv, out_geo=<...>.geo, mesh_in=skin,
  skin_tag=1005)`` for each cap. Sources are SimNIBS's
  ``resources/ElectrodeCaps_MNI`` (which in the image includes TI-Toolbox's
  caps) and the project's own MNI caps under ``code/ti-toolbox/eeg_caps/``.
* :func:`net_stats` / :func:`compare_nets` inspect a net already on the head:
  nearest-neighbour spacing, distance to the scalp, electrodes that collapsed
  onto each other (the failure a cap in the wrong space produces -- 43 GSN-128
  electrodes on one scalp point before 6361c2b2), duplicate labels, and the
  nearest electrode of a second net.

``simnibs`` is imported inside the functions that need it: the route module
that calls these must import nothing heavy (``dev/route_import_guard.py``).
"""

from __future__ import annotations

import csv
import io
import math
import os
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from tit.paths import PathManager

#: charm's skin surface tag (``charm.ini`` ``[mesh] skin_tag = 1005``), the
#: tag ``tit.scene.build`` crops the served skin from.
SKIN_TAG = 1005

#: Two electrodes closer than this are reported as collapsed. Real caps space
#: neighbours >= ~9 mm apart (GSN-256 is the densest shipped); 2 mm is well
#: below any real spacing and well above warp round-off.
COLLAPSE_MM = 2.0

#: An uploaded MNI cap: a few hundred rows at most in any real cap.
MAX_CAP_BYTES = 256 * 1024
MAX_CAP_ROWS = 2048
#: |coordinate| bound for an MNI cap -- the MNI152 head fits in +-120 mm, so a
#: value past this is a cap in some other space (or millimetres x 10).
MNI_LIMIT_MM = 200.0

_ROW_TYPES = {"electrode", "referenceelectrode", "fiducial"}


class CapError(ValueError):
    """An MNI cap file that cannot be warped as it stands."""


def simnibs_caps_dir() -> Path:
    """SimNIBS's ``resources/ElectrodeCaps_MNI`` -- the folder charm warps."""
    from simnibs.utils.file_finder import ElectrodeCaps_MNI

    return Path(ElectrodeCaps_MNI)


def source_caps(pm: PathManager) -> dict[str, tuple[str, Path]]:
    """``{cap file name: (source, path)}`` for every MNI cap that can be warped.

    ``source`` is ``"simnibs"`` or ``"project"``. A project cap never shadows a
    SimNIBS one: :func:`validate_mni_cap` callers refuse the name on upload.
    """
    found: dict[str, tuple[str, Path]] = {}
    for source, directory in (
        ("project", Path(pm.custom_eeg_caps())),
        ("simnibs", simnibs_caps_dir()),
    ):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.csv"):
            if not path.name.startswith("."):
                found[path.name] = (source, path)
    return found


def available_caps(pm: PathManager, sid: str) -> list[dict[str, Any]]:
    """Every source cap plus every net already on *sid*, with their status.

    ``outdated`` means the source file is newer than the subject's copy:
    the image (or the project) carries a cap that changed after this head was
    warped. ponytail: mtime, not content -- an image rebuild touches every
    source, so after an image update every charm-era cap reads as outdated;
    add a recorded source hash per warped cap if that noise matters.
    """
    sources = source_caps(pm)
    on_subject = set(pm.list_eeg_caps(sid))
    positions = Path(pm.eeg_positions(sid))
    rows = []
    for name in sorted(set(sources) | on_subject, key=str.lower):
        source, path = sources.get(name, (None, None))
        source_mtime = path.stat().st_mtime if path else None
        subject_mtime = (
            (positions / name).stat().st_mtime if name in on_subject else None
        )
        rows.append(
            {
                "name": name,
                "source": source,
                "on_subject": name in on_subject,
                "source_mtime": source_mtime,
                "subject_mtime": subject_mtime,
                "outdated": bool(
                    source_mtime is not None
                    and subject_mtime is not None
                    and source_mtime > subject_mtime
                ),
            }
        )
    return rows


def warp_caps(m2m_dir: str, sid: str, caps: list[Path], out_dir: str) -> list[dict]:
    """Warp each MNI cap onto the head, as charm does; one mesh read for all.

    Each cap is written to a hidden temporary name and renamed into place, so
    a warp that fails half-way leaves the previous file (or none) rather than
    a truncated net that the rest of the app would read.
    """
    from simnibs.mesh_tools import mesh_io
    from simnibs.utils import transformations

    mesh = mesh_io.read_msh(os.path.join(m2m_dir, f"{sid}.msh"))
    idx = mesh.elm.get_triangles(SKIN_TAG)
    skin = mesh.crop_mesh(elements=mesh.elm.elm_number[idx])
    del mesh
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for cap in caps:
        stem = cap.stem
        tmp = os.path.join(out_dir, f".tmp-{stem}")
        try:
            transformations.warp_coordinates(
                str(cap),
                m2m_dir,
                transformation_direction="mni2subject",
                out_name=tmp + ".csv",
                out_geo=tmp + ".geo",
                mesh_in=skin,
                skin_tag=SKIN_TAG,
            )
            os.replace(tmp + ".csv", os.path.join(out_dir, f"{stem}.csv"))
            if os.path.exists(tmp + ".geo"):
                os.replace(tmp + ".geo", os.path.join(out_dir, f"{stem}.geo"))
        finally:
            for leftover in (tmp + ".csv", tmp + ".geo"):
                if os.path.exists(leftover):
                    os.remove(leftover)
        written.append({"name": cap.name})
    return written


def validate_mni_cap(text: str) -> int:
    """Number of electrodes in an MNI cap CSV, or raise :class:`CapError`.

    The format charm reads: ``Type,x,y,z,name[,...]`` with ``Type`` one of
    ``Electrode`` / ``ReferenceElectrode`` / ``Fiducial``. Untrusted input:
    every row is checked, and nothing is accepted that the warp would
    silently skip or misplace.
    """
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if not rows:
        raise CapError("The file has no rows.")
    if len(rows) > MAX_CAP_ROWS:
        raise CapError(f"More than {MAX_CAP_ROWS} rows; that is not an EEG cap.")
    electrodes = 0
    for number, row in enumerate(rows, start=1):
        kind = row[0].strip().lower()
        if kind not in _ROW_TYPES or len(row) < 5:
            raise CapError(
                f"Row {number}: expected Electrode|ReferenceElectrode|Fiducial,x,y,z,name."
            )
        try:
            xyz = [float(v) for v in row[1:4]]
        except ValueError:
            raise CapError(f"Row {number}: x, y and z must be numbers.") from None
        if not all(math.isfinite(v) and abs(v) <= MNI_LIMIT_MM for v in xyz):
            raise CapError(
                f"Row {number}: coordinates must be MNI millimetres within ±{MNI_LIMIT_MM:g}."
            )
        if not row[4].strip():
            raise CapError(f"Row {number}: the electrode has no name.")
        electrodes += kind != "fiducial"
    if electrodes == 0:
        raise CapError("The file has no Electrode rows.")
    return electrodes


def _distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=-1))


def nearest_distance(points: np.ndarray, cloud: np.ndarray) -> np.ndarray:
    """Distance from each point to its nearest cloud point, in chunks.

    ponytail: brute force (n x m), ~0.1 s for 256 electrodes x 100 k skin
    nodes; a KD-tree if a cloud gets much larger.
    """
    out = np.empty(len(points))
    for start in range(0, len(points), 16):
        out[start : start + 16] = _distances(points[start : start + 16], cloud).min(
            axis=1
        )
    return out


@lru_cache(maxsize=2)
def _skin_nodes_cached(mesh_path: str, _mtime: float) -> np.ndarray:
    from simnibs.mesh_tools import mesh_io

    skin = mesh_io.read_msh(mesh_path).crop_mesh(tags=[SKIN_TAG])
    return np.asarray(skin.nodes.node_coord, dtype=np.float64)


def skin_nodes(mesh_path: str) -> np.ndarray:
    """The head mesh's skin nodes (full resolution), cached per file version."""
    return _skin_nodes_cached(mesh_path, os.path.getmtime(mesh_path))


def net_stats(
    names: list[str],
    world: np.ndarray,
    skin: np.ndarray | None = None,
    collapse_mm: float = COLLAPSE_MM,
) -> dict[str, Any]:
    """Per-electrode spacing and scalp distance, collapsed pairs, duplicate labels."""
    world = np.asarray(world, dtype=np.float64).reshape(-1, 3)
    n = len(world)
    rows: list[dict[str, Any]] = []
    collapsed: list[dict[str, Any]] = []
    nn = np.full(n, np.nan)
    nn_index = np.zeros(n, dtype=int)
    if n > 1:
        d = _distances(world, world)
        np.fill_diagonal(d, np.inf)
        nn = d.min(axis=1)
        nn_index = d.argmin(axis=1)
        for i, j in zip(*np.nonzero(np.triu(d < collapse_mm, k=1))):
            collapsed.append(
                {"a": names[i], "b": names[j], "distance_mm": round(float(d[i, j]), 3)}
            )
    scalp = nearest_distance(world, skin) if skin is not None and n else None
    for i, name in enumerate(names):
        rows.append(
            {
                "name": name,
                "world": [round(float(v), 3) for v in world[i]],
                "nn_mm": None if n < 2 else round(float(nn[i]), 3),
                "nn_name": None if n < 2 else names[int(nn_index[i])],
                "scalp_mm": None if scalp is None else round(float(scalp[i]), 3),
            }
        )

    def stat(values: np.ndarray | None, fn) -> float | None:
        return (
            None if values is None or len(values) == 0 else round(float(fn(values)), 3)
        )

    finite_nn = nn[np.isfinite(nn)] if n > 1 else None
    return {
        "collapse_mm": collapse_mm,
        "electrodes": rows,
        "collapsed": collapsed,
        "duplicate_names": sorted(k for k, v in Counter(names).items() if v > 1),
        "summary": {
            "count": n,
            "nn_min_mm": stat(finite_nn, np.min),
            "nn_median_mm": stat(finite_nn, np.median),
            "nn_max_mm": stat(finite_nn, np.max),
            "scalp_median_mm": stat(scalp, np.median),
            "scalp_max_mm": stat(scalp, np.max),
        },
    }


def compare_nets(
    world_a: np.ndarray, names_b: list[str], world_b: np.ndarray
) -> list[dict]:
    """For each electrode of net A, the nearest electrode of net B and its distance."""
    if len(world_b) == 0:
        return [{"name": None, "distance_mm": None} for _ in range(len(world_a))]
    d = _distances(
        np.asarray(world_a, float).reshape(-1, 3), np.asarray(world_b, float)
    )
    j = d.argmin(axis=1)
    return [
        {"name": names_b[int(k)], "distance_mm": round(float(d[i, k]), 3)}
        for i, k in enumerate(j)
    ]
