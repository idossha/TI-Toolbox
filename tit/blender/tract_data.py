"""Streamline data for the tract renders: TRX in, plain numpy arrays out.

The tract visuals (Blender stills and animations, the web viewer, the connectome figure) all
read a ``tit.tract`` output directory through this module, so the data contract lives in one
place:

``<bundle_or_all>.trx``
    streamlines in m2m world RAS mm, ``data_per_vertex`` ``ti_along``, ``ti_max``, ``e1_par``,
    ``e2_par`` (V/m) and ``data_per_streamline`` ``length_mm``, ``ti_along_max``,
    ``ti_along_mean``, ``edge_id`` (-1 unassigned).
``edges.json``
    ``edge_id -> {region_a, region_b, n_streamlines, stats}``.
``connectome_<metric>.npz``
    a square ``matrix`` and its ``labels``.

Only numpy and the standard library are imported: the Blender process, the host test suite
(which mocks SciPy and nibabel) and ``simnibs_python`` all import this file. A TRX is a zip (or
directory) of raw little-endian arrays named ``<name>[.<columns>].<dtype>``, so it is read here
without trx-python; ``tests/numerical/test_tract_viz_real.py`` checks the reader against it.
"""

from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass

import numpy as np

#: matplotlib 3.10.8 ``plasma`` sampled at ``linspace(0, 1, 17)``, sRGB. A perceptual map whose
#: low end stays visible on black, so dim context fibres are dark blue rather than gone.
#: Regenerate: ``colormaps["plasma"](np.linspace(0, 1, 17))[:, :3].round(4)``.
PLASMA_SRGB = (
    (0.0504, 0.0298, 0.528),
    (0.1934, 0.0184, 0.5903),
    (0.2999, 0.0096, 0.6316),
    (0.3994, 0.0009, 0.6561),
    (0.4949, 0.012, 0.6579),
    (0.5844, 0.0686, 0.6328),
    (0.6651, 0.1386, 0.5856),
    (0.736, 0.2094, 0.5279),
    (0.7982, 0.2802, 0.4695),
    (0.8533, 0.3516, 0.4137),
    (0.9018, 0.4251, 0.3597),
    (0.9426, 0.5026, 0.3058),
    (0.9734, 0.5858, 0.2515),
    (0.9914, 0.6754, 0.1985),
    (0.993, 0.7717, 0.1548),
    (0.9744, 0.8746, 0.1441),
    (0.94, 0.9752, 0.1313),
)

#: metric -> (label, units). Every entry is a field descriptor, not an activation prediction.
METRICS = {
    "ti_along": ("TI envelope along the fibre", "V/m"),
    "ti_max": ("TI_max at the fibre", "V/m"),
    "ti_ratio": ("ti_along / ti_max", "1"),
    "direction": ("Fibre direction (|x| R, |y| G, |z| B)", ""),
}


@dataclass
class Tracts:
    """Concatenated streamlines: streamline ``i`` is ``points[offsets[i]:offsets[i + 1]]``."""

    points: np.ndarray  # (V, 3) float32, world RAS mm
    offsets: np.ndarray  # (S + 1,) int64
    dpv: dict[str, np.ndarray]  # name -> (V,)
    dps: dict[str, np.ndarray]  # name -> (S,)

    @property
    def n(self) -> int:
        return len(self.offsets) - 1

    @property
    def lengths(self) -> np.ndarray:
        return np.diff(self.offsets)

    def streamline_id(self) -> np.ndarray:
        """(V,) index of the streamline each vertex belongs to."""
        return np.repeat(np.arange(self.n), self.lengths)


def _trx_entries(path: str) -> dict[str, bytes]:
    if os.path.isdir(path):
        return {
            os.path.relpath(os.path.join(d, f), path)
            .replace(os.sep, "/"): open(os.path.join(d, f), "rb")
            .read()
            for d, _dirs, files in os.walk(path)
            for f in files
        }
    with zipfile.ZipFile(path) as archive:
        return {
            i.filename: archive.read(i) for i in archive.infolist() if not i.is_dir()
        }


def _trx_array(name: str, payload: bytes) -> tuple[str, np.ndarray]:
    """``("dpv/ti_along", array)`` from ``dpv/ti_along.float32`` and its bytes."""
    stem, _, dtype = name.rpartition(".")
    columns = 1
    head, _, last = stem.rpartition(".")
    if head and last.isdigit():
        stem, columns = head, int(last)
    array = np.frombuffer(payload, dtype=np.dtype(dtype).newbyteorder("<"))
    return stem, array.reshape(-1, columns)


