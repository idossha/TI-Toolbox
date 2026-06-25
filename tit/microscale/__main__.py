#!/usr/bin/env simnibs_python
"""CLI entry point for the microscale polarization-map pipeline.

Usage::

    simnibs_python -m tit.microscale config.json

The JSON config drives the **subthreshold cortical polarization map**: for each
subject it computes the analytic per-vertex somatic ΔVm over the TI central
surface (``ΔVm = coupling * E_normal``) and, on a NEURON subsample, the
distribution of polarization around that estimate.  See
:func:`tit.microscale.population.run_population`.

Config keys (populate :class:`~tit.microscale.config.PopulationConfig`)::

    {
      "project_dir": "/path/to/project",
      "subject_ids": ["001"],
      "sim_name": "my_sim",
      "model": "l5_pyramidal",
      "cluster_normal_field": "TI_normal",
      "cluster_threshold": null,
      "n_subsample": 50,
      "n_clones": 5,
      "n_azimuth": 6,
      "polarization_coupling": 0.27,
      "carrier_freqs": [2000.0, 2010.0],
      "overwrite": false
    }

``"mode"`` is optional and accepts ``"polarization"`` (default) or its alias
``"population"``.  The single-cell spike/threshold demonstrator is library-only
(:mod:`tit.microscale.coupling`); it is intentionally not a CLI mode because its
absolute numbers are not quantitatively faithful (see that module).

See Also
--------
tit.microscale.config : ``PopulationConfig``.
tit.microscale.population : ``run_population``.
"""

import json
import sys

from tit.paths import get_path_manager


def main() -> None:
    """Parse the config JSON and run the polarization-map pipeline."""
    config_path = sys.argv[1]
    with open(config_path) as f:
        data = json.load(f)

    get_path_manager(data.pop("project_dir"))
    mode = data.pop("mode", "polarization")
    if mode not in ("polarization", "population"):
        raise SystemExit(
            f"Unknown mode {mode!r}; this module runs the polarization map only "
            "(use 'polarization'). The single-cell demonstrator is library-only."
        )
    print("Starting microscale polarization pipeline...", flush=True)

    subject_ids = data.pop("subject_ids")
    cfg = _build_config(data)

    failed: list[str] = []
    for sid in subject_ids:
        print(
            f"[sub-{sid}] sim={cfg.sim_name} model={cfg.model} "
            f"clones={cfg.n_clones} azimuth={cfg.n_azimuth} "
            f"subsample={cfg.n_subsample}",
            flush=True,
        )
        try:
            _run_subject(sid, cfg)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  ✗ FAILED: {exc}", flush=True)
            failed.append(sid)

    if failed:
        raise SystemExit(f"microscale failed for: {', '.join(failed)}")
    print("✓ Microscale polarization pipeline complete.", flush=True)


def _build_config(data: dict):
    from tit.microscale.config import PopulationConfig

    def _f(key, default):
        return data.get(key, default)

    kwargs = dict(
        sim_name=data["sim_name"],
        model=_f("model", "l5_pyramidal"),
        conductivity=_f("conductivity", "scalar"),
        n_clones=_f("n_clones", 5),
        n_azimuth=_f("n_azimuth", 6),
        cluster_normal_field=_f("cluster_normal_field", "TI_normal"),
        cluster_threshold=_f("cluster_threshold", None),
        n_subsample=_f("n_subsample", 50),
        polarization_coupling=_f("polarization_coupling", 0.27),
        duration=_f("duration", 100.0),
        dt=_f("dt", 0.005),
        temperature=_f("temperature", 37.0),
        cpus=_f("cpus", 1),
        seed=_f("seed", 0),
        render_population=_f("render_population", True),
        render_video=_f("render_video", True),
        overwrite=_f("overwrite", False),
    )
    if data.get("carrier_freqs") is not None:
        kwargs["carrier_freqs"] = tuple(float(x) for x in data["carrier_freqs"])
    return PopulationConfig(**kwargs)


def _run_subject(sid: str, cfg) -> None:
    from tit.microscale.population import run_population

    run_population(sid, cfg)


if __name__ == "__main__":
    main()
