#!/usr/bin/env simnibs_python
"""fsaverage-space meso-scale solve: constant L5 population, per-subject drive.

Holds the neuron population geometry CONSTANT (one canonical L5 pyramidal aligned
to the cortical normal) and varies only the per-subject FIELD EXPOSURE over the
significant cluster. Under the quasi-uniform, normal-directed approximation the
cable solve depends only on the two normal-carrier amplitudes (E1n, E2n), so a
single solve per (subject [, vertex]) suffices and absolute position is irrelevant.

For each subject we drive the cell with the two kHz carriers, run NEURON, and read:
  * peak_depol_mV  -- max somatic depolarization (≈ linear in field; ~Fig5)
  * demod_mV       -- amplitude of the somatic Vm at the ENVELOPE frequency
                      |f1-f2|. This is the demodulated/priming signal; for a
                      passive membrane it is ~0, so a non-zero value reflects the
                      cell's active-channel rectification (Mirzakhalili 2020).

Input  : <project>/derivatives/microscale/group/cluster_carrier_normal.csv
         (subject_id, e1n_mean, e2n_mean, ...) written host-side.
Output : <project>/derivatives/microscale/group/fsavg_meso_readout.csv

Run inside the ti-toolbox container (NEURON required; PROJECT_DIR set):
    simnibs_python scripts/run_fsavg_meso.py
    simnibs_python scripts/run_fsavg_meso.py --test     # 1 subject, short
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import numpy as np

from tit.microscale.field_sampler import (
    place_morphology,
    uniform_quasipotential,
)
from tit.microscale.coupling import build_extracellular_timeseries
from tit.microscale.models import build_cell
from tit.paths import get_path_manager

# --- Stimulation parameters (edit to match the protocol) -------------------
CF = 2000.0          # carrier centre frequency (Hz)
DF = 1.0             # beat/envelope frequency (Hz)  -> f1=CF, f2=CF+DF
DURATION_MS = 4000.0 # >= a few envelope periods (1 Hz -> >=2000 ms)
DT_MS = 0.025        # must resolve the carriers (period 0.5 ms)
SETTLE_MS = 500.0    # drop onset transient before reading steady response
V_REST = -65.0
NORMAL = np.array([0.0, 0.0, 1.0])   # cell apical axis; drive along it


def solve_one(e1n: float, e2n: float, duration_ms: float) -> dict:
    """Two-carrier NEURON solve for one (E1n, E2n); return Vm readouts (mV)."""
    from neuron import h

    cell = build_cell("l5_pyramidal")
    segs = list(cell.segments())
    soma_idx = next(i for i, (sec, _s) in enumerate(segs) if sec is cell.soma)

    local_um = cell.segment_coords_um()
    soma_local_um = cell.soma_coord_um()
    target_um = np.zeros(3)
    world_um = place_morphology(local_um, soma_local_um, target_um, NORMAL)

    # Normal-directed carrier vectors (V/m) -> per-segment quasipotential (mV).
    ve1 = uniform_quasipotential(e1n * NORMAL, world_um, target_um)
    ve2 = uniform_quasipotential(e2n * NORMAL, world_um, target_um)

    n_steps = int(round(duration_ms / DT_MS)) + 1
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
        v_soma = h.Vector()
        v_soma.record(segs[soma_idx][1]._ref_v)
        t_rec = h.Vector()
        t_rec.record(h._ref_t)
        h.finitialize(V_REST)
        h.continuerun(duration_ms)
        t = np.asarray(t_rec)
        vm = np.asarray(v_soma)
    finally:
        for v in play:
            v.play_remove()
        for _sec, seg in segs:
            seg.e_extracellular = 0.0

    keep = t >= SETTLE_MS
    tv, vv = t[keep], vm[keep]
    peak_depol = float(np.max(vv) - V_REST)
    # Demodulated component: amplitude of Vm at the envelope frequency DF.
    vv0 = vv - vv.mean()
    fs = 1000.0 / DT_MS  # Hz
    freqs = np.fft.rfftfreq(vv0.size, d=1.0 / fs)
    amp = np.abs(np.fft.rfft(vv0)) * 2.0 / vv0.size
    k = int(np.argmin(np.abs(freqs - DF)))
    demod = float(amp[k])
    return {
        "peak_depol_mV": peak_depol,
        "demod_mV": demod,
        "vm_mean_mV": float(vv.mean()),
        "vm_ptp_mV": float(np.ptp(vv)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--test", action="store_true", help="1 subject, short duration")
    args = ap.parse_args()

    pm = get_path_manager()
    if not pm.project_dir:
        print("ERROR: set PROJECT_DIR.", flush=True)
        return 1
    base = os.path.join(pm.project_dir, "derivatives", "microscale", "group")
    in_csv = os.path.join(base, "cluster_carrier_normal.csv")
    out_csv = os.path.join(base, "fsavg_meso_readout.csv")
    if not os.path.exists(in_csv):
        print(f"ERROR: missing {in_csv} (run the host prep first).", flush=True)
        return 1

    with open(in_csv, newline="") as fh:
        subjects = list(csv.DictReader(fh))
    duration = 1000.0 if args.test else DURATION_MS
    if args.test:
        subjects = subjects[:1]
    print(f"carriers {CF}/{CF + DF} Hz, env {DF} Hz, dur {duration} ms, dt {DT_MS} ms",
          flush=True)

    rows = []
    for i, r in enumerate(subjects):
        sid = r["subject_id"]
        e1n, e2n = float(r["e1n_mean"]), float(r["e2n_mean"])
        print(f"[{i + 1}/{len(subjects)}] sub-{sid} E1n={e1n:.3f} E2n={e2n:.3f} V/m",
              flush=True)
        out = solve_one(e1n, e2n, duration)
        print(f"    peak_depol={out['peak_depol_mV']:.4g} mV  "
              f"demod={out['demod_mV']:.4g} mV", flush=True)
        rows.append({"subject_id": sid, "e1n_mean": e1n, "e2n_mean": e2n, **out})

    with open(out_csv, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"✓ wrote {out_csv}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
