# Lane B3 — Optimizer merge (Flex / Ex / mEx into one page)

Branch `feature/v3-electron-gui`, worktree `.claude/worktrees/v3-electron-gui`.
Spec of record: `desktop/DESIGN.md` v3 §2, §4.5, §4.6, §9, §11, §12; `wireframes.md` §4;
`u0-design-notes.md` §3; orchestrator decisions Q1–Q5.
Parity ledger (every control, where it went): `desktop/src/renderer/pages/optimizer/PARITY.md`.

## What shipped

One page `optimizer` (title **Optimizer**, ⌘4 per Q5, icon `Target`), replacing `optimizer-flex`
and `optimizer-ex`, both deleted with their specs and their two `PARITY.md`s (merged into one).

- **Method segment** `⟨Flex │ Ex │ mEx⟩` is the first row of the work pane, beside **Run name**.
- **One ROI picker.** `pages/_shared/roi`'s `RoiPicker` gained a fourth mode, `saved` — the ex/mEx
  target mechanism (saved ROI CSVs, Add/delete dialog, radius, coordinate space, Combine). Flex
  uses `["cortical","subcortical","spherical"]`, ex/mEx `["saved","subcortical"]`, mEx with
  `allowCombine={false}` so the control that the Qt tab disabled simply does not exist.
- **Ex/mEx leadfield is a gate, not a field**: a 28 px precondition strip under the segment, with
  the net select, a size chip when it exists, and `required` + `Generate (≈40 min)` when it does not.
- **Right pane is B2's `RunPanel`** (`kind` follows the segment, `jobKinds={["flex","ex","mex"]}`).
  For ex/mEx the page runs one `POST /api/plan/{kind}` per ROI target and merges them into one
  `PlanResult`, stamping `PlanJob.label` with the target name so the **grid's columns are the
  targets** — a two-ROI ex-search shows two columns of one chip each. Without the stamp every
  target collapses into one column, because the mock (and the real server before a run name is
  typed) resolves the same output directory for all of them.
- **Search cost, stated twice from one function** (`cost.ts`, unit-tested): beside the control that
  changes it and in the action-bar digest.
  `Ex: "4 electrodes · 7 splits · 7 combinations"`, `mEx: "N electrodes · 4 pairs · K combinations"`,
  `Flex: "population 13 × 500 generations ≈ 6,500 solves"`.
- Status cells `lastJob` / `planCost` via `useStatusCells`; `⌘⏎` via `useRunShortcut`; no page header.
- Subject comes from the shell switcher (U6). Flex batches across `useSubject().selection`; Ex/mEx
  run for the primary subject, because the leadfield is resolved per subject.

## Dev loop — the numbers, per round

Instrument: `tests/e2e/_metrics.ts` (`captureScreen` / `deadSpaceRatio` / `firstScreenControls`),
run under `scripts/e2e-quiet-check.sh` (every round reported **PASS**, no window reached the
screen). Populated state: subject `ernie`, cortical DK40 → `L · bankssts`, a flex job queued.

| round | 1280×800 dead | 1440×900 dead | work pane @1280 | right pane @1280 | first-screen hidden | what changed |
|---|---|---|---|---|---|---|
| R1 `b3-r1c-29431` | **0.7473** | 0.7571 | — | — | `[]` (16/16) | first build |
| R2 `b3-r2-949` | 0.7443 | 0.7705 | 0.6680 | 0.8593 | `[]` | short option labels; multi-control fields span the row; `--field-label-w` 128; `.run-work` gap 8 |
| R2b `b3-r2b-29533` | 0.7339 | 0.7705 | **0.6520** | 0.8593 | `[]` | **the real defect**: `FormSection` already wraps children in `.form-grid`, so every nested `.form-grid` I wrote was squeezed into one 184 px column — removed all of them; the ROI picker spans the row |
| R3b `b3-r3b-23583` (final) | **0.7365** | **0.7461** | **0.6520** | 0.8690 | `[]` (Flex 18/18, Ex 39/39, mEx 39/39) | two-up from a 700 px container, not 760 — at 1440 `--page-pad` 24 took `.run-work` to ~722 px and the form went **single-column**, the opposite of §2.1 |

