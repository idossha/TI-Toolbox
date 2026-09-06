# Judge 3 — staff front-end engineer lens (feasibility / risk / testability)

Verdict: **workflow-first (35) > density-first (33) > viewer-centric (27)**.

Read in full: all three proposals, `desktop/DESIGN.md`, `r2-v3-renderer-map.md`, `r1-tetravox-embed.md` §0–1.
Viewed: `simulator-light.png`, `viewer-light.png`, `optimizer-flex-spherical-light.png`,
`analyzer-cortical-light.png`, `jobs-light.png`, `results-light.png`, `panel-source-light.png`,
`preprocess-light.png`.

---

## 1. The measurement that reorders the field

All three proposals delete the Viewer's hand-rolled Layers editor
(`desktop/src/renderer/pages/viewer/index.tsx:751`) on the promise that Tetravox's own layer panel,
histogram, coordinate bar, info panel and region table replace it for free. **That is false as
stated, and I measured it.**

- `@tetravox/engine` ships **zero React**: `find /Users/idohaber/00_development/tetravox/packages/engine/src -name '*.tsx'` → **0**.
  R1 corroborates by grep (`r1-tetravox-embed.md:13-20`): the engine imports no React and exposes one
  entry, `create(canvas, opts)` (`packages/engine/src/api.ts:675-679`).
- The chrome lives in `packages/app/src/renderer/src/panels/**` and is **9,345 LOC of React**:
  layers 6,073 · regions 1,747 · histogram 777 · info 469 · coordinate 180 · measure 99.

