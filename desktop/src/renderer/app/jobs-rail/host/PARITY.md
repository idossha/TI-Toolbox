# System — parity checklist

Source: `tit/gui/system_monitor_tab.py` (`SystemMonitorTab` + `ProcessMonitorThread`). F2's Phase-0
skeleton already shipped the live `/ws/system` connection, the CPU/Memory charts and the process
table (see `docs/dev/ADR.md` running state, 2026-08-27); this pass finishes the
DESIGN.md §"System screen" list: a disk chart, running jobs, a DooD-siblings placeholder, and
Terminate.

## Controls

| Qt control | Default | v3 equivalent | Status |
|---|---|---|---|
| "System Overview" CPU/Memory labels + Last Update | 0% / 0% / --:--:-- | `CardHeader` value chips (`cpu-value`, `mem-value`, `disk-value` test ids), driven by `/ws/system` | Done (carried over from F2) |
| CPU graph (matplotlib, 60-point rolling window) | — | `LineChart` (uPlot), CPU % over the stream's retained samples | Done (F2) |
| Memory graph | — | `LineChart`, Memory % | Done (F2) |
| *(no Qt equivalent — 2.x had no disk gauge)* | — | `LineChart`, Disk % — DESIGN.md §"System screen" asks for CPU/RAM/**disk** charts explicitly | Done, new this pass |
| Process table: PID / Name / Command / CPU% / Mem% / MB / Time | sortable, alternating rows | `DataTable`: PID / Name / Command / CPU % / RSS (bytes, not raw MB) — "Mem %" and "Time" (per-process runtime) are not in `SystemSnapshot.processes` (`{pid, name, cmdline, cpu_percent, rss, started}`), see gap 1 | Done, two columns narrower than Qt |
| "Terminate Selected Process" button + confirm dialog | select a row, then a button below the table, `QMessageBox.question` | Per-row `IconButton` (destructive, `aria-label`) → `AlertDialog` naming the PID and process name, confirm label repeats the verb ("Terminate process") per DESIGN.md §6 rule 2 | Done — improved: no separate "select a row" step |
| "Manual Refresh" / "Pause Monitoring" / "Clear Graphs" buttons | — | Not carried over: the stream is always live (no manual poll to trigger) and there is no PyQt-style "monitoring thread" to pause — `/ws/system` is the app's single source of truth and pausing it would desync the rest of the app. `useSystemStream`'s shared-connection model does the equivalent of "clear graphs" automatically (a fresh mount starts an empty sample buffer) | Intentionally dropped — no v3 equivalent needed |
| *(no Qt equivalent)* | — | "Running jobs" card, sourced from the same `/ws/jobs` store the rail and Jobs page use (no separate poll) — DESIGN.md §"System screen": "running jobs, DooD siblings" | Done, new this pass |
| *(no Qt equivalent — 2.x ran everything via `docker exec`, no DooD)* | — | "DooD siblings" card: an `EmptyState` placeholder — see gap 2 | Placeholder only, per the lane brief ("DooD siblings placeholder") |

## Known gaps (report to orchestrator / B2)

1. **`SystemSnapshot.processes` has no `memory_percent` or a formatted runtime string.** The Qt
   tab shows both ("Mem%" column, colour-highlighted above 10%; "Time" as `1h 23m`). The contract
   carries `rss` (bytes) and `started` (unix seconds) instead — this page derives elapsed time
   nowhere for processes (only for jobs, via `elapsedLabel`) because `started` alone can't be
   reformatted without duplicating that helper for a slightly different shape, and RSS already
   substitutes for a rough memory picture. Not blocking; a follow-up could add
   `memory_percent`/`runtime` to `SystemSnapshot.processes` to close the last two columns, or this
   page could derive `runtime` client-side from `started` the same way `elapsedLabel` does for jobs.
2. **DooD siblings has no backing data.** Nothing in `SystemSnapshot`, `/api/jobs`, or any catalog
   route reports the `docker stats` view of sibling containers that TODO §2.4's scheduler tracks
   internally (`docker stats --no-stream` for cost accounting) — there is no route exposing it to
   the client. The lane brief calls for a "placeholder" here, which is what this card is; a real
   version needs either a `GET /api/system` field (`dood_containers: [{id, image, cpu_percent,
   mem_bytes, job_id}]`) or a dedicated route, both B1/B2 scope (the scheduler already has the
   data server-side per TODO §2.4).
3. **No host process is currently "unmanaged but toolbox-relevant" in the mock beyond the two
   seeded rows** (`simnibs_python -m tit.sim ...`, `charm ...`) — the E2E test exercises Terminate
   against one of those two, not a live toolbox run. Real-world coverage (a process spawned outside
   any job, e.g. a user's own `simnibs_python -m tit.opt.ex` from a terminal) needs the container
   integration pass (Stage 3), not this mock.
