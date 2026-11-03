# Recorded UI payloads (decision P5)

Lane S2's Playwright `real` project writes the **exact** `POST /api/jobs` (or
`POST /api/jobs/groups`) body each run page submitted into this directory, one file per row:

```
tests/smoke/payloads/<row id>.json     # preferred (e.g. sim_ti.json)
tests/smoke/payloads/<kind>.json       # fallback  (e.g. sim.json)
```

The file may be either the full request body (`{"kind", "config", "subject_ids", …}`) or a bare
config object; `tests/smoke/test_kinds.py::_load_submission` accepts both and reports which
source it used in the results table (`source` column: `payload` or `builtin`).

**Why this exists.** The `flex` failure on 2026-09-03 was a *shape* disagreement: the UI emitted
`atlas_path: string[]`, the runner assumed a scalar, and each side passed its own tests. Replaying
the UI's real body through Level A catches a config→runner divergence with the same JSON that
Level B used to catch a UI→config one.

**Safety.** A recorded payload is not namespaced by the harness, so it can name a real output.
Before submitting one, `test_kinds.py` asks `POST /api/plan/{kind}` whether the output already
exists and **skips the row** rather than overwrite it (decision P6). Re-record the payload with a
`smoke-` name if you want that row to run.

**Re-pointed inputs.** Dataset 000 lost the runs some payloads were recorded on. On 2026-11-03
`analyzer.json` and `analyzer-voxel.json` were moved from ernie's `Thalamus` to
`AF3_PO10_and_AF4_Oz`, `flex.json` from ernie's DK40 annotation (its `m2m_ernie` has no
`segmentation/`) to sub-101's, and `nifti_average.json` and `stats.json` from the `L_Insula` runs of
101, ernie and MNI152 to 101 `L_Insula`, ernie `AF3_PO10_and_AF4_Oz` and CHN
`left_insula_mean`; only those subject and simulation names changed, every other field is as
recorded.
