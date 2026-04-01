#!/usr/bin/env simnibs_python
"""4-pair multi-polar focality test with scaled hyperparameters.

Single 4-pair run on the right thalamus with DE parameters tuned for
the larger search space (16 params vs 8 for standard 2-pair).

Based on first sweep results:
  - 2-pair baseline: -71.05 in 27 min (8 params, popsize=13, tol=0.1)
  - 4-pair default:  -66.25 in 96 min (16 params, same hyperparams — worse)

The default run likely converged prematurely (tol=0.1 in a 16-dim space).
This run uses aggressive hyperparameters to give DE a fair shot:
  - popsize 25 (vs default 13) — more exploration per generation
  - maxiter 3000 (vs default 1000) — much more time to converge
  - tol 0.01 (vs default 0.1) — don't stop early
  - mutation [0.5, 1.5] — wider mutation range for larger space
  - recombination 0.9 — high crossover to share good components

Usage (inside Docker)::

    simnibs_python scripts/mp_sweep.py
"""

import os
import time

from tit import get_path_manager
from tit.opt import FlexConfig, run_flex_search

# ── Configuration ────────────────────────────────────────────────────────────

SUBJECT = "101"
PROJECT_DIR = "/mnt/000/"

RIGHT_THALAMUS = FlexConfig.SphericalROI(
    x=12,
    y=-18,
    z=6,
    radius=10.0,
    use_mni=True,
    volumetric=True,
    tissues="GM",
)

ELECTRODE = FlexConfig.ElectrodeConfig(
    shape="ellipse",
    dimensions=[8.0, 8.0],
    gel_thickness=4.0,
)


def main():
    pm = get_path_manager(PROJECT_DIR)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join(pm.flex_search(SUBJECT), f"mp_4pair_scaled_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)

    config = FlexConfig(
        subject_id=SUBJECT,
        goal="focality",
        postproc="max_TI",
        current_mA=2.0,
        electrode=ELECTRODE,
        roi=RIGHT_THALAMUS,
        non_roi_method="everything_else",
        n_pairs=4,
        n_multistart=1,
        # Scaled for 16-param search space
        population_size=5,
        max_iterations=500,
        tolerance=0.3,
        mutation="0.5,0.7",
        recombination=0.9,
        thresholds="0.1,0.2",
        run_final_electrode_simulation=True,
        output_folder=output_dir,
    )

    print(f"Output: {output_dir}")
    print(f"n_pairs=4, popsize=25, maxiter=3000, tol=0.01")
    print(f"mutation=[0.5,1.5], recombination=0.9")
    print(f"Target: right thalamus MNI (12,-18,6) r=10mm")
    print(f"Reference: 2-pair baseline scored -71.05")
    print()

    t0 = time.time()
    result = run_flex_search(config)
    elapsed = time.time() - t0

    print(f"\n{'=' * 60}")
    print(f"  Result: {result.best_value:.4f}")
    print(f"  Time:   {elapsed / 60:.1f} min")
    print(f"  Success: {result.success}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
