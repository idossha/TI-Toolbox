#!/usr/bin/env simnibs_python
"""Couple a sampled TI field to a NEURON cell and run it.

The coupling math (carrier superposition, spike counting) is factored into pure
NumPy functions so it is testable without NEURON; the actual cable solve
(:func:`simulate_response`, :func:`polarization_map`, :func:`find_threshold`)
imports ``neuron`` lazily.

Field -> e_extracellular (quasi-static, two-carrier)
----------------------------------------------------
For temporal interference the two electrode pairs each produce a field vector at
the target.  We build a per-segment quasipotential for each pair
(:func:`tit.microscale.field_sampler.uniform_quasipotential`) and drive each
segment's ``e_extracellular`` with the superposed carriers::

    V_e(seg, t) = A * [ Ve1(seg)·sin(2π f1 t) + Ve2(seg)·sin(2π f2 t) ]

The envelope demodulation is *not* imposed -- it emerges from the cell's active
channels (Mirzakhalili et al. 2020; Wang et al. 2022).

Registering custom (user-supplied) cells
-----------------------------------------
The realistic Blue Brain / Aberra cortical morphologies are CC-BY-NC-SA and are
not shipped.  A user who has them under their own terms can build a
:class:`~tit.microscale.models.Cell` and register it::

    from tit.microscale.models import register_model
    register_model(my_spec, my_builder)
"""

from __future__ import annotations

import numpy as np

from tit.microscale.field_sampler import (
    load_field,
    place_morphology,
    sample_at,
    uniform_quasipotential,
)
from tit.microscale.models import build_cell

# ---------------------------------------------------------------------------
# Pure coupling math (NEURON-free, unit tested)
# ---------------------------------------------------------------------------


def build_extracellular_timeseries(
    ve1: np.ndarray,
    ve2: np.ndarray,
    t_ms: np.ndarray,
    f1: float,
    f2: float,
    amplitude: float = 1.0,
) -> np.ndarray:
    """Per-segment extracellular potential time course (mV) for two carriers.

    Parameters
    ----------
    ve1, ve2 : ndarray, shape (M,)
        Per-segment quasipotential (mV) for pair 1 and pair 2 at unit carrier
        amplitude.
    t_ms : ndarray, shape (T,)
        Time samples in ms.
    f1, f2 : float
        Carrier frequencies in Hz.
    amplitude : float, optional
        Global amplitude multiplier.

    Returns
    -------
    ndarray, shape (M, T)
        ``V_e(seg, t)`` in mV.
    """
    ve1 = np.asarray(ve1, dtype=float).reshape(-1, 1)
    ve2 = np.asarray(ve2, dtype=float).reshape(-1, 1)
    t_s = np.asarray(t_ms, dtype=float).reshape(1, -1) / 1000.0
    s1 = np.sin(2.0 * np.pi * f1 * t_s)
    s2 = np.sin(2.0 * np.pi * f2 * t_s)
    return amplitude * (ve1 * s1 + ve2 * s2)


def count_spikes(v_soma: np.ndarray, threshold: float = 0.0) -> int:
    """Count upward threshold crossings (spikes) in a somatic voltage trace.

    Parameters
    ----------
    v_soma : ndarray, shape (T,)
        Somatic membrane potential (mV).
    threshold : float, optional
        Crossing threshold in mV.  Default 0 mV.

    Returns
    -------
    int
        Number of upward crossings.
    """
    v = np.asarray(v_soma, dtype=float)
    above = v >= threshold
    # Rising edges: was below, now at/above.
    crossings = np.logical_and(~above[:-1], above[1:])
    return int(np.count_nonzero(crossings))


# ---------------------------------------------------------------------------
# Field -> per-segment quasipotentials (uniform-field approximation)
# ---------------------------------------------------------------------------


