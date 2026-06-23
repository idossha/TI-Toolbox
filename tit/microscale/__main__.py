#!/usr/bin/env simnibs_python
"""CLI entry point for the microscale (field -> neuron) package.

Usage::

    simnibs_python -m tit.microscale config.json

The JSON config is dispatched on its ``"mode"`` field:

* ``"response"``  -> drive each target with the TI carriers; emit spike counts
  and per-cell polarization maps.
* ``"threshold"`` -> bisect the field amplitude to each target's firing
  threshold.

The remaining keys populate :class:`~tit.microscale.config.MicroscaleConfig`,
plus a top-level ``"subject_ids"`` list and an optional per-target ``"normals"``
list (defaults to ``+z`` when absent).

See Also
--------
tit.microscale.config : ``MicroscaleConfig``.
"""

import json
import os
import sys

import numpy as np

from tit.paths import get_path_manager


def main() -> None:
    """Parse config JSON and dispatch to the response or threshold pipeline."""
    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))
    mode = data.pop("mode", "response")
    print(f"Starting microscale {mode} pipeline...", flush=True)

    subject_ids = data.pop("subject_ids")
    normals = data.pop("normals", None)
    cfg = _build_config(data)

    failed: list[str] = []
    for sid in subject_ids:
        print(f"[sub-{sid}] sim={cfg.sim_name} model={cfg.model}", flush=True)
        try:
            _run_subject(sid, cfg, mode, normals)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  ✗ FAILED: {exc}", flush=True)
            failed.append(sid)

    if failed:
        raise SystemExit(f"microscale failed for: {', '.join(failed)}")
    print("✓ Microscale pipeline complete.", flush=True)


def _build_config(data: dict):
    from tit.microscale.config import MicroscaleConfig

    targets = tuple(tuple(float(c) for c in t) for t in data.get("targets", ()))
    carriers = data.get("carrier_freqs")
    kwargs = dict(
        sim_name=data["sim_name"],
        model=data.get("model", "ball_stick"),
        targets=targets,
        conductivity=data.get("conductivity", "scalar"),
        duration=data.get("duration", 100.0),
        dt=data.get("dt", 0.005),
        temperature=data.get("temperature", 37.0),
        amplitude_scale=data.get("amplitude_scale", 1.0),
        cpus=data.get("cpus", 1),
        overwrite=data.get("overwrite", False),
    )
    if carriers is not None:
        kwargs["carrier_freqs"] = tuple(float(x) for x in carriers)
    return MicroscaleConfig(**kwargs)


def _run_subject(sid: str, cfg, mode: str, normals) -> None:
    """Run all targets for one subject and write outputs."""
    from tit.microscale.coupling import (
        _load_pair_meshes,
        find_threshold,
        polarization_map,
        simulate_response,
    )
    from tit.microscale.metrics import (
        write_polarization_npz,
        write_response_npz,
        write_targets_csv,
    )

    pm = get_path_manager()
    m1, m2 = _load_pair_meshes(sid, cfg)

    targets = list(cfg.targets)
    if not targets:
        raise ValueError("no targets provided (ROI sampling not yet supported)")
    norms = _resolve_normals(normals, len(targets))

    out_dir = pm.microscale_sim(sid, cfg.sim_name)
    stem = f"sub-{sid}_sim-{cfg.sim_name}"
    write_targets_csv(os.path.join(out_dir, f"{stem}_targets.csv"), targets, norms)

    results: list[dict] = []
    pol_maps: list[dict] = []
    for idx, (tgt, nrm) in enumerate(zip(targets, norms)):
        print(f"  [{idx + 1}/{len(targets)}] target {tgt}", flush=True)
        if mode == "threshold":
            thr = find_threshold(cfg, np.array(tgt), np.array(nrm), m1, m2)
            results.append({"threshold": thr, "n_spikes": -1})
            print(f"      threshold scale = {thr:g}", flush=True)
        elif mode == "response":
            resp = simulate_response(cfg, np.array(tgt), np.array(nrm), m1, m2)
            results.append(resp)
            pol_maps.append(polarization_map(cfg, np.array(tgt), np.array(nrm), m1, m2))
            print(f"      spikes = {resp['n_spikes']}", flush=True)
        else:
            raise SystemExit(
                f"Unknown mode: {mode!r} (expected 'response' or 'threshold')"
            )

    write_response_npz(os.path.join(out_dir, f"{stem}_response.npz"), results)
    if pol_maps:
        write_polarization_npz(
            os.path.join(out_dir, f"{stem}_polarization.npz"), pol_maps
        )
    print(f"  ✓ wrote outputs to {out_dir}", flush=True)


def _resolve_normals(normals, n: int) -> list:
    """Return one orientation per target, defaulting to apical +z."""
    if normals is None:
        return [(0.0, 0.0, 1.0)] * n
    if len(normals) != n:
        raise ValueError(f"normals ({len(normals)}) must match number of targets ({n})")
    return [tuple(float(c) for c in nrm) for nrm in normals]


if __name__ == "__main__":
    main()