def load_trx(path: str) -> Tracts:
    """Read a ``.trx`` (zip or directory) into memory: positions, offsets, dpv/ and dps/."""
    entries = _trx_entries(path)
    header = json.loads(entries.pop("header.json"))
    arrays = dict(_trx_array(n, b) for n, b in entries.items() if n.count("/") <= 1)
    points = arrays["positions"].astype(np.float32)
    n_streamlines = int(header["NB_STREAMLINES"])
    offsets = arrays["offsets"][:, 0].astype(np.int64)
    if len(offsets) == n_streamlines:  # older writers omit the closing NB_VERTICES
        offsets = np.append(offsets, len(points))
    if len(points) != header["NB_VERTICES"] or len(offsets) != n_streamlines + 1:
        raise ValueError(f"{path}: positions/offsets disagree with header.json")
    dpv = {
        k[4:]: v[:, 0].astype(np.float32)
        for k, v in arrays.items()
        if k.startswith("dpv/")
    }
    dps = {k[4:]: v[:, 0].copy() for k, v in arrays.items() if k.startswith("dps/")}
    return drop_degenerate(Tracts(points, offsets, dpv, dps))


def drop_degenerate(tracts: Tracts) -> Tracts:
    """Remove streamlines with fewer than two points (no tangent, no tube)."""
    keep = np.flatnonzero(tracts.lengths >= 2)
    return tracts if len(keep) == tracts.n else select(tracts, keep)


def select(tracts: Tracts, index: np.ndarray) -> Tracts:
    """The streamlines *index* (in that order), with their per-vertex data."""
    index = np.asarray(index, dtype=np.int64)
    lengths = tracts.lengths[index]
    starts = tracts.offsets[:-1][index]
    vertex = np.repeat(starts - np.r_[0, np.cumsum(lengths)[:-1]], lengths) + np.arange(
        lengths.sum()
    )
    return Tracts(
        tracts.points[vertex],
        np.r_[0, np.cumsum(lengths)].astype(np.int64),
        {k: v[vertex] for k, v in tracts.dpv.items()},
        {k: v[index] for k, v in tracts.dps.items()},
    )


def subsample(
    weight: np.ndarray, k: int, seed: int = 0, floor: float = 0.1
) -> np.ndarray:
    """Up to *k* streamline indices, drawn without replacement with odds rising with *weight*.

    Each streamline's odds are ``floor + weight / max(weight)``, so the high-field fibres are
    nearly always kept and the rest still contributes context (weighted reservoir sampling,
    Efraimidis & Spirakis 2006: the *k* largest ``log(u) / w``). Returned sorted.
    """
    weight = np.nan_to_num(np.asarray(weight, dtype=np.float64), nan=0.0)
    if len(weight) <= k:
        return np.arange(len(weight))
    top = weight.max()
    w = floor + (weight / top if top > 0 else 0.0)
    keys = np.log(np.random.default_rng(seed).random(len(weight))) / w
    return np.sort(np.argpartition(-keys, k)[:k])


def arc_length(tracts: Tracts) -> np.ndarray:
    """(V,) distance in mm from each streamline's first point, along the streamline."""
    step = np.zeros(len(tracts.points))
    step[1:] = np.linalg.norm(np.diff(tracts.points.astype(np.float64), axis=0), axis=1)
    step[tracts.offsets[:-1]] = 0.0
    total = np.cumsum(step)
    return total - np.repeat(total[tracts.offsets[:-1]], tracts.lengths)


def decimate(tracts: Tracts, step_mm: float) -> Tracts:
    """Keep about one point per *step_mm* of arc (and both ends of every streamline)."""
    s = arc_length(tracts)
    bucket = np.floor(s / step_mm)
    keep = np.r_[True, bucket[1:] != bucket[:-1]]
    keep[tracts.offsets[:-1]] = True
    keep[tracts.offsets[1:] - 1] = True
    counts = np.add.reduceat(keep.astype(np.int64), tracts.offsets[:-1])
    return Tracts(
        tracts.points[keep],
        np.r_[0, np.cumsum(counts)].astype(np.int64),
        {k: v[keep] for k, v in tracts.dpv.items()},
        dict(tracts.dps),
    )


