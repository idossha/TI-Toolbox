---
name: troubleshoot-project
description: Diagnose a TI-Toolbox project directory — which subjects, head models, simulations, optimizations, jobs and reports exist, and what is missing for the user's goal.
argument-hint: [project-root] [subject-id]
---

# Troubleshoot a TI-Toolbox project

Before anything else, `read_wiki_page("troubleshooting")` — the verified archive of
known problems. Match the user's error text against it first; only investigate
further when nothing matches. If you find a new, confirmed cause, tell the user to
report it in GitHub Discussions (Q&A) so it can be added.

Take `<project-root> [subject-id]` from the user request (or `$ARGUMENTS` in
clients that provide it). If no project root is given, ask for it (inside the container it is `/mnt/<project>`; on the host it is
the folder the desktop app or `--project` was pointed at).

## 1. Look before you diagnose

Call MCP `inspect_project(project_root, subject?)`. It reports both halves of a v3
project: the BIDS derivatives, and the `code/ti-toolbox/` tree — the job store
(counts by state plus recent failures with their `error.type`), notebooks,
pipelines and viewer scenes.

## 2. Walk the pipeline and report the first missing stage

- `anat_files` empty → needs DICOM/NIfTI import (`pre-processing` wiki).
- `has_m2m` / `has_head_mesh` false → CHARM not run or failed; check
  `derivatives/SimNIBS/sub-<id>/m2m_<id>/charm_log.html`.
- `freesurfer_recon` false → atlas / cortical ROI features unavailable.
- `leadfields` empty → ex-search cannot run; build a leadfield first (`ex-search`).
- A simulation with no `mesh_files` / `nifti_files` → the run failed; go to step 3.
- `qsirecon` false but the user wants `vn`/`dir`/`mc` conductivity → needs
  diffusion processing.
- A flex/ex/mex run directory that does not appear at all → the catalog
  deliberately ignores a run with no completion manifest (`flex_meta.json`,
  `run_config.json`), so a cancelled or in-progress run never shows as a result.

## 3. Read the job, not just the output directory

In v3 the evidence is in the job store, `<project>/code/ti-toolbox/jobs/<id>/`:
`spec.json` (the exact config that ran), `status.json` (state, exit code, error),
`events.jsonl` and `stdout.log`. States are `queued running succeeded failed
cancelled skipped lost`. Map the `error.type` to what to tell the user:

| `error.type` | Shown as | What it means |
|---|---|---|
| `preflight` | Preflight check failed | Inputs were missing before anything ran — go back to step 2. |
| `lock_wait` / `budget_wait` | Waiting on a lock / on the resource budget | Not a failure. Another job holds the resource. |
| `runner_failed` | Runner failed | The module raised. Read the last lines of `stdout.log`. |
| `oom_suspected` | Likely out of memory | Raise Docker's memory (32 GB+ for diffusion), or run fewer jobs at once. |
| `cancelled` / `skipped` | Cancelled / Skipped | A user cancelled it, or a dependency failed or was unknown. |
| **`lost`** | **Lost (server restarted mid-run)** | The server restarted while it ran. The job is over and will not resume — re-submit it. |
| `docker_unavailable` | Docker is unavailable | The daemon is not running, or the socket is not mounted. |
| `kind_error` | Invalid job configuration | The config does not match the job kind. |

A job stuck at `running` with nothing behind it is the known re-adoption gap: the
manager holds the child pid in memory only, so a server restart strands it.
`POST /api/jobs/{id}/force` frees it and lands it in `lost`.

## 4. Won't start at all

- **Image not found on the first run** — the tag is not published yet (a
  pre-release checkout). The launcher says so and names the fix: build it with
  `container/blueprint/build.sh --tag <image>`, or pass `--image` with a tag they
  already have (`docker images idossha/ti-toolbox`). The first legitimate pull is
  ~2.3 GB and slow; that is not a hang.
- **Version lockstep** — the desktop app resolves an image tag from its own
  version, so a mismatch between `desktop/package.json`, `tit/__init__.py` and the
  compose default means the app asks for a tag nobody built. `get_toolbox_version`
  reports both versions and whether they agree; `dev/update/update_version.py` is
  the only correct way to change them.
- **Nothing to paste** — the bearer token lives only in the container's
  environment. If a user is hunting for a token to enter, that is the wrong
  question.
- The host needs only CPython ≥ 3.11 and the `docker` CLI. `list_launch_paths`
  gives the three supported ways to start.

## 5. Configs

- Montages: `read_project_config(project_root, "montage_list.json")` — confirm the
  name and EEG net exist, exactly (net names are real filenames, e.g.
  `GSN-HydroCel-185.csv`).
- Pipelines: `read_project_config(project_root, "<name>.json", where="pipelines")`.
- Viewer scenes: `where="viewer"` (`<kind>.tetravox.json`).
- Free-hand electrodes: `where="stim_configs", subject="<id>"` — reads
  `m2m_<id>/stim_configs/*.json`, shaped
  `{"name", "type": "U"|"M", "electrode_positions": {label: [x, y, z]}}` in
  subject-RAS millimetres. Only the first four positions are used, so an
  mTI free-hand config will not resolve.

## 6. Report

Summarise as a short table: subject → stages present/missing → next action, each
with the relevant wiki slug, plus a line per failed job (`kind`, `error.type`, the
last meaningful line of `stdout.log`). **Do not modify any files.**
