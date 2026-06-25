#!/usr/bin/env simnibs_python
"""Persist the microscale polarization-map outputs.

Pure I/O helpers (NumPy + stdlib) plus two best-effort surface writers, all
writing under ``derivatives/SimNIBS/sub-<id>/microscale/<sim>/``:

* ``sub-<id>_sim-<sim>_polarization.npz`` -- the full population result: the
  analytic per-vertex ΔVm map, the cluster indices, and the NEURON-subsample
  distribution arrays.
* ``sub-<id>_sim-<sim>_summary.csv``      -- a readable region-level table
  (ΔVm statistics + the delivered field vs literature firing thresholds).
* ``sub-<id>_sim-<sim>_polarization.msh`` -- the central surface carrying the
  ΔVm node field (SimNIBS/gmsh native; best-effort, needs simnibs).
* ``sub-<id>_sim-<sim>_polarization.gii`` -- a GIFTI overlay of the same map
  (portable; loads in FreeView/Connectome Workbench; best-effort, needs nibabel).
"""

from __future__ import annotations

import csv
import os

import numpy as np

from tit.microscale.config import (
    KHZ_TIS_THRESHOLD_VM,
    LFS_THRESHOLD_VM,
)


def write_population_npz(path: str, result: dict) -> str:
    """Persist a :func:`tit.microscale.population.run_population` result.

    Stores the cluster arrays, the analytic central map (all vertices), the
    NEURON subsample arrays ``(n_sub, n_clones, n_azimuth)``, and the flat
    summary stats (one scalar per key, as a ``summary_keys``/``summary_values``
    pair).

    Returns
    -------
    str
        *path*.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    summary = result.get("summary", {})
    np.savez(
        path,
        cluster_idx=np.asarray(result["cluster_idx"], dtype=int),
        vertices_mm=np.asarray(result["vertices_mm"], dtype=float),
        normals=np.asarray(result["normals"], dtype=float),
        ti_normal=np.asarray(result["ti_normal"], dtype=float),
        analytic_delta_vm=np.asarray(result["analytic_delta_vm"], dtype=float),
        subsample_idx=np.asarray(result["subsample_idx"], dtype=int),
        neuron_delta_vm=np.asarray(result["neuron_delta_vm"], dtype=float),
        amplification=np.asarray(result["amplification"], dtype=float),
        summary_keys=np.asarray(list(summary.keys()), dtype=object),
        summary_values=np.asarray(list(summary.values()), dtype=float),
    )
    return path


def region_summary(result: dict) -> dict:
    """Compute the region-level polarization summary (the readable headline).

    Aggregates the analytic ΔVm map over the *cluster* vertices and the driving
    normal field, and frames both against the Wang et al. 2022 single-cell
    firing thresholds so the subthreshold margin is explicit.

    Returns
    -------
    dict
        Ordered metric -> value (floats; thresholds as ``"lo-hi"`` strings).
    """
    cluster_idx = np.asarray(result["cluster_idx"], dtype=int).reshape(-1)
    analytic = np.asarray(result["analytic_delta_vm"], dtype=float).reshape(-1)
    e_normal = np.asarray(result["ti_normal"], dtype=float).reshape(-1)

    dvm = analytic[cluster_idx] if cluster_idx.size else analytic
    en = e_normal[cluster_idx] if cluster_idx.size else e_normal
    dvm = dvm[np.isfinite(dvm)]
    en = en[np.isfinite(en)]

    peak_dvm = float(np.max(np.abs(dvm))) if dvm.size else float("nan")
    peak_e = float(np.max(np.abs(en))) if en.size else float("nan")
    # Honest margin: how far the peak delivered field is below the lowest
    # single-cell firing threshold (Wang 2022, low-frequency 10 Hz).
    margin = LFS_THRESHOLD_VM[0] / peak_e if peak_e > 0 else float("inf")

    return {
        "n_cluster_vertices": float(dvm.size),
        "delta_vm_mean_mV": float(np.mean(dvm)) if dvm.size else float("nan"),
        "delta_vm_median_mV": float(np.median(dvm)) if dvm.size else float("nan"),
        "delta_vm_p5_mV": float(np.percentile(dvm, 5)) if dvm.size else float("nan"),
        "delta_vm_p95_mV": float(np.percentile(dvm, 95)) if dvm.size else float("nan"),
        "delta_vm_peak_abs_mV": peak_dvm,
        "e_normal_peak_abs_Vm": peak_e,
        "lfs_threshold_Vm": f"{LFS_THRESHOLD_VM[0]:g}-{LFS_THRESHOLD_VM[1]:g}",
        "khz_tis_threshold_Vm": f"{KHZ_TIS_THRESHOLD_VM[0]:g}-{KHZ_TIS_THRESHOLD_VM[1]:g}",
        "subthreshold_margin_x": float(margin),
    }


def write_region_summary_csv(path: str, result: dict) -> str:
    """Write the region-level polarization summary as a metric/value table.

    One row per metric from :func:`region_summary` -- the table a user reads to
    see the polarization magnitude and how far below the firing threshold the
    delivered field is.

    Returns
    -------
    str
        *path*.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    summary = region_summary(result)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in summary.items():
            w.writerow([k, v])
    return path


def write_polarization_msh(central_msh_path: str, out_path: str, delta_vm) -> str:
    """Write the analytic ΔVm map onto the central surface as a SimNIBS ``.msh``.

    Reads the simulation's TI central surface, attaches the per-vertex somatic
    polarization ``delta_Vm_mV`` as a node field, and writes a new mesh under the
    microscale output directory -- so the map opens in gmsh / the SimNIBS viewer
    exactly like ``TI_normal`` and the other surface scalars.

    Best-effort: needs SimNIBS.  Returns ``out_path`` on success.

    Raises
    ------
    Exception
        Propagated from SimNIBS I/O; callers run this inside a try/except so a
        missing surface does not fail the pipeline.
    """
    from simnibs.mesh_tools import mesh_io

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mesh = mesh_io.read_msh(central_msh_path)
    values = np.asarray(delta_vm, dtype=float).reshape(-1)
    n = min(len(values), mesh.nodes.nr)
    field = np.zeros(mesh.nodes.nr, dtype=float)
    field[:n] = values[:n]
    mesh.add_node_field(field, "delta_Vm_mV")
    mesh_io.write_msh(mesh, out_path)
    return out_path


def write_polarization_gifti(out_path: str, delta_vm) -> str:
    """Write the ΔVm map as a GIFTI functional overlay (one value per vertex).

    A ``*.func.gii``-style overlay (geometry comes from the matching surface)
    that loads in FreeView / Connectome Workbench.  Best-effort: needs nibabel.

    Returns
    -------
    str
        *out_path*.
    """
    import nibabel as nib

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    values = np.asarray(delta_vm, dtype=np.float32).reshape(-1)
    darr = nib.gifti.GiftiDataArray(
        data=values, intent="NIFTI_INTENT_SHAPE", datatype="NIFTI_TYPE_FLOAT32"
    )
    img = nib.gifti.GiftiImage(darrays=[darr])
    nib.save(img, out_path)
    return out_path
