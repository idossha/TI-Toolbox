# Lane TM — R2: shared terminal, scrollable and locally clearable (2026-09-05)

Plan of record: `desktop/IMPLEMENTATION_PLAN.md` §R2. Nothing committed (worktree WIP rule).

## What changed

Most of R2's *implementation* was already present in the untracked `desktop/` WIP when this lane
opened; this lane verified it against the plan's semantics and closed the gate's missing evidence.

| File | Change |
| --- | --- |
| `desktop/tests/e2e/terminal.spec.ts` | **New.** The R2 geometry gate: real layout, both axes, scroll offsets, local Clear. |
| `desktop/tests/unit/job-console.test.tsx` | Input line array is now `Object.freeze`d as well as deep-compared, so a Clear implemented as a splice fails loudly instead of silently. |
| `desktop/tests/e2e/preprocess.spec.ts` | Minimal run-page assertion: whichever log source the run page shows (`live`/`file`), it carries the shared `Follow tail` switch and `Clear terminal` control. |

Verified-as-already-conforming (unchanged by this lane):

- `src/renderer/app/jobs/logLines.ts` is the one pure module for event→line conversion
  (`jobEventsToLogLines`) and sequence merging (`mergeJobEvents`); both `pages/_shared/run/JobTerminal.tsx`
  and `app/jobs-rail/ConsolePane.tsx` import it and neither carries its own copy.
- `ui/Jobs.tsx::JobConsole` is the single interactive renderer (run pages, Jobs rail, gallery). Clear is a
  per-source `clearedThrough` sequence watermark over the caller's array — no mutation, no truncation,
  server events and log files untouched; lines with `seq > clearedThrough` render normally.
- `sourceKey` (`job:<id>` / `file:<path>`) keys the inner component, so switching source resets the
  watermark and the text filter; `follow` lives in the outer component and is therefore retained.
- Overflow/virtualisation unchanged: `.job-console-lines { overflow: auto }` + `.job-console-line
  { white-space: pre }`, rows via `ui/VirtualList.tsx`.
- Jobs-detail `<pre>` excerpts untouched.

## Gate evidence

Commands run from `desktop/`.

| Gate clause | Command | Result |
| --- | --- | --- |
| 100-line console `scrollHeight > clientHeight`; long line `scrollWidth > clientWidth`; scrolling changes both offsets; Clear removes all rendered lines | `npx playwright test tests/e2e/terminal.spec.ts` | `1 passed (5.5s)` — measured `clientWidth 420 / scrollWidth 4076` on the gallery console |
| Clear leaves the input array byte-for-byte unchanged (frozen + deep-equal), shows the next higher-sequence line, watermark does not carry to another source key, filter resets | `npx vitest run tests/unit/job-console.test.tsx tests/unit/job-log-lines.test.ts` | `2 files, 4 tests passed` |
| Same shared control on a run page | `npx playwright test tests/e2e/preprocess.spec.ts -g "never an empty box"` | `1 passed` (terminal `data-source=file`, so the Follow/Clear branch really executed — confirmed with a temporary log line) |
| Same shared control in the Jobs rail | `npx playwright test tests/e2e/jobs.spec.ts` | `11 passed (57.0s)` (includes the existing `Clear terminal` assertion on the Console tab) |
| No regressions | `pnpm run typecheck`; `npx eslint <lane files>`; `pnpm run test` | clean; clean; `79 files / 889 tests passed` |

Full-suite reference run (`pnpm run e2e`, 9.8 min): `147 passed, 3 skipped, 4 failed` — see below; none of
the four are R2 files.

## Open items / findings for other lanes

1. **`tests/e2e/gallery.spec.ts:40` is red** ("the shared console scrolls in both directions and clears
   locally") and is not in this lane's ownership. Cause is the *test*, not the product: it assigns
   `scrollTop` and `scrollLeft` inside one `evaluate`, and the read-back `scrollLeft` is 0. Splitting them
   into two `evaluate` calls (and unchecking `Follow tail` first, since follow-tail's `scrollToIndex`
   re-parks the box) makes the identical assertions pass — that is exactly what `terminal.spec.ts` does.
   Proposed change: delete that test as superseded by `tests/e2e/terminal.spec.ts`, or apply the split.
2. **Optional product improvement, `src/renderer/ui/VirtualList.tsx` (not owned):** follow-tail calls
   `virtualizer.scrollToIndex(...)` on every commit, which resets `scrollLeft` to 0, so a user cannot read
   a long line sideways while following. Exact change: capture `parentRef.current.scrollLeft` before the
   `scrollToIndex` in the `requestAnimationFrame` callback and restore it afterwards.
3. **Other red specs in the full run, all outside R2:** `preprocess.spec.ts:134` (POST
   `/api/jobs/groups` body assertions — R3 batch lane), `table-room.spec.ts:201` and `viewer.spec.ts:319`
   (both fail on `gotoPage(page, …, "Subjects")` — the R1 Overview rename).

## Proposed record entries (for the consolidation lane)

- **DESIGN.md §4.6 wording:** "Clear is local and presentational: a per-source sequence watermark hides the
  lines currently on screen. It never deletes server events or truncates a log file; lines with a higher
  sequence appear normally, and changing job/file source resets the watermark while Follow is retained and
  the text filter resets."
- **ARCHITECTURE.md (renderer):** `app/jobs/logLines.ts` is the single pure event→line + sequence-merge
  module; `ui/Jobs.tsx::JobConsole` is the single interactive log renderer for run pages, the Jobs rail and
  the gallery. Jobs-detail `<pre>` excerpts remain diagnostic records, not terminals.
- **DECISIONS.md:** "Terminal Clear is presentational, not destructive" — recoverable by changing source or
  by new output; raw logs and the event stream stay intact.
- No contract change: R2 touches no API surface.
