#!/usr/bin/env simnibs_python
"""Serial fixed-candidate Flex benchmark against a real subject.

Run each mode in a fresh process, with the observation leg reusing the baseline
parameters.json. No optimizer convergence or final electrode FEM is claimed.
Example (inside the existing dev container, one process at a time)::

    simnibs_python dev/flex_candidate_benchmark.py --project /mnt/000 \
        --subject ernie --output /mnt/000/code/ti-toolbox/bench-UNIQUE/baseline
    simnibs_python dev/flex_candidate_benchmark.py --project /mnt/000 \
        --subject ernie --output /mnt/000/code/ti-toolbox/bench-UNIQUE/observed \
        --observe --parameters /mnt/000/code/ti-toolbox/bench-UNIQUE/baseline/parameters.json

The normal builder resolves the checkout's integration within this process. Each output
folder must be new. Peak RSS is process lifetime (including setup); steady RSS
is also sampled after preparation and each evaluation. Input subject files are
read, while all benchmark records/logs go to the requested new output folder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import resource
import sys
import time

import numpy as np


def _rss_kib() -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise RuntimeError("Linux process RSS unavailable")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--subject", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--observe", action="store_true")
    parser.add_argument("--goal", choices=("mean", "focality_tf"), default="mean")
    parser.add_argument(
        "--optimizer-only",
        action="store_true",
        help="Run actual DE maxiter=1/popsize=1 after preparation, instead of fixed benchmark trials",
    )
    parser.add_argument("--parameters")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--cpus", type=int, default=2)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("TIT_NO_TELEMETRY", "1")
    from numba import set_num_threads
    from tit.paths import get_path_manager
    from tit.opt.config import FlexConfig
    from tit.opt.flex.builder import build_optimization

    set_num_threads(args.cpus)
    root = Path(__file__).resolve().parents[1]
    source = root / "resources/map-electrodes/tes_flex_optimization.py"
    get_path_manager(args.project)
    config = FlexConfig(
        subject_id=args.subject,
        goal=args.goal,
        postproc="max_TI",
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(dimensions=[10.0, 10.0]),
        roi=FlexConfig.SphericalROI(
            x=-35.0, y=-20.0, z=50.0, radius=15.0, volumetric=True, use_mni=False
        ),
        output_folder=str(output),
        observe_background=args.observe,
        visualize_valid_skin_region=False,
        cpus=args.cpus,
        max_iterations=1 if args.optimizer_only else None,
        population_size=1 if args.optimizer_only else None,
    )
    opt = build_optimization(config)
    opt.seed = 17
    opt.visualize_valid_skin_region = False
    opt.run_final_electrode_simulation = False
    if args.parameters:
        parameters = json.loads(Path(args.parameters).read_text())
        opt.initial_x0 = np.asarray(parameters[0], dtype=float)
    else:
        parameters = None
    started = time.perf_counter()
    opt.run(cpus=args.cpus, save_mat=False, prepare_only=True)
    prepared = time.perf_counter()
    if parameters is None:
        # Small distinct nearby placements keep the benchmark about extraction
        # rather than rejection frequency. Every trial still uses real checks.
        parameters = [np.asarray(opt.x0).tolist()]
        for index in range(args.samples):
            trial = np.asarray(opt.x0).copy()
            trial[index % len(trial)] += (index + 1) * 1e-4
            parameters.append(trial.tolist())
    (output / "parameters.json").write_text(json.dumps(parameters, indent=2) + "\n")
    solve_count = 0
    original_solve = opt._ofem.solve

    def count_solve(*positional, **keywords):
        nonlocal solve_count
        solve_count += 1
        return original_solve(*positional, **keywords)

    opt._ofem.solve = count_solve
    record = {
        "config": opt._candidate_recorder.config,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "python": sys.version,
        "platform": sys.platform,
        "setup_seconds": prepared - started,
        "setup_rss_kib": _rss_kib(),
        "roi_samples": [len(roi.get_nodes()) for roi in opt.roi],
        "evaluations": [],
        "claim": "fixed candidate verification; not converged optimization",
    }
    if args.optimizer_only:
        opt.polish = False
        opt._optimizer_options_std.update(maxiter=1, popsize=1, disp=False)
        record["effective_optimizer_options"] = {
            "maxiter": 1,
            "popsize": 1,
            "polish": False,
            "seed": 17,
        }
        optimizer_started = time.perf_counter()
        opt.run(cpus=args.cpus, save_mat=False)
        record.update(
            claim="short actual differential evolution; iteration limit is not convergence",
            optimizer_seconds=time.perf_counter() - optimizer_started,
            optimizer_termination=opt.optimizer_termination,
            accepted=bool(getattr(opt, "_accepted_candidate_valid", False)),
            accepted_candidate_id=getattr(opt, "_accepted_candidate_id", None),
            objective=float(opt.optim_funvalue),
            valid_candidates=opt._candidate_recorder.valid,
            rejected_counts=dict(opt._candidate_recorder.rejected),
            solves=solve_count,
            peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            total_seconds=time.perf_counter() - started,
        )
        opt._candidate_recorder.close()
        (output / "benchmark.json").write_text(
            json.dumps(record, indent=2, allow_nan=False) + "\n"
        )
        print(json.dumps(record, allow_nan=False), flush=True)
        if not record["accepted"]:
            raise RuntimeError(
                "Actual optimizer did not accept a recorded valid candidate"
            )
        from tit.opt.config import FlexResult
        from tit.opt.flex.manifest import write_manifest

        write_manifest(
            str(output),
            config,
            FlexResult(
                True, str(output), [record["objective"]], record["objective"], 0
            ),
            "Validation smoke — not converged",
        )
        return
    for index, parameter in enumerate(parameters):
        solve_before = solve_count
        valid_before = opt._candidate_recorder.valid
        before = time.perf_counter()
        objective = float(opt.goal_fun(np.asarray(parameter)))
        elapsed = time.perf_counter() - before
        observation = {
            "index": index,
            "warmup": index == 0,
            "seconds": elapsed,
            "objective": objective,
            "valid": opt._candidate_recorder.valid > valid_before,
            "solves": solve_count - solve_before,
            "rss_kib": _rss_kib(),
        }
        record["evaluations"].append(observation)
        print(json.dumps(observation), flush=True)
        (output / "benchmark.json").write_text(
            json.dumps(record, indent=2, allow_nan=False) + "\n"
        )
    valid = [item for item in record["evaluations"] if item["valid"]]
    if not valid:
        raise RuntimeError("No valid candidate; no benchmark can be claimed")
    winner = min(valid, key=lambda item: item["objective"])
    opt.optim_parameters = np.asarray(parameters[winner["index"]])
    opt.optim_funvalue = winner["objective"]
    record["accepted"] = opt._candidate_recorder.finalize(opt)
    record["accepted_candidate_id"] = opt._accepted_candidate_id
    record["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    record["total_seconds"] = time.perf_counter() - started
    opt._candidate_recorder.close()
    (output / "benchmark.json").write_text(
        json.dumps(record, indent=2, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {key: record[key] for key in ("accepted", "peak_rss_kib", "total_seconds")}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
