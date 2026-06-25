#!/usr/bin/env simnibs_python
"""Amplitude sweep on one L5 cell: separate the LINEAR and NONLINEAR response.

Drives a single canonical L5 pyramidal with two kHz carriers (equal normal
amplitude A) across a wide range of A, and at each A extracts:
  * peak_depol_mV  -- peak somatic polarization (the LINEAR priming response, ~A)
  * demod_mV       -- somatic Vm amplitude at the envelope freq |f1-f2|
                      (the NONLINEAR mixing product / neuron-mixer, ~A^2;
                      Luff et al. 2024)
  * carrier_mV     -- Vm amplitude at the carrier f1 (linear carrier-following)
  * n_spikes       -- activation (suprathreshold onset)

Plotting the two scalings on log-log shows where linear priming dominates and
where the nonlinear mixing product would catch up -- placing our delivered dose
(~0.1-0.2 V/m) on the curve.

Run in the ti-toolbox container (NEURON):
    simnibs_python scripts/run_meso_sweep.py
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

from tit.microscale.field_sampler import place_morphology, uniform_quasipotential
from tit.microscale.coupling import build_extracellular_timeseries, count_spikes
from tit.microscale.models import build_cell
from tit.paths import get_path_manager

CF, DF = 2000.0, 1.0
DURATION_MS, DT_MS, SETTLE_MS, V_REST = 4000.0, 0.025, 500.0, -65.0
NORMAL = np.array([0.0, 0.0, 1.0])
AMPS_VM = np.logspace(-2.0, 1.6, 16)  # 0.01 .. ~40 V/m


def solve(amp: float) -> dict:
    from neuron import h

    cell = build_cell("l5_pyramidal")
    segs = list(cell.segments())
    soma_idx = next(i for i, (sec, _s) in enumerate(segs) if sec is cell.soma)
    world_um = place_morphology(
        cell.segment_coords_um(), cell.soma_coord_um(), np.zeros(3), NORMAL
    )
    ve1 = uniform_quasipotential(amp * NORMAL, world_um, np.zeros(3))
    ve2 = uniform_quasipotential(amp * NORMAL, world_um, np.zeros(3))
    n_steps = int(round(DURATION_MS / DT_MS)) + 1
    t_ms = np.arange(n_steps) * DT_MS
    ve_t = build_extracellular_timeseries(ve1, ve2, t_ms, CF, CF + DF, amplitude=1.0)

    h.celsius = 37.0
    h.dt = DT_MS
    t_vec = h.Vector(t_ms)
    play = []
    try:
        for i, (_sec, seg) in enumerate(segs):
            v = h.Vector(ve_t[i])
            v.play(seg._ref_e_extracellular, t_vec, 1)
            play.append(v)
        v_soma = h.Vector(); v_soma.record(segs[soma_idx][1]._ref_v)
        t_rec = h.Vector(); t_rec.record(h._ref_t)
        h.finitialize(V_REST)
        h.continuerun(DURATION_MS)
        t, vm = np.asarray(t_rec), np.asarray(v_soma)
    finally:
        for v in play:
            v.play_remove()
        for _sec, seg in segs:
            seg.e_extracellular = 0.0

    keep = t >= SETTLE_MS
    vv = vm[keep]
    n_spikes = count_spikes(vv)
    vv0 = vv - vv.mean()
    fs = 1000.0 / DT_MS
    freqs = np.fft.rfftfreq(vv0.size, d=1.0 / fs)
    amp_spec = np.abs(np.fft.rfft(vv0)) * 2.0 / vv0.size
    demod = float(amp_spec[int(np.argmin(np.abs(freqs - DF)))])
    carrier = float(amp_spec[int(np.argmin(np.abs(freqs - CF)))])
    return {
        "amp_Vm": amp,
        "peak_depol_mV": float(np.max(vv) - V_REST),
        "demod_mV": demod,
        "carrier_mV": carrier,
        "n_spikes": int(n_spikes),
    }


def main() -> int:
    pm = get_path_manager()
    if not pm.project_dir:
        print("ERROR: set PROJECT_DIR.", flush=True)
        return 1
    out = os.path.join(pm.project_dir, "derivatives", "microscale", "group",
                       "meso_amplitude_sweep.csv")
    rows = []
    for a in AMPS_VM:
        r = solve(float(a))
        print(f"A={a:8.3f} V/m  peak={r['peak_depol_mV']:.4g}  "
              f"demod={r['demod_mV']:.4g}  spikes={r['n_spikes']}", flush=True)
        rows.append(r)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"✓ wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
