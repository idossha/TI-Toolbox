#!/usr/bin/env simnibs_python
"""Neuron-model registry for microscale coupling.

The default model is an **authored, self-contained ball-and-stick cortical
neuron** built procedurally with NEURON's built-in ``hh`` (active Hodgkin-Huxley
channels) and ``extracellular`` mechanisms.  It needs no vendored assets and no
``.mod`` compilation, so it carries no third-party license.

Why not ship realistic Blue Brain / Aberra morphologies?  The widely-used
realistic cortical cells (e.g. the Goswami/Caldas-Martinez TI repo) are licensed
**CC-BY-NC-SA** (non-commercial, share-alike) and therefore cannot be vendored
into this toolbox.  Users who have obtained such cells under their own terms can
register them via :func:`register_model` (see the module docstring of
:mod:`tit.microscale.coupling`).

NEURON is imported lazily inside the builders so importing this module (e.g. to
read the registry) does not require NEURON to be installed.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from tit.microscale.config import NeuronModelSpec

#: Registry of model name -> (spec, builder).  Builders return a :class:`Cell`.
_REGISTRY: dict[str, tuple[NeuronModelSpec, Callable[[], "Cell"]]] = {}


class Cell:
    """A built multicompartment neuron with 3D segment geometry.

    Wraps the NEURON sections and exposes the geometry and the per-segment
    ``e_extracellular`` references the coupling layer needs.

    Attributes
    ----------
    sections : list
        NEURON ``Section`` objects, soma first.
    soma : NEURON Section
        The somatic section (spike-detection site).
    name : str
        Registry key the cell was built from.
    """

    def __init__(self, sections: list, soma, name: str, kinds=None) -> None:
        self.sections = sections
        self.soma = soma
        self.name = name
        self._kinds = kinds or {}  # section-name -> region tag (for rendering)
        self._played = []  # keep Vector/refs alive for the run's lifetime

    def segments(self):
        """Yield ``(section, segment)`` for every segment, soma first."""
        for sec in self.sections:
            for seg in sec:
                yield sec, seg

    def segment_coords_um(self) -> np.ndarray:
        """Centre coordinate (um) of every segment, in section/segment order."""
        coords = []
        for sec in self.sections:
            coords.extend(_section_segment_centers(sec))
        return np.asarray(coords, dtype=float)

    def soma_coord_um(self) -> np.ndarray:
        """Centre coordinate (um) of the soma's middle segment."""
        centers = _section_segment_centers(self.soma)
        return np.asarray(centers[len(centers) // 2], dtype=float)

    def section_spans(self) -> list:
        """Per-section grouping for rendering.

        Returns a list of ``(name, kind, diam_um, start, count)`` aligned with
        the segment order of :meth:`segment_coords_um` / :meth:`segments`, where
        *kind* is a coarse label (``"soma"``/``"dendrite"``/``"axon"``/
        ``"other"``) derived from the section name.

        Returns
        -------
        list of tuple
        """
        spans = []
        start = 0
        for sec in self.sections:
            n = sec.nseg
            name = sec.name().split(".")[-1]
            if name in self._kinds:
                kind = self._kinds[name]
            elif "soma" in name:
                kind = "soma"
            elif "apic" in name or "tuft" in name:
                kind = "apical"
            elif "basal" in name or "dend" in name:
                kind = "basal"
            elif "node" in name:
                kind = "node"
            elif "ais" in name:
                kind = "ais"
            elif "axon" in name:
                kind = "axon"
            else:
                kind = "other"
            spans.append((name, kind, float(sec.diam), start, n))
            start += n
        return spans


def register_model(spec: NeuronModelSpec, builder: Callable[[], Cell]) -> None:
    """Register a model builder under ``spec.name``."""
    _REGISTRY[spec.name] = (spec, builder)


def get_spec(name: str) -> NeuronModelSpec:
    """Return the :class:`NeuronModelSpec` registered under *name*."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown model {name!r}; registered: {list(_REGISTRY)}")
    return _REGISTRY[name][0]


def list_models() -> list[str]:
    """List registered model names."""
    return list(_REGISTRY)


def build_cell(name: str) -> Cell:
    """Build and return the :class:`Cell` registered under *name*."""
    if name not in _REGISTRY:
        raise KeyError(f"Unknown model {name!r}; registered: {list(_REGISTRY)}")
    return _REGISTRY[name][1]()


# ---------------------------------------------------------------------------
# Geometry helper (pure, NEURON-light)
# ---------------------------------------------------------------------------


def _section_segment_centers(sec) -> list:
    """Compute 3D centres (um) of each segment of *sec* from its pt3d data.

    Interpolates the section's 3D points by arc length at each segment's
    normalized centre ``seg.x``.  Falls back to a straight section if pt3d is
    absent.
    """
    n3d = int(sec.n3d())
    if n3d < 2:
        # No 3D info: degenerate; return the origin per segment.
        return [(0.0, 0.0, 0.0) for _ in sec]
    pts = np.array([[sec.x3d(i), sec.y3d(i), sec.z3d(i)] for i in range(n3d)])
    arc = np.array([sec.arc3d(i) for i in range(n3d)])
    total = arc[-1] if arc[-1] > 0 else 1.0
    arc_norm = arc / total
    centers = []
    for seg in sec:
        x = seg.x
        # Linear interpolation of the 3D polyline at normalized position x.
        j = int(np.searchsorted(arc_norm, x))
        j = max(1, min(j, n3d - 1))
        x0, x1 = arc_norm[j - 1], arc_norm[j]
        t = 0.0 if x1 == x0 else (x - x0) / (x1 - x0)
        centers.append(tuple(pts[j - 1] + t * (pts[j] - pts[j - 1])))
    return centers


# ---------------------------------------------------------------------------
# Default authored model: ball-and-stick with active channels
# ---------------------------------------------------------------------------

BALL_STICK_SPEC = NeuronModelSpec(
    name="ball_stick",
    description=(
        "Authored ball-and-stick cortical neuron: soma + apical dendrite + "
        "axon, built along local +z with NEURON built-in hh (active) and "
        "extracellular mechanisms. No vendored assets."
    ),
    morphology="",  # procedural
    mechanisms=(),  # built-in hh/extracellular only
    has_active_channels=True,
    license="",  # authored in-repo, no third-party license
)


def _build_ball_stick() -> Cell:
    """Build the default ball-and-stick cell along local +z (apical up).

    Soma at the origin; apical dendrite extends +z; axon extends -z.  All
    sections carry ``hh`` and ``extracellular``.
    """
    from neuron import h

    h.load_file("stdrun.hoc")

    soma = h.Section(name="soma")
    apic = h.Section(name="apic")
    axon = h.Section(name="axon")

    # Geometry (um). Soma centred at origin; apical up (+z), axon down (-z).
    # Lengths are explicit constants: the section .L is derived from the pt3d
    # points below, so we must NOT read sec.L between pt3dclear() (which zeros
    # it) and the second pt3dadd() — doing so collapses the section to ~0 length.
    soma_half = 10.0
    apic_len = 600.0
    axon_len = 400.0
    soma_d, apic_d, axon_d = 20.0, 2.0, 1.0

    soma.pt3dclear()
    soma.pt3dadd(0.0, 0.0, -soma_half, soma_d)
    soma.pt3dadd(0.0, 0.0, soma_half, soma_d)

    apic.pt3dclear()
    apic.pt3dadd(0.0, 0.0, soma_half, apic_d)
    apic.pt3dadd(0.0, 0.0, soma_half + apic_len, apic_d)

    axon.pt3dclear()
    axon.pt3dadd(0.0, 0.0, -soma_half, axon_d)
    axon.pt3dadd(0.0, 0.0, -soma_half - axon_len, axon_d)

    apic.nseg, axon.nseg = 21, 21
    apic.connect(soma(1.0))
    axon.connect(soma(0.0))

    for sec in (soma, apic, axon):
        sec.insert("hh")
        sec.insert("extracellular")

    return Cell([soma, apic, axon], soma, "ball_stick")


register_model(BALL_STICK_SPEC, _build_ball_stick)


# ---------------------------------------------------------------------------
# Spec-based builder: procedural branched L5 pyramidal + SWC-loaded cells
# ---------------------------------------------------------------------------


def build_from_spec(morph, name: str) -> Cell:
    """Build a NEURON :class:`Cell` from a :class:`MorphologySpec`.

    Creates one NEURON section per :class:`~tit.microscale.morphology.SectionSpec`
    (pt3d geometry, connected to its parent), assigns ``nseg`` by length, and
    inserts ``hh`` + ``extracellular`` on every section.  The region tags are
    carried through to :meth:`Cell.section_spans` for rendering.
    """
    from neuron import h

    h.load_file("stdrun.hoc")
    secs = {}
    kinds = {}
    for sp in morph.sections:
        sec = h.Section(name=sp.name)
        sec.pt3dclear()
        for x, y, z, d in sp.points:
            sec.pt3dadd(float(x), float(y), float(z), float(d))
        # ~1 compartment per 25 um, odd, capped.
        length = max(sec.L, 1.0)
        sec.nseg = int(min(101, max(1, (length // 25) * 2 + 1)))
        sec.insert("hh")
        sec.insert("extracellular")
        secs[sp.name] = sec
        kinds[sp.name] = sp.kind
    # connect children to parents (parents created first in spec order)
    for sp in morph.sections:
        if sp.parent is not None and sp.parent in secs:
            secs[sp.name].connect(secs[sp.parent](sp.parent_end))

    ordered = [secs[sp.name] for sp in morph.sections]
    soma = secs.get(morph.soma_name, ordered[0])
    return Cell(ordered, soma, name, kinds=kinds)


L5_SPEC = NeuronModelSpec(
    name="l5_pyramidal",
    description=(
        "Procedurally generated branched layer-5 pyramidal neuron: soma, "
        "branched basal dendrites, apical trunk + tuft, axon initial segment + "
        "myelinated axon with nodes of Ranvier. Built-in hh + extracellular; "
        "license-free. Renders like a real reconstruction."
    ),
    morphology="procedural",
    mechanisms=(),
    has_active_channels=True,
    license="",
)


def _build_l5_pyramidal() -> Cell:
    from tit.microscale.morphology import pyramidal_l5

    return build_from_spec(pyramidal_l5(seed=0), "l5_pyramidal")


register_model(L5_SPEC, _build_l5_pyramidal)


def load_swc_cell(path: str, name: str | None = None) -> Cell:
    """Build a :class:`Cell` from an SWC reconstruction file.

    Use for realistic morphologies (e.g. NeuroMorpho.org, or Aberra/Blue Brain
    exports).  The returned cell renders and couples exactly like the built-in
    models.

    Parameters
    ----------
    path : str
        Path to an ``.swc`` file.
    name : str, optional
        Cell name (defaults to the file stem).

    Returns
    -------
    Cell
    """
    import os

    from tit.microscale.morphology import load_swc

    name = name or os.path.splitext(os.path.basename(path))[0]
    return build_from_spec(load_swc(path), name)