Final panes: 1280 `{nav 56, content 1224, work 826, right 360, gap 6}`;
1440 `{nav 216, content 1224, work 770, right 400, gap 6}`. `pageHeaderHeight` 0 in all four.
Status cells: `lastJob`, `planCost` (+ the shell's `connection`, `version`). No `ras`, no dashes.

### Self-critique against DESIGN.md §12.4 / plan §3 (final round)

1. **Dead space ≤ 22 % — FAIL, 0.7365 @1280 / 0.7461 @1440.** See "the limit I could not meet".
   No pane exists without content: `panes.right` is 360/400 and always holds the plan + terminal.
2. Nothing restates the nav label; **no page header** — `pageHeaderHeight === 0`, asserted. PASS.
3. Every chip is from the shared vocabulary — the plan chips come from B2's `PLAN_CHIP_KIND`; the
   leadfield strip uses `Chip kind="success"|"danger"`. No ad-hoc colours (`optimizer.css` is
   tokens only). PASS.
4. Numbers tabular, units suffixed, paths mono: cost line is `tabular-nums`; the plan cell's
   `output_dir` is the cell tooltip. PASS.
5. Both themes captured at both sizes; no literal colours in the page's CSS or TSX. PASS.
6. Status bar shows only `lastJob` + `planCost` + the shell cluster; asserted `statusCells`
   contains `lastJob` and the bar contains no "—". PASS.
7. `firstScreenControls(page).hidden === []` at 1280×800 **for all three methods** (18 / 39 / 39
   controls). PASS.
8. `⌘⏎` runs the primary (`useRunShortcut`, ignored while a dialog owns the document). PASS.
9. Copy: sentence case, verbs on buttons ("Run flex search", "Generate (≈40 min)"), no exclamation
   marks, no Freeview/Gmsh/X11 (the spherical picker's viewer button deep-links the embed). PASS.
10. Spec asserts DOM state and measured geometry, never pixels; 6 tests, quiet. PASS.

### The limit I could not meet, and why

**Dead space ≤ 22 % (§12.3) is not reachable by any form-shaped run page with this instrument.**
Measured at the same commit, lane B2's `preprocess` — the reference implementation of shape A —
scores **0.7967 @1280 / 0.8334 @1440**; the Optimizer scores 0.7365 / 0.7461, i.e. it is already
6–9 points *better* than the reference page. The instrument counts a sample as content only when
the topmost element is a control, a leaf with text, or a small tinted box; a label-left form row is
28 px of content in a 36 px row, and the gutter between two rows is dead by definition. The number
in §12.3 was derived from U0's **cell-occupancy pixel proxy** (a different quantity: any pixel
differing from the ground counts, so a border or a tint marks a whole 16 px cell as content), and
the two are not comparable — u0 §1.1 predicted the DOM metric would be "no better", and it is in
fact far worse for forms.

Per-pane, at 1280: **work 0.652** (the half this lane owns) and **right 0.869** (B2's `RunPanel`,
whose terminal is empty against the mock because a queued job emits no log lines). The spec
therefore asserts what this lane can defend — `work ≤ 0.70`, plus a whole-box regression guard at
0.78 — and states the §12.3 gap in a comment rather than silently relaxing it.

**Recommendation to the orchestrator:** either restate §12.3's limit per shape (a form pane cannot
beat ~0.65 with this definition; the Viewer's canvas can), or extend `isContent` to count a
control's own label-and-gutter row — e.g. treat a sample as content when it is inside an element
that contains a control within `--row-h`. Both are program-level calls, not a lane's.

## Cross-lane needs (exact diffs — I did not edit files I do not own)

**1. `desktop/src/renderer/pages/simulator/FlexTab.tsx` (lane B2)** — the last dead route:

```diff
@@ -62,7 +62,7 @@
           icon={<Waypoints size={24} />}
           message="No flex-search runs for the selected subjects yet."
-          actionLabel="Go to Optimizer · Flex-search"
-          onAction={() => navigate("/optimizer-flex")}
+          actionLabel="Go to Optimizer"
+          onAction={() => navigate("/optimizer")}
         />
```

**2. `desktop/tests/unit/shell-registry.test.ts` (lane B1) — no change needed, verified.**
`LEGACY_SLOT` already maps `optimizer-flex → optimizer` and retires the stand-in the moment
`pages/optimizer` is discovered; `optimizer-ex` has no slot. `smoke.spec.ts` already asserts
`nav-item-optimizer-ex` has count 0. `app/registry.ts` needs nothing.

**3. `desktop/tests/unit/forms-ajvResolver.test.ts` — I edited it (imports only), flagged here.**
It imported `pages/optimizer-ex/{ExForm,lib}`, which this lane deletes, so leaving it would have
made `npm run typecheck` and `npx vitest run` fail for *every* lane. The change is three lines:

```diff
-import { buildExConfig, DEFAULT_EX_FORM } from "../../src/renderer/pages/optimizer-ex/ExForm";
-import { sphereRoiTargets } from "../../src/renderer/pages/optimizer-ex/lib";
+import { buildExConfig, defaultExFormState, savedTargets } from "../../src/renderer/pages/optimizer/exConfig";
@@
-    const target = sphereRoiTargets(["Thalamus_target"], false)[0]!;
-    const form = { ...DEFAULT_EX_FORM, buckets: { … } };
-    const config = buildExConfig("ernie", "…/leadfield.hdf5", form, target);
+    const target = savedTargets(["Thalamus_target"], false)[0]!;
+    const form = { ...defaultExFormState(), buckets: { … } };
+    const config = buildExConfig("ernie", "…/leadfield.hdf5", form, target, "");
```

**4. Shared-CSS observation for B1/B2 (not fixed here, scoped around instead).**
`.run-work`'s `@container (max-width: 760px)` collapse fires at 1440×900 on every shape-A page —
`--page-pad` 24 takes the container to ~722 px — so Pre-processing, Simulator, Analyzer and the
Optimizer are all **single-column at 1440**, which §2.1 says should be the two-up size. The
Optimizer works around it page-locally (`@container (min-width: 700px)`, honest because its label
column is 128 px, not 160). The general fix belongs in `run.css` or in `--page-pad`.

## Gates

- `npm run typecheck` — clean for every file this lane owns (`grep -E "optimizer|_shared/roi"`
  empty). The run as a whole still reports errors from in-flight files owned by other lanes:
  `tests/unit/viewer-{page,store}.test.ts`, `src/renderer/pages/help/KeyboardTab.tsx`,
  `tests/unit/outputsTree-build.test.ts`.
- `npm run lint` — clean for this lane's files (`npx eslint` over them: no output). The suite's one
  error is `tests/e2e/subjects.spec.ts`'s unused `gotoPage` import (lane B4).
- `npx vitest run` — **53 files, 577 tests, all passing**, including this lane's
  `optimizer-cost` (12), `optimizer-roi` (9), `optimizer-ex` (7), `optimizer-flexconfig` (8).
- `npm run build` — green.
- `TIT_E2E_RUN_ID=b3-r3b-23583 bash scripts/e2e-quiet-check.sh npx playwright test
  tests/e2e/optimizer.spec.ts` — **6 passed**, `PASS`, no Electron window reached the screen.

## Files

Added: `desktop/src/renderer/pages/optimizer/{index.tsx, api.ts, flexConfig.ts, exConfig.ts,
cost.ts, FlexSections.tsx, ExSections.tsx, optimizer.css, PARITY.md}`;
`desktop/tests/e2e/optimizer.spec.ts`; `desktop/tests/unit/{optimizer-cost,optimizer-roi}.test.ts`.
Changed: `desktop/src/renderer/pages/_shared/roi/{types.ts, api.ts, RoiPicker.tsx}` (the `saved`
mode); `desktop/tests/unit/{optimizer-ex,optimizer-flexconfig}.test.ts` (renamed from
`optimizer-ex-defaults` / `optimizer-flex`); `desktop/tests/unit/forms-ajvResolver.test.ts`
(imports only, see above).
Deleted: `desktop/src/renderer/pages/optimizer-flex/**`, `desktop/src/renderer/pages/optimizer-ex/**`,
`desktop/tests/e2e/{optimizer-flex,optimizer-ex}.spec.ts`.

Artifacts (screens + metrics, both themes, both sizes):
`desktop/tests/e2e/artifacts/b3-r1c-29431/`, `b3-r2-949/`, `b3-r2b-29533/`, `b3-r3b-23583/`.
