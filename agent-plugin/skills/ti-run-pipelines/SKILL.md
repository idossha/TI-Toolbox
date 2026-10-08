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
2. **Ask before you guess.** Before proposing, check the request names: the subject(s); the
   target (region or coordinates); what to run (simulate a given montage, optimise first, or
   both); the goal or intensity; the electrode net when it matters. If anything consequential
   is missing or ambiguous, do not pick for the user. Ask ONE question offering two paths:
   "I can propose a sensible default flow (<the flow in one line>), or ask you a few quick
   questions." In Claude Code use the AskUserQuestion tool with those two short options; in
   Codex ask in plain text. If they pick questions, ask at most 3–4 focused ones, each with
   the recommended default first. Fill low-stakes gaps (run names, output folders) yourself.
   *Worked example.* "Run a left insula simulation for subject CHN" names a subject and a
   target but not a montage, so "simulate" could mean a montage they have or an optimised
   one. Ask: "Default: flex-search for the strongest mean field in the left insula (DK40) at
   1 mA, then simulate the best montage — or a few quick questions (montage, goal, current)?"
   Never decide silently ("You did not name a montage, so…").
3. **The user approves, the app runs** (`approval_required: true`, the default). Put the
   whole pipeline in one `propose_pipeline` call. `submit_job` and `simulate_flex_result`
   are refused in this mode — never try to get around that (no other creator name, no
   settings change). `propose_pipeline` returns `proposed: false` with errors when a step
   does not validate; nothing was shown to the user — fix it and propose again.
4. **Never keep the user waiting on a tool.** After proposing, write one line ("It's waiting
   for your approval on the Jobs page; I'll pick it up from there.") and make
   `watch_proposal(proposal_id)` the last call of the turn. It returns on the next change
   only — approved, rejected, a step finished, all done.
   - **Claude Code** moves the call to the background (after 5 s from the Assistant page,
     2 min elsewhere, or at once when the user types) and wakes you with its result. End your
     turn as soon as it is backgrounded; the user keeps chatting. Keep one watch per
     proposal; to answer "status" meanwhile, use `get_proposal` (it returns at once).
   - **Codex** has no background calls: `watch_proposal` returns within 45 s. If nothing
     changed, end the turn telling the user to say "status" anytime; then call
     `watch_proposal(proposal_id, timeout_s=0)` and report what changed.
   - **On each wake-up** report only what changed, in two or three lines: approved (and what
     the user edited, `approved_config` — go with it); a finished step's state, output
     folder, report (`*.html`) and key numbers from `log_tail`. Then watch again.
     `changed: false` means nothing happened: say nothing and watch again.
   - **Rejected:** tell the user, quote their note, ask what to change. Never propose the
     same plan again unchanged.
   - **`done: true`:** a short final summary of every step, then stop watching.
5. **Never invent** atlas paths, label ids, EEG net names, run names or subject ids. Get
   ROIs from `find_regions`, runs from `watch_proposal`/`get_proposal`, nets from the user or
   a flex run's mappings.
6. **Plan before you propose or submit.** `plan_job` (same arguments as one step) shows
   `errors`, `missing_inputs`, `will_overwrite`, `lock_conflicts`, `eta_minutes`; fix errors
   yourself and tell the user about missing inputs. `propose_pipeline` plans every step
   again in the app, and the card shows the user the same facts.
7. **Overwriting is the user's decision.** If `will_overwrite` is non-empty, prefer a new run
   name (`output_folder: "<name>"` for flex). Pass `overwrite: true` only when the user
   already said to replace; otherwise the card asks them (approval is refused until they
   allow it or rename).
8. **Leave defaults alone.** Send only the fields the user's intent decides; the server
   fills the rest with the same defaults the app's pages use (`get_config_schema` shows them).
9. **One heavy job at a time is fine** — the app's scheduler queues jobs of the same
   product (Pre-processing, Simulator, Optimizer). Do not cancel or resubmit to "speed up".
10. **Tell the user the ETA** (the plan's estimate) when you propose: preprocessing and
   optimisation run for tens of minutes or more, and the app's Jobs view shows them live.
11. **Report results with paths**: the job state, the output folder and the report (`*.html`)
   from `watch_proposal` (`finished`) or `wait_for_job`. On failure, quote the `error` and the last log lines, then check the
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
watch_proposal(proposal_id=...)                       # last call of the turn; wakes you on changes
find_regions(subject_id="101", query="thalamus")      # atlases exist only after preprocessing
propose_pipeline(title="Maximise the field in the bilateral thalamus", rationale="...",
  steps=[
    {"id": "opt", "kind": "flex", "subject_ids": ["101"],
     "config": {"goal": "mean", "roi": <rois.all>, "output_folder": "thalamus_mean"}},
    {"id": "sim", "kind": "sim_from_flex", "subject_ids": ["101"],
     "config": {"flex_step": "opt"}}])                # electrodes + currents from that run
watch_proposal(proposal_id=...)                       # -> approved; watch again
                                                      # -> opt succeeded (the app queues sim); again
                                                      # -> sim succeeded, done: final summary
```

Two proposals, because an atlas target needs the head model first; with a coordinate target
(`SphericalROI`) or a subject that already has `has_m2m: true`, propose `pre` → `flex` →
`sim_from_flex` (with `after`) in one plan, or skip `pre`. To simulate an existing run, propose
one `sim_from_flex` step with `"flex_run": "<run name>"`.

**Direct mode** (`approval_required: false`, the user turned it on): `plan_job` then
`submit_job` per step, `wait_for_job` between dependent steps (also the last call of a turn —
it backgrounds like `watch_proposal`), and `simulate_flex_result` for a flex result.

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