Consequence: under the in-renderer `create(canvas)` route (density-first §7, viewer-centric §10 step 3)
that chrome must be **rebuilt in TI's own design system**. Under a whole-app embed
(workflow-first §4.6's `WebContentsView`) it comes free — but for a reason workflow-first never gives.

Second measurement: `git ls-files packages/wasm/pkg` returns only `tvx_wasm.d.ts`. The 848 KB
`tvx_wasm_bg.wasm` is git-ignored and `npm pack` drops it (`r1-tetravox-embed.md:36-40`).
**Tetravox is not installable into `desktop/` today** without a one-line upstream fix to
`scripts/build-wasm.sh`. Any IA whose *shell* has a canvas-shaped hole in every screen cannot ship
until that lands.

---

## 2. Scores

| | clarity | compactness | workflow_fit | feasibility | total |
|---|---|---|---|---|---|
| workflow-first | 9 | 8 | 10 | 8 | **35** |
| density-first | 9 | 10 | 7 | 7 | **33** |
| viewer-centric | 8 | 8 | 7 | 4 | **27** |

### workflow-first — 35

Feasibility is the reason it wins, not the lens. Its §7.3 migration table is **component-level**:
each row names a source file and a destination slot, and says "unchanged" 14 times
(`ConductivityDialog`, `MontageManager`, `FlexTab`, `FreehandTab`, `ElectrodeBuckets`, `RoiPicker`,
`QsiPrepDialog`, `SubjectPicker`, `PlanSummary`, the `catalog.py` calls). For parallel agents on a
one-day budget that is the difference between "move this into that slot" and "rewrite this".

It explicitly preserves the discovery mechanism every agent depends on — "`registry.ts:29`'s
`import.meta.glob` discovery is preserved exactly" (§2.1 rule 3), with the nav change reduced to a
`PageDef.navGroup` field edit plus the hand-maintained `GROUP_LABEL` map at `NavRail.tsx:7-14`.
That matches `r2-v3-renderer-map.md` §3.2 exactly.

§7.4 "**None are required to ship the IA**", with both optional endpoints labelled convenience-only,
is the best risk posture of the three and is verifiable against `contracts/openapi.v1.yaml`.

The Workbench (§4.2) is the only screen in any proposal that answers the maintainer's actual
complaint. A PyQt transcription has no notion of *where a subject is*; four stage cards with
`● ◐ ◑ ○` state, derived entirely from existing catalog calls (`catalog.py:203-213`, `:71-99`,
`:831`), plus NEEDS ATTENTION, is that notion. It is also self-contained — one agent, one directory.

Weaknesses: §4.7 deletes the Jobs route entirely (see rejection 7); §4.6's Tetravox reasoning is
wrong (rejection 1); compaction is real but less rigorous than density-first's.

### density-first — 33

The best-evidenced document of the three. Its §0 table derives the 674 px work column at 1280 from
four cited rules (`shell.css:14` + `shell.css:178` + `components.css:1385` + `:1373`) and the 94 px
per-section chrome from `components.css:841,849`. That is an acceptance metric, not an argument.

§13's build order is the single best sequencing idea in any proposal: tokens and primitives first,
verified in `dev/Gallery.tsx` (661 LOC, every primitive side by side), **with no page-file changes in
that commit**. That decouples the F2-owned design system from the P1–P8 page lanes, which is exactly
the coupling that produced the duplication catalogued in `r2-v3-renderer-map.md` §6 (7× `getSimulationsFor`,
2 ROI pickers, 2 PlanSummary vocabularies, 5 PlanPanel shells).

Feasibility costs it a point against workflow-first on three specifics it does not mention:
`tests/unit/cssRules.test.ts:29-49,52-77` asserts the `@media (max-width:1099px)` and
`(max-width:1199px)` blocks **as text and in source order**, and both are deleted by §2;
`navBrandMark.test.tsx:45-55` mocks `useNavGroups` and asserts the `.nav-brand` DOM that the
always-56px rail removes; and the min-window change to 1120×720 crosses into `main/index.ts:330-331`
(P9 lane). All fixable, none free.

Workflow fit is where it genuinely trails: nine rail items are verbs and the merges are right, but
nothing in it tells a researcher what to do next for ernie. Its Project inspector (Recent + four verb
buttons, §6.1) is the closest it gets.

### viewer-centric — 27

The most intellectually coherent and the least buildable in a day.

Its best passages are genuinely the best in the field. §7.1's model join — `RoiRegion.id`
(`pages/_shared/roi/types.ts:26-30`) is already the atlas label index, and a Tetravox `LabelTable` is
keyed by exactly that, so the two join with **no translation layer** — is the single most valuable
specific insight in any proposal. §8.4 (no WebGL2) is the only real risk section anyone wrote, and
its corollary rule (`⊕ Pick in viewer` is always an *additional* affordance beside a live x/y/z row)
is the rule that makes viewer-driven input safe. §11's ten-item preservation list is the best
non-goals section of the three.

But the feasibility gap is structural, not fixable by scoping:

1. **The shell is 7 new regions** (activity bar, run bar, task panel, canvas, inspector, dock, status
   bar) replacing a 3-region flex shell (`shell.css:3-10`). `r2-v3-renderer-map.md` §4.7: there is
   **no canvas primitive, no full-bleed container, and no split-view primitive other than
   `ResizablePanels`**.
2. **Every task panel is rewritten, not relocated.** §4.1's one-at-a-time numbered step accordion at
   §4.3 rule 1's "never a 2-column field grid in a 360 px panel" means `RoiPicker` (327 LOC),
   `ExForm`, `MExForm`, `ElectrodeBuckets`, `SphereRows`, `ElectrodeParams`, `HyperParams`,
   `FocalityOptions` — all built for the ~660 px two-column grid visible in
   `optimizer-flex-spherical-light.png` — are re-laid-out by their page agents.
3. **The canvas is the premise.** It deletes the Viewer page (§2.1 "There is **no** Viewer nav item")
   and mounts the canvas at app start. Against §1's packaging blocker, its own build sequence step 1
   ships "a placeholder canvas": a 360 px form column beside an empty 840 px rectangle — visibly
   worse than `simulator-light.png` today.
4. **It is already degraded at its own reference width.** 56 + 360 + 320 = 736; at 1280 that leaves
   544 px against its own 640 px canvas floor, so §3.3's ladder collapses the inspector to a 40 px
   strip at 1240–1399. The inspector is where §3.5 puts the entire viewer UI, and 1280 is the width
   DESIGN.md §8 mandates for the committed screenshot suite.
5. It adopts the `create(canvas)` route (§10 step 3) while treating the inspector as "Tetravox's right
   column, adopted verbatim… re-inventing it would be a bug factory" (§3.5) — i.e. it picked the
   embed route that does **not** deliver the 9,345 LOC it plans to adopt.

---

## 3. Grafts and rejections

See the structured result. Fourteen grafts (eight from density-first, six from viewer-centric),
eight rejections.
