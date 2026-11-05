"""Streamline data for the tract renders: TRX in, plain numpy arrays out.

The tract visuals (Blender stills and animations, the web viewer, the connectome figure) all
read a ``tit.tract`` output directory through this module, so the data contract lives in one
place:

``<bundle_or_all>.trx``
    streamlines in m2m world RAS mm, ``data_per_vertex`` ``ti_along``, ``ti_max``, ``ti_avg``,
    ``e1_par``, ``e2_par`` (V/m; ``e<c>_par`` signed region_a -> region_b) and
    ``data_per_streamline`` ``length_mm``, ``ti_along_max``, ``ti_along_mean``, ``edge_id``
    (-1 unassigned).
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

#: matplotlib 3.10.8 ``coolwarm`` at ``linspace(0, 1, 17)``, sRGB: the diverging map of
#: ``align_index`` (blue across the field, neutral grey at 1, warm along it).
COOLWARM_SRGB = (
    (0.2298, 0.2987, 0.7537),
    (0.3042, 0.4069, 0.8453),
    (0.3837, 0.5102, 0.9178),
    (0.4677, 0.6056, 0.9685),
    (0.5543, 0.6901, 0.9955),
    (0.6408, 0.7608, 0.9978),
    (0.724, 0.8149, 0.9757),
    (0.8006, 0.8504, 0.93),
    (0.8674, 0.8644, 0.8626),
    (0.9256, 0.8255, 0.7711),
    (0.9595, 0.767, 0.6741),
    (0.9697, 0.6905, 0.5751),
    (0.9567, 0.598, 0.4773),
    (0.9214, 0.4914, 0.3834),
    (0.8654, 0.3711, 0.2958),
    (0.7906, 0.2314, 0.2162),
    (0.7057, 0.0156, 0.1502),
)

#: The align_index colour window: log2 ratio in [-ALIGN_OCTAVES, +ALIGN_OCTAVES], 1 at the centre.
ALIGN_OCTAVES = 1.0

#: metric -> (label, units). Every entry is a field descriptor, not an activation prediction.
METRICS = {
    "ti_along": ("TI envelope along the fibre", "V/m"),
    "ti_max": ("TI_max at the fibre", "V/m"),
    "ti_ratio": ("ti_along / ti_max", "1"),
    "align_index": ("Field along fibre ÷ random-direction baseline", "1"),
    "direction": ("Fibre direction (|x| R, |y| G, |z| B)", ""),
}

#: Metrics drawn on the diverging map, centred at 1.
DIVERGING = frozenset({"align_index"})


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


def read_dps(path: str, key: str) -> np.ndarray | None:
    """One ``data_per_streamline`` array of a zipped TRX, without reading the rest of it."""
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith(f"dps/{key}."):
                return _trx_array(name, archive.read(name))[1].ravel()
    return None


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


def concat(parts: list[Tracts]) -> Tracts:
    """One Tracts of *parts* in order; data keys are those every part has."""
    dpv_keys = set.intersection(*(set(p.dpv) for p in parts))
    dps_keys = set.intersection(*(set(p.dps) for p in parts))
    lengths = np.concatenate([p.lengths for p in parts])
    return Tracts(
        np.concatenate([p.points for p in parts]),
        np.r_[0, np.cumsum(lengths)].astype(np.int64),
        {k: np.concatenate([p.dpv[k] for p in parts]) for k in dpv_keys},
        {k: np.concatenate([p.dps[k] for p in parts]) for k in dps_keys},
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


def arc_length_mean(tracts: Tracts, values: np.ndarray) -> np.ndarray:
    """Per-streamline trapezoid mean of *values*: the ``mean`` the assess stage reports.

    Assessed streamlines are evenly spaced, so inner points weigh 1 and the two ends 1/2; a plain
    point mean weighs the ends in full and differs from assess in the third decimal.
    """
    values = np.asarray(values, dtype=np.float64)
    first, last = tracts.offsets[:-1], tracts.offsets[1:] - 1
    total = np.add.reduceat(values, first) - 0.5 * (values[first] + values[last])
    return total / (tracts.lengths - 1)


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
    """(V,) the scalar a metric colours by, in its own units (``direction`` has none).

    ``align_index`` is ``ti_along / ti_avg`` (``ti_avg``: the envelope along a uniformly random
    direction), so 1 means as much field along the fibre as a random direction would see.
    """
    if metric == "align_index":
        along, avg = tracts.dpv["ti_along"], tracts.dpv["ti_avg"]
        return np.divide(along, avg, out=np.ones_like(along), where=avg > 0)
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


def display_metric(tracts: Tracts, metric: str) -> np.ndarray:
    """(V,) *metric* as drawn: averaged along each fibre (:data:`SMOOTH_MM`).

    A ratio is the ratio of the averaged numerator and denominator, as the tract pipeline's
    streamline ``align_index`` is a ratio of arc-length means.
    """
    if metric in ("align_index", "ti_ratio"):
        top = smooth_along(tracts, tracts.dpv["ti_along"])
        key = "ti_avg" if metric == "align_index" else "ti_max"
        bottom = smooth_along(tracts, tracts.dpv[key])
        default = 1.0 if metric == "align_index" else 0.0
        return np.divide(top, bottom, out=np.full_like(top, default), where=bottom > 0)
    return smooth_along(tracts, vertex_metric(tracts, metric))


def colour_position(values: np.ndarray, metric: str, vmax: float) -> np.ndarray:
    """Values -> [0, 1] along the colour map: linear to *vmax*, or log2 about 1 (diverging)."""
    values = np.asarray(values, dtype=np.float64)
    if metric in DIVERGING:
        octaves = np.log2(np.maximum(values, 1e-6)) / ALIGN_OCTAVES
        return np.clip(0.5 + 0.5 * octaves, 0.0, 1.0).astype(np.float32)
    return np.clip(values / vmax, 0.0, 1.0).astype(np.float32)


def peak_vertex(tracts: Tracts, values: np.ndarray) -> np.ndarray:
    """(S,) global vertex index of each streamline's maximum of *values* (first on a tie)."""
    order = np.lexsort((-np.asarray(values), tracts.streamline_id()))
    return order[tracts.offsets[:-1]]


def robust_max(values: np.ndarray, q: float = 99.5) -> float:
    """The *q*-th percentile of the finite values, so one outlier does not wash out the map."""
    finite = np.asarray(values)[np.isfinite(values)]
    top = float(np.percentile(finite, q)) if finite.size else 0.0
    return top if top > 0 else 1.0


def colormap(v: np.ndarray, stops=PLASMA_SRGB) -> np.ndarray:
    """(..., 3) sRGB of *stops* at *v* in [0, 1] (clipped), linearly interpolated."""
    stops = np.asarray(stops)
    x = np.linspace(0.0, 1.0, len(stops))
    v = np.clip(np.asarray(v, dtype=np.float64), 0.0, 1.0)
    return np.stack([np.interp(v, x, stops[:, c]) for c in range(3)], axis=-1)


def stops_for(metric: str):
    """The colour stops *metric* is drawn with."""
    return COOLWARM_SRGB if metric in DIVERGING else PLASMA_SRGB


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
