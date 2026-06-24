#!/usr/bin/env simnibs_python
"""Neuron morphology generation and loading (NEURON-free, pure geometry).

Produces :class:`MorphologySpec` objects -- a list of :class:`SectionSpec`
(named, region-tagged polylines with per-point diameters and a parent link) that
:mod:`tit.microscale.models` turns into NEURON sections, and that
:mod:`tit.microscale.viz` renders.

Two sources:

* :func:`pyramidal_l5` -- a procedurally generated, license-free branched layer-5
  pyramidal cell (soma, branched basal dendrites, apical trunk + tuft, an axon
  initial segment + myelinated axon with nodes of Ranvier).  Deterministic given
  a seed.  This is the default model and renders like a real reconstruction
  (cf. Shirinpour et al. 2021, Fig. 2D).
* :func:`load_swc` -- parse a standard SWC reconstruction (e.g. from
  NeuroMorpho.org or an Aberra/Blue Brain export) into a :class:`MorphologySpec`.

Region tags (used for coloring): ``soma``, ``basal``, ``apical``, ``tuft``,
``ais``, ``axon``, ``node``.  All coordinates and diameters are micrometres.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class SectionSpec:
    """One unbranched neurite section.

    Attributes
    ----------
    name : str
        Unique section name.
    kind : str
        Region tag (soma/basal/apical/tuft/ais/axon/node).
    points : list of (x, y, z, diam)
        Polyline points in um (diam is the local diameter in um).
    parent : str or None
        Name of the parent section (None for the root/soma).
    parent_end : float
        Location on the parent (0 or 1) where this section attaches.
    """

    name: str
    kind: str
    points: list
    parent: str | None = None
    parent_end: float = 1.0


@dataclass
class MorphologySpec:
    """A whole-cell morphology: ordered sections, soma first."""

    sections: list = field(default_factory=list)
    soma_name: str = "soma"

    def by_name(self, name: str) -> SectionSpec:
        for s in self.sections:
            if s.name == name:
                return s
        raise KeyError(name)


# ---------------------------------------------------------------------------
# Procedural layer-5 pyramidal cell
# ---------------------------------------------------------------------------


def _unit(v):
    n = math.sqrt(sum(c * c for c in v))
    return [c / n for c in v] if n else v


def _add(a, b):
    return [a[i] + b[i] for i in range(3)]


def _scale(v, s):
    return [c * s for c in v]


def _rotate_jitter(direction, rng, spread_deg):
    """Perturb a 3D direction by a random angle up to spread_deg."""
    d = _unit(direction)
    # random small vector, project out the parallel component
    r = [rng.gauss(0, 1) for _ in range(3)]
    perp = [r[i] - sum(r[k] * d[k] for k in range(3)) * d[i] for i in range(3)]
    perp = _unit(perp)
    ang = math.radians(rng.uniform(0, spread_deg))
    return _unit([math.cos(ang) * d[i] + math.sin(ang) * perp[i] for i in range(3)])


def _grow_branch(
    spec, name, kind, start, direction, length, d0, d1, parent, parent_end, n_pts=6
):
    """Append a tapered straight-ish branch and return its end point + name."""
    pts = []
    direction = _unit(direction)
    for k in range(n_pts + 1):
        f = k / n_pts
        p = _add(start, _scale(direction, length * f))
        pts.append([p[0], p[1], p[2], d0 + (d1 - d0) * f])
    spec.sections.append(
        SectionSpec(name, kind, pts, parent=parent, parent_end=parent_end)
    )
    return pts[-1][:3], name


def pyramidal_l5(seed: int = 0) -> MorphologySpec:
    """Procedurally generate a branched layer-5 pyramidal morphology (um).

    Deterministic given *seed*.  Apical trunk along +z, basal dendrites and axon
    descending.  Returns a :class:`MorphologySpec`.
    """
    rng = random.Random(seed)
    spec = MorphologySpec()
    soma_h = 12.0

    # Soma (vertical spheroid approximated by 2 points).
    spec.sections.append(
        SectionSpec(
            "soma",
            "soma",
            [[0, 0, -soma_h / 2, 22.0], [0, 0, soma_h / 2, 22.0]],
            parent=None,
        )
    )
    top = [0, 0, soma_h / 2]
    bot = [0, 0, -soma_h / 2]

    # Apical trunk (proximal + distal segments for a taper + color gradient).
    _, _ = _grow_branch(
        spec,
        "apic_prox",
        "apical",
        top,
        [0, 0, 1],
        320.0,
        4.0,
        2.6,
        "soma",
        1.0,
        n_pts=8,
    )
    trunk_mid = spec.by_name("apic_prox").points[-1][:3]
    _, _ = _grow_branch(
        spec,
        "apic_dist",
        "apical",
        trunk_mid,
        [0, 0, 1],
        300.0,
        2.6,
        1.6,
        "apic_prox",
        1.0,
        n_pts=8,
    )
    tuft_origin = spec.by_name("apic_dist").points[-1][:3]

    # Apical tuft: 5 branches splaying upward/outward, each bifurcating once.
    for i in range(5):
        az = 2 * math.pi * i / 5 + rng.uniform(-0.3, 0.3)
        out = [0.5 * math.cos(az), 0.5 * math.sin(az), 1.0]
        end, nm = _grow_branch(
            spec,
            f"tuft{i}",
            "tuft",
            tuft_origin,
            _rotate_jitter(out, rng, 25),
            140.0,
            1.4,
            0.8,
            "apic_dist",
            1.0,
            n_pts=5,
        )
        for j in range(2):
            d2 = _rotate_jitter(out, rng, 40)
            _grow_branch(
                spec, f"tuft{i}_{j}", "tuft", end, d2, 90.0, 0.8, 0.4, nm, 1.0, n_pts=4
            )

    # Basal dendrites: 6 branches from the soma base, down-and-out, bifurcating.
    for i in range(6):
        az = 2 * math.pi * i / 6 + rng.uniform(-0.2, 0.2)
        out = [math.cos(az), math.sin(az), -0.45]
        end, nm = _grow_branch(
            spec,
            f"basal{i}",
            "basal",
            bot,
            _rotate_jitter(out, rng, 20),
            190.0,
            1.8,
            0.9,
            "soma",
            0.0,
            n_pts=6,
        )
        for j in range(2):
            d2 = _rotate_jitter(out, rng, 45)
            _grow_branch(
                spec,
                f"basal{i}_{j}",
                "basal",
                end,
                d2,
                120.0,
                0.9,
                0.4,
                nm,
                1.0,
                n_pts=4,
            )

    # Axon initial segment (AIS) then a myelinated axon with nodes of Ranvier.
    ais_end, _ = _grow_branch(
        spec, "ais", "ais", bot, [0, 0, -1], 30.0, 1.4, 1.0, "soma", 0.0, n_pts=3
    )
    prev = "ais"
    node_xyz = ais_end
    for k in range(6):
        # internode (myelinated)
        end, nm = _grow_branch(
            spec,
            f"axon{k}",
            "axon",
            node_xyz,
            [0, 0, -1],
            100.0,
            1.0,
            1.0,
            prev,
            1.0,
            n_pts=3,
        )
        # node of Ranvier (short, highlighted)
        nend, nnm = _grow_branch(
            spec, f"node{k}", "node", end, [0, 0, -1], 3.0, 0.8, 0.8, nm, 1.0, n_pts=1
        )
        prev, node_xyz = nnm, nend
        if k == 2:  # one collateral branch for realism
            _grow_branch(
                spec,
                "axon_coll",
                "axon",
                end,
                _rotate_jitter([0.7, 0.3, -0.6], rng, 10),
                160.0,
                0.7,
                0.5,
                nm,
                1.0,
                n_pts=4,
            )
    return spec


# ---------------------------------------------------------------------------
# SWC loader
# ---------------------------------------------------------------------------

_SWC_KIND = {1: "soma", 2: "axon", 3: "basal", 4: "apical"}


def load_swc(path: str) -> MorphologySpec:
    """Parse an SWC reconstruction into a :class:`MorphologySpec`.

    Builds one section per maximal unbranched path (NeuroMorpho/CNIC convention).
    SWC type codes: 1=soma, 2=axon, 3=(basal) dendrite, 4=apical dendrite; other
    codes map to ``axon``.  Coordinates/radii are um (radius -> diameter).

    Parameters
    ----------
    path : str
        Path to an ``.swc`` file.

    Returns
    -------
    MorphologySpec
    """
    samples = {}
    order = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            sid = int(parts[0])
            t = int(parts[1])
            x, y, z, r = map(float, parts[2:6])
            parent = int(parts[6])
            samples[sid] = (t, x, y, z, 2.0 * r, parent)
            order.append(sid)

    # children map + branch/end detection
    children: dict[int, list] = {}
    for sid, (_t, _x, _y, _z, _d, parent) in samples.items():
        children.setdefault(parent, []).append(sid)

    spec = MorphologySpec()
    sec_of_sample: dict[int, str] = {}
    counter = [0]

    def emit_path(start_sid, parent_sec, parent_end):
        # walk until a branch point or terminal
        pts = []
        sid = start_sid
        t0 = samples[start_sid][0]
        while True:
            t, x, y, z, d, _p = samples[sid]
            pts.append([x, y, z, d])
            sec_of_sample[sid] = None  # placeholder
            kids = children.get(sid, [])
            if len(kids) != 1:
                break
            nxt = kids[0]
            if samples[nxt][0] != t0:  # type change -> new section
                break
            sid = nxt
        name = f"{_SWC_KIND.get(t0, 'axon')}{counter[0]}"
        counter[0] += 1
        kind = _SWC_KIND.get(t0, "axon")
        spec.sections.append(
            SectionSpec(name, kind, pts, parent=parent_sec, parent_end=parent_end)
        )
        for sid_ in range(start_sid, sid + 1):
            if sid_ in sec_of_sample:
                sec_of_sample[sid_] = name
        # recurse into the branch's children
        for kid in children.get(sid, []):
            emit_path(kid, name, 1.0)

    roots = children.get(-1, []) + children.get(0, [])
    for r in roots:
        emit_path(r, None, 1.0)
    if spec.sections:
        spec.soma_name = spec.sections[0].name
    return spec
