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

    def __init__(self, sections: list, soma, name: str) -> None:
        self.sections = sections
        self.soma = soma
        self.name = name
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
    soma.L, soma.diam = 20.0, 20.0
    apic.L, apic.diam = 600.0, 2.0
    axon.L, axon.diam = 400.0, 1.0
    apic.nseg, axon.nseg = 21, 21

    soma.pt3dclear()
    soma.pt3dadd(0.0, 0.0, -10.0, soma.diam)
    soma.pt3dadd(0.0, 0.0, 10.0, soma.diam)

    apic.pt3dclear()
    apic.pt3dadd(0.0, 0.0, 10.0, apic.diam)
    apic.pt3dadd(0.0, 0.0, 10.0 + apic.L, apic.diam)

    axon.pt3dclear()
    axon.pt3dadd(0.0, 0.0, -10.0, axon.diam)
    axon.pt3dadd(0.0, 0.0, -10.0 - axon.L, axon.diam)

    apic.connect(soma(1.0))
    axon.connect(soma(0.0))

    for sec in (soma, apic, axon):
        sec.insert("hh")
        sec.insert("extracellular")

    return Cell([soma, apic, axon], soma, "ball_stick")


register_model(BALL_STICK_SPEC, _build_ball_stick)
