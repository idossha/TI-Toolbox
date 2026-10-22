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
import importlib.util
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

#: The four 10-20 sites that carry two names: the original 10-20 system's
#: T3/T4/T5/T6 are the 10-10 nomenclature's T7/T8/P7/P8 (Oostenveld &
#: Praamstra 2001, Table 1; ACNS guideline 5, 2006). A cap that lists both
#: names (SimNIBS's ``EEG10-20_extended_SPM12``) puts them on one point by
#: design, so such a pair is an alias, not a collapse.
ALIAS_PAIRS = frozenset(
    frozenset(pair) for pair in (("T3", "T7"), ("T4", "T8"), ("T5", "P7"), ("T6", "P8"))
)

#: What to do about a collapsed net: the panel action that re-warps it.
REAPPLY_FIX = (
    "Re-apply in EEG caps: open the EEG caps panel for sub-{sid}, select {net} and "
    "apply it again (or Re-apply all). That re-warps it onto this head; a net warped "
    "before TI-Toolbox 3.1.1 can have many electrodes on one scalp point."
)

#: An uploaded MNI cap: a few hundred rows at most in any real cap.
MAX_CAP_BYTES = 256 * 1024
MAX_CAP_ROWS = 2048
#: |coordinate| bound for an MNI cap -- the MNI152 head fits in +-120 mm, so a
#: value past this is a cap in some other space (or millimetres x 10).
MNI_LIMIT_MM = 200.0

#: The row types SimNIBS's ``read_csv_positions`` keeps, spelled the only way it
#: compares them (exactly: no strip, no case folding).
_ROW_TYPES = ("Electrode", "ReferenceElectrode", "Fiducial")


class CapError(ValueError):
    """An MNI cap file that cannot be warped as it stands."""


def simnibs_caps_dir() -> Path:
    """SimNIBS's ``resources/ElectrodeCaps_MNI`` -- the folder charm warps.

    Located with ``find_spec`` rather than by importing
    ``simnibs.utils.file_finder`` (which defines it the same way, from the
    package directory): that import costs ~4 s in the image and was most of
    the caps list's first answer.
    """
    spec = importlib.util.find_spec("simnibs")
    if spec is None or not spec.submodule_search_locations:
        raise CapError("SimNIBS is not installed")
    return Path(spec.submodule_search_locations[0]) / "resources" / "ElectrodeCaps_MNI"


# The caps TI-Toolbox ships in ``resources/ElectrodeCaps_MNI``; the image build
# copies them into SimNIBS's folder (``Dockerfile.ti-toolbox``), so only the
# name tells them apart there. ``tests/test_caps.py`` pins this to the folder.
TIT_CAPS = frozenset(
    {
        "BioSemi-128-A1.csv",
        "BioSemi-256-A1.csv",
        "BioSemi-64-10-10.csv",
        "GSN-HydroCel-128.csv",
        "GSN-HydroCel-185.csv",
        "GSN-HydroCel-256.csv",
    }
)


def has_electrodes(path: str | os.PathLike) -> bool:
    """Whether the cap file at *path* has at least one ``Electrode`` row.

    The catalog's rule (``tit.catalog._eeg_caps_with_electrodes``), shared so
    the caps panel and every net picker agree: SimNIBS's ``Fiducials.csv``
    (Nz/Iz/LPA/RPA, which charm also writes to every ``eeg_positions``) is a
    landmark file, not a cap. A file that is not text has no electrodes.
    """
    from tit.catalog import _read_cap_electrode_labels

    try:
        return bool(_read_cap_electrode_labels(os.fspath(path)))
    except ValueError:  # UnicodeDecodeError: not a text file
        return False


def source_caps(pm: PathManager) -> dict[str, tuple[str, Path]]:
    """``{cap file name: (source, path)}`` for every MNI cap that can be warped.

    ``source`` is ``"ti-toolbox"`` (a cap TI-Toolbox ships, even where it
    replaces a SimNIBS file of that name), ``"simnibs"`` or ``"project"``. A
    project cap never shadows an image one: the upload route refuses the name.
    A file with no electrode (:func:`has_electrodes`) is not a cap.
    """
    found: dict[str, tuple[str, Path]] = {}
    for source, directory in (
        ("project", Path(pm.custom_eeg_caps())),
        ("simnibs", simnibs_caps_dir()),
    ):
        if not directory.is_dir():
            continue
        for path in directory.glob("*.csv"):
            if not path.name.startswith(".") and has_electrodes(path):
                tit = source == "simnibs" and path.name in TIT_CAPS
                found[path.name] = ("ti-toolbox" if tit else source, path)
    return found


