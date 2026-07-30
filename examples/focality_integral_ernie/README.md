# Deep vs superficial focality: ROC vs integral (ernie)

Validation/demo for the `focality_integral` flex-search goal. Runs flex-search
four times on the SimNIBS `ernie` head model — {superficial, deep} target ×
{ROC `focality`, threshold-free `focality_integral`} — and renders a visual
comparison report: TI field on gray matter, optimized electrodes on the scalp,
ROC curves (Weise-style), ROI/non-ROI field distributions (Fernández-Corazza-
style), and DE progress curves.

## What it shows (empirical, 2 mA, ernie)

At a modest optimization budget, the threshold-free **integral** objective — with
its smoother landscape — reaches a far more focal montage at the **superficial**
target and ties at **depth**:

| Target | Goal | AUC | mean ROI/non-ROI |
|---|---|---|---|
| superficial | ROC | 0.55 | 1.00 |
| superficial | **integral** | **0.94** | **1.78** |
| deep | ROC | 0.79 | 1.34 |
| deep | integral | 0.78 | 1.30 |

Note: the ROC objective **does not automatically "go flat" at deep targets** — with
a *reachable* ROI threshold (0.1/0.2 V/m) the deep target reached ROI mean 0.23 V/m
> 0.20, so ROC kept its gradient. Flatness only appears when the ROI threshold is set
*infeasibly* high (see `--thresholds`), which is exactly the threshold-selection
pitfall the threshold-free integral objective avoids.

## Run

```bash
# 1. Run the four optimizations (writes results.json + per-run outputs + final-sim meshes).
OUT_DIR=/tmp/focint_ernie PROJECT_DIR=/path/to/bids_project \
    simnibs_python run_comparison.py --maxiter 15 --popsize 6 --cpus 4

# 2. Render the PNG panels (+ a basic report.html).
simnibs_python make_report.py /tmp/focint_ernie/results.json

# 3. (optional) Assemble a polished, self-contained report.html with metrics.
simnibs_python make_artifact.py /tmp/focint_ernie /tmp/focint_ernie/report.html
```

`PROJECT_DIR` must be a BIDS project with
`derivatives/SimNIBS/sub-ernie/m2m_ernie`. Outputs go under `OUT_DIR`, never into
the source dataset.

### Useful flags

- `--only <cell>` — run one cell, e.g. `--only deep_focality`.
- `--thresholds "nonROImax,ROImin"` — ROC thresholds in V/m (default `0.1,0.2`).
  Set `ROImin` above what the target can reach to reproduce the flat-ROC regime.
- `--no-final-sim` — skip the final TI-field simulation (fast; no field render).

## Notes

- Small budgets are fast but not fully converged; `--maxiter 15 --popsize 6` gives
  reasonable results. On macOS SimNIBS falls back to the MUMPS solver (~20 s per FEM
  solve on ernie); expect several minutes per condition, more with the final sim.
- `run_comparison.py` persists `results.json` after every cell, so partial runs are
  never lost. It captures the exact best-montage ROI/non-ROI fields (for ROC curves
  and distributions), the DE trajectory, and the per-channel final-sim meshes (for
  the TI field render and electrode-on-scalp positions, read from the mesh gel tags).
- Targets (MNI): superficial = left M1 hand-knob `[-37,-21,58]`; deep = left
  hippocampus `[-28,-20,-16]` (volumetric). Edit the constants at the top of
  `run_comparison.py` to retarget.