def per_pair_quasipotentials(
    cell,
    target_mm: np.ndarray,
    normal: np.ndarray,
    mesh_pair1,
    mesh_pair2,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-segment quasipotentials (mV) for the two HF pair fields.

    Places the cell at *target_mm* oriented along *normal*, samples each pair's
    E-field at the soma (quasi-uniform approximation), and integrates it over
    the placed morphology.

    Returns
    -------
    tuple of ndarray
        ``(ve1, ve2)``, each shape ``(M,)`` in mV.
    """
    target_mm = np.asarray(target_mm, dtype=float).reshape(3)
    local_um = cell.segment_coords_um()
    soma_local_um = cell.soma_coord_um()
    target_um = target_mm * 1000.0
    world_um = place_morphology(local_um, soma_local_um, target_um, normal)

    e1 = np.asarray(sample_at(mesh_pair1, target_mm.reshape(1, 3))).reshape(3)
    e2 = np.asarray(sample_at(mesh_pair2, target_mm.reshape(1, 3))).reshape(3)
    ve1 = uniform_quasipotential(e1, world_um, target_um)
    ve2 = uniform_quasipotential(e2, world_um, target_um)
    return ve1, ve2


def _load_pair_meshes(subject_id: str, cfg) -> tuple:
    """Read the two HF pair meshes carrying per-pair ``E`` vectors."""
    import os

    from tit.paths import get_path_manager

    pm = get_path_manager()
    hf_dir = os.path.join(pm.simulation(subject_id, cfg.sim_name), "high_Frequency")
    cond = cfg.conductivity
    m1, _ = load_field(
        os.path.join(hf_dir, f"{subject_id}_TDCS_1_{cond}.msh"), field="E"
    )
    m2, _ = load_field(
        os.path.join(hf_dir, f"{subject_id}_TDCS_2_{cond}.msh"), field="E"
    )
    return m1, m2


# ---------------------------------------------------------------------------
# NEURON runs (lazy import)
# ---------------------------------------------------------------------------


def simulate_response(
    cfg,
    target_mm: np.ndarray,
    normal: np.ndarray,
    mesh_pair1,
    mesh_pair2,
) -> dict:
    """Drive a cell with the TI carriers and return its response.

    Returns
    -------
    dict
        ``{"n_spikes", "v_soma", "t", "ve1_max", "ve2_max"}``.
    """
    from neuron import h

    cell = build_cell(cfg.model)
    ve1, ve2 = per_pair_quasipotentials(cell, target_mm, normal, mesh_pair1, mesh_pair2)

    n_steps = int(round(cfg.duration / cfg.dt)) + 1
    t_ms = np.arange(n_steps) * cfg.dt
    f1, f2 = cfg.carrier_freqs
    ve_t = build_extracellular_timeseries(
        ve1, ve2, t_ms, f1, f2, amplitude=cfg.amplitude_scale
    )

    h.celsius = cfg.temperature
    h.dt = cfg.dt
    t_vec = h.Vector(t_ms)
    for i, (_sec, seg) in enumerate(cell.segments()):
        vec = h.Vector(ve_t[i])
        vec.play(seg._ref_e_extracellular, t_vec, 1)
        cell._played.append(vec)
    cell._played.append(t_vec)

    v_soma = h.Vector()
    v_soma.record(cell.soma(0.5)._ref_v)
    t_rec = h.Vector()
    t_rec.record(h._ref_t)

    h.finitialize(-65.0)
    h.continuerun(cfg.duration)

    v = np.asarray(v_soma)
    return {
        "n_spikes": count_spikes(v),
        "v_soma": v,
        "t": np.asarray(t_rec),
        "ve1_max": float(np.max(np.abs(ve1))),
        "ve2_max": float(np.max(np.abs(ve2))),
    }


def polarization_map(
    cfg,
    target_mm: np.ndarray,
    normal: np.ndarray,
    mesh_pair1,
    mesh_pair2,
) -> dict:
    """Steady-state per-segment polarization (ΔVm, mV) under a static field.

    Drives the cell with the static superposed pair fields (no carriers) and
    measures each segment's deviation from rest -- a cheap, orientation-aware
    readout that does not require resolving the kHz carriers.

    Returns
    -------
    dict
        ``{"delta_vm", "seg_coords_um"}`` where ``delta_vm`` is shape ``(M,)``.
    """
    from neuron import h

    cell = build_cell(cfg.model)
    ve1, ve2 = per_pair_quasipotentials(cell, target_mm, normal, mesh_pair1, mesh_pair2)
    ve_static = cfg.amplitude_scale * (ve1 + ve2)

    h.celsius = cfg.temperature
    segs = list(cell.segments())
    for i, (_sec, seg) in enumerate(segs):
        seg.e_extracellular = float(ve_static[i])

    h.finitialize(-65.0)
    # Integrate to a quasi-steady state.
    h.continuerun(50.0)
    v_pol = np.array([seg.v for _sec, seg in segs])

    # Baseline (field off) for the same cell.
    cell0 = build_cell(cfg.model)
    h.finitialize(-65.0)
    h.continuerun(50.0)
    v_rest = np.array([seg.v for _sec, seg in cell0.segments()])

    return {
        "delta_vm": v_pol - v_rest,
        "seg_coords_um": cell.segment_coords_um(),
    }


def find_threshold(
    cfg,
    target_mm: np.ndarray,
    normal: np.ndarray,
    mesh_pair1,
    mesh_pair2,
    lo: float = 0.0,
    hi: float = 100.0,
    tol: float = 0.05,
    max_iter: int = 20,
) -> float:
    """Bisect the amplitude scale to the firing threshold.

    Scales ``cfg.amplitude_scale`` (geometrically searched between *lo* and *hi*)
    until the cell just spikes.  Returns the threshold multiplier, or ``inf`` if
    the cell does not fire at *hi*.

    Returns
    -------
    float
        Threshold amplitude multiplier, or ``float("inf")``.
    """
    from dataclasses import replace

    def fires(scale: float) -> bool:
        c = replace(cfg, amplitude_scale=scale)
        return (
            simulate_response(c, target_mm, normal, mesh_pair1, mesh_pair2)["n_spikes"]
            > 0
        )

    if not fires(hi):
        return float("inf")
    if fires(lo if lo > 0 else tol):
        return lo

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        if fires(mid):
            hi = mid
        else:
            lo = mid
        if (hi - lo) <= tol:
            break
    return hi