def available_caps(pm: PathManager, sid: str) -> list[dict[str, Any]]:
    """Every source cap plus every net already on *sid*, with their status.

    ``subject_mtime`` is when the subject's copy was written (applied). A file
    on the subject with no electrode (``Fiducials.csv``) is not a net.
    """
    sources = source_caps(pm)
    positions = Path(pm.eeg_positions(sid))
    on_subject = {
        name for name in pm.list_eeg_caps(sid) if has_electrodes(positions / name)
    }
    rows = []
    for name in sorted(set(sources) | on_subject, key=str.lower):
        rows.append(
            {
                "name": name,
                "source": sources.get(name, (None,))[0],
                "on_subject": name in on_subject,
                "subject_mtime": (
                    (positions / name).stat().st_mtime if name in on_subject else None
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


def _csv_rows(text: str) -> list[list[str]]:
    """*text*'s CSV rows, any line ending; a UTF-8 byte-order mark is dropped."""
    try:
        return list(csv.reader(io.StringIO(text.removeprefix("\ufeff"), newline="")))
    except csv.Error as exc:
        raise CapError(f"Not a readable CSV file: {exc}.") from None


def normalise_mni_cap(text: str) -> str:
    """*text* as the upload route stores it: no byte-order mark, no blank rows, ``\\n`` ends.

    SimNIBS's ``read_csv_positions`` reads ``row[0]`` of every row, so a blank
    row in the middle of a cap raises ``IndexError``; it refuses a file whose
    last row has fewer than three cells, so one blank line too many at the end
    raises ``OSError``; and a byte-order mark (Excel's "CSV UTF-8") becomes
    part of the first type cell, so that row is dropped. Removing them changes
    no electrode.
    """
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(
        row for row in _csv_rows(text) if any(cell.strip() for cell in row)
    )
    return out.getvalue()


def _mni_mm(cells: list[str], number: int) -> None:
    try:
        values = [float(v) for v in cells]
    except ValueError:
        raise CapError(f"Row {number}: x, y and z must be numbers.") from None
    if not all(math.isfinite(v) and abs(v) <= MNI_LIMIT_MM for v in values):
        raise CapError(
            f"Row {number}: coordinates must be MNI millimetres within ±{MNI_LIMIT_MM:g}."
        )


def _numbers(cells: list[str]) -> bool:
    try:
        [float(v) for v in cells]
    except ValueError:
        return False
    return True


def validate_mni_cap(text: str) -> int:
    """Number of electrodes in an MNI cap CSV, or raise :class:`CapError`.

    The format charm reads, as SimNIBS's ``read_csv_positions`` reads it:
    ``Type,x,y,z,name[,...]`` or ``Type,x,y,z,pos2_x,pos2_y,pos2_z,name[,...]``,
    with ``Type`` spelled exactly ``Electrode`` / ``ReferenceElectrode`` /
    ``Fiducial``. Untrusted input: the :func:`normalise_mni_cap` form of
    *text* is checked row by row, and nothing is accepted that the warp would
    skip, crash on or file under another name -- a type in another case or
    with a space (skipped), a name with spaces around it (kept with them, so
    ``Cz`` is not found), a repeated electrode name (the net keeps one).

    Args:
        text: The cap file's text.

    Returns:
        The number of ``Electrode`` and ``ReferenceElectrode`` rows.

    Raises:
        CapError: The first rule the file breaks, naming its row.
    """
    rows = _csv_rows(normalise_mni_cap(text))
    if not rows:
        raise CapError("The file has no rows.")
    if len(rows) > MAX_CAP_ROWS:
        raise CapError(f"More than {MAX_CAP_ROWS} rows; that is not an EEG cap.")
    names: list[str] = []
    for number, row in enumerate(rows, start=1):
        kind = row[0]
        if kind not in _ROW_TYPES:
            spelled = [t for t in _ROW_TYPES if t.lower() == kind.strip().lower()]
            if spelled:
                raise CapError(
                    f"Row {number}: write the type exactly as {spelled[0]}; "
                    f"SimNIBS skips a row typed {kind!r}."
                )
        if kind not in _ROW_TYPES or len(row) < 5:
            raise CapError(
                f"Row {number}: expected Electrode|ReferenceElectrode|Fiducial,x,y,z,name."
            )
        _mni_mm(row[1:4], number)
        name = row[4]
        if kind != "Fiducial" and len(row) >= 7 and _numbers(row[4:7]):
            # SimNIBS reads cells 5-7 as a second position and the name from cell 8.
            _mni_mm(row[4:7], number)
            name = row[7] if len(row) >= 8 else ""
        if not name.strip():
            raise CapError(f"Row {number}: the electrode has no name.")
        if name != name.strip():
            raise CapError(
                f"Row {number}: the name {name!r} has spaces around it; SimNIBS keeps "
                f"them, so the electrode would not be found as {name.strip()!r}."
            )
        if kind != "Fiducial":
            names.append(name)
    repeated = sorted(k for k, v in Counter(names).items() if v > 1)
    if repeated:
        raise CapError(
            f"Electrode names repeat: {', '.join(repeated[:5])}"
            f"{', ...' if len(repeated) > 5 else ''}; SimNIBS keeps only the last row "
            f"of each name."
        )
    if not names:
        raise CapError("The file has no Electrode rows.")
    return len(names)


def _distances(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(axis=-1))


def nearest_distance(points: np.ndarray, cloud: np.ndarray) -> np.ndarray:
    """Distance from each point to its nearest cloud point.

    ponytail: brute force as one matrix product (|p|^2 + |c|^2 - 2 p.c), so
    256 electrodes x 35 k skin nodes is one BLAS call instead of a Python
    loop of broadcasts; the nearest node is then re-measured exactly, so the
    product's round-off never reaches the answer. A KD-tree if a cloud gets
    much larger (``scipy`` is mocked in the host suite).
    """
    points = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    cloud = np.asarray(cloud, dtype=np.float64).reshape(-1, 3)
    squared = (
        (points**2).sum(axis=1)[:, None]
        + (cloud**2).sum(axis=1)[None, :]
        - 2.0 * points @ cloud.T
    )
    nearest = cloud[squared.argmin(axis=1)]
    return np.sqrt(((points - nearest) ** 2).sum(axis=1))


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
    """Per-electrode spacing and scalp distance, collapsed pairs, duplicate labels.

    Two electrodes closer than *collapse_mm* are ``collapsed``, unless their
    labels are one of the 10-20 :data:`ALIAS_PAIRS`; those are listed under
    ``aliases`` instead, since a cap carrying both names puts them on one point.
    """
    world = np.asarray(world, dtype=np.float64).reshape(-1, 3)
    n = len(world)
    rows: list[dict[str, Any]] = []
    collapsed: list[dict[str, Any]] = []
    aliases: list[dict[str, Any]] = []
    nn = np.full(n, np.nan)
    nn_index = np.zeros(n, dtype=int)
    if n > 1:
        d = _distances(world, world)
        np.fill_diagonal(d, np.inf)
        nn = d.min(axis=1)
        nn_index = d.argmin(axis=1)
        for i, j in zip(*np.nonzero(np.triu(d < collapse_mm, k=1))):
            pair = {
                "a": names[i],
                "b": names[j],
                "distance_mm": round(float(d[i, j]), 3),
            }
            is_alias = frozenset((names[i], names[j])) in ALIAS_PAIRS
            (aliases if is_alias else collapsed).append(pair)
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
        "aliases": aliases,
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


def net_points(parsed: dict[str, list[dict[str, Any]]]) -> tuple[list[str], np.ndarray]:
    """Names and world positions of a parsed net's electrodes and reference.

    *parsed* is :func:`tit.scene.build.parse_electrode_csv`'s split. The
    reference is a physical electrode on the head, so it counts for spacing;
    fiducials are landmarks, not electrodes, and do not.
    """
    rows = parsed["electrodes"] + parsed["reference"]
    world = np.asarray([r["world"] for r in rows], dtype=np.float64).reshape(-1, 3)
    return [r["name"] for r in rows], world


def collapsed_pairs(parsed: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """The electrode pairs of a parsed net that sit on one point (aliases excluded)."""
    names, world = net_points(parsed)
    return net_stats(names, world)["collapsed"]


def net_file_collapsed(path: str | os.PathLike) -> list[dict[str, Any]]:
    """:func:`collapsed_pairs` of the net CSV at *path*; ``[]`` if it cannot be read."""
    from tit.scene.build import parse_electrode_csv

    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return collapsed_pairs(parse_electrode_csv(text))


def collapsed_summary(net: str, sid: str, pairs: list[dict[str, Any]]) -> str:
    """What is wrong with a collapsed net: how many pairs, and the first three."""
    shown = ", ".join(f"{p['a']}-{p['b']}" for p in pairs[:3])
    more = ", ..." if len(pairs) > 3 else ""
    return (
        f"EEG net {net} on sub-{sid} has {len(pairs)} electrode pair"
        f"{'' if len(pairs) == 1 else 's'} closer than {COLLAPSE_MM:g} mm "
        f"({shown}{more})"
    )


def collapsed_message(net: str, sid: str, pairs: list[dict[str, Any]]) -> str:
    """:func:`collapsed_summary` and the fix, as one message for an error."""
    return (
        f"{collapsed_summary(net, sid, pairs)}. {REAPPLY_FIX.format(sid=sid, net=net)}"
    )


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
