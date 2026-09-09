---
layout: wiki
title: Jobs
permalink: /wiki/jobs/
---

# Jobs

Everything long-running in TI-Toolbox v3 is a **job**: pre-processing, a simulation, a search, an
analysis, a report, a group statistic, a Blender export. A page never runs work in its own process,
so a page never has a Stop button and never has a console of its own. Both live here.

<img src="{{ site.baseurl }}/assets/imgs/v3/jobs.png" alt="The Jobs page: a filterable table of every job the server knows about" style="width: 100%; max-width: 1000px;">
<em>The Jobs page (⌘9). One row per job: state, kind, subjects, stage, elapsed time, CPU and memory.</em>

## Where jobs appear

- **The Jobs rail** at the bottom of every page — a one-line summary ("2 running"), expanded to a
  260 px panel with ⌘J. Its tabs are **Jobs** and **Host** — Host being the quick glance at the
  machine (CPU, memory, disk, toolbox processes) without leaving the page you are on; the
  full-height version is the **System** page, pinned at the bottom of the rail above Settings. The Jobs tab is the table beside the
  selected job's detail pane, split by a divider you can **drag**, **double-click to reset**, and
  which is remembered between sessions.
- **The Jobs page** (⌘9) — the full table with filters and a detail pane.
- **A run page's right pane** — the **Terminal** tab shows the console of the job that page just
  submitted, beside the **Scene** tab.

## The table

Filters for **state**, **kind** and **subject**, a free-text filter, and a **grouping toggle**: the
same list rendered either flat (one row per job) or as a tree of *group → subject → stage*. A
batch you submitted from a run page, and a whole pipeline run, are each **one group**, so they can
be watched and cancelled as one thing.

| Column | Notes |
|---|---|
| **State** | `queued · running · succeeded · failed · cancelled` |
| **Kind** | `pre · sim · flex · flex_adaptive · flex_pareto · ex · mex · analyzer · source · stats · report · nilearn · nifti_average · blender` |
| **Subjects** | Every subject the job covers |
| **Stage** | The runner's own current stage and its percentage, e.g. `DICOM conversion · 40 %` |
| **Elapsed / CPU / RSS** | Live from the server, not estimated |

## The detail pane

Select a row — in the panel or on the page — and the pane on the right opens with:

- **Summary** — kind, subjects, group, created, elapsed, CPU, RSS and exit code, plus (on the
  full page) the last 40 lines of the console.
- **Raw log** — the whole log: streamed over `/ws/jobs`, backfilled over REST, falling back to the
  log file on disk for a job whose events the server no longer holds. Level colouring, a filter,
  follow-tail and **Clear** are in the console's own toolbar.
- **Artifacts** — what the job wrote, with Open (into the Viewer) and Reveal. A generated **report**
  is one of these; browse reports in **Results**.
- **Actions** — Stop, Rerun, Force and Delete, in the pane's header row.

When a job fails, the pane names *which kind* of failure it was rather than only printing a
traceback: `preflight`, `lock_wait`, `budget_wait`, `runner_failed`, `oom_suspected`, `cancelled`,
`skipped`, `lost`, `docker_unavailable` — plus the last 20 lines of the log.

**Clear** on any console is a per-view watermark. It hides what you have already read in *that*
view; it never deletes a server event and never truncates a log file on disk.

## Batches, groups and parallelism

A run page submits its whole table as **one request** (`POST /api/jobs/groups`) carrying one
template config plus per-subject overrides, and gets one `group_id` back. Two consequences worth
knowing:

- A table that mixes two job kinds becomes **one group per kind**, and the page says so — *"Queued
  3 searches in 2 groups (ex, flex)"* — rather than implying an atomic batch.
- **Subjects running in parallel** (on Pre-processing) is a scheduler admission cap on that group.
  It counts jobs, not subjects. Leave it at 1 unless you know the box can take it: two FEM-class
  jobs at once will contend for memory and finish later than they would in sequence.

## Server restart

A server restart deliberately interrupts work; it does not resume or automatically resubmit
jobs. Startup reconciliation marks queued jobs **failed**, with an interrupted-before-start
reason. For a running job, it stops any verified surviving runner process tree and associated
job containers, then marks the job **failed** as interrupted. If the runner has already exited
and its saved events record a real exit, the job instead retains that actual **succeeded** or
**failed** outcome. These transitions are persisted before the server accepts new requests.

Review the job's outcome and outputs, then explicitly submit a new run if needed. Reopening a
browser or reconnecting a client to a server that stayed running is different from restarting
the server; client disconnection alone does not trigger this reconciliation.

## Replacing existing outputs

Existing outputs require a fresh confirmation each time you run. **Replace and rerun**
is available only when **Settings → Allow unsafe overrides** is enabled for the current
project; it is disabled by default. **Skip** keeps existing results and runs only missing
work; **Cancel** submits nothing. The permission is project-specific so another dataset
does not inherit it, and API submissions are checked too.

A pipeline's **Skip pipeline** option submits no jobs: its dependent steps cannot be
partially skipped safely. Replacement is unavailable when dependent outputs cannot yet
be previewed.
