# Three-arm focality comparison on deep targets (ernie)

Validation/demo for the `focality_integral` flex-search goal. For deep targets
(thalamus, hippocampus) it runs flex-search under **three arms** — ROC focality at
two thresholds and threshold-free integral focality — and renders a visual report:
progress on a common metric, ROC curves (Weise-style), ROI/non-ROI distributions
(Fernández-Corazza-style), the TI field **on the T1 with the ROI outlined**, and the
optimized electrodes on the scalp.

## Why three arms

The two ROC arms use different threshold pairs (non-ROI max, ROI min): a
conservative `0.1/0.2 V/m` and an aggressive `0.2/0.4 V/m`. Comparing them shows how
much the ROC result depends on a threshold the user must pick — the pitfall the
threshold-free integral objective sidesteps.

## Objectives are on different scales

- **ROC arm** minimizes `−100·(√2 − d)`, d = distance of the (1−specificity,
  sensitivity) point to the ideal corner at the chosen thresholds. Range ≈ [−141, 0].
- **Integral arm** minimizes `−IF`, `IF = (mean E_ROI/V_ROI)/√(mean E_nonROI/V_nonROI)`.
  Range ≈ [−5, 0].

Because those aren't comparable, all cross-arm plots use a **common** yardstick: the
mean-field ROI/non-ROI contrast (progress, summary) and the ROC AUC.

## Run

```bash
# 1. Optimize (3 arms × 2 targets = 6 runs) at SimNIBS default budget.
OUT_DIR=/tmp/foc3 PROJECT_DIR=/path/to/bids_project \
    simnibs_python run_comparison.py --default --cpus 4

# 2. Render the PNG panels (comparative + per-condition T1/scalp).
simnibs_python make_report.py /tmp/foc3/results.json

# 3. Assemble the self-contained report.html.
simnibs_python make_artifact.py /tmp/foc3 /tmp/foc3/report.html
```

`--default` uses SimNIBS defaults (popsize 13, maxiter 1000, tol 0.1). Drop it and
pass `--maxiter N --popsize N` for a faster, lower-budget run. Other flags:
`--only <cell>` (e.g. `thalamus_integral`), `--no-final-sim` (skip field render).

`PROJECT_DIR` must be a BIDS project with `derivatives/SimNIBS/sub-ernie/m2m_ernie`
(the m2m must contain `T1.nii.gz` for the on-T1 overlay). Outputs go under `OUT_DIR`,
never into the source dataset.

## Files

- `run_comparison.py` — runs the arms; captures the objective trajectory, a common
  ROI/non-ROI progress metric, best-montage fields, and the final-sim meshes.
- `t1_overlay.py` — mesh→NIfTI + T1/field/ROI-contour slice renderer.
- `make_report.py` — PNG panels. `make_artifact.py` — HTML report with captions.

## Targets (MNI)

thalamus `[-10,-19,8]` r6 · hippocampus `[-28,-20,-16]` r8 (both volumetric). Edit
`TARGETS`/`ARMS` at the top of `run_comparison.py` to change targets or thresholds.
