# Deep vs superficial focality: ROC vs integral (ernie)

Validation/demo for the `focality_integral` flex-search goal. Runs flex-search
four times on the SimNIBS `ernie` head model — {superficial, deep} target ×
{ROC `focality`, threshold-free `focality_integral`} — and renders a comparison
figure + HTML report.

**Point:** at a *deep* target the ROC objective goes flat (both thresholds
jointly infeasible → constant objective → differential evolution has no
gradient), while integral focality stays smooth and optimizable. The figure
shows this as a flat trajectory in the deep/ROC cell only.

## Run

```bash
# 1. Run the four optimizations (writes results.json + per-run outputs).
OUT_DIR=/tmp/focint_ernie PROJECT_DIR=/path/to/bids_project \
    simnibs_python run_comparison.py --maxiter 3 --popsize 4 --cpus 4

# 2. Render the figure + HTML report.
simnibs_python make_report.py /tmp/focint_ernie/results.json
# -> /tmp/focint_ernie/comparison.png, report.html
```

`PROJECT_DIR` must be a BIDS project with
`derivatives/SimNIBS/sub-ernie/m2m_ernie`. Outputs go under `OUT_DIR`, never
into the source dataset.

## Notes

- Budgets are intentionally small (fast, not fully converged). Larger
  `--maxiter`/`--popsize` converge better but reach the same qualitative
  conclusion. On macOS SimNIBS falls back to the MUMPS solver (~20 s per FEM
  solve on ernie); expect a few minutes per run.
- `run_comparison.py` persists `results.json` after every cell, so partial runs
  are never lost and `make_report.py` can render whatever completed.
- Targets (MNI): superficial = left M1 hand-knob `[-37,-21,58]`; deep = left
  hippocampus `[-28,-20,-16]` (volumetric). Edit the constants at the top of
  `run_comparison.py` to retarget.
