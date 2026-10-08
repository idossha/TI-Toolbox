---
name: ti-run-pipelines
description: Run TI-Toolbox pipelines for the user through the app they have open — stage raw DICOM/NIfTI into BIDS, preprocess (charm head model), flex-search or ex-search optimisation, simulate a montage or an optimisation result, and follow the jobs. Use when the user asks you to DO something with their data in TI-Toolbox ("preprocess sub-101", "optimise for the thalamus", "simulate the best montage"), not to explain it. Needs the ti-toolbox-jobs MCP server.
user-invocable: false
---

# Running TI-Toolbox pipelines for the user

You drive the TI-Toolbox the user already has open, through the `ti-toolbox-jobs` MCP
server. Every job you submit goes through the app's own job server: it appears live in the
desktop app's job list and terminal, and writes exactly the records, outputs and reports a
job started from the app writes. You never run `simnibs_python` yourself and never write
into `derivatives/` by hand.

## Rules

1. **`connect` first**, every session. It tells you the project folder, every subject and
   what it has (`has_sourcedata`, `has_raw`, `has_m2m`, ...), and what is already queued or
   running. If it says no TI-Toolbox is running, tell the user to open the app on their
   project (or run `tit launch`) — do not try to start one.
2. **Never invent** atlas paths, label ids, EEG net names, run names or subject ids. Get
   ROIs from `find_regions`, runs from `wait_for_job`/`simulate_flex_result`, nets from the
   user or a flex run's mappings.
3. **`plan_job` before every `submit_job`**, with the same arguments. Read `errors`,
   `missing_inputs`, `will_overwrite`, `lock_conflicts`, `eta_minutes`. Fix errors yourself;
   tell the user about missing inputs.
4. **Overwriting is the user's decision.** If `will_overwrite` is non-empty, say which
   folders would be replaced and ask. Only then pass `overwrite: true`. Prefer a new run
   name (`output_folder: "<name>"` for flex) over replacing.
5. **Leave defaults alone.** Send only the fields the user's intent decides; the server
   fills the rest with the same defaults the app's pages use (`get_config_schema` shows them).
6. **One heavy job at a time is fine** — the app's scheduler queues jobs of the same
   product (Pre-processing, Simulator, Optimizer). Do not cancel or resubmit to "speed up".
7. **Follow, don't poll blindly.** `wait_for_job(job_ids)` waits up to `timeout_s` (default
   50 s); call it again while `done` is false. Preprocessing and optimisation run for tens of
   minutes or more; tell the user `plan_job`'s `eta_minutes` (an estimate) and that they can
   watch the job live in the app's Jobs view.
8. **Report results with paths**: the job state, the output folder and the report (`*.html`)
   from `wait_for_job`. On failure, quote the `error` and the last log lines, then check the
   `troubleshooting` wiki page (read-only server) before guessing.

## Recipe: raw scans → head model → optimise → simulate

```text
connect
inspect_raw_data(path="~/Downloads/scan")            # proposes {"T1w": [...], "T2w": [...]}
  -> confirm the mapping with the user if anything is ambiguous (several T1w candidates,
     "mixed series", no T1w)
stage_raw_data(subject_id="101", mapping={...})       # copies into sourcedata/sub-101/<modality>/
plan_job(kind="pre", subject_ids=["101"], config={})  # app defaults: DICOM import, FastSurfer, charm
submit_job(kind="pre", subject_ids=["101"], config={})
wait_for_job(job_ids=[...])                           # repeat until done; every stage must succeed
find_regions(subject_id="101", query="thalamus")      # -> atlases[].rois.{all,left,right}
plan_job(kind="flex", subject_ids=["101"], config={"goal": "mean", "roi": <rois.all>,
         "output_folder": "thalamus_mean"})
submit_job(<same>)
wait_for_job(job_ids=[...])
simulate_flex_result(subject_id="101", flex_run="thalamus_mean")
wait_for_job(job_ids=[...])                           # report the simulation folder + report
```

`subject_id` is without `sub-`. A subject that already has `has_m2m: true` skips straight to
the optimisation. `config` for `pre` takes the Pre-processing page's flags; set
`run_fastsurfer: false` only if the user says so (it supplies the subcortical atlases).

## Translating intent into a flex-search config

| The user says | Send |
|---|---|
| "high / maximum intensity", "strongest field in X" | `goal: "mean"` (mean field in the ROI); `"max"` only for "peak" |
| "focal", "spare the rest of the brain" | `goal: "focality_tf"`, `intensity_weight` 0 (balanced) to 1 (favour intensity) |
| "focality with thresholds" | kind `flex_adaptive` (the app's default focality mode), `goal: "focality"` |
| "bilateral X", "both X" | `roi: rois.all` from `find_regions` (union of left and right) |
| "left X" / "right X" | `rois.left` / `rois.right` |
| "N mA" | `current_mA: N` (per channel; total is 2N). Otherwise leave the 1 mA default — field scales linearly with current, so the placement is what the search decides |
| "map to <net>", "use the 10-10 cap" | `enable_mapping: true, eeg_net: "<net file>.csv"` |
| "more thorough" | `n_multistart: 3` (or more); it is the only thing CPUs parallelise |

ROI choice: `find_regions` returns `SubcorticalROI` (volume atlas — deep structures such as
thalamus, hippocampus, amygdala) and `AtlasROI` (cortical surface atlas). Paste the object
verbatim into `roi`. For a target given as coordinates use
`{"_type": "SphericalROI", "x": [..], "y": [..], "z": [..], "radius": [..], "use_mni": true,
"volumetric": true, "tissues": "GM"}` — `volumetric: true` for deep targets. ex-search takes
different targets (an ROI CSV and a leadfield); read `get_config_schema(kind="ex")` first.

## Simulating

- A flex result: `simulate_flex_result` picks the run's electrodes (a mapped EEG net if the
  run has one, or `eeg_net` you pass, else the optimised XYZ positions) and the run's own
  current, plans, and submits — or stops and asks when a simulation of that run exists.
  `overrides` takes extra `SimulationConfig` fields (e.g. `{"conductivity": "vn"}`, which
  needs DTI).
- A named montage: `submit_job(kind="sim", config={"montages": [{"_type": "Montage",
  "name": ..., "mode": "net", "electrode_pairs": [[a, b], [c, d]], "eeg_net": ...}],
  "intensities": [mA, mA]})`. Two pairs is TI; four or more is mTI with one current per pair.

## When something goes wrong

| Symptom | Do |
|---|---|
| `missing_inputs` from `plan_job` | Read each `how_to_fix`; usually run `pre` first |
| HTTP 422 on submit | The detail names the field; fix it and plan again |
| HTTP 409 / overwrite refusal | Ask the user; resubmit with `overwrite: true` or a new run name |
| Job `failed` | Quote `error.message` + `log_tail`; check `read_wiki_page("troubleshooting")` |
| Job `lost` | The server restarted mid-run; resubmit after telling the user |
| "Several TI-Toolbox projects are open" | Ask which project; `connect(project=<path>)` |
