#!/usr/bin/env simnibs_python
"""4-pair leadfield-based DE optimization on subject 101.

Runs DE over discrete EEG-net electrode positions from the leadfield,
targeting the right thalamus. Compare with flex-search mp results.

Usage (inside Docker):
    simnibs_python scripts/mp_leadfield_test.py
"""

import os
import time

from tit import get_path_manager
from tit.opt import MultiPolarConfig, run_mp_search
from tit.opt.config import FlexConfig

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


def main():
    pm = get_path_manager(PROJECT_DIR)
    lf_path = os.path.join(pm.leadfields(SUBJECT), "101_leadfield_GSN-HydroCel-185.hdf5")
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out = os.path.join(pm.flex_search(SUBJECT), f"mp_leadfield_{timestamp}")

    config = MultiPolarConfig(
        subject_id=SUBJECT,
        leadfield_hdf=lf_path,
        n_pairs=4,
        roi=RIGHT_THALAMUS,
        current_mA=2.0,
        non_roi_method="everything_else",
        population_size=30,
        max_iterations=500,
        tolerance=0.01,
        mutation="0.5,1.0",
        recombination=0.7,
        output_dir=out,
    )

    print(f"Output: {out}")
    print(f"Leadfield: {lf_path}")
    print(
        f"n_pairs=4, DE on {config.population_size} pop, {config.max_iterations} maxiter"
    )
    print(f"Target: right thalamus MNI (12,-18,6) r=10mm")
    print()

    t0 = time.time()
    result = run_mp_search(config)
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"  Focality: {result.best_focality:.4f}")
    print(f"  Time:     {elapsed/60:.1f} min")
    print(f"  Montage:")
    for plus, minus, mA in result.best_montage:
        print(f"    {plus} -> {minus}  ({mA:.1f} mA)")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
