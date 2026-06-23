#!/usr/bin/env simnibs_python
"""Assemble and persist microscale neuron-response outputs.

Pure I/O helpers (NumPy + stdlib) that write the per-simulation artifacts under
``derivatives/SimNIBS/sub-<id>/microscale/<sim>/``:

* ``sub-<id>_sim-<sim>_targets.csv``      -- placed target coordinates/normals
* ``sub-<id>_sim-<sim>_response.npz``     -- spike counts / thresholds per target
* ``sub-<id>_sim-<sim>_polarization.npz`` -- per-cell ΔVm maps
"""

from __future__ import annotations

import csv
import os

import numpy as np


def write_targets_csv(path: str, targets_mm, normals) -> str:
    """Write the placed-target table.

    Parameters
    ----------
    path : str
        Output CSV path.
    targets_mm : sequence of (x, y, z)
        Target soma coordinates in mm.
    normals : sequence of (nx, ny, nz)
        Orientation (cortical normal) per target.

    Returns
    -------
    str
        *path*.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "x_mm", "y_mm", "z_mm", "nx", "ny", "nz"])
        for i, (t, n) in enumerate(zip(targets_mm, normals)):
            w.writerow([i, *(float(v) for v in t), *(float(v) for v in n)])
    return path


def write_response_npz(path: str, results: list[dict]) -> str:
    """Persist per-target response metrics to a ``.npz``.

    Parameters
    ----------
    path : str
        Output ``.npz`` path.
    results : list of dict
        One dict per target with at least ``"n_spikes"`` and optionally
        ``"threshold"``, ``"ve1_max"``, ``"ve2_max"``.

    Returns
    -------
    str
        *path*.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    n_spikes = np.array([r.get("n_spikes", -1) for r in results], dtype=float)
    threshold = np.array([r.get("threshold", np.nan) for r in results], dtype=float)
    ve1_max = np.array([r.get("ve1_max", np.nan) for r in results], dtype=float)
    ve2_max = np.array([r.get("ve2_max", np.nan) for r in results], dtype=float)
    np.savez(
        path,
        n_spikes=n_spikes,
        threshold=threshold,
        ve1_max=ve1_max,
        ve2_max=ve2_max,
    )
    return path


def write_polarization_npz(path: str, maps: list[dict]) -> str:
    """Persist per-cell polarization (ΔVm) maps to a ``.npz``.

    Each entry contributes a ``delta_vm_<i>`` and ``coords_<i>`` array (segment
    counts may differ across models, so they are stored per target rather than
    stacked).

    Returns
    -------
    str
        *path*.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    arrays: dict[str, np.ndarray] = {}
    for i, m in enumerate(maps):
        arrays[f"delta_vm_{i}"] = np.asarray(m["delta_vm"], dtype=float)
        arrays[f"seg_coords_um_{i}"] = np.asarray(m["seg_coords_um"], dtype=float)
    np.savez(path, **arrays)
    return path
