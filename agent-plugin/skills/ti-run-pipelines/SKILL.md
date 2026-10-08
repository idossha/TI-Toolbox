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
   what it has (`has_sourcedata`, `has_raw`, `has_m2m`, ...), what is already queued or
   running, and `approval_required`. If it says no TI-Toolbox is running, tell the user to
   open the app on their project (or run `tit launch`) — do not try to start one.
2. **The user approves, the app runs** (`approval_required: true`, the default). Put the
   whole pipeline in one `propose_pipeline` call, tell the user it is waiting on the Jobs
   page, then `wait_for_approval`. `submit_job` and `simulate_flex_result` are refused in
   this mode — never try to get around that (no other creator name, no settings change).
   - **Approved:** the app queues the steps itself, each when the steps in its `after`
     have succeeded; you only follow (`wait_for_job` on the returned job ids,
     `get_proposal` for steps not yet queued). If `edited_by_user` is true, say what the
     user changed (`approved_config`) and go with it.
   - **Rejected:** tell the user, quote their note, ask what to change. Never propose
     the same plan again unchanged.
   - `propose_pipeline` returns `proposed: false` with errors when a step does not
     validate; nothing was shown to the user — fix it and propose again.
3. **Never invent** atlas paths, label ids, EEG net names, run names or subject ids. Get
   ROIs from `find_regions`, runs from `wait_for_job`/`get_proposal`, nets from the user or
   a flex run's mappings.
4. **Plan before you propose or submit.** `plan_job` (same arguments as one step) shows
   `errors`, `missing_inputs`, `will_overwrite`, `lock_conflicts`, `eta_minutes`; fix errors
   yourself and tell the user about missing inputs. `propose_pipeline` plans every step
   again in the app, and the card shows the user the same facts.
5. **Overwriting is the user's decision.** If `will_overwrite` is non-empty, prefer a new run
   name (`output_folder: "<name>"` for flex). Pass `overwrite: true` only when the user
   already said to replace; otherwise the card asks them (approval is refused until they
   allow it or rename).
6. **Leave defaults alone.** Send only the fields the user's intent decides; the server
   fills the rest with the same defaults the app's pages use (`get_config_schema` shows them).
7. **One heavy job at a time is fine** — the app's scheduler queues jobs of the same
   product (Pre-processing, Simulator, Optimizer). Do not cancel or resubmit to "speed up".
8. **Follow, don't poll blindly.** `wait_for_approval` and `wait_for_job` wait up to
   `timeout_s` (default 50 s); call again while pending / `done` is false. Preprocessing and
   optimisation run for tens of minutes or more; tell the user the plan's ETA (an estimate)
   and that they can watch the jobs live in the app's Jobs view.
9. **Report results with paths**: the job state, the output folder and the report (`*.html`)
   from `wait_for_job`. On failure, quote the `error` and the last log lines, then check the
   `troubleshooting` wiki page (read-only server) before guessing.

## Recipe: raw scans → head model → optimise → simulate

```text
connect                                               # approval_required: true
inspect_raw_data(path="~/Downloads/scan")            # proposes {"T1w": [...], "T2w": [...]}
  -> confirm the mapping with the user if anything is ambiguous (several T1w candidates,
     "mixed series", no T1w)
stage_raw_data(subject_id="101", mapping={...})       # copies into sourcedata/sub-101/<modality>/
propose_pipeline(title="Head model for sub-101", rationale="...",
  steps=[{"id": "pre", "kind": "pre", "subject_ids": ["101"], "config": {}}])
wait_for_approval(proposal_id=...)                    # then wait_for_job on the step's job ids
find_regions(subject_id="101", query="thalamus")      # atlases exist only after preprocessing
propose_pipeline(title="Maximise the field in the bilateral thalamus", rationale="...",
  steps=[
    {"id": "opt", "kind": "flex", "subject_ids": ["101"],
     "config": {"goal": "mean", "roi": <rois.all>, "output_folder": "thalamus_mean"}},
    {"id": "sim", "kind": "sim_from_flex", "subject_ids": ["101"],
     "config": {"flex_step": "opt"}}])                # electrodes + currents from that run
wait_for_approval(proposal_id=...)
wait_for_job(job_ids=<opt's job ids>)                 # the app queues "sim" when "opt" succeeds
get_proposal(proposal_id=...)                         # -> sim's job ids; wait_for_job on them
```

Two proposals, because an atlas target needs the head model first; with a coordinate target
(`SphericalROI`) or a subject that already has `has_m2m: true`, propose `pre` → `flex` →
`sim_from_flex` (with `after`) in one plan, or skip `pre`. To simulate an existing run, propose
one `sim_from_flex` step with `"flex_run": "<run name>"`.

**Direct mode** (`approval_required: false`, the user turned it on): `plan_job` then
`submit_job` per step, `wait_for_job` between dependent steps, and `simulate_flex_result`
for a flex result.

`subject_id` is without `sub-`. `config` for `pre` takes the Pre-processing page's flags; set
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

- A flex result: a `sim_from_flex` step (`flex_step` or `flex_run`; optional `eeg_net`,
  `intensities` and any `SimulationConfig` field such as `"conductivity": "vn"`, which needs
  DTI) — or, in direct mode, `simulate_flex_result`. Both use the app's rule: the run's
  electrodes (a mapped EEG net if the run has one, or the `eeg_net` you pass, else the
  optimised XYZ positions) and the run's own current.
- A named montage: a `sim` step (or `submit_job` in direct mode) with
  `config={"montages": [{"_type": "Montage", "name": ..., "mode": "net", "electrode_pairs":
  [[a, b], [c, d]], "eeg_net": ...}], "intensities": [mA, mA]}`. Two pairs is TI; four or more
  is mTI with one current per pair.

## When something goes wrong

| Symptom | Do |
|---|---|
| `missing_inputs` from `plan_job` | Read each `how_to_fix`; usually run `pre` first |
| HTTP 403 on submit | Approval is required: use `propose_pipeline` |
| A step `error` / `skipped` in `get_proposal` | Tell the user; they can retry the step from the card once the cause is fixed |
| HTTP 422 on submit | The detail names the field; fix it and plan again |
| HTTP 409 / overwrite refusal | Ask the user; resubmit with `overwrite: true` or a new run name |
| Job `failed` | Quote `error.message` + `log_tail`; check `read_wiki_page("troubleshooting")` |
| Job `lost` | The server restarted mid-run; resubmit after telling the user |
| "Several TI-Toolbox projects are open" | Ask which project; `connect(project=<path>)` |