def tangents(tracts: Tracts) -> np.ndarray:
    """(V, 3) unit tangents: central differences inside, one-sided at the two ends."""
    p = tracts.points.astype(np.float64)
    nxt = np.minimum(
        np.arange(len(p)) + 1, np.repeat(tracts.offsets[1:] - 1, tracts.lengths)
    )
    prv = np.maximum(
        np.arange(len(p)) - 1, np.repeat(tracts.offsets[:-1], tracts.lengths)
    )
    t = p[nxt] - p[prv]
    return t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)


def vertex_metric(tracts: Tracts, metric: str) -> np.ndarray:
    """(V,) the scalar a metric colours by, in its own units (``direction`` has none)."""
    if metric == "ti_ratio":
        along, peak = tracts.dpv["ti_along"], tracts.dpv["ti_max"]
        return np.divide(along, peak, out=np.zeros_like(along), where=peak > 0)
    if metric in ("ti_along", "ti_max"):
        return tracts.dpv[metric]
    raise ValueError(
        f"unknown scalar metric {metric!r}; choose one of {sorted(METRICS)}"
    )


#: Display smoothing of the colour along each fibre, in mm. Real ti_along jitters ~28 % per 1 mm
#: step from tangent noise (sub-CHN left_insula_mean: median |step change| 0.025 of 0.089 V/m,
#: ti_max 0.006 of 0.31), which renders as speckle instead of a fibre.
SMOOTH_MM = 3.0


def smooth_along(
    tracts: Tracts, values: np.ndarray, half_width_mm: float = SMOOTH_MM
) -> np.ndarray:
    """*values* averaged along each streamline (two box passes of +-*half_width_mm*).

    Windows stop at streamline ends, so no value leaks from one streamline into the next.
    """
    sid = tracts.streamline_id()
    step = np.linalg.norm(np.diff(tracts.points, axis=0), axis=1)[np.diff(sid) == 0]
    w = int(round(half_width_mm / float(np.median(step)))) if step.size else 0
    if w < 1:
        return np.asarray(values, dtype=np.float32)
    i = np.arange(len(sid))
    lo = np.maximum(i - w, tracts.offsets[:-1][sid])
    hi = np.minimum(i + w, tracts.offsets[1:][sid] - 1)
    out = np.asarray(values, dtype=np.float64)
    for _ in range(2):
        total = np.r_[0.0, np.cumsum(out)]
        out = (total[hi + 1] - total[lo]) / (hi - lo + 1)
    return out.astype(np.float32)


def peak_vertex(tracts: Tracts, values: np.ndarray) -> np.ndarray:
    """(S,) global vertex index of each streamline's maximum of *values* (first on a tie)."""
    order = np.lexsort((-np.asarray(values), tracts.streamline_id()))
    return order[tracts.offsets[:-1]]


def robust_max(values: np.ndarray, q: float = 99.5) -> float:
    """The *q*-th percentile of the finite values, so one outlier does not wash out the map."""
    finite = np.asarray(values)[np.isfinite(values)]
    top = float(np.percentile(finite, q)) if finite.size else 0.0
    return top if top > 0 else 1.0


def colormap(v: np.ndarray) -> np.ndarray:
    """(..., 3) sRGB of :data:`PLASMA_SRGB` at *v* in [0, 1] (clipped), linearly interpolated."""
    stops = np.asarray(PLASMA_SRGB)
    x = np.linspace(0.0, 1.0, len(stops))
    v = np.clip(np.asarray(v, dtype=np.float64), 0.0, 1.0)
    return np.stack([np.interp(v, x, stops[:, c]) for c in range(3)], axis=-1)


def read_edges(path: str) -> dict[int, dict]:
    """``edges.json`` as ``{edge_id: record}``; ``{}`` when the file is absent."""
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as stream:
        data = json.load(stream)
    if isinstance(data, list):  # a list of records carrying their own edge_id
        return {int(r["edge_id"]): r for r in data}
    return {int(k): v for k, v in data.items()}


def edge_name(record: dict) -> str:
    """``"region_a – region_b"`` for an ``edges.json`` record."""
    return f"{record.get('region_a', '?')} – {record.get('region_b', '?')}"


def read_connectome(path: str) -> tuple[np.ndarray, list[str]]:
    """``(matrix, labels)`` from ``connectome_<metric>.npz``."""
    with np.load(path, allow_pickle=False) as data:
        matrix = np.asarray(data["matrix"], dtype=np.float64)
        labels = [str(x) for x in data["labels"]]
    if matrix.shape != (len(labels), len(labels)):
        raise ValueError(
            f"{path}: matrix {matrix.shape} does not match {len(labels)} labels"
        )
    return matrix, labels
