"""Build the flex-search "mini study" configs for subject ernie.

Two targets (thalamus, lhippo) x six arms (mean, tf_w0, tf_w1, roc_fixed,
roc_adapt, mean_ratio) = 12 study-1 runs, plus study 2 adds one more
`mean_ratio` arm per target for a total of 14 configs.

Run inside the ti-toolbox container (needs `tit`, no SimNIBS heavy deps
required for config building, but `tit.config_io` imports through
`tit.opt.config` which is pure Python -- the whole thing can run under
`simnibs_python`):

    simnibs_python build_configs.py [--smoke]

`--smoke` overrides the DE hyperparameters to something that finishes in
seconds and prefixes every output_folder with "smoke_" so the throwaway
outputs cannot collide with real study output directories.

Threshold-order note (see tit/opt/flex/pareto.py:231 and
tit/opt/flex/drivers.py's adaptive step-2 call): the codebase's own
convention for the SimNIBS ROC `thresholds` string is
"<nonroi_threshold>,<roi_threshold>" (non-ROI first). This is the *opposite*
of the naive reading of the study brief ("ROI 0.2 V/m, non-ROI 0.1 V/m" ->
you might guess "0.2,0.1"). We follow the codebase convention: thresholds
here are written "0.1,0.2" (nonroi=0.1, roi=0.2).
"""

import argparse
import json
import os

from tit import get_path_manager
from tit.config_io import serialize_config
from tit.opt import FlexConfig

PROJECT_DIR = "/mnt/000"
SUBJECT_ID = "ernie"
ATLAS_PATH = (
    "/mnt/000/derivatives/SimNIBS/sub-ernie/m2m_ernie/segmentation/labeling.nii.gz"
)

# Shared "strong" DE hyperparameters for the real study.
STRONG_HYPERPARAMS = dict(
    n_multistart=1,
    max_iterations=1000,
    population_size=15,
    tolerance=1e-4,
)

# Smoke-test overrides: fast, and tolerance=None (SimNIBS solver default;
# DE's relative-improvement `tol` doesn't make sense at population_size=4).
SMOKE_HYPERPARAMS = dict(
    n_multistart=1,
    max_iterations=2,
    population_size=4,
    tolerance=None,
)

TARGETS = {
    "thalamus": FlexConfig.SubcorticalROI(
        atlas_path=ATLAS_PATH, label=[10, 49], tissues="GM", atlas_space="subject"
    ),
    "lhippo": FlexConfig.SubcorticalROI(
        atlas_path=ATLAS_PATH, label=17, tissues="GM", atlas_space="subject"
    ),
}


def _base_kwargs(hyperparams: dict) -> dict:
    """Fields shared by every arm before target/arm-specific overrides."""
    kwargs = dict(
        subject_id=SUBJECT_ID,
        current_mA=2.0,
        electrode=FlexConfig.ElectrodeConfig(),
        run_final_electrode_simulation=True,  # else no simulated field to analyze
    )
    kwargs.update(hyperparams)
    return kwargs


def build_arm(target_name: str, arm: str, hyperparams: dict, out_prefix: str) -> FlexConfig:
    roi = TARGETS[target_name]
    kwargs = _base_kwargs(hyperparams)
    output_folder_name = f"{out_prefix}{target_name}_{arm}"

    if arm == "mean":
        kwargs.update(goal="mean", postproc="max_TI")
    elif arm == "tf_w0":
        kwargs.update(goal="focality_tf", postproc="max_TI", intensity_weight=0.0)
    elif arm == "tf_w1":
        kwargs.update(goal="focality_tf", postproc="max_TI", intensity_weight=1.0)
    elif arm == "roc_fixed":
        # ROI threshold 0.2 V/m, non-ROI threshold 0.1 V/m -> codebase order is
        # "nonroi,roi" (see module docstring).
        kwargs.update(
            goal="focality",
            postproc="max_TI",
            thresholds="0.1,0.2",
            non_roi_method="everything_else",
        )
    elif arm == "roc_adapt":
        kwargs.update(
            goal="focality",
            postproc="max_TI",
            non_roi_method="everything_else",
            mode="flex_adaptive",
            adaptive=FlexConfig.AdaptiveFocalityConfig(),  # defaults: 80/20
        )
    elif arm == "mean_ratio":
        kwargs.update(
            goal="mean",
            postproc="max_TI",
            optimize_current_ratio=True,
            ratio_levels=21,
        )
    else:
        raise ValueError(f"unknown arm {arm!r}")

    if kwargs["goal"] == "focality":
        # goal='focality' always needs a non_roi_method; roc_adapt sets it above
        # too but keep this defensive for any future arm that forgets it.
        kwargs.setdefault("non_roi_method", "everything_else")

    kwargs["roi"] = roi
    kwargs["output_folder"] = os.path.join(
        get_path_manager().flex_search(SUBJECT_ID), output_folder_name
    )

    return FlexConfig(**kwargs)


# NOTE on run count: the brief lists exactly 6 numbered arms (mean, tf_w0, tf_w1,
# roc_fixed, roc_adapt, mean_ratio) and says "six arms per target (12 runs)". Arm 6
# (mean_ratio) is also described as "study 2" (compared against arm 1's mean run).
# 6 arms x 2 targets = 12 configs total; this script builds exactly those 12 -- the
# brief's later "14 runs total" does not square with its own 6-arm list and no 7th
# arm is specified anywhere, so we did not invent one. Flagged for the requester.
ARMS = ["mean", "tf_w0", "tf_w1", "roc_fixed", "roc_adapt", "mean_ratio"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    get_path_manager(PROJECT_DIR)

    hyperparams = SMOKE_HYPERPARAMS if args.smoke else STRONG_HYPERPARAMS
    out_prefix = "smoke_" if args.smoke else "study_"

    here = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(here, "configs" if not args.smoke else "configs_smoke")
    os.makedirs(config_dir, exist_ok=True)

    written = []
    for target in ["thalamus", "lhippo"]:
        for arm in ARMS:
            cfg = build_arm(target, arm, hyperparams, out_prefix)
            data = serialize_config(cfg)
            name = f"{target}_{arm}"
            path = os.path.join(config_dir, f"{name}.json")
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
            written.append(path)
            print(f"wrote {path}")

    print(f"\n{len(written)} configs written to {config_dir}")


if __name__ == "__main__":
    main()
